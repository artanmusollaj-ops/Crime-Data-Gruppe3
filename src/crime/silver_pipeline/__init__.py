"""Die Silver-Schicht: aus mehreren Quellen werden vergleichbare Tabellen.

Bronze haelt je Quelle einen unveraenderten Schnappschuss. Silver ist die
erste Schicht, die **deutet**: Typen setzen, Einheiten aufloesen, Fehlwerte
als solche kennzeichnen, Schluessel harmonisieren, Quellen zusammenfuehren.

Die Quellen haben drei verschiedene Koerner, deshalb gibt es nicht eine
Tabelle, sondern drei:

===========================  ==========================================
``tract``                    eine Zeile je Census Tract
``crime_offense``            eine Zeile je Delikt
``weather_day``              eine Zeile je Stadt und Tag
===========================  ==========================================

Sie in eine Tabelle zu zwingen wuerde entweder Zeilen vervielfachen - ein
Wetterwert an jedem Delikt derselben Stadt und desselben Tages - oder
Information wegwerfen. Zusammengefuehrt wird erst in Gold, dort auf dem
Aggregationskorn.

Werkzeug ist DuckDB mit der ``spatial``-Extension (Absprache 5.3). Es liest
Bronze direkt, gleichgueltig ob Parquet oder NDJSON, sodass die noch offene
Formatfrage aus Absprache 4.1 die Silver-Schicht nicht aufhaelt.

Anders als Bronze sind Silver-Tabellen **abgeleitet und wiederherstellbar**.
Sie werden deshalb ersetzt und nicht als Lauf angehaeuft; das Manifest nennt
aber die ``run_id`` jedes Bronze-Laufs, aus dem die Tabelle entstanden ist -
ohne diese Herkunft ist der Referenzstand aus Absprache 7.1 nicht belegbar.
"""

SILVER_LAYER = "silver"
BRONZE_LAYER = "bronze"

# Der Fehlwert des ACS. In Bronze bleibt er unveraendert stehen; ihn zu deuten
# ist ausdruecklich Aufgabe dieser Schicht.
ACS_MISSING_VALUE = "-666666666"
