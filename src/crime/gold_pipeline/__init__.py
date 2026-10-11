"""Gold: die Schicht, auf der ausgewertet wird.

**Gold aggregiert hier nicht.** Das ist eine Abkehr vom urspruenglichen Entwurf,
der zwei vorberechnete Wuerfel vorsah - ``fact_tract_month`` und
``fact_city_day``. Gemessen wurde der Grund dafuer nicht mehr gefunden:

    ein Delikt, ein Tag, eine Stadt              0,6 ms
    ein Delikt, ein Monat, beide Staedte         0,9 ms
    Rate je 1'000 Einwohner, Tract x Familie     6,8 ms
    Delikte je Tag mit Tagestemperatur           3,4 ms

Bei 348'000 Zeilen ist DuckDB nicht der Engpass; eine vorberechnete
Monatsspalte spart 0,3 Millisekunden. Was die Aggregation dagegen kostet, ist
genau das, was die Auswertungsplattform koennen soll: ``fact_tract_month`` kennt
keine Tage, ``fact_city_day`` keine Tracts, und beide fassen 59 Delikte zu 25
Familien zusammen - "nur Shoplifting" waere nicht mehr zu beantworten.

Gold behaelt deshalb die Granularität und macht die Faktentabelle **abfragbar**: ein
Sternschema mit einer Faktentabelle je Delikt und fuenf kleinen Dimensionen.
Jede Frage wird damit ein Filter und ein ``GROUP BY`` auf einer Tabelle.

| Tabelle | Granularität |
| --- | --- |
| ``fact_offense`` | ein Delikt |
| ``dim_tract`` | ein Census Tract, mit Stadtzuordnung |
| ``dim_tract_acs`` | ein Census Tract in einem ACS-Vintage, mit der Einwohnerzahl |
| ``dim_offense`` | ein NIBRS-Delikt |
| ``dim_date`` | ein Kalendertag |
| ``dim_city_day`` | Stadt und Tag, mit dem Wetter |

**Warum die Einwohnerzahl eine eigene Tabelle hat.** Bis zum 3.10.2026 stand
sie in ``dim_tract``, und das ging, solange es einen einzigen Jahrgang gab:
Eine Tabelle mit einer Zeile je Tract kann nur eine Einwohnerzahl tragen. Ueber
mehrere Jahrgaenge bekaeme jede Tat denselben Nenner, auch die von 2021 - und
das Ergebnis saehe vollstaendig aus. ``fact_offense.population_vintage`` nennt
je Zeile, welches Vintage fuer sie gilt.

Anders als Silver wird Gold **ersetzt und nicht angehaeuft**: Es ist vollstaendig
aus Silver ableitbar, und die Herkunft steht im Manifest.
"""

from __future__ import annotations

from pathlib import Path

from silver_pipeline import STUDIENSTAEDTE


GOLD_LAYER = "gold"
SILVER_LAYER = "silver"
PARQUET_FILE = "part-0001.parquet"

# Die beiden Staedte als **Verbundschluessel**: kleingeschrieben, weil so die
# Spalte ``city`` in ``silver/crime_offense`` aussieht und ``dim_tract``
# darueber verbunden wird.
#
# Abgeleitet, nicht abgeschrieben. Bis zum 14.9.2026 stand dieselbe Zuordnung
# ein zweites Mal in ``silver_pipeline`` - gross statt klein, unter demselben
# Namen ``STUDIENSTAEDTE``. Zwei Dinge unter einem Namen, mit verschiedenen
# Werten: Wer die falsche importierte, bekam stillschweigend etwas anderes,
# und eine dritte Stadt waere nur an einer der beiden Stellen gelandet. Die
# Tatsache steht jetzt einmal da, der abgeleitete Schluessel heisst anders.
STADT_SCHLUESSEL = {
    geoid: name.lower() for geoid, name in STUDIENSTAEDTE.items()
}

