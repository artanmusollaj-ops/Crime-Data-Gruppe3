"""Tests for the Chicago bronze ingestion script."""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest
import requests

import download_chicago as dc
from storage.quellen import QuellenFehler, SocrataQuelle, lade


STARTED = datetime(2026, 9, 4, 4, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run_20260904T040000000000Z"
INGEST_DATE = "2026-09-04"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def write_manifest(
    data_root: Path,
    ingest_date: str,
    run_id: str,
    layer: str = dc.BRONZE_LAYER,
    **overrides,
) -> Path:
    manifest = {
        "status": "complete",
        "event_year": 2024,
        "max_records": None,
        "watermark": {"maximum_seen": "2024-05-01T00:00:00.000"},
    }
    manifest.update(overrides)
    directory = dc.run_parent(data_root, layer, ingest_date) / run_id
    directory.mkdir(parents=True)
    path = directory / "manifest.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def make_partial(
    data_root: Path,
    ingest_date: str,
    name: str,
    age_hours: float,
    layer: str = dc.BRONZE_LAYER,
) -> Path:
    """Create a .part work directory with a backdated modification time."""
    path = dc.run_parent(data_root, layer, ingest_date) / name
    path.mkdir(parents=True)
    (path / dc.PARQUET_FILE).write_bytes(b"incomplete")
    stamp = (STARTED - timedelta(hours=age_hours)).timestamp()
    os.utime(path, (stamp, stamp))
    return path


class FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload, raise_error=None, json_error=None, body=None):
        self._payload = payload
        self._raise_error = raise_error
        self._json_error = json_error
        self.content = (
            body if body is not None else json.dumps(payload).encode("utf-8")
        )

    def raise_for_status(self):
        if self._raise_error is not None:
            raise self._raise_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload


SCHEMA_PAYLOAD = {
    "columns": [
        {"fieldName": "id", "dataTypeName": "number", "name": "ID"},
        {"fieldName": "arrest", "dataTypeName": "checkbox", "name": "Arrest"},
        {"fieldName": ":@computed_region_x", "dataTypeName": "number", "name": "R"},
    ]
}


class FakeSession:
    """Replays canned responses and records every request.

    Eine Abfrage wird an ihrer Form erkannt: Metadaten-URL, count-Abfrage,
    reine id-Abfrage oder Datenseite.
    """

    def __init__(self, pages=(), id_pages=(), count=None, metadata=None):
        self.pages = list(pages)
        self.id_pages = list(id_pages)
        self.count = count
        self.metadata = metadata
        self.calls: list[dict] = []
        self.headers: dict[str, str] = {}
        self.tokens: list[str | None] = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.closed = True
        return False

    def get(self, url, params=None, timeout=None):
        call = {"url": url, "params": params, "timeout": timeout}
        self.calls.append(call)
        if url == dc.METADATA_URL:
            return self.metadata
        if self.is_count(call):
            if isinstance(self.count, list):
                return self.count.pop(0) if len(self.count) > 1 else self.count[0]
            return self.count
        if self.is_ids(call):
            return self.id_pages.pop(0)
        return self.pages.pop(0)

    @staticmethod
    def select_of(call: dict) -> str:
        return str((call["params"] or {}).get("$select", ""))

    @classmethod
    def is_count(cls, call: dict) -> bool:
        return cls.select_of(call).startswith("count(")

    @classmethod
    def is_ids(cls, call: dict) -> bool:
        return cls.select_of(call) == dc.ID_FIELD

    def _of_kind(self, kind) -> list[dict]:
        return [
            call
            for call in self.calls
            if call["url"] != dc.METADATA_URL and kind(call)
        ]

    @property
    def page_calls(self) -> list[dict]:
        return self._of_kind(lambda c: not self.is_count(c) and not self.is_ids(c))

    @property
    def count_calls(self) -> list[dict]:
        return self._of_kind(self.is_count)

    @property
    def id_calls(self) -> list[dict]:
        return self._of_kind(self.is_ids)

    @property
    def metadata_calls(self) -> list[dict]:
        return [call for call in self.calls if call["url"] == dc.METADATA_URL]


def count_response(value) -> FakeResponse:
    return FakeResponse([{dc.COUNT_ALIAS: str(value)}])


def id_response(records) -> FakeResponse:
    return FakeResponse([{dc.ID_FIELD: row[dc.ID_FIELD]} for row in records])


@pytest.fixture
def fake_session(monkeypatch):
    """Ersetzt build_session; Seiten, id-Liste und Zaehlung kommen vom Test.

    Ohne eigene Angabe werden id-Liste und Zaehlung aus ``pages`` abgeleitet,
    sodass ein Lauf per Vorgabe konsistent ist.
    """

    def install(pages=(), count="auto", ids="auto", metadata="auto", **response_kwargs):
        alle = [row for page in pages for row in page]

        if count == "auto":
            count_value = count_response(len(alle))
        elif isinstance(count, (FakeResponse, list, type(None))):
            count_value = count
        else:
            count_value = count_response(count)

        if ids == "auto":
            id_pages = [id_response(alle)]
        elif ids is None:
            id_pages = []
        else:
            id_pages = [page if isinstance(page, FakeResponse) else id_response(page)
                        for page in ids]

        session = FakeSession(
            pages=[FakeResponse(page, **response_kwargs) for page in pages],
            id_pages=id_pages,
            count=count_value,
            metadata=FakeResponse(SCHEMA_PAYLOAD) if metadata == "auto" else metadata,
        )

        def build(token):
            session.tokens.append(token)
            if token:
                session.headers["X-App-Token"] = token
            return session

        monkeypatch.setattr(dc, "build_session", build)
        return session

    return install


# --------------------------------------------------------------------------
# arguments
# --------------------------------------------------------------------------


def test_arguments_defaults(monkeypatch):
    monkeypatch.setattr("sys.argv", ["download_chicago.py"])
    args = dc.arguments()
    assert args.year == dc.DEFAULT_YEAR
    # Seit der Storage-Abstraktion entscheidet die Ablage (LOCAL_DATA_ROOT,
    # Vorgabe data) - die Kommandozeile laesst die Wurzel offen.
    assert args.data_root is None
    from storage import for_root
    assert for_root(args.data_root).local_root == Path("data")
    assert args.max_records is None
    assert args.full is False
    assert args.no_token is False


def test_arguments_parses_all_options(monkeypatch):
    monkeypatch.setattr(
        "sys.argv",
        [
            "download_chicago.py",
            "--year",
            "2001",
            "--data-root",
            "/tmp/data-test",
            "--max-records",
            "5",
            "--full",
            "--no-token",
        ],
    )
    args = dc.arguments()
    assert args.year == 2001
    assert args.data_root == Path("/tmp/data-test")
    assert args.max_records == 5
    assert args.full is True
    assert args.no_token is True


@pytest.mark.parametrize(
    "argv",
    [
        ["download_chicago.py", "--year", "2000"],
        ["download_chicago.py", "--max-records", "0"],
        ["download_chicago.py", "--max-records", "-1"],
    ],
)
def test_arguments_rejects_out_of_range_values(monkeypatch, argv):
    monkeypatch.setattr("sys.argv", argv)
    with pytest.raises(SystemExit) as excinfo:
        dc.arguments()
    assert excinfo.value.code == 2


# --------------------------------------------------------------------------
# app_token
# --------------------------------------------------------------------------


def test_app_token_disabled_never_touches_dotenv(monkeypatch):
    monkeypatch.setattr(
        dc, "find_dotenv", lambda **kwargs: pytest.fail("dotenv must not be read")
    )
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "secret")
    assert dc.app_token(True) is None


