"""Tests fuer die NOAA-GHCN-Daily-Ingestion.

Sie laufen ohne Netzzugriff. Die CSV, an der die Ableitung nach Bronze haengt,
wird zur Laufzeit erzeugt - inklusive der rechtsbuendig aufgefuellten Werte und
einer Spalte, die nicht im gepinnten Schema steht, damit der Weg nach ``_extra``
tatsaechlich geprueft wird.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import download_noaa as dn


STATION = "USW00094847"
STARTED = datetime(2026, 9, 7, 4, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run_20260907T040000000000Z"
INGEST_DATE = "2026-09-07"


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------

# SNWD und TAVG stehen bewusst drin: die Quelle liefert sie, das gepinnte
# Schema kennt sie nicht, sie muessen also in _extra landen.
HEADER = (
    "STATION,DATE,LATITUDE,LONGITUDE,ELEVATION,NAME,"
    "PRCP,PRCP_ATTRIBUTES,SNOW,SNOW_ATTRIBUTES,SNWD,SNWD_ATTRIBUTES,"
    "TMAX,TMAX_ATTRIBUTES,TMIN,TMIN_ATTRIBUTES,TAVG,TAVG_ATTRIBUTES"
)


def csv_row(
    date: str,
    *,
    station: str = STATION,
    prcp: str = "    0",
    tmax: str = "  214",
    tmin: str = "  103",
    snwd: str = "    0",
    tavg: str = "  158",
) -> str:
    """Eine Datenzeile, wie GHCN-Daily sie schreibt."""
    return (
        f'"{station}","{date}","42.23130","-83.33073","201.5",'
        f'"DETROIT METRO AIRPORT, MI US",'
        f'"{prcp}","H,,S","    0","H,,S","{snwd}","H,,S",'
        f'"{tmax}","H,,S","{tmin}","H,,S","{tavg}","H,,S"'
    )


def make_csv(rows: list[str] | None = None, header: str = HEADER) -> bytes:
    """Baut eine vollstaendige Stations-CSV."""
    if rows is None:
        rows = [csv_row("2026-09-05"), csv_row("2026-09-06")]
    return ("\n".join([header, *rows]) + "\n").encode("utf-8")


class FakeResponse:
    def __init__(self, payload: bytes, headers: dict | None = None):
        self.content = payload
        self.headers = headers if headers is not None else {
            "Content-Length": str(len(payload)),
            "Last-Modified": "Sun, 06 Sep 2026 13:25:33 GMT",
        }

    def raise_for_status(self) -> None:
        return None


class FakeSession:
    """Liefert je Aufruf eine vorbereitete Antwort und merkt sich die URLs."""

    def __init__(self, payload: bytes, headers: dict | None = None):
        self.payload = payload
        self.headers = headers
        self.urls: list[str] = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        return FakeResponse(self.payload, self.headers)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def read_manifest(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


def write_default_run(tmp_path: Path, **overrides) -> dn.RunPaths:
    payload = overrides.pop("payload", None)
    if payload is None:
        payload = make_csv()
    delivery = dn.Delivery(
        payload=payload,
        url=dn.station_url(STATION),
        content_length=len(payload),
        last_modified="Sun, 06 Sep 2026 13:25:33 GMT",
    )
    return dn.write_run(
        overrides.pop("data_root", tmp_path / "data"),
        overrides.pop("started", STARTED),
        delivery,
        station=overrides.pop("station", STATION),
    )


# --------------------------------------------------------------------------
# Adressen und Ablage
# --------------------------------------------------------------------------


def test_station_url_follows_the_published_pattern():
    assert dn.station_url("USW00094846") == (
        "https://www.ncei.noaa.gov/data/"
        "global-historical-climatology-network-daily/access/USW00094846.csv"
    )


def test_run_parent_partitions_by_station_not_by_state():
    """Wetter ist kein Tract-Merkmal, der Schluessel heisst station=."""
    parent = dn.run_parent(Path("data"), dn.BRONZE_LAYER, STATION)
    assert parent == (
        Path("data") / "bronze" / "dataset=noaa_ghcnd" / f"station={STATION}"
    )
    assert "state=" not in str(parent)


def test_default_stations_are_one_airport_per_city():
    from weather_pipeline import DEFAULT_STATIONS, STATIONS

    staedte = [STATIONS[s]["city"] for s in DEFAULT_STATIONS]
    assert sorted(staedte) == ["chicago", "detroit"]
    assert len(staedte) == len(set(staedte)), "je Stadt genau eine Station"


# --------------------------------------------------------------------------
# Vollstaendigkeit der Auslieferung
# --------------------------------------------------------------------------


def test_short_delivery_is_rejected():
    """Content-Length gegen die empfangenen Bytes ist der erste Nachweis."""
    payload = make_csv()
    session = FakeSession(payload, headers={"Content-Length": str(len(payload) + 99)})
    with pytest.raises(dn.IngestionError, match="Unvollstaendige Auslieferung"):
        dn.fetch_delivery(session, STATION)


def test_missing_content_length_does_not_block_the_run():
    """Fehlt die Angabe, wird nichts behauptet - der Lauf laeuft weiter."""
    payload = make_csv()
    session = FakeSession(payload, headers={})
    delivery = dn.fetch_delivery(session, STATION)
    assert delivery.content_length is None
    assert delivery.payload == payload


def test_empty_delivery_is_rejected():
    session = FakeSession(b"", headers={})
    with pytest.raises(dn.IngestionError, match="Leere Auslieferung"):
        dn.fetch_delivery(session, STATION)


# --------------------------------------------------------------------------
# Lesen und pruefen der Reihe
# --------------------------------------------------------------------------


def test_series_reports_its_own_date_range():
    series = dn.read_series(
        make_csv([csv_row("2026-09-06"), csv_row("1946-10-09")]), STATION
    )
    assert series.first_date == "1946-10-09"
    assert series.last_date == "2026-09-06"
    assert len(series.rows) == 2


def test_foreign_station_in_the_file_is_rejected():
    """Eine falsch einsortierte Partition faellt sonst erst in Silver auf."""
    payload = make_csv([csv_row("2026-09-05"), csv_row("2026-09-06", station="USW00094846")])
    with pytest.raises(dn.IngestionError, match="fremde Stationen"):
        dn.read_series(payload, STATION)


def test_missing_required_column_is_rejected():
    header = HEADER.replace("DATE,", "")
    payload = make_csv([csv_row("2026-09-05")], header=header)
    with pytest.raises(dn.IngestionError, match="Pflichtspalte DATE"):
        dn.read_series(payload, STATION)


def test_file_without_data_rows_is_rejected():
    with pytest.raises(dn.IngestionError, match="ohne Datenzeilen"):
        dn.read_series((HEADER + "\n").encode("utf-8"), STATION)


def test_header_fingerprint_changes_when_the_source_adds_a_column():
    """Schema-Drift muss sichtbar sein, obwohl _extra sie auffaengt."""
    vorher, _ = dn.source_schema(dn.read_series(make_csv(), STATION).header)
    nachher, felder = dn.source_schema(
        dn.read_series(make_csv(header=HEADER + ",WT01,WT01_ATTRIBUTES"), STATION).header
    )
    assert vorher != nachher
    assert "WT01" in felder


# --------------------------------------------------------------------------
# Ableitung nach Bronze
# --------------------------------------------------------------------------


def test_bronze_pins_the_schema():
    table = dn.bronze_table(dn.read_series(make_csv(), STATION))
    assert table.schema.names == list(dn.COLUMNS)
    assert all(str(field.type) == "string" for field in table.schema)


def test_unpinned_columns_land_in_extra_instead_of_being_dropped():
    """SNWD und TAVG liefert die Quelle, das Schema kennt sie nicht."""
    table = dn.bronze_table(dn.read_series(make_csv(), STATION))
    extra = json.loads(table.column(dn.EXTRA_COLUMN)[0].as_py())
    assert extra["SNWD"] == "    0"
    assert extra["TAVG"] == "  158"
    assert "TMAX" not in extra, "gepinnte Spalten gehoeren nicht nach _extra"


def test_values_keep_the_form_the_source_used():
    """Aufgefuellter Text bleibt aufgefuellt; geparst wird in Silver."""
    table = dn.bronze_table(dn.read_series(make_csv(), STATION))
    assert table.column("TMAX")[0].as_py() == "  214"
    assert table.column("TMAX_ATTRIBUTES")[0].as_py() == "H,,S"


def test_empty_field_becomes_null_not_empty_text():
    payload = make_csv([csv_row("2026-09-05", prcp="")])
    table = dn.bronze_table(dn.read_series(payload, STATION))
    assert table.column("PRCP")[0].as_py() is None


def test_extra_is_null_when_the_source_carries_nothing_extra():
    schmal = ",".join(
        name for name in HEADER.split(",") if not name.startswith(("SNWD", "TAVG"))
    )
    row = (
        f'"{STATION}","2026-09-05","42.23130","-83.33073","201.5",'
        f'"DETROIT METRO AIRPORT, MI US",'
        f'"    0","H,,S","    0","H,,S","  214","H,,S","  103","H,,S"'
    )
    table = dn.bronze_table(dn.read_series(make_csv([row], header=schmal), STATION))
    assert table.column(dn.EXTRA_COLUMN)[0].as_py() is None


# --------------------------------------------------------------------------
# Der veroeffentlichte Lauf
# --------------------------------------------------------------------------


def test_run_writes_both_layers_under_one_run_id(tmp_path):
    run = write_default_run(tmp_path)
    assert run.raw.name == RUN_ID
    assert run.bronze.name == RUN_ID
    assert (run.raw / f"{STATION}.csv").exists()
    assert (run.bronze / dn.PARQUET_FILE).exists()
    assert not list((tmp_path / "data").rglob(".*.part"))


def test_raw_holds_the_delivery_byte_for_byte(tmp_path):
    payload = make_csv()
    run = write_default_run(tmp_path, payload=payload)
    assert (run.raw / f"{STATION}.csv").read_bytes() == payload


def test_manifest_proves_completeness(tmp_path):
    payload = make_csv()
    run = write_default_run(tmp_path, payload=payload)
    manifest = read_manifest(run.bronze)

    assert manifest["status"] == "complete"
    assert manifest["immutable"] is True
    assert manifest["station_id"] == STATION
    assert manifest["city"] == "detroit"
    assert manifest["ingest_date"] == INGEST_DATE
    assert manifest["row_count"] == 2

    vollstaendig = manifest["completeness"]
    assert vollstaendig["verified"] is True
    assert vollstaendig["content_length"] == len(payload)
    assert vollstaendig["downloaded_bytes"] == len(payload)
    assert vollstaendig["csv_rows_read"] == vollstaendig["rows_written"] == 2
    assert vollstaendig["station_column_consistent"] is True


def test_manifest_carries_the_observation_range_for_silver(tmp_path):
    """Silver ordnet mehrere Schnappschuesse, ohne Parquet zu lesen."""
    run = write_default_run(tmp_path)
    manifest = read_manifest(run.bronze)
    assert manifest["first_observation_date"] == "2026-09-05"
    assert manifest["last_observation_date"] == "2026-09-06"


def test_manifest_names_the_join_axis(tmp_path):
    """Wetter wird ueber Datum und Stadt verbunden, nicht raeumlich."""
    run = write_default_run(tmp_path)
    assert read_manifest(run.bronze)["join_keys"] == ["city", "DATE"]


def test_bronze_manifest_points_back_at_raw(tmp_path):
    run = write_default_run(tmp_path)
    roh = read_manifest(run.raw)
    bronze = read_manifest(run.bronze)
    assert roh["layer"] == "raw"
    assert bronze["layer"] == "bronze"
    assert bronze["derived_from"].endswith(RUN_ID)
    assert bronze["schema"]["TMAX"] == "string"
    assert roh["run_id"] == bronze["run_id"]


def test_manifest_never_carries_a_token(tmp_path):
    run = write_default_run(tmp_path)
    text = (run.bronze / "manifest.json").read_text(encoding="utf-8").lower()
    for verboten in ("token", "api_key", "apikey", "password"):
        assert verboten not in text


def test_parquet_round_trips(tmp_path):
    run = write_default_run(tmp_path)
    table = pq.read_table(run.bronze / dn.PARQUET_FILE)
    assert table.num_rows == 2
    assert table.column("STATION").to_pylist() == [STATION, STATION]
    assert table.column("DATE").to_pylist() == ["2026-09-05", "2026-09-06"]


def test_failed_run_publishes_nothing(tmp_path):
    """Ein Abbruch darf keinen halben Lauf hinterlassen."""
    data_root = tmp_path / "data"
    kaputt = make_csv([csv_row("2026-09-05", station="USW00094846")])
    delivery = dn.Delivery(
        payload=kaputt,
        url=dn.station_url(STATION),
        content_length=len(kaputt),
        last_modified=None,
    )
    with pytest.raises(dn.IngestionError):
        dn.write_run(data_root, STARTED, delivery, station=STATION)

    assert not list(data_root.rglob("run_*"))
    assert not list(data_root.rglob(".*.part"))


# --------------------------------------------------------------------------
# Wann gibt es etwas zu tun?
# --------------------------------------------------------------------------


def test_second_run_on_the_same_day_is_skipped(tmp_path):
    """Die Quelle haengt taeglich eine Zeile an - zweimal laden bringt nichts."""
    data_root = tmp_path / "data"
    payload = make_csv()
    session = FakeSession(payload)

    erst = dn.ingest_station(session, data_root, STARTED, STATION, force=False)
    assert erst is not None

    spaeter = STARTED.replace(hour=18)
    zweit = dn.ingest_station(session, data_root, spaeter, STATION, force=False)
    assert zweit is None
    assert len(session.urls) == 1, "der zweite Lauf darf nicht laden"


def test_force_writes_another_run_on_the_same_day(tmp_path):
    data_root = tmp_path / "data"
    session = FakeSession(make_csv())
    dn.ingest_station(session, data_root, STARTED, STATION, force=False)
    erzwungen = dn.ingest_station(
        session, data_root, STARTED.replace(hour=18), STATION, force=True
    )
    assert erzwungen is not None
    assert len(dn.completed_runs(data_root, STATION)) == 2


def test_a_new_day_loads_again(tmp_path):
    data_root = tmp_path / "data"
    session = FakeSession(make_csv())
    dn.ingest_station(session, data_root, STARTED, STATION, force=False)
    morgen = STARTED + timedelta(days=1)
    assert dn.ingest_station(session, data_root, morgen, STATION, force=False)


def test_incomplete_run_does_not_count_as_done(tmp_path):
    """Nur ein Manifest mit status=complete beantwortet die Frage."""
    data_root = tmp_path / "data"
    run = write_default_run(tmp_path)
    pfad = run.bronze / "manifest.json"
    manifest = json.loads(pfad.read_text(encoding="utf-8"))
    manifest["status"] = "aborted"
    pfad.write_text(json.dumps(manifest), encoding="utf-8")
    assert dn.completed_runs(data_root, STATION, INGEST_DATE) == []


def test_broken_manifest_is_an_error_not_a_silent_reload(tmp_path):
    data_root = tmp_path / "data"
    run = write_default_run(tmp_path)
    (run.bronze / "manifest.json").write_text("{kein json", encoding="utf-8")
    with pytest.raises(dn.IngestionError, match="Invalid manifest"):
        dn.completed_runs(data_root, STATION)


def test_stale_partial_directories_are_discarded(tmp_path):
    data_root = tmp_path / "data"
    partial = run_partial(data_root, STATION)
    alt = (STARTED - timedelta(hours=dn.STALE_PARTIAL_HOURS + 1)).timestamp()
    import os

    os.utime(partial, (alt, alt))
    entfernt = dn.discard_stale_partials(data_root, STARTED)
    assert partial in entfernt
    assert not partial.exists()


def test_fresh_partial_directories_are_kept(tmp_path):
    """Ein laufender Lauf darf nicht unter sich selbst aufgeraeumt werden."""
    data_root = tmp_path / "data"
    partial = run_partial(data_root, STATION)
    assert dn.discard_stale_partials(data_root, STARTED) == []
    assert partial.exists()


def run_partial(data_root: Path, station: str) -> Path:
    path = dn.run_parent(data_root, dn.RAW_LAYER, station) / f".{RUN_ID}.part"
    path.mkdir(parents=True)
    return path
