# Detroit Crime Data Pipeline – Installations- und Betriebsanleitung

## 1. Zweck und aktueller Umfang

Diese Anleitung beschreibt den vollständigen aktuellen Ablauf der Detroit-Pipeline:

1. lokale Python-Umgebung erstellen;
2. Abhängigkeiten und Jupyter-Kernel installieren;
3. Tests ausführen und Testprotokolle prüfen;
4. ArcGIS-Metadaten und erwartete Datensatzanzahl kontrollieren;
5. einen vollständigen Jahresdownload (`FULL`) oder einen inkrementellen Lauf (`DAILY`) starten;
6. Bronze-Dateien und Run-Manifeste validieren;
7. einen einzelnen Bronze-Snapshot in eine Silver-nahe Datei transformieren;
8. Datenqualität, Schlüssel und Data Lineage prüfen.

Die Anleitung gilt ausschließlich für die Detroit-RMS-Crime-Quelle. Die gemeinsame Harmonisierung mit der Chicago-Pipeline, das Zusammenführen mehrerer Detroit-Läufe und die produktive gemeinsame Silver-/Gold-Stufe sind noch nicht implementiert.

## 2. Pipeline-Überblick

```text
Detroit ArcGIS REST API
        │
        ├── Metadaten, Schema-Fingerprint und Count prüfen
        │
        ├── Object-IDs fixieren und Features batchweise laden
        │
        ▼
Bronze
  ├── unveränderte ArcGIS-Attribute und Geometrie als NDJSON
  └── Run-Manifest mit Counts, Filter, Checksumme und Lineage
        │
        ├── Zeit, Koordinaten und Texte normalisieren
        ├── Schlüssel und Quality Flags erzeugen
        └── freigegebene Deliktkategorien mappen
        ▼
Detroit Silver-nahe Ausgabe
  ├── Parquet, CSV oder NDJSON
  └── Quality-Report
        │
        ▼
Zukünftige gemeinsame Silver-Stufe
  ├── mehrere Full-/Daily-Läufe konsolidieren
  ├── Detroit und Chicago auf gemeinsamen Data Contract abbilden
  └── transformierte Datensätze per UNION ALL zusammenführen
```

## 3. Datenquelle

Die Pipeline verwendet den öffentlichen Detroit ArcGIS Feature Layer:

```text
https://services2.arcgis.com/qvkbeam7Wirps6zC/arcgis/rest/services/RMS_Crime_Incidents/FeatureServer/0
```

Die Abfrage erfolgt über ArcGIS REST. Selenium oder ein Browser-Scraper werden für Detroit nicht benötigt.

## 4. Projektstruktur

Die relevanten Dateien und Verzeichnisse sind:

```text
<PROJECT_ROOT>/
├── src/crime/detroit_pipeline/
│   ├── __init__.py
│   ├── detroit_arcgis.py
│   ├── extract_detroit.py
│   ├── transform_detroit.py
│   └── README.md
├── pyproject.toml                # Paketdefinition und Abhaengigkeiten
├── requirements.txt              # installiert das Projekt editierbar (-e .[dev])
├── notebooks/
│   └── 05_detroit_bronze_ingestion.ipynb
├── tests/
│   ├── __init__.py
│   ├── run_tests.py
│   ├── test_bronze_ingestion.py
│   └── test_detroit_arcgis.py
├── data/                         # wird beim ersten Schreiben automatisch erstellt
│   ├── bronze/
│   │   └── detroit/
│   └── silver/
├── logs/                         # wird durch den Test-Runner automatisch erstellt
│   └── tests/
└── docs/
    └── DETROIT_PIPELINE_ANLEITUNG.md
```

Die Ordner `data`, die benötigten Unterordner und `logs/tests` müssen nicht manuell erstellt werden. Die Pipeline verwendet `mkdir(parents=True, exist_ok=True)` vor dem Schreiben.

`__pycache__`-Ordner und `*.pyc`-Dateien werden von Python automatisch erzeugt. Sie enthalten kompilierten Bytecode, gehören nicht zu den fachlichen Daten und sollten über `.gitignore` ausgeschlossen werden.

## 5. Umgebung aufbauen

### 5.1 Voraussetzungen

- Python 3.11 oder 3.12 empfohlen;
- Internetzugriff auf den ArcGIS-Dienst;
- ausreichend freier Speicher für die gewählten Jahre;
- Ausführung der Befehle aus dem Projekt-Root, also dem Ordner, der `src/`, `notebooks` und `tests` enthält.

### 5.2 Virtuelle Umgebung erstellen

Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Windows Eingabeaufforderung:

```bat
py -m venv .venv
.venv\Scripts\activate.bat
```

Nach der Aktivierung sollte die Shell den Präfix `(.venv)` anzeigen.

### 5.3 Abhängigkeiten installieren

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install jupyter ipykernel
```

Die eigentliche Bronze-Ingestion nutzt nur die Python-Standardbibliothek. `pyarrow` wird für die empfohlene Silver-Ausgabe als Parquet benötigt. `jupyter` und `ipykernel` sind nur für die interaktive Notebook-Ausführung erforderlich.

### 5.4 Jupyter-Kernel registrieren

```bash
python -m ipykernel install --user \
  --name crime-data \
  --display-name "Python (Crime Data)"
