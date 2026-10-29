"""Load NOAA GHCN-Daily station series into immutable runs.

Jeder Aufruf schreibt einen Lauf nach data/raw/ und data/bronze/ unter einer
gemeinsamen run_id, genau wie die Chicago- und die TIGER-Ingestion. Raw haelt
die CSV Byte fuer Byte; Bronze ist daraus abgeleitetes Parquet mit gepinntem
Schema.

Das Aenderungsverhalten liegt zwischen den beiden bekannten Faellen. Eine
TIGER-Vintage ist eingefroren, die Falldaten wachsen um einzelne Ereignisse -
eine Stationsreihe waechst taeglich um genau eine Zeile am Ende, wird aber
immer als ganze Datei ausgeliefert. Es gibt also kein Delta abzurufen und kein
Wasserzeichen mitzufuehren: Jeder Lauf ist ein vollstaendiger Schnappschuss.

Weil jeder Lauf vollstaendig ist, erzeugt ein selteneres Laden anders als bei
einer Ereignisquelle **keine Luecke** - der naechste Lauf bringt die
Zwischenzeit mit. Ein taeglicher Vollschnappschuss fuer eine Reihe, die
taeglich eine Zeile anhaengt, kostet dagegen das Siebenfache an Platz. Zwei
Bremsen greifen deshalb vor dem Download, in dieser Reihenfolge:

1. **Mindestabstand.** Liegt der letzte Lauf dieser Station weniger als
   ``DEFAULT_MIN_INTERVAL_DAYS`` Tage zurueck, wird gar nicht gefragt.
   ``--force`` ueberspringt diese Bremse, ``--min-interval-days 0`` hebt sie auf.
2. **Bedingter Abruf.** Sonst wird mit ``If-None-Match`` und
   ``If-Modified-Since`` aus dem letzten Manifest gefragt. Hat NOAA die Datei
   seit dem letzten Lauf nicht neu veroeffentlicht, antwortet der Dienst mit
   ``304`` und null Bytes statt mit elf Megabyte. Diese Bremse greift auch bei
   ``--force`` - ein erzwungener Lauf, der nichts Neues findet, soll nichts
   kosten.

Beide Regeln stehen so in Abschnitt 3.1 der Projektabsprache, Entscheid
"B plus D".

Vollstaendigkeit wird nachgewiesen statt behauptet, mit den Mitteln, die diese
Quelle hergibt: ``Content-Length`` gegen die empfangenen Bytes, die Zeilenzahl
der CSV gegen die geschriebenen Parquet-Zeilen, und die Zusicherung, dass jede
Zeile dieselbe Station nennt wie die angefragte Datei. Ein Fingerabdruck ueber
die Kopfzeile macht Schema-Drift sichtbar - die Quelle fuehrt weit mehr
Groessen als die vier, die das Projekt auswertet, und kann jederzeit weitere
ergaenzen.

Werte bleiben Text, so wie die Quelle sie schreibt, einschliesslich der
Leerzeichen, mit denen sie rechtsbuendig aufgefuellt sind (``"  214"``). Das
Parsen und das Umrechnen der Einheiten gehoert nach Silver; GHCN-Daily fuehrt
Temperaturen in Zehntelgrad Celsius und Niederschlag in Zehntelmillimetern.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import logging
import shutil
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from manifeste import Lauf, code_stand
from storage import PublishError, for_root
from typing import Any, NamedTuple

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from weather_pipeline import DEFAULT_STATIONS, STATIONS


BASE_URL = (
    "https://www.ncei.noaa.gov/data/"
    "global-historical-climatology-network-daily/access"
)
DATASET = "noaa_ghcnd"
USER_AGENT = "crime-data-gruppe3/0.1 (Hochschulprojekt CAS Data Engineering)"

RAW_LAYER = "raw"
BRONZE_LAYER = "bronze"
LAYERS = (RAW_LAYER, BRONZE_LAYER)
LAYER_FORMAT = {
    RAW_LAYER: "text/csv (GHCN-Daily je Station, unveraendert)",
    BRONZE_LAYER: "parquet (snappy, Werte als Text wie in der Quelle)",
}
PARQUET_FILE = "part-0001.parquet"

# Wochenrhythmus statt taeglich (Projektabsprache 3.1, Entscheid "B plus D").
# 0 laedt bei jedem Aufruf, begrenzt nur durch den bedingten Abruf.
# Der Ladevertrag; siehe "Vertragsversionen" in AENDERUNGEN.md.
CONTRACT_VERSION = 1

DEFAULT_MIN_INTERVAL_DAYS = 7

TIMEOUT_SECONDS = 300
RETRY_TOTAL = 5
RETRY_BACKOFF = 1.0
RETRY_STATUS = (429, 500, 502, 503, 504)
STALE_PARTIAL_HOURS = 24

# Die Identitaetsspalten. Sie stehen in jeder Zeile und beantworten, wo und
# wann gemessen wurde; ohne sie ist eine Zeile wertlos.
IDENTITY_COLUMNS = (
    "STATION",
    "DATE",
    "LATITUDE",
    "LONGITUDE",
    "ELEVATION",
    "NAME",
)

# Die vier Groessen, die die Leitfrage braucht, je mit ihrer Flag-Spalte.
# Die Quelle liefert ueber hundert weitere Spalten - SNWD, TAVG, AWND, die
# Wettertyp-Flags WT01 bis WV20. Die landen unveraendert in EXTRA_COLUMN,
# statt verworfen zu werden: Wer spaeter Schneehoehe oder Mitteltemperatur
# auswerten will, findet sie dort und braucht keinen neuen Ladelauf. Eine
# Groesse von dort ins gepinnte Schema zu heben, kostet einen Eintrag hier.
MEASUREMENT_COLUMNS = ("PRCP", "SNOW", "TMAX", "TMIN")
ATTRIBUTE_SUFFIX = "_ATTRIBUTES"

# Alles ist Text. GHCN-Daily liefert CSV, dort gibt es keinen anderen Typ, und
# das Parsen gehoert nach Silver.
FIELD_TYPES: dict[str, pa.DataType] = {name: pa.string() for name in IDENTITY_COLUMNS}
for _name in MEASUREMENT_COLUMNS:
    FIELD_TYPES[_name] = pa.string()
    FIELD_TYPES[f"{_name}{ATTRIBUTE_SUFFIX}"] = pa.string()

EXTRA_COLUMN = "_extra"
STATION_COLUMN = "STATION"
DATE_COLUMN = "DATE"

log = logging.getLogger("weather_noaa_ingestion")


def build_schema() -> pa.Schema:
    """Pin one Parquet schema for every station and every run."""
    fields = [pa.field(name, kind) for name, kind in FIELD_TYPES.items()]
    fields.append(pa.field(EXTRA_COLUMN, pa.string()))
    return pa.schema(fields)


SCHEMA = build_schema()
COLUMNS = tuple(SCHEMA.names)


class IngestionError(RuntimeError):
    """A run could not be downloaded or stored safely."""


class Delivery(NamedTuple):
    """Die geladene CSV samt der Nachweise ihrer Unversehrtheit."""

    payload: bytes
    url: str
    content_length: int | None
    last_modified: str | None
    etag: str | None


class Series(NamedTuple):
    """Die gelesene Messreihe und was sie ueber sich selbst aussagt."""

    header: tuple[str, ...]
    rows: list[dict[str, str]]
    first_date: str | None
    last_date: str | None


class RunPaths(NamedTuple):
    """Wo ein veroeffentlichter Lauf gelandet ist."""

    raw: Path
    bronze: Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    parser.add_argument(
        "--station",
        action="append",
        choices=sorted(STATIONS),
        help=(
            "Stations-ID; mehrfach moeglich. Ohne Angabe die Flughafenstation "
            "je Stadt."
        ),
    )
    parser.add_argument(
        "--min-interval-days",
        type=int,
        default=DEFAULT_MIN_INTERVAL_DAYS,
        help=(
            "Mindestabstand zum letzten Lauf in Tagen "
            f"(Standard {DEFAULT_MIN_INTERVAL_DAYS}, 0 hebt die Bremse auf)"
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Mindestabstand ignorieren. Der bedingte Abruf greift weiterhin: "
            "hat die Quelle nichts Neues, wird kein Lauf geschrieben."
        ),
    )
    args = parser.parse_args()
    args.station = args.station or list(DEFAULT_STATIONS)
    if args.min_interval_days < 0:
        parser.error("--min-interval-days darf nicht negativ sein")
    return args


def station_url(station: str) -> str:
    """Die Adresse einer Stationsreihe; sie folgt einem festen Muster."""
    return f"{BASE_URL}/{station}.csv"


def csv_name(station: str) -> str:
    return f"{station}.csv"


def run_parent(data_root: Path, layer: str, station: str) -> Path:
    """Partitioniert wird nach Station, nicht nach Bundesstaat.

    Wetter ist kein Tract-Merkmal: Eine Station gilt fuer die ganze Stadt und
    wird ueber Datum und Stadt verbunden. Der Abrufzeitpunkt steckt in der
    run_id, das Abrufdatum zusaetzlich im Manifest.
    """
    return data_root / layer / f"dataset={DATASET}" / f"station={station}"


def discard_stale_partials(data_root: Path, now: datetime) -> list[Path]:
    """Drop work directories a crashed run left behind."""
    cutoff = (now - timedelta(hours=STALE_PARTIAL_HOURS)).timestamp()
    removed = []
    for layer in LAYERS:
        pattern = f"{layer}/dataset={DATASET}/station=*/.*.part"
        # Lokal mit Absicht: ein `.part` wird nie publiziert.
        for path in sorted(data_root.glob(pattern)):
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                log.warning("Discarded stale partial run: %s", path)
                removed.append(path)
    return removed


def completed_runs(
    data_root: Path, station: str, ingest_date: str | None = None
) -> list[Path]:
    """Bereits veroeffentlichte Laeufe dieser Station.

    Ohne ``ingest_date`` alle, sonst nur die dieses Abruftags. Die Liste ist
    nach run_id sortiert, und weil die run_id ein UTC-Zeitstempel ist, ist der
    letzte Eintrag der jüngste Lauf.

    Das ist die Entsprechung zum Wasserzeichen der Ereignis-Ingestion: Sie
    beantwortet, ob es ueberhaupt etwas zu tun gibt.

    Gelesen wird nur Bronze, weil Bronze zuletzt veroeffentlicht wird - ein
    Raw-Lauf ohne Bronze-Zwilling kostet eine Wiederholung, nie eine Luecke.
    """
    return [
        lauf.verzeichnis
        for lauf in fertige_laeufe_der_station(data_root, station)
        if ingest_date is None or lauf.manifest.get("ingest_date") == ingest_date
    ]


def fertige_laeufe_der_station(data_root: Path, station: str) -> list[Lauf]:
    """Wie ``completed_runs``, aber mit Manifest - lokal oder auf SeaweedFS."""
    ablage = for_root(data_root)
    prefix = ablage.relativ(run_parent(data_root, BRONZE_LAYER, station))
    return ablage.laeufe(prefix, "run_*/manifest.json", streng=True, fehler=IngestionError)


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


def manifest_des_laufs(lauf: Lauf | Path) -> dict[str, Any]:
    """Das Manifest eines Laufs - schon geladen (``Lauf``) oder vom Pfad."""
    if isinstance(lauf, Lauf):
        return lauf.manifest
    pfad = lauf / "manifest.json"
    try:
        return json.loads(pfad.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise IngestionError(f"Invalid manifest: {pfad}") from error


def conditional_headers(run_dir: Lauf | Path | None) -> dict[str, str]:
    """Baut ``If-None-Match``/``If-Modified-Since`` aus dem letzten Manifest.

    Ohne vorherigen Lauf bleibt der Abruf unbedingt. Ein Manifest ohne die
    beiden Angaben - etwa aus einem Lauf vor dieser Aenderung - liefert einen
    leeren Satz und damit denselben Vollabruf wie bisher.
    """
    if run_dir is None:
        return {}
    manifest = manifest_des_laufs(run_dir)

    abfrage = manifest.get("query") or {}
    kopf = {}
    # ETag ist der genauere Validator: Er haengt am Inhalt, nicht an einer
    # Uhrzeit mit Sekundenauflösung.
    if abfrage.get("etag"):
        kopf["If-None-Match"] = abfrage["etag"]
    if abfrage.get("last_modified"):
        kopf["If-Modified-Since"] = abfrage["last_modified"]
    return kopf


def fetch_delivery(
    session: requests.Session,
    station: str,
    *,
    validators: dict[str, str] | None = None,
) -> Delivery | None:
    """Laedt eine Stationsreihe und weist nach, dass sie ganz angekommen ist.

    ``None`` heisst: Der Dienst hat mit ``304 Not Modified`` geantwortet, die
    Datei ist seit dem letzten Lauf unveraendert, es gibt nichts zu schreiben.
    """
    url = station_url(station)
    try:
        response = session.get(
            url, timeout=TIMEOUT_SECONDS, headers=validators or {}
        )
        if response.status_code == 304:
            log.info(
                "%s unveraendert seit dem letzten Lauf (HTTP 304, 0 Byte)",
                csv_name(station),
            )
            return None
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
    if not payload:
        raise IngestionError(f"Leere Auslieferung fuer {station}")

    log.info(
        "%s geladen: %s Byte", csv_name(station), f"{len(payload):,}"
    )
    return Delivery(
        payload=payload,
        url=url,
        content_length=content_length,
        last_modified=response.headers.get("Last-Modified"),
        etag=response.headers.get("ETag"),
    )


def read_series(payload: bytes, station: str) -> Series:
    """Liest die CSV und prueft, dass sie die angefragte Station enthaelt.

    Eine Datei, die eine andere Station nennt, waere eine stillschweigend
    falsch einsortierte Partition - der Fehler faellt sonst erst in Silver auf,
    wenn niemand mehr weiss, woher die Zeilen kamen.
    """
    text = payload.decode("utf-8-sig", errors="strict")
    reader = csv.DictReader(io.StringIO(text))
    header = tuple(reader.fieldnames or ())
    if not header:
        raise IngestionError(f"CSV ohne Kopfzeile fuer {station}")
    for required in (STATION_COLUMN, DATE_COLUMN):
        if required not in header:
            raise IngestionError(
                f"Pflichtspalte {required} fehlt in der Kopfzeile von {station}"
            )

    rows = [row for row in reader]
    if not rows:
        raise IngestionError(f"CSV ohne Datenzeilen fuer {station}")

    fremd = sorted({row[STATION_COLUMN] for row in rows} - {station})
    if fremd:
        raise IngestionError(
            f"CSV von {station} enthaelt fremde Stationen: {fremd}"
        )

    dates = sorted(value for row in rows if (value := row[DATE_COLUMN]))
    return Series(
        header=header,
        rows=rows,
        first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
    )


def source_schema(header: tuple[str, ...]) -> tuple[str, list[str]]:
    """Fingerabdruck ueber die Kopfzeile der Quelle.

    GHCN-Daily fuehrt je Station nur die Groessen, die dort gemessen werden,
    und kann weitere ergaenzen. Aendert sich die Kopfzeile, aendert sich der
    Hash - auch dann, wenn die Ingestion weiterlaeuft, weil EXTRA_COLUMN neue
    Spalten auffaengt.
    """
    fields = list(header)
    digest = hashlib.sha256(json_text(fields).encode("utf-8")).hexdigest()
    return digest, fields


def json_text(value: Any) -> str:
    """Serialise a value compactly and deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def bronze_table(series: Series) -> pa.Table:
    """Bildet die Messreihe auf das gepinnte Schema ab, ohne etwas zu verlieren.

    Jede Spalte, die nicht im Schema steht, wandert je Zeile nach
    EXTRA_COLUMN. Leere Felder werden zu NULL - in einer CSV ist ein leeres
    Feld die Abwesenheit einer Messung, nicht der Text der Laenge null.
    """
    rows = series.rows
    weitere = [name for name in series.header if name not in FIELD_TYPES]

    arrays = []
    for name, kind in FIELD_TYPES.items():
        werte = [leer_zu_none(row.get(name)) for row in rows]
        arrays.append(pa.array(werte, type=kind))
    arrays.append(pa.array(extra_column(rows, weitere), type=pa.string()))
    return pa.Table.from_arrays(arrays, schema=SCHEMA)


