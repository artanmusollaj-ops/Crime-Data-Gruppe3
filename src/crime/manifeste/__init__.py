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

import hashlib
import json
import subprocess
from functools import lru_cache
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

# Dasselbe noch einmal, fuer den Lademodus - nur steht er zusaetzlich in zwei
# verschiedenen Schluesseln. Chicagos Ingestion schreibt ``mode`` mit
# ``full_snapshot``, Detroits ``extraction_mode`` mit ``FULL``. Census, TIGER
# und NOAA nennen gar keinen Modus; sie laden immer voll, und ein Lauf ohne
# Angabe gilt deshalb **nicht** als Vollabzug - wer die Unterscheidung
# braucht, soll sie im Manifest finden und nicht erraten.
VOLLABZUG = frozenset({"full", "full_snapshot"})


class ManifestFehler(RuntimeError):
    """Ein Manifest liegt da, laesst sich aber nicht lesen."""


class Lauf(NamedTuple):
    """Ein fertiger Lauf: sein Verzeichnis und sein Manifest.

    ``relativ`` ist der Ablagepfad unter der Wurzel (``bronze/city=.../run_x``),
    gesetzt von ``storage.Storage.laeufe``; bei einem Lauf, der nur auf S3
    liegt, existiert ``verzeichnis`` lokal nicht.
    """

    verzeichnis: Path
    manifest: dict[str, Any]
    relativ: str = ""

    @property
    def run_id(self) -> str:
        # Chicago, Census, NOAA: run_id. Detroit: pipeline_run_id.
        return str(
            self.manifest.get("run_id")
            or self.manifest.get("pipeline_run_id")
            or self.verzeichnis.name
        )

    @property
    def begonnen_um(self) -> str:
        # started_at bei Detroit, started_at_utc bei Chicago, Census, TIGER
        # und NOAA. Gebraucht wird er, wo Laeufe in ihre zeitliche Reihenfolge
        # gebracht werden muessen: Detroits Laufverzeichnisse heissen nach
        # einer UUID und sagen nichts ueber die Reihenfolge.
        return str(
            self.manifest.get("started_at")
            or self.manifest.get("started_at_utc")
            or ""
        )

    @property
    def vollabzug(self) -> bool:
        """Ob der Lauf ein Vollschnappschuss ist - und nicht ein Delta.

        Wer Schnappschuesse vergleicht, darf nur Vollabzuege nehmen: Ein Delta
        enthaelt nur die bewegten Zeilen, und *was fehlt* laesst sich darin
        nicht von *was sich nicht geaendert hat* unterscheiden.
        """
        return str(
            self.manifest.get("extraction_mode")
            or self.manifest.get("mode")
            or ""
        ).lower() in VOLLABZUG

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
    relativ: str = ""

    @property
    def zeilen(self) -> int | None:
        zahl = self.manifest.get("row_count")
        if zahl is None:
            zahl = self.manifest.get("rows")
        return int(zahl) if zahl is not None else None


