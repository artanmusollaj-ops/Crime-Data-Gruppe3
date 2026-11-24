"""``fakt`` traegt alles, was die alte Verdichtung trug.

Bis zum 23.11.2026 legte das Dashboard sieben Tabellen je Stadt und Monat
direkt aus ``gold/fact_offense`` an. Seither haelt es die Taten schlank im
Speicher (``serving.dashboard.taten``). In Stufe 1 bildete es dieselben sieben
als Sichten darueber; seit Stufe 3 (24.11.2026) fragen die Bretter ``fakt``
selbst ab, auf den Tag genau. Die Sichten stehen darum hier, als ``NEU``: Sie
verdichten ``fakt`` so, wie es die alte Verdichtung mit der Quelle tat.

Was dabei still falsch werden kann, ohne dass ein Brett wirft:

- ein Verzeichnis, das eine Tat verliert - ein Tract ohne Eintrag in
  ``dim_tract``, ein Quellcode mit zwei Bezeichnungen, ein ``NULL`` in einem
  der fuenf Schluessel der Quellcodes;
- eine Kategorie, die anders entsteht - kein NIBRS-Code, oder einer, den
  ``dim_offense`` nicht kennt;
- ein Merkmal, das anders gerechnet wird - die Platzhalter-Tatzeit, eine
  mehrdeutige Ortszeit ohne Wert.

Darum steht hier die alte Verdichtung woertlich, und jede Verdichtung von
``fakt`` muss ihr zeilengleich entsprechen, auf einem Bestand mit genau
diesen Faellen. Am
echten Release vom 20.11.2026 waren zusaetzlich alle 569 Antworten einer
Matrix aus Brett, Stadt, Zeitraum, Kategorie, Mass und Ebene vorher und
nachher zeichengleich (``AENDERUNGEN.md``, 23.11.2026).
"""

from __future__ import annotations

from datetime import date, datetime, time

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from serving.dashboard import PLATZHALTER_SQL, Bestand
from test_dashboard import RELEASE, TRACT_AUSSEN, TRACT_C, TRACT_D, stern

#: Ein Tract, den ``dim_tract`` nicht fuehrt.
TRACT_FREMD = "17031888800"

#: Die Verdichtung bis zum 23.11.2026, woertlich aus ``Bestand._lade``.
ALT = {
    "raten": """
        SELECT t.city AS stadt, date_trunc('month', f.date)::DATE AS monat,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               f.population_vintage AS vintage,
               count(*) FILTER (f.counts_case) AS faelle,
               count(*) AS delikte
        FROM {F} f
        JOIN {T} t ON t.geoid = f.tract_geoid
        LEFT JOIN {D} d USING (nibrs_code)
        WHERE t.city IS NOT NULL
        GROUP BY ALL""",
    "fenster": """
        SELECT reporting_city AS stadt, min(date) AS von, max(date) AS bis
        FROM {F} GROUP BY 1""",
    "stunden": """
        SELECT f.reporting_city AS stadt, date_trunc('month', f.date)::DATE AS monat,
               isodow(f.date) AS wochentag, f.hour_of_day AS stunde,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               {PLATZHALTER} AS platzhalter,
               count(*) FILTER (f.counts_case) AS faelle
        FROM {F} f
        LEFT JOIN {D} d USING (nibrs_code)
        GROUP BY ALL""",
    "tage": """
        SELECT reporting_city AS stadt, date_trunc('month', date)::DATE AS monat,
               isodow(date) AS wochentag, count(DISTINCT date) AS n
        FROM {F} GROUP BY ALL""",
    "tract_monat": """
        SELECT f.reporting_city AS stadt, f.tract_geoid AS geoid,
               date_trunc('month', f.date)::DATE AS monat,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               f.population_vintage AS vintage,
               count(*) FILTER (f.counts_case) AS faelle, count(*) AS delikte
        FROM {F} f
        LEFT JOIN {D} d USING (nibrs_code)
        WHERE f.geo_status = 'inside_city'
        GROUP BY ALL""",
    "verortung": """
        SELECT f.reporting_city AS stadt, date_trunc('month', f.date)::DATE AS monat,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               f.geo_status, count(*) FILTER (f.counts_case) AS faelle
        FROM {F} f
        LEFT JOIN {D} d USING (nibrs_code)
        GROUP BY ALL""",
    "qualitaet": """
        SELECT f.reporting_city AS stadt, date_trunc('month', f.date)::DATE AS monat,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               f.mapping_status, f.geo_status,
               coalesce(f.local_time_ambiguous, false) AS ortszeit_mehrdeutig,
               count(*) AS delikte
        FROM {F} f
        LEFT JOIN {D} d USING (nibrs_code)
        GROUP BY ALL""",
    "zuordnung": """
        SELECT f.reporting_city AS stadt, date_trunc('month', f.date)::DATE AS monat,
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS kategorie,
               f.source_offense_code AS quellcode,
               min(f.source_offense_description) AS quelltext,
               f.nibrs_code, min(d.nibrs_description) AS nibrs_text,
               f.mapping_status AS status, count(*) AS delikte
        FROM {F} f
        LEFT JOIN {D} d USING (nibrs_code)
        GROUP BY 1, 2, 3, 4, 6, 8""",
}


