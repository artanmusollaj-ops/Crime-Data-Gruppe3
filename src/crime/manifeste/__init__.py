"""Ein Leser fuer die Manifeste - statt elf.

Jede Schicht schreibt je Lauf oder Tabelle ein ``manifest.json``. Es zu finden
und zu lesen war am 13.9. an **elf Stellen** implementiert, jede ein wenig
anders: sieben kannten nur ``complete``, Detroits Leser nur ``SUCCESS``, der
Controller beide; drei uebersprangen versteckte ``.part``-Verzeichnisse, die
uebrigen nicht; die Ingestion warf bei kaputtem JSON, der Controller warnte.
Als der Controller entstand, musste er jede dieser Eigenheiten einzeln
nachvollziehen - und vier der elf Stellen stammten vom selben Tag.

Hier steht es einmal. Was sich je Aufrufer unterscheidet, ist ein Parameter:

* ``muster``   - wo die Manifeste liegen (``run_*/manifest.json``,
                 ``ingest_date=*/run_*/manifest.json`` ...)
* ``fehler``   - welche Ausnahme ein kaputtes Manifest ausloest. Die
                 Ingestion sagt ``IngestionError``, Silver ``TransformError``;
                 ihre Tests haengen an diesen Typen
* ``streng``   - ob ein kaputtes Manifest wirft oder nur gewarnt wird. Fuer
                 eine Pipeline ist es ein Fehler in der eigenen Schicht; fuer
                 den Controller, der nur inventarisiert, eine Warnung

Was **nicht** hierhergehoert: ``detroit_pipeline.bronze_manifest.validate_manifest``.
Das ist kein Leser, sondern ein Zulassungstor mit Pruefsummen, Zeilenzahlen und
Schema-Fingerabdruck. Es prueft, ob ein Lauf *gilt* - hier wird nur gefunden,
ob er *fertig* ist.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, NamedTuple


LOG = logging.getLogger("manifeste")

MANIFEST = "manifest.json"
PARQUET_FILE = "part-0001.parquet"

# Beide Vokabulare gelten. Acht Module schreiben ``complete``, Detroits
# Ingestion ``SUCCESS``. Das zu vereinheitlichen wuerde jedes bereits
# geschriebene Manifest ungueltig machen, fuer einen kosmetischen Gewinn.
FERTIG = frozenset({"complete", "success"})


class ManifestFehler(RuntimeError):
    """Ein Manifest liegt da, laesst sich aber nicht lesen."""


class Lauf(NamedTuple):
    """Ein fertiger Lauf: sein Verzeichnis und sein Manifest."""

    verzeichnis: Path
    manifest: dict[str, Any]

    @property
    def run_id(self) -> str:
        # Chicago, Census, NOAA: run_id. Detroit: pipeline_run_id.
        return str(
            self.manifest.get("run_id")
            or self.manifest.get("pipeline_run_id")
            or self.verzeichnis.name
        )

    @property
    def abgeschlossen_um(self) -> str:
        # completed_at_utc bei acht Modulen, finished_at bei Detroit.
        return str(
            self.manifest.get("completed_at_utc")
            or self.manifest.get("finished_at")
            or self.manifest.get("built_at_utc")
            or ""
        )

    @property
    def zeilen(self) -> int:
        # row_count bei acht Modulen, downloaded_count bei Detroit.
        return int(
            self.manifest.get("row_count")
            or self.manifest.get("downloaded_count")
            or 0
        )

    def datei(self, vorgabe: str = PARQUET_FILE) -> Path:
        """Die Datendatei des Laufs - Detroit nennt sie im Manifest."""
        return self.verzeichnis / str(self.manifest.get("bronze_file") or vorgabe)


class Tabelle(NamedTuple):
    """Eine gebaute Silver- oder Gold-Tabelle."""

    schicht: str
    name: str
    verzeichnis: Path
    manifest: dict[str, Any]

    @property
    def zeilen(self) -> int | None:
        zahl = self.manifest.get("row_count")
        if zahl is None:
            zahl = self.manifest.get("rows")
        return int(zahl) if zahl is not None else None


def versteckt(pfad: Path) -> bool:
    """Ein ``.part``- oder ``.partial``-Verzeichnis ist ein Lauf, der noch nicht gilt.

    ``.`` und ``..`` zaehlen nicht - sonst waere unter ``--data-root ../data``
    jeder Lauf versteckt, und der Leser meldete stumm: nichts da.
    """
    return any(teil.startswith(".") and teil not in (".", "..") for teil in pfad.parts)


def read_manifest(
    pfad: Path,
    *,
    streng: bool = True,
    fehler: type[Exception] = ManifestFehler,
) -> dict[str, Any] | None:
    """Liest ein ``manifest.json``. Kaputt: werfen (streng) oder warnen und ``None``."""
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        if streng:
            raise fehler(f"Invalid manifest: {pfad}") from error
        LOG.warning("Manifest nicht lesbar, uebersprungen: %s", pfad)
        return None


def fertige_laeufe(
    wurzel: Path,
    muster: str = f"**/run_*/{MANIFEST}",
    *,
    streng: bool = True,
    fehler: type[Exception] = ManifestFehler,
    status: frozenset[str] = FERTIG,
) -> list[Lauf]:
    """Alle fertigen Laeufe unter ``wurzel``, nach Pfad sortiert.

    Nach Pfad sortiert heisst bei ``run_<UTC-Zeitstempel>``: der letzte ist der
    juengste. Versteckte Verzeichnisse zaehlen nie. Ein Lauf, dessen Manifest
    nicht ``fertig`` sagt, wird mit Warnung uebersprungen - er liegt da, gilt
    aber nicht.
    """
    if not wurzel.exists():
        return []
    laeufe: list[Lauf] = []
    for pfad in sorted(wurzel.glob(muster)):
        if versteckt(pfad):
            continue
        manifest = read_manifest(pfad, streng=streng, fehler=fehler)
        if manifest is None:
            continue
        if str(manifest.get("status", "")).lower() not in status:
            LOG.warning("Lauf uebersprungen, nicht fertig: %s", pfad.parent)
            continue
        laeufe.append(Lauf(pfad.parent, manifest))
    return laeufe


def tabellen(
    data_root: Path,
    schichten: tuple[str, ...] = ("silver", "gold"),
    *,
    fehler: type[Exception] = ManifestFehler,
) -> list[Tabelle]:
    """Jede gebaute Tabelle unter den Schichten, nach Schicht und Name sortiert.

    Gesucht wird ``dataset=<name>/**/manifest.json``; liegt eine Tabelle
    unter einer ``vintage=``, findet der Glob sie trotzdem.
    """
    gefunden: list[Tabelle] = []
    for schicht in schichten:
        wurzel = data_root / schicht
        if not wurzel.exists():
            continue
        for pfad in sorted(wurzel.glob(f"dataset=*/**/{MANIFEST}")):
            if versteckt(pfad):
                continue
            manifest = read_manifest(pfad, streng=True, fehler=fehler)
            name = next(
                t for t in pfad.parts if t.startswith("dataset=")
            ).removeprefix("dataset=")
            gefunden.append(Tabelle(schicht, name, pfad.parent, manifest or {}))
    return sorted(gefunden, key=lambda t: (t.schicht, t.name))
