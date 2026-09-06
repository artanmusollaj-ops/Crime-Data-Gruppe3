"""Load Chicago crime data into immutable bronze runs.

Every call writes one run to data/raw/ and data/bronze/ under a shared run id.
Raw holds the API responses byte for byte; bronze is derived from them. Values keep the JSON type the API
sent them with: arrest and domestic are booleans, location is a nested struct,
everything else is a string, because that is what the API sends. No dates,
numbers or codes are parsed here; that belongs in the layers above.

The column set is pinned, so every run ever written shares one schema. Anything
that does not fit it - a field the city adds later, or a value whose JSON type
changes - is preserved verbatim in the _extra column instead of being dropped.
Socrata's own ":" columns, such as :@computed_region_*, are discarded.

Vollstaendigkeit wird nicht behauptet, sondern nachgewiesen: Vor dem Download
wird die Menge der ids festgeschrieben, geladen wird per Keyset-Pagination, und
danach muss die Menge der geladenen ids exakt der festgeschriebenen entsprechen.
Ein Fingerabdruck ueber die Feldtypen der Quelle macht Schema-Drift sichtbar.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NamedTuple

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from dotenv import find_dotenv, load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_URL = "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
METADATA_URL = "https://data.cityofchicago.org/api/views/ijzp-q8t2.json"
DATASET_ID = "ijzp-q8t2"
CITY = "chicago"
# Zwei Schichten je Lauf. Raw ist das Beweisstueck: die API-Antworten Byte fuer
# Byte. Bronze ist daraus abgeleitet und jederzeit neu erzeugbar.
RAW_LAYER = "raw"
BRONZE_LAYER = "bronze"
LAYERS = (RAW_LAYER, BRONZE_LAYER)
LAYER_FORMAT = {
    RAW_LAYER: "application/json (gzip, eine API-Antwort je Datei)",
    BRONZE_LAYER: "parquet (snappy)",
}
DEFAULT_YEAR = 2024
PAGE_SIZE = 10_000
# Die Mitgliedschaft des Snapshots wird ueber id festgeschrieben. Socrata
# liefert reine id-Abfragen in sehr grossen Seiten, ein ganzer Jahrgang kostet
# damit nur wenige zusaetzliche Anfragen.
ID_FIELD = "id"
ID_PAGE_SIZE = 50_000
LOOKBACK_DAYS = 14
TIMEOUT_SECONDS = 60
RETRY_TOTAL = 5
RETRY_BACKOFF = 1.0
RETRY_STATUS = (429, 500, 502, 503, 504)
STALE_PARTIAL_HOURS = 24
COUNT_ALIAS = "row_count"
PARQUET_FILE = "part-0001.parquet"

# The pinned column set. The API is queried without $select, so whole records
# arrive and a new field lands in EXTRA_COLUMN rather than being lost.
FIELDS = (
    "id",
    "case_number",
    "date",
    "block",
    "iucr",
    "primary_type",
    "description",
    "location_description",
    "arrest",
    "domestic",
    "beat",
    "district",
    "ward",
    "community_area",
    "fbi_code",
    "x_coordinate",
    "y_coordinate",
    "year",
    "updated_on",
    "latitude",
    "longitude",
    "location",
)
# Socrata bookkeeping columns all live in the ":" namespace: the spatial joins
# :@computed_region_* plus :id, :created_at, :updated_at, :version. They are
# platform artefacts, not city data, so they are dropped rather than kept in
# EXTRA_COLUMN. Today the API already omits them whenever $where or $order is
# used, which our query always does, but that behaviour is undocumented.
SYSTEM_PREFIX = ":"
BOOLEAN_FIELDS = ("arrest", "domestic")
LOCATION_FIELD = "location"
LOCATION_SUBFIELDS = ("latitude", "longitude", "human_address")
EXTRA_COLUMN = "_extra"

log = logging.getLogger("chicago_ingestion")


def build_schema() -> pa.Schema:
    """Pin one Parquet schema that mirrors the JSON types of the API."""

    def column(field: str) -> pa.Field:
        if field in BOOLEAN_FIELDS:
            return pa.field(field, pa.bool_())
        if field == LOCATION_FIELD:
            return pa.field(
                field,
                pa.struct([pa.field(key, pa.string()) for key in LOCATION_SUBFIELDS]),
            )
        return pa.field(field, pa.string())

    return pa.schema(
        [column(field) for field in FIELDS] + [pa.field(EXTRA_COLUMN, pa.string())]
    )


SCHEMA = build_schema()
COLUMNS = tuple(SCHEMA.names)


class IngestionError(RuntimeError):
    """A run could not be downloaded or stored safely."""


class Download(NamedTuple):
    """Alles, was ein Lauf geladen hat, plus die Nachweise der Vollstaendigkeit.

    ``snapshot_size`` und ``snapshot_sha256`` beschreiben die vor dem Download
    festgeschriebene Menge der ids. Ist sie gesetzt, wurde geprueft, dass genau
    diese Datensaetze angekommen sind. ``source_count_after`` dokumentiert nur,
    ob sich die Quelle waehrend des Laufs bewegt hat, und blockiert nicht.
    """

    records: list[dict[str, Any]]
    bodies: list[bytes]
    source_count_before: int | None = None
    source_count_after: int | None = None
    snapshot_size: int | None = None
    snapshot_sha256: str | None = None
    schema_fingerprint: str | None = None
    schema_fields: dict[str, str] | None = None


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--max-records", type=int, help="Limit for test runs")
    parser.add_argument("--full", action="store_true", help="Force a new full snapshot")
    parser.add_argument("--no-token", action="store_true")
    args = parser.parse_args()
    if args.year < 2001:
        parser.error("--year must be 2001 or later")
    if args.max_records is not None and args.max_records < 1:
        parser.error("--max-records must be greater than zero")
    return args


def app_token(disabled: bool) -> str | None:
    if disabled:
        return None
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
    return os.getenv("SOCRATA_APP_TOKEN") or None


def run_parent(data_root: Path, layer: str, ingest_date: str) -> Path:
    return data_root / layer / f"city={CITY}" / f"ingest_date={ingest_date}"


def discard_stale_partials(data_root: Path, now: datetime) -> list[Path]:
    """Drop work directories a crashed run left behind.

    A run takes minutes, so anything older than STALE_PARTIAL_HOURS cannot
    belong to a live run and is safe to remove. Published runs are untouched.
    """
    cutoff = (now - timedelta(hours=STALE_PARTIAL_HOURS)).timestamp()
    removed = []
    for layer in LAYERS:
        pattern = f"{layer}/city={CITY}/ingest_date=*/.*.part"
        for path in sorted(data_root.glob(pattern)):
            if path.is_dir() and path.stat().st_mtime < cutoff:
                shutil.rmtree(path, ignore_errors=True)
                log.warning("Discarded stale partial run: %s", path)
                removed.append(path)
    return removed


def previous_watermark(data_root: Path, year: int) -> str | None:
    """Liest das hoechste Wasserzeichen aus vollstaendigen Bronze-Laeufen.

    Bronze wird zuletzt veroeffentlicht, das Wasserzeichen rueckt also erst vor,
    wenn der ganze Lauf stand. Ein Raw-Lauf ohne Bronze-Zwilling kostet eine
    Wiederholung, nie eine Luecke.
    """
    values = []
    pattern = f"{BRONZE_LAYER}/city={CITY}/ingest_date=*/run_*/manifest.json"
    for path in data_root.glob(pattern):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise IngestionError(f"Invalid manifest: {path}") from error

        if (
            manifest.get("status") == "complete"
            and manifest.get("event_year") == year
            and manifest.get("max_records") is None
        ):
            value = manifest.get("watermark", {}).get("maximum_seen")
            if value:
                values.append(value)
    # Sorts as text, which matches chronological order only because the API
    # returns fixed-width timestamps such as 2024-05-01T09:00:00.000.
    return max(values, default=None)


def delta_start(watermark: str | None) -> str | None:
    if watermark is None:
        return None
    try:
        value = datetime.fromisoformat(watermark.replace("Z", "+00:00"))
    except ValueError as error:
        raise IngestionError(f"Invalid watermark: {watermark}") from error
    start = value - timedelta(days=LOOKBACK_DAYS)
    # SoQL floating timestamps carry no offset, so drop any zone information.
    return start.replace(tzinfo=None).isoformat(timespec="milliseconds")


def where_clause(year: int, updated_from: str | None) -> str:
    where = [
        f"date >= '{year}-01-01T00:00:00'",
        f"date < '{year + 1}-01-01T00:00:00'",
    ]
    if updated_from:
        where.append(f"updated_on >= '{updated_from}'")
    return " AND ".join(where)


def query(
    year: int,
    updated_from: str | None,
    limit: int,
    after_id: int | None = None,
    select: str | None = None,
) -> dict[str, Any]:
    """Baut eine Seitenabfrage mit Keyset-Pagination ueber die id.

    Statt ``$offset`` wird der zuletzt gesehene Schluessel weitergereicht.
    Damit koennen gleichzeitige Aenderungen an der Quelle keine Zeilen zwischen
    den Seiten verschieben, wie es bei Offset-Paginierung passieren kann.
    Ohne ``select`` werden ganze Datensaetze geladen, damit ein neues API-Feld
    nicht verloren geht.
    """
    where = where_clause(year, updated_from)
    if after_id is not None:
        where = f"{where} AND {ID_FIELD} > {after_id}"
    params: dict[str, Any] = {
        "$where": where,
        "$order": ID_FIELD,
        "$limit": limit,
    }
    if select:
        params["$select"] = select
    return params


def count_query(year: int, updated_from: str | None) -> dict[str, Any]:
    return {
        "$select": f"count(1) AS {COUNT_ALIAS}",
        "$where": where_clause(year, updated_from),
    }


def build_session(token: str | None) -> requests.Session:
    """Create a session that retries throttling and transient server errors."""
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=RETRY_STATUS,
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    if token:
        session.headers["X-App-Token"] = token
    return session


def fetch_raw(
    session: requests.Session, params: dict[str, Any], url: str = API_URL
) -> tuple[Any, bytes]:
    """Liefert die geparste Antwort und ihren unveraenderten Koerper."""
    try:
        response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json(), response.content
    except requests.JSONDecodeError as error:
        raise IngestionError("API returned invalid JSON") from error
    except requests.RequestException as error:
        raise IngestionError(f"API request failed: {error}") from error


def fetch_json(
    session: requests.Session, params: dict[str, Any], url: str = API_URL
) -> Any:
    return fetch_raw(session, params, url)[0]


def source_schema(session: requests.Session) -> tuple[str | None, dict[str, str]]:
    """Liest die Feldtypen der Quelle und bildet daraus einen Fingerabdruck.

    Der Fingerabdruck macht Schema-Drift sichtbar: Aendert die Stadt den Typ
    eines Feldes, aendert sich der Hash, auch wenn die Ingestion weiterlaeuft.
    Die Spalten im ``:``-Namensraum bleiben aussen vor, weil sie ohnehin
    verworfen werden und ihre Aenderungen den Fingerabdruck nur verrauschen.

    Faellt der Endpunkt aus, laeuft der Lauf ohne Fingerabdruck weiter; das ist
    Beobachtung, kein Vollstaendigkeits-Gate.
    """
    try:
        payload = fetch_json(session, {}, url=METADATA_URL)
        columns = payload.get("columns") or []
        fields = {
            str(column["fieldName"]): str(column.get("dataTypeName") or "")
            for column in columns
            if column.get("fieldName")
            and not str(column["fieldName"]).startswith(SYSTEM_PREFIX)
        }
        if not fields:
            raise IngestionError("Metadaten enthalten keine Felder")
        return hashlib.sha256(json_text(fields).encode("utf-8")).hexdigest(), fields
    except (IngestionError, AttributeError, KeyError, TypeError) as error:
        log.warning("Schema-Fingerabdruck nicht verfuegbar: %s", error)
        return None, {}


def snapshot_ids(
    session: requests.Session, year: int, updated_from: str | None
) -> list[int]:
    """Schreibt die Mitgliedschaft des Snapshots fest, bevor geladen wird.

    Erst wenn feststeht, welche ids zum Lauf gehoeren, laesst sich nach dem
    Download beweisen, dass genau diese Datensaetze angekommen sind. Reine
    id-Abfragen sind klein, ein voller Jahrgang kostet nur wenige Anfragen.
    """
    ids: list[int] = []
    after_id: int | None = None

    while True:
        page = fetch_json(
            session, query(year, updated_from, ID_PAGE_SIZE, after_id, ID_FIELD)
        )
        if not isinstance(page, list):
            raise IngestionError("API response is not a list")
        if not page:
            break
        try:
            batch = [int(row[ID_FIELD]) for row in page]
        except (KeyError, TypeError, ValueError) as error:
            raise IngestionError(f"Unbrauchbare id in der Snapshot-Liste: {error}")
        ids.extend(batch)
        after_id = batch[-1]
        log.info("Snapshot: %s id(s) festgeschrieben", f"{len(ids):,}")
        if len(page) < ID_PAGE_SIZE:
            break

    if len(ids) != len(set(ids)):
        raise IngestionError("API lieferte doppelte ids in der Snapshot-Liste")
    return ids


def expected_rows(
    session: requests.Session, year: int, updated_from: str | None
) -> int | None:
    """Ask the API how many rows this run should contain.

    Returns None when the count is unavailable. The run is then published with
    completeness marked unverified instead of failing over a secondary query.
    """
    try:
        payload = fetch_json(session, count_query(year, updated_from))
        return int(payload[0][COUNT_ALIAS])
    except (IngestionError, LookupError, TypeError, ValueError) as error:
        log.warning("Row count unavailable, completeness not verified: %s", error)
        return None


def fetch_records(
    session: requests.Session,
    year: int,
    updated_from: str | None,
    max_records: int | None,
) -> tuple[list[dict[str, Any]], list[bytes]]:
    """Laedt Datensaetze per Keyset-Pagination und behaelt jede Antwort bei.

    Die Antwortkoerper wandern unveraendert in die Raw-Schicht, deshalb werden
    sie hier neben den geparsten Datensaetzen gesammelt.
    """
    records: list[dict[str, Any]] = []
    bodies: list[bytes] = []
    after_id: int | None = None

    while True:
        remaining = max_records - len(records) if max_records else PAGE_SIZE
        limit = min(PAGE_SIZE, remaining)
        if limit <= 0:
            break

        page, body = fetch_raw(session, query(year, updated_from, limit, after_id))
        if not isinstance(page, list):
            raise IngestionError("API response is not a list")
        if not page:
            break

        try:
            after_id = int(page[-1][ID_FIELD])
        except (KeyError, TypeError, ValueError) as error:
            raise IngestionError(f"Datensatz ohne brauchbare id: {error}")

        records.extend(page)
        bodies.append(body)
        log.info("Downloaded %s record(s)", f"{len(records):,}")
        if len(page) < limit:
            break

    return records, bodies


def verify_snapshot(records: list[dict[str, Any]], expected_ids: list[int]) -> None:
    """Prueft, dass genau die festgeschriebenen Datensaetze angekommen sind."""
    try:
        geladen = {int(row[ID_FIELD]) for row in records}
    except (KeyError, TypeError, ValueError) as error:
        raise IngestionError(f"Datensatz ohne brauchbare id: {error}")

    erwartet = set(expected_ids)
    if geladen == erwartet:
        return
    fehlend = len(erwartet - geladen)
    zusaetzlich = len(geladen - erwartet)
    raise IngestionError(
        f"Snapshot nicht eingehalten: {len(geladen):,} von {len(erwartet):,} "
        f"id(s) geladen, {fehlend:,} fehlend, {zusaetzlich:,} unerwartet"
    )


def download(
    year: int,
    updated_from: str | None,
    token: str | None,
    max_records: int | None,
) -> Download:
    """Laedt einen Lauf und weist seine Vollstaendigkeit nach.

    Reihenfolge der Pruefungen:

    1. Serverseitige Zeilenzahl vor dem Lauf.
    2. Feste id-Liste; sie muss zur Zeilenzahl passen und darf keine
       Dubletten enthalten.
    3. Nach dem Download muss die Menge der geladenen ids exakt der Liste
       entsprechen.
    4. Zweite Zeilenzahl; sie dokumentiert nur, ob sich die Quelle waehrend
       des Laufs bewegt hat, und blockiert nicht.

    Ein Lauf mit ``max_records`` kuerzt absichtlich und durchlaeuft die Gates
    nicht; er wird spaeter auch nicht als Wasserzeichen verwendet.
    """
    with build_session(token) as session:
        fingerprint, fields = source_schema(session)

        if max_records:
            records, bodies = fetch_records(session, year, updated_from, max_records)
            return Download(
                records,
                bodies,
                schema_fingerprint=fingerprint,
                schema_fields=fields,
            )

        count_before = expected_rows(session, year, updated_from)
        expected_ids = snapshot_ids(session, year, updated_from)
        if count_before is not None and count_before != len(expected_ids):
            raise IngestionError(
                f"Zeilenzahl {count_before:,} passt nicht zur Snapshot-Liste "
                f"mit {len(expected_ids):,} id(s)"
            )

        records, bodies = fetch_records(session, year, updated_from, None)
        verify_snapshot(records, expected_ids)
        count_after = expected_rows(session, year, updated_from)

    digest = hashlib.sha256(
        ",".join(str(value) for value in sorted(expected_ids)).encode("utf-8")
    ).hexdigest()
    if count_before != count_after:
        log.warning(
            "Quelle hat sich waehrend des Laufs veraendert: %s -> %s",
            count_before,
            count_after,
        )
    return Download(
        records,
        bodies,
        source_count_before=count_before,
        source_count_after=count_after,
        snapshot_size=len(expected_ids),
        snapshot_sha256=digest,
        schema_fingerprint=fingerprint,
        schema_fields=fields,
    )


def json_text(value: Any) -> str:
    """Serialise a value compactly and deterministically."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fits(field: str, value: Any) -> bool:
    """Does the value carry the JSON type this column is pinned to?"""
    if field in BOOLEAN_FIELDS:
        return isinstance(value, bool)
    if field == LOCATION_FIELD:
        return (
            isinstance(value, dict)
            and set(value) <= set(LOCATION_SUBFIELDS)
            and all(isinstance(item, str) for item in value.values())
        )
    return isinstance(value, str)


