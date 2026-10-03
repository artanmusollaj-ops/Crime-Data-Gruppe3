# Architektur: was gebaut ist, und wohin es geht

**Stand: 18.9.2026.** Dieser Text ist als Kapitel für den Leistungsnachweis
gedacht. Er hat zwei Teile, und die Trennung ist die wichtigste Aussage darin:

* **Teil A — die Ist-Architektur.** Was läuft, mit Zahlen, die nachgerechnet
  werden können. Jede Angabe hier steht unter einem Test.
* **Teil B — die Ziel-Architektur.** Was für LN2 und den Betrieb geplant ist.
  Nichts davon ist gebaut, und der Text sagt an jeder Stelle, was es kosten
  würde und was noch offen ist.

Wer die beiden Teile vermischt, schreibt eine Absichtserklärung und nennt sie
Dokumentation. Deshalb stehen sie getrennt.

---

# Teil A · Die Ist-Architektur

## A.1 Die Leitidee: eine Schicht, eine Zuständigkeit

Die Strecke führt zwei unvergleichbare Quellen in eine vergleichbare Tabelle
über. Sie tut das in Schichten, und jede Schicht hat **genau eine** Aufgabe:

```text
        Chicago ─┐
        Detroit ─┤
  Census TIGER ──┼──▶  raw ─▶ bronze ─▶ silver ─▶ gold ─▶ serving ─▶ releases
    Census ACS ──┤       │       │         │        │        │           │
     NOAA GHCN ──┘    Beweis  geparst   gedeutet  Stern   Abfragen   freigegeben
```

| Schicht | Aufgabe | Was sie ausdrücklich **nicht** tut | Grösse |
| --- | --- | --- | ---: |
| **raw** | die Antwort der Quelle, Byte für Byte, mit SHA-256 | nichts deuten, nichts umformen | 130 MB |
| **bronze** | Parquet mit gepinntem Schema, Originaltypen | nichts deuten; Unerwartetes nach `_extra` statt in den Papierkorb | 124 MB |
| **silver** | deuten: Typen, Einheiten, Zeitzonen, NIBRS, Raum | nichts wegwerfen — Lücken werden gekennzeichnet, nicht gefiltert | 47 MB |
| **gold** | Sternschema, eine Zeile je **Tat** | nicht aggregieren | 15 MB |
| **serving** | abfragbar machen: Sichten, vier Vergleichstabellen, Karte | nicht der Bestand sein | 0,9 MB |
| **releases** | ein freigegebener Gesamtstand unter einer Kennung | sich nie ändern | 121 MB |

**Der Stand in Zahlen** — der Referenzstand, auf den sich alle
Abgabedokumente beziehen:

| | |
| --- | ---: |
| `silver/crime_offense` | 348'329 Zeilen (Detroit: eine Anklage) |
| `gold/fact_offense` | **345'091** Zeilen (eine Tat) |
| Chicago | 251'517 Delikte · 2'661'953 Einwohner · **94,5** je 1'000 |
| Detroit | 84'761 Delikte · 638'635 Einwohner · **132,7** je 1'000 |

**Warum raw und bronze getrennt sind.** Raw ist das Beweisstück: Ein Delta-Lauf
hält Datensätze so fest, wie sie in diesem Moment waren, und das lässt sich
später nicht rekonstruieren. Bronze ist daraus abgeleitet und jederzeit neu
erzeugbar. Diese Trennung kostet 130 MB und ist der Grund, warum sich jede Zahl
bis zur gzip-Datei zurückverfolgen lässt.

**Warum Gold nicht aggregiert.** Notebook 34 hat beide Bauweisen gebaut und
gemessen: Bei 345'091 Zeilen liegt jede realistische Frage direkt auf dem Stern
im einstelligen Millisekundenbereich. Ein vorberechneter Würfel spart nichts,
was ein Mensch bemerkt, und kostet drei Fragen, die er nicht mehr beantwortet.
Die Entscheidung ist ein **Messergebnis**, keine Stilfrage.

### Drei Ladestrategien für fünf Quellen

