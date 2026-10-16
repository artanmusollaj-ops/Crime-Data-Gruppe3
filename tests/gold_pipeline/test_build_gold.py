"""Tests fuer die Gold-Schicht.

Gold macht drei Dinge, die schiefgehen koennen, ohne dass es auffaellt:

1. Es ordnet Tracts einer Stadt zu. Eine falsche Regel aendert jeden Nenner.
2. Es legt Fremdschluessel zwischen Fakten und Dimensionen. Ein verwaister
   Schluessel laesst ein Dashboard Faelle verlieren, ohne zu scheitern.
3. Es schreibt die Faktentabelle um. Dabei kann eine Zeile verlorengehen.

Genau darauf zielen diese Tests. Sie laufen ohne Netz; die Silver-Quellen
werden als kleine Parquet-Dateien zur Laufzeit erzeugt.
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_gold as bg
from gold_pipeline import (
    GATE_HOECHSTENS, GATE_MINDESTENS, STADT_SCHLUESSEL, TABELLEN,
)
# Statt einer vierten Fassung: manifeste, serving.pruefe_stand und
# storage.release rechnen dasselbe SHA-256 schon.
from manifeste import datei_hash
from silver_pipeline import TransformError, connect


PROJECT_ROOT = Path(__file__).resolve().parents[2]
# Das Referenz-Vintage dieser Tests. Seit Vertrag 6 nimmt dim_tract_query es
# entgegen, weil die Stadtzuordnung sagen muss, aus welchem Jahrgang sie kommt.
VINTAGE = 2024
CHICAGO = "1714000"
DETROIT = "2622000"


def wkb_rechteck(x0: float, y0: float, breite: float, hoehe: float) -> bytes:
    punkte = [
        (x0, y0), (x0 + breite, y0), (x0 + breite, y0 + hoehe),
        (x0, y0 + hoehe), (x0, y0),
    ]
    return (
        struct.pack("<BII", 1, 3, 1)
        + struct.pack("<I", len(punkte))
        + b"".join(struct.pack("<dd", a, b) for a, b in punkte)
    )


# --------------------------------------------------------------------------
# Kleine Silver-Quellen
# --------------------------------------------------------------------------


def schreibe(tmp_path: Path, name: str, table: pa.Table) -> bg.Quelle:
    pfad = tmp_path / f"{name}.parquet"
    pq.write_table(table, pfad)
    return bg.Quelle(name, pfad)


def tract_quelle(tmp_path: Path, tracts, name: str = "tract") -> bg.Quelle:
    """tracts: (geoid, population, geometrie).

    ``name`` trennt mehrere Vintages: Seit Vertrag 6 liest Gold ``silver/tract``
    je Vintage, und zwei Quellen brauchen zwei Dateien.
    """
    n = len(tracts)
    return schreibe(tmp_path, name, pa.table({
        "geoid": pa.array([t[0] for t in tracts]),
        "state_fips": pa.array([t[0][:2] for t in tracts]),
        "state_name": pa.array(["illinois"] * n),
        "county_fips": pa.array([t[0][2:5] for t in tracts]),
        "tract_code": pa.array([t[0][5:] for t in tracts]),
        "name": pa.array([f"Census Tract {t[0][-4:]}" for t in tracts]),
        "land_area_m2": pa.array([100_000] * n, type=pa.int64()),
        "water_area_m2": pa.array([0] * n, type=pa.int64()),
        "centroid_lat": pa.array([41.8] * n, type=pa.float64()),
        "centroid_lon": pa.array([-87.6] * n, type=pa.float64()),
        "geometry": pa.array([t[2] for t in tracts], pa.binary()),
        "population": pa.array([t[1] for t in tracts], type=pa.int64()),
        "median_household_income_usd": pa.array([70_000] * n, type=pa.int64()),
        "population_below_poverty": pa.array([100] * n, type=pa.int64()),
        "poverty_rate": pa.array([0.05] * n, type=pa.float64()),
        "quality_flags": pa.array([[]] * n, pa.list_(pa.string())),
    }))


def place_quelle(tmp_path: Path) -> bg.Quelle:
    """Chicago als Quadrat von (0,0) bis (10,10); Detroit weit daneben."""
    return schreibe(tmp_path, "place", pa.table({
        "geoid": pa.array([CHICAGO, DETROIT]),
        "state_fips": pa.array(["17", "26"]),
        "state_name": pa.array(["illinois", "michigan"]),
        "place_fips": pa.array(["14000", "22000"]),
        "name": pa.array(["Chicago", "Detroit"]),
        "name_long": pa.array(["Chicago city", "Detroit city"]),
        "lsad_code": pa.array(["25", "25"]),
        "lsad_text": pa.array(["city", "city"]),
        "class_code": pa.array(["C5", "C5"]),
        "land_area_m2": pa.array([1, 1], type=pa.int64()),
        "water_area_m2": pa.array([0, 0], type=pa.int64()),
        "centroid_lat": pa.array([41.8, 42.3], type=pa.float64()),
        "centroid_lon": pa.array([-87.6, -83.0], type=pa.float64()),
        "geometry": pa.array(
            [wkb_rechteck(0, 0, 10, 10), wkb_rechteck(100, 100, 10, 10)],
            pa.binary(),
        ),
        "quality_flags": pa.array([[], []], pa.list_(pa.string())),
    }))


def offense_quelle(tmp_path: Path, zeilen) -> bg.Quelle:
    """zeilen: (offense_id, city, tag, nibrs_code, tract_geoid).

    Optional als sechstes Element ``counts``; ohne Angabe zaehlt die Zeile.
    Silver haelt jede Anklage und markiert je Tat eine als zaehlend - Gold
    nimmt nur diese, sonst waere Detroit um 3,8 Prozent zu hoch gezaehlt.

    Optional als siebtes und achtes Element ``mapping_status`` und
    ``source_offense_code``; ohne Angabe ``exact`` und ``0110``. Gebraucht
    werden beide nur von der Zuordnungsabdeckung je Jahrgang (FR-38) -
    ueberall sonst ist die Vorgabe gemeint, und eine Vorrichtung, die sie
    verlangte, waere in hundert Tests Rauschen.
    """
    def wahl(z, i, vorgabe):
        return z[i] if len(z) > i else vorgabe

    n = len(zeilen)
    return schreibe(tmp_path, "crime_offense", pa.table({
        "city": pa.array([z[1] for z in zeilen]),
        "offense_id": pa.array([z[0] for z in zeilen]),
        "event_id": pa.array([z[0] for z in zeilen]),
        "occurred_at_utc": pa.array(
            [datetime.combine(z[2], datetime.min.time()) for z in zeilen],
            pa.timestamp("us"),
        ),
        "occurred_at_local": pa.array(
            [datetime.combine(z[2], datetime.min.time()).replace(hour=14) for z in zeilen],
            pa.timestamp("us"),
        ),
        "occurred_date_local": pa.array([z[2] for z in zeilen], pa.date32()),
        # Seit Vertrag 2 fuehrt Silver die beiden Zeitzonen-Randfaelle; Gold
        # nimmt local_time_ambiguous mit, weil dort hour_of_day gerechnet wird.
        "local_time_ambiguous": pa.array([False] * n),
        "local_time_nonexistent": pa.array([False] * n),
        "source_offense_code": pa.array([wahl(z, 7, "0110") for z in zeilen]),
        "source_offense_description": pa.array(["TEST"] * n),
        "nibrs_code": pa.array([z[3] for z in zeilen]),
        "nibrs_description": pa.array(["Test"] * n),
        "nibrs_group": pa.array(["A"] * n),
        "crime_against": pa.array(["Person"] * n),
        "nibrs_match": pa.array(["nibrs_definition"] * n),
        "nibrs_mapped": pa.array([True] * n),
        "mapping_status": pa.array([wahl(z, 6, "exact") for z in zeilen]),
        "latitude": pa.array([41.8] * n, pa.float64()),
        "longitude": pa.array([-87.6] * n, pa.float64()),
        "tract_geoid": pa.array([z[4] for z in zeilen]),
        "located": pa.array([True] * n),
        "arrest": pa.array([False] * n),
        "unfounded": pa.array([False] * n),
        "dataset": pa.array(["crime_offense"] * n),
        "offense_group_id": pa.array([z[0] for z in zeilen]),
        "counts": pa.array([z[5] if len(z) > 5 else True for z in zeilen]),
        "counts_reason": pa.array(
            ["eine_zeile_ist_ein_delikt" if (len(z) < 6 or z[5])
             else "weitere_anklage_zur_selben_tat" for z in zeilen]),
        # Jede Zeile ist hier ihr eigener Fall: Fallebene gleich Tatebene.
        "counts_case": pa.array([z[5] if len(z) > 5 else True for z in zeilen]),
    }))


def weather_quelle(tmp_path: Path, tage) -> bg.Quelle:
    n = len(tage)
    return schreibe(tmp_path, "weather_day", pa.table({
        "city": pa.array(["chicago"] * n),
        "date": pa.array(tage, pa.date32()),
        "station_id": pa.array(["USW00094846"] * n),
        "station_name": pa.array(["CHICAGO OHARE"] * n),
        "temp_max_c": pa.array([20.0] * n, pa.float64()),
        "temp_min_c": pa.array([10.0] * n, pa.float64()),
        "precipitation_mm": pa.array([0.0] * n, pa.float64()),
        "snowfall_mm": pa.array([0.0] * n, pa.float64()),
        "precipitation_trace": pa.array([False] * n),
        "snowfall_trace": pa.array([False] * n),
        "quality_flags": pa.array([[]] * n, pa.list_(pa.string())),
        "dataset": pa.array(["weather_day"] * n),
    }))


@pytest.fixture
def con():
    verbindung = connect(spatial=True)
    yield verbindung
    verbindung.close()


# --------------------------------------------------------------------------
# Die Mehrheitsregel
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "breite_innen,erwartet,anteil",
    [
        (1.0, "chicago", 1.0),    # ganz in der Stadt
        (0.6, "chicago", 0.6),    # mehrheitlich drin
        (0.5, None, 0.5),         # genau halb - die Schwelle ist ausschliessend
        (0.4, None, 0.4),         # mehrheitlich draussen
        (0.0, None, 0.0),         # gar nicht drin
    ],
)
def test_stadtzuordnung_folgt_der_mehrheitsregel(
    con, tmp_path, breite_innen, erwartet, anteil
):
    """Ein Tract der Breite 1 liegt mit ``breite_innen`` innerhalb Chicagos.

    Chicago reicht bis x = 10. Der Tract beginnt bei x = 10 - breite_innen und
    ist eine Einheit breit; sein Anteil ist damit genau ``breite_innen``.
    """
    tract = tract_quelle(tmp_path, [
        ("17031010100", 1000, wkb_rechteck(10 - breite_innen, 1, 1.0, 1.0)),
    ])
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path), VINTAGE)}"
    )
    stadt, gemessen = con.execute(
        "SELECT city, city_area_share FROM d"
    ).fetchone()
    assert stadt == erwartet
    assert gemessen == pytest.approx(anteil, abs=1e-9)


def test_der_flaechenanteil_bleibt_auch_unterhalb_der_schwelle(con, tmp_path):
    """Wer flaechengewichtet rechnen will, braucht ihn - auch wo city NULL ist."""
    tract = tract_quelle(tmp_path, [
        ("17031010100", 1000, wkb_rechteck(9.7, 1, 1.0, 1.0)),
    ])
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path), VINTAGE)}"
    )
    stadt, anteil = con.execute("SELECT city, city_area_share FROM d").fetchone()
    assert stadt is None
    assert anteil == pytest.approx(0.3)


def test_jeder_tract_steht_genau_einmal(con, tmp_path):
    """Auch wenn er zwei Stadtgrenzen beruehrt, darf er sich nicht verdoppeln."""
    tract = tract_quelle(tmp_path, [
        ("17031010100", 1000, wkb_rechteck(1, 1, 2, 2)),
        ("17031010200", 2000, wkb_rechteck(50, 50, 2, 2)),
    ])
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path), VINTAGE)}"
    )
    assert con.execute("SELECT count(*) FROM d").fetchone()[0] == 2
    assert con.execute(
        "SELECT count(*) FROM (SELECT geoid FROM d GROUP BY geoid HAVING count(*) > 1)"
    ).fetchone()[0] == 0


def test_ein_tract_ausserhalb_beider_staedte_bleibt_erhalten(con, tmp_path):
    """Er faellt aus dem Nenner, nicht aus der Tabelle."""
    tract = tract_quelle(tmp_path, [
        ("17031010200", 2000, wkb_rechteck(50, 50, 2, 2)),
    ])
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path), VINTAGE)}"
    )
    zeile = con.execute(
        "SELECT geoid, city, city_area_share, reference_vintage FROM d"
    ).fetchone()
    assert zeile == ("17031010200", None, 0.0, VINTAGE)


# --------------------------------------------------------------------------
# dim_offense
# --------------------------------------------------------------------------


def test_dim_offense_traegt_die_amtliche_liste(tmp_path):
    zeilen = bg.dim_offense_rows(PROJECT_ROOT / "config")
    amtlich = [z for z in zeilen if not z["retired"]]
    assert len(amtlich) == 81
    nach_code = {z["nibrs_code"]: z for z in zeilen}
    assert nach_code["13A"]["nibrs_description"] == "Aggravated Assault"
    assert nach_code["13A"]["nibrs_family"] == "13"
    assert nach_code["23C"]["nibrs_family"] == "23"
    assert nach_code["90Z"]["nibrs_group"] == "B"


def test_zurueckgezogene_codes_stehen_drin_und_sind_gekennzeichnet(tmp_path):
    """Ohne sie verloere ein Filter ueber die Dimension 1'019 Delikte."""
    nach_code = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}
    for code in ("90A", "90I"):
        assert code in nach_code, f"{code} fehlt - er kommt in den Falldaten vor"
        assert nach_code[code]["retired"] is True
        assert nach_code[code]["nibrs_description"], f"{code} ohne Bezeichnung"
    assert nach_code["90Z"]["retired"] is False
    assert nach_code["90Z"]["resolution"] == "current"


