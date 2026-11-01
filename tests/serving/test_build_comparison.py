"""Tests fuer die vier Vergleichstabellen in Serving.

Sie laufen ohne Netz und ohne die echten Daten: ``gold/fact_offense`` und
``gold/dim_offense`` werden zur Laufzeit als kleine Parquet-Dateien erzeugt.

Der Schwerpunkt liegt auf dem, was bei einer Vorberechnung stillschweigend
schieflaeuft: eine Summe, die nicht mehr auf die Faktentabelle aufgeht; eine
Tat ohne Kategorie, die beim Filtern verschwindet; eine Teilwoche, die neben
einer vollen wie ein Einbruch aussieht.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_comparison as bc
from silver_pipeline import TransformError


def schreibe(data_root: Path, tabelle: str, zeilen: dict[str, list]) -> Path:
    ziel = data_root / "gold" / f"dataset={tabelle}"
    ziel.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(zeilen), ziel / bc.PARQUET_FILE)
    (ziel / "manifest.json").write_text(json.dumps({
        "status": "complete", "built_at_utc": "2026-09-17T10:00:00+00:00",
        "input_fingerprint": f"abc-{tabelle}", "derived_from": {},
    }), encoding="utf-8")
    return ziel


def gold(data_root: Path, taten: list[tuple[str, date, str | None, bool]]) -> None:
    """Eine kleine Faktentabelle: (Stadt, Datum, NIBRS-Code, counts_case)."""
    schreibe(data_root, "fact_offense", {
        "offense_id": [f"o{i}" for i in range(len(taten))],
        "reporting_city": [t[0] for t in taten],
        "date": [t[1] for t in taten],
        "nibrs_code": [t[2] for t in taten],
        "nibrs_family": [t[2][:2] if t[2] else None for t in taten],
        "counts_case": [t[3] for t in taten],
        "mapping_status": ["exact" if t[2] else "unmapped" for t in taten],
        "geo_status": ["inside_city"] * len(taten),
        "local_time_ambiguous": [False] * len(taten),
        # Seit Vertrag 2 baut build_comparison auch rate_tract. Die Rate
        # braucht einen Tract und den Zeiger auf ihren Nenner; ohne beides
        # liefe die Abfrage ins Leere, statt zu scheitern.
        "tract_geoid": ["17031010100"] * len(taten),
        "population_vintage": [bc.RATENJAHR] * len(taten),
    })
    schreibe(data_root, "dim_offense", {
        "nibrs_code": ["13A", "23C", "240"],
        "nibrs_category": ["Assault Offenses", "Larceny/Theft Offenses",
                           "Motor Vehicle Theft"],
    })
    schreibe(data_root, "dim_tract_acs", {
        "geoid": ["17031010100"],
        "vintage": [bc.RATENJAHR],
        "population": [1000],
    })


def lies(ziel: Path, tabelle: str) -> list[dict]:
    con = duckdb.connect()
    try:
        pfad = ziel / f"dataset={tabelle}" / bc.PARQUET_FILE
        spalten = [r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{pfad}')").fetchall()]
        return [dict(zip(spalten, r)) for r in
                con.execute(f"SELECT * FROM read_parquet('{pfad}')").fetchall()]
    finally:
        con.close()


# Ein Jahrgang, der an einem Montag beginnt (2024) - und am Dienstag endet.
MO = date(2024, 1, 1)
TATEN = [
    ("chicago", MO, "13A", True),
    ("chicago", MO, "13A", True),
    ("chicago", MO + timedelta(days=1), "23C", True),
    ("chicago", date(2024, 12, 31), "240", True),      # Dienstag: Teilwoche
    ("detroit", MO, "13A", True),
    ("detroit", MO, "13A", False),                      # zweite Anklage, kein Fall
    ("detroit", MO, None, True),                        # unmapped, zaehlt trotzdem
]


# --------------------------------------------------------------------------
# Die Gegenprobe
# --------------------------------------------------------------------------


def test_jede_tabelle_summiert_sich_auf_die_faktentabelle(tmp_path):
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    bc.build(data_root)
    serving = data_root / "serving"
    for tabelle in ("comparison_day", "comparison_week", "comparison_month"):
        zeilen = lies(serving, tabelle)
        assert sum(z["offenses"] for z in zeilen) == 7, tabelle
        assert sum(z["cases"] for z in zeilen) == 6, tabelle


def test_eine_tat_ohne_code_bleibt_zaehlbar(tmp_path):
    """Sie bekommt die Kategorie 'unmapped' - ein Filter auf Kategorie sieht sie."""
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    bc.build(data_root)
    tag = lies(data_root / "serving", "comparison_day")
    unmapped = [z for z in tag if z["nibrs_category"] == "unmapped"]
    assert len(unmapped) == 1 and unmapped[0]["reporting_city"] == "detroit"
    assert unmapped[0]["offenses"] == 1


def test_ein_code_ohne_kategorie_bricht_ab(tmp_path):
    """Der Fall, den eine Kategorie-Summe stillschweigend verloere."""
    data_root = tmp_path / "data"
    gold(data_root, TATEN + [("chicago", MO, "999", True)])
    with pytest.raises(TransformError, match="ohne Kategorie"):
        bc.build(data_root)


# --------------------------------------------------------------------------
# Teilperioden
# --------------------------------------------------------------------------


def test_die_teilwoche_am_jahresende_ist_ausgewiesen(tmp_path):
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    bc.build(data_root)
    wochen = lies(data_root / "serving", "comparison_week")
    letzte = [z for z in wochen if z["week_start"] == date(2024, 12, 30)]
    assert letzte, "die Woche ab 30.12. fehlt"
    assert letzte[0]["days_in_period"] == 7
    assert letzte[0]["days_in_window"] == 2, "30.12. bis 31.12. sind zwei Tage im Fenster"
    erste = {z["reporting_city"]: z for z in wochen if z["week_start"] == MO}
    assert erste["chicago"]["days_in_window"] == 7
    # Seit Vertrag 3 je Stadt: Detroits Daten liegen hier nur am 1.1., also
    # ist seine erste Woche eine Teilwoche mit einem Tag (C-10).
    assert erste["detroit"]["days_in_window"] == 1


def test_der_monat_kennt_seine_laenge(tmp_path):
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    bc.build(data_root)
    monate = {z["month"]: z for z in lies(data_root / "serving", "comparison_month")}
    assert monate[date(2024, 1, 1)]["days_in_period"] == 31
    assert monate[date(2024, 12, 1)]["days_in_period"] == 31
    assert monate[date(2024, 12, 1)]["days_in_window"] == 31, (
        "das Fenster reicht bis 31.12., der Dezember ist ganz drin"
    )


def test_das_fenster_gilt_je_stadt(tmp_path):
    """C-10: Endet eine Stadt frueher, ist ihr letzter Monat eine Teilperiode.

    Bis Vertrag 2 rechnete ``days_in_window`` am gemeinsamen Fenster beider
    Staedte. Chicagos Daten endeten am 26.9.2026, Detroits am 4.10. - und
    Chicagos September hiess vollstaendig, obwohl vier Tage fehlten.
    """
    data_root = tmp_path / "data"
    gold(data_root, [
        ("chicago", date(2026, 8, 1), "13A", True),
        ("chicago", date(2026, 9, 26), "13A", True),
        ("detroit", date(2026, 8, 1), "13A", True),
        ("detroit", date(2026, 10, 4), "13A", True),
    ])
    bc.build(data_root)
    monate = {(z["reporting_city"], z["month"]): z
              for z in lies(data_root / "serving", "comparison_month")}
    assert monate[("chicago", date(2026, 9, 1))]["days_in_window"] == 26
    assert monate[("chicago", date(2026, 9, 1))]["days_in_period"] == 30
    assert monate[("detroit", date(2026, 10, 1))]["days_in_window"] == 4
    assert monate[("chicago", date(2026, 8, 1))]["days_in_window"] == 31


def test_das_manifest_zaehlt_die_teilperioden(tmp_path):
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    ziele = bc.build(data_root)
    manifest = json.loads((ziele["comparison_week"] / "manifest.json").read_text())
    # Chicagos Woche ab 30.12. und - seit Vertrag 3, je Stadt - Detroits
    # erste Woche und sein Januar: Detroits Daten liegen nur am 1.1. Mit dem
    # gemeinsamen Fenster bis Vertrag 2 waren es eine Woche und kein Monat.
    assert manifest["checks"]["partial_periods"] == {"comparison_week": 2,
                                                     "comparison_month": 1}


# --------------------------------------------------------------------------
# Manifest und Herkunft
# --------------------------------------------------------------------------


def test_das_manifest_nennt_gold_als_herkunft(tmp_path):
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    ziele = bc.build(data_root)
    manifest = json.loads((ziele["comparison_day"] / "manifest.json").read_text())
    assert manifest["layer"] == "serving"
    assert manifest["contract_version"] == bc.CONTRACT_VERSION
    assert set(manifest["derived_from"]) == {
        "gold_fact_offense", "gold_dim_offense", "gold_dim_tract_acs"}
    assert manifest["derived_from"]["gold_fact_offense"]["input_fingerprint"] == "abc-fact_offense"
    assert manifest["checks"]["per_city"]["chicago"] == {"offenses": 4, "cases": 4}
    assert "additiv" in manifest["notes"] and "keine_achse" in manifest["notes"]


def test_partition_quality_traegt_die_anteile(tmp_path):
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    bc.build(data_root)
    q = {(z["reporting_city"], z["month"]): z
         for z in lies(data_root / "serving", "partition_quality")}
    detroit = q[("detroit", date(2024, 1, 1))]
    assert detroit["offenses"] == 3
    assert detroit["share_unmapped"] == pytest.approx(33.33, abs=0.01)
    assert detroit["share_inside_city"] == 100.0


def test_ohne_gold_ein_klarer_fehler(tmp_path):
    with pytest.raises(TransformError, match="build_gold"):
        bc.build(tmp_path / "data")


def test_neubau_ersetzt_statt_anzuhaeufen(tmp_path):
    data_root = tmp_path / "data"
    gold(data_root, TATEN)
    bc.build(data_root)
    bc.build(data_root)
    assert len(list((data_root / "serving").glob("dataset=comparison_day/*"))) == 2
    assert not list((data_root / "serving").glob(".*"))