def bronze_row(record: dict[str, Any]) -> dict[str, Any]:
    """Map one record onto the pinned columns, losing nothing.

    A value whose JSON type no longer matches the schema, and any field outside
    FIELDS, is kept verbatim in EXTRA_COLUMN and its column is left null.
    Socrata's own SYSTEM_PREFIX columns are the exception: they are discarded.
    """
    row: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for field in FIELDS:
        value = record.get(field)
        if value is None:
            row[field] = None
        elif not fits(field, value):
            row[field] = None
            extra[field] = value
        elif field == LOCATION_FIELD:
            row[field] = {key: value.get(key) for key in LOCATION_SUBFIELDS}
        else:
            row[field] = value

    for field, value in record.items():
        if field not in FIELDS and not field.startswith(SYSTEM_PREFIX):
            extra[field] = value

    row[EXTRA_COLUMN] = json_text(extra) if extra else None
    return row


def bronze_table(records: list[dict[str, Any]]) -> pa.Table:
    return pa.Table.from_pylist([bronze_row(row) for row in records], schema=SCHEMA)


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


def query_url(year: int, updated_from: str | None, limit: int) -> str:
    """Build a reproducible first-page URL; the token is never in the URL."""
    request = requests.Request("GET", API_URL, params=query(year, updated_from, limit))
    return request.prepare().url or API_URL