def test_jeder_zurueckgezogene_code_sagt_was_er_heute_bedeutet(tmp_path):
    """"Zurueckgezogen" allein ist keine Auskunft.

    Wer eine Zeitreihe ueber mehrere Jahrgaenge legt oder nach einem Delikt
    filtert, muss wissen, wohin ein gestrichener Code heute zeigt - sonst
    uebersieht ein Filter auf 26A genau die Faelle, die frueher 90A hiessen.
    """
    nach_code = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}
    erlaubt = {"current", "replaced", "reclassified", "not_an_offense", "unresolved"}
    for code, zeile in nach_code.items():
        assert zeile["resolution"] in erlaubt, f"{code}: {zeile['resolution']}"
        if zeile["retired"]:
            assert zeile["retirement_note"], f"{code} ohne Begruendung"
        if zeile["resolution"] in {"replaced", "reclassified"}:
            assert zeile["replaced_by"] in nach_code, (
                f"{code} zeigt auf {zeile['replaced_by']}, den es nicht gibt"
            )
        else:
            assert zeile["replaced_by"] is None


def test_bad_checks_loest_sich_belegt_auf(tmp_path):
    """Der Beleg ist die ILCS-Tabelle, nicht eine Vermutung."""
    nach_code = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}
    zeile = nach_code["90A"]
    assert zeile["resolution"] == "replaced"
    assert zeile["replaced_by"] == "26A"
    assert "17-1(B)" in zeile["retirement_note"], (
        "die Notiz muss das Statut nennen, auf das sich die Aufloesung stuetzt"
    )


def test_runaway_ist_keine_tat_und_sagt_das(tmp_path):
    """Ein Code ohne Nachfolger ist aufgeloest, wenn der Grund dasteht."""
    zeile = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}["90I"]
    assert zeile["resolution"] == "not_an_offense"
    assert zeile["replaced_by"] is None
    assert "Not a Crime" in zeile["retirement_note"], (
        "die Notiz muss den FBI-Beleg nennen, nicht eine Herleitung"
    )


def test_die_familie_bleibt_das_kuerzel(tmp_path):
    """Sie ist ein technischer Schluessel, keine Gliederung."""
    zeilen = bg.dim_offense_rows(PROJECT_ROOT / "config")
    assert all(z["nibrs_family"] == z["nibrs_code"][:2] for z in zeilen)
    assert "nibrs_family_description" not in zeilen[0], (
        "die Familie bekommt keinen Namen - dafuer ist nibrs_category da"
    )


def test_jeder_code_hat_genau_eine_kategorie(tmp_path):
    nach_code = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}
    ohne = sorted(c for c, z in nach_code.items() if not z["nibrs_category"])
    assert not ohne, f"Codes ohne Kategorie: {ohne}"


def test_die_kategorie_ist_nicht_die_familie(tmp_path):
    """Genau die vier Stellen, an denen das Praefix in die Irre fuehrt.

    Sie sind der Grund, warum das Handbuch gelesen wird statt left(code, 2)
    genommen: Waeren Familie und Kategorie dasselbe, braeuchte es die Datei
    nicht.
    """
    nach_code = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}

    def kat(code):
        return nach_code[code]["nibrs_category"]

    # Eine Kategorie, zwei Familien
    assert kat("11A") == kat("36A") == "Sex Offenses"
    # Eine Kategorie, drei Familien
    assert kat("58A") == kat("61A") == kat("620") == "Commerce Violations"
    # Eine Familie, drei Kategorien
    assert kat("100") == "Kidnapping/Abduction"
    assert kat("101") == "Treason"
    assert kat("103") == "Espionage"
    # Group B hat keinen Sammelnamen fuer die Familie 90
    neunzig = {kat(c) for c in nach_code if c.startswith("90")}
    assert len(neunzig) > 5, f"Familie 90 sollte viele Kategorien haben: {neunzig}"


def test_das_handbuch_nennt_28_und_10(tmp_path):
    """Die Zahlen, die das Handbuch ueber sich selbst sagt."""
    zeilen = [z for z in bg.dim_offense_rows(PROJECT_ROOT / "config") if not z["retired"]]
    a = {z["nibrs_category"] for z in zeilen if z["nibrs_group"] == "A"}
    b = {z["nibrs_category"] for z in zeilen if z["nibrs_group"] == "B"}
    assert len(a) == 28, f"{len(a)} Group-A-Kategorien"
    assert len(b) == 10, f"{len(b)} Group-B-Kategorien"
    assert sum(1 for z in zeilen if z["nibrs_group"] == "A") == 71


def test_die_zurueckgezogenen_behalten_ihre_kategorie_von_2011(tmp_path):
    """Das Handbuch 2025 kennt sie nicht mehr; die Codeliste 2011 schon.

    Die Kategorie kommt aus derselben CSV wie alle anderen - die Datei sagt je
    Zeile, welches Dokument sie belegt. Gold kennt die vier Codes nicht
    namentlich und muss es auch nicht.
    """
    nach_code = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}
    assert nach_code["90A"]["nibrs_category"] == "Bad Checks"
    assert nach_code["90I"]["nibrs_category"] == "Runaway"


def test_11b_und_11c_werden_auf_11a_umgeschluesselt(tmp_path):
    """Nicht zurueckgezogen, aber beim Veroeffentlichen zusammengefasst.

    Wer sie in einer Auswertung stehen laesst, zaehlt anders als das FBI - bei
    uns sind das 205 Faelle aus Detroit.
    """
    nach_code = {z["nibrs_code"]: z for z in bg.dim_offense_rows(PROJECT_ROOT / "config")}
    for code in ("11B", "11C"):
        zeile = nach_code[code]
        assert zeile["retired"] is False, f"{code} ist meldbar, nicht zurueckgezogen"
        assert zeile["resolution"] == "reclassified"
        assert zeile["replaced_by"] == "11A"
        assert "2023" in zeile["retirement_note"], (
            f"{code}: die Notiz muss die Fassung nennen, ab der das gilt"
        )
    assert nach_code["11A"]["resolution"] == "current"


def test_in_der_echten_dimension_ist_jeder_genutzte_code_aufloesbar(con):
    """Gegen die gebaute Schicht, nicht nur gegen die Liste im Code."""
    fakt, dim = gold("fact_offense"), gold("dim_offense")
    if fakt is None or dim is None:
        pytest.skip("keine gebaute Gold-Schicht vorhanden")
    offen = con.execute(
        f"SELECT d.nibrs_code, count(*) FROM read_parquet('{fakt}') f "
        f"JOIN read_parquet('{dim}') d ON d.nibrs_code = f.nibrs_code "
        "WHERE d.retired AND d.resolution = 'unresolved' GROUP BY 1"
    ).fetchall()
    assert not offen, f"zurueckgezogen und ungeloest, aber in den Daten: {offen}"


def test_fehlende_codeliste_wird_gemeldet(tmp_path):
    with pytest.raises(TransformError, match="Codeliste fehlt"):
        bg.dim_offense_rows(tmp_path)


# --------------------------------------------------------------------------
# dim_date und dim_city_day
# --------------------------------------------------------------------------


def test_dim_date_traegt_denselben_typ_wie_die_fakten(con, tmp_path):
    """generate_series liefert TIMESTAMP; der Schluessel muss DATE sein.

    Sonst haengt der Join zwischen Fakt und Dimension an einer
    stillschweigenden Typumwandlung - und die geht irgendwann nicht mehr gut.
    """
    offense = offense_quelle(tmp_path, [
        ("a", "chicago", date(2024, 1, 1), "13A", "17031010100"),
    ])
    con.execute(f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_date_query(offense)}")
    typen = {z[0]: z[1] for z in con.execute("DESCRIBE SELECT * FROM d").fetchall()}
    assert typen["date"] == "DATE"
    assert typen["month_start"] == "DATE"


def test_dim_date_enthaelt_auch_tage_ohne_delikt(con, tmp_path):
    """Sonst zeigt eine Zeitreihe eine Luecke als Nicht-Ereignis."""
    offense = offense_quelle(tmp_path, [
        ("a", "chicago", date(2024, 1, 1), "13A", "17031010100"),
        ("b", "chicago", date(2024, 1, 5), "13A", "17031010100"),
    ])
    con.execute(f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_date_query(offense)}")
    tage = [z[0] for z in con.execute("SELECT date FROM d ORDER BY date").fetchall()]
    assert tage == [date(2024, 1, d) for d in range(1, 6)]


def test_dim_date_kennt_wochenende_und_monat(con, tmp_path):
    offense = offense_quelle(tmp_path, [
        ("a", "chicago", date(2024, 6, 8), "13A", "17031010100"),
    ])
    con.execute(f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_date_query(offense)}")
    zeile = con.execute(
        "SELECT year, month, quarter, day_name, is_weekend, month_start FROM d"
    ).fetchone()
    assert zeile[0] == 2024 and zeile[1] == 6 and zeile[2] == 2
    assert zeile[3] == "Saturday" and zeile[4] is True
    assert zeile[5] == date(2024, 6, 1)


def test_dim_city_day_wird_auf_die_spanne_beschnitten(con, tmp_path):
    """Die Wetterquelle reicht bis 1942 zurueck."""
    offense = offense_quelle(tmp_path, [
        ("a", "chicago", date(2024, 1, 2), "13A", "17031010100"),
        ("b", "chicago", date(2024, 1, 4), "13A", "17031010100"),
    ])
    weather = weather_quelle(tmp_path, [
        date(1980, 5, 1), date(2024, 1, 1), date(2024, 1, 3), date(2024, 1, 9),
    ])
    con.execute(
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_city_day_query(weather, offense)}"
    )
    tage = [z[0] for z in con.execute("SELECT date FROM d ORDER BY date").fetchall()]
    assert tage == [date(2024, 1, 3)]


# --------------------------------------------------------------------------
# fact_offense und der Nachweis
# --------------------------------------------------------------------------


# Ein Detroiter Tract gehoert in jede Vorrichtung: ``reconcile`` verlangt, dass
# beide Studienstaedte Tracts haben - eine Stadtgrenze, die keinen einzigen
# trifft, macht jeden Nenner wertlos. Detroit liegt bei (100,100).
DETROIT_TRACT = ("26163500100", 700, wkb_rechteck(101, 101, 2, 2))


