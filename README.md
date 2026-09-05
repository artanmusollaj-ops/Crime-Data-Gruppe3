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
API-Abruf als unveränderlichen Lauf in zwei Schichten ab. Standard ist das im
PoC festgelegte Jahr 2024.

| Schicht | Verzeichnis | Inhalt |
| --- | --- | --- |
| Raw | `data/raw/` | die API-Antworten Byte für Byte, gzip-komprimiert |
| Bronze | `data/bronze/` | daraus abgeleitetes Parquet mit festem Schema |

Beide Schichten teilen dieselbe `run_id`. Raw ist das Beweisstück und lässt sich
nicht rekonstruieren — ein Delta-Lauf hält Datensätze so fest, wie sie in diesem
Moment waren. Bronze ist abgeleitet und jederzeit neu erzeugbar. Detroit folgt
derselben Aufteilung.

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

### Aufbau der Schichten

```text
data/
├── raw/
│   └── city=chicago/
│       └── ingest_date=2026-09-05/
│           └── run_20260905T174014844258Z/
│               ├── page-0001.json.gz
│               ├── page-0002.json.gz
│               └── manifest.json
└── bronze/
    └── city=chicago/
        └── ingest_date=2026-09-05/
            └── run_20260905T174014844258Z/
                ├── part-0001.parquet
                └── manifest.json
```

Die Partitionierung folgt dem Abrufdatum, nicht dem Tatdatum. Jeder Lauf wird
zuerst in versteckten `.part`-Verzeichnissen erstellt und erst nach
erfolgreichem Abschluss atomar veröffentlicht — zuerst Raw, dann Bronze.

**Raw.** Eine Datei je API-Seite mit dem unveränderten Antwortkörper. Nichts wird
umgewandelt: `arrest` bleibt ein JSON-Boolean, `location` ein verschachteltes
Objekt. Die Kompression ist deterministisch (`mtime=0`), damit der SHA-256 im
Manifest allein von der Antwort abhängt.

**Bronze.** Aus Raw abgeleitet, mit den Originaltypen im Parquet-Schema. Das
Manifest verweist über `derived_from` auf den Raw-Lauf derselben `run_id`.

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
- Vollständigkeitsnachweis (`completeness`): Zählung davor und danach, Grösse
  und SHA-256 der festgeschriebenen `id`-Liste, geladene Zeilen
- Schema-Fingerabdruck der Quelle samt Feldtypen (`source_schema`)
- Schicht (`layer`), Format und die Dateien dieser Schicht

### Robustheit

Fünf Mechanismen schützen die Bronze-Schicht vor unbemerkt unvollständigen
Läufen:

**Wiederholungen.** Die Session wiederholt gedrosselte und vorübergehend
fehlerhafte Antworten (429, 500, 502, 503, 504) bis zu fünfmal mit
exponentiellem Backoff. Ein voller Snapshot braucht rund 30 Anfragen; ohne
Wiederholung würde ein einzelner Fehler den ganzen Lauf verwerfen.

**Keyset-Pagination statt Offset.** Jede Folgeseite fragt ab der zuletzt
gesehenen `id` (`... AND id > 13324861`, sortiert nach `id`) statt über
`$offset`. Bei Offset-Paginierung verschieben gleichzeitige Änderungen an der
Quelle die Seitengrenzen, wodurch Zeilen übersprungen oder doppelt geliefert
werden können. Mit dem Schlüssel als Anker kann das nicht passieren.

**Festgeschriebener Snapshot.** Vor dem Download wird die Menge der `id`-Werte
abgefragt und festgehalten. Danach muss die Menge der geladenen `id`-Werte
exakt dieser Liste entsprechen — nicht nur die Anzahl. Fehlt eine Zeile oder
kommt eine unerwartete hinzu, bricht der Lauf ab und veröffentlicht nichts. Eine
reine `id`-Abfrage liefert bis zu 50 000 Werte, ein ganzer Jahrgang kostet also
nur wenige zusätzliche Anfragen.

**Zählungen als Klammer.** `count(1)` läuft vor dem Lauf gegen die
`id`-Liste (Abweichung = Abbruch) und noch einmal danach. Die zweite Zählung
blockiert nicht, sondern hält als `source_changed_during_run` fest, ob sich die
Quelle während des Laufs bewegt hat. Ist die Zählung nicht verfügbar, bleibt der
`id`-Abgleich als Nachweis bestehen. Läufe mit `--max-records` kürzen absichtlich
und durchlaufen keine dieser Prüfungen.

**Schema-Fingerabdruck.** Aus den Feldnamen und Feldtypen der Quelle wird ein
SHA-256 gebildet und im Manifest abgelegt. Ändert die Stadt den Typ eines
Feldes, ändert sich der Fingerabdruck — auch dann, wenn die Ingestion
weiterläuft. Die Spalte `_extra` fängt neue Felder auf, eine Typänderung an
einem bestehenden Feld würde sie nicht bemerken.

**Aufräumen.** Bricht ein Lauf hart ab, bleiben seine `.part`-Verzeichnisse
liegen. Der nächste Start entfernt sie in beiden Schichten, sobald sie älter als
24 Stunden sind. Veröffentlichte Läufe werden nie angefasst.

Das Wasserzeichen wird ausschliesslich aus Bronze-Manifesten gelesen, und Bronze
wird zuletzt veröffentlicht. Scheitert ein Lauf zwischen den Schichten, bleibt
das Beweisstück in Raw erhalten, das Wasserzeichen rückt aber nicht vor: Der
nächste Lauf wiederholt dasselbe Fenster, statt eine Lücke zu hinterlassen.

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