# Ab diesem Flaechenanteil gehoert ein Tract zur Stadt. Tracts liegen nicht
# sauber in Stadtgrenzen - sie ueberschreiten sie. Die Mehrheitsregel gibt
# jedem Tract genau eine Stadt und ist damit eindeutig; an den Falldaten
# geprueft trifft sie die amtliche Einwohnerzahl gut (siehe
# notebooks/34_gold_sternschema.ipynb).
STADT_SCHWELLE = 0.5

# Was die beiden Statusspalten annehmen duerfen. Ein neuer Wert bedeutet, dass
# jemand die Einstufung geaendert hat - dann soll der Bau stehen bleiben und
# nicht still eine Kennzahl verschieben.
MAPPING_STATUS_WERTE = {"exact", "ambiguous", "fallback_90Z", "unmapped"}
GEO_STATUS_WERTE = {"inside_city", "outside_city", "no_tract", "missing_coordinate"}

# Untergrenzen fuer die Veroeffentlichung, in Prozent der Faktenzeilen.
#
# **Es sind Boeden, keine Ziele.** Am Jahrgang 2024 gemessen liegen die Werte
# weit darueber: inside_city 97,45 %, exact 95,49 %, unmapped 0,0009 %. Die
# Schwellen haben absichtlich viel Luft - sie sollen einen *Einsturz*
# abfangen, nicht die normale Bewegung der Quelle. Ein gebrochener raeumlicher
# Join oder ein Crosswalk, der ins Leere laeuft, faellt hier auf; dass die
# Stadt ein paar hundert Faelle anders codiert, nicht.
#
# Eng gezogene Schwellen waeren schlimmer als keine: Sie wuerden bei jeder
# Datenbewegung rot, und die erste Reaktion waere, sie hochzusetzen statt
# hinzusehen.
GATE_MINDESTENS = {
    "inside_city": 90.0,      # gemessen 97,45
    "exact": 85.0,            # gemessen 95,49
}
GATE_HOECHSTENS = {
    "unmapped": 1.0,          # gemessen 0,0009
}


# Die fuenf Tabellen des Sternschemas, in der Reihenfolge des Bauplans.
# ``build_gold`` prueft sich dagegen: Kommt eine dazu und fehlt sie hier, faellt
# der Bau auf. Gebraucht wird die Liste ausserhalb, damit ein Release sagen
# kann, was vollstaendig heisst - ohne die fuenf Namen ein zweites Mal zu
# tippen (siehe ``orchestration.release``).
TABELLEN: tuple[str, ...] = (
    "fact_offense", "dim_tract", "dim_tract_acs", "dim_offense", "dim_date",
    "dim_city_day",
)


def table_dir(data_root: Path, table: str) -> Path:
    """Wohin eine Gold-Tabelle geschrieben wird."""
    return data_root / GOLD_LAYER / f"dataset={table}"


#: Das Jahr, fuer das die Abgabedokumente ihre Raten je 1'000 Einwohner nennen.
#:
#: Eine Rate braucht einen Zeitraum, sonst ist sie keine. Bis zum 4.10.2026
#: stand in den Dokumenten "Chicago 94,5 je 1'000" ohne Jahr, und das ging,
#: weil genau ein Jahrgang gebaut war. Seit dem Mehrjahresbau zaehlt dieselbe
#: Abfrage sechs Jahrgaenge zusammen: 500,7 je 1'000 fuer Chicago - eine Zahl,
#: die nicht zu hoch ist, sondern **nichts bedeutet**, weil ihr Zaehler sechs
#: Jahre und ihr Nenner eines umfasst.
#:
#: 2024 bleibt das Bezugsjahr: Es ist der Jahrgang, auf den die Fragestellung
#: und die Hypothesen gestellt sind, und der juengste, der vollstaendig
#: vorliegt (2025 und 2026 sind es nicht - ``dim_date.year_is_complete``
#: sagt es je Tag). Eine Tabelle mit einer Rate je Jahr waere das Bessere und
#: ist nicht dasselbe; sie steht aus.
RATENJAHR = 2024


