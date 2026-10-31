"""GitHub configuration PRs via Git Data API; no shell, arbitrary code or bypass.

Coupled mode exports reviewed candidates and gates publication on the verified
merge. Explicit legacy separate mode exports published revisions. Protected main
and exact head/base checks gate merging; source changes use developer CI.
"""

import base64
import json
import os
import re
from urllib.parse import quote

import requests

from .store import AdminError, encode
from .runtime import secret


class GitHub:
    def __init__(self):
        self.repo = os.getenv("ADMIN_GITHUB_REPOSITORY", "")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repo):
            raise AdminError("ADMIN_GITHUB_REPOSITORY als owner/repo konfigurieren")
        self.branch = os.getenv("ADMIN_GITHUB_BASE", "main")
        if not re.fullmatch(r"[A-Za-z0-9_-]+", self.branch):
            raise AdminError("Ungueltiger Basisbranch")
        self.token = secret("ADMIN_GITHUB_TOKEN")
        if not self.token:
            raise AdminError("GitHub-Token fehlt")

    def call(self, method, path, value=None, *, missing=False):
        response = requests.request(
            method,
            "https://api.github.com/repos/" + self.repo + path,
            json=value,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30,
            allow_redirects=False,
        )
        if missing and response.status_code == 404:
            return None
        if not 200 <= response.status_code < 300:
            raise AdminError(
                f"GitHub verweigert {method} ({response.status_code}); Repository-Rechte/Schutzregeln pruefen"
            )
        return response.json() if response.content else {}


PROTECTION_MODES = ("produktiv", "entwicklung")
# Conclusions that count as "did not fail". A skipped job (the Windows run is
# main-only) is not a failure, but it is no evidence either - at least one
# run must have succeeded.
PASSING = {"success", "skipped", "neutral"}


def protection_mode():
    """ADMIN_GIT_SCHUTZ; missing means produktiv, so a typo never loosens it."""
    value = os.getenv("ADMIN_GIT_SCHUTZ", "produktiv")
    if value not in PROTECTION_MODES:
        raise AdminError("ADMIN_GIT_SCHUTZ muss produktiv oder entwicklung sein, nicht " + repr(value))
    return value


def check_protection(gh, commit_sha):
    """Gate before any merge; returns the mode it checked under.

    produktiv: main must carry GitHub's branch protection - strict status
    checks, one approving review, stale reviews dismissed, admins included.
    GitHub then enforces CI and review itself.

    entwicklung: while the project is still being built, main stays
    unprotected so its developers can push. The console then checks what
    the protection would have enforced on its own PR: every GitHub Actions
    run on the exact head commit completed without failure, and at least one
    passed. Without that, it would merge unchecked into an unprotected main.
    Workflow runs, not check runs: the check-runs endpoint takes only GitHub
    App tokens, and the console holds a fine-grained personal token, which
    reads workflow runs with "Actions: read" (GitHub REST docs, "List check
    runs for a Git reference" and "List workflow runs for a repository").
    """
    mode = protection_mode()
    if mode == "produktiv":
        protection = gh.call("GET", "/branches/" + gh.branch + "/protection", missing=True) or {}
        checks = protection.get("required_status_checks") or {}
        reviews = protection.get("required_pull_request_reviews") or {}
        if (
            not checks.get("strict")
            or not (checks.get("contexts") or checks.get("checks"))
            or reviews.get("required_approving_review_count", 0) < 1
            or not reviews.get("dismiss_stale_reviews")
            or not protection.get("enforce_admins", {}).get("enabled")
        ):
            raise AdminError(
                "Main braucht strikte CI, Review, veraltete Reviews verwerfen und Admin-Schutz "
                "(oder ADMIN_GIT_SCHUTZ=entwicklung waehrend der Entwicklung)"
            )
        return mode
    runs = gh.call("GET", "/actions/runs?head_sha=" + commit_sha + "&per_page=100").get(
        "workflow_runs") or []
    open_or_failed = sorted(
        r.get("name", "?") for r in runs
        if r.get("status") != "completed" or r.get("conclusion") not in PASSING
    )
    if not runs or open_or_failed or not any(r.get("conclusion") == "success" for r in runs):
        raise AdminError(
            "Entwicklungsmodus: CI auf dem PR-Head nicht gruen"
            + (" (" + ", ".join(open_or_failed) + ")" if open_or_failed else " (kein Lauf)")
            + "; kein Merge"
        )
    return mode


