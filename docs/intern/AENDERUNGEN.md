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
| Tests | **1'678** |
| `silver/crime_offense` | 348'329 Zeilen (Detroit: eine Anklage) |
| `gold/fact_offense` | **345'091** Zeilen (eine Tat) |
| Chicago | 251'517 Delikte · 2'661'953 Einwohner · **94,5** je 1'000 |
| Detroit | 84'761 Delikte · 638'635 Einwohner · **132,7** je 1'000 |
| Fallebene (`counts_case`) | Chicago 259'614 · Detroit 80'230 Fälle; Detroit **124,6** je 1'000 |

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
| `bronze/city=detroit` | **3** | 18.09.2026 | Abfragefenster in **Detroiter Ortszeit** statt UTC (Konzept 8.6). Version 1 zog es in UTC — jene Läufe enthielten 66 Fälle aus 2023 und vermissten 56 vom Jahresende 2024. Version 3: **Delta über `updated_at` mit 14 Tagen Rückgriff** innerhalb des Tatjahrgangs, Zeilen ohne Stempel immer dabei — der erste Lauf bleibt ein Vollschnappschuss |
| `bronze/dataset=tiger_tract`, `bronze/dataset=tiger_place` | 1 | 14.09.2026 | Vintage-Archiv je Bundesstaat, Geometrie als WKB in EPSG:4269, Feld-Allowlist mit `_extra` |
| `bronze/dataset=acs5_tract` | 1 | 14.09.2026 | fünf Variablen je Tract, Fehlwert `-666666666` bleibt unverändert stehen |
| `bronze/dataset=noaa_ghcnd` | 1 | 14.09.2026 | Vollschnappschuss je Station, bedingter Abruf über ETag, Mindestabstand sieben Tage |
| `silver/tract` | **2** | 14.09.2026 | ein Census Tract je Zeile, TIGER und ACS über einen vollen äusseren Join. Version 2: `median_household_income_usd` und `population_below_poverty` als `INTEGER` statt `BIGINT` — die Einwohnerzahl bleibt `BIGINT`, sie ist der Nenner jeder Rate |
| `silver/place` | 1 | 14.09.2026 | ein Ort je Zeile, Geometrie für die Stadtgrenze |
| `silver/weather_day` | 1 | 14.09.2026 | eine Stadt an einem Tag, eine Station je Stadt |
| `silver/crime_offense` | **3** | 19.09.2026 | eine Anklage je Zeile; `counts` markiert die Tat, `counts_case` den Fall; NIBRS als gemeinsame Achse. Version 2: `local_time_ambiguous` und `local_time_nonexistent` weisen die beiden Zeitzonen-Randfälle je Zeile aus. Version 3: **`source_offense_description` trägt für Chicago beide IUCR-Hälften** (`primary_type: description`) — die zweite allein war bei 23,7 % der Zeilen mehrdeutig |
| `silver/source_change` | **3** | 03.10.2026 | Unterschied zwischen aufeinanderfolgenden **Vollabzügen** je Quelle, eine Zeile je geändertem Feld; `ESRI_OID` und reine Leerzeichen ausgenommen, Zeitstempel als `beruehrt` statt als Inhaltsänderung. Version 2 ergänzte die **Datierung aus den Deltas**: `zuerst_gesehen_in`, `zuerst_gesehen_am` und `datierung` mit `delta` / `kein_delta` / `nicht_datierbar`. Gefunden wird weiter nur zwischen Vollabzügen — aus einem Delta liesse sich *verschwunden* nicht von *ruhig* unterscheiden. Version 3: Die Datierung **klebt** — sie nennt den besten je bestimmten Befund, nicht den heutigen, sonst löschte das Aufräumen der Deltas sie wieder |
| `gold/*` | **7** | 03.10.2026 | Sternschema, eine Zeile je Tat, Mehrheitsregel für die Stadtzuordnung. Version 2: `dim_date` mit `SMALLINT`/`TINYINT` statt `BIGINT`, `fact_offense.hour_of_day` als `TINYINT`. Version 3: `dim_city_day` führt `precipitation_trace` und `snowfall_trace` mit — ein Messwert 0 mit Spurenflag ist nicht trocken. Version 4: `fact_offense` führt `local_time_ambiguous` mit, weil `hour_of_day` dort gerechnet wird. Version 5: `source_offense_description` übernimmt Silvers Vertrag 3 — für Chicago beide IUCR-Hälften | Version 6: Die ACS-Masse liegen **je Vintage** in der neuen Tabelle `dim_tract_acs` (`population`, `median_household_income_usd`, `poverty_rate`); `dim_tract` behält die Stadtzuordnung und nennt mit `reference_vintage`, aus welchem Jahrgang sie kommt; `fact_offense` trägt `population_vintage` und sagt damit je Zeile, welcher Nenner für sie gilt. Eine Tabelle mit einer Zeile je Tract konnte nur eine Einwohnerzahl tragen — über mehrere Jahrgänge hätte jede Tat denselben Nenner bekommen, auch die von 2021 Version 7: `dim_date` trägt `year_is_complete` — ob der Jahrgang dieses Tages ganz in den Daten liegt. Ein Teiljahr darf nicht in einen Jahresvergleich geraten: 2026 hat am 3.10. neun Monate, und neun gegen zwölf gestellt ergeben einen Rückgang, den es nicht gibt. Dazu im Manifest von `fact_offense` der Nachweis `year_coverage` je Jahrgang, mit `days_with_offenses` gegen `days_in_year` — denn eine Lücke **innerhalb** des Jahres sieht man an der Spalte nicht
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

## 04.10.2026 · Der Platzbedarf wird gemessen und je Quelle hochgerechnet, nicht mit einem Faktor geschätzt (#130)

Der Speicherbedarf des Mehrjahreslaufs stand als **ein Faktor** in den
Planungsdokumenten: 1'874'417 Zeilen gegen 348'341 sind das 5,38-Fache,
aufgerundet 5,5 — und dieser Faktor wurde auf ganz `data/` angewandt. Daran war
dreierlei falsch, und jedes einzeln:

1. **Ein Zeilenverhältnis ist kein Byteverhältnis.** Gemessen kostet Detroits
   Zeile in Bronze **189,0 Bytes**, Chicagos **64,4** — fast das Dreifache, weil
   Detroit mehr und längere Textfelder trägt.
2. **Nicht alles wächst mit den Jahren.** NOAA liefert mit GHCN-Daily immer die
   ganze Reihe einer Station; sechs Jahrgänge kosten dort **nichts** zusätzlich.
   Census wächst nicht mit den Jahren, sondern mit den **Vintages**, und
   2021–2026 braucht **vier**, nicht sechs: Für 2025 und 2026 gibt es kein
   ACS-5-Jahres-Vintage, sie borgen das von 2024.
3. **Die Basis war der Bestand, nicht ein Jahrgang.** `data/` hielt am
   4.10.2026 acht Chicago-Läufe und sechs Release-Stände. Den Faktor darauf
   anzuwenden rechnet das Anhäufen mit hoch — dieselbe Falle wie „den Bestand
   aus Bronze lesen", diesmal in der Basis einer Hochrechnung. Basis je
   Jahrgang ist deshalb der **grösste Lauf je Quelle und Vintage**: Der
   grösste über alle Vintages hinweg hätte für Census die Kosten *eines*
   Vintages mit der Zahl *aller* geteilt.

**Aus dem einen Faktor sind vier Regeln geworden** (`orchestration.platzbedarf`):

| Regel | wie sie rechnet | 2021–2026 |
| --- | --- | ---: |
| Taten | Zeilen je Jahr × Bytes je Zeile, **je Stadt** | 498,8 MB |
| Census | distinkte ACS-Vintages × Kosten je Vintage | 375,9 MB |
| konstant | wächst nicht mit den Jahren (NOAA, Marken, Zeiger) | 24,9 MB |
| Releases | 8 Stände × Grösse eines **hochgerechneten** Standes | 1'831,1 MB |

**Das Ergebnis: 2,73 GB statt 3,2 oder 3,5 GB.** Die beiden alten Zahlen standen
nebeneinander in `addendum.md` und FR-52 und widersprachen sich; beide sind
ersetzt und verweisen jetzt auf das erzeugte Dokument. Für FR-52 ändert sich die
Richtung nicht — ohne `releases/` sind es 0,90 GB, und Moodles Grenze von 1 GB
bleibt die Hürde.

**Die Ausgangsbasis war ebenfalls falsch.** `architektur-ist-und-ziel.md` nannte
für `releases/` **121 MB**, gemessen sind **254,1 MB** — mehr als das Doppelte.
Dieselbe Tabelle stand ein zweites Mal als SVG-Text in
`architektur-einseiter.html`, und **dort stand sie unbewacht**: Der Sammler in
`tests/test_dokumentzahlen.py` sieht nur tausendergetrennte Ganzzahlen und damit
keine einzige MB-Angabe. Beide Tabellen sind richtiggestellt:

| Schicht | war | ist |
| --- | ---: | ---: |
| raw | 130 MB | **143,5 MB** |
| bronze | 124 MB | **162,2 MB** |
| silver | 47 MB | **49,5 MB** |
| gold | 15 MB | **15,3 MB** |
| serving | 0,9 MB | 0,9 MB |
| releases | 121 MB | **254,1 MB** |

**Bewacht wird das jetzt in beiden Dokumenten.**
`tests/test_platzbedarf_dokumente.py` hält die Schichtentabelle und die Grösse
je Release gegen eine frische Messung — mit einem MB/GB-Muster statt des
Ganzzahl-Sammlers, und mit Datei, Zeile und gemessener Zahl in der Meldung. Eine
Stelle allein nachzuziehen genügt nicht; das ist die Lehre aus den acht
überholten Aussagen vom 20.9.

**Die Byte-Summe steht jetzt einmal im Projekt.** `Storage.bytes_unter(prefix)`
ersetzt drei ausgeschriebene Fassungen (`storage/__main__.py`,
`orchestration.aufraeumen`, `tools/build_referenz.py`). Jede war nur im
`local`-Modus richtig, jede zählte `.part`-Verzeichnisse mit, und
`build_referenz.py` teilte durch 1'048'576, wo alle anderen durch 1e6 teilten —
dieselbe Referenz war dort um 4,8 % kleiner als an jeder anderen Stelle. Die neue
Summe nimmt lokal `st_size`, auf S3 `Objekt.size` und zählt im Hybridmodus eine
Datei, die lokal **und** oben liegt, genau einmal. `storage.release` bleibt
unberührt: Seine Summe steht in unveränderlichen Release-Manifesten.

**Dazu die kanonische Schichtenliste.** `storage.SCHICHTEN` nennt die sechs
Schichten in der Reihenfolge der Strecke; `LAUFSCHICHTEN` und
`TABELLENSCHICHTEN` sind Auswahlen daraus. Vorher standen drei einander
widersprechende `SCHICHTEN` im Projekt — `storage/__main__.py` kannte raw und
bronze, `serving/build_analysis_db.py` und `tools/build_feldkatalog.py` silver,
gold und serving. Keine war falsch, aber keine liess sich fragen, *welche*
Schichten es gibt.

**Ändern sich dadurch Löschentscheidungen? Nein — nachgemessen.**
`python -m orchestration.aufraeumen` liefert vor und nach dem Umbau **byteweise
dieselbe Ausgabe**, und ein Test hält fest, dass `entscheide` an keiner
Byte-Summe hängt: Ein Lauf mit 0 Bytes bekommt denselben Grund wie einer mit
vielen.

**Die gemessenen Zeilen je Jahrgang liegen unter `config/`.**
`config/zeilen_je_jahrgang.csv` trägt Stadt, Jahr, Zeilen, Messdatum und
Adresse — am 3.10.2026 an beiden APIs gemessen. Sie sind Fremddaten und keine
Konstante im Code; fehlt ein Jahr, bricht die Hochrechnung ab und nennt es,
statt es stillschweigend zu überspringen. Die Datei liegt mit LF, und `config/`
bekommt dafür **keine** `eol`-Regel: Die Crosswalks daneben liegen absichtlich
mit CRLF, und drei Tests vergleichen diese Bytes.

**Was bewusst nicht in dieser Story steckt:** der Mehrjahreslauf selbst. Dies
baut das Messgerät, die Hochrechnung und die Wächter — ohne Netz und ohne
`CENSUS_API_KEY`. Gemessen wird danach, und dieser Schritt erledigt den
ausstehenden Gold-Neubau mit.

**Neu:** `src/crime/orchestration/platzbedarf.py`,
`tools/build_platzbedarf.py`, `docs/intern/platzbedarf.md` (erzeugt),
`config/zeilen_je_jahrgang.csv`, `tests/orchestration/test_platzbedarf.py`,
`tests/test_platzbedarf_dokumente.py`.

**Zahlen.** 1'606 → **1'678 Tests**, Standardlauf **1'579**, Referenzwächter
82 → **99**. Der Importgraph hat mit `orchestration.platzbedarf` eine Kante
mehr: 26 → **27**, davon zehn gezeichnet; `docs/architektur.md` und die
erzeugten Bilder sind nachgezogen.

## 04.10.2026 · Detroits Fallanteil fällt — Gold sagt dasselbe, nur entdoppelt (#131)

Die Zurückstellung aus der FR-38-Review.
`test_abdeckung_der_faelle_ist_ausgewiesen` bildete `gedeckt / gesamt` aus den
Zahlen von `detroit_codes()` und nannte das Ergebnis „Abdeckung der Fälle", mit
der Schwelle 0,999. `detroit_codes()` liest aber **alle** Läufe unter
`bronze/city=detroit`.

**Gemessen am 4.10.2026: 8 Läufe, 452'980 Zeilen für 253'838 verschiedene
`ESRI_OID` — Faktor 1,78.** Der Anteil war damit nach Ingestionshäufigkeit
gewichtet und nicht nach Fällen. Und 452'980 ist genau die Zahl, die
`AGENTS.md` unter *Known pitfalls* als Beispiel führt: *„Den Bestand aus Bronze
zu lesen heisst, alle Läufe zu lesen: 452'980 Zeilen für einen Jahrgang von
88'686, und das Ergebnis sah plausibel aus."* Der Test ist in die dokumentierte
Falle getreten, und zwar mit derselben Zahl.

**Die Aussage ist nicht verloren.** Gold liefert sie entdoppelt: je Stadt in
`coverage_percent_by_city` (Detroit `unmapped` 0,0, `exact` 95,1748) und seit
FR-38 je Jahrgang in `mapping_by_year`. Die Schwelle, die der Test behauptete,
erzwingt `pruefe_gate` über `GATE_HOECHSTENS = {"unmapped": 1.0}` sogar **je
Stadt im Bau** — nicht bloss in einem Test. Der Ersatz ist also strenger als
das Entfallene.

**Dasselbe war Chicago bei FR-38 schon erspart worden**: Dort wurde der Anteil
nie gebaut, und an seiner Stelle steht ein Kommentar mit demselben Argument.
Detroits Fassung war die ältere. Jetzt sagen beide Seiten dasselbe — und
Chicagos Kommentar ist nachgezogen, weil er auf Detroits Rechnung als
bestehenden Defekt verwies.

**Ein Docstring hat sich selbst widersprochen.** `detroit_codes()` sagte „Die
MICR-Codes des **juengsten** Detroit-Bronze-Laufs", während die Funktion immer
schon alle las. Für ihren Zweck ist das richtig — gefragt ist die *Menge* der
vorkommenden Codes, und ein Code, der nur in einem älteren Delta steht, muss
genauso zugeordnet sein. Der Docstring sagt das jetzt, samt dem Hinweis, dass
die Zahlen daneben Grössenordnungen für die Fehlermeldung sind und keine
Statistik. `test_jeder_code_der_daten_steht_in_der_tabelle` bleibt unverändert;
er fragt nach der Menge und ist über alle Läufe richtig.

**Und eine Zahl, die seit dem 3.10. offen war, ist jetzt gemessen.** `README.md`
und `docs/architektur-ist-und-ziel.md` sagten „1'176 der 1'203 Tests" für einen
frischen Klon — zweimal zurückgestellt, weil die einzige Messmethode schien,
`data/` beiseitezuschieben. Die Review hat den besseren Weg gezeigt: eine
**Kopie** des Baums ohne `data/`, nur mit den vier versionierten `.gitkeep`.
Gemessen am 4.10.2026 nach dem Rebase auf #130: **1'550 bestanden, 29
übersprungen** von 1'579. Beide Stellen stehen jetzt richtig, und `README.md`
sagt statt „75 abgewählte" die gemessenen 99 — die Zahl stand vier Zeilen neben
der Gesamtzahl und widersprach ihr.

**Zahlen.** 1'679 → **1'678 Tests** — einer weniger, nicht mehr. Standardlauf
1'579, Referenzwächter unverändert 99. Kein Vertragssprung, keine Datei in
`config/` angefasst. Die Zahlen sind die nach dem Rebase auf #130; vor dem
Rebase stand hier 1'605 von 1'523, weil der Branch noch von `147aae1` abzweigte.

## 04.10.2026 · Releases werden aufgeräumt: gepinnt plus die letzten acht, lokal und auf SeaweedFS (#129)

Releases wurden bis hierher nur angehäuft. `orchestration.aufraeumen` kannte das
Wort nicht — es räumte Raw- und Bronze-Läufe —, und `storage/release.py` sagte im
Docstring ausdrücklich: *„Was bewusst nicht hier steht: Loeschen. Releases werden
aufgehoben, bis eine Regel dafuer entschieden ist."*

**Gemessen am 4.10.2026: 8 Releases lokal (323 MB) und 49 auf SeaweedFS (1'085
Dateien, rund 2,1 GB).** Releases waren damit 1'085 von 1'464 Objekten im
Bucket — **74 Prozent**, und nichts verwaltete sie.

**Die Regel ist die, die `docs/intern/datenhistorie.md` 5.5 empfiehlt: gepinnt
plus die letzten n.** Vier Gründe, jüngstes Release zuerst:

| Grund | was ihn auslöst |
| --- | --- |
| `Referenzstand` | das Release steht in `config/referenzstand.csv` — **dasselbe** Register und dieselbe Lesefunktion wie bei Läufen |
| `aktueller Zeiger` | `releases/AKTUELL.json` nennt es; es bleibt immer, auch ausserhalb der Reihe |
| `unter den letzten 8` | es liegt unter den acht jüngsten |
| `ENTBEHRLICH` | alles andere |

**n = 8, und das überholt E6 im PRD zum LN2.** Dort stand *fünf*, als
*entschieden* geführt und ohne Begründung. §5.5 begründet acht — zwei Monate
wöchentlicher Releases. Zwei Zahlen für dieselbe Regel sind eine, die veraltet,
also gilt die begründete. E6 und die Rechnung in NFR-7 (1,1 → 1,8 GB bei sechs
Jahrgängen) sind nachgezogen, mit einem Vermerk im Dokument, weil es
`status: final` trägt. §5.5s offene Frage 5 ist damit beantwortet.

**Warum das aktuelle Release eine eigene Regel ist.** Nichts im Projekt sortiert
Releases, um das neueste zu finden — alles geht über `AKTUELL.json`: ClickHouse,
Elasticsearch, Kibana, `serving.pruefe_stand` und `tools.build_einstieg`. Ein
altes Release zu entfernen ist deshalb folgenlos; das aktuelle zu entfernen
bricht fünf Verbraucher auf einmal. Fehlt der Zeiger, sagt der Bericht das und
läuft weiter.

**Zwei Schalter, nicht einer.** `--loeschen` wirkt wie bisher **nur lokal**; erst
`--auch-fern` dazu räumt SeaweedFS. Läufe liegen lokal, Releases liegen oben als
der gemeinsame Stand — ein Löschen dort betrifft jede Maschine, die vom Bucket
liest. Rund 900 Objekte aus dem geteilten Speicher zu entfernen soll zwei
bewusste Entscheidungen kosten, nicht eine; dieselbe Haltung wie `publish_table`
mit `erzwingen=True`. Der Trockenlauf bleibt die Vorgabe, und `--auch-fern`
allein bleibt einer und sagt das.

**Das Protokoll `S3Client` hat jetzt `delete`.** Es kannte `head`, `get`, `put`
und `list`. Dazu auf `Storage` die Methode `entferne_oben(prefix)`: Sie zählt
über `list` auf, statt Schlüssel zu raten, schliesst den Präfix mit `/` ab —
sonst träfe `release=2026-10-03` auch `release=2026-10-03T19-53-12Z` — und lehnt
einen leeren Präfix ab, weil das der ganze Bucket wäre. Ein fehlgeschlagenes
`delete` bricht ab und lässt den Rest stehen; S3 behandelt das Löschen eines
fehlenden Schlüssels nicht als Fehler, also ist ein zweiter Lauf wiederholbar.
**Damit das stimmt, geht `release.json` zuletzt weg** — das Spiegelbild von
„`release.json` geht zuletzt hoch" in `release.py`. Sortiert liegt es mitten im
Präfix (`gold/` < `release.json` < `serving/`), und `release.liste` erkennt ein
Release *nur* an einem Schlüssel, der darauf endet: Wäre es zuerst weg, machte
ein Abbruch das Release unsichtbar und die 26,5 MB grosse `analyse.duckdb`
unauffindbar. `releases/AKTUELL.json` liegt ausserhalb jedes Release-Präfixes
und wird nie angefasst. **Für Läufe und Tabellen gilt das nicht** — die bleiben
unveränderlich, `erstelle` lehnt eine bestehende Kennung weiterhin ab.

**Der Referenzstand ist gepinnt, vor dem ersten Löschlauf.**
`release=2026-09-17T19-42-24Z` steht mit `grund=referenzstand` im Register;
`architektur-ist-und-ziel.md` sagt, 82 Wächter halten die Abgabedokumente gegen
genau diesen Bau. Er ist das älteste der 49 Releases und wäre ohne den Eintrag
entbehrlich gewesen. Die neun `grund=LN1`-Einträge sind unberührt. Die
Release-Kennung steht in der Spalte `run_id` — der Spaltenname wird dadurch
unscharf, und das ist der Preis dafür, dass es **ein** Register gibt und nicht
zwei. Wer später eine Typspalte will, findet alle Einträge an einem Ort.

**Gemeldet wird, was wirklich wegging** — getrennt nach Ort, nicht aus der
Entscheidungsliste. Ein Release, das nur oben liegt, hat kein lokales
Verzeichnis; `--loeschen` ohne `--auch-fern` entfernt dafür nichts, und die
Ausgabe sagt beides: „0 Release(s) lokal gelöscht, 0.0 MB frei" und „Auf
SeaweedFS unverändert: 2 entbehrliche Release(s), …". Und `--auch-fern` wird
**vor** dem ersten Löschen abgelehnt, wenn die Ablage kein S3 kennt —
`STORAGE_BACKEND=local` ist die Vorgabe, und `loesche_releases` nimmt das lokale
Verzeichnis weg, bevor es nach oben greift.

