# Detroit RMS Crime – ArcGIS REST Extraction und Parsing

Dieses kleine Paket implementiert eine nachvollziehbare Batch-Pipeline fuer die
offiziellen Detroit-RMS-Crime-Daten. Es trennt bewusst zwei Aufgaben:

1. **Extraction/Bronze:** Die ArcGIS-Features werden source-nah und unveraendert
   als NDJSON gespeichert.
2. **Parsing/Silver:** Zeit, Geometrie, Schluessel und Deliktkategorien werden
   normalisiert; problematische Datensaetze bleiben mit Quality Flags erhalten.

Die Quelle ist ein oeffentlicher ArcGIS Feature Layer:

```text
https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/
RMS_Crime_Incidents/FeatureServer/0
```

## Dateien

| Datei | Aufgabe |
|---|---|
| `detroit_arcgis.py` | ArcGIS-Client, Retry, ID-Pagination und Parser |
| `extract_detroit.py` | kompletter Jahresdownload und inkrementelles Update-Fenster in Bronze |
| `transform_detroit.py` | Bronze-nach-Silver-Transformation |
| `../tests/test_detroit_arcgis.py` | Unit Tests fuer Parser und Hilfsfunktionen |
| `../tests/test_bronze_ingestion.py` | Bronze-Integrationstest mit Kategorie- und Gesamtzahlen |
| `../notebooks/05_detroit_bronze_ingestion.ipynb` | dokumentierter Bronze-Download im Jupyter Notebook |
| `../DETROIT_PIPELINE_ANLEITUNG.md` | vollstaendige Installations-, Betriebs-, Test- und Uebergabeanleitung |
| `../DETROIT_10_LONG_LAG_EVENTS.md` | zehn reale Mehrfachdelikt-Events zur fachlichen Einordnung von `updated_at` |
| `requirements.txt` | optionale Parquet-Abhaengigkeit |

## Warum Object-ID-Pagination?

Der ArcGIS Layer erlaubt maximal 2.000 Features pro Antwort. Eine reine
Offset-Pagination kann bei gleichzeitigen Inserts oder Updates Zeilen
ueberspringen oder doppelt liefern. Der Extractor:

1. fragt den serverseitigen Count ab;
2. fixiert alle passenden `ESRI_OID`-Werte;
3. sortiert die IDs;
4. laedt exakt diese IDs in Batches;
5. prueft ID-, Download- und Server-Count;
6. schreibt ein Run-Manifest mit Schema-Hash und Checksumme.

## Installation

Im Elternverzeichnis des Pakets:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r detroit_pipeline/requirements.txt
```

Ohne `pyarrow` funktionieren Download, CSV, NDJSON und Tests trotzdem.

## Verwendete Libraries und Module

Die Bronze-Pipeline ist bewusst schlank aufgebaut. Fuer ArcGIS REST wird kein
Selenium und keine zusaetzliche HTTP-Library wie `requests` benoetigt. Der
Download verwendet ausschliesslich die Python-Standardbibliothek. Dadurch gibt
es weniger Abhaengigkeiten, kleinere Laufzeitumgebungen und weniger potenzielle
Versionskonflikte.

### Externe Abhaengigkeiten

| Library | Typ | Funktion im Projekt | Erforderlich fuer |
|---|---|---|---|
| `pyarrow` | Runtime, optional | Erzeugt komprimierte Parquet-Dateien mit Zstandard-Kompression | Silver-Ausgabe als `.parquet` |
| `jupyter` | Entwicklungsumgebung | Startet und verwaltet das Bronze-Ingestion-Notebook | interaktive Notebook-Ausfuehrung |
| `ipykernel` | Entwicklungsumgebung | Stellt die virtuelle Python-Umgebung als auswaehlbaren Jupyter-Kernel bereit | korrekte Notebook-Umgebung |

Nur `pyarrow` steht in `requirements.txt`, weil es die einzige externe
Abhaengigkeit der eigentlichen Pipeline ist. `jupyter` und `ipykernel` werden
nur fuer die lokale Notebook-Arbeit installiert:

```bash
python -m pip install --upgrade pip
pip install -r detroit_pipeline/requirements.txt
pip install jupyter ipykernel
python -m ipykernel install --user \
  --name crime-data \
  --display-name "Python (Crime Data)"
