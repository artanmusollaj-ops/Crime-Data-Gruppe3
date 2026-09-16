# DuckDB-Prüfskripte für Silver: Mapping, Zählregeln und Aggregate

**Basis:** zuletzt geprüftes Chicago-/Detroit-Projektpaket, Stand 16.09.2026.  
**Ausführung:** SQL in DuckDB, kein Python-Skript erforderlich.  
**Eingaben:** `data/silver/dataset=crime_offense/part-0001.parquet` und drei Mapping-/Kategorien-CSV-Dateien unter `config/`.

Die Skripte lesen Silver direkt; Gold und `analyse.duckdb` werden nicht benötigt. Sie verändern keine Projektdateien oder produktiven Tabellen. Sie erstellen ausschliesslich temporäre Tabellen/Views in der aktiven Verbindung. Die optionalen Vorher-/Nachher-Snapshots befinden sich ebenfalls nur im Speicher.

## 1. Schnellstart

1. Den Inhalt dieses Pakets beispielsweise unter `Crime-Data-Gruppe3/sql_checks/` ablegen.
2. DuckDB mit dem **Projektordner als Arbeitsverzeichnis** öffnen.
3. In `00_setup.sql` die Pfade und den Zeitraum prüfen.
4. `00_setup.sql` vollständig ausführen.
5. Danach die gewünschten Abfragen aus `01` bis `04` in **derselben Verbindung** ausführen.

Optional kann `SILVER_CHECKS_GESAMT.sql` in einer neuen Verbindung ausgeführt werden. Diese Datei kombiniert das Setup und alle Basisprüfungen 01–04. Die Reprocessing-Snapshots sind absichtlich nicht darin enthalten. Bei Verwendung dieser Gesamtdatei die Parameter direkt am Anfang dieser Datei ändern; sie sind keine automatische Referenz auf `00_setup.sql`.

Die SQL-Dateien enthalten mehrere SELECTs. Je nach Editor wird nur das letzte Ergebnis angezeigt. Um ein bestimmtes Ergebnis zu sehen, nach dem Setup den betreffenden SELECT-Block samt zugehörigem WITH markieren und ausführen. TEMP-Views müssen in derselben Verbindung verfügbar sein; manche Erweiterungen wechseln die Verbindung zwischen Tabs.

### Beispiel über die DuckDB-CLI

**PowerShell**, Pfad zur eigenen `duckdb.exe` bei Bedarf anpassen:

```powershell
Set-Location 'C:\Users\artan\Projekte\Crime-Data-Gruppe3'
& 'C:\Users\artan\duckdb_cli-windows-amd64\duckdb.exe'
```

**Danach im DuckDB-Prompt**, keine PowerShell-Befehle mehr:

```text
.read sql_checks/00_setup.sql
.read sql_checks/01_schluessel_zaehlregeln.sql
.read sql_checks/02_mapping.sql
.read sql_checks/03_zeitfenster.sql
.read sql_checks/04_aggregate.sql
```

`.read` ist ein CLI-Befehl. Im SQL-Editor einer VS-Code-Erweiterung stattdessen den SQL-Inhalt ausführen. Wenn relative Pfade nicht gefunden werden, in den SQL-Dateien absolute Pfade mit `/` verwenden, beispielsweise `C:/Users/artan/Projekte/Crime-Data-Gruppe3/data/...`.

## 2. Zeitraum und Stichtag einstellen

Die Parameter stehen in `00_setup.sql`:

```sql
CREATE OR REPLACE TEMP TABLE audit_parameters AS
SELECT DATE '2024-01-01' AS scope_start,
       DATE '2025-01-01' AS scope_end_exclusive,
       DATE '2025-01-01' AS completed_before_local,
       FALSE AS exclude_unfounded;
```

| Gewünschter Zeitraum | `scope_start` | `scope_end_exclusive` |
|---|---|---|
| Ganzes Jahr 2024 | 2024-01-01 | 2025-01-01 |
| Juni 2024 | 2024-06-01 | 2024-07-01 |
| 9. November 2024 | 2024-11-09 | 2024-11-10 |

Die Grenzen sind **lokale Kalendergrenzen je Stadt**. Ein halb offenes Fenster enthält den Beginn und schliesst das Ende aus.