**`storage/release.py` sagt nicht mehr, dass es die Regel nicht gibt.** Der
Docstring verneinte sie ausdrücklich und rechnete dazu „ein Jahr wöchentlicher
Releases ist unter einem Gigabyte" — bei 42,3 MB je Release sind es 2,2 GB.
Beide Sätze sind nachgezogen, mit Verweis auf `orchestration.aufraeumen`.
Dasselbe in `ausblick.md` 6a („Releases werden aufgehoben, bis diese Regel
entschieden ist") und in `storage-architektur.md`, wo `entferne_oben` in der
Methodenliste fehlte.

**Nicht ausgeführt: der scharfe Lauf.** Diese Änderung baut die Regel und weist
sie im Trockenlauf und mit Tests nach. Der Trockenlauf meldet heute *„49
Releases, 40 entbehrlich, 1'676,8 MB frei"*. Dass die rund 900 Objekte
tatsächlich aus dem geteilten Speicher verschwinden, ist eine eigene
Entscheidung und gehört Christian — wie das Nachladen der Stores. Serverseitige
Lifecycle-Regeln am Bucket bleiben ausdrücklich aussen vor: Eine Ablaufregel am
Bucket kann die gepinnten Stände nicht kennen.

**Vier Dokumente sagten etwas, das nicht mehr stimmt** — und sagen es jetzt
richtig: `storage-architektur.md` 9 (*„räumt ausschliesslich lokal auf"*),
README 2.5 (*„räumt weiterhin nur lokal auf"*), `ausblick.md` (*„`aufraeumen`
räumt bisher nur lokal"*) und README 2.4, das die Release-Regel samt beiden
Schaltern jetzt beschreibt. Dazu ein Wächter über README,
`storage-architektur.md` und `datenhistorie.md`: Er hält `die letzten acht`
gegen `aufraeumen.RELEASES_N` und fällt, wenn ein Dokument eine andere Zahl
nennt oder `--auch-fern` nicht erwähnt. Ohne ihn veraltet das unbewachte
Dokument genauso. **Das PRD ist bewusst nicht dabei:** Es liegt unter
`_bmad-output/` und ist ungetrackt — ein Wächter darüber wäre in jedem frischen
Klon ein `FileNotFoundError`. Es ist von Hand nachgezogen.

**Kein Vertragssprung.** Es ändert sich nichts an Bedeutung, Granularität,
Regeln oder Spalten einer Tabelle. Was sich ändert, ist, wie lange ein Release
liegt.

**Zahlen.** 1'566 → **1'606 Tests**, Standardlauf **1'524**, Referenzwächter
unverändert 82. 40 neue: 28 für die Release-Regel (jede Zeile der
Entscheidungsmatrix, die beiden Zusagen *ohne `--loeschen` nichts* und *ohne
`--auch-fern` oben nichts*, der Abbruch mitten im Präfix, die Ablehnung von
`--auch-fern` ohne S3, und dass ein nur oben liegendes Release keine freien MB
meldet), 12 für `delete` und `entferne_oben`. `docs/referenz/` neu erzeugt.

## 04.10.2026 · Gold ist byteweise reproduzierbar, weil fact_offense jetzt eine Reihenfolge hat (#128)

Der Befund vom 3.10. war richtig, aber die Ursache falsch benannt. Ich hatte
geschrieben, der Inhalt sei identisch und nur die Parquet-Kodierung weiche ab.
Der Inhalt ist als **Multimenge** identisch — mein Hash hatte ein `ORDER BY` in
der Aggregation und hat damit genau das verdeckt, worum es geht.

**Gemessen am 4.10.2026: 245'760 von 345'091 Zeilen lagen zwischen zwei Läufen
an anderer Position.** 71 Prozent der Tabelle. Die Zeilengruppengrenzen waren
identisch, und fast jede Spalte jeder Gruppe hatte eine andere komprimierte
Grösse — die Signatur vertauschter Zeilen, nicht die einer anderen Kodierung.
Die Dateigrösse schwankte dabei zwischen Aufrufen (14'947'218 bis 15'001'199
Bytes) und war in einem Paar sogar gleich, während die Bytes abwichen: Eine
gleiche Grösse beweist hier nichts.

**Die Ursache ist eine fehlende Klausel.** `fact_offense_query` war die
**einzige** Abfrage der ganzen Strecke ohne `ORDER BY`. Vier Dimensionsabfragen
haben eine — `dim_tract`, `dim_tract_acs`, `dim_date`, `dim_city_day`;
`dim_offense` entsteht gar nicht aus einer Abfrage, sondern aus `CREATE TABLE`
plus `executemany`, und folgt der Codeliste. Alle fünf Dimensionen waren
byteweise stabil, nachgeprüft.
`build_crime_offense.build_query` endet mit `ORDER BY b.city,
b.occurred_at_utc, b.offense_id`, `serving.build_comparison` ebenso. Ohne die
Klausel entscheidet der Hash-Join mit vierzehn Threads, in welcher Reihenfolge
die Zeilen fallen.

Sortiert wird jetzt nach `date`, dann `offense_id`. Der Tag ist die Achse, auf
der am meisten gefiltert wird, also kann die Zeilengruppenstatistik greifen;
die Kennung macht die Ordnung eindeutig. Der sortierte Stand reproduziert sich
exakt bei **15'808'123 Bytes**; gegen die schwankende unsortierte Spanne sind
das **5,4 bis 5,8 Prozent** mehr Platz, bei keiner messbaren Zeit (0,09 gegen
0,08 Sekunden). `ORDER BY offense_id` allein wären rund 7,7 Prozent gewesen.

**Nicht gewählt: `DUCKDB_THREADS=1`.** Das macht die Bytes ebenfalls stabil,
aber nur weil es die Scanreihenfolge erzwingt — es hätte die fehlende
Sortierung maskiert und die Parallelität des ganzen Laufs gekostet. Die
Schraube aus FR-61 bleibt, wofür sie gedacht war: Speicher und Fäden auf einer
geteilten Maschine zu begrenzen.

**Zwei Wächter, und der Byte-Vergleich allein hätte nicht gereicht.** Die
Review hat vorgerechnet, dass ein Vergleich von genau zwei Läufen eine fehlende
Klausel nur sporadisch fängt — nachgemessen **drei von sechs Durchgängen**. Das
ist der Fall aus `AGENTS.md`: „der Wächter war grün und wertlos". Die erste
Fassung dieses Eintrags behauptete „in beide Richtungen geprüft" und ruhte auf
einem einzigen glücklichen Lauf.

Deshalb stehen jetzt zwei Wächter da.
`test_die_faktentabelle_ist_nach_tag_und_kennung_sortiert` prüft nicht Bytes,
sondern die **Eigenschaft**: Die Vorrichtung liefert die Zeilen in verkehrter
Tagesreihenfolge, ohne Klausel kommen sie so wieder heraus. Deterministisch,
**sechs von sechs** gefangen, und ohne `referenzstand`-Marke — er läuft bei
jedem Push mit. `test_ein_zweiter_lauf_liefert_dieselben_bytes` baut Gold
zweimal als eigenen Unterprozess und vergleicht die Prüfsummen aller sechs
Tabellen; er bleibt für das, was eine Eigenschaftsprüfung nicht sieht —
Nichtbestimmtheit im Schreiber selbst, bei gleicher Zeilenfolge. Sein Docstring
sagt jetzt, was er wert ist. Er trägt die `referenzstand`-Marke, weil er
gebautes Silber braucht, läuft nicht unter Windows (Symlink), und prüft
`dim_tract_acs` nur in der Einzel-Vintage-Gestalt, weil das Silber nur
`vintage=2024` hat.

**Was das für §3 heisst.** Das Erfolgskriterium „Reproduzierbarkeit — zweiter
Lauf, gleiche Prüfsummen" war für Gold **nicht erfüllt**, obwohl NFR-1 sie als
„gehalten, nicht neu zu bauen" führt. Jetzt ist sie es, und ein Wächter hält
sie. Nebeneffekt: `serving.pruefe_stand` meldete Gold nach jedem Neubau als
„anders", obwohl kein Wert sich geändert hatte — das hört auf.

**Kein Vertragssprung.** `CONTRACT_VERSION` beschreibt Bedeutung,
Granularität, Regeln und Spalten. Die Zeilenreihenfolge ist keines davon, und
kein Verbraucher darf sich auf sie stützen.

**Noch zu tun, nicht Teil dieser Änderung:** Das gebaute `data/gold` trägt
weiterhin die alte Reihenfolge. Der erste Neubau verschiebt seine Bytes
**einmal**; danach stehen sie. Nachzuziehen sind dann: Serving, ein neues
Release, die geladenen Elasticsearch- und ClickHouse-Stände — und
`docs/einstieg.html`, das je Datensatz die Dateigrösse nennt und für
`fact_offense` heute 14,3 MB zeigt, nach der Sortierung rund 15,1. Der Wächter
`test_die_abgelegte_seite_ist_nicht_aelter_als_das_release` fällt, bis
`python tools/build_einstieg.py` neu gelaufen ist. Das Nachladen der Stores
rührt an laufende Container.

**Zahlen.** 1'564 → **1'566 Tests**, Standardlauf **1'484**, Referenzwächter
82 statt 81. Zwei neue: der Sortierungstest laeuft im Standardlauf mit, der
Byte-Vergleich ist abgewählt.
`docs/referenz/` neu erzeugt.

## 03.10.2026 · Die NIBRS-Zuordnung über sechs Jahrgänge (#128)

FR-38, und es ist dieselbe Rechnung wie bei `coverage_percent_by_city` — nur
auf der Zeitachse. Die Zuordnung war nirgends jahresbezogen: `abdeckung()`
misst über die **ganze** Faktentabelle, Silbers `reconcile()` je Stadt. Über
2021–2026 verschwindet damit ein schlechter Jahrgang im Mittel von sechs. Ein
Crosswalk, der ab 2026 ins Leere läuft, bliebe bei einer Schwelle von 85 %
unsichtbar, solange die fünf Jahrgänge davor tragen.

**`mapping_by_year` steht jetzt im Manifest von `fact_offense`** — neben
`year_coverage` und nicht darin: jenes ist zeitliche Abdeckung, dies ist
Zuordnungsabdeckung. Je Jahrgang die Zahl der Taten, die Anteile der vier
`mapping_status`-Werte, und drei Dinge **beim Namen**:

| | |
| --- | --- |
| `unmapped_codes` | welcher Quellcode unzugeordnet blieb, mit Stadt und Zahl, absteigend |
| `new_source_codes` | welcher Code im Vorjahrgang nicht vorkam |
| `retired_source_codes` | welcher im Vorjahrgang vorkam und jetzt fehlt |

Bis hierher war eine Lücke **nur ein Prozentsatz**. Welcher Code sie
verursacht, stand nirgends — und ohne den Code ist nicht zu entscheiden, ob
eine Zeile im Crosswalk fehlt oder die Stadt etwas Neues codiert. Die Stadt
steht überall dabei, weil derselbe vierstellige Code in beiden Städten etwas
völlig anderes bedeuten kann: `1101` ist in Chicagos IUCR *Public Aid
Wire/Mail Fraud* und führt auf 26D Welfare Fraud, in Detroits MICR *Sexual
Penetration Penis/Vagina CSC1* und führt auf 11A Rape. Sieben Codes stehen in
beiden Tabellen (`1101`, `1102`, `1200`, `2900`, `4800`, `5000`, `5001`).

**Die Differenz und kein Inventar.** Ein volles Codeinventar je Jahrgang wären
für Chicago rund 400 Codes mal sechs — kein Manifest, das jemand liest.
Gefragt ist die Änderung: neu und weggefallen, je Jahrgang eine Handvoll
Zeilen. Der älteste Jahrgang hat keinen Vorgänger und damit keine neuen Codes;
„alle Codes neu" wäre dort keine Aussage.

Für den heutigen Einjahresbau liest sich der Nachweis so — und er nennt den
Code, den `unmapped: 0.0009` bisher verschwieg:

```json
"2024": { "offenses": 345091,
          "exact": 95.4902, "ambiguous": 1.4732,
          "fallback_90Z": 3.0357, "unmapped": 0.0009,
          "unmapped_codes": [{"city": "chicago", "code": "1481", "offenses": 3}],
          "new_source_codes": [], "retired_source_codes": [] }
```

**Ein Teiljahrgang wird gemeldet, aber nicht verglichen.** FR-37 sagt einen
Commit zuvor: Ein Teiljahr darf nicht in einen Jahresvergleich geraten — und
`retired_source_codes` ist einer. Für einen Jahrgang mit
`year_is_complete = false` bleiben beide Codelisten deshalb leer, und der
Vergleich überspringt ihn: Der nächste **volle** Jahrgang vergleicht gegen den
letzten vollen. Ohne diese Regel erschiene an 2026 jeder Code, der dort nur
**noch nicht** vorkam, als weggefallen — bei neun von zwölf Monaten wären das
die meisten. Der Preis ist bewusst getragen: Ein echter neuer Code von 2026
wird erst sichtbar, wenn 2026 voll ist. Dieselbe Zurückhaltung gilt für einen
Jahrgang **ohne Taten**: gemeldet mit `offenses` 0, aber nicht verglichen, denn
ein leerer Codesatz liesse jeden Code erst wegfallen und im nächsten Jahrgang
wieder neu erscheinen.

**Das Tor bleibt global.** `pruefe_gate` prüft weiter den Gesamtanteil und jede
Stadt, nicht jeden Jahrgang: Ein Bau soll nicht an einem Jahrgang scheitern,
dessen Daten erst halb geladen sind — ein halber Jahrgang ist kein Einsturz.
Die Jahreszahlen stehen aber im Manifest, und ein **Test** hält sie gegen
`GATE_MINDESTENS`/`GATE_HOECHSTENS`. Fällt also etwas, scheitert die Suite und
nicht die Strecke — und erst, wenn die Daten da sind. Ein Jahrgang **ohne
Taten** wird dabei übersprungen: Dort steht `exact` auf 0,0, und das ist keine
schlechte Zuordnung, sondern keine Daten. `run_all --jahre 2021,2026` hätte
sonst vier Scheinverletzungen gemeldet.

**`seen_in_detroit_2024` entfällt.** Die Spalte stand als elfte in
`config/micr_nibrs_mapping.csv`, 128-mal `true`, von Hand gepflegt — und ihr
Wächter `test_seen_in_detroit_stimmt_mit_den_daten` wäre gebrochen, sobald mehr
als 2024 geladen ist: Er vergleicht sie mit `detroit_codes()`, und das liest
**alle** Bronze-Läufe. Ob ein Code **vorkommt**, ist eine Eigenschaft der Daten
und keine der Zuordnungstabelle. Zwei Ersatzspalten (`erstmals_gesehen`,
`zuletzt_gesehen`) hätten dasselbe Problem eine Ebene später — sie müssten bei
jedem Jahrgang nachgezogen werden, und `tools/extend_micr_arrest_charges.py`
berechnet sie nicht. An ihre Stelle tritt `mapping_by_year`. Die Datei hat
jetzt **11 Spalten** und behält ihre 129 CRLF-Zeilen; erzeugt wurde sie vom
Werkzeug, nicht von Hand.

**Chicagos Crosswalk bekommt den Wächter, den Detroits längst hatte.**
`tests/config/test_iucr_nibrs_mapping.py` prüfte die Tabelle nur gegen
**Kataloge** — Chicagos IUCR-Katalog, die NIBRS-Codeliste, die ILCS-Tabelle der
Landespolizei. Keiner davon sagt, was in den Falldaten steht. Jetzt steht dort
der Wächter, der eine Lücke beim Namen nennt: jeder `iucr` der Bronze-Läufe
muss im Crosswalk stehen. Gemessen: 341 verschiedene Codes in den Läufen, alle
in der Tabelle. Einen **Fallanteil** wie bei Detroit gibt es hier bewusst
nicht — Bronze hält jeden Lauf, und Chicago lädt Deltas mit 14 Tagen
Überlappung: 8 Läufe, 520'490 Zeilen für 259'643 verschiedene ids, Faktor 2,00.
Ein solcher Anteil wäre nach Ingestionshäufigkeit gewichtet und nicht nach
Fällen. Auf entdoppelter Basis und je Jahrgang steht er in `mapping_by_year`.

**Kein Vertragssprung.** Keine Tabelle und keine Spalte in Gold ändert sich;
`mapping_by_year` ist ein Nachweis im Manifest, kein Schema. Die
Zuordnungslogik selbst ist unangetastet — dies ist eine Mess- und
Nachweisänderung, nicht eine Änderung daran, *wie* zugeordnet wird.

**Zahlen.** 1'550 → **1'564 Tests**, Standardlauf **1'483**. Fünfzehn neue,
einer entfallen: je Zeile der I/O-Matrix einer (ein ganz zugeordneter Jahrgang,
der schlechte Jahrgang im Mittel von sechs, der neue Code, der weggefallene,
der älteste ohne Vorgänger, der Jahrgang ohne Taten, der Teiljahrgang), dazu
der Massstab nach einem Teiljahrgang, die Reihenfolge der unzugeordneten Codes,
die Stadt an jeder Zeile, die Summe der vier Anteile auf 100 — und auf 0 beim
leeren Jahrgang —, der Nachweis im Manifest, der Schwellenwächter je Jahrgang,
der leere Jahrgang als Nicht-Verletzung, und der Chicagoer Datenwächter. Gold und Serving neu gebaut, lokales Release
`2026-10-03T19-53-12Z`, ClickHouse und Elasticsearch darauf geladen;
Feldkatalog, Referenz, Einstiegsseite und Notebook 32 nachgezogen. Die Raten
bleiben bei 94,5 und 132,7.

---

## 03.10.2026 · Ein Teiljahr sagt, dass es eines ist (#128)

FR-37 und FR-39, und sie gehören zusammen: Das eine kennzeichnet, das andere
misst.

**`dim_date` trägt `year_is_complete`** — ob der Jahrgang dieses Tages ganz in
den Daten liegt. Der Grund ist eine Zahl, die sonst entsteht: **2026 hat am
3.10. neun Monate.** Neun Monate gegen zwölf gestellt ergeben einen Rückgang
der Kriminalität von einem Viertel, und den gibt es nicht. Die Spalte sitzt am
Datum und nicht in einer eigenen Tabelle, weil sie ein Jahresattribut eines
Tages ist — jede Abfrage, die nach Jahr gruppiert, hat sie damit zur Hand.

Geprüft wird, ob die Datenspanne den 1. Januar **und** den 31. Dezember des
Jahres einschliesst. Unvollständig ist deshalb nicht nur „noch nicht zu Ende":
Ein Jahrgang, der erst im März beginnt, ist es auch — ein eigener Test hält
das.

**Das Projekt hatte diese Disziplin schon, eine Ebene tiefer.**
`comparison_week` und `comparison_month` führen `days_in_period` gegen
`days_in_window`: Eine Woche, die am 30. Dezember beginnt, hat sieben Tage,
aber nur zwei im Datenfenster, und das steht daneben. FR-37 zieht dieselbe
Ehrlichkeit auf die Jahresebene hoch. Eine Jahresvergleichstabelle, in die ein
Teiljahr geraten könnte, gibt es noch nicht; wenn sie kommt, filtert sie auf
die Spalte.

**Die Grenze der Spalte ist benannt, und dafür gibt es FR-39.**
`year_is_complete` sieht nur die Enden. Einem Jahrgang könnte der halbe Juli
fehlen, und die Spalte sagte weiter „ganz". Das Manifest von `fact_offense`
trägt deshalb `year_coverage` je Jahrgang: Zahl der Taten, erster und letzter
abgedeckter Tag, **`days_with_offenses` gegen `days_in_year`**. Bei zwei
Grossstädten ist jeder Tag besetzt — fällt die erste Zahl unter die zweite,
fehlt wirklich etwas. Ein Test führt genau diesen Fall vor: zwei Tage am 1.1.
und 31.12., `complete` sagt wahr, und 363 fehlende Tage stehen direkt daneben.

Für den heutigen Einjahresbau liest sich der Nachweis so:

```json
"2024": { "offenses": 345091, "first_date": "2024-01-01",
          "last_date": "2024-12-31", "days_with_offenses": 366,
          "days_in_year": 366, "complete": true }
```

**Vertrag `gold/*` 6 → 7**, weil `dim_date` eine Spalte bekommt.

**Zahlen.** 1'542 → **1'550 Tests**, Standardlauf **1'469**. Acht neue Tests:
der ganze Jahrgang, der im Oktober endende, der im März beginnende, drei
Jahrgänge gemischt, die Abdeckung mit Spanne und Tagen, das Schaltjahr mit 366,
die benannte Lücke mitten im Jahr, und der Nachweis im Manifest. Gold und
Serving neu gebaut, lokales Release `2026-10-03T17-49-45Z`, Feldkatalog,
Referenz und Einstiegsseite neu erzeugt. Die Raten bleiben bei 94,5 und 132,7.

## 03.10.2026 · Notebook 34 kennt die sechste Sterntabelle — und drei Zahlen stimmten schon vorher nicht (#128)

Der offene Punkt aus dem Eintrag zu FR-35. `notebooks/34_gold_sternschema.ipynb`
las in vier Zellen `sum(population) FROM dim_tract`, und sein Sternschema-Bild
zeigte vier Dimensionen. **Kein Test hat das gemeldet**: Notebooks laufen nur im
wöchentlichen Datenlauf, und dort wäre es als Fehler aufgeschlagen — genau die
Falle, die in `AGENTS.md` unter den Fallstricken steht.

Das Notebook benutzt jetzt `gold_pipeline.einwohner_je_stadt` statt einer
eigenen Fassung — und **zeigt den Nenner im Klartext**, bevor es ihn verwendet:

```
SELECT d.city AS city, sum(a.population) AS n FROM dim_tract d
JOIN dim_tract_acs a ON a.geoid = d.geoid AND a.vintage = d.reference_vintage
WHERE d.city IS NOT NULL GROUP BY d.city
```

Das ist der Punkt, an dem ein Notebook mehr kann als eine Funktion: Es erklärt
den Verbund über **zwei** Spalten an der Stelle, an der er zum ersten Mal
gebraucht wird, ohne eine zweite Fassung davon anzulegen. Die Tabellenliste
kommt aus `gold_pipeline.TABELLEN`, nicht mehr aus einem Tupel von Hand — eine
siebte Sterntabelle erscheint dort künftig von selbst. Das Sternschema-Bild hat
einen fünften Strahl bekommen, an zwei Spalten statt an einer, und `dim_tract`
führt dort jetzt `reference_vintage` statt `population`.

**Drei Zahlen stimmten schon vor dieser Änderung nicht.** Sie sind beim Lesen
der Zelle aufgefallen, nicht durch einen Test:

| | stand im Notebook | gemessen am 3.10.2026 |
| --- | ---: | ---: |
| `fact_offense` (zweimal genannt) | 345'073 | **345'091** |
| `silver/crime_offense` im Bild | 348'311 | **348'329** |
| Schritt Silver → Gold (dreimal) | 3'340 | **3'238** |

Die ersten beiden sind die achtzehn Zeilen, die mit der Quellbewegung
dazugekommen sind. Die 3'340 war nie richtig: Der Schritt ist die Zahl der
nicht zählenden Anklagen, und die waren auch mit den alten Zahlen 3'238
(348'311 − 345'073). Eine Zahl, die aus zwei anderen folgt, war von Hand
daneben geschrieben.

**Geprüft und unverändert:** Notebook 33 liest die Serving-Sicht auf Silber,
nicht Gold; Notebook 36 nennt `gold/dim_tract` nur als Pfad. Beide brauchten
nichts. Das Notebook ist mit `nbconvert --execute` durchgelaufen, die Raten
bestätigen die Abgabezahlen: Chicago 94,5, Detroit 132,7, mit den
Grenzfällen 95,6.

## 03.10.2026 · Die Einwohnerzahl bekommt eine Zeitachse (#128)

FR-35, und damit ist Welle 1 auf dem Weg: `run_all --jahre 2021-2026` läuft
jetzt durch bis Serving. Der Riegel vor Gold von heute Morgen ist weg, weil der
Grund dafür behoben ist.

**Der Grund.** `dim_tract` trug `population`, `median_household_income_usd` und
`poverty_rate`, und das ging, solange es einen einzigen Jahrgang gab: Eine
Tabelle mit einer Zeile je Tract kann nur **eine** Einwohnerzahl tragen. Über
sechs Jahrgänge hätte jede Tat denselben Nenner bekommen, auch die von 2021 —
und das Ergebnis hätte vollständig ausgesehen.

**Vertrag `gold/*` 5 → 6.** Die drei ACS-Masse liegen in der neuen Tabelle
`dim_tract_acs`, je Tract **und Vintage**. `dim_tract` behält die
Stadtzuordnung und nennt mit `reference_vintage`, aus welchem Jahrgang sie
kommt. `fact_offense` trägt `population_vintage` und sagt damit je Zeile,
welcher Nenner für sie gilt: bis 2024 das eigene Jahr, darüber der jüngste
vorhandene. **Damit steht FR-36 in den Daten und nicht in einer Fussnote** —
eine Rate für 2025 ruht auf der Bevölkerung von 2024, und die Zeile sagt es
selbst. Geklammert wird auf die geladene Spanne, damit keine Tat auf eine
fehlende Zeile zeigt; ein Wächter prüft das für alle sechs Jahrgänge.

**Die Stadtzuordnung wird nicht je Vintage neu gerechnet.** Das war eine
Entscheidung und keine Auslassung: Ein Tract soll dauerhaft zu einer Stadt
gehören. Würde die Mehrheitsregel gegen die Ortsgrenzen jedes Vintages laufen,
könnte ein Tract 2021 zu Chicago gehören und 2024 nicht — dann sprünge die Rate
aus einem Grund, der nichts mit Kriminalität zu tun hat. `reference_vintage`
macht sichtbar, aus welchem Stand sie stammt.

**Der Nebenbefund war die eigentliche Arbeit.** Die Abfrage „Einwohner je
Stadt" stand an **neun** Stellen im Projekt: im Driftbericht, auf der
Einstiegsseite und in sieben Wächtern, die die Raten in den Abgabedokumenten
halten. In `tools/build_einstieg.py` stand sogar der Kommentar *„Dieselbe
Abfrage wie in tests/test_aenderungen.py — eine Definition"* — zwei Fassungen
sind keine Definition, und mit dem Verbund über zwei Spalten wären es neun
Gelegenheiten geworden, das zweite Prädikat zu vergessen. Wer nur `geoid`
verbindet, bekommt je Tract so viele Zeilen, wie Vintages geladen sind, und das
Ergebnis sieht aus wie eine Zahl. Die Regel steht jetzt einmal in
`gold_pipeline.einwohner_je_stadt`, und ein Test führt die Vervielfachung vor.

**Zwei Tests haben ihre eigene Falle verloren.** `test_architektur_dokument`
verdrahtete die Fünf doppelt — als Zahl und als Zahlwort —, und die Release-Tests
nannten 9, 10 und 11 Tabellen als Konstanten. Beide lesen die Zahl jetzt aus
`gold_pipeline.TABELLEN` und `serving.build_comparison.TABELLEN`.

**Zahlen.** 1'532 → **1'542 Tests**, Standardlauf **1'461**. Die Raten sind
**unverändert**: Chicago 94,5, Detroit 132,7 — dieselben 2'661'953 und 638'635
Einwohner, nur aus einer anderen Tabelle. Gold und Serving neu gebaut, ein
lokales Release `2026-10-03T17-26-24Z`, `docs/feldkatalog.md`,
`docs/referenz/`, die drei Architekturbilder und `docs/einstieg.html` neu
erzeugt. `docs/architektur.md`: 24 → 26 Importkanten, sieben → neun gezeichnete
Pfeile — `gold_pipeline` und `orchestration` greifen jetzt nach
`census_pipeline`, wo die Vintage-Regel wohnt.

**Offen.** Elasticsearch und ClickHouse halten weiterhin das vorige Release;
`pruefe_stand` meldet das zu Recht. Sie werden mit
`python -m serving.load_elasticsearch` beziehungsweise `load_clickhouse`
nachgezogen — das rührt an laufende Container und ist deshalb nicht Teil dieser
Änderung.

## 03.10.2026 · Der Gesamtlauf nimmt einen Jahresbereich, und Gold sagt Nein (#128)

FR-34 aus dem LN2-PRD. `run_all` nahm bisher keinen Jahrgang an: Chicago lief
auf dem Standardwert seines Moduls, und für Detroit stand `--years 2024` als
Konstante in der Stufenliste. `--jahre` nimmt jetzt `2024`, `2021-2026` oder
`2021,2023`. **Vorgabe bleibt 2024** — ein Aufruf ohne die Option tut
byteweise dasselbe wie vorher, ein Mehrjahreslauf ist eine Ansage und kein
Nebeneffekt eines Updates.

**Die Entfaltung gehört nicht in `STUFEN`.** Das war der entscheidende Punkt
am Entwurf: `STUFEN` beschreibt die **Form** der Strecke, und daraus entstehen
das Datenflussbild (`tools/build_architekturbilder.py`) und die Stufenzahlen
auf der Referenz-Startseite — drei Wächter zählen dort vierzehn. Hätte die
Jahresentfaltung `STUFEN` selbst verlängert, wären aus vierzehn Stufen
plötzlich neununddreissig geworden, samt zwei erzeugten Artefakten und ihren
Wächtern. Wie oft eine Stufe läuft, ist deshalb eine Eigenschaft des **Laufs**
und steht in `auswahl`. Jede Stufe sagt über zwei neue Felder, worüber sie sich
wiederholt: `je="jahr"` für die Kriminalquellen, `je="vintage"` für Census und
seine Silver-Tabellen, nichts für NOAA und alles Abgeleitete. Aus 2021–2026
werden so 39 Stufen — nicht 84, weil NOAA je Station einen Vollschnappschuss
lädt und sechs Aufrufe sechsmal dasselbe geholt hätten.

**Ab 2025 bleibt es beim 2024er Vintage.** `vintage_fuer(jahr)` ist
`min(jahr, 2024)`, mit der Messung vom 3.10.2026 als Begründung: Das jüngste
verfügbare ACS-5-Jahres-Vintage **ist** 2024. Sechs Jahrgänge brauchen deshalb
vier Vintages, nicht sechs. Eine Rate für 2025 ruht damit auf der Bevölkerung
von 2024 — das ist keine Hochrechnung, sondern eine geliehene Bevölkerung, und
FR-36 verlangt, dass es überall dabeisteht. Hier steht erst die Mechanik; die
Kennzeichnung in Gold, auf den Dashboards und auf der Seite fehlt noch.

**Mehrere Vintages und Gold im selben Lauf werden abgelehnt, vor der ersten
Stufe.** `build_gold` nimmt ein einzelnes `--vintage` und verbindet alles
damit. Bei vier Vintages bekäme jede Tat von 2021 den Nenner von 2024 — und
das Ergebnis sähe vollständig aus. Sechs Jahrgänge zu laden und das erst in
Gold zu merken, kostet eine Stunde und hinterlässt einen halben Stand; der
Riegel greift deshalb, bevor ein Byte fliesst. Ein Mehrjahreslauf geht
vorerst mit `--bis silver`. Das schliesst **FR-35**, und das ist der nächste
Schritt: `silver/tract` und `silver/place` liegen schon je Vintage, Gold muss
je Jahrgang das passende wählen — und das ändert das Sternschema, also einen
Datenvertrag.

**Nebenbefund.** Argparse fängt `ValueError` aus einem `type=`-Aufruf und
ersetzt die Meldung durch *„invalid jahre_aus_text value: '1999'"*. Der
Benutzer hätte erfahren, dass seine Angabe falsch ist, aber nicht warum — und
das Warum ist der ganze Sinn der Prüfung. `jahre_argument` reicht die
Begründung als `ArgumentTypeError` durch: *„1999 liegt ausserhalb von 2001 bis
2027"*, *„'2021-2019' läuft rückwärts"*.

**Offen geblieben, bewusst:** `leistungsnachweise.md` 7.3 sagt *„Der Zeitraum
ist auf 2024 festgelegt"* und verweist auf die Projektabsprache. Das stimmt
weiterhin — der Controller **kann** jetzt mehr, gebaut wird aber nichts
anderes, solange Gold nur ein Vintage verbindet. Die Absprache zu ändern ist
Artans Teil und gehört zu FR-53 bis FR-55.

**Zahlen.** 1'507 -> **1'532 Tests**, Standardlauf **1'451**. 25 neue Tests:
die Jahresarithmetik, die sechs Leseformen und fünf Fehlerfälle von `--jahre`,
die Entfaltung je Achse, und vier Tests um den Gold-Riegel — darunter einer,
der prüft, dass bei mehreren Vintages **keine** Stufe startet. `docs/referenz/`
neu gebaut. Kein Datenvertrag ändert sich: Bei der Vorgabe 2024 sind die
Befehlszeilen identisch.

## 03.10.2026 · DuckDB bekommt Grenzen, und keine Verbindung kommt daran vorbei (#128)

Erste Anforderung aus dem LN2-PRD (FR-61), und sie stand vor dem
Mehrjahreslauf, nicht danach: **Ohne `memory_limit` nimmt DuckDB rund 80 % des
Arbeitsspeichers der Maschine.** Auf einem Laptop, der nur die Strecke fährt,
ist das richtig. Auf `srv01` mit 7,7 GiB und fünfzehn Diensten ist es die
Stelle, an der ein Lauf über sechs Jahrgänge stirbt — und er stirbt nicht
allein, er nimmt die Nachbardienste mit.

`DUCKDB_MEMORY_LIMIT` und `DUCKDB_THREADS` kommen jetzt aus der Umgebung und
werden auf **jeder** Verbindung gesetzt, die `storage.duckdb` herstellt. Ohne
Angabe bleibt DuckDBs eigene Vorgabe: Wer nichts setzt, merkt nichts.

**Der eigentliche Befund lag daneben.** Der Docstring von `storage/duckdb.py`
las sich schon immer so, als ginge jede Verbindung durch dieses Modul.
Tatsächlich riefen **neun Stellen** `duckdb.connect()` selbst auf — darunter
`build_source_change`, das über alle Bronze-Läufe liest, und
`build_analysis_db`, das die Serving-Datenbank schreibt. Eine Grenze nur im
Modul wäre also eine Zusage gewesen, die an den beiden grössten Abfragen
vorbeigeht. Alle neun laufen jetzt über `storage.duckdb.verbinde`, und ein
Wächter hält das: `test_keine_verbindung_umgeht_die_grenzen` liest `src/` und
`tools/` und nennt jede Stelle, die wieder selbst verbindet.

Ein Wert, den DuckDB ablehnt, lässt die Verbindung **scheitern** statt still zu
verfallen. Eine stillschweigend verworfene Grenze wäre schlimmer als keine: Der
Lauf liefe weiter, mit der Zusage im Protokoll und ohne sie im Prozess. Ein
leerer Wert ist dabei keine Angabe und keine Null — sonst schaltete
`DUCKDB_THREADS=` in einer `.env` die Parallelität ab, ohne dass jemand das
gemeint hätte.

**Zahlen.** 1'496 -> **1'507 Tests**, Standardlauf **1'426** (8 übersprungen,
81 Referenzwächter abgewählt). Elf neue Tests, davon einer der Strukturwächter
oben. `docs/referenz/` neu gebaut — neun Seiten haben sich geändert. Die
Testzahl wurde in `README.md`, `docs/architektur-ist-und-ziel.md`,
`docs/architektur-einseiter.html`, `docs/ln1_konzept.md` (drei Stellen),
`docs/intern/leistungsnachweise.md` (zwei Stellen) und im Kopf dieser Datei
nachgezogen. Kein Datenvertrag ändert sich: Es wird nichts anders geladen oder
gedeutet, nur anders begrenzt.

Die Zeile in Kapitel 10 des Konzepts sagte *„erwartet 1'415 bestandene Tests"*.
Das war schon vorher unscharf — der Standardlauf **sammelt** 1'426 und
überspringt davon 8, bestanden werden also 1'418. Jetzt steht die gesammelte
Zahl dort, und dass acht übersprungen werden.

## 03.10.2026 · Das Notebook erklaert jetzt auch, wie die Historisierung haelt (direkt auf main)

Gefragt war, ob `notebooks/37_quellbewegung.ipynb` exakt erklaert, wie die
Historisierung funktioniert. Antwort: Es erklaerte, **wie Aenderungen gefunden
werden** - nicht, **wodurch sie ein Aufraeumen ueberleben.** Das ist aber der
Unterschied zwischen einem Differenzbericht und einer Historisierung.

Der neue Abschnitt nennt die Mechanik: Die Tabelle ist append-only und
`aufraeumen` fasst nur Raw und Bronze an, Silber nie. Die Datierung klebt, ein
aufgeraeumtes Delta loescht sie nicht. Sie liegt unter
`data/silver/dataset=source_change/` und im hybrid-Modus auf SeaweedFS, nicht
in Git. Dazu Regel 4 - ein Vollabzug bleibt, bis sein Unterschied gezogen ist,
und faellt die Auskunft aus, gibt es keine Freigabe - und Regel 0, der
Referenzstand.

**Vorgefuehrt statt behauptet**, und die Vorfuehrung hat etwas aufgedeckt. Der
Aufraeumbericht laeuft im Notebook **zweimal**, einmal mit den Pins und einmal
ohne, weil sonst ueberall nur "Referenzstand" steht und keine Regel sichtbar
wird. Das Ergebnis ist unbequem:

* **Regel 4 kommt nicht vor.** Kein Lauf wird gehalten, weil sein Unterschied
  noch nicht gezogen waere - er ist ueberall gezogen.
* **Die Pins halten heute nichts, was nicht ohnehin gehalten wuerde.** Ohne sie
  waere genau derselbe eine Lauf entbehrlich. Fast alles traegt *"von Silver
  genannt"*: Silber entdoppelt ueber **alle** Laeufe und nennt sie deshalb alle
  in `derived_from`, und Regel 2 haelt, was Silber nennt.

Daraus folgt: **Fuer die beiden Kriminalitaetsquellen laesst sich derzeit
praktisch nichts aufraeumen.** Von 22 Laeufen ist einer entbehrlich, 24,5 MB,
und der gehoert NOAA. Die Rechnung *"31,9 MB Schnappschuesse fuer 102
geaenderte Zeilen"* beschreibt, was zu gewinnen waere - eingeloest ist sie
nicht. Wer das aendern will, muss an Regel 2 oder an Silber: Ein Silber, das
vom letzten Vollabzug plus den Deltas danach baut, braeuchte die aelteren
nicht mehr, und erst dann traegt der Referenzstand wirklich etwas.

Die Lage ist also: Die Aenderungsgeschichte **ist** gesichert und wuerde ein
Aufraeumen ueberleben. Nur findet das Aufraeumen noch nicht statt. Das steht
jetzt so im Notebook, statt dass die Rechnung aus der `datenhistorie.md` als
erreicht gelesen werden kann.

**Nicht geaendert:** Die LN1-Pins bleiben, bis die Rueckmeldung der Pruefenden
vorliegt. Sie sind die Belege fuer die Zahlen vom 25.9.

---

## 03.10.2026 · Silber neu gebaut, Referenzstand nachgezogen (direkt auf main)

Der zweite Chicago-Vollabzug lag seit dem Morgen in Bronze, ohne dass Silber
ihn kannte. Acht Stufen neu gebaut - Silber, Gold, Serving - in 26 Sekunden,
dazu ein Release und ein nachgezogener Referenzstand.

**Die Verschiebung ist klein und sie erklaert sich selbst.**

| | vorher | nachher | |
| --- | ---: | ---: | ---: |
| `silver/crime_offense` | 348'311 | **348'329** | +18 |
| `gold/fact_offense` | 345'073 | **345'091** | +18 |
| Chicago, Anklagen | 259'625 | **259'643** | +18 |
| Chicago, Vorfaelle | 259'596 | **259'614** | +18 |
| Chicago, verortete Delikte | 251'516 | **251'517** | +1 |
| Raten je 1'000 | 94,5 / 132,7 | **94,5 / 132,7** | unveraendert |

**Warum nur 18 und nicht 366.** Der neue Vollabzug hat 259'638 Zeilen gegen
259'272 am 5.9., also 366 mehr. In Silber kommen davon nur **18** an - und das
ist genau die Zahl, die `source_change` vorhergesagt hat: Von den 371 neuen
Delikten trugen **353 schon die Deltas** vom 17. und 18.9. ein, lange bevor
der Vollabzug lief. Nur 18 trug kein Delta. Die Datierung hat sich damit
selbst bestaetigt, an einer Zahl, die nicht aus ihr stammt.

Und die fuenf **verschwundenen** Delikte? Silber entdoppelt, es loescht nicht -
sie stehen weiter drin, und Gold zaehlt sie mit. Deshalb +18 und nicht +13.
Dass die Quelle sie zurueckgezogen hat, steht in `source_change`; dass sie
trotzdem in der Auswertung sind, ist eine Entscheidung und kein Versehen.

**Der Referenzstand.** `aufraeumen --pinnen stand-2026-10-03` haelt die zwoelf
Laeufe fest, auf denen das neue Gold ruht. Die neun **LN1-Pins bleiben
unangetastet**: Bereits gepinnte Laeufe behalten ihren ersten Grund, und damit
bleiben die abgegebenen Zahlen vom 25.9. reproduzierbar. Beides steht jetzt
nebeneinander in `config/referenzstand.csv`, unterscheidbar an der Spalte
`grund`.

**Release 2026-10-03T10-56-39Z** gebildet und publiziert, 21 Dateien, 42,2 MB;
`AKTUELL.json` zeigt darauf. Danach ClickHouse und Elasticsearch nachgeladen -
`serving.pruefe_stand` hatte gemeldet, dass fuenf Sichten und drei Aliasse noch
das Release vom 21.9. bedienten. Vier Orte, ein Stand.

**78 Zahlen in zwoelf Dokumenten nachgezogen**, von den Waechtern benannt und
nicht gesucht. Unberuehrt geblieben sind die datierten Eintraege dieses
Protokolls und `datenhistorie.md` - was dort steht, war zu seinem Zeitpunkt
richtig und bleibt es. Im Kopfabschnitt oben stehen die neuen Zahlen.

**Zwei Waechter trugen Zahlen von Hand**, und das ist ihre schwache Stelle:
`test_der_einseiter_traegt_dieselben_zahlen` fuehrt eine Liste der Werte, die
an zwei Stellen stehen muessen, und `test_der_manifesteintrag_nennt_die_zahl_der_laeufe`
vergleicht gegen ein festes Paar statt gegen den Text. Beide sind nachgezogen,
beide mit einem Kommentar, der sagt, dass die Zahl dort von Hand gefuehrt wird.

**Der Nebeneffekt, um den es eigentlich ging:** Jetzt laesst sich aufraeumen.
Der Bericht nennt einen entbehrlichen NOAA-Lauf (24,5 MB). Dass die
Aenderungsgeschichte davon unberuehrt bleibt, haelt der Waechter von heute
Nachmittag fest - die Datierung klebt.

---

## 03.10.2026 · Die Datierung klebt, damit das Aufraeumen gehen kann (direkt auf main)

Gefragt war, ob die historischen Aenderungen erhalten bleiben, wenn Raw- und
Bronze-Laeufe geloescht werden. Die Antwort war: ja - **ausser der
Datierung**. Und das war ein Mangel in dem, was drei Stunden vorher gebaut
wurde.

**Was bleibt, und wo.** `silver/source_change` ist append-only. Die Tabelle
liegt unter `data/silver/dataset=source_change/` und im hybrid-Modus zusaetzlich
auf SeaweedFS. `orchestration.aufraeumen` fasst nur Raw und Bronze an, Silver
nie. Regel 4 fragt `build_source_change` direkt: Ein Vollabzug, dessen
Unterschied noch nicht gezogen ist, bleibt - und faellt die Auskunft aus, gibt
es keine Freigabe, sondern eine leere Menge. Je Zeile erhalten: Stadt,
Schluessel, Vergleichspaar, beide Zeitpunkte, Art, Feld, alter und neuer Wert.
**4'718 Zeilen gegen 113,6 MB Bronze - Verhaeltnis 1'581 zu 1.**

**Was nicht blieb.** Die Datierung war als Annotation ausgelegt, bei jedem Bau
frisch gerechnet. Nachgestellt im Wegwerfverzeichnis: Loescht man das Delta,
wird aus `('delta', 'd1')` wieder `('nicht_datierbar', None)` - die
Aenderungszeile bleibt, ihre Datierung ist weg. Dazu kam: **Keine
Aufraeumregel haelt ein Delta, weil die Datierung es braucht.** Heute sind
Chicagos Deltas zufaellig geschuetzt, als "Referenzstand" oder "von Silver
genannt". Nach einem Silver-Neubau und einem verschobenen Referenzstand werden
sie entbehrlich, und der 17.9. waere an 369 Zeilen nicht mehr nachzulesen.

Das widerspricht dem Zweck der Tabelle: den Unterschied herausziehen,
**bevor** der Rohstoff entbehrlich wird. Fuer die zehn Tatsachenspalten galt
das. Fuer die drei Datierungsspalten war es gebrochen.

**Vertrag 3: die Datierung klebt.** Sie nennt den besten Befund, der je
bestimmt wurde, nicht den heutigen. Nachgerechnet wird, was besser wird -
Rangfolge `delta` > `kein_delta` > `nicht_datierbar` -, und nie abwaerts. Die
Spalten sind dieselben, ihre Bedeutung ist es nicht, und deshalb steigt die
Zahl.

Damit braucht es **keine** neue Aufraeumregel: Die Deltas duerfen weg, sobald
ihre Auskunft in der Tabelle steht. Das ist der Punkt - Aufraeumen ist ein
Ziel des Lebenszyklus, nicht ein Unfall, und eine Spalte, die daran zerbricht,
verhindert es.

Der Preis, ausdrücklich: Eine einmal falsch bestimmte Datierung waere
eingefroren. Sie entsteht deterministisch aus den Laeufen, ein Fehler kaeme
also nur aus einem Programmfehler - und dagegen ist Datenverlust der
schlechtere Tausch.

**Zwei Waechter halten das fest.**
`test_die_datierung_verblasst_nicht_wenn_die_deltas_weg_sind` baut, loescht das
Delta, baut erneut und verlangt dieselbe Datierung bei gleicher Zeilenzahl.
`test_eine_bessere_datierung_verdraengt_eine_schlechtere` zeigt die Rangfolge
an einem Fall: `kein_delta` wird zu `delta`, sobald ein Delta den Schluessel
traegt - und das zuerst getroffene Delta bleibt dabei stehen, es wird nicht
durch ein spaeteres ersetzt.

**Zahlen.** 1'494 -> **1'496 Tests**, Standardlauf 1'415. `docs/referenz/` und
`docs/feldkatalog.md` neu gebaut; die Beschreibung von `datierung` nennt jetzt
das Kleben.

---

## 03.10.2026 · Die Deltas datieren, was die Vollabzuege finden (direkt auf main)

Gefragt war, ob sich auch die Deltas vergleichen lassen, statt nur die
Vollabzuege. Die Antwort war dreiteilig, und die mittlere Fassung hat gewonnen.

**Warum ein Delta nicht vergleichen kann.** Es enthaelt nur die bewegten
Zeilen. Eine Zeile, die nicht darin steht, ist entweder unveraendert oder
gelöscht - `verschwunden` ist daraus nicht entscheidbar. Ein naiver Vergleich
haette 88'000 ruhige Zeilen als verschwunden gemeldet. Dazu kommt: Ein Delta
wird ueber das Stempelfeld ausgewaehlt und findet nur, was die Quelle selbst
gemeldet hat.

**Diese blinde Stelle ist jetzt beziffert**, an den Vollabzuegen, die beides
sehen: Ein Delta haette **99 %** von Detroits und **100 %** von Chicagos
Inhaltsaenderungen gefunden. Die acht Ausnahmen sind alle dasselbe Feld,
`nearest_intersection`, und dieselbe Korrektur bei mehreren Delikten -
`Ashley Ave & Ashley Dr` -> `Ashley Ave & Mack Ave` viermal, `Brush St &
Gratiot Ave` -> `Brush St & Clinton St` dreimal -, ohne dass ein Stempel sich
bewegte. Das sieht nach einer Neuberechnung auf Quellseite aus und nicht nach
Einzelbearbeitungen. Fuer die Abgabezahlen harmlos: Das Feld kommt nie nach
Silver.

**Gewaehlt ist die Fassung, die nichts riskiert.** Gefunden wird weiter nur
zwischen Vollabzuegen. Die Deltas erzeugen keine Zeile - sie **datieren**, was
die Vollabzuege finden. Vertrag 2 ergaenzt dafuer drei Spalten:

| `datierung` | heisst |
| --- | --- |
| `delta` | ein Delta im Fenster trug den Schluessel; `zuerst_gesehen_in` nennt das **erste** |
| `kein_delta` | Deltas lagen vor, keines trug den Schluessel |
| `nicht_datierbar` | kein lesbares Delta liegt im Fenster |

Drei Zustaende statt einer Leerstelle, aus demselben Grund, aus dem es die
Markierungszeile `art = 'unveraendert'` gibt: *nichts gefunden* ist nicht
dasselbe wie *nicht nachgesehen*. Und `kein_delta` heisst ausdruecklich nicht
*"nicht angemeldet"* - es hat drei Ursachen, die von dort aus nicht zu trennen
sind: die Quelle hat nichts gemeldet, oder die Aenderung kam nach dem letzten
Delta, oder die Zeile war schon weg.

**Was es bringt, in Zahlen.** Chicagos Fenster ist 28 Tage breit. 369 der
dort gefundenen Zeilen sind jetzt auf den **17.9.** datiert, also 16 Tage vor
dem Vollabzug; sechs weitere auf den 18.9., zwei auf den 5.9. Aus
*irgendwann in dreissig Tagen* wird damit ein Tag.

**Detroit datiert nichts, und das ist richtig.** Seine drei Deltas liefen am
18.9. um 11:08, 11:57 und 14:33 - das letzte Vergleichsfenster endet um
**11:02**. Sechs Minuten zu spaet. Kein Delta liegt in einem Fenster, also
`nicht_datierbar`. Mit dem Monatstakt loest sich das von selbst.

**Die Datierung ist eine Annotation, keine Tatsache des Paares.** Sie wird bei
jedem Bau neu gerechnet, auch fuer die 4'718 schon gezogenen Zeilen - sonst
haette Vertrag 2 nur fuer kuenftige Paare einen Wert gehabt. Sie wird besser,
sobald ein Delta dazukommt, und verblasst, wenn die Deltas aufgeraeumt sind
(**so war es am Nachmittag noch; der Eintrag darueber macht die Datierung
klebrig, weil das Verblassen Datenverlust war**);
die zehn Tatsachenspalten bleiben unberuehrt. Ein Test haelt genau das fest:
bauen, ein Delta nachlegen, nochmals bauen - die Zeilenzahl bleibt, die
Datierung springt von `nicht_datierbar` auf `delta`.

**Ein Fehler, den die Tests gefangen haben.** Der erste Entwurf legte die
Schluesseltabelle in `datiere` mit `CREATE OR REPLACE` an - je Quelle. Damit
loeschte der Durchgang fuer Chicago die Deltas von Detroit wieder, und nur die
letzte Quelle ueberlebte. Aufgefallen ist es, weil die Tests die Datierung je
Quelle pruefen und nicht die Gesamtzahl. Die Tabelle wird jetzt einmal
angelegt, und `datiere` fuellt nur.

**Nachgetragen: `silver/source_change` stand nicht im Vertragsregister.** Das
Modul fuehrte `CONTRACT_VERSION` seit dem 1.10., aber kein Test hielt die Zahl
gegen den Abschnitt "Vertragsversionen"; der Datensatz fehlte in der Abbildung
von `test_vertragsversionen.py`. Beides ist ergaenzt - die Version steigt also
nicht nur, sie wird jetzt auch bewacht.

**`notebooks/37_quellbewegung.ipynb`** zeigt die Datierung mit: auf welches
Delta wie viele Zeilen datiert sind und wie weit vor dem Vollabzug, dazu die
Gegenprobe, welches Fenster ueberhaupt Deltas traf. Der Grenzen-Abschnitt ist
nachgezogen - Punkt 1 lautete "nur Vollabzuege" und heisst jetzt praeziser
"gefunden wird nur zwischen Vollabzuegen, datiert wird mit den Deltas".

**Und noch eine Luecke, auf die das gestossen ist.** Der Feldkatalog leitet
Spalten und Typen aus den Manifesten der gebauten Tabellen ab. Das Manifest von
`source_change` trug **kein `schema`** - als einzige Silver-Tabelle. Folge: Der
Abschnitt im Katalog war **leer**, eine Ueberschrift mit einer Kopfzeile und
nichts darunter, und der Waechter, der jede gebaute Spalte auf eine
Beschreibung haelt, pruefte fuer diese Tabelle gar nichts. Der Werkzeugkopf
verspricht *"der Lauf scheitert und nennt die Spalte"* - er konnte es nie,
weil er keine Spalte sah.

Das Manifest traegt jetzt sein Schema, und damit scheiterte der Lauf wie
vorgesehen und nannte elf Spalten ohne Beschreibung. Alle dreizehn sind
eingetragen; der Katalog hat zum ersten Mal einen gefuellten
`source_change`-Abschnitt. Dabei fiel noch auf, dass ein Vertragswechsel allein
nicht zum Schreiben fuehrte: Die Tabelle ist append-only, und ohne neues Paar
hielt der Lauf sich fuer fertig. Jetzt publiziert er auch, wenn sich Vertrag
oder Schema bewegt haben.

**Zahlen.** 1'486 -> **1'494 Tests**, Standardlauf 1'413. `docs/referenz/` und
`docs/feldkatalog.md` neu gebaut.

---

## 03.10.2026 · Chicago bewegt sich anders als Detroit, und jetzt sieht man es (direkt auf main)

**Entschieden: ein Vollschnappschuss je Stadt und Monat.** Damit ist Punkt 3
aus Abschnitt 8 von `datenhistorie.md` beantwortet und die offene Flanke des
Nachtrags vom 1.10. geschlossen - `source_change` hoert nicht mehr nach den
fuenf Detroit-Schnappschuessen auf zu wachsen.

**Chicagos zweiter Vollabzug** lief am 3.10. um 09:30 UTC: **259'638 Zeilen**
gegen 259'272 am 5.9., Vollstaendigkeit nachgewiesen, Schema-Fingerabdruck
unveraendert. `silver/source_change` waechst von 4'292 auf **4'718 Zeilen**.

**Vier Asymmetrien standen dem im Weg, nicht die eine, die der Code
erwartete.** Im Modul stand *"sobald ein zweiter geladen wird, gehoert hier
eine Zeile hin"*. Das war zu optimistisch:

| Was | Chicago | Detroit |
| --- | --- | --- |
| Lademodus | `mode = full_snapshot` | `extraction_mode = FULL` |
| Startzeitpunkt | `started_at_utc` | `started_at` |
| Form der Bronze-Datei | flache Spalten | Struct `attributes` |
| Schluessel | `id` | `incident_entry_id` |

Die ersten zwei wohnen jetzt im gemeinsamen Manifestleser
(`manifeste.Lauf.vollabzug`, `manifeste.Lauf.begonnen_um`) - dieselbe Loesung
wie bei `FERTIG`, wo `complete` und `SUCCESS` beide gelten. Die anderen zwei
sind Eigenschaften der Quelle (`Quelle.struct`, `Quelle.schluessel`). Ohne das
haette das Modul auch zwei Chicago-Vollabzuege nicht gefunden: Es las nur
`extraction_mode`.

Beim Lesen der flachen Spalten kommt `storage.parquet_spalten` zum Einsatz und
nicht `DESCRIBE` - der Pfad traegt `city=` und `ingest_date=`, und daraus
haette DuckDB zwei Hive-Spalten abgeleitet und als Quellfelder verglichen. Zwei
Felder, die sich je Lauf aendern und nichts bedeuten.

**Das Testdoppel ist weg.** `FalscherLauf` war eine eigene Klasse mit drei
Attributen, kannte nur Detroits Vokabular und waere beim Umbau gruen
geblieben - ein Doppel prueft, was man ihm beigebracht hat. Jetzt baut der
Test echte `manifeste.Lauf`-Objekte, und `test_nur_vollschnappschuesse_werden_verglichen`
laeuft ueber **beide** Staedte.

**Der Befund.** Das Paar 5.9./3.10. - 28 Tage - bringt 371 neu, 49 geaendert,
5 verschwunden, 1 beruehrt. Die Gegenprobe stimmt auf die Zeile: 371 - 5 = 366,
und genau 366 Zeilen mehr hat der neue Schnappschuss. **`verschwunden` hat
damit zum ersten Mal Belege** - fuenf Delikte, die Chicago aus dem Jahrgang
2024 entfernt hat.

Die beiden Staedte bewegen sich sichtbar unterschiedlich. Bei Detroit sind
78 % aller Feldbewegungen die drei Zeitstempel, und von den fachlichen 22 % ist
`case_status` allein 70 % - die Quelle fuehrt den Verfahrensstand nach. Bei
Chicago sind 62 % der Bewegungen fachlich, und sie sind Umklassierungen:
`arrest` 15-mal, davon **13-mal von `false` auf `true`** und zweimal zurueck -
ein Haftvermerk wird auch zuruckgenommen -, dazu `fbi_code`, `description`,
`iucr` und `primary_type`. Dass diese vier dieselbe Umklassierung beschreiben,
ist gemessen und nicht behauptet: Drei Delikte bewegten alle vier Felder, eines
drei von vier, keines nur eines.

Einmal bewegte sich der Tatzeitpunkt selbst - Chicago vom 12.5. auf den
4.1.2024, Detroit ein Fall um sieben Tage. Das betrifft jede Zeitreihe und
jede Monatszelle in Gold.

`location`, `latitude`, `longitude` und `_extra` ruehrten sich **nicht**.
Chicagos `rauschen` bleibt deshalb leer, und das ist ein Messergebnis:
`location` galt als Rauschkandidat, weil es die Koordinaten doppelt fuehrt.

**`notebooks/37_quellbewegung.ipynb`** fuehrt das alles vor - mit der
Gegenprobe gegen die Bronze-Manifeste, den Beispielen woertlich aus der
Tabelle, und einem Abschnitt, der die Grenzen ausdruecklich nennt: nur
Vollabzuege, nur was zwischen zwei Aufnahmen sichtbar ist, und zwei ungleiche
Fenster von sieben und 28 Tagen, aus denen sich keine Rate je Monat rechnen
laesst. Es steht in `BELEGEN` und laeuft im Datenlauf nach dem Bau; es sind
reine Abfragen, also Sekunden.

**Zahlen.** 1'483 -> **1'486 Tests**, Standardlauf 1'405. `docs/referenz/`,
`docs/feldkatalog.md` und die drei Architektur-SVGs neu gebaut - der
Importgraph hat mit `storage/parquet.py` ein Modul mehr.

---

## 03.10.2026 · Vier Jobs weniger, und ein Waechter, der ohne Daten nicht urteilt (direkt auf main)

**Der rote Lauf.** Seit dem 1. Oktober war CI auf jedem Pull Request rot, und
zwar an einer Stelle: `test_einstieg.py` meldete `2024-01-01` und `2024-12-31`
als Erzeugungszeitstempel auf der Einstiegsseite. Es ging zwei Tage als
"Actions gehen nicht" durch. Beide Daten sind aber die Jahresgrenzen der
Faktentabelle und kommen nachweislich aus dem Release - lokal stehen sie auf
der Erlaubnisliste, und der Test ist gruen.

Der Fehler lag im Waechter. Seine Erlaubnisliste entsteht erst aus dem
Release; `data/` ist nicht versioniert, ein frischer Klon hat also keines, und
dann ist die Liste leer und **jedes** Datum ein Fremdkoerper, auch das
richtige. Er ueberspringt sich jetzt mit `kein Release - die Erlaubnisliste
waere leer`, so wie drei andere Tests derselben Datei es schon taten. Geprueft
wird damit dort, wo die Daten liegen: auf dem eigenen Rechner und im
Datenlauf. Beide Richtungen sind belegt - mit Release prueft er, ohne Release
ueberspringt er.

**Der Zuschnitt der Actions.** Bis heute lief eine Matrix aus zwei
Betriebssystemen und zwei Python-Versionen, dazu ruff und der Referenzbau:
sechs Jobs, rund **34 verrechnete Minuten** je Lauf. Windows wird zum
doppelten Satz abgerechnet und brauchte doppelt so lange wie Linux - allein
die beiden Windows-Jobs waren 26 dieser 34 Minuten. Am 1. Oktober liefen acht
Laeufe, also etwa 270 Minuten an einem Tag. Seit dem 21.9. weist GitHub den
Wochenlauf mit *"The job was not started because recent account payments have
failed or your spending limit needs to be increased"* ab; er scheiterte
zweimal nach drei Sekunden, ohne je zu starten. Dass dabei ein Schluessel
fehle, war eine Fehldiagnose: `CENSUS_API_KEY` liegt seit dem 13.9. als Secret
vor.

Drei Jobs statt sechs:

| Job | Wann | Verrechnet |
| --- | --- | ---: |
| `pruefung` - Linux 3.11, aus den Bereichen, ruff vorangestellt | jeder Pull Request und Push | ~4 |
| `windows` - Windows, Lockfile-Stand 3.13 | nur Push auf main | ~13 |
| `kanarienvogel` - Linux, `3.x` | woechentlich, darf rot werden | ~3 |

Ein Pull Request kostet damit **vier statt vierunddreissig** Minuten.

Was jeder Job traegt, und warum nicht anders: Linux **3.11** installiert aus
den Bereichen in `pyproject.toml` - das Lockfile kann es nicht, numpy 2.5
verlangt 3.12 - und ist damit der einzige Beleg, dass die Zusage
`requires-python = ">=3.11"` noch stimmt. Linux, weil die drei
PDF-Reproduktionen gegen `poppler-utils` definiert sind und sich anderswo
ueberspringen. `ruff` im selben Job statt in einem eigenen: vierzehn Sekunden
werden sonst als ganze Minute verrechnet. Windows nur auf main - es hat genau
einen Fehler gefunden, den `\r`-Fehler in beiden PDF-Werkzeugen, und das
rechtfertigt keine dreizehn Minuten je Push. Der Kanarienvogel haelt die
Zusage nach oben offen ehrlich: `pyproject.toml` nennt keine Obergrenze, und
genau das war der Zustand, in dem Python 3.14 mit `\z` statt `\Z` die S3-Seite
des hybrid-Modus still null Laeufe finden liess. Er loest absichtlich auf die
neueste Fassung auf und darf rot werden, ohne dass jemand etwas geaendert hat.

Der Job `referenz` faellt weg. Er baute die Code-Referenz und haengte sie als
Artefakt an - aber `docs/referenz/` ist versioniert, das Artefakt war eine
Kopie dessen, was ohnehin im Repository liegt, und die Tests bauen es auf
jedem Pull Request zweimal.

**Zahlen.** Die Differenz zwischen Standardlauf und ganzer Suite stand noch
als `40` in `ln1_konzept.md` und als `658 von 698` im Kopf von
`datenlauf.yml`; richtig sind **1'401 von 1'482**, also 81. 1'476 -> **1'482
Tests** durch den neuen Waechter unten.

`projektabsprache.md` nennt weiterhin 633 Tests, und das ist richtig: Das
Papier ist ein Schnappschuss der Abstimmung, kein mitwachsendes Dokument.
Falsch war seine Stichtagszeile - sie behauptete, **alle** Zahlen seien am
6. September erhoben, waehrend das Papier ausdruecklich datierte `Nachtrag`-
und `Nachgemessen`-Bloecke bis zum 20. September traegt. Sie sagt das jetzt:
Grundstand 6. September, Spaeteres mit eigenem Datum, dazu der Verweis auf den
Kopfabschnitt von `AENDERUNGEN.md` fuer die laufenden Zahlen. Die Zahl zu
aendern haette das Papier nur anders falsch gemacht.

**Und ein Waechter dafuer.** Dass diese Zeile zwei Wochen zurueckhing, hat
kein Test gesehen - sie ist keine Zahl, sondern ein Satz ueber Zahlen.
`tests/test_projektabsprache.py` prueft jetzt die eine nachpruefbare Zusage
darin: dass das genannte juengste Datum das juengste ist. Dazu, dass jeder
`Nachtrag`-Marker ein lesbares Datum traegt, dass keiner vor dem Grundstand
liegt, dass alle im selben Jahr liegen - sonst waere `vom 20. September` ohne
Jahresangabe nicht eindeutig - und dass das Muster ueberhaupt etwas findet.
Diese letzte Probe ist die Lehre vom 19.9.: Ein Muster, das nach einem Umzug
nichts mehr trifft, laesst den Vergleich auf zwei leere Mengen fallen und
bleibt gruen.

Vorgefuehrt statt behauptet: Gegen vier veraenderte Fassungen des Papiers -
Zeile nennt das alte Datum, neuer Nachtrag ohne Nachziehen, Nachtrag ohne
Datum, Zeile ganz entfernt - wird der Waechter rot; gegen das echte Papier
gruen. Der Marker `referenzstand` fehlt ihm absichtlich: Er haelt Prosa gegen
Prosa, braucht keine gebauten Daten und soll deshalb auf jedem Pull Request
laufen.

---

## 03.10.2026 · Die Hive-Falle hat jetzt eine Stelle statt drei Kommentare (direkt auf main)

DuckDB leitet aus einem Pfad im Hive-Muster Spalten ab, die in keiner Datei
stehen: unter `dataset=fact_offense/release=.../part-0001.parquet` ergaenzt
`DESCRIBE SELECT *` die Spalten `dataset` und `release`. Dreimal in zwei
Wochen hat das etwas kaputt gemacht - `load_elasticsearch` haette zwei Felder
zu viel abgebildet, die Einstiegsseite zeigte je Datensatz **24 statt 22**
Spalten, und beim Anhaengen in `build_source_change` passten die Spaltenzahlen
nicht mehr. Behoben wurde es jedes Mal an der betroffenen Stelle, mit
demselben Kommentar daneben. Drei Kommentare sind kein Schutz, sondern drei
Gelegenheiten, den vierten zu vergessen.

`storage.parquet` ist diese eine Stelle: `parquet_schema` und
`parquet_spalten` lesen das Arrow-Schema der Datei, nicht eine Abfrage
darueber. Die Begruendung steht einmal im Modulkopf; `load_clickhouse.felder`,
`load_elasticsearch.felder` und `tools/build_einstieg.messe` verweisen nur
noch darauf.

`silver_pipeline.schema_of` bleibt unveraendert. Es faehrt `DESCRIBE` ueber
Relationen mit ausgeschriebenen Spalten, und ein Vergleich der gebauten
Manifeste gegen die Arrow-Schemata zeigt beidseitig dieselben Spalten -
`crime_offense` 27 zu 27, `weather_day` 11 zu 11. Die Falle hat nur
`SELECT *`.

**Was der neue Waechter prueft.** `tests/storage/test_parquet.py` haelt beide
Seiten fest: dass der Helfer die Spalten der Datei nennt, und dass `DESCRIBE`
sie weiterhin dazuerfindet - mit Einzelpfad wie mit Dateiliste. Faellt die
zweite Haelfte eines Tages, hat DuckDB sich geaendert, und dann gehoeren die
Warnungen nachgezogen statt der Test angepasst. Eine Warnung vor einer Falle,
die es nicht mehr gibt, ist genauso irrefuehrend wie keine.

**Zahlen.** 1'470 -> **1'476 Tests**. `docs/referenz/` neu gebaut (43 Seiten),
weil `storage/parquet.py` hinzukommt.

---

## 01.10.2026 · Was die Quelle geändert hat, steht jetzt in einer Tabelle (#126)

`docs/intern/datenhistorie.md` rechnete am 16.9. vor, was beim Aufraeumen
verlorengeht: **31,9 MB Schnappschuesse fuer 102 geaenderte Zeilen.** Die
Bewegung der Quellen - Detroit aendert Eintraege noch Jahre nach der Tat - ist
selbst ein Gegenstand, und sie steckte nur implizit in den Bronze-Laeufen.

`silver_pipeline.build_source_change` zieht sie heraus:
`silver/dataset=source_change`, **append-only**, eine Zeile je geaendertem
Feld. Aus den fuenf vorhandenen Detroit-Schnappschuessen sind das **4'292
Zeilen** ueber vier Paare, in 1,3 Sekunden.

**Die Messungen des Papiers wurden nachgerechnet und stimmen** - Zeile fuer
Zeile: 102 mit echter Inhaltsaenderung, 147 nur `updated_at` bewegt, und je
Feld 249 / 121 / 89 / 14 / 1 sowie zehn echte Beschreibungsaenderungen. Ein
Waechter mit dem Marker `referenzstand` haelt das fest. Das Papier hatte von
Hand gemessen; jetzt misst der Code dasselbe.

**Was ohne Normalisierung passiert waere.** `ESRI_OID` ist die Zeilennummer
der ArcGIS-Antwort und bewegt sich bei **88'677 von 88'685** Zeilen; 150 von
160 Beschreibungsaenderungen waren reine Leerzeichen. Faktor **870** Rauschen,
in dem die hundert echten Aenderungen nicht zu finden sind.

**Eine Mehrdeutigkeit im Papier war aufzuloesen.** Abschnitt 5.1 nennt die
Option *"ohne Zeitstempel"*, begruendet die Empfehlung aber damit, dass eine
nur beruehrte Zeile "eine eigene Beobachtung" sei. Beides zusammen geht nicht.
Aufgeloest: Zeitstempel zaehlen nicht als Inhaltsaenderung, werden aber
aufgezeichnet, und eine Zeile, an der sich nur sie bewegt haben, traegt
`art = 'beruehrt'`. Davon gab es im ersten Paar 147.

**Das Aufraeumen kennt die Tabelle jetzt.** Neue Regel: Ein Vollschnappschuss,
dessen Unterschied noch nicht gezogen ist, bleibt stehen. Sie steht am
**Ende** der Kette, und das ist Absicht - sie ist die einzige Regel, die von
allein vergeht. Stuende sie weiter vorn, verdeckte eine voruebergehende
Bedingung die dauerhafte, und ein Lauf saehe nach *"einmal ziehen, dann darf
es weg"* aus, wo in Wahrheit ein Delta darueber haengt.

**Zwei Fehler beim Bauen, beide lehrreich.**

1. **Ein Paar ohne Aenderung war nicht von einem ungeprueften zu
   unterscheiden.** Zwischen den beiden Schnappschuessen vom 18.9. (07:51 und
   11:02) hatte sich in drei Stunden nichts bewegt - also schrieb der
   Vergleich keine Zeile, und die neue Aufraeumregel haette die beiden Laeufe
   **fuer immer** gesperrt. Jetzt traegt ein solches Paar eine Markierungszeile
   mit `art = 'unveraendert'`, und das ist selbst eine Beobachtung.
2. **Zum dritten Mal in zwei Wochen die Hive-Spalten.** Beim Anhaengen an den
   Bestand passten die Spaltenzahlen nicht: DuckDB leitet aus dem Pfad
   `dataset=source_change` eine Spalte `dataset` ab, die in keiner Datei
   steht. Dieselbe Falle traf am 28.9. `load_elasticsearch` (dort als Warnung
   im Docstring festgehalten) und am 1.10. die Einstiegsseite, wo sie zwei
   Spalten zu viel anzeigte. Konsequenz hier: Die Spalten stehen ausgeschrieben
   in `SPALTEN`, kein `SELECT *`.

**Fuer die Analyse bereit, ohne Zusatzcode.** `build_analysis_db` findet
Silver-Tabellen von selbst; `source_change` ist damit sofort in DuckDB
abfragbar. Erste Befunde: `3072 -> 3002` ist mit 43 Faellen die haeufigste
Umcodierung - genau der Code, den das Papier mit 1'404 Anklagen und
`mapping_status = ambiguous` markiert hat. Und es gibt deutliche
Umklassierungen, etwa 43-mal von Koerperverletzung auf Sachbeschaedigung.

**Offen und draengend.** Papier 5.2 empfahl einen Vollschnappschuss je Stadt
und Monat. Nicht umgesetzt: `run_all` laedt Detroit mit `--mode delta`. **Nach
den fuenf vorhandenen Schnappschuessen entsteht kein neues Vergleichspaar
mehr** - die Tabelle hoert auf zu wachsen, nicht weil sich nichts aendert,
sondern weil wir nicht mehr hinsehen.

**Zahlen.** 1'445 → **1'470 Tests**.
## 01.10.2026 · Die Einstiegsseite — eine Datei, kein Dienst (#127)

Wer ankommt, will wissen: Was liegt hier, und wo frage ich es? Das brauchte
bisher jemanden, der es erklaert. `tools/build_einstieg.py` schreibt
`docs/einstieg.html` - **erzeugt, nicht gepflegt.** Dieselbe Bauart wie
`build_referenz.py` und `build_architekturbilder.py`.

Kein zusaetzlicher Dienst: Die Frage *"was liegt hier?"* braucht keinen
laufenden Prozess, sondern eine Antwort, die stimmt. Auf der Seite stehen
Release-Kennung, Vertragsversion und Code-Verweis, die Datensaetze mit Zeilen-
und Spaltenzahlen, die Kennzahlen beider Staedte, die Gueteziffern gegen die
Schwellen des Publish-Gates, und die drei Zugaenge mit je einem Beispiel.
**Jede Zahl wird beim Erzeugen gemessen.**

**Kein Zeitstempel - und das ist die Entscheidung, die die Seite traegt.** Ein
*"zuletzt erzeugt am ..."* waere verlockend und machte zwei Laeufe
unvergleichbar; ein festgehaltener Dienstzustand waere schlimmer: eine Seite,
die behauptet, Kibana laufe, weil es vor drei Tagen lief. Fuer alles Lebendige
nennt sie den Befehl (`serving.pruefe_stand`) statt eines Ergebnisses von
gestern. Ein Test prueft, dass **kein** Datum darauf steht, das nicht aus dem
Release kommt.

**Die Rate je 1'000 ist nicht neu erfunden.** Sie kommt aus derselben Abfrage,
mit der `tests/test_aenderungen.py` die Zahl hier im Protokoll bewacht. Eine
zweite Definition waere eine zweite Wahrheit.

**Was beim Bauen schiefging, und was es lehrt.** Die erste Fassung zeigte
ueberall **zwei Spalten zu viel** - 24 statt 22 bei `fact_offense`. Ursache:
`DESCRIBE SELECT * FROM read_parquet(...)` zaehlt die Hive-Spalten mit, die
DuckDB aus dem Pfad ableitet, und im Release sind das **zwei**: `dataset` und
`release`. Der Docstring von `load_elasticsearch.felder` warnt seit dem 28.9.
genau davor - und zwar vor der ersten; die zweite steuert das
Release-Verzeichnis bei. Jetzt kommt die Spaltenzahl aus dem Arrow-Schema, und
ein Waechter rechnet sie gegen die Dateien nach.

Ausserdem gefunden und behoben: kleingeschriebene Staedtenamen in einer von
zwei Tabellen, `0,0 MB` fuer alles unter 50 KB (jetzt `< 0,1`), zwei
abgeschnittene Beispielabfragen, eine unsinnige CSS-Regel.

**Zahlen.** 1'435 → **1'445 Tests**.

---

## 01.10.2026 · Vier Orte, und niemand verglich sie (#124)

Es gibt inzwischen vier Stellen, die behaupten, die Daten zu zeigen: die
Arbeits-Gold-Schicht (auf der die DuckDB-Sichten liegen), ClickHouse,
Elasticsearch und die Kibana-Dashboards. Jede prueft sich **beim Laden** gegen
das Release. Danach prueft niemand mehr, ob sie noch dasselbe sagen.

Das Szenario ist nicht ausgedacht: Ein neues Release entsteht, ClickHouse wird
nachgezogen, Elasticsearch vergessen. Die Dashboards zeigen weiter den alten
Stand - ohne Hinweis, weil der Alias brav irgendwohin zeigt und alle Zahlen in
sich stimmig sind. **Jede Stelle ist konsistent, und das Ganze ist falsch.**

`serving.pruefe_stand` stellt eine Frage an alle vier und nimmt das Release als
Massstab. Dass jede Tabelle und jeder Index die Release-Kennung im Namen
traegt, war bisher Lesbarkeit; jetzt ist es die Grundlage der Antwort.

Vorgefuehrt: Alias auf einen alten Index umgelegt, Werkzeug gelaufen -
*weicht ab, z.B. fact_offense-19990101t000000z*, Rueckgabewert 1, mit dem
Befehl, der es zusammenbraechte. Zurueckgelegt, wieder gruen.

**Was das Werkzeug gefunden hat, bevor es fertig war.** Drei Fehler, alle in
Sachen, die seit Tagen als erledigt galten:

1. **Der Compose-ClickHouse war unbenutzbar.** Der Einstiegspunkt meldet
   *"neither CLICKHOUSE_USER nor CLICKHOUSE_PASSWORD is set, disabling network
   access for user 'default'"* - der Dienst antwortete nur von innen. Der
   Healthcheck merkte nichts davon, weil `/ping` keine Anmeldung braucht: Der
   Container stand auf **healthy** und war trotzdem nicht ansprechbar. Behoben
   mit `CLICKHOUSE_SKIP_USER_SETUP`.
2. **`load_clickhouse` war nicht wiederholbar.** `CREATE TABLE IF NOT EXISTS`
   plus bedingungsloser Insert heisst: Ein zweiter Lauf fuegt ein zweites Mal
   ein. Aus 345'073 Zeilen wurden 690'146. Aufgefallen ist das, als ein Lauf
   nach einem gescheiterten Abgleich wiederholt wurde - also genau dann, wenn
   man es am wenigsten gebrauchen kann. Jetzt `CREATE OR REPLACE TABLE`, das
   ClickHouse atomar ausfuehrt.
3. **Die Zahlen kamen als Text.** ClickHouse liefert `UInt64` in JSON je nach
   Einstellung als `"345073"` statt `345073`; JSON kann 64 Bit nicht
   verlustfrei als Zahl. Unter `:latest` ging es gut, unter dem in
   `docker-compose.yml` gepinnten **24.8** schlug jeder Abgleich an, obwohl
   nichts fehlte. Der Testklient verliess sich auf eine Servervoreinstellung;
   die Fassung im Modul setzt sie ausdruecklich.

**Und die Fehlermeldung stuerzte dabei selbst ab.** `f"{wert:,}"` wirft bei
allem, was keine Zahl ist - die Meldung ueber einen Abgleichsfehler war also
genau dann unbrauchbar, wenn die Abweichung der *Typ* war. Jetzt nennt sie
Wert und Typ, und das war es, was den Fehler sichtbar machte.

**Der ClickHouse-Klient ist ins Modul gezogen.** Bis hierher weigerte sich
`load_clickhouse.main`, ohne `--trocken` zu laufen: Ein Klient werde gereicht
und nicht gebaut. Als Trennung gedacht, hiess das praktisch, dass das Modul
seine eigene Aufgabe nicht erledigen konnte und jeder Aufrufer denselben
Klienten neu schrieb - der Test tat es, `pruefe_stand` haette es wieder getan.
`python -m serving.load_clickhouse` laeuft jetzt zum ersten Mal durch; das
Release liegt dafuer lesend in ClickHouses `user_files`.

**Nebenbei: die Ports haengen jetzt an 127.0.0.1.** Keiner dieser drei Dienste
verlangt eine Anmeldung, und Docker schreibt seine Weiterleitungen an der
Rechnerfirewall vorbei.

**Zahlen.** 1'404 → **1'435 Tests**.

---

## 28.09.2026 · Kibana, und die Dashboards stehen als Code (#123)

Ein im Browser zusammengeklicktes Dashboard lebt in Kibanas eigenem Index. Es
laesst sich nicht lesen, nicht vergleichen, nicht begruenden, und es ist weg,
sobald jemand den Container neu aufsetzt. Alles andere in diesem Projekt ist
reproduzierbar; das waere die eine Stelle, an der man sich auf einen Zustand
verlaesst, den niemand nachbauen kann.

`serving/build_kibana` beschreibt die Dashboards deshalb und legt sie ueber die
Saved-Objects-Schnittstelle an. **Drei Bretter, 13 Tafeln, 17 Objekte.**

**Eine Beschreibung, zwei Darstellungen.** Jede `Tafel` sagt einmal, was sie
zeigt. Daraus entsteht beides: das Lens-Dokument fuer Kibana **und** die
gleichwertige Elasticsearch-Abfrage. Ein Test stellt sie wirklich und prueft,
dass etwas zurueckkommt. Damit ist nicht nur belegt, dass das JSON angenommen
wurde, sondern dass die Tafel auch etwas anzeigen *kann* — ein Dashboard, das
sauber importiert und leer bleibt, ist bei erzeugten Dashboards der Normalfall.

**Die erste Datei mit Docker.** Bis hierher liefen ClickHouse und
Elasticsearch von Hand gestartet, und das ging, solange sie nichts voneinander
wollten. Kibana will: Es braucht Elasticsearch unter einem aufloesbaren Namen,
und auf Dockers Standardbruecke gibt es keine Namensaufloesung. Ein Netz, das
jemand von Hand anlegt, ist genau die Voraussetzung, die beim Nachbauen fehlt —
also `docker-compose.yml`, mit allen drei Diensten und benannten Volumes.

**Was Kibana nicht prueft, und wir jetzt schon.**

- *Das Zeitfenster.* Kibana zeigt beim Oeffnen die letzten 15 Minuten; unsere
  Daten enden 2024. Ohne `timeRestore` oeffnet sich jedes Dashboard leer, und
  nichts deutet darauf hin, dass nur der Zeitraum falsch steht. Das Fenster
  kommt aus dem Release.
- *Gruppieren auf `text`.* `source_offense_description` liegt als `text` mit
  `.keyword`-Unterfeld. Eine Tafel, die das Feld direkt gruppiert, importiert
  anstandslos und bleibt leer. Ein Test haelt die Entscheidung gegen die echte
  Abbildung im Index — und prueft auch die Gegenrichtung, damit niemand
  vorsorglich ein `.keyword` an ein Feld haengt, das schon `keyword` ist.
- *Verweise ins Leere.* Kibana legt ein Dashboard auch dann an, wenn seine
  Tafeln fehlen; beim Oeffnen steht dann *Could not locate that panel*.
- *Kacheln, die nichts anzeigen.* Ein XY-Diagramm zeigt genau einen
  Gruppierungs- und einen Aufteilungsverweis. Eine dritte Gruppierung laege in
  den Spalten und wuerde nirgends verwendet.

**Zwei Fehler im eigenen Entwurf, gefunden am Bild.**

1. Drei Bretter haben je eine Tafel `gesamt`, zwei davon heissen verschieden —
   *Delikte insgesamt* und *Treffer*. Ohne den Brettnamen in der Kennung
   ueberschrieb das letzte Anlegen die anderen. Jetzt traegt jede Kennung ihr
   Brett, und ein Test haelt die Eindeutigkeit fest.
2. Der Tagesverlauf war nach Haeufigkeit sortiert (0, 12, 17, 16, …) und damit
   eine Rangliste statt eines Verlaufs. `Eimer` kennt jetzt eine Ordnung, und
   sie gilt in beiden Darstellungen gleich.

**`unique_count` schaetzt.** Kibana setzt es auf `cardinality` um, und das ist
HyperLogLog — bis zur Genauigkeitsschwelle exakt, darueber ungefaehr, ohne dass
die Kachel es sagt. Die Schwelle wird jetzt gesetzt statt der Voreinstellung
ueberlassen. Gemessen liegen die beiden Kacheln bei **1'146** Tracts und
**429** Quellcodes, weit darunter.

**Die Bilder entstehen, statt abgelegt zu werden.**
`tools/build_dashboardbilder.py` fotografiert die laufenden Dashboards nach
`docs/bilder/`. Ein Werkzeug und kein Test: Es braucht die Dienste, geladene
Daten und einen Chrome, und das gehoert in die Hand dessen, der die Abgabe
baut. Kibanas eigene Bildausgabe (*Reporting*) braucht eine kostenpflichtige
Lizenz.

**Der README kannte die Analyseplattform bisher gar nicht** — auch ClickHouse
nicht. Abschnitt 2.6 traegt sie jetzt nach, mit Ports, Zusagen und der
Begruendung, warum die Ports verschoben sind.

**Zahlen.** 1'353 → **1'404 Tests**. Der Standardlauf sammelt davon **1'327**;
das Konzept nennt beide.

---

## 28.09.2026 · Elasticsearch neben ClickHouse — für die Fragen, die SQL schlecht stellt (#122)

Zwei Kopien derselben Daten sind ein Fehler, solange beide dasselbe können.
Diese kann etwas anderes, und das ist gemessen und nicht behauptet:

- **Volltext.** `source_offense_description` trägt **421** verschiedene
  Beschreibungen. Wer „explosive" sucht, findet in Elasticsearch **12** Fälle
  über **drei** Beschreibungen hinweg, ohne eine davon zu kennen. In ClickHouse
  wäre das `LIKE '%EXPLOSIVE%'` über 345'073 Zeilen.
- **Umkreis.** **342'727** der 345'073 Zeilen tragen Koordinaten. *Alle Delikte
  im Umkreis von 500 m* ist eine `geo_distance`-Zeile — im Chicagoer Loop sind
  das **3'394**. Genau diese Frageform braucht eine Wirkungsanalyse zu einer
  ortsgebundenen Massnahme.

**Drei Indizes, nicht fünf.** `dim_date` (Kalender) und `dim_city_day`
(Wetterzahlen) tragen weder Text noch Ort. Sie liegen in ClickHouse und
gehören nicht ein zweites Mal abgelegt — dasselbe Argument, mit dem
`serving/__init__` gegen materialisierte Tabellen argumentiert.

**Dieselbe Zusage wie bei ClickHouse.** Geladen wird in einen Index, dessen
Name das Release trägt; erst nach bestandenem Abgleich zeigt der **Alias**
darauf. Elasticsearch legt einen Aliaswechsel atomar um, wenn Entfernen und
Hinzufügen in einem Aufruf stehen.

**Eindeutigkeit wird erzwungen statt geschätzt.** Elasticsearch hat keine
exakte Zählung verschiedener Werte — `cardinality` schätzt (HyperLogLog) und
trägt keinen Nachweis. Stattdessen ist der Schlüssel die Dokumentkennung: Zwei
gleiche Schlüssel ergeben ein Dokument, und die Zeilenzahl fällt. Die
Zeilenprüfung **ist** damit die Schlüsselprüfung. Ein Test hält das fest.

**Was der Lauf gegen einen echten Dienst gefunden hat.** Das Testdoppel hatte
`GET /_alias/<name>` als gutmütig nachgebildet. Der echte Dienst antwortet mit
**404**, solange der Alias nicht existiert — also beim allerersten Laden immer,
und `ignore_unavailable` hilft dort nicht, es gilt für fehlende Indizes.
Gefragt wird deshalb die Gesamtliste und in Python gefiltert. Dieselbe Lehre
wie beim ClickHouse-Teil: Ein Doppel prüft, was man ihm beigebracht hat.

**Gemessen statt angenommen.** Kein einziger der 345'073 Zeitstempel trägt
Bruchteile einer Sekunde. Elasticsearchs `date` löst Millisekunden auf und
verliert hier also nichts — aber das ist eine Messung und keine Eigenschaft der
Welt, und deshalb hält `pruefe_zeitgenauigkeit` sie fest, statt sie zu glauben.

**Der Lauf.** 351'440 Dokumente in drei Indizes, in 10 Sekunden, jeder gegen
das Release abgeglichen (Zeilen, Schlüssel, Verteilung). Release
`2026-09-21T12-55-05Z`, unverändert — es wurde nichts neu gebaut.

**Nebenbei richtiggestellt.** Konzept 10 versprach, `python -m pytest` liefere
die Gesamtzahl. Der Standardlauf wählt die Referenzwächter ab und sammelt
**1'276** von 1'353; die Zeile nennt jetzt beide.

**Zahlen.** 1'322 → **1'353 Tests**.

---

## 22.09.2026 · Ein Pfadmuster fand unter Python 3.14 keinen einzigen Lauf (direkt auf main)

Zehn Tests in `tests/storage/` wurden auf meiner Maschine rot, auf einem
sauberen `main` und ohne dass jemand Code angefasst hätte. Die Ursache lag
nicht im Projekt, sondern eine Schicht darunter.

`glob_regex` in `storage/backend.py` baut aus einem Muster wie
`**/run_*/manifest.json` einen regulären Ausdruck — Segment für Segment, und
jedes Segment über `fnmatch.translate`. Das hängt an jedes Ergebnis einen Anker
für das **Stringende**. Der musste weg, sonst stünde mitten im Pfadmuster ein
Stringende; die Zeile schnitt dafür ein `\Z` ab.

**Python 3.14 schreibt `\z`.** Kleingeschrieben. Das Abschneiden griff nicht
mehr, der Anker blieb stehen:

```
^(?s:station=[^/]*)\z/(?s:run_[^/]*)\z/(?s:manifest\.json)\z$
```

Ein Stringende vor einem `/` ist eine Bedingung, die nichts erfüllt. Jedes
Muster mit einem Platzhalter in einem **nicht letzten** Segment traf ab da auf
gar nichts. Muster, deren einziger Platzhalter hinten stand, liefen weiter —
deshalb fielen von acht Glob-Fällen genau fünf um und nicht alle.

`Storage.laeufe` und `list_files` schicken jeden S3-Schlüssel durch diesen
Filter. Die S3-Seite des `hybrid`-Modus fand damit **null Läufe**, still und
ohne Fehlermeldung: leere Listen, ein `KeyError: 'fact_offense'`, ein
„Kein vollständiger Bronze-Lauf". Alle zehn roten Tests hingen an dieser einen
Zeile.

Sie schneidet jetzt beide Schreibweisen ab.

### Ändern sich dadurch die Zahlen? Nein — nachgemessen, nicht angenommen

Auf 3.12 und 3.13 erzeugen alte und neue Fassung **byte-identische** Ausdrücke;
für `run_*`, `manifest.json`, `**`, `dataset=*`, `a*b*c` und `*` einzeln
verglichen. `fnmatch.translate` liefert dort ausschliesslich `\Z`, und genau
das schnitt die alte Zeile ab. Der Unterschied besteht allein unter 3.14, und
dort nur zwischen „kaputt" und „richtig".

Die volle Testsuite gegen drei Interpreter:

| | Suite | `referenzstand` |
| --- | ---: | ---: |
| 3.12.8 | 1'214 grün | 75 grün |
| 3.13.0 | 1'215 grün | 75 grün |
| 3.14.6 | 1'214 grün | 75 grün |

3.13 zählt einen Test mehr, weil `test_ein_zweiter_lauf_liefert_dieselben_dateien`
nur dort läuft — die Marke in `docs/referenz/erzeugt-mit.json` nennt 3.13, und
unter 3.14 überspringt sich der Test.

Alle Zahlen der Abgabe entstanden unter 3.13. Sie gelten unverändert für
Release `2026-09-21T12-55-05Z`.

### Zwei Dinge, die dabei sichtbar wurden

**Die API-Referenz war überholt**, sobald die Zeile geändert war — der Wächter
auf 3.13 hat es gefangen, `docs/referenz/` ist neu gebaut (drei Dateien,
Zeilennummern und die neue Konstante). Unter 3.14 hätte niemand es gemerkt:
Dort überspringt sich derselbe Wächter.

**Getestet wird, was nicht zugesagt ist.** `pyproject.toml` sagt
`requires-python = ">=3.11"` ohne obere Grenze; die CI-Matrix fährt `3.11` und
`3.13`. 3.14 ist damit eine Version, die das Projekt verspricht und nie prüft —
weshalb dieser Fehler auf jeder Maschine grün war ausser meiner.

---

## 22.09.2026 · Auch die vier Dimensionen kommen nach ClickHouse (direkt auf main)

Das Modul war auf `fact_offense` verdrahtet. Jetzt trägt es fünf `Ziel`-Sätze —
je Tabelle Sortierung, Schlüssel, Verteilung für den Abgleich, optional
Partitionierung und `LowCardinality`.

### Was der Versuch mit ClickHouses eigener Ableitung gezeigt hat

Die Dimensionen von Hand über `CREATE TABLE … AS SELECT * FROM file(…)` zu
laden lief **sofort in denselben Fehler**, den `ddl()` abfängt: *Sorting key
contains nullable columns*. Parquet meldet alles als nullbar, also auch jeden
Sortierschlüssel. Man kommt mit `assumeNotNull()` durch — und hat dann eine
Tabelle, die nicht sagt, welche Spalten wirklich leer sein dürfen.

### Drei Entscheidungen, die nicht ableitbar sind

**`LowCardinality` nur für die grossen zwei.** Bei 85 Zeilen (`dim_offense`),
366 (`dim_date`) oder 732 (`dim_city_day`) ist das Wörterbuch teurer als der
Text. Nur `fact_offense` und `dim_tract` tragen welche.

**Die Verteilung meidet Wahrheitswerte.** DuckDB liefert `True`, ClickHouse
über TSV `1` — der Abgleich schlüge an, ohne dass etwas fehlt. Deshalb nur Text
und ganze Zahlen.

**`dim_tract` gruppiert über `(state_fips, county_fips)`, nicht über `city`.**
Letzteres trägt bei 5'227 der 6'282 Tracts NULL, und wie zwei Engines NULL
sortieren, ist nichts, worauf ein Nachweis ruhen sollte.

### Der Schlüssel darf zusammengesetzt sein

`dim_city_day` hat 732 Zeilen, aber nur 366 verschiedene Daten — über `date`
allein hätte der Abgleich die Hälfte nicht geprüft. Der Schlüssel ist jetzt ein
Tupel, gezählt über `count(DISTINCT (a, b))` beziehungsweise `uniqExact(a, b)`.

### Und ein Fehler, der genau die Warnung war, die ich selbst gegeben hatte

Der erste Ladelauf von `dim_tract` scheiterte am Abgleich: *`('17', '001', 19)`
fehlt in ClickHouse*. Nichts fehlte. Mein HTTP-Klient las TSV und verwandelte
alles Ziffernförmige in `int` — aus County `'001'` wurde die Zahl `1`. Genau
die führenden Nullen, vor denen Projektabsprache Punkt 2 warnt und die ich zwei
Antworten zuvor als Elasticsearch-Falle beschrieben hatte.

Behoben mit `FORMAT JSONCompact`, das die Typen mitliefert. Das `Klient`-
Protokoll sagt jetzt ausdrücklich, dass `abfrage` Werte mit ihrem Typ
zurückgeben muss — wer TSV liest und rät, baut sich diesen Fehler ein.

### Geladen und geprüft

Gegen ClickHouse 26.9.1, aus Release `2026-09-21T12-55-05Z`:

| Ziel | Zeilen | Schlüssel | Spalten |
| --- | ---: | ---: | ---: |
| `fact_offense` | 345'073 | 345'073 | 22 |
| `dim_offense` | 85 | 85 | 11 |
| `dim_tract` | 6'282 | 6'282 | 14 |
| `dim_date` | 366 | 366 | 11 |
| `dim_city_day` | 732 | 732 | 11 |

Alle fünf Abgleiche bestanden, alle fünf Sichten umgelegt, zusammen unter einer
Sekunde.

### Ein Mangel in den eigenen Integrationstests

Nach dem Laden aller fünf war die Sicht `fact_offense` plötzlich weg — die
Dimensionen standen, die Fakten nicht. Ursache: Die beiden Integrationstests
liefen in `default` und räumten im `finally` `DROP VIEW fact_offense` auf.
`sicht_umlegen` benennt die Sicht immer nach dem Ziel, also legen sie dieselbe
Sicht an wie ein echter Ladelauf — **und löschen beim Aufräumen eine, die ihnen
nicht gehört.**

Auf einem ClickHouse, das einen echten Stand bedient, hätte ein Testlauf ihn
abgeschaltet. Behoben: Jeder Test bekommt eine eigene Datenbank
(`pruefung_<zufall>`), die danach ganz verschwindet. `default` bleibt unberührt
— nachgeprüft.

**Zahlen.** 1'317 → **1'322 Tests**.

---

## 22.09.2026 · Der erste Schritt zur Analyseplattform: ClickHouse (direkt auf main)

`serving/load_clickhouse.py`. Noch kein Docker, keine laufende Datenbank — der
Teil, der die Arbeit macht: DDL und Ladeschicht für `fact_offense`.

### Die Zusage, die nicht verlorengehen darf

Alles bis hierher ruht auf unveränderlichen Läufen: Ein Stand ist ganz da oder
gar nicht. Eine Datenbank kennt das nicht. Deshalb lädt das Modul **nie** in
`fact_offense`, sondern in `fact_offense_<Release>`, prüft, und legt erst dann
die Sicht darauf um. Fällt die Prüfung, bleibt der alte Stand stehen — dieselbe
Zusage wie beim `.part`-Umbenennen in `storage`.

### Abgelesen gegen entschieden

Die Spaltenliste kommt aus dem Parquet des Releases, damit eine neue
Gold-Spalte nicht stillschweigend fehlt. Entschieden sind Sortierung,
Partitionierung und `LowCardinality`. Ein Test hält beides gegeneinander: Für
jede Spalte muss ein Typ entschieden sein, sonst bricht der Bau — statt zu
raten.

### Drei Dinge, die erst beim Bauen auffielen

**Parquet markiert jede Spalte als nullbar.** Übernähme man das, wären alle 22
Spalten `Nullable` — gemessen sind es **acht**. Die Nullbarkeit wird jetzt
gezählt, nicht geglaubt.

**`nibrs_code` trägt drei NULL** (die unmapped-Zeilen aus Chicago) und wäre der
natürliche dritte Sortierschlüssel gewesen. Ein nullbarer Sortierschlüssel
verlangt in ClickHouse `allow_nullable_key`. Drei Zeilen von 345'073 sind
diesen Schalter nicht wert; die Sortierung ist `(reporting_city, date)`, und
`ddl()` weist zurück, wenn eine Schlüsselspalte NULL bekommt.

**`Nullable(LowCardinality(String))` verweigert ClickHouse** — die Schachtelung
muss andersherum. Fällt ohne laufende Datenbank nicht auf; ein Test hält es
jetzt fest.

### Der Abgleich

Zeilenzahl, `count(distinct offense_id)` und die Verteilung über Stadt ×
`mapping_status` × `geo_status`. Eine Prüfsumme über den Inhalt wäre stärker,
liesse sich zwischen zwei Engines aber nicht ehrlich vergleichen — sie hängt an
der Textdarstellung von Zahlen und Zeitstempeln.

### Zwölf Tests, keiner braucht ClickHouse

`FalscheDatenbank` ist ein paar Listen, wie `FakeS3Client` in `storage`. Die
beiden wichtigsten sind die Gegenproben: Eine fehlende Zeile und eine
verschobene Verteilung lassen die Sicht **stehen**. Nur eine Prüfung fasst das
echte Release an — ob für jede Gold-Spalte ein Typ entschieden ist; sie trägt
`referenzstand`.

**Zwei eigene Fehler unterwegs**, beide im Test und nicht im Modul: Das
Beispiel-Parquet liess DuckDB `41.7` als `DECIMAL` lesen statt als `DOUBLE`,
und der gefälschte Klient ordnete die Verteilungsabfrage der Zeilenzahl zu,
weil auch sie `count()` enthält. Das Modul hat sich in beiden Fällen korrekt
geweigert.

Dazu ein dritter, den ein bestehender Wächter fand: `args.data_root` muss durch
`for_root` gehen, sonst scheitert der Lauf im `s3`-Modus. Nachgezogen.

### Nachgereicht: gegen ein echtes ClickHouse

Der Docker-Daemon lief eine Stunde später, und damit liess sich prüfen, was
erzeugter Text nie zeigt. **Die Schachtelung war der Beweis wert**:
`Nullable(LowCardinality(String))` sah richtig aus und wird von ClickHouse
verweigert — ohne laufende Datenbank wäre das bis zum ersten Ladelauf
unentdeckt geblieben.

Gegen ClickHouse 26.9.1, aus dem Release `2026-09-21T12-55-05Z` geladen:

| | |
| --- | --- |
| Zeilen | 345'073, Abgleich bestanden, Sicht umgelegt |
| auf der Platte | 17,4 MiB in 12 Parts (Parquet: 14,3 MB) |
| `reporting_city` | `LowCardinality(String)` |
| `nibrs_code` | `LowCardinality(Nullable(String))` |
| `offense_id` | `String` — ohne NULL kein Nullable |

**Der Sortierschlüssel wirkt messbar.** Dieselben Fragen wie in Notebook 34:

| Abfrage | gelesene Zeilen von 345'073 |
| --- | ---: |
| Stadt + Code + ein Tag | **8'192** |
| Code + ein Monat, beide Städte | **30'684** |
| Deliktfamilie, ohne Stadt- und Datumsfilter | 345'073 |

8'192 ist eine Granule — ClickHouse überspringt den Rest, weil
`(reporting_city, date)` die Sortierung ist. Die Zeiten liegen bei 3 bis 5 ms
und damit **nicht** unter DuckDB (0,4 bis 4,5 ms). Bei diesem Umfang gewinnt
ClickHouse nichts; der Gewinn läge bei vielen gleichzeitigen Lesern.

**Die Gegenprobe am echten System:** Ein Ladelauf, der nur 1'000 statt 345'073
Zeilen schreibt, lässt die Sicht stehen. Die halbe Tabelle liegt daneben und
stört niemanden — genau wie ein abgebrochener `.part`-Upload.

Zwei Tests halten das fest; sie überspringen sich, wo kein ClickHouse läuft
(`CLICKHOUSE_URL`, Vorgabe `http://localhost:18123/`).

**Zahlen.** 1'303 → **1'317 Tests**.

---

## 22.09.2026 · Ein drittes Architekturbild: der Systemkontext (direkt auf main)

Die beiden bisherigen Bilder zeigen je eine **Innenansicht** — wer wessen Code
benutzt, und was `run_all` tut. Was fehlte, war die Aussensicht: woher die
Daten kommen, wer die Strecke anstösst, wo sie liegt und womit sie gebaut ist.

`docs/bilder/architektur-kontext.svg`, erzeugt von demselben Werkzeug wie die
anderen beiden. Vier Bänder, weil das vier verschiedene Fragen sind:
**Entwicklungswerkzeuge**, **Systemkontext** mit den fünf Quellen, **Datenfluss**
über die vier Schichten, **Steuerung** links mit gestrichelten Pfeilen, und
**Speicherorte** unten.

### Jede Zahl darin ist gelesen, keine geschrieben

Das ist der Punkt, an dem das erste Bild zwei Tage zuvor gescheitert war — es
führte seine Kantenzahl als feste `19` mit, während der Graph 23 hatte. Hier
kommen sie alle aus dem Code:

| im Bild | gelesen aus |
| --- | --- |
| die fünf Quellen | `run_all.STUFEN`, über das Modul je Stufe mit `quelle` |
| die vier Schichten | `run_all.GRUPPEN` |
| die vier Steuerungsmodule | das Verzeichnis `orchestration/` |
| `local \| s3 \| hybrid` | `storage.config.BACKENDS` |
| DuckDB 1.5.5 | **`requirements.lock`**, nicht die installierte Umgebung |
| 14 Notebooks, 6 Generatoren | die Verzeichnisse selbst |

Die DuckDB-Version aus der Sperrdatei statt aus `importlib.metadata` zu lesen
ist kein Detail: Sonst hinge das Bild am Rechner, auf dem es entsteht, und der
Reproduzierbarkeitstest wäre anderswo rot.

**Warum DuckDB erst ab Silver eingerahmt ist.** Raw und Bronze entstehen mit
Python und pyarrow — dort wird abgelegt, nicht gerechnet. Erst Silver rechnet,
und in Serving kommt die zweite Rolle dazu: derselbe Motor ist der Zugang für
eigene Abfragen. Der gestrichelte Rahmen sagt das, statt es der Bildunterschrift
zu überlassen.

### Fünf neue Wächter

Reproduzierbarkeit und Wohlgeformtheit gelten jetzt für alle drei Bilder
(`ALLE` statt `(PAKETE, FLUSS)`). Dazu vier eigene: die Zahlen im `aria-label`,
jede Quelle und jede Schicht als sichtbarer Kasten, die gepinnte
DuckDB-Version, und die Speichermodi gegen `BACKENDS`. Kommt eine sechste
Quelle dazu, fällt der Test — statt dass sie still fehlt.

### Beim Zeichnen aufgefallen

Drei Kollisionen im ersten Entwurf: Die Beschriftung *Datenfluss* lag im
Pfeilbündel der Quellen, die Untertitel der Speicherkästen sassen auf der
Kastenkante, und der DuckDB-Rahmen reichte eine Zeile zu weit nach unten in die
Speicherorte hinein. Alle drei sind Rechenfehler in den Masszahlen, keine
Geschmacksfragen — und sie fallen nur auf, wenn man das Bild ansieht statt nur
das SVG zu lesen.

`docs/architektur.md` heisst jetzt *„in drei Bildern"*, die Übersicht steht als
Abschnitt 1 davor, die übrigen sind nachnummeriert.

**Zahlen.** 1'298 → **1'303 Tests**.

---

## 21.09.2026 · Das Release der Abgabe (direkt auf main)

**`2026-09-21T12-55-05Z`**, 21 Dateien, 42,5 MB, Commit `1fc6bba` — dem Kopf
von `main` — mit **`git_dirty: false`**. Alle 21 Prüfsummen nachgerechnet.

Bis hierher zeigte `AKTUELL` auf ein Release, das ein Notebook-Lauf nebenbei
erzeugt hatte: Im `hybrid`-Modus bildet **jeder grüne Gesamtlauf** ein Release
und legt den Zeiger um, und Notebook 36 ruft `run_all` dreimal je Durchlauf.
Zeiger, Code und Dokumentation standen dadurch auf drei verschiedenen Commits.
Jetzt auf einem.

### Ändern sich dadurch die Zahlen? Nein — nachgemessen, nicht angenommen

Vor dem Bau wurde je Tabelle ein Abdruck über den **sortierten Inhalt** aller
Spalten genommen, danach noch einmal. **Alle dreizehn Tabellen sind identisch**,
in Zeilenzahl und Inhalt:

| | Zeilen |
| --- | ---: |
| `silver/crime_offense` | 348'311 |
| `silver/tract` · `place` · `weather_day` | 6'282 · 2'206 · 55'465 |
| `gold/fact_offense` | 345'073 |
| `gold/dim_tract` · `dim_offense` · `dim_date` · `dim_city_day` | 6'282 · 85 · 366 · 732 |
| `serving/comparison_day` · `_week` · `_month` | 13'264 · 2'506 · 620 |
| `serving/partition_quality` | 24 |

Das Gate ebenso: `inside_city` 97,451 %, `exact` 95,4905 %, `unmapped`
0,0009 %.

**Warum es auch nicht anders sein konnte:** Zwischen dem Commit des vorigen
Release und `main` hat sich unter `src/crime/` **genau eine Zeile** geändert —
eine Zahl in einem Docstring von `build_comparison`. Keine Logik. Dazu kommt
die Idempotenz, die Notebook 36 mit drei Neubauten belegt.

**Für die Abgabe heisst das:** Jede Zahl in `ln1_konzept.md`,
`leistungsnachweise.md`, im README und in den Notebooks gilt unverändert für
Release `2026-09-21T12-55-05Z`. Es gibt nichts nachzuziehen.

Lokal liegen noch vier Releases (161 MB): dieses, das erste saubere vom
19.9. und die beiden, die weiter unten als Beleg zitiert werden. Alles übrige
steht auf SeaweedFS.

---

## 20.09.2026 · Das erste Architekturbild zählte 19 Kanten, hatte aber 23 (direkt auf main)

Christian ist beim Lesen von `architektur.md` über das erste Bild gestolpert.
**Zu Recht, und schlimmer als gedacht.**

### Das Bild log über sich selbst

`tools/build_architekturbilder.py` rechnet die gezeichneten Pfeile aus — und
schrieb die Gesamtzahl daneben als feste `19`. Der Importgraph hat **23**
Kanten. In der Fusszeile stand damit *„Nur 6 der 19 Kanten sind gezeichnet"*,
und das Dokument schrieb es ab.

Das ist der unangenehmste Fall dieser ganzen Durchsicht: Das Bild wird aus dem
Code erzeugt, ein Test prüft die byteweise Reproduzierbarkeit, und genau
deshalb glaubt man ihm. Eine hartkodierte Zahl darin ist ein gezeichnetes Bild
mit einem Generator davor.

Zwei weitere Fehler im selben Bild: Die Beschreibung nannte *„Zuoberst
gold_pipeline"* — zuoberst steht längst `orchestration`, das Gold und Serving
anstösst. Und die Fusszeile endete auf *„manifeste alle ausser "* mit nichts
dahinter, weil inzwischen jedes Paket `manifeste` benutzt und die Liste leer
blieb. Alle drei rechnet der Generator jetzt.

### Das Dokument dazu

| Aussage | stand da | gemessen |
| --- | --- | --- |
| Kanten im Importgraph | 19 | **23** |
| gezeichnete Pfeile | drei | **sechs** |
| Kanten auf die Fundamente | sechzehn | **siebzehn** |
| Ingestion-Pakete | fünf | **vier** |
| Produktionscode | 10'569 Zeilen | **12'704** |
| Prosa | 11'600 Zeilen | **12'983** |
| Docstrings | 295 | **339** |
| Test-Docstrings | 512 | **733** |
| Dokumente | zwölf | **sechzehn** |

Der Kopfsatz *„mehr Erklärung als Code"* stimmt weiterhin — aber der Abstand
ist von einem Zehntel auf zwei Prozent geschmolzen. Das steht jetzt dort.

### Die Würfel fehlten ganz

Auf die Frage, ob das Dokument die drei festen Würfel vermerkt: **nein**, mit
keinem Wort. Und sie liegen auch nicht dort, wo man sie vermutet — nicht in
Gold, sondern in **Serving**. Gold hält den Stern und aggregiert nicht;
`serving.build_comparison` baut `comparison_day`, `_week`, `_month` und dazu
`partition_quality`, das je Stadt und Monat die Güte der Zuordnungen darunter
ausweist. Neuer Abschnitt *„Gold ist der Stern — die Würfel liegen in
Serving"*.

Nebenbei trug der Modulkopf von `build_comparison` noch die alte Zeilenzahl
344'617; jetzt 345'073.

### Der Wächter, der das hätte fangen müssen

`test_die_bildbeschreibung_nennt_die_echten_zahlen` gab es bereits — er prüfte
aber nur die **Paketzahl** im `aria-label`. Die Kantenzahl lief daneben frei.
Er prüft jetzt beide, dazu die Fusszeile und die Stufenzahl des zweiten Bildes
(die er vorher zwar auslas, aber nie verglich).

Dazu neu `test_das_dokument_nennt_dieselben_kanten_wie_der_graph`. Ein erster
Entwurf davon suchte die Zahl *irgendwo* im Text und ging durch, obwohl die
Aussage daneben zurückgedreht war — die Zahl stand noch an einer zweiten
Stelle. Er prüft jetzt die **Sätze** und liest dabei auch ausgeschriebene
Zahlwörter.

**Zahlen.** 1'297 → **1'298 Tests**.

---

## 20.09.2026 · Ein Wächter hält die Dokumentzahlen gegen das Release (#121)

`tests/test_dokumentzahlen.py`, vier Tests, Marke `referenzstand`. Er schliesst
die Lücke, durch die in dieser Woche die halbe Dokumentation veraltet ist, ohne
dass etwas rot wurde.

### Wie er prüft

**Nicht** „steht Zahl X an Stelle Y" — das wäre eine zweite Liste, die selbst
veraltet. Sondern umgekehrt: Er misst die Kennzahlen aus `release.json` und den
Schichten darunter, sammelt jede Tausenderzahl aus den Dokumenten und meldet
jede, die einer Kennzahl **nahe** ist, ohne eine zu sein. Das ist genau die
Signatur einer veralteten Fassung.

Die Schwelle liegt bei **0,3 %**. Die tatsächlich gefundenen Abweichungen lagen
zwischen 0,001 % und 0,14 %; die nächstgelegene echte Nachbarzahl (`88'278`
gegen `88'686`) bei 0,46 %. Gegengeprobt: `348'311` in `README.md` zu `347'957`
zurückgedreht meldet er

```
README.md:40  347'957 sieht aus wie eine veraltete Fassung von
              silver/crime_offense = 348'311
```

Zahlen auf `'000` bleiben aussen vor — „rund 348'000" ist eine Näherung, keine
Kennzahl. Zeilen, die einen Lauf oder eine datierte Messung festhalten, stehen
in `SCHUTZ` und dürfen veralten; das ist ihr Zweck.

**Wann er läuft.** Weder auf Pull Requests noch im Datenlauf — beide hätten den
falschen Datenstand, der eine gar keinen, der andere einen frischeren als die
Dokumente. Er gehört zu `python -m pytest -m referenzstand`, gegen den
gepinnten Stand, und dort vor allem vor einer Abgabe.

### Der volle `referenzstand`-Lauf deckte zehn weitere Stellen auf

Zum ersten Mal in dieser Woche komplett gefahren. Er fand, was der
Zahlensweep nicht sehen konnte:

| Dokument | stand da | gemessen |
| --- | --- | --- |
| `zaehlperspektiven.md` erste Woche 2024 | 6'694 Taten | **6'711** |
| letzte Woche 2024 | 1'647 Taten | **1'650** |
| `ASSAULT AND BATTERY/SIMPLE ASSAULT` | 16'837 Zeilen | **16'806** |
| Codes mit mehreren Beschreibungen | 34 Chicago, 43 Detroit | **35** und **42** |
| `ambiguous` mit Zeilen 2024 | 16 (5'140 Zeilen) | **17** (5'122), übrige **drei** |
| Läufe im Silver-Manifest | drei Chicago, zwei Detroit | **sieben** und **acht** |
| Detroit-Zeilen in Silver | 88'685 | **88'686** |
| `datenhistorie.md`, Code `3072` | 1'443 Anklagen, 1'403 Taten | **1'404** und **1'365** |

### Eine eigene Korrektur

Meine Nachführung von Detroits Mehrfamilien-Vorfällen war **falsch**: Ich hatte
auf allen Silver-Zeilen gerechnet und kam auf 6'758 (8,4 %). Das Dokument
rechnet auf der **Tatebene**, also auf `fact_offense`, und dort sind es
**4'233 (5,3 %)**, der Überhang **4'569 statt 7'377**. Aufgefallen ist es dem
bestehenden Wächter `test_die_mehrfamilien_vorfaelle_stimmen`, nicht mir. Der
neue Wächter rechnet jetzt ebenfalls auf der Tatebene, und ein Kommentar
dort sagt, warum.

### Zwei Wächter spiegelten selbst einen überholten Stand

`test_der_manifesteintrag_nennt_die_zahl_der_laeufe` verlangte fest `(3, 2)`
Läufe; beide Städte laden inzwischen Deltas, und die Zahl wächst mit jedem. Und
`test_die_mehrdeutigen_beschreibungen_stimmen` prüfte Chicagos
Beschreibungs-Mehrdeutigkeit gegen einen Vertrag, den es seit dem 19.9. nicht
mehr gibt — seit beide IUCR-Hälften in `source_offense_description` stehen, ist
der Anteil null. Er prüft jetzt die Null.

Ausserdem trug `tools/build_feldkatalog.py` Detroits Überzählung mit „3,9 %"
hartkodiert; der Feldkatalog ist erzeugt, und eine Handkorrektur darin hätte der
nächste Lauf überschrieben.

**Zahlen.** 1'293 → **1'297 Tests**, davon 75 abgewählt.

---

## 20.09.2026 · Alle Dokumente gegen Release `2026-09-19T23-05-26Z` nachgeführt (#121)

Die Frage war: Stimmen die Referenzzahlen in den Dokumenten noch mit dem
aktuellen Release? **Bei den meisten nicht.** 117 verschiedene Tausenderzahlen
stehen in den fünfzehn Dokumenten, und ausgerechnet die am häufigsten
wiederholten waren die veralteten — `259'272` allein 23-mal, `347'957` und
`344'617` je zwölfmal.

Nachgeführt sind **81 Zeilen in neun Dokumenten** plus die Stand-Tabelle in
dieser Datei, der Einseiter und die Literalliste im Wächter.

### Die Kennzahlen

| | stand da | Release `…23-05-26Z` |
| --- | --- | --- |
| `silver/crime_offense`, Zeilen | 347'957 | **348'311** |
| `gold/fact_offense`, Taten | 344'617 | **345'073** |
| Chicago, Taten | 259'272 | **259'625** |
| Chicago, Fälle und Vorfälle | 259'243 | **259'596** |
| Detroit, Anklagen | 88'685 | **88'686** |
| Detroit, Taten | 85'345 | **85'448** |
| Detroit, Fälle und Vorfälle | 80'229 | **80'230** |
| `weather_day` | 55'449 | **55'465** |
| Detroit, Delikte in der Rate | 84'658 | **84'761** |
| Detroit, Rate je 1'000 | 132,6 | **132,7** |

### Die abgeleiteten Tabellen

`mapping_status` auf Tatebene: Chicago 247'877/3'697/7'695/3 →
**248'187/3'718/7'717/3**, Detroit 81'195/1'403/2'747/0 →
**81'325/1'365/2'758/0**. `geo_status` in `eine-zahl.md`: `outside_city` 6'007 →
**6'010**, `missing_coordinate` 1'748 → **2'098**.

In `zaehlperspektiven.md` mussten drei Tabellen neu gerechnet werden. Die
auffälligste: Detroits Vorfälle in mehr als einer Deliktfamilie stiegen von
4'148 (5,2 %) auf **6'758 (8,4 %)**, der Überhang beim Summieren je Familie von
4'474 auf **7'377 (9,2 %)**. Das ist kein Rundungsdrift, sondern eine Folge der
angeschlossenen Arrest Charges.

### Die Prozentangaben

| | stand da | gemessen |
| --- | --- | --- |
| Chicago ohne Koordinate | 0,67 % | **0,81 %** |
| Chicago Verortungsquote | 99,33 % | **99,19 %** |
| Detroit zählt zu hoch | 3,9 % | **3,8 %** |
| Zeilen in der doppelten Stunde | 48 | **49** |

### Was stehen bleibt, und warum

Historische Belege sind **nicht** angefasst: die Manifestauszüge des Laufs
`run_20260905T174633859259Z` in `eine-zahl.md` und `ln1_konzept.md` 8.3, die
datierten Messungen in `ausblick.md` („gemessen am 13.9.2026", „am 14.9.2026"),
die Speicher-Evaluation mit Detroits damaligen 88'685 Zeilen, der Satz über die
beiden Vollschnappschüsse, und `datenhistorie.md` als Ganzes — das Dokument
*ist* der Verlauf.

### Geprüft und richtig

`6'282` Tracts, `2'206` Orte, `13'264`/`2'506`/`620`/`24` in Serving, `251'516`
Chicago-Delikte, `2'661'953` und `638'635` Einwohner, Rate `94,5`, Fallebene
`124,6`, `10'475` im Auffang `90Z`, `97,0 %` echte NIBRS-Delikte, Detroit
`0,29 %` ohne Koordinate, die ACS-Lücken (Wayne 9,6 % und 6,4 %, Cook 1,7 % und
0,3 %), `83,35 %`/`83,44 %`/`93,0 %`/`49,4 %` zu H7, `55,9 %` gegen `54,6 %` am
17.9., und die sieben Prüfsummen in `docs/quellen/README.md`.

**Was dabei auffiel:** `test_architektur_dokument.py` hält den Einseiter gegen
den langen Text und die Stand-Tabelle — dieser Wächter hat die Inkonsistenz
sofort gemeldet. Für die übrigen 80 Zeilen gibt es keinen. Ein Wächter, der die
Kennzahlen der Dokumente gegen `release.json` hält, wäre die eigentliche
Lösung; er bräuchte die Marke `referenzstand`.

---

## 20.09.2026 · Der Cachezustand in H6 war behauptet, nicht gemessen (#121)

Christian ist beim Lesen von Notebook 36 über diese Zeile gestolpert:

```python
print(f"   Cachezustand: warm -- die Daten lagen vom vorigen Lauf im "
      f"Seitencache des Betriebssystems")
```

**Zu Recht.** Im Block „Umgebung" wird alles andere gemessen —
`platform.system()`, `duckdb.__version__`, die Dateigrösse aus `stat()`. Der
Cachezustand war der einzige fest verdrahtete String, und er trug eine
Begründung mit sich, die selbst eine Annahme über das Betriebssystem ist.

Inhaltlich war die Aussage plausibel: Die drei Läufe folgen unmittelbar
aufeinander, und H2 liest kurz davor alle sechs Tabellen. Plausibel ist aber
nicht gemessen, und genau das ist der Anspruch dieses Notebooks.

### Jetzt wird es gezeigt

Wer alle Parquet-Dateien liest und dabei einen Durchsatz erreicht, den keine
SSD liefert, hat sie aus dem Arbeitsspeicher gelesen. Gemessen: **61,6 MB in 9
Dateien in 4 ms, also 16 bis 18 GB/s** — ein Mehrfaches dessen, was eine
NVMe-SSD schafft. Die Zelle prüft die Schwelle selbst und schreibt
„Cachezustand: unklar", wenn der Durchsatz unter 10 GB/s liegt; dann wäre er
auch von Platte möglich.

### Und dass es für den Befund nicht trägt

Der wichtigere Teil. Das vollständige Lesen kostet 4 ms; selbst zwanzigmal
langsamer wären es 0,1 s gegen rund 27 s Laufzeit. Der warme Cache ist hier
also **keine Einschränkung**, sondern eine Randnotiz — anders als in den
Notebooks 31 und 33, wo Lesen gegen Lesen verglichen wird und er den
gemessenen Vorteil tatsächlich drückt. Auch das steht jetzt gerechnet in der
Zelle statt als Vorbehalt in der Prosa.

---

## 20.09.2026 · Das erste Release aus sauberem Arbeitsbaum (#121)

**Neues Release** `2026-09-19T23-05-26Z`, 21 Dateien, 42,2 MB — und das erste
mit **`git_dirty: false`**. Commit `8bc6fd6`.

Bis hierher trug jedes Release `git_dirty: true`. Damit reicht der Commit als
Herkunftsnachweis nicht: Was im Arbeitsbaum stand, ist nirgends festgehalten,
und ein Wiederaufbau aus dem Commit könnte etwas anderes ergeben. Die Zahlen,
die in `ln1_konzept.md` und `leistungsnachweise.md` stehen, haben jetzt eine
zitierfähige Kennung.

Gebaut wurde die ganze Kette neu (`run_all --ohne-ingestion --release`), damit
auch die Manifeste von Silver und Gold den sauberen Commit tragen und nicht nur
das Release selbst.

| | |
| --- | ---: |
| `gold/fact_offense` | 345'073 |
| `gold/dim_tract` | 6'282 |
| `gold/dim_offense` | 85 |
| `gold/dim_date` | 366 |
| `gold/dim_city_day` | 732 |
| `serving/comparison_day` | 13'264 |
| `serving/comparison_week` | 2'506 |
| `serving/comparison_month` | 620 |
| `serving/partition_quality` | 24 |

Gate: `inside_city` 97,451 %, `exact` 95,491 %, `unmapped` 0,0009 % — alle drei
weit über beziehungsweise unter ihren Schwellen.

### 25 Releases lokal aufgeräumt

Es waren 28 lokale Releases à rund 42 MB aufgelaufen, zusammen 1,1 GB. Der
Grund: `run_all` bildet je grünem Lauf ein Release, und die Notebooks 31, 33 und
36 rufen `run_all` auf — Notebook 36 allein dreimal je Durchlauf. Beim
Gegenlesen der Notebooks sind so an einem Tag zwanzig entstanden.

Lokal entfernt wurden 25, **1,06 GB frei**. Behalten sind drei: das aktuelle und
die beiden, die weiter oben in dieser Datei als Beleg zitiert werden
(`2026-09-17T19-42-24Z`, `2026-09-19T15-12-28Z`).

**Auf SeaweedFS steht alles unverändert.** Der Modus ist `hybrid`; die 25 zeigen
in `release liste` jetzt `oben` statt `beide` und sind mit
`python -m orchestration.release holen <Kennung>` wieder da. Gelöscht wurde
nichts, was nur einmal existierte.

### Eine Ungenauigkeit, die dabei auffiel — korrigiert

Der Kommentar an `GATE_MINDESTENS` nannte als gemessenen Wert `inside_city`
97,55 %. Das Release misst **97,451 %**. `exact` (95,49) und `unmapped` (0,0009)
stimmen weiterhin.

Mitgezogen ist der Schnappschuss in
`test_das_gate_haelt_die_gemessene_abdeckung_aus`: Er führte acht Anteile, von
denen sechs veraltet waren (`outside_city` 1,87 statt 1,8689,
`missing_coordinate` 0,58 statt 0,6799, `no_tract` 0,0 statt 0,0003, `ambiguous`
1,48 statt 1,473, `fallback_90Z` 3,03 statt 3,0356). Sie tragen jetzt die Werte
aus Release `2026-09-19T23-05-26Z` und sagen im Docstring, woher sie stammen.
Ebenso die beiden Vergleiche in `test_die_schwellen_liegen_unter_dem_gemessenen_stand`,
die den Fünf-Punkte-Abstand prüfen.

**Warum das niemand gemerkt hat:** Der Schnappschuss steht als Zahl im Test,
damit er ohne gebaute Daten läuft — und genau deshalb kann er von den Daten
wegdriften, ohne dass etwas rot wird. Ein Wächter, der ihn gegen
`release.json` hält, wäre die eigentliche Lösung; er bräuchte die Marke
`referenzstand` und liefe damit nicht auf Pull Requests.

---

## 20.09.2026 · Notebook 36: zwei Nummernkreise heissen beide H1 bis H6 (#121)

Das Hypothesen-Notebook prüft H1 bis H6 und zitiert sie wörtlich. **Kapitel 3.3
von `ln1_konzept.md` führt ebenfalls Hypothesen unter H1 bis H8 — und es sind
andere.** H3 heisst im Notebook *Zeitliche Konsistenz*, im Konzept *Die
Deliktschlüssel beider Städte lassen sich vollständig auf NIBRS abbilden*. Wer
die Nummern vergleicht, vergleicht Verschiedenes.

Die Notebook-Fassung stammt aus **Artans Konzeptfassung**, die nicht im
Repository liegt; genau deshalb zitiert das Notebook sie wörtlich, und
`tests/test_notebook_hypothesen.py` erzwingt das. Beide Nummerierungen sind also
in ihrem eigenen Dokument richtig. Das Notebook trägt jetzt oben einen
Hinweiskasten, der die Kollision benennt. **Welche Nummerierung in der Abgabe
gilt, entscheidet Artan** — hier wird nichts umbenannt.

### Vier Zahlen waren veraltet

| Stelle | stand da | gemessen |
| --- | --- | --- |
| H3, doppelte Stunde | 48 Chicagoer Zeilen | **49** (dreimal im Text) |
| H6, Bilanz | Median 2 bis 3 Sekunden | **Median 27 s**, Spannweite 27 bis 31 s |
| H6, Ergebnis | „zwei Grössenordnungen unter dem Budget" | **Faktor 22**, also rund eine |
| Was nicht gezeigt wird | „Sechzehn Zuordnungen" offen | **17** mit `match = nibrs_ermessen` |

Der Rest hält: `verified = true` in allen fertigen Läufen, drei Neubauten mit
identischem sortiertem Inhalt über sechs Tabellen, vier Rechnerzeitzonen mit
demselben UTC-Zeitpunkt, 71,3 % der Chicagoer Zeilen unter mehrdeutiger
Kategoriebezeichnung, alle vier Reproduzierbarkeits-Voraussetzungen belegt,
`git_dirty = false`, neun gepinnte Läufe.

### Die Hypothesentabelle des Konzepts war überholt

Beim Gegenlesen von Notebook 34 fiel auf, dass Kapitel 8.5 und die H1-Zeile in
3.3 auf einem älteren Datenstand ruhen. Beide sind nachgeführt, jeweils mit
datierter Anmerkung:

| Stelle | stand da | gemessen |
| --- | --- | --- |
| 8.5 Delikte Tatebene | 344'617 | **345'073** (Chicago 259'625, Detroit 85'448) |
| 8.5 Auffang `90Z` | 10'442 | **10'475** (7'717 / 2'758) |
| 3.3 H1: Sexualdelikte Chicago | 6,5-Faches | **12,0-Faches** |
| 3.3 H1: Sexualdelikte Detroit | 5,1-Faches | **5,2-Faches** |
| 3.3 H1: Betrug, Faktor | 18 | **20** (3,78 % gegen 0,19 %) |

**Die Prozentsätze und damit beide Aussagen sind unverändert** — 100 % Abdeckung,
97,0 % echte NIBRS-Delikte, und die Geo-Lücke trifft Sexualdelikte in beiden
Städten gleichgerichtet, Betrug nur in Chicago. Der Zuwachs kommt aus Detroits
Delta-Läufen und den nachgezogenen Chicago-Deltas, nicht aus geänderten
Zuordnungen.

---

## 20.09.2026 · Notebook 35: der Beispielfall trug erfundene Koordinaten (#121)

Das Kontrollen-Notebook hält der Nachrechnung als einziges fast lückenlos stand
— 31 harte und 11 weiche Kontrollen über sechs Stufen, jede zweimal vorgeführt.
Geprüft und unverändert: die 2'098 Chicagoer Delikte ohne Koordinate, die 29
Delikte Unterschied zwischen Tat- und Fallebene, Chicagos Anteil von drei
Vierteln aller Zeilen, 14 Stufen in 4 Gruppen, `compare_with_tiger` als einziger
Vollständigkeitsvergleich, der nur warnt und `verified` auf `true` lässt, und
alle sechs Verweise am Ende. Auch die „dreizehn Stufen" in 6.3 stimmen: Am
15.9.2026 waren es dreizehn, die vierzehnte kam danach.

### Der Fehler steckt im Beispielfall

Abschnitt „Ein Fall von Anfang bis Ende" sagt ausdrücklich, der Fall werde
nachgebaut **„mit den Werten, die er im echten Jahrgang trägt"**. Die
Koordinaten trugen das nicht:

| | stand da | in Bronze |
| --- | --- | --- |
| `latitude` | `41.79` | **`41.766555312`** |
| `longitude` | `-87.60` | **`-87.623323691`** |

Rund 2,6 Kilometer daneben. Alles andere am Fall stimmt auf die Stelle: ids
27932 und 27933, die Zeitpunkte 2024-01-01T00:56 und 2024-01-03T20:59, `iucr`
0110, `arrest` false — und `JH100028` ist tatsächlich der erste Mordfall des
Jahrgangs 2024 mit genau zwei Zeilen.

### Die Zahl in „Zwei Arten von Kontrolle" wird jetzt gerechnet

Dort stand *„von den 31 harten Kontrollen brechen 28 tatsächlich ab"* — beides
von Hand gezählt, während die Landkarte darunter eine Datenstruktur ist, die
sich zählen lässt. Die Liste trägt jetzt `HART_OHNE_ABBRUCH` mit den drei
Ausnahmen (`GATE_MINDESTENS`, `ERWARTETE_QUELLEN`, `gepinnte_laeufe`), eine
Zusicherung prüft, dass alle drei überhaupt als hart geführt sind, und die
Auszählung gibt „31 harte, davon 28 abbrechend" selbst aus. Kommt eine
Kontrolle dazu, wandert die Zahl mit.

---

## 20.09.2026 · Sechs Notebooks trugen ihre Ausgaben mit — mein Fehler (#121)

Notebooks liegen in diesem Repository **ohne** gespeicherte Ausgaben. Beim
Durchgehen der Notebooks habe ich sie mit
`nbconvert --execute --inplace` ausgeführt und damit die Ausgaben eingecheckt —
in 21, 22, 31, 32 und 33, alle fünf bereits gepusht. Aufgefallen ist es erst bei
34, weil dort als einzigem ein Wächter steht:
`test_das_notebook_speichert_keine_ausgaben`, mit der Begründung *„So halten es
die übrigen dreizehn auch."*

Sie hielten es so — nur prüfte es niemand. Alle sechs sind geleert (70 Zellen),
und der Wächter gilt jetzt für **alle vierzehn**:
`tests/test_notebooks.py::test_kein_notebook_speichert_seine_ausgaben`.

Warum die Konvention gilt: Eine gespeicherte Ausgabe ist eine Zahl, die niemand
nachrechnet. Sie veraltet still, sie bläht jeden Diff auf, und sie behauptet
einen Stand, den die Datei daneben längst nicht mehr hat — genau das Problem,
das diese ganze Durchsicht aufräumt.

### Notebook 34 selbst

Der Inhalt hält der Nachrechnung fast vollständig stand: die 3,7 % Detroiter
Anklagenüberhang, 16 und 38 Prozent Überzählung der naiven Regel, 78 nur
berührte Detroit-Tracts, 5'249 Chicagoer Grenzfälle auf 23'143 anteiligen
Einwohnern (227 gegen 94,5 Delikte je 1'000), Raten 94,5 gegen 132,7, der
einzelne Fall von 251'516 in der Gegenrichtung, 967 Zeilen unter `90I`, die
Geo-Lücke mit 0,81 % gegen 0,29 % und dem Faktor 20 bei Betrug — alles
nachgemessen und unverändert.

Vier Stellen waren es nicht:

| Stelle | stand da | jetzt |
| --- | --- | --- |
| Kopf, Aufzählung | Punkte `1.`, `0.`, `2.` | fortlaufend |
| Kopf, Standdatum | 12. September 2026 | 20. September 2026 — der Text nannte selbst schon den 17.9. |
| 2.2 Überschrift | „das Tatebene" | „die Tatebene" |
| 6. Grenzen | „die 42 amtlichen Kategorien aus dem User Manual 2025.0" | **38** aus dem Handbuch, **4** aus der Codeliste 2011 |

Die letzte ist die inhaltliche: `config/nibrs_offense_categories_2025.csv` führt
42 Kategorien, aber nur 38 davon (28 Group A, 10 Group B) stammen aus dem
Handbuch. Die vier übrigen — *Bad Checks*, *Drunkenness*, *Peeping Tom*,
*Runaway* — gehören zu den zurückgezogenen Codes und stehen nur in der Fassung
2011. Notebook 32 und `feldkatalog.md` sagen „28 + 10" und meinen das Handbuch;
Notebook 34 sagte „42" und schrieb sie alle dem Handbuch zu. Beide Zahlen
stimmen, die Zuschreibung stimmte nicht. Die Spalte `source` der Datei sagt es je
Zeile.

**Zahlen.** 1'292 → **1'293 Tests**.

---

## 20.09.2026 · Notebook 33 zählte noch drei Silver-Tabellen (#121)

Die Serving-Evaluation vergleicht Sichten gegen Kopie über „die drei
Silver-Tabellen, 410'000 Zeilen". Seit `place` dazukam sind es **vier**, und die
Zahlen darunter wachsen mit:

| Aussage | stand da | gemessen |
| --- | --- | --- |
| Tabellen und Zeilen | drei, 410'000 | **vier, 412'264** |
| Parquet zusammen | 36 MB | **49,4 MB** |
| Platzfaktor Kopie zu Sichten | das 150-fache | **gut das 200-fache** (0,3 gegen rund 62 MB) |

Der Befund selbst ist davon unberührt und hat sich sogar verstärkt: Sichten
bleiben gleich schnell bis knapp schneller, alle vier Gegenproben liefern
identische Ergebnisse, und die Kopie zeigt nach einem Neubau der Quelle weiter
den alten Stand (1 statt 100 Zeilen), während die Sicht sofort nachzieht.

### Der Faktor wird jetzt gerechnet

Die Zelle in Abschnitt 2 gibt ihn selbst aus, statt ihn in der Prosa
festzuschreiben. Er hängt an der Zahl der Silver-Tabellen und schwankt zudem um
ein paar Prozent, weil DuckDB seine Datei nicht byteweise gleich gross baut —
zwei Läufe ergaben 225 und 227. Eine feste Zahl im Text wäre genau die Sorte
Angabe, die beim nächsten Silver-Neubau still falsch wird.

### In den Abgabedokumenten nachgeführt

`ln1_konzept.md` 7.3 nannte das 150-fache; korrigiert auf gut das 200-fache. In
`projektabsprache.md` 7.1 bleibt das Messprotokoll von damals stehen — es ist ein
Protokoll, kein Ist-Zustand — und trägt jetzt eine datierte Anmerkung mit den
Zahlen des heutigen Stands. Die Millisekunden-Werte in beiden Dokumenten liegen
weiter im Rahmen der Neumessung und bleiben unverändert.

---

## 19.09.2026 · Die sieben amtlichen Unterlagen haben jetzt eine Herkunft (#121)

`docs/quellen/` hielt sieben Binärdateien — 8,8 MB PDF und XLSX —, aus denen die
Referenztabellen in `config/` reproduziert werden. **Keine einzige trug einen
Quellenverweis.** Kein Herausgeber, keine Fassung, keine Adresse, keine
Prüfsumme. Wer ein Dokument neu holen oder prüfen wollte, ob es noch das richtige
ist, musste raten. Für Belege, auf denen jede Deliktzuordnung des Projekts ruht,
ist das die schwächste Stelle der ganzen Kette.

### Neu: `docs/quellen/README.md`

Je Dokument Titel, Herausgeber, Fassung, Umfang, Adresse, Grösse, SHA-256 und
wofür es gebraucht wird. **Fünf der sieben sind per Prüfsumme belegt** — am
19.09.2026 unter der angegebenen Adresse heruntergeladen und byteweise mit der
hier liegenden Datei verglichen, alle fünf identisch:

| Dokument | Adresse | belegt |
| --- | --- | --- |
| `nibrs_technical_specification_2025.pdf` | `le.fbi.gov/file-repository/2025-0-nibrs-technical-specification-062625.pdf` | Prüfsumme |
| `nibrs-user-manual-2025-0-062625.pdf` | `le.fbi.gov/file-repository/nibrs-user-manual-2025-0-062625.pdf` | Prüfsumme |
| `NIBRS_Offense_Codes.pdf` | `ucr.fbi.gov/nibrs/2011/resources/nibrs-offense-codes` | Prüfsumme |
| `isp_nibrs_code_table_2026.xlsx` | `isp.illinois.gov/…/NIBRS Code Table 2026.xlsx` | Prüfsumme |
| `illinois_nibrs_iepd_2023.xlsx` | `isp.illinois.gov/…/2025 nibrs_CodesTables.xlsx` | Prüfsumme |
| `micr_manual_1110_2024.pdf` | `michigan.gov/…/micr-assets/MICR-Manual_1110.pdf` | nur Adresse |
| `micr_appendix_f_2009.pdf` | `michigan.gov/…/micr-assets/2009/diappf.pdf` | nur Adresse |

Die beiden Michigan-Dokumente lassen sich von hier aus nicht nachziehen:
`michigan.gov` beantwortet **jeden** automatisierten Abruf mit HTTP 403, auch mit
Browser-Kennung. Das stand schon in Notebook 32 und ist der Grund, warum sie
überhaupt als Datei im Repository liegen.

### Ein Dateiname führte in die Irre

`illinois_nibrs_iepd_2023.xlsx` stammt aus der ISP-Arbeitsmappe
**`2025 nibrs_CodesTables.xlsx`**. Die `2023` im lokalen Namen gehört zum Blatt
`OffenseILUCRCode` (Fassung 2023.0), nicht zur Arbeitsmappe — gebraucht wird das
Blatt `OffenseCode`. Der Name bleibt, weil `tests/config/test_nibrs_offense_codes.py`
ihn führt; der Herkunftsnachweis sagt jetzt, was wirklich zu holen ist.

Nebenbei sichtbar geworden: Michigan führt die Handbuchreihe inzwischen als
`MICR-Manual_1122` (Juli 2025) und `_1130` weiter. Unsere Fassung 1110 ist
überholt — sie bleibt, weil `config/micr_nibrs_mapping.csv` gegen sie gebaut ist;
ein Wechsel ist ein eigener Schritt mit eigenem Abgleich.

### Der Wächter dazu

`tests/test_quellenverzeichnis.py`, 18 Tests. Jede Datei in `docs/quellen/`
braucht einen Eintrag mit Adresse, Belegstufe und Verwendungszweck; jeder Eintrag
braucht seine Datei; **und die genannte SHA-256 muss zur Datei passen.** Der
letzte Punkt fängt den Fehler, den sonst niemand bemerkt: ein Dokument
austauschen und den Eintrag stehen lassen.

### Notebook 32 nebenbei nachgeführt

| Aussage | stand da | gemessen |
| --- | --- | --- |
| 6.1 angeschlossene Arrest Charges | „20 der 23" | **alle 23** — die drei offenen sind seit dem Anschluss von `3072`, `5421`, `5422` zugeordnet |
| 6.2 MICR-Codes mit mehr als einer Kategorie | „zwei von 97" | **zwei von 96** |
| 8. Zahl der Dokumente | „alle sechs Dokumente" | **sieben** — Abschnitt 1.1 führt sieben |
| 3. Ablage der Codeliste | „liegt als PDF unter `docs/`" | `docs/quellen/` |

Geprüft und unverändert: die 81 amtlichen Codes, 54 Chicago- und 63
Detroit-Zielcodes, die vier zurückgezogenen Codes, 66 wörtliche und 15 erklärte
Bezeichnungen gegen Illinois, 103 zu 8 bei der ISP-Gegenprobe, 152 gegen 81
Detroit-Beschreibungen, 97,0 % echte NIBRS-Delikte und 10'475 im Auffang `90Z`,
Detroits Abdeckung bei 100,00 %.

**Zahlen.** 1'274 → **1'292 Tests**.

---

## 19.09.2026 · Notebook 31 stand noch vor seinem eigenen Entscheid (#121)

Das Speicher-Notebook ist die Begründung dafür, dass Detroit auf Parquet
umgestellt wurde. Es war aber durchgehend in der Zeitform von **vor** dieser
Umstellung geschrieben: „Detroit legt NDJSON ab", „Heute übernimmt Detroits
NDJSON beide Rollen", „Detroit kann die fehlende Raw-Schicht bekommen". Alles
drei ist seit dem 11. beziehungsweise 14.09.2026 überholt — Detroit schreibt
Parquet und hat eine eigene Raw-Schicht. Wer das Notebook heute liest, hielt den
Ist-Zustand für den Plan.

### Drei Faktoren waren veraltet

Neu gemessen am Lauf `run_dd30…` (88'686 Zeilen, ganzer Tatjahrgang 2024):

| Aussage in Abschnitt 7 | stand da | gemessen |
| --- | --- | --- |
| Parquet gegen NDJSON | rund 19-mal kleiner | **rund 14-mal** (89,4 gegen 6,5 MB) |
| Parquet gegen gzip-NDJSON | rund 1,8-mal kleiner | **rund 1,7-mal** (10,9 gegen 6,5 MB) |
| fünf Spalten über alle Zeilen | rund 6-mal schneller | **rund 5-mal** |

Ebenso sprach Abschnitt 1 von einer „120-MB-Datei"; das rekonstruierte NDJSON
misst 89,4 MB.

### Neu: die Vorhersage gegen die Wirklichkeit

Das Notebook hatte 81 % Platzersparnis versprochen. Der neue Abschnitt 9 rechnet
nach, was davon eingetroffen ist:

| | Modell (Abschnitt 6) | umgesetzt |
| --- | --- | --- |
| Raw | 10,9 MB | 10,4 MB |
| Bronze | 6,5 MB | **16,7 MB** |
| zusammen | 17,4 MB | **27,1 MB** |
| gegenüber 89,4 MB NDJSON | 81 % weniger | **70 % weniger** |

Die Lücke steckt vollständig in Bronze: **ohne `_feature_json` wären es 6,0 MB
statt 16,7** — das Modell hat Bronze also fast auf das MB genau getroffen. Die
10,7 MB Differenz sind eine Entscheidung, die nach dieser Evaluation fiel: Bronze
behielt die Spalte mit dem geparsten Quellfeature, obwohl Raw seit dem 14.9. die
HTTP-Bytes ohnehin aufbewahrt. Die Antwort der Quelle liegt damit zweimal auf der
Platte — bewusst, denn das geparste Feature „genügt für die Auswertung, ist aber
kein Beweis" (Modulkopf `extract_detroit`).

**Die 81 % sind damit nicht erreicht und dürfen nicht als erreicht zitiert
werden.** Erreicht sind 70 %, und die Begründung für die Differenz steht jetzt im
Notebook.

### Geprüft und unverändert

Der Befund selbst hält in jedem Punkt: `count(*)` liest bei Parquet nur die
Metadaten (`COLUMN_DATA_SCAN` gegen `READ_JSON_AUTO`), das vollständige
Materialisieren bleibt bei Faktor 1,3, und NDJSON rät sein Schema über alle drei
Stichprobengrössen stabil — das Argument *für* NDJSON, das das Notebook
ausdrücklich stehen lässt. Auch der Verweis auf Absprache 4.2 („Hängt von 4.1
ab") stimmt weiterhin.

---

## 19.09.2026 · Notebook 22 zählte vier Flag-Aussagen falsch (#121)

Die Wetterquelle ist die am gründlichsten erkundete des Projekts — und genau in
den ausgezählten Feststellungen steckten die Fehler. Alle vier am Lauf vom
17.09.2026 nachgemessen:

| Aussage | stand da | gemessen |
| --- | --- | --- |
| 5.5: was die Zeilen vor dem Messbeginn tragen | „nur `TAVG` und einige Wolkenparameter" | **nur `TAVG` und `TAVG_ATTRIBUTES`** — genau zwei Schlüssel, keine Wolkenparameter |
| 5.6 / Appendix B: das Quellenflag `Z` | „bei Detroits `SNOW` auch `Z`" | `0`, `1`, `W`, `X`, `Z` an **beiden** Stationen in **allen** vier Grössen |
| 5.8: der literale Text `null` | „in 919 Zeilen `T,,0,null`" | **1'090** Zeilen: 919 als `,,0,null`, 171 als `T,,0,null` — die Zahl gehörte zum anderen Muster |
| Appendix B: Spurenmengen | „rund 4'200 Zeilen je Station" | **4'192** an O'Hare, **4'493** an Detroit Metro |

Dazu zwei Genauigkeiten: `TMAX` ist an O'Hare in 84,9 % der Zeilen belegt, an
Detroit Metro in 94,2 % — die bisherigen „rund 85 %" galten nur für O'Hare, weil
dort 4'402 Zeilen vor dem Messbeginn liegen statt 1'515. Und O'Hares
`SNOW_ATTRIBUTES` führt die Beobachtungszeit nicht durchgehend leer, sondern
1'094-mal als `2400`.

### Die Feststellungen standen in falscher Reihenfolge

5.9 stand vor 5.8 — beide Nummern werden aus Abschnitt 2, 6.7 und Appendix B
heraus referenziert. Getauscht.

### Eine Zahl war falsch, eine hielt stand

Abschnitt 6.1 sprach von „24 MB", die man mit einem `HEAD` spart. Die beiden
Standardstationen liefern zusammen **21,1 MB** (10,9 + 10,1). Korrigiert.

Beim Nachrechnen des Jahresbedarfs habe ich dagegen zuerst danebengegriffen: Die
8,3 GB aus Projektabsprache 3.1 sind die **Platte** (23,3 MB je Lauf × 365), das
Netz sind 7,5 GB. Beides stimmt, die Tabelle ist korrekt. Im Notebook steht jetzt,
welche Spalte gemeint ist.

### Geprüft und unverändert

112 gegen 116 Quellspalten, die vier `I`-Beanstandungen bei O'Hares `SNOW`
(1999-01-09 bis 2011-01-24, vier von 24'603), leeres Q-Flag bei `TMAX`, `TMIN`
und `PRCP` an beiden Stationen, die Feldzahlen je Spalte (3/3/4 und `SNOW` 4
gegen 3), Reihenbeginn 1946-10-09 mit `TMAX` ab 1958-11-01, 100 % Belegung ab
den 1960ern, der Nachlauf der Quelle, das gepinnte Schema mit 15 Spalten, die
Stationsliste, `join_keys`, `value_encoding` und der Manifest-Nachweis. Auch
Feststellung 5.9 hält: Der Vergleich der Läufe vom 7. und 8.9. ergibt je Station
2 neue Zeilen, 0 entfernte, O'Hare 0 geänderte und Detroit genau 1 — die Zeile
vom 2026-09-02, die nachträglich `SNWD` bekommen hat.

---

## 19.09.2026 · Der räumliche Join rechnet nicht um — und das ist messbar (#121)

Notebook 21 behauptete in 5.3: „[der Unterschied NAD83/WGS84] wird beim Join
ausdrücklich umgerechnet statt stillschweigend gleichgesetzt". Derselbe Satz
stand als Kommentar in `download_tiger.py`, und `projektabsprache.md` 
plante den Join von Anfang an „mit Umrechnung WGS84 → NAD83".

**Es gibt keine Umrechnung.** `build_crime_offense` joint mit
`ST_Within(ST_Point(longitude, latitude), geom)`; `ST_Transform` kommt in der
ganzen Pipeline nicht vor. Die beiden Bezugssysteme werden gleichgesetzt.

### Warum das mehr ist als ein falscher Kommentar

Die Rechtfertigung lautete überall „der Unterschied liegt unter einem Meter,
also folgenlos". Tatsächlich sind es ein bis zwei Meter, und die Messung am
Tatjahrgang 2024 zeigt, dass diese Grössenordnung sehr wohl entscheidet:

| Abstand zur Grenze des eigenen Tracts | Anteil der verorteten Fälle |
| --- | --- |
| näher als 1 cm | 1,11 % |
| näher als 8 cm | 11,31 % |
| näher als ~1 m | **25,37 %** |
| näher als ~9 m | 30,90 % |
| näher als ~90 m | 53,36 % |

Eine Gleichverteilung innerhalb der Tracts liesse 6,00 % im Ein-Meter-Streifen
erwarten — gemessen ist es gut das Vierfache. Der Grund ist nicht das Datum,
sondern die Verortung: Beide Städte setzen ihre Koordinaten auf Strassenachsen,
und TIGER schneidet die Tract-Grenzen entlang genau derselben Strassen.

### Was das für H7 bedeutet

Detroit liefert sein eigenes Tract mit (`census_block_2020_geoid`). Die
Nachrechnung auf dem aktuellen Stand ergibt 79'874 vergleichbare Zeilen und
**83,44 % Übereinstimmung** — praktisch dieselben 83,35 %, mit denen
`ln1_konzept.md` und `leistungsnachweise.md` H7 als falsifiziert bewerten. Beide
Dokumente schliessen das Koordinatensystem als Erklärung aus. Das hält nicht:

| Abweichende Fälle (13'228) | Abstand zu dem Tract, **das Detroit nennt** |
| --- | --- |
| näher als ~1 m | 6'537 — 49,42 % |
| näher als ~9 m | 12'309 — **93,05 %** |
| näher als ~90 m | 13'162 — 99,50 % |

Der Punkt sitzt also fast immer auf der gemeinsamen Kante beider Tracts. Die
Abweichung ist eine Frage der Kante, keine falsche Verortung.

**Geändert wurde nur die Sachaussage**, in beiden Dokumenten als datierte
Anmerkung neben der bestehenden Argumentation. Die Bewertung von H7 ist Artans
und bleibt unangetastet — sie gehört aber nochmals angesehen.

### Was sonst noch fehlte

Notebook 21 dokumentierte die Quelle nur zur Hälfte: Die zweite TIGER-
Auslieferung `place` — die Stadtgrenzen, ohne die es keinen Nenner für eine Rate
gibt — kam im ganzen Notebook nicht vor, auch nicht im Aufruf unter 9. Wer sich
daran hielt, lud nur Tracts. Ergänzt in Kopf, 1., 3., 8., 9. und Appendix A.

### Geprüft und unverändert

`STATES`, beide Vintage-Vorgaben, `EXPECTED_CRS`, die Pflichtdateien, die drei
ACS-Variablen, der Sentinel `-666666666` (Michigan: 146 Tracts, bestätigt), die
Missing-Key-Falle (HTTP 200, `text/html`), die Schema-Drift über `GEOIDFQ`, der
Kreuzabgleich TIGER/ACS (3'017 zu 3'017, deckungsgleich) und die FIPS-Tabelle.

---

## 19.09.2026 · Notebook 13 widersprach sich selbst (#121)

**Anlass.** Die Textkontrolle, nachdem heute Vormittag die Laufauswahl repariert
wurde. Hier war die Ausbeute am grössten — das Notebook trug noch die Welt vor
dem Delta-Umbau.

**Der schwerste Befund: eine Zusammenfassung, die dem eigenen Schritt 7
widerspricht.** Das Ergebnis schloss mit

> *„… und dass die Lücke hier nicht systematisch nach Delikttyp verzerrt ist."*

Schritt 7 desselben Notebooks zeigt das Gegenteil, mit Zahlen: Sexualdelikte
1,84 %, Familiendelikte 2,27 %, `OTHER` 2,65 % — das Sechs- bis Neunfache des
Schnitts von 0,29 %. Wer nur die Zusammenfassung liest, zieht den falschen
Schluss. Sie sagt jetzt, was gemessen wurde: **dieselbe Schlagseite wie bei
Chicago, nur um eine Grössenordnung kleiner** — 16 von 869 Sexualdelikten gegen
Chicagos 171 von 1'746.

**Das Argument stand auf dem Kopf.** Schritt 12 hiess: *„sie ist der Grund,
warum die Pipeline bei vollen Snapshots bleibt"*, und schloss mit *„Detroit lädt
deshalb den vollen Jahrgang neu — was bei 88'685 Zeilen und 97 Sekunden die
einfachere und die richtigere Variante ist."* Seit dem 18.9. ist genau das
Gegenteil der Fall. Die Messung trägt jetzt die richtige Folgerung: Sie sagt
nicht, dass kein Delta geht, sondern **worauf** es gehen muss.

**Sieben Zahlen nachgeführt:**

| | war | ist |
| --- | ---: | ---: |
| umklassierte Delikte zwischen zwei Ständen | 10 in 20 Stunden | **113 in knapp 7 Tagen** |
| Überzählung durch Zeilen statt Taten | 3,9 % | **3,7 %** |
| Anklage weicht von der Tat ab | 3,6 % | **3,5 %** |
| Chicagos Geo-Lücke zum Vergleich | 0,7 % | **0,81 %** |
| Zuordnung aus dem MICR-Handbuch | 94,4 % | **94,5 %** |
| Sommer über Februar | 25 % | **33 %** |
| vorliegende Schnappschüsse | zwei, 20 Stunden | **fünf, knapp 7 Tage** |

**Eine Folge ergänzt.** Schritt 2 sagt richtig, dass Löschungen erst der
Vergleich zweier Schnappschüsse zeigt. Seit dem Delta-Umbau entstehen keine
neuen mehr — die fünf vorliegenden sind das Fenster. Das steht jetzt dabei, mit
dem Verweis auf die offene Entscheidung in `datenhistorie.md` 5.2.

**Was geprüft wurde und hält:** die 46 Raw-Antworten, `ESRI_OID` als Nicht-
Schlüssel, die 15 Zeilen mit leerer statt fehlender Beschreibung, 152 gegen 81
beziehungsweise 79 Beschreibungen ungetrimmt/getrimmt, ein Viertel ohne
`updated_in_ibr_at`, die drei Zeilen mit `updated_at` vor der Tat, kein Tag
ohne Fall, kein Schema-Drift.

---

## 19.09.2026 · Notebook 12 verschwieg, wohin es schreibt (#121)

**Anlass.** Die Textkontrolle, nachdem heute Vormittag schon die Technik daran
repariert wurde — Projektwurzel, Delta-Modus, Ausgabeverzeichnis, Parquet statt
NDJSON.

**Der Befund.** Das Notebook sagte nur: *„`RUN_DOWNLOAD` ist absichtlich
zunächst `False`."* Warum das hier mehr wiegt als bei Chicago, stand nirgends.

`02_chicago_bronze_ingestion` schreibt in ein Wegwerfverzeichnis unter
`$TMPDIR` und räumt danach auf — dort ist ein eingeschalteter Download
harmlos. **Notebook 12 schreibt in den echten Bestand** unter `data/`. Ein
Lauf erzeugt dort einen unveränderlichen Bronze-Lauf und rückt bei `DELTA` das
Wasserzeichen vor. Das steht jetzt als Warnkasten darin, zusammen mit dem
Gegenstück: Nach SeaweedFS publiziert das Notebook **nicht**, das tut nur
`main()` der CLI.

Dieselbe Unterscheidung prüft seit heute
`tests/test_notebooks.py::test_ein_ladendes_notebook_schreibt_nicht_unbemerkt_in_den_bestand`
— jetzt steht sie auch dort, wo sie jemand liest.

**Eine Zusage war zu schwach formuliert.** Zum DuckDB-Import stand nur
*„derselbe Quelllauf wird übersprungen"*. `load_run` kann mehr, und das ist die
interessantere Hälfte: Bei bekannter Run-ID mit **anderen Bytes** bricht es ab
— *„Run-ID bereits mit anderen Bytes importiert"*. Dieselbe Kennung mit anderem
Inhalt ist ein Widerspruch, kein Update. Die drei Ausgänge stehen jetzt als
Tabelle darin.

**Zwei ungenutzte Importe** entfernt (`SOURCE_TIMEZONE`, `datetime`).

**Was geprüft wurde und hält:** Parquet mit ZSTD, Raw vor Bronze
veröffentlicht, `DELTA` und `FULL` nach `full/year=…` partitioniert, `DAILY`
ohne Jahresfilter und ohne Wasserzeichen, die Kategoriesumme gegen
`downloaded_count`, `__MISSING__` für fehlende Kategorien, die vier Zeilen ohne
Änderungsstempel.

---

## 19.09.2026 · Notebook 11 begründete seine Ladestrategie falsch (#121)

**Anlass.** Dieselbe Kontrolle wie bei 01, 02 und 03, jetzt auch für die
**Texte**, nicht nur die Zahlen. Das Notebook sagt über sich selbst: *„Es
behauptet so wenig wie möglich. Jede Zahl wird von einer Zelle gerechnet."*
Genau daran habe ich es gemessen.

**Der Hauptbefund.** Abschnitt 5 begründete die ID-basierte Paginierung so:

> *„Der Layer meldet **kein** `supportsPagination`. Ein `resultOffset` ist damit
> nicht verlässlich."*

Gegen den Dienst geprüft: Er meldet **`supportsPagination: true`**. Die
Begründung trägt nicht.

**Die Entscheidung bleibt trotzdem richtig**, nur aus einem anderen Grund — und
der ist der bessere. Es geht nicht darum, dass Offsets nicht *gehen*, sondern
darum, dass sie nichts *belegen*: Bei Offset-Paginierung steht erst am Ende
fest, welche Zeilen man hat. Die feste ID-Liste steht **vor** dem ersten
Datenabruf fest, liegt als `snapshot_ids_sha256` im Manifest, und der Lauf
bricht ab, wenn die geladene Menge abweicht.

Dass der Weg gangbar ist, ist dabei ebenfalls nachgemessen: `returnIdsOnly`
liefert **827'419 IDs in einem Zug**, bei einem Abruflimit von 2000 Zeilen.

**Zwei weitere Korrekturen.**

*„Zeitraum: ab 2016 belastbar"* — der Dienst sagt etwas anderes. 2016 trägt
**6'367** Fälle, 2017 dagegen **83'092**. Belastbar ist der Bestand ab 2017;
2016 ist der eine Monat ab Dezember, mit dem die Quelle beginnt.

*„`arrest_charge` ist fünfstellig"* — bei 88'684 von 88'686 Zeilen. Zwei tragen
statt einer Kennziffer die Zeichen `%` und `/`.

**Eine Lücke geschlossen.** Die Entscheidungstabelle in Abschnitt 9 kannte den
Delta-Ladeweg nicht — das Notebook trug noch den Stand vom 11.9. Die
Entscheidung steht jetzt darin, mit der Begründung aus Abschnitt 8: Über die
Hälfte des Jahrgangs wird mehr als ein Jahr nach der Tat noch geändert, ein
Delta nach Tatdatum sähe keine dieser Korrekturen.

**Stand der Dokumentation** von 11.9. auf 19.9. gesetzt — nach den Eingriffen
von heute und gestern wäre das alte Datum eine Behauptung gewesen.

---

## 19.09.2026 · Notebook 03 verschwieg einen eigenen Befund (#121)

**Anlass.** Dieselbe Kontrolle wie bei 01 und 02, diesmal für Chicagos
Datenqualität. Das Notebook ist **technisch das sauberste von allen**: Es
entdoppelt korrekt und sagt es auch, alle Prüfungen laufen, jede Zahl in der
Prosa deckt sich mit der Ausgabe. Es *verschweigt* aber einen Befund, den es
selbst ausdruckt.

**Der Fund.** In der Distriktverteilung stehen zwei Nummern, die es in Chicago
nicht gibt — `031` mit 14 Fällen und `061` mit **331**. Die Prosa nannte nur
`031` und erklärte es als Erfassungsartefakt. `061` kam nirgends vor, obwohl es
23-mal grösser ist.

Nachgemessen ist es kein Artefakt:

```
Beat 6100 / District 061 / community_area 0 :  334 Zeilen
davon ohne Koordinate                       :  331
häufigste Delikte: Criminal Sexual Assault 116,
                   Offense Involving Children 60, Sex Offense 42
```

**Chicago markiert die unterdrückten Orte doppelt.** Wo die Stadt die Koordinate
zurückhält, setzt sie auch Distrikt, Beat und Community Area auf Werte
ausserhalb des Schemas. Diese 331 Zeilen sind **16 % aller Zeilen ohne
Koordinate** — ein zweiter, unabhängiger Beleg für den Befund aus Schritt 6,
und er stand die ganze Zeit in der Ausgabe.

**Warum das mehr ist als eine Ergänzung.** Wer nach District gruppiert und `061`
für einen Erfassungsfehler hält — so wie es die Prosa nahelegte —, wirft genau
die Delikte weg, bei denen die Stadt den Ort bewusst schützt. Das steht jetzt
ausdrücklich im Ergebnis.

**Ausserdem präzisiert:** *„eine Handvoll Zeilen, bei denen `beat` und `district`
nicht zusammenpassen"* sind **20**.

---

## 19.09.2026 · Alle vierzehn Notebooks Satz für Satz gegengelesen (#121)

**Anlass.** Bei 01, 02 und 13 war es dasselbe Muster: Der Code stimmt, die Prosa
daneben ist älter als er. Also alle vierzehn durchgegangen und jede Zahl in der
Prosa gegen die Ausgabe derselben Zelle gehalten.

### Zwei Notebooks lasen ihren eigenen Bestand falsch

Das ist der schwerwiegendere Teil. `11_detroit_source` und `32_nibrs_source`
lesen Bronze über `read_parquet` **aller** Laufdateien — ohne Entdopplung. Mit
einem Lauf war das richtig. Heute liegen acht Detroit-Läufe übereinander, und
das Notebook rechnete auf **452'980 Zeilen** für einen Jahrgang von 88'686:

```
Zeilen (Delikte)            : 452,980      →   88,686
Vorfaelle (case_id)         :  80,234      →   80,234
davon mit >1 Delikt         : 100.0%       →    9.4%
Delikte je Vorfall im Mittel:   5.65       →    1.11
```

*„Delikte je Vorfall im Mittel: 5,65"* und *„100 % der Vorfälle haben mehr als
ein Delikt"* — beides stand so im Beleg-Notebook zur Quelle. Beide Notebooks
entdoppeln jetzt wie Silver: je Schlüssel die Fassung mit dem jüngsten
Änderungsstempel. Bei Notebook 32 betraf es beide Städte (Chicago 260'852 →
259'625).

Damit fielen auch abgeleitete Zahlen an ihren Platz: Detroits Randleerzeichen
von 145'374 auf 28'058, „ohne Koordinate" von 1'298 auf 259.

### 24 Zahlen in der Prosa nachgeführt

| Notebook | Beispiel | war | ist |
| --- | --- | ---: | ---: |
| 03 | Chicagoer Fälle ohne Koordinate | 0,7 % | **0,81 %** |
| 11 | Chicago Zeilen / Fälle | 259'272 / 259'243 | **259'625 / 259'596** |
| 11 | Detroit Taten / Fälle | 85'345 / 80'229 | **85'448 / 80'230** |
| 11 | die drei offenen MICR-Codes | 1'647 Zeilen | **1'594** |
| 22 | Schneeflag-Ausnahmen | 4 von 24'593 | **4 von 24'603** |
| 31 | gesparter Platz | 85 % | **81 %** |
| 32 | Zeilen auf `90Z` | 10'442 | **10'475** |
| 34 | Chicagos Geo-Ausfall insgesamt | 0,67 % | **0,81 %** |
| 34 | Betrug, Faktor zwischen den Städten | 18 | **20** |
| 35 | Chicagoer Delikte ohne Koordinate | 1'748 | **2'098** |

Dazu die Zahlen in der SVG-Grafik von Notebook 34 — sie trug noch 347'957 und
344'617 und damit den Referenzstand vom 17.9.

### Was geprüft wurde und stimmt

**H4 hält weiterhin**: 185'228 von 259'625 Zeilen (71,3 %) stehen unter einer
mehrdeutigen Kategoriebezeichnung. Die Hypothese hängt an Chicagos
`primary_type` und ist von der heutigen Änderung an
`source_offense_description` **nicht** berührt — das war die naheliegende
Sorge und sie trifft nicht zu.

Ebenfalls unverändert richtig: Notebook 03 entdoppelt korrekt und meldet es
auch; Notebook 21 und 33 arbeiten auf Silver und sind davon nicht betroffen;
die 434 IUCR- und 128 MICR-Zeilen, die 81 amtlichen NIBRS-Codes und die vier
zurückgezogenen stehen unverändert.

### Der Befund hinter dem Befund

Zwei der drei ernsten Fehler dieser Woche haben dieselbe Ursache: **Ein
Notebook, das „den Bestand" lesen will, liest in Wahrheit alle Läufe.** Das
war richtig, solange es einen gab. Seit beide Städte Deltas laden, ist es
falsch — und es fällt nicht auf, weil das Ergebnis plausibel aussieht.

Gegenprobe nach allen Korrekturen: **14 von 14 grün**, kein neuer Bronze-Lauf.

---

## 19.09.2026 · Notebook 02: eine Zusage, die nur lokal gilt (#121)

**Anlass.** Dasselbe Durchsehen wie bei Notebook 01, diesmal für die
Chicago-Ingestion. Das Notebook **läuft** und der weitaus grösste Teil stimmt —
nachgemessen: 22 Quellfelder plus `_extra` ergeben 23 Spalten, davon 19 der
Quellfelder `string`, zwei `bool`, eines `struct`; Keyset-Pagination über
`id > <letzte>`; `.{run_id}.part`; `STALE_PARTIAL_HOURS = 24`;
`whole_records: true`; `derived_from` zeigt auf den Raw-Lauf. Alles wie
beschrieben.

**Der Fund.** Schritt 9 versprach:

> *„Bei einem Testlauf bleibt es bewusst bei `None`. Der nächste Lauf wäre also
> weiterhin ein Vollabzug."*

Die Ausgabe desselben Notebooks sagte daneben:

```
Wasserzeichen im Datenordner: 2026-09-17T15:43:58.000
Nächster Modus              : delta
```

**Warum.** Der Testlauf schreibt in einen Ordner unter `$TMPDIR` — das isoliert
das **Schreiben**. `previous_watermark()` liest aber über die Ablage, und die
steht auf `hybrid`: Sie sieht damit auch die Läufe auf SeaweedFS. Ein leerer
Testordner heisst deshalb nicht, dass es kein Wasserzeichen gibt. Der Testlauf
startete als **Delta**, während der Text einen Vollabzug beschrieb.

**Kein Schaden, und das ist nachgesehen.** Publiziert wird in `main()`, nicht in
`write_run()` — das Notebook ruft beide direkt auf. Ein Testlauf schreibt also
weder nach `data/` noch nach SeaweedFS.

**Korrigiert statt kaschiert.** Beide Stellen sagen jetzt, wovon es abhängt: bei
`STORAGE_BACKEND=local` steht `None`, bei `hybrid` und `s3` das Wasserzeichen des
Projekts. Beides ist richtig — die Funktion beantwortet *„was haben wir schon
geladen"*, und in der hybriden Ablage gehören die Läufe auf dem Server dazu. Wer
den Vollabzug sehen will, nimmt `FORCE_FULL = True` oder startet lokal.

**Ein Begriff, den es nicht gibt.** *„Staging-Schicht"* stand an fünf Stellen —
in Notebook 02, Notebook 21 und zweimal in `download_acs.py`. Die Schicht heisst
**Silver**. Ein Leser der Abgabe hätte nach einer Schicht gesucht, die es nie
gab.

---

## 19.09.2026 · Chicagos Beschreibung trägt jetzt beide IUCR-Hälften (#121)

**Silver-Vertrag 2 → 3, Gold-Vertrag 4 → 5.**

**Das Problem.** Chicago beschreibt ein Delikt in **zwei** Feldern, und Silver
führte nur das zweite:

| Quelle liefert | Silver behielt |
| --- | --- |
| `THEFT` + `$500 AND UNDER` | `$500 AND UNDER` |
| `MOTOR VEHICLE THEFT` + `AUTOMOBILE` | `AUTOMOBILE` |
| `BATTERY` + `SIMPLE` | `SIMPLE` |

„AUTOMOBILE" ist kein Delikt. Schlimmer: Dieselbe Beschreibung stand unter
verschiedenen Delikttypen.

```
SIMPLE                →  BATTERY / ASSAULT / STALKING           31'632 Zeilen
AGGRAVATED - HANDGUN  →  ASSAULT / CRIMINAL SEXUAL ASSAULT /
                         BATTERY                                 6'413 Zeilen
TO VEHICLE            →  CRIMINAL TRESPASS / CRIMINAL DAMAGE    15'857 Zeilen
```

**23,7 % aller Chicagoer Zeilen** trugen eine Beschreibung, die für sich
genommen mehrdeutig war. Der `source_offense_code` daneben war eindeutig — zwei
Spalten für dieselbe Sache, und nur eine hielt.

**Die Lösung.** `source_offense_description` trägt für Chicago beide Hälften,
getrennt durch `": "`:

```
0486  BATTERY: DOMESTIC BATTERY SIMPLE
0820  THEFT: $500 AND UNDER
0910  MOTOR VEHICLE THEFT: AUTOMOBILE
```

Das Trennzeichen ist geprüft: `":"` kommt in **keinem** Chicagoer Quelltext vor.
`" - "` wäre kollidiert — es steht 43'139-mal in den Beschreibungen selbst
(`AGGRAVATED - KNIFE / CUTTING INSTRUMENT`).

Drei Randfälle sind abgefangen: fehlt eine Hälfte, steht die andere allein;
sind beide gleich, steht sie einmal (180 Zeilen, etwa `INTIMIDATION`).

**Detroit bleibt unverändert** — dort ist `offense_description` bereits
vollständig (`ASSAULT AND BATTERY/SIMPLE ASSAULT`).

**Das Ergebnis, gemessen.**

| | vorher | nachher |
| --- | ---: | ---: |
| mehrdeutige Beschreibungen, Chicago | 23,7 % | **0,00 %** |
| Zeilen Chicago | 259'625 | 259'625 |

Die Zeilenzahlen bewegen sich nicht — es ist eine reine Deutungsänderung. Genau
dafür gibt es die Vertragsversion.

**Warum jetzt und nicht nach der Abgabe.** Ich hatte empfohlen, es zu
verschieben und in der Präsentation aktiv zu benennen. Christian hat anders
entschieden: zu grosses Problem, sofort umsetzen. Die Entscheidung war richtig
— eine Spalte, die in fast einem Viertel der Zeilen das Falsche behaupten kann,
ist kein Nachtrag wert.

**Nachgeführt.** `zaehlperspektiven.md` 3 (der Befund ist für Chicago erledigt,
für Detroit steht er unverändert — dort hat er eine andere Ursache),
`datenhistorie.md` 8 Punkt 6 (war die offene Freitagsfrage), der Feldkatalog
über sein Werkzeug, Notebook 01, und die Testfixturen in
`test_build_crime_offense.py`.

**Neues Release** `2026-09-19T15-12-28Z`, 21 Dateien.

---

## 19.09.2026 · Notebook 01 beschrieb einen Plan, nicht die Umsetzung (#121)

**Anlass.** Eine Nachfrage zu einem Absatz in
[`01_chicago_source.ipynb`](../../notebooks/01_chicago_source.ipynb). Das
Notebook trägt den Stand **3.9.2026** — es beschreibt, was wir *vorhatten*. An
drei Stellen ist die Umsetzung anders ausgefallen, an einer war die Aussage
schlicht falsch.

**Die falsche Aussage.** *„Homicide erhält die Kennzeichnung
`record_granularity = VICTIM`, die übrigen Kategorien `record_granularity =
INCIDENT`."* Ein solches Feld gibt es für Chicago **nirgends** — weder als
Spalte noch im Manifest. `record_granularity` existiert nur in Detroits
Bronze-Manifest, als Angabe für den ganzen Lauf mit dem Wert
`INCIDENT_OFFENSE`.

Die Sache dahinter stimmt und ist gelöst — nur anders: Chicago führt bei
Tötungsdelikten **eine Zeile je Opfer**, im Jahrgang 2024 sind das **597 Zeilen
auf 568 Fälle**, und alle **25** Chicagoer Fälle mit mehr als einer Zeile
tragen NIBRS `09A`. Getrennt wird das über `counts` (Tatebene) und
`counts_case` (Fallebene).

**Zwei bewusst verworfene Pläne**, die im Notebook noch als Absicht standen:

| geplant | umgesetzt |
| --- | --- |
| „Das Ingestion-Skript soll sich nur auf die benötigten Spalten beschränken" | ohne `$select`, alle 22 Quellfelder gepinnt — *„a new field lands in EXTRA_COLUMN rather than being lost"* |
| „Der ursprüngliche Wert aus `primary_type` bleibt unverändert erhalten" | in Bronze ja; Silver führt ihn **nicht** weiter, dort steht Chicagos `description` als `source_offense_description` |

Der zweite Punkt ist die offene Frage aus
[`datenhistorie.md`](datenhistorie.md) 8 von der anderen Seite: `0820` heisst
in Silver nur noch *„$500 AND UNDER"* — ohne das `THEFT` aus `primary_type`
bedeutungslos.

**Was dagegen exakt stimmt.** Gegen den Live-Endpunkt nachgemessen: Appendix A
nennt **31 Felder mit identischen Namen und identischen Positionen** — 22
Quellfelder plus 9 von Socrata berechnete. Die 22 decken sich eins zu eins mit
dem gepinnten `FIELDS` im Code. Und Entscheidung 4 wurde ausgeführt:
`case_number` kommt **25-mal** mehrfach vor und taugt deshalb nicht als
Deliktschlüssel — in Silver ist `id` der `offense_id`, `case_number` der
`event_id`.

**Nachgeführt statt umgeschrieben.** Die verworfenen Pläne stehen weiter da,
mit einem datierten Nachtrag daneben. Ein Quellnotebook, das nur den Endstand
zeigt, verschweigt die Entscheidung — und die ist hier das Interessante.

**Eine Randzahl.** *„ohne die jeweils jüngsten sieben Tage"* — am 19.9.2026
gemessen sind es acht. Jetzt als „rund sieben" mit dem Messwert daneben.

---

## 19.09.2026 · Drei Notebooks liefen nicht mehr (#121)

**Anlass.** Alle vierzehn Notebooks einmal ausgeführt und ihren Inhalt gegen
den gebauten Stand gehalten. **Elf liefen, drei nicht.**

| Notebook | Ursache | seit |
| --- | --- | --- |
| `12_detroit_bronze_ingestion` | sucht das Paket im Projekt-Root, es liegt unter `src/crime/` | dem Umzug des Codes |
| `13_detroit_data_quality` | nimmt den jüngsten Lauf als Jahresschnappschuss | dem Delta-Umbau, 18.9. |
| `35_kontrollen` | baut eine Minimaltabelle mit „genau den Spalten, die `reconcile` liest" | der Erweiterung von `reconcile` |

**Notebook 13 ist der inhaltlich wichtigste Fall.** Es beschreibt Detroits
Jahrgang und nahm dafür `laeufe[-1]`. Seit dem 18.9. ist das ein **Delta** mit
3'184 Zeilen — eine Änderungsmenge, kein Bestand. Schritt 3 verglich damit
einen Vollschnappschuss gegen ein Delta, fand keine Feldunterschiede und stürzte
beim Sortieren einer leeren Tabelle ab.

Es trennt jetzt Schnappschüsse von Deltas und rechnet auf dem jüngsten
Vollschnappschuss. Schritt 3 vergleicht den **ältesten gegen den jüngsten** —
alle fünf ziehen dasselbe Abfragefenster, sind also vergleichbar, und die
weiteste Spanne ist die stärkste Evidenz. Statt drei Stunden liegen nun
**6 Tage 22 Stunden** dazwischen: 1'129 geänderte Beschreibungen, davon 113 mit
wirklich anderem Wert.

**Eine Zahl ist dabei gewandert.** Das Notebook misst den Anteil des Jahrgangs,
der mehr als ein Jahr nach der Tat noch geändert wurde. Dokumentiert waren
**54,6 %**; auf dem Schnappschuss vom 18.9. sind es **55,9 %**. Nachgeführt in
README 2.1, `architektur-ist-und-ziel.md`, dem Einseiter, dem Docstring von
`build_delta_where` und den beiden Testdateien. Die Aussage wird dadurch
stärker, nicht schwächer — und der Weg der Zahl steht jetzt im README.

**Was den Fund verzögert hat.** Der wöchentliche Datenlauf führt **8 der 14**
Notebooks aus; die sechs ladenden bleiben bewusst aussen vor, weil sie an sechs
fremden Diensten hängen. Notebook 12 gehört dazu — es war seit Wochen kaputt,
und kein roter Lauf zeigte darauf.

Die Lücke schliesst jetzt `tests/test_notebooks.py` von der anderen Seite:
**ohne Ausführung, ohne Netz.** Geprüft wird, dass jede Wurzelprobe auf einen
vorhandenen Pfad zeigt, dass jeder importierte Name der Strecke existiert und
dass ein ladendes Notebook nicht unbemerkt in den Bestand schreibt. Genau das
hätte Notebook 12 auf jedem Pull Request gefangen.

**Zwei Regeln des Wächters waren zuerst falsch** — und die Notebooks hatten
recht:

* `02_chicago_bronze_ingestion` lädt mit `RUN_DOWNLOAD = True`, schreibt aber
  in ein Wegwerfverzeichnis unter `tempfile.gettempdir()` und räumt auf. Dort
  ist der eingeschaltete Download richtig; ohne ihn wäre die Vorführung
  wertlos. Die Regel lautet jetzt: **Schalter aus oder Wegwerfverzeichnis.**
* `32_nibrs_source` legt bewusst den Projekt-Root auf `sys.path` — es
  importiert `tests.config.*`, nicht die Strecke. Die Regel gilt jetzt nur für
  Notebooks, die ein Paket aus `src/crime` importieren.

**Gegenprobe.** Nach den Reparaturen alle vierzehn ausgeführt: **14 von 14
grün**, und kein einziger neuer Bronze-Lauf dabei entstanden.

**Zahlen.** 1'229 → **1'274 Tests**.

---

## 19.09.2026 · Die internen Dokumente liegen in `docs/intern/` (#121)

**Der Entscheid dahinter.** Der Inhalt der Vertiefungen **wandert in das
Word-Dokument**; verwiesen wird von dort nicht zurück. Damit ist `docs/` kein
Anhangsordner, sondern Quellmaterial — und alles, was nicht einfliesst, hat
darin nichts zu suchen.

**Was verschoben wurde.** Fünf Dokumente nach [`docs/intern/`](.):
`AENDERUNGEN.md`, `projektabsprache.md`, `leistungsnachweise.md`,
`datenhistorie.md`, `DETROIT_PIPELINE_ANLEITUNG.md`. Wer jetzt `docs/` öffnet,
sieht zwölf Dokumente, die alle in die Abgabe einfliessen — und keines, das
offene Entscheide oder Lücken auflistet.

**Zuerst das Netz, dann der Sprung.** Die Dokumentnamen stehen 448-mal in 143
Dateien, und es gab keinen Wächter über tote Verweise. `tests/test_verweise.py`
kam deshalb **vor** dem Umzug: Er prüft jeden relativen Verweis in README,
Dokumenten und Notebook-Zellen. Vorher null tote Verweise, nachher null — der
Umzug ist damit nicht behauptet sauber, sondern gemessen.

Der Wächter hat einen zweiten Test bei sich, der zählt, wie viel er überhaupt
findet (31 Dateien, 255 Verweise). Ein Prüfer, dessen Muster nicht mehr passt,
meldet sonst nichts und sieht dabei grün aus.

**Was der Umzug angefasst hat.** 20 Dateien mit Verweisen, dazu zehn mit
Pfadkonstanten in Python (`PROJECT_ROOT / "docs" / "AENDERUNGEN.md"`) — die
zweite Form hatte die erste Ersetzung nicht erfasst, und 22 Tests brachen mit
Fehlern ab. Das ist genau der Fall, für den es den Verweis-Wächter allein nicht
tut: Er liest Markdown, nicht Python.

**Eine stille Abschwächung verhindert.** Der Abgleich zwischen Wegweiser und
Konzept 11.5 vergleicht verlinkte Dokumentnamen. Nach dem Umzug stand dort
`intern/AENDERUNGEN.md`, und das alte Muster `[\w.-]+\.md` traf das nicht mehr
— der Vergleich wäre auf **zwei leere Mengen** zusammengefallen und weiter grün
gewesen. Verglichen wird jetzt der Dateiname ohne Ordner.

**Zahlen.** 1'226 → **1'274 Tests**. In `docs/` liegen 12 Dokumente statt 17.

---

## 19.09.2026 · Die Abgabe liegt gar nicht im Repository (#121)

**Die Korrektur.** Gestern stand hier, die Abgabe sei `ln1_konzept.md`. Sie ist
es nicht: Die Abgabe entsteht als eigenes **Word-Dokument**, und das Konzept ist
seine Hauptquelle. Damit ist **kein** Dokument in `docs/` die Abgabe — die
Einteilung von gestern war eine Ebene zu tief angesetzt.

**Was sich dadurch ändert.** Wenig am Inhalt, viel an der Beschriftung:

| | gestern | heute |
| --- | --- | --- |
| `ln1_konzept.md` | „die Abgabe" | **Hauptquelle** des Word-Dokuments |
| Kapitel 11.3 | „Anhang zu diesem Leistungsnachweis" | „Vertiefungen, die in die Abgabe einfliessen" |
| Kapitel 11.5 | „nicht Teil der Abgabe" | „fliessen nicht ein" — plus der Hinweis, dass sie beiliegen, wenn das Repository abgegeben wird |
| `docs/README.md` | „Abgabe — was zum LN gehört" | „Abgabe — was in das Word-Dokument fliesst" |

**Was dabei richtig bleibt.** Der Befund von gestern — ein Verweis auf die
eigene Mängelliste mitten im Hypothesen-Kapitel — war nicht weniger schlimm,
sondern genauso: Dieser Text wandert ins Word-Dokument, und der Satz wäre
mitgewandert.

**Der neue Punkt, der vorher nicht sichtbar war.** Die Fassung im Repository
ist die **belastbarere**: Jede Zahl darin wird von der Testsuite gegen die
gebauten Daten gehalten. Im Word-Dokument gilt das nicht mehr — dort ist eine
Zahl so aktuell wie der Tag, an dem sie kopiert wurde. Beide Dokumente sagen das
jetzt, mit der praktischen Folge: **spät übertragen**, und danach
`python -m pytest -m referenzstand` laufen lassen.

**Zwei neue Wächter.** Einer prüft, dass sich **kein** Dokument in `docs/` zur
Abgabe erklärt. Die Behauptung ist billig hingeschrieben und teuer, wenn sie
falsch ist: Sie entscheidet, welcher Text lektoriert wird. Wer sie wieder
aufstellen will, muss den Test ändern — und trifft damit eine Entscheidung,
statt einen Satz stehen zu lassen. Der zweite hält fest, dass der Wegweiser
sagt, **wo** die Abgabe stattdessen liegt.

Der Eintrag vom 18.9. hat einen Nachtrag bekommen, statt umgeschrieben zu
werden. Er beschreibt, was damals galt.

**Zahlen.** 1'224 → **1'274 Tests**.

---

## 18.09.2026 · Die Abgabe zeigte auf ihre eigene Mängelliste (#121)

> **Nachtrag vom 19.9.2026.** Die Prämisse dieses Eintrags stimmte nur einen
> Tag: `ln1_konzept.md` ist ebenfalls nicht die Abgabe. Sie entsteht als
> eigenes Word-Dokument. Was hier beschrieben ist, bleibt richtig und wichtig —
> der Verweis auf die Mängelliste stand im Text, der ins Word-Dokument wandert.
> Siehe den Eintrag vom 19.9.

**Der Befund.** `leistungsnachweise.md` sagte in Zeile 8 über sich selbst:
*„Die Abgabe selbst ist `ln1_konzept.md` — dieses Dokument ist Arbeitsgrundlage
und **nicht Teil der Abgabe**."* Das Konzept verlinkte es trotzdem — und einmal
an der teuersten Stelle:

> Kapitel 3 · Forschungsfragen und Hypothesen:
> *„Der Entscheid über Auswahl und Formulierung ist offen; siehe
> `leistungsnachweise.md` Abschnitt 2.3."*

Wer dem Verweis mitten im Kernkapitel folgte, landete in *„Anforderungen,
Stand, Lücken"*. Der Satz bleibt — der Entscheid **ist** offen —, der Verweis
nach draussen ist weg.

**Der zweite Befund, umgekehrt.** Das Konzept verwies auf **keines** der vier
Dokumente, die ausdrücklich für LN1 geschrieben wurden:
`architektur-ist-und-ziel.md`, `architektur-einseiter.html`,
`zaehlperspektiven.md`, `eine-zahl.md`. Sie existierten, aber die Abgabe wusste
nichts von ihnen — gelesen hätte sie niemand.

**Kapitel 11 gegliedert.** Aus einer Tabelle mit 42 Zeilen, in der Code,
Notebooks, Anhänge, amtliche Quellen und interne Arbeitspapiere durcheinander
standen, wurden fünf:

| | |
| --- | --- |
| 11.1 | Der Code |
| 11.2 | Die Notebooks: der Rechenweg |
| **11.3** | **Anhang zu diesem Leistungsnachweis** — die vier verwaisten sind jetzt darin |
| 11.4 | Amtliche Quellen und die daraus erzeugten Crosswalks |
| **11.5** | **Interne Arbeitsgrundlagen — nicht Teil der Abgabe**, mit dem Vorbehalt im Vorspann |

**Eine falsche Zahl dabei gefunden.** Der Feldkatalog-Eintrag nannte *„133
Spalten in 9 Tabellen"*. Nachgezählt sind es **174 Spalten in 13 Tabellen** —
die vier Serving-Tabellen aus #108 fehlten, und die Zahl war schon vorher zu
niedrig.

**Drei Wächter dazu.** Der wichtigste hält Wegweiser und Kapitel 11 auf
**dieselbe** Einteilung: Was in `docs/README.md` als Anhang steht, muss in 11.3
stehen, und was intern ist, in 11.5. Zwei Orte, eine Wahrheit — sonst driften
sie, und genau das war der Ausgangszustand.

Der zweite verbietet Verweise auf Mängellisten im Fliesstext der Abgabe. Er
schlug beim ersten Lauf **ein zweites Mal** an: `AENDERUNGEN.md` in Kapitel 5.2.
Diese Stelle bleibt — sie ist eine Selbstkorrektur (*„hier stand bis heute …"*)
und zeigt auf den **Beleg**, nicht auf eine Lücke. Der Wächter nennt deshalb
drei Dokumente namentlich, statt „intern" pauschal zu verbieten; die Begründung
steht als Kommentar daneben.

**Was das für die Einteilung heisst.** `architektur.md`, `storage-architektur.md`
und `ausblick.md` waren im Wegweiser vom Vormittag als *intern* eingeordnet.
Das war falsch: Das Konzept verweist auf alle drei, LN1 verlangt die
Storage-Evaluation ausdrücklich, und ein Ausblick gehört in einen solchen
Bericht. Sie stehen jetzt im Anhang. Abgabe und Anhang sind damit **zehn**
Dokumente, intern **fünf**.

**Zahlen.** 1'222 → **1'274 Tests**.

---

## 18.09.2026 · docs/ sagt jetzt, welches Dokument für wen ist (#121)

**Was.** Ein Wegweiser [`docs/README.md`](../../README.md), zwei neue Ordner
[`quellen/`](../quellen/) und [`archiv/`](../archiv/), und die Einteilung in **Abgabe,
intern, erzeugt** ist aufgeschrieben statt erinnert.

**Der Befund vorher.** Fünfzehn Markdown-Dateien, zwei HTML-Seiten und **8,8 MB
amtliche PDFs** lagen flach nebeneinander. Nichts daran sagte, welches Dokument
in den Leistungsnachweis gehört und welches nur wir brauchen — und bei einigen
ist der Unterschied wesentlich: `leistungsnachweise.md` ist *über* den LN und
benennt Lücken; in der Abgabe wäre das ein Eigentor.

| | vorher | nachher |
| --- | ---: | ---: |
| Dateien direkt in `docs/` | 24 | 17 |
| davon Binärdateien | 8,8 MB | 0 |

**Was verschoben wurde.** Die sieben amtlichen Unterlagen nach `quellen/` —
NIBRS-Spezifikation und -Handbuch, Michigans MICR-Handbücher, Illinois'
Codetabellen. Sie bleiben im Repository, weil `tests/config/` die Crosswalks
daraus **neu baut und byteweise vergleicht**; ein Crosswalk ohne seine Quelle
wäre eine Behauptung. `DETROIT_TIMEZONE_AENDERUNGEN.md` (11 Zeilen, Stand
9.9.2026) nach `archiv/` — der Inhalt steht seither im Code und hier.

**Was der Umzug gekostet hat.** Elf Dateien mit Pfadangaben: drei Werkzeuge,
vier Crosswalk-Tests, das Konzept, zwei Notebooks und ein Bericht. Die
erzeugten CSVs blieben unberührt — sie führen den **Dateinamen ohne Pfad** als
Herkunft, und genau deshalb hat der Umzug keinen einzigen Byte-Vergleich
gebrochen.

**Was dabei aufgefallen ist.** Notebook 32 überschrieb seine Tabelle mit *„Sechs
Dokumente, und warum jedes einzeln nötig war"* — die Tabelle hatte **sieben**
Zeilen. Der Fehler stand dort, seit das siebte Dokument dazukam.

**Sechs Wächter** in `tests/test_dokumentwegweiser.py`. Ein Wegweiser, den
niemand nachführt, ist schlimmer als keiner: Er sieht nach Ordnung aus. Geprüft
wird deshalb in beide Richtungen — jedes Dokument steht darin, kein Verweis
darin ist tot, kein Dokument steht in zwei Abschnitten (die Einteilung wäre dann
nicht entschieden), und `docs/` enthält keine losen PDFs mehr.

Die Ausnahme ist `feldkatalog.md`: Anhang der Abgabe **und** erzeugt. Beides ist
wahr, und der Wegweiser muss es an der ersten Stelle dazusagen — auch das ist
getestet.

**Was bewusst nicht geschah.** Kein Dokument wurde umbenannt und keines in einen
Unterordner verschoben. Die Dokumentnamen stehen **448-mal in 143 Dateien**, und
es gibt keinen repo-weiten Wächter über tote Verweise. Der kommt zuerst; alles
Weitere danach.

---

## 18.09.2026 · Der Standardlauf ist wieder grün (#121)

**Was.** `python -m pytest` wählt den Marker `referenzstand` ab. Die Wächter
sind nicht abgeschaltet, sie haben einen eigenen Aufruf:

```bash
python -m pytest                     # alles ausser dem Referenzstand
python -m pytest -m referenzstand    # genau diese 71 Wächter
python -m pytest -m ""               # beides zusammen, alle 1'274
```

**Warum.** Am Morgen meldete die Suite **34 Fehlschläge**. Keiner davon war ein
Fehler: Alle 34 halten eine dokumentierte Zahl gegen die *gebauten* Daten, und
die Daten sind seit dem gepinnten Referenzstand weitergelaufen — vier
Chicago-Deltas und Detroits neuer Ladeweg. Ein normaler Zwischenzustand, aber
er hatte zwei Kosten: Die Suite sah kaputt aus, obwohl sie es nicht war, und
**ein echter Fehlschlag wäre in diesem roten Rauschen nicht aufgefallen**.

Das war keine neue Erkenntnis — der Datenlauf wählt den Marker seit dem
13.9. ab, und `-m "not referenzstand"` stand als Empfehlung im README. Nur
musste man sie kennen und tippen. Jetzt ist die Vorgabe das, was man ohnehin
will, und die Ausnahme braucht das Argument.

**Was gleich bleibt.** Die Summenzeile nennt die abgewählten weiterhin
(`71 deselected`) — stumm abwählen wäre der nächste Verwirrungsgrund. Und
`datenlauf.yml` behält sein eigenes `-m "not referenzstand"`: Was in GitHub
Actions läuft, soll in der Workflow-Datei stehen und nicht in einer Vorgabe,
die drei Verzeichnisse weiter jemand ändert.

**Was der Umbau gekostet hat, bevor er saß.** Der erste Entwurf des Wächters
übersprang sich stillschweigend. Grund: Er gab `--collect-only -q` mit, und
zusammen mit dem `-q` aus `addopts` wurde daraus `-qq` — dann druckt pytest
statt der Summenzeile nur noch die Zahlen je Datei, und die Regex fand nichts.
Zwei Tests standen auf grün, ohne je etwas geprüft zu haben. Der Wächter misst
seither die **Ausgabe** statt der Einstellung.

**Zahlen.** 1'211 → **1'274 Tests** (fünf neue in
`tests/test_referenzstand_marker.py`). Standardlauf: 1'145 ausgeführt, 71
abgewählt. Frischer Klon: 1'125 von 1'145, die übrigen 20 brauchen Daten.

---

## 18.09.2026 · Detroit lädt Deltas — auf `updated_at`, nicht auf dem Tatdatum (#121)

**Was.** Detroits Ingestion lädt seit heute wie Chicagos: ein Wasserzeichen,
14 Tage Rückgriff, und nur noch das Geänderte. `--mode delta` ist der Modus des
Gesamtlaufs; `--mode full` bleibt für Backfills und Bestandsabgleiche.
Bronze-Vertrag **2 → 3**.

**Warum das vorher nicht ging — und warum es jetzt geht.** Der erste Versuch
scheiterte an einer Messung: **54,6 %** des Jahrgangs 2024 wurden mehr als ein
Jahr nach der Tat noch geändert (Notebook 13, Schritt 12). Ein Delta nach
*Tatdatum* hätte keine dieser Korrekturen gesehen, und Detroit lud seither jedes
Mal den ganzen Jahrgang.

Die Messung sagt aber nicht, dass kein Delta geht, sondern **worauf** es gehen
muss. Über vier volle Schnappschüsse (11.9., 12.9., 17.9., 18.9.) haben wir
nachgerechnet, ob `updated_at` als Änderungsmarke trägt:

* **1'270** Zeilen änderten sich inhaltlich — Beschreibung, Code, Kategorie,
  Fallstatus, Tatzeitpunkt oder Koordinate.
* **Jede einzelne** trug dabei einen neuen `updated_at`. **Keine** änderte sich
  ohne bewegten Stempel.
* Umgekehrt bewegte sich der Stempel **499**-mal ohne inhaltliche Änderung. Das
  kostet doppelt geladene Zeilen, die Silver über `incident_entry_id` und den
  jüngsten `updated_at` ohnehin dedupliziert.
* **4** von 88'686 Zeilen tragen gar kein `updated_at`, stabil über alle vier
  Schnappschüsse.

**Wie die Abfrage aussieht.** Zwei Bedingungen, und je eine allein wäre falsch:
der Jahrgang nach `incident_occurred_at` — sonst kämen Fälle aus jedem Tatjahr —
und darin `updated_at >= Wasserzeichen − 14 Tage`. Die vier Zeilen ohne Stempel
kommen über `OR updated_at IS NULL` immer mit; sie hätten sonst nie wieder eine
Chance, in einen Lauf zu geraten.

**Was das kostet und bringt.** Der erste Lauf auf einem leeren Rechner findet
kein Wasserzeichen und lädt voll: 88'686 Zeilen in 100 s. Der zweite lud
**3'184 Zeilen in 7 s**.

**Was dabei aufgefallen ist.** Drei Dinge, die ohne den Umbau still geblieben
wären:

1. **`_extract_where` kannte den Modus nicht** und brach mit *„Nicht
   unterstuetzter Extraction Mode: DELTA"* ab. Die Vertragstabelle dort ist
   Absicht — sie verhindert, dass ein Umbau einen Jahresbestand nach Update-Zeit
   zieht. DELTA brauchte deshalb einen eigenen Eintrag, und zwar mit **zwei**
   Feldern: `window_field` trägt das Fenster (Tatzeit), `date_field` die Auswahl
   (Änderungszeit). Bei FULL und INCREMENTAL ist es dasselbe Feld, bei DELTA
   nicht.
2. **Die Delta-Bedingung wurde zweimal gebraucht** — einmal zum Bauen der
   Abfrage, einmal zum Prüfen, dass die übergebene Abfrage die richtige ist.
   Zwei getippte Fassungen derselben Zeichenkette wären früher oder später zwei
   verschiedene; sie steht jetzt als `delta_bedingung()` an einer Stelle.
3. **Die Aufräumregel trug die Antwort schon.** `DELTA_MODI` kennt `delta` und
   `incremental`, und Detroits neues `extraction_mode: DELTA` fällt darunter —
   ein Delta hält seitdem auch bei Detroit alles bis zum nächsten vollen Lauf
   fest. Ein Test hält das fest, weil beide Städte den Modus **anders schreiben**
   (`mode` gegen `extraction_mode`) und ein Tippfehler dort still die Basis eines
   Deltas löschen würde.

**Was das für die Historie heisst.** Löschungen sind nur zwischen zwei vollen
Schnappschüssen erkennbar. Fünf davon liegen für Detroit vor; **neue kommen ohne
Beschluss keine mehr dazu.** Das verschiebt nichts an der Empfehlung in
[`datenhistorie.md`](datenhistorie.md) 5.2 — es macht sie dringlicher und gilt
jetzt für beide Städte.

**Wächter.** 1'179 → **1'274 Tests**. 25 davon in
`tests/detroit_pipeline/test_detroit_delta.py`, und dort wendet der
Fake-Client den Delta-Filter *wirklich* an, statt immer alles zu liefern — ein
Fake, der alles zurückgibt, bestünde auch einen Test, dessen Abfrage nichts
einschränkt. Dazu fünf CLI-Tests, der Detroit-Fall in `test_aufraeumen.py` und
einer in `test_build_crime_offense.py`: Ein Delta darf den Bestand darunter
nicht verschwinden lassen. Fiele der, wäre es der Tabelle nicht anzusehen — sie
wäre nur kürzer, um alles, was sich nicht geändert hat.

---

## 18.09.2026 · Dieselbe Architektur auf einer A4-Seite (#120)

**Was.** [`architektur-einseiter.html`](../architektur-einseiter.html) — das
Architekturkapitel aus #119 als **ein Blatt zum Ausdrucken**, mit zwei
gezeichneten Bildern: der Datenfluss über die sechs Schichten, und der geplante
Verbund hinter Cloudflare. Dazu die fünf Kennzahlen, die drei Ladestrategien,
und die Tabelle, was bei zehn Städten zuerst bricht.

**Gemessen, nicht behauptet.** Ein Test druckt das Blatt mit Chrome nach PDF
und zählt die Seiten; bei zwei Seiten fällt er. Er trägt `referenzstand` und
überspringt sich ohne Chrome — die Prüfung gehört an den Rechner, an dem
jemand wirklich druckt.

**Was die Wächter dabei gefunden haben.** Der Einseiter nennt Detroits
**54,6 %** — der Anteil des Jahrgangs, der mehr als ein Jahr nach der Tat noch
geändert wurde, und der Grund für den Vollschnappschuss. Ein Test hält beide
Dokumente auf dieselben Zahlen, und dabei fiel auf, dass der **lange Text die
Ladestrategien überhaupt nicht behandelte**. Er hat jetzt eine Tabelle dazu —
Delta mit Überlappung, Vollschnappschuss, eingefrorene Vintage — samt der
Zeile, die erklärt, warum die Publish-Sperre am 17.9. umgebaut werden musste:
Sie hielt einen abgelösten NOAA-Lauf für einen fehlenden.

**Sechs weitere Wächter:** dieselben Zahlen wie im langen Text, die Testzahl
gegen das README, die Trennung von Ist und Ziel, keine Bilder von aussen
(sonst wäre der Ausdruck ein weisses Rechteck), und eine Beschreibung je Bild.

**Zahlen.** 1'173 → **1'179 Tests**. Frischklon 1'098 von 1'179.

**Nachlesen.** `docs/architektur-einseiter.html` ·
`tests/test_architektur_dokument.py` · PR #120

---

## 18.09.2026 · Ein Architekturkapitel für LN1 — Ist und Ziel getrennt (#119)

**Was.** [`architektur-ist-und-ziel.md`](../architektur-ist-und-ziel.md), als
Kapitel für den Leistungsnachweis gedacht. Zwei Teile, und die Trennung ist
die Aussage: **Teil A** beschreibt, was läuft, mit Zahlen aus dem
Referenzstand; **Teil B** beschreibt die Ziel-Architektur und sagt an jeder
Stelle, was sie kosten würde.

**Teil A** führt die sechs Schichten mit ihrer je einen Aufgabe und dem, was
sie ausdrücklich nicht tun; die zehn Pakete mit den zwei Regeln, die sie
zusammenhalten (keine Zyklen, das Fundament hängt an nichts); die vierzehn
Stufen; die drei Betriebsarten der Ablage mit ihren vier Zusagen; die Herkunft
über `derived_from`, `contract_version` und `code_version`; die 42 Kontrollen,
von denen 28 abbrechen; und was heute wo läuft — **eine Entwicklungsmaschine,
ein CI-Dienst, ein Objektspeicher**.

**Teil B** ist Christians Zielbild: Docker-Verbund auf einem privaten Server,
Cloudflare-Tunnel ohne offenen Port, Anmeldung über Cloudflare Access,
Elasticsearch und Kibana als Auswertung, `homepage` als Dienstübersicht, eine
eigene Admin-Oberfläche, Grafana für den Betrieb, tägliche und wöchentliche
Sicherung, vorbereitet für einen automatisierten Rollout nach Google Cloud,
und eine skalierbare Ingestion.

**Der Widerspruch, den der Text auflöst.** `ausblick.md` 5 hat OpenSearch
geprüft und verworfen — *„die falsche Form, nicht die falsche Grösse“*.
Diese Bewertung war richtig für die damalige Frage: *Ersetzt es DuckDB?* Nein.
Elasticsearch kommt jetzt als **Serving-Index neben dem Stern**, und dafür
sprechen drei messbare Dinge: Kibana ist eine fertige Oberfläche samt Karte für
die 1'055 Tract-Umrisse; Volltext ist keine hypothetische Anforderung, weil
23,3 % der Chicagoer Beschreibungen mehrdeutig sind; und eine DuckDB-Datei ist
für einen Leser gedacht, ein Index für mehrere. **Bedingung:** abgeleitet,
jederzeit neu aufzubauen, mit der Release-Kennung versehen — Parquet bleibt die
Quelle der Wahrheit.

**Zwölf Wächter**, alle ohne gebaute Daten. Sie halten Teil A gegen den Code
(Stufen je Gruppe, Pakete, Schichten, Kontrollen, Betriebsarten, Testzahlen
gegen das README, Referenzzahlen gegen dieses Dokument) und **Teil B gegen die
Abwesenheit**: Solange der Text sagt, nichts davon sei gebaut, darf kein
`docker-compose.yml` und kein Elasticsearch in `requirements.txt` stehen.
Entsteht eines, fällt der Test — und der Baustein gehört dann nach Teil A, mit
Zahlen. Ein weiterer prüft, dass der Widerspruch zum Ausblick benannt bleibt.

**Drei Lücken, die die Wächter beim Schreiben gefunden haben:** Das Paketbild
nannte vier Pakete nur silbenweise umbrochen; Teil A hatte keine Zahlentabelle,
obwohl er sich darauf berief; und drei der sieben Bausteine in Teil B nannten
keinen Preis. Alle drei geschlossen, bevor der Text stand.

**Zahlen.** 1'161 → **1'173 Tests**. Frischklon 1'092 von 1'173.

**Nachlesen.** `docs/architektur-ist-und-ziel.md` ·
`tests/test_architektur_dokument.py` · PR #119

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
[`docs/zaehlperspektiven.md`](../zaehlperspektiven.md) sagte, ein Widerspruch in
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
[`docs/zaehlperspektiven.md`](../zaehlperspektiven.md) — die vier Arten zu zählen,
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

**Was.** [`notebooks/36_hypothesen.ipynb`](../../notebooks/36_hypothesen.ipynb)
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

**Was.** [`notebooks/35_kontrollen.ipynb`](../../notebooks/35_kontrollen.ipynb)
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

**Was.** [`docs/eine-zahl.md`](../eine-zahl.md) rollt die Rate **94,5** rückwärts
auf: sieben Stufen von der Folie bis zu den 26 gzip-Dateien, die die Stadt
Chicago am 5. September geliefert hat. Zähler, Nenner, Herkunftskette,
Vollständigkeitsnachweis, Rohantwort.

**Warum.** Der Lesepfad in [`architektur.md`](../architektur.md) führt durch den
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

**Was.** [`docs/architektur.md`](../architektur.md) zeigt den Aufbau in zwei
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

**Was.** [`ausblick.md`](../ausblick.md) hat einen Abschnitt 5: die
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
[`ausblick.md`](../ausblick.md).

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
Stufe B ([`ausblick.md`](../ausblick.md)).

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
dieser Datei. Artans Punkt 2 ([`ausblick.md`](../ausblick.md)).

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
Punkt 1, Stufe A ([`ausblick.md`](../ausblick.md)).

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

**Was.** [`docs/ausblick.md`](../ausblick.md) — Material für LN2. Zwei Punkte
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

**Was.** [`docs/storage-architektur.md`](../storage-architektur.md) beschreibt
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

**Nachlesen.** [`docs/archiv/2026-09-09-detroit-zeitzonenvertrag.md`](../archiv/2026-09-09-detroit-zeitzonenvertrag.md) · PR #25 — am 18.9.2026 ins Archiv verschoben, der Inhalt steht seither im Code und in diesem Dokument

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
| #125 | erste Fassung dieser Einstiegsseite | **nicht gemergt** — GitHub schloss ihn, als beim Merge von #124 dessen Branch gelöscht wurde; er war darauf aufgebaut. Neu als #127 |
| #50 | ein überholter Kommentar in `build_analysis_db.py` | eine Zeile, ändert keine Aussage |
| #80 | `docs/detroit-schichten.html` entfernt — der Entwurf „Detroit-Schichten angleichen" aus der Zeit vor #39 | veraltet und nirgends verlinkt; was daraus wurde, steht in `DETROIT_PIPELINE_ANLEITUNG.md` und Konzept 7.3. Christian hat es entschieden |
| #81 | `docs/chicago-ingestion.html` entfernt — eine dritte, unverlinkte Beschreibung derselben Pipeline | veraltet (kein Storage-Backend, keine `contract_version`, 259 270 statt 259 272 Zeilen) und nirgends verlinkt; der Inhalt steht im Modul-Docstring, in Notebook 02, README 2.1 und Konzept 6 |
| #84 | `docs/feldkatalog.md` neu erzeugt, nachdem er von Hand bearbeitet worden war | kein inhaltlicher Entscheid, sondern die Wiederherstellung des erzeugten Stands; die Begründung steht als Anmerkung unter *Vertragsversionen* |
| #68 | `orchestration.drift` las den Fingerabdruck unter einem falschen Schlüssel (`fingerprint` statt `input_fingerprint`) — der erste Lauf zeigte `None` | Fehlerbehebung mit Test, ändert keine Aussage |
| #104 | der Übergang in `zaehlperspektiven.md` 3 neu gefasst — „Auch die 28 beweisen weniger…“ sagte nicht, was gemeint war | Formulierung, keine geänderte Aussage; die Aussage selbst war schon richtig, nur unlesbar neben dem Absatz davor. Christian hat nachgefragt |
| #112 | `datenhistorie.md` 8: die vier offenen Punkte aus dem Chat für Freitag notiert (Chicagos Beschreibung aus beiden IUCR-Hälften, die 20/16 `ambiguous`-Zuordnungen, H1/H6, „Anklage“); §5 heisst „Fünf“ statt „Vier“ | Agenda, keine geänderte Aussage; die Zahlen stehen bereits in `zaehlperspektiven.md` und sind dort bewacht. Christian hat entschieden, die Beschreibungsfrage offen zu lassen |
| #113 | README 2.5: der Release-Ablauf Schritt für Schritt, je Rolle (wer baut, wer liest); `tools/build_referenz.py` übergibt jedes Modul ausdrücklich an pdoc, weil ein Paket mit `__all__` sonst keine Unterseiten bekommt - `storage.backend`, `storage.config` und `storage.release` hatten bis dahin keine | Bedienungsanleitung und Werkzeug, keine geänderte Aussage. Christian hat gefragt, „wo ist das beschrieben“ |
| #117 | die gemessene Drift festgehalten (Christians Entscheidung: nicht nachziehen), README 1.4 erklärt die roten `referenzstand`-Wächter, und zwei Tests räumen wieder auf, statt Feldkatalog und SVG im Arbeitsbaum zu hinterlassen | Dokumentation und ein Testfehler; die Sache selbst steht im Eintrag zu #116, wo sie aufgefallen ist |

