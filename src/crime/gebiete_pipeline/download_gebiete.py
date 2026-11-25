"""Laedt die Grenzen der Polizeibezirke in unveraenderliche Laeufe.

    python -m gebiete_pipeline.download_gebiete

Eine Auslieferung je Stadt und Ebene, heute eine Ebene: der Polizeibezirk
(Chicago District, Detroit Precinct). Raw haelt die GeoJSON-Datei Byte fuer
Byte, wie das Portal sie liefert; Bronze ist daraus abgeleitetes Parquet mit
der Geometrie als WKB, wie bei ``census_pipeline.download_tiger``.

**Jeder Aufruf schreibt einen Lauf**, anders als TIGER. Eine TIGER-Vintage ist
eingefroren und wird einmal geladen. Die Polizeibezirke dagegen sind der
*aktuelle* Stand eines Portals - Chicago nennt den Datensatz ausdruecklich
»current« -, und ob sich eine Grenze geaendert hat, sieht man nur, wenn man
nachsieht. Beide Dateien zusammen sind rund 1,1 MB; ein Lauf je Woche kostet
weniger, als ein eigener Pruefweg kostete, und haelt die Quelle in derselben
Altersregel wie Taten und Wetter. Ob sich etwas geaendert hat, sagt der
SHA-256 der Raw-Datei im Manifest, nebeneinander gehalten.

**Vollstaendig** heisst: Das Portal nennt auf eine zweite Frage, wie viele
Polygone es fuehrt, und genau so viele kommen in Bronze an. Ein GeoJSON ohne
Zaehlung waere nur »lesbar«, nicht »vollstaendig«.

Nichts wird gedeutet. Chicagos District 31 kommt als drei Polygone, Detroits
Precinct 07 als zwei; Bronze behaelt jedes, zusammengelegt wird in Silver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from pyogrio.raw import read_arrow
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from manifeste import code_stand
from storage import PublishError, for_root

log = logging.getLogger("gebiete_ingestion")


# Die vier Helfer gleichen denen in ``census_pipeline.download_tiger``. Sie
# stehen hier noch einmal, weil zwischen den Ingestion-Paketen keine Kante
# sein soll (``docs/architektur.md``, getestet in test_architekturbilder).


def json_text(value: Any) -> str:
    """Kompakt und deterministisch."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def extra_column(extra: dict[str, list[Any]], rows: int) -> list[str | None]:
    """Je Zeile ein JSON-Objekt mit allem, was nicht ins Schema passte."""
    werte: list[str | None] = []
    for i in range(rows):
        zeile = {n: spalte[i] for n, spalte in extra.items() if spalte[i] is not None}
        werte.append(json_text(zeile) if zeile else None)
    return werte


