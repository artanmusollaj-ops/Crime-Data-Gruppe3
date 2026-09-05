# Crime-Data-Gruppe3

## Lokale Python-Umgebung

Das Projekt verwendet eine klassische virtuelle Python-Umgebung mit `pip`
und `requirements.txt`.

Einmalig einrichten:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Bei der weiteren Arbeit genügt:

```bash
source .venv/bin/activate
```

Die aktive Umgebung lässt sich mit `deactivate` wieder verlassen.

## Chicago-Ingestion

Das Skript `src/crime-pipeline/ingestion/download_chicago.py` legt jeden
API-Abruf als unveränderlichen Bronze-Lauf unter `data/bronze/` ab. Standard
ist das im PoC festgelegte Jahr 2024.

Erster Aufruf: vollständigen Snapshot laden:

```bash
python src/crime-pipeline/ingestion/download_chicago.py
```

Spätere Aufrufe erkennen das höchste erfolgreiche `updated_on`-Wasserzeichen
aus den Manifesten und erstellen automatisch einen Delta-Lauf mit 14 Tagen
Überlappung. Frühere Läufe werden nie verändert oder gelöscht.

Für einen kleinen Test werden die Daten in ein separates Verzeichnis
geschrieben:

```bash
python src/crime-pipeline/ingestion/download_chicago.py \
  --data-root /tmp/chicago-ingestion-test \
  --max-records 5
```

Wenn `SOCRATA_APP_TOKEN` in `.env` gesetzt ist, verwendet das Skript ihn
automatisch. Der öffentliche API-Zugriff funktioniert auch ohne Token:

```bash
python src/crime-pipeline/ingestion/download_chicago.py --no-token --max-records 5
```

Ein zusätzlicher vollständiger Snapshot wird mit `--full` als neuer Lauf
erstellt. Auch dabei wird kein früherer Lauf überschrieben:

```bash
python src/crime-pipeline/ingestion/download_chicago.py --full
```

### Aufbau der Bronze-Schicht

```text
data/
└── bronze/
    └── city=chicago/
        └── ingest_date=2026-09-04/
            └── run_20260904T040000000000Z/
                ├── part-0001.parquet
                └── manifest.json
```

Die Partitionierung folgt dem Abrufdatum, nicht dem Tatdatum. Jeder Lauf wird
zuerst in einem versteckten `.part`-Verzeichnis erstellt und erst nach
erfolgreichem Abschluss atomar veröffentlicht.

### Originaltypen und festes Schema

Die Werte behalten den JSON-Typ, den die API liefert. Es wird nichts
interpretiert und nichts umgewandelt:

| Feld | Parquet-Typ | Grund |
| --- | --- | --- |
| `arrest`, `domestic` | `bool` | die API sendet echte JSON-Booleans |
| `location` | `struct<latitude, longitude, human_address>` | die API sendet ein verschachteltes Objekt |
| alle übrigen 19 Felder | `string` | die API sendet Strings, auch für Datum, Zahlen und Koordinaten |

Datumswerte bleiben also Text, weil sie als Text ankommen. Das Parsen von
Zeitstempeln, das Casten von `ward` oder `latitude` sowie Deduplizierung, SCD2
und DuckDB gehören in die Staging- beziehungsweise Curated-Schicht.

Die Abfrage nutzt kein `$select`, es werden ganze Datensätze geladen. Die 22
bekannten Felder sind als Spalten fixiert, damit alle Läufe dasselbe Schema
haben und gemeinsam gelesen werden können. Alles, was nicht in dieses Schema
passt, wird unverändert in der Spalte `_extra` als JSON aufbewahrt:

- ein Feld, das die Stadt später ergänzt, zum Beispiel `{"victim_age":"34"}`
- ein Wert, dessen JSON-Typ sich ändert, zum Beispiel `{"arrest":"true"}`;
  die Spalte `arrest` ist für diese Zeile dann leer
- ein `location`-Objekt mit unerwarteten Schlüsseln

Damit geht kein Wert verloren, obwohl die Antworten selbst nicht archiviert
werden, und das Schema bleibt über alle Läufe hinweg stabil.

