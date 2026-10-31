"""Tests fuer die TIGER-Ingestion.

Sie laufen ohne Netzzugriff. Das Shapefile, an dem die Ableitung nach Bronze
haengt, wird zur Laufzeit erzeugt: ein Zwei-Zeilen-Layer, den pyogrio schreibt
und anschliessend wie die echte Auslieferung als ZIP verpackt wird. Damit
braucht das Repository keine Binaerdatei als Fixture.
"""

from __future__ import annotations

import json
import struct
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

# Ohne pyogrio gibt es keine TIGER-Ingestion; dann diese Datei ueberspringen,
# statt die uebrige Suite mitzureissen.
pytest.importorskip("pyogrio", reason="pyogrio wird fuer die TIGER-Ingestion gebraucht")

from pyogrio.raw import write_arrow  # noqa: E402

import download_tiger as dt  # noqa: E402


VINTAGE = 2024
STATE = "26"
STARTED = datetime(2026, 9, 6, 4, 0, 0, tzinfo=timezone.utc)
RUN_ID = "run_20260906T040000000000Z"


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------


def wkb_square(x: float = 0.0, y: float = 0.0, size: float = 1.0) -> bytes:
    """Ein Quadrat als WKB-Polygon, little endian."""
    points = [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]
    return (
        struct.pack("<BII", 1, 3, 1)
        + struct.pack("<I", len(points))
        + b"".join(struct.pack("<dd", a, b) for a, b in points)
    )


def source_table(**overrides) -> pa.Table:
    """Eine Quelltabelle, wie pyogrio sie aus dem Shapefile liefert."""
    columns = {
        "STATEFP": pa.array(["26", "26"]),
        "COUNTYFP": pa.array(["163", "163"]),
        "TRACTCE": pa.array(["500100", "500200"]),
        "GEOID": pa.array(["26163500100", "26163500200"]),
        "NAME": pa.array(["5001", "5002"]),
        "NAMELSAD": pa.array(["Census Tract 5001", "Census Tract 5002"]),
        "MTFCC": pa.array(["G5020", "G5020"]),
        "FUNCSTAT": pa.array(["S", "S"]),
        "ALAND": pa.array([100, 200], type=pa.int64()),
        "AWATER": pa.array([1, 2], type=pa.int64()),
        "INTPTLAT": pa.array(["+42.0", "+42.1"]),
        "INTPTLON": pa.array(["-083.0", "-083.1"]),
        "wkb_geometry": pa.array([wkb_square(), wkb_square(2.0, 2.0)], pa.binary()),
    }
    columns.update(overrides)
    return pa.table(columns)


def make_archive(
    directory: Path,
    vintage: int = VINTAGE,
    state: str = STATE,
    table: pa.Table | None = None,
    members: tuple[str, ...] = (".shp", ".shx", ".dbf", ".prj", ".cpg"),
) -> bytes:
    """Schreibt ein Shapefile und verpackt es wie die echte Auslieferung."""
    work = directory / f"fixture_{vintage}_{state}"
    work.mkdir(parents=True, exist_ok=True)
    stem = f"tl_{vintage}_{state}_tract"
    write_arrow(
        table if table is not None else source_table(),
        work / f"{stem}.shp",
        driver="ESRI Shapefile",
        geometry_name="wkb_geometry",
        geometry_type="Polygon",
        crs="EPSG:4269",
    )
    archive = work / f"{stem}.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for suffix in members:
            part = work / f"{stem}{suffix}"
            if part.exists():
                handle.write(part, part.name)
    return archive.read_bytes()


