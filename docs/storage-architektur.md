# Die Datenablage: lokal, SeaweedFS oder beides

Wo die Schichten `raw`, `bronze`, `silver`, `gold` und `serving` liegen, ist
seit dem 13.9.2026 eine Einstellung und keine Eigenschaft des Codes mehr.
Dieses Dokument beschreibt, wie das gebaut ist, was es zusichert und was es
bewusst **nicht** tut.

Kurzfassung für Eilige:

```text
Hybrid READ:    lokal zuerst, S3 als Rückfall
Hybrid WRITE:   lokal, prüfen, dann gezielt nach S3 publizieren
Serving DuckDB: immer lokal
```

Die Bedienung steht in [`README.md`](../README.md), Abschnitt 2.5. Die
Einordnung in den Lebenszyklus in [`ln2_konzept.md`](ln2_konzept.md),
Kapitel 7.4. Hier steht das Wie und das Warum.

---

## 1 · Das Problem, das es löst

`data/` ist vollständig aus der Versionierung ausgeschlossen — allein Chicago
und Census belegen rund 70 MB, und ein Repository ist kein Datenspeicher. Die
Folge: **Jeder lud selbst.** Damit hatte jeder eigene `run_id`s, und durch
Chicagos Delta-Logik andere Zeilen. Zwei Leute, zwei Zahlen, und keine
Möglichkeit zu sagen, welche gilt.

Absprache 7.1 hielt das als offene Frage fest: *„Wie kommen wir zum gleichen
Datenstand?"* Der Vorschlag damals war ein verabredeter Referenzstand auf dem
Papier. Was fehlte, war ein **Ort**.

Den gibt es jetzt: ein SeaweedFS, angesprochen über die S3-Schnittstelle. Er
trägt den **veröffentlichten** Bestand. Das lokale `data/` bleibt, was es war
— Arbeitskopie und Zwischenstand.

```text
                    SeaweedFS
             der veröffentlichte Stand
                        ▲
                        │  publish (nur nach bestandener Prüfung)
                        │
                 lokale Pipeline
                        │
                     DuckDB
```

Lesen darf aus beiden Richtungen. Publiziert wird kontrolliert, in eine
Richtung.

---

## 2 · Der Kern: ein relativer Ablagepfad

Alles Persistierte wird intern **relativ** adressiert:

```text
bronze/city=chicago/ingest_date=2026-09-13/run_abc/part-0001.parquet
```

Daraus macht die Ablage, je nach Modus:

| Modus | Ergebnis |
| --- | --- |
| `local` | `data/bronze/city=chicago/…/part-0001.parquet` |
| `s3` | `s3://urban-crime/bronze/city=chicago/…/part-0001.parquet` |
| `hybrid` | `data/…`, wenn die Datei da ist — sonst `s3://urban-crime/…` |

**Die Struktur unter der Wurzel ist in allen Modi dieselbe.** Partitionen,
Laufverzeichnisse, `part-0001.parquet`, `manifest.json` — nichts daran ändert
sich, und nichts daran darf sich ändern: Ein Bestand, der lokal gebaut wurde,
muss auf SeaweedFS ohne Umrechnung lesbar sein und umgekehrt.

Was ein Ablagepfad **nicht** sein darf, prüft `storage.paths.relativ()`:
absolute Pfade, Laufwerksbuchstaben und `..` werden abgewiesen. Backslashes
aus Windows werden zu Schrägstrichen — die Adresse ist immer POSIX.

---

## 3 · Die drei Modi

### `local` — der Ausgangszustand

Lesen und Schreiben ausschliesslich unter `LOCAL_DATA_ROOT` (Vorgabe `data`).
Das Verhalten entspricht dem Projekt vor dem Umbau, Zeile für Zeile. `boto3`
wird nie importiert, kein Netzzugriff findet statt, keine S3-Variable wird
gelesen.

Das ist die **Vorgabe**. Wer nichts konfiguriert, arbeitet so.

### `hybrid` — der Modus für die Zusammenarbeit

```text
LESEN                          SCHREIBEN

  angefragte Datei               Transformation
        │                              │
        ▼                              ▼
  lokal vorhanden?               lokales Ergebnis
    ╱        ╲                         │
  ja          nein                     ▼
   │            │                  Validierung
   ▼            ▼                   ╱       ╲
 lokal      SeaweedFS          scheitert    gelingt
                                   │           │
                                   ▼           ▼
                                Abbruch    publish
                                              │
                                              ▼
                                          SeaweedFS
```

Das lokale Verzeichnis ist damit ein **Working Set**: Was da ist, wird
benutzt; was fehlt, kommt vom gemeinsamen Bestand. Niemand muss vorher
synchronisieren.

### `s3` — ohne lokalen Bestand

Gelesen wird immer von SeaweedFS. Geschrieben wird trotzdem zuerst lokal —
die Pipelines brauchen ein Arbeitsverzeichnis für `.part`-Ordner und das
atomare Umbenennen, und die Prüfungen laufen auf dem fertigen lokalen
Ergebnis. Nach dem Publizieren wird die lokale Kopie entfernt. Es bleibt also
kein lokaler Bestand zurück, und es muss keiner vorhanden sein.

---

## 4 · Konfiguration: was wann nötig ist

Alles kommt aus der Umgebung oder aus `.env` im Projekt-Root. **Die Umgebung
schlägt `.env`** — so kann CI Secrets setzen, ohne dass eine mitgebrachte
Datei dazwischenfunkt. `.env` ist über `.gitignore` ausgeschlossen und wird
nie committet.

| Variable | Vorgabe | `local` | `hybrid` | `s3` |
| --- | --- | :---: | :---: | :---: |
| `STORAGE_BACKEND` | `local` | — | **nötig** | **nötig** |
| `LOCAL_DATA_ROOT` | `data` | optional | optional | optional |
| `S3_ENDPOINT` | `s3.datenwerft.ch` | — | optional | optional |
| `S3_ACCESS_KEY` | — | — | **nötig** | **nötig** |
| `S3_SECRET_KEY` | — | — | **nötig** | **nötig** |
| `S3_BUCKET` | `urban-crime` | — | optional | optional |
| `S3_USE_SSL` | `true` | — | optional | optional |
| `HYBRID_READ_PRIORITY` | `local` | — | optional | — |
| `HYBRID_PUBLISH_AFTER_WRITE` | `true` | — | optional | — |
| `STORAGE_KEEP_LOCAL` | `false` | — | — | **wird je Lauf gesetzt** |

**Wer lokal arbeitet, füllt nichts davon aus.** Keine der S3-Variablen wird
gelesen, `STORAGE_BACKEND` selbst kann fehlen — `local` ist die Vorgabe. Eine
`.env` braucht es nur für `CENSUS_API_KEY` (Ingestion) und optional
`SOCRATA_APP_TOKEN`.

Zwei Einstellungen sind absichtlich eng gehalten:

* **`HYBRID_READ_PRIORITY`** kennt nur `local`. Ein `s3` als Lesepriorität
  wäre ein zweites Verhalten mit eigenen Überraschungen; solange es niemand
  braucht, gibt es nur eines. Ein anderer Wert ist ein Fehler, kein stilles
  Umschalten.
* **`HYBRID_PUBLISH_AFTER_WRITE=false`** baut lokal weiter, publiziert aber
  nichts. Nützlich, wenn jemand einen Zwischenstand bauen will, ohne ihn für
  alle zu setzen.

Fehlt ein Schlüssel im Modus `hybrid` oder `s3`, sagt das die Konfiguration
sofort und nennt die Variable — nicht erst die fünfte Pipeline-Stufe.

---

## 5 · Lesen

`resolve_read_path(*teile)` liefert die Zeichenkette, die `read_parquet()`
lesen soll — lokal ein Dateipfad, entfernt eine `s3://`-URL. Der aufrufende
Code weiss nicht, welches von beidem er bekommt, und soll es nicht wissen.

```python
pfad = storage.resolve_read_path("silver", "dataset=crime_offense", "part-0001.parquet")
con.execute(f"SELECT count(*) FROM read_parquet('{pfad}')")
```

Für Verzeichnisse und Suchen gilt dasselbe:

* **`list_files(prefix, muster)`** vereinigt lokal und entfernt; bei gleichem
  Pfad gewinnt lokal. Das Muster folgt `Path.glob` — `**/` deckt auch null
  Ebenen ab, `*` bleibt in seiner Ebene.
* **`laeufe(prefix, muster)`** liefert die **fertigen** Läufe, ebenfalls
  vereinigt. Ein Lauf, dessen Manifest nicht `complete`/`SUCCESS` sagt, zählt
  nicht — auch dann nicht, wenn er lokal liegt und SeaweedFS einen fertigen
  hat. Es entscheidet die Manifest-Logik, nicht die Nähe.
* **`tabellen()`** liefert die gebauten Silver- und Gold-Tabellen.
* **`groessen_unter(prefix, muster)`** liefert dieselbe Auswahl wie
  `list_files`, aber als `{Ablagepfad: Bytes}` — lokal aus `st_size`, oben aus
  `Objekt.size`. **`bytes_unter(prefix, muster)`** ist deren Summe und damit
  die **eine** Byte-Summe des Projekts; ein Präfix, das es nicht gibt, ist
  dabei 0 Bytes und kein Fehler. `lokal=True` misst nur die Arbeitskopie,
  auch im `s3`-Modus, in dem die Ablage sonst gar nicht lokal liest — das
  fragen `aufraeumen` (was gibt das Löschen frei?) und
  `python -m storage publizieren` (was ist noch hochzuladen?).

Dass Läufe **vereinigt** werden, ist wichtig und nicht selbstverständlich:
Chicago lädt einen Vollschnappschuss und danach Deltas, und Silver liest
**alle**. Wer lokal einen eigenen Lauf hat und auf SeaweedFS zwei weitere,
bekommt alle drei. Läufe verdrängen einander nie — sie ergänzen sich.

---

## 5a · Holen: Raw, Bronze und Releases

Seit dem 17.9.2026. Die Regel „lesen, nicht kopieren" (Abschnitt 5) bleibt
für Silver und Gold. Für das Unveränderliche gilt sie nicht — eine Kopie
eines Laufs kann nicht veralten, und jeder Rechner soll den ganzen Bestand
haben:

* `Storage.hole(rel)` holt ein Objekt in die lokale Wurzel: in eine
  `.part`-Datei, verglichen (Grösse, dann MD5 gegen das ETag), dann umbenannt.
  Was lokal identisch liegt, wird nicht erneut geladen.
* `Storage.hole_lauf(rel_dir)` holt einen Lauf ganz, `manifest.json` zuletzt —
  wie beim Publizieren ist das Manifest das Zeichen, dass er ganz da ist.
* `Storage.fehlende_laeufe()` nennt, was oben liegt und lokal kein Manifest
  hat; `hole_fehlende_laeufe()` holt es, Raw vor Bronze.
* `storage.release.hole()` holt ein Release — `release.json` zuerst, dann
  jede Datei gegen ihre SHA-256; `--nur-datenbank` allein die
  `analyse.duckdb`; `einsetzen()` setzt die Tabellen unteilbar an die festen
  Pfade.

Der Gesamtlauf holt in jedem Modus mit S3 zuerst alle fehlenden Raw- und
Bronze-Läufe; scheitert das, läuft nichts weiter (`--ohne-holen` schaltet es
ab). Von Hand: `python -m storage holen [--wirklich]` und
`python -m orchestration.release holen [KENNUNG|aktuell] [--nur-datenbank]
[--einsetzen]`.

---

## 6 · Schreiben und Publizieren

Gebaut wird immer lokal, mit `.part`-Verzeichnis und atomarem Umbenennen wie
bisher. Publiziert wird **danach**, gezielt, und nur, was die bestehenden
Prüfungen bestanden hat:

```text
  Ingestion            Silver / Gold
      │                      │
  Download               Transformation
      │                      │
  Vollständigkeits-      reconcile,
  nachweis               Publish-Gate
      │                      │
  atomar umbenennen      atomar ersetzen
      │                      │
      └──────────┬───────────┘
                 ▼
         publish_run / publish_table
                 ▼
     Datendateien zuerst, manifest.json ZULETZT
```

**Warum das Manifest zuletzt geht:** Es ist oben dasselbe Signal wie das
Umbenennen lokal. Liegt `manifest.json` auf SeaweedFS, ist der Lauf
vollständig dort. Bricht ein Upload in der Mitte ab, fehlt das Manifest — und
alle Leser überspringen den Lauf, statt ihn halb zu lesen.