def raten_je_stadt(fact_offense: str, dim_tract: str, dim_tract_acs: str,
                   jahr: int = RATENJAHR) -> str:
    """Delikte, Faelle, Einwohner und die beiden Raten je Stadt - fuer **ein** Jahr.

    Die Abfrage, die hinter jeder Ratenzeile der Abgabedokumente steht. Sie
    liegt hier und nicht bei ihren Benutzern, aus demselben Grund wie
    ``einwohner_je_stadt``: Gebraucht wird sie im Driftbericht, auf der
    Einstiegsseite und in den Waechtern ueber ``ln2_konzept.md``, ``README.md``,
    ``AENDERUNGEN.md`` und ``eine-zahl.md``. Sechs Fassungen waeren fuenf zu
    viel - und waeren sie es, wuerde eine davon den Jahresfilter vergessen.

    **Gezaehlt wird nach Ortszeit** (``fact_offense.date``), nicht nach UTC:
    Dieselbe Achse, auf der die Jahrgaenge geladen sind.

    **Der Nenner ist der der Zeile**, nicht der der Tabelle: ``population_vintage``
    nennt je Tat, welches ACS-Vintage fuer sie gilt, und der Verbund nimmt genau
    dieses. Ein Jahr, dessen Taten alle dasselbe Vintage tragen, bekommt damit
    einen Nenner - haette ein Jahr gemischte Vintages, waere die Rate nicht
    definiert, und die Abfrage ergaebe dann mehr als eine Zeile je Stadt, statt
    stillschweigend eines davon zu nehmen.

    Die Spalten: ``city``, ``delikte``, ``faelle``, ``einwohner``, ``rate``,
    ``rate_fallebene``. Gezaehlt werden nur Taten in einem Tract, der einer der
    beiden Staedte zugeordnet ist - derselbe Ausschnitt, fuer den der Nenner
    gilt.
    """
    # Der Nenner kommt aus ``einwohner_je_stadt`` - mit dem Vintage, das die
    # Taten dieses Jahres selbst nennen, statt mit dem Referenz-Vintage der
    # Stadtzuordnung. Beide sind fuer 2024 dasselbe; fuer 2025 und 2026 nicht,
    # und dort ist genau das die Aussage: Eine Rate fuer 2026 ruht auf der
    # Bevoelkerung von 2024, weil es keine neuere gibt.
    nenner = einwohner_je_stadt(
        dim_tract, dim_tract_acs,
        "(SELECT any_value(population_vintage) FROM j)",
    )
    return f"""
        WITH j AS (
            SELECT * FROM {fact_offense} WHERE year(date) = {jahr}
        ), e AS ({nenner})
        SELECT t.city                                            AS city,
               count(*)                                          AS delikte,
               count(*) FILTER (f.counts_case)                   AS faelle,
               any_value(e.n)                                    AS einwohner,
               round(count(*) * 1000.0 / any_value(e.n), 1)      AS rate,
               round(count(*) FILTER (f.counts_case) * 1000.0
                     / any_value(e.n), 1)                        AS rate_fallebene
        FROM j f
        JOIN {dim_tract} t ON t.geoid = f.tract_geoid
        JOIN e ON e.city = t.city
        WHERE t.city IS NOT NULL
        GROUP BY t.city
        ORDER BY t.city
    """


