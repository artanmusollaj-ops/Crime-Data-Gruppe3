"""Tests fuer die ACS-Ingestion.

Sie laufen ohne Netzzugriff und - bis auf den Abgleich mit den Geometrien -
auch ohne pyogrio: Die Attributseite braucht kein GDAL.
"""

from __future__ import annotations

import gzip
import importlib.util
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import download_acs as da


VINTAGE = 2024
STATE = "26"
STARTED = datetime(2026, 9, 6, 4, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run_20260906T040000000000Z"

braucht_pyogrio = pytest.mark.skipif(
    importlib.util.find_spec("pyogrio") is None,
    reason="Der Abgleich mit den TIGER-Geometrien braucht pyogrio",
)


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------


def payload(rows=None, header=None) -> bytes:
    """Eine Antwort, wie die API sie liefert: Kopfzeile plus Datenzeilen."""
    header = header or [
        "NAME",
        "B01003_001E",
        "B19013_001E",
        "B17001_002E",
        "state",
        "county",
        "tract",
    ]
    rows = rows if rows is not None else [
        ["Census Tract 1; Wayne County; Michigan", "1837", "70326", "129",
         "26", "163", "000100"],
        ["Census Tract 2; Wayne County; Michigan", "0", "-666666666", "0",
         "26", "163", "000200"],
    ]
    return json.dumps([header, *rows]).encode("utf-8")


def make_answer(**overrides) -> da.Answer:
    body = overrides.pop("body", payload())
    header, rows = da.parse_payload(body)
    return da.Answer(
        header=header,
        rows=rows,
        body=body,
        url=da.query_url(VINTAGE, STATE),
    )


class FakeResponse:
    def __init__(self, body: bytes):
        self.content = body

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    def __init__(self, body: bytes):
        self.body = body
        self.calls: list[list[tuple[str, str]]] = []

    def get(self, url, params=None, **kwargs):
        self.calls.append(list(params or []))
        return FakeResponse(self.body)


def read_manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def write_default_run(tmp_path: Path, **overrides) -> da.RunPaths:
    return da.write_run(
        overrides.pop("data_root", tmp_path / "data"),
        overrides.pop("started", STARTED),
        overrides.pop("answer", None) or make_answer(),
        vintage=overrides.pop("vintage", VINTAGE),
        state=overrides.pop("state", STATE),
    )


def write_tiger_run(tmp_path: Path, geoids: list[str], vintage: int = VINTAGE) -> None:
    """Legt einen Geometrie-Lauf an, gegen den der Abgleich laufen kann."""
    import download_tiger as dt

    parent = dt.run_parent(tmp_path / "data", dt.BRONZE_LAYER, vintage, STATE)
    run = parent / RUN_ID
    run.mkdir(parents=True)
    table = pa.Table.from_pylist(
        [{"GEOID": value} for value in geoids],
        schema=pa.schema([pa.field("GEOID", pa.string())]),
    )
    pq.write_table(table, run / dt.PARQUET_FILE)
    (run / "manifest.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# Die Antwort pruefen, nicht ihren Status
# --------------------------------------------------------------------------


def test_parse_payload_reads_header_and_rows():
    header, rows = da.parse_payload(payload())
    assert header[0] == "NAME"
    assert len(rows) == 2


def test_parse_payload_catches_the_missing_key_page():
    """Die API antwortet ohne Schluessel mit HTTP 200 und HTML."""
    html = b"<html><head><title>Missing Key</title></head><body></body></html>"
    with pytest.raises(da.IngestionError, match="Missing Key"):
        da.parse_payload(html)


def test_parse_payload_rejects_invalid_json():
    with pytest.raises(da.IngestionError, match="keine ACS-Tabelle|invalid JSON"):
        da.parse_payload(b"[kaputt")


def test_parse_payload_rejects_a_table_without_rows():
    with pytest.raises(da.IngestionError, match="ohne Datenzeilen"):
        da.parse_payload(json.dumps([["NAME", "state", "county", "tract"]]).encode())


def test_parse_payload_rejects_missing_geography_columns():
    body = json.dumps([["NAME", "B01003_001E"], ["Tract", "1"]]).encode()
    with pytest.raises(da.IngestionError, match="Pflichtspalten"):
        da.parse_payload(body)


def test_fetch_table_sends_the_key_and_returns_the_body():
    session = FakeSession(payload())
    answer = da.fetch_table(session, VINTAGE, STATE, "geheim")
    assert answer.body == payload()
    assert ("key", "geheim") in session.calls[0]


def test_query_url_never_contains_the_key():
    """Der Schluessel gehoert bei dieser API in die Abfrage - nicht ins Manifest."""
    url = da.query_url(VINTAGE, STATE)
    assert "key=" not in url
    assert "state%3A26" in url or "state:26" in url


# --------------------------------------------------------------------------
# Abbildung auf das gepinnte Schema
# --------------------------------------------------------------------------


def test_geoid_is_state_county_tract():
    row = {"state": "26", "county": "163", "tract": "000100"}
    assert da.geoid(row) == "26163000100"


def test_geoid_rejects_an_unusable_key():
    with pytest.raises(da.IngestionError, match="Unbrauchbare GEOID"):
        da.geoid({"state": "26", "county": "163", "tract": ""})


def test_bronze_table_uses_the_pinned_schema():
    assert da.bronze_table(make_answer()).schema == da.SCHEMA


def test_bronze_table_keeps_every_value_as_text():
    """Die API sendet alles als Text; gedeutet wird erst oberhalb von Bronze."""
    table = da.bronze_table(make_answer())
    assert table.column("B01003_001E").to_pylist() == ["1837", "0"]


def test_bronze_table_keeps_the_missing_value_code_verbatim():
    """-666666666 heisst 'nicht verfuegbar' und bleibt unveraendert stehen."""
    table = da.bronze_table(make_answer())
    assert table.column("B19013_001E").to_pylist()[1] == "-666666666"


def test_bronze_table_puts_an_unknown_column_into_extra():
    header = [
        "NAME", "B01003_001E", "B19013_001E", "B17001_002E",
        "B25001_001E", "state", "county", "tract",
    ]
    rows = [["Tract", "1", "2", "3", "77", "26", "163", "000100"]]
    table = da.bronze_table(make_answer(body=payload(rows=rows, header=header)))
    assert json.loads(table.column(da.EXTRA_COLUMN)[0].as_py()) == {"B25001_001E": "77"}


def test_bronze_table_without_extras_leaves_the_column_empty():
    table = da.bronze_table(make_answer())
    assert table.column(da.EXTRA_COLUMN).to_pylist() == [None, None]


def test_verify_tracts_rejects_duplicates():
    rows = [
        ["Tract", "1", "2", "3", "26", "163", "000100"],
        ["Tract", "1", "2", "3", "26", "163", "000100"],
    ]
    table = da.bronze_table(make_answer(body=payload(rows=rows)))
    with pytest.raises(da.IngestionError, match="doppelte GEOIDs"):
        da.verify_tracts(table)


# --------------------------------------------------------------------------
# Abgleich mit den Geometrien
# --------------------------------------------------------------------------


def test_compare_with_tiger_without_a_geometry_run(tmp_path):
    ergebnis = da.compare_with_tiger(
        tmp_path / "data", VINTAGE, STATE, ["26163000100"]
    )
    assert ergebnis["compared"] is False


@braucht_pyogrio
def test_compare_with_tiger_confirms_matching_tracts(tmp_path):
    geoids = ["26163000100", "26163000200"]
    write_tiger_run(tmp_path, geoids)
    ergebnis = da.compare_with_tiger(tmp_path / "data", VINTAGE, STATE, geoids)
    assert ergebnis["compared"] is True
    assert ergebnis["matching"] is True
    assert ergebnis["tiger_tracts"] == ergebnis["acs_tracts"] == 2


@braucht_pyogrio
def test_compare_with_tiger_reports_a_difference(tmp_path):
    write_tiger_run(tmp_path, ["26163000100", "26163009999"])
    ergebnis = da.compare_with_tiger(
        tmp_path / "data", VINTAGE, STATE, ["26163000100", "26163000200"]
    )
    assert ergebnis["matching"] is False
    assert ergebnis["only_in_tiger"] == ["26163009999"]
    assert ergebnis["only_in_acs"] == ["26163000200"]


@braucht_pyogrio
def test_compare_with_tiger_ignores_another_vintage(tmp_path):
    write_tiger_run(tmp_path, ["26163000100"], vintage=2020)
    ergebnis = da.compare_with_tiger(
        tmp_path / "data", VINTAGE, STATE, ["26163000100"]
    )
    assert ergebnis["compared"] is False


# --------------------------------------------------------------------------
# Veroeffentlichen eines Laufs
# --------------------------------------------------------------------------


def test_write_run_publishes_both_layers(tmp_path):
    run = write_default_run(tmp_path)
    assert (run.raw / da.RESPONSE_FILE).exists()
    assert (run.bronze / da.PARQUET_FILE).exists()
    assert run.raw.parent == da.run_parent(
        tmp_path / "data", da.RAW_LAYER, VINTAGE, STATE
    )


def test_write_run_raw_holds_the_untouched_response(tmp_path):
    answer = make_answer()
    run = write_default_run(tmp_path, answer=answer)
    assert gzip.decompress((run.raw / da.RESPONSE_FILE).read_bytes()) == answer.body


def test_write_run_bronze_matches_the_pinned_schema(tmp_path):
    run = write_default_run(tmp_path)
    table = pq.ParquetFile(run.bronze / da.PARQUET_FILE).read()
    assert table.schema == da.SCHEMA
    assert table.column("GEOID").to_pylist() == ["26163000100", "26163000200"]


def test_write_run_manifest_documents_the_variables(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path).bronze)
    assert manifest["variables"]["B01003_001E"].startswith("Einwohner")
    assert manifest["missing_value_code"] == "-666666666"
    assert "GEOID" in manifest["derived_columns"]


def test_write_run_manifest_keeps_the_key_out(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path).bronze)
    assert "key=" not in manifest["query"]["url_without_key"]


