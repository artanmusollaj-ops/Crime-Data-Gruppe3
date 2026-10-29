"""Immutable evidence per revision AND attempt, independent of job workspaces."""

import io
import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path

from .store import AdminError, encode, now

ARTIFACTS = (
    "impact_report.json",
    "impact_by_partition.parquet",
    "impact_records.parquet",
    "impact_quality.parquet",
    "impact_quality_month.parquet",
    "source_snapshot.json",
    "result.json",
    "recovery.json",
    "run.log",
)


def checked(store, iid, *, require_remote=False):
    from .candidates import file_hash

    with store.db() as c:
        raw = c.execute("SELECT * FROM impact_archive WHERE impact_id=?", (iid,)).fetchone()
    if not raw:
        raise AdminError("Impact-Nachweis noch nicht archiviert; Archivierung ausfuehren")
    record = dict(raw)
    root = Path(record["path"])
    if not root.resolve().is_relative_to((store.root / "impact_archive").resolve()):
        raise AdminError("Ungueltiger Archivpfad")
    if file_hash(root / "archive_manifest.json") != record["manifest_hash"]:
        raise AdminError("Archivmanifest wurde veraendert")
    manifest = json.loads((root / "archive_manifest.json").read_text())
    if manifest["impact_id"] != iid or manifest["revision_id"] != record["revision_id"]:
        raise AdminError("Archivkennung stimmt nicht ueberein")
    for name, expected in manifest["files"].items():
        if Path(name).name != name or file_hash(root / name) != expected:
            raise AdminError("Archivnachweis wurde veraendert: " + name)
    if require_remote and not record["remote_verified_at"]:
        raise AdminError("S3-Archivierung noch nicht bestaetigt")
    return record, manifest


def persist(store, iid, objects=None):
    """Idempotent local snapshot; S3 failure retains the complete local archive."""
    from .candidates import file_hash

    with store.db() as c:
        impact = c.execute("SELECT * FROM impact WHERE id=?", (iid,)).fetchone()
        job = c.execute("SELECT * FROM job WHERE id=?", (iid,)).fetchone()
        prior = c.execute("SELECT * FROM impact_archive WHERE impact_id=?", (iid,)).fetchone()
    if not impact or not job:
        raise AdminError("Impact-Lauf fehlt")
    impact, job = dict(impact), dict(job)
    if impact["status"] in {"QUEUED", "RUNNING"}:
        raise AdminError("Laufendes Ergebnis noch nicht archivieren")
    if impact["status"] == "ARCHIVE_PENDING":
        resume = json.loads(impact["error"])["archive_resume"]
        impact.update(status=resume["impact_status"], error=resume["impact_error"])
        job["status"] = resume["job_status"]
    target = store.root / "impact_archive" / impact["revision_id"] / iid
    if not prior:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            work = target.with_name("." + iid + "-" + uuid.uuid4().hex + ".part")
            work.mkdir()
            try:
                folder = store.root / "jobs" / iid
                for name in ARTIFACTS:
                    if (folder / name).is_file():
                        shutil.copyfile(folder / name, work / name)
                if impact["report_hash"] and (
                    not (work / "impact_report.json").exists()
                    or file_hash(work / "impact_report.json") != impact["report_hash"]
                ):
                    raise AdminError("Bericht fehlt oder Berichtshash passt nicht")
                (work / "revision.json").write_text(encode(store.get(impact["revision_id"])))
                (work / "attempt.json").write_text(encode({"impact": impact, "job": job}))
                manifest = {
                    "schema": 1,
                    "revision_id": impact["revision_id"],
                    "impact_id": iid,
                    "report_hash": impact["report_hash"],
                    "created_at": now(),
                    "remote_required": os.getenv("ADMIN_OBJECT_STORE", "local") == "s3",
                    "files": {p.name: file_hash(p) for p in sorted(work.iterdir())},
                }
                (work / "archive_manifest.json").write_text(encode(manifest))
                work.rename(target)
            finally:
                if work.exists():
                    shutil.rmtree(work)
        # Resume a crash after directory rename, without recreating its timestamp.
        manifest = json.loads((target / "archive_manifest.json").read_text())
        if manifest["impact_id"] != iid or manifest["report_hash"] != impact["report_hash"]:
            raise AdminError("Archiv passt nicht zum Impact-Lauf")
        with store.db() as c:
            c.execute(
                "INSERT INTO impact_archive VALUES (?,?,?,?,?,?,NULL)",
                (
                    iid,
                    impact["revision_id"],
                    str(target),
                    file_hash(target / "archive_manifest.json"),
                    manifest["created_at"],
                    impact["report_hash"],
                ),
            )
    record, manifest = checked(store, iid)
    if os.getenv("ADMIN_OBJECT_STORE", "local") == "s3" or manifest["remote_required"]:
        from .object_store import Objects

        objects = objects or Objects()
        prefix = "admin/impact_archive/" + impact["revision_id"] + "/" + iid + "/"
        for name in sorted(manifest["files"]) + ["archive_manifest.json"]:
            objects.immutable(target / name, prefix + name)
        with store.db() as c:
            c.execute(
                "UPDATE impact_archive SET remote_verified_at=? WHERE impact_id=?", (now(), iid)
            )
    return {
        "impact_id": iid,
        "revision_id": impact["revision_id"],
        "archive_sha256": record["manifest_hash"],
    }