`completed_before_local` ist die Mitternacht **nach** dem letzten fachlich abgeschlossenen Tat-Tag. Für die Aussage „Daten bis einschliesslich 13.09.2026“ wird `2026-09-14` eingetragen. Das ist kein Ladezeitpunkt und kein Filter auf `updated_at`.

Der Setup-Check verlangt `Beginn < Ende <= Abschlussgrenze`. Für unterschiedliche fachliche Stichtage je Stadt wären getrennte Läufe oder eine Erweiterung auf eine stadtspezifische Parametertabelle erforderlich.

`exclude_unfounded = FALSE` entspricht der bisherigen Übernahme dieser Zeilen in die Kennzahlen. Bei `TRUE` werden sie aus den Analyseprofilen ausgeschlossen, aber `counts_case` wird **nicht neu gerankt**. S08 zeigt einen möglichen Rangfolgekonflikt. Bei Chicago ist `unfounded` im aktuellen Schema unbekannt (`NULL`); es wird nicht als ausgeschlossen behandelt. Das beweist keine Bestätigung der Tat.

Ein anderes Analysefenster lässt sich nach dem Setup auch direkt einstellen:

```sql
UPDATE audit_parameters
SET scope_start = DATE '2024-06-01',
    scope_end_exclusive = DATE '2024-07-01';
```

Dabei selbst auf gültige Grenzen achten oder den Parametercheck aus 00 erneut ausführen. Nicht nochmals den ganzen Setup-Block mit den alten Datumswerten ausführen.

## 3. Was die Skripte prüfen

| Datei | Prüfungen | Interpretation |
|---|---|---|
| `00_setup.sql` | Parameter, Quelle und Referenzen | Doppelte Referenzschlüssel stoppen das Setup, bevor ein Join Zahlen vervielfacht |
| `01_schluessel_zaehlregeln.sql` | IDs, Gruppierung, `counts`, `counts_case`, Textvarianten | Technische Fehler und fachliche Auswahlwirkung getrennt |
| `02_mapping.sql` | Status, Zielcodes gegen CSV, unbekannte Codes, Kategorien und Herkunft | Abgleich der Umsetzung mit aktuellen Referenzen; kein Beweis der polizeilichen Fachsemantik |
| `03_zeitfenster.sql` | NULL-Zeiten, Datumskonsistenz, Scope/Stichtag, Zeitzonenumrechnung und Abdeckung | Prüfung lokaler Tatzeit; fehlende Tage nicht automatisch als null Fälle interpretieren |
| `04_aggregate.sql` | Zähleinheiten, Tag/Woche/Monat, DISTINCT-Additivität und Auswahlwirkung | Keine Vermischung von Reports, Deliktzeilen und Hauptdelikt-Auswahl |
| `05_snapshot_vorher.sql` | Kopie vor ETL-Reprocessing | Nur optional, vor dem neuen Verarbeitungslauf |
| `06_reprocessing_vergleich.sql` | Inhalt, Referenzen und Aggregate vorher/nachher | Wiederholung bei identischen Eingaben muss unverändert bleiben; neue Daten dürfen Unterschiede erzeugen |

### Prüfungen mit normalerweise leerem Ergebnis

- **S02–S06:** Schlüssel- und Auswahlkonsistenz. S05/S06 prüfen den bestehenden Vertrag, nicht dessen fachliche Eignung.
- **M02, M03, M05, M07, M09:** Mappingkonsistenz; ein bewusst geänderter Mappingstand kann bei M03 zunächst eine Abweichung erklären.
- **Z01, Z03, Z05:** fehlende/inkonsistente Zeit, Stichtagsüberschreitung oder Umrechnungsabweichung. Bei Z05 kann auch eine nicht existierende Chicago-Quellzeit die Ursache sein.
- **A06:** Zeilenzahlaggregation auf zwei Wegen muss übereinstimmen.
- **R03–R05:** bei exakt gleichen Eingaben, Konfigurationen und Regeln keine Änderungen.

**Z02 hat eine Sonderrolle:** Es prüft, ob der gesamte Silver-Bestand im Analysefenster liegt. Bei einer Datei mit dem ganzen Jahr und einem Juni-Analysefenster sind Treffer ausserhalb Juni erwartbar. Diese Abfrage ist nur dann ein Fehlercheck, wenn die ganze Datei auf den konfigurierten Scope beschränkt sein soll.