def test_app_token_reads_environment(monkeypatch):
    loaded: list[str] = []
    monkeypatch.setattr(dc, "find_dotenv", lambda **kwargs: "/somewhere/.env")
    monkeypatch.setattr(dc, "load_dotenv", lambda path: loaded.append(path))
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "secret")
    assert dc.app_token(False) == "secret"
    assert loaded == ["/somewhere/.env"]


def test_app_token_skips_load_without_dotenv_file(monkeypatch):
    monkeypatch.setattr(dc, "find_dotenv", lambda **kwargs: "")
    monkeypatch.setattr(dc, "load_dotenv", lambda path: pytest.fail("nothing to load"))
    monkeypatch.setenv("SOCRATA_APP_TOKEN", "secret")
    assert dc.app_token(False) == "secret"


@pytest.mark.parametrize("value", ["", None])
def test_app_token_missing_or_empty_is_none(monkeypatch, value):
    monkeypatch.setattr(dc, "find_dotenv", lambda **kwargs: "")
    if value is None:
        monkeypatch.delenv("SOCRATA_APP_TOKEN", raising=False)
    else:
        monkeypatch.setenv("SOCRATA_APP_TOKEN", value)
    assert dc.app_token(False) is None


# --------------------------------------------------------------------------
# run_parent / discard_stale_partials
# --------------------------------------------------------------------------


def test_run_parent_partitions_by_layer_city_and_ingest_date(tmp_path):
    assert dc.run_parent(tmp_path, dc.BRONZE_LAYER, INGEST_DATE) == (
        tmp_path / "bronze" / "city=chicago" / f"ingest_date={INGEST_DATE}"
    )


def test_discard_stale_partials_removes_abandoned_work_directories(tmp_path, caplog):
    caplog.set_level(logging.WARNING)
    stale = make_partial(tmp_path, "2026-09-01", f".{RUN_ID}.part", age_hours=48)

    assert dc.discard_stale_partials(tmp_path, STARTED) == [stale]
    assert not stale.exists()
    assert "Discarded stale partial run" in caplog.text


def test_discard_stale_partials_keeps_a_running_job(tmp_path):
    fresh = make_partial(tmp_path, INGEST_DATE, f".{RUN_ID}.part", age_hours=0.5)
    assert dc.discard_stale_partials(tmp_path, STARTED) == []
    assert fresh.exists()


def test_discard_stale_partials_keeps_published_runs(tmp_path):
    path = write_manifest(tmp_path, "2026-09-01", "run_a")
    stamp = (STARTED - timedelta(days=30)).timestamp()
    os.utime(path.parent, (stamp, stamp))

    assert dc.discard_stale_partials(tmp_path, STARTED) == []
    assert path.exists()


def test_discard_stale_partials_on_a_missing_root(tmp_path):
    assert dc.discard_stale_partials(tmp_path / "absent", STARTED) == []


# --------------------------------------------------------------------------
# previous_watermark
# --------------------------------------------------------------------------


def test_previous_watermark_without_runs(tmp_path):
    assert dc.previous_watermark(tmp_path, 2024) is None


def test_previous_watermark_takes_the_greatest_value(tmp_path):
    for day, seen in [
        ("2026-09-01", "2024-05-01T00:00:00.000"),
        ("2026-09-02", "2024-07-31T23:59:59.000"),
        ("2026-09-03", "2024-06-15T12:00:00.000"),
    ]:
        write_manifest(tmp_path, day, f"run_{day}", watermark={"maximum_seen": seen})
    assert dc.previous_watermark(tmp_path, 2024) == "2024-07-31T23:59:59.000"


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "failed"},
        {"event_year": 2023},
        {"max_records": 5},
        {"watermark": {}},
        {"watermark": {"maximum_seen": None}},
    ],
    ids=["incomplete", "other_year", "test_run", "no_watermark", "empty_watermark"],
)
def test_previous_watermark_ignores_unusable_runs(tmp_path, overrides):
    write_manifest(tmp_path, "2026-09-01", "run_a", **overrides)
    assert dc.previous_watermark(tmp_path, 2024) is None


def test_previous_watermark_ignores_other_cities(tmp_path):
    directory = (
        tmp_path / dc.BRONZE_LAYER / "city=zurich" / "ingest_date=2026-09-01" / "run_a"
    )
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "event_year": 2024,
                "max_records": None,
                "watermark": {"maximum_seen": "2024-12-31T00:00:00.000"},
            }
        ),
        encoding="utf-8",
    )
    assert dc.previous_watermark(tmp_path, 2024) is None


def test_previous_watermark_ignores_partial_runs(tmp_path):
    partial = make_partial(tmp_path, "2026-09-01", f".{RUN_ID}.part", age_hours=1)
    (partial / "manifest.json").write_text(
        json.dumps(
            {
                "status": "complete",
                "event_year": 2024,
                "max_records": None,
                "watermark": {"maximum_seen": "2024-12-31T00:00:00.000"},
            }
        ),
        encoding="utf-8",
    )
    assert dc.previous_watermark(tmp_path, 2024) is None


def test_previous_watermark_rejects_broken_manifest(tmp_path):
    path = write_manifest(tmp_path, "2026-09-01", "run_a")
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(dc.IngestionError, match="Invalid manifest"):
        dc.previous_watermark(tmp_path, 2024)


# --------------------------------------------------------------------------
# delta_start
# --------------------------------------------------------------------------


def test_delta_start_without_watermark():
    assert dc.delta_start(None) is None


@pytest.mark.parametrize(
    "watermark, expected",
    [
        ("2024-07-31T23:59:59.000", "2024-07-17T23:59:59.000"),
        ("2024-01-05T00:00:00.000", "2023-12-22T00:00:00.000"),
    ],
)
def test_delta_start_subtracts_the_lookback(watermark, expected):
    assert dc.delta_start(watermark) == expected


@pytest.mark.parametrize(
    "watermark", ["2024-07-31T23:59:59.000Z", "2024-07-31T23:59:59.000+00:00"]
)
def test_delta_start_drops_the_zone_soql_cannot_parse(watermark):
    assert dc.delta_start(watermark) == "2024-07-17T23:59:59.000"


def test_delta_start_uses_the_configured_lookback(monkeypatch):
    monkeypatch.setattr(dc, "LOOKBACK_DAYS", 1)
    assert dc.delta_start("2024-07-31T00:00:00.000") == "2024-07-30T00:00:00.000"


def test_delta_start_rejects_unparsable_watermark():
    with pytest.raises(dc.IngestionError, match="Invalid watermark"):
        dc.delta_start("not-a-timestamp")


# --------------------------------------------------------------------------
# where_clause / query / count_query / query_url
# --------------------------------------------------------------------------


def test_where_clause_limits_the_event_year():
    assert dc.where_clause(2024, None) == (
        "date >= '2024-01-01T00:00:00' AND date < '2025-01-01T00:00:00'"
    )


def test_where_clause_adds_the_delta_filter():
    assert dc.where_clause(2024, "2024-07-17T23:59:59.000").endswith(
        " AND updated_on >= '2024-07-17T23:59:59.000'"
    )


def test_query_asks_for_whole_records():
    """No $select, so a field added by the city is still delivered."""
    params = dc.query(2024, None, 10)
    assert "$select" not in params
    assert params["$where"] == dc.where_clause(2024, None)
    assert params["$order"] == dc.ID_FIELD
    assert params["$limit"] == 10
    assert "$offset" not in params


def test_query_pages_by_keyset_not_offset():
    """Der zuletzt gesehene Schluessel wandert in die WHERE-Bedingung."""
    params = dc.query(2024, None, 10, after_id=13324861)
    assert params["$where"].endswith(" AND id > 13324861")
    assert params["$where"].startswith(dc.where_clause(2024, None))
    assert "$offset" not in params