```

Im Notebook anschließend den Kernel **Python (Crime Data)** auswählen. Dadurch wird verhindert, dass Jupyter versehentlich eine andere Python-Installation verwendet.

### 5.5 Installation kontrollieren

```bash
python --version
python -c "import pyarrow; print(pyarrow.__version__)"
python -c "import detroit_pipeline; print('detroit_pipeline importiert')"
```

Wenn nur Bronze geladen und noch kein Parquet geschrieben werden soll, ist ein fehlender `pyarrow`-Import nicht kritisch. Für Parquet muss die Installation erfolgreich sein.

## 6. Tests vor dem ersten Download

### 6.1 Empfohlener Test-Runner mit Protokollen

Aus dem Projekt-Root:

```bash
python -m tests.run_tests
```

Der Runner führt die gesamte Suite aus — derzeit 239 Tests, davon zwölf für Detroit — und erzeugt für jeden Testlauf neue Dateien:

```text
logs/tests/test_run_<TIMESTAMP>.log
logs/tests/test_run_<TIMESTAMP>.json
```

Die Dateien werden wegen des Zeitstempels nicht überschrieben. Der Prozess liefert Exit-Code `0` bei Erfolg und `1` bei fehlgeschlagenen Tests. Ein erfolgreicher Lauf enthält:

```text
239 passed

Test Run Summary:
  Status       : SUCCESS
  Ausgefuehrt  : 239
```

Alternativ nur die Standard-Testausgabe, ohne Protokolldateien:

```bash
python -m pytest
```

Nur die Detroit-Tests:

```bash
python -m pytest tests/test_detroit_arcgis.py tests/test_bronze_ingestion.py
```

### 6.2 Aktuell vorhandene Unit Tests

`tests/test_detroit_arcgis.py` prüft:

1. Mapping von `STOLEN VEHICLE` auf `VEHICLE_THEFT`;
2. Beibehaltung, aber Analyseausschluss von `UNFOUNDED`;
3. Kennzeichnung unbekannter Kategorien als `UNREVIEWED`;
4. halb-offenen Full-Load-Zeitfilter;
5. halb-offenen Daily-Load-Zeitfilter;
6. Allowlist der zulässigen Datumsfelder;
7. Aufteilung von Object-IDs in API-konforme Batches.
8. Quality Flag `MISSING_SOURCE_UPDATED_AT` bei fehlendem `updated_at`;
9. 1:n-Beziehung zwischen Event und Offense sowie Deduplikation zweier
   Source-Kategorien auf derselben Canonical Category.

### 6.3 Aktuell vorhandene Bronze-Integrationstests

`tests/test_bronze_ingestion.py` prüft:

1. Bronze-Datei und Manifest;
2. Anzahl geladener Testdatensätze je Deliktkategorie;
3. Übereinstimmung von Kategoriesumme und Gesamtzahl;
4. Daily-Modus und `updated_at`-Filter;
5. Daily-Zeitfenster und Dateiname;
6. wichtige Manifestfelder und Download-Count.
7. Full-Load-Vertrag mit `incident_occurred_at` als Auswahlzeitachse;
8. maschinenlesbare Auswahlsemantik und die explizite Aussage, dass die
   Extraktion keine Source-Löschungen erkennt.

Die ausgegebene Teststatistik basiert auf fünf kontrollierten Fake-Datensätzen:

```text
Geladene Datensaetze pro Deliktkategorie:
  ASSAULT     :        2
  LARCENY     :        1
  ROBBERY     :        1
  __MISSING__ :        1
  INSGESAMT   :        5
```

Diese fünf Datensätze sind kein Live-Download und sagen nichts über die aktuelle Anzahl in Detroit aus. Der Fake-Client macht Tests reproduzierbar und unabhängig von Netzwerk und ArcGIS-Verfügbarkeit.

### 6.4 Noch nicht abgedeckte Tests

Folgende Prüfungen sollten mit der gemeinsamen Silver-Stufe ergänzt werden:

- Upsert und Deduplikation über mehrere Bronze-Läufe;
- Auswahl der neuesten Version anhand `source_updated_at_utc`;
- Schema-Contract zwischen Detroit und Chicago;
- `UNION ALL` und Reconciliation beider Städte;
- Mapping-Coverage-Gate vor Gold;
- Erkennung gelöschter Quelldatensätze durch periodischen Full-Abgleich;
- kontrollierter Live-Smoke-Test gegen ArcGIS;
- Retry-Tests für HTTP 429 und temporäre Serverfehler;
- Validierung eines freigegebenen Schema-Fingerprints.

## 7. Notebook starten

```bash
jupyter notebook
```

Danach öffnen:

```text
notebooks/05_detroit_bronze_ingestion.ipynb
```

Das Präfix `05` ist nur die Reihenfolge innerhalb der Notebook-Sammlung. Das Notebook kann technisch umbenannt werden, solange keine externe Dokumentation oder Automatisierung auf den alten Namen verweist.

## 8. Notebook Schritt für Schritt

### Schritt 1 – Projektpfad und Imports

Die erste Codezelle sucht den Projekt-Root. Das Notebook kann aus dem Projekt-Root oder aus dem Ordner `notebooks` gestartet werden. Falls `src/crime/detroit_pipeline` nicht gefunden wird, bricht es mit einer verständlichen Fehlermeldung ab.

Es werden unter anderem folgende Funktionen importiert:

- `ArcGISClient`: Zugriff auf Layer-Metadaten, Counts, IDs und Features;
- `build_year_where`: Full-Load-Filter nach Tatzeitpunkt;
- `build_updated_where`: Daily-Filter nach Änderungszeitpunkt;
- `extract_year`: kompletter Jahresdownload;
- `extract_updated_window`: inkrementeller Download;
- `format_load_summary`: Kategorie- und Gesamtausgabe.

### Schritt 2 – Lauf konfigurieren

Beispiel für einen Full Load:

```python
LOAD_MODE = "FULL"
RUN_DOWNLOAD = False
YEARS = [2023, 2024, 2025]