**Socrata-eigene Spalten.** Die Plattform liefert neun Spalten
`:@computed_region_*` sowie Metadaten wie `:id` und `:updated_at`. Es sind
räumliche Verknüpfungen von Socrata, keine Daten der Stadt, und ihre Werte
ändern sich, wenn Socrata seine Grenzdateien aktualisiert. `ward`, `district`,
`community_area` und `beat` enthalten dieselbe Information bereits aus der
Quelle. Alle Felder mit dem Präfix `:` werden deshalb verworfen und landen auch
nicht in `_extra`.

Die API lässt diese Spalten zwar bereits weg, sobald `$where` oder `$order`
gesetzt ist, was in dieser Abfrage immer der Fall ist. Dieses Verhalten ist
aber nicht dokumentiert, deshalb filtert das Skript zusätzlich selbst. Das
Manifest hält die Regel als `query.dropped_field_prefix` fest.

Das Manifest enthält unter anderem:

- Start- und Endzeit des Laufs
- Zeilenanzahl und API-Abfrage ohne Token
- vorheriges und neues `updated_on`-Wasserzeichen
- Lookback-Zeitraum
- vollständiges Parquet-Schema mit Typen (`schema`)
- Dateigrösse und SHA-256 der Parquet-Datei
- Information, ob ein App Token verwendet wurde
- Vollständigkeitsprüfung (`completeness`)

### Robustheit

Drei Mechanismen schützen die Bronze-Schicht vor unbemerkt unvollständigen
Läufen:

**Wiederholungen.** Die Session wiederholt gedrosselte und vorübergehend
fehlerhafte Antworten (429, 500, 502, 503, 504) bis zu fünfmal mit
exponentiellem Backoff. Ein voller Snapshot braucht rund 26 Anfragen; ohne
Wiederholung würde ein einzelner Fehler den ganzen Lauf verwerfen.

**Vollständigkeitsprüfung.** Vor dem Paginieren fragt das Skript mit
`count(1)` die erwartete Zeilenzahl ab. Werden weniger Zeilen geladen, bricht
der Lauf ab und veröffentlicht nichts, statt einen abgeschnittenen Snapshot als
`complete` zu markieren und das Wasserzeichen über die Lücke hinaus zu setzen.
Ist die Zählung selbst nicht verfügbar, läuft die Ingestion weiter und das
Manifest hält `"completeness": {"verified": false}` fest. Läufe mit
`--max-records` kürzen absichtlich und werden nicht geprüft.

**Aufräumen.** Bricht ein Lauf hart ab, bleibt sein `.part`-Verzeichnis liegen.
Der nächste Start entfernt solche Verzeichnisse, sobald sie älter als 24 Stunden
sind. Veröffentlichte Läufe werden nie angefasst.

Fortschritt und Fehler gehen über das `logging`-Modul nach stderr.

### Daten lesen

Die Datenordner werden von Git ignoriert. Ein einzelner Lauf:

```python
import pandas as pd

run = "data/bronze/city=chicago/ingest_date=2026-09-04/run_20260904T040000000000Z"
df = pd.read_parquet(f"{run}/part-0001.parquet")
```

Mehrere Läufe zusammen: Da neben jeder Parquet-Datei ein `manifest.json` liegt,
werden die Dateien gezielt ausgewählt und mit dem festen Schema gelesen:

```python
from pathlib import Path
import pyarrow.parquet as pq

parts = sorted(Path("data/bronze").glob("**/part-0001.parquet"))
table = pq.read_table(parts)
```

Löschungen werden später durch einen separaten Schlüsselabgleich erkannt und
als eigener unveränderlicher Lauf dokumentiert. Die Auflösung mehrerer
Versionen derselben `id` erfolgt erst oberhalb der Bronze-Schicht.

Weitere Optionen zeigt:

```bash
python src/crime-pipeline/ingestion/download_chicago.py --help
```

## Tests

Die Tests der Ingestion laufen ohne Netzzugriff und ohne App Token:

```bash
python -m pytest
```

Sie decken Argumentprüfung, Token-Ermittlung, Wasserzeichen und Lookback,
API-Abfrage und Paginierung, Wiederholungen und Vollständigkeitsprüfung, das
Aufräumen liegengebliebener `.part`-Verzeichnisse, die unveränderte Ablage der
Antworten in Raw, die Spalte `_extra` für neue API-Felder sowie das atomare
Veröffentlichen beider Schichten inklusive Manifest ab.

Weitere Optionen zeigt:

```bash
python src/crime-pipeline/ingestion/download_chicago.py --help
```