#: Dieselben sieben, aus ``fakt`` und seinen Verzeichnissen - bis Stufe 3 die
#: Sichten in ``serving.dashboard.taten``. ``fenster`` legt das Dashboard
#: selbst an.
_MONAT = "date_trunc('month', f.tag)::DATE"
NEU = {
    "raten": f"""
        SELECT n.city AS stadt, {_MONAT} AS monat, f.kategorie AS kategorie,
               f.vintage, count(*) FILTER (f.fall) AS faelle, count(*) AS delikte
        FROM fakt f JOIN tract_nr n ON n.nr = f.tract
        WHERE n.city IS NOT NULL
        GROUP BY ALL""",
    "fenster": "SELECT stadt, von, bis FROM fenster",
    "stunden": f"""
        SELECT f.stadt AS stadt, {_MONAT} AS monat, isodow(f.tag) AS wochentag,
               f.stunde, f.kategorie AS kategorie, f.platzhalter,
               count(*) FILTER (f.fall) AS faelle
        FROM fakt f GROUP BY ALL""",
    "tage": f"""
        SELECT f.stadt AS stadt, {_MONAT} AS monat, isodow(f.tag) AS wochentag,
               count(DISTINCT f.tag) AS n
        FROM fakt f GROUP BY ALL""",
    "tract_monat": f"""
        SELECT f.stadt AS stadt, n.geoid, {_MONAT} AS monat,
               f.kategorie AS kategorie, f.vintage,
               count(*) FILTER (f.fall) AS faelle, count(*) AS delikte
        FROM fakt f LEFT JOIN tract_nr n ON n.nr = f.tract
        WHERE f.geo_status = 'inside_city'
        GROUP BY ALL""",
    "verortung": f"""
        SELECT f.stadt AS stadt, {_MONAT} AS monat,
               f.kategorie AS kategorie, f.geo_status AS geo_status,
               count(*) FILTER (f.fall) AS faelle
        FROM fakt f GROUP BY ALL""",
    "qualitaet": f"""
        SELECT f.stadt AS stadt, {_MONAT} AS monat,
               f.kategorie AS kategorie,
               f.mapping_status AS mapping_status,
               f.geo_status AS geo_status, f.ortszeit_mehrdeutig,
               count(*) AS delikte
        FROM fakt f GROUP BY ALL""",
    "zuordnung": f"""
        SELECT q.stadt, {_MONAT} AS monat, f.kategorie AS kategorie,
               q.quellcode, min(q.quelltext) AS quelltext,
               q.nibrs_code, min(d.nibrs_description) AS nibrs_text,
               q.status, count(*) AS delikte
        FROM fakt f JOIN quelle q ON q.nr = f.quelle
        LEFT JOIN delikt d ON d.nibrs_code = q.nibrs_code
        GROUP BY 1, 2, 3, 4, 6, 8""",
}


def _mit_randfaellen(root) -> None:
    """Haengt an die Taten des Release die Faelle an, an denen ein Verzeichnis kippt."""
    pfad = (root / "releases" / f"release={RELEASE}" / "gold" / "dataset=fact_offense"
            / "part-0001.parquet")
    tabelle = pq.read_table(pfad)
    basis = tabelle.slice(0, 1).to_pylist()[0]

    def tat(i: int, **aenderung) -> dict:
        return basis | {"offense_id": f"rand{i}"} | aenderung

    rand = [
        # Ohne Tract, und mit einem Tract, den dim_tract nicht kennt.
        tat(1, tract_geoid=None, geo_status="no_tract"),
        tat(2, tract_geoid=TRACT_FREMD, geo_status="inside_city"),
        # Ohne NIBRS-Code: Kategorie unmapped, und NULL in einem Schluessel
        # der Quellcodes.
        tat(3, nibrs_code=None, mapping_status="unmapped"),
        # Ein NIBRS-Code, den dim_offense nicht fuehrt: Kategorie NULL.
        tat(4, nibrs_code="999", mapping_status="exact"),
        # Derselbe Quellcode mit zwei Bezeichnungen im selben Monat.
        tat(5, source_offense_description="Andere Bezeichnung"),
        tat(6, source_offense_code=None, source_offense_description=None),
        tat(16, mapping_status=None),
        # Die Platzhalter-Tatzeiten und knapp daneben.
        tat(7, hour_of_day=0, occurred_at_local=datetime(2024, 5, 3, 0, 0, 0)),
        tat(8, hour_of_day=12, occurred_at_local=datetime(2024, 5, 3, 12, 0, 0)),
        tat(9, hour_of_day=12, occurred_at_local=datetime(2024, 5, 3, 12, 0, 30)),
        # Mehrdeutige Ortszeit: wahr, und ohne Wert.
        tat(10, local_time_ambiguous=True),
        tat(11, local_time_ambiguous=None),
        # Kein Fall, nur eine weitere Anklage; ein anderes Vintage.
        tat(12, counts_case=False),
        tat(13, population_vintage=None),
        # Eine dritte Verortung, und ein Tag am Monatsende.
        tat(14, geo_status="missing_coordinate", tract_geoid=None),
        tat(15, date=date(2024, 2, 29)),
    ]
    pq.write_table(pa.concat_tables([tabelle, pa.Table.from_pylist(rand, schema=tabelle.schema)]),
                   pfad)


