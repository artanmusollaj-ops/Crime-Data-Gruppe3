# Ausblick: Lineage, Versionierung, Skalierung, Cloud

Material für den zweiten Leistungsnachweis und darüber hinaus. Dieses
Dokument ist **kein Konzept** — es analysiert, was heute trägt und wo es
aufhört, damit die Entscheidungen später auf Zahlen stehen und nicht auf
Gefühl. Was davon in ein Konzept gehört, entscheidet sich beim Schreiben.

Zwei der vier Themen kommen von **Artan** (14.9.2026) und stehen deshalb
vorn.

| Thema | Kommt von | Dringlichkeit |
| --- | --- | --- |
| [1 · Stichtagskonsistenz und Lineage](#1--stichtagskonsistenz-und-lineage) | Artan | **Stufe A und B erledigt am 14.9.** (#77, #79); C offen |
| [2 · Die Ladelogik versionieren](#2--die-ladelogik-versionieren) | Artan | **erledigt am 14.9.** (#78) |
| [3 · Skalieren](#3--skalieren) | Gedankenspiel | mittel — erst relevant ab Stadt drei |
| [4 · In die Cloud](#4--in-die-cloud) | Gedankenspiel | niedrig — technisch fast vorbereitet, fachlich unnötig |
| [5 · Die Analyseplattform](#5--die-analyseplattform) | Christian | **hoch** — LN2 im Dezember |

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
| Silver → Crosswalk | ~~ein **Pfad**~~ → Pfad **und SHA-256** | **ja, seit 14.9.** |
| Silver → `silver/tract` | ~~ein **Pfad**~~ → Referenz mit Zeitpunkt und Abdruck | **ja, seit 14.9.** |
| Gold → Silver | ~~nur ein **Pfad**~~ → Referenz samt Silvers eigener Herkunft | **ja, seit 14.9.** |
| Silver/Gold → Vorgängerstand | gar nichts | nein: es gibt keinen Verlauf (Stufe C) |

**Ein Pfad ist keine Version.** `data/silver/dataset=crime_offense/part-0001.parquet`
zeigt auf das, was gerade dort liegt. Wird Silver neu gebaut, zeigt derselbe
Satz im Gold-Manifest auf etwas anderes — und nichts am Manifest verrät es.
Genau das ist Artans Punkt: Zwischen „Werte vom Tag X" und „Bronze Load XY"
fehlt in der Mitte die Angabe, **welches** Silver gemeint war.

### Der billige Teil der Lösung — **gebaut am 14.9.2026**

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

**So sieht sie heute aus**, von einer Gold-Zahl aus gelesen:

```text
gold/fact_offense    input_fingerprint e7ec6a4a…
  ruht auf silver/crime_offense
      gebaut am      2026-09-14T11:37:57
      Eingabeabdruck 1608aec7…
      und das ruhte auf:
        Chicago  3 Läufe, erster run_20260905T174633859259Z
        Detroit  2 Läufe
        tract    gebaut 2026-09-14T11:37:56, Abdruck 215d02b2…
        iucr_nibrs_mapping.csv         ed36120081941cff…
        micr_nibrs_mapping.csv         b4a0099d868abffc…
        nibrs_offense_codes_2025.csv   6f650716c8992a38…
```

**Der Abdruck hängt nicht an Pfaden und nicht an der Uhrzeit.** Das fiel
beim Bauen auf: Die erste Fassung hashte die Herkunft mitsamt den absoluten
Pfaden — damit hätten Christian und Artan für **denselben** Stand
verschiedene Abdrücke bekommen, und die ganze Zusage wäre wertlos gewesen.
Gehasht wird deshalb nur das Kennzeichnende: Lauf-Kennungen, Prüfsummen und
die Abdrücke der Vorgänger (`manifeste.kennzeichen`).

### Der Konflikt, den niemand gesucht hat — **gelöst am 14.9.2026** (#79)

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

**Gebaut als Regel 0** in `orchestration.aufraeumen`, mit einem versionierten
Register `config/referenzstand.csv` — ein Referenzstand ist eine Verabredung
des Teams, kein Zustand eines Rechners.

**Und er wird abgeleitet, nicht getippt.** Das ist der Ertrag von Stufe A:
Weil ein Gold-Manifest seine Silver-Quelle samt deren Herkunft nennt, stehen
die Bronze-Läufe darin. `--pinnen` liest sie heraus:

```bash
$ python -m orchestration.aufraeumen --pinnen LN1
9 Lauf/Laeufe als 'LN1' festgehalten in config/referenzstand.csv
$ python -m orchestration.aufraeumen
  1d879a0e-2398-4dcb-b59f-6218   88'685 Zeilen   27.2 MB  Referenzstand
  run_20260907T181228996304Z     55'445 Zeilen   24.5 MB  vorheriger Schnappschuss
```

Neun Läufe über alle fünf Quellen — genau die, auf denen die veröffentlichten
Zahlen ruhen. Der NOAA-Lauf vom 7.9. ist **nicht** dabei: Silver nimmt den
jüngsten, also ruht keine Zahl auf ihm.

### In drei Stufen

| Stufe | Was | Aufwand | Was man danach kann |
| --- | --- | --- | --- |
| ~~**A**~~ | ~~Gold nennt die Identität des Silver-Stands; Crosswalks mit Hash~~ — **erledigt 14.9.2026 (#77)** | klein | jede heutige Zahl vollständig **erklären** |
| ~~**B**~~ | ~~Gepinnte Läufe, die das Aufräumen überleben~~ — **erledigt 14.9.2026 (#79)** | klein | jede gepinnte Zahl **reproduzieren** |
| **C** | Silver und Gold versioniert ablegen (`vintage=`/`asof=`), statt zu ersetzen | mittel–gross | **mehrere** Stände nebeneinander halten und vergleichen |

Stufe A und B sind gebaut und lösen Artans Punkt. **Stufe C ist ausdrücklich
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

### Es gab schon ein Vorbild — in Detroit

```json
"window_contract_version": 2,
"bronze_contract_version": 2,
"raw_contract_version": 1
```

Detroit machte bereits exakt das, was Artan vorschlägt — nur für Detroit, und
nur für diese drei Verträge. Die Zahl sprang auf 2, als der Zeitzonen-Fix
kam. **Das war kein Neubau, sondern ein Muster, das verallgemeinert gehörte —
und seit dem 14.9.2026 ist es das** (#78): Alle fünf Quellen und alle neun
abgeleiteten Tabellen tragen `contract_version`, dazu `code_version` mit
Git-Commit und der Angabe, ob der Arbeitsbaum sauber war.

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

### Umgesetzt am 14.9.2026 (#78)

1. **Code-Version in jedem Manifest** — `code_version` mit Git-Commit und
   `git_dirty`. Das zweite ist wichtiger, als es aussieht: Ein Lauf aus einem
   veränderten Arbeitsbaum lässt sich aus dem Commit allein **nicht**
   nachbauen; wer das später wissen will, findet es dort statt es zu vermuten.
   Ohne Git bleibt es bei `None` — ein Lauf darf daran nie scheitern.
2. **`contract_version` für jede Quelle**, nicht nur Detroit — und für jede
   abgeleitete Tabelle. Sie steigt, wenn sich ändert, *was* geladen oder
   gedeutet wird; nicht, *wie* der Code es tut.
3. **Der Wächter**: `tests/test_vertragsversionen.py` hält jede Zahl gegen
   das Register *Vertragsversionen* in `AENDERUNGEN.md`. Wer erhöht und das
   Register vergisst, fällt durch — mit der Meldung, was zu schreiben ist.
   Das war der Punkt, den ich am wenigsten weglassen wollte: Eine
   Versionsnummer ohne Begründung ist schlimmer als keine, sie sieht nach
   Ordnung aus.
4. **Version 1 bedeutet: der Vertrag, wie er am 14.9.2026 gilt.** Rückwirkend
   Nummern zu vergeben hätte eine Ordnung vorgetäuscht, die es damals nicht
   gab; frühere Änderungen stehen als Einträge in `AENDERUNGEN.md`. Detroit
   ist die Ausnahme — dort steht die 2 seit dem 11.9. in den Daten selbst.

### Woran es sich beweisen muss

Der ehrliche Test ist nicht, ob das Feld im Manifest steht, sondern ob diese
Frage beantwortbar wird:

> „Die Zahl auf Folie 7 stammt vom 8.9. Wurde sie mit derselben Logik geladen
> wie die von heute — und wenn nein, wo genau ist der Unterschied?"

Vor dem 14.9.: nein, nur über die Git-Historie und Kopfrechnen. Seither: ja,
durch Vergleich zweier Manifeste — `contract_version` sagt, ob die Bedeutung
eine andere ist, `code_version` sagt genau, welcher Code lief.

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
| ~~`STUDIENSTAEDTE`~~ | ~~**doppelt definiert**~~ — **zusammengeführt am 14.9.2026 (#82)**: Silver trägt den amtlichen Namen, Gold leitet `STADT_SCHLUESSEL` daraus ab | erledigt |
| `DEFAULT_VINTAGE` | an fünf Stellen, plus `DEFAULT_YEAR` | mittel |
| räumlicher Join | eine Relation über alle Tracts | mittel |
| DuckDB-Einstellungen | keine Grenzen gesetzt | klein |

Die zwei CTEs sind **nicht** schlecht gebaut: Chicago und Detroit
unterscheiden sich echt — Socrata gegen ArcGIS, IUCR gegen MICR, Ortszeit
ohne Zone gegen Epoch-Millisekunden, ein Delikt je Zeile gegen Anklagen. Für
zwei Städte war das die ehrliche Lösung. Für zehn ist es keine.

Der Ausweg ist nicht „noch eine CTE", sondern ein **Quellprofil**: eine
Datenstruktur je Stadt mit Leser, Zeitzone, Crosswalk, Spaltenzuordnung und
Regel zur Granularität; die Abfrage wird aus einer Liste solcher Profile erzeugt. Danach
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

## 5 · Die Analyseplattform

Für den zweiten Leistungsnachweis. Die Anforderung steht seit dem 13.9.:
Tag, Monat und Jahr wählbar, beide Städte gegeneinander **und** einzeln, das
Stadtgebiet mit seinen Tracts eingefärbt nach Filter.

### Die Zahlen, an denen die Werkzeugfrage hängt

Gemessen am 14.9.2026 auf `gold/fact_offense` (344'617 Zeilen, 14,8 MB),
ohne Index, ohne Vorberechnung:

| Abfrage, wie ein Dashboard sie stellt | Zeit |
| --- | ---: |
| Karte: Tract × Monat, auf einen Monat gefiltert | **2 ms** |
| Zeitreihe beider Städte über ein Jahr | **2 ms** |
| Rate je Tract, mit Einwohnern als Nenner | **7 ms** |

Ein Mensch klickt einen Filter und erwartet eine Antwort unter etwa 200 ms.
Wir haben das Hundertfache an Luft — auf der **rohen** Faktentabelle, ohne
Server.

### Streamlit, ClickHouse, OpenSearch

| | Wofür gebaut | Wann es richtig wird | Hier |
| --- | --- | --- | --- |
| **Streamlit** | Python-Oberflächen für wenige Nutzer | sofort, bei 1–20 Nutzern | **passt** |
| **ClickHouse** | Milliarden Zeilen, viele gleichzeitige Abfragen | ab ~50–100 Mio Zeilen oder vielen parallelen Nutzern | ~1000× zu gross |
| **OpenSearch** | Volltext, Exploration ohne festes Schema | wenn die Frage *„finde alles mit dem Wort X"* lautet | falsche **Form** |

**ClickHouse** ist keine Stufe, in die wir hineinwachsen. Zehn Städte über
zehn Jahre wären rund 20 Mio Zeilen — das rechnet DuckDB auf einem Laptop
weiterhin interaktiv. Erst bei etwa fünfzig Städten über zwanzig Jahre, oder
wenn zwanzig Leute gleichzeitig schwere Aggregationen fahren, lohnt sich der
Serverbetrieb.

**OpenSearch** ist die falsche Form, nicht die falsche Grösse: Unsere Fragen
sind Aggregationen über ein Sternschema, und das ist SQLs Heimat. Der eine
Fall, in dem es gepasst hätte, war Artans Fund über die
`offense_description` (eine Larceny-Zeile mit CSC-Text) — eine einmalige
Untersuchung, keine Plattformanforderung. Dafür genügt eine Abfrage auf
`analyse.duckdb`.

### Kein Würfel — zum zweiten Mal gemessen

Ein erster Entwurf sah eine vorberechnete Datei für das Dashboard vor
(Tract × Tag × Deliktfamilie). Christian hat eingewandt, das sei der Würfel,
den das Projekt schon einmal verworfen hat. Die Messung gibt ihm recht:

| | Zeilen |
| --- | ---: |
| Granularität `fact_offense` | 344'617 |
| Aggregat Tract × Tag × Familie | 296'651 — **86 %** davon |

**14 % weniger Zeilen ist keine Aggregation.** Die scheinbare Ersparnis
(0,73 statt 14,8 MB) kam fast vollständig daher, dass Spalten wegfielen —
nicht Zeilen. Und genau das leistet Parquet von selbst:

```text
Eine Kartenabfrage liest 4 Spalten:   0,69 MB   =  5 % der Datei
Das materialisierte Aggregat:         0,73 MB
```

Das Aggregat wäre **grösser gewesen als die Spaltenauswahl, die ohnehin
kostenlos ist** — und hätte dafür jede Dimension weggeworfen, die niemand
vorher festgelegt hat. Dazu kommen Row Groups mit Min/Max je Spalte, über
die ein Zeitfilter ganze Blöcke überspringt.

**Das Format ist der Würfel** — einer, den niemand vorab entscheiden muss.

Und der Wunsch nach *dynamischen* Ansichten ist das stärkste Argument
dagegen, nicht dafür: Ein Würfel legt Dimensionen und Granularität vorab
fest. Wer danach nach `arrest`, `mapping_status`, Tageszeit oder
`geo_status` filtern will, findet sie dort nicht; in der Faktentabelle
schon. Die Umschaltung zwischen Tat- und Fallebene wären im Würfel zwei
Würfel.

Damit bestätigt sich, was Konzept 5.2 als Zusage führt — dort noch mit dem
alten Wort *Granularität*, siehe die Anmerkung zur Begriffswahl unten: *„Keine
vorberechneten Aggregate. Gold behält die Granularität — eine Zeile je Tat, mit
Zeitpunkt und Koordinate. Aggregiert wird in der Abfrage, nicht im
Speicher."* Dieselbe Messung hatte schon `fact_tract_month` (95'219) und
`fact_city_day` (11'156) verworfen.

> **Zur Begriffswahl.** Dieser Abschnitt sagt **Granularität**, wo das
> übrige Projekt bislang *Granularität* sagt, und **Tat-/Fallebene** statt
> *Tatebene/Fallebene*. „Granularität" ist der eingeführte deutsche Begriff
> für Kimballs *grain*; „Granularität" ist eine wörtliche Übersetzung, die im
> deutschen Data Engineering unüblich ist. Christian hat das am 14.9.
> angemerkt. Der Begriff kommt an 128 Stellen in 27 Dateien vor — die
> Umstellung ist ein eigener Schritt und steht in der Reihenfolge unten.

### Die eigentliche Schwierigkeit ist nicht die Menge

Sie ist die **Bedeutung**. Jede angezeigte Zahl trägt eine Entscheidung, die
dieses Projekt bewusst sichtbar gemacht hat:

- **Welche Granularität?** Detroit steht auf Tatebene bei 132,6 je 1'000,
  auf Fallebene bei 124,6. Beide richtig, verschiedene Aussagen.
- **Was zählt mit?** `geo_status` sagt, warum eine Zeile in einer
  Tract-Auswertung fehlt — 6'445 Fälle liegen ausserhalb, 0,58 % haben
  keine Koordinate.
- **Wie sicher ist die Zuordnung?** `mapping_status`: `exact`, `ambiguous`,
  `fallback_90Z`.
- **Absolut oder je Einwohner?** Absolut liegt Chicago fast überall vorn, je
  Einwohner Detroit.
- **Die Mehrheitsregel** untertreibt Chicagos Rate um gut einen Punkt (94,5
  statt 95,6).

Ein Dashboard, das eine dieser Entscheidungen still trifft und eine Zahl
hinstellt, macht die Arbeit dieses Projekts zunichte. Daraus folgen drei
Grundsätze:

1. **Die Granularität ist ein Schalter, keine Annahme.** Tat- oder Fallebene
   gehört sichtbar in die Kopfzeile, nicht in eine Fussnote.
2. **Jede Kennzahl nennt ihren Nenner und ihre Ausschlüsse.** *„94,5 je
   1'000 — von 251'516 Delikten in Tracts der Stadt; 1'753 ohne Koordinate
   nicht enthalten."*
3. **Was fehlt, wird gezeigt, nicht weggelassen.** Ein Tract ohne Einwohner
   bekommt keine Rate, sondern eine eigene Farbe. Sonst liest jemand die
   Null als Sicherheit.

Das spricht **gegen** ein fertiges BI-Werkzeug: Metabase oder Superset
stellen gern eine Zahl ohne Fussnote hin.

### Zwei Bauarten

| | Woher gelesen wird | Bewertung |
| --- | --- | --- |
| **A · Streamlit** (serverseitig) | DuckDB direkt auf `fact_offense` und `dim_tract`, lokal oder `s3://` | Vorschlag für LN2: an einem Wochenende lauffähig, passt zu unseren Fähigkeiten |
| **B · Statische Seite** (DuckDB-WASM) | dieselben Parquet-Dateien über HTTP-Range-Requests, nur die gebrauchten Spalten | eleganter — kein Server, erfüllt Anforderung 5 aus 7.1 wörtlich; aber neu für uns |

In **beiden** Fällen: keine neue Datei, keine neue Schicht. Die
Serving-Schicht bekommt allenfalls eine *Sicht* in `analyse.duckdb` — einen
Namen, keine Daten.

Die Karte ist gelöst: 1'055 Tract-Umrisse liegen als GeoJSON mit 0,55 MB
bereit, auf rund 2 m vereinfacht. Die Geometrie geht **einmal** an den
Browser, bei jedem Filterwechsel nur noch ein Wert je `geoid`. Die Geometrie
ist das Schwere — und sie ändert sich nie.

Eine ehrliche Grenze: Die Faktentabelle hat nur **drei Row Groups**, das
Überspringen per Zeitfilter ist also grob. Bei 2 ms ist das gleichgültig;
falls es je zählt, wäre der Hebel „nach Datum sortiert schreiben, mehr Row
Groups" — und immer noch kein Würfel.

### Was zu entscheiden ist, und es ist nicht technisch

Drei Fragen für die Absprache, die den Aufbau stärker bestimmen als jedes
Werkzeug:

1. Welche Granularität ist die **Hauptaussage** — Tat oder Fall?
2. Absolute Zahlen oder Raten als Voreinstellung?
3. Erzählt das Dashboard eine **Geschichte** (kuratiert) oder lässt es
   **erkunden** (Filter über alles)?

---

## 6 · Reihenfolge

Nach Nutzen je Aufwand, nicht nach Reiz:

| | Was | Warum zuerst |
| --- | --- | --- |
| ~~**1**~~ | ~~Gold nennt die Identität des Silver-Stands; Crosswalks mit Hash (1·A)~~ — **erledigt 14.9.2026** | schliesst die Lineage-Kette; klein |
| ~~**2**~~ | ~~Code-Version und Vertragsversion in jedes Manifest (2)~~ — **erledigt 14.9.2026** | beantwortet, ab wann anders geladen wurde |
| ~~**3**~~ | ~~Gepinnte Läufe, die das Aufräumen überleben (1·B)~~ — **erledigt 14.9.2026** | macht aus erklärbar ein reproduzierbar |
| ~~**4**~~ | ~~`STUDIENSTAEDTE`-Duplikat zusammenführen~~ — **erledigt 14.9.2026** | fünf Minuten; kostet sonst bei Stadt drei einen halben Tag |
| **5** | Quellprofil statt zwei CTEs | der einzige echte Blocker für eine dritte Stadt |
| **6** | Partitioniertes Silver mit Fingerabdruck je Partition | linear → konstant; unabhängig von Infrastruktur |
| **7** | Cloud Stufe 1 | danach ein Nachmittag, kein Projekt |
| **8** | *Granularität* → *Granularität* durchgehend (128 Stellen, 27 Dateien) | der eingeführte Begriff; betrifft auch Artans Dokumente |
| **8** | Dashboard für LN2 (Abschnitt 5) | eigener Zeitplan — Dezember |

Die Punkte 1 bis 3 sind Artans, sie sind zusammen überschaubar, und sie
betreffen etwas, das **heute schon** unvollständig ist — nicht erst bei
zehnfachem Volumen. Deshalb stehen sie oben.