def approved(store, rid):
    from .candidates import active_id, checked_impact, verify_release, release_path, file_hash

    r = store.get(rid)
    if r["resource"] not in {"mapping", "settings"}:
        raise AdminError("Git-Export nur fuer Mapping und Konfiguration")
    with store.db() as c:
        decision = c.execute(
            "SELECT * FROM decision WHERE revision=? AND decision='approve'", (rid,)
        ).fetchone()
        row = (
            c.execute("SELECT * FROM impact WHERE id=?", (decision["impact_id"],)).fetchone()
            if decision
            else None
        )
    from .release_flow import requires_git, verify_waiting

    if (
        row
        and requires_git(dict(row), r)
        and row["status"] in {"AWAITING_GIT", "APPROVED_PENDING_PUBLICATION"}
    ):
        row = dict(row)
        report, _archive = verify_waiting(store, row)
        if decision["impact_report_sha256"] != row["report_hash"] or not report["metadata"].get(
            "git_provenance"
        ):
            raise AdminError("Git-/Review-Nachweis fehlt")
        return r, row
    if not row or row["status"] != "PUBLISHED" or store.current(r["resource"])["id"] != rid:
        raise AdminError("Nur aktuell freigegebene Revisionen exportieren")
    row = dict(row)
    if active_id(store) != row["published_release_id"]:
        raise AdminError("Releasebasis veraendert; aktuellen Vorschlag verwenden")
    report = checked_impact(store, row)
    if not report["review_ready"] or decision["impact_report_sha256"] != row["report_hash"]:
        raise AdminError("Gepruefter Impact-Nachweis fehlt")
    published = release_path(store, row["published_release_id"])
    verify_release(published)
    if file_hash(published / "release.json") != row["published_manifest_hash"]:
        raise AdminError("Release-Nachweis veraendert")
    return r, row


def saved(store, rid):
    from .operations import schema

    schema(store)
    with store.db() as c:
        row = c.execute("SELECT document FROM git_change WHERE revision=?", (rid,)).fetchone()
    return json.loads(row[0]) if row else None


def save(store, d):
    with store.db() as c:
        c.execute(
            "INSERT OR REPLACE INTO git_change VALUES (?,?,?)",
            (d["revision"], d["state"], encode(d)),
        )


def changes(store, r):
    before = store.get(r["parent"])["payload"]
    after = r["payload"]
    if r["resource"] == "mapping":
        result = {}
        for name in sorted(set(before) | set(after)):
            if not re.fullmatch(r"[a-z0-9_]+\.csv", name):
                raise AdminError("Ungueltiger Mappingpfad")
            if before.get(name) != after.get(name):
                if name not in before or name not in after:
                    raise AdminError("Dateianlage/-loeschung erfordert Entwicklerreview")
                result["config/" + name] = (before[name], after[name])
        return result
    return {"config/platform_admin_settings.json": (encode(before) + "\n", encode(after) + "\n")}


