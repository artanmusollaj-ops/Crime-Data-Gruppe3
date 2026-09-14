"""Tests fuer die Silver-Tabelle ``weather_day``.

Sie laufen ohne Netzzugriff. Die NOAA-Bronze wird als kleine Parquet-Datei
zur Laufzeit erzeugt, mit denselben Eigenheiten wie die echte Quelle:
rechtsbuendig aufgefuellte Werte, Zehntel bei Temperatur und Niederschlag,
Millimeter beim Schnee, leere Felder, das Spurenmengen-Flag und
Flag-Spalten mit unterschiedlich vielen Feldern.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_weather_day as bw


OHARE = "USW00094846"
METRO = "USW00094847"
MIDWAY = "USW00014819"


# --------------------------------------------------------------------------
# Hilfsmittel
# --------------------------------------------------------------------------


def noaa_table(station: str = OHARE, rows: list[dict] | None = None) -> pa.Table:
    """Eine NOAA-Bronze-Tabelle im gepinnten Schema, alles als Text."""
    if rows is None:
        rows = [
            # Werte wie in der Quelle: rechtsbuendig aufgefuellt.
            {"DATE": "2024-01-01", "PRCP": "    0", "PRCP_ATTRIBUTES": ",,0,2400",
             "SNOW": "    0", "SNOW_ATTRIBUTES": ",,0",
             "TMAX": "  214", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": "  103", "TMIN_ATTRIBUTES": ",,0"},
            {"DATE": "2024-01-02", "PRCP": "  1742", "PRCP_ATTRIBUTES": ",,0,2400",
             "SNOW": "  472", "SNOW_ATTRIBUTES": ",,0",
             "TMAX": " -328", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": " -400", "TMIN_ATTRIBUTES": ",,0"},
        ]
    spalten = {
        "STATION": [station] * len(rows),
        "DATE": [r["DATE"] for r in rows],
        "LATITUDE": ["41.96017"] * len(rows),
        "LONGITUDE": ["-87.93164"] * len(rows),
        "ELEVATION": ["204.8"] * len(rows),
        "NAME": [f"AIRPORT {station}"] * len(rows),
        "_extra": [None] * len(rows),
    }
    for name in ("PRCP", "SNOW", "TMAX", "TMIN"):
        spalten[name] = [r.get(name) for r in rows]
        spalten[f"{name}_ATTRIBUTES"] = [r.get(f"{name}_ATTRIBUTES") for r in rows]
    return pa.table({k: pa.array(v, type=pa.string()) for k, v in spalten.items()})


def write_bronze_run(
    data_root: Path,
    station: str,
    table: pa.Table | None = None,
    run_id: str = "run_20260908T120000000000Z",
    status: str = "complete",
) -> Path:
    verzeichnis = (
        data_root / "bronze" / f"dataset={bw.NOAA_DATASET}" / f"station={station}" / run_id
    )
    verzeichnis.mkdir(parents=True)
    pq.write_table(table if table is not None else noaa_table(station),
                   verzeichnis / bw.PARQUET_FILE)
    (verzeichnis / "manifest.json").write_text(
        json.dumps({"status": status, "run_id": run_id}), encoding="utf-8"
    )
    return verzeichnis


def gebaut(tmp_path: Path, stations=(OHARE,), **tabellen):
    data_root = tmp_path / "data"
    for station in stations:
        write_bronze_run(data_root, station, tabellen.get(station))
    ziel = bw.build(data_root, list(stations))
    manifest = json.loads((ziel / "manifest.json").read_text(encoding="utf-8"))
    return ziel, manifest, pq.read_table(ziel / bw.PARQUET_FILE)


def spalte(tabelle, name):
    return tabelle.column(name).to_pylist()


# --------------------------------------------------------------------------
# Granularität und Ablage
# --------------------------------------------------------------------------


def test_grain_is_city_and_day(tmp_path):
    """Eine andere Granularität als die Faktentabelle - deshalb eine eigene Tabelle."""
    _, manifest, tabelle = gebaut(tmp_path)
    assert manifest["grain"] == "eine Stadt an einem Tag"
    assert manifest["join_keys"] == ["city", "date"]
    assert spalte(tabelle, "city") == ["chicago", "chicago"]
    assert manifest["reconciliation"]["city_date_unique"] is True


def test_table_dir_has_no_vintage():
    """Die Reihen wachsen taeglich, es gibt keinen eingefrorenen Jahrgang."""
    assert bw.table_dir(Path("data")) == Path("data") / "silver" / "dataset=weather_day"


def test_two_stations_for_one_city_is_an_error(tmp_path):
    """O'Hare und Midway sind beide Chicago - die Granularität braeche."""
    data_root = tmp_path / "data"
    write_bronze_run(data_root, OHARE)
    write_bronze_run(data_root, MIDWAY)
    with pytest.raises(bw.TransformError, match="Mehr als eine Station je Stadt"):
        bw.build(data_root, [OHARE, MIDWAY])


