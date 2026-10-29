"""Single-host bridge to the existing storage and orchestration contracts.

The marker protects managed CLI entrypoints even when an old cron command
forgets its environment. It is not an OS permission boundary.
"""
import hashlib
import json
import os
import shutil
from datetime import date, timedelta
from pathlib import Path

from storage import for_root
from storage.managed import managed
from .store import AdminError, encode


def scope_years(settings):
    start = date.fromisoformat(settings["scope_start"])
    end = date.fromisoformat(settings["scope_end_exclusive"]) - timedelta(days=1)
    return tuple(range(start.year, end.year + 1))


def manifest_paths(store, city):
    return for_root(store.data).list_files(f"bronze/city={city}", "**/manifest.json")


def manifest_text(store, relative):
    # Caller must validate any path originating in an HTTP request.
    return for_root(store.data).read_text(relative)


def remote_snapshot(store, target):
    storage = for_root(store.data)
    if storage.backend == "local":
        return None
    if storage.backend != "s3":
        raise AdminError("Kandidaten mit Remote-Quellen verlangen STORAGE_BACKEND=s3; "
                         "hybrid mit lokalem Vorrang ist fuer Freigaben nicht eindeutig.")
    manifests = storage.list_files("bronze", "**/manifest.json")
    before = {p: storage.read_text(p) for p in manifests}
    if not before:
        raise AdminError("Keine Bronze-Manifeste in S3. Zuerst Quellen ingestieren.")
    destination = storage.mit_wurzel(target)
    required = sum(storage.groessen_unter("bronze").values())
    if shutil.disk_usage(target).free < required:
        raise AdminError(f"Bronze-Snapshot braucht mindestens {required} freie Bytes; "
                         "zusaetzlich Platz fuer Silver, Gold und Release vorsehen.")
    for rel, raw in before.items():
        value = json.loads(raw)
        if str(value.get("status", "")).lower() not in {"complete", "success"}:
            continue
        # Empty target prevents stale-cache shortcuts in Storage.hole.
        run_dir = str(Path(rel).parent).replace("\\", "/")
        for key in storage.list_files(run_dir):
            if hasattr(storage.client, "download"):
                expected = storage.client.head(key)
                out = destination.local_path(key)
                out.parent.mkdir(parents=True, exist_ok=True)
                temporary = out.with_name("." + out.name + ".part")
                storage.client.download(key, temporary)
                if expected is None or temporary.stat().st_size != expected.size:
                    raise AdminError("S3-Snapshotdownload unvollstaendig: " + key)
                from storage.backend import etag_md5
                md5 = etag_md5(expected.etag)
                if md5:
                    digest = hashlib.md5()
                    with temporary.open("rb") as stream:
                        for block in iter(lambda: stream.read(1 << 20), b""):
                            digest.update(block)
                    if digest.hexdigest() != md5:
                        raise AdminError("S3-Snapshotpruefsumme abweichend: " + key)
                temporary.replace(out)
            else:
                destination.hole(key)
    after = {p: storage.read_text(p) for p in storage.list_files("bronze", "**/manifest.json")}
    if before != after:
        raise AdminError("S3-Bronze hat sich waehrend des Snapshots geaendert; erneut starten.")
    from .candidates import file_hash

    files = {p.relative_to(target / "bronze").as_posix(): file_hash(p)
             for p in sorted((target / "bronze").rglob("*")) if p.is_file()}
    for rel, raw in before.items():
        p = target / rel
        if p.exists() and p.read_text(encoding="utf-8") != raw:
            raise AdminError("Heruntergeladenes Bronze-Manifest weicht vom Snapshot ab.")
    if not files:
        raise AdminError("Kein vollstaendiger Bronze-Lauf in S3.")
    return {"files": files, "sha256": hashlib.sha256(encode(files).encode()).hexdigest(),
            "origin": "s3", "manifest_count": len(before)}


def copy_history(store, target, baseline):
    rel = "silver/dataset=source_change"
    if baseline and (baseline / rel).exists():
        shutil.copytree(baseline / rel, target / rel)
        return
    storage = for_root(store.data)
    if storage.backend == "local":
        if (store.data / rel).exists():
            shutil.copytree(store.data / rel, target / rel)
    elif storage.exists(rel + "/manifest.json"):
        destination = storage.mit_wurzel(target)
        for p in storage.list_files(rel):
            destination.hole(p)


def reconcile_serving(store):
    """Durable outbox reconciliation, also after publication/worker crash."""
    from .operations import schema, submit
    from .candidates import active_id, release_path

    if os.getenv("ADMIN_AUTO_SERVING", "false").lower() != "true":
        return
    schema(store)
    rid = active_id(store)
    if not rid or not (release_path(store, rid) / "admin/approval.json").exists():
        return
    payload = encode({"id": rid})
    with store.db() as con:
        found = con.execute("SELECT 1 FROM operation WHERE kind='serving' AND payload=?", (payload,)).fetchone()
    # Failed/uncertain attempts need an explicit retry, never a retry storm.
    if not found:
        submit(store, "serving", {"reason": "Freigegebenen Release in Analyse bereitstellen"}, "release-worker")


def enable(store, actor):
    """Explicit one-time adoption of the currently published baseline."""
    from .jobs import writer_lock
    from .candidates import verify_release, active_id, release_path
    from .store import now

    with writer_lock(store):
        storage = for_root(store.data)
        if storage.backend == "hybrid":
            raise AdminError("Managed-Modus unterstuetzt local oder s3, nicht hybrid.")
        expected = "s3" if storage.backend == "s3" else "local"
        if os.getenv("ADMIN_OBJECT_STORE", "local") != expected:
            raise AdminError("ADMIN_OBJECT_STORE und STORAGE_BACKEND muessen uebereinstimmen.")
        if managed(store.data):
            return {"status": "already_managed", "release_id": active_id(store)}
        with store.db() as con:
            if con.execute("SELECT 1 FROM job WHERE status IN ('QUEUED','RUNNING')").fetchone():
                raise AdminError("Vor der Uebernahme offene Jobs abschliessen oder kontrolliert abbrechen.")
        if storage.backend == "s3" and storage.exists("releases/AKTUELL.json"):
            from storage.release import hole
            hole(storage, "aktuell")
        rid = active_id(store)
        manifest = verify_release(release_path(store, rid)) if rid else None
        if manifest and manifest.get("years"):
            configured = set(scope_years(store.current("settings")["payload"]))
            if not set(manifest["years"]).issubset(configured):
                raise AdminError("Konfigurierter Zeitraum umfasst nicht alle Jahre des aktiven "
                                 "Releases. Settings vor der Uebernahme abgleichen.")
        record = {"enabled_at": now(), "actor": actor, "baseline_release_id": rid,
                  "baseline_manifest": manifest, "storage_backend": storage.backend,
                  "retrospective_approval": False}
        (store.root / "managed.json").write_text(encode(record), encoding="utf-8")
        return record