def test_write_run_manifest_records_the_completeness(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path).bronze)
    assert manifest["completeness"]["unique_tracts"] == 2
    assert manifest["completeness"]["tiger_cross_check"]["compared"] is False


def test_write_run_rejects_duplicate_tracts_without_publishing(tmp_path):
    rows = [
        ["Tract", "1", "2", "3", "26", "163", "000100"],
        ["Tract", "1", "2", "3", "26", "163", "000100"],
    ]
    with pytest.raises(da.IngestionError, match="doppelte GEOIDs"):
        write_default_run(tmp_path, answer=make_answer(body=payload(rows=rows)))
    assert list((tmp_path / "data").rglob("run_*")) == []
    assert list((tmp_path / "data").rglob(".*.part")) == []


def test_write_run_never_overwrites_an_existing_run(tmp_path):
    write_default_run(tmp_path)
    with pytest.raises(OSError):
        write_default_run(tmp_path)


# --------------------------------------------------------------------------
# Vintage-Frage, Schluessel und Argumente
# --------------------------------------------------------------------------


def test_completed_runs_finds_a_published_run(tmp_path):
    run = write_default_run(tmp_path)
    assert da.completed_runs(tmp_path / "data", VINTAGE, STATE) == [run.bronze]


def test_ingest_state_skips_a_vintage_that_is_already_loaded(tmp_path):
    write_default_run(tmp_path)
    session = FakeSession(payload())
    run = da.ingest_state(
        session, tmp_path / "data", STARTED, VINTAGE, STATE, "geheim", force=False
    )
    assert run is None
    assert session.calls == []


