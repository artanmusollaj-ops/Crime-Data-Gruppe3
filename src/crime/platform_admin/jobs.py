"""Local job queue. No arbitrary commands, no remote publication, one writer.

Run the worker under the same OS account as the UI. The lock coordinates
admin workers only; do not run independent pipeline writers concurrently.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .store import AdminError, encode, now


STAGE_NAMES = {
    "chicago_pipeline.download_chicago": "Import · Chicago",
    "detroit_pipeline.extract_detroit": "Import · Detroit",
    "census_pipeline.download_tiger": "Import · Census TIGER",
    "census_pipeline.download_acs": "Import · Census ACS5",
    "weather_pipeline.download_noaa": "Import · NOAA-Wetter",
    "silver_pipeline.build_tract": "Silver · Census-Tracts",
    "silver_pipeline.build_place": "Silver · Stadtgrenzen",
    "silver_pipeline.build_weather_day": "Silver · Wettertage",
    "silver_pipeline.build_crime_offense": "Silver · harmonisierte Delikte",
    "silver_pipeline.build_source_change": "Silver · Quellhistorisierung",
    "orchestration.vorpruefung": "Vorpruefung · Quellen und Speicher",
    "serving.load_elasticsearch": "Analyse · Elasticsearch",
    "serving.build_kibana": "Analyse · Kibana",
    "serving.build_einstieg": "Analyse · Einstiegsseite",
    "serving.pruefe_stand": "Analyse · Release-Abgleich",
    "gold_pipeline.build_gold": "Gold · Sternschema",
    "serving.build_comparison": "Serving · Vergleichstabellen",
    "serving.build_analysis_db": "Serving · Analysedatenbank",
    "serving.export_geojson": "Serving · GeoJSON",
}


class PipelineCommandError(RuntimeError):
    """Ein Pipeline-Unterprozess mit fuer Operatoren lesbarer Diagnose."""

    def __init__(self, command, returncode, *, cause, dependency, remediation):
        self.command = list(command)
        self.returncode = returncode
        self.module = self.command[2] if len(self.command) > 2 else self.command[0]
        self.stage = STAGE_NAMES.get(self.module, self.module)
        self.cause = cause
        self.dependency = dependency
        self.remediation = remediation
        super().__init__(
            f"{self.stage} ist mit Exit-Code {returncode} fehlgeschlagen. "
            f"Ursache: {cause}"
            + (f" Fehlende Abhaengigkeit: {dependency}." if dependency else "")
            + (f" Loesung: {remediation}" if remediation else "")
        )

    def result(self, log_path):
        return {
            "ok": False,
            "error_type": type(self).__name__,
            "error": str(self),
            "stage": self.stage,
            "module": self.module,
            "exit_code": self.returncode,
            "cause": self.cause,
            "missing_dependency": self.dependency,
            "remediation": self.remediation,
            "command": self.command,
            "log_path": str(log_path),
        }


def _log_diagnosis(log_path, module):
    """Extrahiert die fachliche Ursache statt nur ``exit status 1`` zu melden."""
    try:
        text = open(log_path, encoding="utf-8", errors="replace").read()
    except OSError:
        text = ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    error_lines = [
        re.sub(r"^.*?\bERROR\s+", "", line)
        for line in lines
        if re.search(r"\bERROR\b", line)
    ]
    cause = error_lines[-1] if error_lines else (
        lines[-1] if lines else "Der Unterprozess lieferte keine Fehlerdetails."
    )
    dependency = ""
    remediation = "Job-Log oeffnen, die letzte Fehlermeldung beheben und neu starten."

    lower = text.casefold()
    missing = re.findall(
        r"(?:kein vollstaendiger bronze-lauf fuer|[-] )\s*"
        r"(tiger_tract|acs5_tract)[,:]?\s*(?:vintage\s*(\d+),?\s*)?"
        r"staat\s*(\d+)",
        lower,
    )
    if missing:
        dependency = ", ".join(
            f"{dataset} / Vintage {vintage or 'konfiguriert'} / Staat {state}"
            for dataset, vintage, state in dict.fromkeys(missing)
        )
        remediation = (
            "Die genannten Census-Bronze-Quellen ingestieren: "
            "TIGER mit 'python -m census_pipeline.download_tiger "
            "--auslieferung tract', ACS5 mit 'python -m "
            "census_pipeline.download_acs'; danach einen neuen Rebuild starten."
        )
    elif "spatial-extension nicht verfuegbar" in lower:
        dependency = "DuckDB-Erweiterung spatial"
        remediation = (
            "Im gleichen virtuellen Environment 'INSTALL spatial; LOAD spatial' "
            "testen beziehungsweise den Extension-Download/Cache freigeben."
        )
    elif "icu-extension nicht verfuegbar" in lower:
        dependency = "DuckDB-Erweiterung ICU"
        remediation = (
            "Im gleichen virtuellen Environment 'INSTALL icu; LOAD icu' testen "
            "beziehungsweise den Extension-Download/Cache freigeben."
        )
    elif "silver-tabelle" in lower and "fehlt" in lower:
        dependency = "vorgelagerte Silver-Tabelle"
        remediation = "Den im Log genannten Silver-Build erfolgreich ausfuehren und neu starten."
    elif "kein vollstaendiger chicago-bronze-lauf" in lower:
        dependency = "Chicago-Bronze-Full-Load"
        remediation = "Chicago Full erfolgreich ausfuehren und danach neu starten."
    elif "kein erfolgreicher detroit-bronze-lauf" in lower:
        dependency = "Detroit-Bronze-Full-Load"
        remediation = "Detroit Full erfolgreich ausfuehren und danach neu starten."
    elif "nicht gebaut" in lower and "gold/" in lower:
        dependency = "vorgelagerte Gold-Tabelle"
        remediation = "Gold-Build erfolgreich ausfuehren und danach neu starten."
    elif re.search(r"\b(401|403)\b", text) or "unauthorized" in lower or "forbidden" in lower:
        dependency = "gueltige API-Berechtigung beziehungsweise Zugangsdaten"
        remediation = (
            "API-Key, Token und Zugriffsrechte der genannten Quelle pruefen; "
            "danach den Import erneut starten. Keine Zugangsdaten in das Job-Log kopieren."
        )
    elif re.search(r"\b429\b", text) or "rate limit" in lower or "too many requests" in lower:
        dependency = "verfuegbares API-Anfragekontingent"
        remediation = (
            "Das vom Anbieter genannte Retry-Fenster abwarten und den Job danach erneut starten."
        )
    elif any(term in lower for term in (
        "connectionerror", "connect timeout", "read timeout", "timed out",
        "name resolution", "temporary failure", "connection refused",
    )):
        dependency = "Netzwerkzugriff auf die Quell-API"
        remediation = (
            "Internet-, DNS-, Proxy- und Firewall-Zugriff auf den im Log genannten Host pruefen; "
            "danach den Job erneut starten."
        )
    elif "no module named" in lower or "modulenotfounderror" in lower:
        dependency = "installiertes Python-Projekt mit Laufzeitabhaengigkeiten"
        remediation = (
            "Im selben virtuellen Environment wie Worker und Webserver "
            "'python -m pip install -e .' ausfuehren und beide Dienste neu starten."
        )
    elif "permissionerror" in lower or "permission denied" in lower:
        dependency = "Schreib-/Leseberechtigung auf Projekt- und Datenverzeichnis"
        remediation = (
            "Berechtigungen und parallele Dateisperren fuer den im Log genannten Pfad pruefen; "
            "Webserver und Worker unter demselben OS-Konto betreiben."
        )
    elif "no space left" in lower or "disk full" in lower:
        dependency = "freier Speicherplatz fuer Kandidat und Release"
        remediation = (
            "Freien Speicherplatz auf dem Datenlaufwerk schaffen; der Rebuild benoetigt "
            "zusaetzlich Platz fuer Bronze-Snapshot, Kandidat und Impact-Artefakte."
        )

    if module in STAGE_NAMES and not dependency:
        remediation += f" Fehlgeschlagener Schritt: {STAGE_NAMES[module]}."
    return cause, dependency, remediation


def enqueue(store, name, actor, *, slot=None, instant=None, origin=None):
    """Pin the approved configuration and source parameters in one transaction.

    ``origin="batch"`` marks a rebuild a scheduled source run queued; only those
    qualify for approval by the quality gate (auto_approval).
    """
    from .candidates import queue_in_transaction
    from .store import digest

    if not actor.strip():
        raise AdminError("Bearbeiter erforderlich")
    actor = actor.strip()
    instant = instant or datetime.now(timezone.utc)
    with store.db() as c:
        c.execute("BEGIN IMMEDIATE")
        heads = dict(c.execute("SELECT resource,revision FROM head").fetchall())
        settings = store.get(heads["settings"])["payload"]
        matches = [j for j in settings["jobs"] if j["name"] == name]
        if len(matches) != 1:
            raise AdminError("Jobname nicht konfiguriert")
        spec = dict(matches[0])
        if slot and (
            not spec["enabled"] or c.execute("SELECT 1 FROM job WHERE slot=?", (slot,)).fetchone()
        ):
            return None
        if spec["task"] in {"rebuild", "replay"}:
            if "data" not in heads:
                raise AdminError(
                    "Nach Upgrade init erneut ausfuehren (bestehende Revisionen bleiben erhalten)"
                )
            rid = uuid.uuid4().hex
            payload = {"task": spec["task"], "job_name": name}
            if origin:
                payload["origin"] = origin
            c.execute(
                "INSERT INTO revision VALUES (?,?,?,?,?,?,?,?)",
                (
                    rid,
                    "data",
                    heads["data"],
                    encode(payload),
                    digest(payload),
                    actor,
                    "Neuaufbau gegen letzten freigegebenen Release: " + name,
                    now(),
                ),
            )
            jid = queue_in_transaction(store, c, rid, actor)
            c.execute("UPDATE job SET name=?,slot=? WHERE id=?", (name, slot, jid))
            return jid
        if spec["task"] == "daily_detroit":
            spec["reference_date"] = (
                instant.astimezone(ZoneInfo("America/Detroit")).date().isoformat()
            )
        jid = uuid.uuid4().hex
        try:
            c.execute(
                """INSERT INTO job(id,name,slot,mapping_revision,settings_revision,
                spec,actor,status,queued_at) VALUES(?,?,?,?,?,?,?,'QUEUED',?)""",
                (jid, name, slot, heads["mapping"], heads["settings"], encode(spec), actor, now()),
            )
        except sqlite3.IntegrityError:
            if slot:
                return None
            raise
        return jid


def schedule(store, *, instant=None):
    """At most one catch-up per UTC calendar day/job. No backlog storm."""
    with store.db() as c:
        if c.execute("SELECT 1 FROM impact WHERE status='APPROVED_PENDING_PUBLICATION'").fetchone():
            return []
    instant = (instant or datetime.now(timezone.utc)).astimezone(timezone.utc)
    settings = store.current("settings")
    queued = []
    for spec in sorted(settings["payload"]["jobs"], key=lambda j: (j["at_utc"], j["name"])):
        if spec["enabled"] and instant.strftime("%H:%M") >= spec["at_utc"]:
            # Deliberately independent of settings revision: editing a schedule
            # must not cause another scheduled execution on the same day.
            slot = instant.date().isoformat() + ":" + spec["name"]
            jid = enqueue(store, spec["name"], "scheduler", slot=slot, instant=instant)
            if jid:
                queued.append(jid)
    return queued


@contextmanager
def writer_lock(store):
    """Never steal a possibly live writer lock, including after a crash."""
    path = store.root / "worker.lock"
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise AdminError("Worker-Lock vorhanden; laufenden Prozess pruefen") from exc
    try:
        with os.fdopen(fd, "w") as f:
            f.write(encode({"pid": os.getpid(), "started_at": now(), "token": uuid.uuid4().hex}))
        yield
    finally:
        path.unlink(missing_ok=True)


def commands(store, spec, config):
    """Reuse the tested existing stage CLIs with explicit roots."""
    import sys
    from orchestration.run_all import auswahl

    if spec["task"] == "delta_detroit":
        return [[sys.executable, "-m", "detroit_pipeline.extract_detroit",
                 "--mode", "delta", "--years", *map(str, spec["years"]),
                 "--data-root", str(store.data)]]

    if spec["task"] == "daily_detroit":
        return [
            [
                sys.executable,
                "-m",
                "detroit_pipeline.extract_detroit",
                "--mode",
                "daily",
                "--lookback-days",
                str(spec.get("lookback_days", 14)),
                "--reference-date",
                spec["reference_date"],
                "--data-root",
                str(store.data),
            ]
        ]
    if spec["task"] == "full_detroit":
        return [
            [
                sys.executable,
                "-m",
                "detroit_pipeline.extract_detroit",
                "--mode",
                "full",
                "--years",
                *[str(year) for year in spec["years"]],
                "--data-root",
                str(store.data),
            ]
        ]
    if spec["task"] in {"daily_chicago", "full_chicago"}:
        command = [
            sys.executable,
            "-m",
            "chicago_pipeline.download_chicago",
            "--year",
            str(spec["year"]),
            "--data-root",
            str(store.data),
        ]
        if spec["task"] == "full_chicago":
            command.append("--full")
        else:
            from chicago_pipeline.download_chicago import LOOKBACK_DAYS
            if spec.get("lookback_days", LOOKBACK_DAYS) != LOOKBACK_DAYS:
                raise AdminError("Chicago-Delta verwendet den Pipeline-Lookback von 14 Tagen; "
                                 "abweichende alte Jobkonfiguration korrigieren.")
        return [command]
    result = []
    if spec["task"] in {"rebuild", "replay"}:
        for stage in auswahl(True, None, spec.get("years", (2024,))):
            command = stage.befehl(store.data)
            if stage.modul in {"silver_pipeline.build_crime_offense", "gold_pipeline.build_gold"}:
                command += ["--config-root", str(config)]
            result.append(command)
    return result


def recover_import(store, jid, actor, reason):
    """Explicitly close an abandoned import after the operator stopped writers."""
    if not actor.strip() or not reason.strip():
        raise AdminError("Bearbeiter und dokumentierte Prozesspruefung erforderlich")
    with writer_lock(store), store.db() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM job WHERE id=?", (jid,)).fetchone()
        if not row or row["status"] != "RUNNING":
            raise AdminError("Nur einen verwaisten RUNNING-Job abschliessen")
        if con.execute("SELECT 1 FROM impact WHERE id=?", (jid,)).fetchone():
            raise AdminError("Fuer Impact-Laeufe abandon-impact verwenden")
        result = {"ok": False, "error_type": "ExplicitAbandonment", "error": reason,
                  "recovered_by": actor, "recovered_at": now()}
        folder = store.root / "jobs" / jid
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "recovery.json").write_text(encode(result), encoding="utf-8")
        con.execute("UPDATE job SET status='FAILED',finished_at=?,result=? WHERE id=?",
                    (now(), encode(result), jid))
        return result


#: Every command a tick ran: module, arguments, exit code, seconds. The worker
#: writes it as the run protocol after the tick (run_protocol), in the format
#: orchestration.run_all writes for the cron run.
TICK_STAGES = []


def execute_commands(store, command_list, log):
    env = dict(os.environ)
    # Only isolated candidates force local storage; imports use publish_run.
    isolated = not hasattr(store, "root")
    env.update(
        STORAGE_BACKEND="local" if isolated else os.getenv("STORAGE_BACKEND", "local"),
        LOCAL_DATA_ROOT=str(store.data),
        HYBRID_PUBLISH_AFTER_WRITE="false" if isolated else os.getenv("HYBRID_PUBLISH_AFTER_WRITE", "true"),
        PYTHON_DOTENV_DISABLED="1",
    )
    from .progress import record
    from pathlib import Path

    if hasattr(store, "root") and (store.root / "worker.lock").exists():
        env["ADMIN_WRITER_TOKEN"] = json.loads((store.root / "worker.lock").read_text())["token"]

    for command in command_list:
        record(Path(log.name).parent, command[2], "RUNNING")
        log.write("\n" + encode(command) + "\n")
        log.flush()
        stage = {"modul": command[2], "args": [str(a) for a in command[3:]], "exit": None}
        TICK_STAGES.append(stage)
        started = time.monotonic()
        try:
            finished = subprocess.run(
                command,
                cwd=store.project,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
                shell=False,
            )
        except OSError as error:
            stage.update(exit=-1, sekunden=round(time.monotonic() - started, 1))
            record(Path(log.name).parent, command[2], "FAILED", str(error))
            raise PipelineCommandError(
                command,
                getattr(error, "errno", -1) or -1,
                cause=f"Unterprozess konnte nicht gestartet werden: {error}",
                dependency="ausfuehrbares Python und erreichbares Projektverzeichnis",
                remediation=(
                    "Worker im aktivierten Projekt-Environment starten und Installation mit "
                    "'python -m pip install -e .' pruefen."
                ),
            ) from error
        log.flush()
        stage.update(exit=finished.returncode, sekunden=round(time.monotonic() - started, 1))
        if finished.returncode:
            record(Path(log.name).parent, command[2], "FAILED")
            cause, dependency, remediation = _log_diagnosis(log.name, command[2])
            raise PipelineCommandError(
                command,
                finished.returncode,
                cause=cause,
                dependency=dependency,
                remediation=remediation,
            )
        record(Path(log.name).parent, command[2], "SUCCEEDED")


def run_one(store, *, runner=execute_commands, evaluator=None):
    """Claim one job; failed checks leave the last immutable release untouched."""
    from .checks import evaluate

    evaluator = evaluator or evaluate
    with writer_lock(store):
        with store.db() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute(
                "SELECT 1 FROM impact WHERE status='APPROVED_PENDING_PUBLICATION'"
            ).fetchone():
                return None
            row = c.execute(
                "SELECT * FROM job WHERE status='QUEUED' ORDER BY queued_at LIMIT 1"
            ).fetchone()
            if not row:
                return None
            job = dict(row)
            c.execute("UPDATE job SET status='RUNNING',started_at=? WHERE id=?", (now(), job["id"]))
        folder = store.root / "jobs" / job["id"]
        folder.mkdir(parents=True)
        log_path = folder / "run.log"
        log_path.touch()
        with store.db() as c:
            c.execute("UPDATE job SET log_path=? WHERE id=?", (str(log_path), job["id"]))
        status, result = "FAILED", {}
        try:
            spec = json.loads(job["spec"])
            if spec["task"] == "impact":
                from .candidates import build

                with store.db() as c:
                    c.execute("UPDATE impact SET status='RUNNING' WHERE id=?", (job["id"],))
                result = build(store, job, spec, folder, runner, evaluator)
                status = (
                    "AWAITING_REVIEW"
                    if result["ok"]
                    else (
                        "REVIEW_REQUIRED"
                        if result["technical_ok"] and result["replay_ok"]
                        else "FAILED"
                    )
                )
            else:
                result, status = run_standard(store, job, spec, folder, log_path, runner, evaluator)
        except Exception as exc:
            result = (
                exc.result(log_path)
                if isinstance(exc, PipelineCommandError)
                else {"ok": False, "error_type": type(exc).__name__, "error": str(exc)}
            )
            status = "FAILED"
            from .progress import read, record

            for step, evidence in read(folder)["steps"].items():
                if evidence["status"] == "RUNNING":
                    record(folder, step, "FAILED", str(exc))
            with store.db() as c:
                c.execute(
                    "UPDATE impact SET status='FAILED',error=?,finished_at=? WHERE id=?",
                    (encode(result), now(), job["id"]),
                )
            with log_path.open("a", encoding="utf-8") as log:
                log.write(encode(result) + "\n")
        (folder / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        with store.db() as c:
            c.execute(
                "UPDATE job SET status=?,finished_at=?,result=?,log_path=? WHERE id=?",
                (status, now(), encode(result), str(log_path), job["id"]),
            )
        if json.loads(job["spec"]).get("task") == "impact":
            from .impact_archive import persist

            try:
                persist(store, job["id"])
            except Exception as exc:
                # A failed S3 upload must not make unarchived evidence approvable.
                error = {"archive_error": type(exc).__name__}
                from .impact_archive import mark_pending

                mark_pending(store, job["id"], exc)
                status = "ARCHIVE_PENDING"
                result = {**result, **error}
        return {"id": job["id"], "status": status, "result": result}


def run_standard(store, job, spec, folder, log_path, runner, evaluator):
    if spec["task"] not in {
        "delta_detroit",
        "daily_detroit",
        "full_detroit",
        "daily_chicago",
        "full_chicago",
        "checks",
    }:
        raise AdminError(
            "Ableitungen erfordern einen isolierten Impact-Lauf; alten Queuejob neu einreihen"
        )
    settings = store.get(job["settings_revision"])["payload"]
    config = store.materialize(job["mapping_revision"])
    from .run_evidence import capture, inventory

    city_key = "detroit" if "detroit" in spec["task"] else "chicago" if "chicago" in spec["task"] else None
    before = inventory(store, city_key) if city_key else {}
    try:
        with log_path.open("w", encoding="utf-8") as log:
            runner(store, commands(store, spec, config), log)
    finally:
        if city_key:
            capture(store, city_key, before, folder, job, spec)
    if spec["task"] in {
        "delta_detroit",
        "daily_detroit",
        "full_detroit",
        "daily_chicago",
        "full_chicago",
    }:
        city = "Detroit" if "detroit" in spec["task"] else "Chicago"
        return {
            "ok": True,
            "note": f"Nur {city} Bronze geladen; Neuaufbau und Impact-Review fuer Analysefreigabe erforderlich.",
        }, "SUCCEEDED"
    if spec["task"] != "checks":
        raise AdminError("Ableitungen erfordern einen isolierten Impact-Lauf")
    result = evaluator(store.data, settings)
    if not result["technical_ok"] or not result["replay_ok"]:
        status = "FAILED"
    elif not result["quality_ok"]:
        status = "REVIEW_REQUIRED"
    else:
        status = "SUCCEEDED"
    return result, status