DAILY_LOOKBACK_DAYS = 14
DAILY_REFERENCE_DATE = None

OUTPUT_DIR = PROJECT_ROOT / "data" / "bronze" / "detroit"
BATCH_SIZE = 1000
PAUSE_SECONDS = 0.05
```

Beispiel für den täglichen Betrieb:

```python
LOAD_MODE = "DAILY"
RUN_DOWNLOAD = False
YEARS = [2024]  # wird im DAILY-Modus ignoriert

DAILY_LOOKBACK_DAYS = 14
DAILY_REFERENCE_DATE = None
```

Parameter:

| Parameter | Bedeutung |
|---|---|
| `LOAD_MODE` | `FULL` oder `DAILY` |
| `RUN_DOWNLOAD` | Sicherheitsschalter; bei `False` wird nichts heruntergeladen |
| `YEARS` | Liste der Jahre für `FULL`, beispielsweise `[2023, 2024, 2025]` |
| `DAILY_LOOKBACK_DAYS` | Länge des Update-Fensters; muss größer als null sein |
| `DAILY_REFERENCE_DATE` | Optionales fachliches Laufdatum für Backfills; `None` verwendet das aktuelle Datum in Detroit |
| `OUTPUT_DIR` | Basisverzeichnis der Bronze-Daten |
| `BATCH_SIZE` | gewünschte Zahl der Features pro API-Batch |
| `PAUSE_SECONDS` | Pause zwischen API-Batches |

Die effektive Batch-Größe wird automatisch auf das von ArcGIS veröffentlichte `maxRecordCount` begrenzt. In der aktuell beobachteten Quelle beträgt dieses Limit 2.000.

`RUN_DOWNLOAD` sollte zunächst `False` bleiben. Dadurch können Metadaten und erwartete Counts geprüft werden, ohne bereits den vollständigen Datensatz zu übertragen.

### Schritt 3 – Metadaten und erwartete Zeilenzahl prüfen

Diese Zelle lädt nur:

- Layer-Metadaten;
- Object-ID-Feld;
- maximales API-Record-Limit;
- Anzahl und Namen der Felder;
- Schema-Fingerprint;
- serverseitigen Count für jedes gewünschte Zeitfenster.

Ein Count-Resultat wie das folgende ist noch kein Download:

```python
{
    "year": 2024,
    "source_count": 88695,
    "object_id_field": "ESRI_OID",
    "max_record_count": 2000,
    "field_count": 28,
    "schema_fingerprint": "...",
}
```

Dass diese Prüfung nur ungefähr eine Sekunde dauert, ist plausibel: ArcGIS berechnet den Count serverseitig und liefert nur Metadaten beziehungsweise eine Zahl zurück.

Vor dem Download prüfen:

- Ist `LOAD_MODE` korrekt?
- Sind die Jahre beziehungsweise das Daily-Fenster korrekt?
- Ist `source_count` plausibel und größer als null?
- Ist das Object-ID-Feld weiterhin `ESRI_OID`?
- Hat sich der Schema-Fingerprint unerwartet geändert?
- Ist das API-Limit plausibel?

Ein geänderter Schema-Fingerprint bedeutet nicht automatisch einen Fehler, muss aber vor der Transformation untersucht werden. Detroit könnte Felder, Typen oder Aliase geändert haben.

### Schritt 4 – Download starten

Erst nach erfolgreicher Plausibilitätsprüfung:

```python
RUN_DOWNLOAD = True
```

Danach die Konfigurationszelle erneut ausführen und anschließend Schritt 3 und Schritt 4 ausführen.

Der Full-Modus führt für jedes Element in `YEARS` einen separaten Download aus. Der Daily-Modus erzeugt genau einen Lauf für das berechnete Update-Fenster.

Während des Downloads:

1. wird der serverseitige Count gelesen;
2. wird die vollständige passende `ESRI_OID`-Liste fixiert und sortiert;
3. wird geprüft, ob Count und ID-Anzahl übereinstimmen;
4. werden genau diese IDs in Batches geladen;
5. werden die Features direkt in eine temporäre NDJSON-Datei gestreamt;
6. wird die Zahl empfangener Features gegen die ID-Anzahl geprüft;
7. wird die temporäre Datei erst nach erfolgreicher Validierung veröffentlicht;
8. werden ein zweiter Source-Count und das Manifest geschrieben.

Scheitert der Download vor der Veröffentlichung, wird die temporäre `*.tmp`-Datei entfernt. Ein unvollständiger Snapshot soll nicht als erfolgreiches Bronze-Artefakt erscheinen.

### Schritt 5 – Kategorie- und Gesamtzahlen prüfen

Die letzte Notebook-Zelle liest jedes Manifest und zeigt:

- Modus und Zeitraum;
- Pfad der Bronze-Datei;
- Zahl der Datensätze je `offense_category`;
- `__MISSING__` für fehlende Kategorien;
- Gesamtzahl der geladenen Datensätze.

Die Summe der Kategorien muss exakt `downloaded_count` entsprechen. Andernfalls löst `format_load_summary` einen Data-Quality-Fehler aus.

## 9. Full Load

### 9.1 Fachlicher Filter

Der Full Load filtert anhand von `incident_occurred_at`, also dem Tat- beziehungsweise Ereigniszeitpunkt:

```sql
incident_occurred_at >= TIMESTAMP '2024-01-01 00:00:00'
AND incident_occurred_at < TIMESTAMP '2025-01-01 00:00:00'
```

Das Intervall ist halb-offen. Dadurch gehört ein Datensatz am 1. Januar 2025 nicht gleichzeitig zum Jahr 2024 und 2025.

Detroit RMS ist in der Pipeline ab 2016 zugelassen. Die Quelle ist laut aktueller Projektdokumentation erst ab Dezember 2016 verfügbar; 2016 ist deshalb kein vollständiges Kalenderjahr.

Die Pipeline validiert diesen Vertrag vor jedem Lauf. `FULL` darf ausschließlich
`incident_occurred_at` verwenden; eine versehentliche Kombination mit
`updated_at` bricht ab. Im Manifest wird dies als
`selection_basis = INCIDENT_OCCURRENCE_TIME` protokolliert.

### 9.2 Welche Datensätze werden geladen?

Geladen werden alle zum Abrufzeitpunkt in der Quelle vorhandenen Zeilen, deren `incident_occurred_at` im gewählten Kalenderjahr liegt, darunter auch:

- alle Deliktkategorien, nicht nur die fünf später gemappten Kategorien;
- Datensätze mit fehlender `offense_category`;
- Fälle mit `case_status = UNFOUNDED`;
- Datensätze, die erst später korrigiert oder aktualisiert wurden, sofern ihr Tatzeitpunkt im gewählten Jahr liegt;
- mehrere Offense-Zeilen, die zum selben Polizeifall gehören.

Bronze führt bewusst keine fachlichen Ausschlüsse durch.

### 9.3 Welche Datensätze werden nicht geladen?

Nicht geladen werden:

- Datensätze mit Tatzeitpunkt außerhalb des gewählten Kalenderjahres;
- Datensätze ohne vergleichbaren `incident_occurred_at`-Wert, weil der Zeitfilter für `NULL` nicht wahr wird;
- Datensätze, die vor der fixierten ID-Abfrage nicht in der Quelle vorhanden waren;
- Datensätze, die erst nach der ID-Fixierung neu angelegt werden.

Neue Datensätze während eines laufenden Full Loads werden absichtlich nicht nachträglich in den fixierten Snapshot aufgenommen. Ein unterschiedlicher `source_count_after` wird im Manifest mit `source_changed_during_run = true` dokumentiert.

### 9.4 Mehrere Jahre laden

Im Notebook:

```python
LOAD_MODE = "FULL"
YEARS = [2023, 2024, 2025]
RUN_DOWNLOAD = True
```

Für jedes Jahr entstehen ein eigener Ordner und eine eigene Run-ID:

```text
data/bronze/detroit/full/
├── year=2023/
├── year=2024/
└── year=2025/
```

Die CLI verarbeitet pro Aufruf nur ein Jahr:

```bash
python -m detroit_pipeline.extract_detroit \
  --year 2024 \
  --batch-size 1000 \
  --pause-seconds 0.05 \
  --output-dir data/bronze/detroit/full/year=2024