def test_query_keeps_the_delta_filter_alongside_the_keyset():
    params = dc.query(2024, "2024-07-17T23:59:59.000", 10, after_id=42)
    assert "updated_on >= '2024-07-17T23:59:59.000'" in params["$where"]
    assert " AND id > 42" in params["$where"]


def test_query_can_select_only_ids():
    params = dc.query(2024, None, 50_000, None, dc.ID_FIELD)
    assert params["$select"] == "id"
    assert params["$order"] == dc.ID_FIELD


def test_count_query_matches_the_page_filter():
    params = dc.count_query(2024, "2024-07-17T23:59:59.000")
    assert params["$select"] == f"count(1) AS {dc.COUNT_ALIAS}"
    assert params["$where"] == dc.query(2024, "2024-07-17T23:59:59.000", 1)["$where"]
    assert "$limit" not in params


def test_query_url_is_reproducible_and_token_free():
    url = dc.query_url(2024, None, 5)
    assert url.startswith(dc.API_URL)
    assert "%24limit=5" in url
    assert "%24offset" not in url
    assert "%24select" not in url
    assert "token" not in url.lower()


# --------------------------------------------------------------------------
# build_session / fetch_json / expected_rows
# --------------------------------------------------------------------------


def test_build_session_retries_throttling_and_server_errors():
    with dc.build_session(None) as session:
        retries = session.get_adapter(dc.API_URL).max_retries
    assert retries.total == dc.RETRY_TOTAL
    assert retries.backoff_factor == dc.RETRY_BACKOFF
    assert set(dc.RETRY_STATUS) <= set(retries.status_forcelist)
    assert "GET" in retries.allowed_methods
    assert retries.respect_retry_after_header is True


def test_build_session_sends_the_token_as_a_header():
    with dc.build_session("secret") as session:
        assert session.headers["X-App-Token"] == "secret"


def test_build_session_without_a_token_sends_no_header():
    with dc.build_session(None) as session:
        assert "X-App-Token" not in session.headers


def test_fetch_json_returns_the_payload():
    session = FakeSession([FakeResponse([{"id": "1"}])])
    assert dc.fetch_json(session, {"$limit": 1}) == [{"id": "1"}]
    assert session.calls[0]["url"] == dc.API_URL
    assert session.calls[0]["timeout"] == dc.TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "error",
    [
        requests.HTTPError("429"),
        requests.ConnectionError("boom"),
        requests.Timeout(),
        requests.exceptions.RetryError("too many retries"),
    ],
    ids=["http", "connection", "timeout", "retries_exhausted"],
)
def test_fetch_json_wraps_request_failures(error):
    session = FakeSession([FakeResponse(None, raise_error=error)])
    with pytest.raises(dc.IngestionError, match="API request failed"):
        dc.fetch_json(session, {})


def test_fetch_json_wraps_invalid_json():
    error = requests.JSONDecodeError("Expecting value", "<html>", 0)
    session = FakeSession([FakeResponse(None, json_error=error)])
    with pytest.raises(dc.IngestionError, match="invalid JSON"):
        dc.fetch_json(session, {})


def test_expected_rows_parses_the_count():
    session = FakeSession(count=count_response(259270))
    assert dc.expected_rows(session, 2024, None) == 259270
    assert session.calls[0]["params"]["$select"].startswith("count(1)")


@pytest.mark.parametrize(
    "response",
    [
        FakeResponse([]),
        FakeResponse([{"other": "1"}]),
        FakeResponse([{dc.COUNT_ALIAS: "not-a-number"}]),
        FakeResponse({dc.COUNT_ALIAS: "5"}),
        FakeResponse(None, raise_error=requests.ConnectionError("boom")),
    ],
    ids=["empty", "wrong_key", "not_numeric", "not_a_list", "request_failed"],
)
def test_expected_rows_degrades_to_unverified(response, caplog):
    caplog.set_level(logging.WARNING)
    session = FakeSession(count=response)
    assert dc.expected_rows(session, 2024, None) is None
    assert "completeness not verified" in caplog.text


# --------------------------------------------------------------------------
# download
# --------------------------------------------------------------------------


def test_download_stops_on_a_short_page(fake_session):
    session = fake_session(pages=[[{"id": "1"}, {"id": "2"}]])
    result = dc.download(2024, None, None, None)
    assert result.records == [{"id": "1"}, {"id": "2"}]
    assert result.source_count_before == 2
    assert result.snapshot_size == 2
    assert len(session.page_calls) == 1
    assert session.page_calls[0]["params"]["$limit"] == dc.PAGE_SIZE
    assert session.closed is True


def test_download_pages_by_keyset(monkeypatch, fake_session):
    """Jede Folgeseite fragt ab der letzten gesehenen id, nicht per Offset."""
    monkeypatch.setattr(dc, "PAGE_SIZE", 2)
    session = fake_session(
        pages=[[{"id": "1"}, {"id": "2"}], [{"id": "3"}, {"id": "4"}], [{"id": "5"}]]
    )
    result = dc.download(2024, None, None, None)
    assert [row["id"] for row in result.records] == ["1", "2", "3", "4", "5"]
    wheres = [call["params"]["$where"] for call in session.page_calls]
    assert " AND id > " not in wheres[0]
    assert wheres[1].endswith(" AND id > 2")
    assert wheres[2].endswith(" AND id > 4")
    assert all("$offset" not in call["params"] for call in session.page_calls)


def position(session, call) -> int:
    """Index eines Aufrufs ueber Identitaet; gleiche Aufrufe sind gleich gross."""
    return next(i for i, other in enumerate(session.calls) if other is call)


def test_download_order_of_operations(fake_session):
    """Schema, Zaehlung, id-Liste, Seiten, zweite Zaehlung."""
    session = fake_session(pages=[[{"id": "1"}]])
    dc.download(2024, "2024-07-17T23:59:59.000", None, None)

    assert session.metadata_calls
    assert len(session.count_calls) == 2
    assert len(session.id_calls) == 1
    reihenfolge = [
        position(session, session.count_calls[0]),
        position(session, session.id_calls[0]),
        position(session, session.page_calls[0]),
        position(session, session.count_calls[-1]),
    ]
    assert reihenfolge == sorted(reihenfolge)
    assert session.id_calls[0]["params"]["$where"] == dc.where_clause(
        2024, "2024-07-17T23:59:59.000"
    )


def test_download_rejects_a_count_that_misses_the_snapshot(fake_session):
    fake_session(pages=[[{"id": "1"}, {"id": "2"}]], count=99)
    with pytest.raises(dc.IngestionError, match="Zeilenzahl 99 passt nicht"):
        dc.download(2024, None, None, None)


def test_download_rejects_a_missing_record(fake_session):
    """Die id-Liste ist der Vertrag: fehlt eine Zeile, scheitert der Lauf."""
    fake_session(
        pages=[[{"id": "1"}, {"id": "2"}]],
        ids=[[{"id": "1"}, {"id": "2"}, {"id": "3"}]],
        count=3,
    )
    with pytest.raises(dc.IngestionError, match="1 fehlend"):
        dc.download(2024, None, None, None)


def test_download_rejects_an_unexpected_record(fake_session):
    fake_session(
        pages=[[{"id": "1"}, {"id": "9"}]], ids=[[{"id": "1"}, {"id": "2"}]], count=2
    )
    with pytest.raises(dc.IngestionError, match="1 unerwartet"):
        dc.download(2024, None, None, None)


def test_download_rejects_duplicate_ids_in_the_snapshot(fake_session):
    fake_session(
        pages=[[{"id": "1"}]], ids=[[{"id": "1"}, {"id": "1"}]], count=2
    )
    with pytest.raises(dc.IngestionError, match="doppelte ids"):
        dc.download(2024, None, None, None)