@lru_cache(maxsize=1)
def code_stand() -> dict[str, Any]:
    """Welcher Code diesen Lauf erzeugt hat - Commit und Sauberkeit.

    Das ist die **forensische** Haelfte der Frage *"ab wann wurden die Daten
    anders geladen?"*: Der Commit sagt genau, welcher Code lief. Was er nicht
    sagt, ist ob sich die **Bedeutung** geaendert hat - er springt auch bei
    einem Tippfehler im Kommentar. Dafuer gibt es ``contract_version``.

    ``dirty`` ist wichtiger, als es aussieht: Ein Lauf aus einem veraenderten
    Arbeitsbaum laesst sich aus dem Commit allein **nicht** nachbauen. Wer
    das spaeter wissen will, findet es hier statt es zu vermuten.

    Ohne Git - installiertes Paket, kein Repository, kein git im Pfad -
    bleibt es bei ``None``. Ein Lauf darf daran nie scheitern.
    """
    wurzel = Path(__file__).resolve().parents[3]

    def git(*argumente: str) -> str | None:
        try:
            fertig = subprocess.run(
                ["git", "-C", str(wurzel), *argumente],
                capture_output=True, text=True, timeout=10,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        return fertig.stdout.strip() if fertig.returncode == 0 else None

    commit = git("rev-parse", "HEAD")
    if commit is None:
        return {"git_commit": None, "git_dirty": None}
    geaendert = git("status", "--porcelain")
    return {"git_commit": commit, "git_dirty": bool(geaendert)}


def fingerabdruck(wert: Any) -> str:
    """Ein Abdruck ueber die Eingaben - derselbe Stand, derselbe Abdruck.

    Kanonisch heisst: sortierte Schluessel. Zwei Tabellen mit demselben
    Abdruck ruhen auf denselben Eingaben, gleichgueltig in welcher
    Reihenfolge sie gefunden wurden.
    """
    roh = json.dumps(wert, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(roh.encode("utf-8")).hexdigest()


# Was sagt, *wo* und *wann* - nicht, *was*. Beides faellt aus dem Abdruck.
FLUECHTIG = ("path", "built_at_utc")


def kennzeichen(wert: Any) -> Any:
    """Nur die Teile einer Herkunft, die den Eingabestand kennzeichnen.

    Pfade und Bauzeitpunkte fallen weg. Der Grund ist der gemeinsame
    Speicher: Derselbe Stand liegt bei Christian unter ``/Users/...`` und bei
    Artan anderswo, und ein zweiter Bau aus denselben Eingaben findet zu einer
    anderen Uhrzeit statt. Beides darf den Abdruck nicht veraendern, sonst
    traegt derselbe Stand zwei Abdruecke und die Zusage ist wertlos.

    Was bleibt, ist das Kennzeichnende: Lauf-Kennungen, Pruefsummen und die
    Abdruecke der Vorgaenger.
    """
    if isinstance(wert, dict):
        return {k: kennzeichen(v) for k, v in wert.items() if k not in FLUECHTIG}
    if isinstance(wert, list):
        return [kennzeichen(v) for v in wert]
    return wert


def eingabe_abdruck(herkunft: Any) -> str:
    """Der Abdruck ueber die Eingaben - derselbe Stand, derselbe Abdruck."""
    return fingerabdruck(kennzeichen(herkunft))


def datei_hash(pfad: Path) -> str:
    """SHA-256 einer Referenzdatei - fuer Crosswalks und Codelisten.

    Ein Pfad sagt nur, *wo* etwas lag. Wer eine Zahl erklaeren will, braucht
    aber, *was* dort stand: Die Crosswalks werden aus amtlichen PDFs erzeugt
    und koennen sich aendern, ohne dass der Pfad sich aendert.
    """
    h = hashlib.sha256()
    with pfad.open("rb") as datei:
        for block in iter(lambda: datei.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def referenz(pfad: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    """Wie eine abgeleitete Tabelle genannt wird, wenn eine andere auf ihr ruht.

    **Ein Pfad ist keine Version.** ``data/silver/dataset=crime_offense/
    part-0001.parquet`` zeigt auf das, was gerade dort liegt; wird Silver neu
    gebaut, zeigt derselbe Satz auf etwas anderes, und nichts verraet es.
    Deshalb nennt eine Referenz auch **wann** jener Stand gebaut wurde, auf
    **welchen Eingaben** er ruhte (``input_fingerprint``) und - woertlich -
    dessen eigene Herkunft. Damit ist die Kette im Manifest selbst
    verschachtelt: Gold nennt Silver, Silver nennt die Bronze-Laeufe.

    Das ersetzt keine Historisierung der Dateien. Es macht die Frage
    beantwortbar, aus welchen Eingaben eine Zahl entstanden ist - und das ist
    die Frage, die in einer Abgabe gestellt wird.
    """
    eintrag: dict[str, Any] = {"path": str(pfad)}
    for schluessel in ("built_at_utc", "input_fingerprint"):
        if manifest.get(schluessel):
            eintrag[schluessel] = manifest[schluessel]
    if manifest.get("derived_from") is not None:
        eintrag["derived_from"] = manifest["derived_from"]
    return eintrag


def referenzdatei(pfad: Path) -> dict[str, Any]:
    """Eine versionierte Referenzdatei mit ihrer Pruefsumme."""
    return {"path": str(pfad), "sha256": datei_hash(pfad)}


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