class FakeResponse:
    def __init__(self, payload: bytes, headers: dict | None = None):
        self.content = payload
        self.headers = headers if headers is not None else {
            "Content-Length": str(len(payload)),
            "Last-Modified": "Fri, 27 Jun 2025 20:05:42 GMT",
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


def write_default_run(tmp_path: Path, **overrides) -> dt.RunPaths:
    payload = overrides.pop("payload", None)
    if payload is None:
        payload = make_archive(tmp_path)
    archive = dt.Archive(
        payload=payload,
        url=dt.tiger_url(VINTAGE, STATE),
        members=dt.verify_archive(payload, VINTAGE, STATE),
        content_length=len(payload),
        last_modified="Fri, 27 Jun 2025 20:05:42 GMT",
    )
    return dt.write_run(
        overrides.pop("data_root", tmp_path / "data"),
        overrides.pop("started", STARTED),
        archive,
        vintage=overrides.pop("vintage", VINTAGE),
        state=overrides.pop("state", STATE),
    )


# --------------------------------------------------------------------------
# Adressen und Ablage
# --------------------------------------------------------------------------


def test_tiger_url_follows_the_published_pattern():
    assert dt.tiger_url(2024, "17") == (
        "https://www2.census.gov/geo/tiger/TIGER2024/TRACT/tl_2024_17_tract.zip"
    )


def test_archive_and_member_names_carry_vintage_and_state():
    assert dt.archive_name(2020, "26") == "tl_2020_26_tract.zip"
    assert dt.shapefile_member(2020, "26") == "tl_2020_26_tract.shp"


def test_run_parent_partitions_by_vintage_and_state(tmp_path):
    """Partitioniert wird nach Vintage, nicht nach Abrufdatum."""
    parent = dt.run_parent(tmp_path, dt.BRONZE_LAYER, 2024, "17")
    assert parent == (
        tmp_path / "bronze" / "dataset=tiger_tract" / "vintage=2024" / "state=17"
    )


def test_both_layers_are_known():
    assert dt.LAYERS == (dt.RAW_LAYER, dt.BRONZE_LAYER)


# --------------------------------------------------------------------------
# Vollstaendigkeit des Archivs
# --------------------------------------------------------------------------


def test_verify_archive_accepts_a_complete_delivery(tmp_path):
    members = dt.verify_archive(make_archive(tmp_path), VINTAGE, STATE)
    assert f"tl_{VINTAGE}_{STATE}_tract.shp" in members


def test_verify_archive_rejects_a_missing_required_member(tmp_path):
    """Ohne .prj fehlt die Projektion, das Shapefile ist unbrauchbar."""
    payload = make_archive(tmp_path, members=(".shp", ".shx", ".dbf"))
    with pytest.raises(dt.IngestionError, match="unvollstaendig"):
        dt.verify_archive(payload, VINTAGE, STATE)


def test_verify_archive_rejects_a_broken_checksum(tmp_path):
    """Ein gekipptes Byte im Inhalt muss auffallen, nicht durchrutschen."""
    payload = bytearray(make_archive(tmp_path))
    # Die ersten Bytes hinter dem lokalen Header gehoeren zu den Nutzdaten.
    payload[60] ^= 0xFF
    with pytest.raises(dt.IngestionError, match="Pruefsumme|ZIP-Archiv"):
        dt.verify_archive(bytes(payload), VINTAGE, STATE)


def test_verify_archive_rejects_something_that_is_not_a_zip():
    with pytest.raises(dt.IngestionError, match="ZIP-Archiv"):
        dt.verify_archive(b"<html>404 Not Found</html>", VINTAGE, STATE)


def test_fetch_archive_rejects_a_truncated_download(tmp_path, monkeypatch):
    """Content-Length und empfangene Bytes muessen uebereinstimmen."""
    payload = make_archive(tmp_path)
    session = FakeSession(payload, headers={"Content-Length": str(len(payload) + 1)})
    with pytest.raises(dt.IngestionError, match="Unvollstaendige Auslieferung"):
        dt.fetch_archive(session, VINTAGE, STATE)


def test_fetch_archive_returns_the_evidence(tmp_path):
    payload = make_archive(tmp_path)
    session = FakeSession(payload)
    archive = dt.fetch_archive(session, VINTAGE, STATE)
    assert archive.payload == payload
    assert archive.content_length == len(payload)
    assert archive.last_modified
    assert session.urls == [dt.tiger_url(VINTAGE, STATE)]


# --------------------------------------------------------------------------
# Abbildung auf das gepinnte Schema
# --------------------------------------------------------------------------


def test_bronze_table_uses_the_pinned_schema():
    assert dt.bronze_table(source_table()).schema == dt.SCHEMA


def test_bronze_table_keeps_the_geometry_as_wkb():
    table = dt.bronze_table(source_table())
    assert table.column(dt.GEOMETRY_COLUMN).to_pylist()[0] == wkb_square()


def test_bronze_table_keeps_an_unknown_column_in_extra():
    """GEOIDFQ gibt es erst ab neueren Vintages; verloren gehen darf es nicht."""
    table = dt.bronze_table(
        source_table(GEOIDFQ=pa.array(["1400000US26163500100", None]))
    )
    assert table.column(dt.EXTRA_COLUMN).to_pylist() == [
        '{"GEOIDFQ":"1400000US26163500100"}',
        None,
    ]


def test_bronze_table_moves_a_changed_type_to_extra():
    """Wechselt der Typ einer bekannten Spalte, bleibt die Spalte leer."""
    table = dt.bronze_table(source_table(ALAND=pa.array(["100", "200"])))
    assert table.column("ALAND").to_pylist() == [None, None]
    assert json.loads(table.column(dt.EXTRA_COLUMN)[0].as_py()) == {"ALAND": "100"}


def test_bronze_table_fills_a_missing_column_with_null():
    source = source_table()
    source = source.drop_columns(["NAMELSAD"])
    table = dt.bronze_table(source)
    assert table.schema == dt.SCHEMA
    assert table.column("NAMELSAD").to_pylist() == [None, None]


def test_bronze_table_without_extras_leaves_the_column_empty():
    table = dt.bronze_table(source_table())
    assert table.column(dt.EXTRA_COLUMN).to_pylist() == [None, None]


def test_bronze_table_keeps_every_row():
    assert dt.bronze_table(source_table()).num_rows == 2


# --------------------------------------------------------------------------
# Fingerabdruck der Quelle
# --------------------------------------------------------------------------


def test_source_schema_is_stable_for_the_same_fields():
    meta = {"fields": ["GEOID", "ALAND"], "ogr_types": ["OFTString", "OFTInteger64"]}
    assert dt.source_schema(meta)[0] == dt.source_schema(dict(meta))[0]


def test_source_schema_changes_when_a_type_changes():
    """Genau dafuer ist der Fingerabdruck da: EXTRA_COLUMN merkt es nicht."""
    alt = {"fields": ["GEOID", "ALAND"], "ogr_types": ["OFTString", "OFTInteger64"]}
    neu = {"fields": ["GEOID", "ALAND"], "ogr_types": ["OFTString", "OFTString"]}
    assert dt.source_schema(alt)[0] != dt.source_schema(neu)[0]
    assert dt.source_schema(neu)[1] == {"GEOID": "OFTString", "ALAND": "OFTString"}


# --------------------------------------------------------------------------
# Lesen des Shapefiles
# --------------------------------------------------------------------------


def test_read_features_reads_straight_from_the_archive(tmp_path):
    """GDAL liest ueber /vsizip/, das Archiv wird nicht ausgepackt."""
    archive = tmp_path / "tl_2024_26_tract.zip"
    archive.write_bytes(make_archive(tmp_path))
    table, meta = dt.read_features(archive, VINTAGE, STATE)
    assert table.num_rows == 2
    assert str(meta["crs"]) == dt.EXPECTED_CRS


def test_windows_reads_landed_bytes_and_can_rename_with_table_alive(tmp_path, monkeypatch):
    work, final = tmp_path / ".raw.part", tmp_path / "published"
    work.mkdir()
    archive = work / dt.archive_name(VINTAGE, STATE)
    payload = make_archive(tmp_path)
    archive.write_bytes(payload)
    original = dt.read_arrow
    calls = []

    def read(source, **kwargs):
        calls.append((source, kwargs))
        return original(source, **kwargs)

    monkeypatch.setattr(dt, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(dt, "read_arrow", read)
    table, _ = dt.read_features(archive, VINTAGE, STATE)
    assert calls == [(payload, {"layer": "tl_2024_26_tract"})]
    work.rename(final)
    assert table.num_rows == 2
    assert (final / archive.name).read_bytes() == payload


def test_read_features_reports_an_unreadable_archive(tmp_path):
    archive = tmp_path / "tl_2024_26_tract.zip"
    archive.write_bytes(b"kein zip")
    with pytest.raises(dt.IngestionError, match="nicht lesbar"):
        dt.read_features(archive, VINTAGE, STATE)


# --------------------------------------------------------------------------
# Veroeffentlichen eines Laufs
# --------------------------------------------------------------------------


def test_write_run_publishes_both_layers(tmp_path):
    run = write_default_run(tmp_path)
    assert run.raw.name == RUN_ID and run.bronze.name == RUN_ID
    assert run.raw.parent == dt.run_parent(
        tmp_path / "data", dt.RAW_LAYER, VINTAGE, STATE
    )
    assert (run.raw / dt.archive_name(VINTAGE, STATE)).exists()
    assert (run.bronze / dt.PARQUET_FILE).exists()


def test_write_run_raw_holds_the_untouched_archive(tmp_path):
    payload = make_archive(tmp_path)
    run = write_default_run(tmp_path, payload=payload)
    assert (run.raw / dt.archive_name(VINTAGE, STATE)).read_bytes() == payload


def test_write_run_bronze_is_derived_from_the_landed_archive(tmp_path):
    run = write_default_run(tmp_path)
    table = pq.ParquetFile(run.bronze / dt.PARQUET_FILE).read()
    assert table.schema == dt.SCHEMA
    assert table.column("GEOID").to_pylist() == ["26163500100", "26163500200"]


def test_parquet_output_stream_is_explicit_and_closed_before_publication(tmp_path, monkeypatch):
    original = dt.pq.write_table
    streams = []

    def write(table, stream, **kwargs):
        assert not isinstance(stream, (str, Path))
        assert not stream.closed
        streams.append(stream)
        return original(table, stream, **kwargs)

    monkeypatch.setattr(dt.pq, "write_table", write)
    run = write_default_run(tmp_path)
    assert streams and all(stream.closed for stream in streams)
    assert read_manifest(run.raw)["status"] == "complete"
    assert read_manifest(run.bronze)["status"] == "complete"


def test_write_run_manifest_documents_the_completeness(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path).bronze)
    assert manifest["status"] == "complete"
    assert manifest["completeness"]["verified"] is True
    assert manifest["completeness"]["archive_crc_ok"] is True
    assert manifest["completeness"]["features_written"] == 2
    assert manifest["completeness"]["downloaded_bytes"] > 0
    assert ".shp" in manifest["completeness"]["required_members"]


def test_write_run_manifest_records_vintage_state_and_crs(tmp_path):
    manifest = read_manifest(write_default_run(tmp_path).bronze)
    assert manifest["vintage"] == VINTAGE
    assert manifest["state_fips"] == STATE
    assert manifest["state_name"] == "michigan"
    assert manifest["crs"] == dt.EXPECTED_CRS
    assert manifest["geometry_encoding"] == "WKB"


def test_write_run_only_bronze_declares_the_parquet_schema(tmp_path):
    run = write_default_run(tmp_path)
    assert read_manifest(run.bronze)["schema"]["geometry"] == "binary"
    assert "schema" not in read_manifest(run.raw)
    assert read_manifest(run.raw)["layer"] == dt.RAW_LAYER


def test_write_run_manifest_records_the_file_checksum(tmp_path):
    run = write_default_run(tmp_path)
    entry = read_manifest(run.raw)["files"][0]
    assert entry["path"] == dt.archive_name(VINTAGE, STATE)
    assert len(entry["sha256"]) == 64


def test_write_run_leaves_no_work_directories(tmp_path):
    write_default_run(tmp_path)
    assert list((tmp_path / "data").rglob(".*.part")) == []


def test_write_run_cleans_up_when_bronze_cannot_be_written(tmp_path, monkeypatch):
    """Scheitert die Ableitung, bleibt kein halber Lauf zurueck."""

    def boom(*args, **kwargs):
        raise dt.IngestionError("Shapefile nicht lesbar")

    monkeypatch.setattr(dt, "read_features", boom)
    with pytest.raises(dt.IngestionError):
        write_default_run(tmp_path)
    assert list((tmp_path / "data").rglob(".*.part")) == []
    assert list((tmp_path / "data").rglob("run_*")) == []


def test_write_run_never_overwrites_an_existing_run(tmp_path):
    write_default_run(tmp_path)
    with pytest.raises(OSError):
        write_default_run(tmp_path)


@pytest.mark.parametrize("winerror", [5, 32, 33])
def test_publish_directory_retries_transient_windows_locks(tmp_path, monkeypatch, winerror):
    work, final = tmp_path / ".work.part", tmp_path / "finished"
    work.mkdir()
    (work / "evidence").write_bytes(b"original")
    original = Path.rename
    attempts, waits = [], []

    def rename(path, target):
        attempts.append(path)
        if len(attempts) < 3:
            error = PermissionError("transient lock")
            error.winerror = winerror
            raise error
        return original(path, target)

    monkeypatch.setattr(dt, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(dt.time, "sleep", waits.append)
    dt.publish_directory(work, final)
    assert waits == [0.1, 0.2]
    assert (final / "evidence").read_bytes() == b"original"
    assert not work.exists()


def test_publish_directory_stops_after_bounded_retries(tmp_path, monkeypatch):
    work, final = tmp_path / ".work.part", tmp_path / "finished"
    work.mkdir()
    waits = []

    def blocked(*_):
        error = PermissionError("permanent denial")
        error.winerror = 5
        raise error

    monkeypatch.setattr(dt, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(Path, "rename", blocked)
    monkeypatch.setattr(dt.time, "sleep", waits.append)
    with pytest.raises(PermissionError, match="permanent denial"):
        dt.publish_directory(work, final)
    assert len(waits) == 5
    assert work.exists() and not final.exists()


def test_publish_directory_never_replaces_existing_target(tmp_path):
    work, final = tmp_path / ".work.part", tmp_path / "finished"
    work.mkdir()
    final.mkdir()
    (final / "evidence").write_bytes(b"already published")
    with pytest.raises(FileExistsError):
        dt.publish_directory(work, final)
    assert (final / "evidence").read_bytes() == b"already published"
    assert work.exists()


def test_write_run_survives_a_transient_raw_publication_lock(tmp_path, monkeypatch):
    original = Path.rename
    blocked = []

    def rename(path, target):
        if not blocked and "raw" in path.parts and path.name.endswith(".part"):
            blocked.append(path)
            error = PermissionError("scanner")
            error.winerror = 5
            raise error
        return original(path, target)

    monkeypatch.setattr(dt, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(Path, "rename", rename)
    monkeypatch.setattr(dt.time, "sleep", lambda _: None)
    run = write_default_run(tmp_path)
    assert blocked
    assert read_manifest(run.raw)["status"] == "complete"
    assert read_manifest(run.bronze)["status"] == "complete"


# --------------------------------------------------------------------------
# Die Vintage-Frage: gibt es ueberhaupt etwas zu tun?
# --------------------------------------------------------------------------


def test_completed_runs_finds_a_published_run(tmp_path):
    run = write_default_run(tmp_path)
    assert dt.completed_runs(tmp_path / "data", VINTAGE, STATE) == [run.bronze]


def test_completed_runs_ignores_another_vintage(tmp_path):
    write_default_run(tmp_path)
    assert dt.completed_runs(tmp_path / "data", 2020, STATE) == []


def test_completed_runs_ignores_another_state(tmp_path):
    write_default_run(tmp_path)
    assert dt.completed_runs(tmp_path / "data", VINTAGE, "17") == []


def test_completed_runs_ignores_an_incomplete_manifest(tmp_path):
    run = write_default_run(tmp_path)
    manifest = read_manifest(run.bronze)
    manifest["status"] = "failed"
    (run.bronze / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert dt.completed_runs(tmp_path / "data", VINTAGE, STATE) == []


def test_completed_runs_reports_a_broken_manifest(tmp_path):
    run = write_default_run(tmp_path)
    (run.bronze / "manifest.json").write_text("{kaputt", encoding="utf-8")
    with pytest.raises(dt.IngestionError, match="Invalid manifest"):
        dt.completed_runs(tmp_path / "data", VINTAGE, STATE)


def test_ingest_state_skips_a_vintage_that_is_already_loaded(tmp_path):
    """Eine Vintage ist eingefroren - zweimal laden bringt nichts Neues."""
    write_default_run(tmp_path)
    session = FakeSession(make_archive(tmp_path))
    run = dt.ingest_state(
        session, tmp_path / "data", STARTED, VINTAGE, STATE, force=False
    )
    assert run is None
    assert session.urls == []


def test_ingest_state_force_writes_a_second_run(tmp_path):
    write_default_run(tmp_path)
    session = FakeSession(make_archive(tmp_path))
    later = STARTED + timedelta(days=1)
    run = dt.ingest_state(session, tmp_path / "data", later, VINTAGE, STATE, force=True)
    assert run is not None
    assert len(dt.completed_runs(tmp_path / "data", VINTAGE, STATE)) == 2


def test_ingest_state_downloads_when_nothing_is_there(tmp_path):
    session = FakeSession(make_archive(tmp_path))
    run = dt.ingest_state(
        session, tmp_path / "data", STARTED, VINTAGE, STATE, force=False
    )
    assert run is not None
    assert session.urls == [dt.tiger_url(VINTAGE, STATE)]


# --------------------------------------------------------------------------
# Aufraeumen und Argumente
# --------------------------------------------------------------------------


def test_discard_stale_partials_removes_only_old_leftovers(tmp_path):
    data_root = tmp_path / "data"
    parent = dt.run_parent(data_root, dt.RAW_LAYER, VINTAGE, STATE)
    alt = parent / ".run_alt.part"
    neu = parent / ".run_neu.part"
    for path in (alt, neu):
        path.mkdir(parents=True)
    import os

    veraltet = (STARTED - timedelta(hours=dt.STALE_PARTIAL_HOURS + 1)).timestamp()
    os.utime(alt, (veraltet, veraltet))

    removed = dt.discard_stale_partials(data_root, STARTED)
    assert removed == [alt]
    assert not alt.exists() and neu.exists()


def test_discard_stale_partials_never_touches_a_published_run(tmp_path):
    run = write_default_run(tmp_path)
    dt.discard_stale_partials(tmp_path / "data", STARTED + timedelta(days=30))
    assert run.raw.exists() and run.bronze.exists()


def test_arguments_rejects_a_vintage_before_the_first_one(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--vintage", "1999"])
    with pytest.raises(SystemExit):
        dt.arguments()


def test_arguments_defaults_to_every_known_state(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog"])
    args = dt.arguments()
    assert args.state == sorted(dt.STATES)
    assert args.vintage == dt.DEFAULT_VINTAGE
    assert args.force is False


def test_arguments_accepts_repeated_state_flags(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--state", "17", "--state", "26"])
    assert dt.arguments().state == ["17", "26"]


def test_states_cover_both_cities():
    """Illinois fuer Chicago, Michigan fuer Detroit."""
    assert dt.STATES == {"17": "illinois", "26": "michigan"}