```

## 10. Incremental/Daily Load

### 10.1 Fachlicher Filter

Der Daily Load filtert nicht nach Tatjahr, sondern nach `updated_at`:

```sql
updated_at >= TIMESTAMP '<WINDOW_START> 00:00:00'
AND updated_at < TIMESTAMP '<WINDOW_END_EXCLUSIVE> 00:00:00'
```

Bei einem Referenzdatum 5. September 2026 und 14 Tagen Lookback gilt:

```text
window_start         = 2026-08-23 00:00:00
window_end_exclusive = 2026-09-06 00:00:00
```

Damit umfasst das Fenster den Lauftag und die 13 vorherigen Kalendertage in der Zeitzone `America/Detroit`.

### 10.2 Welche Datensätze werden geladen?

Geladen werden alle Zeilen mit `updated_at` innerhalb des Fensters:

- neu angelegte Crime Records;
- Änderungen an kürzlich angelegten Records;
- nachträgliche Korrekturen an älteren Delikten;
- Status-, Beschreibungs-, Kategorie-, Zeit- oder Ortsänderungen, sofern die Quelle dabei `updated_at` aktualisiert;
- alle Kategorien und Statuswerte, einschließlich `UNFOUNDED` und später `UNREVIEWED` gemappter Kategorien.

Ein Delikt aus dem Jahr 2020 kann deshalb in einem Daily Load von 2026 erscheinen, wenn es 2026 innerhalb des Fensters geändert wurde. Das ist beabsichtigt.

Die Selektion erfolgt auf Offense-Zeilen. Ein neuer Report erzeugt neue Zeilen;
eine zusätzliche `incident_entry_id` unter einer schon bekannten
`report_number` ist ein neues Delikt desselben Events. Bei einer Event-weiten
Neupublikation kann Detroit für mehrere vorhandene Offense-Zeilen dasselbe neue
`updated_at` setzen. Der Incremental Load lädt dann alle betroffenen Zeilen.

Die Pipeline validiert auch diesen Vertrag: `INCREMENTAL` darf ausschließlich
`updated_at` verwenden. Das Manifest führt
`selection_basis = SOURCE_LAST_UPDATED_TIME`,
`record_granularity = INCIDENT_OFFENSE`, `window_is_half_open = true` und
`captures_source_deletions = false`.

### 10.3 Welche Datensätze werden nicht geladen?

Nicht geladen werden:

- unveränderte Records mit `updated_at` vor `window_start`;
- Änderungen mit `updated_at >= window_end_exclusive`;
- Records ohne `updated_at`;
- Änderungen außerhalb des 14-Tage-Fensters;
- physisch aus der Quelle gelöschte Records, weil ein gelöschter Record nicht mehr über die API zurückgegeben werden kann;
- Änderungen, bei denen das Quellsystem `updated_at` nicht korrekt aktualisiert.

Wegen der letzten beiden Punkte sollte periodisch ein Full Load beziehungsweise eine Source-Reconciliation durchgeführt werden.

Die Live-Prüfung vom 5. September 2026 ergab für den Gesamtbestand 823.951 von
823.951 Records mit vorhandenem `incident_occurred_at`. Im 2024-Bestand waren
hingegen 5 von 88.695 Offense-Zeilen ohne `updated_at`. Diese Werte sind eine
zeitabhängige Beobachtung und kein dauerhaft garantierter Source Contract.
Records ohne `updated_at` können über einen Full Load erscheinen, aber nicht
durch den normalen Incremental-Filter selektiert werden.

### 10.4 Technisches Update oder fachliche Änderung?

`updated_at` ist das Extraktionswasserzeichen, aber kein Beweis für eine
inhaltliche Änderung. Bei einer untersuchten Extremfall-Stichprobe besaßen alle
Offense-Zeilen eines Events identische, sehr späte `updated_at`-Werte, während
`case_status_updated_at` und `updated_in_ibr_at` meist deutlich früher lagen.
Das ist mit einer technischen Neuverarbeitung oder Neupublikation vereinbar.

Die zukünftige Silver-Konsolidierung soll daher einen Hash der fachlichen
Attribute mit dem bisherigen Stand vergleichen:

```text
offense_key unbekannt                       → INSERT
offense_key bekannt, business_hash geändert → BUSINESS_UPDATE
offense_key bekannt, business_hash gleich   → TECHNICAL_REFRESH / UNCHANGED
neue offense_key bei bekannter report_number → NEW_OFFENSE_FOR_EVENT
im Full-Abgleich verschwundene offense_key   → POSSIBLE_DELETE
```

Technische Felder wie `ESRI_OID`, `pipeline_run_id`, `ingested_at` und das
Wasserzeichen selbst gehören nicht in den `business_hash`.

### 10.5 Warum 14 Tage Überlappung?

Ein täglicher Lauf lädt bewusst erneut einen Teil der bereits zuvor geladenen Daten. Das reduziert das Risiko, verspätete Quelländerungen oder einen ausgefallenen einzelnen Tageslauf zu verlieren.

Die Überlappung erzeugt erwartete Wiederholungen zwischen verschiedenen Bronze-Dateien. Bronze bewahrt diese Snapshots unverändert auf. Die zukünftige Silver-Stufe muss sie idempotent zusammenführen.

### 10.6 Backfill eines Daily-Fensters

Für einen reproduzierbaren historischen Lauf:

```python
LOAD_MODE = "DAILY"
DAILY_LOOKBACK_DAYS = 14
DAILY_REFERENCE_DATE = date(2026, 9, 5)
RUN_DOWNLOAD = True
```

`DAILY_REFERENCE_DATE = None` verwendet das aktuelle Datum in Detroit. Ein Backfill überschreibt bestehende Daten nicht, weil jeder Extraktionslauf eine neue Run-ID erhält.

## 11. Bronze-Artefakte und Verzeichnisstruktur

### 11.1 Full Load

```text
data/bronze/detroit/full/year=2024/
├── detroit_rms_crime_2024_<RUN_ID>.ndjson
└── detroit_rms_crime_2024_<RUN_ID>.manifest.json
```

### 11.2 Daily Load

```text
data/bronze/detroit/incremental/run_date=2026-09-05/
├── detroit_rms_crime_incremental_2026-08-23_2026-09-06_<RUN_ID>.ndjson
└── detroit_rms_crime_incremental_2026-08-23_2026-09-06_<RUN_ID>.manifest.json
```

### 11.3 NDJSON

Die NDJSON-Datei enthält pro Zeile genau ein JSON-Objekt:

```json
{
  "attributes": {"...": "unveränderte ArcGIS-Attribute"},
  "geometry": {"x": -83.0, "y": 42.3},
  "_meta": {
    "source_system": "detroit_rms_crime",
    "dataset_id": "RMS_Crime_Incidents",
    "layer_url": "...",
    "pipeline_run_id": "...",
    "ingested_at": "...",
    "schema_fingerprint": "..."
  }
}
```

`attributes` und `geometry` bleiben source-nah. `_meta` ergänzt ausschließlich technische Provenance.

### 11.4 Manifest

Das Manifest dokumentiert unter anderem:

- `pipeline_run_id`;
- `status`;
- Quellsystem, Dataset und Layer-URL;
- `extraction_mode`;
- verwendetes Datumsfeld und WHERE-Filter;
- Start und exklusives Ende des Fensters;
- Schema-Fingerprint;
- Object-ID-Feld;
- Count vor und nach dem Download;
- Anzahl fixierter Object-IDs;
- Anzahl tatsächlich geladener Datensätze;
- Kategoriehäufigkeiten;
- Batch-Größe;
- Start, Ende und Dauer des Laufs;
- Pfad der Bronze-Datei;
- SHA-256-Prüfsumme der Bronze-Datei.

NDJSON und Manifest bilden gemeinsam einen nachvollziehbaren Bronze-Snapshot. Beide Dateien sollten zusammen aufbewahrt werden.

## 12. Data Lineage

Jeder Extraktionslauf erhält eine neue UUID als `pipeline_run_id`. Zusätzlich wird der Startzeitpunkt als `ingested_at` gespeichert.

```text
source_record_id / offense_key → welcher Crime-Quelldatensatz?
pipeline_run_id                → durch welchen Extraktionslauf geladen?
ingested_at                    → wann wurde er geladen?
schema_fingerprint             → mit welchem Quellschema?
bronze_sha256                  → welche exakte Bronze-Datei?
```

Die Run-ID steht:

- im Bronze-Dateinamen;
- in jeder Bronze-Zeile unter `_meta`;
- im Manifest;
- nach der aktuellen Detroit-Transformation in jeder Silver-nahen Zeile.

Beim späteren gemeinsamen Silver-/Gold-Aufbau sollten zusätzlich `silver_run_id`, `gold_run_id`, Transformationszeitpunkt, Schema-Version, Mapping-Version und verwendete Bronze-Run-IDs protokolliert werden.

## 13. Detroit-Transformation in die Silver-nahe Stufe

### 13.1 Parquet-Ausgabe

```bash
python -m detroit_pipeline.transform_detroit \
  data/bronze/detroit/full/year=2024/detroit_rms_crime_2024_<RUN_ID>.ndjson \
  --output data/silver/detroit_crime_2024.parquet
