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

import csv
import struct
from datetime import date, datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_gold as bg
from gold_pipeline import STADT_SCHWELLE, STUDIENSTAEDTE
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
    """zeilen: (offense_id, city, tag, nibrs_code, tract_geoid)."""
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
        "latitude": pa.array([41.8] * n, pa.float64()),
        "longitude": pa.array([-87.6] * n, pa.float64()),
        "tract_geoid": pa.array([z[4] for z in zeilen]),
        "located": pa.array([True] * n),
        "arrest": pa.array([False] * n),
        "unfounded": pa.array([False] * n),
        "dataset": pa.array(["crime_offense"] * n),
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
    erlaubt = {"current", "replaced", "not_an_offense", "unresolved"}
    for code, zeile in nach_code.items():
        assert zeile["resolution"] in erlaubt, f"{code}: {zeile['resolution']}"
        if zeile["retired"]:
            assert zeile["retirement_note"], f"{code} ohne Begruendung"
        if zeile["resolution"] == "replaced":
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
    assert "Harboring" in zeile["retirement_note"], (
        "die Notiz muss den Unterschied zum Beherbergen benennen"
    )


def test_die_familie_ist_das_kuerzel_und_nichts_erfundenes(tmp_path):
    """Kein Familienname, weil die Spezifikation dafuer keine Liste fuehrt."""
    zeilen = bg.dim_offense_rows(PROJECT_ROOT / "config")
    assert all(z["nibrs_family"] == z["nibrs_code"][:2] for z in zeilen)
    assert "nibrs_family_description" not in zeilen[0]


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
        "nibrs_family VARCHAR, nibrs_group VARCHAR, crime_against VARCHAR, "
        "federal_only BOOLEAN, retired BOOLEAN, replaced_by VARCHAR, "
        "resolution VARCHAR, retirement_note VARCHAR)"
    )
    con.executemany(
        "INSERT INTO dim_offense VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [tuple(z.values()) for z in bg.dim_offense_rows(PROJECT_ROOT / "config")],
    )
    con.execute(f"CREATE OR REPLACE TABLE dim_date AS {bg.dim_date_query(offense)}")
    con.execute(
        f"CREATE OR REPLACE TABLE dim_city_day AS {bg.dim_city_day_query(weather, offense)}"
    )
    con.execute(f"CREATE OR REPLACE TABLE fact_offense AS {bg.fact_offense_query(offense)}")
    return offense


def test_das_korn_bleibt_erhalten(con, tmp_path):
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
    assert set(einwohner) == set(STUDIENSTAEDTE.values())
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


def test_die_echte_faktentabelle_hat_das_korn_von_silver(con):
    fakt = gold("fact_offense")
    silber = PROJECT_ROOT / "data" / "silver" / "dataset=crime_offense" / "part-0001.parquet"
    if fakt is None or not silber.exists():
        pytest.skip("keine gebaute Gold-Schicht vorhanden")
    a = con.execute(f"SELECT count(*) FROM read_parquet('{fakt}')").fetchone()[0]
    b = con.execute(f"SELECT count(*) FROM read_parquet('{silber}')").fetchone()[0]
    assert a == b
