"""Release policy, pinned build provenance and append-only lifecycle events."""

import hashlib
import base64
import importlib.metadata
import json
import os
import uuid
from pathlib import Path

from .store import AdminError, DEFAULT_SETTINGS, digest, encode, now


def mode():
    value = os.getenv("ADMIN_RELEASE_MODE", "coupled")
    if value not in {"coupled", "separate"}:
        raise AdminError("ADMIN_RELEASE_MODE muss coupled oder separate sein")
    return value


def requires_git(row, revision):
    return revision["resource"] in {"mapping", "settings"} and (
        json.loads(row["spec"]).get("release_policy") == "coupled" or mode() == "coupled"
    )


def event(c, row, action, actor, reason, evidence=None):
    c.execute(
        "INSERT INTO release_event VALUES (?,?,?,?,?,?,?,?)",
        (
            uuid.uuid4().hex,
            row["revision_id"],
            row["id"],
            action,
            actor,
            reason,
            now(),
            encode(evidence or {}),
        ),
    )


def blob_hash(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def in_scope(path):
    p = Path(path)
    return (
        (
            path.startswith("src/crime/")
            and not any(x in {"__pycache__", ".pytest_cache"} for x in p.parts)
            # pip install -e legt es im Abbild an; in Git steht es nie.
            and not any(x.endswith(".egg-info") for x in p.parts)
            and p.suffix not in {".pyc", ".pyo"}
        )
        or (
            path.startswith("config/")
            and not path.startswith("config/admin_reviews/")
            and path != "config/platform_admin_settings.json"
        )
        or path in {"pyproject.toml", "requirements.txt", "requirements.lock",
                    "requirements-admin.lock", "Dockerfile", "Dockerfile.admin"}
    )


def source_inventory(project):
    """Blob hashes of every in-scope file below ``project``, as Git names them."""
    project = Path(project)
    result = {}
    for folder in ("src/crime", "config"):
        for p in sorted((project / folder).rglob("*")):
            rel = p.relative_to(project).as_posix()
            if p.is_file() and in_scope(rel):
                if p.is_symlink():
                    raise AdminError("Symlink im Build-Quellstand")
                result[rel] = blob_hash(p.read_bytes())
    for name in ("pyproject.toml", "requirements.txt"):
        p = project / name
        if not p.is_file():
            raise AdminError("Builddatei fehlt: " + name)
        result[name] = blob_hash(p.read_bytes())
    for name in ("requirements.lock", "requirements-admin.lock", "Dockerfile", "Dockerfile.admin"):
        p = project / name
        if p.is_file():
            result[name] = blob_hash(p.read_bytes())
    return result


def tree_mismatch(project, ls_tree):
    """Paths where ``project`` and ``git ls-tree -r`` output disagree.

    The image check in ``.github/workflows/abbilder.yml`` runs this inside the
    freshly built image: an impact job attests the worker against main with
    the same comparison, and on 3.11.2026 the first one on srv01 failed
    because the image never carried requirements.txt.
    """
    tree = {}
    for line in ls_tree.splitlines():
        meta, _, path = line.partition("\t")
        kind, sha = meta.split()[1:3]
        if kind == "blob" and in_scope(path):
            tree[path] = sha
    actual = source_inventory(project)
    return sorted(p for p in actual.keys() | tree.keys() if actual.get(p) != tree.get(p))


def inventory(store, spec):
    result = source_inventory(store.project)
    for name, text in store.get(spec["base_heads"]["mapping"])["payload"].items():
        result["config/" + name] = blob_hash(text.encode())
    return result


def capture(store, spec, client=None):
    """Compare the runtime sources and active mappings to an exact Git main tree."""
    from .gitops import GitHub

    gh = client or GitHub()
    base = gh.call("GET", "/git/ref/heads/" + gh.branch)["object"]["sha"]
    tree = gh.call("GET", "/git/trees/" + base + "?recursive=1")
    if tree.get("truncated"):
        raise AdminError("Git-Baum unvollstaendig; Build nicht attestierbar")
    expected = inventory(store, spec)
    actual = {
        i["path"]: i["sha"] for i in tree["tree"] if i["type"] == "blob" and in_scope(i["path"])
    }
    mismatch = sorted(
        p for p in expected.keys() | actual.keys() if expected.get(p) != actual.get(p)
    )
    if mismatch:
        raise AdminError(
            "Worker/aktive Konfiguration entspricht nicht Main: "
            + ", ".join(mismatch[:8])
            + ". Geprueften Code deployen und Konfiguration abgleichen."
        )

    settings = store.get(spec["base_heads"]["settings"])["payload"]
    item = gh.call("GET", "/contents/config/platform_admin_settings.json?ref=" + base, missing=True)
    if item:
        if json.loads(base64.b64decode(item["content"])) != settings:
            raise AdminError("Aktive Settings weichen von Main ab")
    elif settings != DEFAULT_SETTINGS:
        raise AdminError("Aktive Settings fehlen in Main; Migration zuerst abgleichen")
    versions = {}
    for package in ("duckdb", "pyarrow", "pandas", "pyogrio"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "unavailable"
    return {
        "repository": gh.repo,
        "base_branch": gh.branch,
        "base_sha": base,
        "source_blobs": expected,
        "source_sha256": digest(expected),
        "dependencies": versions,
    }


def check_build_unchanged(store, spec, provenance):
    if inventory(store, spec) != provenance["source_blobs"]:
        raise AdminError("Build-Quellen waehrend Simulation veraendert; erneut simulieren")


def verify_waiting(store, row, *, publication=False):
    """No local activation/config mutation since the reviewed simulation."""
    from .candidates import active_id, checked_impact, file_hash, release_path, verify_release
    from .impact_archive import checked

    spec = json.loads(row["spec"])
    with store.db() as c:
        heads = dict(c.execute("SELECT resource,revision FROM head").fetchall())
    if heads != spec["base_heads"] or active_id(store) not in (
        {row["baseline_release_id"], row["published_release_id"]}
        if publication
        else {row["baseline_release_id"]}
    ):
        raise AdminError("Baseline seit Review veraendert; neuer Impact erforderlich")
    report = checked_impact(store, row)
    if not report.get("review_ready"):
        raise AdminError("Quality Gates nicht bestanden")
    archived, manifest = checked(
        store, row["id"], require_remote=os.getenv("ADMIN_OBJECT_STORE", "local") == "s3"
    )
    if manifest["report_hash"] != row["report_hash"]:
        raise AdminError("Archiv und Review stimmen nicht ueberein")
    if row["baseline_release_id"]:
        baseline = release_path(store, row["baseline_release_id"])
        verify_release(baseline)
        if file_hash(baseline / "release.json") != report["metadata"]["baseline_manifest_sha256"]:
            raise AdminError("Baseline-Nachweis veraendert")
    return report, archived


if __name__ == "__main__":
    import sys

    # git ls-tree -r HEAD | python -m platform_admin.release_flow /app
    mismatched = tree_mismatch(sys.argv[1] if len(sys.argv) > 1 else ".", sys.stdin.read())
    for path in mismatched:
        print(path)
    sys.exit(1 if mismatched else 0)