def test_download_records_a_moving_source_without_blocking(fake_session, caplog):
    """Aendert sich die Quelle waehrend des Laufs, wird das nur dokumentiert."""
    caplog.set_level(logging.WARNING)
    fake_session(
        pages=[[{"id": "1"}, {"id": "2"}]],
        count=[count_response(2), count_response(7)],
    )
    result = dc.download(2024, None, None, None)
    assert result.source_count_before == 2
    assert result.source_count_after == 7
    assert len(result.records) == 2
    assert "veraendert" in caplog.text


def test_download_continues_when_the_count_is_unavailable(fake_session):
    """Ohne Zaehlung bleibt der id-Abgleich als Nachweis bestehen."""
    fake_session(pages=[[{"id": "1"}]], count=FakeResponse([]))
    result = dc.download(2024, None, None, None)
    assert result.records == [{"id": "1"}]
    assert result.source_count_before is None
    assert result.snapshot_size == 1


def test_download_snapshot_digest_is_stable(fake_session):
    fake_session(pages=[[{"id": "2"}, {"id": "1"}]])
    first = dc.download(2024, None, None, None)
    fake_session(pages=[[{"id": "1"}, {"id": "2"}]])
    second = dc.download(2024, None, None, None)
    assert first.snapshot_sha256 == second.snapshot_sha256
    assert len(first.snapshot_sha256) == 64


def test_download_honours_max_records(monkeypatch, fake_session):
    monkeypatch.setattr(dc, "PAGE_SIZE", 2)
    session = fake_session(pages=[[{"id": "1"}, {"id": "2"}], [{"id": "3"}]])
    result = dc.download(2024, None, None, 3)
    assert len(result.records) == 3
    assert [call["params"]["$limit"] for call in session.page_calls] == [2, 1]


def test_download_skips_the_gates_for_a_limited_run(fake_session):
    session = fake_session(pages=[[{"id": "1"}]])
    result = dc.download(2024, None, None, 1)
    assert session.count_calls == []
    assert session.id_calls == []
    assert result.snapshot_size is None
    assert result.source_count_before is None


def test_download_reads_the_schema_fingerprint(fake_session):
    session = fake_session(pages=[[{"id": "1"}]])
    result = dc.download(2024, None, None, None)
    assert len(session.metadata_calls) == 1
    assert result.schema_fingerprint is not None
    assert result.schema_fields == {"id": "number", "arrest": "checkbox"}


def test_download_builds_the_session_with_the_token(fake_session):
    session = fake_session(pages=[[]])
    dc.download(2024, None, "secret", None)
    assert session.tokens == ["secret"]
    assert session.headers["X-App-Token"] == "secret"


def test_download_passes_the_delta_filter_through(fake_session):
    session = fake_session(pages=[[]])
    dc.download(2024, "2024-07-17T23:59:59.000", None, None)
    assert "updated_on >= '2024-07-17T23:59:59.000'" in (
        session.page_calls[0]["params"]["$where"]
    )


def test_download_propagates_request_failures(fake_session):
    fake_session(pages=[[]], raise_error=requests.HTTPError("500"))
    with pytest.raises(dc.IngestionError, match="API request failed"):
        dc.download(2024, None, None, None)


def test_download_rejects_a_non_list_payload(fake_session):
    session = fake_session(pages=[[]])
    session.pages = [FakeResponse({"error": True})]
    with pytest.raises(dc.IngestionError, match="not a list"):
        dc.download(2024, None, None, None)


def test_download_logs_progress(fake_session, caplog):
    caplog.set_level(logging.INFO)
    fake_session(pages=[[{"id": "1"}, {"id": "2"}]])
    dc.download(2024, None, None, None)
    assert "Downloaded 2 record(s)" in caplog.text


# --------------------------------------------------------------------------
# schema
# --------------------------------------------------------------------------


def test_schema_mirrors_the_json_types_the_api_sends():
    types = {field.name: field.type for field in dc.SCHEMA}
    assert types["arrest"] == pa.bool_()
    assert types["domestic"] == pa.bool_()
    assert types["location"] == pa.struct(
        [pa.field(key, pa.string()) for key in dc.LOCATION_SUBFIELDS]
    )
    for name in ("id", "date", "updated_on", "latitude", "ward", "fbi_code"):
        assert types[name] == pa.string(), name
    assert types[dc.EXTRA_COLUMN] == pa.string()


def test_schema_columns_are_the_fields_plus_extra():
    assert dc.COLUMNS == dc.FIELDS + (dc.EXTRA_COLUMN,)
    assert len(dc.FIELDS) == 22


# --------------------------------------------------------------------------
# json_text / fits / bronze_row / bronze_table
# --------------------------------------------------------------------------


def test_json_text_is_compact_and_sorted():
    assert dc.json_text({"b": "ü", "a": 1}) == '{"a":1,"b":"ü"}'


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("arrest", True, True),
        ("arrest", False, True),
        ("arrest", "true", False),
        ("arrest", 1, False),
        ("id", "11224444", True),
        ("id", 11224444, False),
        ("id", True, False),
        ("location", {"latitude": "41.8", "longitude": "-87.6"}, True),
        ("location", {"latitude": "41.8", "human_address": "{}"}, True),
        ("location", {"latitude": "41.8", "elevation": "12"}, False),
        ("location", {"latitude": 41.8}, False),
        ("location", "41.8,-87.6", False),
    ],
)
def test_fits_checks_the_pinned_json_type(field, value, expected):
    assert dc.fits(field, value) is expected


def test_bronze_row_keeps_the_json_types():
    row = dc.bronze_row(
        {
            "id": "13324861",
            "arrest": False,
            "domestic": True,
            "location": {"latitude": "41.8", "longitude": "-87.6", "human_address": "{}"},
        }
    )
    assert row["id"] == "13324861"
    assert row["arrest"] is False
    assert row["domestic"] is True
    assert row["location"] == {
        "latitude": "41.8",
        "longitude": "-87.6",
        "human_address": "{}",
    }
    assert row[dc.EXTRA_COLUMN] is None


def test_bronze_row_fills_a_partial_location_struct():
    row = dc.bronze_row({"location": {"latitude": "41.8"}})
    assert row["location"] == {
        "latitude": "41.8",
        "longitude": None,
        "human_address": None,
    }


def test_bronze_row_missing_fields_are_null():
    row = dc.bronze_row({"id": "1"})
    assert row["case_number"] is None
    assert row["arrest"] is None
    assert row["location"] is None


def test_bronze_row_captures_unknown_fields_in_extra():
    """A field the city adds later must land in _extra, never be dropped."""
    row = dc.bronze_row({"id": "1", "victim_age": "34", "new_flag": True})
    assert row[dc.EXTRA_COLUMN] == '{"new_flag":true,"victim_age":"34"}'


SYSTEM_FIELDS = {
    ":@computed_region_awaf_s7ux": "22",
    ":@computed_region_6mkv_f3dw": "14",
    ":@computed_region_vrxf_vc4k": "1",
    ":id": "row-abcd.efgh~ijkl",
    ":updated_at": "2024-12-21T15:40:46.000",
}


def test_bronze_row_drops_socrata_system_fields():
    """Platform bookkeeping is discarded, not stored in _extra."""
    row = dc.bronze_row({"id": "1", **SYSTEM_FIELDS})
    assert row[dc.EXTRA_COLUMN] is None
    assert not any(name.startswith(":") for name in row)


def test_bronze_row_drops_system_fields_but_keeps_new_city_fields():
    row = dc.bronze_row({"id": "1", "victim_age": "34", **SYSTEM_FIELDS})
    assert json.loads(row[dc.EXTRA_COLUMN]) == {"victim_age": "34"}