def file_entry(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": path.name, "size_bytes": path.stat().st_size, "sha256": digest}


def publish_directory(work: Path, final: Path) -> None:
    """Atomar umbenennen, nie ueberschreiben."""
    if final.exists():
        raise FileExistsError(f"Lauf existiert bereits: {final}")
    work.rename(final)

USER_AGENT = "crime-data-gruppe3/0.1 (Hochschulprojekt CAS Data Engineering)"
# Der Ladevertrag; siehe "Vertragsversionen" in AENDERUNGEN.md.
CONTRACT_VERSION = 1

DATASET = "gebiete"
RAW_LAYER = "raw"
BRONZE_LAYER = "bronze"
LAYERS = (RAW_LAYER, BRONZE_LAYER)
LAYER_FORMAT = {
    RAW_LAYER: "application/geo+json (unveraendert, wie ausgeliefert)",
    BRONZE_LAYER: "parquet (snappy, Geometrie als WKB)",
}
RAW_FILE = "gebiete.geojson"
PARQUET_FILE = "part-0001.parquet"

TIMEOUT_SECONDS = 120
RETRY_TOTAL = 5
RETRY_BACKOFF = 1.0
RETRY_STATUS = (429, 500, 502, 503, 504)
STALE_PARTIAL_HOURS = 24

# Beide Portale liefern GeoJSON in WGS84 (RFC 7946 laesst nichts anderes zu),
# wie die Koordinaten der Taten.
EXPECTED_CRS = "EPSG:4326"

GEOMETRY_COLUMN = "geometry"
SOURCE_GEOMETRY_COLUMN = "wkb_geometry"
EXTRA_COLUMN = "_extra"

#: Das gepinnte Bronze-Schema, fuer jede Auslieferung dasselbe. Kennung und
#: Name kommen aus je einem Feld der Quelle, wie es dort heisst; alles andere
#: geht nach ``_extra``.
SCHEMA = pa.schema([
    pa.field("gebiet_id", pa.string()),
    pa.field("gebiet_name", pa.string()),
    pa.field(GEOMETRY_COLUMN, pa.binary()),
    pa.field(EXTRA_COLUMN, pa.string()),
])


class Auslieferung(NamedTuple):
    """Eine Grenzdatei: wo sie liegt und welche Felder Kennung und Name tragen."""

    stadt: str
    ebene: str
    plattform: str
    url: str
    zaehl_url: str
    id_feld: str
    name_feld: str
    quelle: str


#: **Chicago:** »Boundaries - Police Districts (current)«, City of Chicago Data
#: Portal, Datensatz ``24zt-jpfn`` (https://data.cityofchicago.org/d/24zt-jpfn),
#: ueber die Socrata-API als GeoJSON. 25 Polygone fuer 23 Districts.
#:
#: **Detroit:** »DPD Precincts«, ArcGIS Online der City of Detroit, Layer
#: ``DPD_Precincts_Reid2`` (Ordner »2015 New Precincts Overlay«), als GeoJSON
#: mit ``outSR=4326``. Zwoelf Polygone fuer elf Precincts. Ein neuerer Layer
#: ist im selben Dienst nicht veroeffentlicht; gemessen am 25.11.2026 liegen
#: 96,6 % der Taten von 2024 im Polygon des Precincts, den die Polizei nennt,
#: in Chicago 97,4 %.
AUSLIEFERUNGEN: tuple[Auslieferung, ...] = (
    Auslieferung(
        stadt="chicago", ebene="polizeibezirk", plattform="socrata",
        url="https://data.cityofchicago.org/resource/24zt-jpfn.geojson?$limit=1000",
        zaehl_url="https://data.cityofchicago.org/resource/24zt-jpfn.json?$select=count(*)",
        id_feld="dist_num", name_feld="dist_label",
        quelle="Chicago Data Portal 24zt-jpfn, Boundaries - Police Districts (current)",
    ),
    Auslieferung(
        stadt="detroit", ebene="polizeibezirk", plattform="arcgis",
        url=("https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
             "DPD_Precincts_Reid2/FeatureServer/0/query"
             "?where=1%3D1&outFields=*&outSR=4326&f=geojson"),
        zaehl_url=("https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/"
                   "DPD_Precincts_Reid2/FeatureServer/0/query"
                   "?where=1%3D1&returnCountOnly=true&f=json"),
        id_feld="name", name_feld="name",
        quelle="City of Detroit ArcGIS, DPD_Precincts_Reid2 (2015 New Precincts Overlay)",
    ),
)


class IngestionError(RuntimeError):
    """Ein Lauf liess sich nicht sicher laden oder ablegen."""


class Datei(NamedTuple):
    payload: bytes
    url: str
    erwartet: int
    last_modified: str | None


class RunPaths(NamedTuple):
    raw: Path
    bronze: Path


def run_parent(data_root: Path, layer: str, aus: Auslieferung) -> Path:
    return (data_root / layer / f"dataset={DATASET}" / f"ebene={aus.ebene}"
            / f"city={aus.stadt}")


def build_session() -> requests.Session:
    retry = Retry(total=RETRY_TOTAL, backoff_factor=RETRY_BACKOFF,
                  status_forcelist=RETRY_STATUS,
                  allowed_methods=frozenset(["GET", "HEAD"]), raise_on_status=False)
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def zaehle(antwort: Any, aus: Auslieferung) -> int:
    """Wie viele Polygone das Portal nach eigener Angabe fuehrt."""
    try:
        if aus.plattform == "socrata":
            return int(antwort[0]["count"])
        return int(antwort["count"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise IngestionError(f"{aus.stadt}: Zaehlung unlesbar: {antwort!r}") from error


def lade(session: requests.Session, aus: Auslieferung) -> Datei:
    """Holt Zaehlung und Grenzdatei; eine HTML-Seite statt JSON bricht ab."""
    try:
        zaehlung = session.get(aus.zaehl_url, timeout=TIMEOUT_SECONDS)
        zaehlung.raise_for_status()
        erwartet = zaehle(zaehlung.json(), aus)
        antwort = session.get(aus.url, timeout=TIMEOUT_SECONDS)
        antwort.raise_for_status()
    except requests.RequestException as error:
        raise IngestionError(f"{aus.stadt}: Download fehlgeschlagen: {error}") from error
    except ValueError as error:
        raise IngestionError(f"{aus.stadt}: Zaehlung ist kein JSON") from error
    payload = antwort.content
    try:
        inhalt = json.loads(payload)
    except ValueError as error:
        raise IngestionError(f"{aus.stadt}: Grenzdatei ist kein JSON") from error
    if not isinstance(inhalt, dict) or inhalt.get("type") != "FeatureCollection":
        # ArcGIS antwortet auf einen Fehler mit HTTP 200 und {"error": ...}.
        raise IngestionError(f"{aus.stadt}: keine FeatureCollection: {str(inhalt)[:200]}")
    log.info("%s %s geladen: %s Byte, %s Polygone erwartet",
             aus.stadt, aus.ebene, f"{len(payload):,}", erwartet)
    return Datei(payload, aus.url, erwartet, antwort.headers.get("Last-Modified"))


def bronze_tabelle(quelle: pa.Table, aus: Auslieferung) -> pa.Table:
    """Kennung, Name und Geometrie heraus, alle anderen Felder nach ``_extra``."""
    namen = quelle.schema.names
    for feld in (aus.id_feld, aus.name_feld, SOURCE_GEOMETRY_COLUMN):
        if feld not in namen:
            raise IngestionError(f"{aus.stadt}: Feld {feld!r} fehlt in der Grenzdatei")
    extra = {n: quelle.column(n).to_pylist() for n in namen
             if n not in {aus.id_feld, aus.name_feld, SOURCE_GEOMETRY_COLUMN}}
    zeilen = quelle.num_rows
    als_text = [None if v is None else str(v) for v in quelle.column(aus.id_feld).to_pylist()]
    name = [None if v is None else str(v) for v in quelle.column(aus.name_feld).to_pylist()]
    return pa.Table.from_arrays([
        pa.array(als_text, pa.string()),
        pa.array(name, pa.string()),
        quelle.column(SOURCE_GEOMETRY_COLUMN).combine_chunks().cast(pa.binary()),
        pa.array(extra_column(extra, zeilen), pa.string()),
    ], schema=SCHEMA)


def quellschema(meta: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Fingerabdruck ueber die Felder der Quelle, wie bei TIGER."""
    felder = {str(n): str(t) for n, t in zip(meta.get("fields", []), meta.get("ogr_types", []))}
    return hashlib.sha256(json_text(felder).encode("utf-8")).hexdigest(), felder


def discard_stale_partials(data_root: Path, now: datetime) -> list[Path]:
    cutoff = (now - timedelta(hours=STALE_PARTIAL_HOURS)).timestamp()
    removed = []
    for layer in LAYERS:
        # Lokal mit Absicht: wie in `download_tiger` - ein `.part` wird nie
        # publiziert, und was geloescht wird, liegt unten.
        for path in sorted(data_root.glob(f"{layer}/dataset={DATASET}/*/*/.*.part")):
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                log.warning("Verwaister Teillauf entfernt: %s", path)
                removed.append(path)
    return removed


def write_run(data_root: Path, started: datetime, aus: Auslieferung, datei: Datei) -> RunPaths:
    """Schreibt Raw und Bronze und veroeffentlicht beide atomar, Raw zuerst."""
    run_id = started.strftime("run_%Y%m%dT%H%M%S%fZ")
    parents = {layer: run_parent(data_root, layer, aus) for layer in LAYERS}
    work = {layer: p / f".{run_id}.part" for layer, p in parents.items()}
    final = {layer: p / run_id for layer, p in parents.items()}
    for path in work.values():
        path.mkdir(parents=True)
    try:
        roh = work[RAW_LAYER] / RAW_FILE
        roh.write_bytes(datei.payload)
        try:
            # Aus der gelandeten Datei gelesen, nicht aus dem Speicher: Bronze
            # ist so nachweislich aus dem Beweisstueck abgeleitet.
            meta, quelle = read_arrow(roh.read_bytes())
        except Exception as error:  # pyogrio wirft je nach Ursache Verschiedenes
            raise IngestionError(f"{aus.stadt}: Grenzdatei nicht lesbar: {error}") from error
        crs = str(meta.get("crs") or "")
        if crs and crs != EXPECTED_CRS:
            raise IngestionError(f"{aus.stadt}: CRS {crs} statt {EXPECTED_CRS}")
        bronze = bronze_tabelle(quelle, aus)
        if bronze.num_rows != datei.erwartet:
            raise IngestionError(
                f"{aus.stadt}: {bronze.num_rows} Polygone gelesen, das Portal nennt {datei.erwartet}")
        parquet = work[BRONZE_LAYER] / PARQUET_FILE
        with parquet.open("wb") as stream:
            pq.write_table(bronze, stream, compression="snappy")

        fingerabdruck, felder = quellschema(meta)
        manifest = {
            "status": "complete",
            "contract_version": CONTRACT_VERSION,
            "code_version": code_stand(),
            "immutable": True,
            "source": aus.quelle,
            "dataset": DATASET,
            "ebene": aus.ebene,
            "city": aus.stadt,
            "ingest_date": started.date().isoformat(),
            "run_id": run_id,
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "row_count": bronze.num_rows,
            "crs": crs,
            "geometry_encoding": "WKB",
            "completeness": {
                "verified": True,
                "source_count": datei.erwartet,
                "features_written": bronze.num_rows,
                "downloaded_bytes": len(datei.payload),
            },
            "source_schema": {"fingerprint": fingerabdruck, "fields": felder},
            "query": {"method": "GET", "url": datei.url, "count_url": aus.zaehl_url,
                      "last_modified": datei.last_modified},
        }
        dateien = {RAW_LAYER: [file_entry(roh)], BRONZE_LAYER: [file_entry(parquet)]}
        for layer in LAYERS:
            dokument = dict(manifest, layer=layer, format=LAYER_FORMAT[layer], files=dateien[layer])
            if layer == BRONZE_LAYER:
                dokument["schema"] = {f.name: str(f.type) for f in SCHEMA}
                dokument["derived_from"] = f"{RAW_LAYER}/.../{run_id}"
            (work[layer] / "manifest.json").write_text(
                json.dumps(dokument, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        publish_directory(work[RAW_LAYER], final[RAW_LAYER])
        publish_directory(work[BRONZE_LAYER], final[BRONZE_LAYER])
        return RunPaths(final[RAW_LAYER], final[BRONZE_LAYER])
    except BaseException:
        for path in work.values():
            shutil.rmtree(path, ignore_errors=True)
        raise


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    parser.add_argument("--stadt", action="append",
                        choices=sorted({a.stadt for a in AUSLIEFERUNGEN}),
                        help="Nur diese Stadt; mehrfach moeglich. Ohne Angabe alle.")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    from storage.verwaltet import sperre
    sperre(for_root(args.data_root).local_root, worker_erlaubt=True)
    from storage.analysesitzung import schreibzugriff
    with schreibzugriff(for_root(args.data_root).local_root, invalidieren=True):
        started = datetime.now(timezone.utc)
        ablage = for_root(args.data_root)
        data_root = ablage.local_root
        auswahl = [a for a in AUSLIEFERUNGEN if not args.stadt or a.stadt in args.stadt]
        try:
            discard_stale_partials(data_root, started)
            with build_session() as session:
                # Erst alles laden, dann schreiben: Faellt ein Portal aus,
                # entsteht kein halber Satz.
                dateien = [(aus, lade(session, aus)) for aus in auswahl]
            for aus, datei in dateien:
                lauf = write_run(data_root, started, aus, datei)
                log.info("Lauf geschrieben: %s", lauf.bronze)
                ablage.publish_run(lauf.raw)
                ablage.publish_run(lauf.bronze)
            return 0
        except (IngestionError, OSError, ValueError, PublishError) as error:
            log.error("Ingestion fehlgeschlagen: %s", error)
            return 1
        except KeyboardInterrupt:
            log.error("Abgebrochen; kein fertiger Lauf veroeffentlicht")
            return 130


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    raise SystemExit(main())