def leer_zu_none(value: str | None) -> str | None:
    """Ein leeres CSV-Feld ist eine fehlende Messung, kein leerer Text."""
    if value is None or value == "":
        return None
    return value


def extra_column(
    rows: list[dict[str, str]], weitere: list[str]
) -> list[str | None]:
    """Je Zeile ein JSON-Objekt mit allem, was nicht ins Schema passte."""
    if not weitere:
        return [None] * len(rows)
    values: list[str | None] = []
    for row in rows:
        rest = {
            name: row[name]
            for name in weitere
            if leer_zu_none(row.get(name)) is not None
        }
        values.append(json_text(rest) if rest else None)
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


def write_landing(
    work_dir: Path, delivery: Delivery, name: str
) -> tuple[Path, list[dict[str, Any]]]:
    """Legt die CSV unveraendert ab - Byte fuer Byte, wie ausgeliefert."""
    path = work_dir / name
    path.write_bytes(delivery.payload)
    return path, [file_entry(path)]


def write_bronze(
    work_dir: Path, csv_path: Path, station: str
) -> tuple[pa.Table, Series, list[dict[str, Any]]]:
    """Leitet die Parquet-Datei aus der gelandeten Raw-Datei ab.

    Gelesen wird bewusst die Datei, die gerade in Raw geschrieben wurde, und
    keine zweite Kopie im Speicher: Bronze ist damit nachweislich aus genau dem
    Beweisstueck abgeleitet, dessen SHA-256 im Manifest steht.
    """
    series = read_series(csv_path.read_bytes(), station)
    path = work_dir / PARQUET_FILE
    bronze = bronze_table(series)
    pq.write_table(bronze, path, compression="snappy")
    return bronze, series, [file_entry(path)]