```

### Python-Standardbibliothek in der Pipeline

| Modul | Funktion im Projekt |
|---|---|
| `urllib.request`, `urllib.parse`, `urllib.error` | HTTP-GET/POST, Parameter-Encoding und Fehlerbehandlung fuer ArcGIS REST |
| `json` | Lesen der API-Antworten sowie Schreiben von NDJSON, Manifesten, Quality- und Testreports |
| `pathlib` | Betriebssystemunabhaengige Projekt-, Bronze-, Silver- und Logpfade |
| `datetime`, `zoneinfo` | Full-/Daily-Zeitfenster, UTC-Zeitpunkte und Zeitzone `America/Detroit` |
| `hashlib` | SHA-256-Schluessel, Schema-Fingerprint und Dateipruefsumme |
| `uuid` | Eindeutige `pipeline_run_id` fuer jeden Bronze-Lauf |
| `logging` | Warnungen bei Retries und technische Laufmeldungen |
| `time`, `random` | Pause, exponentielles Backoff und Jitter zwischen API-Wiederholungen |
| `argparse` | Kommandozeilenparameter fuer Extraction und Transformation |
| `csv` | Optionale Silver-Ausgabe als CSV |
| `dataclasses`, `typing` | Strukturierte Layer-Metadaten und Typdefinitionen |

### Python-Standardbibliothek fuer Tests

| Modul | Funktion im Projekt |
|---|---|
| `unittest` | Test-Discovery, Assertions, Status `ok`/`FAIL`/`ERROR` und Tracebacks |
| `tempfile` | Isolierte temporaere Bronze-Verzeichnisse ohne produktive Daten zu veraendern |
| `contextlib` | Leitet Terminalausgabe gleichzeitig in den Test-Log um |
| `time.perf_counter` | Misst die Dauer des gesamten Testlaufs |

### Abhaengigkeiten nach Pipeline-Stufe

| Pipeline-Schritt | Benoetigte externe Library |
|---|---|
| ArcGIS-Metadaten und Count | keine |
| Bronze Full Load | keine |
| Bronze Daily Load | keine |
| Silver als CSV oder NDJSON | keine |
| Silver als Parquet | `pyarrow` |
| Automatisierte Tests und Testlogs | keine |
| Jupyter Notebook interaktiv starten | `jupyter`, `ipykernel` |

`__pycache__` ist keine Library und keine `pyarrow`-Komponente. Python erzeugt
diesen Ordner automatisch fuer kompilierten Bytecode (`*.pyc`). Er kann
geloescht werden und sollte mit `__pycache__/` sowie `*.py[cod]` in `.gitignore`
ausgeschlossen werden.

## Schritt 1: Bronze extrahieren

```bash
python -m detroit_pipeline.extract_detroit \
  --year 2024 \
  --output-dir data/bronze/detroit
```

Optional kann die API staerker geschont werden:

```bash
python -m detroit_pipeline.extract_detroit \
  --year 2024 \
  --batch-size 1000 \
  --pause-seconds 0.2 \
  --output-dir data/bronze/detroit
```

Ergebnis:

```text
detroit_rms_crime_2024_<RUN_ID>.ndjson
detroit_rms_crime_2024_<RUN_ID>.manifest.json
```

Bronze enthaelt weiterhin die originalen `attributes` und `geometry`. Unter
`_meta` werden nur technische Provenance-Felder ergaenzt.

## Schritt 2: Nach Silver transformieren

Empfohlenes Parquet-Format:

```bash
python -m detroit_pipeline.transform_detroit \
  data/bronze/detroit/detroit_rms_crime_2024_<RUN_ID>.ndjson \
  --output data/silver/detroit_crime_2024.parquet
```

Zum Debuggen als CSV:

```bash
python -m detroit_pipeline.transform_detroit \
  data/bronze/detroit/detroit_rms_crime_2024_<RUN_ID>.ndjson \
  --output data/silver/detroit_crime_2024.csv