Die fünf Quellen ändern sich unterschiedlich, und die Ladestrategie folgt dem
Änderungsverhalten — nicht der Bequemlichkeit:

| Quelle | Strategie | Warum |
| --- | --- | --- |
| Chicago | **Delta** über `updated_on`, 14 Tage Überlappung | Ein Wasserzeichen sagt, ab wann; die Überlappung fängt Nachmeldungen |
| Detroit | **Delta** über `updated_at` im Tatjahrgang, 14 Tage Überlappung | Derselbe Weg, aber mit zwei Bedingungen: **55,9 %** des Jahrgangs 2024 wurden *mehr als ein Jahr nach der Tat* noch geändert — ein Delta nach Tatdatum verpasst genau diese Korrekturen |
| TIGER, ACS | **eingefroren** | Eine feste Vintage; ein erneutes Laden wäre ein anderer Jahrgang, kein neuerer Stand |
| NOAA | **Vollschnappschuss je Station** | Die Quelle liefert den ganzen Verlauf; der jüngste Lauf löst den vorigen ab |

Die letzte Zeile ist der Grund, warum die Publish-Sperre am 17.9.2026 umgebaut
werden musste: Sie hielt einen **abgelösten** Lauf für einen **fehlenden**.

**Detroits zweite Bedingung ist die eigentliche Arbeit.** Die 55,9 % sagen
nicht, dass kein Delta geht, sondern worauf es gehen muss. Gemessen über vier
Schnappschüsse: 1'270 Zeilen änderten sich inhaltlich, **jede einzelne** mit
einem neuen `updated_at`, keine ohne. Der Jahresfilter bleibt auf der Tatzeit —
sonst kämen Fälle aus jedem Tatjahr —, ausgewählt wird darin nach
Änderungszeit. Die vier Zeilen ohne Stempel kommen über `OR updated_at IS NULL`
immer mit. Seit dem 18.9.2026 lädt ein Detroit-Lauf so **3'184 statt 88'686
Zeilen**; der erste Lauf auf einem leeren Rechner bleibt ein Vollschnappschuss.

## A.2 Der Code: zehn Pakete, gerichtete Abhängigkeiten

```text
  Fundament   manifeste, storage          kennt keine Schicht über sich
                     ▲
  Ingestion   chicago_pipeline, detroit_pipeline,
              census_pipeline, weather_pipeline      je Quelle ein Paket
                     │
  Deuten      silver_pipeline
                     │
  Stern       gold_pipeline
                     │
  Abfragbar   serving
                     │
  Steuerung   orchestration               Reihenfolge, Aufräumen, Drift, Release
```

Zwei Regeln halten das zusammen, und beide sind getestet:

1. **Keine Zyklen.** `tests/test_architekturbilder.py` liest den Importgraphen
   aus dem AST und fällt, wenn zwei Pakete einander brauchen.
2. **Das Fundament hängt an nichts.** `manifeste` und `storage` dürfen keine
   Schicht über sich importieren. Diese Regel hat beim Bau des Release-Moduls
   sofort angeschlagen: Der erste Entwurf liess `storage.release` die
   DuckDB-Datei bauen — ein Import aus `serving` in einem Fundament. Seither
   reicht `orchestration.release` den Haken herein, und `storage` kennt nur
   Dateien.

Die beiden Architekturbilder in [`architektur.md`](architektur.md) werden
**aus dem Code erzeugt**, nicht gezeichnet. Ein Paket, das dazukommt, erscheint
von selbst; eine Zahl im Bild, die nicht mehr stimmt, lässt einen Test fallen.

## A.3 Orchestrierung: vierzehn Stufen, Abbruch beim ersten Fehler

`orchestration.run_all` fährt die Strecke in vierzehn Stufen:

| Gruppe | Stufen | |
| --- | ---: | --- |
| ingestion | 6 | chicago, detroit, tiger_tract, tiger_place, acs, noaa |
| silver | 4 | tract, place, weather_day, crime_offense |
| gold | 1 | die fünf Sterntabellen in einem Zug |
| serving | 3 | comparison, analyse_db, tracts_geojson |