def test_bronze_table_has_no_system_columns():
    table = dc.bronze_table([{"id": "1", **SYSTEM_FIELDS}])
    assert table.schema == dc.SCHEMA
    assert not any(name.startswith(":") for name in table.schema.names)


def test_bronze_row_captures_a_changed_type_in_extra():
    """If arrest ever stops being a boolean the value is kept, not lost."""
    row = dc.bronze_row({"id": "1", "arrest": "true"})
    assert row["arrest"] is None
    assert row[dc.EXTRA_COLUMN] == '{"arrest":"true"}'


def test_bronze_row_captures_an_unexpected_location_shape_in_extra():
    location = {"latitude": "41.8", "elevation": "12"}
    row = dc.bronze_row({"location": location})
    assert row["location"] is None
    assert json.loads(row[dc.EXTRA_COLUMN]) == {"location": location}


def test_bronze_table_matches_the_pinned_schema():
    table = dc.bronze_table([{"id": "1", "arrest": True}])
    assert table.schema == dc.SCHEMA
    assert table.num_rows == 1


def test_bronze_table_without_records_keeps_the_schema():
    table = dc.bronze_table([])
    assert table.schema == dc.SCHEMA
    assert table.num_rows == 0


def test_bronze_table_schema_is_stable_across_differing_records():
    """Two runs with different fields present must still share one schema."""
    first = dc.bronze_table([{"id": "1"}])
    second = dc.bronze_table([{"id": "2", "arrest": True, "victim_age": "34"}])
    assert first.schema == second.schema == dc.SCHEMA


# --------------------------------------------------------------------------
# file_hash / file_entry
# --------------------------------------------------------------------------


def test_file_hash_matches_hashlib(tmp_path):
    path = tmp_path / dc.PARQUET_FILE
    path.write_bytes(b"chicago")
    assert dc.file_hash(path) == hashlib.sha256(b"chicago").hexdigest()


def test_file_hash_reads_files_larger_than_one_chunk(tmp_path):
    payload = b"x" * (1024 * 1024 * 2 + 17)
    path = tmp_path / "big.bin"
    path.write_bytes(payload)
    assert dc.file_hash(path) == hashlib.sha256(payload).hexdigest()


def test_file_entry_describes_the_file(tmp_path):
    path = tmp_path / dc.PARQUET_FILE
    path.write_bytes(b"chicago")
    assert dc.file_entry(path) == {
        "path": dc.PARQUET_FILE,
        "size_bytes": 7,
        "sha256": hashlib.sha256(b"chicago").hexdigest(),
    }


# --------------------------------------------------------------------------
# write_run
# --------------------------------------------------------------------------


RECORDS = [
    {
        "id": "13324861",
        "case_number": "JH100083",
        "date": "2024-01-01T00:00:00.000",
        "updated_on": "2024-05-01T09:00:00.000",
        "arrest": False,
        "domestic": False,
        "beat": "1533",
        "fbi_code": "04B",
        "latitude": "41.874896437",
        "location": {
            "latitude": "41.874896437",
            "longitude": "-87.751134319",
            "human_address": '{"address": "", "city": ""}',
        },
    },
    {
        "id": "13324862",
        "case_number": "JH100084",
        "date": "2024-01-02T00:00:00.000",
        "updated_on": "2024-06-02T09:00:00.000",
        "arrest": True,
        "domestic": True,
    },
]


def make_download(
    records=RECORDS, verified=True, count_after=None, bodies=None
) -> dc.Download:
    """Baut ein Download-Ergebnis wie nach einem geprueften Lauf.

    ``verified=False`` entspricht einem Lauf mit ``--max-records``: keine
    Zaehlung, keine feste id-Liste.
    """
    if bodies is None:
        bodies = [json.dumps(records).encode("utf-8")]
    if not verified:
        return dc.Download(
            records, bodies, schema_fingerprint="abc123", schema_fields={}
        )
    return dc.Download(
        records,
        bodies,
        source_count_before=len(records),
        source_count_after=len(records) if count_after is None else count_after,
        snapshot_size=len(records),
        snapshot_sha256="f" * 64,
        schema_fingerprint="abc123",
        schema_fields={"id": "number"},
    )


def write_default_run(data_root: Path, **overrides) -> dc.RunPaths:
    kwargs = {
        "year": 2024,
        "mode": "full_snapshot",
        "old_watermark": None,
        "updated_from": None,
        "token_used": False,
        "max_records": None,
    }
    result = overrides.pop("result", None) or make_download()
    started = overrides.pop("started", STARTED)
    kwargs.update(overrides)
    return dc.write_run(data_root, started, result, **kwargs)


def read_manifest(directory) -> dict:
    """Liest ein Manifest; ohne Angabe der Schicht das der Bronze-Schicht."""
    if isinstance(directory, dc.RunPaths):
        directory = directory.bronze
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def read_part(path) -> pa.Table:
    """Liest genau die eine Parquet-Datei, ohne den Dataset-Layer.

    ``pq.read_table`` liest ueber die Dataset-Schicht: sie liest die
    Hive-Verzeichnisse ueber der Datei mit und haengt ``city`` und
    ``ingest_date`` als zusaetzliche Dictionary-Spalten an das Schema an - je
    nach PyArrow-Version. Geprueft wird hier aber, was in der Datei steht,
    also wird sie direkt gelesen.
    """
    return pq.ParquetFile(path).read()


def test_write_run_publishes_both_layers(tmp_path):
    run = write_default_run(tmp_path)
    assert run.raw == dc.run_parent(tmp_path, dc.RAW_LAYER, INGEST_DATE) / RUN_ID
    assert run.bronze == dc.run_parent(tmp_path, dc.BRONZE_LAYER, INGEST_DATE) / RUN_ID
    assert sorted(path.name for path in run.raw.iterdir()) == [
        "manifest.json",
        "page-0001.json.gz",
    ]
    assert sorted(path.name for path in run.bronze.iterdir()) == [
        "manifest.json",
        dc.PARQUET_FILE,
    ]
    assert run.raw.name == run.bronze.name == RUN_ID
    for layer in dc.LAYERS:
        assert list(dc.run_parent(tmp_path, layer, INGEST_DATE).glob(".*.part")) == []


def test_write_run_parquet_keeps_the_original_types(tmp_path):
    run = write_default_run(tmp_path)
    table = read_part(run.bronze / dc.PARQUET_FILE)
    assert table.schema == dc.SCHEMA

    rows = table.to_pylist()
    assert rows[0]["id"] == "13324861"
    assert rows[0]["arrest"] is False
    assert rows[1]["arrest"] is True
    assert rows[0]["domestic"] is False
    assert rows[0]["beat"] == "1533"
    assert rows[0]["fbi_code"] == "04B"
    assert rows[0]["latitude"] == "41.874896437"
    assert rows[0]["location"] == {
        "latitude": "41.874896437",
        "longitude": "-87.751134319",
        "human_address": '{"address": "", "city": ""}',
    }
    assert rows[1]["location"] is None
    assert rows[0][dc.EXTRA_COLUMN] is None


def test_write_run_parquet_is_readable_with_pandas(tmp_path):
    run = write_default_run(tmp_path)
    frame = pd.read_parquet(run.bronze / dc.PARQUET_FILE)
    assert list(frame.columns) == list(dc.COLUMNS)
    # pandas hands back numpy scalars, so compare by value, not identity.
    assert frame.loc[0, "arrest"] == False  # noqa: E712
    assert frame.loc[1, "arrest"] == True  # noqa: E712
    assert frame.loc[0, "location"]["longitude"] == "-87.751134319"


