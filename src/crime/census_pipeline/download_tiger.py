"""Load Census TIGER/Line tract boundaries into immutable runs.

Jeder Aufruf schreibt einen Lauf nach data/raw/ und data/bronze/ unter einer
gemeinsamen run_id, genau wie die Chicago-Ingestion. Raw haelt das ZIP-Archiv
Byte fuer Byte; Bronze ist daraus abgeleitetes Parquet mit der Geometrie als
WKB.

Der Unterschied zur Ereignis-Ingestion liegt im Aenderungsverhalten der Quelle.
Eine TIGER-Vintage erscheint einmal im Jahr und ist danach eingefroren: Es gibt
kein ``updated_on``, also auch kein Wasserzeichen, keinen Lookback und keinen
Delta-Lauf. An dessen Stelle tritt eine einfachere Frage - ist diese Vintage fuer
diesen Bundesstaat schon geladen? Dann gibt es nichts zu tun, solange nicht
``--force`` einen neuen Lauf erzwingt.

Vollstaendigkeit wird auch hier nachgewiesen statt behauptet, nur mit anderen
Mitteln: Ein ZIP traegt je Mitgliedsdatei eine CRC32-Pruefsumme. Laesst sich das
Archiv oeffnen, stimmen alle CRCs und sind die vier Pflichtdateien eines
Shapefiles enthalten, dann ist die Auslieferung vollstaendig angekommen. Ein
Fingerabdruck ueber die Feldtypen der Quelle macht Schema-Drift zwischen den
Vintages sichtbar - ``GEOIDFQ`` etwa kam erst spaeter dazu.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import shutil
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from pyogrio.raw import read_arrow
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from census_pipeline import STATES


BASE_URL = "https://www2.census.gov/geo/tiger"
DATASET = "tiger_tract"
ARCHIVE_DIRECTORY = "TRACT"
USER_AGENT = "crime-data-gruppe3/0.1 (Hochschulprojekt CAS Data Engineering)"
DEFAULT_VINTAGE = 2024
# Vor 2020 gelten die Tract-Grenzen des Zensus 2010. Wer Faelle von 2001 bis
# 2019 verortet, braucht deshalb zusaetzlich eine aeltere Vintage - darum steht
# die Vintage im Pfad und ist nicht fest verdrahtet.
EARLIEST_VINTAGE = 2002

RAW_LAYER = "raw"
BRONZE_LAYER = "bronze"
LAYERS = (RAW_LAYER, BRONZE_LAYER)
LAYER_FORMAT = {
    RAW_LAYER: "application/zip (TIGER/Line Shapefile, unveraendert)",
    BRONZE_LAYER: "parquet (snappy, Geometrie als WKB)",
}
PARQUET_FILE = "part-0001.parquet"

TIMEOUT_SECONDS = 300
RETRY_TOTAL = 5
RETRY_BACKOFF = 1.0
RETRY_STATUS = (429, 500, 502, 503, 504)
STALE_PARTIAL_HOURS = 24

# Ein Shapefile besteht aus mehreren Dateien. Ohne diese vier ist es unlesbar,
# ihr Fehlen ist deshalb ein Abbruchgrund und keine Warnung.
REQUIRED_MEMBERS = (".shp", ".shx", ".dbf", ".prj")
# TIGER liefert NAD83. Die Koordinaten der Falldaten sind WGS84; der Unterschied
# liegt unter einem Meter, wird beim Join aber ausdruecklich umgerechnet statt
# stillschweigend gleichgesetzt.
EXPECTED_CRS = "EPSG:4269"

# Das gepinnte Spaltenset. Es ist die Schnittmenge ueber die Vintages: Spalten,
# die eine Vintage zusaetzlich mitbringt, landen unveraendert in EXTRA_COLUMN,
# statt das Schema von Lauf zu Lauf wandern zu lassen.
FIELD_TYPES: dict[str, pa.DataType] = {
    "STATEFP": pa.string(),
    "COUNTYFP": pa.string(),
    "TRACTCE": pa.string(),
    "GEOID": pa.string(),
    "NAME": pa.string(),
    "NAMELSAD": pa.string(),
    "MTFCC": pa.string(),
    "FUNCSTAT": pa.string(),
    "ALAND": pa.int64(),
    "AWATER": pa.int64(),
    "INTPTLAT": pa.string(),
    "INTPTLON": pa.string(),
}
GEOMETRY_COLUMN = "geometry"
SOURCE_GEOMETRY_COLUMN = "wkb_geometry"
EXTRA_COLUMN = "_extra"

log = logging.getLogger("census_tiger_ingestion")


def build_schema() -> pa.Schema:
    """Pin one Parquet schema for every vintage and every state."""
    fields = [pa.field(name, kind) for name, kind in FIELD_TYPES.items()]
    fields.append(pa.field(GEOMETRY_COLUMN, pa.binary()))
    fields.append(pa.field(EXTRA_COLUMN, pa.string()))
    return pa.schema(fields)


SCHEMA = build_schema()
COLUMNS = tuple(SCHEMA.names)


class IngestionError(RuntimeError):
    """A run could not be downloaded or stored safely."""


class Archive(NamedTuple):
    """Das geladene Archiv samt der Nachweise seiner Unversehrtheit."""

    payload: bytes
    url: str
    members: list[str]
    content_length: int | None
    last_modified: str | None


class RunPaths(NamedTuple):
    """Wo ein veroeffentlichter Lauf gelandet ist."""

    raw: Path
    bronze: Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", type=int, default=DEFAULT_VINTAGE)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--state",
        action="append",
        choices=sorted(STATES),
        help="FIPS-Nummer; mehrfach moeglich. Ohne Angabe alle bekannten.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Neuen Lauf schreiben, auch wenn die Vintage schon geladen ist",
    )
    args = parser.parse_args()
    if args.vintage < EARLIEST_VINTAGE:
        parser.error(f"--vintage must be {EARLIEST_VINTAGE} or later")
    args.state = args.state or sorted(STATES)
    return args


def tiger_url(vintage: int, state: str) -> str:
    """Die Adresse einer Tract-Auslieferung; sie folgt einem festen Muster."""
    name = archive_name(vintage, state)
    return f"{BASE_URL}/TIGER{vintage}/{ARCHIVE_DIRECTORY}/{name}"


def archive_name(vintage: int, state: str) -> str:
    return f"tl_{vintage}_{state}_tract.zip"


def shapefile_member(vintage: int, state: str) -> str:
    return f"tl_{vintage}_{state}_tract.shp"


def run_parent(data_root: Path, layer: str, vintage: int, state: str) -> Path:
    """Partitioniert wird nach Vintage und Bundesstaat, nicht nach Abrufdatum.

    Eine Vintage ist eingefroren: Wann sie geladen wurde, ist Metadatum im
    Manifest, aber kein Ordnungskriterium. Der Abrufzeitpunkt steckt weiterhin in
    der run_id.
    """
    return (
        data_root
        / layer
        / f"dataset={DATASET}"
        / f"vintage={vintage}"
        / f"state={state}"
    )


def discard_stale_partials(data_root: Path, now: datetime) -> list[Path]:
    """Drop work directories a crashed run left behind."""
    cutoff = (now - timedelta(hours=STALE_PARTIAL_HOURS)).timestamp()
    removed = []
    for layer in LAYERS:
        pattern = f"{layer}/dataset={DATASET}/vintage=*/state=*/.*.part"
        for path in sorted(data_root.glob(pattern)):
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                log.warning("Discarded stale partial run: %s", path)
                removed.append(path)
    return removed


def completed_runs(data_root: Path, vintage: int, state: str) -> list[Path]:
    """Bereits veroeffentlichte Laeufe dieser Vintage.

    Das ist die Entsprechung zum Wasserzeichen der Ereignis-Ingestion: Sie
    beantwortet, ob es ueberhaupt etwas zu tun gibt. Gelesen wird nur Bronze,
    weil Bronze zuletzt veroeffentlicht wird - ein Raw-Lauf ohne Bronze-Zwilling
    kostet eine Wiederholung, nie eine Luecke.
    """
    parent = run_parent(data_root, BRONZE_LAYER, vintage, state)
    runs = []
    for path in sorted(parent.glob("run_*/manifest.json")):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise IngestionError(f"Invalid manifest: {path}") from error
        if manifest.get("status") == "complete":
            runs.append(path.parent)
    return runs


def build_session() -> requests.Session:
    """Create a session that retries throttling and transient server errors."""
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=RETRY_STATUS,
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_archive(session: requests.Session, vintage: int, state: str) -> Archive:
    """Laedt ein Archiv und weist nach, dass es unversehrt angekommen ist."""
    url = tiger_url(vintage, state)
    try:
        response = session.get(url, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        payload = response.content
    except requests.RequestException as error:
        raise IngestionError(f"Download failed: {error}") from error

    declared = response.headers.get("Content-Length")
    content_length = int(declared) if declared and declared.isdigit() else None
    if content_length is not None and content_length != len(payload):
        raise IngestionError(
            f"Unvollstaendige Auslieferung: {len(payload):,} von "
            f"{content_length:,} Byte"
        )

    members = verify_archive(payload, vintage, state)
    log.info(
        "%s geladen: %s Byte, %s Dateien im Archiv",
        archive_name(vintage, state),
        f"{len(payload):,}",
        len(members),
    )
    return Archive(
        payload=payload,
        url=url,
        members=members,
        content_length=content_length,
        last_modified=response.headers.get("Last-Modified"),
    )


def verify_archive(payload: bytes, vintage: int, state: str) -> list[str]:
    """Prueft das Archiv gegen seine eigenen Pruefsummen.

    Ein ZIP fuehrt je Mitgliedsdatei eine CRC32 mit. ``testzip`` liest jede
    Datei und meldet die erste, deren Pruefsumme nicht stimmt. Zusammen mit den
    Pflichtdateien des Shapefiles ist das der Vollstaendigkeitsnachweis dieser
    Quelle - sie liefert keine Zeilenzahl, gegen die sich zaehlen liesse.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            broken = archive.testzip()
            if broken is not None:
                raise IngestionError(f"Falsche Pruefsumme im Archiv: {broken}")
            members = sorted(info.filename for info in archive.infolist())
    except zipfile.BadZipFile as error:
        raise IngestionError(f"Kein lesbares ZIP-Archiv: {error}") from error

    stem = shapefile_member(vintage, state).removesuffix(".shp")
    fehlend = [
        suffix for suffix in REQUIRED_MEMBERS if f"{stem}{suffix}" not in members
    ]
    if fehlend:
        raise IngestionError(f"Shapefile unvollstaendig, es fehlen: {fehlend}")
    return members