def test_ingest_state_force_writes_a_second_run(tmp_path):
    write_default_run(tmp_path)
    session = FakeSession(payload())
    later = STARTED + timedelta(days=1)
    run = da.ingest_state(
        session, tmp_path / "data", later, VINTAGE, STATE, "geheim", force=True
    )
    assert run is not None
    assert len(da.completed_runs(tmp_path / "data", VINTAGE, STATE)) == 2


def test_census_key_reports_a_missing_key(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(da.KEY_VARIABLE, raising=False)
    monkeypatch.setattr(da, "find_dotenv", lambda **kwargs: "")
    with pytest.raises(da.IngestionError, match="CENSUS_API_KEY fehlt"):
        da.census_key()


def test_census_key_reads_the_environment(monkeypatch):
    monkeypatch.setenv(da.KEY_VARIABLE, "geheim")
    monkeypatch.setattr(da, "find_dotenv", lambda **kwargs: "")
    assert da.census_key() == "geheim"


def test_arguments_rejects_a_vintage_before_the_first_one(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--vintage", "2000"])
    with pytest.raises(SystemExit):
        da.arguments()


def test_arguments_defaults_to_every_known_state(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog"])
    assert da.arguments().state == sorted(da.STATES)


def test_schema_covers_every_requested_variable():
    for code in da.VARIABLES:
        assert code in da.SCHEMA.names
