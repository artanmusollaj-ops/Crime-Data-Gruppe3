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

import struct
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_gold as bg
from gold_pipeline import STADT_SCHLUESSEL
from silver_pipeline import TransformError, connect


PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


def tract_quelle(tmp_path: Path, tracts) -> bg.Quelle:
    """tracts: (geoid, population, geometrie)."""
    n = len(tracts)
    return schreibe(tmp_path, "tract", pa.table({
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
    """
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
        "source_offense_code": pa.array(["0110"] * n),
        "source_offense_description": pa.array(["TEST"] * n),
        "nibrs_code": pa.array([z[3] for z in zeilen]),
        "nibrs_description": pa.array(["Test"] * n),
        "nibrs_group": pa.array(["A"] * n),
        "crime_against": pa.array(["Person"] * n),
        "nibrs_match": pa.array(["nibrs_definition"] * n),
        "nibrs_mapped": pa.array([True] * n),
        "mapping_status": pa.array(["exact"] * n),
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
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path))}"
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
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path))}"
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
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path))}"
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
        f"CREATE OR REPLACE TEMP VIEW d AS {bg.dim_tract_query(tract, place_quelle(tmp_path))}"
    )
    zeile = con.execute("SELECT geoid, city, city_area_share, population FROM d").fetchone()
    assert zeile == ("17031010200", None, 0.0, 2000)


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
    """Legt alle fuenf Relationen an, wie ``build`` es tut."""
    tracts = list(tracts or [("17031010100", 1000, wkb_rechteck(1, 1, 2, 2))])
    if not any(t[0].startswith("26") for t in tracts):
        tracts.append(DETROIT_TRACT)
    offense = offense_quelle(tmp_path, zeilen)
    tract = tract_quelle(tmp_path, tracts)
    place = place_quelle(tmp_path)
    weather = weather_quelle(tmp_path, [z[2] for z in zeilen])
    con.execute(f"CREATE OR REPLACE TABLE dim_tract AS {bg.dim_tract_query(tract, place)}")
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
    nachweis = bg.reconcile(con, offense)
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
        bg.reconcile(con, offense)


def test_ein_verwaister_deliktschluessel_faellt_auf(con, tmp_path):
    """Genau der Fehler, der beim ersten Bau 1'019 Delikte gekostet haette."""
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
    ])
    con.execute("DELETE FROM dim_offense WHERE nibrs_code = '13A'")
    with pytest.raises(TransformError, match="dim_offense"):
        bg.reconcile(con, offense)


def test_ein_ungeloester_code_in_den_daten_laesst_den_bau_scheitern(con, tmp_path):
    """Die Zusage in einem Satz: Was in den Daten steht, muss auflösbar sein."""
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "90E", "17031010100"),
    ])
    with pytest.raises(TransformError, match="ohne Aufloesung"):
        bg.reconcile(con, offense)


def test_ein_aufgeloester_code_in_den_daten_geht_durch(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "90A", "17031010100"),
        ("b", "chicago", date(2024, 3, 2), "90I", "17031010100"),
    ])
    nachweis = bg.reconcile(con, offense)
    assert nachweis["retired_codes"]["90A"]["replaced_by"] == "26A"
    assert nachweis["retired_codes"]["90A"]["offenses"] == 1
    assert nachweis["retired_codes"]["90I"]["resolution"] == "not_an_offense"


def test_eine_fehlende_begruendung_faellt_auf(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
    ])
    con.execute("UPDATE dim_offense SET retirement_note = NULL WHERE retired")
    with pytest.raises(TransformError, match="ohne Begruendung"):
        bg.reconcile(con, offense)


def test_ein_verwaister_tract_faellt_auf(con, tmp_path):
    offense = baue(con, tmp_path, [
        ("a", "chicago", date(2024, 3, 1), "13A", "17031010100"),
    ])
    con.execute("DELETE FROM dim_tract")
    with pytest.raises(TransformError, match="dim_tract"):
        bg.reconcile(con, offense)


def test_ohne_zugeordnete_tracts_scheitert_der_bau(con, tmp_path):
    """Eine Stadtgrenze, die keinen Tract trifft, macht jeden Nenner wertlos."""
    offense = baue(
        con, tmp_path,
        [("a", "chicago", date(2024, 3, 1), "13A", "17031010200")],
        tracts=[("17031010200", 2000, wkb_rechteck(50, 50, 2, 2))],
    )
    with pytest.raises(TransformError, match="Keine Tracts der Stadt zugeordnet"):
        bg.reconcile(con, offense)


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
    nachweis = bg.reconcile(con, offense)
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
    if pfad is None:
        pytest.skip("keine gebaute Gold-Schicht vorhanden")
    einwohner = dict(
        con.execute(
            f"SELECT city, sum(population) FROM read_parquet('{pfad}') "
            "WHERE city IS NOT NULL GROUP BY city"
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
    """Die Schwellen sind Boeden, keine Ziele - der echte Stand muss durchgehen."""
    gemessen = {
        "inside_city": 97.55, "outside_city": 1.87,
        "missing_coordinate": 0.58, "no_tract": 0.0,
        "exact": 95.49, "ambiguous": 1.48,
        "fallback_90Z": 3.03, "unmapped": 0.0009,
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
    assert bg.GATE_MINDESTENS["inside_city"] <= 97.55 - 5
    assert bg.GATE_MINDESTENS["exact"] <= 95.49 - 5


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