def write_run(
    data_root: Path,
    started: datetime,
    delivery: Delivery,
    *,
    station: str,
) -> RunPaths:
    """Schreibt beide Schichten und veroeffentlicht sie atomar, Raw zuerst."""
    ingest_date = started.date().isoformat()
    run_id = started.strftime("run_%Y%m%dT%H%M%S%fZ")
    parents = {layer: run_parent(data_root, layer, station) for layer in LAYERS}
    work = {layer: parent / f".{run_id}.part" for layer, parent in parents.items()}
    final = {layer: parent / run_id for layer, parent in parents.items()}
    for path in work.values():
        path.mkdir(parents=True)

    try:
        name = csv_name(station)
        staged, raw_files = write_landing(work[RAW_LAYER], delivery, name)
        files = {RAW_LAYER: raw_files}
        bronze, series, files[BRONZE_LAYER] = write_bronze(
            work[BRONZE_LAYER], staged, station
        )

        fingerprint, fields = source_schema(series.header)
        info = STATIONS.get(station, {})
        manifest = {
            "status": "complete",
            "contract_version": CONTRACT_VERSION,
            "code_version": code_stand(),
            "immutable": True,
            "source": "noaa_ghcnd",
            "dataset": DATASET,
            "station_id": station,
            "station_name": info.get("name"),
            "city": info.get("city"),
            "ingest_date": ingest_date,
            "run_id": run_id,
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": datetime.now(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "row_count": bronze.num_rows,
            # Der Schnappschuss ist vollstaendig bis hierher. Silver braucht
            # das, um mehrere Laeufe zu ordnen, ohne die Parquet-Dateien zu
            # lesen - es ist das Gegenstueck zum Wasserzeichen bei Chicago.
            "first_observation_date": series.first_date,
            "last_observation_date": series.last_date,
            # Wetter wird nicht raeumlich verbunden. Das steht im Manifest,
            # damit Silver es nicht aus dem Pfad erraten muss.
            "join_keys": ["city", DATE_COLUMN],
            "value_encoding": (
                "Text wie in der Quelle, rechtsbuendig aufgefuellt. "
                "GHCN-Daily fuehrt Temperaturen in Zehntelgrad Celsius und "
                "Niederschlag in Zehntelmillimetern; geparst wird in Silver."
            ),
            "completeness": {
                # Die Quelle nennt keine Zeilenzahl. Nachgewiesen wird
                # deshalb, dass die Auslieferung ganz angekommen ist und dass
                # jede gelesene Zeile auch geschrieben wurde.
                "verified": True,
                "content_length": delivery.content_length,
                "downloaded_bytes": len(delivery.payload),
                "csv_rows_read": len(series.rows),
                "rows_written": bronze.num_rows,
                "station_column_consistent": True,
            },
            "source_schema": {
                "fingerprint": fingerprint,
                "column_count": len(fields),
                "fields": fields,
            },
            # last_modified und etag sind nicht nur Herkunftsangaben: Der
            # naechste Lauf fragt mit ihnen bedingt an und laedt nichts, wenn
            # die Quelle unveraendert ist.
            "query": {
                "method": "GET",
                "url": delivery.url,
                "last_modified": delivery.last_modified,
                "etag": delivery.etag,
            },
        }
        if len(series.rows) != bronze.num_rows:
            raise IngestionError(
                f"Zeilenzahl weicht ab: {len(series.rows)} gelesen, "
                f"{bronze.num_rows} geschrieben"
            )

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