Publiziert wird **je Lauf oder je Tabelle**, nicht als Verzeichnis-Sync. Ein
`rsync data/` wäre schneller zu schreiben und falsch: Er brächte auch
Halbfertiges, Verworfenes und Fremdes mit.

Nach jedem Upload wird das Objekt zurückgelesen: Existenz und Grösse immer,
die MD5-Prüfsumme gegen das ETag, wo der Dienst eines liefert. Ein Upload,
der nicht bestätigt ist, gilt nicht als erfolgt.

**Was oben schon liegt, wird einmal je Präfix aufgelistet** — seit dem
5.10.2026. Bis dahin fragte `publish_files` je Datei mit einem `HEAD`, ob dort
schon etwas liegt. Beim Publizieren der sechs Jahrgänge waren das 446
Anfragen in Folge, und der Endpunkt drosselte 350 davon: Unter dichter
Anfragefolge antwortet er auf einen **fehlenden** Schlüssel mit `403` statt
`404`. Gemessen — 120 Anfragen in 8,5 s ergaben 120 × `403`, derselbe
fehlende Schlüssel einzeln abgefragt `403` einmal und `404` viermal. `403`
gilt als vorübergehend, also holte die Wiederholung nach einer Sekunde das
ehrliche `404`; das Ergebnis stimmte, der Upload dauerte doppelt so lang.

Ein `list` beantwortet dieselbe Frage für alle Dateien eines Verzeichnisses:
Es nennt je Objekt Schlüssel, Grösse und ETag — und genau das, nicht mehr,
braucht der Vergleich. Je **Präfix**, nicht einmal für alles: Ein Release
trägt Dateien unter `gold/dataset=…` und `serving/dataset=…`, und ein `list`
auf den gemeinsamen Stamm brächte jedes andere Release mit.

Jede Entscheidung bleibt dieselbe — identisch oben wird übersprungen,
abweichend oben ist ohne `ueberschreiben` ein Fehler, `manifest.json` geht
zuletzt hoch. Das `HEAD` **nach** dem Upload bleibt ebenso: Es ist keine
Vorabfrage, sondern die Bestätigung, und sie muss je Datei geschehen, bevor
das Manifest hochgeht. `tests/storage/test_backend.py` zählt die Anfragen
mit — ein `list` je Präfix, kein `HEAD` vorab.

Scheitert eine Anfrage wiederholbar, nennt die Warnung im Log den **Fehlercode**
und, wo boto3 einen mitgibt, den HTTP-Status (`403 (HTTP 403)`). Vorher stand
dort der Klassenname `ClientError`, und so heisst jeder abgelehnte Aufruf —
die Drosselung war daran nicht von einem fehlenden Schlüssel zu unterscheiden.

---

## 6a · Das Release: der ganze Stand unter einer Kennung

Seit dem 17.9.2026 (`storage.release`). Silver und Gold werden weiterhin je
Tabelle an festen Pfaden veröffentlicht — nacheinander, und zwischen zwei
Tabellen liegt ein Fenster mit gemischtem Stand. Wer einen **ganzen** Stand
braucht, liest ein Release:

```text
releases/release=2026-09-17T15-04-05Z/gold/dataset=fact_offense/...
releases/release=2026-09-17T15-04-05Z/serving/dataset=comparison_day/...
releases/release=2026-09-17T15-04-05Z/serving/analyse.duckdb     selbständig
releases/release=2026-09-17T15-04-05Z/serving/tracts.geojson
releases/release=2026-09-17T15-04-05Z/release.json               Prüfsummen
releases/AKTUELL.json                                             der Zeiger
```

Gebildet wird es lokal, vollständig oder gar nicht (`.part`, dann `rename`),
mit SHA-256 je Datei in `release.json`. Publiziert wird es **wie ein Lauf**:
unveränderlich, identisch oben übersprungen, anders oben ein Fehler;
`release.json` zuletzt, und erst danach wird `AKTUELL.json` ersetzt — ein
Objekt, dessen Ersetzung lokal wie auf S3 unteilbar ist. Alle Tabellen
wechseln gemeinsam; ein Abbruch an jeder Stelle lässt den alten Stand gültig.

| Modus | Holt Raw/Bronze vor dem Lauf | Release |
| --- | --- | --- |
| `local` | nein — es gibt kein S3 | nur mit `run_all --release`; bleibt lokal, `AKTUELL.json` lokal |
| `hybrid` | **ja**, was oben liegt und lokal fehlt | nach jedem grünen Gesamtlauf; lokal gebildet, hochgebracht, lokale Kopie bleibt |
| `s3` | nein — von Hand mit `python -m storage holen --wirklich` | wie `hybrid`, lokale Kopie danach entfernt |

Automatisch holt nur `hybrid`. `s3` ist als *ohne lokalen Bestand* definiert;
ein Lauf, der ihn füllte, widerspräche der eigenen Definition — dort liest
Silver Bronze direkt von S3. `tests/storage/test_modi.py` hält diese Matrix
fest.

### `STORAGE_KEEP_LOCAL` — warum „danach" eine Reihenfolge braucht

Die Release-Zeile sagt für `s3`: *lokal gebildet, hochgebracht, lokale Kopie
**danach** entfernt.* Bis zum 16.10.2026 stand das so im Dokument und anders
im Code: `publish_table` entfernte die Kopie sofort, und
`storage.release.sammle` liest das Dateisystem. Auf `srv01` scheiterte das
Release deshalb mit *„es fehlt: gold/dataset=fact_offense, …"* — bei einer
**grünen** Strecke. Sieben Tabellen, alle oben, keine unten.

`STORAGE_KEEP_LOCAL` setzt die Reihenfolge durch.
`orchestration.run_all` setzt die Variable für die abgeleiteten Stufen,
**wenn ein Release folgt**, und entfernt die Kopien danach in einem Zug
(`Storage.arbeitskopien_entfernen`). Zwei Grenzen gehören dazu:

* **Nur Tabellen, nie Läufe.** `publish_run` fragt den Schalter nicht. Ein
  Lauf ist unveränderlich und jederzeit wieder zu holen; ihn lokal zu
  behalten häuft nur an — 141 Bronze-Läufe waren der Grund, warum der
  Silver-Bau erstickte. Auch ein von Hand global gesetztes
  `STORAGE_KEEP_LOCAL` kann Raw und Bronze nicht lokal halten.
* **Entfernt wird nur, was oben liegt — und zwar dasselbe.**
  `arbeitskopien_entfernen` vergleicht je Tabelle beide Manifeste. Fehlt das
  entfernte, bleibt die Kopie: Sonst verschwände eine Tabelle, deren Upload
  scheiterte, und wäre nirgends mehr. **Weichen sie ab, bleibt sie auch.** Die
  erste Fassung fragte nur, *ob* oben etwas liegt, und löschte am 17.10.2026
  eine frisch gebaute `source_change`, deren Gegenstück oben vom 3.10. war —
  21,4 Mio. Zeilen, gebaut und verloren, weil `build_source_change` damals
  kein `publish_table` rief. Eine Unsicherheit (unlesbares JSON, Netzfehler)
  gilt als Abweichung und schützt die Kopie.
* **Gefragt werden nur Silver und Gold** (`Storage.PUBLIZIERTE_SCHICHTEN`).
  Keine Serving-Tabelle wird je einzeln publiziert: `build_comparison`
  schreibt lokal und ruft nie `publish_table`. Die Tabellen reisen allein im
  Release mit, und ihre lokale Kopie *ist* der Bestand — `pruefe_stand` und
  die Lader lesen sie dort. Stand `serving` in der Liste, meldete jeder Lauf
  fünfmal *„Nicht oben, lokale Kopie bleibt"*: richtig, harmlos, und eine
  Warnung, die immer kommt, erzieht dazu, Warnungen zu überlesen.

In die `.env` gehört die Variable nicht. Wer sie dort setzt, hält den ganzen
abgeleiteten Bestand lokal und hat `s3` zu einem halben `hybrid` gemacht.

**Ein halb hochgebrachtes Release ist sichtbar, seit dem 17.10.2026.**
`publiziere` schickt `release.json` zuletzt hinauf, damit ein abgebrochener
Upload nie für ein Release gehalten werden kann — `storage.release.liste`
findet Releases genau an diesem Manifest. Das hiess aber auch: Niemand fand
die Reste. Ein `InternalError` von SeaweedFS brach den Upload beim 26. von 28
Objekten ab und liess 182,3 MB liegen, unsichtbar für jedes Werkzeug.
`orchestration.aufraeumen` zeigt sie jetzt als eigenen Block und räumt sie mit
`--loeschen` weg (oben erst mit `--auch-fern`). Geschützt werden muss dabei
nichts: Ein halbes Release ist nie gepinnt und nie der Zeiger — beides hängt
an einer Kennung, die `release.json` trägt.

### Der Betriebsblick — und die zwei Zeilen, die ausserhalb liegen

`serving.betriebsstand` schreibt den Zustand des letzten Laufs im Textformat
von Prometheus neben die Startseite (`/app/startseite/metrics`, vom Dienst
`start` ausgeliefert): Status, Alter des Standes, Exitcode je Stufe,
Quellenfrische, Zeilenzahlen, Release. Gemessen wird dafür **nichts Neues** —
`pipeline_run.json` trägt das alles schon; es fehlte die Sichtbarkeit.

Zwei Eigenschaften sind Absicht und von Wächtern gehalten:

* **Geschrieben wird in jedem Fall**, über ein `trap … EXIT` im Datenlauf und
  nicht als Zeile am Ende von `main` — die läuft bei einem Abbruch gerade
  nicht. Am 12. und 15.10.2026 ist der Lauf gescheitert, und gewusst hat es
  niemand.
* **Ein fehlender Lauf meldet `lauf_bekannt 0`**, statt zu schweigen. Eine
  Metrikdatei, die bei fehlendem Protokoll nichts sagt, liest sich auf der
  anderen Seite als „keine Daten" — und das wird in jedem Dashboard als Lücke
  gezeichnet, nicht als Alarm.

**Was dieses Repository nicht leisten kann** (am 17.10.2026 auf `srv01`
gemessen): Prometheus wird aus
`/srv/docker/infrastructure/monitoring/prometheus/prometheus.yaml`
konfiguriert — geteilt mit anderen Diensten — und scrapet nur sich selbst.
Es liegt im Netz `monitoring`, der Dienst `start` in `proxy`. Damit der Blick
entsteht, braucht es dort **zwei Zeilen**: einen Scrape auf
`http://start/metrics` und eine Netzzuordnung, die ihn erreichbar macht.

### Der Meldeweg — und eine widerrufene Messung

**Was hier bis zum 18.10.2026 stand, war falsch.** Der Satz lautete: *„Ein
Meldekanal fehlt ganz: Alertmanager läuft mit der Beispielvorgabe
(`webhook_configs: http://127.0.0.1:5001/`, dort hört nichts), ist in
Prometheus nicht eingetragen, und auf dem Host gibt es kein `MAILTO`, kein
`sendmail` und keinen laufenden MTA."* Richtig daran war allein der letzte
Teil — es gibt keinen MTA, und einen braucht es auch nicht. Der Rest hat
Christian eine Entscheidung abverlangt, die längst getroffen war: Er
antwortete „Mail ist die einzige sinnvolle Möglichkeit", weil diese Messung
behauptete, es gäbe nichts.

**Gemessen am 18.10.2026 auf `srv01`, lesend:**

| | Stand |
| --- | --- |
| Alertmanager (`infrastructure/monitoring/alertmanager/alertmanager.yaml`) | **Telegram-Empfänger**, `bot_token_file` und `chat_id_file` als Docker-Secrets, `send_resolved: true`, HTML-Vorlage; Route ohne Matcher, also **jeder** Alarm |
| Ausgangsweg | eigenes Netz `alerting-egress` am Alertmanager, genau dafür angelegt |
| in Prometheus eingetragen | ja: `alerting.alertmanagers: [alertmanager:9093]` |
| Scrapes | **zehn**: prometheus, alertmanager, node, containers, loki, alloy, grafana, seaweedfs, n8n, traefik |
| Regeln | `rule_files: /etc/prometheus/rules/*.yaml`, Verzeichnis eingehängt, **sieben** Regeln aktiv (Host, Monitoring, Backups) |

