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
Einordnung in den Lebenszyklus in [`ln1_konzept.md`](ln1_konzept.md),
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
`tracts.geojson` und seit dem 17.9.2026 die vier Vergleichstabellen aus
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
`orchestration.aufraeumen` räumt ausschliesslich lokal auf — SeaweedFS wird
davon nie berührt.

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
| `read_text(*teile)` / `write_text(text, *teile)` | kleine Dateien |
| `publish_to_shared_storage(*teile)` | ein Verzeichnis publizieren |

Auf dem `Storage`-Objekt zusätzlich: `laeufe()`, `tabellen()`,
`publish_run()`, `publish_table()`, `publish_files()`, `vergleiche_stand()`,
`entfernter_stand()`, `relativ()`, `mit_wurzel()`.

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