def test_write_run_manifest_describes_the_run(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path))
    assert manifest["status"] == "complete"
    assert manifest["immutable"] is True
    assert manifest["layer"] == "bronze"
    assert manifest["format"] == "parquet (snappy)"
    assert manifest["city"] == "chicago"
    assert manifest["dataset_id"] == dc.DATASET_ID
    assert manifest["event_year"] == 2024
    assert manifest["mode"] == "full_snapshot"
    assert manifest["ingest_date"] == INGEST_DATE
    assert manifest["run_id"] == RUN_ID
    assert manifest["started_at_utc"] == "2026-09-04T04:00:00Z"
    assert manifest["completed_at_utc"].endswith("Z")
    assert manifest["row_count"] == 2
    assert manifest["max_records"] is None
    assert manifest["used_app_token"] is False
    assert manifest["query"]["method"] == "GET"
    assert manifest["query"]["whole_records"] is True
    assert manifest["query"]["dropped_field_prefix"] == ":"


def test_write_run_manifest_records_the_column_types(tmp_path):
    schema = read_manifest(write_default_run(tmp_path))["schema"]
    assert list(schema) == list(dc.COLUMNS)
    assert schema["arrest"] == "bool"
    assert schema["id"] == "string"
    assert schema["location"].startswith("struct<")
    assert schema[dc.EXTRA_COLUMN] == "string"


def test_write_run_manifest_records_the_file_checksum(tmp_path):
    run = write_default_run(tmp_path)
    parquet = run.bronze / dc.PARQUET_FILE
    entry = read_manifest(run.bronze)["files"][0]
    assert entry["path"] == dc.PARQUET_FILE
    assert entry["size_bytes"] == parquet.stat().st_size
    assert entry["sha256"] == dc.file_hash(parquet)


def test_write_run_records_the_completeness_evidence(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path))
    assert manifest["completeness"] == {
        "verified": True,
        "source_count_before": 2,
        "source_count_after": 2,
        "source_changed_during_run": False,
        "snapshot_size": 2,
        "snapshot_sha256": "f" * 64,
        "downloaded_rows": 2,
    }


def test_write_run_flags_a_source_that_moved(tmp_path):
    manifest = read_manifest(
        write_default_run(tmp_path, result=make_download(count_after=5))
    )
    assert manifest["completeness"]["source_changed_during_run"] is True
    assert manifest["completeness"]["verified"] is True


def test_write_run_marks_an_unverified_run(tmp_path):
    manifest = read_manifest(
        write_default_run(tmp_path, result=make_download(verified=False))
    )
    assert manifest["completeness"]["verified"] is False
    assert manifest["completeness"]["snapshot_size"] is None
    assert manifest["completeness"]["downloaded_rows"] == 2


def test_write_run_records_the_source_schema_fingerprint(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path))
    assert manifest["source_schema"] == {
        "fingerprint": "abc123",
        "fields": {"id": "number"},
    }


def test_write_run_watermark_for_a_full_snapshot(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path))
    assert manifest["watermark"] == {
        "field": "updated_on",
        "previous_maximum": None,
        "lookback_days": 0,
        "query_from": None,
        "maximum_seen": "2024-06-02T09:00:00.000",
    }


def test_write_run_watermark_for_a_delta_run(tmp_path):
    manifest = read_manifest(
        write_default_run(
            tmp_path,
            mode="delta",
            old_watermark="2024-05-15T00:00:00.000",
            updated_from="2024-05-01T00:00:00.000",
        )
    )
    assert manifest["mode"] == "delta"
    assert manifest["watermark"]["previous_maximum"] == "2024-05-15T00:00:00.000"
    assert manifest["watermark"]["query_from"] == "2024-05-01T00:00:00.000"
    assert manifest["watermark"]["lookback_days"] == dc.LOOKBACK_DAYS
    assert manifest["watermark"]["maximum_seen"] == "2024-06-02T09:00:00.000"


def test_write_run_keeps_the_old_watermark_when_nothing_is_newer(tmp_path):
    manifest = read_manifest(
        write_default_run(
            tmp_path,
            result=make_download(records=[]),
            mode="delta",
            old_watermark="2024-06-02T09:00:00.000",
            updated_from="2024-05-19T09:00:00.000",
        )
    )
    assert manifest["row_count"] == 0
    assert manifest["watermark"]["maximum_seen"] == "2024-06-02T09:00:00.000"


def test_write_run_without_records_and_without_watermark(tmp_path):
    run = write_default_run(tmp_path, result=make_download(records=[]))
    manifest = read_manifest(run)
    assert manifest["row_count"] == 0
    assert manifest["watermark"]["maximum_seen"] is None
    assert read_part(run.bronze / dc.PARQUET_FILE).schema == dc.SCHEMA


def test_write_run_marks_a_limited_run_as_a_test_run(tmp_path):
    manifest = read_manifest(
        write_default_run(
            tmp_path, max_records=5, result=make_download(verified=False)
        )
    )
    assert manifest["max_records"] == 5
    assert "%24limit=5" in manifest["query"]["url_first_page"]


def test_write_run_first_page_url_uses_the_page_size(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path))
    assert f"%24limit={dc.PAGE_SIZE}" in manifest["query"]["url_first_page"]
    assert "token" not in manifest["query"]["url_first_page"].lower()


def test_write_run_records_a_used_token_without_leaking_it(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path, token_used=True))
    assert manifest["used_app_token"] is True
    assert "secret" not in json.dumps(manifest)


def test_write_run_removes_the_work_directory_on_failure(tmp_path, monkeypatch):
    def boom(records):
        raise ValueError("parquet conversion failed")

    monkeypatch.setattr(dc, "bronze_table", boom)
    with pytest.raises(ValueError, match="parquet conversion failed"):
        write_default_run(tmp_path)

    assert list(dc.run_parent(tmp_path, dc.BRONZE_LAYER, INGEST_DATE).iterdir()) == []


def test_write_run_cleanup_does_not_mask_the_real_error(tmp_path, monkeypatch):
    def boom(records):
        raise ValueError("parquet conversion failed")

    def failing_rmtree(path, ignore_errors=False):
        if not ignore_errors:
            raise OSError("cleanup failed")

    monkeypatch.setattr(dc, "bronze_table", boom)
    monkeypatch.setattr(dc.shutil, "rmtree", failing_rmtree)
    with pytest.raises(ValueError, match="parquet conversion failed"):
        write_default_run(tmp_path)


def test_write_run_cleans_up_after_an_interrupt(tmp_path, monkeypatch):
    def cancelled(records):
        raise KeyboardInterrupt

    monkeypatch.setattr(dc, "bronze_table", cancelled)
    with pytest.raises(KeyboardInterrupt):
        write_default_run(tmp_path)

    assert list(dc.run_parent(tmp_path, dc.BRONZE_LAYER, INGEST_DATE).iterdir()) == []


def test_write_run_never_overwrites_an_existing_run(tmp_path):
    run = write_default_run(tmp_path)
    checksum = dc.file_hash(run.bronze / dc.PARQUET_FILE)

    with pytest.raises(OSError):
        write_default_run(tmp_path)

    assert dc.file_hash(run.bronze / dc.PARQUET_FILE) == checksum
    for layer in dc.LAYERS:
        assert list(dc.run_parent(tmp_path, layer, INGEST_DATE).glob(".*.part")) == []


def test_write_landing_stores_responses_byte_for_byte(tmp_path):
    bodies = [b'[{"id":"1"}]', b'[{"id":"2"}]']
    entries = dc.write_landing(tmp_path, bodies)

    assert [entry["path"] for entry in entries] == [
        "page-0001.json.gz",
        "page-0002.json.gz",
    ]
    for entry, body in zip(entries, bodies):
        path = tmp_path / entry["path"]
        assert gzip.decompress(path.read_bytes()) == body
        assert entry["sha256"] == dc.file_hash(path)


