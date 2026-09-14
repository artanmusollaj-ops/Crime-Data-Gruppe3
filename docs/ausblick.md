# Ausblick: Lineage, Versionierung, Skalierung, Cloud

Material für den zweiten Leistungsnachweis und darüber hinaus. Dieses
Dokument ist **kein Konzept** — es analysiert, was heute trägt und wo es
aufhört, damit die Entscheidungen später auf Zahlen stehen und nicht auf
Gefühl. Was davon in ein Konzept gehört, entscheidet sich beim Schreiben.

Zwei der vier Themen kommen von **Artan** (14.9.2026) und stehen deshalb
vorn.

| Thema | Kommt von | Dringlichkeit |
| --- | --- | --- |
| [1 · Stichtagskonsistenz und Lineage](#1--stichtagskonsistenz-und-lineage) | Artan | **hoch** — eine Lücke, die heute schon besteht |
| [2 · Die Ladelogik versionieren](#2--die-ladelogik-versionieren) | Artan | **hoch** — billig, und es gibt ein Vorbild im Projekt |
| [3 · Skalieren](#3--skalieren) | Gedankenspiel | mittel — erst relevant ab Stadt drei |
| [4 · In die Cloud](#4--in-die-cloud) | Gedankenspiel | niedrig — technisch fast vorbereitet, fachlich unnötig |

---

## 1 · Stichtagskonsistenz und Lineage

> *„Werte vom Tag X → Silver-Load/Mapping Y → Bronze Load XY am Tag X."*

Die Frage dahinter: Wenn in drei Monaten jemand auf eine Zahl in der Abgabe
zeigt — lässt sich dann sagen, **aus welchen Eingaben sie entstanden ist**,
und lässt sie sich **noch einmal erzeugen**?

### Was die Kette heute leistet

```text
   Quelle          Raw            Bronze          Silver           Gold
     │              │               │               │               │
     │  Abruf am    │  run_id       │  run_id       │  nennt die    │  nennt einen
     │  Tag X       │  identisch ───┤  + Prüfsumme  │  run_ids ─────┤  DATEIPFAD
     │              │  in beiden    │               │  namentlich   │
     ▼              ▼               ▼               ▼               ▼
                  ✓ stark        ✓ stark        ✓ stark        ✗ schwach
```

Die linke Hälfte ist gut: Raw und Bronze tragen dieselbe `run_id`, sind
unveränderlich, und Silver nennt jeden Bronze-Lauf, aus dem es entstanden
ist — namentlich, nicht als Pfad:

```json
"chicago_bronze_runs": ["run_20260905T174633859259Z", "…", "…"],
"detroit_bronze_runs": ["1cca323d-…", "1d879a0e-…"]
```

Von einer **heutigen** Silver-Tabelle aus lässt sich die Kette also
rückwärts lesen. Von einer heutigen **Gold**-Tabelle aus nicht mehr.

### Die schwachen Glieder

| Glied | Heute festgehalten | Reicht das? |
| --- | --- | --- |
| Bronze → Raw | `run_id` identisch, `bronze_sha256` | **ja** |
| Silver → Bronze | Lauf-Kennungen namentlich | **ja** |
| Silver → Crosswalk | `config/iucr_nibrs_mapping.csv` — ein **Pfad** | nein: kein Hash, keine Version |
| Silver → `silver/tract` | ein **Pfad** | nein |
| Gold → Silver | `{"table": "crime_offense", "path": "data/silver/…/part-0001.parquet"}` | **nein — das schwächste Glied** |
| Silver/Gold → Vorgängerstand | gar nichts | nein: es gibt keinen Verlauf |

**Ein Pfad ist keine Version.** `data/silver/dataset=crime_offense/part-0001.parquet`
zeigt auf das, was gerade dort liegt. Wird Silver neu gebaut, zeigt derselbe
Satz im Gold-Manifest auf etwas anderes — und nichts am Manifest verrät es.
Genau das ist Artans Punkt: Zwischen „Werte vom Tag X" und „Bronze Load XY"
fehlt in der Mitte die Angabe, **welches** Silver gemeint war.

### Der billige Teil der Lösung

Man braucht dafür **keine** Historisierung der Silver-Dateien. Es genügt,
dass Gold die **Identität** des Silver-Stands festhält, aus dem es gebaut
wurde — Zeitpunkt und einen Fingerabdruck über dessen Eingaben. Dann schliesst
sich die Kette transitiv:

```text
Gold-Zahl  ──►  Silver-Stand (Zeitpunkt + Fingerabdruck)
                      │
                      └──►  Bronze-Läufe (namentlich)  ──►  Raw (Beweis)
                      └──►  Crosswalks (Version/Hash)
                      └──►  Code-Version (siehe Abschnitt 2)
```

Damit ist eine Zahl vollständig erklärt — **und** reproduzierbar, solange die
genannten Bronze-Läufe noch existieren. Die Zutaten dafür liegen fast alle
schon da: `built_at_utc` in jedem Manifest, `input_fingerprint` in
`pipeline_run.json`, die Lauf-Kennungen in Silver. Es fehlt, sie
**miteinander zu verknüpfen** statt nebeneinander abzulegen.

Aufwand: klein. Wirkung: die Kette ist geschlossen statt an einer Stelle
gerissen.

### Der Konflikt, den niemand gesucht hat

Reproduzierbarkeit braucht die alten Bronze-Läufe. Die **Aufbewahrungsregel**
von gestern (`orchestration.aufraeumen`) behält:

1. den jüngsten Lauf und den davor,
2. alles, was **das aktuelle** Silver nennt,
3. die Basis jedes Delta-Laufs.

Punkt 2 ist der Haken: Sobald Silver auf neueren Läufen neu gebaut wird,
werden die Läufe des **vorigen** Stands entbehrlich — und wären beim nächsten
`--loeschen` weg. Die Regel ist für den Arbeitsalltag richtig und für die
Historisierung falsch. Beides gleichzeitig geht nur mit einer vierten Regel:

> **Gepinnt bleibt.** Ein Lauf, auf den sich eine veröffentlichte Zahl
> bezieht — eine Abgabe, eine Folie, ein Referenzstand —, wird markiert und
> nie aufgeräumt.

Das ist eine kleine Erweiterung einer Sache, die es schon gibt, und sie macht
den Unterschied zwischen „wir könnten reproduzieren" und „wir können".

### In drei Stufen

| Stufe | Was | Aufwand | Was man danach kann |
| --- | --- | --- | --- |
| **A** | Gold nennt die Identität des Silver-Stands, nicht nur den Pfad; Crosswalks mit Hash statt Pfad | klein | jede heutige Zahl vollständig **erklären** |
| **B** | Gepinnte Läufe, die das Aufräumen überleben | klein | jede gepinnte Zahl **reproduzieren** |
| **C** | Silver und Gold versioniert ablegen (`vintage=`/`asof=`), statt zu ersetzen | mittel–gross | **mehrere** Stände nebeneinander halten und vergleichen |

Stufe A und B zusammen lösen Artans Punkt. **Stufe C ist ausdrücklich
optional** — sie ist die teure Variante und hebt die Entscheidung auf, dass
abgeleitete Schichten ersetzt und nicht angehäuft werden (Konzept 7.4). Ich
würde sie erst bauen, wenn jemand tatsächlich zwei Stände vergleichen will;
bis dahin leisten A und B dasselbe für einen Bruchteil.

---

## 2 · Die Ladelogik versionieren

> *„Falls es mal Änderungen an der Downloadlogik gibt, dass die Änderung
> versioniert ist — nicht nur in GitHub — sondern ab wann die Daten anders
> geladen werden."*

Genau richtig, und der Grund ist im Projekt schon vorgekommen: Am 11.9. wurde
Detroits Abfragefenster von UTC auf Ortszeit umgestellt. Läufe davor
enthielten 66 Fälle aus 2023 und vermissten 56 vom Jahresende 2024 (Konzept
8.6). Zwei Läufe, gleiche Struktur, gleiche Quelle — **anders geladen**. Ohne
Vermerk im Lauf selbst sieht man das keinem der beiden an.

### Es gibt schon ein Vorbild — in Detroit

```json
"window_contract_version": 2,
"bronze_contract_version": 2,
"raw_contract_version": 1
```

Detroit macht bereits exakt das, was Artan vorschlägt — nur für Detroit, und
nur für diese drei Verträge. Die Zahl sprang auf 2, als der Zeitzonen-Fix
kam. **Das ist kein Neubau, das ist ein Muster, das verallgemeinert gehört.**

Chicago, Census und NOAA haben nichts Vergleichbares. Und was durchgängig
fehlt, ist der Code-Stand selbst: Die Silver-Manifeste halten `"tool": "duckdb
1.5.5 mit spatial und icu"` fest — die **Engine**, nicht unseren Code.

### Drei Fragen, die leicht verwechselt werden

| Frage | Antwort wäre | Eigenschaft |
| --- | --- | --- |
| **Welcher Code lief?** | Git-Commit im Manifest | automatisch, forensisch genau — aber ändert sich auch bei einem Tippfehler im Kommentar |
| **Hat sich die *Bedeutung* geändert?** | Vertragsversion, von Hand erhöht | bewusst, grob, fachlich — sagt *dass* es anders ist |
| **Ab wann gilt das Neue?** | ein Verlauf | heute nur als Prosa in `AENDERUNGEN.md` |

Der Reiz liegt darin, dass die dritte Frage **keine eigene Antwort braucht**:
Wenn jeder Lauf seine Vertragsversion trägt und Läufe unveränderlich und
zeitgestempelt sind, ist „ab wann" eine *Abfrage*, keine Buchführung —

> „Ab welchem Lauf wurde Detroits Fenster in Ortszeit gezogen?"
> → der erste Lauf mit `window_contract_version = 2`.

Kein Register, das jemand pflegen muss und das veraltet. Die Daten
beantworten es selbst. Das ist derselbe Gedanke wie beim Manifest überhaupt:
Was wahr ist, steht beim Gegenstand, nicht in einer Liste daneben.

### Vorschlag

1. **Code-Version in jedes Lauf-Manifest** — Git-Commit und ob der
   Arbeitsbaum sauber war. Billig, automatisch, beantwortet Frage 1.
2. **Vertragsversion für jede Quelle**, nicht nur Detroit. Eine Konstante je
   Pipeline, die erhöht wird, wenn sich ändert, *was* geladen wird —
   Zeitfenster, Feldauswahl, Dedup-Regel, Wasserzeichen-Logik. Nicht, wenn
   sich ändert, *wie* der Code es tut.
3. **Ein Wächter**: Wird eine Vertragsversion erhöht, muss ein Eintrag in
   `AENDERUNGEN.md` sie nennen. Sonst steht in einem Jahr eine 3 im Manifest,
   und niemand weiss mehr, wofür.
4. **Dieselbe Angabe für Silver und Gold** — dort heisst sie
   Transformationsversion und ändert sich, wenn sich eine Deutung ändert (das
   Tatkorn, das Fallkorn, die Mehrheitsregel).

Punkt 3 ist der, den ich am wenigsten weglassen würde. Eine Versionsnummer
ohne Begründung ist schlimmer als keine: Sie sieht nach Ordnung aus.

### Woran es sich beweisen muss

Der ehrliche Test ist nicht, ob das Feld im Manifest steht, sondern ob diese
Frage beantwortbar wird:

> „Die Zahl auf Folie 7 stammt vom 8.9. Wurde sie mit derselben Logik geladen
> wie die von heute — und wenn nein, wo genau ist der Unterschied?"

Heute: nein, nur über die Git-Historie und Kopfrechnen. Mit 1 und 2: ja, durch
Vergleich zweier Manifeste.

---

## 3 · Skalieren

Ausgangswert, gemessen am 13.9.2026: **Silver, Gold und Serving zusammen
23,1 Sekunden** für 347'957 Zeilen. Raw 89 MB, Bronze 89 MB, Silver 47 MB,
Gold 14 MB.

### Drei Achsen, ungleich schwer

| Achse | Schwierigkeit | Warum |
| --- | --- | --- |
| Mehr Zeilen | leicht | DuckDB rechnet 20 Mio Zeilen auf einem Laptop |
| Mehr Jahrgänge | mittel | `DEFAULT_VINTAGE = 2024` an fünf Stellen |
| **Mehr Städte** | **schwer** | zwei handgeschriebene CTEs in der Silver-Abfrage |

### Was zuerst bricht — und es ist nicht die Engine

1. **Der Vollneubau.** Silver und Gold werden bei jedem Lauf **ganz** neu
   gebaut. Bei zehn Städten und zehn Jahren baut man jedes Mal 20 Millionen
   Zeilen neu — auch die neun Städte, die sich nicht bewegt haben. Das ist
   der erste echte Schmerz, und er kommt lange vor jeder Speichergrenze.
2. **Der räumliche Join.** Schon heute die empfindlichste Stelle; im Code
   steht, dass ein `LEFT JOIN` DuckDB in eine verschachtelte Schleife zwingt
   und der Lauf dann nicht mehr endet. Heute 348'000 Punkte gegen 6'282
   Polygone. Bei 50 Städten: Millionen gegen Zehntausende (die USA haben rund
   85'000 Tracts). Muss nach Bundesstaat partitioniert werden — ein Punkt in
   Illinois kann nie in einem Michigan-Tract liegen, aber der Join weiss das
   nicht.
3. **Der Speicher.** Kein `memory_limit`, keine `threads`-Einstellung. Auf
   einem eigenen Rechner gut, auf einem CI-Runner mit 7 GB ab einigen
   Millionen Zeilen Glückssache.
4. **Erst danach die Datenmenge selbst** — ~135 Byte je Silver-Zeile, also
   ~2,7 GB bei 20 Millionen. Für S3 nichts.

### Die konkreten Bremsen

| Stelle | Was klemmt | Aufwand |
| --- | --- | --- |
| `build_crime_offense.build_query()` | zwei handgeschriebene CTEs; 30 bzw. 39 Erwähnungen der beiden Städte im Modul | **gross** |
| `STUDIENSTAEDTE` | **doppelt definiert** — `gold_pipeline/__init__.py` klein, `build_place.py` gross geschrieben | klein, aber jetzt fällig |
| `DEFAULT_VINTAGE` | an fünf Stellen, plus `DEFAULT_YEAR` | mittel |
| räumlicher Join | eine Relation über alle Tracts | mittel |
| DuckDB-Einstellungen | keine Grenzen gesetzt | klein |

Die zwei CTEs sind **nicht** schlecht gebaut: Chicago und Detroit
unterscheiden sich echt — Socrata gegen ArcGIS, IUCR gegen MICR, Ortszeit
ohne Zone gegen Epoch-Millisekunden, ein Delikt je Zeile gegen Anklagen. Für
zwei Städte war das die ehrliche Lösung. Für zehn ist es keine.

Der Ausweg ist nicht „noch eine CTE", sondern ein **Quellprofil**: eine
Datenstruktur je Stadt mit Leser, Zeitzone, Crosswalk, Spaltenzuordnung und
Kornregel; die Abfrage wird aus einer Liste solcher Profile erzeugt. Danach
ist eine dritte Socrata-Stadt mit IUCR eine Konfigurationszeile statt
SQL-Arbeit.

### Der Umbau, der am meisten brächte

**Silver und Gold nach `city=` und `year=` partitionieren und nur neu bauen,
was sich bewegt hat.** Die halbe Maschinerie existiert: `pipeline_run.json`
trägt einen `input_fingerprint` über alle Bronze-Läufe. Derselbe Gedanke je
Partition beantwortet „muss ich das neu bauen?" ohne neuen Mechanismus.

Das ist der Unterschied zwischen Laufzeit proportional zum **Gesamtbestand**
und proportional zur **Änderung** — und er hängt an keiner Cloud.

---

## 4 · In die Cloud

### Was schon getan ist

Der Storage-Umbau vom 13.9. hat den schwierigen Teil erledigt: **Keine
Pipeline weiss mehr, wo die Daten liegen** ([`storage-architektur.md`](storage-architektur.md)).
Das ist die Entkopplung, die man sonst *vor* einem Umzug nachrüsten muss.

Der Wechsel von SeaweedFS zu AWS S3, MinIO oder GCS wäre heute **fast** eine
Zeile in `.env`. Fast: `region_name="us-east-1"` und
`addressing_style="path"` sind im S3-Client fest verdrahtet. SeaweedFS
braucht Path-Style, AWS bevorzugt Virtual-Hosted. Zwei Konfigurationsfelder,
ein Abend — kein Umbau.

### Der Ablauf in vier Stufen

| Stufe | Was passiert | Aufwand | Gewinn |
| --- | --- | --- | --- |
| **0 — heute** | Laptop + GitHub Actions wöchentlich, SeaweedFS als gemeinsamer Speicher | — | — |
| **1 — Lift** | ein Container, `STORAGE_BACKEND=s3`, Secrets aus dem Secret Manager, Scheduler; `run_all` als **ein** Job | Dockerfile, Registry, Job, Secrets | läuft ohne eigenen Rechner |
| **2 — Stufen trennen** | jede Stufe ein Task, Abhängigkeiten als DAG | Stufenliste exportieren statt selbst fahren | parallele Ingestion, Wiederaufnahme, Ressourcen je Stufe |
| **3 — Engine tauschen** | DuckDB → Athena / BigQuery / Spark | gross | echte horizontale Skalierung |

Stufe 2 ist billiger, als sie aussieht: `run_all` hat die Stufen bereits als
Datenstruktur (`STUFEN` mit Gruppe, Name, Modul, Argumenten) und kennt die
Reihenfolge. Die Abhängigkeiten sind schon explizit.

**Stufe 3 ist die teure.** Hier zahlt sich die Formatwahl aus: Parquet mit
Hive-Partitionen ist genau das, was Athena, BigQuery und Spark erwarten — die
**Dateien** müssten nicht angefasst werden. Was nicht mitkommt, ist das SQL:
fünfmal `ST_GeomFromWKB`, dazu `ST_Within`, `ST_Point` aus der
`spatial`-Extension und `epoch_ms`/`timezone()` aus `icu`. Jede Zielplattform
hat Entsprechungen, keine hat dieselben Namen.

### Was konkret nötig wäre

- Container-Image mit gepinnten Abhängigkeiten — `requirements.lock` gibt es
- Secret-Verwaltung statt `.env` (die Umgebung schlägt `.env` bereits)
- Scheduler statt des Cron in `datenlauf.yml`
- Bucket mit Lifecycle-Regeln — `aufraeumen` räumt bisher nur lokal
- IAM statt geteilter Schlüssel; heute darf jeder mit den Schlüsseln alles
- **Alarmierung** — steht als Lücke in Konzept 9. Ohne jemanden, der auf
  *Actions* schaut, ist das in der Cloud keine Lücke mehr, sondern ein Loch
- Kosten: bei 251 MB und einem Lauf pro Woche Rappen; Treiber wäre Compute

### Die ehrliche Einordnung

Bei 350'000 Zeilen und 23 Sekunden beantwortet „Cloud" **keine Frage, die wir
haben**. Das ist kein Argument dagegen — es ist eines dafür, den Schritt als
Lernzweck zu deklarieren statt als Notwendigkeit. Eine Arbeit, die sagt *„wir
haben gemessen, dass wir es nicht brauchen, und hier ist der Pfad, falls
doch"*, ist stärker als ein Architekturdiagramm ohne Zahlen.

---

## 5 · Reihenfolge

Nach Nutzen je Aufwand, nicht nach Reiz:

| | Was | Warum zuerst |
| --- | --- | --- |
| **1** | Gold nennt die Identität des Silver-Stands; Crosswalks mit Hash (1·A) | schliesst die Lineage-Kette; klein |
| **2** | Code-Version und Vertragsversion in jedes Manifest (2) | beantwortet „ab wann anders geladen" — und es gibt ein Vorbild |
| **3** | Gepinnte Läufe, die das Aufräumen überleben (1·B) | macht aus „erklärbar" ein „reproduzierbar" |
| **4** | `STUDIENSTAEDTE`-Duplikat zusammenführen | fünf Minuten; kostet sonst bei Stadt drei einen halben Tag |
| **5** | Quellprofil statt zwei CTEs | der einzige echte Blocker für eine dritte Stadt |
| **6** | Partitioniertes Silver mit Fingerabdruck je Partition | linear → konstant; unabhängig von Infrastruktur |
| **7** | Cloud Stufe 1 | danach ein Nachmittag, kein Projekt |

Die Punkte 1 bis 3 sind Artans, sie sind zusammen überschaubar, und sie
betreffen etwas, das **heute schon** unvollständig ist — nicht erst bei
zehnfachem Volumen. Deshalb stehen sie oben.
