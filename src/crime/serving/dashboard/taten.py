"""Die Taten im Speicher: eine schlanke Faktentabelle mit ihren Verzeichnissen.

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

**Die Bretter fragen ``fakt`` direkt ab**, seit Stufe 3 (24.11.2026) mit
einem ``WHERE`` auf ``fakt.tag``. Bis dahin lagen ueber ``fakt`` sieben
Monatssichten mit den Namen der alten Tabellen. Sie stehen jetzt nur noch in
``tests/serving/test_dashboard_taten.py``: Dort halten sie zeilengleich gegen
die alte Verdichtung fest, dass ``fakt`` alles traegt, was jene trug.

**Bezirk und Festnahme** (seit 25.11.2026, Gold-Vertrag 11): ``bezirk`` ist
der Polizeibezirk als Zahl, ``festnahme`` die Festnahme. Ein aelteres Release
fuehrt den Bezirk nicht und ``arrest`` womoeglich auch nicht; dann bleiben
beide ``NULL``, und das Dashboard laedt trotzdem.

**Dunkelheit und Sechseck** (seit 25.11.2026): ``dunkel`` sagt, ob die Tat
nach Sonnenuntergang und vor Sonnenaufgang lag - dieselbe Regel wie die Tafel
»Tag und Nacht« (``zeitverlauf.lade_licht``), ``NULL`` wo das nicht sicher ist
(Platzhalterzeit, kein Sonnenstand). ``hq`` und ``hr`` sind die Zelle eines
Sechseckrasters mit ``SECHSECK_M`` Metern Kantenlaenge, axial nach Red Blob
Games, »Hexagonal Grids« (https://www.redblobgames.com/grids/hexagons/),
gerechnet in Metern um den Mittelpunkt der Taten jeder Stadt (``mitte``).

Nicht hier: ``monate`` kommt aus ``serving/comparison_month``, und
``doppelte`` braucht die Delikt-ID, die die Faktentabelle nicht fuehrt.
Hier steht dafuer ``fenster``, je Stadt der erste und letzte Tag mit Daten.
"""

from __future__ import annotations

from typing import Any

#: Kantenlaenge eines Sechsecks in Metern; eine Zelle hat rund 0,65 km².
SECHSECK_M = 500.0
#: Mittlerer Erdradius in Metern (IUGG), fuer die lokale Projektion.
ERDRADIUS_M = 6371008.8

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


def sechseck_sql(lat: str, lon: str, lat0: str, lon0: str) -> tuple[str, str]:
    """Die axiale Zelle (q, r) eines Punkts, spitze Sechsecke, als SQL.

    Gleichrechteckige Projektion um (lat0, lon0) - ueber eine Stadt genau
    genug -, dann Pixel zu Sechseck und Wuerfelrunden nach Red Blob Games.
    """
    x = f"(radians({lon}) - radians({lon0})) * {ERDRADIUS_M} * cos(radians({lat0}))"
    y = f"(radians({lat}) - radians({lat0})) * {ERDRADIUS_M}"
    q = f"((sqrt(3) / 3 * ({x}) - ({y}) / 3) / {SECHSECK_M})"
    r = f"((2.0 / 3 * ({y})) / {SECHSECK_M})"
    s = f"(-({q}) - ({r}))"
    rq, rr, rs = f"round({q})", f"round({r})", f"round({s})"
    dq, dr, ds = f"abs({rq} - {q})", f"abs({rr} - {r})", f"abs({rs} - {s})"
    q_ende = f"CASE WHEN {dq} > {dr} AND {dq} > {ds} THEN -{rr} - {rs} ELSE {rq} END"
    r_ende = (f"CASE WHEN {dq} > {dr} AND {dq} > {ds} THEN {rr} "
              f"WHEN {dr} > {ds} THEN -{rq} - {rs} ELSE {rr} END")
    return f"CAST({q_ende} AS SMALLINT)", f"CAST({r_ende} AS SMALLINT)"


