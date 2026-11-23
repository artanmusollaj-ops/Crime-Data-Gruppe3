"""Die Taten im Speicher: eine schlanke Faktentabelle, die Monatssichten darueber.

Bis zum 23.11.2026 verdichtete das Dashboard ``gold/fact_offense`` beim Laden
auf sieben Tabellen je Stadt und Monat. Ein Zeitraum war darum immer ein
Monatsbereich in einem Jahr. Fuer einen freien Zeitraum, auf den Tag genau und
ueber alle Jahre, haette man dieselben Tabellen je Tag verdichten muessen - und
das traegt nicht: Tract x Tag x Kategorie ergibt 1,6 Mio. Zeilen aus 1,9 Mio.
Taten, verdichtet also kaum noch.

**Gemessen** am Release ``2026-11-20T10-08-03Z`` (1'895'123 Taten), je
Variante in einem eigenen Prozess:

=====================================  ========  =========  ===============
Variante                               Zeilen    DuckDB     Spitze Prozess
=====================================  ========  =========  ===============
sieben Tabellen je Monat (bis hier)    0,9 Mio.   89 MiB    394 MiB
dieselben je Tag                       2,9 Mio.  252 MiB    612 MiB
diese Faktentabelle                    1,9 Mio.   97 MiB    244 MiB
=====================================  ========  =========  ===============

Das Dashboard darf auf ``srv01`` 640 MiB belegen. Die Faktentabelle haelt
darum keinen Text: Stadt, Kategorie, Verortung und Zuordnung sind
Aufzaehlungstypen, Tract und Quellcode Nummern in je einem Verzeichnis. Eine
Abfrage ueber sechs Jahre braucht darauf auf einem Kern hoechstens 17 ms.

**Die Sichten heissen wie die Tabellen vorher** und liefern dieselben Spalten
mit denselben Typen. Die Bretter merken also nichts, und
``tests/serving/test_dashboard_taten.py`` haelt jede Sicht zeilengleich gegen
die alte Verdichtung. Ein freier Zeitraum ist danach ein ``WHERE`` auf
``fakt.tag``; das ist der naechste Schritt.

Nicht hier: ``monate`` kommt aus ``serving/comparison_month``, und
``doppelte`` braucht die Delikt-ID, die die Faktentabelle nicht fuehrt.
"""

from __future__ import annotations

from typing import Any

#: Die Kategorie einer Tat wie in ``build_comparison``: ueber ``dim_offense``,
#: ohne NIBRS-Code ``unmapped``. Erwartet die Aliase ``f`` und ``d``.
KATEGORIE_SQL = "CASE WHEN f.nibrs_code IS NULL THEN 'unmapped' ELSE d.nibrs_category END"


def _aufzaehlung(con: Any, name: str, abfrage: str) -> str:
    """Legt einen ENUM-Typ aus den Werten der Abfrage an und gibt den Typnamen.

    Ohne Werte - ein leerer Bestand - bleibt es ``VARCHAR``: DuckDB nimmt
    keinen ENUM ohne Wert.
    """
    werte = sorted({r[0] for r in con.execute(abfrage).fetchall() if r[0] is not None})
    if not werte:
        return "VARCHAR"
    liste = ", ".join("'" + w.replace("'", "''") + "'" for w in werte)
    con.execute(f"CREATE TYPE {name} AS ENUM ({liste})")
    return name