def newest_run(data_root: Path, station: str) -> Lauf | None:
    """Der jüngste vollstaendige Lauf dieser Station, oder None.

    Als ``Lauf`` mit Manifest, nicht als Pfad: Liegt er nur auf SeaweedFS,
    gibt es lokal nichts zu lesen.
    """
    vorhanden = fertige_laeufe_der_station(data_root, station)
    return vorhanden[-1] if vorhanden else None


def run_age_days(run_dir: Lauf | Path, reference: date) -> int | None:
    """Alter eines Laufs in Tagen, gemessen am Abrufdatum im Manifest."""
    manifest = manifest_des_laufs(run_dir)
    pfad = (run_dir.verzeichnis if isinstance(run_dir, Lauf) else run_dir) / "manifest.json"
    roh = manifest.get("ingest_date")
    if not roh:
        return None
    try:
        return (reference - date.fromisoformat(roh)).days
    except ValueError as error:
        raise IngestionError(
            f"Unlesbares ingest_date in {pfad}: {roh!r}"
        ) from error


def ingest_station(
    session: requests.Session,
    data_root: Path,
    started: datetime,
    station: str,
    force: bool,
    min_interval_days: int = DEFAULT_MIN_INTERVAL_DAYS,
) -> RunPaths | None:
    """Laedt eine Stationsreihe; None, wenn es nichts zu tun gab.

    Zwei Bremsen vor dem Download, siehe Modul-Docstring: der Mindestabstand
    zum letzten Lauf, den ``force`` uebergeht, und der bedingte Abruf, den es
    nicht uebergeht.
    """
    letzter = newest_run(data_root, station)

    if letzter is not None and not force and min_interval_days > 0:
        alter = run_age_days(letzter, started.date())
        if alter is not None and alter < min_interval_days:
            log.info(
                "%s wurde vor %s Tag(en) geladen (%s), Mindestabstand ist %s; "
                "--force laedt trotzdem",
                station,
                alter,
                letzter.verzeichnis.name,
                min_interval_days,
            )
            return None

    delivery = fetch_delivery(
        session, station, validators=conditional_headers(letzter)
    )
    if delivery is None:
        # 304: Die Quelle ist unveraendert. Ein weiterer Schnappschuss waere
        # byteweise derselbe und kostet nur Platz.
        return None
    return write_run(data_root, started, delivery, station=station)


def main() -> int:
    args = arguments()
    from storage.managed import guard
    guard(for_root(args.data_root).local_root, allow_worker=True)
    started = datetime.now(timezone.utc)

    ablage = for_root(args.data_root)
    data_root = ablage.local_root

    try:
        discard_stale_partials(data_root, started)
        geschrieben = 0
        with build_session() as session:
            for station in args.station:
                info = STATIONS.get(station, {})
                log.info(
                    "Starting GHCN-Daily for %s (%s, %s)",
                    station,
                    info.get("name", "unbekannt"),
                    info.get("city", "unbekannt"),
                )
                run = ingest_station(
                    session,
                    data_root,
                    started,
                    station,
                    args.force,
                    args.min_interval_days,
                )
                if run is not None:
                    geschrieben += 1
                    log.info("Immutable run completed: %s", run.raw)
                    log.info("                        %s", run.bronze)
                    ablage.publish_run(run.raw)
                    ablage.publish_run(run.bronze)
        log.info("Fertig: %s Lauf/Laeufe geschrieben", geschrieben)
        return 0
    except (IngestionError, OSError, ValueError, PublishError) as error:
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