def baue(con, tmp_path, zeilen, tracts=None):
    """Legt alle sechs Relationen an, wie ``build`` es tut."""
    tracts = list(tracts or [("17031010100", 1000, wkb_rechteck(1, 1, 2, 2))])
    if not any(t[0].startswith("26") for t in tracts):
        tracts.append(DETROIT_TRACT)
    offense = offense_quelle(tmp_path, zeilen)
    tract = tract_quelle(tmp_path, tracts)
    place = place_quelle(tmp_path)
    weather = weather_quelle(tmp_path, [z[2] for z in zeilen])
    con.execute(
        "CREATE OR REPLACE TABLE dim_tract AS "
        + bg.dim_tract_query(tract, place, VINTAGE)
    )
    con.execute(
        "CREATE OR REPLACE TABLE dim_tract_acs AS "
        + bg.dim_tract_acs_query({VINTAGE: tract})
    )
    con.execute(
        "CREATE OR REPLACE TABLE dim_offense (nibrs_code VARCHAR, nibrs_description VARCHAR, "
        "nibrs_category VARCHAR, nibrs_family VARCHAR, nibrs_group VARCHAR, "
        "crime_against VARCHAR, federal_only BOOLEAN, retired BOOLEAN, "
        "replaced_by VARCHAR, resolution VARCHAR, retirement_note VARCHAR)"
    )
    con.executemany(
        "INSERT INTO dim_offense VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [tuple(z.values()) for z in bg.dim_offense_rows(PROJECT_ROOT / "config")],
    )
    con.execute(f"CREATE OR REPLACE TABLE dim_date AS {bg.dim_date_query(offense)}")
    con.execute(
        f"CREATE OR REPLACE TABLE dim_city_day AS {bg.dim_city_day_query(weather, offense)}"
    )
    con.execute(f"CREATE OR REPLACE TABLE fact_offense AS {bg.fact_offense_query(offense)}")
    return offense


def test_das_granularitaet_bleibt_erhalten(con, tmp_path):
    """Gold aggregiert nicht - eine Zeile je Delikt, auch bei gleichem Tag und Code."""
    zeilen = [
        (f"id{i}", "chicago", date(2024, 3, 1), "13A", "17031010100")
        for i in range(7)
    ]
    baue(con, tmp_path, zeilen)
    assert con.execute("SELECT count(*) FROM fact_offense").fetchone()[0] == 7


def test_die_deliktfamilie_liegt_in_der_faktentabelle(con, tmp_path):
    baue(con, tmp_path, [("a", "chicago", date(2024, 3, 1), "23C", "17031010100")])
    assert con.execute("SELECT nibrs_family FROM fact_offense").fetchone()[0] == "23"


def test_die_stunde_kommt_aus_der_ortszeit(con, tmp_path):
    baue(con, tmp_path, [("a", "chicago", date(2024, 3, 1), "13A", "17031010100")])
    assert con.execute("SELECT hour_of_day FROM fact_offense").fetchone()[0] == 14


def test_der_nachweis_geht_durch(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
        ("b", "chicago", date(2024, 3, 2), "23C", "17031010100"),
    ])
    nachweis = bg.reconcile(con, offense, VINTAGE)
    assert nachweis["verified"] is True
    assert nachweis["fact_rows"] == nachweis["silver_rows"] == 2
    assert nachweis["orphan_keys"] == {"dim_offense": 0, "dim_tract": 0, "dim_date": 0}


def test_eine_verlorene_zeile_faellt_auf(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
        ("b", "chicago", date(2024, 3, 2), "23C", "17031010100"),
    ])
    con.execute("DELETE FROM fact_offense WHERE offense_id = 'b'")
    with pytest.raises(TransformError, match="silver/crime_offense"):
        bg.reconcile(con, offense, VINTAGE)


def test_ein_verwaister_deliktschluessel_faellt_auf(con, tmp_path):
    """Genau der Fehler, der beim ersten Bau 1'019 Delikte gekostet haette."""
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
    ])
    con.execute("DELETE FROM dim_offense WHERE nibrs_code = '13A'")
    with pytest.raises(TransformError, match="dim_offense"):
        bg.reconcile(con, offense, VINTAGE)


def test_ein_ungeloester_code_in_den_daten_laesst_den_bau_scheitern(con, tmp_path):
    """Die Zusage in einem Satz: Was in den Daten steht, muss auflösbar sein."""
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "90E", "17031010100"),
    ])
    with pytest.raises(TransformError, match="ohne Aufloesung"):
        bg.reconcile(con, offense, VINTAGE)


def test_ein_aufgeloester_code_in_den_daten_geht_durch(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "90A", "17031010100"),
        ("b", "chicago", date(2024, 3, 2), "90I", "17031010100"),
    ])
    nachweis = bg.reconcile(con, offense, VINTAGE)
    assert nachweis["retired_codes"]["90A"]["replaced_by"] == "26A"
    assert nachweis["retired_codes"]["90A"]["offenses"] == 1
    assert nachweis["retired_codes"]["90I"]["resolution"] == "not_an_offense"


def test_eine_fehlende_begruendung_faellt_auf(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
    ])
    con.execute("UPDATE dim_offense SET retirement_note = NULL WHERE retired")
    with pytest.raises(TransformError, match="ohne Begruendung"):
        bg.reconcile(con, offense, VINTAGE)


def test_ein_verwaister_tract_faellt_auf(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
    ])
    con.execute("DELETE FROM dim_tract")
    with pytest.raises(TransformError, match="dim_tract"):
        bg.reconcile(con, offense, VINTAGE)


def test_ohne_zugeordnete_tracts_scheitert_der_bau(con, tmp_path):
    """Eine Stadtgrenze, die keinen Tract trifft, macht jeden Nenner wertlos."""
    offense = baue(
        con, tmp_path,
        [("a", "chicago", date(2024, 3, 1), "13A", "17031010200")],
        tracts=[("17031010200", 2000, wkb_rechteck(50, 50, 2, 2))],
    )
    with pytest.raises(TransformError, match="Keine Tracts der Stadt zugeordnet"):
        bg.reconcile(con, offense, VINTAGE)


def test_der_nachweis_misst_die_randfaelle(con, tmp_path):
    """Faelle in Tracts ohne Stadt sind kein Fehler, aber sie gehoeren gezaehlt."""
    offense = baue(
        con, tmp_path,
        [
            ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
            ("b", "chicago", date(2024, 3, 2), "13A", "17031010300"),
        ],
        tracts=[
            ("17031010100", 1000, wkb_rechteck(1, 1, 2, 2)),
            ("17031010300", 500, wkb_rechteck(9.7, 1, 1.0, 1.0)),
        ],
    )
    nachweis = bg.reconcile(con, offense, VINTAGE)
    assert nachweis["offenses_whose_tract_belongs_to_no_study_city"] == 1
    assert nachweis["city_assignment"]["chicago"]["population"] == 1000


# --------------------------------------------------------------------------
# Gegen die gebaute Gold-Schicht, wenn sie vorliegt
# --------------------------------------------------------------------------


def gold(name: str) -> Path | None:
    pfad = PROJECT_ROOT / "data" / "gold" / f"dataset={name}" / "part-0001.parquet"
    return pfad if pfad.exists() else None


def test_die_echte_stadtzuordnung_trifft_die_amtliche_einwohnerzahl(con):
    """Die Probe aufs Exempel: Detroit ist amtlich 639'111 Einwohner gross.

    Die Regel ist eine Naeherung - Tracts ueberschreiten Stadtgrenzen. Sie waere
    aber wertlos, wenn sie um zweistellige Prozentsaetze danebenlaege; die naive
    Variante "alle beruehrten Tracts" tut genau das (Detroit 884'691).
    """
    pfad = gold("dim_tract")
    acs = gold("dim_tract_acs")
    if pfad is None or acs is None:
        pytest.skip("keine gebaute Gold-Schicht vorhanden")
    # Seit Vertrag 6 steht die Einwohnerzahl in dim_tract_acs, je Vintage.
    # Verbunden wird ueber geoid UND vintage - ohne das zweite Praedikat
    # summiert diese Abfrage jeden Tract so oft, wie Vintages geladen sind.
    einwohner = dict(
        con.execute(
            f"SELECT d.city, sum(a.population) FROM read_parquet('{pfad}') d "
            f"JOIN read_parquet('{acs}') a "
            "  ON a.geoid = d.geoid AND a.vintage = d.reference_vintage "
            "WHERE d.city IS NOT NULL GROUP BY d.city"
        ).fetchall()
    )
    assert set(einwohner) == set(STADT_SCHLUESSEL.values())
    # Zensus 2020: Chicago 2'746'388, Detroit 639'111. Der ACS schaetzt
    # niedriger als der Zensus zaehlt, deshalb eine einseitige Spanne.
    assert 2_400_000 < einwohner["chicago"] < 2_800_000
    assert 580_000 < einwohner["detroit"] < 660_000


def test_in_der_echten_schicht_zeigt_kein_schluessel_ins_leere(con):
    fakt, dim_o, dim_t, dim_d = (
        gold("fact_offense"), gold("dim_offense"), gold("dim_tract"), gold("dim_date")
    )
    if None in (fakt, dim_o, dim_t, dim_d):
        pytest.skip("keine gebaute Gold-Schicht vorhanden")
    for name, pfad, spalte in (
        ("dim_offense", dim_o, "nibrs_code"),
        ("dim_tract", dim_t, "geoid"),
        ("dim_date", dim_d, "date"),
    ):
        quell_spalte = "date" if name == "dim_date" else (
            "nibrs_code" if name == "dim_offense" else "tract_geoid"
        )
        verwaist = con.execute(
            f"SELECT count(*) FROM read_parquet('{fakt}') f "
            f"LEFT JOIN read_parquet('{pfad}') d ON d.{spalte} = f.{quell_spalte} "
            f"WHERE f.{quell_spalte} IS NOT NULL AND d.{spalte} IS NULL"
        ).fetchone()[0]
        assert verwaist == 0, f"{verwaist} Zeilen zeigen auf keine Zeile in {name}"


def test_die_echte_faktentabelle_traegt_das_tatebene(con):
    """Gold zaehlt Taten, Silver haelt Anklagen.

    Detroits Zeilen sind Anklagen, Chicagos sind Delikte. Waere Gold auf
    Anklageebene, stuende Detroit um 3,8 Prozent zu hoch in jedem Vergleich.
    """
    fakt = gold("fact_offense")
    silber = PROJECT_ROOT / "data" / "silver" / "dataset=crime_offense" / "part-0001.parquet"
    if fakt is None or not silber.exists():
        pytest.skip("keine gebaute Gold-Schicht vorhanden")
    a = con.execute(f"SELECT count(*) FROM read_parquet('{fakt}')").fetchone()[0]
    b, zaehlend = con.execute(
        f"SELECT count(*), count(*) FILTER (WHERE counts) FROM read_parquet('{silber}')"
    ).fetchone()
    assert a == zaehlend, "Gold nimmt genau die zaehlenden Zeilen"
    assert a < b, "und es sind weniger als alle - sonst greift die Auswahl nicht"
    doppelt = con.execute(
        f"SELECT count(*) FROM (SELECT offense_group_id FROM read_parquet('{fakt}') "
        "WHERE offense_group_id IS NOT NULL GROUP BY 1 HAVING count(*) > 1)"
    ).fetchone()[0]
    assert doppelt == 0, f"{doppelt} Taten stehen mehrfach in Gold"


def test_eine_nicht_zaehlende_zeile_kommt_nicht_nach_gold(con, tmp_path):
    """Die Auswahl aus Silver muss in Gold ankommen."""
    offense = offense_quelle(tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100", True),
        ("b", "chicago", date(2024, 3, 1), "23C", "17031010100", False),
    ])
    con.execute("CREATE OR REPLACE TABLE leere_tracts AS SELECT NULL::VARCHAR AS geoid, NULL::VARCHAR AS city WHERE false")
    con.execute("CREATE OR REPLACE TABLE fo AS "
                + bg.fact_offense_query(offense, "leere_tracts"))
    ids = [z[0] for z in con.execute("SELECT offense_id FROM fo").fetchall()]
    assert ids == ["a"]


def test_dim_offense_nennt_seine_referenzdateien(tmp_path):
    """Die Dimension, die die Deliktklassifikation traegt, braucht eine Herkunft.

    Ihr ``derived_from`` war lange **leer** - ausgerechnet bei der Tabelle, die
    entscheidet, was in beiden Staedten als welches Delikt zaehlt. Die uebrigen
    vier Gold-Tabellen nannten ihre Silver-Quellen korrekt; diese fiel durch,
    weil sie nicht aus Silver kommt, sondern aus zwei Dateien unter ``config/``.
    """
    quellen = bg.referenzquellen(Path("config"))
    namen = {q.name for q in quellen}
    assert namen == {bg.NIBRS_CODES, bg.NIBRS_KATEGORIEN}
    assert {q.layer for q in quellen} == {"config"}, (
        "sonst behauptet das Manifest, die Dateien kaemen aus Silver"
    )