def lade_taten(con: Any, fakten: str, delikte: str, tracts: str) -> None:
    """Legt ``fakt`` mit seinen Verzeichnissen an und die Monatssichten darueber."""
    from serving.dashboard import PLATZHALTER_SQL

    F = f"read_parquet('{fakten}', hive_partitioning=false)"
    D = f"read_parquet('{delikte}', hive_partitioning=false)"
    T = f"read_parquet('{tracts}', hive_partitioning=false)"
    con.execute(f"""
        CREATE TABLE delikt AS
        SELECT nibrs_code, nibrs_category, nibrs_description FROM {D}""")
    stadt = _aufzaehlung(con, "stadt_t", f"SELECT DISTINCT reporting_city FROM {F}")
    kategorie = _aufzaehlung(con, "kategorie_t", """
        SELECT nibrs_category FROM delikt UNION SELECT 'unmapped'""")
    verortung = _aufzaehlung(con, "verortung_t", f"SELECT DISTINCT geo_status FROM {F}")
    zuordnung = _aufzaehlung(con, "zuordnung_t", f"SELECT DISTINCT mapping_status FROM {F}")
    # Die Stadt eines Tracts kommt aus dim_tract, wie in
    # gold_pipeline.raten_je_stadt; ein Tract ohne Eintrag dort hat keine.
    con.execute(f"""
        CREATE TABLE tract_nr AS
        SELECT row_number() OVER (ORDER BY g.geoid)::INTEGER AS nr, g.geoid, t.city
        FROM (SELECT DISTINCT tract_geoid AS geoid FROM {F}
              WHERE tract_geoid IS NOT NULL) g
        LEFT JOIN {T} t USING (geoid)""")
    # Je Stadt, Quellcode, Quelltext, NIBRS-Code und Zuordnung eine Nummer:
    # rund 520 Eintraege fuer die Tafel »NIBRS-Zuordnung im Detail«.
    con.execute(f"""
        CREATE TABLE quelle AS
        SELECT row_number() OVER (ORDER BY stadt, quellcode, quelltext, nibrs_code, status)::INTEGER AS nr, *
        FROM (SELECT DISTINCT reporting_city AS stadt,
                     source_offense_code AS quellcode,
                     source_offense_description AS quelltext,
                     nibrs_code, mapping_status AS status FROM {F})""")
    # Nach Stadt und Tag sortiert: Ein Zeitraum liest dann zusammenhaengende
    # Bloecke.
    con.execute(f"""
        CREATE TABLE fakt AS
        SELECT f.reporting_city::{stadt} AS stadt,
               f.date AS tag,
               date_trunc('month', f.date)::DATE AS monat,
               n.nr AS tract,
               ({KATEGORIE_SQL})::{kategorie} AS kategorie,
               f.population_vintage AS vintage,
               f.counts_case AS fall,
               f.hour_of_day AS stunde,
               {PLATZHALTER_SQL} AS platzhalter,
               f.geo_status::{verortung} AS geo_status,
               f.mapping_status::{zuordnung} AS mapping_status,
               coalesce(f.local_time_ambiguous, false) AS ortszeit_mehrdeutig,
               q.nr AS quelle
        FROM {F} f
        LEFT JOIN delikt d USING (nibrs_code)
        LEFT JOIN tract_nr n ON n.geoid = f.tract_geoid
        LEFT JOIN quelle q
          ON q.stadt IS NOT DISTINCT FROM f.reporting_city
         AND q.quellcode IS NOT DISTINCT FROM f.source_offense_code
         AND q.quelltext IS NOT DISTINCT FROM f.source_offense_description
         AND q.nibrs_code IS NOT DISTINCT FROM f.nibrs_code
         AND q.status IS NOT DISTINCT FROM f.mapping_status
        ORDER BY 1, 2""")
    _monatssichten(con)


