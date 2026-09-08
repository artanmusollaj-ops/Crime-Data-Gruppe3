"""Tests fuer die Silver-Tabelle ``tract``.

Sie laufen ohne Netzzugriff und ohne die echten Bronze-Laeufe: Beide Quellen
werden als kleine Parquet-Dateien zur Laufzeit erzeugt, inklusive einer
Geometrie als WKB und der Fehlwert-Kennung des ACS. Damit ist pruefbar, was
diese Schicht tatsaechlich leistet - deuten, nicht kopieren.
"""

from __future__ import annotations

import json
import struct
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_tract as bt


VINTAGE = 2024
STARTED = datetime(2026, 9, 8, 22, 0, 0, tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------


def wkb_square(x: float, y: float, size: float = 1.0) -> bytes:
    """Ein Quadrat als WKB-Polygon, little endian."""
    punkte = [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]
    return (
        struct.pack("<BII", 1, 3, 1)
        + struct.pack("<I", len(punkte))
        + b"".join(struct.pack("<dd", a, b) for a, b in punkte)
    )


def tiger_table(geoids=("17031010100", "17031010200")) -> pa.Table:
    """Eine TIGER-Quelltabelle, wie die Bronze-Schicht sie schreibt."""
    n = len(geoids)
    return pa.table({
        "STATEFP": pa.array([g[:2] for g in geoids]),
        "COUNTYFP": pa.array([g[2:5] for g in geoids]),
        "TRACTCE": pa.array([g[5:] for g in geoids]),
        "GEOID": pa.array(list(geoids)),
        "NAME": pa.array([g[-4:] for g in geoids]),
        "NAMELSAD": pa.array([f"Census Tract {g[-4:]}" for g in geoids]),
        "MTFCC": pa.array(["G5020"] * n),
        "FUNCSTAT": pa.array(["S"] * n),
        "ALAND": pa.array([100_000] * n, type=pa.int64()),
        "AWATER": pa.array([500] * n, type=pa.int64()),
        # Fuehrendes Plus und fuehrende Nullen wie in der Quelle.
        "INTPTLAT": pa.array([f"+41.{8 + i}" for i in range(n)]),
        "INTPTLON": pa.array([f"-087.{6 + i}" for i in range(n)]),
        "geometry": pa.array(
            [wkb_square(i * 2.0, i * 2.0) for i in range(n)], pa.binary()
        ),
        "_extra": pa.array([None] * n, type=pa.string()),
    })


def acs_table(
    geoids=("17031010100", "17031010200"),
    population=("1837", "2500"),
    income=("70326", "55000"),
    poverty=("129", "250"),
) -> pa.Table:
    """Eine ACS-Quelltabelle - alle Werte als Text, so wie die API sie liefert."""
    return pa.table({
        "GEOID": pa.array(list(geoids)),
        "NAME": pa.array([f"Census Tract {g[-4:]}" for g in geoids]),
        "B01003_001E": pa.array(list(population)),
        "B19013_001E": pa.array(list(income)),
        "B17001_002E": pa.array(list(poverty)),
        "state": pa.array([g[:2] for g in geoids]),
        "county": pa.array([g[2:5] for g in geoids]),
        "tract": pa.array([g[5:] for g in geoids]),
        "_extra": pa.array([None] * len(geoids), type=pa.string()),
    })


def write_bronze_run(
    data_root: Path,
    dataset: str,
    state: str,
    table: pa.Table,
    run_id: str = "run_20260906T120000000000Z",
    status: str = "complete",
) -> Path:
    """Legt einen Bronze-Lauf so ab, wie die Ingestion es tut."""
    verzeichnis = (
        data_root
        / "bronze"
        / f"dataset={dataset}"
        / f"vintage={VINTAGE}"
        / f"state={state}"
        / run_id
    )
    verzeichnis.mkdir(parents=True)
    pq.write_table(table, verzeichnis / bt.PARQUET_FILE)
    (verzeichnis / "manifest.json").write_text(
        json.dumps({"status": status, "run_id": run_id}), encoding="utf-8"
    )
    return verzeichnis


def bronze_fuer_illinois(data_root: Path, **overrides) -> None:
    """Der Normalfall: TIGER und ACS deckungsgleich fuer einen Staat."""
    write_bronze_run(
        data_root, bt.TIGER_DATASET, "17", overrides.pop("tiger", tiger_table())
    )
    write_bronze_run(
        data_root, bt.ACS_DATASET, "17", overrides.pop("acs", acs_table())
    )


def gebaut(tmp_path: Path, **overrides) -> tuple[Path, dict, pa.Table]:
    data_root = tmp_path / "data"
    bronze_fuer_illinois(data_root, **overrides)
    ziel = bt.build(data_root, VINTAGE, ["17"])
    manifest = json.loads((ziel / "manifest.json").read_text(encoding="utf-8"))
    tabelle = pq.read_table(ziel / bt.PARQUET_FILE)
    return ziel, manifest, tabelle


# --------------------------------------------------------------------------
# Ablage und Herkunft
# --------------------------------------------------------------------------


def test_table_dir_partitions_by_vintage():
    """Eine neue Vintage ist eine andere Tabelle, keine neuere Version."""
    assert bt.table_dir(Path("data"), 2024) == (
        Path("data") / "silver" / "dataset=tract" / "vintage=2024"
    )


def test_newest_complete_run_wins(tmp_path):
    data_root = tmp_path / "data"
    write_bronze_run(
        data_root, bt.TIGER_DATASET, "17", tiger_table(),
        run_id="run_20260901T120000000000Z",
    )
    write_bronze_run(
        data_root, bt.TIGER_DATASET, "17", tiger_table(),
        run_id="run_20260907T120000000000Z",
    )
    quelle = bt.newest_bronze_run(data_root, bt.TIGER_DATASET, VINTAGE, "17")
    assert quelle.run_id == "run_20260907T120000000000Z"


def test_incomplete_run_is_ignored(tmp_path):
    data_root = tmp_path / "data"
    write_bronze_run(
        data_root, bt.TIGER_DATASET, "17", tiger_table(),
        run_id="run_20260901T120000000000Z",
    )
    write_bronze_run(
        data_root, bt.TIGER_DATASET, "17", tiger_table(),
        run_id="run_20260907T120000000000Z", status="aborted",
    )
    quelle = bt.newest_bronze_run(data_root, bt.TIGER_DATASET, VINTAGE, "17")
    assert quelle.run_id == "run_20260901T120000000000Z"


def test_missing_bronze_is_a_clear_error(tmp_path):
    with pytest.raises(bt.TransformError, match="Kein vollstaendiger Bronze-Lauf"):
        bt.newest_bronze_run(tmp_path / "data", bt.TIGER_DATASET, VINTAGE, "17")


def test_manifest_names_every_source_run(tmp_path):
    """Ohne diese Herkunft ist der Referenzstand aus Absprache 7.1 nicht belegbar."""
    _, manifest, _ = gebaut(tmp_path)
    datensaetze = {q["dataset"] for q in manifest["derived_from"]}
    assert datensaetze == {bt.TIGER_DATASET, bt.ACS_DATASET}
    assert all(q["run_id"].startswith("run_") for q in manifest["derived_from"])
    assert all(q["layer"] == "bronze" for q in manifest["derived_from"])


# --------------------------------------------------------------------------
# Was diese Schicht deutet
# --------------------------------------------------------------------------


def test_grain_is_one_row_per_tract(tmp_path):
    _, manifest, tabelle = gebaut(tmp_path)
    assert manifest["grain"] == "ein Census Tract"
    assert tabelle.num_rows == 2
    assert len(set(tabelle.column("geoid").to_pylist())) == 2


def test_text_becomes_numbers(tmp_path):
    """Der ACS liefert Text; Silver ist die Schicht, die daraus Zahlen macht."""
    _, _, tabelle = gebaut(tmp_path)
    assert tabelle.column("population").to_pylist() == [1837, 2500]
    assert tabelle.column("median_household_income_usd").to_pylist() == [70326, 55000]
    assert str(tabelle.schema.field("population").type) == "int64"


def test_acs_missing_value_becomes_null(tmp_path):
    """-666666666 heisst 'keine Schaetzung moeglich', nicht ein Einkommen."""
    _, _, tabelle = gebaut(
        tmp_path, acs=acs_table(income=(bt.ACS_MISSING_VALUE, "55000"))
    )
    assert tabelle.column("median_household_income_usd").to_pylist() == [None, 55000]
    assert "MISSING_MEDIAN_INCOME" in tabelle.column("quality_flags")[0].as_py()


def test_poverty_rate_is_derived(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    quote = tabelle.column("poverty_rate").to_pylist()
    assert quote[0] == pytest.approx(129 / 1837)
    assert quote[1] == pytest.approx(250 / 2500)


def test_zero_population_leaves_the_rate_undefined(tmp_path):
    """Keine Division durch null - aber die absolute Zahl bleibt erhalten."""
    _, _, tabelle = gebaut(
        tmp_path, acs=acs_table(population=("0", "2500"), poverty=("0", "250"))
    )
    assert tabelle.column("poverty_rate")[0].as_py() is None
    assert tabelle.column("population")[0].as_py() == 0
    assert "ZERO_POPULATION" in tabelle.column("quality_flags")[0].as_py()


def test_clean_tract_has_no_flags(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    assert tabelle.column("quality_flags")[1].as_py() == []


def test_centroid_text_becomes_coordinates(tmp_path):
    """INTPTLAT kommt als '+41.8', INTPTLON mit fuehrenden Nullen."""
    _, _, tabelle = gebaut(tmp_path)
    assert tabelle.column("centroid_lat")[0].as_py() == pytest.approx(41.8)
    assert tabelle.column("centroid_lon")[0].as_py() == pytest.approx(-87.6)


def test_extra_column_is_not_carried_over(tmp_path):
    """_extra bleibt in Bronze; hierher zu heben kostet eine Codeaenderung."""
    _, _, tabelle = gebaut(tmp_path)
    assert "_extra" not in tabelle.schema.names


def test_geometry_survives_as_wkb(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    assert str(tabelle.schema.field("geometry").type) == "binary"
    assert tabelle.column("geometry")[0].as_py() == wkb_square(0.0, 0.0)


def test_state_name_is_resolved(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    assert tabelle.column("state_name").to_pylist() == ["illinois", "illinois"]


# --------------------------------------------------------------------------
# Der Nachweis dieser Schicht
# --------------------------------------------------------------------------


def test_reconciliation_proves_the_join_lost_nothing(tmp_path):
    _, manifest, _ = gebaut(tmp_path)
    nachweis = manifest["reconciliation"]
    assert nachweis["verified"] is True
    assert nachweis["row_count"] == 2
    assert nachweis["geoid_unique"] is True
    assert nachweis["tracts_without_geometry"] == 0
    assert nachweis["tracts_without_acs_attributes"] == 0
    assert nachweis["invalid_geometries"] == 0


def test_tract_without_acs_is_kept_and_flagged(tmp_path):
    """Ein Tract ohne Attribute darf nicht stillschweigend verschwinden."""
    _, manifest, tabelle = gebaut(
        tmp_path,
        tiger=tiger_table(("17031010100", "17031010200", "17031010300")),
        acs=acs_table(),
    )
    assert tabelle.num_rows == 3
    assert manifest["reconciliation"]["tracts_without_acs_attributes"] == 1
    ohne = [
        zeile
        for zeile in tabelle.to_pylist()
        if "MISSING_ACS_ATTRIBUTES" in zeile["quality_flags"]
    ]
    assert len(ohne) == 1
    assert ohne[0]["geoid"] == "17031010300"
    assert ohne[0]["population"] is None


def test_acs_row_without_geometry_is_an_error(tmp_path):
    """Ohne Geometrie ist kein raeumlicher Join moeglich - das muss auffallen."""
    data_root = tmp_path / "data"
    bronze_fuer_illinois(
        data_root,
        tiger=tiger_table(("17031010100",)),
        acs=acs_table(
            ("17031010100", "17031099999"), ("1837", "10"), ("70326", "1"), ("129", "0")
        ),
    )
    with pytest.raises(bt.TransformError, match="keine\\s+Geometrie"):
        bt.build(data_root, VINTAGE, ["17"])


def test_column_statistics_land_in_the_manifest(tmp_path):
    _, manifest, _ = gebaut(
        tmp_path, acs=acs_table(income=(bt.ACS_MISSING_VALUE, "55000"))
    )
    statistik = manifest["column_statistics"]
    assert statistik["population_total"] == 1837 + 2500
    assert statistik["median_income_filled"] == 1
    assert statistik["median_income_missing_share"] == pytest.approx(0.5)


def test_manifest_records_the_tool(tmp_path):
    _, manifest, _ = gebaut(tmp_path)
    assert manifest["tool"].startswith("duckdb ")
    assert "spatial" in manifest["tool"]


# --------------------------------------------------------------------------
# Ersetzen statt anhaeufen
# --------------------------------------------------------------------------


def test_rebuild_replaces_instead_of_accumulating(tmp_path):
    """Silver ist abgeleitet - jeder Aufbau ersetzt den vorherigen Stand."""
    data_root = tmp_path / "data"
    bronze_fuer_illinois(data_root)
    erst = bt.build(data_root, VINTAGE, ["17"])
    zweit = bt.build(data_root, VINTAGE, ["17"])
    assert erst == zweit
    assert sorted(p.name for p in zweit.iterdir()) == [
        "manifest.json",
        bt.PARQUET_FILE,
    ]
    assert not list(zweit.parent.glob(".*"))


def test_failed_rebuild_keeps_the_previous_table(tmp_path):
    """Ein Fehler darf den vorhandenen Stand nicht zerstoeren."""
    data_root = tmp_path / "data"
    bronze_fuer_illinois(data_root)
    ziel = bt.build(data_root, VINTAGE, ["17"])
    vorher = (ziel / bt.PARQUET_FILE).read_bytes()

    # Ein ACS-Tract ohne Geometrie laesst den naechsten Aufbau scheitern.
    write_bronze_run(
        data_root, bt.ACS_DATASET, "17",
        acs_table(
            ("17031010100", "17031099999"), ("1", "1"), ("1", "1"), ("0", "0")
        ),
        run_id="run_20260908T120000000000Z",
    )
    with pytest.raises(bt.TransformError):
        bt.build(data_root, VINTAGE, ["17"])

    assert ziel.exists()
    assert (ziel / bt.PARQUET_FILE).read_bytes() == vorher
    assert not list(ziel.parent.glob(".*"))
