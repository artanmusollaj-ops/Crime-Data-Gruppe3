"""Transactional control metadata; source CSVs remain untouched.

SQLite is used for control-plane writes from UI and worker, not analytics.
Each proposal has a parent revision. Approval uses compare-and-swap so that
two reviewers cannot silently overwrite each other's changes.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class AdminError(ValueError):
    """Invalid configuration, stale proposal or unsupported action."""


def now():
    return datetime.now(timezone.utc).isoformat()


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encode(value).encode()).hexdigest()


DEFAULT_SETTINGS = {
    "scope_start": "2024-01-01",
    "scope_end_exclusive": "2025-01-01",
    "maximum_unmapped_ratio": 0.05,
    "jobs": [
        {"name": "rebuild", "task": "rebuild", "enabled": False, "at_utc": "07:00"},
        {
            "name": "detroit_daily",
            "task": "daily_detroit",
            "enabled": False,
            "at_utc": "07:00",
            "lookback_days": 14,
        },
        {
            "name": "chicago_daily",
            "task": "daily_chicago",
            "enabled": False,
            "at_utc": "07:15",
            "year": 2024,
            "lookback_days": 14,
        },
        {
            "name": "chicago_full",
            "task": "full_chicago",
            "enabled": False,
            "at_utc": "06:00",
            "year": 2024,
        },
        {"name": "quality", "task": "checks", "enabled": False, "at_utc": "08:00"},
        {
            "name": "detroit_full",
            "task": "full_detroit",
            "enabled": False,
            "at_utc": "06:15",
            "years": [2024],
        },
    ],
}


def validate_settings(value):
    """Only implemented knobs are accepted; no arbitrary commands or credentials."""
    from datetime import date
    import re

    if set(value) != set(DEFAULT_SETTINGS):
        raise AdminError("Erlaubt: scope_start, scope_end_exclusive, maximum_unmapped_ratio, jobs")
    if not date.fromisoformat(value["scope_start"]) < date.fromisoformat(
        value["scope_end_exclusive"]
    ):
        raise AdminError("scope_start muss vor scope_end_exclusive liegen")
    ratio = value["maximum_unmapped_ratio"]
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)) or not 0 <= ratio <= 1:
        raise AdminError("maximum_unmapped_ratio muss zwischen 0 und 1 liegen")
    names = set()
    if not isinstance(value["jobs"], list) or len(value["jobs"]) > 20:
        raise AdminError("jobs muss eine Liste mit maximal 20 Eintraegen sein")
    for j in value["jobs"]:
        if set(j) - {
            "name",
            "task",
            "enabled",
            "at_utc",
            "lookback_days",
            "year",
            "years",
        }:
            raise AdminError("Unbekannte Joboption")
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", j.get("name", "")) or j["name"] in names:
            raise AdminError("Eindeutiger Jobname erforderlich")
        names.add(j["name"])
        if j.get("task") not in {
            "rebuild",
            "replay",
            "checks",
            "daily_detroit",
            "delta_detroit",
            "full_detroit",
            "daily_chicago",
            "full_chicago",
        }:
            raise AdminError("Unbekannter Jobtyp")
        if type(j.get("enabled")) is not bool or not re.fullmatch(
            r"([01]\d|2[0-3]):[0-5]\d", j.get("at_utc", "")
        ):
            raise AdminError("enabled als Boolean und at_utc als HH:MM UTC erforderlich")
        if "lookback_days" in j and (
            j["task"] not in {"daily_detroit", "daily_chicago"}
            or type(j["lookback_days"]) is not int
            or not 1 <= j["lookback_days"] <= 366
        ):
            raise AdminError("lookback_days nur fuer Daily-Jobs, 1 bis 366")

        if j["task"] in {"daily_chicago", "full_chicago"}:
            if j["task"] == "daily_chicago" and j.get("lookback_days", 14) != 14:
                raise AdminError("Chicago-Delta: die aktuelle Pipeline verwendet fest 14 Tage Lookback")
            if type(j.get("year")) is not int or not 2001 <= j["year"] <= 9998:
                raise AdminError("Chicago: year als Ganzzahl zwischen 2001 und 9998 erforderlich")
        elif "year" in j:
            raise AdminError("year nur fuer Chicago-Jobs erlaubt")
        if j["task"] in {"full_detroit", "delta_detroit"}:
            years = j.get("years")
            if (
                not isinstance(years, list)
                or not 1 <= len(years) <= 25
                or any(type(year) is not int or not 2001 <= year <= 9998 for year in years)
                or len(set(years)) != len(years)
            ):
                raise AdminError(
                    "Detroit Full: years als eindeutige Liste mit 1 bis 25 Jahren erforderlich"
                )
        elif "years" in j:
            raise AdminError("years nur fuer Detroit-Full-/Delta-Jobs erlaubt")


def rows(text):
    reader = csv.DictReader(io.StringIO(text))
    return reader.fieldnames, list(reader)


# The crosswalks are generated from official sources (tools/build_*_mapping.py)
# and held against their generators; the console never edits them. A reviewed
# correction is one row in mapping_overrides.csv, which silver applies on top.
OVERRIDES = "mapping_overrides.csv"
OVERRIDE_FIELDS = ["city", "source_code", "nibrs_code", "reason"]
CROSSWALKS = {
    "chicago": ("iucr_nibrs_mapping.csv", "iucr", "ibr_code"),
    "detroit": ("micr_nibrs_mapping.csv", "micr_code", "nibrs_code"),
}
#: The review unit per mapping file: one row, identified by these columns.
ROW_KEYS = {
    "iucr_nibrs_mapping.csv": ("iucr",),
    "micr_nibrs_mapping.csv": ("micr_code",),
    "nibrs_offense_codes_2025.csv": ("nibrs_code",),
    OVERRIDES: ("city", "source_code"),
}


def row_key(name, row):
    return "/".join(row[k] for k in ROW_KEYS[name])


def write_rows(name, fields, records):
    """CSV text for a mapping file. The overrides file is LF like the repo
    copy; the crosswalks keep their CRLF (.gitattributes)."""
    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=fields, lineterminator="\n" if name == OVERRIDES else "\r\n"
    )
    writer.writeheader()
    writer.writerows(records)
    return out.getvalue()


def repository_settings(project):
    """Settings baseline from ``config/platform_admin_settings.json``, else the defaults.

    Its own function so the console tests can start from DEFAULT_SETTINGS no
    matter what the repository carries: since 7.11.2026 the file is in Git,
    and 87 tests built around the defaults read it and failed.
    """
    path = Path(project) / "config" / "platform_admin_settings.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else DEFAULT_SETTINGS


class Store:
    def __init__(self, project: Path, data: Path):
        self.project, self.data = Path(project).resolve(), Path(data).resolve()
        self.root = self.data / "admin"
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "control.sqlite"
        with self.db() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS revision(
                    id TEXT PRIMARY KEY, resource TEXT NOT NULL, parent TEXT,
                    payload TEXT NOT NULL, sha256 TEXT NOT NULL,
                    actor TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS head(resource TEXT PRIMARY KEY, revision TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS decision(
                    id TEXT PRIMARY KEY, revision TEXT UNIQUE NOT NULL, decision TEXT NOT NULL,
                    actor TEXT NOT NULL, reason TEXT NOT NULL, decided_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS job(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, slot TEXT UNIQUE,
                    mapping_revision TEXT NOT NULL, settings_revision TEXT NOT NULL,
                    spec TEXT NOT NULL, actor TEXT NOT NULL, status TEXT NOT NULL,
                    queued_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    result TEXT, log_path TEXT);
                CREATE TABLE IF NOT EXISTS impact(
                    id TEXT PRIMARY KEY, revision_id TEXT NOT NULL,
                    baseline_release_id TEXT, candidate_release_id TEXT NOT NULL,
                    status TEXT NOT NULL, spec TEXT NOT NULL, report_hash TEXT,
                    report_path TEXT, candidate_path TEXT, created_at TEXT NOT NULL,
                    finished_at TEXT, error TEXT, published_release_id TEXT);
                CREATE TABLE IF NOT EXISTS impact_archive(
                    impact_id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, path TEXT NOT NULL,
                    manifest_hash TEXT NOT NULL, created_at TEXT NOT NULL, report_hash TEXT,
                    remote_verified_at TEXT);
                CREATE TABLE IF NOT EXISTS review_assignment(
                    revision_id TEXT PRIMARY KEY, actor TEXT NOT NULL, assigned_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS review_read(
                    revision_id TEXT NOT NULL, actor TEXT NOT NULL, read_at TEXT NOT NULL,
                    PRIMARY KEY(revision_id,actor));
                CREATE TABLE IF NOT EXISTS review_inbox_event(
                    id INTEGER PRIMARY KEY, revision_id TEXT NOT NULL, actor TEXT NOT NULL,
                    action TEXT NOT NULL, created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS release_event(
                    id TEXT PRIMARY KEY, revision_id TEXT NOT NULL, impact_id TEXT NOT NULL,
                    action TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL,
                    created_at TEXT NOT NULL, evidence TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS impact_revision ON impact(revision_id,created_at);
            """)

            impact_columns = {r[1] for r in c.execute("PRAGMA table_info(impact)")}
            for column in ("candidate_manifest_hash", "published_manifest_hash"):
                if column not in impact_columns:
                    c.execute(f"ALTER TABLE impact ADD COLUMN {column} TEXT")
            existing = {r[1] for r in c.execute("PRAGMA table_info(decision)")}
            for column in ("impact_id", "impact_report_sha256"):
                if column not in existing:
                    c.execute(f"ALTER TABLE decision ADD COLUMN {column} TEXT")

    @contextmanager
    def db(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA busy_timeout=30000")
            with c:
                yield c
        finally:
            c.close()

    def initialize(self, actor):
        """Import repository baseline, explicitly not a retrospective human approval."""
        files = {
            p.name: p.read_text(encoding="utf-8-sig")
            for p in sorted((self.project / "config").glob("*.csv"))
        }
        for required in (
            "iucr_nibrs_mapping.csv",
            "micr_nibrs_mapping.csv",
            "nibrs_offense_codes_2025.csv",
            OVERRIDES,
        ):
            if required not in files:
                raise AdminError(f"Konfiguration fehlt: {required}")
        self.validate_mappings(files)
        settings = repository_settings(self.project)
        validate_settings(settings)
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            for resource, value in [
                ("mapping", files),
                ("settings", settings),
                ("data", {"note": "Repository-Baseline"}),
            ]:
                if c.execute("SELECT 1 FROM head WHERE resource=?", (resource,)).fetchone():
                    continue
                rid = uuid.uuid4().hex
                c.execute(
                    "INSERT INTO revision VALUES (?,?,?,?,?,?,?,?)",
                    (
                        rid,
                        resource,
                        None,
                        encode(value),
                        digest(value),
                        actor,
                        "Import der Repository-Baseline; keine fachliche Einzelfreigabe",
                        now(),
                    ),
                )
                c.execute("INSERT INTO head VALUES (?,?)", (resource, rid))

    def get(self, rid):
        with self.db() as c:
            r = c.execute("SELECT * FROM revision WHERE id=?", (rid,)).fetchone()
        if not r:
            raise AdminError("Revision nicht gefunden")
        result = dict(r)
        result["payload"] = json.loads(result["payload"])
        if digest(result["payload"]) != result["sha256"]:
            raise AdminError("Revisionsinhalt stimmt nicht mit Pruefsumme ueberein")
        return result

    def current(self, resource):
        with self.db() as c:
            r = c.execute("SELECT revision FROM head WHERE resource=?", (resource,)).fetchone()
        if not r:
            raise AdminError("Zuerst initialisieren")
        return self.get(r[0])

    def validate_mappings(self, files):
        _, codes = rows(files["nibrs_offense_codes_2025.csv"])
        allowed = {r["nibrs_code"] for r in codes} | {"90A", "90E", "90H", "90I"}
        for name, key, target in [
            ("iucr_nibrs_mapping.csv", "iucr", "ibr_code"),
            ("micr_nibrs_mapping.csv", "micr_code", "nibrs_code"),
        ]:
            _, records = rows(files[name])
            seen = set()
            for r in records:
                if not r[key] or r[key] != r[key].strip() or r[key] in seen:
                    raise AdminError(f"{name}: fehlender, unnormalisierter oder doppelter Code")
                seen.add(r[key])
                if r["mapped"] not in {"true", "false"}:
                    raise AdminError("mapped muss true oder false sein")
                if r["mapped"] == "true" and r[target] not in allowed:
                    raise AdminError(f"Unbekannter Zielcode {r[target]}")
        fields, overrides = rows(files[OVERRIDES])
        if fields != OVERRIDE_FIELDS:
            raise AdminError(f"{OVERRIDES}: Kopfzeile muss {','.join(OVERRIDE_FIELDS)} sein")
        seen = set()
        for r in overrides:
            if r["city"] not in CROSSWALKS:
                raise AdminError(f"{OVERRIDES}: unbekannte Stadt {r['city']}")
            name, key, _target = CROSSWALKS[r["city"]]
            if r["source_code"] not in {c[key] for c in rows(files[name])[1]}:
                raise AdminError(f"{OVERRIDES}: Quellcode {r['source_code']} fehlt im Crosswalk")
            if (r["city"], r["source_code"]) in seen:
                raise AdminError(f"{OVERRIDES}: {r['city']} {r['source_code']} doppelt")
            seen.add((r["city"], r["source_code"]))
            if r["nibrs_code"] not in allowed:
                raise AdminError(f"Unbekannter Zielcode {r['nibrs_code']}")
            if not (r["reason"] or "").strip():
                raise AdminError(f"{OVERRIDES}: Begruendung fehlt")

    def propose(self, resource, payload, parent, actor, reason, *, supersedes=None):
        if not actor.strip() or not reason.strip():
            raise AdminError("Bearbeiter und Begruendung erforderlich")
        if resource == "settings":
            validate_settings(payload)
        elif resource == "mapping":
            self.validate_mappings(payload)
        elif resource == "data":
            if payload.get("task") not in {"rebuild", "replay"}:
                raise AdminError("Datenvorschlag muss rebuild oder replay sein")
        else:
            raise AdminError("Unbekannte Ressource")
        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            head = c.execute("SELECT revision FROM head WHERE resource=?", (resource,)).fetchone()
            if not head or head[0] != parent:
                raise AdminError("Veraltete Basis; aktuellen Stand laden")
            rid = uuid.uuid4().hex
            c.execute(
                "INSERT INTO revision VALUES (?,?,?,?,?,?,?,?)",
                (
                    rid,
                    resource,
                    parent,
                    encode(payload),
                    digest(payload),
                    actor.strip(),
                    reason.strip(),
                    now(),
                ),
            )
            if supersedes:
                old = c.execute(
                    "SELECT actor,resource,parent FROM revision WHERE id=?", (supersedes,)
                ).fetchone()
                if (
                    not old
                    or not old["parent"]
                    or old["resource"] != resource
                    or old["actor"].strip().casefold() != actor.strip().casefold()
                ):
                    raise AdminError("Nur eigenen offenen Vorschlag ersetzen")
                if c.execute("SELECT 1 FROM decision WHERE revision=?", (supersedes,)).fetchone():
                    raise AdminError("Revision wurde bereits entschieden")
                if c.execute(
                    "SELECT 1 FROM impact WHERE revision_id=? AND status='RUNNING'", (supersedes,)
                ).fetchone():
                    raise AdminError("Laufenden Impact zuerst abschliessen lassen")
                c.execute(
                    "INSERT INTO decision(id,revision,decision,actor,reason,decided_at) VALUES (?,?,?,?,?,?)",
                    (
                        uuid.uuid4().hex,
                        supersedes,
                        "superseded",
                        actor.strip(),
                        "Ersetzt durch " + rid + ": " + reason.strip(),
                        now(),
                    ),
                )
                c.execute(
                    "UPDATE job SET status='CANCELLED',finished_at=? WHERE id IN (SELECT id FROM impact WHERE revision_id=?) AND status='QUEUED'",
                    (now(), supersedes),
                )
                c.execute(
                    "UPDATE impact SET status='SUPERSEDED' WHERE revision_id=? AND status IN ('QUEUED','READY')",
                    (supersedes,),
                )
            from .candidates import queue_in_transaction

            queue_in_transaction(self, c, rid, actor.strip())
        return rid

    def propose_mapping(self, city, code, target, parent, actor, reason):
        """One source-code override; no substring/similarity-based automatic mapping.

        Writes mapping_overrides.csv, never the generated crosswalk. Choosing
        the crosswalk's own target again removes the override.
        """
        current = self.current("mapping")
        if current["id"] != parent:
            raise AdminError("Veraltete Mappingbasis")
        if city not in CROSSWALKS:
            raise AdminError("Unbekannte Stadt")
        if not reason.strip() or "\n" in reason or "\r" in reason:
            raise AdminError("Begruendung als eine Zeile erforderlich")
        files = current["payload"]
        name, key, dest = CROSSWALKS[city]
        selected = [r for r in rows(files[name])[1] if r[key] == code]
        if len(selected) != 1:
            raise AdminError(
                "Quellcode nicht eindeutig vorhanden; neue Codes erfordern Code-Review"
            )
        _, codes = rows(files["nibrs_offense_codes_2025.csv"])
        if target not in {r["nibrs_code"] for r in codes} or target == "90Z":
            raise AdminError("Einen konkreten vorhandenen NIBRS-Zielcode waehlen")
        overrides = [
            r for r in rows(files[OVERRIDES])[1] if (r["city"], r["source_code"]) != (city, code)
        ]
        crosswalk = selected[0]
        if not (crosswalk["mapped"] == "true" and crosswalk[dest] == target):
            overrides.append(
                {"city": city, "source_code": code, "nibrs_code": target, "reason": reason}
            )
        overrides.sort(key=lambda r: (r["city"], r["source_code"]))
        files[OVERRIDES] = write_rows(OVERRIDES, OVERRIDE_FIELDS, overrides)
        return self.propose("mapping", files, parent, actor, reason)

    def decide(self, rid, choice, actor, reason, *, impact_id=None, report_hash=None):
        """Approval binds the exact reviewed, checked candidate and publishes it."""
        from .candidates import decide

        return decide(self, rid, choice, actor, reason, impact_id, report_hash)

    def retry_impact(self, rid, actor):
        from .candidates import queue_in_transaction

        with self.db() as c:
            c.execute("BEGIN IMMEDIATE")
            return queue_in_transaction(self, c, rid, actor)

    def materialize(self, rid):
        """Write immutable job config; verify every reuse, never change repo config."""
        r = self.get(rid)
        if r["resource"] != "mapping":
            raise AdminError("Keine Mappingrevision")
        target = self.root / "config_versions" / rid
        target.mkdir(parents=True, exist_ok=True)
        for name, content in r["payload"].items():
            if Path(name).name != name or not name.endswith(".csv"):
                raise AdminError("Ungueltiger Konfigurationsname")
            path = target / name
            if path.exists():
                if path.read_bytes() != content.encode("utf-8"):
                    raise AdminError("Konfigurationssnapshot wurde nachtraeglich veraendert")
            else:
                with path.open("x", encoding="utf-8", newline="") as f:
                    f.write(content)
        return target

    def history(self):
        with self.db() as c:
            revisions = [
                dict(r)
                for r in c.execute("""SELECT r.id,r.resource,r.parent,
                r.sha256,r.actor,r.reason,r.created_at,d.decision,d.actor AS reviewer,
                d.reason AS decision_reason,d.decided_at,d.impact_id,d.impact_report_sha256 FROM revision r
                LEFT JOIN decision d ON r.id=d.revision ORDER BY r.created_at DESC""")
            ]
            jobs = [
                dict(r) for r in c.execute("SELECT * FROM job ORDER BY queued_at DESC LIMIT 100")
            ]
            impacts = [dict(r) for r in c.execute("SELECT * FROM impact ORDER BY created_at DESC")]
        with self.db() as c:
            archives = [
                dict(r) for r in c.execute("SELECT * FROM impact_archive ORDER BY created_at DESC")
            ]
            events = [
                dict(r) for r in c.execute("SELECT * FROM release_event ORDER BY created_at DESC")
            ]
        from .progress import read

        for job in jobs:
            job["progress"] = read(self.root / "jobs" / job["id"])
        return {
            "revisions": revisions,
            "jobs": jobs,
            "impacts": impacts,
            "archives": archives,
            "release_events": events,
        }