def _monatssichten(con: Any) -> None:
    """Die sieben Verdichtungen von bis zum 23.11.2026, als Sichten auf ``fakt``."""
    # Eine gespeicherte Spalte, kein Ausdruck: Die Bretter filtern auf
    # ``monat``, und nur auf einer Spalte zieht DuckDB den Filter vor die
    # Verdichtung. Mit dem Ausdruck rechnete jede Anfrage alle Jahre.
    monat = "f.monat"
    # Die Regel von gold_pipeline.raten_je_stadt: nur Taten in einem Tract
    # mit Stadtzuordnung, das Vintage je Tat. Beide Ebenen: Faelle fuer die
    # Rate vorn (E5), Delikte fuer die Tatebene daneben und fuer die
    # Kategorien, die sich nur dort addieren.
    con.execute(f"""
        CREATE VIEW raten AS
        SELECT n.city AS stadt, {monat} AS monat, f.kategorie AS kategorie,
               f.vintage, count(*) FILTER (f.fall) AS faelle, count(*) AS delikte
        FROM fakt f JOIN tract_nr n ON n.nr = f.tract
        WHERE n.city IS NOT NULL
        GROUP BY ALL""")
    # Das Fenster je Stadt, selbst gerechnet. comparison_month tut es seit
    # Vertrag 3 auch (C-10, 1.11.2026), aber das Dashboard liest das aktive
    # Release - und ein Release mit Vertrag 2 rechnet noch am gemeinsamen
    # Fenster beider Staedte. Eine Tabelle, keine Sicht: Sie haengt an keiner
    # Auswahl, und als Sicht lief jede Anfrage einmal ueber alle Taten.
    con.execute("""
        CREATE TABLE fenster AS
        SELECT stadt AS stadt, min(tag) AS von, max(tag) AS bis
        FROM fakt GROUP BY 1""")
    # Fuer »Zeitverlauf«: Faelle je Wochentag und lokaler Stunde. Genau 00:00
    # und 12:00 sind Platzhalter fuer eine unbekannte Tatzeit; sie werden
    # mitgezaehlt, aber markiert.
    con.execute(f"""
        CREATE VIEW stunden AS
        SELECT f.stadt AS stadt, {monat} AS monat, isodow(f.tag) AS wochentag,
               f.stunde, f.kategorie AS kategorie, f.platzhalter,
               count(*) FILTER (f.fall) AS faelle
        FROM fakt f GROUP BY ALL""")
    # Der Nenner der Heatmap: wie viele Montage, Dienstage ... ein Monat je
    # Stadt mit Daten hat.
    con.execute(f"""
        CREATE VIEW tage AS
        SELECT f.stadt AS stadt, {monat} AS monat, isodow(f.tag) AS wochentag,
               count(DISTINCT f.tag) AS n
        FROM fakt f GROUP BY ALL""")
    # Fuer »Geografie«: Faelle je Tract und Monat nach der Regel von
    # gold_pipeline.raten_je_tract.
    con.execute(f"""
        CREATE VIEW tract_monat AS
        SELECT f.stadt AS stadt, n.geoid, {monat} AS monat,
               f.kategorie AS kategorie, f.vintage,
               count(*) FILTER (f.fall) AS faelle, count(*) AS delikte
        FROM fakt f LEFT JOIN tract_nr n ON n.nr = f.tract
        WHERE f.geo_status = 'inside_city'
        GROUP BY ALL""")
    con.execute(f"""
        CREATE VIEW verortung AS
        SELECT f.stadt AS stadt, {monat} AS monat,
               f.kategorie AS kategorie, f.geo_status AS geo_status,
               count(*) FILTER (f.fall) AS faelle
        FROM fakt f GROUP BY ALL""")
    # Fuer »Datenqualität«: Taten je Zuordnung, Verortung und Ortszeit.
    con.execute(f"""
        CREATE VIEW qualitaet AS
        SELECT f.stadt AS stadt, {monat} AS monat,
               f.kategorie AS kategorie,
               f.mapping_status AS mapping_status,
               f.geo_status AS geo_status, f.ortszeit_mehrdeutig,
               count(*) AS delikte
        FROM fakt f GROUP BY ALL""")
    # Fuer »Datenqualität«, Tafel »NIBRS-Zuordnung im Detail«: je Quellcode,
    # wohin er in NIBRS faellt, je Monat, damit Zeitraum und Kategorie der
    # Leiste greifen. Gezaehlt werden Taten wie in ``qualitaet``.
    con.execute(f"""
        CREATE VIEW zuordnung AS
        SELECT q.stadt, {monat} AS monat, f.kategorie AS kategorie,
               q.quellcode, min(q.quelltext) AS quelltext,
               q.nibrs_code, min(d.nibrs_description) AS nibrs_text,
               q.status, count(*) AS delikte
        FROM fakt f JOIN quelle q ON q.nr = f.quelle
        LEFT JOIN delikt d ON d.nibrs_code = q.nibrs_code
        GROUP BY 1, 2, 3, 4, 6, 8""")
