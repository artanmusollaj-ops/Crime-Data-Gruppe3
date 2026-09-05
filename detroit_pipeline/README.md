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
| `extract_detroit.py` | kompletter Jahresdownload in Bronze |
| `transform_detroit.py` | Bronze-nach-Silver-Transformation |
| `../tests/test_detroit_arcgis.py` | Unit Tests fuer Parser und Hilfsfunktionen |
| `../tests/test_bronze_ingestion.py` | Bronze-Integrationstest mit Kategorie- und Gesamtzahlen |
| `../notebooks/05_detroit_bronze_ingestion.ipynb` | dokumentierter Bronze-Download im Jupyter Notebook |
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
pip install -r detroit_arcgis_pipeline/requirements.txt
```

Ohne `pyarrow` funktionieren Download, CSV, NDJSON und Tests trotzdem.

## Schritt 1: Bronze extrahieren

```bash
python -m detroit_arcgis_pipeline.extract_detroit \
  --year 2024 \
  --output-dir data/bronze/detroit
```

Optional kann die API staerker geschont werden:

```bash
python -m detroit_arcgis_pipeline.extract_detroit \
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
python -m detroit_arcgis_pipeline.transform_detroit \
  data/bronze/detroit/detroit_rms_crime_2024_<RUN_ID>.ndjson \
  --output data/silver/detroit_crime_2024.parquet
```

Zum Debuggen als CSV:

```bash
python -m detroit_arcgis_pipeline.transform_detroit \
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

```bash
python -m unittest discover -s tests -v
```

Der Bronze-Integrationstest arbeitet mit einem kontrollierten Fake-Client. Er
laedt keine Live-Daten, prueft aber denselben Ingestion-Ablauf inklusive
Kategoriezaehlung, Gesamtzahl, NDJSON und Manifest. Dadurch bleibt CI stabil.

## Nutzung in einem Jupyter Notebook

```python
from pathlib import Path
from detroit_arcgis_pipeline.extract_detroit import extract_year
from detroit_arcgis_pipeline.transform_detroit import transform

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