Die Reihenfolge ist keine Kosmetik: `silver/tract` braucht beide
Census-Quellen, `crime_offense` zusätzlich `tract`, und ohne `tiger_place`
bekäme `dim_tract` keine Stadtzuordnung — was nicht scheitern würde, sondern
eine Rate ohne Nenner lieferte. **Die erste gescheiterte Stufe bricht die Kette
ab**, denn jede weitere baute sonst auf einem halben Stand.

Der Lauf schreibt `data/pipeline_run.json`: welche Stufen liefen, auf welchen
Bronze-Läufen das Ergebnis ruht, wie alt jede Quelle ist, was von SeaweedFS
geholt wurde, ob ein Release entstand — und einen Fingerabdruck über die
Eingaben. Zwei Läufe auf demselben Stand tragen denselben Abdruck.

**Kein Airflow, und das ist begründet.** Bei fünf Quellen und vier
Batch-Pipelines wäre ein Scheduler Aufwand ohne Erkenntnisgewinn. Was fehlt,
ist nicht die Maschinerie, sondern der Anstoss: Ausserhalb des wöchentlichen
Datenlaufs startet nichts von selbst.

## A.4 Ablage: drei Betriebsarten, ein Adressraum

Alles Persistierte wird relativ adressiert —
`bronze/city=chicago/ingest_date=…/run_…/part-0001.parquet`. Daraus macht das
Backend `data/…` oder `s3://urban-crime/…`; die Struktur ist in allen
Betriebsarten dieselbe.

| Modus | Lesen | Schreiben | Holt Raw/Bronze | Release |
| --- | --- | --- | --- | --- |
| `local` | `data/` | `data/` | — | nur auf Wunsch, bleibt lokal |
| `hybrid` | lokal zuerst, sonst SeaweedFS | lokal, prüfen, **dann** publizieren | ja, vor jedem Lauf | nach jedem grünen Lauf |
| `s3` | immer SeaweedFS | lokal als Arbeitsraum, publizieren, lokale Kopie entfernen | von Hand | nach jedem grünen Lauf |

Die Zusagen dahinter, jede mit Test:

* **Läufe sind unveränderlich.** Liegt ein Objekt schon anders oben, ist das
  ein Fehler, kein Überschreiben. Verglichen wird Grösse **und** Prüfsumme —
  gleiche Grösse allein galt bis zum 15.9. als identisch, und drei Bytes `NEU`
  waren damit dasselbe wie drei Bytes `ALT`.
* **Publiziert wird zuletzt das Manifest.** Es ist das Zeichen, dass ein Lauf
  ganz oben ist.
* **Kein Rückschritt.** Ein älterer eigener Stand verdrängt keinen neueren.
  Seit dem 17.9. zählt dabei, ob ein Bronze-Lauf **erreichbar** ist, nicht ob
  der Bau ihn benutzt hat — NOAA liefert Vollschnappschüsse, und ein
  abgelöster Lauf ist nicht verloren.
* **Ein Release ist der ganze Stand oder keiner.** Fehlt eine der neun
  Tabellen oder die Karte, entsteht keines.

## A.5 Herkunft: jede Zahl hat einen Weg zurück

Jeder Lauf und jede Tabelle trägt ein `manifest.json` mit:

| Feld | Was es beantwortet |
| --- | --- |
| `derived_from` | woraus dieser Stand entstand — bis zu den Bronze-Läufen und den Crosswalks mit SHA-256 |
| `input_fingerprint` | derselbe Eingabestand, derselbe Abdruck |
| `contract_version` | **was** geladen oder gedeutet wird — Zeitfenster, Feldauswahl, Granularität |
| `code_version` | **welcher Commit**, und ob der Arbeitsbaum sauber war |
| `checks` | die Zahlen, die der Bau über sich selbst festgestellt hat |

