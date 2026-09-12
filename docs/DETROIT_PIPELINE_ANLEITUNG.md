# Detroit Pipeline: Einrichtung und Betrieb

Stand: 09.09.2026. Für die Detroit-Version mit Parquet und DuckDB.

## 1. Voraussetzungen

- Windows 64 Bit auf einem Intel-/AMD-PC.
- Reguläres CPython 3.14 (kein Free-threaded-Build).
- VS Code mit Python- und Jupyter-Erweiterung für die Notebooks.
- Projektordner außerhalb OneDrive, zum Beispiel `C:\Projekte\detroit_pipeline`.

Öffne den Projektordner in VS Code. Alle folgenden PowerShell-Befehle werden im Projekt-Root ausgeführt: Dort liegen `requirements.txt`, `detroit_pipeline/`, `notebooks/` und `tests/`.

## 2. Einrichtung Schritt für Schritt

### Schritt 1: Python prüfen oder installieren

```powershell
py -V:3.14 -c "import sys, sysconfig; print(sys.version); print('Free-threaded:', sysconfig.get_config_var('Py_GIL_DISABLED'))"
```

Erwartet: Python 3.14 und `Free-threaded: 0` oder `None`.
Falls Python nicht vorhanden ist, installiere reguläres Python 3.14 für Windows x86-64 über die [offizielle Python-Downloadseite](https://www.python.org/downloads/windows/). Wähle keine Free-threaded-Variante. Öffne danach das Terminal neu und wiederhole die Prüfung.

### Schritt 2: Projektumgebung erstellen

```powershell
py -V:3.14 -m venv .venv314
```

Eine bereits korrekt eingerichtete `.venv314` kannst du weiterverwenden. Die folgenden Befehle wählen den Interpreter direkt aus; eine Aktivierung der Umgebung ist nicht nötig.

### Schritt 3: Abhängigkeiten installieren

```powershell
.\.venv314\Scripts\python.exe -m pip install --upgrade pip
.\.venv314\Scripts\python.exe -m pip install --only-binary=:all: -r requirements.txt
.\.venv314\Scripts\python.exe -m pip install ipykernel
```

Erst nach erfolgreicher Installation fortfahren.

| Bibliothek | Funktion |
|---|---|
| pyarrow | Parquet-Dateien schreiben und lesen |
| duckdb | Daten lokal importieren und mit SQL verarbeiten |
| tzdata | Zeitzonendaten für die korrekte Detroit-Zeit unter Windows |
| ipykernel | Projektumgebung als Jupyter-Kernel verwenden |

### Schritt 4: VS Code und Notebook-Kernel auswählen

1. In VS Code `Strg+Umschalt+P` → **Python: Select Interpreter** → `.venv314\Scripts\python.exe`.
2. Im Notebook **Kernel auswählen** → **Python-Umgebungen** → `.venv314`.
3. Einen bereits laufenden Kernel neu starten.
4. Im Notebook kontrollieren:

```python
import sys
print(sys.executable)
```

Der Pfad muss auf `.venv314\Scripts\python.exe` enden.

### Schritt 5: Tests ausführen

```powershell
.\.venv314\Scripts\python.exe -m tests.run_tests
```

Erwartet: **die ganze Suite, Status SUCCESS** — derzeit 585 Tests. Der Runner
sammelt mit pytest und fuehrt damit alle Pipelines aus, nicht nur Detroit.
Eine zweistellige Zahl waere ein Alarmzeichen, kein Erfolg.
Text- und JSON-Protokolle entstehen unter `logs/tests/`. Einzelne `error:`-Ausgaben mit anschließendem `ok` gehören zu den Tests ungültiger Parameter. Entscheidend ist das Gesamtergebnis.

### Schritt 6: Notebook verwenden oder per CLI laden

- `notebooks/11_detroit_source.ipynb`: das Quellen-Notebook. Es dokumentiert den Feature Layer, die Zeitzonen-Deklaration und die beiden Deliktfelder und rechnet jede Zahl selbst nach — gegen den Dienst und gegen den Bronze-Bestand.
- `notebooks/12_detroit_bronze_ingestion.ipynb`: produktiver Download. Zellen von oben nach unten ausführen. In der Konfiguration `LOAD_MODE = "FULL"` und beispielsweise `YEARS = [2024]` wählen; `RUN_DOWNLOAD = True` aktiviert den Download. Für Daily `LOAD_MODE = "DAILY"` und `DAILY_LOOKBACK_DAYS = 14` wählen; `DAILY_REFERENCE_DATE = None` verwendet den Detroit-Vortag.
- Im Lade-Notebook startet `LOAD_DUCKDB = True` in Schritt 6 den Import der gerade geladenen Runs.

Alternativ verwendest du die CLI-Befehle in den folgenden Abschnitten. Führe denselben Download nicht gleichzeitig im Notebook und per CLI aus.

## 3. Full Load
```powershell
.\.venv314\Scripts\python.exe -m detroit_pipeline.extract_detroit --mode full --years 2020 2021 2022 2023 2024 2025 2026
```

Jedes Jahr wird separat nach incident_occurred_at in America/Detroit geladen.
2025 bedeutet [2025-01-01 00:00 Detroit, 2026-01-01 00:00 Detroit).
UTC-Abfragegrenzen sind jeweils 05:00 UTC. Sommer-/Winterzeit wird per ZoneInfo umgerechnet, niemals mit einem festen Offset.
Ein laufendes Jahr enthält nur den aktuell veröffentlichten Bestand, keinen abgeschlossenen Jahresbestand.
NULL im Tatdatum wird vom Jahresfilter nicht erfasst. Für solche Zeilen braucht es eine separate spätere Reconciliation.

CLI und Notebook legen an:

- data/bronze/detroit/full/year=2025/run_<UUID>/part-0001.parquet
- im gleichen Run-Ordner: manifest.json

Direkte Python-Aufrufe extract_year(..., output_dir=...) legen nur run_<UUID> unter dem übergebenen Verzeichnis an. Jahrespartitionierung erledigt der Aufrufer.

## 4. Daily und Backfill
```powershell
.\.venv314\Scripts\python.exe -m detroit_pipeline.extract_detroit --mode daily --lookback-days 14
.\.venv314\Scripts\python.exe -m detroit_pipeline.extract_detroit --mode daily --lookback-days 14 --reference-date 2026-09-07
```

reference-date ist der letzte eingeschlossene Detroit-Kalendertag. Das Beispiel lädt updated_at im Intervall [25.08.2026 00:00 Detroit, 08.09.2026 00:00 Detroit).
Ohne Datum wird der abgeschlossene Detroit-Vortag zur Laufzeit ermittelt.
Daily hat KEINEN Tatjahresfilter: Aktualisierungen alter Fälle bleiben erreichbar.
Ordner: incremental/run_date=2026-09-07/run_<UUID>/; run_date bezeichnet hier den fachlichen Referenztag, nicht zwingend den tatsächlichen Ladetag.
Der wirkliche Ladezeitpunkt steht in den UTC-Lineage-Feldern.

Daily verwendet weiterhin updated_at. Ein zusätzlicher OR-Filter auf incident_occurred_at ist in diesem Umbau nicht hinzugefügt.
Neue Deliktzeilen werden erfasst, wenn ihr updated_at im Fenster liegt.
Nicht garantiert erfasst werden: NULL updated_at, rückdatierte Updates außerhalb des Fensters, Löschungen, oder erst verspätet veröffentlichte Zeilen mit altem updated_at.
14 Tage Overlap reduzieren Risiken, garantieren keine vollständige CDC. Nach längeren Ausfällen ein größeres Fenster/backfill verwenden und periodische Full-Abgleiche einplanen.
Ein fixer Scheduler ersetzt keinen gespeicherten Wasserstand; automatische Watermark-Fortschreibung ist nicht implementiert.

## 5. Veröffentlichung und Datenvertrag
Die ID-Liste wird vor dem Download fixiert. Doppelte/unerwartete IDs, unvollständige Mengen und Count-Abweichungen brechen den Run ab.
Die API liefert damit dennoch keinen transaktional eingefrorenen Datenstand: fachliche Änderungen während des Downloads sind möglich.
Zuerst entsteht .run_<UUID>.partial. Parquet wird in begrenzten Batches mit ZSTD geschrieben.
Nach erfolgreichem Abschluss werden Footer/Count, Hash und Manifest erstellt; erst dann wird der gesamte Ordner auf run_<UUID> umbenannt.
Bei regulär abgefangenen Fehlern wird der eigene Arbeitsordner entfernt; nach hartem Prozessabbruch können .partial-Reste bleiben. Diese niemals importieren. Vor manueller Bereinigung aktive Jobs ausschließen.

Parquet-Spalten:

| Feld | Zweck |
|---|---|
| attributes | Struct aus typisierten ArcGIS-Quellfeldern; Datumsfelder bleiben Epoch-Millisekunden |
| _feature_json | vollständiges geparstes Quellfeature einschließlich Attribute und Geometrie |
| _extra | neue Attribute/Typabweichungen als JSON |
| source_system | detroit_rms_crime |
| pipeline_run_id | UUID dieses Extraktionsruns |
| ingested_at_utc | UTC-Zeit des Run-Starts pro Zeile |

Keine Canonical-Mappings und keine fachliche Offense-Deduplizierung in diesem Writer.
Quellwerte bleiben im JSON erhalten; bei einer Typabweichung ist nur die typisierte Projektion NULL.
Das ist semantischer Erhalt des geparsten Features, keine byteidentische Archivierung der HTTP-Antwort.
Das Schema ist innerhalb eines Runs fest. Unterschiede zwischen Runs sind im Schema-Fingerprint sichtbar.
Silver darf nicht blind alle Struct-Schemata per Positions-UNION zusammenwerfen.

Das Manifest enthält unter anderem Status, Quellschema, Speicherschema, Query, lokale/UTC-Fenster, Counts, Kategorien, Run-ID, relative Dateireferenz und SHA256.
SUCCESS ist der technische Abschluss des Downloads, kein Beweis fachlicher Vollständigkeit der Quelle.
Die Kategorienstatistik zählt rohe Offense-Zeilen; sie ist keine Event- oder Canonical-Category-Statistik.

## 6. DuckDB laden
```powershell
.\.venv314\Scripts\python.exe -m detroit_pipeline.load_duckdb --manifest "data/bronze/detroit/full/year=2025/run_<UUID>/manifest.json" --database "data/warehouse/crime.duckdb"
```

<UUID> durch den tatsächlichen Run ersetzen. Mehrere Manifeste können nach --manifest angegeben werden.
Im Notebook übernimmt Schritt 6 die gerade erzeugten run_results, wenn LOAD_DUCKDB=True gesetzt ist.
Kein rekursives Laden beliebiger Dateien: nur explizite, validierte Manifeste.
Geprüft werden Formatvertrag, SUCCESS, SHA256, Schema, Counts und Lineage.
bronze.detroit_records hält Rohfeatures, source_record_id aus incident_entry_id und Herkunft.
metadata.bronze_runs hält Manifest, Importzeit und Schlüssel (source_system, source_run_id).

- gleicher Run + gleiche Bytes → SKIPPED
- gleiche Run-ID + andere Bytes → Fehler
- neuer Run mit bekannten Offenses → zusätzliche Bronze-Beobachtungen
- Importfehler → Datensätze und Ledger gemeinsam zurückrollen

Damit ist der Import desselben Runs idempotent. Ein neuer Full Load erzeugt absichtlich einen neuen Run.
COUNT(*) über alle Bronze-Runs ist deshalb KEINE Kriminalitätsstatistik.
Parquet bleibt die wiederherstellbare Dateibasis; DuckDB ist die lokale Arbeitsdatenbank.
Nur einen schreibenden Prozess für diese DuckDB-Datei betreiben. Chicago/Detroit-Importe serialisieren; Dashboard-Verbindungen bei Wartung berücksichtigen.
Es wird keine vorhandene Tabelle automatisch migriert. Namens-/Schema-Konflikte mit einer vorhandenen Datenbank zuerst in einer Kopie prüfen.

## 7. Orchestrierung
CLI ist für Cron/Windows-Aufgabenplanung verwendbar. Diese Lieferung installiert keinen Scheduler.
Scheduler setzt Arbeitsverzeichnis und den absoluten Pfad zur .venv314/Scripts/python.exe unter Windows beziehungsweise zum regulären venv-Interpreter unter Linux; stdout/stderr und Exit-Code protokollieren.
Extraktion vor Import ausführen; nach Extraktionsfehler keinen Import anstoßen.
Ein erneuter Import erfolgreicher Manifeste ist sicher. Bei mehreren Full-Jahren sind die Runs einzeln erfolgreich/fehlgeschlagen, nicht als gemeinsamer DB-Commit.
Für eine erste lokale Lösung reicht ein serieller Job mit Prozesssperre und expliziten Manifestpfaden.
Ein Wrapper für vollautomatische Run-Erkennung, Sperre und Retry-Steuerung ist noch separat einzurichten.
Täglich z. B. 07:00 Europe/Zurich planen. Detroit-Vortag wird im Code bestimmt; ein UTC-Cron muss separat korrekt konfiguriert werden.
07:00 Zürich liegt bei den heutigen Zeitzonenregeln nach Detroit-Mitternacht, garantiert aber nicht, dass die Quelle schon alle Ereignisse publiziert hat.

Monitoring: Job-Exitcode, letzte erfolgreiche Referenz, Count-Veränderungen, fehlende IDs/Datumswerte, extra_rows, Schemas, Importstatus und Speicherplatz beobachten.
Periodische Full-Abgleiche ergänzen Daily. Fehlende Zeilen erst nach erfolgreicher, vergleichbarer Vollaufnahme als mögliche Löschung markieren.

## 8. Silver als nächster Schritt
DuckDB kann sowohl Silver als auch Gold halten; VS Code ist nur das Entwicklungswerkzeug.

1. Explizite typisierte Detroit-Silver-Projektion aus Bronze erstellen und unbekannte/ungültige Werte kennzeichnen.
2. offense_key aus (source_system, incident_entry_id), event_key aus (source_system, report_number) bilden. Alle Schlüsselbestandteile als Strings behandeln.
3. Erstbeobachtung first_seen_at = frühestes ingested_at_utc; last_seen_at = späteste Beobachtung. Das ist kein polizeiliches created_at und fehlende Daily-Zeilen bedeuten keine Löschung.
4. Fachlichen Hash aus definierten Business-Feldern bilden. Technische IDs/Runzeiten ausschließen.
5. Aktuelle Offense-Version mit expliziter Reihenfolge nach Quell-Update, Beobachtungszeit und Tie-Breaker konsolidieren; NULL und gleichzeitige widersprüchliche Updates gesondert behandeln.
6. Wiederholung desselben Runs darf keine neue History erzeugen. A→B→A muss als drei Versionen darstellbar sein; (offense_key,business_hash) allein ist kein History-Primärschlüssel.
7. Full-Reconciliation nach kompatiblem Tatzeitfenster, vollständigem Snapshot und stabilen Identitäten durchführen. Reklassifikation nicht aus ähnlichen IDs als Löschung ableiten.
8. Canonical Mapping versionieren und UNREVIEWED sichtbar halten.
9. Pro Kategorie COUNT(DISTINCT event_key) beziehungsweise DISTINCT(source_system,report_number,canonical_category) zählen. Zwei Assault-Offenses desselben Reports ergeben eine Analysis Unit für ASSAULT.
10. Gesamtereignisse separat zählen. Kategoriesummen können die Gesamtzahl der Events überschreiten.

Für Chicago eigene Quelladapter, Identitäts-, Zeit- und Vollständigkeitsregeln prüfen.
Unterschiedliche Run-ID-Formate sind akzeptabel; immer zusammen mit source_system verwenden.
Gemeinsames Parquet-Format allein bedeutet kein gemeinsames Schema.
Wetter über lokale Tages-/Stundenreferenz und Raumbezug anbinden; Census über Gebiet und Erhebungsjahr/Vintage, nicht über beliebige Tagesgleichheit.
Gold-Aggregate aus Silver-Current erstellen; technische Ladezeit nie als Tatdatum verwenden.

## 9. Tests
```powershell
.\.venv314\Scripts\python.exe -m tests.run_tests
```

**585 automatisierte Offline-Tests**, davon rund 40 fuer dieses Paket. Der
Runner sammelt seit dem 11.9. mit pytest: Vorher benutzte er
`unittest.discover`, das nur `TestCase`-Klassen erkennt, und meldete SUCCESS
nach 39 von damals 448 Tests — ein gruener Lauf, der 91 Prozent der Suite nie
angefasst hatte.
tests/detroit_pipeline/test_detroit_arcgis.py: API-Client/Parser und Schlüssel.
tests/detroit_pipeline/test_bronze_ingestion.py: Ingestion, Count-Gates und Kategorieausgabe.
tests/detroit_pipeline/test_detroit_timezone.py: lokale Jahres-/Tagesfenster, UTC, DST, Zürich-Ausführungszeiten.
tests/detroit_pipeline/test_extract_detroit_cli.py: Full/Daily-CLI und Parameterfehler.
tests/detroit_pipeline/test_parquet_contract.py: Payload-Roundtrip, Typdrift, leere Runs, beschädigte Artefakte, atomare Fehlerbehandlung, wiederholter DB-Import, Overlap, Rollback und mehrere Delikte.
tests/run_tests.py schreibt je Lauf eigene Text- und JSON-Dateien unter logs/tests/. Sie werden nicht automatisch auf fünf Runs gekürzt.
Die Statistik mit fünf Datensätzen ist eine Test-Fixture, kein echter Detroit-Download.
Prüfstand für dieses Paket: Offline-Tests unter CPython 3.14.7/Windows AMD64 sowie Python 3.12/Linux bestanden. Die Tests verwenden kleine Fixtures und simulierte Quellen.
Live-API, großer Jahresdownload, realer Scheduler und gemeinsame Chicago-Integration sind durch diese Offline-Tests nicht verifiziert.

## 10. Bestehende NDJSON-Dateien
Nicht einfach die Endung ändern. Der Einzeldatei-Parser kann Legacy-NDJSON weiter lesen.
Der neue DuckDB-Importer akzeptiert ausschließlich neue Parquet-Manifeste des Vertrags 2.
Diese Lieferung enthält keinen automatischen historischen NDJSON-Migrator.
Für den Umstieg einen neuen Full-Bestand laden oder später eine geprüfte Konvertierung mit Eltern-Run-Lineage erstellen. Alte Rohdaten archivieren.
Keine alten und neuen Bestände ungeprüft für Statistiken zusammenzählen.


## 11. Projektintegration und Funktionsumfang

Die Pipeline extrahiert ArcGIS-Daten in Parquet-Runs und importiert sie transaktional in DuckDB-Bronze. Die laufübergreifende Silver-Current/History-Verarbeitung und Gold-Aggregate sind noch aufzubauen. Der vorhandene Einzeldatei-Parser ersetzt diese Konsolidierung nicht.

Bei Übernahme in das gemeinsame Repository ausschließlich die Detroit-Dateien integrieren. Gemeinsame Requirements und Test-Runner zusammenführen. `.venv314/`, andere virtuelle Umgebungen, `data/` und `logs/` in `.gitignore` ausschließen. Für geplante Jobs denselben Interpreter wie für die erfolgreichen Tests verwenden.

## 12. Fehlerbehebung

| Problem | Vorgehen |
|---|---|
| DuckDB: kein passendes Wheel oder Compilerfehler | Reguläres CPython 3.14 x86-64 verwenden. `Free-threaded: 1` passt nicht zum regulären DuckDB-Wheel dieses Pakets. Eine neue Umgebung mit dem regulären Interpreter erstellen. |
| `ModuleNotFoundError: detroit_pipeline` | Im Projekt-Root starten und prüfen, ob `detroit_pipeline/` vorhanden ist. |
| Import funktioniert im Terminal, aber nicht im Notebook | Notebook-Kernel auf `.venv314` setzen, neu starten und `sys.executable` prüfen. |
| `ZoneInfoNotFoundError` | Requirements mit dem tatsächlich verwendeten Interpreter installieren; sie enthalten `tzdata`. |
| Dateipfad zu lang | Kurzen lokalen Projektpfad außerhalb OneDrive verwenden. |

Falls die Ursache unklar bleibt:

```powershell
py -0p
.\.venv314\Scripts\python.exe -c "import sys, sysconfig; print(sys.executable); print(sys.version); print(sysconfig.get_config_var('Py_GIL_DISABLED'))"
.\.venv314\Scripts\python.exe -m pip debug --verbose
```
