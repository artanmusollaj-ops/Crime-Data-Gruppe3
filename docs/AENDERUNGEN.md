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
| Tests | **1'161** |
| `silver/crime_offense` | 347'957 Zeilen (Detroit: eine Anklage) |
| `gold/fact_offense` | **344'617** Zeilen (eine Tat) |
| Chicago | 251'516 Delikte · 2'661'953 Einwohner · **94,5** je 1'000 |
| Detroit | 84'658 Delikte · 638'635 Einwohner · **132,6** je 1'000 |
| Fallebene (`counts_case`) | Chicago 259'243 · Detroit 80'229 Fälle; Detroit **124,6** je 1'000 |

> Die Rate zählt nur Delikte in Tracts, die einer der beiden Städte zugeordnet
> sind. Absolute Fallzahlen legen das Gegenteil nahe — Chicago hat in fast
> jeder Kategorie mehr Fälle.

---

## Vertragsversionen

Was sich ändert, wenn eine dieser Zahlen steigt: **was** geladen oder gedeutet
wird — Zeitfenster, Feldauswahl, Dedup-Regel, Granularität. Nicht, *wie* der Code es
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
| `silver/tract` | **2** | 14.09.2026 | ein Census Tract je Zeile, TIGER und ACS über einen vollen äusseren Join. Version 2: `median_household_income_usd` und `population_below_poverty` als `INTEGER` statt `BIGINT` — die Einwohnerzahl bleibt `BIGINT`, sie ist der Nenner jeder Rate |
| `silver/place` | 1 | 14.09.2026 | ein Ort je Zeile, Geometrie für die Stadtgrenze |
| `silver/weather_day` | 1 | 14.09.2026 | eine Stadt an einem Tag, eine Station je Stadt |
| `silver/crime_offense` | **2** | 16.09.2026 | eine Anklage je Zeile; `counts` markiert die Tat, `counts_case` den Fall; NIBRS als gemeinsame Achse. Version 2: `local_time_ambiguous` und `local_time_nonexistent` weisen die beiden Zeitzonen-Randfälle je Zeile aus |
| `gold/*` | **4** | 16.09.2026 | Sternschema, eine Zeile je Tat, Mehrheitsregel für die Stadtzuordnung. Version 2: `dim_date` mit `SMALLINT`/`TINYINT` statt `BIGINT`, `fact_offense.hour_of_day` als `TINYINT`. Version 3: `dim_city_day` führt `precipitation_trace` und `snowfall_trace` mit — ein Messwert 0 mit Spurenflag ist nicht trocken. Version 4: `fact_offense` führt `local_time_ambiguous` mit, weil `hour_of_day` dort gerechnet wird |
| `serving/comparison_*` | 1 | 17.09.2026 | vier aus Gold abgeleitete Vergleichstabellen (`comparison_day`, `comparison_week`, `comparison_month`, `partition_quality`): eine Stadt, eine Periode, eine NIBRS-Kategorie; Taten und Fälle summieren sich auf `fact_offense`; Teilperioden als `days_in_window` ausgewiesen; Taten ohne Code als Kategorie `unmapped` |