def test_skipped_station_is_named_in_the_manifest(tmp_path):
    """Ein zugeschaltetes Midway darf nicht stillschweigend verschwinden."""
    data_root = tmp_path / "data"
    write_bronze_run(data_root, OHARE)
    write_bronze_run(data_root, MIDWAY)
    ziel = bw.build(data_root, [OHARE])
    manifest = json.loads((ziel / "manifest.json").read_text(encoding="utf-8"))
    assert [e["station_id"] for e in manifest["skipped_stations"]] == [MIDWAY]
    assert "Absprache 3" in manifest["skipped_stations"][0]["reason"]


def test_two_cities_land_in_one_table(tmp_path):
    _, manifest, tabelle = gebaut(
        tmp_path, stations=(OHARE, METRO), **{METRO: noaa_table(METRO)}
    )
    assert sorted(set(spalte(tabelle, "city"))) == ["chicago", "detroit"]
    assert manifest["row_count"] == 4
    assert len(manifest["coverage"]) == 2


def test_missing_bronze_is_a_clear_error(tmp_path):
    with pytest.raises(bw.TransformError, match="Kein vollstaendiger Bronze-Lauf"):
        bw.build(tmp_path / "data", [OHARE])


def test_incomplete_run_is_ignored(tmp_path):
    data_root = tmp_path / "data"
    write_bronze_run(data_root, OHARE, run_id="run_20260901T120000000000Z")
    write_bronze_run(
        data_root, OHARE, run_id="run_20260908T120000000000Z", status="aborted"
    )
    quelle = bw.newest_bronze_run(data_root, OHARE)
    assert quelle.run_id == "run_20260901T120000000000Z"


def test_manifest_names_every_source_run(tmp_path):
    _, manifest, _ = gebaut(tmp_path)
    assert len(manifest["derived_from"]) == 1
    eintrag = manifest["derived_from"][0]
    assert eintrag["station_id"] == OHARE
    assert eintrag["city"] == "chicago"
    assert eintrag["run_id"].startswith("run_")


# --------------------------------------------------------------------------
# Die Einheiten - der Kern dieser Schicht
# --------------------------------------------------------------------------


def test_temperature_tenths_become_celsius(tmp_path):
    """400 sind 40,0 Grad; -328 sind -32,8 Grad. An Rekorden geprueft."""
    _, _, tabelle = gebaut(tmp_path)
    assert spalte(tabelle, "temp_max_c") == [21.4, -32.8]
    assert spalte(tabelle, "temp_min_c") == [10.3, -40.0]