def test_das_manifest_uebernimmt_die_schicht_der_quelle(con, tmp_path):
    """Vorher stand in jeder Zeile 'silver', unabhaengig von der Wahrheit."""
    con.execute("CREATE OR REPLACE TABLE leer AS SELECT 1 AS x")
    # Die Referenzdatei traegt seit dem 14.9. ihre Pruefsumme im Manifest -
    # es muss sie also geben.
    (tmp_path / "a.csv").write_text("x\n", encoding="utf-8")
    manifest = bg.build_manifest(
        con, "leer",
        [bg.Quelle("a.csv", tmp_path / "a.csv", layer="config"),
         bg.Quelle("b", tmp_path / "b.parquet")],
        datetime.now(timezone.utc), None, "eine Zeile", {},
    )
    assert [q["layer"] for q in manifest["derived_from"]] == ["config", "silver"]


# --------------------------------------------------------------------------
# Abdeckung und Publish-Gate
# --------------------------------------------------------------------------


def test_geo_status_nennt_den_grund_statt_nur_ja_oder_nein(con, tmp_path):
    """``located`` sagt, *dass* eine Zeile fehlt. ``geo_status`` sagt *warum*.

    Vier Faelle, und sie fuehren zu verschiedenen Schluessen: Ohne Koordinate
    hat die Quelle nichts geliefert; ausserhalb der Stadt hat die
    Mehrheitsregel entschieden. Das erste ist eine Luecke, das zweite eine
    Entscheidung - eine Auswertung darf sie nicht in einen Topf werfen.
    """
    baue(
        con, tmp_path,
        [
            ("drin", "chicago", date(2024, 3, 1), "13A", "17031010100"),
            ("draussen", "chicago", date(2024, 3, 2), "13A", "17031010300"),
            ("kein_tract", "chicago", date(2024, 3, 3), "13A", None),
        ],
        tracts=[
            ("17031010100", 1000, wkb_rechteck(1, 1, 2, 2)),
            ("17031010300", 500, wkb_rechteck(9.7, 1, 1.0, 1.0)),
        ],
    )
    status = dict(con.execute(
        "SELECT offense_id, geo_status FROM fact_offense"
    ).fetchall())
    assert status["drin"] == "inside_city"
    assert status["draussen"] == "outside_city"
    assert status["kein_tract"] == "no_tract"


def test_die_abdeckung_zaehlt_jede_zeile_genau_einmal(con, tmp_path):
    baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
        ("b", "chicago", date(2024, 3, 2), "13A", "17031010100"),
    ])
    anteile = bg.abdeckung(con)
    geo = sum(anteile[w] for w in bg.GEO_STATUS_WERTE)
    zuordnung = sum(anteile[w] for w in bg.MAPPING_STATUS_WERTE)
    assert geo == pytest.approx(100.0, abs=0.01)
    assert zuordnung == pytest.approx(100.0, abs=0.01)


def test_ein_unbekannter_statuswert_laesst_den_bau_stehen(con, tmp_path):
    """Wer die Einstufung aendert, soll es merken - nicht die Kennzahl.

    Ein neuer Wert in ``mapping_status`` wuerde sonst in keiner Gruppierung
    auftauchen, die die bekannten Werte aufzaehlt. Die Zeile verschwaende aus
    der Abdeckung, ohne dass eine Summe sich beklagt.
    """
    baue(con, tmp_path, [("a", "chicago", date(2024, 3, 1), "13A", "17031010100")])
    con.execute("UPDATE fact_offense SET mapping_status = 'halbwegs_sicher'")
    with pytest.raises(TransformError, match="Unbekannte Statuswerte"):
        bg.abdeckung(con)


def test_das_gate_haelt_die_gemessene_abdeckung_aus():
    """Die Schwellen sind Boeden, keine Ziele - der echte Stand muss durchgehen.

    Die Werte sind der Schnappschuss aus Release ``2026-09-21T12-55-05Z`` -
    dem Stand der Abgabe, gebaut auf Commit ``1fc6bba`` mit sauberem
    Arbeitsbaum. Sie sind seit ``2026-09-19T23-05-26Z`` unveraendert. Sie stehen hier als Zahlen und nicht als
    Verweis auf ``release.json``, damit der Test ohne gebaute Daten laeuft.
    """
    gemessen = {
        "inside_city": 97.451, "outside_city": 1.8689,
        "missing_coordinate": 0.6799, "no_tract": 0.0003,
        "exact": 95.4905, "ambiguous": 1.473,
        "fallback_90Z": 3.0356, "unmapped": 0.0009,
    }
    bg.pruefe_gate(gemessen)  # darf nicht werfen


def test_das_gate_faellt_bei_gebrochenem_raeumlichem_join():
    """Der Fall, fuer den es das Gate gibt."""
    kaputt = {"inside_city": 12.0, "exact": 95.49, "unmapped": 0.0}
    with pytest.raises(TransformError, match="inside_city"):
        bg.pruefe_gate(kaputt)


def test_das_gate_faellt_bei_zu_vielen_ohne_zuordnung():
    kaputt = {"inside_city": 97.5, "exact": 90.0, "unmapped": 7.5}
    with pytest.raises(TransformError, match="unmapped"):
        bg.pruefe_gate(kaputt)


def test_die_schwellen_liegen_unter_dem_gemessenen_stand():
    """Ein Gate, das knapp unter dem Ist liegt, wird beim ersten Rot hochgesetzt.

    Deshalb steht hier, wie viel Luft es haben soll: mindestens fuenf
    Prozentpunkte. Wer die Schwelle enger zieht, muss diesen Test anfassen -
    und damit die Entscheidung sichtbar machen.
    """
    assert bg.GATE_MINDESTENS["inside_city"] <= 97.451 - 5
    assert bg.GATE_MINDESTENS["exact"] <= 95.4905 - 5


def test_kein_delikt_landet_in_der_falschen_stadt(con):
    """Die Zusage, auf der jeder Staedtevergleich ruht.

    Die Mehrheitsregel geht den Umweg ueber den Tract: Ein Punkt liegt in einem
    Tract, und der Tract gehoert zu einer Stadt. Dieselbe Frage laesst sich
    **direkt** stellen - Punkt gegen Ortsgrenze, andere Geometrie, andere
    Operation. Das ist die unabhaengige Referenz, die Detroits eigene
    Block-GEOID nicht sein konnte (siehe H7).

    Geprueft wird nur die Richtung, die nicht vorkommen darf: ein Delikt, das
    die Regel Chicago zuschlaegt und das in Detroit liegt, oder umgekehrt. Dass
    die Regel Faelle an der Grenze *ausschliesst*, ist bekannt und in Notebook
    34, Abschnitt 3.2 beziffert - das ist kein Fehler, sondern ihr Preis.
    """
    fakt, dim = gold("fact_offense"), gold("dim_tract")
    platz = (PROJECT_ROOT / "data" / "silver" / "dataset=place" / "vintage=2024"
             / "part-0001.parquet")
    if not (fakt and dim and platz.exists()):
        pytest.skip("Gold oder silver/place nicht gebaut")

    con.execute("INSTALL spatial")
    con.execute("LOAD spatial")
    orte = ", ".join(f"'{g}'" for g in sorted(STADT_SCHLUESSEL))
    paare = ", ".join(f"('{g}','{s}')" for g, s in sorted(STADT_SCHLUESSEL.items()))
    verwechselt = con.execute(f"""
        WITH grenze AS (
            SELECT geoid, ST_GeomFromWKB(geometry) AS geom
            FROM read_parquet('{platz}') WHERE geoid IN ({orte})
        ), stadt(city_geoid, city) AS (VALUES {paare})
        SELECT count(*)
        FROM read_parquet('{fakt}') f
        JOIN read_parquet('{dim}') t ON t.geoid = f.tract_geoid
        JOIN grenze g ON ST_Within(ST_Point(f.longitude, f.latitude), g.geom)
        JOIN stadt s ON s.city_geoid = g.geoid
        WHERE t.city IS NOT NULL AND t.city <> s.city
    """).fetchone()[0]
    assert verwechselt == 0, (
        f"{verwechselt} Delikte liegen in der einen Stadt und sind der anderen "
        "zugeordnet - dann traegt der Staedtevergleich nicht"
    )


def test_fact_offense_traegt_das_fallebene(tmp_path):
    """``counts_case`` kommt unveraendert aus Silver - Gold entscheidet nichts neu."""
    import duckdb
    quelle = offense_quelle(tmp_path, [
        ("a", "chicago", date(2024, 1, 1), "13A", "17031000100"),
        ("b", "detroit", date(2024, 1, 1), "13A", "26163000100", False),
    ])
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE dim_tract AS SELECT '17031000100' AS geoid, 'chicago' AS city")
        zeilen = con.execute(
            "SELECT offense_id, counts_case FROM (" + bg.fact_offense_query(quelle) + ")"
        ).fetchall()
    finally:
        con.close()
    assert zeilen == [("a", True)], "die nicht zaehlende Zeile ist gar nicht in Gold"


# --------------------------------------------------------------------------
# Die Herkunftskette: Gold nennt den Silver-**Stand**
# --------------------------------------------------------------------------


def test_gold_nennt_den_silver_stand_und_dessen_eigene_herkunft():
    """Das schwaechste Glied der Kette, bis zum 14.9.2026.

    Vorher stand hier nur ein Pfad. Wird Silver neu gebaut, zeigt derselbe
    Pfad auf etwas anderes - und nichts am Gold-Manifest verraet es. Jetzt
    ist die Kette im Manifest verschachtelt: Gold nennt Silver, Silver nennt
    seine Bronze-Laeufe.
    """
    quelle = bg.Quelle("crime_offense", "/irgendwo/part-0001.parquet", manifest={
        "built_at_utc": "2026-09-14T08:00:00+00:00",
        "input_fingerprint": "a" * 64,
        "derived_from": {"chicago_bronze_runs": ["run_A", "run_B"]},
    })
    eintrag = bg.herkunft_der_quelle(quelle)
    assert eintrag["layer"] == "silver" and eintrag["table"] == "crime_offense"
    assert eintrag["built_at_utc"] == "2026-09-14T08:00:00+00:00"
    assert eintrag["input_fingerprint"] == "a" * 64
    assert eintrag["derived_from"]["chicago_bronze_runs"] == ["run_A", "run_B"], (
        "die Bronze-Laeufe muessen vom Gold-Manifest aus lesbar sein"
    )


def test_eine_referenzdatei_traegt_ihre_pruefsumme(tmp_path):
    """dim_offense ruht auf zwei CSV unter config/, nicht auf Silver."""
    datei = tmp_path / "codes.csv"
    datei.write_text("nibrs_code\n09A\n", encoding="utf-8")
    eintrag = bg.herkunft_der_quelle(bg.Quelle("codes.csv", datei, layer="config"))
    assert eintrag["layer"] == "config"
    assert len(eintrag["sha256"]) == 64
    assert "built_at_utc" not in eintrag, "eine CSV hat keinen Bauzeitpunkt"


def test_eine_quelle_ohne_manifest_faellt_auf_den_pfad_zurueck():
    """Ein Bestand von vor der Aenderung darf den Bau nicht aufhalten."""
    eintrag = bg.herkunft_der_quelle(bg.Quelle("tract", "/alt/part-0001.parquet"))
    assert eintrag == {"layer": "silver", "table": "tract", "path": "/alt/part-0001.parquet"}


