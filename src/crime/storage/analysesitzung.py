"""Lokale Analysen auf einem belegten Pipeline-Bestand, ohne parallele Schreiber.

Die Sperre ist eine Host-Absprache, keine Zugriffsgrenze. Alle Container muessen
denselben DATA_LOCK_ROOT einhaengen. Ohne Vorgabe liegt sie unter data/.analyse.
Sperrdateien niemals loeschen: Die Betriebssystem-Sperre endet mit dem Prozess.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


class AnalyseFehler(RuntimeError):
    """Kein stabiler, nachgewiesener Analysebestand verfuegbar."""


def _hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.with_name(path.name + ".part")
    work.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    work.replace(path)


def _lock_path(root):
    shared = os.getenv("DATA_LOCK_ROOT")
    if shared:
        key = hashlib.sha256(str(root).encode()).hexdigest()
        return Path(shared) / (key + ".lock")
    return root / ".analyse" / "zugriff.lock"


def _acquire(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(stream):
    stream.seek(0)
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


# Nur Schreibsitzungen geben ihre Berechtigung an Pipeline-Kindprozesse weiter.
# Notebooks bekommen niemals ein solches Token.
@contextmanager
def datensperre(data_root, *, schreiben=False):
    root = Path(data_root).resolve()
    path = _lock_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    authority = path.with_suffix(".json")
    inherited = json.loads(os.getenv("CRIME_DATA_LOCKS", "{}"))
    token = inherited.get(str(root)) if schreiben else None
    stream = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
        try:
            _acquire(stream)
        except OSError as exc:
            # Eine Kindpipeline darf die noch gehaltene Elternsperre mitnutzen.
            try:
                owner = json.loads(authority.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                owner = {}
            if token and owner.get("token") == token:
                yield root
                return
            raise AnalyseFehler(
                "Datenbestand belegt: Analyse oder Schreiber laeuft. "
                "Analysesitzung beenden und erneut versuchen. Keine Sperrdatei loeschen."
            ) from exc
        old = os.environ.get("CRIME_DATA_LOCKS")
        try:
            if schreiben:
                token = uuid.uuid4().hex
                _json(authority, {"token": token, "pid": os.getpid()})
                os.environ["CRIME_DATA_LOCKS"] = json.dumps({**inherited, str(root): token})
            yield root
        finally:
            if schreiben:
                authority.unlink(missing_ok=True)
                if old is None:
                    os.environ.pop("CRIME_DATA_LOCKS", None)
                else:
                    os.environ["CRIME_DATA_LOCKS"] = old
            _release(stream)
    finally:
        stream.close()


@contextmanager
def schreibzugriff(data_root, *, invalidieren=True):
    """Umschliesst den ganzen Schreibvorgang, auch Fehler und Kindprozesse."""
    with datensperre(data_root, schreiben=True) as root:
        if invalidieren:
            (root / ".analyse" / "stand.json").unlink(missing_ok=True)
        yield root


def _inventory(root):
    return {
        p.relative_to(root).as_posix(): _hash(p)
        for layer in ("bronze", "silver", "gold")
        for p in sorted((root / layer).rglob("*"))
        if p.is_file() and (p.suffix == ".parquet" or p.name == "manifest.json")
        and not any(x.startswith(".") for x in p.relative_to(root).parts)
    }


def bestaetige(data_root, *, run_id, projekt_root, release_id=None, status="Arbeitsbestand",
               bereiche=("silver", "gold")):
    """Nur nach erfolgreichem Aufbau unter gehaltener Schreibsperre aufrufen.

    Der Nachweis bleibt vom ueberschriebenen pipeline_run.json unabhaengig.
    Er benennt genau die lokalen Bytes; er bestaetigt keine Review-Freigabe.
    """
    root = Path(data_root).resolve()
    commit, code_dirty = os.getenv("GIT_COMMIT"), None
    if (Path(projekt_root) / ".git").exists() and shutil.which("git"):
        result = subprocess.run(["git", "-C", str(projekt_root), "rev-parse", "HEAD"],
                                capture_output=True, text=True, check=False)
        if result.returncode == 0:
            commit = result.stdout.strip()
            dirty = subprocess.run(["git", "-C", str(projekt_root), "status", "--porcelain"],
                                   capture_output=True, text=True, check=False)
            if dirty.returncode == 0:
                code_dirty = bool(dirty.stdout.strip())
    files = _inventory(root)
    value = {"version": 1, "run_id": run_id, "release_id": release_id,
             "bereiche": list(bereiche), "code_dirty": code_dirty,
             "status": status, "code_commit": commit,
             "finished_at_utc": datetime.now(timezone.utc).isoformat(), "files": files}
    _json(root / ".analyse" / "stand.json", value)
    return value

