"""Die Konfiguration der Datenablage, aus der Umgebung gelesen.

Drei Betriebsarten, gewaehlt ueber ``STORAGE_BACKEND``:

``local``
    Lesen und Schreiben ausschliesslich unter ``LOCAL_DATA_ROOT`` (Vorgabe
    ``data``). Das ist der bisherige Zustand des Projekts, unveraendert.
``s3``
    Lesen direkt von SeaweedFS (``s3://<bucket>/...``). Geschrieben wird
    trotzdem zuerst lokal - die Pipelines brauchen ein Arbeitsverzeichnis fuer
    ``.part`` und Umbenennen -, nach bestandener Pruefung publiziert, und die
    lokale Kopie danach entfernt. Ein lokaler Datenbestand ist weder noetig
    noch bleibt einer zurueck.
``hybrid``
    Lesen: lokal, wenn die Datei da ist, sonst SeaweedFS. Schreiben: lokal,
    pruefen, dann gezielt publizieren. Das lokale ``data/`` ist Arbeitskopie
    und Cache, SeaweedFS der gemeinsame veroeffentlichte Bestand.

Schluessel kommen aus der Umgebung oder ``.env``; ``.env`` ist nicht
versioniert. Nichts hiervon wird protokolliert.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv


BACKENDS = ("local", "s3", "hybrid")
VORGABE_ENDPOINT = "s3.datenwerft.ch"
VORGABE_BUCKET = "urban-crime"


class StorageConfigError(RuntimeError):
    """Die Umgebung beschreibt keine brauchbare Ablage."""


def wahr(text: str | None, vorgabe: bool) -> bool:
    if text is None or not text.strip():
        return vorgabe
    return text.strip().lower() in ("1", "true", "yes", "ja", "on")


@dataclass(frozen=True)
class Config:
    backend: str = "local"
    local_root: Path = Path("data")
    s3_endpoint: str = VORGABE_ENDPOINT
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_bucket: str = VORGABE_BUCKET
    s3_use_ssl: bool = True
    hybrid_read_priority: str = "local"
    hybrid_publish_after_write: bool = True

    @property
    def remote(self) -> bool:
        """Ob SeaweedFS ueberhaupt im Spiel ist."""
        return self.backend in ("s3", "hybrid")

    @property
    def liest_lokal(self) -> bool:
        return self.backend in ("local", "hybrid")

    @property
    def publiziert(self) -> bool:
        """Ob nach bestandener Pruefung nach SeaweedFS geschrieben wird."""
        if self.backend == "s3":
            return True
        return self.backend == "hybrid" and self.hybrid_publish_after_write

    @property
    def endpoint_url(self) -> str:
        schema = "https" if self.s3_use_ssl else "http"
        return f"{schema}://{self.s3_endpoint}"


def load(env: Mapping[str, str] | None = None, *, dotenv: bool = True) -> Config:
    """Liest die Konfiguration; ohne ``env`` aus ``os.environ`` plus ``.env``.

    ``.env`` ueberschreibt nie, was in der Umgebung schon steht - so kann CI
    Secrets setzen, ohne dass eine mitgebrachte Datei dazwischenfunkt.
    """
    if env is None:
        if dotenv:
            pfad = find_dotenv(usecwd=True)
            if pfad:
                load_dotenv(pfad)
        env = os.environ

    backend = (env.get("STORAGE_BACKEND") or "local").strip().lower()
    if backend not in BACKENDS:
        raise StorageConfigError(
            f"STORAGE_BACKEND={backend!r} - erlaubt sind {', '.join(BACKENDS)}"
        )

    prioritaet = (env.get("HYBRID_READ_PRIORITY") or "local").strip().lower()
    if prioritaet != "local":
        raise StorageConfigError(
            f"HYBRID_READ_PRIORITY={prioritaet!r} - vorerst wird nur 'local' unterstuetzt"
        )

    config = Config(
        backend=backend,
        local_root=Path((env.get("LOCAL_DATA_ROOT") or "data").strip()),
        s3_endpoint=(env.get("S3_ENDPOINT") or VORGABE_ENDPOINT).strip(),
        s3_access_key=(env.get("S3_ACCESS_KEY") or "").strip(),
        s3_secret_key=(env.get("S3_SECRET_KEY") or "").strip(),
        s3_bucket=(env.get("S3_BUCKET") or VORGABE_BUCKET).strip(),
        s3_use_ssl=wahr(env.get("S3_USE_SSL"), True),
        hybrid_read_priority=prioritaet,
        hybrid_publish_after_write=wahr(env.get("HYBRID_PUBLISH_AFTER_WRITE"), True),
    )
    if config.remote and not (config.s3_access_key and config.s3_secret_key):
        raise StorageConfigError(
            f"STORAGE_BACKEND={backend} braucht S3_ACCESS_KEY und S3_SECRET_KEY "
            "(in der Umgebung oder in .env; .env wird nicht versioniert)"
        )
    if config.remote and not config.s3_bucket:
        raise StorageConfigError("S3_BUCKET darf nicht leer sein")
    return config
