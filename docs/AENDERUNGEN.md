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
| Tests | **660** |
| `silver/crime_offense` | 347'957 Zeilen (Detroit: eine Anklage) |
| `gold/fact_offense` | **344'617** Zeilen (eine Tat) |
| Chicago | 251'516 Delikte · 2'661'953 Einwohner · **94,5** je 1'000 |
| Detroit | 84'658 Delikte · 638'635 Einwohner · **132,6** je 1'000 |

> Die Rate zählt nur Delikte in Tracts, die einer der beiden Städte zugeordnet
> sind. Absolute Fallzahlen legen das Gegenteil nahe — Chicago hat in fast
> jeder Kategorie mehr Fälle.

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