```

Neben der Silver-Datei entsteht ein `*.quality.json` mit:

- Anzahl Silver-Zeilen;
- Anzahl unterschiedlicher Events und Offenses;
- Anzahl analyseberechtigter Zeilen;
- Mapping-Status;
- Haeufigkeit der Quality Flags.

Bereits die Bronze-Ingestion zeigt nach dem Download die Anzahl der geladenen
Datensaetze pro `offense_category` und die Gesamtzahl an. Dieselben Werte stehen
im Run-Manifest unter `offense_category_counts` und `downloaded_count`.

## Full Load und Daily Load im Notebook

Das Notebook trennt den Betriebsmodus vom Startschalter:

```python
LOAD_MODE = "FULL"       # oder "DAILY"
RUN_DOWNLOAD = False     # erst nach der Count-Pruefung auf True setzen
YEARS = [2023, 2024]
DAILY_LOOKBACK_DAYS = 14
```

Der Full Load filtert nach `incident_occurred_at` und erzeugt eine Partition je
Kalenderjahr:

```text
data/bronze/detroit/full/year=2024/
```

`incident_occurred_at` ist der gemeldete Tat-/Ereigniszeitpunkt, nicht der
Zeitpunkt der erstmaligen Datenerfassung. Jeder Wert in `YEARS` wird als eigenes
halb-offenes Kalenderintervall geladen. Bronze uebernimmt dabei alle passenden
Offense-Zeilen unabhaengig von Kategorie oder Fallstatus. Eine `report_number`
kann deshalb mehrfach vorkommen; die einzelnen Delikte besitzen unterschiedliche
`incident_entry_id`-Werte.

Der Daily Load filtert nach `updated_at`. Dadurch enthaelt er sowohl neue
Records als auch nachtraegliche Aenderungen innerhalb des 14-Tage-Fensters:

```text
data/bronze/detroit/incremental/run_date=2026-09-05/
```

Das Fenster ist halb-offen (`window_start <= updated_at < window_end`) und
umfasst den Lauftag plus die 13 vorherigen Kalendertage. Die Ueberlappung ist
beabsichtigt, damit verspaetete Aenderungen nicht verloren gehen. Silver muss
Daily-Daten idempotent anhand `offense_key` zusammenfuehren und bei mehreren
Versionen die Zeile mit dem neuesten `source_updated_at_utc` behalten.

Der Filter arbeitet auf einzelnen Offense-Zeilen. Er kann damit einen neuen
Report, eine neue Offense zu einem vorhandenen Report oder eine erneut
publizierte beziehungsweise geaenderte Offense laden, sofern Detroit deren
`updated_at` in das Fenster setzt. Auch ein Jahre alter Vorfall wird erfasst,
wenn er heute aktualisiert wird. Nicht erfasst werden geloeschte Source-Records,
Records mit `updated_at = null` sowie Aenderungen, bei denen die Quelle
`updated_at` nicht fortschreibt.

Ein spaetes `updated_at` beweist fuer sich allein keine fachliche Aenderung. Bei
untersuchten Mehrfachdelikten war der Wert fuer alle Offense-Zeilen desselben
Events identisch, waehrend `case_status_updated_at` und `updated_in_ibr_at`
deutlich frueher lagen. Das kann auf eine technische Neupublikation hindeuten.
Die spaetere Silver-Konsolidierung sollte deshalb fachliche Felder per
`business_hash` vergleichen und zwischen `BUSINESS_UPDATE`,
`TECHNICAL_REFRESH` und `UNCHANGED` unterscheiden.

Das Run-Manifest macht den Vertrag maschinenlesbar:

| Manifestfeld | FULL | INCREMENTAL |
|---|---|---|
| `date_field` | `incident_occurred_at` | `updated_at` |
| `selection_basis` | `INCIDENT_OCCURRENCE_TIME` | `SOURCE_LAST_UPDATED_TIME` |
| `record_granularity` | `INCIDENT_OFFENSE` | `INCIDENT_OFFENSE` |
| `window_is_half_open` | `true` | `true` |
| `captures_source_deletions` | `false` | `false` |

## Zaehlsemantik

Detroit publiziert eine Zeile je Offense Charge. Mehrere Zeilen koennen deshalb
zum selben Polizeifall gehoeren. Das Paket erzeugt drei verschiedene Schluessel:

```text
offense_key       = SHA256(source_system | source_record_id)
event_key         = SHA256(source_system | report_number)
analysis_unit_key = SHA256(source_system | report_number | canonical_category)
```

Fuer vergleichbare Gold-Aggregate sollte verwendet werden:

```sql
COUNT(DISTINCT analysis_unit_key)
```

Dadurch werden mehrere Offense Charges desselben Falls innerhalb derselben
Canonical Category nur einmal gezaehlt. Ein Fall darf aber weiterhin in zwei
unterschiedlichen Kategorien vorkommen.

## Mapping im Beispiel

| Detroit `offense_category` | Canonical Category |
|---|---|
| `ROBBERY` | `ROBBERY` |
| `BURGLARY` | `BURGLARY` |
| `LARCENY` | `THEFT` |
| `STOLEN VEHICLE` | `VEHICLE_THEFT` |
| `ASSAULT` | `ASSAULT` |
| `AGGRAVATED ASSAULT` | `ASSAULT` |

Alle anderen Werte erhalten `mapping_status=UNREVIEWED`. Das ist absichtlich
strenger als ein automatisches Mapping auf `OTHER`.

`UNFOUNDED`-Falle bleiben in Silver nachvollziehbar, erhalten aber
`analysis_eligible=false`.

## Tests ausfuehren

Der separate Testordner ist wie folgt aufgebaut:

```text
tests/
├── __init__.py
├── test_detroit_arcgis.py
└── test_bronze_ingestion.py
```

`tests/__init__.py` kennzeichnet den Ordner als Python-Paket und enthaelt keine
fachliche Logik.

`tests/test_detroit_arcgis.py` enthaelt neun Unit Tests fuer:

- das Mapping von `STOLEN VEHICLE` auf `VEHICLE_THEFT`;
- den Ausschluss von `UNFOUNDED` aus der Analyse;
- die explizite Behandlung unbekannter Deliktkategorien;
- das Quality Flag fuer ein fehlendes `updated_at`;
- unterschiedliche Offense Keys, denselben Event Key und denselben
  Analysis-Unit-Key bei zwei Delikten derselben Canonical Category;
- halb-offene Jahresfilter auf `incident_occurred_at`;
- halb-offene Daily-Filter auf `updated_at`;
- die Allowlist fuer erlaubte Datumsfelder;
- die Aufteilung der Object-IDs in API-konforme Batches.

`tests/test_bronze_ingestion.py` enthaelt drei Integrationstests fuer:

- den Full-Load-Vertrag mit `incident_occurred_at` als Zeitachse;
- Datensatzanzahl je Deliktkategorie und die Gesamtzahl;
- den inkrementellen Daily Load inklusive `updated_at`-Filter, Zeitfenster,
  Dateiname, Manifest, Auswahlsemantik und Download-Count.

Die Integrationstests verwenden einen kontrollierten `FakeArcGISClient`. Sie
fuehren keine echten HTTP-Requests oder Downloads aus. Dadurch bleiben lokale
Testlaeufe und CI reproduzierbar und unabhaengig von der Verfuegbarkeit der
Detroit-API.

Alle zwoelf Tests werden aus dem Projekt-Root gestartet:

```bash
python -m unittest discover -s tests -v
```

Ein erfolgreicher Lauf endet mit:

```text
Ran 12 tests
OK
```

### Testlauf dauerhaft protokollieren

Der empfohlene Test-Runner zeigt dieselben Ergebnisse im Terminal und schreibt
sie gleichzeitig in einen zeitgestempelten Text-Log sowie einen strukturierten
JSON-Report:

```bash
python -m tests.run_tests
```

Die Dateien werden automatisch angelegt unter:

```text
logs/tests/test_run_<TIMESTAMP>.log
logs/tests/test_run_<TIMESTAMP>.json
```

Der Text-Log enthaelt:

- alle Testnamen mit `ok`, `FAIL` oder `ERROR`;
- die geladene Anzahl je Deliktkategorie des Bronze-Testbestands;
- die Gesamtzahl der geladenen Testdatensaetze;
- die Zusammenfassung mit Status, erfolgreichen Tests, Failures, Errors,
  uebersprungenen Tests und Laufzeit;
- bei Fehlern den vollstaendigen Python-Traceback.

Der JSON-Report enthaelt dieselben Laufkennzahlen maschinenlesbar, dazu die
Bronze-Fixture-Statistik sowie Listen erfolgreicher, fehlgeschlagener und
uebersprungener Tests. Die Kategorieausgabe bezieht sich auf die fuenf
reproduzierbaren Fake-Datensaetze und nicht auf einen Live-Download.

## Nutzung in einem Jupyter Notebook

```python
from pathlib import Path
from detroit_pipeline.extract_detroit import extract_year
from detroit_pipeline.transform_detroit import transform

bronze_path, manifest_path = extract_year(
    2024,
    Path("data/bronze/detroit"),
)

silver_path, quality_path = transform(
    bronze_path,
    Path("data/silver/detroit_crime_2024.parquet"),
)
```

## Empfohlene naechste Produktionsschritte

- den bekannten Schema-Fingerprint in einem Source Contract versionieren;
- bei unbekanntem Fingerprint den Silver-Publish blockieren;
- fuer inkrementelle Laeufe `updated_at` mit einem Overlap-Fenster verwenden;
- Bronze-Snapshots niemals nachtraeglich ueberschreiben;
- Run-Manifeste in eine `ops.pipeline_runs`-Tabelle laden;
- Mapping-Coverage vor jedem Gold-Build pruefen.