Der Kanal ist also **Telegram**, er ist fertig, und am 18.10.2026 lagen zwei
Alarme aktiv an (`BackupMissingOrStale`, `BackupLastRunFailed`). Für FR-17
braucht es **kein Mailkonto und kein App-Passwort**: Die Route hat keine
Matcher, unsere Regeln melden sich über den bestehenden Empfänger, sobald sie
im Regelverzeichnis liegen.

**Was fehlt, ist dreimal eine Zeile.** Die Regeln selbst liegen fertig und
bewacht in diesem Repository (`docker/prometheus-regeln/urbancrime.yaml`, **neun**
Regeln); `tests/test_alarmregeln.py` hält jeden Namen und jede Marke darin
gegen einen echten Lauf von `serving.betriebsstand`.

**Die Quellen haben zwei Takte, und das kostete eine neunte Regel.** Beim
ersten Scharfschalten stand `QuelleVeraltet` sofort auf `pending`, mit drei
Alarmen: `tiger_tract`, `tiger_place` und `acs5_tract` waren 14 Tage alt.
Nach der Regel zu Recht, nach der Welt falsch — das sind **Jahrgangsdaten**
des Zensus, die nur im Volllauf am zweiten Montag geholt werden. Taten und
Wetter kommen wöchentlich (acht Tage), die drei Jahrgänge monatlich (35 Tage,
denn zwei zweite Montage können so weit auseinanderliegen). Ein Wächter hält
jede Quelle aus `run_all.ERWARTETE_QUELLEN` gegen **genau eine** der beiden
Schwellen — eine siebte Quelle fällt damit auf, bevor sie unbewacht bleibt
oder doppelt alarmiert.

**1 · `start` muss für Prometheus erreichbar sein.** Heute liegt der Dienst in
`proxy` und `urbancrime`, Prometheus in `monitoring`
(`apps/urbancrime/docker-compose.srv01.yml`):

```yaml
  start:
    networks:
      proxy:
      urbancrime:
      # **Mit Alias, nicht nur beitreten.** Compose setzt den Dienstnamen als
      # Netzalias - auf `monitoring` liegen zehn fremde Stapel, und `start`
      # ist dort ein Name, den jeder zweite haben koennte. Unter
      # `urbancrime-start` kann ihn keiner verwechseln.
      monitoring:
        aliases: [urbancrime-start]
```

```yaml
networks:
  monitoring:
    external: true
```

**2 · Der Scrape** (`infrastructure/monitoring/prometheus/prometheus.yaml`,
unter `scrape_configs`). Der Jobname ist nicht frei: Die Regel
`MetrikenUnerreichbar` fragt `up{job="urbancrime"}`, und ein anderer Name
macht lautlos genau die Regel stumm, die das Schweigen aller anderen melden
soll. Ein Test hält diesen Block gegen die Regeldatei.

```yaml
  - job_name: urbancrime
    # Wochentaktige Werte; oefter zu fragen findet nichts und kostet.
    scrape_interval: 2m
    static_configs:
      - targets: [urbancrime-start:80]
```

**3 · Das Regelverzeichnis** (`infrastructure/monitoring/compose.yaml`, beim
Dienst `prometheus`) und eine zweite Glob-Zeile in `prometheus.yaml`:

```yaml
    volumes:
      - /srv/docker/apps/urbancrime/docker/prometheus-regeln:/etc/prometheus/rules-urbancrime:ro
```

```yaml
rule_files:
  - /etc/prometheus/rules/*.yaml
  - /etc/prometheus/rules-urbancrime/*.yaml
```

**Das Verzeichnis, nicht die Datei** — und das ist kein Geschmack: Ein
Datei-Bind-Mount hängt am Inode, und `git pull` *ersetzt* eine Datei, statt
sie zu ändern. Der Container sähe danach für immer die alte Fassung, ohne
Fehlermeldung. Aus demselben Grund heisst die Datei `.yaml` und nicht `.yml`:
Der Glob zählt nur die eine Form.

**Dann einsetzen und nachsehen:**

```bash
cd /srv/docker/apps/urbancrime        && docker compose -f docker-compose.srv01.yml up -d start
cd /srv/docker/infrastructure/monitoring && docker compose up -d prometheus
# Acht Regeln geladen? Und das Ziel oben?
docker exec prometheus wget -qO- http://127.0.0.1:9090/api/v1/rules | grep -c urbancrime
docker exec prometheus wget -qO- "http://127.0.0.1:9090/api/v1/targets?state=active" | grep urbancrime
```

