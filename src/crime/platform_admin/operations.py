"""Durable administrative outbox, processed by the single pipeline worker."""

import json
import os
import uuid
from datetime import datetime, timezone

from .store import AdminError, encode, now
from .release_flow import mode


def schema(store):
    with store.db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS operation(
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL,
            actor TEXT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL,
            created_at TEXT NOT NULL, finished_at TEXT, result TEXT);
        CREATE TABLE IF NOT EXISTS git_change(
            revision TEXT PRIMARY KEY, state TEXT NOT NULL, document TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS service_status(
            name TEXT PRIMARY KEY, updated_at TEXT NOT NULL, document TEXT NOT NULL);
        """)


def submit(store, kind, value, actor):
    schema(store)
    if kind not in {"git-open", "git-merge", "git-withdraw", "archive-retry", "backup", "serving"}:
        raise AdminError("Unbekannte Betriebsaktion")
    reason = value.get("reason", "").strip()
    if not reason:
        raise AdminError("Begruendung erforderlich")
    payload = {"id": value.get("id")}
    if kind in {"git-open", "git-merge"}:
        from .gitops import approved

        approved(store, payload["id"])
        if kind == "git-merge" and store.get(payload["id"])["actor"].casefold() == actor.casefold():
            raise AdminError("Merge muss durch eine zweite Person angefordert werden")
    if kind == "git-withdraw":
        if store.get(payload["id"])["actor"].strip().casefold() == actor.strip().casefold():
            raise AdminError("Ruecknahme verlangt zweite Person")
    if kind == "serving":
        from .candidates import active_id

        payload["id"] = active_id(store)
        if not payload["id"]:
            raise AdminError("Kein freigegebener Release vorhanden")
    oid = uuid.uuid4().hex
    with store.db() as c:
        c.execute("BEGIN IMMEDIATE")
        if c.execute(
            "SELECT 1 FROM operation WHERE kind=? AND payload=? AND status IN ('QUEUED','RUNNING')",
            (kind, encode(payload)),
        ).fetchone():
            raise AdminError("Gleiche Betriebsaktion bereits eingereiht")
        c.execute(
            "INSERT INTO operation VALUES (?,?,?,?,?,'QUEUED',?,NULL,NULL)",
            (oid, kind, encode(payload), actor, reason, now()),
        )
    return oid


def overview(store):
    schema(store)
    with store.db() as c:
        return {
            "operations": [
                dict(r)
                for r in c.execute("SELECT * FROM operation ORDER BY created_at DESC LIMIT 100")
            ],
            "git": [json.loads(r[0]) for r in c.execute("SELECT document FROM git_change")],
            "services": {
                r["name"]: {"updated_at": r["updated_at"], **json.loads(r["document"])}
                for r in c.execute("SELECT * FROM service_status")
            },
            "git_enabled": bool(os.getenv("ADMIN_GITHUB_REPOSITORY")),
            "storage": os.getenv("ADMIN_OBJECT_STORE", "local"),
            "release_mode": mode(),
        }


def record_status(store, name, document):
    schema(store)
    with store.db() as c:
        c.execute(
            "INSERT OR REPLACE INTO service_status VALUES (?,?,?)", (name, now(), encode(document))
        )


def metrics_text(store):
    schema(store)
    result = ["# TYPE crime_admin_jobs gauge"]
    with store.db() as c:
        for row in c.execute("SELECT status,count(*) FROM job GROUP BY status"):
            result.append(f'crime_admin_jobs{{status="{row[0]}"}} {row[1]}')
        for row in c.execute("SELECT status,count(*) FROM operation GROUP BY status"):
            result.append(f'crime_admin_operations{{status="{row[0]}"}} {row[1]}')
        for row in c.execute("SELECT name,updated_at,document FROM service_status"):
            stamp = datetime.fromisoformat(row[1]).timestamp()
            result.append(f'crime_admin_service_updated_seconds{{service="{row[0]}"}} {stamp}')
            status = json.loads(row[2]).get("status", "unknown")
            result.append(f'crime_admin_service_ok{{service="{row[0]}"}} {int(status in {"ok", "SUCCEEDED"})}')
    return "\n".join(result) + "\n"


def run_operation(store):
    """Called outside run_one; lock also excludes data publication while merging."""
    from .jobs import writer_lock

    schema(store)
    with writer_lock(store):
        with store.db() as c:
            c.execute("BEGIN IMMEDIATE")
            # Explicit recovery, never silently repeat an uncertain remote operation.
            if c.execute("SELECT 1 FROM operation WHERE status='RUNNING'").fetchone():
                raise AdminError(
                    "Betriebsaktion RUNNING: alten Prozess pruefen und Recovery ausfuehren"
                )
            row = c.execute(
                "SELECT * FROM operation WHERE status='QUEUED' ORDER BY created_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            row = dict(row)
            c.execute("UPDATE operation SET status='RUNNING' WHERE id=?", (row["id"],))
        payload = json.loads(row["payload"])
        try:
            if row["kind"] == "batch":
                from .batch import execute
                result = execute(store, row, payload)
            elif row["kind"] == "git-withdraw":
                from .coupled_git import withdraw

                result = withdraw(store, payload["id"], row["actor"], row["reason"])
            elif row["kind"] == "archive-retry":
                from .impact_archive import retry

                result = retry(store, payload["id"])
            elif row["kind"].startswith("git-"):
                from .gitops import open_pr, merge_pr

                result = (open_pr if row["kind"] == "git-open" else merge_pr)(
                    store, payload["id"], row["actor"]
                )
            elif row["kind"] == "backup":
                from .object_store import backup

                result = backup(store)
            else:
                from .serving_export import publish

                result = publish(store, payload["id"])
            status = "SUCCEEDED"
        except Exception as exc:
            # Provider bodies/URLs can contain secrets; record only controlled errors.
            from .jobs import PipelineCommandError
            result = (exc.result(store.root / "jobs" / row["id"] / "run.log")
                      if isinstance(exc, PipelineCommandError)
                      else {"error": str(exc) if isinstance(exc, AdminError) else type(exc).__name__})
            status = "FAILED"
        with store.db() as c:
            c.execute(
                "UPDATE operation SET status=?,finished_at=?,result=? WHERE id=?",
                (status, now(), encode(result), row["id"]),
            )
        return {"id": row["id"], "status": status, "result": result}


def recover(store, oid, actor, reason):
    from .jobs import writer_lock

    if not reason.strip() or not actor.strip():
        raise AdminError("Bearbeiter und Recovery-Begruendung erforderlich")
    schema(store)
    with writer_lock(store), store.db() as c:
        cursor = c.execute(
            "UPDATE operation SET status='FAILED',finished_at=?,result=? WHERE id=? AND status='RUNNING'",
            (now(), encode({"recovered_by": actor, "reason": reason}), oid),
        )
        if cursor.rowcount != 1:
            raise AdminError("Keine laufende Betriebsaktion mit dieser ID")


def tick(store):
    """Container worker: publish approvals, then operations, then pipeline work."""
    from .jobs import writer_lock, schedule, run_one
    from .candidates import finish_publication

    schema(store)
    from .integration import reconcile_serving
    from storage import for_root
    if (store.root / "managed.json").exists():
        contract = json.loads((store.root / "managed.json").read_text())
        backend = for_root(store.data).backend
        if (backend != contract.get("storage_backend", backend)
                or os.getenv("ADMIN_OBJECT_STORE", "local") != backend):
            raise AdminError("Worker-Ablage weicht vom uebernommenen Datenbestand ab; "
                             "STORAGE_BACKEND und ADMIN_OBJECT_STORE pruefen.")
    reconcile_serving(store)
    with store.db() as c:
        pending = c.execute(
            "SELECT id FROM impact WHERE status='APPROVED_PENDING_PUBLICATION' ORDER BY created_at LIMIT 1"
        ).fetchone()
    if pending:
        with writer_lock(store):
            result = {"release": finish_publication(store, pending[0])}
    else:
        result = run_operation(store)
        if result is None:
            if os.getenv("ADMIN_SCHEDULER", "true").lower() == "true":
                schedule(store)
            result = run_one(store)
    if os.getenv("ADMIN_OBJECT_STORE", "local") == "s3":
        from .object_store import archive_inputs, backup
        from .jobs import writer_lock

        with writer_lock(store):
            # Daily control/evidence backup; weekly marker in backup metadata.
            last = overview(store)["services"].get("backup", {}).get("updated_at", "")
            if result or last[:10] != datetime.now(timezone.utc).date().isoformat():
                if os.getenv("STORAGE_BACKEND", "local") == "local":
                    archive_inputs(store)
            if last[:10] != datetime.now(timezone.utc).date().isoformat():
                backup(store)
    from .impact_archive import persist_events

    with store.db() as c:
        event_impacts = [r[0] for r in c.execute("SELECT DISTINCT impact_id FROM release_event")]
    for iid in event_impacts:
        persist_events(store, iid)
    record_status(store, "worker", {"status": "ok"})
    return result