def test_precipitation_tenths_become_millimetres(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    assert spalte(tabelle, "precipitation_mm") == [0.0, 174.2]


def test_snowfall_is_already_millimetres_and_not_divided(tmp_path):
    """SNOW steht in der Quelle schon in Millimetern, anders als PRCP."""
    _, _, tabelle = gebaut(tmp_path)
    assert spalte(tabelle, "snowfall_mm") == [0.0, 472.0]


def test_padded_text_is_parsed(tmp_path):
    """Die Quelle fuellt rechtsbuendig auf; das darf nicht stoeren."""
    _, _, tabelle = gebaut(
        tmp_path,
        **{OHARE: noaa_table(rows=[{
            "DATE": "2024-01-01", "TMAX": "  214", "TMAX_ATTRIBUTES": ",,0",
            "TMIN": "  103", "TMIN_ATTRIBUTES": ",,0",
            "PRCP": "    5", "PRCP_ATTRIBUTES": ",,0,2400",
            "SNOW": "    0", "SNOW_ATTRIBUTES": ",,0",
        }])},
    )
    assert spalte(tabelle, "temp_max_c") == [21.4]
    assert spalte(tabelle, "precipitation_mm") == [0.5]


# --------------------------------------------------------------------------
# Fehlwerte, Spurenmengen, Beanstandungen
# --------------------------------------------------------------------------


def test_empty_field_becomes_null_not_zero(tmp_path):
    """Kein Messwert ist nicht dasselbe wie kein Regen."""
    _, _, tabelle = gebaut(
        tmp_path,
        **{OHARE: noaa_table(rows=[{
            "DATE": "2024-01-01", "PRCP": None, "PRCP_ATTRIBUTES": None,
            "SNOW": None, "SNOW_ATTRIBUTES": None,
            "TMAX": None, "TMAX_ATTRIBUTES": None,
            "TMIN": None, "TMIN_ATTRIBUTES": None,
        }])},
    )
    assert spalte(tabelle, "precipitation_mm") == [None]
    assert spalte(tabelle, "temp_max_c") == [None]
    flags = tabelle.column("quality_flags")[0].as_py()
    assert "MISSING_PRECIPITATION" in flags
    assert "MISSING_TEMPERATURE" in flags
    assert "MISSING_SNOWFALL" in flags


def test_trace_amount_is_distinguished_from_dry(tmp_path):
    """PRCP = 0 mit Messflag T heisst messbar, aber unter der Auflösung."""
    _, _, tabelle = gebaut(
        tmp_path,
        **{OHARE: noaa_table(rows=[
            {"DATE": "2024-01-01", "PRCP": "    0", "PRCP_ATTRIBUTES": "T,,0,2400",
             "SNOW": "    0", "SNOW_ATTRIBUTES": "T,,0",
             "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0"},
            {"DATE": "2024-01-02", "PRCP": "    0", "PRCP_ATTRIBUTES": ",,0,2400",
             "SNOW": "    0", "SNOW_ATTRIBUTES": ",,0",
             "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0"},
        ])},
    )
    assert spalte(tabelle, "precipitation_mm") == [0.0, 0.0]
    assert spalte(tabelle, "precipitation_trace") == [True, False]
    assert spalte(tabelle, "snowfall_trace") == [True, False]


def test_quality_flag_is_named_not_dropped(tmp_path):
    """O'Hare hat vier SNOW-Zeilen mit Q-Flag I - beanstandet, nicht entfernt."""
    _, manifest, tabelle = gebaut(
        tmp_path,
        **{OHARE: noaa_table(rows=[{
            "DATE": "1999-01-09", "PRCP": "    0", "PRCP_ATTRIBUTES": ",,0,2400",
            "SNOW": "    0", "SNOW_ATTRIBUTES": "T,I,0,",
            "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
            "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0",
        }])},
    )
    assert "SUSPECT_SNOWFALL" in tabelle.column("quality_flags")[0].as_py()
    assert spalte(tabelle, "snowfall_mm") == [0.0], "der Wert bleibt erhalten"
    assert manifest["coverage"][0]["suspect_rows"] == 1


def test_attribute_field_count_is_not_assumed(tmp_path):
    """Drei Felder bei TMAX, vier bei PRCP, drei bei Detroits SNOW."""
    _, _, tabelle = gebaut(
        tmp_path,
        **{OHARE: noaa_table(rows=[{
            "DATE": "2024-01-01",
            "PRCP": "   10", "PRCP_ATTRIBUTES": "T,,1,null",   # vier Felder, obs 'null'
            "SNOW": "    0", "SNOW_ATTRIBUTES": ",,Z",          # drei Felder
            "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
            "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0",
        }])},
    )
    # Das vierte Feld 'null' darf nicht als Qualitaetsflag gelesen werden.
    assert tabelle.column("quality_flags")[0].as_py() == []
    assert spalte(tabelle, "precipitation_trace") == [True]
    assert spalte(tabelle, "precipitation_mm") == [1.0]


def test_clean_day_has_no_flags(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    assert tabelle.column("quality_flags")[0].as_py() == []


def test_extra_column_is_not_carried_over(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    assert "_extra" not in tabelle.schema.names


def test_date_becomes_a_date(tmp_path):
    _, _, tabelle = gebaut(tmp_path)
    assert str(tabelle.schema.field("date").type) == "date32[day]"


# --------------------------------------------------------------------------
# Nachweis und Abdeckung
# --------------------------------------------------------------------------


def test_reconciliation_matches_bronze_row_count(tmp_path):
    _, manifest, _ = gebaut(tmp_path)
    nachweis = manifest["reconciliation"]
    assert nachweis["verified"] is True
    assert nachweis["bronze_rows"] == nachweis["row_count"] == 2
    assert nachweis["rows_without_date"] == 0


def test_coverage_counts_gaps_in_the_daily_series(tmp_path):
    """Die Reihe soll taeglich sein; fehlende Tage werden ausgewiesen."""
    _, manifest, _ = gebaut(
        tmp_path,
        **{OHARE: noaa_table(rows=[
            {"DATE": "2024-01-01", "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0",
             "PRCP": "    0", "PRCP_ATTRIBUTES": ",,0,2400",
             "SNOW": "    0", "SNOW_ATTRIBUTES": ",,0"},
            # 02. und 03. fehlen
            {"DATE": "2024-01-04", "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0",
             "PRCP": "    0", "PRCP_ATTRIBUTES": ",,0,2400",
             "SNOW": "    0", "SNOW_ATTRIBUTES": ",,0"},
        ])},
    )
    abdeckung = manifest["coverage"][0]
    assert abdeckung["row_count"] == 2
    assert abdeckung["expected_days"] == 4
    assert abdeckung["missing_days"] == 2


def test_coverage_reports_the_project_timeframe_separately(tmp_path):
    """Die Reihe ist vor 1970 lueckenhaft - fuer das Projekt zaehlt ab 2001."""
    _, manifest, _ = gebaut(
        tmp_path,
        **{OHARE: noaa_table(rows=[
            {"DATE": "1950-01-01", "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0",
             "PRCP": "    0", "PRCP_ATTRIBUTES": ",,0,2400",
             "SNOW": "    0", "SNOW_ATTRIBUTES": ",,0"},
            {"DATE": "2024-01-01", "TMAX": "  100", "TMAX_ATTRIBUTES": ",,0",
             "TMIN": "   50", "TMIN_ATTRIBUTES": ",,0",
             "PRCP": "    0", "PRCP_ATTRIBUTES": ",,0,2400",
             "SNOW": "    0", "SNOW_ATTRIBUTES": ",,0"},
        ])},
    )
    ab = manifest["coverage"][0]["since_cutoff"]
    assert ab["cutoff"] == bw.COVERAGE_CUTOFF
    assert ab["row_count"] == 1
    # Gemessen wird die Dichte im Fenster, nicht der Abstand zum Stichtag.
    # Dass die Reihe im Fenster erst 2024 beginnt, verraet first_date.
    assert ab["first_date"] == "2024-01-01"
    assert ab["missing_days"] == 0
    # Ueber die ganze Reihe klafft die Luecke von 1950 bis 2024.
    assert manifest["coverage"][0]["missing_days"] > 20_000


def test_manifest_explains_the_units(tmp_path):
    """Silver soll die Einheit nennen, damit Gold sie nicht raten muss."""
    _, manifest, _ = gebaut(tmp_path)
    assert "Zehnteln" in manifest["notes"]["units"]
    assert "vier Tagen Nachlauf" in manifest["notes"]["source_lag"]


# --------------------------------------------------------------------------
# Ersetzen statt anhaeufen
# --------------------------------------------------------------------------


def test_rebuild_replaces_instead_of_accumulating(tmp_path):
    data_root = tmp_path / "data"
    write_bronze_run(data_root, OHARE)
    erst = bw.build(data_root, [OHARE])
    zweit = bw.build(data_root, [OHARE])
    assert erst == zweit
    assert sorted(p.name for p in zweit.iterdir()) == ["manifest.json", bw.PARQUET_FILE]
    assert not list(zweit.parent.glob(".*"))


def test_failed_rebuild_keeps_the_previous_table(tmp_path):
    """Ein Fehler darf den vorhandenen Stand nicht zerstoeren."""
    data_root = tmp_path / "data"
    write_bronze_run(data_root, OHARE)
    ziel = bw.build(data_root, [OHARE])
    vorher = (ziel / bw.PARQUET_FILE).read_bytes()

    write_bronze_run(data_root, MIDWAY)
    with pytest.raises(bw.TransformError):
        bw.build(data_root, [OHARE, MIDWAY])

    assert (ziel / bw.PARQUET_FILE).read_bytes() == vorher
    assert not list(ziel.parent.glob(".*"))
