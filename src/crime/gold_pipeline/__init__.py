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

Gold behaelt deshalb das Korn und macht die Faktentabelle **abfragbar**: ein
Sternschema mit einer Faktentabelle je Delikt und vier kleinen Dimensionen.
Jede Frage wird damit ein Filter und ein ``GROUP BY`` auf einer Tabelle.

| Tabelle | Korn |
| --- | --- |
| ``fact_offense`` | ein Delikt |
| ``dim_tract`` | ein Census Tract, mit Stadtzuordnung und Einwohnerzahl |
| ``dim_offense`` | ein NIBRS-Delikt |
| ``dim_date`` | ein Kalendertag |
| ``dim_city_day`` | Stadt und Tag, mit dem Wetter |

Anders als Silver wird Gold **ersetzt und nicht angehaeuft**: Es ist vollstaendig
aus Silver ableitbar, und die Herkunft steht im Manifest.
"""

from __future__ import annotations

from pathlib import Path


GOLD_LAYER = "gold"
SILVER_LAYER = "silver"
PARQUET_FILE = "part-0001.parquet"

# Die beiden Staedte ueber ihre FIPS-Ortsnummer. Ueber den Namen zu gehen waere
# falsch: Illinois fuehrt neben Chicago city auch ein Detroit village.
STUDIENSTAEDTE = {
    "1714000": "chicago",
    "2622000": "detroit",
}

# Ab diesem Flaechenanteil gehoert ein Tract zur Stadt. Tracts liegen nicht
# sauber in Stadtgrenzen - sie ueberschreiten sie. Die Mehrheitsregel gibt
# jedem Tract genau eine Stadt und ist damit eindeutig; an den Falldaten
# geprueft trifft sie die amtliche Einwohnerzahl gut (siehe
# notebooks/34_gold_sternschema.ipynb).
STADT_SCHWELLE = 0.5


def table_dir(data_root: Path, table: str) -> Path:
    """Wohin eine Gold-Tabelle geschrieben wird."""
    return data_root / GOLD_LAYER / f"dataset={table}"
