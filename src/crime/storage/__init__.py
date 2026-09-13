"""Die Datenablage: lokal, SeaweedFS ueber S3, oder hybrid.

    Hybrid READ:    lokal zuerst, S3 als Rueckfall
    Hybrid WRITE:   lokal, pruefen, dann gezielt nach S3 publizieren
    Serving DuckDB: immer lokal

Der Modus kommt aus ``STORAGE_BACKEND`` (``local`` ist die Vorgabe), die
uebrige Konfiguration aus der Umgebung oder ``.env`` - siehe ``config``.
Pipelines holen sich die Ablage mit ``get_storage()`` beziehungsweise
``for_root(data_root)``, wenn eine ``--data-root`` uebergeben wurde.

Die kleine API fuer Notebooks und Skripte (an der Standardablage)::

    from storage import resolve_read_path, exists, read_text
    pfad = resolve_read_path("silver", "dataset=crime_offense", "part-0001.parquet")
"""

from __future__ import annotations

from pathlib import Path

from storage.backend import (
    Boto3Client,
    FakeS3Client,
    PublishError,
    S3Client,
    Storage,
    manifest_von,
)
from storage.config import BACKENDS, Config, StorageConfigError, load

__all__ = [
    "BACKENDS", "Boto3Client", "Config", "FakeS3Client", "PublishError",
    "S3Client", "Storage", "StorageConfigError", "load", "manifest_von",
    "get_storage", "set_storage", "for_root",
    "storage_path", "local_path", "s3_path", "resolve_read_path",
    "publish_to_shared_storage", "exists", "list_files", "read_text", "write_text",
]

_standard: Storage | None = None


def get_storage() -> Storage:
    """Die Ablage aus der Umgebung - einmal gelesen, dann wiederverwendet."""
    global _standard
    if _standard is None:
        _standard = Storage(load())
    return _standard


def set_storage(storage: Storage | None) -> None:
    """Fuer Tests: eine bestimmte Ablage unterschieben, oder mit None vergessen."""
    global _standard
    _standard = storage


def for_root(data_root: Path | None) -> Storage:
    """Die Standardablage, bei Bedarf mit der lokalen Wurzel aus ``--data-root``."""
    basis = get_storage()
    if data_root is None:
        return basis
    return basis.mit_wurzel(Path(data_root))


# -- Bequeme Funktionen an der Standardablage --------------------------------

def storage_path(*teile: str | Path) -> str:
    return get_storage().storage_path(*teile)


def local_path(*teile: str | Path) -> Path:
    return get_storage().local_path(*teile)


def s3_path(*teile: str | Path) -> str:
    return get_storage().s3_path(*teile)


def resolve_read_path(*teile: str | Path) -> str:
    return get_storage().resolve_read_path(*teile)


def exists(*teile: str | Path) -> bool:
    return get_storage().exists(*teile)


def list_files(prefix: str | Path, muster: str = "**/*") -> list[str]:
    return get_storage().list_files(prefix, muster)


def read_text(*teile: str | Path) -> str:
    return get_storage().read_text(*teile)


def write_text(text: str, *teile: str | Path) -> Path:
    return get_storage().write_text(text, *teile)


def publish_to_shared_storage(*teile: str | Path) -> list[str]:
    """Ein Verzeichnis (Lauf oder Tabelle) gezielt publizieren.

    Ein ``run_<id>``-Verzeichnis gilt als unveraenderlich, alles andere als
    abgeleitete Tabelle, die ueberschrieben werden darf.
    """
    storage = get_storage()
    rel = storage.storage_path(*teile)
    if rel.rsplit("/", 1)[-1].startswith("run_"):
        return storage.publish_run(rel)
    return storage.publish_table(rel)