@pytest.fixture(scope="module")
def bestand(tmp_path_factory) -> Bestand:
    root = tmp_path_factory.mktemp("taten")
    taten = (
        [("chicago", date(2024, m, d), c, TRACT_C, time(h, 5))
         for m in (1, 5, 12) for d in (1, 15) for c in ("13A", "23C") for h in (3, 18)]
        + [("detroit", date(2024, m, 7), "120", TRACT_D) for m in (2, 5)]
        + [("chicago", date(2023, 11, 30), "13B", TRACT_AUSSEN)]
        + [("detroit", date(2025, 1, 2), "13A", TRACT_D, time(9, 0), False, "ambiguous")]
    )
    stern(root, taten)
    _mit_randfaellen(root)
    return Bestand(root)


def _alt(bestand: Bestand, name: str) -> str:
    release = bestand.data_root / "releases" / f"release={RELEASE}" / "gold"

    def lies(tabelle: str) -> str:
        return (f"read_parquet('{release / f'dataset={tabelle}' / 'part-0001.parquet'}', "
                "hive_partitioning=false)")

    return ALT[name].format(F=lies("fact_offense"), D=lies("dim_offense"),
                            T=lies("dim_tract"), PLATZHALTER=PLATZHALTER_SQL)


@pytest.mark.parametrize("name", sorted(ALT))
def test_jede_verdichtung_ist_zeilengleich_mit_der_alten(bestand, name):
    con = bestand._con
    alt = _alt(bestand, name)
    neu = NEU[name]
    zuviel = con.execute(f"({neu}) EXCEPT ALL ({alt})").fetchall()
    fehlt = con.execute(f"({alt}) EXCEPT ALL ({neu})").fetchall()
    assert not zuviel and not fehlt, f"{name}: zu viel {zuviel}, fehlt {fehlt}"


@pytest.mark.parametrize("name", sorted(ALT))
def test_jede_verdichtung_hat_die_spalten_der_alten(bestand, name):
    """Gleiche Namen in gleicher Folge; ein Aufzaehlungstyp gilt als Text.

    DuckDB gibt einen ENUM-Wert als ``str`` heraus, die Bretter sehen also
    keinen Unterschied. Jede andere Typabweichung - etwa ein INTEGER statt
    SMALLINT oder ein Datum statt Zeitstempel - wuerde im JSON sichtbar.
    """
    con = bestand._con

    def typen(sql: str) -> list[tuple[str, str]]:
        return [(r[0], "VARCHAR" if r[1].startswith("ENUM") else r[1])
                for r in con.execute(f"DESCRIBE {sql}").fetchall()]

    assert typen(NEU[name]) == typen(_alt(bestand, name))


def test_die_randfaelle_sind_auch_angekommen(bestand):
    """Sonst waere die Gleichheit oben billig."""
    con = bestand._con
    taten = _alt(bestand, "fenster").split("FROM ")[1].split(" GROUP")[0]
    assert con.execute("SELECT count(*) FROM fakt").fetchone()[0] == \
        con.execute(f"SELECT count(*) FROM {taten}").fetchone()[0]
    assert con.execute("SELECT count(*) FROM fakt WHERE tract IS NULL").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM fakt WHERE kategorie IS NULL").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM fakt WHERE platzhalter").fetchone()[0] == 2
    assert con.execute(
        "SELECT count(*) FROM tract_nr WHERE geoid = $g AND city IS NULL",
        {"g": TRACT_FREMD}).fetchone()[0] == 1
    assert con.execute(
        "SELECT count(DISTINCT quelltext) FROM quelle WHERE quellcode = 'Q13A'").fetchone()[0] == 2


def test_die_faktentabelle_traegt_keinen_text(bestand):
    """Der Speicher ist der Grund fuer ``fakt``: Text gehoert in die Verzeichnisse."""
    typen = {r[0]: r[1] for r in bestand._con.execute("DESCRIBE fakt").fetchall()}
    assert "VARCHAR" not in typen.values(), typen
