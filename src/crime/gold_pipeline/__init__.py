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
    """
    return f"""
        SELECT d.city AS city, sum(a.population) AS n
        FROM {dim_tract} d
        JOIN {dim_tract_acs} a
          ON a.geoid = d.geoid AND a.vintage = {vintage}
        WHERE d.city IS NOT NULL
        GROUP BY d.city
    """