def source_schema(meta: dict[str, Any]) -> tuple[str, dict[str, str]]:
    """Fingerabdruck ueber die Feldtypen der Quelle.

    Aendert eine spaetere Vintage den Typ eines Feldes, aendert sich der Hash -
    auch dann, wenn die Ingestion weiterlaeuft. EXTRA_COLUMN faengt neue Felder
    auf, eine Typaenderung an einem bestehenden Feld wuerde sie nicht bemerken.
    """
    fields = {
        str(name): str(kind)
        for name, kind in zip(meta.get("fields", []), meta.get("ogr_types", []))
    }
    digest = hashlib.sha256(json_text(fields).encode("utf-8")).hexdigest()
    return digest, fields


def json_text(value: Any) -> str:
    """Serialise a value compactly and deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_features(archive_path: Path, vintage: int, state: str) -> tuple[pa.Table, dict]:
    """Liest das Shapefile direkt aus dem Archiv, ohne es auszupacken.

    GDAL spricht ZIP-Archive ueber das Praefix ``/vsizip/`` an. Die Geometrie
    kommt dabei schon als WKB, ganz ohne geopandas oder shapely.
    """
    member = shapefile_member(vintage, state)
    source = f"/vsizip/{archive_path}/{member}"
    try:
        meta, table = read_arrow(source)
    except Exception as error:  # pyogrio wirft je nach Ursache Unterschiedliches
        raise IngestionError(f"Shapefile nicht lesbar: {error}") from error

    crs = str(meta.get("crs") or "")
    if crs and crs != EXPECTED_CRS:
        log.warning("Unerwartete CRS: %s statt %s", crs, EXPECTED_CRS)
    return table, meta


def bronze_table(source: pa.Table) -> pa.Table:
    """Bildet die Quelltabelle auf das gepinnte Schema ab, ohne etwas zu verlieren.

    Eine Spalte, die nicht ins Schema passt - unbekannter Name oder anderer Typ -
    wandert vollstaendig nach EXTRA_COLUMN. Anders als bei JSON ist der Typ
    innerhalb einer Shapefile-Spalte einheitlich, deshalb wird spaltenweise
    entschieden und nicht je Wert.
    """
    behalten: dict[str, pa.ChunkedArray] = {}
    extra: dict[str, list[Any]] = {}

    for name in source.schema.names:
        if name == SOURCE_GEOMETRY_COLUMN:
            continue
        passt = name in FIELD_TYPES and source.schema.field(name).type.equals(
            FIELD_TYPES[name]
        )
        if passt:
            behalten[name] = source.column(name)
        else:
            extra[name] = source.column(name).to_pylist()

    rows = source.num_rows
    arrays = []
    for name, kind in FIELD_TYPES.items():
        if name in behalten:
            arrays.append(behalten[name].combine_chunks())
        else:
            arrays.append(pa.nulls(rows, type=kind))

    if SOURCE_GEOMETRY_COLUMN in source.schema.names:
        arrays.append(source.column(SOURCE_GEOMETRY_COLUMN).combine_chunks())
    else:
        arrays.append(pa.nulls(rows, type=pa.binary()))

    arrays.append(pa.array(extra_column(extra, rows), type=pa.string()))
    return pa.Table.from_arrays(arrays, schema=SCHEMA)


def extra_column(extra: dict[str, list[Any]], rows: int) -> list[str | None]:
    """Je Zeile ein JSON-Objekt mit allem, was nicht ins Schema passte."""
    if not extra:
        return [None] * rows
    values: list[str | None] = []
    for index in range(rows):
        row = {
            name: column[index]
            for name, column in extra.items()
            if column[index] is not None
        }
        values.append(json_text(row) if row else None)
    return values


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_entry(path: Path) -> dict[str, Any]:
    return {
        "path": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": file_hash(path),
    }


def write_landing(work_dir: Path, archive: Archive, name: str) -> tuple[Path, list[dict[str, Any]]]:
    """Legt das Archiv unveraendert ab - Byte fuer Byte, wie ausgeliefert."""
    path = work_dir / name
    path.write_bytes(archive.payload)
    return path, [file_entry(path)]


def write_bronze(
    work_dir: Path, archive_path: Path, vintage: int, state: str
) -> tuple[pa.Table, dict[str, Any], list[dict[str, Any]]]:
    """Leitet die Parquet-Datei aus der gelandeten Raw-Datei ab.

    Gelesen wird bewusst das Archiv, das gerade in Raw geschrieben wurde, und
    keine zweite Kopie im Speicher: Bronze ist damit nachweislich aus genau dem
    Beweisstueck abgeleitet, dessen SHA-256 im Manifest steht.
    """
    table, meta = read_features(archive_path, vintage, state)
    path = work_dir / PARQUET_FILE
    bronze = bronze_table(table)
    pq.write_table(bronze, path, compression="snappy")
    return bronze, meta, [file_entry(path)]


def write_run(
    data_root: Path,
    started: datetime,
    archive: Archive,
    *,
    vintage: int,
    state: str,
) -> RunPaths:
    """Schreibt beide Schichten und veroeffentlicht sie atomar, Raw zuerst."""
    ingest_date = started.date().isoformat()
    run_id = started.strftime("run_%Y%m%dT%H%M%S%fZ")
    parents = {
        layer: run_parent(data_root, layer, vintage, state) for layer in LAYERS
    }
    work = {layer: parent / f".{run_id}.part" for layer, parent in parents.items()}
    final = {layer: parent / run_id for layer, parent in parents.items()}
    for path in work.values():
        path.mkdir(parents=True)

    try:
        name = archive_name(vintage, state)
        staged, raw_files = write_landing(work[RAW_LAYER], archive, name)
        files = {RAW_LAYER: raw_files}
        bronze, meta, files[BRONZE_LAYER] = write_bronze(
            work[BRONZE_LAYER], staged, vintage, state
        )

        fingerprint, fields = source_schema(meta)
        manifest = {
            "status": "complete",
            "immutable": True,
            "source": "census_tiger",
            "dataset": DATASET,
            "vintage": vintage,
            "state_fips": state,
            "state_name": STATES.get(state),
            "ingest_date": ingest_date,
            "run_id": run_id,
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "row_count": bronze.num_rows,
            "crs": str(meta.get("crs") or ""),
            "geometry_encoding": "WKB",
            "completeness": {
                # Die Quelle nennt keine Zeilenzahl. Nachgewiesen wird deshalb
                # die Unversehrtheit der Auslieferung: CRC je Mitgliedsdatei
                # plus die Pflichtdateien des Shapefiles.
                "verified": True,
                "archive_crc_ok": True,
                "archive_members": archive.members,
                "required_members": list(REQUIRED_MEMBERS),
                "content_length": archive.content_length,
                "downloaded_bytes": len(archive.payload),
                "features_written": bronze.num_rows,
            },
            "source_schema": {"fingerprint": fingerprint, "fields": fields},
            "query": {
                "method": "GET",
                "url": archive.url,
                "last_modified": archive.last_modified,
            },
        }
        for layer in LAYERS:
            document = dict(manifest, layer=layer, format=LAYER_FORMAT[layer])
            if layer == BRONZE_LAYER:
                document["schema"] = {
                    field.name: str(field.type) for field in SCHEMA
                }
                document["derived_from"] = f"{RAW_LAYER}/.../{run_id}"
            document["files"] = files[layer]
            (work[layer] / "manifest.json").write_text(
                json.dumps(document, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        # Raw ist das Beweisstueck und wird zuerst veroeffentlicht.
        work[RAW_LAYER].rename(final[RAW_LAYER])
        work[BRONZE_LAYER].rename(final[BRONZE_LAYER])
        return RunPaths(final[RAW_LAYER], final[BRONZE_LAYER])
    except BaseException:
        for path in work.values():
            shutil.rmtree(path, ignore_errors=True)
        raise


def ingest_state(
    session: requests.Session,
    data_root: Path,
    started: datetime,
    vintage: int,
    state: str,
    force: bool,
) -> RunPaths | None:
    """Laedt eine Vintage fuer einen Bundesstaat; None, wenn nichts zu tun war."""
    vorhanden = completed_runs(data_root, vintage, state)
    if vorhanden and not force:
        log.info(
            "TIGER %s %s ist bereits geladen (%s); --force erzwingt einen neuen Lauf",
            vintage,
            STATES.get(state, state),
            vorhanden[-1].name,
        )
        return None

    archive = fetch_archive(session, vintage, state)
    return write_run(data_root, started, archive, vintage=vintage, state=state)


def main() -> int:
    args = arguments()
    started = datetime.now(timezone.utc)

    try:
        discard_stale_partials(args.data_root, started)
        geschrieben = 0
        with build_session() as session:
            for state in args.state:
                log.info(
                    "Starting TIGER %s tracts for %s (%s)",
                    args.vintage,
                    STATES.get(state, state),
                    state,
                )
                run = ingest_state(
                    session,
                    args.data_root,
                    started,
                    args.vintage,
                    state,
                    args.force,
                )
                if run is not None:
                    geschrieben += 1
                    log.info("Immutable run completed: %s", run.raw)
                    log.info("                        %s", run.bronze)
        log.info("Fertig: %s Lauf/Laeufe geschrieben", geschrieben)
        return 0
    except (IngestionError, OSError, ValueError) as error:
        log.error("Ingestion failed: %s", error)
        return 1
    except KeyboardInterrupt:
        log.error("Ingestion cancelled; no completed run was published")
        return 130


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    raise SystemExit(main())