def open_pr(store, rid, actor, client=None):
    r, impact = approved(store, rid)
    gh = client or GitHub()
    from .release_flow import requires_git

    coupled = requires_git(impact, r)
    report = None
    archived = None
    if coupled:
        from .release_flow import verify_waiting

        report, archived = verify_waiting(store, impact)
    d = saved(store, rid)
    if d and d.get("number"):
        return d
    if not d:
        base = gh.call("GET", "/git/ref/heads/" + gh.branch)["object"]["sha"]
        if coupled:
            provenance = report["metadata"]["git_provenance"]
            if (provenance["repository"], provenance["base_branch"], provenance["base_sha"]) != (
                gh.repo,
                gh.branch,
                base,
            ):
                raise AdminError(
                    "Main/Repository seit Simulation veraendert; Review zurueckziehen und neu simulieren"
                )
        d = {
            "revision": rid,
            "repository": gh.repo,
            "base_branch": gh.branch,
            "base_sha": base,
            "branch": "engineering/" + rid,
            "report_hash": impact["report_hash"],
            "release_id": impact["published_release_id"] or impact["candidate_release_id"],
            "impact_id": impact["id"],
            "candidate_manifest_hash": impact["candidate_manifest_hash"],
            "archive_hash": archived["manifest_hash"] if archived else None,
            "coupled": coupled,
            "requested_by": actor,
            "state": "PREPARING",
        }
        save(store, d)
    if d["repository"] != gh.repo or d["base_branch"] != gh.branch:
        raise AdminError("Repository-Ziel seit Vorbereitung veraendert")
    if gh.call("GET", "/git/ref/heads/" + gh.branch)["object"]["sha"] != d["base_sha"]:
        raise AdminError("Main wurde veraendert; Git-Vorschlag neu abgleichen")
    diff = changes(store, r)
    if not diff:
        raise AdminError("Keine Git-Aenderungen")
    if not d.get("commit_sha"):
        entries = []
        for path, (before, after) in diff.items():
            item = gh.call("GET", "/contents/" + path + "?ref=" + d["base_sha"], missing=True)
            current = base64.b64decode(item["content"]).decode("utf-8-sig") if item else None
            # Settings absent on the very first import: baseline explicitly equals defaults.
            from .store import DEFAULT_SETTINGS

            first_settings = (
                path.endswith("platform_admin_settings.json")
                and current is None
                and json.loads(before) == DEFAULT_SETTINGS
            )
            equal = (
                (json.loads(current) == json.loads(before))
                if current and path.endswith(".json")
                else (current or "").replace("\r\n", "\n") == before.replace("\r\n", "\n")
            )
            if not equal and not first_settings:
                raise AdminError(
                    "Git-Konflikt an " + path + ": Repository weicht von Vorschlagsbasis ab"
                )
            entries.append({"path": path, "mode": "100644", "type": "blob", "content": after})
        evidence = {
            "revision_id": rid,
            "impact_id": impact["id"],
            "report_sha256": impact["report_hash"],
            "release_id": impact["published_release_id"],
            "author": r["actor"],
            "reason": r["reason"],
            "git_protection": protection_mode(),
        }
        entries.append(
            {
                "path": "config/admin_reviews/" + rid + ".json",
                "mode": "100644",
                "type": "blob",
                "content": encode(evidence) + "\n",
            }
        )
        commit = gh.call("GET", "/git/commits/" + d["base_sha"])
        tree = gh.call("POST", "/git/trees", {"base_tree": commit["tree"]["sha"], "tree": entries})
        new = gh.call(
            "POST",
            "/git/commits",
            {
                "message": "Engineering review "
                + rid
                + "\n\nImpact SHA256: "
                + impact["report_hash"],
                "tree": tree["sha"],
                "parents": [d["base_sha"]],
            },
        )
        d.update(commit_sha=new["sha"], commit_tree=tree["sha"], state="COMMITTED")
        save(store, d)
    ref = gh.call("GET", "/git/ref/heads/" + d["branch"], missing=True)
    if ref:
        if ref["object"]["sha"] != d["commit_sha"]:
            raise AdminError("Vorschlagsbranch extern veraendert; kein Force-Push")
    else:
        gh.call("POST", "/git/refs", {"ref": "refs/heads/" + d["branch"], "sha": d["commit_sha"]})
    prs = gh.call(
        "GET",
        "/pulls?state=all&head="
        + quote(gh.repo.split("/")[0] + ":" + d["branch"], safe="")
        + "&base="
        + gh.branch,
    )
    pr = (
        prs[0]
        if prs
        else gh.call(
            "POST",
            "/pulls",
            {
                "title": "Engineering-Konfiguration " + rid[:12],
                "head": d["branch"],
                "base": gh.branch,
                "body": "Freigegebene Konfiguration.\n\n"
                + "Git-Schutz: " + protection_mode() + "\n\n"
                + json.dumps(
                    evidence
                    if "evidence" in locals()
                    else {"revision": rid, "report_sha256": d["report_hash"]},
                    ensure_ascii=False,
                    indent=2,
                )
                + (
                    "\n\nGekoppelte Freigabe: Daten bleiben inaktiv bis zum verifizierten Merge.\n"
                    + report.get("summary_text", "")
                    + "\nArchiv SHA256: "
                    + archived["manifest_hash"]
                    + (
                        "\nImpact/Download (Anmeldung erforderlich): "
                        + os.environ["ADMIN_PUBLIC_ORIGIN"].rstrip("/")
                        + "/?impact="
                        + impact["id"]
                        if os.getenv("ADMIN_PUBLIC_ORIGIN")
                        else ""
                    )
                    if coupled
                    else "\n\nGetrennter Entwicklungsmodus: Repository-CI und Review erforderlich."
                ),
            },
        )
    )
    if pr["head"]["sha"] != d["commit_sha"] or pr["base"]["ref"] != gh.branch:
        raise AdminError("PR passt nicht zum vorbereiteten Commit")
    d.update(
        number=pr["number"],
        url=pr["html_url"],
        state="PR_OPEN" if pr["state"] == "open" else "CLOSED",
    )
    save(store, d)
    return d