def lade_taten(con: Any, fakten: str, delikte: str, tracts: str,
               stadttage: str | None = None) -> None:
    """Legt ``fakt`` mit seinen Verzeichnissen an, dazu ``fenster`` und ``mitte``.

    ``stadttage`` ist ``gold/dim_city_day`` mit Sonnenstand; ohne ihn bleibt
    ``dunkel`` leer.
    """
    from serving.dashboard import PLATZHALTER_SQL

    F = f"read_parquet('{fakten}', hive_partitioning=false)"
    spalten = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM {F}").fetchall()}
    bezirk = ("TRY_CAST(f.police_area AS UTINYINT)" if "police_area" in spalten
              else "NULL::UTINYINT")
    festnahme = "f.arrest" if "arrest" in spalten else "NULL::BOOLEAN"
    # Der Mittelpunkt der Taten je Stadt: Ursprung des Sechseckrasters. Ohne
    # Koordinaten (nur in Testbestaenden) bleibt das Raster leer.
    if {"latitude", "longitude"} <= spalten:
        con.execute(f"""
            CREATE TABLE mitte AS
            SELECT reporting_city AS stadt, avg(latitude) AS lat, avg(longitude) AS lon
            FROM {F} WHERE latitude IS NOT NULL GROUP BY 1""")
        hq, hr = sechseck_sql("f.latitude", "f.longitude", "m.lat", "m.lon")
    else:
        con.execute("CREATE TABLE mitte (stadt VARCHAR, lat DOUBLE, lon DOUBLE)")
        hq, hr = "NULL::SMALLINT", "NULL::SMALLINT"
    licht_join, dunkel = "", "NULL::BOOLEAN"
    if stadttage and "occurred_at_utc" in spalten:
        licht_join = (f"LEFT JOIN read_parquet('{stadttage}', hive_partitioning=false) c "
                      "ON c.city = f.reporting_city AND c.date = f.date")
        dunkel = (f"CASE WHEN {PLATZHALTER_SQL} OR f.occurred_at_utc IS NULL "
                  "OR c.sunrise_utc IS NULL OR c.sunset_utc IS NULL THEN NULL "
                  "ELSE NOT (f.occurred_at_utc >= c.sunrise_utc "
                  "AND f.occurred_at_utc < c.sunset_utc) END")
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
               n.nr AS tract,
               ({KATEGORIE_SQL})::{kategorie} AS kategorie,
               f.population_vintage AS vintage,
               f.counts_case AS fall,
               f.hour_of_day AS stunde,
               {PLATZHALTER_SQL} AS platzhalter,
               f.geo_status::{verortung} AS geo_status,
               f.mapping_status::{zuordnung} AS mapping_status,
               coalesce(f.local_time_ambiguous, false) AS ortszeit_mehrdeutig,
               q.nr AS quelle,
               {bezirk} AS bezirk,
               {festnahme} AS festnahme,
               {dunkel} AS dunkel,
               {hq} AS hq,
               {hr} AS hr
        FROM {F} f
        LEFT JOIN delikt d USING (nibrs_code)
        LEFT JOIN tract_nr n ON n.geoid = f.tract_geoid
        LEFT JOIN quelle q
          ON q.stadt IS NOT DISTINCT FROM f.reporting_city
         AND q.quellcode IS NOT DISTINCT FROM f.source_offense_code
         AND q.quelltext IS NOT DISTINCT FROM f.source_offense_description
         AND q.nibrs_code IS NOT DISTINCT FROM f.nibrs_code
         AND q.status IS NOT DISTINCT FROM f.mapping_status
        LEFT JOIN mitte m ON m.stadt = f.reporting_city
        {licht_join}
        ORDER BY 1, 2""")
    _fenster(con)


def _fenster(con: Any) -> None:
    """Das Fenster je Stadt: erster und letzter Tag mit einer Tat.

    Selbst gerechnet: comparison_month tut es seit Vertrag 3 auch (C-10,
    1.11.2026), aber das Dashboard liest das aktive Release - und ein Release
    mit Vertrag 2 rechnet noch am gemeinsamen Fenster beider Staedte.
    """
    con.execute("""
        CREATE TABLE fenster AS
        SELECT stadt AS stadt, min(tag) AS von, max(tag) AS bis
        FROM fakt GROUP BY 1""")
