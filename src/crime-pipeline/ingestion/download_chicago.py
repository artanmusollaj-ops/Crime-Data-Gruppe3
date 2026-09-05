"""Load Chicago crime data into immutable bronze runs.

Every call writes one run to data/bronze/. Values keep the JSON type the API
sent them with: arrest and domestic are booleans, location is a nested struct,
everything else is a string, because that is what the API sends. No dates,
numbers or codes are parsed here; that belongs in the layers above.

The column set is pinned, so every run ever written shares one schema. Anything
that does not fit it - a field the city adds later, or a value whose JSON type
changes - is preserved verbatim in the _extra column instead of being dropped.
Socrata's own ":" columns, such as :@computed_region_*, are discarded.
"""

from __future__ import annotations

import argparse
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
DATASET_ID = "ijzp-q8t2"
CITY = "chicago"
LAYER = "bronze"
DEFAULT_YEAR = 2024
PAGE_SIZE = 10_000
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
    """Downloaded records plus the row count the API reported up front."""

    records: list[dict[str, Any]]
    expected_rows: int | None


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


def run_parent(data_root: Path, ingest_date: str) -> Path:
    return data_root / LAYER / f"city={CITY}" / f"ingest_date={ingest_date}"


def discard_stale_partials(data_root: Path, now: datetime) -> list[Path]:
    """Drop work directories a crashed run left behind.

    A run takes minutes, so anything older than STALE_PARTIAL_HOURS cannot
    belong to a live run and is safe to remove. Published runs are untouched.
    """
    cutoff = (now - timedelta(hours=STALE_PARTIAL_HOURS)).timestamp()
    removed = []
    pattern = f"{LAYER}/city={CITY}/ingest_date=*/.*.part"
    for path in sorted(data_root.glob(pattern)):
        if path.is_dir() and path.stat().st_mtime < cutoff:
            shutil.rmtree(path, ignore_errors=True)
            log.warning("Discarded stale partial run: %s", path)
            removed.append(path)
    return removed


def previous_watermark(data_root: Path, year: int) -> str | None:
    """Read the greatest watermark from complete, non-test runs."""
    values = []
    pattern = f"{LAYER}/city={CITY}/ingest_date=*/run_*/manifest.json"
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
    year: int, updated_from: str | None, limit: int, offset: int
) -> dict[str, Any]:
    """Ask for whole records; no $select, so new API fields are never lost."""
    return {
        "$where": where_clause(year, updated_from),
        "$order": "updated_on,id" if updated_from else "date,id",
        "$limit": limit,
        "$offset": offset,
    }


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


def fetch_json(session: requests.Session, params: dict[str, Any]) -> Any:
    try:
        response = session.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except requests.JSONDecodeError as error:
        raise IngestionError("API returned invalid JSON") from error
    except requests.RequestException as error:
        raise IngestionError(f"API request failed: {error}") from error


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


def download(
    year: int,
    updated_from: str | None,
    token: str | None,
    max_records: int | None,
) -> Download:
    """Download all API pages for this run and verify nothing was truncated."""
    records: list[dict[str, Any]] = []

    with build_session(token) as session:
        # A limited run truncates on purpose, so it is never counted.
        expected = None if max_records else expected_rows(session, year, updated_from)

        while True:
            remaining = max_records - len(records) if max_records else PAGE_SIZE
            limit = min(PAGE_SIZE, remaining)
            if limit <= 0:
                break

            page = fetch_json(session, query(year, updated_from, limit, len(records)))
            if not isinstance(page, list):
                raise IngestionError("API response is not a list")

            records.extend(page)
            log.info("Downloaded %s record(s)", f"{len(records):,}")
            if len(page) < limit:
                break

    if expected is not None and len(records) < expected:
        raise IngestionError(
            f"Truncated download: {len(records):,} of {expected:,} expected row(s)"
        )
    return Download(records, expected)


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
    request = requests.Request(
        "GET", API_URL, params=query(year, updated_from, limit, 0)
    )
    return request.prepare().url or API_URL


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
) -> Path:
    """Write Parquet and manifest, then publish the directory atomically."""
    ingest_date = started.date().isoformat()
    run_id = started.strftime("run_%Y%m%dT%H%M%S%fZ")
    parent = run_parent(data_root, ingest_date)
    final_dir = parent / run_id
    work_dir = parent / f".{run_id}.part"
    work_dir.mkdir(parents=True)

    try:
        parquet = work_dir / PARQUET_FILE
        table = bronze_table(result.records)
        pq.write_table(table, parquet, compression="snappy")

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
            "layer": LAYER,
            "format": "parquet (snappy)",
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
                "expected_rows": result.expected_rows,
                "verified": result.expected_rows is not None,
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
            "schema": {field.name: str(field.type) for field in SCHEMA},
            "files": [file_entry(parquet)],
        }
        (work_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        work_dir.rename(final_dir)
        return final_dir
    except BaseException:
        # ignore_errors keeps a cleanup problem from masking the real failure.
        shutil.rmtree(work_dir, ignore_errors=True)
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
        run_dir = write_run(
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
        log.info("Immutable run completed: %s", run_dir)
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