def raten_je_tract(fact_offense: str, dim_tract_acs: str,
                   jahr: int = RATENJAHR) -> str:
    """Taten, Faelle, Einwohner und beide Raten **je Tract** - fuer ein Jahr.

    Das Gegenstueck zu ``raten_je_stadt`` eine Ebene tiefer, und sie liegt
    hier aus demselben Grund: Seit dem 11.10.2026 zeigt eine Kibana-Kachel
    die hoechsten Tract-Raten, und ein Waechter haelt sie dagegen. Stuende
    die Abfrage im Waechter, waere sie eine Kopie der Kachel - und beide
    koennten gemeinsam falsch sein, ohne dass etwas auffaellt.

    **Tracts ohne Einwohner sind nicht enthalten.** Fuer sie ist keine Rate
    definiert; eine gezeigte Null laese sich als Sicherheit, wo in
    Wirklichkeit niemand wohnt - Flughaefen, Parks, Gewerbegebiete. Sie
    werden gezaehlt, nicht dividiert.

    **Gruppiert wird nach ``reporting_city``**, nicht nach der Stadtzuordnung
    des Tracts wie in ``raten_je_stadt``: Auf Tract-Ebene ist die Frage
    "welche Stadt hat das gemeldet", und ``geo_status = 'inside_city'``
    stellt ohnehin sicher, dass der Tract im Gebiet dieser Stadt liegt.

    Die Spalten: ``stadt``, ``geoid``, ``faelle``, ``rate_fallebene``,
    ``taten``, ``rate_tatebene``, ``einwohner`` - dieselben Namen wie in der
    Kachel, damit der Vergleich keine Umbenennung braucht. Zurueck kommen
    **alle** Tracts, absteigend nach der Fallebene; die Kachel schneidet
    selbst ab.
    """
    return f"""
        SELECT f.reporting_city                                   AS stadt,
               f.tract_geoid                                      AS geoid,
               count(*) FILTER (f.counts_case)                     AS faelle,
               round(count(*) FILTER (f.counts_case) * 1000.0
                     / any_value(a.population), 1)                AS rate_fallebene,
               count(*)                                           AS taten,
               round(count(*) * 1000.0
                     / any_value(a.population), 1)                AS rate_tatebene,
               any_value(a.population)                            AS einwohner
        FROM {fact_offense} f
        JOIN {dim_tract_acs} a
          ON a.geoid = f.tract_geoid AND a.vintage = f.population_vintage
        WHERE year(f.date) = {jahr}
          AND f.geo_status = 'inside_city'
          AND a.population > 0
        GROUP BY f.reporting_city, f.tract_geoid
        ORDER BY rate_fallebene DESC, geoid
    """


def einwohner_je_stadt(dim_tract: str, dim_tract_acs: str,
                       vintage: str = "d.reference_vintage") -> str:
    """Die Einwohnerzahl je Stadt - der Nenner jeder Rate dieses Projekts.

    Seit Vertrag 6 liegen die ACS-Masse je Vintage in ``dim_tract_acs``,
    waehrend ``dim_tract`` die Stadtzuordnung traegt. Der Nenner entsteht
    deshalb aus einem Verbund ueber **geoid und vintage**. Ohne das zweite
    Praedikat summiert die Abfrage jeden Tract so oft, wie Vintages geladen
    sind - und das Ergebnis sieht aus wie eine Zahl.

    Die Regel steht deshalb hier und nicht bei ihren Benutzern: Gebraucht wird
    sie im Driftbericht, auf der Einstiegsseite und in sechs Waechtern, die die
    Raten in den Abgabedokumenten halten. Neun Fassungen waeren acht zu viel.

    ``dim_tract`` und ``dim_tract_acs`` sind Relationsausdruecke - Tabellennamen
    oder ``read_parquet('...')``. ``vintage`` waehlt den Jahrgang; die Vorgabe
    nimmt das Referenz-Vintage der Stadtzuordnung, also denselben Stand, aus dem
    ``city`` kommt.

    **Gezaehlt wird jeder Tract mit Stadtzuordnung**, auch einer ohne eine
    einzige Tat. Die ES|QL-Kachel im Dashboard (``serving.build_kibana``)
    kommt ueber ``LOOKUP JOIN`` von den Taten her und summiert deshalb nur
    ueber Tracts, die im Jahrgang mindestens eine tragen. Am 11.10.2026 ergeben
    beide Wege denselben Nenner (2'661'953 und 638'635); ein Tract-Jahr ohne
    Tat liesse sie auseinanderlaufen, und dann weicht die Dashboardzahl von
    der Dokumentzahl ab, ohne dass eine von beiden falsch gerechnet waere.
    """
    return f"""
        SELECT d.city AS city, sum(a.population) AS n
        FROM {dim_tract} d
        JOIN {dim_tract_acs} a
          ON a.geoid = d.geoid AND a.vintage = {vintage}
        WHERE d.city IS NOT NULL
        GROUP BY d.city
    """