Der Unterschied zwischen `contract_version` und `code_version` ist die
forensische Hälfte: *„Ab wann wurde anders geladen?"* ist damit eine Abfrage —
der erste Lauf mit der höheren Zahl — und kein Eintrag, den jemand pflegen
muss. Ein Register in [`AENDERUNGEN.md`](intern/AENDERUNGEN.md) sagt, was jede Zahl
bedeutet; ein Test hält Code und Register zusammen.

[`eine-zahl.md`](eine-zahl.md) rollt eine einzelne Zahl — Chicagos 94,5 je
1'000 — über sieben Schichten rückwärts auf, bis zur gzip-Datei.

## A.6 Qualität: 42 Kontrollen, davon 28 mit Abbruch

Die Kontrollen sind in zwei Arten geteilt, und die Unterscheidung ist eine
Entscheidung, keine Eigenschaft der Daten:

| | Was sie tut | Wann sie richtig ist |
| --- | --- | --- |
| **hart** | bricht ab, nichts wird geschrieben | wenn etwas **still** schieflaufen kann: ein doppelter Schlüssel, ein verlorener Fall |
| **weich** | schreibt das Ergebnis in eine Spalte und zählt | wenn etwas **unvollständig** ist: eine fehlende Koordinate, eine unsichere Zuordnung |

Eine harte Kontrolle auf fehlende Koordinaten hiesse, dass Chicagos Jahrgang
gar nicht erst entsteht — 2'115 Delikte tragen keine. Eine weiche macht die
Lücke **abfragbar** statt unsichtbar. Hart wird es erst dort, wo die Lücke die
Zahl unbrauchbar machte: beim **Publish-Gate** in Gold, der einzigen Kontrolle,
die eine Veröffentlichung verhindert.

[`notebooks/35_kontrollen.ipynb`](../notebooks/35_kontrollen.ipynb) führt jede
Kontrolle an einem Fall vor — einmal mit Daten, die sie durchlässt, und einmal
mit Daten, die sie fangen soll.

## A.7 Prüfung: was wo läuft

| Wo | Was | Wann |
| --- | --- | --- |
| **Pull Request** | 1'507 Tests ohne Netz und Schlüssel, Linux und Windows, Python 3.11 und 3.13, `ruff` davor | bei jedem Push |
| **Frischer Klon** | 1'176 davon — die übrigen 27 brauchen gebaute Daten; 71 Referenzstand-Wächter sind abgewählt | |
| **Datenlauf** | montags: alle fünf Quellen laden, die Strecke bauen, die ganze Suite, acht Notebooks ausführen | wöchentlich |
| **Referenzstand** | 70 Wächter halten dokumentierte Zahlen gegen Parquet | lokal, nicht im Datenlauf |

Der letzte Punkt ist die interessanteste Entscheidung: Die Quellen bewegen
sich. Ein Test, der die dokumentierte Zahl gegen den frischen Stand hält, wäre
im Datenlauf **jede Woche rot**, und ein Alarm, der immer klingelt, ist keiner.
Deshalb misst `orchestration.drift` stattdessen den **Abstand** — und wird rot
erst über einer Toleranz, die das ausdrückt, was auf einer Folie stünde: eine
Rate je 1'000 bewegt sich um ≥ 0,1, eine Zeilenzahl um > 1 %.

## A.8 Was heute wo läuft

```text
Laptop (macOS)                     GitHub Actions                SeaweedFS (S3)
  ├─ die ganze Strecke               ├─ Tests je Pull Request      ├─ raw, bronze
  ├─ data/ als Arbeitskopie          ├─ Datenlauf montags          ├─ silver, gold
  ├─ analyse.duckdb (Sichten)        └─ Code-Referenz als          └─ releases/
  └─ Notebooks                          Artefakt                       + AKTUELL.json
```

Das ist der ehrliche Stand: **eine Entwicklungsmaschine, ein CI-Dienst, ein
Objektspeicher.** Kein Server, kein Dienst, der ständig läuft, keine
Oberfläche ausser Notebooks und der DuckDB-Konsole. Genau hier setzt Teil B an.

---

# Teil B · Die Ziel-Architektur

