"""Die Serving-Schicht: die Auswertungsumgebung des Projekts.

Bis hierher sind die Daten aufbereitet, aber nicht benutzbar. Wer eine Frage
hat, muesste heute wissen, dass die Delikte unter
``data/silver/dataset=crime_offense/part-0001.parquet`` liegen, und das in jede
Abfrage schreiben. Das ist der Unterschied zwischen *vorhanden* und
*abfragbar*.

Diese Schicht schliesst ihn mit einer DuckDB-Datei voller **Sichten**:

    SELECT c.tract_geoid, count(*) * 100000.0 / any_value(t.population) AS rate
    FROM crime_offense c JOIN tract t ON c.tract_geoid = t.geoid
    GROUP BY 1 ORDER BY rate DESC;

**Sichten, nicht Tabellen.** Die Datei haelt keine Daten - sie haelt Namen. Das
ist gemessen und nicht angenommen (Absprache 5.3, Notebook 33):

===========================  ==========  ================
Ad-hoc-Abfrage               Sichten     Materialisiert
===========================  ==========  ================
Filter und Gruppierung          1,6 ms           2,2 ms
Join Delikt x Tract             3,2 ms           3,6 ms
Drei-Wege-Join                  4,0 ms           4,2 ms
Dateigroesse                    0,3 MB          45,1 MB
===========================  ==========  ================

Sichten sind also nicht langsamer, teils schneller: DuckDB liest Parquet nativ
mit Projektions- und Praedikat-Pushdown, und bei dieser Datenmenge gibt es
keinen Dekodier-Aufwand, der sich messen liesse.

Drei Gruende sprechen ausserdem dagegen, die Daten ein zweites Mal abzulegen:

1. **Eine Kopie kann veralten.** Nach einem Silver-Neubau sind Sichten sofort
   aktuell; eine materialisierte Tabelle zeigt den alten Stand, bis jemand neu
   importiert - und niemand sieht ihr an, dass sie es tut.
2. **Eine Kopie ist eine zweite Wahrheit.** Absprache 7.1 haelt die
   dateibasierten Schichten als Speicher fest, DuckDB als Abfrageschicht
   darueber.
3. **Sie kostet Platz ohne Gegenwert** - hier das 150-fache.

**Eigene Tabellen gehen trotzdem.** Die Datei ist eine echte Datenbank; wer ein
Zwischenergebnis behalten will, legt daneben eine Tabelle an::

    CREATE TABLE meine_auswertung AS SELECT ...;

Die Sichten bleiben Sichten, das Arbeitsergebnis liegt in derselben Datei.
Rohdaten und eigene Arbeit bleiben getrennt, ohne zwei Dateien zu jonglieren.

Die Datei selbst ist **abgeleitet und wegwerfbar**: Sie wird nicht versioniert
und jederzeit aus den Schichten neu erzeugt.
"""

from __future__ import annotations

SERVING_LAYER = "serving"
DATABASE_NAME = "analyse.duckdb"
