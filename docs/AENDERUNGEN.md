# Änderungen an der Datenstrecke

Diese Datei hält fest, **was sich an den Zahlen und Zusagen geändert hat und
warum** — gedacht für die Dokumentation und die Präsentation. Neueste zuerst.

Sie ersetzt nicht die Git-Historie. Dort steht, *was* im Code passiert ist; hier
steht, was es für die Aussagen des Projekts bedeutet.

**Wann ein Eintrag entsteht.** Wenn sich etwas ändert, das die Abgabe behauptet:
eine **Zahl**, eine **Zusage** (etwa „die Crosswalks sind reproduzierbar
abgeleitet"), oder eine Aussage in einem der Abgabedokumente, die wir korrigiert
haben. Ein Pull Request, der nur aufräumt, ein Werkzeug bequemer macht oder
einen Kommentar richtigstellt, bekommt **keinen** — steht dann aber unten unter
*Bewusst ohne Eintrag*, damit eine Lücke in den Nummern als Entscheidung
erkennbar ist und nicht als Versehen.

Die frühere Fassung dieser Regel sagte *„ein Eintrag je gemergtem Pull
Request"* **und** *„Testarbeit steht bewusst nicht hier"*. Beides zusammen geht
nicht, und entsprechend fehlten vier Einträge, bis es am 12.9. auffiel.

**Arbeitsteilung seit 12.9.2026:** Christian bearbeitet Silver und Gold, Artan
Dokumentation und Präsentation. Wo unsere Arbeit eine Aussage in
`ln1_konzept.md`, `projektabsprache.md` oder `leistungsnachweise.md` überholt,
korrigieren wir die **Sachaussage** und lassen Aufbau und Formulierung; der
Eintrag hier sagt, was das war.

---

## Der Stand in Zahlen

| | |
| --- | ---: |
| Tests | **931** |
| `silver/crime_offense` | 347'957 Zeilen (Detroit: eine Anklage) |
| `gold/fact_offense` | **344'617** Zeilen (eine Tat) |
| Chicago | 251'516 Delikte · 2'661'953 Einwohner · **94,5** je 1'000 |
| Detroit | 84'658 Delikte · 638'635 Einwohner · **132,6** je 1'000 |
| Fallkorn (`counts_case`) | Chicago 259'243 · Detroit 80'229 Fälle; Detroit **124,6** je 1'000 |

> Die Rate zählt nur Delikte in Tracts, die einer der beiden Städte zugeordnet
> sind. Absolute Fallzahlen legen das Gegenteil nahe — Chicago hat in fast
> jeder Kategorie mehr Fälle.

---

## Vertragsversionen

Was sich ändert, wenn eine dieser Zahlen steigt: **was** geladen oder gedeutet
wird — Zeitfenster, Feldauswahl, Dedup-Regel, Korn. Nicht, *wie* der Code es
tut; dafür steht der Git-Commit im selben Manifest.

Jeder Lauf trägt seine Version bei sich. *„Ab wann wurde anders geladen?"* ist
damit eine **Abfrage** und kein Eintrag, den jemand pflegen muss: der erste
Lauf mit der höheren Zahl. Diese Tabelle sagt, was die Zahl bedeutet.

| Datensatz | Version | seit | was der Vertrag festlegt |
| --- | ---: | --- | --- |
| `bronze/city=chicago` | 1 | 14.09.2026 | Jahresfenster über `date`, Delta über `updated_on` mit 14 Tagen Rückgriff, feste id-Liste als Vollständigkeitsnachweis |
| `bronze/city=detroit` | **2** | 11.09.2026 | Abfragefenster in **Detroiter Ortszeit** statt UTC (Konzept 8.6). Version 1 zog es in UTC — jene Läufe enthielten 66 Fälle aus 2023 und vermissten 56 vom Jahresende 2024 |
| `bronze/dataset=tiger_tract`, `bronze/dataset=tiger_place` | 1 | 14.09.2026 | Vintage-Archiv je Bundesstaat, Geometrie als WKB in EPSG:4269, Feld-Allowlist mit `_extra` |
| `bronze/dataset=acs5_tract` | 1 | 14.09.2026 | fünf Variablen je Tract, Fehlwert `-666666666` bleibt unverändert stehen |
| `bronze/dataset=noaa_ghcnd` | 1 | 14.09.2026 | Vollschnappschuss je Station, bedingter Abruf über ETag, Mindestabstand sieben Tage |
| `silver/tract` | 1 | 14.09.2026 | ein Census Tract je Zeile, TIGER und ACS über einen vollen äusseren Join |
| `silver/place` | 1 | 14.09.2026 | ein Ort je Zeile, Geometrie für die Stadtgrenze |
| `silver/weather_day` | 1 | 14.09.2026 | eine Stadt an einem Tag, eine Station je Stadt |
| `silver/crime_offense` | 1 | 14.09.2026 | eine Anklage je Zeile; `counts` markiert die Tat, `counts_case` den Fall; NIBRS als gemeinsame Achse |
| `gold/*` | 1 | 14.09.2026 | Sternschema, eine Zeile je Tat, Mehrheitsregel für die Stadtzuordnung |

**Version 1 heisst „der Vertrag, wie er am 14.9.2026 gilt".** Frühere
Änderungen — das Tatkorn, das Fallkorn, die Mehrheitsregel — stehen als
Einträge weiter unten; rückwirkend Nummern zu vergeben, hätte eine Ordnung
vorgetäuscht, die es damals nicht gab. Detroit ist die Ausnahme: Dort steht
die 2 seit dem 11.9. in den Daten selbst.

---

## 14.09.2026 · Gepinnte Läufe: aus erklärbar wird reproduzierbar (#79)

**Was.** `orchestration.aufraeumen` hat eine **Regel 0**: Was in
`config/referenzstand.csv` steht, wird nie aufgeräumt. `--pinnen LN1` trägt
den Stand ein, auf dem die gebauten Gold-Tabellen ruhen. Artans Punkt 1,
Stufe B ([`ausblick.md`](ausblick.md)).

**Warum.** Die Aufbewahrungsregel von #65 behält, was **das aktuelle** Silver
nennt. Nach einem Neubau werden die Läufe des vorigen Stands entbehrlich — und
eine veröffentlichte Zahl von letzter Woche wäre nicht mehr nachzubauen. Für
den Arbeitsalltag war die Regel richtig, für die Historisierung falsch. Der
Konflikt fiel bei der Analyse von Artans Punkten auf (#76).

**Abgeleitet, nicht getippt** — das ist der Ertrag der geschlossenen
Herkunftskette (#77): Weil ein Gold-Manifest seine Silver-Quelle samt deren
Herkunft nennt, stehen die Bronze-Läufe darin. `--pinnen` liest sie heraus.
Gegen die echten Daten: **neun Läufe über alle fünf Quellen**. Der NOAA-Lauf
vom 7.9. ist nicht dabei — Silver nimmt den jüngsten, also ruht keine Zahl
auf ihm. Genau das soll ein Referenzstand leisten.

**Versioniert, nicht in `data/`.** Ein Referenzstand ist eine Verabredung des
Teams, kein Zustand eines Rechners; seit die Läufe auf SeaweedFS liegen,
gelten die Kennungen für beide. Die Datei gehört mit committet.

**Damit ist Absprache 7.1 beantwortet.** Dort stand die Frage *„Wie kommen wir
zum gleichen Datenstand?"* mit dem Vorschlag, einen Referenzstand zu
verabreden. Er ist jetzt kein Zettel, sondern eine Datei — und die Läufe
dahinter überleben jedes Aufräumen.

**Wächter.** Zehn Tests in `tests/orchestration/test_aufraeumen.py`: gepinntes
überlebt, wird nicht gelöscht, Detroits nackte UUID wird erkannt, zweimal
pinnen schreibt nicht doppelt, und gepinnt wird nur, was es auch gibt.

**Zahlen.** 924 → **931 Tests**.

---

## 14.09.2026 · Jeder Lauf sagt, welcher Code ihn gemacht hat (#78)

**Was.** Jedes Manifest — fünf Quellen, vier Silver-Tabellen, fünf
Gold-Tabellen — trägt jetzt zwei Angaben: `contract_version` (was geladen
oder gedeutet wird) und `code_version` (welcher Git-Commit, und ob der
Arbeitsbaum sauber war). Dazu ein Register *Vertragsversionen* weiter oben in
dieser Datei. Artans Punkt 2 ([`ausblick.md`](ausblick.md)).

**Warum.** Am 11.9. wurde Detroits Abfragefenster von UTC auf Ortszeit
umgestellt. Läufe davor enthielten 66 Fälle aus 2023 und vermissten 56 vom
Jahresende 2024 (Konzept 8.6). Zwei Läufe, gleiche Struktur, gleiche Quelle —
**anders geladen**. Ohne Vermerk im Lauf selbst sieht man das keinem an.

**Drei Fragen, die leicht verwechselt werden.** *Welcher Code lief* beantwortet
der Commit — automatisch und genau, aber er springt auch bei einem Tippfehler
im Kommentar. *Hat sich die Bedeutung geändert* beantwortet die
Vertragsversion — bewusst gesetzt, grob, fachlich. Und *ab wann gilt das Neue*
braucht **keine eigene Antwort**: Weil Läufe unveränderlich und zeitgestempelt
sind, ist es eine Abfrage — der erste Lauf mit der höheren Zahl. Kein Register,
das jemand pflegen muss und das veraltet.

**`git_dirty` ist wichtiger, als es aussieht.** Ein Lauf aus einem veränderten
Arbeitsbaum lässt sich aus dem Commit allein nicht nachbauen. Wer das später
wissen will, findet es im Manifest, statt es zu vermuten.

**Detroit war das Vorbild** und behält seine drei feineren Verträge
(`bronze_`, `raw_`, `window_contract_version`); `contract_version` ist die
gemeinsame Angabe aller fünf Quellen und steht dort auf **2**, weil diese Zahl
seit dem 11.9. in den Daten steht. Alle anderen starten bei 1 — rückwirkend
Nummern zu vergeben hätte eine Ordnung vorgetäuscht, die es damals nicht gab.

**Wächter.** `tests/test_vertragsversionen.py` hält jede Zahl im Code gegen
das Register. Wer eine Version erhöht und das Register vergisst, fällt durch —
mit der Meldung, was zu schreiben ist. Eine Versionsnummer ohne Begründung ist
schlimmer als keine: Sie sieht nach Ordnung aus.

**Ohne Git** — installiertes Paket, kein Repository — bleibt `code_version`
bei `None`. Ein Lauf darf daran nie scheitern; auch das ist ein Test.

**Zahlen.** 896 → **924 Tests**.

---

## 14.09.2026 · Die Herkunftskette ist geschlossen (#77)

**Was.** Jede abgeleitete Tabelle trägt einen `input_fingerprint` über ihre
Eingaben. Wer auf einer anderen ruht, nennt sie nicht mehr nur als **Pfad**,
sondern als **Stand**: Bauzeitpunkt, Eingabe-Abdruck und — wörtlich — deren
eigene Herkunft. Referenzdateien unter `config/` tragen ihre SHA-256. Artans
Punkt 1, Stufe A ([`ausblick.md`](ausblick.md)).

**Warum.** Gold nannte seine Silver-Quelle als
`{"path": "data/silver/…/part-0001.parquet"}`, und ein Pfad zeigt auf das,
was gerade dort liegt. Wurde Silver neu gebaut, zeigte derselbe Satz auf
etwas anderes — und nichts verriet es. Dasselbe galt für die Crosswalks, die
aus amtlichen PDFs erzeugt werden und sich ändern können, ohne dass ihr Pfad
sich ändert.

**Was jetzt von einer Gold-Zahl aus lesbar ist:**

```text
gold/fact_offense    input_fingerprint e7ec6a4a…
  ruht auf silver/crime_offense, gebaut 2026-09-14T11:37:57, Abdruck 1608aec7…
      Chicago  3 Läufe, erster run_20260905T174633859259Z
      Detroit  2 Läufe
      tract    gebaut 2026-09-14T11:37:56, Abdruck 215d02b2…
      iucr_nibrs_mapping.csv  ed36120081941cff…   (+ zwei weitere)
```

**Ein Entwurfsfehler, den ein Test gefangen hat.** Die erste Fassung hashte
die Herkunft **mitsamt den absoluten Pfaden**. Damit hätten Christian und
Artan für denselben Stand verschiedene Abdrücke bekommen — im gemeinsamen
Speicher wäre die Zusage wertlos gewesen. Gehasht wird jetzt nur das
Kennzeichnende (`manifeste.kennzeichen`): Lauf-Kennungen, Prüfsummen und die
Abdrücke der Vorgänger. Pfade und Bauzeitpunkte fallen heraus — sie sagen,
*wo* und *wann*, nicht *was*.

**Nebenbei aufgeräumt:** `run_all.fingerabdruck` war eine zweite Fassung
derselben Rechnung und kommt jetzt aus `manifeste` — „derselbe Stand" heisst
überall dasselbe.

**Was das nicht ist.** Keine Historisierung: Silver und Gold werden weiterhin
ersetzt. Die Kette **erklärt** jede heutige Zahl vollständig; sie **reproduzieren**
lässt sich eine vergangene erst mit Stufe B (gepinnte Läufe), weil die
Aufbewahrungsregel alte Bronze-Läufe sonst wegräumt.

**Zahlen.** 883 → **896 Tests**.

---

## 14.09.2026 · Artans zwei Punkte analysiert: Lineage und Ladelogik (#76)

**Was.** [`docs/ausblick.md`](ausblick.md) — Material für LN2. Zwei Punkte
von Artan, analysiert gegen den Code, dazu die Gedankenspiele zu Skalierung
und Cloud mit Messwerten.

**Artans Punkt 1: Stichtagskonsistenz.** *„Werte vom Tag X → Silver-Load Y →
Bronze Load XY am Tag X."* Die Kette ist links stark und rechts gerissen:
Silver nennt jeden Bronze-Lauf **namentlich**, Gold nennt seine Silver-Quelle
nur als **Pfad** — und ein Pfad zeigt auf das, was gerade dort liegt. Dasselbe
gilt für die Crosswalks. Von einer Gold-Zahl aus lässt sich heute nicht sagen,
welcher Silver-Stand gemeint war.

Der billige Teil der Lösung braucht **keine** Historisierung: Es genügt, dass
Gold die *Identität* des Silver-Stands festhält (Zeitpunkt und Fingerabdruck
seiner Eingaben) — dann schliesst sich die Kette transitiv bis zu Raw.

**Ein Konflikt, den dabei niemand gesucht hat:** Die Aufbewahrungsregel von
#65 behält, was **das aktuelle** Silver nennt. Nach einem Neubau werden die
Läufe des vorigen Stands entbehrlich — und wären beim nächsten `--loeschen`
weg. Für den Arbeitsalltag richtig, für die Historisierung falsch. Es braucht
eine vierte Regel: *gepinnt bleibt.*

**Artans Punkt 2: die Ladelogik versionieren.** *„Nicht nur in GitHub, sondern
ab wann die Daten anders geladen werden."* Der Anlass steht im Projekt schon:
Am 11.9. wurde Detroits Fenster von UTC auf Ortszeit umgestellt; Läufe davor
enthielten 66 Fälle aus 2023. Zwei Läufe, gleiche Struktur, anders geladen —
ohne Vermerk sieht man das keinem an.

**Und es gibt bereits ein Vorbild: Detroit.** `window_contract_version: 2`,
`bronze_contract_version: 2`, `raw_contract_version: 1` — genau das, was Artan
vorschlägt, nur für eine Quelle und verteilt über drei Module. Chicago, Census
und NOAA haben nichts Vergleichbares; die Silver-Manifeste halten `"tool":
"duckdb 1.5.5 …"` fest, also die **Engine**, nicht unseren Code.

Der Vorschlag trennt drei Fragen, die leicht verwechselt werden: *welcher Code
lief* (Git-Commit, automatisch), *hat sich die Bedeutung geändert*
(Vertragsversion, von Hand), *ab wann gilt das Neue*. Die dritte braucht keine
eigene Antwort: Wenn jeder Lauf seine Vertragsversion trägt und Läufe
unveränderlich sind, ist „ab wann" eine **Abfrage** — der erste Lauf mit
Version 2 — und kein Register, das jemand pflegen muss.

**Dazu Skalierung und Cloud**, gemessen: 23,1 s für die ganze Ableitung. Was
zuerst bricht, ist nicht die Engine, sondern der Vollneubau; der einzige echte
Blocker für eine dritte Stadt sind zwei handgeschriebene CTEs. Für die Cloud
hat der Storage-Umbau die Entkopplung schon erledigt — es fehlen zwei
Konfigurationsfelder (`region_name`, `addressing_style` sind fest verdrahtet).

**Wächter.** `tests/test_ausblick.py`: Solange das Dokument eine Lücke
**behauptet**, muss sie noch da sein. Wer eine schliesst, fällt durch und zieht
den Ausblick mit — und die Meldung nennt den Abschnitt. Dieselbe Drift hatte
Tabelle 5.3 dreimal erwischt.

**Zahlen.** 873 → **883 Tests**.

---

## 13.09.2026 · Die Datenablage hat ein Architekturdokument (#75)

**Was.** [`docs/storage-architektur.md`](storage-architektur.md) beschreibt
den ganzen Aufbau auf 15 Abschnitten: das Problem, den relativen
Ablagepfad, die drei Modi mit Fluss-Diagrammen, jede Umgebungsvariable und
wann sie nötig ist, Lesen, Publizieren, die beiden Konfliktregeln, den
veralteten Stand, was immer lokal bleibt, DuckDB mit S3, die API, die
Werkzeuge, was bewusst fehlt, die Fehlerbilder und wo der Code liegt.

**Warum getrennt.** README 2.5 sagt, wie man es **bedient**; Konzept 7.4
ordnet es in den Lebenszyklus ein. Beide sollen nicht zum Handbuch
anwachsen. Beide verweisen jetzt auf das neue Dokument, und es verweist
zurück.

**Die Frage, die es auslöste.** *Wenn man lokal arbeitet, muss man das
`.env` für S3 nicht ausfüllen, oder?* — Richtig, und zwar vollständig:
`local` ist die Vorgabe, `STORAGE_BACKEND` darf ganz fehlen, keine
`S3_`-Variable wird gelesen, `boto3` nie importiert. Das steht jetzt als
Tabelle in README 1.3 und in Abschnitt 4 des Dokuments — vorher stand im
README eine Beispiel-`.env`, die alle fünf Zeilen zeigte und damit den
falschen Eindruck erweckte, sie gehörten dazu.

**Wächter.** `tests/storage/test_dokumentation.py` hält die Variablentabelle
an der Konfiguration fest: Jede Variable, die `config.py` liest, muss darin
stehen; keine erfundene daneben; und **jede genannte Vorgabe muss die echte
sein** — die Stelle, die am leisesten veraltet. Zwei Gegenproben haben
gezeigt, dass die Prüfung zubeisst. Dazu: alle drei Modi beschrieben, die
drei Merksätze vorhanden, die genannten Code-Dateien existieren, das README
verweist.

**Zahlen.** 865 → **873 Tests**.

---

## 13.09.2026 · Das Konzept auf den Storage-Umbau nachgeführt — und vier veraltete Stellen (#74)

**Was.** `ln1_konzept.md` beschreibt die wählbare Ablage dort, wo sie
hingehört: Kapitel 7. Dazu vier Sachkorrekturen, die beim Durchsehen
aufgefallen sind.

**Kapitel 7.2 widersprach dem Gebauten.** Die Bewertungstabelle führt *„Cloud
(S3, BigQuery) — verworfen"*. Das galt der **Skalierung** und gilt weiter;
zurückgekommen ist S3 für eine Frage, die in der Tabelle nicht vorkam: wie
zwei Leute an denselben Stand kommen. Die Zeile bleibt deshalb stehen — sie
ist der damalige Entscheid —, und ein datierter Nachtrag sagt, was sich
geändert hat und warum die beiden Einwände (Kosten, fremde Zugänge) auf ein
selbstgehostetes SeaweedFS nicht zutreffen.

**Kapitel 7.4** hat einen neuen Abschnitt *Wo diese Struktur liegt, ist
wählbar*: die drei Modi als Tabelle und die drei Regeln, die aus dem
gemeinsamen Bestand mehr machen als einen Netzordner — publizieren erst nach
der Prüfung, Läufe unveränderlich, veralteter eigener Stand wird erkannt.
Dazu `serving/` im Verzeichnisbaum, das dort fehlte.

**Die vier veralteten Stellen.**

| Wo | Stand | Richtig |
| --- | --- | --- |
| Kurzfassung | „627 automatisierte Tests" | 865 |
| Kurzfassung | „alle drei Silver-Tabellen" | vier; Gold und Serving fehlten ganz |
| 5.1 und 5.2 | „neun Sichten" | elf — die Hilfssichten `tabellen` und `herkunft` fehlten in der Aufzählung |
| 7.3 | „Die Silver-Schicht liest beide Formate" | der NDJSON-Rückfall ist seit dem Zeitzonen-Befund bewusst entfernt; ausserdem „vier der fünf Quellen" statt aller fünf |

**Die Testzahl stand an drei Stellen und nur eine war bewacht.** Die
Kurzfassung sagte 627, die geprüfte Tabelle 5.3 sagte 864 — dasselbe
Dokument, zwei Zahlen, und die falsche stand vorn. `test_abgabedokumente.py`
prüft jetzt **jede** Stelle im Konzept.

**Kapitel 10** nennt den Rückgriff auf SeaweedFS: Wer `hybrid` setzt, muss
die Quellen nicht selbst laden. Der Reproduktionsweg darüber stimmt
unverändert — `requirements.txt` enthält `-e .[dev]`, installiert das Projekt
also editierbar.

**Zahlen.** 864 → **865 Tests**.

---

## 13.09.2026 · Ein veralteter lokaler Stand wird gemeldet, nicht publiziert (#73)

**Was.** Bei Silver- und Gold-Tabellen vergleicht die Ablage jetzt den
lokalen Stand mit dem auf SeaweedFS — `built_at_utc` und die Bronze-Läufe
aus `derived_from`. Ist der lokale älter oder ruht er auf weniger Läufen:
**beim Lesen** eine Warnung (gelesen wird trotzdem lokal), **beim
Publizieren** eine Absage. `python -m storage` zeigt es je Tabelle,
`publish_table(..., erzwingen=True)` dreht bewusst zurück.

**Warum.** Christian hat gefragt, was passiert, wenn Artan lokal einen
anderen Stand hat. Gemessen: Er liest **still** seine alte Fassung —
344'607 statt 348'300 Zeilen, genau die Sorte Zahl, die auf eine Folie
kommt. Und veröffentlicht er sie, verdrängt sein Stand vom 8.9. den vom
13.9. für alle, ohne Spur. Die Läufe unter `bronze/` und `raw/` waren nie
betroffen: Sie sind unveränderlich und ergänzen einander, statt sich zu
verdrängen — auch das ist jetzt ein Test.

**Warum Lesen warnt und Publizieren absagt.** „Lokal zuerst" ist die Regel
und bleibt es; wer offline arbeitet, soll weiterarbeiten. Ein Rückschritt im
**gemeinsamen** Bestand ist dagegen nichts, was man aus Versehen tun darf.
Der Bau bleibt dabei lokal fertig — nur das Hochladen unterbleibt, mit einem
Satz statt eines Tracebacks (die fünf Silver- und Gold-Kommandos fangen
`StorageError` jetzt mit).

**Zwei Signale, weil eines nicht reicht.** Die Uhrzeit fängt den Fall
„heute gebaut, aber ohne den Lauf, den ein anderer längst geladen hat"
nicht. Die Lauf-Mengen fangen ihn. Umgekehrt nennt Gold unter
`derived_from` Silver-Tabellen statt Läufe — dort zählt allein die Uhrzeit.

**Gegen den echten Bucket geprüft** (nur lesend, mit einer nachgestellten
Kopie): *„hier gebaut 08.09.2026 10:00 UTC, auf SeaweedFS 13.09.2026 14:06
UTC; dort stecken 4 Bronze-Läufe, die hier fehlen."*

**Der Ausweg** ist immer `python -m orchestration.run_all --ohne-ingestion`
— danach ruht der Stand auf allen Läufen, den lokalen und denen von
SeaweedFS.

**In Artans Dokumenten.** Konzept 5.3, Zeile *Data Management*: die
Umsetzung nennt den Vergleich. README 2.5: *Wenn dein lokaler Stand älter
ist.*

**Zahlen.** 837 → **864 Tests**.

---

## 13.09.2026 · Bestehende Läufe nachpublizieren — und Aussetzer aushalten (#72)

**Was.** `python -m storage publizieren` zeigt, welche fertigen lokalen
Läufe unter `raw/` und `bronze/` auf SeaweedFS fehlen, und bringt sie mit
`--wirklich` hoch — Raw vor Bronze, je Lauf das Manifest zuletzt,
idempotent, kein Sync in die Gegenrichtung. Dazu wiederholt der S3-Client
vorübergehende Fehler (403, 5xx, Verbindungsabbruch) bis zu viermal mit
Pause, bevor sie ein Fehler sind; endgültige (falscher Schlüssel, kein
Bucket) sofort.

**Warum.** Christians erster Hybridlauf brachte Silver und Gold nach
SeaweedFS — Bronze und Raw nicht, weil `--ohne-ingestion` die Stufen
übersprang, die sie publizieren. Für Artan wäre das kein Detail: Silver
liest **alle** Chicago-Läufe; ohne den Vollschnappschuss vom 5.9. baut er
kein `crime_offense`. Beim Nachpublizieren antwortete SeaweedFS auf das
erste HEAD mit 403 und Sekunden später auf denselben Schlüssel mit 404 —
ein Aussetzer, kein Rechteproblem. boto3 wiederholt 403 nicht von sich aus.

**Stand auf SeaweedFS danach.** 146 Objekte, 251 MB: raw 98 (94 MB),
bronze 30 (93 MB), silver 8 (49 MB), gold 10 (15 MB). Alle 29 lokalen Läufe
sind oben; ein zweiter Aufruf sagt *Nichts zu tun*.

**Zahlen.** 832 → **837 Tests**.

---

## 13.09.2026 · Die Ablage sagt, wenn SeaweedFS nicht antwortet (#71)

**Was.** `python -m storage` prüft die Ablage vor der ersten Pipeline:
Modus, Wurzel, Endpoint, Bucket (nie die Schlüssel), DNS-Auflösung, eine
Listung von `silver/`. Und jede Transportstörung aus boto3 wird zu einem
Satz — *SeaweedFS nicht erreichbar: https://…* oder *lehnt ab: Code* — statt
zu einem Traceback aus `botocore/endpoint.py`.

**Warum.** Christians erster Versuch im Hybridmodus fiel mit genau diesem
Traceback. Der Befund: `s3.datenwerft.ch` hat keinen DNS-Eintrag. Das kann
kein Schlüssel heilen, und die Pipeline sollte es in einem Satz sagen.

**Zahlen.** 827 → **832 Tests**.

---

## 13.09.2026 · Die Ablage ist wählbar: lokal, SeaweedFS oder hybrid (#70)

**Was.** Ein Paket `src/crime/storage/` abstrahiert, wo die Schichten
liegen. `STORAGE_BACKEND=local` (Vorgabe) ist der bisherige Zustand,
unverändert. `hybrid` liest lokal, wenn die Datei da ist, sonst von SeaweedFS
(`s3://urban-crime/…`, dieselbe Struktur wie `data/`), und schreibt lokal,
prüft, publiziert dann gezielt. `s3` liest immer von SeaweedFS, schreibt lokal
als Arbeitskopie, publiziert und entfernt die Kopie. Alle Befehle bleiben
gleich; die Konfiguration kommt aus `.env`.

**Die drei Sätze, die es zusammenfassen.**

```
Hybrid READ:    lokal zuerst, S3 als Rückfall
Hybrid WRITE:   lokal, prüfen, dann gezielt nach S3 publizieren
Serving DuckDB: immer lokal
```

**Publizieren ist gezielt, nicht sync.** Je Lauf oder Tabelle die Dateien,
die dieser Lauf erzeugt hat, `manifest.json` zuletzt — das Manifest auf S3
ist das Zeichen, dass ein Lauf vollständig oben ist, wie das Umbenennen
lokal. Nach jedem Upload wird das Objekt zurückgelesen (Existenz, Grösse,
MD5 gegen das ETag). Läufe (`run_…`) sind unveränderlich: identisch schon
oben → übersprungen; anders schon oben → Fehler. Silver- und Gold-Tabellen
werden **überschrieben** — lokal werden sie ebenso ersetzt, nicht angehäuft.

**Welche Pipelines publizieren.** Alle sechs Ingestion-Stufen (Raw zuerst,
Bronze danach), die vier Silver-Tabellen, die fünf Gold-Tabellen — jeweils
erst nach den bestehenden Prüfungen. `data/serving/` bleibt in jedem Modus
lokal; die Sichten in `analyse.duckdb` zeigen je Datei dorthin, wo sie liegt.
`orchestration.aufraeumen` räumt weiterhin nur lokal auf.

**Was Version 1 bewusst nicht tut.** Kein automatisches Herunterladen (was
fehlt, wird von S3 gelesen, nicht kopiert), keine Synchronisation zurück,
kein Dual-Write, nur `local` als Lesepriorität.

**Wächter.** 58 Tests unter `tests/storage/` gegen ein S3 im Speicher, ohne
SeaweedFS: Pfadauflösung je Modus, Rückfall, Vereinigung lokaler und
entfernter Läufe (ein unfertiger lokaler Lauf verdeckt keinen fertigen auf
S3), Reihenfolge und Verifikation beim Publizieren, Konflikte, und die
Pipelines im Hybridmodus — Silver publiziert nach der Prüfung und nicht,
wenn sie scheitert; Chicago und Detroit Raw vor Bronze; die
Auswertungsdatenbank bleibt lokal. `boto3` ist neue Abhängigkeit; im
local-Modus wird es nie importiert.

**Nebenbei.** `manifeste.Lauf` und `Tabelle` tragen jetzt ihren relativen
Ablagepfad (`relativ`); `--data-root` hat keine feste Vorgabe mehr, sondern
folgt `LOCAL_DATA_ROOT` (Vorgabe weiterhin `data`).

**In Artans Dokumenten.** Konzept 5.3 (Umsetzung und Lücke der Zeile *Data
Management*), Kapitel 11 (Zeile *Wo die Daten liegen*). Absprache 7.1:
datierter Nachtrag — der gemeinsame Datenstand hat jetzt einen Ort.

**Zahlen.** 769 → **827 Tests**.

---

## 13.09.2026 · Die Drift bekommt eine Toleranz (#69)

**Was.** `orchestration.drift` wird rot, wenn eine Grösse die Toleranz
überschreitet: eine **Rate je 1'000** um ≥ 0,1 (die Rundung, in der sie
zitiert wird), eine **Zeilen- oder Fallzahl** um > 1 %. Die Tabelle hat eine
Spalte *Toleranz*, das JSON `within_tolerance` und `exceeded` je Grösse, und
die Laufseite eine Annotation, die sagt, welche Grösse wie weit weg ist.
`--nur-melden` schaltet das ab; der Datenlauf tut das nicht.

**Warum.** Christian war sich nach #67 nicht mehr sicher, ob *Drift statt
Rot* richtig ist — zu Recht. Rot bei jeder Abweichung war ein Alarm, der
jede Woche klingelt; eine Tabelle ohne Konsequenz ist ein Alarm, den niemand
hören muss. Die Schwelle ist das, was auf einer Folie stünde: Das
Wochenrauschen der Quellen liegt weit darunter (13.9.: Raten 0,0, Zahlen bis
0,13 %), ein Quellenausfall, ein halber Full Load, eine Schemaänderung weit
darüber. Und wenn die Drift die Schwelle erreicht, ist das genau der Moment,
den Referenzstand nachzuziehen.

**Nicht gebaut ist keine Drift.** Fehlt eine Tabelle, bleibt der Schritt
grün — die Strecke davor ist dann schon rot.

**In Artans Dokumenten.** Konzept Kapitel 9 (Grenze *Referenzstand*), README
(*Drift statt Rot*, mit dem Weg zur Zusammenfassung).

**Zahlen.** 762 → **769 Tests**.

---

## 13.09.2026 · Der Datenlauf weist die Drift aus, statt zu scheitern (#67)

**Was.** Die Wächter, die dokumentierte Zahlen gegen die gebauten Daten
halten, tragen den Marker `referenzstand` — zwölf Testfunktionen, mit Parametern 25 Fälle, in
`test_aenderungen.py`, `test_abgabedokumente.py` und `test_feldkatalog.py`.
Der wöchentliche Datenlauf wählt sie ab (`-m "not referenzstand"`) und ruft
danach `orchestration.drift`: je Grösse dokumentiert, gemessen, Drift und
Prozent — als Tabelle in der Job-Zusammenfassung und als `drift.json` im
Artefakt. Das Werkzeug scheitert nie; fehlt eine Tabelle, steht *nicht
gebaut* in der Zeile.

**Warum.** Der erste Datenlauf mit Schlüssel war rot — und zwar genau an den
Zahlenwächtern: 348'300 Silver-Zeilen statt 347'957, 84'685 Detroit-Taten
statt 84'658. Die Quellen bewegen sich jede Woche; ein Alarm, der jede Woche
klingelt, ist keiner. Christians Entscheid: *die Zahl lieber als Drift
ausweisen statt zu scheitern.* Die Wächter gelten weiter — für den
Referenzstand auf dem eigenen Rechner, wo sie hingehören.

**Was rot jetzt heisst.** Die Strecke bricht, eine Quelle ist älter als acht
Tage, oder ein Test fällt, der auf frischen Daten gelten muss (Einwohnerprobe,
„kein Delikt in der falschen Stadt", das Fallkorn je Fall genau einmal).

**Wächter.** `test_datenlauf_workflow.py`: der Marker wird abgewählt, die
Drift kommt nach den Tests mit `if: always()`, in die Zusammenfassung und ins
Artefakt; und jeder Test, der eine Zahl gegen Parquet hält, trägt den Marker —
sonst wäre der Lauf beim nächsten Wächter wieder jede Woche rot.

**In Artans Dokumenten.** Konzept Kapitel 9: die Grenze *Keine Alarmierung*
sagt nicht mehr, der Lauf scheitere an den Zahlen; neue Grenze *Die Dokumente
beschreiben einen Referenzstand, nicht den Tag.* README: *Drift statt Rot.*

**Zahlen.** 752 → **761 Tests**.

---

## 13.09.2026 · Ein zweites Korn: der Fall — die Städte zählen verschieden (#66)

**Was.** `silver/crime_offense` und `gold/fact_offense` tragen eine neue
Spalte `counts_case`: je Fall zählt eine Zeile, die mit dem schwersten
Delikt, für beide Städte nach derselben Rangfolge (`FALLKORN_RANG`, die
Hierarchieregel des UCR Handbook auf NIBRS übersetzt; bei gleichem Delikt die
früheste Zeile). Additiv — `counts` und alle bisherigen Zahlen bleiben.

**Warum.** Christian hat gefragt, ob Chicagos Mordfälle je Opfer erfasst
sind und ob das berücksichtigt ist. Dokumentiert war es (Notebook 01, 03),
umgesetzt nicht — die dort angekündigte Kennzeichnung `record_granularity =
VICTIM` wurde nie gebaut. Die Messung ergab dann mehr: Die 25 Mordfälle mit
2–3 Zeilen (593 Zeilen, 564 Fälle) sind die **einzigen** Mehrfachzeilen in
ganz Chicago 2024. Chicago führt je Vorfall ein Delikt. Detroit führt jedes:
85'345 Taten auf 80'229 Fälle, 4'658 Fälle mit 2–4 Taten. Das Tatkorn (#38)
hatte Detroits Anklagen angeglichen, nicht die Zählweise der Städte.

**Gemessen.**

| | Chicago | Detroit |
| --- | ---: | ---: |
| Taten (`counts`) | 259'272 | 85'345 |
| Fälle (`counts_case`) | 259'243 | 80'229 |
| Rate je 1'000, Tatkorn → Fallkorn | 94,5 → 94,5 | 132,6 → **124,6** |

Die Reihenfolge bleibt, der Abstand schrumpft um acht Punkte. In Detroit
entschied die Rangfolge in 4'576 Fällen; am meisten verschiebt sich
Sachbeschädigung (290: 10'519 Taten, 8'698 Fälle) — der typische Beifang
eines Einbruchs.

**Für beide Städte gleich.** Christians Rückfrage — *wenn Detroit es gleich
macht, müsste man es nicht für beide so machen?* — ja. Eine Regel nur für
Chicago wäre die nächste Schieflage; die Rangfolge liegt deshalb auf der
NIBRS-Achse, nicht auf MICR, und der Code kennt keinen Sonderweg je Stadt.
Silver prüft beim Bau, dass je Fall mit zählender Zeile genau eine
`counts_case` trägt.

**Korrigiert.** Notebook 11 behauptete „dieselbe Körnung wie bei Chicago".
Die Zelle sagt jetzt das Gegenteil, mit den Zahlen.

**Datenlauf.** Der erste Lauf mit gesetztem `CENSUS_API_KEY` ging durch —
Ingestion, Silver, Gold, Serving, sechs Notebooks. Rot war der Testschritt,
und zwar genau die Zahlenwächter: 348'300 Silver-Zeilen statt 347'957,
84'685 Detroit-Taten statt 84'658. Die Quellen haben sich über Nacht bewegt;
Kapitel 9 beschreibt genau dieses Verhalten.

**In Artans Dokumenten.** Konzept 5.2 (Abschnitt *Das Korn*: zweites Korn
mit Tabelle), Kapitel 9 (neue Grenze *Die Städte zählen verschieden*),
Tabelle 8 (Zeile `crime_offense`), Feldkatalog 133 Spalten. Welche Zählweise
auf die Folie kommt, ist ein Entscheid für Freitag.

**Zahlen.** 744 → **752 Tests**. Neu im Kopf: die Fallkorn-Zeile, bewacht.

---

## 13.09.2026 · Eine Aufbewahrungsregel — und der Lauf vom 11.9. bleibt (#65)

**Was.** `orchestration.aufraeumen` sagt je Quelle, welche Raw- und
Bronze-Läufe bleiben müssen und welche entbehrlich sind. Gelöscht wird nur mit
`--loeschen`, und dann Raw und Bronze zusammen. Punkt 8 der
Schwachstellenliste — der letzte.

**Die Regel.** Es bleiben (1) der jüngste Lauf und der davor, (2) jeder Lauf,
den ein Silver-Manifest unter `derived_from` nennt, (3) die Basis eines
Delta-Laufs — Chicago lädt seit dem vollen Schnappschuss vom 5.9. nur
Änderungen, 42 Zeilen je Lauf; ohne den Schnappschuss darunter wären sie
wertlos. Alles andere ist entbehrlich.

**Was sie heute freigibt: nichts.** Zehn Läufe über sechs Quellen, jeder hat
einen Grund. Die 178 MB aus der Schwachstellenliste sind also keine Altlast,
sondern der Bestand, den die Regel verlangt — das wusste vorher niemand, weil
es keine Regel gab.

**Der Lauf vom 11.9.** Detroits Bronze-Lauf `1cca323d…` hat kein
Raw-Gegenstück: Er ist vom 11.9. 12:50, Detroits Raw-Schicht kam am 12.9.
mit #39. Er bleibt trotzdem. Er ist der *vorherige Schnappschuss*, und nur
mit ihm zeigt Notebook 13 (Schritt 3), dass Detroit abgeschlossene Fälle
nachträglich ändert — 68'655 von 88'685 `ESRI_OID` anders, zehn Delikte in
zwanzig Stunden umklassiert. Notebook 13 speichert keine Ausgaben; ohne den
Lauf wäre der Befund nur noch eine Behauptung. Das Werkzeug meldet ihn als
„ohne Raw".

**Ein Fehler nebenbei.** `manifeste.versteckt()` hielt jeden Pfadteil mit
Punkt am Anfang für ein `.part`-Verzeichnis — auch `..`. Unter
`--data-root ../data` fand der Leser stumm nichts, und `run_all` hätte
dasselbe getroffen. Behoben, mit Test.

**Bewusst nicht.** Die Regel läuft nicht von allein. `data/` ist nicht
versioniert, sie gilt je Rechner, und Löschen bleibt ein Handgriff, den man
sieht. In GitHub Actions läuft jeder Datenlauf auf einer frischen Maschine.

**In Artans Dokumenten.** Konzept 5.3: die Lücke *keine Aufbewahrungsregel*
gestrichen, die Umsetzung ergänzt; Kapitel 11 um die Zeile zum Werkzeug.
Absprache 4.3: datierter Nachtrag. README 2.4 neu.

**Zahlen.** 731 → **744 Tests**.

---

## 13.09.2026 · Verantwortliche je Datensatz (#64)

**Was.** Absprache 7.3 hat eine Tabelle *Verantwortliche je Datensatz*: jede
Stufe des Run-Controllers, der Datensatz dahinter, das Modul, wer zuständig
ist, und wo es belegt ist. Punkt 7 der Schwachstellenliste.

**Warum.** Die Schritt-Tabelle in 7.3 sagte, wer *baut* — nicht, wen man
fragt, wenn eine Quelle klemmt. Tabelle 5.3 des Konzepts führte das als Lücke
unter *Data Management*: „niemand ist für einen Datensatz benannt".

**Was drinsteht.** Stand nach der Arbeitsteilung vom 12.9.: alle sechs
Ingestion-Stufen, Silver, Gold und Serving bei Christian; Hypothesen und die
vier Abgabedokumente bei Artan. Das ist keine Wunschverteilung, sondern der
Befund aus der Git-Historie — jeder Pull Request an der Datenstrecke seit #2
ist von Christian. Eine Stellvertretung regelt die Tabelle bewusst nicht:
bei zwei Personen ist der andere der einzige Ausweg.

**Wächter.** `tests/test_unterstroemungen.py` liest die Tabelle und hält sie
gegen `run_all.STUFEN`: Kommt eine Stufe dazu, fällt der Test, bis sie in der
Absprache einen Verantwortlichen hat. Ein zweiter Test lässt nur Christian,
Artan oder „beide" als Namen zu.

**In Artans Dokumenten.** Absprache 7.3: die Tabelle als datierter Nachtrag,
unter dem bestehenden Entscheid. Konzept 5.3: die Lücke aus der Zeile
*Data Management* gestrichen, die Umsetzung um den Verweis ergänzt.

**Zahlen.** 729 → **731 Tests**.

---

## 13.09.2026 · Die Aktualität wird geprüft, nicht nur aufgezeichnet (#63)

**Was.** `run_all --maximal-alter-tage N`: Ist der jüngste Lauf einer Quelle
älter, scheitert der Lauf und nennt Quelle und Alter. Der Datenlauf gibt
**acht Tage** mit. Punkt 6 der Schwachstellenliste.

**Warum.** Das Gesamtmanifest nannte seit #58 je Quelle den jüngsten Lauf —
und niemand las es. *„Aktualität wird aufgezeichnet, nicht geprüft"* stand als
Lücke in Tabelle 5.3. Eine Zahl, die niemand gegen etwas hält, ist keine
Kontrolle.

**Wann geprüft wird, hängt vom Modus ab.** Bei `--ohne-ingestion` **vor** der
ersten Stufe: Die Daten werden dabei nicht frischer, und ein Gold auf
veraltetem Bronze wäre genau die Zahl, die dann auf einer Folie landet. Mit
Ingestion **danach**: Jetzt sollten alle Quellen frisch sein — sind sie es
nicht, hat eine Quelle nichts Neues geliefert, und das will man erfahren.

**Gegen die echten Daten probiert.** Schwelle ein Tag:

```
Zu alt: city=chicago (7.1 Tage), city=detroit (1.1 Tage),
dataset=acs5_tract (6.9 Tage), dataset=noaa_ghcnd (4.6 Tage),
dataset=tiger_place (1.2 Tage), dataset=tiger_tract (6.9 Tage).
Erlaubt: 1.0 Tage.
```

Nichts gebaut. Mit dreissig Tagen: sieben Stufen in zwei Sekunden.

**Warum acht Tage im Datenlauf.** Wochentakt plus Reserve, NOAAs vier Tage
Nachlauf eingeschlossen. Eine Quelle, die eine Woche lang nichts Neues
liefert, lässt den Montagslauf rot werden.

**Was weiterhin fehlt, und jetzt ehrlich so heisst.** Kapitel 9 sagte „keine
Alarmierung und keine Freshness-Kontrolle". Die zweite gibt es jetzt; die
erste nicht: Der Lauf wird rot, aber niemand wird angerufen. Wer es erfahren
will, muss auf *Actions* sehen.

**Zahlen.** 722 → **729 Tests**.

**Nachlesen.** `src/crime/orchestration/run_all.py` · PR #63

---

## 13.09.2026 · Ein Manifest-Leser statt elf (#62)

**Was.** `src/crime/manifeste/`: `fertige_laeufe()` und `tabellen()`, dazu
`Lauf` und `Tabelle`, die die je Quelle verschieden benannten Schlüssel
auflösen — `run_id`/`pipeline_run_id`, `completed_at_utc`/`finished_at`,
`row_count`/`downloaded_count`. Zehn Stellen lesen jetzt darüber. Punkt 5 der
Schwachstellenliste.

**Warum.** „Manifeste einsammeln" war an **elf Stellen** implementiert, jede
ein wenig anders: sieben kannten nur `complete`, Detroits Leser nur
`SUCCESS`, der Controller beide; drei übersprangen versteckte
`.part`-Verzeichnisse, die übrigen nicht; die Ingestion warf bei kaputtem
JSON, der Controller warnte. Als der Controller entstand, musste er jede
dieser Eigenheiten einzeln nachvollziehen — und **vier der elf Stellen
stammten vom selben Tag.**

**Was je Aufrufer verschieden bleibt, ist ein Parameter.** Das Glob-Muster.
Der Fehlertyp — die Ingestion sagt `IngestionError`, Silver `TransformError`,
und ihre Tests hängen an diesen Typen. Und ob ein kaputtes Manifest wirft oder
nur warnt: Für eine Pipeline ist es ein Fehler in der eigenen Schicht, für den
Controller, der nur inventarisiert, eine Warnung.

**Was bewusst nicht hineingehört.** Detroits `validate_manifest` ist kein
Leser, sondern ein Zulassungstor mit Prüfsummen, Zeilenzahlen und
Schema-Fingerabdruck. Es prüft, ob ein Lauf *gilt*; der Leser findet nur, ob
er *fertig* ist. Und `serving.discover()` globbt Parquet-Dateien, keine
Manifeste.

**Der Beleg, dass es gegriffen hat.** Nach dem Austausch war **jeder
funktionale Test auf Anhieb grün** — Ingestion, Silver, Controller,
Feldkatalog. Ruff meldete genau eines: `read_manifest` in
`build_crime_offense` war jetzt ungenutzt, weil es der alte Leser war. Und
`read_manifest_file`, Detroits Sonderweg, hatte keinen Aufrufer mehr —
entfernt.

**Eine Lehre für die eigene Kette.** Der erste Versuch, diesen Eintrag zu
schreiben, scheiterte an einem `„…"`-Zitat, das einen Python-String zu früh
schloss — und der Pull Request ging trotzdem hinaus, weil `pytest | tail` den
roten Exit-Code verschluckte. Seither läuft die Kette mit `pipefail`.

**Zahlen.** 708 → **722 Tests**; 14 neue halten fest, was elf Stellen je für
sich richtig oder falsch machten.

**Nachlesen.** `src/crime/manifeste/__init__.py` · PR #62

---

## 13.09.2026 · Die Notebooks laufen im Datenlauf — und Notebook 32 war kaputt (#61)

**Was.** Der Datenlauf führt nach dem Bau die sechs Notebooks aus, die Zahlen
belegen: 03, 13, 31, 32, 33, 34. Mit Ausgaben als Artefakt. Punkt 4 der
Schwachstellenliste.

**Warum — und der Beweis kam vor dem Bau.** Beim lokalen Probelauf der sechs
fiel **Notebook 32** sofort: *„Kein Detroit-Bronze-Lauf"*, obwohl zwei da
lagen. Es suchte noch unter `bronze/detroit/` — dem Pfad von vor #39, der seit
gestern `city=detroit/` heisst. **Einen Tag lang still kaputt**, und niemand
hat es gemerkt, weil es niemand ausführte. Diese Notebooks sind die Belege der
Abgabe; ein Beleg, der nicht mehr läuft, ist keiner. Genau das hatte die
Analyse als Risiko benannt, und genau so ist es eingetreten.

**Die Linie.** Notebooks, die **Zahlen belegen**, laufen. Notebooks, die
**laden** (01, 02, 11, 12, 21, 22), laufen nicht — sie würden im Lauf
zusätzliche Bronze-Läufe erzeugen. Ein Formtest hält fest, dass jedes Notebook
im Repository auf einer der beiden Listen steht: Ein neues muss eingeordnet
werden, es kann nicht unbemerkt dazukommen.

**Warum im Datenlauf und nicht auf Pull Requests.** Sie brauchen `data/`.
Ohne gebaute Schichten haben sie nichts zu belegen.

**Was dazukam.** `nbconvert` und `ipykernel` als Dev-Abhängigkeiten; das
Lockfile aus einer frischen Installation neu eingefroren, jetzt 68 Pakete.

**Zahlen.** 705 → **708 Tests**. Lokal laufen alle sechs Notebooks in unter
40 Sekunden zusammen.

**Nachlesen.** `.github/workflows/datenlauf.yml` · PR #61

---

## 13.09.2026 · Ein wöchentlicher Datenlauf, damit die Wächter nicht nur lokal laufen (#60)

**Was.** `.github/workflows/datenlauf.yml`: montags 06:00 UTC und von Hand.
Lädt alle fünf Quellen, fährt den Controller, und lässt dann die **ganze**
Suite laufen — die 40 datengebundenen Tests eingeschlossen. Punkt 3 der
Schwachstellenliste.

**Warum.** `tests.yml` prüft auf jedem Pull Request 665 von 705 Tests. Die 40
übrigen brauchen gebaute Daten, und das sind ausgerechnet die Wächter: Zahlen
in den Abgabedokumenten gegen die Parquet-Dateien, die Einwohnerprobe, „kein
Delikt in der falschen Stadt". Alles, was am 12.9. an Absicherung entstand,
hatte einen blinden Fleck — **es lief nur, wenn jemand lokal `pytest`
tippte.** CI bewies den Code, nicht die Daten.

**Was ein rotes Ergebnis bedeutet.** Das ist der Kern, und er ist kein
Mangel: Die Quellen bewegen sich — Detroit ändert Einträge noch Jahre nach
der Tat, Chicago liefert Deltas. Wenn ein frischer Lauf andere Zahlen baut als
die in `ln1_konzept.md`, sind die Dokumente gegenüber der Quelle veraltet.
Genau das soll jemand erfahren, **bevor** er die alte Zahl auf eine Folie
setzt. Rot heisst: *„der dokumentierte Stand und die Quelle sind auseinander"*
— der Freshness-Alarm, den es bisher nicht gab.

**Was der Lauf braucht.** `CENSUS_API_KEY` als Repository-Secret. Ohne ihn
antwortet die Census-API mit HTTP 200 und einer HTML-Seite; der erste Schritt
prüft das Secret deshalb vorab und sagt, was fehlt — statt nach zwanzig
Minuten Ingestion bei Stufe 5 von 13 zu sterben. **Das Secret kann nur ein
Repository-Inhaber setzen; bis zum ersten grünen Lauf ist der Workflow eine
Einrichtung, kein Nachweis.** Tabelle 5.3 sagt es so.

**Was er nicht tut.** Daten committen. `data/` bleibt ausgeschlossen; was
bleibt, ist das Gesamtmanifest als Artefakt — auch bei Rot, gerade dann.

**Sieben Formtests** halten fest: Zeitplan und Handstart, nicht auf Pull
Requests, Controller vor den Tests, Secret vor der Strecke, Manifest auch bei
Rot, kein `git commit`.

**Zahlen.** 698 → **705 Tests**.

**Nachlesen.** `.github/workflows/datenlauf.yml` · PR #60

---

## 13.09.2026 · Die Unterströmungen gegen das Projekt geprüft — und drei Zeilen Werkzeug (#59)

**Was.** Tabelle 5.3 neu geschrieben und mit einem Wächter versehen; `ruff`,
ein Lockfile und Windows in der CI-Matrix. Punkte 1 und 2 der
Schwachstellenliste vom 13.9.

**Warum die Tabelle einen Wächter braucht.** Sie war **dreimal** veraltet,
während die Arbeit lief, die sie beschreibt: ein Feldkatalog als Lücke, den es
seit #57 gab; eine Orchestrierung als „bewusst offen", die seit #58 gebaut war;
eine leere Lücken-Spalte bei Software Engineering, wo kein Linter und kein
Lockfile existierten. Dieselbe Drift wie bei den Zahlen — nur in Worten.

Wörter lassen sich nicht gegen Parquet halten, aber jede Zeile behauptet oder
vermisst etwas, das als **Datei** existiert oder nicht. `test_unterstroemungen.py`
prüft: Was *Umsetzung* nennt, muss es geben; was *Lücke* nennt, darf es nicht
geben; und die Testzahl stimmt — eine dritte Stelle neben README und dieser
Datei.

**Was jetzt in der Tabelle steht — ehrlich.** Die grösste Lücke ist neu
benannt: **Die 40 datengebundenen Wächter laufen nur lokal.** CI beweist den
Code, nicht die Daten. Dazu: niemand ist für einen Datensatz verantwortlich,
keine Aufbewahrungsregel, keine Zeitplanung, die Notebooks laufen nicht in CI.

**Drei Zeilen Werkzeug.**

| | Was | Was es sofort fand |
| --- | --- | --- |
| `ruff` | Pyflakes plus `raise … from`; bewusst schmal, keine Stilregeln | **12 echte Funde**: 7 ungenutzte Importe, 3 `raise` ohne `from` in Chicagos Ingestion (verschluckt die Ursache), 8 Semikolon-Einzeiler — und einen Einzeiler-Import im Wächter selbst, noch bevor der lief |
| `requirements.lock` | exakte Versionen aus einer frischen Installation | die Drift war real: der Rechner hatte `numpy 2.5.2`, der frische Klon `2.5.3` |
| Windows in CI | `windows-latest` × Python 3.11 / 3.13 | Artan entwickelt darauf — eine Anleitung mit PowerShell und ein CI, das sie nie ausführt, widersprechen sich |

Importsortierung und `zip(strict=)` sind **nicht** aufgenommen: rund 60
Änderungen ohne einen gefangenen Fehler.

**Was erst die vier CI-Runden gezeigt haben.** Der erste Lauf war dreimal
rot, und jeder Fehler war eine eigene Lehre:

| Fund | Lehre |
| --- | --- |
| `numpy==2.5.3` verlangt Python ≥ 3.12 — beide 3.11-Jobs scheiterten an der Installation | **Ein Lockfile gilt je Interpreter.** 3.13 installiert aus dem Lock, 3.11 aus den Bereichen — und prüft damit, dass „3.11 oder neuer" noch stimmt |
| Windows 3.11 meldete *„No module named pytest"* statt des Installationsfehlers | **PowerShell bricht bei gescheitertem `pip` nicht ab.** Der Schritt läuft jetzt unter `bash` mit `set -e` |
| beide PDF-Werkzeuge trennen bewusst auf `\n` (Seitenvorschub), liessen unter Windows aber `\r` an jeder Zeile | echter Portabilitätsfehler, behoben — Artan hätte ihn auf seinem Rechner ebenso getroffen |
| auch danach: *„Code ohne Kategorie: Arson"* — Windows' `pdftotext` ist ein anderer Poppler-Build und setzt `-layout` anders | **Die drei PDF-Reproduktionen sind gegen `poppler-utils` unter Linux definiert** und überspringen sich unter Windows mit genau dieser Begründung, statt den Regex aufzuweichen |

Eine eigene Aussage musste ich dabei zurücknehmen: „die beiden MICR-Tests
bestanden unter Windows" — sie waren im ersten Lauf ebenfalls rot, mein
Log-Filter hatte nur den letzten Fehler gezeigt. Und eine Beobachtung bleibt
unerklärt: Das MICR-Werkzeug schreibt sein *FEHLER* nachweislich auf stderr,
CI sah trotzdem ein leeres stderr. Die Zusicherung zeigt deshalb künftig auch
stdout.

**Zahlen.** 694 → **698 Tests**; im frischen Linux-Klon 658, unter Windows
drei weniger.

**Nachlesen.** `docs/ln1_konzept.md` 5.3 · `tests/test_unterstroemungen.py` · PR #59

---

## 12.09.2026 · Ein Run-Controller, und drei Lücken, die er aufgedeckt hat (#58)

**Was.** `python -m orchestration.run_all` fährt Ingestion, Silver, Gold und
Serving in der richtigen Reihenfolge und schreibt ein Gesamtmanifest.

**Warum jetzt.** Die Annahme, die den Controller lange nach hinten schob, war
falsch: *„ein Jahrgang, einmal geladen, danach stabil."* **Die Quellen bewegen
sich dauernd** — Chicago und Detroit ändern Einträge noch Jahre nach der Tat;
Notebook 13 misst 10 umklassierte Delikte in 20 Stunden und 54,6 % des
Jahrgangs, die mehr als ein Jahr nach der Tat noch angefasst wurden. Damit ist
*„auf welchem Stand beruht diese Zahl?"* keine Formalie.

### Was er tut

| | |
| --- | --- |
| Reihenfolge | 13 Stufen, seriell. `tract` vor `crime_offense`, **beide** TIGER-Auslieferungen, Gold nach Silver |
| Abbruch | bei der ersten gescheiterten Stufe — jede weitere baute sonst auf einem halben Stand |
| Herkunft | `data/pipeline_run.json` nennt **jeden** Bronze-Lauf, auf dem das Ergebnis ruht |
| Fingerabdruck | ein Hash über die Eingaben. Zwei Läufe auf demselben Stand tragen denselben |
| Aktualität | wann jede der sechs Quellen zuletzt geladen wurde |

`--ohne-ingestion` leitet nur neu ab, ohne die Quellen anzufassen — **2
Sekunden** für Silver, Gold und Serving zusammen. `--trocken` zeigt den Plan.

### Was er bewusst nicht tut

Keine Prozesssperre: Ingestion-Läufe sind unveränderlich, Silver und Gold
werden atomar umbenannt — schlimmstenfalls gewinnt der zweite Lauf, und der
schreibt denselben Stand. Keine Wiederaufnahme: Jede Stufe ist idempotent und
die Strecke läuft in Minuten; „nochmal starten" löst dasselbe billiger als ein
Zustandsautomat, den niemand testet.

### Drei Lücken, die er aufgedeckt hat

Ein Controller, der alle Manifeste einsammelt, stolpert über jede
Uneinheitlichkeit:

| Lücke | Behoben |
| --- | --- |
| `silver/crime_offense` hatte als **einziges** Manifest keinen `status` | ergänzt — ausgerechnet die Tabelle, die den Vergleich trägt, sagte nicht, ob ihr Bau durchlief |
| dieselbe Tabelle hatte **keine `row_count`** — die Zahl stand nur je Stadt verschachtelt | ergänzt, wie bei jeder anderen Tabelle |
| **zwei Statusvokabulare**: acht Module schreiben `complete`, Detroit `SUCCESS`; dazu `completed_at_utc` gegen `finished_at` | der Controller nimmt beide und sagt an einer Stelle, warum |

Das dritte habe ich **nicht** vereinheitlicht: Es würde jedes bereits
geschriebene Manifest ungültig machen, für einen kosmetischen Gewinn.

**Zahlen.** 681 → **694 Tests**; im frischen Klon laufen 654 davon.

**Nachlesen.** `src/crime/orchestration/` · PR #58

---

## 12.09.2026 · Ein Feldkatalog, der nicht veralten kann (#57)

**Was.** `docs/feldkatalog.md` — **131 Spalten in 9 Tabellen**, je mit Typ und
Bedeutung. Dazu das Werkzeug, das ihn erzeugt, und vier Tests, die ihn
vollständig halten.

**Warum.** Kapitel 9 nannte als Grenze: *„Kein Feldkatalog. Die Bedeutung der
Felder steht in den Modul-Docstrings und Manifesten, aber nicht an einer Stelle
zusammen."* Das war die letzte offene Umsetzungs-Grenze.

**Warum erzeugt und nicht geschrieben.** Ein Feldkatalog ist genau die Sorte
Dokument, die still veraltet — und in diesem Projekt ist das mit Zahlen schon
**zweimal** passiert. Spaltennamen und Typen kommen deshalb aus den
**Manifesten** der gebauten Tabellen; sie stimmen per Konstruktion. Von Hand
gepflegt wird nur, was sich nicht ableiten lässt: die Bedeutung.

**Wie eine neue Spalte dazukommt.** Der Lauf **scheitert** und nennt sie:

```
1 Spalten ohne Beschreibung:
  gold/fact_offense.geo_status
```

Der Umweg ist Absicht — wer eine Spalte hinzufügt, soll einen Satz darüber
schreiben müssen. Gegenprobe gemacht.

**Vier Tests** halten fest: jede gebaute Spalte hat eine Beschreibung, keine
Beschreibung zeigt ins Leere, jede Spalte steht auch im Dokument (sonst wäre
es nicht neu erzeugt worden), und ein zweiter Lauf liefert dieselbe Datei —
dasselbe Verfahren wie bei den drei Crosswalk-Werkzeugen.

**Ein Fund beim Bauen.** Weil der Katalog das Korn aus den Manifesten liest,
fiel auf, dass `silver/crime_offense` dort noch **„ein Delikt"** stand. Seit
dem Tatkorn-Umbau ist eine Zeile eine **Anklage**. Das Korn ist die Aussage,
die eine Tabelle über sich selbst macht — jetzt lautet sie *„eine Anklage; je
Tat ist eine Zeile mit `counts` markiert"*, und ein Test hält sie fest.

**Zahlen.** 673 → **681 Tests**; im frischen Klon laufen 641 davon.

**Nachlesen.** `docs/feldkatalog.md` · PR #57

---

## 12.09.2026 · Der räumliche Join ist jetzt unabhängig geprüft (#56)

**Was.** Notebook 34 hat einen Abschnitt 3.2: die Stadtzuordnung gegen eine
zweite, unabhängige Referenz gehalten — und die 6'445 Fälle ohne
Stadtzuordnung nach Ursache klassifiziert.

**Warum.** Kapitel 9 nannte als Grenze: *„Der räumliche Join ist nicht
unabhängig validiert."* Der Grund war H7 — Detroits eigene
`census_block_2020_geoid` widerspricht Detroits eigenen Koordinaten und taugt
nicht als Referenz. Die zweite Referenz lag aber die ganze Zeit im Projekt:
**`silver/place`, die Stadtgrenze selbst.** Die Mehrheitsregel geht den Umweg
über den Tract; denselben Punkt kann man **direkt** gegen die Ortsgrenze
halten. Andere Geometrie, andere Operation, dieselbe Frage.

### Das Ergebnis

| Mehrheitsregel | direkte Ortsgrenze | Fälle |
| --- | --- | ---: |
| chicago | chicago | 251'515 |
| detroit | detroit | 84'658 |
| (keine) | chicago | **5'249** |
| (keine) | ausserhalb | 1'185 |
| (keine) | detroit | 12 |
| chicago | ausserhalb | **1** |

**Kein einziger Fall wird der falschen Stadt zugeordnet.** Keine Zeile sagt
*Chicago* per Regel und *Detroit* per Ortsgrenze oder umgekehrt. Das ist die
Zusage, auf der jeder Städtevergleich ruht, und sie ist damit bestätigt. Ein
Test hält sie fest.

Die Abweichungen liegen **alle in einer Richtung**: Die Regel schliesst aus,
was drin ist. Genau **ein** Fall von 251'516 wird fälschlich eingeschlossen.

### Die 6'445, klassifiziert

| | Chicago | Detroit |
| --- | ---: | ---: |
| in der meldenden Stadt (Tract gehört der Nachbargemeinde) | 5'249 | 12 |
| in einer Nachbargemeinde (Oak Park, Evanston, Warren …) | 716 | 415 |
| in keiner Gemeinde (nicht eingemeindet) | 42 | 11 |

Die mittlere Gruppe gehört **zu Recht** nicht in den Zähler — dort hat die
Stadtpolizei jenseits der Stadtgrenze erfasst. Die erste ist ein Fehler der
**Regel**, nicht der Daten.

### Und die Rate? Sie ist verzerrt — messbar

**Die Randtracts sind überdurchschnittlich deliktdicht.** Die 5'249 Chicagoer
Fälle sitzen auf rund 23'100 anteiligen Einwohnern: **227 Delikte je 1'000**
gegen 94,5 im Stadtschnitt. Plausibel — Gewerbestreifen, Verkehrsachsen,
Flughafenumland, wo viele Menschen sind und wenige wohnen.

| Stadt | Delikte | Einwohner | Rate |
| --- | ---: | ---: | ---: |
| Chicago, Mehrheitsregel | 251'516 | 2'661'953 | **94,5** |
| Chicago, mit den Grenzfällen | 256'765 | 2'685'096 | **95,6** |
| Detroit | 84'658 | 638'635 | **132,6** (unverändert) |

**Für die Präsentation.** Der Abstand schrumpft leicht: 132,6 gegen 94,5 sind
40 % mehr, gegen 95,6 noch 39 %. Die Aussage bleibt, ihre Grösse verschiebt
sich um gut einen Prozentpunkt — und das ist jetzt **gemessen statt unbekannt**.

**Warum die Regel trotzdem bleibt.** Eine Zuordnung je Punkt machte den Zähler
genauer und den Nenner unmöglich: Einwohnerzahlen gibt es nur je Tract. Man
bekäme eine exakte Zahl oben und eine geschätzte unten — schlechter als zwei
Zahlen, die derselben Regel folgen.

**Zahlen.** 672 → **673 Tests**.

**Nachlesen.** `notebooks/34_gold_sternschema.ipynb` Abschnitt 3.2 · PR #56

---

## 12.09.2026 · `mapping_status` und `geo_status`, und ein Publish-Gate (#55)

**Was.** Zwei neue Spalten und eine Schwelle, unter der Gold nicht
veröffentlicht wird. Aus der Schwachstellenanalyse, Massnahme 1 und 3.

**Warum.** Drei bekannte Schwächen standen bisher nur in der Dokumentation:
die 90Z-Auffangzuordnungen, die Randfälle ausserhalb der Stadtgrenze, die
fehlenden Koordinaten. Jede Auswertung musste sie selbst herleiten — und
konnte sie ebenso gut vergessen. Als Spalten sind sie **abfragbar**.

### `mapping_status` — darf ich diese Zeile vergleichen?

`nibrs_match` sagt, *woher* eine Zuordnung stammt. `mapping_status` fasst das
zu der Frage zusammen, die eine Auswertung stellt:

| Wert | Bedeutung | Chicago | Detroit |
| --- | --- | ---: | ---: |
| `exact` | ein amtliches Dokument bildet den Code so ab | 95,61 % | 94,65 % |
| `ambiguous` | **wir** haben entschieden, weil die Quellen auseinandergingen | 1,43 % | 1,63 % |
| `fallback_90Z` | gültiger Code, aber der Auffang — für einen Deliktvergleich wertlos | 2,97 % | 3,72 % |
| `unmapped` | kein Code | 3 Zeilen | 0 |

**Die Kategorie `ambiguous` ist der eigentliche Gewinn.** Dahinter stecken 17
IUCR-Codes, bei denen Chicagos Einordnung und NIBRS auseinandergehen — Chicago
führt `0760` als *Burglary from Motor Vehicle*, NIBRS zählt das als `23F Theft
from Motor Vehicle`. Beides vertretbar, aber es ist eine **Entscheidung und
keine Ableitung**. Dasselbe gilt für Detroits drei Codes, die wir über die
File-Class-Angabe aufgelöst haben. Bisher sahen diese 5'340 Zeilen aus wie
jede andere.

### `geo_status` — warum eine Zeile in einer Tract-Auswertung fehlt

| Wert | Zeilen |
| --- | ---: |
| `inside_city` | 336'174 |
| `outside_city` | 6'445 |
| `missing_coordinate` | 1'997 |
| `no_tract` | 1 |

`located` sagte bisher nur *dass* eine Zeile fehlt. Der Unterschied zählt: Ohne
Koordinate hat die **Quelle** nichts geliefert, ausserhalb der Stadt hat
**unsere Mehrheitsregel** entschieden. Das erste ist eine Lücke, das zweite
eine Entscheidung — eine Auswertung darf sie nicht in einen Topf werfen.

Die Spalte entsteht in **Gold** und nicht in Silver: Die vierte Stufe braucht
die Stadtgrenze, und die kennt erst `dim_tract`.

### Das Publish-Gate

Gold wird nur gebaut, wenn die Abdeckung trägt. Zwei Prüfungen:

* **Ohne Spielraum:** Kommt ein Statuswert vor, den der Code nicht kennt, hat
  jemand die Einstufung geändert — der Bau bleibt stehen. Dasselbe in Silver
  für eine unbekannte Herkunft in einem Crosswalk.
* **Mit Spielraum:** `inside_city` ≥ 90 %, `exact` ≥ 85 %, `unmapped` ≤ 1 %.

**Die Schwellen sind Böden, keine Ziele.** Gemessen liegen die Werte bei
97,55 %, 95,49 % und 0,0009 %. Der Abstand ist Absicht: Das Gate soll einen
*Einsturz* abfangen — einen gebrochenen räumlichen Join, einen Crosswalk, der
ins Leere läuft —, nicht die normale Bewegung der Quelle. Ein eng gezogenes
Gate wäre schlimmer als keines: Es würde bei jeder Datenbewegung rot, und die
erste Reaktion wäre, es hochzusetzen statt hinzusehen. Ein Test hält fest,
dass mindestens fünf Prozentpunkte Luft bleiben.

**Messen und Entscheiden sind getrennt.** `abdeckung()` misst und schreibt ins
Manifest, `pruefe_gate()` entscheidet und wird nur vom Bau gerufen. Sonst
hätte eine Testfixture mit zwei Zeilen das Gate gerissen — sie hat
naturgemäss schräge Anteile.

**Für die Präsentation.** Jede Grafik kann jetzt die Abdeckung danebenstellen,
ohne sie neu herzuleiten. Und die Frage *„sind die 3 % auf 90Z vergleichbar?"*
hat eine Spalte statt einer Fussnote.

**Zahlen.** 662 → **672 Tests**. An den Daten ändert sich nichts; die beiden
Spalten kommen dazu.

**Nachlesen.** `MAPPING_STATUS` in `build_crime_offense.py`, `GATE_MINDESTENS`
in `gold_pipeline/__init__.py` · PR #55

---

## 12.09.2026 · CI — die Tests laufen jetzt auch ohne uns (#54)

**Was.** `.github/workflows/tests.yml`: die Suite auf jedem Pull Request und auf
`main`, unter Python **3.11 und 3.13**. Dazu sieben veraltete Statuszeilen in
`leistungsnachweise.md` nachgezogen.

**Warum.** Bis heute liefen die Tests nur, wenn jemand daran dachte. **Zweimal**
ist dabei eine Zahl in den Abgabedokumenten veraltet, ohne dass etwas rot wurde
— gefunden hat es beide Male ein Zufall. Seit es Wächter für diese Zahlen gibt,
müssen sie auch automatisch laufen.

**Was CI prüft — und was nicht.** In einem frischen Klon laufen **628 der 662
Tests**. Die übrigen 34 überspringen sich selbst, weil sie gebaute Daten
brauchen und `data/` nicht versioniert ist. Das ist eine ehrliche Grenze: Die
Zahlen *gegen die Parquet-Dateien* prüft nur ein lokaler Lauf. Was in CI läuft,
ist trotzdem das Wesentliche — die Reproduzierbarkeit der Crosswalks aus den
amtlichen PDFs, die Form der Dokumente, und **beide Wächter über die Testzahl**.

**Ein Fund beim Proben.** Der Probelauf in einem frischen Klon zeigte, dass
`openpyxl` **nirgends deklariert** war. Lokal ist es installiert, in CI wäre es
das nicht — und damit hätten sich **sechs Tests stillschweigend übersprungen**:
genau die, die die 81 NIBRS-Bezeichnungen gegen Illinois' IEPD-Arbeitsmappe
halten, also gegen die *zweite* Quelle. Die Codeliste hätte in CI wieder nur
eine Quelle gehabt. Jetzt steht `openpyxl` in den Testabhängigkeiten: **622 →
628** Tests im frischen Klon.

**Die Matrix ist kein Selbstzweck.** Das README sagt „Python 3.11 oder neuer".
Mit zwei Versionen im Lauf ist das eine geprüfte Aussage statt einer
Behauptung.

**Sieben Statuszeilen nachgezogen.**

| Stand da | Tatsächlich |
| --- | --- |
| Storage „nicht evaluiert" | Notebook 31 misst, Kapitel 7 schreibt es aus |
| „Silver ist leer" | vier Tabellen, 347'957 Zeilen |
| „für Chicago fertig" | beide Städte, seit Notebook 13 |
| „Detroit-Quellnotebook fehlt" | Notebook 11 |
| „Bronze-Format ist offen" | Parquet, Absprache 4.1 |
| Arbeitsteilung „verschoben" | geregelt am 12.9. |
| Absprache 4.2 „Entscheid: Hängt von 4.1 ab" | Variante A, umgesetzt in PR #39 |

**Der erste Lauf fiel durch — und das war nützlich.** `pdftotext` fehlt auf
`ubuntu-latest`. Mein Probelauf hatte das nicht gezeigt, weil er auf dem Mac
lief, wo poppler installiert ist: **Ein frischer Klon allein ist keine treue
CI-Simulation, die Systemwerkzeuge kommen vom Host.** Dabei kam noch eine
Ungleichbehandlung heraus — zwei Tests übersprangen sich bei fehlendem
`pdftotext` sauber, zwei andere fielen rot. Jetzt teilen sie sich eine
Bedingung, und CI installiert `poppler-utils`, damit die Reproduzierbarkeit
der Crosswalks dort wirklich geprüft wird statt übersprungen.

**Nachgemessen statt geschätzt:** **628 von 662** Tests laufen im CI-Lauf, 34
überspringen sich mangels `data/`. Beide Matrix-Jobs grün in je 1 min 50 s.

**Nachlesen.** `.github/workflows/tests.yml` · PR #54

---

## 12.09.2026 · Ein Widerspruch im Konzept, und ein Reproduktionsweg, der nicht lief (#53)

**Was.** Aus einer externen Schwachstellenanalyse: zwei Befunde geprüft und
behoben, plus die Herkunft von `dim_offense`.

### Der Widerspruch

Kapitel 5.2 sagte unter *Was ausdrücklich nicht geliefert wird*:

> **Keine zeilenweisen Falldaten.** Gold ist aggregiert; wer einzelne Fälle
> braucht, geht auf Silver.

`fact_offense` führt `offense_id`, `occurred_at_local`, `latitude`,
`longitude` — **eine Zeile je Tat**. Der Satz war falsch, und er widersprach
der eigenen Kernbegründung: Notebook 34 und die Erklärseite argumentieren
ausführlich *„Gold behält deshalb das Korn"*. Ein Überbleibsel des
Würfel-Entwurfs, beim Umstieg auf das Sternschema nie nachgezogen.

**Warum das mehr wiegt als eine veraltete Zahl.** Eine falsche Zahl ist ein
Fehler; ein Widerspruch zwischen zwei Kapiteln desselben Dokuments ist eine
Einladung zur Nachfrage — ein Prüfer liest 5.2 und öffnet `fact_offense`.

Der Abschnitt sagt jetzt, was tatsächlich gilt: **keine vorberechneten
Aggregate**, und was ein Dashboard zeigt, ist eine engere Auswahl als Gold —
Aggregate je Tract und Zeitraum, ohne Identifikatoren und Punktkoordinaten.
Die alte Fassung steht als Korrekturhinweis dabei, statt spurlos zu
verschwinden.

### Der Reproduktionsweg

Kapitel 10 nachgespielt. Drei Fehler:

| Stand da | Problem |
| --- | --- |
| `extract_detroit --year 2024` | **gibt es nicht** — der Aufruf ist `--mode full --years 2024` |
| `download_tiger` ohne `--auslieferung` | lädt nur Tracts. Ohne `place` bekommt `dim_tract` **keine Stadtzuordnung** — und das scheitert nicht, es liefert still ein Gold ohne Städte |
| Silver mit zwei von vier Tabellen | `build_place` und `build_crime_offense` fehlten, Gold und Serving ganz |

Jetzt stehen alle 15 Befehle da, und **jeder ist nachgeprüft**: `--help` läuft
bei allen durch. Ein Reproduktionsabschnitt, der nicht läuft, ist in einer
Abgabe schlimmer als keiner — er behauptet Reproduzierbarkeit.

### Die Herkunft von `dim_offense`

Ihr `derived_from` war **leer** — ausgerechnet bei der Dimension, die
entscheidet, was in beiden Städten als welches Delikt zählt. Die übrigen vier
Gold-Tabellen nannten ihre Silver-Quellen korrekt; diese fiel durch, weil sie
nicht aus Silver kommt, sondern aus zwei Dateien unter `config/`. `Quelle`
trägt jetzt eine Schicht, und das Manifest nennt sie.

**Was aus der Analyse *nicht* übernommen wurde.** Der Befund *„Detroit hat
keinen automatisch fortgeschriebenen Wasserstand"* ist keine Lücke, sondern
eine gemessene Entscheidung: 54,6 % des Jahrgangs wurden mehr als ein Jahr nach
der Tat noch geändert, ein Wasserstand nach Tatdatum verpasst genau diese
Korrekturen. Ein voller Snapshot dauert 97 Sekunden.

**Zahlen.** 660 → **662 Tests**. An den Daten ändert sich nichts.

**Nachlesen.** `docs/ln1_konzept.md` 5.2 und 10 · PR #53

---

## 12.09.2026 · Die Tract-Umrisse als GeoJSON, für eine Karte (#52)

**Was.** `python -m serving.export_geojson` schreibt
`data/serving/tracts.geojson` — die **1'055 Tract-Umrisse** der beiden Städte,
0,55 MB.

**Warum.** Eine Choroplethenkarte färbt Flächen ein, braucht also Polygone.
`gold/dim_tract` führt aber nur **Zentroide**; die Umrisse liegen in
`silver/tract` als WKB, ein Format, das kein Browser liest. Das war die Lücke
zwischen dem, was gebaut ist, und dem, was ein Dashboard bräuchte.

**Warum die Geometrie nicht nach Gold wandert.** `dim_tract` deckt beide
Countys ab, nicht nur die Städte — mit Geometrie wäre die Dimension **26 MB
statt 0,4 MB**, und jedes `SELECT *` darauf schleppte sie mit. Gold soll klein
bleiben.

**Zahlen — die Vereinfachung ist gemessen, nicht geschätzt.**

| Toleranz | Datei | Fläche je Tract | Stadtfläche gesamt |
| --- | ---: | ---: | ---: |
| keine | 2,94 MB | – | – |
| **0,00002 (~2 m)** | **0,55 MB** | −0,0002 % | −0,011 % |
| 0,0001 (~11 m) | 0,42 MB | −0,0008 % | −0,055 % |
| 0,0005 (~56 m) | 0,37 MB | −0,0826 % | – |

Der ganze Gewinn liegt in den ersten zwei Metern. Die letzte Spalte misst die
**Vereinigung** aller Tracts einer Stadt und beantwortet damit die Frage, ob
zwischen Nachbarflächen Lücken aufreissen, wenn eine gemeinsame Grenze zweimal
unabhängig vereinfacht wird — 0,011 % entspricht einem Saum von Zentimetern.

**Keine Kennzahl in der Datei.** Je Fläche nur `geoid`, `city`, `tract_name`.
Wer einfärben will, verbindet über `geoid` mit `dim_tract` und `fact_offense`.
Die Einwohnerzahl mitzugeben wäre eine zweite Wahrheit, die nach einem
Gold-Neubau still den alten Nenner zeigt — derselbe Grund, aus dem die
Auswertungsdatenbank Sichten hält und keine Kopien.

**Für die Präsentation: was das Bild belegt.** Die 1'055 Flächen einmal
gezeichnet, bestätigen zwei Entscheidungen der Pipeline:

* **Detroit hat zwei Löcher** — Hamtramck und Highland Park, zwei
  eigenständige Städte, vollständig von Detroit umschlossen. 14 Tracts dort
  tragen keine Stadtzuordnung; die Mehrheitsregel hat sie korrekt
  ausgeschlossen. Wären sie dabei, wäre Detroits Nenner zu gross und die Rate
  zu niedrig.
* **Chicagos abgetrennter Block im Nordwesten** ist O'Hare. Tract 9800 hat dort
  **null Einwohner** — genau die Sorte Fläche, für die die Rate `NULL` ist und
  nicht null.

**Zahlen.** 649 → **660 Tests**.

**Nachlesen.** `src/crime/serving/export_geojson.py` · PR #52

---

## 12.09.2026 · Vier fehlende Einträge — und eine Regel, die sich widersprach (#51)

**Was.** Die Einträge zu **#25, #28, #31 und #37** nachgetragen, die Kopfregel
entwirrt, und ein Abschnitt *Bewusst ohne Eintrag* angelegt.

**Warum.** Auf die Frage, ob diese Datei nachgeführt sei, lautete die ehrliche
Antwort: **nein.** Vier gemergte Pull Requests hatten keinen Eintrag, und es
war kein Zufall, dass es ausgerechnet vier waren — im Kopf standen **zwei
Regeln, die sich widersprechen**:

> „Ein Eintrag je gemergtem Pull Request" · „Refactorings, Testarbeit und
> Aufräumen stehen deshalb bewusst **nicht** hier."

Beides zusammen geht nicht. Wo zwei Regeln gelten, gilt keine — und die Praxis
wurde uneinheitlich: #45 (Testarbeit) bekam einen Eintrag, #37 (ebenfalls
Testarbeit) nicht.

**Was gefehlt hat.**

| PR | Warum er hingehört |
| --- | --- |
| **#25** | der Zeitzonen-Fix: Detroits Jahresfenster war in UTC gezogen — 66 Fälle aus dem falschen Jahr, 56 fehlende vom Jahresende |
| **#28** | die ganze Auswertungsumgebung, samt der Messung Sichten gegen Kopie (0,3 MB gegen 45,1 MB) |
| **#31** | die NIBRS-Codeliste bekam eine zweite Quelle — vorher hätte ein Tippfehler beide Städte gleichzeitig verschoben |
| **#37** | aus „die Crosswalks sind reproduzierbar abgeleitet" wurde eine geprüfte Zusage statt einer Behauptung |

**Die neue Regel.** Ein Eintrag entsteht, wenn sich etwas ändert, das die Abgabe
**behauptet** — eine Zahl, eine Zusage, oder eine korrigierte Aussage in einem
Abgabedokument. Alles andere kommt unter *Bewusst ohne Eintrag*, mit
Begründung.

**Damit es nicht wieder passiert.** Zwei Tests: Die PR-Nummern müssen
**lückenlos** sein — jede ist entweder ein Eintrag oder ausgelassen —, und
keine darf beides sein. Der erste braucht kein Netz: Eine fehlende Nummer
fällt schon an der Lücke auf. Gegenprobe gemacht, `#27` aus der Liste
genommen: *„Diese Pull Requests sind weder Eintrag noch ausgelassen: [27]"*.

**Zahlen.** 647 → **649 Tests**.

**Nachlesen.** `tests/test_aenderungen.py` · PR #51

---

## 12.09.2026 · Das README überarbeitet (#49)

**Was.** Neu geschrieben: eine Erklärung, worum es im Projekt geht, die
Einrichtung, der vollständige Ladeweg aller fünf Quellen, die Fehlerbehebung
und die Tests. Von 484 auf 376 Zeilen — kürzer und trotzdem vollständiger.

**Warum.** Das README beschrieb Chicago und das Wetter ausführlich und
**Detroit, Gold und Serving gar nicht**. Wer danach vorging, kam bis Bronze und
dann nicht weiter. Drei Aussagen waren zudem überholt:

| Stand da | Richtig |
| --- | --- |
| „239 bestandene Tests" | **647** |
| `crime_offense` ○ offen, „drei Tabellen" | gebaut, **vier** Tabellen — `place` fehlte ganz |
| kein Wort zu Gold, Serving, Detroit-Ingestion | jetzt mit Befehl und Begründung |

**Die Lücke, die am meisten gekostet hätte.** `CENSUS_API_KEY` war **nirgends
erwähnt**, obwohl er für die ACS-Daten Pflicht ist — und die Census-API
antwortet ohne Schlüssel mit **HTTP 200** und einer HTML-Seite „Missing Key".
Wer dem README folgte, wäre an dieser Stelle ohne verständliche Meldung
steckengeblieben.

**Neu gegenüber vorher.** Der Ladeweg steht jetzt als Reihenfolge da — Ingestion
je Quelle, dann Silver in der richtigen Abfolge (`tract` vor `crime_offense`),
dann Gold und Serving mitsamt einer lauffähigen Beispielabfrage. Dazu sieben
neue Zeilen in der Fehlerbehebung: der fehlende Census-Schlüssel, `.env` aus
dem falschen Verzeichnis, fehlendes Detroit-Bronze, die alten NDJSON-Bestände
und die gesperrte DuckDB-Datei.

**Damit es nicht wieder veraltet.** `tests/test_abgabedokumente.py` prüft jetzt
auch das README: die fünf Zeilenzahlen, beide Raten und die Testzahl selbst.
Gegenprobe gemacht — eine Zahl auf den alten Stand gesetzt, der Test fällt mit
`assert 84648 == 84658`. **639 → 647 Tests**, die acht neuen sind diese Prüfung.

**Nachlesen.** `README.md` · PR #49

---

## 12.09.2026 · Die Erklärung zu Würfel und Stern auch als Markdown (#48)

**Was.** `docs/sternschema-und-wuerfel.md`, inhaltsgleich mit der HTML-Fassung,
plus die drei Diagramme als eigenständige Dateien unter `docs/bilder/`.

**Warum.** Die übrigen Dokumente in `docs/` sind Markdown; eine HTML-Datei
lässt sich im Repository weder überfliegen noch im Pull Request kommentieren.
GitHub stellt Markdown direkt dar, HTML nicht.

**Worauf dabei zu achten war.** Im HTML erben die Diagramme Farbe und Tokens
vom Dokument: `currentColor` für die Linien, `var(--signal)` für die
Hervorhebung. Als eigene Datei in einem `<img>` erbt eine Grafik **nichts** —
`currentColor` fiele auf Schwarz zurück und `var(--signal)` wäre schlicht
ungültig; die hervorgehobene Zelle wäre verschwunden. Jede der drei Dateien
trägt ihre Farben deshalb selbst, in einem `<style>`-Block mitsamt
`prefers-color-scheme` fürs dunkle Thema.

**Geprüft.** Alle sechs Verweise des Dokuments lösen auf, und jede SVG-Datei
rendert eigenständig — also ohne das HTML-Stylesheet ringsum.

**Nachlesen.** `docs/sternschema-und-wuerfel.md` · PR #48

---

## 12.09.2026 · Würfel und Sternschema werden erklärt, nicht vorausgesetzt (#47)

**Was.** Notebook 34 bekommt vor Abschnitt 1 einen Erklärteil mit drei
Diagrammen, und `docs/sternschema-und-wuerfel.html` fasst dasselbe als Seite
zusammen.

**Warum.** Das Notebook **mass** die Entscheidung, erklärte aber nie, was ein
Würfel und was ein Sternschema ist. Wer die Begriffe nicht schon kennt, liest
Messwerte ohne zu wissen, wofür. In einer Abgabe ist das die Stelle, an der
nachgefragt wird.

**Die drei Diagramme.**

| Diagramm | Was es zeigt |
| --- | --- |
| Der Würfel | die drei gewählten Achsen, eine hervorgehobene Zelle — und darunter, was in ihr nicht mehr steckt |
| Das Sternschema | `fact_offense` in der Mitte, vier Dimensionen aussen, jede Kante mit ihrem JOIN-Schlüssel |
| Die Kornleiter | vier Balken nach Zeilenzahl: Silver, Gold, und die zwei verworfenen Würfel |

**Zahlen — die Kornleiter ist gerechnet, nicht geschätzt.** Der verworfene
`fact_tract_month` hätte **95 219** Zeilen gehabt, `fact_city_day` **11 156**.
Damit lässt sich der Handel beziffern: Der Schritt von Silver zu Gold kostet
**3 340** Zeilen (Detroits Mehrfachanklagen), der Schritt zum Würfel **249 398**
— und mit ihnen jede Frage, die feiner ist als Monat und Deliktfamilie.

**Für die Präsentation.** Die Seite hat einen Abschnitt *„Wann ein Würfel
trotzdem richtig ist"*. Die Entscheidung gilt für **diese** Datenmenge, nicht
allgemein — bei zwei Grössenordnungen mehr kehrt sie sich um, und der Würfel
liesse sich aus dem Stern jederzeit nachbauen. Umgekehrt nicht. Das ist die
ehrlichere Fassung als „Sternschema ist besser".

**Nachlesen.** `notebooks/34_gold_sternschema.ipynb` · `docs/sternschema-und-wuerfel.html` · PR #47

---

## 12.09.2026 · Querverweise zwischen Silver und Gold (#46)

**Was.** Drei Verweise in `ln1_konzept.md`, damit beide Schichten
auffindbar sind, ohne den Aufbau zu ändern.

**Warum.** Silver steht in Kapitel 8 (Transformation), **Gold in 5.2**
(Serving). Das ist begründet — Gold entstand aus der Serving-Entscheidung, nicht
aus einer Qualitätsfrage. Wer aber die Schichten sucht, findet sie nicht
nebeneinander und schliesst im Zweifel, Gold sei nicht beschrieben. Genau diese
Frage kam auf.

**Wo.**

| Stelle | Verweis |
| --- | --- |
| Kapitel 8, vor 8.1 | Kasten: Gold ist in 5.2 beschrieben, die Reihenfolge bleibt Bronze → Silver → Gold → Serving, der Verzeichnisbaum steht in 7.4 |
| 5.2, beim Sternschema | Gold setzt auf `silver/crime_offense` auf und ordnet an, deutet aber nichts Neues — gedeutet wird in 8.2 |
| 5.1, Lebenszyklus-Tabelle | Zeile *Transformation* nennt Gold und sagt, dass es in 5.2 steht |

Beide Ankerlinks sind gegen die Überschriften geprüft, damit kein toter Verweis
entsteht — der wäre schlimmer als keiner.

**Nachlesen.** `docs/ln1_konzept.md` Kapitel 5.1, 5.2 und 8 · PR #46

---

## 12.09.2026 · Die Zahlen in den Abgabedokumenten werden jetzt bewacht (#45)

**Was.** `tests/test_abgabedokumente.py` — 14 Tests, die die Zahlen in
`ln1_konzept.md` und `projektabsprache.md` gegen die gebauten Parquet-Dateien
prüfen.

**Warum.** Der Neubau von Silver und Gold hat **fünf Zahlen stehen lassen**,
und alle Tests blieben grün, weil keiner diese Dateien ansieht. Gefunden wurden
sie erst auf die Frage hin, wo Silver und Gold eigentlich dokumentiert sind:

| Stelle | stand da | richtig |
| --- | ---: | ---: |
| Konzept 1, Detroits Korn | 85'335 Taten | **85'345** |
| Konzept 5.2, `fact_offense` | 344'607 | **344'617** |
| Konzept 5.2, Detroits Korn | 85'335 | **85'345** |
| Konzept 5.2, Detroits Rate | 84'648 · 132,5 | **84'658 · 132,6** |
| Absprache 5.2 | 344'607 | **344'617** |

Das ist die teuerste Art Fehler in einer Abgabe: Eine Zahl auf einer Folie
stimmt nicht mit der im Konzept überein, und niemand weiss mehr, welche gilt.
`AENDERUNGEN.md` war schon bewacht — die beiden Dokumente, aus denen die Abgabe
selbst entsteht, nicht.

**Was geprüft wird.** Die Zeilenzahlen aller vier Silver- und fünf
Gold-Tabellen, Detroits Korn (Anklagen zu Taten), beide Raten je 1'000
Einwohner samt Zähler und Nenner, und die H3-Tabelle in 8.5. **Nicht** geprüft
wird der Fliesstext: Er beschreibt Entscheidungen und soll sich nicht mit jedem
Ladelauf ändern. Fehlt `data/`, wird übersprungen statt rot.

Gegenprobe gemacht: Eine Zahl absichtlich auf den alten Stand gesetzt, der Test
fällt mit `assert 344607 == 344617`.

**Nebenbei.** Kapitel 11 „Wo was liegt" nannte den **Silver**-Aufbau, aber
nicht den Gold-Aufbau, und Notebook 03 (Datenqualität Chicago), aber nicht
Notebook 13. Beide ergänzt. Ausserdem im Docstring von `build_gold.py` derselbe
überholte Absatz wie in Notebook 34: `dim_offense` führt seit dem
Kategorien-Werkzeug 42 amtliche Kategorien.

**Zahlen.** 625 → **639 Tests**.

**Nachlesen.** `tests/test_abgabedokumente.py` · PR #45

---

## 12.09.2026 · Die Geo-Lücke beider Städte auf einer Achse (#44)

**Was.** Notebook 34 hat einen Abschnitt 5.2: Der Ausfall fehlender
Koordinaten, gemessen für beide Städte über `dim_offense.nibrs_category` statt
je Stadt über ihre Hauskategorien.

**Warum.** H1 war je Stadt vorgeprüft — Chicago in Notebook 03, Detroit in
Notebook 13. Nur stand die Frage dort in **unvergleichbaren** Kategorien:
Chicago kennt „Delikte an Kindern", Detroit „Family Offense". Ob dieselbe
Ursache wirkt, liess sich so nicht sagen. Genau dafür gibt es `dim_offense`.

**Zahlen.** Verglichen wird das Vielfache des jeweiligen Stadtschnitts (Chicago
verliert 0,67 %, Detroit 0,29 %):

| NIBRS-Kategorie | Chicago | Detroit |
| --- | ---: | ---: |
| Sex Offenses | 4,39 % · **6,5×** | 1,50 % · **5,1×** |
| Fraud Offenses | 3,48 % · **5,2×** | 0,19 % · 0,6× |
| Prostitution Offenses | 1,94 % · 2,9× | 0,33 % · 1,1× |

**Das Ergebnis ist geteilt — und das ist der Punkt.**

* **Sexualdelikte** fehlen in **beiden** Städten stark überproportional.
  Gleiche Richtung, vermutlich gleiche Ursache: die zurückgehaltene Adresse.
  Dieser Teil der Lücke verzerrt den Städtevergleich **nicht**.
* **Betrug** fehlt **nur** in Chicago — Faktor 18 zwischen den Städten.
  Plausibel ist Betrug ohne Tatort (Telefon, online), den Chicago mitführt und
  Detroits Vorfallsbericht so nicht kennt. Hier ist Chicagos Zahl die
  untererfasste.

**Für die Präsentation.** Der Vergleich der **Gesamtraten** trägt: 0,67 % gegen
0,29 % Ausfall verschieben keine Rangfolge. Ein Vergleich **je Delikttyp**
trägt bei Sexualdelikten, weil die Verzerrung gleichgerichtet ist — bei
**Betrug nicht**. Wer die Städte dort gegeneinanderstellt, muss die Abdeckung
danebenstellen.

**Eine frühere Aussage korrigiert.** In der Übergabe vom selben Tag stand, der
Geoausfall sei „in beiden Städten in denselben Kategorien verzerrt". Das war zu
stark: Es gilt für Sexualdelikte, nicht für Betrug. Die Messung oben ersetzt
die Aussage.

**In den Dokumenten korrigiert.** `leistungsnachweise.md`: die
Reihenfolge-Empfehlung unter Tabelle 5 ist eingelöst und sagt jetzt das
Ergebnis. `ln1_konzept.md`: H1 in Kapitel 3.3 und die Schwellenstelle in 3.4
stehen auf der gemeinsamen Achse statt auf zwei Hauskategorien. Ausserdem die
Grenze „Keine Familienbezeichnungen" in Notebook 34 — `dim_offense` führt seit
dem Kategorien-Werkzeug 42 amtliche Kategorien, die Familie ist nur noch ein
technisches Präfix.

**Nachlesen.** `notebooks/34_gold_sternschema.ipynb` Abschnitt 5.2 · PR #44

---

## 12.09.2026 · Der Stand in `leistungsnachweise.md` nachgezogen (#43)

**Was.** Acht Zeilen in den beiden Planungstabellen standen als offen, obwohl
sie erledigt sind. Jede ist vor der Änderung gegen die gebauten Daten geprüft
worden, nicht aus dem Gedächtnis abgehakt.

**Warum.** Es sind die Tabellen, aus denen die Abgabe den Projektstand liest.
Vier Zeilen „offen" bei fertiger Arbeit lesen sich wie ein Rückstand, den es
nicht gibt — und die daraus abgeleitete Summe („fünf Arbeitstage zu zweit")
war damit ebenfalls falsch.

**Zahlen — womit jede Zeile belegt ist.**

| Zeile | Beleg |
| --- | --- |
| Silver: Dedup und Typen | 347'957 Zeilen, `offense_id` eindeutig, Zeitstempel und Koordinaten typisiert |
| Silver: räumlicher Join | Chicago **99,3 %**, Detroit **99,7 %** mit `tract_geoid` |
| NIBRS-Harmonisierung | beide Städte **100 %** zugeordnet — mit dem Vorbehalt aus H3: nur 97,0 % tragen ein echtes NIBRS-Delikt |
| Gold: Raten je Tract | `fact_offense` plus vier Dimensionen, Chicago 94,5 / Detroit 132,6 je 1'000 |

Aufwandssumme von „fünf Arbeitstage zu zweit" auf „rund ein Arbeitstag"
korrigiert; im Fahrplan die Pakete 7 bis 10 abgehakt.

**Nebenbei die eigene Nachlässigkeit korrigiert.** Der Neubau von Silver und
Gold vom selben Tag hatte Kapitel 8.5 in `ln1_konzept.md` nicht mitgezogen:
344'607 → **344'617** Delikte, Detroit 85'335 → **85'345**. Die 90Z-Zahlen und
die 97,0 % bleiben unverändert.

**Was bewusst stehen bleibt.** Die „Reihenfolge-Empfehlung" unter Tabelle 5
(„Detroit-Qualität zuerst") ist Argumentation, nicht Sachstand — dafür gibt es
einen Textvorschlag für Artan statt einer stillen Änderung.

**Nachlesen.** `docs/leistungsnachweise.md` Abschnitte 5 und 7 · PR #43

---

## 12.09.2026 · Ein toter Zwilling der Silver-Schicht entfernt (#42)

**Was.** `transform_detroit.py` und `parse_detroit_feature()` sind gelöscht,
samt `OFFENSE_MAPPING`, `analysis_eligible` und `canonical_category`.

**Warum.** Sie waren eine **zweite, Detroit-eigene Silver-Schicht** aus der
Zeit vor der zweiten Stadt — und sie liefen nicht mehr: `extract_detroit.py`
importiert sie seit dem Umstieg auf Parquet nicht. Am Leben hielten sie nur
noch acht Tests, die sie direkt aufriefen.

Gefährlich war daran die Kategorienzuordnung. `OFFENSE_MAPPING` war eine
Hausliste mit **sechs** Einträgen (`LARCENY → THEFT` und so weiter); alles
andere blieb `UNREVIEWED`. Daneben steht seit Juli der belegte Weg: Detroits
MICR-Code über `config/micr_nibrs_mapping.csv` auf NIBRS, **100 % der Zeilen
zugeordnet**, je Zeile mit Quellenangabe. Zwei Zuordnungen für dieselben Daten
sind in einer Abgabe eine Frage, die man nicht gut beantworten kann.

**Was dabei nicht verloren geht.** Die drei Invarianten, die der tote Code
prüfte, sind in Silver besser abgedeckt — dort gegen den Code, der wirklich
läuft:

| Alte Prüfung | Wo sie heute steht |
| --- | --- |
| `UNFOUNDED` bleibt erhalten, zählt aber nicht | `test_unfounded_wird_gekennzeichnet_nicht_entfernt` — Silver **kennzeichnet** statt zu verwerfen |
| mehrere Delikte eines Vorfalls teilen eine Analyseeinheit | die Tests zu `offense_group_id` und `counts` |
| das Ladedatum verschiebt das lokale Tatdatum nicht | die Zeitzonen-Tests zu `occurred_at_local` |

**Zahlen.** −350 Zeilen Code, **633 → 625 Tests**. An den Daten ändert sich
nichts: Silver, Gold und alle Raten bleiben gleich.

**Nebenbei: H1 gilt jetzt für beide Städte.** Kapitel 3.3 belegte H1 bisher
nur mit Chicago-Zahlen. Notebook 13 misst dieselbe Richtung für Detroit —
2,3 % fehlende Koordinaten bei Familiendelikten gegen 0,16 % bei Diebstahl.
Die Hypothese ist damit in **beiden** Städten vorgeprüft; für „bestätigt"
fehlt noch der Chi-Quadrat-Test.

**In den Dokumenten korrigiert.** `DETROIT_PIPELINE_ANLEITUNG.md` Kapitel 8
beschrieb einen Silver-Entwurf, der so nie gebaut wurde — jetzt steht dort eine
Tabelle, die Entwurfsbegriff und Umsetzung gegenüberstellt. Kapitel 10 und 11
sowie `projektabsprache.md` 5 („Beide Ordner sind leer") nachgezogen.

**Nachlesen.** `src/crime/detroit_pipeline/README.md` · PR #42

---

## 12.09.2026 · Detroits Datenqualität gemessen, Stand nachgezogen (#40)

**Was.** Notebook `13_detroit_data_quality.ipynb` prüft Detroits Bronze Schritt
für Schritt — das Gegenstück zu Notebook 03 für Chicago. Es war die letzte
benannte Lücke zwischen den beiden Städten. Silver und Gold sind dabei auf den
neuesten Bronze-Lauf nachgezogen worden.

**Warum.** Zwei Snapshots desselben Jahrgangs lagen nebeneinander, gut 20
Stunden auseinander. Der Vergleich beantwortet eine Frage, die bei Chicago
offenbleibt: **Ein abgeschlossenes Jahr ist keine Konstante.**

**Zahlen.**

* **10 Delikte in gut 20 Stunden umklassiert** — eine schwere Körperverletzung
  wird zur Schussabgabe ohne Todesfolge, eine Schlägerei zur Sachbeschädigung.
  Jede dieser Änderungen trägt einen neuen `updated_at`; die Deduplizierung in
  Silver trifft deshalb nachweislich die richtige Fassung.
* `gold/fact_offense` **344'607 → 344'617**, Detroit **84'648 → 84'658**,
  Rate **132,5 → 132,6** je 1'000. Chicago unverändert.
* **`ESRI_OID` ist kein Schlüssel:** 68'655 von 88'685 ObjectIDs waren im
  zweiten Lauf andere. Der Wert nummeriert das Abfrageergebnis, nicht den
  Datensatz — `snapshot_ids_sha256` zweier Läufe zu vergleichen sagt nichts.
* **54,6 %** des Jahrgangs wurden mehr als ein Jahr nach der Tat noch
  angefasst. Ein Delta nach Tatdatum verpasst diese Korrekturen — der Grund,
  warum Detroit den vollen Jahrgang neu lädt.
* **Die Zeitzone ist jetzt belegt, nicht angenommen:** `incident_hour_of_day`,
  `incident_time`, `incident_day_of_week` und `incident_year` stimmen ohne eine
  einzige Abweichung mit `America/Detroit` überein und weichen als UTC gelesen
  in jeder Zeile ab.
* **66 %** der `charge_description` sind mit Leerzeichen auf Feldbreite
  gepolstert: 152 scheinbare Werte gegen 79 echte.

**Für die Präsentation.** Detroits Geo-Lücke ist mit **0,29 %** kleiner als
Chicagos (0,7 %), zeigt aber dieselbe Schlagseite: Sexual- und Familiendelikte
liegen um das Sechs- bis Neunfache über dem Schnitt, vermutlich weil die
Adresse zurückgehalten wird. Bei Detroit geht es um 16 von 869 Sexualdelikten —
die Richtung stimmt, das Gewicht nicht.

**Nachlesen.** `notebooks/13_detroit_data_quality.ipynb` · PR #40

---

## 12.09.2026 · Detroit: `city=`-Partition und eine Raw-Schicht (#39)

**Was.** Detroits Bronze liegt unter `city=detroit/` statt `detroit/` — dasselbe
Muster wie Chicago. Und Detroit hat jetzt eine Raw-Schicht: jede ArcGIS-Antwort
unverändert als gzip, mit SHA-256 je Antwort.

**Warum.** Detroit war die einzige der fünf Quellen ohne Raw. Kapitel 7 macht
die Trennung von Beweis und Ableitung zum Prinzip — eine Regel mit genau einer
Ausnahme löst in einer Abgabe immer die Frage aus, warum.

**Zahlen.** 46 Antworten je Jahrgang, 84,6 MB geliefert, **10,0 MB** abgelegt
(Bronze: 16,0 MB).

**In den Dokumenten korrigiert.** `projektabsprache.md`: Raw-Schicht Detroit
*nein* → *ja*, Partitionszeile um `Hive (city)` ergänzt, der Absatz „Was noch
abweicht" um die zwei erledigten Punkte gekürzt.

**Nachlesen.** `DETROIT_PIPELINE_ANLEITUNG.md` Abschnitt 3 · PR #39

---

## 12.09.2026 · Tatkorn: Detroits Zeilen sind Anklagen (#38)

**Was.** Detroit liefert je Vorfall mehrere Zeilen — eine je Anklage. Chicago
liefert eine je Delikt. Silver behält jede Anklage und markiert je Tat **eine**
zählende Zeile; Gold nimmt nur diese.

**Warum.** Artans Fund: eine Zeile mit `offense_category` LARCENY und
`offense_description` *CSC 3rd Degree*. Sie gehört zu einem Vorfall mit zwei
Anklagen zu einer Tat. Welches Feld die Tat trägt, sagen die Daten selbst — bei
mehrzeiligen Vorfällen ist `offense_description` in 38,4 % konstant,
`charge_description` nur in 2,3 %.

Gewählt wird die Zeile, deren Anklage die Tat selbst ist (99,98 % der Fälle);
für die übrigen 19 entscheidet die **Hierarchie des MICR-Handbuchs**.

**Zahlen.**

| | vorher | jetzt |
| --- | ---: | ---: |
| Detroit | 88'685 | **85'335** (−3,8 %) |
| Gold gesamt | 347'957 | **344'607** |
| Rate Detroit je 1'000 | 137,7 | **132,5** |
| Sachbeschädigung | | **−10,8 %** |
| Waffendelikte | | **−10,5 %** |
| Assault | | −0,7 % |

**Für die Präsentation:** Der Juni/November-Bericht steht noch auf Anklagekorn
und trägt seit diesem PR einen Vorbehalt. Seine Aussagen ändern die Richtung
nicht, die Absolutzahlen schon.

**Nachlesen.** Konzept 5.2 · Notebook 32 und 34 · PR #38

---

## 12.09.2026 · Die Werkzeuge beweisen jetzt, dass sie ihre Dateien erzeugen (#37)

**Was.** Alle drei Werkzeuge unter `tools/` laufen im Test in ein temporäres
Verzeichnis, und das Ergebnis muss **byteweise** mit der versionierten CSV
übereinstimmen.

**Warum.** Das Konzept sagt an mehreren Stellen, die Crosswalks seien
reproduzierbar abgeleitet und nicht von Hand gepflegt. Geprüft hat das **nur
eines von drei** Werkzeugen. Bei den anderen beiden prüften die Tests die
fertige Datei — also das Ergebnis, nicht seine Herkunft. **Wer eine Zuordnung
von Hand hineingeschrieben hätte, wäre durch alle Tests gekommen.** Die Zusage
war damit eine Behauptung.

**Zahlen.** Zwei Mutationsproben belegen, dass der Test greift: `0560` in
Chicagos CSV von Hand auf `13B` gesetzt → *„Das Werkzeug erzeugt eine andere
Datei"*; eine Notiz in Detroits CSV umgeschrieben → *„Das Werkzeug baut den
Anschluss nicht mehr so auf"*.

Der schwierige Fall war `extend_micr_arrest_charges.py`: Es *erweitert* eine
bestehende Tabelle und füllt nur, was noch nicht zugeordnet ist — inzwischen
sind das null Zeilen, ein Lauf täte also nichts. Der Test baut deshalb eine
Fassung, in der genau die **23 vom Werkzeug erzeugten Zeilen** geleert sind,
lässt es darauf los und vergleicht. Dazu die Gegenprobe, dass ein zweiter Lauf
nichts mehr ändert.

**Der Preis.** Die Suite läuft statt in 6,6 nun in **14,8 Sekunden** — die
Werkzeuge lesen zwei PDFs und rufen Chicagos Katalog ab. Das ist der Preis
dafür, die Herkunft zu prüfen statt nur das Ergebnis.

**Nachlesen.** `tests/config/` · PR #37

---

## 12.09.2026 · Zurückgezogene und umgeschlüsselte NIBRS-Codes (#36)

**Was.** `dim_offense` sagt jetzt bei jedem Code, was er heute bedeutet.

| Code | | Auflösung | heute | Fälle |
| --- | --- | --- | --- | ---: |
| `11B` | Sodomy | umgeschlüsselt | `11A` | 179 |
| `11C` | Sexual Assault With An Object | umgeschlüsselt | `11A` | 26 |
| `90A` | Bad Checks | ersetzt | `26A` | 50 |
| `90I` | Runaway | keine Straftat | — | 969 |
| `90E`, `90H` | | offen | — | 0 |

**Warum.** „Zurückgezogen" sagt, dass ein Code weg ist, nicht wohin. Wer nach
`26A` filtert, übersieht sonst genau die Fälle, die früher `90A` hiessen.
`11B`/`11C` sind *nicht* zurückgezogen — das FBI schlüsselt sie seit 2023 beim
Veröffentlichen auf `11A` um.

**Für die Präsentation:** Ein Code mit ungeklärter Auflösung, der in den Daten
auftaucht, lässt den Gold-Bau scheitern. Das ist die Zusage, nicht die Hoffnung.

**Nachlesen.** Konzept 5.2 · Notebook 34 Abschnitt 5.1 · PR #36

---

## 12.09.2026 · Gold als Sternschema, und die Stadtgrenze (#33)

**Was.** Gold ist gebaut — aber **nicht als Würfel**. Eine Faktentabelle auf
Deliktkorn plus vier Dimensionen, statt der geplanten `fact_tract_month` und
`fact_city_day`.

**Warum.** Die Begründung für die Würfel war Geschwindigkeit, und die fiel bei
der Messung weg: Eine Abfrage „ein Delikt, ein Tag, eine Stadt" braucht direkt
auf Silver **0,6 ms**, eine vorberechnete Monatsspalte spart 0,2 ms. Der Preis
wäre dagegen konkret gewesen — die Würfel fassen 59 Delikte zu 25 Präfixen
zusammen, *„nur Shoplifting am 9. November"* wäre nicht mehr zu beantworten.

**Die Stadtgrenze ist der zweite Grund.** Bis dahin war **keine Rate je
Einwohner belegbar**: `silver/tract` deckt ganze Countys ab, Cook County hat
5,18 Mio Einwohner gegen Chicagos 2,7 Mio. TIGER/Line PLACE liefert die
Grenzen; ein Tract gehört zu der Stadt, die mehr als die Hälfte seiner Fläche
bedeckt.

| Regel | Chicago | Detroit |
| --- | ---: | ---: |
| alle berührten Tracts | 3'080'550 | 884'691 |
| Flächengewichtung | 2'651'921 | 638'570 |
| **Mehrheitsregel** | **2'661'953** | **638'635** |
| Zensus 2020 | 2'746'388 | 639'111 |

**Zahlen.** Erstmals eine Rate je Einwohner. 1,9 % der Delikte liegen in Tracts
knapp jenseits der Grenze — gemessen, nicht geschätzt.

**In den Dokumenten korrigiert.** Kapitel 5.2 beschrieb die Würfel als
Entwurf; die Messung und das Sternschema stehen jetzt dort.

**Nachlesen.** Konzept 5.2 · Notebook 34 · PR #33

---

## 12.09.2026 · Die amtliche NIBRS-Deliktgliederung (#35)

**Was.** Gruppiert wird über die **28 Group-A- und 10 Group-B-Kategorien** des
NIBRS User Manual, gelesen nach
`config/nibrs_offense_categories_2025.csv`.

**Warum.** Das Projekt hatte über die ersten zwei Zeichen des Codes gruppiert
und das „die Gliederung des Standards" genannt. Das stimmt nicht: `11` und `36`
sind **beide** *Sex Offenses*, `58`/`61`/`62` alle *Commerce Violations*, `10`
zerfällt in drei Kategorien und `90` in zehn.

**Zahlen.** 30 Kategorien belegt, **23 in beiden Städten**, die 99,5 % der Fälle
decken.

**Für die Präsentation:** Das Präfix bleibt als technischer Schlüssel, ist aber
keine amtliche Gliederung — in einer Folie sollte „Deliktkategorie" stehen,
nicht „Deliktfamilie".

**Nachlesen.** Konzept 5.2 · Notebook 32 Abschnitt 1.1 und 3.2 · PR #35

---

## 12.09.2026 · Die Auswertungsumgebung: aus vorhanden wird abfragbar (#28)

**Was.** `python -m serving.build_analysis_db` erzeugt
`data/serving/analyse.duckdb` — eine DuckDB-Datei mit **Sichten** über die
Schichten.

**Warum.** Bis dahin waren die Daten aufbereitet, aber nicht *benutzbar*. Wer
eine Frage hatte, musste wissen, dass die Delikte unter
`data/silver/dataset=crime_offense/part-0001.parquet` liegen — und das in jede
Abfrage schreiben. Das ist der Unterschied zwischen **vorhanden** und
**abfragbar**.

**Zahlen — Sichten gegen Kopie, gemessen.**

| Ad-hoc-Abfrage | Sichten | Kopie |
| --- | ---: | ---: |
| Filter und Gruppierung | 1,8 ms | 2,3 ms |
| Join Delikt × Tract | 3,6 ms | 4,3 ms |
| Drei-Wege-Join | 4,4 ms | 5,1 ms |
| **Dateigrösse** | **0,3 MB** | **45,1 MB** |

Sichten sind sogar knapp schneller — DuckDB liest Parquet nativ mit
Projektions- und Prädikat-Pushdown. Den Ausschlag gaben aber drei Dinge, die
sich nicht messen lassen: Eine Kopie **kann veralten**, ohne dass man es ihr
ansieht. Sie ist eine **zweite Wahrheit** neben den Schichten. Und sie kostet
das **150-fache** an Platz.

**Für die Präsentation.** Die Datei hält keine Daten, sondern Namen. Ein
Silver- oder Gold-Neubau ist darin sofort sichtbar, ohne Import. Als Gold
dazukam, war keine Codeänderung nötig — `discover()` nimmt auf, was in den
Schichten liegt.

**Nachlesen.** `src/crime/serving/__init__.py` · `notebooks/33_serving_evaluation.ipynb` · PR #28

---

## 11.09.2026 · Detroits letzte drei Codes (#32)

**Was.** `3072`, `5421` und `5422` sind zugeordnet. Detroits Abdeckung geht von
98,10 % auf **100 %**.

**Warum.** Sie standen mit der Notiz *„nur Detroit kann das auflösen"*. Detroit
löst es in zwei Feldern, die wir nicht gelesen hatten: `arrest_charge` trägt die
fünfstellige File Class, `charge_description` deren Namen. Beide sind über alle
1'647 Zeilen eindeutig.

**Zahlen.** `3072` bringt 1'447 Fälle nach `23C Shoplifting` — Detroits
Shoplifting-Zahl steigt von 1'740 auf 3'187. `5421`/`5422` gehen mit je 100
Fällen nach `90Z`.

**Für die Präsentation:** Der Beleg ist eine **Rechnung, kein Dokument**. Eine
Bestätigung durch Detroit steht aus; das gehört dazugesagt.

**Nachlesen.** Konzept 8.5 · Notebook 11 Abschnitt 7.1 · PR #32

---

## 11.09.2026 · Die Zielliste selbst bekommt eine zweite Quelle (#31)

**Was.** Notebook 32 prüft nicht mehr nur die Crosswalks *gegen* die 81
NIBRS-Codes, sondern die **Codeliste selbst** gegen eine zweite Abschrift.
Ausserdem ein eigenes Quellen-Notebook für Detroit.

**Warum.** Die 81 Codes waren bis dahin eine Abschrift aus einem PDF, der
niemand widerspricht. **Ein Tippfehler dort verschiebt beide Städte
gleichzeitig** — und fiele nirgends auf, weil beide Crosswalks gegen dieselbe
falsche Liste geprüft würden. Illinois' IEPD-Arbeitsmappe ist eine zweite Hand
am selben FBI-Dokument.

**Zahlen.** Alle **81** Bezeichnungen belegt statt zehn Stichproben. Die
ISP-Tabelle stand vorher nur als Warnung im Notebook (*„nicht als Crosswalk
verwendbar"*), die IEPD-Mappe gar nicht; beide sind jetzt belegende Quellen mit
eigenen Tests.

**Nachlesen.** `notebooks/32_nibrs_source.ipynb` §3.4 · `notebooks/11_detroit_source.ipynb` · PR #31

---

## 11.09.2026 · Crosswalk gegen die Landespolizei geprüft (#30)

**Was.** Chicagos Crosswalk ist gegen die ILCS-Tabelle der Illinois State Police
gegengeprüft. Sieben Codes umgebucht, acht begründete Abweichungen bleiben.

**Warum.** Artan fand `0560 ASSAULT / SIMPLE` auf `13B`. Nach Chicagos eigener
Beschreibung war das richtig — und trotzdem falsch: Illinois trennt *Assault*
als Drohung ohne Berührung von *Battery* als Berührung. **15'120 Fälle.** Jede
andere Prüfung vergleicht die Zuordnung mit Chicagos eigener Beschreibung und
konnte das nicht finden.

**Zahlen.** 111 der 432 Codes sind über den Wortlaut vergleichbar; dort stimmt
die ISP 103 mal zu und widerspricht 8 mal.

**Für die Präsentation:** Die Gegenprobe deckt **ein Viertel** der Tabelle ab
und für Detroit nichts. Kein Netz, sondern ein zweites Augenpaar.

**Nachlesen.** Konzept 8.5 · Notebook 32 Abschnitt 4.1 · PR #30

---

## 11.09.2026 · Der Zeitzonen-Befund (#29)

**Was.** Detroits Jahresfenster war in UTC gezogen statt in Ortszeit.
`2024-01-01 00:00 UTC` ist in Detroit erst der **31.12.2023 um 19:00**.

**Zahlen.** Der alte Bestand enthielt 66 Fälle aus 2023, der neue keinen.
Detroit geht von 88'695 auf 88'685.

**Für die Präsentation:** Das ist der lehrreichste Befund des Projekts, weil
derselbe Fehler **zweimal** auftrat und beide Male typrichtig war. Die Quelle
deklariert ihre Datumsfelder ausdrücklich als UTC — gelesen hatte es niemand.

**Nachlesen.** Konzept 8.6 · PR #29

---

## 11.09.2026 · Detroits Bronze wird Parquet — und das Jahr stimmt wieder (#25)

**Was.** Detroits Ingestion schreibt Bronze als Parquet mit Lauf-Verzeichnis,
Manifest und Datenvertrag — dasselbe Muster wie Chicago. Enthalten ist der
**Zeitzonen-Fix**.

**Warum.** Das Jahresfenster war in **UTC** gezogen statt in Detroiter
Ortszeit. Ein „Jahrgang 2024" enthielt damit Fälle vom 31.12.2023 und liess
welche vom Jahresende fehlen — ohne dass man es einer Zahl ansieht.

**Zahlen.** Die alten NDJSON-Bestände enthalten **66** Fälle aus dem falschen
Jahr und vermissen **56** vom Jahresende 2024. Sie werden seither nicht mehr
gelesen: `silver_pipeline` bricht mit einem klaren Fehler ab, statt sie mit
einer Warnung einzulesen, die man überliest.

**Nachlesen.** `docs/DETROIT_TIMEZONE_AENDERUNGEN.md` · PR #25

---

## 11.09.2026 · `crime_offense`: beide Städte auf NIBRS (#24)

**Was.** Die Tabelle, die den Vergleich trägt. Beide Städte in einer
Deliktsprache, auf einer Zeitachse, mit derselben Raumeinheit.

**Warum.** Chicagos `fbi_code` ist SRS, nicht NIBRS — die beiden Namensräume
überschneiden sich nicht. Ohne gemeinsame Klassifikation ist jeder Vergleich
eine Behauptung.

**Für die Präsentation:** Das ist die Kernleistung des Projekts. Alles danach
sind Korrekturen daran.

**Nachlesen.** Konzept 8.2 · Notebook 32 · PR #24

---

## Bewusst ohne Eintrag

Damit eine Lücke in den Nummern als Entscheidung erkennbar ist und nicht als
Versehen. Jeder Pull Request ab #24 ist entweder oben ein Eintrag oder hier.

| PR | Was er war | Warum kein Eintrag |
| --- | --- | --- |
| #26 | Test-Runner nimmt `-vv` und `-s` wieder auf | Werkzeug, ändert keine Aussage |
| #27 | Tests aufgeräumt, ein Runner statt zwei | Aufräumen |
| #34 | erste Fassung der Deliktgliederung | **nicht gemergt** — ersetzt durch #35 |
| #41 | erste Fassung des toten Zwillings | **nicht gemergt** — durch das Löschen des Basis-Branches geschlossen, neu als #42 |
| #50 | ein überholter Kommentar in `build_analysis_db.py` | eine Zeile, ändert keine Aussage |
| #80 | `docs/detroit-schichten.html` entfernt — der Entwurf „Detroit-Schichten angleichen" aus der Zeit vor #39 | veraltet und nirgends verlinkt; was daraus wurde, steht in `DETROIT_PIPELINE_ANLEITUNG.md` und Konzept 7.3. Christian hat es entschieden |
| #68 | `orchestration.drift` las den Fingerabdruck unter einem falschen Schlüssel (`fingerprint` statt `input_fingerprint`) — der erste Lauf zeigte `None` | Fehlerbehebung mit Test, ändert keine Aussage |