def test_der_verbundschluessel_ist_abgeleitet_nicht_abgeschrieben():
    """Seit dem 14.9.2026 steht die Zuordnung einmal im Projekt.

    Vorher gab es sie zweimal unter demselben Namen ``STUDIENSTAEDTE`` - in
    ``silver_pipeline`` gross, in ``gold_pipeline`` klein. Zwei Dinge, ein
    Name, verschiedene Werte: Wer die falsche importierte, bekam
    stillschweigend etwas anderes, und eine dritte Stadt waere nur an einer
    der beiden Stellen gelandet.

    Jetzt traegt Silver die Tatsache (der amtliche Name, wie TIGER ihn
    schreibt) und Gold leitet den Verbundschluessel ab. Dieser Test haelt die
    Ableitung fest - wer sie wieder abschreibt, faellt durch.
    """
    from silver_pipeline import STUDIENSTAEDTE

    assert set(STADT_SCHLUESSEL) == set(STUDIENSTAEDTE), "dieselben FIPS-Nummern"
    assert STADT_SCHLUESSEL == {
        geoid: name.lower() for geoid, name in STUDIENSTAEDTE.items()
    }
    # Und die Schluessel muessen zu dem passen, was crime_offense in city
    # schreibt - sonst verbindet dim_tract ins Leere.
    assert set(STADT_SCHLUESSEL.values()) == {"chicago", "detroit"}


def test_die_kalendertabelle_traegt_schmale_typen(con, tmp_path):
    """DuckDBs Datumsfunktionen liefern durchweg BIGINT - ohne CAST stuende in
    einer Dimensionstabelle achtmal so viel Platz wie noetig.

    Ein Jahr passt in SMALLINT, alles Uebrige in TINYINT (-128 bis 127):
    Monat 1-12, Quartal 1-4, Tag 1-31, Wochentag 0-6, Tagesnummer 1-366.
    """
    baue(con, tmp_path, [("a", "chicago", date(2024, 3, 1), "13A", "17031010100")])
    typen = dict(con.execute("SELECT column_name, column_type "
                             "FROM (DESCRIBE dim_date)").fetchall())
    assert typen["year"] == "SMALLINT" and typen["day_of_year"] == "SMALLINT"
    for spalte in ("month", "quarter", "day_of_month", "day_of_week"):
        assert typen[spalte] == "TINYINT", spalte


def test_die_tatstunde_ist_ein_tinyint(con, tmp_path):
    """0 bis 23 - dafuer braucht es kein BIGINT, und die Faktentabelle hat
    344'617 Zeilen."""
    baue(con, tmp_path, [("a", "chicago", date(2024, 3, 1), "13A", "17031010100")])
    typen = dict(con.execute("SELECT column_name, column_type "
                             "FROM (DESCRIBE fact_offense)").fetchall())
    assert typen["hour_of_day"] == "TINYINT"


# --------------------------------------------------------------------------
# Das Gate je Stadt (externe Pruefung vom 15.9.2026)
# --------------------------------------------------------------------------


def gate_bestand(con, zeilen: list[tuple[str, str, str, int]]) -> None:
    """``fact_offense`` nur mit den drei Spalten, die das Gate liest."""
    teile = " UNION ALL ".join(
        f"SELECT '{stadt}' AS reporting_city, '{mapping}' AS mapping_status, "
        f"'{geo}' AS geo_status FROM range({n})"
        for stadt, mapping, geo, n in zeilen
    )
    con.execute(f"CREATE OR REPLACE TABLE fact_offense AS {teile}")


def test_eine_grosse_stadt_verdeckt_die_kleine_nicht_mehr(con):
    """Der nachgestellte Befund: 92,5 % gemeinsam, 70 % in Detroit.

    Chicago ist dreimal so gross wie Detroit. Der Gesamtanteil traegt deshalb
    Chicagos Zahl - Detroits Crosswalk haette zu einem Drittel brechen
    koennen, ohne dass das Gate faellt.
    """
    gate_bestand(con, [
        ("chicago", "exact", "inside_city", 750),
        ("detroit", "exact", "inside_city", 175),
        ("detroit", "fallback_90Z", "inside_city", 75),
    ])
    anteile = bg.abdeckung(con)
    je_stadt = bg.abdeckung_je_stadt(con)

    assert anteile["exact"] == 92.5, "der Gesamtanteil haelt die Schwelle"
    assert je_stadt["detroit"]["exact"] == 70.0

    with pytest.raises(TransformError, match="detroit"):
        bg.pruefe_gate(anteile, je_stadt)


def test_ohne_die_staedtezahlen_bleibt_es_beim_gesamtanteil(con):
    """Die Gegenprobe: Der Gesamtanteil allein laesst den Fall weiterhin durch.

    Damit ist belegt, dass die Korrektur an den Staedtezahlen haengt und nicht
    an einer nebenbei verschaerften Schwelle.
    """
    gate_bestand(con, [
        ("chicago", "exact", "inside_city", 750),
        ("detroit", "exact", "inside_city", 175),
        ("detroit", "fallback_90Z", "inside_city", 75),
    ])
    bg.pruefe_gate(bg.abdeckung(con))


def test_beide_staedte_gut_gehen_durch(con):
    gate_bestand(con, [
        ("chicago", "exact", "inside_city", 700),
        ("chicago", "fallback_90Z", "inside_city", 30),
        ("detroit", "exact", "inside_city", 240),
        ("detroit", "fallback_90Z", "inside_city", 10),
    ])
    je_stadt = bg.abdeckung_je_stadt(con)
    assert sorted(je_stadt) == ["chicago", "detroit"]
    bg.pruefe_gate(bg.abdeckung(con), je_stadt)


def test_die_staedtezahlen_stehen_im_nachweis(con):
    """Sonst liesse sich nicht nachlesen, worauf das Gate entschieden hat."""
    gate_bestand(con, [("chicago", "exact", "inside_city", 10)])
    je_stadt = bg.abdeckung_je_stadt(con)
    assert je_stadt["chicago"]["exact"] == 100.0
    assert je_stadt["chicago"]["outside_city"] == 0.0


# --------------------------------------------------------------------------
# Spurenmengen ueberleben bis Gold (Konzept 9.3)
# --------------------------------------------------------------------------


def test_dim_city_day_fuehrt_die_spurenspalten(con, tmp_path):
    """Ein Messwert 0 mit Spurenflag ist nicht trocken.

    NOAA kennt das Flag ``T``: gefallen, aber unter der Aufloesung des
    Geraets. Silver haelt den Unterschied seit jeher; Gold liess beide
    Spalten bis zum 15.9.2026 fallen. Von den 481 Gold-Tagen mit 0 mm
    Niederschlag waren **113 Spurentage**, und der Tabelle war es nicht
    anzusehen. Konzept 9.3 verlangt ausdruecklich, dass sie erhalten bleiben.
    """
    wetter = schreibe(tmp_path, "weather_day", pa.table({
        "city": ["chicago", "chicago", "detroit"],
        "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 1)],
        "station_id": ["S1", "S1", "S2"],
        "station_name": ["OHare", "OHare", "Metro"],
        "temp_max_c": [1.0, 2.0, 3.0],
        "temp_min_c": [-1.0, 0.0, 1.0],
        "precipitation_mm": [0.0, 0.0, 5.0],
        "snowfall_mm": [0.0, 0.0, 0.0],
        "precipitation_trace": [True, False, False],
        "snowfall_trace": [False, True, False],
        "quality_flags": pa.array([[], [], []], type=pa.list_(pa.string())),
    }))
    # Die Abfrage liest von den Falldaten nur die Spanne.
    delikte = schreibe(tmp_path, "crime_offense", pa.table({
        "occurred_date_local": [date(2024, 1, 1), date(2024, 1, 2)],
    }))
    con.execute(
        f"CREATE TABLE dim_city_day AS {bg.dim_city_day_query(wetter, delikte)}"
    )

    spalten = [r[0] for r in con.execute("DESCRIBE dim_city_day").fetchall()]
    for name in ("precipitation_trace", "snowfall_trace"):
        assert name in spalten, f"{name} fehlt in dim_city_day"

    trocken, spuren = con.execute("""
        SELECT count(*) FILTER (precipitation_mm = 0),
               count(*) FILTER (precipitation_mm = 0 AND precipitation_trace)
        FROM dim_city_day
    """).fetchone()
    assert trocken == 2 and spuren == 1, (
        "ein Tag mit 0 mm und Spurenflag muss von einem trockenen "
        "unterscheidbar bleiben"
    )


def test_der_vertrag_steht_auf_drei_seit_den_spurenspalten():
    """Gold deutet etwas anderes als vorher - das gehoert in die Version."""
    assert bg.CONTRACT_VERSION >= 3, (
        "dim_city_day fuehrt seit dem 15.9.2026 zwei Spalten mehr; die "
        "Vertragsversion muss das nennen"
    )



# --------------------------------------------------------------------------
# dim_tract_acs und population_vintage (FR-35)
# --------------------------------------------------------------------------


def acs_quellen(tmp_path, je_vintage: dict[int, int]) -> dict[int, bg.Quelle]:
    """Je Vintage eine Tract-Quelle mit eigener Einwohnerzahl."""
    return {
        vintage: tract_quelle(
            tmp_path,
            [("17031010100", einwohner, wkb_rechteck(1, 1, 2, 2))],
            name=f"tract_{vintage}",
        )
        for vintage, einwohner in je_vintage.items()
    }


def test_jedes_vintage_bringt_seine_eigene_einwohnerzahl(con, tmp_path):
    """Der Grund fuer die ganze Tabelle: eine Zeile je Tract kann nur eine tragen."""
    quellen = acs_quellen(tmp_path, {2021: 900, 2024: 1000})
    con.execute(f"CREATE OR REPLACE TEMP VIEW a AS {bg.dim_tract_acs_query(quellen)}")
    assert con.execute(
        "SELECT vintage, population FROM a ORDER BY vintage"
    ).fetchall() == [(2021, 900), (2024, 1000)]


def test_die_acs_tabelle_steht_aufsteigend_nach_vintage(con, tmp_path):
    quellen = acs_quellen(tmp_path, {2024: 1000, 2021: 900, 2022: 950})
    con.execute(f"CREATE OR REPLACE TEMP VIEW a AS {bg.dim_tract_acs_query(quellen)}")
    vintages = [z[0] for z in con.execute("SELECT vintage FROM a").fetchall()]
    assert vintages == sorted(vintages)


def test_wer_nur_den_tract_verbindet_vervielfacht(con, tmp_path):
    """Die Falle, die diese Tabelle mitbringt - deshalb steht sie im Feldkatalog.

    Vier Vintages und ein Verbund ohne ``vintage`` ergeben die vierfache
    Einwohnerzahl, und das Ergebnis sieht aus wie eine Zahl.
    """
    quellen = acs_quellen(tmp_path, {2021: 900, 2022: 950, 2023: 975, 2024: 1000})
    con.execute(f"CREATE OR REPLACE TEMP VIEW a AS {bg.dim_tract_acs_query(quellen)}")
    con.execute(
        "CREATE OR REPLACE TEMP VIEW d AS "
        + bg.dim_tract_query(quellen[2024], place_quelle(tmp_path), 2024)
    )
    ohne = con.execute(
        "SELECT count(*) FROM d JOIN a ON a.geoid = d.geoid"
    ).fetchone()[0]
    mit = con.execute(
        "SELECT count(*) FROM d JOIN a "
        "ON a.geoid = d.geoid AND a.vintage = d.reference_vintage"
    ).fetchone()[0]
    assert (ohne, mit) == (4, 1)


def test_eine_tat_nennt_das_vintage_ihres_eigenen_jahres(con, tmp_path):
    offense = offense_quelle(tmp_path, [
        ("a", "chicago", date(2022, 3, 1), "13A", "17031010100"),
    ])
    con.execute(
        "CREATE OR REPLACE TABLE dim_tract AS "
        + bg.dim_tract_query(tract_quelle(tmp_path, [DETROIT_TRACT]),
                             place_quelle(tmp_path), 2024)
    )
    con.execute("CREATE OR REPLACE TABLE f AS "
                + bg.fact_offense_query(offense, vintages=(2021, 2022, 2023, 2024)))
    assert con.execute("SELECT population_vintage FROM f").fetchone()[0] == 2022


@pytest.mark.parametrize("jahr, erwartet", [
    (2021, 2021), (2024, 2024),
    # Ab 2025 gibt es kein eigenes Vintage - die Bevoelkerung wird geliehen.
    (2025, 2024), (2026, 2024),
    # Vor der geladenen Spanne: geklammert, damit die Zeile nicht ins Leere zeigt.
    (2019, 2021),
])
def test_das_vintage_wird_auf_die_geladene_spanne_geklammert(
    con, tmp_path, jahr, erwartet
):
    offense = offense_quelle(tmp_path, [
        ("a", "chicago", date(jahr, 3, 1), "13A", "17031010100"),
    ])
    con.execute(
        "CREATE OR REPLACE TABLE dim_tract AS "
        + bg.dim_tract_query(tract_quelle(tmp_path, [DETROIT_TRACT]),
                             place_quelle(tmp_path), 2024)
    )
    con.execute("CREATE OR REPLACE TABLE f AS "
                + bg.fact_offense_query(offense, vintages=(2021, 2022, 2023, 2024)))
    assert con.execute("SELECT population_vintage FROM f").fetchone()[0] == erwartet