**Und der Endpunkt nennt seinen Typ.** `serving.betriebsstand` schreibt
`metrics` — eine Datei **ohne Endung**. nginx kennt dafür keinen Typ und
liefert `application/octet-stream`, und **Prometheus 3 lehnt das ab**
(*„received unsupported Content-Type"*). Am 18.10.2026 sah das aus wie ein
Netzproblem und war keins: Die Verdrahtung stand, der Endpunkt war
unvollständig. `docker/start-nginx.conf` deklariert deshalb
`text/plain; version=0.0.4` für `/metrics` — dort, wo ausgeliefert wird, und
nicht als `fallback_scrape_protocol` im Scrape, denn jeder weitere
Verbraucher dieses Endpunkts bekäme sonst weiter den falschen Typ.

### Das Brett in Grafana — zwei weitere Zeilen

FR-30 verlangt den Blick **in Grafana**: *„ob die Strecke läuft, wie alt jede
Quelle ist, wo die Drift steht, wie voll die Platte ist."* Das Brett liegt
versioniert in diesem Repository (`docker/grafana-brett/urbancrime.json`, 21
Panels), weil es über *unsere* Messwerte redet — **ein Panel mit falschem
Namen zeigt eine leere Fläche, und die liest sich wie „null" und nicht wie
ein Fehler.** `tests/test_grafana_brett.py` hält jeden Ausdruck gegen einen
echten Lauf von `serving.betriebsstand` und prüft, dass alle vier Dinge aus
FR-30 vorkommen.

**1 · Das Verzeichnis einhängen** (`infrastructure/monitoring/compose.yaml`,
beim Dienst `grafana`):

```yaml
      - /srv/docker/apps/urbancrime/docker/grafana-brett:/var/lib/grafana/dashboards-urbancrime:ro
```

**2 · Einen zweiten Anbieter** (`grafana/provisioning/dashboards/urbancrime.yaml`):

```yaml
apiVersion: 1

providers:
  - name: urbancrime
    orgId: 1
    folder: urbancrime
    type: file
    disableDeletion: true
    updateIntervalSeconds: 30
    # Wie beim Anbieter srv01: Was jemand in der Oberflaeche aendert, ist
    # beim naechsten Einlesen weg. Das Brett kommt aus dem Repository.
    allowUiUpdates: false
    options:
      path: /var/lib/grafana/dashboards-urbancrime
```

Ein eigener Anbieter und kein Eintrag im bestehenden Verzeichnis: So landet
das Brett in seinem eigenen Ordner, und `git pull` im Vorhaben zieht es mit —
ein Datei-Bind-Mount hinge am Inode und zeigte für immer die alte Fassung.

Danach `docker compose up -d grafana`; der Anbieter liest alle 30 Sekunden
neu, ein Neustart ist nur für die Einhängung nötig.

**Die Gegenprobe gehört dazu**, denn ein Meldeweg, den niemand ausgelöst hat,
ist eine Vermutung. Sie schickt eine echte Telegram-Nachricht:

```bash
docker exec alertmanager /bin/amtool --alertmanager.url=http://127.0.0.1:9093 \
    alert add LaufGescheitert severity=critical \
    --annotation=summary="Probe, bitte ignorieren"
```

Solange diese Probe nicht einmal gelaufen ist, bleibt FR-17 **teilweise**:
Die Regeln stehen und sind bewacht, der Kanal existiert — aber dass eine
Nachricht ankommt, hat für *unsere* Alarme niemand gesehen.

### Gesichert wird, was sich nicht nachrechnen lässt

**Der Anlass.** Die nächtliche Sicherung von `srv01` nach Backblaze lief voll;
der letzte erfolgreiche Lauf war der 24.9.2026. Nachgemessen am 18.10.2026
trug sie **7,3 GB je Nacht, davon 7,1 GB unsere** — der SeaweedFS-Datenträger
mit 6,3 GB und ein Elasticsearch-Index mit 810 MB.

**Das Missverhältnis ist nicht die Zahl, sondern die Art der Daten.** Ein
aktueller Stand kostet im Restic-Repository 1,743 GiB, und jeder Wochenlauf
schreibt neue Parquet-Dateien unter neuen Lauf-IDs — restic kann nichts
entdoppeln. Bei einer Aufbewahrung von sieben Tagen, vier Wochen und zwölf
Monaten wuchert das: Von zwölf Snapshots behält die Regel elf. Wir haben
wöchentlich wechselnde **Rechenergebnisse** in ein Archiv gelegt, das für
Dinge gedacht ist, die man nicht nachrechnen kann.

| | Stück | Grösse | nachrechenbar? |
| --- | ---: | ---: | --- |
| gepinnte Läufe (`config/referenzstand.csv`) | 21 | **127,8 MiB** | **nein** — die Portale liefern heute andere Daten als im September |
| gepinnte Releases (dieselbe Spalte des Registers) | 2 | **80,7 MiB** | **nein**, als Stand |
| aktuelles Release | 1 | **173,6 MiB** | baubar, aber es ist der Beleg, auf den die Dokumente zeigen |
| raw, bronze, silver, gold, übrige Releases | | ~2,2 GiB | ja — Silver und Gold in 117 Sekunden |
| `urbancrime_elasticsearch-daten` | | 810 MiB | ja — aus dem Release in Minuten |

**Unersetzlich sind 382,2 MiB in 114 Objekten** (18.10.2026 gemessen, und
nichts davon fehlt oben). `orchestration.sicherungssatz` holt genau die in ein
eigenes Volume (`urbancrime_sicherung`, im Container `/app/sicherung`), und es
besitzt dieses Verzeichnis allein: Was nicht dazugehört, entfernt es. Ohne das
zweite wüchse die Sicherung wieder — jede Woche wird ein anderes Release
aktuell, und das vorige bliebe liegen.

**Vier Formen tragen eine Kennung**, und die erste Fassung kannte nur eine.
Chicago: der Verzeichnisname *ist* die Kennung (`run_20260905T…`). Detroit:
`run_` **plus** die blanke UUID, und das Register führt die UUID ohne das
Präfix. Dazu `release=<Kennung>` für ein gepinntes Release und `run=<Kennung>`,
das `aufraeumen` ebenfalls vergleicht. Mit nur der ersten Form galten **zehn**
gepinnte Einträge als verschwunden — darunter alle acht Detroit-Läufe des
LN1-Stands und beide gepinnten Releases. Hätte der Bericht recht gehabt, wäre
der eingefrorene Stand verloren; hatte er unrecht, wäre er ungesichert
geblieben.

**Warum nicht nach `/app/data`.** Dort liegt das Volume
`urbancrime_arbeitsdaten`, und das steht **nicht** in `backup.volumes`. Der
Satz wäre dort gelandet und nie gesichert worden — ein Test hält diese
Verwechslung fest (`tests/test_srv01_compose.py`).

**Warum dasselbe Register wie beim Aufräumen.** `config/referenzstand.csv`
entscheidet schon, welcher Lauf das Aufräumen überlebt. Ein zweites Register
daneben wäre die Stelle, an der beide auseinanderlaufen — dann wird ein Lauf
aufgehoben, aber nicht gesichert, oder umgekehrt.

Geschrieben wird der Satz im wöchentlichen Datenlauf, **nach** dem Release
und nicht davor, damit er das Release trägt, das jetzt gilt. Ein
unvollständiger Satz macht den Lauf nicht rot — er ist ein Problem der
nächsten Sicherung, nicht des gelaufenen Baus —, meldet sich aber mit
Exitcode 1, einer Warnung im Protokoll und in `sicherungssatz.json`.

**Was das für die Serverpolicy heisst** (`/srv/docker/config/srv01.yaml`):
`urbancrime_sicherung` gehört in `backup.volumes`, `seaweedfs_data` und
`urbancrime_elasticsearch-daten` nicht mehr hinein. Damit fällt die
Sicherungsquelle von 7,3 GB auf etwa **0,6 GB**.

### Der Eimer ist versioniert, und das hat 3,91 GiB gekostet

**Am 18.10.2026 gefunden, aus einem fremden Anlass.** Die nächtliche
Serversicherung von `srv01` nach Backblaze lief voll; der letzte erfolgreiche
Lauf war der **24.9.2026**. Gesucht wurde die Ursache dort, gefunden wurde
sie hier.

Der Eimer `urban-crime` hat **Versionierung eingeschaltet**. Ein `delete`
setzt damit eine Löschmarkierung — die Fassung darunter bleibt liegen. Jedes
Aufräumen, das `orchestration.aufraeumen` je gemacht hat, hat deshalb
**keinen Platz freigegeben**. Sichtbar war das in nichts: `list_objects_v2`
nennt nur die jeweils aktuelle Fassung, also meldeten alle unsere Werkzeuge
den Platz als frei.

| im Eimer `urban-crime` | Objekte | Grösse |
| --- | ---: | ---: |
| aktuelle Fassungen | 1'551 | 2,60 GiB |
| **alte Fassungen** | **3'863** | **3,91 GiB** |
| Löschmarkierungen | 2'381 | — |

Aufgefallen ist es an einer Differenz: Der SeaweedFS-Filer meldete für den
Eimer **6,99 GB**, die S3-Auflistung **2,60 GiB**. Dazwischen lagen 41
Release-Verzeichnisse, die als gelöscht galten und deren
`release.json.versions` noch dalag.

`orchestration.aufraeumen` zählt sie seit dem 18.10.2026 je Schicht und
zeigt sie **immer** — auch ohne `--loeschen`, denn Zeigen ist die Aufgabe des
Moduls. Entfernt werden sie nur mit `--fassungen --auch-fern`: Es ist die
einzige Löschung dort, die sich aus keinem Lauf wiederherstellen lässt, weil
eine alte Fassung nirgends sonst liegt. Die aktuelle Fassung bleibt immer.

**Die Lehre ist nicht die Versionierung, sondern die Differenz.** Ein
Werkzeug, das den belegten Platz über dieselbe Schnittstelle misst, über die
es löscht, kann einen Rest nicht sehen, den diese Schnittstelle verbirgt.
Gegengeprüft wurde hier über den Filer — eine zweite, unabhängige Sicht auf
denselben Speicher.

Ein Release entsteht nur nach einem **vollständigen** grünen Lauf bis
einschliesslich Serving — ein halber Stand bekommt keine Kennung. Scheitert
das Publizieren, ist der Lauf gescheitert.

Releases werden aufgehoben; eine Löschregel ist offen (`datenhistorie.md`).

---

## 7 · Zwei Sorten Ziele, zwei Regeln

| | `raw/`, `bronze/` | `silver/`, `gold/` |
| --- | --- | --- |
| Natur | unveränderliche Läufe | abgeleitet, ersetzbar |
| Lokal | angehäuft, nie überschrieben | ersetzt bei jedem Bau |
| Auf S3 | **nie still überschrieben** | **überschrieben** |
| Schutz | Inhaltsvergleich | Standvergleich (Abschnitt 8) |

**Läufe.** Liegt ein Objekt schon oben und ist identisch, wird es
übersprungen — zweimal publizieren ist erlaubt und tut nichts. Liegt es mit
**anderem** Inhalt dort, ist das ein Fehler: `PublishError`, und das Manifest
geht nicht hoch. Da `run_id`s UTC-Zeitstempel oder UUIDs sind, tritt der Fall
praktisch nie ein; die Prüfung ist für den Fall, dass doch.

**Abgeleitete Tabellen** *sollen* überschrieben werden — sie sind das
Ergebnis des letzten Baus, und lokal werden sie ebenso ersetzt. Das ist
dokumentiert und beabsichtigt. Dass dabei niemand versehentlich einen
**älteren** Stand über einen neueren schiebt, regelt der nächste Abschnitt.

---

## 8 · Der veraltete eigene Stand

„Lokal zuerst" hat eine scharfe Kante. Wer eine Silver- oder Gold-Tabelle von
letzter Woche herumliegen hat, liest sie — leise, mit der Zahl von letzter
Woche. Und veröffentlicht er sie, verdrängt sein alter Stand den neuen für
alle.

Deshalb vergleicht die Ablage bei abgeleiteten Tabellen beide Manifeste. Zwei
Signale, weil eines nicht reicht:

1. **`built_at_utc`** — wann gebaut wurde. Alle neun Tabellen tragen es.
2. **Die Bronze-Läufe aus `derived_from`** — worauf der Stand ruht. Das fängt
   den Fall, den die Uhrzeit nicht fängt: *heute gebaut, aber ohne den Lauf,
   den jemand anders längst geladen hat.*

`derived_from` hat drei gewachsene Formen, und alle drei werden gelesen:
`crime_offense` führt Listen je Stadt (`chicago_bronze_runs`), die übrigen
Silver-Tabellen eine Liste von Einträgen mit `run_id`, und **Gold nennt
Silver-Tabellen statt Läufe** — dort zählt allein der Zeitpunkt.

| Wo | Verhalten |
| --- | --- |
| **Lesen** | Warnung im Log, **gelesen wird trotzdem lokal** |
| **Publizieren** | Absage mit `PublishError`; der lokale Bau bleibt fertig |
| **`python -m storage`** | zeigt je Tabelle `aktuell` oder `ALT` mit Begründung |

Der Unterschied ist Absicht: „Lokal zuerst" bleibt die Regel, und wer offline
arbeitet, soll weiterarbeiten können. Ein Rückschritt im **gemeinsamen**
Bestand ist etwas anderes — das darf nicht aus Versehen passieren.
`publish_table(..., erzwingen=True)` dreht bewusst zurück.

Der Ausweg ist in jedem Fall derselbe:

```bash
python -m orchestration.run_all --ohne-ingestion
```

Danach ruht der eigene Stand auf allen Läufen — den lokalen und denen von
SeaweedFS —, und das Publizieren geht durch.

---

## 9 · Was immer lokal bleibt

`data/serving/` — die Auswertungsdatenbank `analyse.duckdb`,
`tracts.geojson` und seit dem 17.9.2026 die fünf Vergleichstabellen aus
`serving.build_comparison`. In **jedem** Modus. Die Vergleichstabellen
erreichen SeaweedFS nicht an einem festen Pfad wie Silver und Gold, sondern
nur als Teil eines Release (Ausblick, Abschnitt 6).

Die Datenbank hält keine Daten, nur Sichten, und diese Sichten tragen Pfade.
Sie ist abgeleitet, in Sekunden neu gebaut und auf einem anderen Rechner
wertlos — sie zu teilen brächte nichts und ginge schief. Wohin ihre Sichten
zeigen, entscheidet dagegen der Modus: im Hybridbetrieb je Datei dorthin, wo
sie liegt.

Die `analyse.duckdb` **in einem Release** (Abschnitt 6a) ist ein anderes
Artefakt: Sie hält **Tabellen**, ist selbständig und wird geteilt — gerade
weil ein Release unveränderlich ist, kann eine Kopie darin nicht veralten.

Ebenfalls lokal: `data/pipeline_run.json` (das Protokoll des letzten
Gesamtlaufs), `data/drift.json` und alle `.part`/`.partial`-Verzeichnisse.
`orchestration.aufraeumen` räumt Raw- und Bronze-**Läufe** ausschliesslich
lokal auf — SeaweedFS wird davon nie berührt. Einzige Ausnahme seit dem
4.10.2026 sind entbehrliche **Releases**: Sie liegen oben als der gemeinsame
Stand, und die Behalteregel (*gepinnt plus die letzten acht*) gilt dort
genauso. Auch die gehen oben erst mit `--loeschen --auch-fern` weg — zwei
Schalter, weil ein Löschen im Bucket jede Maschine betrifft, die davon liest.

---

## 10 · DuckDB und S3

Kann die Ablage S3 lesen, bringt die Verbindung `httpfs` und ein
**temporäres** Secret mit:

```sql
INSTALL httpfs; LOAD httpfs;
CREATE OR REPLACE SECRET seaweedfs (
    TYPE S3, KEY_ID '…', SECRET '…',
    ENDPOINT 's3.datenwerft.ch', URL_STYLE 'path', USE_SSL true
);
```

Ohne `PERSISTENT`: Das Secret lebt nur in dieser Verbindung, nichts landet
auf der Platte. Die Schlüssel kommen aus der Konfiguration und werden nie
protokolliert; schlägt das Anlegen fehl, wird die DuckDB-Meldung **nicht**
durchgereicht, weil sie das SQL samt Schlüssel zitieren könnte.

`URL_STYLE 'path'` ist für SeaweedFS nötig — es adressiert Buckets als
Pfadpräfix, nicht als Subdomain.

Wer `analyse.duckdb` im Hybrid- oder S3-Modus von Hand öffnet, braucht
dieselbe Einrichtung:

```python
from storage import get_storage
from storage.duckdb import connect
con = connect(get_storage().config, "data/serving/analyse.duckdb", read_only=True)
```

---

## 11 · Die API

Am bequemsten über die Standardablage (`from storage import …`):

| Funktion | Was sie liefert |
| --- | --- |
| `resolve_read_path(*teile)` | woher gelesen wird — lokaler Pfad oder `s3://` |
| `local_path(*teile)` | der lokale Pfad, immer |
| `s3_path(*teile)` | die `s3://`-URL, immer |
| `storage_path(*teile)` | der relative Ablagepfad |
| `exists(*teile)` | liegt es lokal oder oben? |
| `list_files(prefix, muster)` | Dateien, lokal ∪ entfernt |
| `groessen_unter(prefix, muster)` | dieselbe Auswahl als `{Pfad: Bytes}` |
| `bytes_unter(prefix, muster)` | deren Summe — die **eine** Byte-Summe |
| `read_text(*teile)` / `write_text(text, *teile)` | kleine Dateien |
| `publish_to_shared_storage(*teile)` | ein Verzeichnis publizieren |

Dazu vier Listen von Schichtnamen, kanonisch an **einer** Stelle
(`storage.backend`), weil es vorher drei einander widersprechende gab. Sie
stehen hier bewusst nicht als Tabelle: Die Tabelle darüber ist die der
Umgebungsvariablen, und `tests/storage/test_dokumentation.py` liest sie
zeilenweise.

* **`SCHICHTEN`** — alle sechs, in der Reihenfolge der Strecke: raw, bronze,
  silver, gold, serving, releases.
* **`LAUFSCHICHTEN`** — die aus unveränderlichen Läufen: raw, bronze.
* **`TABELLENSCHICHTEN`** — die mit Tabellen, ersetzt statt angehäuft: silver,
  gold, serving.
* **`ABGELEITET`** — die engere Menge silver, gold; nur dort ist der
  Standvergleich sinnvoll.

`orchestration.platzbedarf` misst damit die Belegung je Schicht; die
Hochrechnung daraus steht in `docs/intern/platzbedarf.md`.

Auf dem `Storage`-Objekt zusätzlich: `laeufe()`, `tabellen()`,
`publish_run()`, `publish_table()`, `publish_files()`, `vergleiche_stand()`,
`entfernter_stand()`, `relativ()`, `mit_wurzel()` — und `entferne_oben(prefix)`,
die **einzige**, die Daten aus dem geteilten Bucket entfernt: Sie zählt über
`list` auf, löscht `zuletzt` benanntes am Ende (für ein Release das
`release.json`, damit ein Abbruch es nicht unsichtbar macht), lehnt einen
leeren Präfix ab und bricht beim ersten Fehler ab. Gebraucht wird sie von
`orchestration.aufraeumen --loeschen --auch-fern`.

`get_storage()` liest die Konfiguration einmal und merkt sie sich.
`for_root(data_root)` liefert dieselbe Ablage mit anderer lokaler Wurzel —
das ist der Weg, auf dem `--data-root` wirkt. `set_storage()` ist für Tests.

In Notebooks genügt:

```python
from storage import resolve_read_path
pfad = resolve_read_path("silver", "dataset=crime_offense", "part-0001.parquet")
```

---

## 12 · Werkzeuge

```bash
python -m storage                          # Verbindung, Konfiguration, Stand je Tabelle
python -m storage publizieren              # zeigt, welche lokalen Läufe oben fehlen
python -m storage publizieren --wirklich   # bringt sie hoch, Raw vor Bronze
```

`python -m storage` zeigt Modus, Wurzel, Endpoint und Bucket — **nie die
Schlüssel** —, löst den Hostnamen auf, listet `silver/` und vergleicht je
abgeleitete Tabelle den lokalen mit dem veröffentlichten Stand. Das ist der
erste Befehl, wenn etwas nicht stimmt.

`publizieren` gibt es, weil die Pipelines nur den Lauf publizieren, den sie
gerade schreiben. Ein Bestand, der vor der Umstellung entstanden ist, kommt
so hoch — idempotent, in der richtigen Reihenfolge, ohne Sync in die
Gegenrichtung.

```bash
python -m orchestration.release liste                    # jedes Release, lokal und oben
python -m orchestration.release aktuell                  # worauf der Zeiger zeigt
python -m orchestration.release erstellen --publizieren  # bilden, hochbringen, Zeiger umlegen
```

---

## 13 · Was bewusst nicht gebaut ist

* **Kein automatisches Herunterladen von Silver und Gold.** Was lokal fehlt,
  wird von S3 *gelesen*, nicht kopiert. Ein stiller Cache wäre eine zweite
  Wahrheit mit eigenem Alter — genau das Problem, das Abschnitt 8 behandelt.
  Für **Raw, Bronze und Releases** gilt das seit dem 17.9.2026 nicht mehr: Sie
  sind unveränderlich, eine Kopie kann nicht veralten — siehe Abschnitt 5a.
* **Keine Synchronisation zurück.** SeaweedFS ist der veröffentlichte
  Bestand, nicht ein Spiegel des Arbeitsverzeichnisses.
* **Kein gleichzeitiges Schreiben in beide Richtungen.**
* **Keine Sperren, keine Transaktionen.** Bei zwei Bearbeitern und
  unveränderlichen Läufen wäre das Aufwand ohne Gewinn; für die einzige
  Stelle, an der zwei Stände kollidieren können — die abgeleiteten Tabellen
  —, steht die Regel aus Abschnitt 8.
* **Keine Rechteverwaltung.** Wer die Schlüssel hat, darf lesen und
  schreiben.

---

## 14 · Wenn es klemmt

| Meldung | Bedeutung |
| --- | --- |
| `STORAGE_BACKEND=hybrid braucht S3_ACCESS_KEY und S3_SECRET_KEY` | Schlüssel fehlen in Umgebung und `.env` |
| `… loest nicht auf` | kein DNS-Eintrag für `S3_ENDPOINT` — kein Schlüssel hilft |
| `SeaweedFS nicht erreichbar: https://…` | Endpoint antwortet nicht: Host, Port, SSL prüfen |
| `SeaweedFS lehnt ab: InvalidAccessKeyId / SignatureDoesNotMatch` | Schlüssel falsch |
| `SeaweedFS lehnt ab: NoSuchBucket` | `S3_BUCKET` stimmt nicht oder existiert noch nicht |
| `existiert bereits mit anderem Inhalt` | ein Lauf soll überschrieben werden — Abschnitt 7 |
| `Nicht publiziert, das waere ein Rueckschritt` | veralteter eigener Stand — Abschnitt 8 |
| `ConnectionClosedError` / `Connection reset by peer` bei jedem Zugriff | die Verbindung wird auf dem Netzweg abgeschnitten — siehe unten |

### Wenn die Verbindung abgeschnitten wird

Am 17.9.2026 antwortete `s3.datenwerft.ch` von einem Hochschulnetz aus auf
**keinen** Zugriff mehr, während Uploads Minuten vorher noch durchliefen. Kein
Schlüssel, kein Bucket, kein DNS-Problem — der TLS-Handshake selbst wurde
zurückgesetzt. Drei Messungen grenzen so etwas in einer Minute ein:

```bash
# 1 · Was sagt der eigene Resolver, was sagen öffentliche?
dig +short s3.datenwerft.ch ; dig +short @1.1.1.1 s3.datenwerft.ch

# 2 · Kommt überhaupt eine TLS-Verbindung zustande?
curl -sS -o /dev/null -w "%{http_code} %{remote_ip}\n" https://s3.datenwerft.ch/
```

```python
# 3 · Der entscheidende Test: dieselbe IP, zwei verschiedene Hostnamen im
#     ClientHello. Klappt der eine und der andere nicht, liest ein Gerät auf
#     dem Weg den Namen mit und schneidet gezielt ab.
import socket, ssl
for sni in ("s3.datenwerft.ch", "www.cloudflare.com"):
    s = socket.create_connection(("188.114.96.12", 443), timeout=8)
    try:
        ssl.create_default_context().wrap_socket(s, server_hostname=sni)
        print(sni, "TLS ok")
    except Exception as e:
        print(sni, type(e).__name__, e)
    finally:
        s.close()
```

Genau das war der Befund: **TCP stand, TLS mit `www.cloudflare.com` klappte,
TLS mit `s3.datenwerft.ch` wurde zurückgesetzt** — an derselben Adresse. Das
ist keine Frage der Konfiguration; es hilft nur ein anderer Netzweg (anderes
WLAN, Mobilfunk, VPN) oder das Netz zu fragen. Nebenbei fiel dabei auf, dass
der Resolver des Netzes andere Cloudflare-Adressen lieferte als 1.1.1.1, 8.8.8.8
und 9.9.9.9 — nicht die Ursache, aber ein Hinweis auf einen Mittelsmann.

**Bis dahin lokal weiterarbeiten.** `STORAGE_BACKEND=local` in `.env`: Die ganze
Strecke läuft, nur publiziert wird nichts. Gemessen am selben Abend: acht Stufen
in drei Sekunden.

Vorübergehende Störungen — HTTP 403 als Aussetzer, 5xx, abgebrochene
Verbindungen — werden bis zu **viermal** wiederholt, mit Pausen von 1, 3 und
8 Sekunden. Der 403 steht in dieser Liste, weil SeaweedFS beim ersten
Nachpublizieren genau so antwortete und Sekunden später auf denselben
Schlüssel mit 404: ein Aussetzer, kein Rechteproblem. `boto3` wiederholt 403
von sich aus nicht. Endgültige Fehler — falscher Schlüssel, fehlender Bucket
— kommen sofort.

---

## 15 · Wo der Code liegt

| Datei | Inhalt |
| --- | --- |
| `src/crime/storage/config.py` | `Config`, Lesen aus Umgebung und `.env`, Validierung |
| `src/crime/storage/paths.py` | relative Ablagepfade, `s3://`-URL, Abweisung von `..` |
| `src/crime/storage/backend.py` | `Storage`, `Boto3Client`, `FakeS3Client`, Publizieren, Standvergleich |
| `src/crime/storage/duckdb.py` | Verbindung mit `httpfs` und temporärem Secret |
| `src/crime/storage/__main__.py` | `python -m storage` und `publizieren` |
| `tests/storage/` | 103 Tests gegen ein S3 **im Speicher** — kein Test braucht SeaweedFS |

Dass die Tests ohne Server laufen, ist Absicht: `FakeS3Client` ist ein dict
mit vier Methoden. Damit lässt sich alles prüfen, worauf es ankommt — die
Reihenfolge beim Publizieren, der Konflikt, der Rückfall, der veraltete
Stand — ohne dass jemals eine CI-Maschine einen Zugang braucht.

Ein Integrationstest gegen ein echtes SeaweedFS ist möglich und bewusst
nicht Teil der Suite:

```sql
SELECT count(*) FROM read_parquet(
    's3://urban-crime/silver/dataset=crime_offense/part-0001.parquet');
```

---

## 16 · Die Strecke auf `srv01`

Seit dem 6.10.2026 gibt es neben der Entwicklungsfassung eine zweite
Compose-Beschreibung:
[`docker-compose.srv01.yml`](../docker-compose.srv01.yml). Sie steht hier,
weil die Ablage entscheidet, wie sie aussieht: Auf `srv01` ist der Modus `s3`,
SeaweedFS ist der Bestand, und die lokale Kopie wird nach dem Publizieren
entfernt. Daraus folgt beides — es braucht **kein dauerhaftes
`data/`-Volume**, nur einen Arbeitsraum, und `httpfs` wird kritisch statt
nützlich, weil Silver Bronze direkt von S3 liest.

**Seit dem 1.11.2026 ohne Elasticsearch und Kibana (C-9).** Kibana war für
fünf Bretter zu schwer: Zusammen mit Elasticsearch belegte es 2'816 MiB im
Dauerbetrieb, und daneben blieben von 4'325 MiB noch 37 frei. An ihre Stelle
tritt das eigene Dashboard ([`serving.dashboard`](../src/crime/serving/dashboard/__init__.py),
Flask und DuckDB) nach Artans Entwürfen. Es liest Gold und `comparison_month`
direkt aus dem Eimer, lädt ein neues Release höchstens eine Minute später von
selbst nach und braucht weder Lader noch Index noch gespeicherte Objekte.
Entschieden ist **nur der Server**: Lokal bleiben Elasticsearch und Kibana in
`docker-compose.yml`, `load_elasticsearch` und `build_kibana` bleiben
aufrufbar. Die beiden Datenträger stehen auf `srv01` als Rückweg weiter, bis
niemand sie mehr braucht. **Beschrieben, noch nicht eingesetzt:** Bis der
Wechsel auf `srv01` vollzogen und dort nachgemessen ist, laufen dort beide
weiter. Was unten über Elasticsearch und Kibana auf `srv01` steht, ist der
Stand bis zu diesem Tag.

**Sie ist seit dem 8.10.2026 angewandt.** Auf `srv01` liefen Elasticsearch,
Kibana und Jupyter nach dieser Beschreibung; am 11.10.2026 waren alle drei
`healthy`, beide Abbilder per Digest gepinnt, und die Digests in der `.env`
des Stapels sind zeichengleich mit den hier gebauten. Drei der vier Posten
unter „Was daneben einzurichten ist" sind erledigt — die Abbilder seit dem
8.10.2026 in einer Registry, die Tunnel-Routen und die Access-Anwendung seit
dem 9.10.2026, von aussen gemessen. Ein Zeitplan steht ebenfalls: montags
04:30 über `cron`, mit `flock` gegen Überlappung. Der erste Montag fährt
Delta, der zweite den Volllauf, der dritte und vierte wieder Delta; ein fünfter
Montag bleibt frei. Der Volllauf liegt bewusst auf dem zweiten Montag, damit
er nie mit dem Restic-Vollrestore am Monatsersten um 05:00 zusammentrifft.

**Was sie weiter nicht ist: ein Nachweis.** Der Zeitplan hat am 11.10.2026
noch nie gefeuert — `logs/scheduled-pipeline.log` gibt es nicht, und der
Crontab schreibt mit `>>` hinein, die Datei entstünde also auch bei einem
Fehlschlag. Erster Termin ist Montag, der 12.10.2026. Ob die Strecke selbst
dort je durchgelaufen ist, zeigt kein Artefakt: Sie ist ein Stapellauf hinter
einem `profiles:`-Schlüssel und lässt als `--rm`-Lauf keinen Container
zurück. Das tatsächlich auf `srv01` liegende Skript ist als
[`docker/srv01-datenlauf.sh`](../docker/srv01-datenlauf.sh) versioniert; die
Cron-Fassung liegt daneben unter `deploy/cron/` und ihre Voll-/Delta-Verteilung
wird getestet.

### Warum zwei Dateien

`docker-compose.yml` ist die Entwicklungsfassung: drei Analysedienste, Ports
an `127.0.0.1` gebunden, kein Traefik, keine Speichergrenzen. Das ist auf dem
Entwicklungsrechner richtig und auf `srv01` falsch — dort gibt es keinen
Host-Port 80 oder 443, der Eingang ist ein **ausgehender** Cloudflare-Tunnel
auf Traefik, und 7,7 GiB tragen bereits fünfzehn fremde Dienste. Eine Datei,
die beides sein will, ist in einem der beiden Fälle falsch. Die
Entwicklungsfassung bleibt deshalb unangetastet; ein Test hält fest, dass sie
weiter an `127.0.0.1` bindet und kein Traefik-Label trägt.

### Die sechs Dienste

| Dienst | Was er ist | Wie er erreichbar ist |
| --- | --- | --- |
| `dashboard` | Dauerbetrieb, gerouteter Webdienst, liest den Eimer (seit 1.11.2026, statt `elasticsearch` und `kibana`) | `urbancrime-dashboard.datenwerft.ch` über Traefik |
| `start` | Dauerbetrieb, liefert die Einstiegsseite aus (seit 12.10.2026, FR-31) | `urbancrime-start.datenwerft.ch` über Traefik |
| `pipeline` | **Stapellauf**, läuft einmal durch und endet | gar nicht — kein Port, kein Label, kein `unless-stopped` |
| `jupyter` | zeitweilig, **lesende** Analyse | `urbancrime-jupyter.datenwerft.ch` über Traefik |
| `admin` | Dauerbetrieb, Webdienst der Engineering-Konsole (seit 30.10.2026) | `urbancrime-admin.datenwerft.ch` über Traefik |
| `worker` | **Stapellauf** der Konsole, ein Auftrag je Fünf-Minuten-Takt | gar nicht — kein Port, kein Label, `restart: "no"` |

Bis zum 1.11.2026 stand Elasticsearch in dieser Tabelle, und dass es `proxy`
nicht beitrat, war keine Vorsicht, sondern die Vorgabe des Servers: Ein
versehentliches Traefik-Label daran wäre ein offener Datenspeicher. Das
Dashboard hat keinen Datenspeicher, den man finden könnte — es liest den
Eimer mit denselben Schlüsseln wie die Konsole und schreibt nichts, hängt
also auch keinen Datenträger ein.

Pipeline, Worker und Jupyter tragen ein Compose-**Profil** und starten deshalb
nicht mit `up -d`. Das ist nicht Kosmetik: Die Rechnung unten geht nur auf,
solange der Dauerbetrieb aus Dashboard, Konsole und dem kleinen `start`
besteht.

### Die Speichergrenzen — gemessen, nicht geschätzt

Am **6.10.2026** auf der laufenden Maschine gemessen: 31 Container belegen
3'605 MiB, verfügbar sind **4'325 MiB**, und 2'418 von 4'095 MB Swap sind
bereits belegt. Die vorher veranschlagten 5'632 MiB lagen damit **1'307 MiB
über** dem Verfügbaren — die Schätzung war nicht knapp, sie war falsch.

| Dienst | Grenze | Woher die Zahl kommt |
| --- | ---: | --- |
| `dashboard` | 640 MiB | am 1.11.2026 **lokal** unter gunicorn gemessen: Spitze **476 MiB** beim Verdichten der 1,85 Mio. Taten, **412 MiB** mit DuckDB auf 256 MB und zwei Threads; danach hält DuckDB 70–90 MB. Auf `srv01` nachzumessen |
| ~~`elasticsearch`~~ | ~~1'792 MiB~~ | bis zum 1.11.2026; der Heap nutzte gemessen **195 von 1'024 MiB** |
| ~~`kibana`~~ | ~~1'024 MiB~~ | bis zum 1.11.2026; gemessen belegt **771 MiB** |
| `start` | 32 MiB | das obere Ende der Spanne, die ein nginx mit einer statischen Datei belegt (16–32); **nicht** gemessen — gemessen ist der Platz, in den es passt |
| `pipeline` | 1'280 MiB | 1,25 GiB, zeitweilig |
| `jupyter` | 768 MiB | zeitweilig; passt nur, wenn cadvisor gedeckelt wird |
| `admin` | 160 MiB | am 31.10.2026 auf `srv01` gemessen: **52 MiB** in Ruhe, Spitze **66 MiB** mit laufendem Takt. Impact-Downloads werden gestreamt, der grösste denkbare (173 MiB ZIP) blieb bei 46 MiB |
| `worker` | 1'280 MiB | dieselben Bauten wie `pipeline`, zeitweilig und nie neben ihr |

**Die Rechnung.** Dauerbetrieb sind Elasticsearch, Kibana und `start` mit
zusammen 2'848 MiB. Pipeline und Jupyter sind zeitweilig und streiten um
denselben Platz, es zählt also das grössere der beiden: 1'280 MiB. Zusammen
**4'128 MiB** gegen 4'325 MiB verfügbar plus die rund 792 MiB, die das Deckeln
von cadvisor freigibt. `tests/test_srv01_compose.py` rechnet das nach und
nimmt die Einteilung in dauernd und zeitweilig aus der Datei selbst — wer ein
Profil entfernt, macht aus einem zeitweiligen Dienst einen dauernden, und der
Test fällt.

**Der dritte dauernde Dienst war eine Entscheidung.** Bis zum 12.10.2026
liefen genau zwei Dienste dauerhaft, und ein Test hielt das fest. Eine Seite,
die erreichbar sein soll, muss laufen, wenn jemand ihre Adresse aufruft — also
wurden es drei. Vertretbar ist das, weil 229 der 4'325 MiB frei waren und ein
nginx 16–32 davon braucht; entschieden ist es an der Stelle, an der der Test
heute „Elasticsearch, Kibana und `start`" sagt und seinen Grund dazu.

**Der vierte dauernde Dienst, am 30.10.2026.** Die Engineering-Konsole
braucht einen Webdienst, der antwortet, wenn jemand die Adresse aufruft, und
einen Worker, der die Pipelines ausführt. Dauernd laufend hätte der Worker
deren 1'280 MiB belegt — rund 1,3 GiB über dem Budget. Er läuft deshalb wie
die Pipeline als Stapellauf, angestossen alle fünf Minuten von
[`docker/srv01-konsole-takt.sh`](../docker/srv01-konsole-takt.sh) über
dieselbe Sperre wie der Datenlauf, aber ohne zu warten. Dauernd ist nur
`admin`: 2'848 + 160 = 3'008 MiB, mit dem grösseren Zeitweiligen
**4'288 von 4'325 MiB** — 37 MiB frei, ohne die 792 aus cadvisor.

**Am 1.11.2026 fallen zwei und kommt einer.** Elasticsearch und Kibana
weichen dem Dashboard: 640 + 160 + 32 = **832 MiB** dauernd, mit dem
grösseren Zeitweiligen **2'112 von 4'325 MiB** — rund 2,2 GiB frei statt 37.
Der Test heisst weiter `test_der_dauerbetrieb_ist_entschieden` und nennt
jetzt `admin`, `dashboard` und `start`.

**Die eine Voraussetzung, die nicht in dieser Datei steht:** cadvisor muss auf
**256 MiB** gedeckelt werden. Es belegt heute 1'047 MiB — 29 % des gesamten
Containerspeichers und mehr als jeder andere Dienst. Ohne diese Deckelung
passt Jupyter nicht. cadvisor gehört zum Überwachungsstapel und nicht zu
diesem; die Deckelung ist dort vorzunehmen.

**DuckDB wird zusätzlich von innen begrenzt.** Ein Container-Limit tötet den
Prozess, es bremst ihn nicht — und ohne Angabe nimmt DuckDB rund 80 % des
Arbeitsspeichers der **Maschine**, nicht des Containers; das wären hier
6,3 GiB auf einer Maschine mit fünfzehn Nachbardiensten. Pipeline und Jupyter
setzen `memory_limit` und `threads` deshalb über die Umgebung — dieselben zwei
Variablen, die `src/crime/storage/duckdb.py` auf **jeder** Verbindung setzt und
die `.env.example` erklärt: 896 MB bei 1'280 MiB Container, 512 MB bei
768 MiB, 256 MB beim Dashboard mit 640 MiB, zwei Threads von vier vCPU. Ein Test hält fest, dass die innere
Grenze unter der äusseren liegt.

Bis zum 1.11.2026 verbot sich nur Elasticsearch das Auslagern
(`memswap_limit` gleich der Grenze): Ein Heap auf der Platte erzeugt
Cluster-Zeitüberschreitungen statt Langsamkeit. Pipeline und Jupyter bekommen
die Zeile bewusst nicht — dort ist
Swap der Rettungsanker eines einmaligen Laufs, und ein langsamer Wochenlauf
ist besser als ein getöteter.

### Was daneben einzurichten ist

Vier Dinge kann eine Compose-Datei nicht sagen, und alle vier sind nötig,
damit etwas erreichbar **sein kann**. Zwei davon sind eingerichtet: die
Access-Anwendung seit dem 9.10.2026, von aussen gemessen, und die Abbilder
seit dem 8.10.2026 in der Registry. Offen ist allein der Datenträger für Restic:
Die dritte Tunnel-Route, die für `urbancrime-start`, ist seit dem 14.10.2026
angelegt und von aussen gemessen — `urbancrime-start.datenwerft.ch` löst auf
und antwortet mit **302** auf dasselbe Anmeldetor wie Kibana, ohne dass an
der Access-Anwendung etwas zu ändern war. Das Muster `urbancrime-*` hat sie
mitgedeckt, genau wie FR-22 es verspricht. Erreichbar heisst das trotzdem
nicht, dass dort etwas antwortet — was gemessen wurde, liegt vollständig
**vor** dem Ursprung.

**Seit dem 1.11.2026 fällig: die Route für `urbancrime-dashboard`**, auf
dieselbe Weise und unter dieselbe Access-Anwendung. Die Route für
`urbancrime-kibana` kann danach entfallen; hinter ihr antwortet nichts mehr.

**Die Tunnel-Route je Hostname** — angelegt am 9.10.2026, je Hostname eine
veröffentlichte Anwendung auf dem bestehenden Tunnel, und zwar so:

```text
Public hostname: urbancrime-kibana.datenwerft.ch
Service type:    HTTP
Service URL:     http://traefik:80
```

Der Ursprung ist **immer** `http://traefik:80` und **nie** der öffentliche
Hostname: Zeigt die Route auf sich selbst, läuft der Verkehr zurück durch
Cloudflare — eine Schleife oder ein HTTP 403. Traefiks `Host(...)`-Regel
erledigt danach die Zuordnung. Angelegt sind die beiden Routen für Kibana und
Jupyter; für `urbancrime-start.datenwerft.ch` ist sie seit dem 12.10.2026
**fällig und noch nicht angelegt** — der Dienst steht in der Beschreibung, die
Route ist eine Cloudflare-Einstellung und keine Compose-Zeile.
`urbancrime.datenwerft.ch` bleibt dagegen unbesetzt und hat bewusst kein DNS:
Es ist der **einzige** Hostname, den das Muster `urbancrime-*` nicht deckt,
und damit der einzige, den die eine Access-Anwendung nicht schützt. Nichts an
diesem Projekt ist öffentlich — auch die Einstiegsseite nicht.

**Eine eigene Access-Anwendung über `urbancrime-*`** — angelegt am 9.10.2026,
und zwar als **eine**. Die bestehende Wildcard-Policy greift nur vor
`infra-*`, und `infra-*` ist der Infrastruktur
vorbehalten. Deshalb das Muster: `urbancrime.datenwerft.ch` ist die
öffentliche Seite, alles Weitere heisst `urbancrime-<dienst>.datenwerft.ch`,
und **eine** Access-Anwendung über `urbancrime-*` deckt jeden künftigen Dienst
mit. Eine vergessene Access-Regel ist ein offener Dienst; ein Muster lässt
sich nicht vergessen. Ein Test hält die Hostnamen am Muster fest. Nach jeder
neuen Route wird gegen einen **zufälligen** Hostnamen geprüft, dass er die
Seite nicht erreicht.

Gemessen am 9.10.2026 von aussen: Beide Hostnamen umleiten mit **302** auf
das Anmeldetor, beide Umleitungen tragen dieselbe Anwendungskennung — also
eine Anwendung über beide, nicht zwei nebeneinander. Der Zufallstest fällt
dabei stärker aus als gefordert: Der gewürfelte Name löst nicht einmal auf,
es gibt mithin keinen DNS-Platzhalter, der eine künftige Route ungeschützt
durchliesse. Was die Messung **nicht** belegt, steht in
[`intern/AENDERUNGEN.md`](intern/AENDERUNGEN.md) zum 9.10.2026: Access greift
vor dem Ursprung, also sagt eine 302 nichts darüber, ob Traefik, Kibana oder
Jupyter antworten.

**Der Elasticsearch-Datenträger in `config/srv01.yaml` ist entfallen.** Er
stand hier als offen, bis der Abschnitt „Gesichert wird, was sich nicht
nachrechnen lässt" ihn am 18.10.2026 aus der Sicherung nahm; seit dem
1.11.2026 gibt es auf `srv01` auch den Dienst nicht mehr. Das Dashboard hat
nichts zu sichern: Es hält keinen Zustand, nur eine Verdichtung des Eimers.
Der Arbeitsraum der Strecke gehört ausdrücklich **nicht** dazu: Was Restic
sichern muss, ist der Bucket.

**Die Abbilder in einer Registry.** `srv01` verbietet den Bau auf dem Host —
*„large frontend builds have previously exhausted RAM"* —, und das
Actions-Budget ist erschöpft. Gebaut wird deshalb auf einem
Entwicklungsrechner, dann geschoben und per SHA-256-Digest gepinnt; die
Beschreibung trägt kein `build:`, sondern liest den Namen aus der `.env` des
Stapels. Zwei Abbilder sind es: das der Strecke und ein zweites für die
Analyse — das erste plus `jupyterlab` und die Notebooks. Beide liegen als
Beschreibung im Repository ([`Dockerfile`](../Dockerfile) und
[`Dockerfile.jupyter`](../Dockerfile.jupyter)) und seit dem 8.10.2026 auch
als Abbild unter `ghcr.io/datenwerft`, je per SHA-256-Digest ansprechbar.
Damit ist die Voraussetzung erfüllt, die diese Beschreibung an sich selbst
stellt — und am 11.10.2026 auch eingelöst: Beide Variablen in der `.env` auf
`srv01` tragen einen Digest, und beide sind **zeichengleich** mit denen, die
hier gebaut und gemessen wurden. Die Kette ist damit geschlossen: hier
gebaut, Digest gemessen, genau dieser Digest läuft dort.

Nachprüfbar ist das von aussen **nicht**: Die Pakete sind privat, und ein
Test ohne Token käme nicht an die Registry. Die Digests stehen datiert im
Projektgedächtnis; was auf `srv01` wirklich läuft, sagt dort
`docker compose images` — abgelesen am 11.10.2026.

### Was die Engineering-Konsole zusätzlich braucht

Seit dem 30.10.2026 beschrieben, **seit dem 31.10.2026 eingerichtet bis
auf das GitHub-Token**: Abbild mit dem Konsolen-Code (`554fd02`), `.env`,
`init` mit 2021–2026, `urbancrime_konsole` in der Sicherung, `admin` läuft,
die Tunnel-Route steht hinter derselben Access-Anwendung, und der Takt läuft
alle fünf Minuten aus `crontab`. Offen ist nur das Token (S-6 in
[`intern/offene-punkte.md`](intern/offene-punkte.md)); ohne es legt die
Konsole keine PRs an. Die Schritte:

1. **Die Tunnel-Route** für `urbancrime-admin.datenwerft.ch`, wie oben auf
   `http://traefik:80`. Die Access-Anwendung über `urbancrime-*` deckt sie mit.
2. **Die `.env` des Stapels** um `CF_ACCESS_ISSUER`, `CF_ACCESS_AUD` (aus der
   Access-Anwendung), `ADMIN_ROLE_BINDINGS` (JSON: Access-Subjekt → Rollen),
   `ADMIN_METRICS_TOKEN` und `ADMIN_GITHUB_TOKEN` (nur der Worker liest es;
   Contents, Pull requests Lesen und Schreiben, Actions Lesen).
3. **Den Datenträger `urbancrime_konsole` in die Serversicherung.** Er trägt
   die SQLite-Datenbank mit den Review-Entscheidungen; die lässt sich nicht
   nachrechnen.
4. **Einmal `python -m platform_admin init`** im Worker-Container, dann die
   Takt-Zeile in [`deploy/cron/urbancrime.crontab`](../deploy/cron/urbancrime.crontab)
   einkommentieren. Vorher bricht jeder Takt ab.

Der bisherige Datenlauf bleibt, bis jemand `enable-managed` ausführt. Danach
sperrt [`storage.verwaltet`](../src/crime/storage/verwaltet.py) `run_all` und
`release` für alles ausser dem Worker — der Cron-Datenlauf scheitert dann.
**Der Worker übernimmt ihn ganz** (Entscheidung vom 30.10.2026):

| Datenlauf heute | Worker |
| --- | --- |
| montags 04:30, Delta/Voll/Delta/Delta/frei | [`docker/srv01-konsole-datenlauf.sh`](../docker/srv01-konsole-datenlauf.sh) reiht montags einen Batch ein, mit **derselben** Funktion `mode_for_day` |
| Vorprüfung, Quellen laden | Batch (`orchestration.vorpruefung`, Ingestion-Stufen über `run_all.auswahl`) |
| Silver, Gold, Release | Kandidat, **freigegeben vom Qualitätstor** — geplante Quellenläufe ohne Person, Mapping- und Einstellungsänderungen weiter mit vier Augen |
| Startseite, `pruefe_stand` (seit 1.11.2026 ohne Elasticsearch und Kibana) | Serving nach der Freigabe; `SERVING_BETRIEB=server` lässt die beiden Lader aus |
| Drift, Sicherungssatz | danach; beide fällen den Lauf nicht, wie im Cron (`\|\| echo WARNUNG`) |
| `pipeline_run.json` und Betriebsstand, auch nach einem Fehler | nach jedem Takt, der etwas ausgeführt hat — im Format von `run_all` |
| `compose up -d --wait dashboard` und `start` | **nicht** — im Container gibt es kein Docker; die Dienste laufen `unless-stopped` |

Ein Wächter hält die Liste: Jedes Modul, das `srv01-datenlauf.sh` aufruft,
muss im Worker vorkommen oder mit Grund ausgenommen sein. Umgestellt wird mit
S-10 in [`intern/offene-punkte.md`](intern/offene-punkte.md): `enable-managed`
und im selben Zug die beiden Crontab-Zeilen tauschen.

`ADMIN_GIT_SCHUTZ` steht auf `entwicklung`, bis die Entwicklung abgeschlossen
ist (Entscheidung vom 30.10.2026). Für `produktiv` braucht `main` vorher die
fünf GitHub-Schutzregeln — sonst lehnt die Konsole jeden Merge ab.

### Jupyter liest, und zwar aus dem Release

Drei Auflagen machen aus einem Notebook-Server etwas, das auf einer geteilten
Maschine vertretbar ist.

`data/` wird **schreibgeschützt** eingehängt. Damit kann das Notebook, das
Detroit nach Bronze lädt, strukturell nicht in den echten Bestand schreiben —
der Versuch scheitert am Dateisystem und nicht an einer Absprache. Daneben
liegt ein eigener beschreibbarer Arbeitsbereich, sonst liesse sich kein
Notebook speichern.

Gelesen wird die **selbständige** `analyse.duckdb` aus einem Release (93 MB,
Tabellen darin), nicht `data/serving/analyse.duckdb`. Die trägt 17 Sichten mit
absoluten Pfaden auf den Entwicklungsrechner und ist im Container wertlos —
Abschnitt 9 sagt, warum das so ist und warum es so bleibt. Hereingeholt wird
sie über den Stapellauf:

```bash
docker compose -f docker-compose.srv01.yml run --rm pipeline \
    python -m orchestration.release holen aktuell --nur-datenbank
```

Das Notebook, das Hypothesen prüft, bleibt auf dem Entwicklungsrechner: Es
misst Hardware und startet Neubauten. Auf einer geteilten, auslagernden
Maschine misst es das Rauschen der Nachbarn.

### Das zweite Abbild: JupyterLab und drei Vorlagen

[`Dockerfile.jupyter`](../Dockerfile.jupyter) setzt auf dem Strecken-Abbild
auf, statt eine zweite Abhängigkeitsliste zu führen — die wäre eine zweite
Wahrheit neben `requirements.lock`. Gebaut werden beide nacheinander, und das
Grundabbild kommt als Argument herein — gleich unter der Adresse, unter der es
geschoben wird, damit das Analyse-Abbild nicht auf einem Namen aufsetzt, den es
nur auf dem Entwicklungsrechner gibt.

**Seit dem 14.10.2026 baut das die CI**
([`.github/workflows/abbilder.yml`](../.github/workflows/abbilder.yml)), von
Hand angestossen über *Actions → Abbilder → Run workflow*. Der Workflow baut
beide Abbilder, schiebt sie, holt sie zurück, prüft Plattform und
`GIT_COMMIT` gegen den gebauten Stand und legt die zwei fertigen `.env`-Zeilen
in die Job-Zusammenfassung. Der Lauf trägt sie **nicht** auf `srv01` ein: Wer
den Bau startet, entscheidet auch, wann der Stapel umgestellt wird, und ein
Workflow mit Schreibzugriff auf den Server wäre ein zweiter Weg hinein.

**Auf `srv01` genügt seit dem 16.10.2026 ein Befehl**
([`docker/srv01-abbild-einsetzen.sh`](../docker/srv01-abbild-einsetzen.sh)):

```bash
cd /srv/docker/apps/urbancrime && git pull && docker/srv01-abbild-einsetzen.sh
```

Er schlägt den Digest über die mitwandernde Marke `:aktuell` nach, schreibt
beide Zeilen in die `.env`, zieht die Abbilder, liest `GIT_COMMIT` aus dem
neuen Abbild und startet nur neu, was läuft. `--trocken` zeigt, was geschähe.
Vorher waren es fünf Handgriffe, und der dritte — die `.env` von Hand ändern —
war der, bei dem ein Zeichen verlorengeht.

**Gepinnt bleibt der Digest.** Die Marke dient nur dem Nachschlagen; in die
`.env` schreibt das Skript den konkreten Digest, den es gerade gelesen hat.
Eine Marke lässt sich umhängen, ein Digest nicht — deshalb steht in der `.env`
des Stapels niemals `:aktuell`, und ein Wächter hält das fest.

**Was das Skript nicht tut: bauen.** Den Workflow anzustossen bräuchte ein
GitHub-Token mit `workflow`-Recht auf einer Maschine, die von aussen
erreichbar ist — ein zweites Geheimnis, das mehr kann als Pakete lesen. Das
`read:packages`-Token, das `srv01` ohnehin hat, genügt für alles andere.
Ein Zeitplan fehlt absichtlich — ein Abbildbau ist nur nötig, wenn wirklich
umgestellt wird, und Minuten werden in einem privaten Repository verrechnet.

Von Hand geht es weiter, und so sieht der Weg aus, den der Workflow abkürzt:

```bash
echo $GHCR_TOKEN | docker login ghcr.io -u datenwerft --password-stdin

docker build --platform linux/amd64 \
    -t ghcr.io/datenwerft/urban-crime:<datum> \
    --build-arg GIT_COMMIT=$(git rev-parse HEAD) .
docker build --platform linux/amd64 -f Dockerfile.jupyter \
    -t ghcr.io/datenwerft/urban-crime-jupyter:<datum> \
    --build-arg BASIS=ghcr.io/datenwerft/urban-crime:<datum> .

docker push ghcr.io/datenwerft/urban-crime:<datum>
docker push ghcr.io/datenwerft/urban-crime-jupyter:<datum>

# Der Digest, nicht die Marke, kommt in die .env des Stapels:
docker inspect --format='{{index .RepoDigests 0}}' \
    ghcr.io/datenwerft/urban-crime-jupyter:<datum>
```

**`--platform linux/amd64` ist keine Vorsichtsmassnahme, sondern Pflicht.**
Der Entwicklungsrechner ist ein arm64-Mac, `srv01` läuft auf x86-64
(AMD EPYC Genoa). Ein ohne Plattformangabe gebautes Abbild lässt sich
anstandslos schieben und scheitert erst auf `srv01` beim Start mit
`exec format error` — also nach Bau, Schieben und Holen. Gegenprobe vor dem
Schieben: `docker image inspect --format='{{.Os}}/{{.Architecture}}'`. Beim
Bau von Hand ist das eine Angabe, die man vergisst; in der CI ist es die
Maschine — der Runner ist x86-64 — und die Gegenprobe läuft als eigener
Schritt, der zurückholt statt nur zu bauen und damit in einem Zug belegt, dass
der Digest in der Registry liegt, dass er sich holen lässt und dass
`linux/amd64` drinsteht.

Die Marke trägt ein Datum und ist für Menschen; gepinnt wird der Digest, weil
eine Marke sich umhängen lässt und ein Digest nicht. Die beiden Variablen
stehen samt dieser Begründung in [`.env.example`](../.env.example). Der
Namensraum `ghcr.io/datenwerft` hängt am persönlichen Konto und nicht an der
Organisation des Repositorys; die Pakete sind damit vorgabemäss privat, und
`srv01` braucht ein eigenes Token mit `read:packages`, um sie zu holen.

Dieselbe Trennung ist der Grund, warum die CI ein eigenes Secret braucht:
Das eingebaute `GITHUB_TOKEN` darf nur Pakete des Repository-Eigentümers
schreiben, also unter `ghcr.io/artanmusollaj-ops`. Der Workflow meldet sich
deshalb mit `GHCR_TOKEN` an — demselben Token mit `write:packages`, mit dem
auch der Bau von Hand sich anmeldet, hinterlegt unter *Settings → Secrets and
variables → Actions*. Fehlt es, bricht der Workflow im ersten Schritt ab und
sagt das; er baut nicht erst zwanzig Minuten und scheitert dann an der
Anmeldung.

**Warum es das Abbild überhaupt braucht.** Das Strecken-Abbild taugt nicht
als Notebook-Server: `requirements.lock` trägt `ipykernel` und `nbconvert`,
aber **keinen Server**, und `.dockerignore` hält `notebooks/` draussen — für
ein Abbild, das wöchentlich unbeaufsichtigt durchläuft, beides richtig.
Dazugelegt wird deshalb `jupyterlab==4.6.4`, gepinnt wie alles andere, und
zwar mit `-c requirements.lock`: Der Server darf seine Abhängigkeiten
auflösen, aber keinen Pin verschieben. Ohne diese Nebenbedingung zöge pip
`jinja2`, `tornado`, `traitlets` oder `nbformat` mit, und das Analyse-Abbild
rechnete mit anderen Paketen als die Strecke, deren Zahlen es zeigt.

**Mit kommen die drei lesenden Notebooks** — `34_gold_sternschema`,
`35_kontrollen` und `37_quellbewegung`. `35` läuft ohne alles, `34` und `37`
brauchen einen vollständig aufgebauten, ausdrücklich gewählten Bestand aus
Bronze/Silver beziehungsweise Silver/Gold. Eine Ergebnis-Release-Datenbank
allein genügt für ihre Pipeline-Gegenproben nicht. Netz braucht keines, und
keines schreibt in den Bestand. **Nicht mit kommt `36_hypothesen`**: Es misst
Hardware und startet Silber-, Gold- und Serving-Neubauten als Unterprozesse,
und 768 MiB sprengt es dabei (E9). Die `.dockerignore` stellt die drei
einzeln frei und nicht den Ordner — damit liegt `36_hypothesen` nicht einmal
im Baukontext.

**Die drei sind Vorlagen, keine Arbeitskopien.** Sie liegen im Abbild unter
`/vorlagen`, nur lesbar, und das Einstiegsskript
[`docker/jupyter-einstieg.sh`](../docker/jupyter-einstieg.sh) legt sie
**einmal** in den Arbeitsbereich, solange dort nichts liegt. Liegt dort etwas — und nach dem
ersten Start ist das der Normalfall —, fasst es nichts an. Wer eine Vorlage
bearbeitet, bearbeitet damit seine Kopie: Die Notebooks im Repository sind
versionierte Artefakte, die zwei Testdateien halten, und eine im Browser
geänderte Fassung hielte niemand mehr — beim nächsten Abbildwechsel wäre sie
weg. Eigene Analysen liegen im selben Arbeitsbereich und überleben Neustart
und Abbildwechsel, weil er ein benannter Datenträger ist.

**Der Arbeitsbereich ist `/app/arbeit` und JupyterLabs Wurzel.** Beides hat
einen Grund. Die Wurzel, weil unter `/app` daneben `config/`, `src/` und der
ganze eingehängte Bestand liegen und nicht in den Dateibaum eines Browsers
gehören; sie steht in
[`docker/jupyter_server_config.py`](../docker/jupyter_server_config.py) und
nicht nur im Startbefehl, damit ein überschriebenes `command` sie nicht
aufhebt. Und
`/app/arbeit` statt `/arbeit`, weil die Notebooks ihre Projektwurzel beim
Arbeitsverzeichnis und **eine Ebene darüber** suchen, erkannt an `config/`:
Von `/app/arbeit` aus finden sie `/app`, von `/arbeit` aus nichts — jedes der
drei bräche in seiner ersten Zelle ab. `tests/test_jupyter_abbild.py` misst
das an den Notebooks nach, statt es zu behaupten.

**Kein Geheimnis im Abbild.** Kein Token, keine S3-Schlüssel, kein
`CENSUS_API_KEY`: Das Token kommt als `JUPYTER_TOKEN` aus der `.env` des
Stapels, und ein lesender Analysedienst braucht den Bucket nicht — er liest
für Ergebnisabfragen die selbständige Datenbank aus dem Release und für die
belegenden Notebooks den vollständigen lokalen Job-Datenbestand. Der Container läuft als root,
weil der Verbund keinen Benutzer setzt, und die Konfiguration erlaubt das
ausdrücklich; ohne diese Zusage verweigert `jupyter-server` den Start. Setzt
der Verbund doch einen Benutzer, bleiben Arbeitsbereich und `$HOME`
beschreibbar — beide stehen auf `0777`, weil ein Abbild, das nur für eine uid
funktioniert, genau dann klemmt.

**E-5: vollständige Job-Daten nur lesend, Sperren gemeinsam.** Die Konsole baut
isoliert unter `/app/data/admin/jobs/<Job-ID>/data`. Ein erfolgreicher Aufbau
schreibt `.analyse/stand.json` mit Job-/Run-ID, Code-Stand, Schichten, Prüfsummen
und Release-Zuordnung. Jupyter wählt den Bestand mit `CRIME_ANALYSIS_ROOT`.
Die Kandidatenkennung belegt keine Review-Freigabe; diese muss anhand der
Konsolenentscheidung zugeordnet werden. Fehlende oder veränderte Dateien
werden vor der ersten Notebook-Abfrage abgewiesen.

Die Compose-Datei teilt das beschreibbare Volume `datensperren` unter
`/app/datensperren` zwischen Pipeline, Worker und Jupyter. `DATA_LOCK_ROOT`
zeigt in allen drei Diensten dorthin. Die Betriebssystem-Sperre gilt pro
absoluter Datenwurzel und für die ganze Analysesitzung; das Daten-Volume selbst
bleibt in Jupyter nur lesend. Von `konsole` erhält Jupyter ausschliesslich
den nur lesenden Subpath `jobs` unter `/app/data/admin/jobs`, nicht die
Kontrolldatenbank oder Worker-Tokens im Elternordner.

Vor dem ersten Jupyter-Start müssen zwei Verzeichnisse existieren: `jobs/`
im konsole-Volume nach einem erfolgreichen Aufbau und der leere Mountpunkt
`admin/jobs` im arbeitsdaten-Volume. Ohne letzteren kann Docker den Unter-Mount
unter dem nur lesenden `/app/data` nicht anlegen. Der einmalige Befehl und der
Sitzungsablauf stehen in [der Betriebsanleitung](intern/notebook-analysesitzungen.md).
Ein Abbildwechsel aktualisiert bestehende Notebook-Arbeitskopien nicht;
für die Abnahme die neuen Vorlagen in einen eigenen Arbeitsordner kopieren.

Die [lokale Docker-Prüfung vom 31.10.2026](intern/e5-pruefnachweis.md) bestätigt
vollständige Notebook-Ausführung, gegenseitige Sperre, Freigabe und Schreibschutz
mit einer geprüften Kopie des lokalen Aufbaus. Der echte Konsolenablauf auf srv01
ist damit noch nicht abgenommen.

### Die Einstiegsseite wird ausgeliefert, nicht eingehängt

Seit dem 12.10.2026 trägt die Beschreibung einen fünften Dienst: ein nginx
unter `urbancrime-start.datenwerft.ch`, das
[`docs/einstieg.html`](einstieg.html) ausliefert (FR-31). Die Seite stand
vorher nur im Repository — erzeugt, geprüft, und für niemanden erreichbar, der
das Repository nicht hat.

**Woher die Datei kommt, ist die eigentliche Entscheidung.** Ein Bind-Mount
des Repositorys zeigte das Release des letzten `git pull` und nicht das
geladene — und wäre im Serverstapel der einzige Einhängepunkt seiner Art. Der
Weg ist deshalb derselbe wie bei `arbeitsdaten`: Der Stapellauf **schreibt**
in einen benannten Datenträger, der Dienst **liest** ihn mit `:ro`. Ein
eigener Datenträger, nicht `arbeitsdaten`: nginx liefert aus seiner Wurzel
alles aus, was darin liegt, und `arbeitsdaten` trägt den ganzen Arbeitsraum
samt Release. Nach dem Datenlauf trägt er genau unsere eine Datei — weil der
Lauf ihn vorher leert, siehe unten.

Geschrieben wird sie am Ende des Datenlaufs, nach `holen aktuell --einsetzen`
und vor `pruefe_stand`:

```bash
find /app/startseite -mindepth 1 -delete
python -m serving.build_einstieg --adressen server \
    --ziel /app/startseite/index.html
```

`--adressen server` ist die einzige Umschaltung daran. Ohne sie stünden auf
der ausgelieferten Seite Verweise auf `localhost:15601` — richtig auf dem
Entwicklungsrechner und auf dem Server ein Knopf, der im Rechner des Lesenden
landet. Mit ihr stehen dort `urbancrime-<dienst>.datenwerft.ch`, und zwar nur
für das, was wirklich geroutet ist. Elasticsearch bekam dort nie einen Knopf,
weil es nach FR-11 nicht geroutet war; seit dem 1.11.2026 fehlen
Elasticsearch und Kibana auf der Serverseite ganz, und das Dashboard steht an
ihrer Stelle. Der Erzeuger liegt deshalb seit
demselben Tag unter `src/crime/serving/build_einstieg.py` und nicht mehr unter
`tools/`: `.dockerignore` hält `tools/` aus dem Baukontext, im Abbild gab es
ihn also nicht.

**Der Healthcheck greift nach unserer Seite, nicht nach HTTP 200.** Der Grund
ist am 12.10.2026 am laufenden Docker nachgestellt worden: Docker befüllt
einen leeren benannten Datenträger beim ersten Start **aus dem Abbild**, und
das `:ro` auf der lesenden Seite verhindert das nicht. Danach liegen nginx'
eigene `index.html` (896 Bytes, *Welcome to nginx!*) und `50x.html` darin,
`curl -fs` antwortet mit 200 — ein Healthcheck darauf meldete den Dienst
**gesund**, während er hinter Access die Willkommensseite von nginx
auslieferte. Geprüft wird deshalb ein Kennzeichen unserer Seite
(`serving.build_einstieg` aus ihrer Fusszeile), und der Datenlauf **leert den
Datenträger**, bevor er schreibt — sonst bliebe `50x.html` auch danach liegen.

**Der Nachweis fehlt hier noch ganz.** Der Dienst steht in der Beschreibung,
und das ist alles: Seine Tunnel-Route ist am 12.10.2026 **nicht** angelegt,
der Stapel auf `srv01` kennt ihn noch nicht, und ohne einen Datenlauf trägt
der Datenträger keine Seite von uns — der Dienst ist dann `unhealthy` und
behauptet nichts. Was die Beschreibung zusichert, halten
`tests/test_srv01_compose.py` und `tests/test_srv01_datenlauf.py`; was auf
`srv01` steht, sagt dort `docker compose ps`.

### Der Stapellauf ist kein Dienst

Der Pipeline-Container läuft einmal durch und endet. Er trägt **kein**
`ports:`, **kein** Traefik-Label und **nie** `restart: unless-stopped` — damit
würde aus einem Wochenlauf eine Dauerschleife, die jede Runde neue
Bronze-Läufe anhäuft. Gesetzt ist `on-failure:2`: Ein abgebrochener
Netzzugriff soll nicht den ganzen Lauf verlieren, aber ein Lauf, der dreimal
scheitert, hat ein Problem und keinen vierten Versuch.

Angestossen wird er von Hand oder vom Zeitplan:

```bash
docker compose -f docker-compose.srv01.yml run --rm pipeline
```

Der Zeitplan selbst, die Meldung bei Rot und die Rücknahme eines falsch
publizierten Standes sind nicht Teil dieser Beschreibung.

### Die Geheimnisse

Keines steht in der Compose-Datei. Jede Variable ist dort **ohne Wert**
aufgeführt — in Compose heisst das *hole ihn aus der Umgebung* —, und geholt
wird er aus der ignorierten `.env` des Stapels. Fehlt eine Variable dort,
erreicht sie den Container nicht; der Schlüssel für Census fällt dann vor dem
Lauf auf und nicht bei Stufe 5 von 14. Ein Test prüft beide Richtungen: dass
keine Variable mit einem Namen wie `…KEY` oder `…TOKEN` einen Wert trägt, und
dass die drei, die der Lauf braucht, überhaupt genannt sind.

Eine Ausnahme von „ohne Wert": Der Ablagemodus steht fest im Text, als `s3`.
Er ist kein Geheimnis, und ein Serverlauf, der versehentlich in `local` liefe,
publizierte nichts und sähe dabei grün aus.