```

### 13.2 CSV zum Debuggen

```bash
python -m detroit_pipeline.transform_detroit \
  data/bronze/detroit/full/year=2024/detroit_rms_crime_2024_<RUN_ID>.ndjson \
  --output data/silver/detroit_crime_2024.csv
```

Unterstützte Endungen:

- `.parquet` – empfohlen für Analytics, benötigt `pyarrow`;
- `.csv` – gut für manuelle Kontrolle;
- `.jsonl` oder `.ndjson` – typnahe zeilenbasierte Ausgabe.

Neben der Ausgabedatei entsteht:

```text
<SILVER_FILE>.quality.json
```

Der Report enthält Silver-Zeilenzahl, unterschiedliche Events und Offenses, analyseberechtigte Zeilen, Mapping-Status, Quality-Flag-Häufigkeiten, Input- und Outputpfad sowie Transformationszeitpunkt.

Wichtig: `transform_detroit.py` verarbeitet aktuell jeweils genau eine Bronze-Datei. Es konsolidiert nicht automatisch mehrere Full- oder Daily-Läufe und ist noch nicht die gemeinsame Chicago–Detroit-Silver-Pipeline.

## 14. Transformations- und Analyseregeln

### 14.1 Schlüssel

Detroit liefert eine Zeile pro Offense Charge. Mehrere Deliktzeilen können zum selben Polizeifall gehören.

```text
offense_key       = SHA256(source_system | source_record_id)
event_key         = SHA256(source_system | source_event_id)
analysis_unit_key = SHA256(source_system | source_event_id | canonical_category)
```

- `source_record_id`: primär `incident_entry_id`, Fallback `ESRI_OID`;
- `source_event_id`: primär `report_number`, Fallback `case_id`;
- `offense_key`: identifiziert eine physische Detroit-Offense-Zeile;
- `event_key`: identifiziert den Polizeifall;
- `analysis_unit_key`: identifiziert den Fall innerhalb einer Canonical Category.

Für spätere Gold-Aggregationen ist vorgesehen:

```sql
COUNT(DISTINCT analysis_unit_key)
```

Ein Fall mit mehreren Charges derselben Canonical Category zählt damit einmal. Derselbe Fall darf in mehreren unterschiedlichen Canonical Categories jeweils einmal vorkommen.

### 14.2 Aktuelles Deliktmapping

| Detroit `offense_category` | Canonical Category |
|---|---|
| `ROBBERY` | `ROBBERY` |
| `BURGLARY` | `BURGLARY` |
| `LARCENY` | `THEFT` |
| `STOLEN VEHICLE` | `VEHICLE_THEFT` |
| `ASSAULT` | `ASSAULT` |
| `AGGRAVATED ASSAULT` | `ASSAULT` |

Alle anderen Werte erhalten:

```text
mapping_status = UNREVIEWED
quality_flags  enthält UNREVIEWED_OFFENSE_CATEGORY
analysis_eligible = false
```

Unbekannte Kategorien werden nicht automatisch zu `OTHER`. Vor der gemeinsamen Silver-/Gold-Stufe muss die Kategorieinventur eines vollständigen Detroit-Bestands geprüft und das Mapping gemeinsam versioniert werden.

### 14.3 `UNFOUNDED`

Ein Record mit `case_status = UNFOUNDED`:

- bleibt in Bronze erhalten;
- bleibt in der Silver-nahen Ausgabe nachvollziehbar;
- erhält `analysis_eligible = false`;
- erhält keinen `analysis_unit_key`.

Damit werden Rohdaten nicht gelöscht, aber unbegründete Fälle gelangen nicht in vergleichende Aggregate.

### 14.4 Weitere Quality Flags

Die Transformation dokumentiert unter anderem:

- `MISSING_SOURCE_RECORD_ID`;
- `MISSING_SOURCE_EVENT_ID`;
- `MISSING_OCCURRED_AT`;
- `MISSING_SOURCE_UPDATED_AT`;
- `PLACEHOLDER_COORDINATES` bei `(0, 0)`;
- `INVALID_LATITUDE`;
- `INVALID_LONGITUDE`;
- `UNREVIEWED_OFFENSE_CATEGORY`.

Problematische Records werden grundsätzlich behalten. `analysis_eligible` steuert, ob sie später in fachliche Aggregate eingehen dürfen.

`MISSING_SOURCE_UPDATED_AT` schließt einen aus einem Full Load stammenden Record
nicht automatisch aus der fachlichen Analyse aus. Es kennzeichnet die operative
Einschränkung, dass dieser Record durch einen künftigen `updated_at`-Filter nicht
selektiert werden kann, solange die Quelle keinen Wert setzt.

## 15. Duplikate und wiederholte Läufe

### 15.1 Was bereits geprüft wird

- ArcGIS darf in der ID-Antwort keine doppelte `ESRI_OID` liefern;
- Source-Count und Zahl der fixierten IDs müssen übereinstimmen;
- jeder Batch muss genauso viele Features wie angefragte IDs liefern;
- Download-Count und Zahl der fixierten IDs müssen übereinstimmen;
- innerhalb einer einzelnen transformierten Bronze-Datei darf ein `offense_key` nicht doppelt vorkommen.

### 15.2 Was noch nicht umgesetzt ist

Wird dasselbe Jahr mehrfach geladen, entstehen absichtlich mehrere unveränderliche Bronze-Snapshots mit unterschiedlichen `pipeline_run_id`-Werten. Der aktuelle Transformer verhindert keine Wiederholungen zwischen unterschiedlichen Dateien.

Die zukünftige Silver-Konsolidierung muss:

1. Full- und Daily-Dateien gemeinsam lesen;
2. nach `offense_key` gruppieren;
3. bei mehreren Versionen den Datensatz mit dem neuesten `source_updated_at_utc` auswählen;
4. bei Gleichstand eine deterministische Tie-Break-Regel verwenden;
5. die gewählte Bronze-`pipeline_run_id` erhalten;
6. Inserts und Updates protokollieren;
7. Löschungen über periodische Full-Reconciliation behandeln.

Bis diese Logik implementiert ist, dürfen nicht mehrere Full- und Daily-Dateien ungeprüft per `UNION ALL` für Statistiken gezählt werden.

## 16. Monitoring und betriebliche Kontrollen

Nach jedem Lauf sollten mindestens folgende Werte kontrolliert werden:

| Kontrolle | Erwartung |
|---|---|
| Run-Status | `SUCCESS` |
| `source_count_before` vs. `snapshot_object_id_count` | exakt gleich |
| `snapshot_object_id_count` vs. `downloaded_count` | exakt gleich |
| Summe `offense_category_counts` vs. `downloaded_count` | exakt gleich |
| `source_changed_during_run` | beobachten und dokumentieren |
| Schema-Fingerprint | gegen freigegebene Version prüfen |
| `__MISSING__` | Trend und unerwartete Sprünge überwachen |
| `UNREVIEWED` im Quality-Report | vor Gold fachlich prüfen |
| Bronze-SHA-256 | für Reproduzierbarkeit aufbewahren |
| Laufzeit und Retry-Warnungen | auf API- oder Netzwerkprobleme prüfen |

Empfohlene Warnungen für einen späteren produktiven Betrieb:

- Count fällt oder steigt ungewöhnlich stark;
- neuer Schema-Fingerprint;
- neue Deliktkategorie;
- ungewöhnlich viele fehlende IDs, Zeitwerte oder Koordinaten;
- Testlauf fehlgeschlagen;
- Daily-Lauf wurde an einem geplanten Tag nicht ausgeführt;
- `source_changed_during_run = true` tritt wiederholt auf.

## 17. Fehlerbehandlung und typische Probleme

### `Projekt-Root mit detroit_pipeline nicht gefunden`

Das Notebook wurde aus einem unerwarteten Verzeichnis gestartet oder der Paketordner wurde verschoben. Prüfen, ob `detroit_pipeline` direkt im Projekt-Root liegt.

### `LOAD_MODE muss "FULL" oder "DAILY" sein`

Nur diese beiden Werte sind zulässig. Groß-/Kleinschreibung wird normalisiert, Tippfehler jedoch nicht.

### `DAILY_LOOKBACK_DAYS muss größer als 0 sein`

Einen positiven Integer verwenden, normalerweise `14`.

### Schema-Feld fehlt

Fehlt `incident_occurred_at` oder `updated_at`, bricht die Ingestion ab. Vor einer Anpassung prüfen, ob Detroit das Schema geändert hat.

### Source-Count stimmt nicht mit ID-Count überein

Der Snapshot wird nicht veröffentlicht. Den Lauf später erneut starten und bei Wiederholung ArcGIS-Metadaten beziehungsweise Filter untersuchen.

### Batch liefert weniger Features als IDs

Der Lauf bricht ab. Mögliche Ursachen sind gleichzeitige Löschungen, API-Probleme oder ein inkonsistenter Quellzustand.

### HTTP 429 oder temporärer Serverfehler

Der Client wiederholt HTTP 429, 500, 502, 503 und 504 sowie temporäre Netzwerk-/Timeoutfehler mit exponentiellem Backoff und Jitter. Bei dauerhaften Fehlern Lauf abbrechen lassen und später erneut starten; `PAUSE_SECONDS` oder kleinere Batches können die Quelle entlasten.

### Parquet-Ausgabe meldet fehlendes `pyarrow`

```bash
python -m pip install -r requirements.txt
```

### Notebook verwendet das falsche Python

Kernel **Python (Crime Data)** auswählen und gegebenenfalls alle Zellen neu starten.

### Download wurde nicht gestartet

`RUN_DOWNLOAD` steht noch auf `False`. Das ist der vorgesehene sichere Ausgangszustand. Nach der Count-Prüfung auf `True` setzen und die relevanten Zellen erneut ausführen.

## 18. Empfohlener Betriebsablauf

### Initialer Aufbau

1. virtuelle Umgebung erstellen und aktivieren;
2. Abhängigkeiten installieren;
3. Jupyter-Kernel registrieren;
4. `python -m tests.run_tests` erfolgreich ausführen;
5. Notebook mit `RUN_DOWNLOAD = False` starten;
6. Metadaten, Schema-Fingerprint und Counts prüfen;
7. gewünschte Full-Jahre konfigurieren;
8. `RUN_DOWNLOAD = True` setzen und Full Load ausführen;
9. Manifeste, Kategoriecounts und Dateien prüfen;
10. ausgewählten Snapshot testweise transformieren und Quality-Report prüfen.

### Täglicher Betrieb

1. Tests beziehungsweise mindestens einen Pipeline-Smoke-Test ausführen;
2. `LOAD_MODE = "DAILY"` und `DAILY_LOOKBACK_DAYS = 14` setzen;
3. mit `RUN_DOWNLOAD = False` Fenster und Count prüfen;
4. `RUN_DOWNLOAD = True` setzen;
5. Daily Load ausführen;
6. Manifest, Kategoriecounts, Schema-Fingerprint und Laufstatus prüfen;
7. Bronze-Artefakte unverändert aufbewahren;
8. nach Fertigstellung der Silver-Konsolidierung den Daily-Snapshot idempotent upserten.

### Periodischer Abgleich

Zusätzlich zum Daily-Betrieb sollte regelmäßig ein Full Load durchgeführt werden. Er dient der Erkennung von:

- Quelllöschungen;
- Änderungen außerhalb des Lookback-Fensters;
- fehlerhaft gepflegten `updated_at`-Werten;
- langfristigem Schema- oder Kategorien-Drift.

## 19. Übergabe an die gemeinsame Chicago–Detroit-Silver-Stufe

Vor der Integration sollten beide Verantwortlichen einen gemeinsamen Silver Data Contract festlegen:

- gemeinsame Spaltennamen und Datentypen;
- Definition von `source_record_id`, `source_event_id` und physischem Record-Key;
- Zeilengranularität;
- gemeinsame Zeitzonen- und Zeitregeln;
- versioniertes Deliktmapping;
- Null- und Mapping-Status;
- Upsert- und Deduplikationsregeln;
- Data-Lineage-Felder;
- Schema-, Mapping- und Reconciliation-Tests.

Detroit und Chicago werden zunächst separat transformiert. Erst danach werden vertragskonforme Silver-Zeilen per `UNION ALL` zusammengeführt. Ein direkter Join von Detroit-Crime-Zeilen mit Chicago-Crime-Zeilen ist fachlich nicht vorgesehen.

## 20. Checkliste vor einer Analyse

- [ ] Tests sind erfolgreich und Testlogs wurden geprüft.
- [ ] Bronze-Manifest besitzt `status = SUCCESS`.
- [ ] Count, ID-Anzahl, Downloadzahl und Kategoriesumme stimmen überein.
- [ ] Schema-Fingerprint wurde geprüft.
- [ ] Bronze-Datei und Manifest gehören zur selben Run-ID.
- [ ] SHA-256-Prüfsumme ist im Manifest vorhanden.
- [ ] Mapping-Coverage und `UNREVIEWED` wurden geprüft.
- [ ] `UNFOUNDED` ist nicht analyseberechtigt.
- [ ] Mehrere Läufe wurden vor dem Zählen dedupliziert.
- [ ] Gold verwendet `COUNT(DISTINCT analysis_unit_key)`.
- [ ] Die verwendeten Bronze-, Silver- und späteren Gold-Run-IDs sind dokumentiert.
- [ ] Detroit- und Chicago-Daten erfüllen denselben Silver Data Contract.