S07, S08, S09, M04, M06, M08, Z06, Z07, A03 und A04 sind Review- beziehungsweise Profilabfragen. Treffer werden nicht automatisch gelöscht oder umgemappt.

## 4. Die vier Zählperspektiven

Die Aggregate zeigen bewusst:

1. Aktuelle Silver-Offense-Zeilen.
2. Durch `counts` ausgewählte Deliktzeilen.
3. Unterschiedliche Reports je Kategorie, einmal auf allen Offenses und einmal auf den durch `counts` ausgewählten Offenses.
4. Die über `counts_case` markierten Hauptdeliktzeilen.

`COUNT(DISTINCT event_id)` gilt immer innerhalb einer Stadt und des betreffenden Zeitraums. NULL-Report-IDs würden von COUNT DISTINCT ignoriert; deshalb zuerst S03 prüfen.

Die normale Kategorie ist `nibrs_category` aus der Referenzdatei. A05 verwendet zusätzlich die ausdrücklich ausgewiesene Beispieldefinition für die drei Fokus-Kategorien:

- ASSAULT: `13A`, `13B`, `13C`;
- VEHICLE_THEFT: `240`;
- ARSON: `200`.

Ein Report kann mehrere Kategorien enthalten. Die Summe der Kategorie-Reports muss deshalb nicht der Gesamtzahl unterschiedlicher Reports entsprechen. Auch tägliche DISTINCT-Reports sind nicht immer zu Wochen-/Monats-DISTINCT-Reports addierbar. A03 zeigt diese Unterschiede; A02 berechnet jeden Zeitraum direkt aus Einzelzeilen.

Wochen beginnen in A02/A03 am Montag. Schneidet das Analysefenster eine Woche oder einen Monat ab, ist die Gruppe nur eine **Teilperiode**. Das Datum der Woche kann vor `scope_start` liegen, obwohl alle eingehenden Taten innerhalb des Fensters liegen. Periodenbeginn ist nicht Tatdatum.

## 5. Mapping-Review und Freigabe: Grenzen dieser Prüfungen

M06 zeigt `nicht_exakt_prozent`, **keine belastbare Quote offener Mappingreviews**. Ein freigegebener Fallback kann für ein Produkt zulässig sein; ein als exact eingestufter Code kann trotzdem eine bislang unbekannte widersprüchliche Beschreibung tragen.

Die aktuelle Silver-Tabelle besitzt keinen verbindlichen `review_required`-/Freigabestatus. Deshalb setzen diese Skripte keinen 5-%- oder 20-%-Freigabeschwellwert und veröffentlichen nichts automatisch.

Weitere Grenzen:

- `offense_category`, `charge_description`, `arrest_charge` und die ursprüngliche Quellversionszeit sind im gemeinsamen Silver nicht vollständig verfügbar. Deren Widersprüche benötigen eine Rückverfolgung nach Bronze.
- Ein Abgleich mit derselben Mapping-CSV prüft Umsetzungskonsistenz, nicht unabhängig deren fachliche Richtigkeit.
- Gleiche Beschreibung bedeutet nicht automatisch dasselbe Delikt. Textvarianten sind Reviewkandidaten, keine automatische Dedup-Regel.
- Ein leeres Tatdatum kann durch den Jahresfilter bereits in Bronze ausgeschlossen worden sein. Null NULL-Werte in Silver beweisen deshalb keine vollständig erfasste Quelle.
- Ein vorhandener Kalendertag und ein korrektes Maximum beweisen keine Meldevollständigkeit.
- Z05 prüft den UTC-/Lokalzeit-Zusammenhang, kann aber mehrdeutige Chicago-Wanduhrzeiten nicht nachträglich auflösen.
- `replaced_by`-Sonderregeln aus Gold werden nicht still angewandt. Geprüft wird das vorhandene Silver-NIBRS-Mapping.

## 6. Reprocessing kontrolliert prüfen

