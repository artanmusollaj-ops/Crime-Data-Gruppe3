# Crime-Data-Gruppe3

[![Tests](https://github.com/artanmusollaj-ops/Crime-Data-Gruppe3/actions/workflows/tests.yml/badge.svg)](https://github.com/artanmusollaj-ops/Crime-Data-Gruppe3/actions/workflows/tests.yml)

Vergleich der Kriminalitätsdaten von **Chicago und Detroit für das Jahr 2024** —
eine Semesterarbeit im CAS Data Engineering.

Die Frage klingt einfach und ist es nicht: *Wo passiert was, wie oft, im
Verhältnis zu wie vielen Menschen?* Beide Städte veröffentlichen ihre Falldaten
offen, aber sie tun es unvergleichbar. Chicago liefert eine Zeile je Delikt und
codiert nach **IUCR**, Detroit eine Zeile je **Anklage** und codiert nach
**MICR**. Chicagos Zeitstempel ist Ortszeit ohne Zonenangabe, Detroits ist UTC.
Und keine der beiden Quellen sagt, zu welcher Stadt ein Gebiet gehört — ohne
Stadtgrenze gibt es keinen Nenner und damit keine Rate je Einwohner.

Dieses Repository baut die Strecke, die aus zwei unvergleichbaren Quellen eine
vergleichbare Tabelle macht:

```text
        Chicago ─┐
        Detroit ─┤
  Census TIGER ──┼──▶  raw ──▶ bronze ──▶ silver ──▶ gold ──▶ serving
    Census ACS ──┤       │        │          │         │         │
     NOAA GHCN ──┘    Beweis   geparst    gedeutet   Stern    Abfragen
```

| Schicht | Was sie ist |
| --- | --- |
| **raw** | die Antwort der Quelle, Byte für Byte, mit SHA-256. Nicht rekonstruierbar |
| **bronze** | daraus abgeleitetes Parquet mit gepinntem Schema. Deutet nichts |
| **silver** | die erste deutende Schicht: Typen, Einheiten, Zeitzonen, NIBRS, Raum |
| **gold** | Sternschema mit einer Faktentabelle je Tat und vier Dimensionen |
| **serving** | DuckDB-Sichten über die Schichten, für die Auswertung |

**Der Stand in Zahlen** — was gerade in den Schichten liegt:

| | |
| --- | ---: |
| `silver/crime_offense` | 347'957 Zeilen (Detroit: eine Anklage) |
| `gold/fact_offense` | 344'617 Zeilen (eine Tat) |
| Chicago | 251'516 Delikte · 2'661'953 Einwohner · **94,5** je 1'000 |
| Detroit | 84'658 Delikte · 638'635 Einwohner · **132,6** je 1'000 |

Wo etwas ausführlich steht:

| Was | Wo |
| --- | --- |
| Konzept, Methode, Befunde | [`docs/ln1_konzept.md`](docs/ln1_konzept.md) |
| Was jede Spalte bedeutet | [`docs/feldkatalog.md`](docs/feldkatalog.md) |
| Was sich wann geändert hat und warum | [`docs/AENDERUNGEN.md`](docs/AENDERUNGEN.md) |
| Würfel und Sternschema erklärt | [`docs/sternschema-und-wuerfel.md`](docs/sternschema-und-wuerfel.md) |
| Detroit-Pipeline im Detail | [`docs/DETROIT_PIPELINE_ANLEITUNG.md`](docs/DETROIT_PIPELINE_ANLEITUNG.md) |
| Die Quellen einzeln erklärt | [`notebooks/`](notebooks/) 01, 11, 21, 22, 32 |
| Datenqualität je Stadt | [`notebooks/03`](notebooks/03_chicago_data_quality.ipynb), [`notebooks/13`](notebooks/13_detroit_data_quality.ipynb) |

---

## 1 · Einrichten

**Voraussetzungen:** Python 3.11 oder neuer, Git.

**Nicht in einem Sync-Ordner arbeiten.** Das Projekt gehört nicht nach
`~/Documents`, `OneDrive` oder `iCloud Drive`. Sync-Dienste legen mitten im
Betrieb Konfliktkopien an (`datei 2.txt`), ändern Dateirechte und können sowohl
die virtuelle Umgebung als auch `.git/` beschädigen. Ein Ort wie
`~/Projekte/Crime-Data-Gruppe3` ist richtig; versioniert wird über GitHub, eine
zweite Synchronisation braucht es nicht.

### 1.1 Umgebung anlegen

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`requirements.txt` installiert das Projekt editierbar; die Abhängigkeiten stehen
in `pyproject.toml` als Bereiche. Wer **exakt** den Stand will, mit dem CI
unter Python 3.13 läuft:

```bash
python -m pip install -r requirements.lock && python -m pip install -e . --no-deps
```

Der Unterschied ist real — am 13.9. hatte ein Rechner `numpy 2.5.2`, der frische
Klon `2.5.3`. Danach sind alle Pipelines importierbar, unabhängig vom
aktuellen Verzeichnis:

```text
src/crime/
├── chicago_pipeline/   → import chicago_pipeline
├── detroit_pipeline/   → import detroit_pipeline
├── census_pipeline/    → import census_pipeline
├── weather_pipeline/   → import weather_pipeline
├── silver_pipeline/    → import silver_pipeline
├── gold_pipeline/      → import gold_pipeline
└── serving/            → import serving
```

**Anaconda oder Miniconda installiert?** Dann ist `python` in einer frischen
Shell der Conda-Interpreter: Die von `conda init` erzeugte Zeile in `~/.zshrc`
aktiviert bei jedem Start automatisch die Umgebung `base`. Ein `python -m venv
.venv` legt die Umgebung damit auf Conda an — mit einer anderen Python-Version
und anderen Paketversionen als in `pyproject.toml` vorgesehen. Den Interpreter
beim Anlegen deshalb ausschreiben:

```bash
which -a python3    # zeigt alle Interpreter im PATH
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13 -m venv .venv
```

Nach dem Aktivieren zählt nur, worauf `python` tatsächlich zeigt — nicht, was im
Prompt steht:

```bash
source .venv/bin/activate
which python     # .../<projekt>/.venv/bin/python
python -V        # Python 3.13.0
```

**`conda deactivate` ist nicht die Lösung.** `source .venv/bin/activate` stellt
`.venv/bin` an den Anfang des `PATH` und gewinnt damit gegen Conda; eine intakte
Umgebung braucht kein `deactivate`. Zeigt `which python` trotz `(.venv)` im
Prompt auf Conda, geht der Eintrag im `PATH` ins Leere — dann hilft nur, die
Umgebung neu anzulegen. Conda aus dem `PATH` zu nehmen holt lediglich den
nächsten falschen Interpreter nach vorn.

**Die Umgebung lässt sich nicht verschieben.** `.venv/bin/activate` und jedes
Konsolenskript darin enthalten den absoluten Pfad, unter dem die Umgebung
angelegt wurde. Wird das Projekt verschoben oder kopiert, zeigt dieser Pfad ins
Nichts: Der Prompt meldet weiterhin `(.venv)`, `python` fällt aber auf den
nächsten `PATH`-Eintrag durch — auf Conda. Da `.venv` in `.gitignore` steht und
ohnehin nie mitwandert, nach einem Umzug löschen und neu anlegen.

### 1.2 Zertifikate prüfen (nur macOS)

Die Detroit-Pipeline nutzt `urllib` aus der Standardbibliothek. Python-Versionen
von python.org bringen dort **keinen** Zertifikatsspeicher mit, jeder
HTTPS-Aufruf endet dann nach fünf Wiederholungen in
`CERTIFICATE_VERIFY_FAILED`. Einmalig pro Rechner:

```bash
open "/Applications/Python 3.13/Install Certificates.command"
```

Die Chicago-Pipeline ist nicht betroffen, sie nutzt `requests` mit eigenem
Zertifikatsbündel — deshalb kann Chicago laufen, während Detroit scheitert.

### 1.3 Schlüssel hinterlegen

Eine Datei `.env` im Projekt-Root, nach dem Muster von `.env.example`. Sie ist
über `.gitignore` ausgeschlossen.

**Wer lokal arbeitet, braucht zwei Zeilen** — und keine davon betrifft den
gemeinsamen Speicher:

```text
CENSUS_API_KEY=dein_schluessel     # Pflicht für die ACS-Daten
SOCRATA_APP_TOKEN=dein_token       # optional, für Chicago
```

**`CENSUS_API_KEY` ist Pflicht**, wenn Census-Daten geladen werden sollen —
kostenlos unter <https://api.census.gov/data/key_signup.html>. Ohne ihn
antwortet die API mit **HTTP 200** und einer HTML-Seite „Missing Key" statt mit
einem Fehlerstatus; die Pipeline erkennt das und bricht ab, statt eine leere
Tabelle zu schreiben.

`SOCRATA_APP_TOKEN` ist optional. Ohne Token funktioniert der öffentliche
Zugriff auf Chicago ebenfalls, wird aber stärker gedrosselt.

**Den gemeinsamen Speicher braucht es nur, wenn du ihn willst.** `data/` ist
die Vorgabe; solange `STORAGE_BACKEND` fehlt oder auf `local` steht, wird
keine einzige `S3_`-Variable gelesen und `boto3` nie importiert. Wer den
Bestand mit dem Team teilen will, ergänzt drei Zeilen (mehr zu den Modi
in 2.5):

```text
STORAGE_BACKEND=hybrid             # lokal zuerst, SeaweedFS als Rückfall
S3_ACCESS_KEY=dein_schluessel
S3_SECRET_KEY=dein_geheimnis
```

| Variable | Vorgabe | wann nötig |
| --- | --- | --- |
| `STORAGE_BACKEND` | `local` | für `hybrid` und `s3` |
| `S3_ACCESS_KEY`, `S3_SECRET_KEY` | — | für `hybrid` und `s3`, sonst nie |
| `S3_ENDPOINT` | `s3.datenwerft.ch` | nur bei abweichendem Server |
| `S3_BUCKET` | `urban-crime` | nur bei abweichendem Bucket |
| `LOCAL_DATA_ROOT` | `data` | nur bei abweichendem Verzeichnis |

Fehlt ein Schlüssel, sagt es die Konfiguration sofort und nennt die Variable
— nicht erst die fünfte Pipeline-Stufe. Prüfen mit `python -m storage`.

### 1.4 Einrichtung prüfen

```bash
python -m pytest
```

Erwartet werden **896 bestandene Tests**, ohne Netzzugriff und ohne Schlüssel.
Läuft das durch, ist die Einrichtung in Ordnung — die Tests arbeiten mit kleinen
Fixtures und simulierten Quellen.

Bei der weiteren Arbeit genügt `source .venv/bin/activate`; verlassen wird die
Umgebung mit `deactivate`.

---

## 2 · Daten laden

Die Reihenfolge ist nicht beliebig: Jede Schicht liest die darunter. Von einem
leeren `data/` aus sind es drei Blöcke.

> **Hinweis:** `data/` steht in `.gitignore` — die Daten wandern nicht über Git.
> Wer frisch klont, lädt sie mit den Schritten unten selbst. Rechnen Sie mit
> rund zehn Minuten, das meiste davon Wartezeit an den APIs.

### 2.0 Alles auf einmal

```bash
python -m orchestration.run_all                  # alles, inklusive Ingestion
python -m orchestration.run_all --ohne-ingestion # nur neu ableiten
python -m orchestration.run_all --trocken        # nur zeigen, was liefe
```

Der Controller kennt die Reihenfolge, bricht bei der ersten gescheiterten Stufe
ab und schreibt `data/pipeline_run.json`. Mit `--maximal-alter-tage 8` scheitert
er ausserdem, wenn der jüngste Lauf einer Quelle älter ist — bei
`--ohne-ingestion` schon **vor** der ersten Stufe, weil die Daten dabei nicht
frischer werden. Das Manifest enthält: welche Stufen liefen, **auf welchen
Bronze-Läufen** das Ergebnis ruht, wie alt jede Quelle ist, und einen
Fingerabdruck über die Eingaben. Zwei Läufe auf demselben Stand tragen
denselben Fingerabdruck.

Die Abschnitte darunter erklären, was er tut — und sie sind der Weg, wenn nur
eine Stufe neu laufen soll.

### 2.1 Ingestion — raw und bronze

Jeder Aufruf schreibt einen **unveränderlichen Lauf**: erst in ein verstecktes
`.part`-Verzeichnis, dann atomar veröffentlicht, zuerst raw, dann bronze. Beide
teilen dieselbe `run_id`. Frühere Läufe werden nie überschrieben.

```bash
# Chicago — erster Aufruf lädt 2024 vollständig,
# spätere erkennen das Wasserzeichen und laden ein Delta mit 14 Tagen Überlappung
python -m chicago_pipeline.download_chicago

# Detroit — immer ein voller Jahrgang, siehe unten warum
python -m detroit_pipeline.extract_detroit --mode full --years 2024

# Census: Geometrien (Tracts und Stadtgrenzen) und Einwohnerzahlen
python -m census_pipeline.download_tiger --auslieferung tract
python -m census_pipeline.download_tiger --auslieferung place
python -m census_pipeline.download_acs

# Wetter: je Stadt eine Station
python -m weather_pipeline.download_noaa
```

**Warum Detroit keine Deltas lädt.** 54,6 % des Jahrgangs 2024 wurden *mehr als
ein Jahr nach der Tat* noch geändert. Ein Delta nach Tatdatum verpasst diese
Korrekturen. Bei 88'685 Zeilen und 97 Sekunden Laufzeit ist der volle Snapshot
die einfachere und die richtigere Variante — gemessen in
[Notebook 13](notebooks/13_detroit_data_quality.ipynb), Schritt 12.

**Was raw und bronze unterscheidet.** Raw ist das Beweisstück: die Antwort Byte
für Byte, gzip-komprimiert mit `mtime=0`, damit der SHA-256 im Manifest allein
von der Antwort abhängt. Ein Delta-Lauf hält Datensätze so fest, wie sie in
diesem Moment waren — das lässt sich später nicht rekonstruieren. Bronze ist
daraus abgeleitet und jederzeit neu erzeugbar; es behält die Originaltypen der
Quelle und deutet nichts. Alles Unerwartete landet in einer Auffangspalte
`_extra`, statt verworfen zu werden.

Ein Lauf sieht so aus:

```text
data/
├── raw/city=chicago/ingest_date=2026-09-05/run_20260905T174014844258Z/
│   ├── page-0001.json.gz
│   └── manifest.json
└── bronze/city=chicago/ingest_date=2026-09-05/run_20260905T174014844258Z/
    ├── part-0001.parquet
    └── manifest.json
```

Partitioniert wird nach dem **Abrufdatum**, nicht nach dem Tatdatum.

Für einen kleinen Test ohne Spuren im echten `data/`:

```bash
python -m chicago_pipeline.download_chicago \
  --data-root /tmp/chicago-test --max-records 5
```

### 2.2 Silver — die erste deutende Schicht

```bash
python -m silver_pipeline.build_tract          # zuerst: crime_offense braucht ihn
python -m silver_pipeline.build_place
python -m silver_pipeline.build_weather_day
python -m silver_pipeline.build_crime_offense
```

Anders als Bronze wird Silver **ersetzt und nicht angehäuft** — die Schicht ist
abgeleitet und jederzeit neu erzeugbar. Das Manifest nennt trotzdem die `run_id`
jedes Bronze-Laufs, aus dem die Tabelle entstand.

Vier Tabellen, weil die Quellen vier Körner haben. Sie in eine zu zwingen würde
Zeilen vervielfachen — ein Wetterwert an jedem Delikt derselben Stadt und
desselben Tages — oder Information wegwerfen:

| Tabelle | Eine Zeile ist | Zeilen |
| --- | --- | ---: |
| `tract` | ein Census Tract | 6'282 |
| `place` | ein Ort (Stadtgrenze) | 2'206 |
| `weather_day` | eine Stadt an einem Tag | 55'449 |
| `crime_offense` | eine **Anklage**; je Tat zählt eine | 347'957 |

`crime_offense` leistet drei Übersetzungen auf einmal, und jede ist ein eigener
Fehlerherd:

* **Delikte.** Chicagos `iucr` und Detroits `state_offense_code` gehen über
  [`config/iucr_nibrs_mapping.csv`](config/) und
  [`config/micr_nibrs_mapping.csv`](config/) auf **NIBRS**, die bundesweite
  Codeliste. Beide Städte zu 100 % zugeordnet.
* **Zeit.** Chicagos `date` sieht aus wie ein Zeitstempel, ist aber Ortszeit
  ohne Zone; Detroits Feld ist bereits UTC. Wer beide gleich behandelt,
  vergleicht Städte, die je nach Jahreszeit ein bis zwei Stunden
  auseinanderliegen. Die Tabelle führt deshalb `occurred_at_utc` **und**
  `occurred_at_local`.
* **Raum.** Punkt-in-Polygon gegen `tract`, damit beide Städte dieselbe
  Raumeinheit tragen. Chicago 99,3 % verortet, Detroit 99,7 %.

**Die Tabelle wirft nichts weg.** Weder unverortete Fälle noch solche ohne
NIBRS-Zuordnung noch Detroits `UNFOUNDED`-Fälle. Alle drei sind gekennzeichnet
(`located`, `nibrs_mapped`, `unfounded`), damit eine Auswertung sie bewusst
ein- oder ausschliessen kann und dabei sieht, wie viele Zeilen es betrifft.

### 2.3 Gold und Serving

```bash
python -m gold_pipeline.build_gold
python -m serving.build_analysis_db
python -m serving.export_geojson      # die Tract-Umrisse für eine Karte
```

Gold ist ein **Sternschema**: eine Faktentabelle `fact_offense` mit einer Zeile
je **Tat** und vier Dimensionen daneben. Der Unterschied zu Silver ist das Korn
— Detroit liefert je Vorfall mehrere Anklagen; wer Zeilen zählt, zählt Detroit
um 3,9 % zu hoch. Warum kein vorberechneter Würfel gebaut wurde, steht in
[`docs/sternschema-und-wuerfel.md`](docs/sternschema-und-wuerfel.md).

`build_analysis_db` erzeugt `data/serving/analyse.duckdb` — eine DuckDB-Datei
mit **Sichten** über die Parquet-Schichten, keine Kopie. Ein Silver- oder
Gold-Neubau ist darin sofort sichtbar.

```bash
duckdb -readonly data/serving/analyse.duckdb
```

```sql
SHOW TABLES;              -- fünf Gold-, vier Silver- und zwei Metasichten
SELECT * FROM tabellen;   -- welche Sicht auf welche Datei zeigt
```

Ein typischer Stern-Join — die Rate je 1'000 Einwohner:

```sql
WITH einwohner AS (
    SELECT city, sum(population) AS n
    FROM dim_tract WHERE city IS NOT NULL GROUP BY 1
)
SELECT t.city, count(*) AS delikte, any_value(e.n) AS einwohner,
       round(count(*) * 1000.0 / any_value(e.n), 1) AS je_1000
FROM fact_offense f
JOIN dim_tract t ON t.geoid = f.tract_geoid
JOIN einwohner e ON e.city  = t.city
WHERE t.city IS NOT NULL
GROUP BY 1 ORDER BY je_1000 DESC;
```

**`WHERE t.city IS NOT NULL` nie vergessen.** `dim_tract` enthält alle Tracts
beider Countys, auch die ausserhalb der Stadtgrenzen — ohne den Filter zählen
Vorstädte mit.

`export_geojson` schreibt daneben `data/serving/tracts.geojson`: die **1'055
Tract-Umrisse** der beiden Städte, auf rund zwei Meter vereinfacht, 0,55 MB.
Die Datei trägt je Fläche nur `geoid`, `city` und `tract_name` — **keine
Kennzahl**. Wer einfärben will, verbindet über `geoid` mit `dim_tract` und
`fact_offense`; so bleibt Gold die einzige Quelle für Zahlen, die sich ändern
können.

---

### 2.4 Aufräumen — was von Raw und Bronze bleiben muss

Jeder Lauf legt ein neues Verzeichnis an, nichts wird überschrieben. Das ist
gewollt, und es wächst. Was bleiben muss, sagt ein Werkzeug:

```bash
python -m orchestration.aufraeumen             # zeigt je Quelle, was bleibt und warum
python -m orchestration.aufraeumen --loeschen  # löscht die entbehrlichen Läufe, Raw und Bronze zusammen
```

Es bleiben: der **jüngste Lauf und der davor** (der zweite ist der
Schnappschuss, gegen den Notebook 13 die Quelle prüft), alles, was ein
**Silver-Manifest nennt**, und die **Basis eines Delta-Laufs** — Chicago lädt
seit dem ersten vollen Schnappschuss nur Änderungen. Ohne `--loeschen`
geschieht nichts. `data/` ist nicht versioniert; die Regel gilt je Rechner.

### 2.5 Ablage: lokal, SeaweedFS oder hybrid

> Der ganze Aufbau — Entwurf, Zusicherungen, API, Betrieb — steht in
> [`docs/storage-architektur.md`](docs/storage-architektur.md). Hier steht,
> wie man ihn bedient.

Wo die Schichten liegen, entscheidet `STORAGE_BACKEND` in `.env`. Die
Befehle bleiben dieselben, die Struktur unter der Wurzel auch —
`bronze/city=chicago/ingest_date=…/run_…/part-0001.parquet` heisst lokal
`data/…` und auf SeaweedFS `s3://urban-crime/…`.

| Modus | Lesen | Schreiben |
| --- | --- | --- |
| `local` (Vorgabe) | `data/` | `data/` — genau wie bisher |
| `hybrid` | lokal, wenn die Datei da ist, **sonst SeaweedFS** | lokal, prüfen, **dann gezielt publizieren** |
| `s3` | immer SeaweedFS | lokal als Arbeitsverzeichnis, prüfen, publizieren, lokale Kopie entfernen |

**Hybrid ist der Modus für die Zusammenarbeit.** SeaweedFS ist der gemeinsame
veröffentlichte Bestand, `data/` die Arbeitskopie. Wer eine Tabelle lokal
nicht hat, liest sie von SeaweedFS — ohne vorher etwas zu synchronisieren.
Umgekehrt erreicht nur, was Bau **und** Prüfung bestanden hat, den gemeinsamen
Bestand: je Lauf oder Tabelle, `manifest.json` zuletzt. Läufe (`run_…`)
werden nie überschrieben — liegt einer schon anders oben, ist das ein
Fehler. Silver- und Gold-Tabellen werden überschrieben, wie lokal auch.

**Immer lokal:** `data/serving/` — die Auswertungsdatenbank und das
GeoJSON. Die Sichten in `analyse.duckdb` zeigen je Datei dorthin, wo sie
liegt. Wer sie im Hybrid- oder S3-Modus öffnet, braucht dieselbe Verbindung
wie die Pipeline — `httpfs` und ein temporäres Secret, nichts wird
persistiert:

```python
from storage import get_storage
from storage.duckdb import connect
con = connect(get_storage().config, "data/serving/analyse.duckdb", read_only=True)
```

**Wenn dein lokaler Stand älter ist.** „Lokal zuerst" hat eine scharfe
Kante: Eine Silver- oder Gold-Tabelle von letzter Woche wird gelesen, auch
wenn auf SeaweedFS eine neuere liegt. Deshalb vergleicht die Ablage bei
diesen Tabellen beide Manifeste — `built_at_utc` und die Bronze-Läufe aus
`derived_from`:

- **Beim Lesen** eine Warnung, gelesen wird trotzdem lokal. Wer offline
  arbeitet, arbeitet weiter.
- **Beim Publizieren** eine Absage, wenn dein Stand älter ist oder auf
  weniger Bronze-Läufen ruht — er würde einen neueren verdrängen, und
  niemand sähe es ihm an. Der Bau bleibt lokal fertig; nur das Hochladen
  unterbleibt, mit einem Satz statt eines Tracebacks.

`python -m storage` zeigt es je Tabelle, bevor du etwas baust:

```text
Staende    :
  silver/dataset=crime_offense    ALT - hier gebaut 08.09.2026 10:00 UTC,
                                  auf SeaweedFS 13.09.2026 14:06 UTC;
                                  dort stecken 4 Bronze-Laeufe, die hier fehlen
```

Der Ausweg ist immer derselbe: `python -m orchestration.run_all
--ohne-ingestion`. Danach ruht dein Stand auf allen Läufen — den lokalen und
denen von SeaweedFS. Läufe unter `bronze/` und `raw/` sind davon nicht
betroffen: Sie sind unveränderlich und ergänzen einander.

**Bewusst nicht:** kein automatisches Herunterladen (was fehlt, wird von
S3 *gelesen*, nicht kopiert), keine Synchronisation zurück, kein
Dual-Write. `orchestration.aufraeumen` räumt weiterhin nur lokal auf.

In Notebooks und Skripten liefert `from storage import resolve_read_path`
den Pfad, den `read_parquet` lesen soll — lokal oder `s3://`, ohne dass der
Code es wissen muss.

Prüfen, ob SeaweedFS erreichbar ist — **vor** der ersten Pipeline (braucht
die Schlüssel; kein Test hängt davon ab):

```bash
python -m storage
```

Zeigt Modus, Wurzel, Endpoint und Bucket (nie die Schlüssel), löst den
Hostnamen auf und listet `silver/`. Antwortet SeaweedFS nicht, sagt auch jede
Pipeline nur noch einen Satz — *nicht erreichbar*, *lehnt ab* mit dem Code —
statt eines boto3-Tracebacks. Vorübergehende Aussetzer (403, 5xx,
Verbindungsabbruch) werden bis zu viermal mit Pause wiederholt.

**Bestehende Läufe nachpublizieren.** Die Pipelines publizieren nur den
Lauf, den sie gerade schreiben. Was vorher da war — Chicagos
Vollschnappschuss, die Deltas, Detroit, Census, NOAA — kommt so hoch, Raw vor
Bronze, je Lauf das Manifest zuletzt, idempotent:

```bash
python -m storage publizieren              # zeigt, was lokal liegt und oben fehlt
python -m storage publizieren --wirklich   # lädt es hoch
```

Kein Sync: Was auf SeaweedFS liegt und lokal nicht, bleibt unberührt.

## 3 · Wenn etwas klemmt

| Symptom | Ursache und Abhilfe |
| --- | --- |
| `ModuleNotFoundError: No module named 'chicago_pipeline'` | Die editierbare Installation greift nicht. Zuerst `which python` prüfen: Läuft ein anderer Interpreter als der der Umgebung, oder wurde `.venv` neu angelegt ohne `python -m pip install -r requirements.txt`, fehlt die Installation schlicht. Notlösung: `export PYTHONPATH=src/crime`. Die Tests brauchen das nicht, `pyproject.toml` setzt `pythonpath` für pytest ohnehin. |
| Prompt zeigt `(.venv)`, `which python` zeigt auf Conda | Die Umgebung wurde verschoben oder mit dem Conda-Python angelegt; ihr `PATH`-Eintrag geht ins Leere. `.venv` löschen und neu anlegen. `conda deactivate` behebt es nicht. |
| Unerwartete Paketversionen, etwa ein älteres `pyarrow` | Es läuft der Conda-Interpreter statt der Umgebung. Prüfen mit `which python` und `python -c "import pyarrow; print(pyarrow.__version__)"`. |
| `CERTIFICATE_VERIFY_FAILED` bei Detroit | Abschnitt 1.2. Alternativ nur für die Sitzung: `export SSL_CERT_FILE=$(python -c "import certifi; print(certifi.where())")`. |
| `CENSUS_API_KEY fehlt` | Abschnitt 1.3. Der Schlüssel ist kostenlos und wird sofort per Mail zugestellt. |
| Census antwortet mit „Missing Key" trotz Schlüssel | Der Schlüssel steht in `.env`, aber das Programm läuft aus einem anderen Verzeichnis. `.env` wird ab dem **aktuellen** Verzeichnis gesucht — aus dem Projekt-Root starten. |
| `Kein erfolgreicher Detroit-Bronze-Lauf` beim Silver-Bau | Bronze fehlt oder kein Lauf trägt `status: SUCCESS`. Erst die Ingestion aus 2.1. |
| `Nur NDJSON-Bestände aus der Zeit vor dem Zeitzonen-Fix` | Alte Detroit-Daten. Ihr Jahresfenster war in UTC gezogen statt in Detroiter Ortszeit und enthält Fälle aus dem falschen Jahr. Neu laden: `python -m detroit_pipeline.extract_detroit --mode full --years 2024`. |
| DuckDB meldet, die Datei sei gesperrt | Eine andere Sitzung hält `analyse.duckdb` schreibend offen. Mit `-readonly` beziehungsweise `read_only=True` können beliebig viele Leser gleichzeitig zugreifen. |
| Dateien mit „ 2" im Namen, wechselnde Rechte | Ein Sync-Dienst greift in den Ordner. Konfliktkopien entfernen — auch die ohne Endung, etwa `METADATA 2` (`find .venv \( -name "* [0-9]" -o -name "* [0-9].*" \) -delete`) —, neu installieren, und das Projekt aus dem Sync-Ordner nehmen. |

---

## 4 · Tests

```bash
python -m pytest
```

**896 Tests**, alle ohne Netzzugriff und ohne Schlüssel. Sie decken ab:

* **Ingestion** — Argumentprüfung, Token-Ermittlung, Wasserzeichen und
  Lookback, Paginierung, Wiederholungen, Vollständigkeits-Gates, das Aufräumen
  liegengebliebener `.part`-Verzeichnisse und das atomare Veröffentlichen
  beider Schichten samt Manifest.
* **Crosswalks** — dass sich `config/*.csv` aus den amtlichen PDFs
  **reproduzieren** lässt: Das Werkzeug läuft in ein temporäres Verzeichnis,
  und das Ergebnis muss byteweise mit der versionierten Datei übereinstimmen.
  Ohne diese Prüfung wäre „nicht von Hand gepflegt" eine Behauptung.
* **Silver und Gold** — Korn, Deduplikation, Zeitzonen, der räumliche Join, die
  Stadtzuordnung und die zurückgezogenen NIBRS-Codes.
* **Die Dokumente** — `tests/test_abgabedokumente.py` und
  `tests/test_aenderungen.py` prüfen die Zahlen in `docs/` gegen die gebauten
  Parquet-Dateien. Eine Zahl auf einer Folie, die der Zahl im Konzept
  widerspricht, ist der teuerste Fehler in einer Abgabe.

### Vor den Tests: `ruff`

```bash
ruff check src tests tools
```

Pyflakes-Regeln plus `raise … from`: ungenutzte Importe, undefinierte Namen,
verschluckte Ursachen. Das sind die Fehler, die eine Testsuite nicht sieht —
zwei davon sind an einem Tag durchgerutscht, bevor es die Prüfung gab. CI führt
sie vor der Suite aus.

### Sie laufen auch ohne dich

Seit dem 12.9.2026 führt **GitHub Actions** die Suite auf jedem Pull Request und
auf `main` aus — unter **Linux und Windows**, je mit Python **3.11 und 3.13**.
Windows, weil Artan darauf entwickelt.

In einem frischen Klon laufen **855 der 896 Tests**. Die übrigen 41 überspringen
sich selbst, weil sie gebaute Daten brauchen und `data/` nicht versioniert ist.
Was trotzdem läuft, ist das Wesentliche: die Reproduzierbarkeit der Crosswalks
aus den amtlichen PDFs, die Form der Abgabedokumente — und die beiden Wächter
über die Testzahl in diesem README und in `AENDERUNGEN.md`.

### Einmal die Woche mit echten Daten

Die 40 Tests, die ein Pull Request überspringt, sind ausgerechnet die
Wächter — Zahlen gegen Parquet, die Einwohnerprobe, „kein Delikt in der
falschen Stadt". Der Workflow `datenlauf.yml` fährt deshalb **montags** die
ganze Strecke: alle fünf Quellen laden, Silver, Gold und Serving bauen, dann
die komplette Suite. Von Hand startbar unter *Actions → Datenlauf*.

Nach dem Bau führt er die **sechs Notebooks aus, die Zahlen belegen** — 03,
13, 31, 32, 33, 34 — und legt sie mit Ausgaben als Artefakt ab. Die sechs, die
laden, laufen bewusst nicht: Sie würden zusätzliche Bronze-Läufe erzeugen.
Notebook 32 war vor dieser Prüfung einen Tag lang still kaputt.

Er braucht `CENSUS_API_KEY` als Repository-Secret; der erste Schritt prüft
das und sagt, was fehlt.

**Drift statt Rot.** Die Quellen bewegen sich jede Woche — Detroit ändert
Einträge noch Jahre nach der Tat, Chicago liefert Deltas. Die Wächter, die
dokumentierte Zahlen gegen Parquet halten (Marker `referenzstand`), laufen im
Datenlauf deshalb **nicht**; sie gelten für den Referenzstand auf deinem
Rechner. Stattdessen weist `orchestration.drift` je Grösse aus, wie weit der
dokumentierte Stand vom frischen entfernt ist — als Tabelle in der
Job-Zusammenfassung (*Actions → Datenlauf → Lauf → Summary*) und als
`drift.json` im Artefakt. **Rot wird es erst über der Toleranz:** eine Rate
je 1'000 bewegt sich um ≥ 0,1, oder eine Zeilen- oder Fallzahl um > 1 %.
Das Wochenrauschen liegt weit darunter; ein Quellenausfall weit darüber —
und dann ist es Zeit, den Referenzstand nachzuziehen. Lokal zeigt
`python -m orchestration.drift` dieselbe Tabelle.

Weitere Optionen zeigt jedes Modul selbst:

```bash
python -m chicago_pipeline.download_chicago --help
python -m detroit_pipeline.extract_detroit --help
```
