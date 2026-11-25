"""Tests fuer ``silver/police_area``: ein Polizeibezirk je Zeile."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from silver_pipeline import TransformError
from silver_pipeline import build_police_area as bp

RUN = "run_20261125T080000000000Z"


def wkb(wkt: str) -> bytes:
    con = duckdb.connect()
    try:
        con.execute("LOAD spatial")
        return bytes(con.execute("SELECT ST_AsWKB(ST_GeomFromText(?))", [wkt]).fetchone()[0])
    finally:
        con.close()


def quadrat(x: float, y: float, d: float = 0.1) -> str:
    return f"POLYGON(({x} {y}, {x + d} {y}, {x + d} {y + d}, {x} {y + d}, {x} {y}))"


def schreibe(data_root: Path, stadt: str, zeilen: list[tuple[str, str, str]]) -> None:
    ziel = data_root / "bronze/dataset=gebiete/ebene=polizeibezirk" / f"city={stadt}" / RUN
    ziel.mkdir(parents=True)
    pq.write_table(pa.table({
        "gebiet_id": [z[0] for z in zeilen],
        "gebiet_name": [z[1] for z in zeilen],
        "geometry": pa.array([wkb(z[2]) for z in zeilen], pa.binary()),
        "_extra": pa.array([None] * len(zeilen), pa.string()),
    }), ziel / "part-0001.parquet")
    (ziel / "manifest.json").write_text(json.dumps({"status": "complete", "run_id": RUN}))


def lies(ziel: Path) -> list[dict]:
    con = duckdb.connect()
    try:
        cur = con.execute(f"SELECT * EXCLUDE (geometry) FROM read_parquet('{ziel}/part-0001.parquet', hive_partitioning=false) "
                          "ORDER BY city, TRY_CAST(area_id AS INTEGER)")
        namen = [d[0] for d in cur.description]
        return [dict(zip(namen, r)) for r in cur.fetchall()]
    finally:
        con.close()


@pytest.fixture
def beide(tmp_path):
    data_root = tmp_path / "data"
    schreibe(data_root, "chicago", [
        ("1", "1ST", quadrat(-87.7, 41.8)),
        # District 31 kommt in der Quelle in Teilen.
        ("31", "31ST", quadrat(-87.9, 41.9)),
        ("31", "31ST", quadrat(-87.9, 42.0)),
    ])
    schreibe(data_root, "detroit", [("02", "02", quadrat(-83.2, 42.3))])
    return data_root


def test_teilpolygone_werden_ein_bezirk_und_der_schluessel_verliert_die_null(beide):
    zeilen = lies(bp.build(beide))
    assert [(z["city"], z["area_id"], z["area_name"], z["source_name"], z["source_polygons"])
            for z in zeilen] == [
        ("chicago", "1", "District 1", "1ST", 1),
        ("chicago", "31", "District 31", "31ST", 2),
        ("detroit", "2", "Precinct 2", "02", 1),
    ]
    # Zwei Quadrate von 0,1 Grad sind doppelt so gross wie eines.
    assert zeilen[1]["area_km2"] == pytest.approx(2 * zeilen[0]["area_km2"], rel=0.02)
    assert 80 < zeilen[0]["area_km2"] < 100


def test_das_manifest_nennt_herkunft_und_nachweis(beide):
    manifest = json.loads((bp.build(beide) / "manifest.json").read_text())
    assert manifest["contract_version"] == bp.CONTRACT_VERSION
    assert manifest["reconciliation"]["areas_per_city"] == {"chicago": 2, "detroit": 1}
    assert manifest["reconciliation"]["largest_overlap_share"] == 0.0
    assert {(h["city"], h["run_id"]) for h in manifest["derived_from"]} == {
        ("chicago", RUN), ("detroit", RUN)}


def test_eine_fehlende_stadt_bricht_ab(tmp_path):
    data_root = tmp_path / "data"
    schreibe(data_root, "chicago", [("1", "1ST", quadrat(-87.7, 41.8))])
    with pytest.raises(Exception, match="detroit"):
        bp.build(data_root)


def test_stark_ueberlappende_bezirke_brechen_ab(tmp_path):
    """Eine Tat laege sonst in zwei Bezirken."""
    data_root = tmp_path / "data"
    schreibe(data_root, "chicago", [("1", "1ST", quadrat(-87.7, 41.8)),
                                    ("2", "2ND", quadrat(-87.65, 41.8))])
    schreibe(data_root, "detroit", [("02", "02", quadrat(-83.2, 42.3))])
    with pytest.raises(TransformError, match="ueberlappen"):
        bp.build(data_root)


def test_eine_kennung_ohne_zahl_wird_verworfen_und_gezaehlt(tmp_path):
    data_root = tmp_path / "data"
    schreibe(data_root, "chicago", [("1", "1ST", quadrat(-87.7, 41.8)),
                                    ("HQ", "Zentrale", quadrat(-87.5, 41.8))])
    schreibe(data_root, "detroit", [("02", "02", quadrat(-83.2, 42.3))])
    ziel = bp.build(data_root)
    assert [z["area_id"] for z in lies(ziel) if z["city"] == "chicago"] == ["1"]
    nachweis = json.loads((ziel / "manifest.json").read_text())["reconciliation"]
    assert nachweis["source_rows_without_id_or_geometry"] == {"chicago": 1, "detroit": 0}