1. In einer DuckDB-Verbindung `00_setup.sql` ausführen.
2. `05_snapshot_vorher.sql` ausführen. Dadurch werden Silver und die Referenzen kopiert.
3. Die Verbindung offen lassen. Den ETL-Neuaufbau in einem anderen Terminal starten.
4. Nach Abschluss `00_setup.sql` erneut ausführen, mit **denselben Analyseparametern**. Dadurch werden Quelle und aktuelle Referenzen neu eingelesen.
5. **Nicht** erneut 05 ausführen.
6. `06_reprocessing_vergleich.sql` ausführen.

Erwartung bei gleichen Eingaben und Regeln:

- R02: 0 unterschiedliche Parameter-/Referenzzeilen;
- R03: 0 Zeilen nur vorher und 0 nur nachher;
- R04: keine geänderten/neuen/fehlenden Silver-IDs;
- R05: keine abweichenden Tages-/Wochen-/Monatsaggregate.

Bei einer echten Korrektur müssen R04/R05 dagegen die Auswirkungen zeigen. Eine Verschiebung von Juni nach Juli soll die alte und die neue Periode betreffen. `NICHT_MEHR_IM_SILVER` beweist keine Löschung im Polizeisystem.

Die Kopie umfasst die 25 explizit in 00 ausgewählten gemeinsamen Felder. Neue Zusatzfelder wie DST-Flags und die Manifeste werden durch R03 nicht verglichen. Die Skripte beweisen keine unveränderte Bronze-Eingabe: Diese Voraussetzung anhand von Run-IDs, Prüfsummen und Mapping-/Codeversion separat dokumentieren.

Die Verbindung muss währenddessen bestehen bleiben. Die TEMP-Snapshots sind keine dauerhafte Historisierung. Für einen Vergleich über Sitzungsgrenzen hinweg müssen die Stände kontrolliert separat gespeichert werden.

## 7. Validierung auf deinem Paket

Getestet mit DuckDB **1.5.5** gegen das hochgeladene Silver für 2024 und gegen den aus demselben Bronze neu aufgebauten Silver-Stand. Die Skripte benötigen die neuen DST-Spalten nicht und funktionieren damit auch auf dem mitgelieferten älteren Parquet-Schema.

Erwartete Beobachtungen bei unveränderten 2024-Daten:

| Check | Beobachtung |
|---|---|
| S01 | Chicago 259.615; Detroit 88.686 Silver-Zeilen |
| S02 | Keine doppelten/fehlenden Offense-Schlüssel |
| S07 | 2.763 Gruppen mit verschiedenen NIBRS-Zielen; fachliche Reviewkandidaten |
| M03 | Keine Abweichung zu den mitgelieferten Code-Mappingreferenzen |
| M04 | Chicago `1481`: drei Zeilen ohne aktivierte Zuordnung |
| Z01 | Keine fehlenden/inkonsistenten Silver-Tatzeiten |
| Z06 | Sechs Reports mit mehr als einem lokalen Tat-Tag |
| A03 | Acht Wochen-/Monatsgruppen mit Unterschied zur Summe täglicher DISTINCT-Zählungen |
| A04 | 22 Kategorien mit Report-/Kategorie-Kombinationen, die durch `counts` nicht mehr vertreten sind |

Zusätzlich geprüft:

- Detroit, 09.11.2024, ASSAULT: 82 ausgewählte Deliktzeilen, 80 Reports, 78 Hauptdeliktzeilen.
- Detroit, Juni 2024, ASSAULT: 2.208 ausgewählte Deliktzeilen, 2.195 Reports.
- Identischer Snapshot: keine Inhalts- oder Aggregatänderung.
- Kontrollierte Datum-/Kategorieänderung: alte und neue Tages-, Wochen- und Monatsgruppen werden sichtbar.
- Doppelte Schlüssel im Vergleichssnapshot werden zurückgewiesen.

Diese Validierung bedeutet nicht, dass die bestehenden fachlichen Auswahlregeln bereits freigegeben sind. Die Skripte machen ihre Wirkung prüfbar.

`validation_results.json` dokumentiert die Ausführung samt kleinen Ergebnisproben. Es ist Prüfevidenz, kein produktiver Testlauf-Logger. Nach fachlicher Abnahme können ausgewählte Checks im nächsten Schritt als ETL-Tests eingebaut werden.