def test_write_landing_compression_is_deterministic(tmp_path):
    """Gleiche Antwort, gleiche Bytes — sonst waere der SHA-256 wertlos."""
    erste, zweite = tmp_path / "a", tmp_path / "b"
    erste.mkdir()
    zweite.mkdir()
    body = [b'[{"id":"1","updated_on":"2024-05-01T09:00:00.000"}]']
    assert (
        dc.write_landing(erste, body)[0]["sha256"]
        == dc.write_landing(zweite, body)[0]["sha256"]
    )


def test_write_landing_without_pages(tmp_path):
    assert dc.write_landing(tmp_path, []) == []


def test_write_run_raw_holds_the_untouched_response(tmp_path):
    """In Raw stehen die JSON-Typen der API, nicht die Bronze-Umsetzung."""
    run = write_default_run(tmp_path)
    gespeichert = json.loads(
        gzip.decompress((run.raw / "page-0001.json.gz").read_bytes())
    )
    assert gespeichert == RECORDS
    assert gespeichert[0]["arrest"] is False
    assert gespeichert[0]["location"]["human_address"].startswith("{")
    # Bronze macht daraus einen bool und ein struct.
    frame = pq.read_table(run.bronze / dc.PARQUET_FILE).to_pylist()
    assert frame[0]["arrest"] is False
    assert frame[0]["location"]["longitude"] == "-87.751134319"


@pytest.mark.parametrize("layer", dc.LAYERS)
def test_write_run_layer_manifest_is_self_contained(tmp_path, layer):
    run = write_default_run(tmp_path)
    manifest = read_manifest(getattr(run, layer))
    assert manifest["layer"] == layer
    assert manifest["format"] == dc.LAYER_FORMAT[layer]
    assert manifest["run_id"] == RUN_ID
    assert manifest["completeness"]["verified"] is True

    verzeichnis = getattr(run, layer)
    namen = sorted(
        path.name for path in verzeichnis.iterdir() if path.name != "manifest.json"
    )
    assert sorted(entry["path"] for entry in manifest["files"]) == namen
    for entry in manifest["files"]:
        assert entry["sha256"] == dc.file_hash(verzeichnis / entry["path"])


def test_write_run_only_bronze_declares_the_parquet_schema(tmp_path):
    run = write_default_run(tmp_path)
    bronze = read_manifest(run.bronze)
    assert bronze["schema"] == {field.name: str(field.type) for field in dc.SCHEMA}
    assert bronze["derived_from"].endswith(RUN_ID)
    assert "schema" not in read_manifest(run.raw)


def test_write_run_removes_both_work_directories_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(
        dc, "bronze_table", lambda records: (_ for _ in ()).throw(ValueError("kaputt"))
    )
    with pytest.raises(ValueError, match="kaputt"):
        write_default_run(tmp_path)

    for layer in dc.LAYERS:
        assert list(dc.run_parent(tmp_path, layer, INGEST_DATE).iterdir()) == []


def test_write_run_keeps_the_evidence_when_bronze_cannot_be_published(tmp_path):
    """Raw erscheint zuerst; scheitert Bronze, rueckt das Wasserzeichen nicht vor."""
    blocker = dc.run_parent(tmp_path, dc.BRONZE_LAYER, INGEST_DATE) / RUN_ID
    blocker.mkdir(parents=True)
    (blocker / "belegt").write_text("x", encoding="utf-8")

    with pytest.raises(OSError):
        write_default_run(tmp_path)

    raw_run = dc.run_parent(tmp_path, dc.RAW_LAYER, INGEST_DATE) / RUN_ID
    assert (raw_run / "page-0001.json.gz").exists()
    assert dc.previous_watermark(tmp_path, 2024) is None


def test_discard_stale_partials_sweeps_both_layers(tmp_path):
    stale = [
        make_partial(tmp_path, "2026-09-01", f".{RUN_ID}.part", 48, layer=layer)
        for layer in dc.LAYERS
    ]
    assert sorted(dc.discard_stale_partials(tmp_path, STARTED)) == sorted(stale)
    assert not any(path.exists() for path in stale)


def test_write_run_output_is_discovered_as_a_watermark(tmp_path):
    write_default_run(tmp_path)
    assert dc.previous_watermark(tmp_path, 2024) == "2024-06-02T09:00:00.000"


def test_write_run_test_run_is_not_used_as_a_watermark(tmp_path):
    write_default_run(tmp_path, max_records=5, result=make_download(verified=False))
    assert dc.previous_watermark(tmp_path, 2024) is None


def test_runs_from_different_days_read_as_one_dataset(tmp_path):
    """The pinned schema must let every run be read together."""
    write_default_run(tmp_path)
    write_default_run(
        tmp_path,
        started=STARTED + timedelta(days=1),
        result=make_download(records=[{"id": "9", "victim_age": "34"}]),
    )
    # manifest.json sits beside each part file, so select the Parquet files.
    parts = sorted(tmp_path.glob(f"{dc.BRONZE_LAYER}/**/{dc.PARQUET_FILE}"))
    assert len(parts) == 2
    for part in parts:
        assert read_part(part).schema == dc.SCHEMA

    dataset = pq.read_table(parts, schema=dc.SCHEMA)
    assert dataset.num_rows == 3
    assert dataset.schema == dc.SCHEMA
    assert dataset.column("id").to_pylist() == ["13324861", "13324862", "9"]
    assert json.loads(dataset.column(dc.EXTRA_COLUMN)[2].as_py()) == {
        "victim_age": "34"
    }


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------


@pytest.fixture
def run_main(monkeypatch, tmp_path, caplog):
    """Run main() with stubbed argument parsing, token lookup and download."""

    def run(*, records=RECORDS, verified=True, token=None, download=None, **cli):
        options = {
            "source": dc.DEFAULT_SOURCE,
            "year": 2024,
            "data_root": tmp_path,
            "max_records": None,
            "full": False,
            "no_token": True,
        }
        options.update(cli)
        calls: list[tuple] = []

        def fake_download(year, updated_from, app_token, max_records):
            calls.append((year, updated_from, app_token, max_records))
            if download is not None:
                return download(year, updated_from, app_token, max_records)
            return make_download(records=records, verified=verified)

        monkeypatch.setattr(dc, "arguments", lambda: dc.argparse.Namespace(**options))
        monkeypatch.setattr(dc, "app_token", lambda disabled: token)
        monkeypatch.setattr(dc, "download", fake_download)
        caplog.set_level(logging.INFO)
        return dc.main(), calls

    return run


def published_runs(data_root: Path, layer: str = dc.BRONZE_LAYER) -> list[Path]:
    return sorted(data_root.glob(f"{layer}/city=chicago/ingest_date=*/run_*"))


def test_main_first_call_is_a_full_snapshot(run_main, tmp_path, caplog):
    code, calls = run_main()
    assert code == 0
    assert calls == [(2024, None, None, None)]

    runs = published_runs(tmp_path)
    assert len(runs) == 1
    assert runs[0].relative_to(tmp_path).parts[0] == "bronze"
    manifest = read_manifest(runs[0])
    assert manifest["mode"] == "full_snapshot"
    assert manifest["row_count"] == 2
    assert manifest["used_app_token"] is False
    assert manifest["completeness"]["verified"] is True
    assert "Starting full_snapshot for Chicago 2024" in caplog.text
    assert "Immutable run completed" in caplog.text


def test_main_second_call_is_a_delta_with_lookback(run_main, tmp_path):
    write_manifest(
        tmp_path,
        "2026-09-03",
        "run_previous",
        watermark={"maximum_seen": "2024-07-31T23:59:59.000"},
    )
    code, calls = run_main()
    assert code == 0
    assert calls == [(2024, "2024-07-17T23:59:59.000", None, None)]

    manifest = read_manifest(published_runs(tmp_path)[-1])
    assert manifest["mode"] == "delta"
    assert manifest["watermark"]["previous_maximum"] == "2024-07-31T23:59:59.000"