**Nichts in diesem Teil ist gebaut** — mit einer Ausnahme, die seit dem
28.9.2026 gilt und hier benannt gehört, statt den Satz aufzuweichen: Ein
`docker-compose.yml` für die drei **Analysedienste** (ClickHouse,
Elasticsearch, Kibana) existiert und läuft lokal, siehe README 2.6. Das ist
der Verbund auf dem Entwicklungsrechner, nicht der Betrieb: kein Server, kein
Tunnel, keine Anmeldung, und die Pipeline selbst ist weiterhin ein Skript.

Ansonsten beschreibt dieser Teil, wie die Plattform für LN2 und einen echten
Betrieb aussehen soll, und nennt zu jedem Baustein, was er löst und was er
kostet.

## B.1 Das Bild

```text
                        Internet
                           │
                  ┌────────▼────────┐
                  │   Cloudflare    │  Zugang, Anmeldung, WAF
                  │  Access + WAF   │  kein offener Port am Server
                  └────────┬────────┘
                           │  Tunnel (ausgehend aufgebaut)
   ════════════════════════▼════════════════════════════════════
   Privater Server · Docker Compose
     ├─ homepage        Übersicht aller Dienste, eine Startseite
     ├─ admin-web       eigene Oberfläche: Läufe, Releases, Freigabe
     ├─ elasticsearch   Auswertungsindex, aus Gold gespeist
     ├─ kibana          Exploration, Karten, Volltext
     ├─ grafana         Betriebsüberwachung
     ├─ pipeline        die Strecke als Container, zeitgesteuert
     └─ backup          täglich und wöchentlich
   ════════════════════════╤════════════════════════════════════
                           │
                  ┌────────▼────────┐
                  │   SeaweedFS     │  raw, bronze, silver, gold, releases
                  └─────────────────┘  bleibt die Quelle der Wahrheit
```

## B.2 Betrieb: die Strecke als Container

**Was.** Jede Komponente als Docker-Image, zusammengehalten von einem
Compose-Verbund. Die Pipeline selbst wird ein Container, der zeitgesteuert
läuft, statt eines Skripts, das jemand auf seinem Laptop startet.

**Halb gebaut.** Der Compose-Verbund gibt es für die Analysedienste; sie
starten mit einem Befehl und finden einander über ein eigenes Netz. Was fehlt,
ist der Schritt, um den es hier eigentlich geht: **ein Image für die Strecke
selbst.** Solange das nicht steht, ist der Verbund eine Bequemlichkeit beim
Entwickeln und keine Betriebszusage.

**Was es löst.** Heute läuft die Strecke auf genau einer Maschine, und ihre
Abhängigkeiten sind ein `requirements.lock` plus die Hoffnung, dass der
richtige Python-Interpreter im `PATH` steht. Ein Image macht daraus eine
Zusicherung — und ist zugleich die Voraussetzung für alles Weitere in diesem
Teil.

**Was es kostet.** Die Ingestion braucht Schlüssel (`CENSUS_API_KEY`,
`SOCRATA_APP_TOKEN`, S3) — im Container kommen sie aus dem Secret-Mechanismus
der Umgebung, nicht aus einer eingebackenen `.env`. Das ist der Punkt, an dem
ein Container-Aufbau am ehesten leise falsch wird.

**Offen:** ob die Notebooks mit in den Verbund gehören (JupyterLab als
Dienst) oder Entwicklungswerkzeug auf dem Laptop bleiben.

## B.3 Zugang und Sicherheit: kein offener Port

**Was.** Der Server ist aus dem Internet **nicht direkt erreichbar**. Ein
Cloudflare-Tunnel wird vom Server aus nach aussen aufgebaut; eingehend ist
nichts offen. Die Anmeldung übernimmt Cloudflare Access — wer die Dienste
sieht, entscheidet eine Richtlinie dort, nicht ein Passwort im Container.

**Was es löst.** Heute gibt es nichts zu schützen, weil nichts läuft. Sobald
Kibana, Grafana und eine Admin-Oberfläche stehen, wäre jeder offene Port eine
Angriffsfläche — und die drei Dienste bringen je ein eigenes, schwaches
Benutzerkonzept mit. Ein Tunnel plus ein zentrales Zugangstor ersetzt drei
halbe Lösungen durch eine ganze.

