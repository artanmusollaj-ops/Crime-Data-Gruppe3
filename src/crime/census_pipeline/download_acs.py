"""Load ACS 5-year estimates per census tract into immutable runs.

Die Tabelle liefert die Nenner, die der Staedtevergleich braucht: Ohne
Einwohnerzahl je Tract lassen sich nur absolute Fallzahlen vergleichen, keine
Raten. Aufgebaut ist der Lauf wie bei ``download_tiger`` - Raw und Bronze unter
einer gemeinsamen run_id, Partition nach Vintage und Bundesstaat, Manifest je
Schicht.

Die Werte behalten den Typ, den die API sendet: alles ist Text, auch Zahlen.
Auch die Fehlwert-Kennung ``-666666666`` bleibt unveraendert stehen - sie zu
deuten ist Aufgabe der Staging-Schicht, nicht der Ingestion.

Zwei Eigenheiten dieser Quelle sind der Grund fuer eigene Pruefungen:

Erstens antwortet die API **ohne** Schluessel mit HTTP 200 und einer
HTML-Seite "Missing Key" statt mit einem Fehlerstatus. Wer nur den Status
prueft, haelt das fuer einen Erfolg und schreibt einen leeren Lauf. Deshalb
wird die Antwort selbst geprueft, nicht ihr Status.

Zweitens nennt die API keine erwartete Zeilenzahl. Nachgewiesen wird die
Vollstaendigkeit deshalb ueber die Tracts: keine doppelten GEOIDs, und - sofern
ein TIGER-Lauf derselben Vintage vorliegt - ein Abgleich der GEOID-Mengen
zwischen Geometrie und Attributen. Beide Quellen stammen vom selben Herausgeber
und muessen deckungsgleich sein.
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

from census_pipeline import STATES


BASE_URL = "https://api.census.gov/data"
PRODUCT = "acs/acs5"
DATASET = "acs5_tract"
USER_AGENT = "crime-data-gruppe3/0.1 (Hochschulprojekt CAS Data Engineering)"
DEFAULT_VINTAGE = 2024
EARLIEST_VINTAGE = 2009
KEY_PARAMETER = "key"
KEY_VARIABLE = "CENSUS_API_KEY"

# Die abgefragten Variablen. Die Spaltennamen bleiben die Codes der Quelle -
# uebersetzt wird nicht, die Bedeutung haelt das Manifest fest.
VARIABLES = {
    "B01003_001E": "Einwohner insgesamt",
    "B19013_001E": "Median-Haushaltseinkommen (USD)",
    "B17001_002E": "Personen unter der Armutsgrenze",
}
NAME_FIELD = "NAME"
GEOGRAPHY_FIELDS = ("state", "county", "tract")
# GEOID ist die einzige abgeleitete Spalte: die drei Geografiefelder
# aneinandergehaengt. Sie ist der Schluessel zu den TIGER-Geometrien, und die
# Quelle liefert die Teile bereits nullgefuellt ("001", "000100"), sodass das
# Zusammensetzen verlustfrei und umkehrbar ist. Das Manifest weist sie als
# abgeleitet aus.
GEOID_COLUMN = "GEOID"
GEOID_LENGTH = 11
# Der ACS kennzeichnet nicht schaetzbare Werte mit negativen Sentinels,
# etwa das Median-Einkommen eines Tracts ohne Einwohner. Bronze laesst sie
# unveraendert stehen; sie zu deuten ist Aufgabe der Staging-Schicht.
MISSING_VALUE_CODE = "-666666666"
EXTRA_COLUMN = "_extra"

RAW_LAYER = "raw"
BRONZE_LAYER = "bronze"
LAYERS = (RAW_LAYER, BRONZE_LAYER)
LAYER_FORMAT = {
    RAW_LAYER: "application/json (gzip, eine API-Antwort je Datei)",
    BRONZE_LAYER: "parquet (snappy)",
}
PARQUET_FILE = "part-0001.parquet"
RESPONSE_FILE = "page-0001.json.gz"

TIMEOUT_SECONDS = 180
RETRY_TOTAL = 5
RETRY_BACKOFF = 1.0
RETRY_STATUS = (429, 500, 502, 503, 504)
STALE_PARTIAL_HOURS = 24

log = logging.getLogger("census_acs_ingestion")


def build_schema() -> pa.Schema:
    """Pin one Parquet schema for every vintage and every state."""
    fields = [pa.field(GEOID_COLUMN, pa.string()), pa.field(NAME_FIELD, pa.string())]
    fields += [pa.field(code, pa.string()) for code in VARIABLES]
    fields += [pa.field(name, pa.string()) for name in GEOGRAPHY_FIELDS]
    fields.append(pa.field(EXTRA_COLUMN, pa.string()))
    return pa.schema(fields)


SCHEMA = build_schema()
COLUMNS = tuple(SCHEMA.names)


class IngestionError(RuntimeError):
    """A run could not be downloaded or stored safely."""


class Answer(NamedTuple):
    """Die Antwort der API samt ihrem unveraenderten Koerper."""

    header: list[str]
    rows: list[list[Any]]
    body: bytes
    url: str


class RunPaths(NamedTuple):
    raw: Path
    bronze: Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", type=int, default=DEFAULT_VINTAGE)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--state", action="append", choices=sorted(STATES))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.vintage < EARLIEST_VINTAGE:
        parser.error(f"--vintage must be {EARLIEST_VINTAGE} or later")
    args.state = args.state or sorted(STATES)
    return args


def census_key() -> str:
    """Holt den Schluessel aus .env; ohne ihn ist die Quelle nicht nutzbar."""
    dotenv_path = find_dotenv(usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path)
    key = os.getenv(KEY_VARIABLE)
    if not key:
        raise IngestionError(
            f"{KEY_VARIABLE} fehlt. Kostenlos unter "
            "https://api.census.gov/data/key_signup.html und in .env eintragen."
        )
    return key


def acs_url(vintage: int) -> str:
    return f"{BASE_URL}/{vintage}/{PRODUCT}"


def query(state: str) -> list[tuple[str, str]]:
    """Die Abfrage ohne Schluessel - so steht sie auch im Manifest."""
    variables = ",".join([NAME_FIELD, *VARIABLES])
    return [("get", variables), ("for", "tract:*"), ("in", f"state:{state}")]


def query_url(vintage: int, state: str) -> str:
    """Reproduzierbare URL ohne den Schluessel."""
    request = requests.Request("GET", acs_url(vintage), params=query(state))
    return request.prepare().url or acs_url(vintage)


def run_parent(data_root: Path, layer: str, vintage: int, state: str) -> Path:
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
    """Bereits veroeffentlichte Laeufe dieser Vintage; Bronze zaehlt."""
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
    retry = Retry(
        total=RETRY_TOTAL,
        backoff_factor=RETRY_BACKOFF,
        status_forcelist=RETRY_STATUS,
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch_table(
    session: requests.Session, vintage: int, state: str, key: str
) -> Answer:
    """Laedt eine Tabelle und prueft die Antwort, nicht bloss ihren Status."""
    url = acs_url(vintage)
    params = [*query(state), (KEY_PARAMETER, key)]
    try:
        response = session.get(url, params=params, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        body = response.content
    except requests.RequestException as error:
        raise IngestionError(f"API request failed: {error}") from error

    header, rows = parse_payload(body)
    log.info("ACS %s %s: %s Tract(s) geladen", vintage, state, f"{len(rows):,}")
    return Answer(header=header, rows=rows, body=body, url=query_url(vintage, state))


def parse_payload(body: bytes) -> tuple[list[str], list[list[Any]]]:
    """Zerlegt die Antwort und faengt die Falle der fehlenden Schluessel ab.

    Die API antwortet ohne Schluessel mit HTTP 200 und einer HTML-Seite. Ein
    Statuscheck allein wuerde das nicht bemerken, deshalb wird hier auf die
    erwartete Form bestanden: eine Liste von Listen, deren erste die
    Spaltennamen enthaelt.
    """
    text = body.decode("utf-8", errors="replace").lstrip()
    if text[:1] != "[":
        hinweis = "Missing Key" if "Missing Key" in text[:600] else text[:120]
        raise IngestionError(f"Antwort ist keine ACS-Tabelle: {hinweis}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise IngestionError("API returned invalid JSON") from error

    if not isinstance(payload, list) or len(payload) < 1:
        raise IngestionError("ACS-Antwort ohne Kopfzeile")
    header = [str(name) for name in payload[0]]
    rows = [list(row) for row in payload[1:]]
    if not rows:
        raise IngestionError("ACS-Antwort ohne Datenzeilen")
    fehlend = [
        field for field in (*GEOGRAPHY_FIELDS, NAME_FIELD) if field not in header
    ]
    if fehlend:
        raise IngestionError(f"ACS-Antwort ohne Pflichtspalten: {fehlend}")
    return header, rows


def geoid(row: dict[str, Any]) -> str:
    """Setzt die Geografiefelder zum Tract-Schluessel zusammen."""
    value = "".join(str(row.get(field) or "") for field in GEOGRAPHY_FIELDS)
    if len(value) != GEOID_LENGTH:
        raise IngestionError(f"Unbrauchbare GEOID: {value!r}")
    return value


def bronze_rows(answer: Answer) -> list[dict[str, Any]]:
    """Bildet die Antwort auf das gepinnte Schema ab, ohne etwas zu verlieren."""
    bekannt = set(COLUMNS) - {GEOID_COLUMN, EXTRA_COLUMN}
    zeilen = []
    for values in answer.rows:
        record = dict(zip(answer.header, values))
        row: dict[str, Any] = {GEOID_COLUMN: geoid(record)}
        for column in COLUMNS:
            if column in (GEOID_COLUMN, EXTRA_COLUMN):
                continue
            value = record.get(column)
            row[column] = None if value is None else str(value)
        extra = {
            name: value
            for name, value in record.items()
            if name not in bekannt and value is not None
        }
        row[EXTRA_COLUMN] = json_text(extra) if extra else None
        zeilen.append(row)
    return zeilen


def bronze_table(answer: Answer) -> pa.Table:
    return pa.Table.from_pylist(bronze_rows(answer), schema=SCHEMA)


def verify_tracts(table: pa.Table) -> list[str]:
    """Doppelte Tracts waeren ein stiller Fehler; hier brechen sie den Lauf ab."""
    values = table.column(GEOID_COLUMN).to_pylist()
    if len(values) != len(set(values)):
        raise IngestionError("ACS lieferte doppelte GEOIDs")
    return values


def tiger_geoids(data_root: Path, vintage: int, state: str) -> list[str] | None:
    """Die GEOIDs des passenden TIGER-Laufs, falls einer vorliegt.

    Geometrie und Attribute stammen vom selben Herausgeber und derselben
    Vintage; ihre Tract-Mengen muessen deckungsgleich sein. Fehlt der
    Geometrie-Lauf, entfaellt der Abgleich - er ist ein Nachweis, kein Zwang.
    """
    from census_pipeline import download_tiger

    runs = download_tiger.completed_runs(data_root, vintage, state)
    if not runs:
        return None
    part = runs[-1] / download_tiger.PARQUET_FILE
    if not part.exists():
        return None
    return pq.ParquetFile(part).read().column("GEOID").to_pylist()


def compare_with_tiger(
    data_root: Path, vintage: int, state: str, geoids: list[str]
) -> dict[str, Any]:
    """Vergleicht die Tract-Mengen und haelt das Ergebnis fest."""
    referenz = tiger_geoids(data_root, vintage, state)
    if referenz is None:
        return {"compared": False, "reason": "kein TIGER-Lauf dieser Vintage"}

    attribute, geometrie = set(geoids), set(referenz)
    ergebnis = {
        "compared": True,
        "tiger_tracts": len(geometrie),
        "acs_tracts": len(attribute),
        "matching": attribute == geometrie,
        "only_in_tiger": sorted(geometrie - attribute)[:20],
        "only_in_acs": sorted(attribute - geometrie)[:20],
    }
    if not ergebnis["matching"]:
        log.warning(
            "Tract-Mengen weichen ab: %s nur in TIGER, %s nur in ACS",
            len(geometrie - attribute),
            len(attribute - geometrie),
        )
    return ergebnis


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


def write_landing(work_dir: Path, body: bytes) -> list[dict[str, Any]]:
    """Legt die Antwort unveraendert ab; mtime=0 haelt den Hash reproduzierbar."""
    path = work_dir / RESPONSE_FILE
    path.write_bytes(gzip.compress(body, mtime=0))
    return [file_entry(path)]


def write_bronze(
    work_dir: Path, answer: Answer
) -> tuple[pa.Table, list[dict[str, Any]]]:
    path = work_dir / PARQUET_FILE
    table = bronze_table(answer)
    pq.write_table(table, path, compression="snappy")
    return table, [file_entry(path)]


def write_run(
    data_root: Path,
    started: datetime,
    answer: Answer,
    *,
    vintage: int,
    state: str,
) -> RunPaths:
    """Schreibt beide Schichten und veroeffentlicht sie atomar, Raw zuerst."""
    ingest_date = started.date().isoformat()
    run_id = started.strftime("run_%Y%m%dT%H%M%S%fZ")
    parents = {layer: run_parent(data_root, layer, vintage, state) for layer in LAYERS}
    work = {layer: parent / f".{run_id}.part" for layer, parent in parents.items()}
    final = {layer: parent / run_id for layer, parent in parents.items()}
    for path in work.values():
        path.mkdir(parents=True)

    try:
        files = {RAW_LAYER: write_landing(work[RAW_LAYER], answer.body)}
        table, files[BRONZE_LAYER] = write_bronze(work[BRONZE_LAYER], answer)
        geoids = verify_tracts(table)

        manifest = {
            "status": "complete",
            "immutable": True,
            "source": "census_acs5",
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
            "row_count": table.num_rows,
            "variables": dict(VARIABLES),
            "derived_columns": {
                GEOID_COLUMN: "state + county + tract, Schluessel zu TIGER"
            },
            "missing_value_code": MISSING_VALUE_CODE,
            "completeness": {
                # Die Quelle nennt keine Zeilenzahl. Nachgewiesen wird die
                # Eindeutigkeit der Tracts und, wenn moeglich, die Deckung mit
                # den Geometrien derselben Vintage.
                "verified": True,
                "unique_tracts": len(set(geoids)),
                "tiger_cross_check": compare_with_tiger(
                    data_root, vintage, state, geoids
                ),
            },
            "query": {
                "method": "GET",
                # Der Schluessel gehoert bei dieser API in die Abfrage, nicht in
                # einen Header. Im Manifest steht die URL deshalb ohne ihn.
                "url_without_key": answer.url,
                "key_parameter": KEY_PARAMETER,
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
    key: str,
    force: bool,
) -> RunPaths | None:
    """Laedt eine Vintage fuer einen Bundesstaat; None, wenn nichts zu tun war."""
    vorhanden = completed_runs(data_root, vintage, state)
    if vorhanden and not force:
        log.info(
            "ACS %s %s ist bereits geladen (%s); --force erzwingt einen neuen Lauf",
            vintage,
            STATES.get(state, state),
            vorhanden[-1].name,
        )
        return None
    answer = fetch_table(session, vintage, state, key)
    return write_run(data_root, started, answer, vintage=vintage, state=state)


def main() -> int:
    args = arguments()
    started = datetime.now(timezone.utc)

    try:
        key = census_key()
        discard_stale_partials(args.data_root, started)
        geschrieben = 0
        with build_session() as session:
            for state in args.state:
                log.info(
                    "Starting ACS5 %s for %s (%s)",
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
                    key,
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