def test_main_full_flag_ignores_the_watermark_but_keeps_it(run_main, tmp_path):
    write_manifest(
        tmp_path,
        "2026-09-03",
        "run_previous",
        watermark={"maximum_seen": "2024-07-31T23:59:59.000"},
    )
    code, calls = run_main(full=True)
    assert code == 0
    assert calls == [(2024, None, None, None)]

    manifest = read_manifest(published_runs(tmp_path)[-1])
    assert manifest["mode"] == "full_snapshot"
    assert manifest["watermark"]["previous_maximum"] == "2024-07-31T23:59:59.000"
    assert manifest["watermark"]["lookback_days"] == 0


def test_main_forwards_token_and_max_records(run_main, tmp_path):
    code, calls = run_main(token="secret", max_records=5, verified=False)
    assert code == 0
    assert calls == [(2024, None, "secret", 5)]

    manifest = read_manifest(published_runs(tmp_path)[-1])
    assert manifest["used_app_token"] is True
    assert manifest["max_records"] == 5


def test_main_carries_the_completeness_evidence_into_the_manifest(run_main, tmp_path):
    code, _ = run_main()
    assert code == 0
    completeness = read_manifest(published_runs(tmp_path)[-1])["completeness"]
    assert completeness["verified"] is True
    assert completeness["snapshot_size"] == 2
    assert completeness["downloaded_rows"] == 2


def test_main_marks_a_limited_run_as_unverified(run_main, tmp_path):
    code, _ = run_main(verified=False)
    assert code == 0
    completeness = read_manifest(published_runs(tmp_path)[-1])["completeness"]
    assert completeness["verified"] is False
    assert completeness["snapshot_sha256"] is None


def test_main_sweeps_stale_partials_before_writing(run_main, tmp_path):
    stale = make_partial(tmp_path, "2026-09-01", ".run_old.part", age_hours=48)
    code, _ = run_main()
    assert code == 0
    assert not stale.exists()
    assert len(published_runs(tmp_path)) == 1


def test_main_reports_ingestion_errors_without_publishing(run_main, tmp_path, caplog):
    def failing(*args):
        raise dc.IngestionError("Truncated download: 3 of 99 expected row(s)")

    code, _ = run_main(download=failing)
    assert code == 1
    assert published_runs(tmp_path) == []
    assert "Ingestion failed: Truncated download: 3 of 99" in caplog.text


def test_main_reports_a_broken_manifest(run_main, tmp_path, caplog):
    path = write_manifest(tmp_path, "2026-09-03", "run_previous")
    path.write_text("{not json", encoding="utf-8")

    code, calls = run_main()
    assert code == 1
    assert calls == []
    assert "Invalid manifest" in caplog.text


def test_main_handles_a_cancelled_run(run_main, tmp_path, caplog):
    def cancelled(*args):
        raise KeyboardInterrupt

    code, _ = run_main(download=cancelled)
    assert code == 130
    assert published_runs(tmp_path) == []
    assert "cancelled" in caplog.text


# --------------------------------------------------------------------------
# The source descriptor (config/quellen.toml)
# --------------------------------------------------------------------------

OTHER_SOURCE = SocrataQuelle(
    name="dallas", stadt="dallas", anzeigename="Dallas",
    domain="www.dallasopendata.com", datensatz="qv6i-rri7",
    id_feld="servnumid", tatzeit_feld="date1", aenderungs_feld="upzdate",
    felder=("servnumid", "date1", "upzdate", "nibrs_code", "family"),
    boolesche_felder=("family",),
)


@pytest.fixture
def other_source():
    """Switch the module to another Socrata source and back afterwards."""
    dc.use_source(OTHER_SOURCE)
    try:
        yield OTHER_SOURCE
    finally:
        dc.use_source(lade(dc.DEFAULT_SOURCE))


def test_the_default_source_is_chicago_as_the_code_used_to_pin_it():
    """The literals that were constants here until 8.11.2026.

    The bronze bytes of a run were compared before and after the move into
    config/quellen.toml: identical. This test keeps the inputs that decided it.
    """
    assert dc.SOURCE.name == "chicago" and dc.CITY == "chicago"
    assert dc.API_URL == "https://data.cityofchicago.org/resource/ijzp-q8t2.json"
    assert dc.DATASET_ID == "ijzp-q8t2" and dc.ID_FIELD == "id"
    assert (dc.EVENT_FIELD, dc.WATERMARK_FIELD) == ("date", "updated_on")
    assert str(dc.SCHEMA.field("location").type) == (
        "struct<latitude: string, longitude: string, human_address: string>")
    assert [f.name for f in dc.SCHEMA if str(f.type) == "bool"] == ["arrest", "domestic"]


def test_another_source_changes_every_city_specific_value(other_source, tmp_path):
    assert dc.API_URL == "https://www.dallasopendata.com/resource/qv6i-rri7.json"
    assert dc.METADATA_URL == "https://www.dallasopendata.com/api/views/qv6i-rri7.json"
    assert dc.run_parent(tmp_path, dc.RAW_LAYER, "2026-11-08") == (
        tmp_path / "raw" / "city=dallas" / "ingest_date=2026-11-08")
    params = dc.query(2024, "2024-05-01T00:00:00.000", 10, 7)
    assert params["$where"] == (
        "date1 >= '2024-01-01T00:00:00' AND date1 < '2025-01-01T00:00:00' "
        "AND upzdate >= '2024-05-01T00:00:00.000' AND servnumid > 7")
    assert params["$order"] == "servnumid"
    assert dc.COLUMNS == other_source.felder + (dc.EXTRA_COLUMN,)
    assert dc.LOCATION_FIELD is None


def test_another_source_writes_its_own_rows_and_watermark(other_source, tmp_path):
    records = [
        {"servnumid": "1", "date1": "2024-01-01T00:00:00.000",
         "upzdate": "2024-02-01T00:00:00.000", "family": True, "zone": "N"},
        {"servnumid": "2", "date1": "2024-01-02T00:00:00.000",
         "upzdate": "2024-03-01T00:00:00.000", "family": "yes"},
    ]
    run = dc.write_run(
        tmp_path, datetime(2026, 11, 8, tzinfo=timezone.utc),
        dc.Download(records, [b"[]"]), year=2024, mode="full_snapshot",
        old_watermark=None, updated_from=None, token_used=False, max_records=None,
    )
    manifest = json.loads((run.bronze / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["city"] == "dallas" and manifest["dataset_id"] == "qv6i-rri7"
    assert manifest["watermark"]["field"] == "upzdate"
    assert manifest["watermark"]["maximum_seen"] == "2024-03-01T00:00:00.000"
    rows = pq.read_table(run.bronze / dc.PARQUET_FILE).to_pylist()
    assert [row["family"] for row in rows] == [True, None]
    assert json.loads(rows[0][dc.EXTRA_COLUMN]) == {"zone": "N"}
    assert json.loads(rows[1][dc.EXTRA_COLUMN]) == {"family": "yes"}


def test_the_source_option_picks_a_socrata_entry(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["download_chicago", "--source", "dallas"])
    assert dc.arguments().source == "dallas"
    monkeypatch.setattr(sys, "argv", ["download_chicago"])
    assert dc.arguments().source == "chicago"


def test_an_unknown_source_fails_before_anything_is_written(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["download_chicago", "--source", "atlantis",
                                      "--data-root", str(tmp_path)])
    with pytest.raises(QuellenFehler, match="Keine Quelle 'atlantis'"):
        dc.main()
    assert dc.SOURCE.name == "chicago"
    # Lokal mit Absicht: geprueft wird, dass kein Verzeichnis entstanden ist.
    assert not any(tmp_path.iterdir())