def merge_pr(store, rid, actor, client=None):
    r, impact = approved(store, rid)
    from .release_flow import requires_git

    if requires_git(impact, r):
        from .coupled_git import merge

        return merge(store, r, impact, actor, client=client)
    if actor.casefold() == r["actor"].casefold():
        raise AdminError("Merge muss durch zweite Person erfolgen")
    gh = client or GitHub()
    d = saved(store, rid)
    if not d or not d.get("number") or d["report_hash"] != impact["report_hash"]:
        raise AdminError("Passender PR fehlt")
    if d["repository"] != gh.repo or d["base_branch"] != gh.branch:
        raise AdminError("Repository-Ziel veraendert")
    pr = gh.call("GET", "/pulls/" + str(d["number"]))
    if pr["head"]["sha"] != d["commit_sha"] or pr["base"]["ref"] != gh.branch:
        raise AdminError("PR-Head/Basis veraendert; neue Pruefung erforderlich")
    if pr.get("merged"):
        d.update(state="MERGED", merge_sha=pr["merge_commit_sha"])
        save(store, d)
        return d
    d["git_protection"] = check_protection(gh, d["commit_sha"])
    if (
        gh.call("GET", "/git/ref/heads/" + gh.branch)["object"]["sha"] != d["base_sha"]
        or pr.get("base", {}).get("sha") != d["base_sha"]
    ):
        raise AdminError("Main seit Impact-Export veraendert; kein automatischer Merge")
    if (
        pr.get("state") != "open"
        or pr.get("draft")
        or pr.get("mergeable") is not True
        or pr.get("mergeable_state") != "clean"
    ):
        raise AdminError("PR nicht mergebereit: CI, Reviews oder Konflikte pruefen")
    # Server enforces required checks and reviews atomically. Exact head prevents
    # merging a different commit; strict protected branch prevents outdated bases.
    result = gh.call(
        "PUT",
        "/pulls/" + str(d["number"]) + "/merge",
        {"sha": d["commit_sha"], "merge_method": "squash"},
    )
    if not result.get("merged"):
        raise AdminError("GitHub hat den Merge nicht ausgefuehrt")
    d.update(state="MERGED", merge_sha=result["sha"], merged_by=actor)
    save(store, d)
    return d