> **Der Feldkatalog wird erzeugt, nicht gepflegt.** Am 14.9. wurde
> `docs/feldkatalog.md` von Hand bearbeitet (`f1c9b42`): Spaltentypen von
> `BIGINT` auf `SMALLINT`, `TINYINT` und `INTEGER`. Die Datei entsteht aber
> aus `tools/build_feldkatalog.py` und den Manifesten — die Änderung wäre
> beim nächsten Lauf verschwunden, und der Wächter
> `test_ein_zweiter_lauf_liefert_dieselbe_datei` schlug an. Die schmaleren
> Typen sind ein berechtigter **Wunsch**, aber kein Zustand: `year(tag)`
> liefert in DuckDB `BIGINT`. Wer sie will, setzt sie als `CAST` in
> `dim_date_query` und `build_tract`. **Genau das ist am 14.9. geschehen**
> (#86): Die Typen stehen jetzt im Code, der Katalog sagt `SMALLINT` — und es
> stimmt. Dabei fiel auf, dass die Handänderung `median_household_income_usd`
> nur in `gold/dim_tract` umgestellt hatte, nicht in `silver/tract`, obwohl
> Gold den Wert von dort übernimmt. Im Code gesetzt, stimmen beide
> zwangsläufig überein — das ist das Argument für den Code und gegen das
> Dokument.

**Version 1 heisst „der Vertrag, wie er am 14.9.2026 gilt".** Frühere
Änderungen — das Tatebene, das Fallebene, die Mehrheitsregel — stehen als
Einträge weiter unten; rückwirkend Nummern zu vergeben, hätte eine Ordnung
vorgetäuscht, die es damals nicht gab. Detroit ist die Ausnahme: Dort steht
die 2 seit dem 11.9. in den Daten selbst.

---

## 18.09.2026 · Ohne Ablage ein Satz, kein Stapel (#118)

**Was passiert ist.** Christians Lauf brach ab, weil `s3.datenwerft.ch` nicht
mehr antwortete. Die erste Hälfte war richtig: *„Laeufe nicht geholt … Nichts
gebaut“*. Danach druckte derselbe Lauf **sechzig Zeilen botocore-Stapel** —
das Aufnehmen des Bestands für das Manifest griff erneut nach S3, und dort war
nichts abgefangen. Das README sagt an genau dieser Stelle „ein Satz statt
eines boto3-Tracebacks“ zu.

**Der Bau.** `bronze_laeufe` und `aktualitaet` laufen jetzt in einem
`try`/`except StorageError`: Der Lauf gilt als gescheitert, das Protokoll wird
trotzdem geschrieben — mit `inventory_error` und dem, was lokal sichtbar ist.
Dazu ein Schlussfang in `main()`, damit kein Weg übrigbleibt, der einen Stapel
druckt. Die Meldung nennt jetzt auch den Ausweg:

```
Die Ablage antwortet nicht: SeaweedFS: ConnectionClosedError bei LIST raw/…
Ohne SeaweedFS baut nichts. Entweder die Verbindung herstellen
('python -m storage' prueft sie), oder lokal weiterarbeiten:
STORAGE_BACKEND=local in .env.
```

Beides am echten Ausfall geprüft: Exit-Code 1 ohne Stapel, und
`STORAGE_BACKEND=local` fährt dieselbe Strecke in drei Sekunden durch.

**Die Ursache lag nicht im Projekt.** Eingegrenzt in drei Messungen: TCP stand,
TLS mit SNI `www.cloudflare.com` klappte an derselben Adresse, TLS mit SNI
`s3.datenwerft.ch` wurde zurückgesetzt. Ein Gerät auf dem Netzweg liest den
Hostnamen im ClientHello und schneidet gezielt ab. Nebenbei lieferte der
Resolver des Netzes andere Cloudflare-Adressen als 1.1.1.1, 8.8.8.8 und
9.9.9.9 — nicht die Ursache, aber ein Hinweis. Das Rezept steht jetzt in
`storage-architektur.md` 14, damit die nächste Eingrenzung eine Minute dauert
statt einer Stunde.

**Nicht geändert: die 403-Wiederholung.** Im Log steht je neuer Datei einmal
*„ClientError bei HEAD … Versuch 1 von 4, Pause 1 s“*. Das ist SeaweedFS'
Antwort auf ein fehlendes Objekt und seit `ee08274` bewusst als vorübergehend
eingestuft (Abschnitt 14). Es kostet rund eine Sekunde je neuem Objekt — bei
Detroits 46 Raw-Dateien etwa 60 der 168 Sekunden. Korrekt, nur langsam; eine
Abkürzung würde die Zusage unveränderlicher Läufe berühren und gehört
besprochen, nicht nebenbei gebaut.

**Zahlen.** 1'158 → **1'161 Tests**. Frischklon 1'080 von 1'161.

**Nachlesen.** `src/crime/orchestration/run_all.py` ·
`docs/storage-architektur.md` 14 · `tests/orchestration/test_run_all.py` ·
PR #118

---

## 17.09.2026 · Ein abgelöster Vollschnappschuss ist kein Rückschritt (#116)

**Der Abbruch.** Christians Gesamtlauf mit Ingestion scheiterte um 21:30:

> `silver/dataset=weather_day`: hier gebaut 19:30 UTC, auf SeaweedFS 16:05
> UTC; dort stecken 1 Bronze-Lauf/Läufe, die hier fehlen
> (`run_20260908T201217784384Z`)

Die Meldung widerspricht sich selbst: Der hiesige Stand war **neuer** und
ruhte auf einem **neueren** NOAA-Lauf (`run_20260917T193036783822Z`, 55'465
Zeilen gegen 55'449). Der Lauf vom 8.9. war nicht verloren — er lag die ganze
Zeit unter `data/bronze`.

**Die Ursache.** Die Publish-Sperre verglich die Laufkennungen als Mengen: was
der Stand oben nennt und der hiesige nicht, galt als fehlend. Das stimmt für
Chicagos **Deltas**, die sich ergänzen und alle gelesen werden. Für NOAA
stimmt es nicht: Die Quelle liefert **Vollschnappschüsse**, und
`build_weather_day` nimmt über `newest_complete_run` nur den jüngsten. Nach
dem ersten Neuladen wäre `weather_day` damit nie wieder publizierbar gewesen —
dieselbe Sperre hätte auch `tract` und `place` getroffen, sobald TIGER oder
ACS neu geladen werden.

**Der Bau.** Ein Lauf zählt jetzt nur als fehlend, wenn er hier **nicht
erreichbar** ist — lokal oder auf SeaweedFS, gelesen aus den Manifesten
(Detroit nennt seine Kennung `pipeline_run_id`). Die Absicht der Regel bleibt
unberührt: Wer einen Lauf gelöscht oder nie geholt hat und daraus neu baut,
verdrängt einen reicheren Stand — und genau dann ist der Lauf auch nicht
erreichbar. Der Zwischenstand wird nach jedem `hole_lauf` verworfen.

**Nachweis.** Fünf neue Tests, darunter das Gegenstück: derselbe Aufbau ohne
den alten Lauf in Bronze bricht weiterhin ab. Christians Lauf geht seither
durch — acht Stufen, Release `2026-09-17T19-42-24Z` mit 21 Dateien publiziert.

**Was dabei in Bewegung geraten ist.** Der Lauf hat mit frischer Ingestion
gebaut; die Quellen hatten sich seit dem 5.–8. September bewegt.
`orchestration.drift` misst: `silver/crime_offense` +354 Zeilen (+0,10 %),
`gold/fact_offense` +433 Taten (+0,13 %), Detroits Rate 132,6 → **132,7**
(+0,1, „über der Toleranz“). Chicagos Rate, beide Einwohnerzahlen und die
Fallebene stehen unverändert. **Der Referenzstand im Kopf dieses Dokuments ist
bewusst nicht nachgezogen** — das ist eine Verabredung des Teams, keine Zahl,
die ein Lauf verschiebt.

**Auch `docs/feldkatalog.md` bleibt beim Referenzstand.** Er wird aus den
Manifesten erzeugt und stand nach dem Lauf auf 348'311 statt 347'957 — einmal
regeneriert und committet. Das war falsch: Sein Wächter
`test_ein_zweiter_lauf_liefert_dieselbe_datei` trägt `referenzstand`, der
Katalog gehört also zu den Dokumenten, die den **gepinnten** Stand zeigen, und
nicht zu denen, die dem Lauf folgen. Zurückgenommen; er ist jetzt rot wie die
übrigen 35 Wächter, bis der Referenzstand nachgezogen oder die Daten
zurückgeholt sind.

**Christians Entscheidung (17.9.2026): nicht nachziehen.** Der Referenzstand
bleibt der Bau vom 16:05 UTC, die Drift ist gemessen und steht in
[`datenhistorie.md`](datenhistorie.md) 8. **33 der 70 `referenzstand`-Wächter
sind auf einem Rechner mit frischen Daten rot** — das ist ihre Aufgabe. CI und
frischer Klon sind davon nicht berührt, dort gibt es keine Daten. Wann
nachgezogen wird, ist Punkt 6 für den Freitag.

**Und der Grund, warum er zweimal mitgewandert ist.** Nicht Unachtsamkeit:
`test_ein_zweiter_lauf_liefert_dieselbe_datei` **führt das Werkzeug im Projekt
aus**. Das Werkzeug kennt kein Ausgabeverzeichnis und schreibt immer nach
`docs/feldkatalog.md`; scheitert der Vergleich, blieb die neu erzeugte Datei
im Arbeitsbaum liegen und landete im nächsten `git add -A`. Derselbe Bau
steckt in `tests/test_architekturbilder.py` für die beiden SVG. Beide stellen
den vorherigen Inhalt jetzt in einem `finally` wieder her — ein Test darf
messen, verändern darf er nichts.

**Zahlen.** 1'153 → **1'158 Tests**. Frischklon 1'077 von 1'158.

**Nachlesen.** `src/crime/storage/backend.py` (`verfuegbare_laeufe`,
`vergleiche_stand`) · `tests/storage/test_stand.py` · PR #116

---

## 17.09.2026 · Das README auf den heutigen Stand gebracht (#115)

**Was.** Christian hatte den Eindruck, diverse Stellen im README zeigten noch
den alten Verlauf. Das Dokument ist Zeile für Zeile gegen die Wirklichkeit
gehalten worden. Elf Stellen waren veraltet, keine davon falsch gerechnet —
alle waren **stehengeblieben**, während der Umbau sie überholt hat.

| Stelle | war | ist |
| --- | --- | --- |
| Schichtenbild | endete bei `serving` | `… ─▶ serving ─▶ releases` |
| Schichtentabelle | `serving` = nur DuckDB-Sichten | dazu vier Vergleichstabellen; eigene Zeile für `releases` |
| Dokumentenliste | ohne `storage-architektur`, `ausblick`, `projektabsprache`, `leistungsnachweise` | alle vier verlinkt |
| Paketbaum 1.1 | sieben Pakete | zehn — `manifeste`, `storage`, `orchestration` fehlten |
| 2.0 Gesamtlauf | ohne Holen und Release | beide Schritte erklärt, drei Schalter genannt |
| 2.2 NIBRS | „Beide Städte zu 100 % zugeordnet“ | Detroit vollständig, Chicago bis auf drei Zeilen (`unmapped`) |
| 2.3 Befehle | ohne `serving.build_comparison` | mit, und an der richtigen Stelle vor der Datenbank |
| 2.3 `SHOW TABLES` | „fünf Gold-, vier Silver- und zwei Metasichten“ | 15 Sichten, die vier Serving-Sichten dazu |
| 3 Wenn etwas klemmt | ohne Ablage und Release | zwei Zeilen, mit Verweis auf `storage-architektur.md` 14 |
| 4 Tests | „Die 40 Tests, die ein PR überspringt“ | 81 — und 70 tragen `referenzstand` |
| 4 Datenlauf | „sechs Notebooks … 03, 13, 31, 32, 33, 34“ | acht, mit 35 und 36 |

**Nachgeprüft und richtig geblieben:** alle Zahlen im Kopf (347'957, 344'617,
94,5 und 132,6), die vier Silver-Zeilenzahlen, die Verortungsquoten (Chicago
99,3 %, Detroit 99,7 %), Detroits 3,9 %, die 1'055 Tract-Umrisse mit 0,55 MB.
Sie stehen unter Wächtern und haben sich deshalb nicht bewegt — die elf
veralteten Stellen waren genau die, die **keiner** hatten.

**Zahlen.** Unverändert 1'153 Tests.

**Nachlesen.** `README.md` · PR #115

---

## 17.09.2026 · Ein Release ist der ganze Stand oder keiner (#114)

**Wie es auffiel.** Christian hat gefragt, ob der lokale `serving/`-Ordner noch
gebraucht wird. Statt zu antworten, wurde er beiseitegeschoben und ein Release
gebildet. Es entstand — mit **11 statt 21 Dateien**, ohne die vier
Vergleichstabellen, ohne die Karte, und mit `status: complete`. Ein Teilstand,
dem man es nicht ansieht, ist schlimmer als gar keiner.

**Die Ursache.** `storage.release.PFLICHT` verlangte genau eine Tabelle:
`gold/dataset=fact_offense`. Alles andere wurde eingesammelt, wenn es dalag,
und sonst eben nicht. `storage` kann das auch nicht besser wissen — es kennt
Dateien, nicht die Schichten darüber; ein Import aus `serving` wäre der
Zyklus, den der Wächter über den Importgraphen schon einmal gemeldet hat
(#109).

**Der Bau.** Die Pflichtliste wird jetzt **hereingereicht**, wie der Haken für
die Datenbank: `orchestration.release.VOLLSTAENDIG` leitet sie aus den
Schichten selbst ab — `gold_pipeline.TABELLEN` (neu, und `build_gold` prüft
seinen Bauplan dagegen), `serving.build_comparison.TABELLEN` und
`export_geojson.GEOJSON_NAME`. Zehn Einträge, keiner abgeschrieben; kommt eine
Tabelle dazu, steht sie von allein darin. Ohne `serving/` bricht das Bilden
jetzt ab, nennt jede fehlende Tabelle und legt nichts an — Exit-Code 1.

**Die Antwort auf die Frage:** Ja, `data/serving/` wird gebraucht. Er ist
nicht nur Arbeitsstand, sondern die **Quelle**, aus der das Release
zusammengesetzt wird (`sammle` liest `gold/dataset=*` und `serving/`). Löschen
darf man ihn jederzeit — er ist abgeleitet, und `run_all --ohne-ingestion`
baut ihn in Sekunden neu; nur ein Release lässt sich in der Zwischenzeit nicht
bilden. 920 KB.

**Nebenbei aufgeräumt.** Zwei Release-Verzeichnisse aus meinen eigenen
Proben (`16-31-45Z`, `18-36-15Z`) sind entfernt; der lokale Zeiger steht
wieder auf dem Release, das Christian um 18:31 UTC selbst gebildet und
publiziert hat — 21 Dateien, vollständig, lokal und auf SeaweedFS derselbe
Stand.

**Zahlen.** 1'149 → **1'153 Tests**. Frischklon 1'072 von 1'153.

**Nachlesen.** `src/crime/orchestration/release.py` (`VOLLSTAENDIG`) ·
`src/crime/gold_pipeline/__init__.py` (`TABELLEN`) ·
`tests/storage/test_release.py` · PR #114

---

## 17.09.2026 · Die drei Modi geprüft — und die fünfte Entscheidung für Freitag (#111)

**Was.** Etappen 5 und 6 des Umbaus nach dem externen Rat.

**Die Modi, als Matrix.** Beim Durchsehen fiel ein Widerspruch auf, den
keiner der drei Einzeltests sehen konnte, weil jeder nur seinen Modus sah:
`s3` ist definiert als *ohne lokalen Bestand* — und das automatische Holen
von Raw und Bronze (#110) hätte ihn genau damit gefüllt. Seither holt der
Gesamtlauf **nur im Hybridmodus** von selbst; in `s3` liest Silver Bronze
direkt von SeaweedFS, und von Hand geht `python -m storage holen --wirklich`
weiterhin. `tests/storage/test_modi.py` hält die Matrix fest, und
`storage-architektur.md` 6a sagt dasselbe — ein Test prüft, dass beide
übereinstimmen:

| Modus | holt Raw/Bronze | Release | publiziert | lokale Kopie bleibt |
| --- | --- | --- | --- | --- |
| `local` | nein | nur mit `--release` | nein | ja |
| `hybrid` | **ja** | nach jedem grünen Lauf | ja | ja |
| `s3` | von Hand | nach jedem grünen Lauf | ja | nein |

**Die fünfte Entscheidung.** `datenhistorie.md` 5.5: Was von den Releases
bleibt? Seit #109 entsteht neben der Quellhistorie eine zweite — *was wir
wann gesagt haben* —, und sie wird nur angehäuft; `aufraeumen` fasst Releases
nicht an. Gemessen: 42,3 MB je Release, rund 2,2 GB im Jahr bei wöchentlichem
Lauf. Drei Möglichkeiten stehen mit Kosten und Verlust nebeneinander;
**empfohlen** ist *gepinnt + die letzten n* mit demselben Register wie für
Läufe (`config/referenzstand.csv`) und n = 8. Nicht vor Freitag; bis dahin
wird nichts gelöscht. Der Ausblick sagt es jetzt an derselben Stelle, und ein
Wächter hält die Zahl an beiden Orten gleich.

**Damit ist der Umbau nach dem Rat vollständig** — sechs Etappen in vier
Pull Requests (#108 bis #111): Aggregate in Serving, Release je Kennung mit
Zeiger, Holen von Releases und Läufen, die Modi geprüft, die Löschfrage
vorbereitet.

**Zahlen.** 1'142 → **1'149 Tests**. Frischklon 1'068 von 1'149.

**Nachlesen.** `tests/storage/test_modi.py` · `docs/datenhistorie.md` 5.5 ·
`docs/storage-architektur.md` 6a · PR #111

---

## 17.09.2026 · Holen: Releases herunterladen, Raw und Bronze auf jeden Rechner (#110)

**Was.** Etappen 3 und 4 des Umbaus nach dem externen Rat, in einem Zug,
weil sie sich eine Grundlage teilen: `Storage.hole` bringt ein Objekt geprüft
und unteilbar in die lokale Wurzel — in eine `.part`-Datei, Grösse und MD5
gegen das ETag, dann `rename`; was identisch da ist, wird nicht erneut
geladen. Darauf ruhen zwei Dinge:

**Releases holen.** `python -m orchestration.release holen [KENNUNG|aktuell]`
holt `release.json` zuerst und dann jede Datei darin, jede gegen ihre SHA-256
aus dem Manifest — nicht nur gegen das ETag. Eine Datei, die nicht zum
Manifest passt, wird verworfen und der Abbruch gemeldet. `--nur-datenbank`
holt allein `serving/analyse.duckdb` — die Schritte 3 bis 5 des Rats für ein
Dashboard, das nichts anderes braucht — und legt den Zeiger bewusst nicht um:
Nur die Datenbank ist kein ganzer Stand. `--einsetzen` setzt die Tabellen
danach Tabelle für Tabelle unteilbar an die festen Pfade `gold/dataset=…` und
`serving/dataset=…`; wer dort liest, liest dann den freigegebenen Stand.

**Raw und Bronze auf jeden Rechner.** Bis heute galt „kein automatisches
Herunterladen". Für Silver und Gold bleibt das richtig — ein stiller Cache
wäre eine zweite Wahrheit mit eigenem Alter. Für Läufe gilt es nicht: Sie sind
unveränderlich, eine Kopie kann nicht veralten, und Christian will den ganzen
Bestand auf jedem Rechner. Jeder Gesamtlauf in einem Modus mit S3 holt
deshalb **zuerst** alle Raw- und Bronze-Läufe, die oben liegen und lokal
fehlen — Raw vor Bronze, je Lauf `manifest.json` zuletzt, so dass ein
abgebrochener Download nirgends als Lauf gilt. Scheitert das Holen, läuft
nichts weiter: Silver auf einem halben Bronze wäre der Stand, den niemand
erklären kann. `--ohne-holen` schaltet es ab; von Hand `python -m storage
holen [--wirklich]`.

**Gemessen.** Am 17.9. liegen 14 Raw- und 15 Bronze-Läufe oben und
dieselben lokal — `python -m storage holen` meldet *nichts zu tun*. Ein
`release holen` ohne publiziertes Release nennt den fehlenden Pfad, statt
etwas zu erfinden.

**Was sich damit umkehrt.** `storage-architektur.md` 13 und README 2.5 sagten
„kein automatisches Herunterladen". Sie sagen es jetzt nur noch für Silver
und Gold; Abschnitt 5a beschreibt das Holen. Der Modul-Docstring von
`storage.backend` ebenso.

**Zahlen.** 1'119 → **1'142 Tests** (zwölf für das Holen, sieben für das
Release-Holen und -Einsetzen, vier für den Lauf). Frischklon 1'061 von 1'142.

**Nachlesen.** `src/crime/storage/backend.py` (`hole`, `hole_lauf`,
`fehlende_laeufe`) · `src/crime/storage/release.py` (`hole`, `einsetzen`) ·
`tests/storage/test_holen.py` · PR #110

---

## 17.09.2026 · Der Veröffentlichungsstand ist gebaut: ein Release je Kennung (#109)

**Was.** Etappe 2 des Umbaus nach dem externen Rat. `storage.release` bildet
nach jedem grünen Gesamtlauf ein Verzeichnis je Kennung —
`data/releases/release=2026-09-17T16-31-45Z/` — mit den fünf Gold-Tabellen,
den vier Serving-Tabellen, dem GeoJSON, einer **selbständigen**
`analyse.duckdb` und `release.json`. Publiziert wird es unveränderlich wie ein
Lauf, `release.json` zuletzt; erst danach wird `releases/AKTUELL.json`
umgelegt — ein Objekt, dessen Ersetzung lokal wie auf S3 unteilbar ist. Alle
Tabellen wechseln gemeinsam; ein Abbruch an jeder Stelle lässt den alten Stand
gültig. Die festen Pfade `gold/dataset=…` werden weiterhin bedient.

**Gemessen am Referenzstand.** 21 Dateien, **42,3 MB** — 14 MB Parquet plus
eine **26,5 MB** grosse Datenbank mit zehn Tabellen. `release.json` trägt
SHA-256 je Datei, die Vertragsversionen (`gold` 4, `serving/comparison_*` 1),
den Code-Stand, das Publish-Gate und die Herkunft bis zu den fünf Bronze-Läufen
und den drei Crosswalk-Prüfsummen. Ein Jahr wöchentlicher Releases: rund 2 GB.

**Die Datenbank im Release hält Tabellen, nicht Sichten.** Die
Arbeitsdatenbank `data/serving/analyse.duckdb` bleibt Sichten — ihre Pfade
sind absolut, auf einem anderen Rechner wäre sie wertlos. Ein Release ist
unveränderlich; eine Kopie darin kann nicht veralten. `release_info` nennt
Kennung und Zeitpunkt, damit ein Dashboard sagen kann, welchen Stand es zeigt.

**Je Modus.** `local`: nur mit `run_all --release`, bleibt lokal. `hybrid`:
nach jedem grünen Gesamtlauf von selbst, lokale Kopie bleibt. `s3`: wie
`hybrid`, lokale Kopie danach entfernt. Ein Release entsteht nur nach einem
vollständigen grünen Lauf bis einschliesslich Serving; ein halber Stand
bekommt keine Kennung. **Scheitert das Publizieren, ist der Lauf gescheitert.**

**Ein Importzyklus, vom Wächter gefunden.** Der erste Entwurf liess
`storage.release` die Datenbank selbst bauen — ein Import aus `serving` in
einem Fundament. `test_die_fundamente_haengen_an_nichts` hat es beim ersten
vollen Lauf gemeldet. Seither reicht der Aufrufer den Haken:
`orchestration.release` kennt `serving`, `storage.release` kennt nur Dateien.
Die Befehle heissen deshalb `python -m orchestration.release erstellen | liste
| aktuell`, nicht `python -m storage release`.

**Und ein Beinahe-Commit.** `data/releases/` war nicht in `.gitignore` — 42 MB
wären untracked in den ersten Commit gewandert. Jetzt ignoriert wie `serving/`.

**Nachgezogen.** Ausblick 6 führt den Bau als *gebaut* statt *offen*, der
Wächter prüft das Gegenteil von vorher; `storage-architektur.md` 6a, 9, 12;
README 2.5; Datenflussbild („serving: lokal gebaut; als Release publiziert").
Bewusst noch nicht umgestellt: die Leser der festen Pfade — der feste Pfad ist
die Arbeitskopie, das Release der freigegebene Stand.

**Offen, für Freitag.** Releases werden aufgehoben; welche und wie lange,
entscheidet `datenhistorie.md` (Etappe 6).

**Zahlen.** 1'095 → **1'119 Tests** (17 für das Release, 7 für den Lauf).
Frischklon 1'038 von 1'119.

**Nachlesen.** `src/crime/storage/release.py` ·
`src/crime/orchestration/release.py` · `tests/storage/test_release.py` ·
PR #109

---

## 17.09.2026 · Vier Vergleichstabellen in Serving — der Würfel, den es doch gibt (#108)

**Was.** Eine neue Stufe `serving/comparison` (`serving.build_comparison`)
leitet aus Gold vier Tabellen ab: `comparison_day`, `comparison_week`,
`comparison_month` — je Stadt, Periode und NIBRS-Kategorie, Taten und
Fälle — und `partition_quality` je Stadt und Monat mit den Anteilen von
`mapping_status` und `geo_status`. Sie liegen unter `data/serving/dataset=…`,
bekommen Sichten in `analyse.duckdb` (jetzt 13 statt 9) und stehen im
Feldkatalog (174 Spalten in 13 Tabellen).

**Warum, obwohl Notebook 34 gemessen hat, dass sie nichts sparen.** Die
Ablehnung der Aggregate ruhte allein auf dem Geschwindigkeitsargument.
Christian hat entschieden, dass für ein Studienprojekt ein zweites zählt: Beide
Bauweisen sollen **gebaut** nebeneinander stehen, und der externe Rat vom
17.9. hatte die Tabellen als Teil des Veröffentlichungsstands vorgeschlagen.
Die Messung bleibt richtig, die Folgerung daraus war zu eng.

**Wo sie liegen — und wo nicht.** In **Serving**, nicht in Gold. Gold bleibt der
Stern und die Quelle der Wahrheit; Serving ist das, was ein Dashboard liest
und was ein Release enthält. Die Tabellen sind jederzeit aus Gold neu
erzeugbar und erreichen SeaweedFS nie an einem festen Pfad, nur als Teil
eines Release (Etappe 2). Konzept 5.2 sagt seither *„Keine vorberechneten
Aggregate in Gold"* — eine Sachkorrektur in Artans Dokument, die Struktur
bleibt.

**Die Gegenprobe ist hart.** Jede der drei Vergleichstabellen muss sich je
Stadt auf `fact_offense` aufsummieren, Taten wie Fälle — sonst bricht der Bau
ab. Das geht, weil jede Tat genau eine Kategorie trägt und `counts_case` genau
eine Zeile je Fall markiert (`zaehlperspektiven.md`). Gemessen: 344'617 Taten,
339'472 Fälle, in allen drei Tabellen. Die drei Chicagoer Taten ohne Code
tragen die Kategorie `unmapped`, damit sie zählbar bleiben; ein **vorhandener**
Code ohne Kategorie bricht ab.

**Teilperioden sind ausgewiesen.** `days_in_window` gegen `days_in_period`:
Die Woche ab 30.12. hat sieben Tage, zwei davon im Fenster, 1'647 Taten. Wer
das nicht liest, sieht am Jahresende einen Einbruch, der keiner ist.

**Nachgezogen.** 14 statt 13 Stufen (`run_all`, Architekturbilder, Konzept 5.3,
`architektur.md`); Absprache 7.3 mit einer Zeile für `comparison`;
Ausblick 6 sagt jetzt, was ein Release enthält, statt was nicht;
`sternschema-und-wuerfel.md` samt HTML-Zwilling mit einem vierten Punkt;
Notebook 34 unterscheidet die nachgebauten Würfel vom Bestand;
Leistungsnachweis-Dokument: dreizehn Sichten statt neun. Vertragsversion
`serving/comparison_*` = 1 im Register.

**Zahlen.** 1'082 → **1'095 Tests** (zehn für die Stufe, drei angepasste
Wächter). Frischklon 1'014 von 1'095.

**Nachlesen.** `src/crime/serving/build_comparison.py` ·
`tests/serving/test_build_comparison.py` · PR #108

---

## 17.09.2026 · Der Würfel wird gebaut statt behauptet — und Notebook 34 war kaputt (#107)

**Der Anlass.** Christian hat eingewandt, die Ablehnung der Aggregate ruhe auf
einem Geschwindigkeitsargument — für ein Studienprojekt könne ein Würfel aber
**Nachweiswert** haben. Das ist ein eigenes Kriterium, und es fehlte in der
Abwägung.

**Die Antwort: bauen, aber im Notebook.** Notebook 34 *zählte* bisher nur, wie
viele Zeilen `fact_tract_month` und `fact_city_day` hätten. Jetzt werden beide
Würfel wirklich gebaut, gegen den Stern gestellt und mit denselben drei Fragen
geprüft:

| Frage | Stern | tract_month | city_day |
| --- | ---: | --- | --- |
| nur Ladendiebstahl 23C, Jahr | 16'773 | nur Familie 23 | nur Familie 23 (77'752) |
| der 9. November, beide Städte | 960 | nur Monate | 960 |
| ein Tract, ganzes Jahr | 3'878 | 3'878 | nur Städte |

Dazu die Gegenprobe (die Würfelzellen summieren sich auf 344'617 Taten — ein
Würfel ist nicht falsch, er ist **ärmer**) und der faire Gegentest: Dieselbe
Frage kostet auf dem Stern 0,73 ms und auf dem Würfel 0,23 ms. Der Würfel
gewinnt, und der Gewinn ist unsichtbar.

**Gebaut werden sie im Notebook und nirgends sonst** — nicht in `data/gold/`,
nicht im Veröffentlichungsstand. Eine Tabelle in der Pipeline ist ein
Bauauftrag, ein Test und eine zweite Stelle, an der Zahlen auseinanderlaufen;
eine im Notebook ist ein Beleg, der bei jedem Lauf neu entsteht. Die Zusage
aus Konzept 5.2 bleibt.

### Dabei gefunden: Notebook 34 lief seit dem 14.9. nicht mehr

**Was.** Am 14.9.2026 um 12:34 UTC wurde die doppelte Zuordnung GEOID →
Stadtname entflochten (`9d287a1`): `silver_pipeline.STUDIENSTAEDTE` trägt
`'Chicago'`, der abgeleitete `gold_pipeline.STADT_SCHLUESSEL` trägt
`'chicago'`. Das Notebook importierte weiter `STUDIENSTAEDTE` und griff mit
`werte['chicago']` zu — **`KeyError`**. Damit war alles ab der
Einwohnerrechnung tot: Stadtzuordnung, Mehrheitsregel, die Raten 94,5 und
132,6, der Vergleich der Kategorien.

**Warum es niemand sah.** Der Datenlauf jenes Tages lief um **06:05 UTC**,
sechs Stunden vor dem Commit. Der nächste ist montags. Drei Tage lang war ein
Beleg der Abgabe kaputt, ohne dass etwas rot wurde — derselbe Fall wie
Notebook 32 nach der `city=`-Umbenennung, und aus demselben Grund: Der einzige
Ort, an dem diese Notebooks ausgeführt werden, läuft wöchentlich.

**Eine zweite Stelle wäre schlimmer gewesen.** Die Zelle mit der Rate filtert
`WHERE t.city = ?`. Mit dem grossgeschriebenen Wert hätte sie **nicht
gescheitert, sondern null Zeilen gezählt** — ein stiller falscher Wert statt
eines Abbruchs. Sie kam nur nicht dazu, weil der `KeyError` vorher fiel.

**Behoben.** Beide Zellen benutzen jetzt `STADT_SCHLUESSEL`, und die Namen
werden aus der Konstante abgeleitet statt eingetippt. Der Kommentar an
`STADT_SCHLUESSEL` hatte den Fall wörtlich vorhergesagt: *„Wer die falsche
importierte, bekam stillschweigend etwas anderes."* Genau das ist passiert.

**Gegengeprüft.** Das Notebook läuft wieder vollständig durch und liefert die
bekannten Zahlen: Mehrheitsregel 2'661'953 und 638'635 Einwohner, Raten 94,5
und 132,6, Grenzvariante 95,6.

**Nebenbei angeglichen:** Die ältere Zelle zählte die Würfelzeilen ohne
`WHERE counts` und nannte deshalb 95'609 statt 95'219 — zwei Zahlen für
dieselbe Tabelle in benachbarten Zellen. Jetzt rechnen beide auf der Tatebene.

**Acht neue Wächter** in `tests/test_notebook_sternschema.py`, alle ohne
gebaute Daten und damit auf jedem Pull Request: dass jeder importierte Name
existiert, dass die beiden Zuordnungen sich wirklich in der Schreibweise
unterscheiden (sonst wäre die Falle weg und die Prüfung überflüssig), dass das
Notebook `STADT_SCHLUESSEL` benutzt und `STUDIENSTAEDTE` nur im Kommentar,
dass beide Würfel gebaut werden, dass sie **nicht** in `data/gold` landen,
dass die Gegenprobe drinsteht, keine Ausgaben gespeichert sind und die
Abschnitte fortlaufend nummeriert bleiben.

**Zahlen.** 1'074 → **1'082 Tests**.

**Nachlesen.** `notebooks/34_gold_sternschema.ipynb` ·
`tests/test_notebook_sternschema.py` · PR #107

---

## 17.09.2026 · Der Veröffentlichungsstand bekommt eine Release-Kennung (#106)

**Was.** Ein externer Rat hat den Bau aus `ausblick.md` Abschnitt 6 bestätigt
und in zwei Punkten verbessert. Der Abschnitt ist nachgezogen. **Gebaut wird
nichts** — das bleibt LN2, Priorität 8.

**Was der Rat bestätigt hat.** Versionierte Parquet-Dateien plus ein Verweis
auf den freigegebenen Stand, atomar umgelegt; Parquet als Bestand, DuckDB als
bequemes Serving-Paket; und dass der Nutzen erst entsteht, wenn ein Dashboard
danebensteht. Das stand seit dem 15.9. so im Abschnitt, bis hin zum Namen des
Verweises (`AKTUELL.json` gegen `current_release.json`).

**Was übernommen wird.**

1. **Eine Kennung je Release statt je Tabelle.** Der erste Entwurf liess jede
   Tabelle ihre eigene Version tragen. Das ist beweglicher — und genau die
   Beweglichkeit ist die Möglichkeit, aus der ein gemischter Stand entsteht,
   also das Problem, das der Abschnitt löst. Gold wird ohnehin immer als
   Ganzes gebaut.
2. **`analyse.duckdb` gehört ins Release.** Sie entsteht heute in Stufe 7 und
   bleibt lokal; jeder von uns baut seine eigene. Mit Prüfsumme im Release
   wäre sie ein Download und für beide derselbe Stand. Der Bestand bleibt
   Parquet — die DuckDB-Datei hängt an einer Version und an Extensions.

**Was nicht übernommen wird.** Der vorgeschlagene Verzeichnisbaum enthielt
`comparison_day/week/month.parquet` und `quality/partition_quality.parquet`.
Die drei `comparison_*` sind **vorberechnete Aggregate** — der Würfel, den
Notebook 34 gemessen und Abschnitt 5 verworfen hat, diesmal in dreifacher
Ausführung. Konzept 5.2 sagt *„Keine vorberechneten Aggregate"* zu.
`partition_quality` wäre eine zweite Ablage für Zahlen, die in jedem Manifest
unter `checks` stehen. Der Rat kannte unsere fünf Gold-Tabellen nicht; das ist
kein Widerspruch in der Sache, aber ein Grund, einen Verzeichnisbaum nicht
ohne die Tabellen dahinter zu lesen.

**Was ein Release kostet, gemessen.** 14 MB `fact_offense`, 296 KB
`dim_tract`, drei Dimensionen je 12–16 KB, 808 KB Serving — **rund 15 MB**.
Ein Jahr wöchentlicher Releases wären etwa 780 MB. Das Aufheben ist damit kein
Kostenproblem, sondern eine Aufräumregel.

**Keine fünfte Entscheidung für Freitag.** `datenhistorie.md` stellt vier
Fragen, die offen sind und Artan brauchen. Der Veröffentlichungsstand ist
entschieden, nur noch nicht gebaut. Beide Dokumente verweisen jetzt
gegenseitig darauf, dass eine Release-Historie die **veröffentlichten Stände**
festhält und nicht die **Quelländerungen** — sonst landet am Freitag eine
Entscheidung auf dem Tisch, die gar nicht ansteht.

**Zahlen.** 1'071 → **1'074 Tests**. Die drei neuen halten fest, dass die
Lücke noch besteht (`release=` kommt im Storage-Backend nicht vor), dass die
drei Aggregate namentlich abgelehnt bleiben und in Gold nicht auftauchen, und
dass beide Dokumente aufeinander verweisen.

**Nachlesen.** `docs/ausblick.md` 6 · `docs/datenhistorie.md` 8 ·
`tests/test_ausblick.py` · PR #106

---

## 17.09.2026 · Die Beschreibung ist nicht das Delikt (#105)

**Was.** Der schwächste Punkt in `docs/zaehlperspektiven.md` 3 lautete:
*„Gleiche Beschreibung heisst nicht gleiches Delikt. Textvarianten sind
Kandidaten für ein Review, keine Regel zum Zusammenlegen."* Die Überschrift
behauptete das eine, der Satz darunter das Gegenteil, und belegt war keines von
beidem. Nachgemessen ist der Befund viel stärker.

**Chicago: 23,3 % der Zeilen tragen eine mehrdeutige Beschreibung.** 60'478
Stück. Der Grund ist strukturell: Die IUCR-Bezeichnung besteht aus zwei
Hälften, und Silver führt nur die zweite (`description`, nicht `primary_type`).

| in Silver | IUCR | die volle Bezeichnung | NIBRS |
| --- | --- | --- | ---: |
| `SIMPLE` | 0460 | BATTERY · SIMPLE | 13B |
| | 0560 | ASSAULT · SIMPLE | 13C |
| `AGGRAVATED - HANDGUN` | 0261 | CRIMINAL SEXUAL ASSAULT · … | 11A |
| | 041A | BATTERY · … | 13A |

`SIMPLE` allein steht **31'565-mal** und meint einmal Körperverletzung, einmal
Bedrohung. In Detroit sind 54 Beschreibungen betroffen; `ASSAULT AND
BATTERY/SIMPLE ASSAULT` deckt **26 verschiedene NIBRS-Codes** über 16'837
Zeilen ab, weil die MICR-Beschreibung eine Ebene über dem Code steht.

**Die Umkehrung gilt auch:** 34 der 53 Chicagoer und 43 der 50 Detroiter
NIBRS-Codes tragen mehr als eine Beschreibung. Damit ist die ursprüngliche
Aussage über Textvarianten nicht falsch — sie war nur die kleinere Hälfte.

**Die Regel daraus:** nie nach `source_offense_description` gruppieren, immer
nach `nibrs_code` oder `source_offense_code`. Der Text ist zum Lesen da, nicht
zum Zählen.

**Gleich mitkorrigiert: „die 16 Zuordnungen".** Der Abschnitt über den
Crosswalk sprach von 16 Zuordnungen, die wir als `ambiguous` entschieden haben.
Gemessen sind es **20 in den Crosswalks**, von denen **16** Zeilen im Jahrgang
2024 haben (5'140 Zeilen). Vier Entscheidungen sind getroffen, aber nicht
belegt — sie betreffen Codes, die 2024 nicht vorkommen.

**Was geprüft und nicht geändert wurde.** Die übrigen Behauptungen des
Abschnitts halten: Das Publish-Gate prüft tatsächlich nur Abdeckung
(`GATE_MINDESTENS` = inside_city 90 %, exact 85 %; `GATE_HOECHSTENS` =
unmapped 1 %), Silver führt keinen Freigabestatus, und eine Tat ohne Datum
bliebe wirklich schon am Jahresfilter hängen — beide Ingestionen filtern mit
einem Bereichsvergleich auf dem Datumsfeld, den NULL nicht besteht.

**Vier neue Wächter**, alle mit `referenzstand`: die Prozentzahl und die
Zeilenzahl der mehrdeutigen Chicagoer Beschreibungen, der grösste Detroiter
Fall, die Umkehrung je Stadt, und die 20 gegen die 16.

**Zahlen.** 1'067 → **1'071 Tests**.

**Nachlesen.** `docs/zaehlperspektiven.md` · `tests/test_zaehlperspektiven.py`
· PR #105

---

## 17.09.2026 · „31 davon brechen ab" waren 28 (#103)

**Was.** `docs/zaehlperspektiven.md` eröffnete den Abschnitt *Was die Prüfungen
nicht beweisen* mit „42 Kontrollen stehen auf der Strecke, 31 davon brechen
ab". Die 42 und die 31 stimmen — die Behauptung über die 31 nicht.

**Drei der 31 brechen nichts ab.** Das Notebook definiert *hart* als „bricht
ab, nichts wird geschrieben". Danach gemessen:

| | was sie ist | was sie tut |
| --- | --- | --- |
| `GATE_MINDESTENS` | Schwellenwerte | `pruefe_gate` prüft dagegen und bricht ab |
| `ERWARTETE_QUELLEN` | Liste der Bestände | `veraltete_quellen` prüft dagegen |
| `gepinnte_laeufe` | Register des Referenzstands | **schützt** — der Lauf wird beim Aufräumen übergangen |

Sie sind zu Recht als hart geführt: „hart" ist die Einstufung der Sache, nicht
ihrer Wirkung. Falsch war nur, die Einstufung mit dem Abbruch gleichzusetzen.
**28 der 42 Kontrollen brechen tatsächlich ab.**

**Die Ironie gehört zum Befund.** Der Satz stand als erster in einem Abschnitt,
der davor warnt, eine Zahl für einen Beweis zu halten — und war selbst genau
das. Gefragt hat wieder Christian, nicht ein Test.

**Geprüft wurde vorher.** Dass 31 Einträge „hart" tragen, ist beim Schreiben
des Dokuments aus der Landkarte ausgelesen worden; dass jeder davon abbricht,
wurde angenommen. Der Unterschied zwischen *ausgelesen* und *angenommen* ist
der ganze Fehler.

**Damit das nicht wieder passiert.** Vier Wächter in
`tests/test_notebook_kontrollen.py` — sie laufen ohne gebaute Daten auf jedem
Pull Request mit: die drei Zahlen des Dokuments gegen die Landkarte, die drei
Ausnahmen namentlich, und die Gegenprobe, dass die beiden Schwellen wirklich
Konstanten sind und `gepinnte_laeufe` wirklich nicht wirft. Wird eine davon zur
abbrechenden Prüfung, fällt der Test — und die 28 stimmen wieder nicht.

Notebook 35 sagt es jetzt selbst, direkt unter der hart/weich-Tabelle.

**Zahlen.** 1'061 → **1'065 Tests**.

**Nachlesen.** `docs/zaehlperspektiven.md` · `notebooks/35_kontrollen.ipynb` ·
`tests/test_notebook_kontrollen.py` · PR #103

---

## 17.09.2026 · Der Rückgriff auf Bronze war falsch beschrieben (#102)

**Was.** Der letzte Absatz von
[`docs/zaehlperspektiven.md`](zaehlperspektiven.md) sagte, ein Widerspruch in
den Bronze-Feldern brauche „den Rückgriff auf den Bronze-Lauf, aus dem die
Zeile stammt — das Manifest nennt ihn namentlich". Beides stimmt nicht.

**Was stimmt.** Anklagetext (`charge_description`, `arrest_charge`),
Quellkategorie (`offense_category`, `primary_type`, `fbi_code`) und der
Zeitpunkt der letzten Quelländerung (`updated_on`, `updated_at`) stehen
tatsächlich nicht in Silver. Nur eben gar nicht statt „nicht durchgängig":
Silvers 28 Spalten führen keine davon.

**Was falsch war.** Das Manifest nennt unter `derived_from` **alle** Läufe, aus
denen die Tabelle entstanden ist — drei für Chicago, zwei für Detroit —, nicht
den einen je Zeile. **Silver führt überhaupt keine Zeilen-Herkunft.** Und für
Detroit gibt es den einen Lauf gar nicht: Gemessen stehen **alle 88'685
Detroiter Zeilen in beiden Schnappschüssen**; bei Chicago sind es 42 von
259'272, die in mehr als einem Lauf vorkommen. Wer zurückverfolgen will, sucht
den Schlüssel in den genannten Läufen; die Zeilen-Lineage selbst liegt in den
Bronze-Manifesten.

**Wie es dazu kam.** Der Satz stammt sinngemäss aus Artans README, wo er über
*seine* Prüfskripte gesagt war, und ist beim Übernehmen nicht nachgemessen
worden — im Unterschied zu allen Zahlen desselben Dokuments. Gefragt hat
Christian, nicht ein Test.

**Damit das nicht wieder still altert.** Drei neue Wächter in
`tests/test_zaehlperspektiven.py`: Sie halten die sieben genannten Spaltennamen
gegen das tatsächliche Silver-Schema, prüfen die Zahl der Bronze-Läufe gegen
das Manifest und die 88'685 gegen die Tabelle. Ein Absatz, der Spaltennamen
nennt, veraltet sonst schneller als einer, der Zahlen nennt.

**Zahlen.** 1'058 → **1'061 Tests**.

**Nachlesen.** `docs/zaehlperspektiven.md` · `tests/test_zaehlperspektiven.py`
· PR #102

---

## 17.09.2026 · Vier Prüfungen aus Artans SQL-Sammlung geerntet (#101)

**Was.** Artan hat am Wochenende 37 DuckDB-Abfragen gegen die gebauten
Schichten geschrieben und im Branch `sql_check_scripts` abgelegt — entgegen der
Absprache, dass Silver und Gold bei Christian liegen. Der Branch wird **nicht
gemergt und nicht gelöscht**: Er bleibt als Nachweis stehen. Vier seiner
Prüfungen sind in den Bau übernommen worden, und zwei Abschnitte seines README
als Dokumentation.

**Warum nicht mergen.** Die Abfragen laufen, wenn jemand daran denkt. Eine
Prüfung, die im Bau steht, läuft immer — und bricht ab, statt eine Zeile in
einer Ergebnisdatei zu erzeugen, die niemand liest. Dazu kommt, dass die
Zeilenzahlen im README (259.615 / 88.686) zwei Läufe alt waren und die
mitgelieferte `validation_results.json` einen Zustand festhält, der nicht mehr
gilt; ein Ergebnis mit Verfallsdatum im Repository wäre schlechter als keines.

**Die vier, in `silver_pipeline.build_crime_offense.reconcile`:**

| | was sie prüft | hart? | was sie verhindert |
| --- | --- | --- | --- |
| **S04** | keine Zeile mit `counts_case`, die nicht auch `counts` trägt | hart | die beiden Zählperspektiven liessen sich nicht mehr ineinander überführen |
| **Z05** | jeder UTC-Zeitpunkt ergibt zurückgerechnet dieselbe Ortszeit | hart | eine vertauschte Stadtzeitzone verschöbe jede Stundenverteilung |
| **M03** | jede Zeile trägt den Code, den der Crosswalk **heute** nennt | hart | eine geänderte Mapping-CSV ohne Neubau — Silver driftet von seiner Referenz weg |
| **S03** | Zeilen ohne `event_id`, Leerraum zählt als fehlend | **weich** | nichts — sie macht sichtbar, worauf eine Abfrage von Hand achten muss |

**S03 ist weich, und das ist der lehrreichste Teil der Ernte.** Als harte
Prüfung eingebaut, machte sie sofort einen bestehenden Test rot:
`test_ohne_fallnummer_ist_die_zeile_ihr_eigener_fall`. `event_id` ist die
**Fallnummer der Quelle**, und die darf fehlen; der Bau setzt sie dann auf NULL
und zählt die Zeile über `coalesce(event_id, offense_id)` als ihren eigenen
Fall — sonst fielen alle Zeilen ohne Nummer in einen einzigen Fall zusammen.
Hart eingebaut hätte S03 einen Bestand unbaubar gemacht, den der Entwurf
ausdrücklich vorsieht.

Artans Sorge bleibt trotzdem richtig, sie trifft nur eine andere Stelle: nicht
den Bau, sondern **jede Abfrage von Hand**. `count(DISTINCT event_id)`
überspringt NULL stillschweigend. Die Zahl steht deshalb im Manifest, und der
Hinweis steht in `docs/zaehlperspektiven.md`. Heute ist sie null, weil beide
Quellen durchgehend Fallnummern liefern — dass sie null *ist*, heisst nicht,
dass sie null *sein muss*.

**M03 ist die eigentliche Lücke.** Der Bau wendet den Crosswalk als Join an und
ist im Moment des Baus zwangsläufig konsistent. Die Lücke öffnet sich erst
danach: Wird die CSV geändert und Silver nicht neu gebaut, behauptet die
Tabelle etwas anderes als ihre Referenz. Das Manifest hielt die Prüfsumme der
CSV zwar fest — nur verglich sie niemand mit der Datei auf der Platte.

**Gegengeprüft, nicht angenommen.** Jede der vier ist gegen eine eingebaute
Verletzung gehalten worden: eine Zeile als Fall ohne Tat, eine um eine
Stunde verschobene Ortszeit, ganz Detroit mit Chicagos Zone gerechnet, ein
geänderter `ibr_code`, ein geändertes `match`, eine auf `false` gesetzte
Zuordnung. Alle brechen ab; ohne diese Gegenprobe wäre eine grüne Prüfung nur
eine Vermutung. Genauso geprüft ist, dass S03 **nicht** abbricht, sondern
zählt — und dass Z05 die nicht existente Ortszeit aussen vor lässt, sonst
schlüge sie bei jedem Vorstellen der Uhr an.

**Eine Grenze, die dabei sichtbar wurde.** Beim Zurückstellen der Uhr hat
Detroit schon EST, während Chicago noch CDT hat — für genau eine Stunde im Jahr
fallen beide Zonen zusammen. **30 der 88'685** Detroiter Zeilen liegen darin
und blieben einem vertauschten Zonennamen gegenüber blind. Die übrigen
**88'655** fielen auf. Das steht als Kommentar an der Prüfung, nicht als
Fussnote irgendwo.

**Nicht übernommen: A06.** Sie vergleicht die Zeilenzahl von `fact_offense`
mit der Zahl der `counts`-Zeilen in Silver. Beide Wege messen 344'617 — weil
Gold genau diese Auswahl übernimmt. Eine Prüfung, die zwei Namen für dieselbe
Rechnung gegeneinanderhält, kann nicht scheitern.

**Was als Dokumentation geblieben ist.**
[`docs/zaehlperspektiven.md`](zaehlperspektiven.md) — die vier Arten zu zählen,
was sich aus ihnen nicht addieren lässt, und was die 42 Kontrollen **nicht**
beweisen. Die Gliederung ist Artans; alle Zahlen sind am Referenzstand neu
gemessen, weil die seinen veraltet waren. Zwei Befunde daraus sind neu:
**5,2 %** der Detroiter Vorfälle enthalten Delikte aus mehr als einer
NIBRS-Familie — wer Vorfälle je Familie zählt und addiert, liegt **4'474**
(5,6 %) zu hoch. Und die letzte Woche des Jahrgangs hat zwei Tage: 1'647 Taten
gegen 6'694 in einer vollen Woche.

**Die Landkarte in Notebook 35** führt jetzt **42 Kontrollen** statt 41,
31 hart statt 30: `gegen_crosswalk` ist als eigener Ort im Code dazugekommen.
Der Wächter über die Liste hat dabei einen ersten Versuch abgelehnt, der
`reconcile` zweimal aufführte — einmal hart, einmal weich. Ein Ort im Code,
ein Eintrag; die weiche Zählung steht im Manifest, nicht in der Landkarte.

**Zahlen.** 1'035 → **1'058 Tests** (zehn Gegenproben zu den neuen Prüfungen,
elf Wächter über das neue Dokument). `silver/crime_offense` bleibt bei 347'957
Zeilen — die Prüfungen zählen alle null, sie sollen es bleiben.

**Nachlesen.** `src/crime/silver_pipeline/build_crime_offense.py` ·
`docs/zaehlperspektiven.md` · `tests/test_zaehlperspektiven.py` · PR #101

---

## 16.09.2026 · Was beim Aufräumen verlorenginge (#100)

**Was.** [`docs/datenhistorie.md`](datenhistorie.md) misst, was die Quellen
zwischen zwei Läufen tatsächlich verändern, und schlägt vor, wie sich das
behalten lässt, ohne die Läufe aufzuheben. Entscheidungsvorlage für den 18.9.

**Warum.** Für die Auswertung zählt der aktuelle Stand. Die Bewegung der
Quellen ist aber selbst ein Gegenstand — *was ändert sich, wie oft, welcher
Art, und was verschwindet.* Heute steckt diese Information implizit in den
Bronze-Läufen; sobald `aufraeumen` einen löscht, ist sie weg.

**Die Messung.** Detroit hat zwei vollständige Schnappschüsse desselben
Bestands, 21 Stunden auseinander:

| | Zeilen |
| --- | ---: |
| in beiden | 88'685 |
| neu, verschwunden | 0, 0 |
| **echte Inhaltsänderung** | **102** |
| nur `updated_at` bewegt | 147 |

Darunter **14 geänderte Deliktcodes**, und die haben ein Muster: durchweg vom
spezifischen zum allgemeinen Code, `3072 → 3002`, `4801 → 4800`, `1178 → 1108`
und so fort. `3072` trägt allein 1'403 zählende Taten, alle als `ambiguous`
markiert — eine Umcodierung dort verschiebt die Vergleichszahl.

**Die Falle, ohne die der Vorschlag nicht trüge.** Ein naiver Vergleich meldet
**88'677** geänderte Zeilen statt 102, Faktor 870. Zwei Quellen erzeugen das
Rauschen: `ESRI_OID` ändert sich bei praktisch jeder Zeile und ist eine
ArcGIS-Zeilennummer ohne Aussage; und 150 der 160 Beschreibungsänderungen sind
reine Leerzeichen, weil die Quelle auf feste Breite auffüllt. Echt sind zehn,
darunter `BURGLARY - FORCED ENTRY` → `DAMAGE TO PROPERTY`.

**Der Vorschlag.** Nicht die Läufe aufheben, sondern den Unterschied
herausziehen, bevor sie gelöscht werden dürfen. 31,9 MB lagern, um 102 Zeilen
zu bewahren, ist das falsche Verhältnis. Eine append-only Silver-Tabelle mit
einer Zeile je geändertem Feld, dazu eine neue Vorbedingung in `aufraeumen`.

**Vier Entscheidungen stehen offen**, jede mit Empfehlung und Folge: welche
Felder als Änderung zählen, ob Löschungen erkennbar sein sollen, wie oft
geladen wird, und ob die Tabelle vor oder nach der Harmonisierung liegt.

**Wächter.** Neun Tests gegen die gepinnten Läufe. Einer fand beim ersten Lauf
einen Fehler im Dokument: Ich hatte eine Gold-Zahl genannt und Silver
darübergeschrieben, 1'403 zählende Taten gegen 1'443 Anklagen. Genau die
Granularität, die man an dieser Stelle verwechselt.

**Zahlen.** 1'026 → **1'035 Tests**.

---

## 16.09.2026 · Der Einstieg von Notebook 36 sagte noch das Alte (#99)

**Was.** Ein Absatz. `notebooks/36_hypothesen.ipynb` fasste im Einstieg
zusammen, eine Hypothese sei *„in einem Teil nicht erfüllt"*. Seit #98 ist H3
eingelöst, und der Abschnitt zu H3 sagt das auch — nur die Zusammenfassung
ganz oben nicht.

**Warum das mehr ist als ein Tippfehler.** Der Einstieg ist die Stelle, die
jemand liest, der nicht das ganze Notebook durchgeht. Hätte er sie
übernommen, stünde in der Präsentation ein Befund, den es nicht mehr gibt.

**Was jetzt dort steht.** Alle sechs halten. Zwei tragen eine Einschränkung,
die im Konzept nachgezogen gehört: H1 ist für die drei Referenzquellen anders
zu formulieren, und H6 beruft sich auf einen Referenzrechner, den niemand
festgelegt hat. Dazu die Geschichte von H3 als das, was sie ist — eine
Hypothese, die beim ersten Lauf nicht hielt und noch am selben Tag eingelöst
wurde.

**Zahlen.** Unverändert 1'026 Tests.

---

## 16.09.2026 · H3 eingelöst: die zwei Stunden im Jahr (#98)

**Was.** `silver/crime_offense` führt `local_time_ambiguous` und
`local_time_nonexistent`, `reconcile` zählt beide je Stadt ins Manifest, und
`local_time_ambiguous` geht bis `gold/fact_offense` mit. Silver-Vertrag 1 → 2,
Gold-Vertrag 3 → 4.

**Warum.** H3 verlangt, dass *„nicht existente oder mehrdeutige lokale
Quellzeiten ausdrücklich als Sonderfälle ausgewiesen"* werden. Die Messung in
`notebooks/36_hypothesen.ipynb` hatte gezeigt, dass die Unabhängigkeit von der
Rechnerzeitzone hält, die Ausweisung aber fehlt: **48 Chicagoer Zeilen** liegen
in der Stunde, die es am 3. November zweimal gab, und nichts machte sie
sichtbar.

**Wie erkannt wird.** Ohne jedes Wissen über Wechseldaten, allein aus der
Zeitzonendatenbank:

* *Nicht existent:* Hin und zurück gerechnet kommt eine **andere** Ortszeit
  heraus. Die Uhr wurde vorgestellt, die genannte Zeit gab es nie.
* *Mehrdeutig:* Eine Stunde vor **oder** nach dem gewählten Zeitpunkt führt auf
  **dieselbe** Ortszeit. Die Uhr wurde zurückgestellt, es gab sie zweimal.

Beide Prädikate sind gegen sieben Zeitpunkte geprüft, davon vier Randfälle
einschliesslich der Minuten knapp davor und danach.

**Warum Detroit beide Spalten trägt, obwohl sie dort immer falsch sind.** Die
Quelle liefert Millisekunden seit Epoch, also einen **Zeitpunkt**; daraus
entsteht immer eine eindeutige Ortszeit. Mehrdeutig wird es erst, wenn eine
Quelle Wanduhrzeit **ohne Zone** liefert, und das tut nur Chicago. Die Spalte
steht trotzdem in beiden Städten, damit die Tabelle eine Granularität hat und
nicht zwei.

**Warum es bis Gold mitgeht.** Weil `hour_of_day` dort gerechnet wird. Eine
Stundenverteilung zählt die 48 Zeilen in einen der beiden Töpfe; ohne die
Spalte wäre nicht zu sehen, welche das sind. Dieselbe Überlegung wie bei den
Spurenmengen am Vortag.

**Was dabei sonst noch stimmte.** Der Modul-Docstring behauptete, `reconcile`
zähle diese Fälle. Das tat er nicht. Jetzt tut er es, und ein Test hält
Docstring und Code aneinander.

**Wächter.** Drei neue Tests, dazu ein angepasster. Der wichtigste prüft beide
Prädikate gegen sieben Zeitpunkte; zwei weitere halten fest, dass die Spalten
in der Endauswahl stehen und dass `reconcile` sie zählt. Zwei davon fallen
gegen den Stand von gestern.

**Zahlen.** 1'023 → **1'026 Tests**. Silver-Vertrag 1 → 2, Gold 3 → 4.
Zeilenzahlen und Raten ändern sich nicht.

---

## 16.09.2026 · Die Hypothesen H1 bis H6, nachgewiesen (#97)

**Was.** [`notebooks/36_hypothesen.ipynb`](../notebooks/36_hypothesen.ipynb)
misst die sechs Hypothesen aus Kapitel 3 der Konzeptfassung und weist je
Hypothese aus, ob sie hält. Kapitel 4 verlangt drei getrennte Evidenzarten und,
wo gemessen wird, drei Wiederholungen mit Median und Spannweite. Genau so ist
es gemacht.

| | Hypothese | Ergebnis |
| --- | --- | --- |
| H1 | gelieferte IDs == Erwartungsmenge | hält, wörtlich für Chicago und Detroit |
| H2 | Wiederholung erzeugt denselben Inhalt | hält, drei Neubauten, sechs Tabellen |
| H3 | Tageszuordnung zeitzonenunabhängig, Sonderfälle ausgewiesen | **hält zur Hälfte** |
| H4 | Codes zeigen mehr Mehrdeutigkeit als Namen | hält deutlich, 71 % der Zeilen |
| H5 | fixierter Eingabestand, gleiches Ergebnis | hält für den gepinnten Stand |
| H6 | Aufbau unter zehn Minuten | hält, Median 2,3 s |

**Der Befund, für den sich das Notebook gelohnt hat.** H3 verlangt, dass
*„nicht existente oder mehrdeutige lokale Quellzeiten ausdrücklich als
Sonderfälle ausgewiesen"* werden. Die Unabhängigkeit von der Rechnerzeitzone
hält über vier Zonen von Kiritimati bis Anchorage. Die Ausweisung fehlt:
**48 Chicagoer Zeilen** liegen in der doppelten Stunde am 3. November, und
weder eine Spalte noch das Manifest noch eine Warnung nennt sie.

**Und ein Docstring, der etwas Falsches behauptete.**
`silver_pipeline.build_crime_offense` sagte, `reconcile` zähle die Fälle in
der nicht existenten Stunde. Das tut er nicht — `checks` enthält keinen
solchen Zähler. Der Satz ist korrigiert und benennt die Lücke jetzt offen; ein
Test hält fest, dass er nicht zurückkommt, solange es den Zähler nicht gibt.

**Was H4 so deutlich macht.** Chicago liefert zu jeder Zeile den Code `iucr`
**und** die Kategorie `primary_type`. Damit lässt sich direkt zählen, was eine
Zuordnung nach Namen verlöre: 19 von 31 Bezeichnungen decken mehr als einen
NIBRS-Code ab, `THEFT` allein sieben. **185'004 von 259'272 Zeilen**, also
71,4 Prozent, liegen unter einer solchen Bezeichnung.

**Drei Formulierungen, die nachgezogen gehören.** H1 braucht einen Zusatz für
Quellen ohne Identifikatormenge — TIGER, ACS und NOAA belegen Vollständigkeit
anders. H3 muss entweder eingelöst oder auf den haltenden Teil zugespitzt
werden. Und H6 beruft sich auf einen *„vereinbarten Referenzrechner"*, den
weder Konzept noch Absprache festlegen.

**Wächter.** Acht Tests. Alle sechs Hypothesen müssen als Abschnitt vorkommen,
jede ein Ergebnis nennen, in der Bilanz stehen und wörtlich zitiert sein; das
Notebook misst dreimal mit Median und Spannweite und sagt, was es nicht zeigt.

**Zahlen.** 1'015 → **1'023 Tests**. Vierzehn Notebooks, acht davon im
Datenlauf.

---

## 15.09.2026 · Ein Messwert 0 ist nicht trocken (#96)

**Was.** `gold/dim_city_day` führt jetzt `precipitation_trace` und
`snowfall_trace` mit. Die Vertragsversion von Gold steigt auf **3**.

**Warum.** NOAA kennt das Messflag `T`: gefallen, aber unter der Auflösung des
Geräts. Der Messwert ist dann `0`, und das heisst etwas anderes als *trocken*.
Silver hält den Unterschied seit jeher; Gold liess beide Spalten fallen.

Gemessen war das keine Feinheit:

| | Tage mit 0 mm Niederschlag | davon Spurentage |
| --- | ---: | ---: |
| Chicago | 241 | 45 |
| Detroit | 240 | 68 |
| **zusammen** | **481** | **113** |

Fast ein Viertel der scheinbar trockenen Tage war nicht trocken, und der
Tabelle war es nicht anzusehen. Beim Schnee sind es weitere 55 Tage.

**Woher der Befund kommt.** Aus Artans Konzeptentwurf für Leistungsnachweis 1,
Abschnitt 9.3: *„Spurenmengen von Niederschlag und Schnee müssen in Gold
erhalten bleiben. Ein Messwert 0 mit Trace-Flag bedeutet nicht dasselbe wie
sicher trocken."* Der Satz stand als Anforderung da und war nicht umgesetzt.

**Was der Feldkatalog dazu lernt.** Die beiden Beschreibungen wandern von
`JE_TABELLE` nach `GEMEINSAM` in `tools/build_feldkatalog.py` — die Spalten
bedeuten in Silver und Gold dasselbe, und zwei Einträge wären zwei Stellen, an
denen dieselbe Erklärung veralten kann.

**Wächter.** Zwei Tests. Der erste baut einen Tag mit 0 mm und Spurenflag und
einen ohne und verlangt, dass sie unterscheidbar bleiben; der zweite hält die
Vertragsversion. Beide fallen gegen den Stand von gestern.

**Zahlen.** 1'013 → **1'015 Tests**. Gold-Vertrag 2 → **3**.

---

## 15.09.2026 · Die Kontrollen an einem Ort, vorgeführt (#95)

**Was.** [`notebooks/35_kontrollen.ipynb`](../notebooks/35_kontrollen.ipynb)
zeigt alle **41 Kontrollen** der Strecke in der Reihenfolge, in der sie
greifen — von der Ingestion bis Gold, dazu Ablage, Serving und
Orchestrierung. Jede wird **zweimal** vorgeführt: einmal mit Daten, die sie
durchlässt, und einmal mit Daten, die sie fangen soll.

**Warum.** Die Kontrollen liegen dort, wo sie wirken, und das ist richtig so.
Nur muss man dafür zehn Pakete durchsehen, um die Frage zu beantworten, die
in einem Kolloquium zuerst kommt: *Was prüft ihr eigentlich?*

**Die zweite Vorführung ist die wichtigere.** Eine Kontrolle, von der man nur
gesehen hat, dass sie schweigt, hat man nicht gesehen. Deshalb fällt im
Notebook der Vollständigkeitsnachweis über eine verlorene Seite, das
Publish-Gate über eine verdeckte Stadt, `reconcile` über einen doppelten
Deliktschlüssel und `verify` über eine Datei, die keine Parquet-Datei ist.

**Ein Fall reist durch.** `JH100028`, der erste Mordfall des Jahrgangs mit
seinen zwei Opferzeilen, geht am Schluss durch alle Schichten, und daneben
steht, welche Kontrolle ihn angesehen hat und was sie gesagt hat.

**Die Unterscheidung, die das Notebook trägt.** *Hart* bricht ab, *weich*
markiert und zählt. Hart ist richtig, wo etwas **still** schieflaufen kann;
weich, wo etwas **unvollständig** ist. Eine harte Kontrolle auf fehlende
Koordinaten hiesse, dass Chicagos Jahrgang gar nicht entsteht — 1'748 Delikte
tragen keine. Die weiche macht die Lücke abfragbar statt unsichtbar.

| Schicht | hart | weich |
| --- | ---: | ---: |
| Ingestion | 9 | 6 |
| Ablage | 5 | 1 |
| Silver | 6 | 1 |
| Gold | 4 | 1 |
| Serving | 2 | 1 |
| Orchestrierung | 4 | 1 |
| **gesamt** | **30** | **11** |

Zwei Beobachtungen aus dieser Verteilung stehen im Notebook: Die Ingestion
trägt die meisten harten Kontrollen, weil nur dort noch etwas über die
**Quelle** zu sagen ist. Und genau **eine** Kontrolle verhindert eine
Veröffentlichung, nämlich das Publish-Gate; alle anderen brechen ab, bevor
etwas entsteht.

**Es läuft überall.** Das Notebook erzeugt seine Beispiele selbst und braucht
kein gebautes `data/`. Es läuft ab sofort im wöchentlichen Datenlauf mit,
damit eine Vorführung, die nicht mehr funktioniert, auffällt.

**Wächter.** Sieben Tests. Der wichtigste hält jeden in der Landkarte
genannten Namen gegen den Code — beim Schreiben stand dort
`detroit_arcgis.get_object_ids`, und das ist eine Methode von `ArcGISClient`.
Das Notebook hat es beim ersten Lauf selbst gemeldet; der Test wiederholt die
Prüfung auf jedem Pull Request, damit es nicht erst eine Woche später
auffällt.

**Zahlen.** 1'006 → **1'013 Tests**. Dreizehn Notebooks, sieben davon im
Datenlauf.

---

## 15.09.2026 · Zwei Optionen, die nirgends ankamen (#94)

**Was.** Die beiden letzten Befunde der externen Prüfung, beide klein und
beide mit derselben Form: Etwas ist ausdrücklich angeboten und wirkt nicht.

**1 · `--data-root` erreichte die Stufen nicht.** Der Gesamtlauf wertete die
Option aus und benutzte sie für Inventar und Protokoll — die dreizehn
Unterprozesse bekamen sie nie. Wer den Lauf auf ein anderes Verzeichnis
richtete, baute im Standardordner und protokollierte anderswo. Die abgefangenen
Befehlszeilen zeigten es: keine einzige trug die Option.

Jetzt trägt sie jede, und zwar **immer** — auch ohne `--data-root` steht der
aufgelöste Pfad in der Befehlszeile. Das beseitigt eine zweite Fehlerquelle:
Vater und Kind lesen dieselbe Umgebung, aber nicht mehr notwendigerweise
gleich.

**Ein Modul kannte die Option gar nicht.** `detroit_pipeline.extract_detroit`
nahm `--output-dir` und `--raw-dir` einzeln. Es hat jetzt dieselbe Option wie
die übrigen elf, und ein Test hält fest, dass jedes Stufenmodul sie kennt —
sie weiterzureichen hilft nur, wenn sie drüben ankommt.

**2 · Eigene Tabellen in der Serving-Datenbank gingen beim Neubau verloren.**
Konzept 5.2 lädt ausdrücklich dazu ein: *„wer ein Zwischenergebnis behalten
will, legt daneben `CREATE TABLE meins AS SELECT …` an"*, und die
Hinweistabelle der Datenbank sagt dasselbe. Nur entstand beim Bau eine **neue
Datei**, die die bisherige ersetzte. Die eigene Tabelle war weg, ohne Meldung.

Sie werden jetzt übernommen. Alles, was dieses Modul anlegt, sind Sichten —
was also als Tabelle dasteht, hat jemand selbst angelegt. Trägt eine davon den
Namen einer Sicht, gewinnt die Sicht und die Tabelle wird mit Meldung
übergangen: Sonst verdeckte ein eingefrorenes Zwischenergebnis stillschweigend
die Daten, über die es gerechnet wurde.

**Wächter.** Vier Tests, alle vier fallen gegen den Stand von gestern: jede
Stufe bekommt die Wurzel, jedes Stufenmodul kennt die Option, eine eigene
Tabelle überlebt den Neubau, und sie verdeckt dabei keine Sicht.

**Zahlen.** 1'001 → **1'006 Tests**.

---

## 15.09.2026 · Kontrollen, die vor der Veröffentlichung greifen (#93)

**Was.** Drei Befunde derselben externen Prüfung, alle an Kontrollen, die
Probleme zwar erkannten, ihre Veröffentlichung aber nicht verhinderten.

**1 · Das Publish-Gate rechnete über beide Städte gemittelt.** Ein Mittel
verdeckt. Vorgerechnet: 750 Chicagoer Zeilen zu 100 % exakt und 250 Detroiter
zu 70 % ergeben 92,5 % gemeinsam — bestanden, bei einer Schwelle von 85 %.
Detroits Crosswalk hätte zu einem Drittel brechen können, ohne dass etwas rot
wird. Chicago ist dreimal so gross wie Detroit; der Gesamtanteil trägt deshalb
Chicagos Zahl.

Das Gate prüft jetzt den Gesamtanteil **und jede Stadt für sich**, mit
denselben Schwellen: Wer den Vergleich zweier Städte baut, muss ihn für beide
tragen können. Die Zahlen je Stadt stehen im Nachweis, damit nachlesbar ist,
worauf entschieden wurde. Der echte Stand trägt es bequem — Chicago 95,61 %,
Detroit 95,14 % exakt.

**2 · Eine fehlende Quelle galt als frisch.** Geprüft wurde nur, was
`aktualitaet` gefunden hatte, und das sind genau die *vorhandenen* Quellen.
Bei vier fehlenden von fünf kam `{}` heraus, also „alles in Ordnung" — obwohl
der Docstring seit jeher sagte, eine Quelle ohne fertigen Lauf zähle als
unendlich alt. Jetzt tut der Code das auch.

Die Liste der erwarteten Bestände ist **abgeleitet, nicht gepflegt**: Jede
Ingestion-Stufe nennt in `STUFEN`, welchen Bronze-Bestand sie füllt. Eine
sechste Quelle taucht in der Prüfung auf, sobald sie eine Stufe hat.

**3 · Die Frische wurde nach allen dreizehn Stufen geprüft.** Der Lauf endete
zwar mit `failed`, aber Gold und Serving waren gebaut — aus Daten, die er
selbst als zu alt erkannt hatte. Eine Kontrolle, die erst nach der
Veröffentlichung greift, ist ein Protokoll, keine Kontrolle. Der Lauf ist
jetzt zweigeteilt: laden, prüfen, ableiten.

**Was offen bleibt.** Geprüft wird das Ladedatum, nicht der Inhalt. Ein frisch
geladener, inhaltlich alter Bestand fällt damit nicht auf. Und die
Census-Vintage ist bewusst eingefroren; für sie wäre eine eigene Regel
richtig, statt sie an derselben Achttagesschwelle zu messen. Beides steht im
Ausblick.

**Wächter.** Sieben Tests. Vier fallen gegen den Stand von gestern: die
verdeckte Stadt, die fehlende Quelle, die Reihenfolge, die abgeleitete
Quellenliste. Drei sind Gegenproben — der Gesamtanteil allein lässt den Fall
weiterhin durch (die Korrektur hängt also an den Städtezahlen, nicht an einer
nebenbei verschärften Schwelle), zwei gute Städte gehen durch, und die
Städtezahlen stehen im Nachweis.

**Zahlen.** 995 → **1'001 Tests**.

---

## 15.09.2026 · Gleiche Grösse ist kein gleicher Inhalt (#92)

**Was.** Drei Befunde einer externen Prüfung an der Ablage, alle nachgestellt
und behoben.

**1 · Die Integritätsprüfung nahm Byteanzahl für Inhalt.** Liess sich das ETag
eines S3-Objekts nicht als MD5 lesen, genügte die gleiche Grösse für
„identisch" — der Upload unterblieb. In der Gegenprobe galten drei Bytes `NEU`
als identisch mit drei Bytes `ALT`, und oben blieb der alte Inhalt stehen. Ein
ETag ist nicht immer eine Prüfsumme: Bei mehrteiligen Uploads setzt S3 einen
Hash über die Teil-Hashes mit angehängtem `-N`. Ist es unbrauchbar, wird der
Inhalt jetzt geholt und verglichen — und das kostet nur dann einen Download,
wenn die Grössen ohnehin gleich sind. **Unbekannte Prüfsumme gilt nicht als
Gleichheit.**

**2 · „Manifest zuletzt" schützt keine bestehende Tabelle.** Es schützt einen
*neuen* Lauf: ohne Manifest gilt er nicht. Wird dagegen eine vorhandene
Tabelle aktualisiert, fällt zuerst die Parquet-Datei. Bricht danach der
Manifest-Upload ab, liegt oben der neue Inhalt unter dem alten Manifest — mit
Bauzeitpunkt vom 1. August und Status `complete`. Genau so war es in der
Gegenprobe zu sehen.

Seither fällt **zuerst der Status**: Das entfernte Manifest wird auf
`publishing` gesetzt, bevor eine Datei fällt. Scheitert schon das, ist nichts
angefasst. Ein Leser sieht danach der Reihe nach den vollständigen alten
Stand, dann *keinen*, dann den vollständigen neuen.

**Damit das wirkt, musste `tabellen()` den Status lesen.** Er wurde bisher
geschrieben und nie gelesen — jede Tabelle mit Manifest galt als gebaut, auch
eine mitten im Publizieren. Jetzt gilt derselbe Massstab wie bei `laeufe()`.

**3 · Die Arbeitsverzeichnisse hiessen für alle gleich.** `.<name>.part` und
`.<name>.superseded`, und jeder Lauf räumte sie zu Beginn weg — auch die eines
anderen, der gerade schrieb. Sie tragen jetzt die Prozessnummer.

**Was offen bleibt, und warum.** Die fünf Gold-Tabellen werden weiterhin
nacheinander veröffentlicht; zwischen `fact_offense` und `dim_city_day` liegt
ein Fenster mit gemischtem Stand. Ein gemeinsamer Stand braucht Versionspfade
und einen Verweis, der umgelegt wird — ein kleiner, aber breiter Eingriff, weil
jeder Leser die Tabelle dann über den Verweis auflöst. Der Nutzen entsteht,
sobald ein Dashboard danebensteht, also für LN2. `ausblick.md` Abschnitt 6
beschreibt den Bau, `ausblick.md` Abschnitt 7 ordnet ihn ein.

**Wächter.** Neun Tests. Sechs davon fallen gegen den Stand von gestern:
gleiche Grösse ohne Prüfsumme, der abgebrochene Manifest-Upload, die
gescheiterte Entwertung, die unfertige Tabelle, das fremde
Arbeitsverzeichnis. Drei sind Gegenproben, damit die Korrektur nicht zu viel
tut: identischer Inhalt wird nicht erneut geladen, eine **neue** Tabelle wird
nicht entwertet, ein gescheiterter Lauf lässt den alten Stand stehen.

**Zahlen.** 986 → **995 Tests**.

---

## 15.09.2026 · Das dritte Abgabedokument bekommt seinen Wächter (#91)

**Was.** `leistungsnachweise.md` führte acht überholte Aussagen. Sie sind
korrigiert, und `tests/test_unterstroemungen.py` prüft jetzt **beide**
Unterströmungs-Tabellen statt nur einer, dazu die Lebenszyklus-Tabelle und
zwei Sätze im Fliesstext.

**Warum.** Dieselbe Tabelle gibt es zweimal, in `ln1_konzept.md` und in
`leistungsnachweise.md`. Der Wächter deckte nur die erste ab. Die zweite ist
genau so veraltet, wie die erste es dreimal war — nur unbemerkt, weil sie
niemand prüfte:

| Was dort stand | Was gilt |
| --- | --- |
| „keine CI, keine Alarmierung" | fünf Jobs auf jedem Pull Request seit dem 12.9. |
| Lücke „Architekturdiagramm" | zwei Bilder, aus dem Code erzeugt |
| Lücke „Katalog/Glossar der Felder" | `feldkatalog.md`, aus den Manifesten erzeugt |
| Orchestration: „grösste Lücke, heute manuelle Aufrufe" | `run_all`, dreizehn Stufen |
| „Evaluation schriftlich, Silver/Gold leer" | beides gebaut, Evaluation in Kapitel 7 |
| Lücke „Qualitätsanalyse Detroit" | Notebook 13 |
| Lücke „Detroit-Quellnotebook" | Notebook 11 |
| „233 Tests" und an anderer Stelle „633 Tests" | 986 |

**Das Dokument widersprach sich dabei selbst.** Abschnitt 1 schrieb „Silver ist
leer"; zwei Zeilen darüber stand in derselben Tabelle „vier Silver-Tabellen,
`crime_offense` mit 347'957 Zeilen".

**Zwei weitere Funde nebenbei.** `ln1_konzept.md` führte unter Orchestration
„keine Zeitplanung" — den wöchentlichen Datenlauf gibt es seit dem 13.9.
Und `projektabsprache.md` führte „Weiterhin offen: keine CI. Niemand führt
diese Tests bei einem Push aus", drei Tage nachdem die CI stand und während
sie genau diesen Satz prüfte. Beides korrigiert.

**Wächter.** Die drei bestehenden Prüfungen laufen jetzt über beide Tabellen,
dazu zwei neue: die vierspaltige Lebenszyklus-Tabelle, und ein Test gegen
Sätze im Fliesstext, der etwas als offen führt, das es gibt. Letzterer
vergleicht **exakte Formulierungen**, keine Suchmuster: Dieselben Dokumente
erwähnen vergangene Lücken absichtlich („das stand als Lücke in Tabelle 5.3"),
und ein unscharfer Treffer darauf wäre ein falscher Alarm.

Alle acht Altlasten wurden einzeln wieder eingesetzt; jede fällt durch.

**Zahlen.** 980 → **986 Tests**.

---

## 14.09.2026 · Die Referenz gehoert ins Repository (#90)

**Was.** `docs/referenz/` ist jetzt versioniert. Dazu drei Aenderungen, ohne
die das nicht geht: Der Bau setzt `PYTHONHASHSEED` und startet sich einmal
selbst neu, eine Marke `erzeugt-mit.json` haelt fest, womit die abgelegten
Seiten geschrieben wurden, und `.gitattributes` legt sie ueberall mit LF ab.

**Warum.** In diesem Projekt liegen erzeugte Artefakte im Repository — die
Crosswalks, der Feldkatalog, die beiden Architekturbilder. Die Regel dahinter
ist nicht die Groesse, sondern die Reproduzierbarkeit: Was ein zweiter Lauf
byteweise wiederholt, gehoert hinein, weil es dann pruefbar ist. #89 hatte die
Referenz wegen ihrer 7 MB davon ausgenommen und damit die Regel gegen ihr
eigenes Kriterium eingetauscht.

**Der Fehler, den das aufgedeckt hat.** Der Waechter aus #89 behauptete
*„ein zweiter Lauf liefert dieselben Dateien"* und war gruen. Er war es aus
dem falschen Grund: Er baute **zweimal im selben Prozess**. Manche
Vorgabewerte im Code sind Mengen, pdoc druckt sie mit `repr`, und die
Reihenfolge einer Menge von Zeichenketten haengt an deren Hashwerten — die
sind je Prozess zufaellig, innerhalb eines Prozesses aber fest. Zwei Baeufe im
selben Prozess konnten also gar nicht abweichen.

Fuenf Laeufe in fuenf Prozessen zeigten dann bis zu **vier verschiedene
Dateien**, ohne dass sich eine Zeile Code geaendert haette:
`frozenset({'complete', 'success'})` im einen Lauf, `frozenset({'success',
'complete'})` im naechsten. Mit festem Hash-Seed sind sechs Laeufe identisch.
Der Test ruft das Werkzeug jetzt als eigenen Prozess auf — so, wie ein Mensch
es aufruft.

**Warum eine Marke noetig ist.** pdocs Ausgabe ist nur *innerhalb* einer
Python-Version gleich. 3.13 schreibt `pathlib._local.Path`, wo 3.12 noch
`pathlib.Path` schreibt, und zeigt fuer `__init__` einen Quelltext, den 3.12
nicht hat: **19 von 25 Dateien** unterscheiden sich zwischen den beiden.
Dasselbe gilt fuer die Plattform, aus einem Grund, der sich nicht
wegkonfigurieren laesst: Ein `Path`-Vorgabewert in einer Signatur ist unter
Windows eine `WindowsPath` und sonst eine `PosixPath`, und pdoc druckt den
Klassennamen mit. `os.name` steht deshalb ebenfalls in der Marke.

Der Vergleich laeuft damit auf Linux und macOS mit der Python-Version aus der
Marke — in CI also im 3.13-Job unter Ubuntu, auf jedem Push. Dieselbe
Ueberlegung wie bei den drei PDF-Reproduktionen, die nur unter Linux laufen:
Ein Waechter, der auf der halben Testmatrix rot ist, ohne dass etwas kaputt
waere, ist keiner.

**Was `.gitattributes` klarstellt.** `docs/referenz/**` wird mit LF abgelegt,
sonst waere ein Windows-Bau auf Linux erwartbar verschieden. Die Regel gilt
**nur dort**: Die Crosswalks unter `config/` liegen mit CRLF im Repository, so
wie die Werkzeuge sie aus den amtlichen PDFs schreiben, und drei Tests
vergleichen genau diese Bytes. Eine eol-Regel darueber haette sie beim
naechsten Checkout umgeschrieben und die Reproduktion gebrochen.

**Der zweite Fehler, den erst CI zeigte.** Der Byte-Vergleich war lokal
gruen und auf beiden 3.13-Runnern rot — eine einzige Datei, `storage.html`,
und keine Ahnung woran. Die Ursache stand in einer von 12'000 Zeilen:
`S3Client` ist ein `typing.Protocol`, und Python haengt solchen Klassen ein
`__init__` aus `typing.py` an. pdoc zeigt jedes `__init__` mit Parametern —
also standen **neun Zeilen CPython** in der Seite, samt ihrer Zeilennummern.
Die verschieben sich zwischen Patchversionen; auf 3.13.0 lag die Funktion bei
Zeile 1940, auf dem Runner anderswo.

Gefiltert wird das ueber pdocs eigenen Ausstieg: `tools/pdoc_vorlage/`
ueberschreibt das Makro `is_public` und laesst Mitglieder weg, deren
Quelldatei ausserhalb von `src/crime` liegt. Ein erster Entwurf nahm zu viel
weg — `<string>` als Quelldatei heisst *erzeugt*, nicht *fremd*, und damit
verschwanden auch alle `NamedTuple`-Konstruktoren. Beide Faelle stehen jetzt
als Test.

Nebenbei: Dass der Waechter nur *„storage.html weicht ab"* sagte, war selbst
ein Mangel. Er nennt jetzt die erste abweichende Zeile.

**Zahlen.** 976 → **980 Tests**. Das Repository waechst von 9,0 auf 9,6 MB
(gemessen an zwei gepackten Klonen). Die 7,2 MB HTML kosten also rund 0,6 MB,
weil fuenfundzwanzig Seiten dasselbe CSS tragen und sich entsprechend gut
packen lassen.

---

## 14.09.2026 · Die Docstrings werden blaetterbar (#89)

**Was.** `python tools/build_referenz.py` erzeugt `docs/referenz/` — eine Seite
je Modul, mit Suche und Quelltext daneben, aus den Docstrings. Das Verzeichnis
ist nicht versioniert; es entsteht in gut einer Sekunde neu. Auf `main` baut
es ein CI-Job und haengt es als Artefakt an den Lauf, damit es auch ohne
Python zu oeffnen ist.

**Warum.** Der vorige Eintrag hielt fest, dass dieses Projekt **mehr Erklaerung
als Code** hat. Der groesste Teil davon steht in Docstrings — an der einzigen
Stelle also, an der man ihn nur findet, wenn man schon weiss, wo man suchen
muss. `architektur.md` zeigt seither den Aufbau, `eine-zahl.md` den Weg einer
Zahl. Was fehlte, war das Nachschlagewerk dazwischen.

**Die Luecke, die dabei auffiel.** `chicago_pipeline` hatte eine
**vollstaendig leere `__init__.py`** — das Paket der wichtigsten Quelle des
Projekts, ohne eine Zeile Erklaerung. Im Quelltext faellt das niemandem auf,
weil man ohnehin gleich ins Modul springt. In einer Referenz ist es eine leere
Seite. Der Docstring steht jetzt da, und ein Test haelt fest, dass jedes Paket
und jedes Modul einen hat.

**Die Startseite ist abgeleitet, nicht gepflegt.** pdoc erzeugt als Startseite
eine nackte Modulliste mit Fremdlogo. Stattdessen stehen die zehn Pakete in
der Reihenfolge des Gesamtlaufs: Fundament, dann die vier Gruppen aus
`run_all.STUFEN`, dann was zu keiner Stufe gehoert. Die Stufenzahlen kommen aus
`STUFEN`, jede Kurzbeschreibung ist die erste Zeile des Paket-Docstrings. Ein
neues Paket erscheint damit von selbst an der richtigen Stelle.

**Zwei Entwuerfe, die verworfen wurden.** Der erste gruppierte nach der Tiefe
im Importgraph — das ergab lesbare Zahlen und falsche Namen: `orchestration`
landete unter *Ableitung*, `gold_pipeline` in einer Ebene ohne Titel. Die
Tiefe bedeutet etwas anderes als die Schicht. Der zweite schrieb ueber jede
Gruppe, was die Schicht tut — und wiederholte damit bei `silver_pipeline` und
`gold_pipeline` den Docstring, der einen Zentimeter darunter nochmal stand.
Beides prueft jetzt je ein Test.

**Was pdoc nebenbei zeigte.** Rund dreissig Typannotationen kann es nicht
aufloesen. Dreiundzwanzig sind `NamedTuple`-Felder, ein bekannter Fall bei
aufgeschobenen Annotationen. Die uebrigen vier sind echt: Die Methode `list`
der drei S3-Klassen in `storage` verdeckt im Klassenkoerper das eingebaute
`list`. Zur Laufzeit stoert das nichts, und der Name bleibt, weil er die
S3-Schnittstelle spiegelt — aber er steht jetzt begruendet im Code statt
unbemerkt darin. Das Werkzeug sammelt die Warnungen ein und meldet eine Zeile
statt dreissig.

**Waechter.** 17 Tests: jedes Paket und jedes Modul hat einen Docstring, jede
erste Zeile ist ein ganzer Satz, jedes Paket bekommt eine Seite, kein Verweis
der Startseite ist tot, keine Seite traegt einen Rechnerpfad — und **ein
zweiter Lauf liefert dieselben Dateien**, dieselbe Regel wie bei den
Crosswalks, dem Feldkatalog und den Architekturbildern.

**Zahlen.** 959 → **976 Tests**.

---

## 14.09.2026 · Eine Zahl von Ende zu Ende (#88)

**Was.** [`docs/eine-zahl.md`](eine-zahl.md) rollt die Rate **94,5** rückwärts
auf: sieben Stufen von der Folie bis zu den 26 gzip-Dateien, die die Stadt
Chicago am 5. September geliefert hat. Zähler, Nenner, Herkunftskette,
Vollständigkeitsnachweis, Rohantwort.

**Warum.** Der Lesepfad in [`architektur.md`](architektur.md) führt durch den
Code. Er beantwortet nicht die Frage, die in einer Abgabe zuerst kommt:
*Woher wisst ihr das?* Dieses Dokument tut es an einer einzigen Zahl — und
weil der Weg alle Schichten durchläuft, kommt dabei jede wesentliche
Entscheidung des Projekts genau einmal vor, in der Reihenfolge, in der sie
wirkt.

**Der Einzelfall, der alles auf einmal trägt.** `JH100028`, der erste Mordfall
des Jahrgangs: zwei Opfer, zwei Zeilen, `offense_id` 27932 und 27933. Die
Ortszeit 00:56 ist UTC 06:56, beim zweiten Opfer springt die UTC-Zeit auf den
Folgetag. IUCR `0110` wird NIBRS `09A`, Status `exact`. Der Tract kam aus dem
eigenen Punkt-in-Polygon-Join. Beide Zeilen zählen als Tat, nur die frühere
als Fall. Vier Entscheidungen — Zeitzone, NIBRS, Raum, Granularität — an einem
Fall, den man in einer Minute vorführen kann.

**Was beim Schreiben auffiel.** Die Herkunftskette ist reicher, als sie bisher
irgendwo dargestellt war: Sie hängt nicht nur am Zähler. Der Nenner hat seine
eigene Kette über `silver/tract` zu den TIGER- und ACS-Läufen, und die drei
Crosswalks hängen mit ihrer SHA-256 daran. Das ist richtig so — eine geänderte
Zuordnungstabelle verschiebt die Zahlen genauso wie neue Daten.

**Wächter.** 13 Tests in `tests/test_eine_zahl.py`, alle gegen die gebauten
Daten statt gegen Konstanten: die Formelzeile muss aufgehen, die
`geo_status`-Tabelle muss sich auf die Gesamtzahl summieren, jeder im
Dokument genannte Lauf und jeder Abdruck muss im Manifest vorkommen, und
`JH100028` muss weiterhin genau zwei Zeilen haben. Sechs eingebaute
Falschzahlen fielen durch; die siebte zunächst nicht — die Prüfung des Zählers
hing an der Zahlenmenge des ganzen Dokuments statt an der Formelzeile. Das ist
jetzt verankert.

**Der Fehler, den der Wächter sofort fand.** Beim Umbau von Stufe 4 war
Detroits Fallzahl 80'229 aus dem Text gefallen. Der Test schlug beim ersten
Lauf an — genau der Fall, für den er da ist.

**Zahlen.** 946 → **959 Tests**. Zwölf Dokumente in `docs/`.

---

## 14.09.2026 · Zwei Architekturbilder, aus dem Code erzeugt (#87)

**Was.** [`docs/architektur.md`](architektur.md) zeigt den Aufbau in zwei
Bildern und führt einen Lesepfad: sechs Stellen, rund 400 Zeilen, in der
Reihenfolge, in der sie sich erklären. Beide Bilder erzeugt
`tools/build_architekturbilder.py` aus dem AST und aus
`orchestration.run_all.STUFEN`.

**Warum.** Konzept 5.3 führte unter *Data Architecture* wochenlang *„kein
Diagramm der Abhängigkeitskanten"* als Lücke. Die ist damit geschlossen — und
zwar so, dass sie nicht wiederkommt: Ein gezeichnetes Bild wäre am Tag darauf
falsch, ein erzeugtes nicht.

**Der Befund, der die Aufgabe verschoben hat.** Das Projekt hat **mehr
Erklärung als Code**: rund 11'600 Zeilen Prosa (294 Docstrings, 475
Test-Docstrings, elf Dokumente) gegen 10'569 Zeilen Produktionscode. Es fehlte
also kein Text, sondern ein Weg hinein.

**Warum nur drei von neunzehn Pfeilen gezeichnet sind.** Sechzehn Kanten
zeigen auf `manifeste` und `storage`; alle zu zeichnen ergibt ein Knäuel, in
dem die drei übrigen untergehen. Die Fundamente stehen als Band darunter, die
Bildunterschrift nennt genau, wer sie benutzt. Dasselbe in lesbar, nicht
weniger.

**Die Pointe der beiden Bilder.** Im Importgraph fehlt eine Kante von
`silver_pipeline` zu `chicago_pipeline`, im Datenfluss steht sie. Kein
Widerspruch: **Die Schichten hängen an Dateien, nicht aneinander.** Silver
liest Chicagos Bronze-Läufe über die Ablage, nicht über einen Import — deshalb
erzwingt eine dritte Stadt keine Änderung an Silver, und deshalb hat der
Storage-Umbau die Pipelines nicht angefasst.

**Wächter.** Acht Tests: ein zweiter Lauf liefert dieselben Dateien, das SVG
ist wohlgeformt und hat eine Beschreibung, jedes Paket steht im Bild, die
genannten Zahlen stimmen — und der **Importgraph hat keine Zyklen**. Das
letzte ist eine Aussage über die Architektur, nicht über die Zeichnung:
`manifeste` hängt an nichts, `storage` nur an `manifeste`.

**Zahlen.** 938 → **946 Tests**.

---

## 14.09.2026 · Artans schmale Typen, im Code statt im Dokument (#86)

**Was.** Die neun Spalten, die Artan am 14.9. im Feldkatalog schmaler
eingetragen hatte, sind jetzt im Code schmal — und damit in den Daten:

| Spalte | vorher | jetzt |
| --- | --- | --- |
| `dim_date.year`, `.day_of_year` | `BIGINT` | `SMALLINT` |
| `dim_date.month`, `.quarter`, `.day_of_month`, `.day_of_week` | `BIGINT` | `TINYINT` |
| `fact_offense.hour_of_day` | `BIGINT` | `TINYINT` |
| `median_household_income_usd`, `population_below_poverty` | `BIGINT` | `INTEGER` |

**Warum es im Code stehen muss.** `docs/feldkatalog.md` wird erzeugt; eine
Handänderung ist beim nächsten Werkzeuglauf weg (#84). Erst der `CAST` in
`dim_date_query`, `fact_offense_query` und `build_tract` macht die Aussage
wahr — danach schreibt das Werkzeug sie von selbst.

**Und der Beweis, dass genau das der Unterschied ist.** Die Handänderung
hatte `median_household_income_usd` nur in `gold/dim_tract` umgestellt, nicht
in `silver/tract` — obwohl Gold den Wert von dort übernimmt. Zwei Zeilen für
dieselbe Spalte, zwei Typen. Im Code gesetzt, stimmen beide zwangsläufig
überein.

**Geprüft, dass nichts verlorenging.** `TRY_CAST` liefert bei Überlauf
stillschweigend `NULL`; deshalb vorher gemessen und nachher gezählt:
6'102 Einkommen (Maximum 250'001), 6'282 Armutszahlen (Maximum 5'819),
344'617 Tatstunden (0 bis 23) — alle unverändert, alle weit unter der Grenze.
Die **Einwohnerzahl bleibt bewusst `BIGINT`**: Sie ist der Nenner jeder Rate,
und dort ist Vorsicht mehr wert als vier Byte.

**Vertragsversionen.** `silver/tract` und `gold/*` steigen auf **2** — das
Schema ist Teil dessen, was eine Tabelle zusagt, und wer sie mit `pyarrow`
liest, bekommt jetzt einen anderen Typ. Die Zahlen selbst ändern sich nicht:
die Drift-Messung bleibt auf 0,00 in allen elf Grössen.

**Wächter.** Drei Tests halten die Typen fest, damit sie nicht still wieder
breit werden.

**Zahlen.** 935 → **938 Tests**.

---

## 14.09.2026 · Korn wird Granularität (#85)

**Was.** Der Begriff *Korn* heisst im ganzen Projekt jetzt **Granularität**,
die beiden Prägungen *Tatkorn* und *Fallkorn* heissen **Tatebene** und
**Fallebene**. 160 Stellen in 29 Dateien: Code, Tests, Notebooks, README und
die Abgabedokumente.

**Warum.** „Korn" ist eine wörtliche Übersetzung von Kimballs *grain*; im
deutschen Data Engineering ist **Granularität** der eingeführte Begriff, und
„Korn" lässt zuerst an Getreide denken. Christian hat es angemerkt, und er
hat recht: In einer Abgabe liest sich das als Übersetzungsfehler.

**Warum nicht „Tatgranularität".** Korrekt, aber unlesbar. *Ebene* ist in der
Dimensionsmodellierung eingeführt und trägt dieselbe Unterscheidung in zwei
Silben. Wo es um den Begriff geht, steht *Granularität*; wo es um die beiden
konkreten geht, *Tat-* und *Fallebene*.

**Was dabei zu beachten war.** *Korn* ist sächlich, *Granularität* weiblich —
die Artikel mussten mit (`das Korn` → `die Granularität`). Und mehrere Muster
im Code lesen Dokumenttext: `orchestration.drift` sucht `\| Fallkorn.*?` im
Kopf von `AENDERUNGEN.md`, `test_abgabedokumente` sucht
`\| Delikte \(Tatkorn\)` im Konzept. Text und Muster wurden zusammen
geändert, sonst hätte die Drift-Messung ins Leere gegriffen.

**Nicht angefasst: die datierten Einträge in dieser Datei.** Das Projekt hält
in `test_aenderungen` fest, dass sie Vergangenes beschreiben und sich nicht
ändern sollen. Nur der Kopf ist nachgezogen. Ebenso unberührt bleiben die
Manifest-Schlüssel — dort heisst es weiterhin `grain`, englisch wie alle
anderen Schlüssel.

**Mitgezogen.** `docs/bilder/korn.svg` → `granularitaet.svg`, die Testnamen,
der Schlüssel `detroit_rate_fallkorn` in `drift.py`.

**Zahlen.** 935 Tests, unverändert — eine Begriffsumstellung ändert keine Zahl.

---

## 14.09.2026 · Die Analyseplattform durchdacht — und der Würfel zum zweiten Mal verworfen (#83)

**Was.** [`ausblick.md`](ausblick.md) hat einen Abschnitt 5: die
Analyseplattform für LN2. Messwerte, die Bewertung von Streamlit, ClickHouse
und OpenSearch, zwei Bauarten — und drei Entwurfsgrundsätze, die aus diesem
Projekt kommen und nicht aus einem Dashboard-Lehrbuch.

**Die Zahl, an der alles hängt.** DuckDB beantwortet die typischen
Dashboard-Abfragen auf der **rohen** Faktentabelle in **2 bis 7
Millisekunden**. Ein Mensch erwartet unter 200 ms. Damit ist die
Werkzeugfrage keine Leistungsfrage: ClickHouse wäre bei 344'617 Zeilen rund
tausendfach überdimensioniert, OpenSearch hat die falsche Form — unsere
Fragen sind Aggregationen über ein Sternschema.

**Ein Vorschlag, den Christian zurückgewiesen hat — zu Recht.** Der erste
Entwurf sah eine vorberechnete Datei fürs Dashboard vor. Sein Einwand: *„Dann
können wir genauso gut zurück zum Würfel."* Die Messung gibt ihm recht:

| | Zeilen |
| --- | ---: |
| `fact_offense` | 344'617 |
| Aggregat Tract × Tag × Familie | 296'651 — **86 %** davon |

14 % weniger Zeilen ist keine Aggregation. Die scheinbare Ersparnis kam
daher, dass **Spalten** wegfielen — und genau das leistet Parquet von selbst:
Eine Kartenabfrage liest vier Spalten, 0,69 MB, **5 % der Datei**. Das
Aggregat wäre grösser gewesen als die kostenlose Spaltenauswahl und hätte
dafür jede Dimension weggeworfen, die niemand vorab festgelegt hat.

**Das Format ist der Würfel** — einer, den niemand vorher entscheiden muss.
Und der Wunsch nach dynamischen Filtern ist das stärkste Argument dagegen,
nicht dafür. Dieselbe Messung hatte `fact_tract_month` und `fact_city_day`
schon einmal verworfen; Konzept 5.2 führt es als Zusage.

**Wächter.** `tests/test_ausblick.py` prüft, dass kein Aggregat in Gold
liegt und die Serving-Schicht keine Parquet-Datei **schreibt**. Zwei
Fehlversuche beim Bauen des Wächters sind lehrreich: Ein Prüfen auf
`GROUP BY` schlug an — das steht in den Docstrings als Abfragebeispiel; ein
Prüfen auf `.parquet` ebenso — das ist die Konstante zum **Lesen**.

**Zur Begriffswahl.** Der neue Abschnitt sagt **Granularität**, wo das
übrige Projekt *Korn* sagt. „Granularität" ist der eingeführte deutsche
Begriff für Kimballs *grain*. Die Umstellung betrifft 128 Stellen in 27
Dateien und steht als eigener Punkt in der Reihenfolge.

**Zahlen.** 932 → **935 Tests**.

---

## 14.09.2026 · Zwei Dinge unter einem Namen, entflochten (#82)

**Was.** Die Zuordnung der beiden Studienstädte zu ihren FIPS-Ortsnummern
stand **zweimal** im Projekt, unter demselben Namen `STUDIENSTAEDTE` und mit
**verschiedenen Werten**: in `silver_pipeline/build_place.py` gross
(`"Chicago"`), in `gold_pipeline/__init__.py` klein (`"chicago"`). Jetzt steht
die Tatsache einmal in `silver_pipeline`, und Gold leitet daraus
`STADT_SCHLUESSEL` ab. Punkt 4 der Reihenfolge in
[`ausblick.md`](ausblick.md).

**Warum die Werte verschieden waren — und beide richtig.** Silver prüft gegen
TIGERs `name`-Feld, und dort steht *Chicago*; das ist der Nachweis, dass eine
GEOID auf den Ort zeigt, den wir meinen. Gold braucht denselben Ort als
Verbundschlüssel, und die Spalte `city` in `crime_offense` ist
kleingeschrieben. Zwei verschiedene Dinge — nur hiessen sie gleich.

**Was daran gefährlich war.** Wer die falsche importierte, bekam
stillschweigend etwas anderes. Und beim Eintragen einer dritten Stadt wäre sie
an einer der beiden Stellen gelandet: Silver hätte sie geprüft und Gold nicht
zugeordnet, oder umgekehrt — beides ohne Fehlermeldung, mit einer Rate ohne
Nenner als Ergebnis.

**Eine dritte Stadt wird jetzt an genau einer Stelle eingetragen.** Ein Test
hält die Ableitung fest, ein zweiter, dass die Definition nur noch einmal
vorkommt.

**Zahlen.** 931 → **932 Tests**.

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
| #81 | `docs/chicago-ingestion.html` entfernt — eine dritte, unverlinkte Beschreibung derselben Pipeline | veraltet (kein Storage-Backend, keine `contract_version`, 259 270 statt 259 272 Zeilen) und nirgends verlinkt; der Inhalt steht im Modul-Docstring, in Notebook 02, README 2.1 und Konzept 6 |
| #84 | `docs/feldkatalog.md` neu erzeugt, nachdem er von Hand bearbeitet worden war | kein inhaltlicher Entscheid, sondern die Wiederherstellung des erzeugten Stands; die Begründung steht als Anmerkung unter *Vertragsversionen* |
| #68 | `orchestration.drift` las den Fingerabdruck unter einem falschen Schlüssel (`fingerprint` statt `input_fingerprint`) — der erste Lauf zeigte `None` | Fehlerbehebung mit Test, ändert keine Aussage |
| #104 | der Übergang in `zaehlperspektiven.md` 3 neu gefasst — „Auch die 28 beweisen weniger…“ sagte nicht, was gemeint war | Formulierung, keine geänderte Aussage; die Aussage selbst war schon richtig, nur unlesbar neben dem Absatz davor. Christian hat nachgefragt |
| #112 | `datenhistorie.md` 8: die vier offenen Punkte aus dem Chat für Freitag notiert (Chicagos Beschreibung aus beiden IUCR-Hälften, die 20/16 `ambiguous`-Zuordnungen, H1/H6, „Anklage“); §5 heisst „Fünf“ statt „Vier“ | Agenda, keine geänderte Aussage; die Zahlen stehen bereits in `zaehlperspektiven.md` und sind dort bewacht. Christian hat entschieden, die Beschreibungsfrage offen zu lassen |
| #113 | README 2.5: der Release-Ablauf Schritt für Schritt, je Rolle (wer baut, wer liest); `tools/build_referenz.py` übergibt jedes Modul ausdrücklich an pdoc, weil ein Paket mit `__all__` sonst keine Unterseiten bekommt - `storage.backend`, `storage.config` und `storage.release` hatten bis dahin keine | Bedienungsanleitung und Werkzeug, keine geänderte Aussage. Christian hat gefragt, „wo ist das beschrieben“ |
| #117 | die gemessene Drift festgehalten (Christians Entscheidung: nicht nachziehen), README 1.4 erklärt die roten `referenzstand`-Wächter, und zwei Tests räumen wieder auf, statt Feldkatalog und SVG im Arbeitsbaum zu hinterlassen | Dokumentation und ein Testfehler; die Sache selbst steht im Eintrag zu #116, wo sie aufgefallen ist |