**Was es kostet.** Eine Abhängigkeit von einem Anbieter, und die Anmeldung
funktioniert nur, solange Cloudflare erreichbar ist. Am 17.9.2026 hat das
Projekt genau erlebt, wie sich so etwas anfühlt: `s3.datenwerft.ch` war von
einem Hochschulnetz aus stundenlang nicht erreichbar, weil ein Gerät auf dem
Weg den Hostnamen im TLS-Handshake mitlas und die Verbindung zurücksetzte —
nachgewiesen dadurch, dass dieselbe IP mit einem anderen Hostnamen im
ClientHello sofort antwortete. Ein Tunnel verschiebt diese Abhängigkeit, er
beseitigt sie nicht.

**Offen:** ob der Zugang für die Prüfenden der Semesterarbeit über Cloudflare
läuft oder ob es dafür einen zweiten, einfacheren Weg braucht.

## B.4 Auswertung: Elasticsearch — und der Widerspruch, der aufzulösen ist

**Der Widerspruch, offen benannt.** [`ausblick.md`](ausblick.md) Abschnitt 5
hat OpenSearch geprüft und verworfen: *„die falsche Form, nicht die falsche
Grösse — unsere Fragen sind Aggregationen über ein Sternschema, und das ist
SQLs Heimat."* Diese Bewertung war richtig **für die Frage, die dort gestellt
wurde**: Ersetzt es DuckDB als Abfrageschicht? Nein.

**Die Frage ist jetzt eine andere.** Elasticsearch kommt nicht als Ersatz für
den Stern, sondern als **Serving-Index neben ihm** — und dafür sprechen drei
Dinge, die DuckDB nicht leistet:

1. **Kibana ist eine fertige Oberfläche.** Zeitreihen, Karten, Facetten,
   Filter — ohne dass wir ein Dashboard bauen. Für die Tract-Umrisse
   (`tracts.geojson`, 1'055 Flächen) und die Koordinaten je Tat ist die
   Kartendarstellung sofort da.
2. **Volltext über die Beschreibungen.** Das ist keine hypothetische
   Anforderung: Gemessen tragen **23,3 % der Chicagoer Zeilen** eine
   Beschreibung, die für sich genommen mehrdeutig ist — `SIMPLE` steht
   31'565-mal und meint einmal Körperverletzung, einmal Bedrohung. Die
   Mapping-Prüfung ist genau die Aufgabe, für die Volltext und Facetten
   gebaut sind.
3. **Mehrere gleichzeitige Nutzer.** Eine DuckDB-Datei ist für einen Leser
   gedacht; ein Index ist ein Dienst.

**Die Bedingung, unter der das trägt.** Elasticsearch ist ein **abgeleiteter
Index, kein Bestand** — gespeist aus `gold/fact_offense` und den vier
Vergleichstabellen, jederzeit neu aufzubauen, versehen mit der Release-Kennung,
aus der er stammt. Die Quelle der Wahrheit bleibt Parquet. Ohne diese Regel
entstünde genau das, was das Projekt an drei Stellen verhindert: eine zweite
Wahrheit mit eigenem Alter.

**Was es kostet.** Ein Index verdoppelt die Daten und altert, sobald ein neues
Release entsteht — es braucht also einen Neuaufbau je Release und eine sichtbare
Angabe, welchen Stand der Index zeigt. Dazu Speicher: Elasticsearch braucht
für 345'000 Dokumente mit Geo- und Textfeldern erfahrungsgemäss ein Mehrfaches
der 15 MB Parquet.

**Offen:** ob die Aggregationen für das Dashboard aus Elasticsearch kommen oder
weiterhin aus den vorberechneten Vergleichstabellen. Beides geht; die Antwort
entscheidet, wie viel Logik doppelt existiert.

## B.5 Oberflächen: Homepage, Admin, Grafana

**homepage** — eine Startseite, die alle Dienste mit Status auflistet. Klein,
aber sie beantwortet die Frage, die bei einem Verbund aus sechs Containern
zuerst kommt: *Was läuft hier eigentlich, und wo?*

**admin-web** — die eigene Oberfläche, und der einzige Teil, der wirklich
gebaut werden muss. Was sie können soll:

| | |
| --- | --- |
| Läufe | welcher Lauf wann, mit welchem Ergebnis, auf welchen Quellen |
| Releases | welche es gibt, welches `AKTUELL` ist, Prüfsummen |
| Freigabe | ein Release zum aktuellen machen — der Handgriff, der heute ein Befehl ist |
| Drift | wie weit der dokumentierte Stand vom gebauten entfernt ist |
| Qualität | `partition_quality` je Stadt und Monat |

Das meiste davon liest nur Manifeste — die Daten dafür liegen bereits vor, in
`pipeline_run.json`, `release.json` und den Tabellen-Manifesten. Das ist der
Grund, warum diese Oberfläche überschaubar ist: Sie zeigt, was die Strecke
ohnehin aufschreibt.

**grafana** — Betriebsüberwachung: läuft der Lauf, wie lange dauert er, wie
alt ist die jüngste Quelle, wie viel liegt in welcher Schicht. Heute gibt es
dafür **keine Alarmierung ausser einem roten CI-Lauf**; das ist die grösste
offene Lücke im Betrieb.

**Was es kostet.** Drei Oberflächen sind drei Dinge, die gepflegt werden
wollen — und zwei davon (homepage, Grafana) zeigen nur, was ohnehin
aufgeschrieben wird. Der Nutzen liegt fast ganz bei `admin-web`; die anderen
beiden sind billig, weil sie nichts Eigenes wissen müssen. Wer hier anfängt,
sollte mit `admin-web` anfangen.

## B.6 Sicherung: täglich und wöchentlich

**Was.** Tägliche Sicherung des veränderlichen Teils (Elasticsearch-Indizes,
Grafana- und Admin-Zustand, Konfiguration), wöchentlich ein vollständiger
Stand einschliesslich der Releases.

**Was es löst.** SeaweedFS hält die Daten, aber niemand hat bisher geprüft, was
bei einem Verlust dort passiert. Ein Backup ist erst eines, wenn eine
Rückspielung gelungen ist — das gehört als Übung dazu, nicht als Zeile in einem
Konzept.

**Was hier hilft:** Raw und Bronze sind **unveränderlich**, und jedes Release
trägt SHA-256 je Datei. Eine Rückspielung ist damit nachprüfbar und nicht nur
hoffentlich vollständig.

**Was es kostet.** Platz und eine Regel. Ein Release sind rund 42 MB; ohne
Aufräumregel wächst das linear, und genau diese Regel ist noch nicht
entschieden ([`datenhistorie.md`](intern/datenhistorie.md) 5.5). Eine Sicherung ohne
Löschregel ist nur ein Aufschub.

## B.7 Cloud: vorbereitet, nicht umgezogen

**Was.** Das Projekt wird so gebaut, dass es sich nach Google Cloud ausrollen
lässt, ohne die Strecke anzufassen. Der PoC läuft weiter auf dem privaten
Server.

**Was dafür schon getan ist** — und das ist der Punkt, der im
Leistungsnachweis zählt:

* **Ein Adressraum für alles Persistierte.** `bronze/city=chicago/…` heisst
  lokal `data/…` und auf S3 `s3://urban-crime/…`. Auf GCS wäre es `gs://…` —
  ein Backend mehr, kein Umbau.
* **Kein Pfad im Code.** Die Pipelines fragen die Ablage nach einem Lesepfad;
  ob der lokal oder entfernt ist, entscheidet die Konfiguration.
* **Läufe sind unveränderlich, Ableitungen wegwerfbar.** Ein Umzug kopiert
  `raw/` und `bronze/` und baut den Rest neu.

**Was noch fehlt:** ein zweites Backend für GCS, die Ingestion als Job statt
als Prozess, und eine Antwort auf die Kostenfrage.

## B.8 Skalierung der Ingestion — die eigentliche technische Frage

Die Ingestion ist der Teil, der bei mehr Städten zuerst bricht, und es ist
**nicht** die Datenmenge, die ihn brechen lässt:

| Achse | heute | was passiert bei zehn Städten |
| --- | --- | --- |
| Zeilen | 348'329 | rund 1,7 Mio — DuckDB rechnet das weiterhin interaktiv |
| Laufzeit Ingestion | Detroit 7 s im Delta, 100 s beim ersten vollen Lauf | linear, aber **seriell**: zehn Städte nacheinander |
| Code je Quelle | zwei Pipelines mit je eigener Logik | zehn Pipelines, zehnmal derselbe Fehler |

Zwei Umbauten stehen deshalb an, und sie sind unterschiedlich dringend:

**1. Ein Quellprofil statt zweier Sonderwege.** Heute trägt
`build_crime_offense` Chicago und Detroit in zwei getrennten CTEs. Eine dritte
Stadt bedeutet einen dritten. Ein Profil je Quelle — Feldnamen, Zeitzone,
Crosswalk, Granularität — macht daraus Konfiguration. Das ist der **einzige
echte Blocker** für eine dritte Stadt.

**2. Parallele Ingestion.** Die sechs Ingestion-Stufen laufen heute
nacheinander, obwohl keine von der anderen abhängt. Sie sind fast
ausschliesslich Wartezeit an fremden APIs. In der Cloud wären sie
naheliegenderweise einzelne Jobs; schon lokal brächte Nebenläufigkeit den
grössten Teil der Laufzeit zurück.

**Was dabei nicht verhandelbar ist.** Auch parallel bleibt jeder Lauf
unveränderlich und schreibt sein eigenes Verzeichnis; die Reihenfolge zwischen
den **Gruppen** bleibt streng. Parallel heisst innerhalb der Ingestion, nicht
über die Schichten hinweg.

**Was es kostet.** Das Quellprofil ist ein Umbau an der Stelle, die heute am
besten geprüft ist — `build_crime_offense` trägt die Zeitachse, die
NIBRS-Zuordnung und das Fallebene. Er lohnt sich erst mit der dritten Stadt,
und er will in kleinen Schritten gemacht werden, jeder mit grüner Suite.
Nebenläufigkeit ist billiger, bringt aber nur Laufzeit — kein einziges neues
Ergebnis.

---

## Was dieser Text nicht behauptet

Teil B ist ein Plan, und Pläne altern. Drei Dinge sind ausdrücklich noch nicht
entschieden:

1. **Ob Elasticsearch die Aggregationen übernimmt** oder nur Exploration,
   Volltext und Karte — B.4.
2. **Wie die Prüfenden Zugang bekommen**, wenn alles hinter Cloudflare Access
   liegt — B.3.
3. **Wann der Referenzstand nachgezogen wird.** Seit dem 17.9.2026 steht der
   gebaute Stand vor dem dokumentierten; die Drift ist gemessen und in
   [`datenhistorie.md`](intern/datenhistorie.md) 8 festgehalten.

---

**Zu den Zahlen.** Teil A nennt den **Referenzstand** — den Bau vom 17.9.2026,
16:05 UTC, auf den sich alle Abgabedokumente beziehen und den 70 Wächter mit
dem Marker `referenzstand` gegen die Parquet-Dateien halten. Der gebaute Stand
auf dem Entwicklungsrechner ist seit einer frischen Ingestion am Abend des
17.9. geringfügig weiter (silver +0,10 %, gold +0,13 %, Detroits Rate 132,7 →
132,7); die Drift ist gemessen und in [`datenhistorie.md`](intern/datenhistorie.md) 8
festgehalten. Die Speichergrössen in A.1 sind dagegen der tatsächliche Stand
auf der Platte am 18.9.2026 — sie stehen unter keinem Test und sind als
Grössenordnung gemeint.

Teil B nennt keine Zahl, die nicht aus Teil A oder aus einem protokollierten
Lauf stammt.