def test_keine_tat_zeigt_auf_ein_fehlendes_vintage(con, tmp_path):
    """Der Verbund muss aufgehen, sonst ruht eine Rate auf keinem Nenner."""
    quellen = acs_quellen(tmp_path, {2021: 900, 2022: 950, 2023: 975, 2024: 1000})
    offense = offense_quelle(tmp_path, [
        (f"id{jahr}", "chicago", date(jahr, 3, 1), "13A", "17031010100")
        for jahr in (2021, 2022, 2023, 2024, 2025, 2026)
    ])
    con.execute(f"CREATE OR REPLACE TABLE dim_tract_acs AS {bg.dim_tract_acs_query(quellen)}")
    con.execute(
        "CREATE OR REPLACE TABLE dim_tract AS "
        + bg.dim_tract_query(quellen[2024], place_quelle(tmp_path), 2024)
    )
    con.execute("CREATE OR REPLACE TABLE fact_offense AS "
                + bg.fact_offense_query(offense, vintages=tuple(quellen)))
    verwaist = con.execute(
        "SELECT count(*) FROM fact_offense f LEFT JOIN dim_tract_acs a "
        "  ON a.geoid = f.tract_geoid AND a.vintage = f.population_vintage "
        "WHERE f.tract_geoid IS NOT NULL AND a.geoid IS NULL"
    ).fetchone()[0]
    assert verwaist == 0
    # Und die beiden Jahre ohne eigenes Vintage leihen sich 2024.
    assert con.execute(
        "SELECT count(*) FROM fact_offense WHERE population_vintage = 2024"
    ).fetchone()[0] == 3


def test_ein_zu_neues_vintage_wird_abgelehnt():
    """``--acs-vintages 2025`` gibt es nicht, und das soll es sagen."""
    import argparse
    with pytest.raises(argparse.ArgumentTypeError, match="juengste"):
        bg.acs_vintages("2021,2025")
    assert bg.acs_vintages("2023, 2021,2021") == (2021, 2023)


# --------------------------------------------------------------------------
# Das Teiljahr (FR-37) und die Abdeckung je Jahrgang (FR-39)
# --------------------------------------------------------------------------


def jahrestage(con, tmp_path, tage) -> None:
    """Legt dim_tract, dim_date und fact_offense ueber genau diese Tage an.

    ``dim_tract`` muss dabei sein: ``fact_offense_query`` liest daraus die
    Stadtzuordnung fuer ``geo_status``.
    """
    offense = offense_quelle(tmp_path, [
        (f"id{n}", "chicago", tag, "13A", "17031010100")
        for n, tag in enumerate(tage)
    ])
    con.execute(
        "CREATE OR REPLACE TABLE dim_tract AS "
        + bg.dim_tract_query(
            tract_quelle(tmp_path, [("17031010100", 1000, wkb_rechteck(1, 1, 2, 2))]),
            place_quelle(tmp_path), VINTAGE)
    )
    con.execute(f"CREATE OR REPLACE TABLE dim_date AS {bg.dim_date_query(offense)}")
    con.execute("CREATE OR REPLACE TABLE fact_offense AS "
                + bg.fact_offense_query(offense, vintages=(VINTAGE,)))


def test_ein_ganzer_jahrgang_gilt_als_ganz(con, tmp_path):
    jahrestage(con, tmp_path, [date(2023, 1, 1), date(2023, 7, 1), date(2023, 12, 31)])
    assert con.execute(
        "SELECT DISTINCT year_is_complete FROM dim_date"
    ).fetchall() == [(True,)]


def test_ein_jahrgang_der_im_oktober_endet_ist_nicht_ganz(con, tmp_path):
    """Der Fall 2026: neun Monate, und sie duerfen nicht gegen zwoelf stehen."""
    jahrestage(con, tmp_path, [date(2026, 1, 1), date(2026, 10, 3)])
    assert con.execute(
        "SELECT DISTINCT year_is_complete FROM dim_date"
    ).fetchall() == [(False,)]


def test_ein_jahrgang_dem_der_anfang_fehlt_ist_auch_nicht_ganz(con, tmp_path):
    """Unvollstaendig ist nicht nur "noch nicht zu Ende"."""
    jahrestage(con, tmp_path, [date(2022, 3, 15), date(2022, 12, 31)])
    assert con.execute(
        "SELECT DISTINCT year_is_complete FROM dim_date"
    ).fetchall() == [(False,)]


def test_bei_mehreren_jahrgaengen_ist_nur_der_letzte_offen(con, tmp_path):
    jahrestage(con, tmp_path, [date(2024, 1, 1), date(2025, 6, 1), date(2026, 10, 3)])
    assert dict(con.execute(
        "SELECT year, any_value(year_is_complete) FROM dim_date GROUP BY 1 ORDER BY 1"
    ).fetchall()) == {2024: True, 2025: True, 2026: False}


def test_die_abdeckung_nennt_tage_und_spanne_je_jahrgang(con, tmp_path):
    jahrestage(con, tmp_path, [date(2026, 1, 1), date(2026, 1, 2), date(2026, 3, 5)])
    abdeckung = bg.jahresabdeckung(con)
    assert set(abdeckung) == {"2026"}
    z = abdeckung["2026"]
    assert z["offenses"] == 3
    assert (z["first_date"], z["last_date"]) == ("2026-01-01", "2026-03-05")
    assert z["days_with_offenses"] == 3
    assert z["days_in_year"] == 365
    assert z["complete"] is False


def test_das_schaltjahr_hat_366_tage(con, tmp_path):
    jahrestage(con, tmp_path, [date(2024, 1, 1), date(2024, 12, 31)])
    assert bg.jahresabdeckung(con)["2024"]["days_in_year"] == 366


def test_eine_luecke_mitten_im_jahr_sieht_man_nur_an_den_tagen(con, tmp_path):
    """Die dokumentierte Grenze von ``year_is_complete`` - und warum es FR-39 gibt.

    Die Spalte prueft nur, ob der 1.1. und der 31.12. in der Spanne liegen. Ein
    Jahrgang, dem der halbe Juli fehlt, bleibt dort "ganz". Erst
    ``days_with_offenses`` gegen ``days_in_year`` zeigt es.
    """
    jahrestage(con, tmp_path, [date(2023, 1, 1), date(2023, 12, 31)])
    z = bg.jahresabdeckung(con)["2023"]
    assert z["complete"] is True, "die Spanne schliesst beide Enden ein"
    assert z["days_with_offenses"] == 2 and z["days_in_year"] == 365, (
        "und genau daran sieht man, dass 363 Tage fehlen"
    )


def test_der_nachweis_traegt_die_jahresabdeckung(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
    ])
    nachweis = bg.reconcile(con, offense, VINTAGE)
    assert nachweis["year_coverage"]["2024"]["offenses"] == 1
    assert nachweis["year_coverage"]["2024"]["complete"] is False, (
        "ein einzelner Maerztag deckt 2024 nicht ab"
    )


# --------------------------------------------------------------------------
# Die Zuordnung je Jahrgang (FR-38)
# --------------------------------------------------------------------------
#
# ``abdeckung`` mittelt ueber die ganze Faktentabelle und damit ueber alle
# Jahrgaenge. Ueber sechs davon verschwindet ein schlechter im Mittel der
# uebrigen - dasselbe Argument, mit dem ``abdeckung_je_stadt`` entstand, nur
# auf der Zeitachse. Die Tests folgen der I/O-Matrix von FR-38.