class RunPaths(NamedTuple):
    """Wo ein veroeffentlichter Lauf gelandet ist."""

    raw: Path
    bronze: Path


def write_landing(work_dir: Path, bodies: list[bytes]) -> list[dict[str, Any]]:
    """Legt jede API-Antwort unveraendert ab, gzip-komprimiert.

    ``mtime=0`` macht die komprimierten Bytes zu einer reinen Funktion der
    Antwort, sodass der SHA-256 im Manifest reproduzierbar bleibt.
    """
    entries = []
    for number, body in enumerate(bodies, start=1):
        path = work_dir / f"page-{number:04d}.json.gz"
        path.write_bytes(gzip.compress(body, mtime=0))
        entries.append(file_entry(path))
    return entries


def write_bronze(
    work_dir: Path, records: list[dict[str, Any]]
) -> tuple[pa.Table, list[dict[str, Any]]]:
    """Leitet die Parquet-Datei aus den Datensaetzen ab."""
    path = work_dir / PARQUET_FILE
    table = bronze_table(records)
    pq.write_table(table, path, compression="snappy")
    return table, [file_entry(path)]


def write_run(
    data_root: Path,
    started: datetime,
    result: Download,
    *,
    year: int,
    mode: str,
    old_watermark: str | None,
    updated_from: str | None,
    token_used: bool,
    max_records: int | None,
) -> RunPaths:
    """Schreibt beide Schichten und veroeffentlicht sie atomar, Raw zuerst."""
    ingest_date = started.date().isoformat()
    run_id = started.strftime("run_%Y%m%dT%H%M%S%fZ")
    parents = {
        layer: run_parent(data_root, layer, ingest_date) for layer in LAYERS
    }
    work = {layer: parent / f".{run_id}.part" for layer, parent in parents.items()}
    final = {layer: parent / run_id for layer, parent in parents.items()}
    for path in work.values():
        path.mkdir(parents=True)

    try:
        files = {RAW_LAYER: write_landing(work[RAW_LAYER], result.bodies)}
        table, files[BRONZE_LAYER] = write_bronze(
            work[BRONZE_LAYER], result.records
        )

        watermarks = [old_watermark] if old_watermark else []
        watermarks.extend(
            row["updated_on"] for row in result.records if row.get("updated_on")
        )
        # Text comparison; see the note in previous_watermark.
        maximum_seen = max(watermarks, default=None)
        first_limit = min(PAGE_SIZE, max_records) if max_records else PAGE_SIZE
        manifest = {
            "status": "complete",
            "immutable": True,
            "city": CITY,
            "dataset_id": DATASET_ID,
            "event_year": year,
            "mode": mode,
            "ingest_date": ingest_date,
            "run_id": run_id,
            "started_at_utc": started.isoformat().replace("+00:00", "Z"),
            "completed_at_utc": datetime.now(timezone.utc).isoformat().replace(
                "+00:00", "Z"
            ),
            "row_count": table.num_rows,
            "max_records": max_records,
            "used_app_token": token_used,
            "completeness": {
                # verified sagt, ob die Snapshot-Kette durchlaufen wurde: feste
                # id-Liste vor dem Download, Abgleich danach.
                "verified": result.snapshot_size is not None,
                "source_count_before": result.source_count_before,
                "source_count_after": result.source_count_after,
                "source_changed_during_run": (
                    result.source_count_before != result.source_count_after
                ),
                "snapshot_size": result.snapshot_size,
                "snapshot_sha256": result.snapshot_sha256,
                "downloaded_rows": table.num_rows,
            },
            "source_schema": {
                "fingerprint": result.schema_fingerprint,
                "fields": result.schema_fields or {},
            },
            "watermark": {
                "field": "updated_on",
                "previous_maximum": old_watermark,
                "lookback_days": LOOKBACK_DAYS if updated_from else 0,
                "query_from": updated_from,
                "maximum_seen": maximum_seen,
            },
            "query": {
                "method": "GET",
                "url_first_page": query_url(year, updated_from, first_limit),
                "whole_records": True,
                "dropped_field_prefix": SYSTEM_PREFIX,
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

        # Raw ist das Beweisstueck und wird zuerst veroeffentlicht. Scheitert
        # danach Bronze, bleibt es erhalten, das Wasserzeichen rueckt aber nicht
        # vor und der naechste Lauf wiederholt dasselbe Fenster.
        work[RAW_LAYER].rename(final[RAW_LAYER])
        work[BRONZE_LAYER].rename(final[BRONZE_LAYER])
        return RunPaths(final[RAW_LAYER], final[BRONZE_LAYER])
    except BaseException:
        # ignore_errors keeps a cleanup problem from masking the real failure.
        for path in work.values():
            shutil.rmtree(path, ignore_errors=True)
        raise


def main() -> int:
    args = arguments()
    started = datetime.now(timezone.utc)
    token = app_token(args.no_token)

    try:
        discard_stale_partials(args.data_root, started)
        watermark = previous_watermark(args.data_root, args.year)
        updated_from = delta_start(watermark) if watermark and not args.full else None
        mode = "delta" if updated_from else "full_snapshot"
        log.info("Starting %s for Chicago %s", mode, args.year)

        result = download(args.year, updated_from, token, args.max_records)
        run = write_run(
            args.data_root,
            started,
            result,
            year=args.year,
            mode=mode,
            old_watermark=watermark,
            updated_from=updated_from,
            token_used=token is not None,
            max_records=args.max_records,
        )
        log.info("Immutable run completed: %s", run.raw)
        log.info("                        %s", run.bronze)
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
