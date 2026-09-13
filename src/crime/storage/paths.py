"""Relative Ablagepfade - die eine Adresse, die alle Backends verstehen.

Alles Persistierte wird intern relativ zur Ablagewurzel adressiert::

    bronze/city=chicago/ingest_date=2026-09-13/run_abc/part-0001.parquet

Daraus macht das Backend ``data/...`` oder ``s3://urban-crime/...``. Die
Struktur unter der Wurzel ist in allen Backends dieselbe.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class PfadFehler(ValueError):
    """Ein Teil laesst sich nicht als relativer Ablagepfad deuten."""


def relativ(*teile: str | Path) -> str:
    """Fuegt Teile zu einem relativen POSIX-Pfad zusammen.

    Backslashes werden zu Schraegstrichen (Windows), fuehrende ``./`` und
    ``/`` fallen weg. ``..`` und absolute Pfade sind keine Ablagepfade.
    """
    segmente: list[str] = []
    for teil in teile:
        text = str(teil).replace("\\", "/")
        if text.startswith("/") or (len(text) > 1 and text[1] == ":"):
            raise PfadFehler(f"kein relativer Ablagepfad: {teil!r}")
        for segment in text.split("/"):
            if segment in ("", "."):
                continue
            if segment == "..":
                raise PfadFehler(f"'..' ist in Ablagepfaden nicht erlaubt: {teil!r}")
            segmente.append(segment)
    return "/".join(segmente)


def s3_url(bucket: str, rel: str) -> str:
    return f"s3://{bucket}/{rel}" if rel else f"s3://{bucket}"


def unter_wurzel(wurzel: Path, pfad: Path) -> str | None:
    """Der relative Ablagepfad eines lokalen Pfads - oder None, wenn er
    nicht unter der Wurzel liegt."""
    try:
        rel = pfad.resolve().relative_to(wurzel.resolve())
    except ValueError:
        return None
    return PurePosixPath(*rel.parts).as_posix()


def versteckt(rel: str) -> bool:
    """``.part``- und ``.partial``-Verzeichnisse sind nichts Veroeffentlichtes."""
    return any(teil.startswith(".") for teil in rel.split("/"))