def test_ein_ganz_zugeordneter_jahrgang_hat_nichts_zu_melden(con, tmp_path):
    """Der Normalfall: ein Jahrgang, alles zugeordnet, drei leere Listen."""
    baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
        ("b", "chicago", date(2024, 7, 1), "13A", "17031010100"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    assert set(jahre) == {"2024"}
    z = jahre["2024"]
    assert z["offenses"] == 2
    assert z["exact"] == 100.0
    assert z["unmapped_codes"] == []
    assert z["new_source_codes"] == []
    assert z["retired_source_codes"] == []


def test_ein_schlechter_jahrgang_verschwindet_nicht_mehr_im_mittel(con, tmp_path):
    """Der Fall, um den es FR-38 geht - und er ist kein Gedankenspiel.

    Fuenf gute Jahrgaenge zu 40 Zeilen und ein sechster, in dem zwei von fuenf
    Zeilen unzugeordnet sind: Der Gesamtanteil liegt bei 0,98 Prozent und
    haelt damit ``GATE_HOECHSTENS["unmapped"]`` von 1,0. Der Jahrgang 2026
    liegt bei 40 Prozent. Genau diese Rechnung hat ``abdeckung_je_stadt``
    fuer die Staedte vorgefuehrt; hier ist sie auf der Zeitachse.

    Gemessen wird trotzdem bis zum Ende - ein Nachweis darf auch dann Zahlen
    liefern, wenn sie schlecht aussehen.
    """
    zeilen = [
        (f"g{jahr}-{i}", "chicago", date(jahr, 6, 1), "13A", "17031010100")
        for jahr in range(2021, 2026) for i in range(40)
    ] + [
        ("x1", "chicago", date(2026, 6, 1), "13A", "17031010100", True, "exact", "0110"),
        ("x2", "chicago", date(2026, 6, 2), "13A", "17031010100", True, "exact", "0110"),
        ("x3", "chicago", date(2026, 6, 3), "13A", "17031010100", True, "exact", "0110"),
        ("x4", "chicago", date(2026, 6, 4), "90Z", "17031010100", True, "unmapped", "9998"),
        ("x5", "chicago", date(2026, 6, 5), "90Z", "17031010100", True, "unmapped", "9999"),
    ]
    baue(con, tmp_path, zeilen)

    jahre = bg.zuordnung_je_jahrgang(con)
    assert sorted(jahre) == [str(j) for j in range(2021, 2027)]
    assert jahre["2026"]["offenses"] == 5
    assert jahre["2026"]["unmapped"] == 40.0
    # Und die Codes beim Namen, mit Stadt und Zahl - absteigend.
    assert jahre["2026"]["unmapped_codes"] == [
        {"city": "chicago", "code": "9998", "offenses": 1},
        {"city": "chicago", "code": "9999", "offenses": 1},
    ]
    # Das Mittel, das es bis hierher allein zu sehen gab, bleibt unauffaellig.
    assert bg.abdeckung(con)["unmapped"] < GATE_HOECHSTENS["unmapped"]


def test_der_teuerste_unzugeordnete_code_steht_oben(con, tmp_path):
    """Wer eine Luecke schliesst, faengt beim groessten Posten an."""
    baue(con, tmp_path, [
        ("a", "chicago", date(2024, 6, 1), "90Z", "17031010100", True, "unmapped", "9998"),
        ("b", "chicago", date(2024, 6, 2), "90Z", "17031010100", True, "unmapped", "9999"),
        ("c", "chicago", date(2024, 6, 3), "90Z", "17031010100", True, "unmapped", "9999"),
        ("d", "chicago", date(2024, 6, 4), "90Z", "17031010100", True, "unmapped", "9999"),
    ])
    assert bg.zuordnung_je_jahrgang(con)["2024"]["unmapped_codes"] == [
        {"city": "chicago", "code": "9999", "offenses": 3},
        {"city": "chicago", "code": "9998", "offenses": 1},
    ]


def test_der_unzugeordnete_code_traegt_seine_stadt(con, tmp_path):
    """``1101`` heisst in den beiden Staedten etwas voellig Verschiedenes.

    In Chicagos IUCR ist es *Public Aid Wire/Mail Fraud* und fuehrt auf 26D
    Welfare Fraud, in Detroits MICR *Sexual Penetration Penis/Vagina CSC1* und
    fuehrt auf 11A Rape - nachzulesen in beiden Crosswalks unter diesem Code.
    Sieben Codes stehen in beiden Tabellen. Ohne die Stadt waere eine Zeile
    der Liste deshalb nicht aufloesbar: Der Code allein sagt nicht, in welchem
    Crosswalk er fehlt.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2024, 6, 1), "90Z", "17031010100", True, "unmapped", "1101"),
        ("b", "detroit", date(2024, 6, 2), "90Z", "26163500100", True, "unmapped", "1101"),
    ])
    assert bg.zuordnung_je_jahrgang(con)["2024"]["unmapped_codes"] == [
        {"city": "chicago", "code": "1101", "offenses": 1},
        {"city": "detroit", "code": "1101", "offenses": 1},
    ]


def test_ein_neuer_quellcode_steht_nur_in_seinem_jahrgang(con, tmp_path):
    """IUCR 9999 kommt erst 2026 vor - und nur dort darf es stehen.

    Die Spanne laeuft vom 1.1.2024 bis zum 31.12.2026, damit alle drei
    Jahrgaenge **ganz** sind: Ein Teiljahrgang nimmt am Vergleich nicht teil,
    und dann stuende hier nichts.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2024, 1, 1), "13A", "17031010100", True, "exact", "0110"),
        ("b", "chicago", date(2025, 6, 1), "13A", "17031010100", True, "exact", "0110"),
        ("c", "chicago", date(2026, 6, 1), "13A", "17031010100", True, "exact", "0110"),
        ("d", "chicago", date(2026, 12, 31), "90Z", "17031010100", True, "fallback_90Z", "9999"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    assert jahre["2026"]["new_source_codes"] == [{"city": "chicago", "code": "9999"}]
    for jahr in ("2024", "2025"):
        assert jahre[jahr]["new_source_codes"] == [], jahr
    # Und er gilt nicht gleich wieder als weggefallen.
    assert all(not z["retired_source_codes"] for z in jahre.values())


def test_ein_weggefallener_code_steht_im_jahrgang_seines_wegfalls(con, tmp_path):
    """MICR 2307 bis 2023, danach nicht mehr - gemeldet wird es bei 2024.

    Beide Jahrgaenge liegen ganz in der Spanne (1.1.2023 bis 31.12.2024);
    waere 2024 ein Teiljahrgang, wuerde er nicht verglichen.
    """
    baue(con, tmp_path, [
        ("a", "detroit", date(2023, 1, 1), "13A", "26163500100", True, "exact", "1301"),
        ("b", "detroit", date(2023, 6, 2), "90Z", "26163500100", True, "fallback_90Z", "2307"),
        ("c", "detroit", date(2024, 12, 31), "13A", "26163500100", True, "exact", "1301"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    assert jahre["2024"]["retired_source_codes"] == [
        {"city": "detroit", "code": "2307"}]
    assert jahre["2023"]["retired_source_codes"] == []
    assert jahre["2024"]["new_source_codes"] == []


def test_ein_teiljahrgang_wird_gemeldet_aber_nicht_verglichen(con, tmp_path):
    """Entscheidung 3 von FR-38: Ein Teiljahr gehoert nicht in einen Vergleich.

    2026 endet am 3.10. und ist damit ``year_is_complete = false``. Jeder
    Code, der dort nur **noch nicht** vorkam, waere sonst "weggefallen" - und
    das ist dieselbe Falle, gegen die FR-37 eine Spalte zuvor
    ``year_is_complete`` gesetzt hat. Der Teiljahrgang wird gemeldet (Zahlen
    und unzugeordnete Codes stehen da), aber beide Codelisten bleiben leer.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2025, 1, 1), "13A", "17031010100", True, "exact", "0110"),
        ("b", "chicago", date(2025, 6, 1), "90Z", "17031010100", True, "unmapped", "2307"),
        ("c", "chicago", date(2025, 12, 31), "13A", "17031010100", True, "exact", "0110"),
        ("d", "chicago", date(2026, 10, 3), "13A", "17031010100", True, "exact", "0110"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    # Gemeldet: die Zahlen und der unzugeordnete Code stehen weiter da.
    assert jahre["2026"]["offenses"] == 1
    assert jahre["2026"]["exact"] == 100.0
    # Nicht verglichen: 2307 kam 2025 vor und 2026 nicht - das ist kein
    # Wegfall, sondern ein Jahr, das noch laeuft.
    assert jahre["2026"]["retired_source_codes"] == []
    assert jahre["2026"]["new_source_codes"] == []


def test_nach_einem_teiljahrgang_wird_gegen_den_letzten_ganzen_verglichen(con, tmp_path):
    """Der Teiljahrgang verschiebt den Massstab nicht.

    2026 ist ganz (die Spanne reicht bis zum 31.12.), 2027 ist das Teiljahr.
    Faellt 2027 aus dem Vergleich, muss der Massstab fuer einen spaeteren
    Jahrgang weiter 2026 sein - sonst waere der uebersprungene Jahrgang doch
    wieder der Vergleichspunkt.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2026, 1, 1), "13A", "17031010100", True, "exact", "0110"),
        ("b", "chicago", date(2026, 6, 1), "90Z", "17031010100", True, "fallback_90Z", "2307"),
        ("c", "chicago", date(2026, 12, 31), "13A", "17031010100", True, "exact", "0110"),
        # 2027 bleibt ein Teiljahr: nur ein Tag, und er traegt 2307 nicht.
        ("d", "chicago", date(2027, 3, 1), "13A", "17031010100", True, "exact", "0110"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    assert jahre["2027"]["retired_source_codes"] == []
    assert jahre["2027"]["new_source_codes"] == []
    # Und ``vorher`` steht noch auf 2026, nicht auf dem duennen 2027: Waere es
    # umgesetzt worden, zeigte 2026 selbst eine Bewegung.
    assert jahre["2026"]["new_source_codes"] == []


def test_der_aelteste_jahrgang_hat_keine_neuen_codes(con, tmp_path):
    """Sonst stuende dort das ganze Inventar und sagte nichts.

    Der aelteste Jahrgang hat keinen Vorgaenger. "Alle Codes neu" waere fuer
    Chicago eine Liste von rund 400 Zeilen - und keine Aussage.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2023, 1, 1), "13A", "17031010100", True, "exact", "0110"),
        ("b", "chicago", date(2023, 6, 2), "13A", "17031010100", True, "exact", "0810"),
        ("c", "chicago", date(2024, 6, 1), "13A", "17031010100", True, "exact", "0110"),
        ("d", "chicago", date(2024, 12, 31), "13A", "17031010100", True, "exact", "0810"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    assert jahre["2023"]["new_source_codes"] == []
    assert jahre["2023"]["retired_source_codes"] == []
    # 2024 ist ganz und wird verglichen - die Listen sind leer, weil beide
    # Jahrgaenge dieselben zwei Codes tragen, nicht weil nicht verglichen wird.
    assert jahre["2024"]["new_source_codes"] == []
    assert jahre["2024"]["retired_source_codes"] == []


def test_ein_jahrgang_ohne_taten_teilt_nicht_durch_null(con, tmp_path):
    """``dim_date`` hat die Tage, ``fact_offense`` keine Zeile - 2024 dazwischen.

    Der Jahrgang muss dastehen: Dass ein Jahr in der Spanne liegt und keine
    Tat traegt, ist eine Aussage und keine Luecke, die man weglaesst. Und er
    verschiebt den Codevergleich nicht - sonst stuende jeder Code 2024 als
    weggefallen und 2025 wieder als neu da.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2023, 12, 30), "13A", "17031010100"),
        ("b", "chicago", date(2025, 1, 2), "13A", "17031010100"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    assert set(jahre) == {"2023", "2024", "2025"}
    z = jahre["2024"]
    assert z["offenses"] == 0
    assert [z[w] for w in sorted(bg.MAPPING_STATUS_WERTE)] == [0.0, 0.0, 0.0, 0.0]
    assert z["unmapped_codes"] == []
    assert z["new_source_codes"] == [] and z["retired_source_codes"] == []
    assert jahre["2025"]["new_source_codes"] == []


def test_die_vier_anteile_eines_jahrgangs_summieren_auf_hundert(con, tmp_path):
    """Die vier Werte von ``mapping_status`` zerlegen den Jahrgang vollstaendig.

    Faellt der Test, zaehlt eine Zeile zweimal oder keinmal - etwa weil der
    Nenner aus ``dim_date`` und der Zaehler aus den Fakten kaeme.

    **Ausser bei einem Jahrgang ohne Taten.** Dort ist nichts zu zerlegen, und
    alle vier Anteile stehen auf 0.0 - sie summieren auf 0 und nicht auf 100.
    2025 liegt hier genau dafuer leer zwischen den beiden besetzten
    Jahrgaengen; ohne diese Unterscheidung behauptete der Test etwas Falsches.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2024, 6, 1), "13A", "17031010100", True, "exact", "0110"),
        ("b", "chicago", date(2024, 6, 2), "13A", "17031010100", True, "ambiguous", "0760"),
        ("c", "chicago", date(2024, 6, 3), "90Z", "17031010100", True, "fallback_90Z", "1481"),
        ("d", "chicago", date(2026, 6, 1), "90Z", "17031010100", True, "unmapped", "9999"),
        ("e", "chicago", date(2026, 6, 2), "13A", "17031010100", True, "exact", "0110"),
        ("f", "chicago", date(2026, 6, 3), "13A", "17031010100", True, "exact", "0110"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    assert jahre["2025"]["offenses"] == 0, "2025 muss leer sein, sonst prueft der Test die Haelfte"
    for jahr, z in jahre.items():
        summe = sum(z[wert] for wert in bg.MAPPING_STATUS_WERTE)
        erwartet = 100.0 if z["offenses"] else 0.0
        assert summe == pytest.approx(erwartet, abs=0.01), f"{jahr}: {summe}"


def test_der_nachweis_traegt_die_zuordnung_je_jahrgang(con, tmp_path):
    """``mapping_by_year`` steht neben ``year_coverage``, nicht darin.

    Beim Einjahresbau muss der Jahreswert dem Gesamtanteil entsprechen - tut
    er es nicht, zaehlt eine der beiden Messungen anders, und dann ist nicht
    zu sagen, welche stimmt.
    """
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 6, 1), "13A", "17031010100", True, "exact", "0110"),
        ("b", "chicago", date(2024, 6, 2), "90Z", "17031010100", True, "unmapped", "9999"),
    ])
    nachweis = bg.reconcile(con, offense, VINTAGE)
    jahre = nachweis["mapping_by_year"]
    assert set(jahre) == {"2024"}
    for wert in bg.MAPPING_STATUS_WERTE:
        assert jahre["2024"][wert] == nachweis["coverage_percent"][wert], wert
    assert jahre["2024"]["unmapped_codes"] == [
        {"city": "chicago", "code": "9999", "offenses": 1}]


def schwellenverletzungen(jahre: dict) -> list[tuple]:
    """Welche Jahrgaenge ``GATE_MINDESTENS``/``GATE_HOECHSTENS`` nicht halten.

    ``inside_city`` kommt dabei nie vor: Das ist raeumliche Abdeckung und
    steht in ``geo_status``, nicht in ``mapping_status``. Geprueft wird, was
    dieser Nachweis traegt - deshalb das ``wert in z``.

    **Ein Jahrgang ohne Taten wird uebersprungen.** Dort steht ``exact`` auf
    0.0, und 0.0 liegt unter 85.0 - gemeldet waere eine Verletzung, die es
    nicht gibt. Nichts zugeordnet zu haben ist keine schlechte Zuordnung,
    sondern keine Daten; wer die Luecke sehen will, liest ``year_coverage``.
    """
    verletzt = []
    for jahr, z in sorted(jahre.items()):
        if not z["offenses"]:
            continue
        for wert, boden in GATE_MINDESTENS.items():
            if wert in z and z[wert] < boden:
                verletzt.append((jahr, wert, z[wert], f">= {boden}",
                                 z["unmapped_codes"][:3]))
        for wert, decke in GATE_HOECHSTENS.items():
            if wert in z and z[wert] > decke:
                verletzt.append((jahr, wert, z[wert], f"<= {decke}",
                                 z["unmapped_codes"][:3]))
    return verletzt


def test_jeder_jahrgang_des_gebauten_gold_haelt_die_schwellen():
    """Entscheidung 2 von FR-38: Das Tor bleibt global, der Waechter wird jaehrlich.

    ``pruefe_gate`` haelt den Gesamtanteil und jede Stadt - nicht jeden
    Jahrgang. Das ist Absicht: Ein Bau soll nicht an einem Jahrgang
    scheitern, dessen Daten erst halb geladen sind; ein halber Jahrgang ist
    kein Einsturz. Die Jahreszahlen stehen aber im Manifest, und hier haelt
    sie ein **Test** gegen dieselben Schwellen. Faellt also etwas, scheitert
    die Suite und nicht die Strecke - und erst, wenn die Daten da sind.
    """
    pfad = PROJECT_ROOT / "data" / "gold" / "dataset=fact_offense" / "manifest.json"
    if not pfad.exists():
        pytest.skip("keine gebaute Gold-Schicht vorhanden")
    nachweis = json.loads(pfad.read_text(encoding="utf-8")).get("reconciliation") or {}
    jahre = nachweis.get("mapping_by_year")
    if jahre is None:
        pytest.skip("das gebaute Manifest ist aelter als FR-38 - Gold neu bauen")

    verletzt = schwellenverletzungen(jahre)
    assert not verletzt, (
        f"Jahrgaenge unter der Schwelle (Jahr, Wert, gemessen, verlangt, "
        f"die teuersten unzugeordneten Codes): {verletzt}"
    )


def test_ein_jahrgang_ohne_taten_ist_keine_schwellenverletzung(con, tmp_path):
    """Der Fall, den ``run_all --jahre 2021,2026`` baut.

    ``dim_date`` laeuft durchgehend von 2021 bis 2026; dazwischen liegen vier
    Jahrgaenge mit Tagen und ohne Taten. Deren ``exact`` steht auf 0.0, und
    ohne das Ueberspringen meldete der Waechter vier Verletzungen, die keine
    sind - im **Standardlauf**, denn er traegt keine ``referenzstand``-Marke.
    """
    baue(con, tmp_path, [
        ("a", "chicago", date(2021, 6, 1), "13A", "17031010100", True, "exact", "0110"),
        ("b", "chicago", date(2026, 6, 1), "13A", "17031010100", True, "exact", "0110"),
    ])
    jahre = bg.zuordnung_je_jahrgang(con)
    leer = [j for j, z in jahre.items() if not z["offenses"]]
    assert leer == ["2022", "2023", "2024", "2025"], leer
    assert schwellenverletzungen(jahre) == []


# --------------------------------------------------------------------------
# Die Reihenfolge der Faktentabelle
# --------------------------------------------------------------------------


def test_die_faktentabelle_ist_nach_tag_und_kennung_sortiert(con, tmp_path):
    """Der Waechter, der eine fehlende ``ORDER BY``-Klausel **immer** faengt.

    Der Byte-Vergleich unten tut das nicht: Ohne die Klausel entscheidet der
    Hash-Join, in welcher Reihenfolge die Zeilen fallen, und zwei Laeufe
    stimmen trotzdem haeufig ueberein. Am 4.10.2026 gemessen - sechs Durchgaenge
    ohne die Klausel, **drei gefangen, drei durchgelassen**. Ein Waechter, der
    den Fehler in der Haelfte der Faelle verschweigt, ist der Fall aus
    ``AGENTS.md``: "der Waechter war gruen und wertlos".

    Dieser hier prueft nicht Bytes, sondern die **Eigenschaft**, und die ist
    deterministisch. Die Vorrichtung liefert die Zeilen absichtlich in
    verkehrter Tagesreihenfolge: Ohne ``ORDER BY`` kommt sie so wieder heraus
    und der Test faellt, mit ihr ist sie sortiert. Deshalb traegt er **keine**
    ``referenzstand``-Marke und laeuft bei jedem Push mit - anders als der
    Byte-Vergleich, den der Standardlauf und ``datenlauf.yml`` beide abwaehlen.
    """
    offense = offense_quelle(tmp_path, [
        ("c", "chicago", date(2024, 12, 31), "13A", "17031010100"),
        ("b", "chicago", date(2024, 6, 15), "13A", "17031010100"),
        ("a", "chicago", date(2024, 1, 2), "13A", "17031010100"),
    ])
    con.execute(
        "CREATE OR REPLACE TABLE dim_tract AS "
        + bg.dim_tract_query(
            tract_quelle(tmp_path, [("17031010100", 1000, wkb_rechteck(1, 1, 2, 2))]),
            place_quelle(tmp_path), VINTAGE)
    )
    con.execute("CREATE OR REPLACE TABLE f AS "
                + bg.fact_offense_query(offense, vintages=(VINTAGE,)))
    assert con.execute(
        "SELECT list(offense_id) FROM (SELECT offense_id FROM f)"
    ).fetchone()[0] == ["a", "b", "c"], (
        "fact_offense_query liefert die Zeilen nicht nach date, offense_id - "
        "fehlt der Abfrage das ORDER BY?"
    )
    verkehrt = con.execute("""
        SELECT count(*) FROM (
            SELECT date, offense_id,
                   lag(date) OVER () AS vorher_tag,
                   lag(offense_id) OVER () AS vorher_kennung
            FROM f)
        WHERE vorher_tag IS NOT NULL
          AND (date, offense_id) < (vorher_tag, vorher_kennung)
    """).fetchone()[0]
    assert verkehrt == 0, f"{verkehrt} Uebergaenge laufen rueckwaerts"


# --------------------------------------------------------------------------
# Zweiter Lauf, gleiche Bytes
# --------------------------------------------------------------------------


# Die vier Silber-Tabellen, die ``build`` liest (build_gold.py:1182-1185).
# Fehlt eine, scheitert der Unterprozess mit TransformError - dann soll der
# Waechter ueberspringen und nicht hart fallen.
SILBER_EINGABEN = (
    "dataset=crime_offense/part-0001.parquet",
    f"dataset=tract/vintage={VINTAGE}/part-0001.parquet",
    f"dataset=place/vintage={VINTAGE}/part-0001.parquet",
    "dataset=weather_day/part-0001.parquet",
)


@pytest.mark.referenzstand
def test_ein_zweiter_lauf_liefert_dieselben_bytes(tmp_path):
    """Dieselbe Regel wie bei ``docs/referenz/``, dem Feldkatalog und den Bildern.

    **Nie in einem Prozess.** Zwei Baue in derselben Python-Instanz teilen den
    Hash-Seed und die Threadzahl; sie koennen uebereinstimmen, ohne dass der
    Bau deterministisch ist. Gebaut wird deshalb zweimal als eigener
    Unterprozess - genau so, wie ein Mensch das Modul aufruft.

    Der Befund, den dieser Waechter begleitet: Am 4.10.2026 lagen zwischen zwei
    Laeufen **245'760 von 345'091 Zeilen** von ``fact_offense`` an anderer
    Position, weil ``fact_offense_query`` als einzige Abfrage der Strecke kein
    ``ORDER BY`` hatte.

    **Was dieser Test nicht leistet.** Er faengt eine fehlende Klausel nur in
    etwa der Haelfte der Faelle - gemessen drei von sechs. Dafuer gibt es
    ``test_die_faktentabelle_ist_nach_tag_und_kennung_sortiert``, der
    deterministisch ist und im Standardlauf mitlaeuft. Hier geht es um das,
    was eine Eigenschaftspruefung **nicht** sieht: Nichtbestimmtheit im
    Schreiber selbst, bei gleicher Zeilenfolge. Deshalb bleibt er, und deshalb
    steht hier, was er wert ist.

    ``dim_tract_acs`` wird dabei nur in seiner **Einzel-Vintage-Gestalt**
    geprueft: Gebaut wird ohne ``--acs-vintages``, weil das Silber nur
    ``vintage=2024`` hat. Die Mehr-Vintage-Gestalt ist ein ``UNION ALL`` mit
    eigenem ``ORDER BY`` und hier nicht abgedeckt.

    Gelesen wird das echte Silber ueber einen Symlink, geschrieben in zwei
    eigene Wurzeln unter ``tmp_path``: Ein Test darf messen, nie den
    Arbeitsbaum veraendern. Unter Windows braucht ein Symlink Sonderrechte,
    deshalb laeuft er dort nicht - dieselbe Ueberlegung wie bei den drei
    PDF-Reproduktionen, die nur unter Linux laufen.
    """
    if os.name == "nt":
        pytest.skip("Symlink auf das Silber braucht unter Windows Sonderrechte")
    silber = PROJECT_ROOT / "data" / "silver"
    fehlend = [rel for rel in SILBER_EINGABEN if not (silber / rel).is_file()]
    if fehlend:
        pytest.skip(f"Silber unvollstaendig, es fehlt: {fehlend}")

    staende = []
    for lauf in ("eins", "zwei"):
        wurzel = tmp_path / lauf / "data"
        wurzel.mkdir(parents=True)
        (wurzel / "silver").symlink_to(silber, target_is_directory=True)
        fertig = subprocess.run(
            [sys.executable, "-m", "gold_pipeline.build_gold",
             "--data-root", str(wurzel)],
            capture_output=True, text=True, cwd=PROJECT_ROOT,
            env={**os.environ, "STORAGE_BACKEND": "local"},
        )
        assert fertig.returncode == 0, fertig.stderr[-2000:]
        staende.append({
            name: datei_hash(wurzel / "gold" / f"dataset={name}" / "part-0001.parquet")
            for name in TABELLEN
        })

    eins, zwei = staende
    anders = sorted(name for name in TABELLEN if eins[name] != zwei[name])
    assert not anders, (
        f"diese Gold-Tabellen sind zwischen zwei Laeufen nicht byteweise "
        f"gleich: {anders}. Fehlt der Abfrage ein ORDER BY? "
        f"Erwartet wird gleiche Pruefsumme, siehe NFR-1."
    )


# --------------------------------------------------------------------------
# Der Schlussbericht im S3-Modus (gefunden am 14.10.2026)
# --------------------------------------------------------------------------


def test_der_schlussbericht_liest_ueber_die_ablage_nicht_ueber_den_pfad(
        tmp_path, monkeypatch):
    """``main`` darf das Manifest nicht dort suchen, wo ``build`` es wegraeumt.

    Im S3-Modus publiziert ``build`` jede Tabelle und **entfernt danach die
    lokale Arbeitskopie** - im Protokoll steht je Tabelle *„Local working copy
    removed (STORAGE_BACKEND=s3)"*. ``ziele`` zeigt dann auf eine Datei, die
    es nicht mehr gibt. Bis zum 14.10.2026 las ``main`` genau diesen Pfad und
    beendete jeden Gold-Bau im S3-Modus mit *„Invalid manifest"* und
    Exitcode 1 - obwohl alle sieben Tabellen sauber publiziert waren. Fuer
    ``orchestration.run_all`` war das ein gescheiterter Lauf, und zwar jedes
    Mal.

    Der Test stellt genau das nach: ``build`` liefert einen Pfad auf eine
    Datei, die nicht existiert, die Ablage kennt das Manifest aber. Laeuft
    ``main`` dann durch, fragt es die Ablage; faellt es, fragt es den Pfad.
    """
    weggeraeumt = tmp_path / "gold" / "dataset=fact_offense" / "manifest.json"
    assert not weggeraeumt.exists(), "der Pfad muss ins Leere zeigen"

    inhalt = {
        "reconciliation": {
            "city_assignment": {"chicago": {"tracts": 2, "population": 7}},
            "offenses_in_a_tract": 5,
            "offenses_whose_tract_belongs_to_no_study_city": 1,
        }
    }
    in_der_ablage = tmp_path / "ablage-manifest.json"
    in_der_ablage.write_text(json.dumps(inhalt), encoding="utf-8")

    gefragt: list = []

    class Ablage:
        """Eine Ablage, deren lokale Kopie weg ist - wie nach s3-Publikation."""

        local_root = tmp_path

        def tabellen_manifest(self, ziel):
            gefragt.append(ziel)
            return json.loads(in_der_ablage.read_text(encoding="utf-8"))

    monkeypatch.setattr(bg, "for_root", lambda *a, **k: Ablage())
    monkeypatch.setattr(bg, "build", lambda *a, **k: {
        "fact_offense": weggeraeumt})
    monkeypatch.setattr(sys, "argv", ["build_gold"])

    assert bg.main() == 0, "der Schlussbericht hat den weggeraeumten Pfad gelesen"
    assert gefragt == [weggeraeumt], (
        "die Ablage wurde nicht nach der Tabelle gefragt: " + repr(gefragt))