def retry(store, iid):
    result = persist(store, iid)
    record, _ = checked(store, iid)
    attempt = json.loads((Path(record["path"]) / "attempt.json").read_text())
    with store.db() as c:
        c.execute(
            "UPDATE impact SET status=?,error=? WHERE id=? AND status='ARCHIVE_PENDING'",
            (attempt["impact"]["status"], attempt["impact"]["error"], iid),
        )
        c.execute(
            "UPDATE job SET status=? WHERE id=? AND status='ARCHIVE_PENDING'",
            (attempt["job"]["status"], iid),
        )
    return result


def zip_bytes(store, iid):
    record, manifest = checked(store, iid)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        for name in sorted(manifest["files"]) + ["archive_manifest.json"]:
            z.write(Path(record["path"]) / name, name)
        with store.db() as c:
            events = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM release_event WHERE impact_id=? ORDER BY created_at,id", (iid,)
                )
            ]
        z.writestr(zipfile.ZipInfo("lifecycle_at_download.json"), encode(events))
    return stream.getvalue()


def persist_events(store, iid, objects=None):
    """Append lifecycle receipts beside the immutable attempt; never rewrite reports."""
    record, manifest = checked(store, iid)
    target = Path(record["path"]) / "events"
    target.mkdir(exist_ok=True)
    with store.db() as c:
        events = [
            dict(r)
            for r in c.execute(
                "SELECT * FROM release_event WHERE impact_id=? ORDER BY created_at,id", (iid,)
            )
        ]
    remote = os.getenv("ADMIN_OBJECT_STORE", "local") == "s3" or manifest["remote_required"]
    if remote:
        from .object_store import Objects

        objects = objects or Objects()
    for entry in events:
        path = target / (entry["id"] + ".json")
        payload = encode(entry).encode()
        if path.exists():
            if path.read_bytes() != payload:
                raise AdminError("Lifecycle-Nachweis wurde veraendert")
        else:
            with path.open("xb") as f:
                f.write(payload)
        if remote:
            objects.immutable(
                path,
                "admin/impact_archive/"
                + record["revision_id"]
                + "/"
                + iid
                + "/events/"
                + path.name,
            )


def mark_pending(store, iid, exc):
    """Keep terminal state even if the first archive failed before its rename."""
    with store.db() as c:
        row = c.execute("SELECT status,error FROM impact WHERE id=?", (iid,)).fetchone()
        job = c.execute("SELECT status FROM job WHERE id=?", (iid,)).fetchone()
        if row["status"] == "ARCHIVE_PENDING":
            return
        error = {
            "archive_error": type(exc).__name__,
            "archive_resume": {
                "impact_status": row["status"],
                "impact_error": row["error"],
                "job_status": job["status"],
            },
        }
        c.execute(
            "UPDATE impact SET status='ARCHIVE_PENDING',error=? WHERE id=?", (encode(error), iid)
        )
        c.execute("UPDATE job SET status='ARCHIVE_PENDING' WHERE id=?", (iid,))
