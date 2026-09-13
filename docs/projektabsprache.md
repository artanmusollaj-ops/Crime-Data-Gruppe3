# Projektabsprache: Scope, Schichten und Konventionen

Arbeitspapier für die Abstimmung zu zweit. Jeder Abschnitt hat denselben
Aufbau: **Stand** (was heute nachweislich da ist), **Frage** (worüber wir uns
einig werden müssen), **Vorschlag** (Empfehlung mit Begründung) und eine Zeile
`Entscheid:` zum Ausfüllen.

> **Verhältnis zu [`leistungsnachweise.md`](leistungsnachweise.md):** Dort steht
> die Abgabe-Sicht — Anforderungen der beiden Leistungsnachweise, Forschungsfragen,
> Hypothesen, Lebenszyklus, Arbeitspakete. Hier stehen die technischen Entscheide.
> Die Leitfrage in Abschnitt 2.1 wird durch die dortigen Forschungsfragen
> abgelöst; beide Dokumente gehören in dieselbe Sitzung.

Alle Zahlen in diesem Dokument sind am 6. September 2026 aus dem Repository und
den geladenen Daten erhoben, nicht geschätzt.

---

## 1 · Ausgangslage

| Quelle | Stand | Umfang | Schichten |
| --- | --- | --- | --- |
| **Chicago** | Pipeline fertig, getestet | 259'272 Fälle 2024, 3 Läufe (1 voll, 2 Delta) | raw + bronze |
| **Detroit** | Pipeline fertig | 88'685 Fälle 2024, 1 Lauf, 32 Deliktkategorien | nur bronze |
| **Census TIGER** | Pipeline fertig, getestet | 3'265 Tracts Illinois, 3'017 Michigan (Vintage 2024) | raw + bronze |
| **Census ACS** | Pipeline fertig, getestet | dieselben Tracts, 3 Variablen | raw + bronze |
| **Wetter (NOAA)** | Pipeline fertig, getestet | 29'181 Tage O'Hare (ab 1946), 26'264 Detroit Metro (ab 1942) | raw + bronze |

Ergänzend: 633 Tests, 11 Notebooks, `data/silver/` mit allen vier Tabellen,
`data/gold/` mit dem Sternschema (eine Faktentabelle, vier Dimensionen). Die Deliktzuordnung liegt in drei Referenzdateien:
`config/nibrs_offense_codes_2025.csv` (81 amtliche NIBRS-Codes),
`config/iucr_nibrs_mapping.csv` (434 Chicago-Codes) und
`config/micr_nibrs_mapping.csv` (128 Detroit-Codes).

**Was implizit schon entschieden ist** (durch den Code, nicht durch ein
Gespräch): unveränderliche Läufe mit Manifest, Nachweis der Vollständigkeit
statt Behauptung, festes Schema je Quelle mit `_extra` für Unerwartetes,
Jahrgang 2024 als PoC, Census Tract als räumliche Bezugseinheit.

---

## 2 · Scope: Was soll das Projekt beantworten

### 2.1 Die Leitfrage

**Stand.** Die Richtung ist erkennbar — NIBRS-Harmonisierung, zwei Städte,
Tracts, Sozialdaten —, aber nirgends in einem Satz festgehalten. Ohne diesen
Satz lässt sich nicht entscheiden, was in Gold gehört und wann wir fertig sind.

**Frage.** Was ist die eine Frage, die wir beantworten?

| Variante | Was dafür nötig ist |
| --- | --- |
| A: Deskriptiver Vergleich | „Wie unterscheidet sich die Kriminalitätsstruktur beider Städte je Tract?" — Fälle, NIBRS, Einwohner |
| B: Sozioökonomischer Zusammenhang | zusätzlich Einkommen und Armut aus ACS, Korrelationsrechnung |
| C: Wettereinfluss | zusätzlich NOAA, Zeitreihen je Tag |
| D: A + B + C | alles, deutlich mehr Aufwand |

**Vorschlag.** **A als Pflicht, B als Kür, C als Ausbaustufe.** A ist mit dem
heutigen Stand fast erreichbar; B kostet wenig zusätzlich, weil die ACS-Daten
schon liegen; C bringt eine dritte Zeitachse ins Spiel und lohnt erst, wenn A
steht. So ist das Projekt zu jedem Zeitpunkt vorzeigbar.

`Entscheid: D. Ein Grossteil der Daten ist schon heruntergeladen. Ein Integration sollte nicht mehr so aufwändig sein.`

### 2.2 Zeitraum

**Stand.** Beide Städte sind mit dem Jahrgang 2024 geladen. Chicago reicht
grundsätzlich bis 2001 zurück.

**Frage.** Bleibt es bei 2024, oder wollen wir mehrere Jahre?

**Wichtige Nebenwirkung.** Tract-Grenzen haben sich mit dem Zensus 2020
geändert. Für Fälle ab 2020 gilt TIGER-Vintage 2020+, davor die Grenzen von
2010. Ein Vergleich über diesen Bruch hinweg braucht **zwei** Vintages und eine
ausdrückliche Erklärung im Ergebnis. Das ist der teuerste Teil einer
Mehrjahres-Auswertung — nicht das Laden der Falldaten.

**Vorschlag.** **Bei 2024 bleiben.** Ein sauber belegtes Jahr ist mehr wert als
fünf Jahre mit einem stillschweigenden Grenzbruch. Falls Zeit bleibt: 2021–2024,
weil das vollständig innerhalb der 2020er-Grenzen liegt.

`Entscheid: Auf 2024 beschränken um im Leistungsnachweis 1 zu zeigen`

### 2.3 Räumliche Einheit

**Stand.** Die Census-Pipeline lädt Tracts, beide Städte liefern Koordinaten.
Chicagos `community_area` und Detroits Bezirke sind untereinander nicht
vergleichbar.

**Vorschlag.** **Census Tract** als gemeinsame Einheit, Stadt als übergeordnete
Ebene. Chicagos `community_area` zusätzlich mitführen, weil sie für lokale
Leser aussagekräftiger ist.

`Entscheid: Gemeinsame Einheit, Stadt als übergeordnert. Darunter noch miteinander abgleichen ob granularer berschrieben und übernommen.`

### 2.4 Umgang mit der Geo-Lücke

**Stand.** Aus dem Qualitäts-Notebook: 1'748 Chicago-Fälle (0,67 %) haben keine
Koordinaten, und der Ausfall ist **nicht zufällig** — 4,3 % bei Delikten an
Kindern, 3,7 % bei Sexualdelikten, gegenüber 0,4 % bei Diebstahl. Die Stadt
unterdrückt die Verortung bei sensiblen Delikten.

**Frage.** Wie gehen wir damit um, und prüfen wir dasselbe für Detroit?

**Vorschlag.** Fälle ohne Koordinaten **nicht stillschweigend fallen lassen**,
sondern in jeder Tract-Auswertung die Abdeckung je Delikttyp mitausweisen. Und:
Für Detroit dieselbe Prüfung fahren, bevor wir Zahlen nebeneinanderstellen —
sonst vergleichen wir womöglich unterschiedlich stark verzerrte Grundgesamtheiten.

`Entscheid: Vorschlag umsetzen. Detroit wird noch analysiert. In der Analyse bemerken`

---

## 3 · Die Wetterquelle

**Stand.** Gebaut und getestet als `weather_pipeline` (PR #11). „NOAH" heisst
korrekt **NOAA** (National Oceanic and Atmospheric Administration).

Die Fragen unten sind **nach dem Vorschlag umgesetzt**, damit heute etwas
Vorzeigbares steht — der Entscheid bleibt offen und kann jede Antwort noch
ändern. Was dabei anders war als hier beschrieben: die Kopfzeile hat nicht 11,
sondern 112 Spalten bei O'Hare und 116 bei Detroit Metro. Die vier Größen des
Vorschlags sind gepinnt, alles übrige liegt unverändert in `_extra` — also auch
`SNWD`, `TAVG` und `AWND`. Eine Größe von dort ins Schema zu heben kostet einen
Eintrag im Code und **keinen neuen Ladelauf**.

Ausserdem: die Reihen enden rund vier Tage vor dem Abrufdatum. Ein Wetterjoin
auf die jüngsten Falldaten läuft dort ins Leere.

**Geprüft am 6.9.2026:** Es braucht **keinen** API-Schlüssel. Die Reihen liegen
als eine CSV je Station bereit — dasselbe Muster wie TIGER, also überträgt sich
das Design der Census-Pipeline fast unverändert:

```text
https://www.ncei.noaa.gov/data/global-historical-climatology-network-daily/access/<STATION>.csv
```

| Station | ID | Grösse |
| --- | --- | --- |
| Chicago O'Hare | `USW00094846` | 10,9 MB |
| Chicago Midway | `USW00014819` | 2,8 MB |
| Detroit Metro | `USW00094847` | 10,1 MB |

Spalten: `STATION, DATE, LATITUDE, LONGITUDE, ELEVATION, NAME, PRCP, SNOW,
SNWD, TMAX, TMIN` — jeweils mit `_ATTRIBUTES`-Spalte für Qualitätsflags.

**Der entscheidende Unterschied zu allen anderen Quellen:** Wetter ist **kein
Tract-Merkmal**. Es wird über **Datum + Stadt** verbunden, nicht räumlich. Die
Partition heisst also `station=` und nicht `state=`, und der Join geschieht auf
einer anderen Achse als bei Census.

**Fragen.**

1. Eine Station je Stadt (Flughafen) oder mehrere? — *umgesetzt: eine je Stadt.
   Chicago Midway ist als dritte Station hinterlegt und mit `--station`
   zuschaltbar, ohne Codeänderung.*
2. Welche Grössen? Vorschlag: `TMAX`, `TMIN`, `PRCP`, `SNOW` — mehr braucht die
   Leitfrage kaum. — *umgesetzt; der Rest liegt in `_extra`.*
3. Übernehmen wir die Qualitätsflags aus den `_ATTRIBUTES`-Spalten nach Bronze?
   Vorschlag: ja, unverändert — sie sind Teil der Quelle. — *umgesetzt.*

**Vorschlag insgesamt.** Eine `weather_pipeline` nach dem Muster von
`download_tiger`: eine Datei je Station, Vollständigkeit über `Content-Length`
und Zeilenzahl, festes Schema plus `_extra`. **Umgesetzt.** Die Vorbedingung
„erst bauen, wenn Variante C (2.1) beschlossen ist" ist damit vorweggenommen:
Fällt der Entscheid gegen C, liegt eine Pipeline da, die niemand auswertet —
sie kostet dann nichts weiter, ausser dass sie mitgepflegt wird.

`Entscheid: Gemäss Voschlag umsetzen. Allenfalls einen Mechaninsmus einbauen, der alte Download mit dem neuen überprüft und dann gelöscht wird. Daten in Quelle historisiert. Aufbewahrung regeln`

### 3.1 Abrufhäufigkeit, bedingter Abruf und Speicher

**Stand.** Jeder Lauf lädt die **ganze** Datei. Die Quelle bietet kein Delta an:
eine CSV je Station mit der kompletten Historie, kein Datumsfilter, keine
Paginierung. Gemessen am 7.9.2026:

| | O'Hare | Detroit Metro | zusammen |
| --- | --- | --- | --- |
| Download je Lauf | 10,9 MB | 10,1 MB | **21,1 MB** |
| auf der Platte je Lauf | 12,0 MB | 11,2 MB | **23,3 MB** |

Weil Läufe unveränderlich sind, liegt die fast identische Historie danach so oft
auf der Platte, wie wir Läufe machen:

| Frequenz | Platte pro Jahr | Netz pro Jahr |
| --- | --- | --- |
| täglich (365 Läufe) | **8,3 GB** | 7,5 GB |
| wöchentlich (52) | 1,2 GB | 1,1 GB |
| monatlich (12) | 0,3 GB | 0,2 GB |

Zum Vergleich: Chicago und Census belegen zusammen rund 70 MB (siehe 7.1).

**Umgesetzt am 8.9.2026** gemäss Entscheid: Mindestabstand von sieben Tagen
(`--min-interval-days`, `--force` übergeht ihn) plus bedingter Abruf über
`If-None-Match` und `If-Modified-Since` aus dem letzten Manifest. Der bedingte
Abruf greift auch bei `--force`, damit ein erzwungener Lauf ohne Neuigkeit
nichts kostet.

**Was die Quelle anbietet und wir nicht nutzen.** Ebenfalls nachgemessen:

```text
ETag            "a7052a-65ad06f950b00"
Last-Modified   Sun, 06 Sep 2026 13:25:32 GMT
Accept-Ranges   bytes

If-Modified-Since: <Last-Modified>   ->  HTTP 304, 0 Byte
Range: bytes=-2000                   ->  HTTP 206, 2000 Byte
```

Ein **bedingter Abruf** funktioniert also: Hat NOAA die Datei seit unserem
letzten Lauf nicht neu veröffentlicht, antwortet der Server mit `304` und null
Bytes statt mit 11 MB. Die Ingestion fragt das derzeit nicht.

Ein **Delta über `Range`** wäre technisch ebenfalls möglich — davon ist
abzuraten, und das ist inzwischen **belegt**. Der zweite Schnappschuss vom
8.9.2026 gegen den ersten vom 7.9.2026, Zeile für Zeile verglichen:

| | O'Hare | Detroit Metro |
| --- | --- | --- |
| neue Zeilen am Ende | 2 | 2 |
| entfernte Zeilen | 0 | 0 |
| **nachträglich geänderte Zeilen** | **0** | **1** (2026-09-02) |

In Detroit hat die Zeile vom 2.9. nachträglich `SNWD` und `SNWD_ATTRIBUTES`
bekommen, wo vorher leere Felder standen — eine Korrektur einen Tag hinter dem
damaligen Rand. **Die Quelle ist also nicht append-only.** Ein Delta, das nur
das Dateiende anhängt, hätte diese Korrektur übersehen.

Einzuschränken ist der Befund auf das Gemessene: ein Intervall von einem Tag,
zwei Stationen. Korrekturen tief in der Historie sind damit nicht ausgeschlossen,
nur nicht beobachtet. Der Vollschnappschuss deckt beide Fälle ab.

**Frage.** Wie oft laufen wir, und bauen wir den bedingten Abruf ein?

| Variante | Aufwand | Folge |
| --- | --- | --- |
| A: täglich, wie heute | 0 | 8,3 GB im Jahr für eine Reihe, die täglich um eine Zeile wächst |
| B: wöchentlich, plus `--force` vor einer Auswertung | 0, nur Absprache | 1,2 GB im Jahr; jeder Schnappschuss bleibt vollständig |
| C: monatlich, plus `--force` vor einer Auswertung | 0, nur Absprache | 0,3 GB im Jahr; grösserer Abstand zum aktuellen Rand |
| D: bedingter Abruf zusätzlich (`If-None-Match`) | ~20 Zeilen plus Tests | spart Netz, nicht Platte; macht `--force` billig |

**Vorschlag.** **B plus D.** Der entscheidende Punkt ist, dass **jeder Lauf ein
vollständiger Schnappschuss ist**: Anders als bei einer Ereignisquelle entsteht
durch einen selteneren Lauf **keine Lücke**, weil der nächste Lauf die
Zwischenzeit vollständig mitbringt. Ein täglicher Vollschnappschuss für eine
Quelle, die täglich eine Zeile anhängt, ist die falsche Frequenz — er kostet das
Siebenfache und bringt nichts, was der Wochenlauf nicht auch hätte.

D ist unabhängig davon sinnvoll und billig: Es macht einen erzwungenen Lauf, der
nichts Neues findet, kostenlos.

**Nicht blockierend.** Fällt der Entscheid gar nicht, läuft Variante A weiter.
Der Einbau von D wartet ausdrücklich auf diesen Entscheid.

`Entscheid: B plus D ist o.k.`

---

## 4 · Bronze: der grösste Abstimmungsbedarf

**Stand seit dem 11.9.** Detroit schreibt Parquet in Laufverzeichnissen. Damit
sind die Konventionen nah beieinander, aber noch nicht gleich:

| | Chicago | Detroit | Census |
| --- | --- | --- | --- |
| Pfad | `bronze/city=chicago/ingest_date=…/run_…/` | `bronze/city=detroit/full/year=…/run_…/` | `bronze/dataset=…/vintage=…/state=…/run_…/` |
| Partition | Hive (`city`, `ingest_date`) | Hive (`city`), dazu (`year`, `run_date`); `full`/`incremental` ohne Schlüssel | Hive (`dataset`, `vintage`, `state`) |
| Format | Parquet (snappy) | Parquet (ZSTD) | Parquet (snappy) |
| Lauf-Kennung | `run_<UTC-Zeitstempel>` | `run_<UUID4>` | `run_<UTC-Zeitstempel>` |
| Manifest | `manifest.json` je Schicht im Lauf-Ordner | `manifest.json` im Lauf-Ordner | wie Chicago |

**Was noch abweicht.** `full`/`incremental` sind keine `key=value`-Paare. Die
Lauf-Kennung ist eine UUID statt eines Zeitstempels, sortiert also nicht
chronologisch.

**Erledigt am 12.9.:** Detroit benennt die Stadt jetzt als Partitionsschlüssel
(`city=detroit/` statt `detroit/`) und schreibt eine **Raw-Schicht** — jede
ArcGIS-Antwort unverändert als gzip, mit SHA-256 je Antwort im Manifest. 46
Antworten je Jahrgang, 84,6 MB geliefert, 10 MB abgelegt.
| Manifest-Felder | `completeness`, `watermark`, `source_schema`, `query` | `offense_category_counts`, `pipeline_run_id`, … | wie Chicago plus `crs` |
| Raw-Schicht | ja | ja | ja |
| Schema | gepinnt, 23 Spalten, `_extra` | verschachteltes JSON (`attributes`/`geometry`/`_meta`) | gepinnt, 14 bzw. 9 Spalten, `_extra` |

Der Kommentar in `.gitignore` nannte das lange einen Übergang („Detroit legt
(noch) flach ab") — seit dem 12.9. ist er eingelöst.

### 4.1 Was bedeutet „Bronze" bei uns?

**Frage.** Ist Bronze die unveränderte Landung oder schon eine tabellarische
Ableitung? Chicago und Census beantworten das mit **beidem**: Raw hält das
Original, Bronze ist die abgeleitete Tabelle. Detroits NDJSON übernimmt beide
Rollen gleichzeitig.

**Vorschlag.** **Zweischichtig, wie bei Chicago und Census.** Raw ist das
Beweisstück und unwiederbringlich; Bronze ist daraus jederzeit neu erzeugbar.
Diese Trennung hat sich bewährt: Beim Chicago-Schemafehler liess sich Bronze
neu ableiten, ohne die API erneut zu befragen.

`Entscheid: Es wird angeschaut was perfomanter ist. Wenn parquet besser ist, wird es umgesetzt da es besser ist zu vereinheitlichen`

**Angeschaut am 9.9.2026 — Parquet ist besser.** Gemessen an denselben Daten in
beiden Formaten, reproduzierbar in
[`notebooks/31_storage_evaluation.ipynb`](../notebooks/31_storage_evaluation.ipynb):

| Kriterium | Ergebnis |
| --- | --- |
| Grösse | 6,5 MB gegen 89,4 MB; auch gegen gzip-komprimiertes NDJSON (10,9 MB) noch 1,8-mal kleiner |
| Wenige Spalten, alle Zeilen — was Silver tut | **6,0-mal schneller** |
| Zeilen zählen | aus den Metadaten, ohne die Daten zu lesen |
| Alle Spalten materialisieren | nur 1,3-mal schneller |
| Schema-Stabilität | **kein Unterschied**, NDJSON rät hier stabil |

Der stärkste Befund ist nicht die Geschwindigkeit: Detroits NDJSON übernimmt
heute Raw und Bronze gleichzeitig. Getrennt nach der Konvention der anderen drei
Quellen — Raw als gzip-komprimiertes NDJSON, Bronze als Parquet — sind beide
Schichten zusammen **18,3 statt 89,4 MB**. Die fehlende Schicht kostet also
nichts, sie spart 85 %.

Gegen Parquet spricht, dass es ohne Werkzeug nicht lesbar ist. Genau deshalb
bleibt NDJSON in Raw, wo man es zur Fehlersuche braucht.

**Damit ist 4.2 entsperrt**, dessen Entscheid „Hängt von 4.1 ab" lautete.

### 4.2 Angleichung Detroits

**Frage.** Ziehen wir Detroit auf die gemeinsame Konvention nach?

| Variante | Aufwand | Folge |
| --- | --- | --- |
| A: alles angleichen (Raw + Hive-Partition + Parquet + Manifest) | ~1 Tag | eine Konvention, ein Lesepfad für Silver |
| B: nur Pfad und Manifest angleichen, NDJSON behalten | ~2 h | Silver muss zwei Formate lesen |
| C: so lassen, Unterschiede dokumentieren | 0 | jede Auswertung trägt den Sonderfall mit |

**Vorschlag.** **Variante A, aber erst nach dem Scope-Entscheid.** Begründung:
Silver liest sonst dauerhaft zwei Welten, und jede spätere Auswertung, jedes
Notebook und jeder Test zahlt diesen Preis erneut. Der Umbau ist einmalig und
gut testbar — Detroits Vollständigkeitsnachweis (Object-IDs vorher festschreiben,
danach abgleichen) ist inhaltlich bereits derselbe wie bei Chicago, er ist nur
anders abgelegt.

Falls die Zeit knapp wird: Variante B ist ein vertretbarer Kompromiss, weil der
Pfad das ist, was Silver am meisten stört.

`Entscheid: Variante A, umgesetzt am 12.9.2026 (PR #39).` Detroits Bronze liegt
unter `city=detroit/`, jeder Lauf schreibt Raw als gzip mit SHA-256 je Antwort,
Parquet mit gepinntem Schema und ein Manifest. Silver liest damit **einen**
Lesepfad für beide Städte.

### 4.3 Gemeinsame Regeln für jede künftige Quelle

**Vorschlag** als Checkliste, an der sich auch die Wetter-Pipeline messen lässt:

- [ ] Zwei Schichten: `raw/` (unverändert, Byte für Byte) und `bronze/` (Parquet, festes Schema)
- [ ] Hive-Partition mit sprechenden Schlüsseln, erster Schlüssel benennt die Quelle
- [ ] Lauf-Kennung `run_<UTC-Zeitstempel>`, identisch über beide Schichten
- [ ] `manifest.json` je Schicht und Lauf, mit Vollständigkeitsnachweis und Schema-Fingerabdruck
- [ ] Läufe unveränderlich; Schreiben über `.part`-Verzeichnis und atomares Umbenennen, Raw zuerst
- [ ] Gepinntes Schema, alles Unerwartete nach `_extra`, nichts stillschweigend verwerfen
- [ ] Werte behalten den Typ der Quelle; Parsen erst in Silver
- [ ] Schlüssel und Token nie im Manifest oder in einer abgelegten URL

`Entscheid: Wetter und Census bereits umgesetzt analog Chicago`

---

## 5 · Silver und Gold

**Stand.** Beide Schichten sind gebaut: `silver/crime_offense` (347'957
Zeilen) und das Gold-Sternschema darauf (`fact_offense`, 344'617 Zeilen). Der
früher hier genannte Detroit-eigene Normalisierer `transform_detroit.py` ist
entfernt — er hätte eine zweite, unbelegte Kategorienzuordnung neben dem
NIBRS-Crosswalk gehalten.

### 5.1 Was gehört in Silver?

**Vorschlag.** Silver ist die Schicht, in der aus zwei Städten **eine** Tabelle
wird. Konkret:

1. Deduplizieren je `id`, Version mit dem höchsten `updated_on` (Chicago-Deltas überlappen bewusst)
2. Typen setzen: Zeitstempel parsen, Koordinaten nach `float` — führende Nullen von `iucr`, `beat`, `district` dabei **erhalten**
3. Räumlicher Join: Koordinate in Tract-Polygon, mit Umrechnung WGS84 → NAD83
4. NIBRS-Harmonisierung über `config/iucr_nibrs_mapping.csv` und das Detroit-Pendant
5. Eine gemeinsame Faktentabelle mit `stadt`, `fall_id`, `zeitpunkt`, `nibrs_kategorie`, `geoid`, `lat`, `lon`, `verortet` (ja/nein)

Wichtig: Punkt 5 behält auch die **nicht verorteten** Fälle, mit einer Kennzeichnung.
Sonst verschwindet die Verzerrung aus Abschnitt 2.4 unbemerkt.

**Nachtrag 8.9.2026: drei Körner, nicht eine Tabelle.** Der Vorschlag oben
entstand vor der Wetterquelle und spricht von „einer Tabelle". Das geht nicht
auf, weil die Quellen drei verschiedene Granularitäten haben:

| Tabelle | Eine Zeile ist | Woraus |
| --- | --- | --- |
| `crime_offense` | **ein Delikt** | Chicago- und Detroit-Bronze, beide Crosswalks, `tract` |
| `tract` | **ein Census Tract** | TIGER (Geometrie) + ACS (Attribute) |
| `weather_day` | **eine Stadt an einem Tag** | NOAA-Bronze |

Alles in eine Tabelle zu zwingen hiesse, einen Wetterwert an jedes Delikt
derselben Stadt und desselben Tages zu hängen — Zeilen vervielfachen sich, und
jede Aggregation über Wetter zählt danach falsch. Zusammengeführt wird deshalb
erst in Gold, dort auf dem Aggregationskorn.

Zum Korn der Faktentabelle: **Delikt, nicht Fall.** Detroit liefert das schon
fertig mit `offense_key` und `event_key` für die 1:n-Beziehung; Chicago hat `id`
als Schlüssel, `case_number` taugt nicht (25 Nummern kommen mehrfach vor, siehe
Abschnitt 8).

**Was in `weather_day` gedeutet werden muss** und in Bronze bewusst nicht
passiert: Zehntel auflösen (`"  214"` sind 21,4 °C, `SNOW` dagegen schon mm),
leeres Feld zu `NULL` statt `0` — bei Niederschlag der entscheidende
Unterschied —, das Messflag `T` für Spurenmengen als eigene Spalte, und die
Feldzahl der `_ATTRIBUTES`-Spalten je Spalte bestimmen statt annehmen (drei bei
`TMAX`, vier bei `PRCP`, drei bei Detroits `SNOW`, und im vierten Feld teils der
literale Text `null`). Notebook 22 belegt das.

**Spaltennamen englisch.** Der Vorschlag oben nennt `stadt`, `fall_id`,
`zeitpunkt`; Abschnitt 6.1 hat dagegen „Code: englische Bezeichner" entschieden,
und Bronze folgt dem schon (`ingested_at_utc`, `pipeline_run_id`). Silver
verwendet deshalb englische Spaltennamen.

**`_extra` bleibt in Bronze.** Eine Größe von dort nach Silver zu heben kostet
eine Codeänderung und keinen neuen Ladelauf — der `SNWD`-Fall zeigt, dass das
trägt.

**Stand.** Alle vier Tabellen sind gebaut, jeweils mit Herkunftsnachweis über
die Bronze-Läufe im Manifest: `tract` (6'282 Zeilen), `place` (2'206 Zeilen,
die Stadtgrenzen), `weather_day` (55'449
Zeilen, zwei Städte) und seit dem 10.9. `crime_offense` (347'957 Zeilen,
259'272 Chicago und 88'685 Detroit; Detroits Zeilen sind Anklagen, je Tat
zählt eine — Gold kommt damit auf 344'617).

Der frühere Vorbehalt, `crime_offense` müsse auf Artans Zeitzonen-Fix warten,
trägt nicht mehr: Sein Branch ändert das **Abfragefenster** — welche Zeilen in
Bronze landen —, nicht das **Satzschema**. Silver liest aus unveränderlichen
Bronze-Läufen; ein Neubau nach seinem Merge zieht die Korrektur nach, ohne dass
am Silver-Code etwas zu ändern wäre. Geprüft am Diff seines Branches: keine
Änderung an den Feldern eines Datensatzes.

`crime_offense` löst dabei ein Problem, das vorher niemandem auffiel: **Chicago
liefert `date` als Ortszeit ohne Zonenangabe, Detroit Millisekunden seit Epoch.**
Ohne Umrechnung liegen beide Städte je nach Jahreszeit eine oder zwei Stunden
auseinander, und man sieht es keinem Wert an.

Aus `weather_day` ein Befund für die Abdeckung: Die Reihen reichen bis 1942
zurück und sind dort lückenhaft — Detroit fehlen 4'451 Tage, alle vor 1970.
**Ab 2001 ist die Reihe für beide Städte lückenlos**, 9'379 Tage je Stadt mit
durchgehend belegter Temperatur. Für den Zeitraum aus Abschnitt 2.2 ist die
Quelle also vollständig; das Manifest weist beides getrennt aus.

`Entscheid: Wird miteinander abgeglichen. Zwei Version, Abgleich welche besser Claude oder Codex.`

### 5.2 Was gehört in Gold?

**Vorschlag.** Auswertungsfertige Aggregate, je nach Leitfrage:

- Fälle je `geoid` × Monat × NIBRS-Kategorie
- dazu Einwohner aus ACS und die abgeleitete Rate je 1'000 Einwohner
- Abdeckungsquote je Zelle, damit eine Rate nie ohne ihre Verlässlichkeit dasteht

**Zu klären:** Tracts mit **null Einwohnern** (Wasserflächen, Flughäfen,
Industrie — in Michigan 103 Stück). Dort ist eine Rate nicht definiert.
Vorschlag: Rate `null`, absolute Zahl trotzdem ausweisen, Zelle in Auswertungen
kenntlich machen.

`Entscheid: Muss noch definiert werden. Forschungsfragen noch definieren.`

### 5.3 Werkzeug für Silver und Gold

**Stand.** Der Chicago-Modulkopf nennt DuckDB als Zielbild, im Code steht davon
noch nichts. Der räumliche Join braucht Punkt-in-Polygon.

| Variante | Vorteil | Nachteil |
| --- | --- | --- |
| pandas + shapely | vertraut, wenig Neues | Punkt-in-Polygon von Hand, langsam bei 350'000 Punkten |
| geopandas | `sjoin` in einer Zeile | zieht pandas, shapely, pyogrio, fiona mit |
| DuckDB + `spatial`-Extension | SQL, schnell, liest Parquet direkt | neues Werkzeug im Team |

**Vorschlag.** **DuckDB mit der `spatial`-Extension**, weil es Parquet direkt
liest, der Join als SQL nachvollziehbar bleibt und wir schon WKB in Bronze
liegen haben. Wer lieber bei Python bleibt: geopandas ist die pragmatische
Alternative. Wichtig ist vor allem, dass wir **eines** wählen.

`Entscheid: DuckDB`

### 5.4 DuckDB: Abfrageschicht oder zweite Kopie?

**Stand.** Der Detroit-Branch brachte `load_duckdb.py` mit, das Bronze in eine
DuckDB-Datei unter `data/warehouse/` importiert — als materialisierte Tabellen,
mit dem Datensatz als JSON-Blob. Absprache 7.1 hält dagegen fest:
dateibasierte Schichten als Speicher, **DuckDB als Abfrageschicht darüber**.

**Gemessen statt gestritten**, zweimal:

*Bronze, Abfrage über Detroits 88'695 Zeilen (Kategorie × Monat):*

| | Zeit | Grösse |
| --- | ---: | ---: |
| Parquet direkt | 3,8 ms | 12,1 MB |
| DuckDB-Kopie als JSON-Blob | **64,3 ms** | 32,0 MB |

Der Grund: `load_duckdb.py` legt den ganzen Datensatz als JSON ab und extrahiert
nur `incident_entry_id` in eine Spalte. Jede Auswertung muss also pro Zeile JSON
parsen. Die Kopie ist damit **17× langsamer und 2,6× grösser** als die Datei,
die sie ersetzen sollte.

*Serving, Ad-hoc über alle drei Silver-Tabellen (410'000 Zeilen):*

| | Sichten | Kopie |
| --- | ---: | ---: |
| Drei-Wege-Join | 4,4 ms | 5,1 ms |
| Join Delikt × Tract | 3,6 ms | 4,3 ms |
| Dateigrösse | **0,3 MB** | 45,1 MB |

Auch hier sind Sichten nicht langsamer, teils schneller. Ergebnisse in beiden
Messungen identisch geprüft. Methodik:
[`notebooks/33_serving_evaluation.ipynb`](../notebooks/33_serving_evaluation.ipynb).

**Entscheid: Sichten, keine Kopie.** Nicht wegen der Geschwindigkeit — die ist
ein Gleichstand —, sondern weil eine Kopie veralten kann, ohne dass man es ihr
ansieht, und weil sie eine zweite Wahrheit neben den unveränderlichen Schichten
ist. Gebaut in `src/crime/serving/build_analysis_db.py`.

**Was aus `load_duckdb.py` bleiben soll:** sein `validate_manifest`. Status,
Prüfsumme, fünf Zählwege gegeneinander, Schema-Fingerabdruck und die Herkunft
jeder Zeile — ein ernsthaftes Eingangstor, völlig unabhängig von der
Speicherfrage. Es gehört behalten; nur der Importer sollte später auf **Gold**
zielen statt auf Bronze.

`Entscheid: ______________________________________________`

---

## 6 · Dokumentation

**Stand.** Heute vier Formen nebeneinander: Notebooks (5 Stück), Markdown in
`docs/`, exportiertes HTML in `docs/` (drei Dateien, zusammen rund 340 KB), und
ausführliche Modul-Docstrings im Code.

**Dein Vorschlag — Notebooks — halte ich für richtig**, mit einer Ergänzung:
Notebooks eignen sich für alles, was man *zeigen* und *nachvollziehen* will.
Für Entscheidungen wie dieses Dokument taugen sie nicht, weil man Beschlüsse
nicht in Zellenausgaben sucht.

**Vorschlag: drei klar getrennte Orte.**

| Form | Wofür | Beispiel |
| --- | --- | --- |
| **Notebook** | Quelle erklären, Ingestion vorführen, Qualität prüfen, Ergebnisse zeigen | `01_chicago_source`, `03_chicago_data_quality` |
| **Markdown in `docs/`** | Entscheide, Absprachen, Anleitungen | dieses Dokument, `DETROIT_PIPELINE_ANLEITUNG.md` |
| **Docstring im Modul** | warum der Code so gebaut ist | Kopf von `download_chicago.py` |

Ergänzende Regeln zur Diskussion:

- **HTML nur als Export**, nie als Quelle. Wer eine Abgabe braucht, exportiert
  aus dem Notebook. Der aktuelle Bestand in `docs/` sollte entweder als Export
  gekennzeichnet oder entfernt werden — sonst pflegt man zwei Wahrheiten.
- **Notebooks ohne gespeicherte Ausgaben** einchecken. Das hält die Diffs lesbar;
  wer Ergebnisse braucht, führt aus. (Die neueren Notebooks sind bereits so abgelegt.)
- **Nummernschema festlegen.** Heute: 01, 02, 03, 05, 06 — mit Lücke bei 04.
  Vorschlag: 0x Chicago, 1x Detroit, 2x Census/Wetter, 3x übergreifende
  Auswertung. Dann kollidiert nichts, wenn jeder für sich weiterarbeitet.
- **Je Quelle zwei Notebooks**: eines zur Quelle, eines zur Ingestion. Dazu je
  Stadt eines zur Datenqualität. Für Detroit fehlen beide noch.

`Entscheid: Wird so umgesetzt`

### 6.1 Sprache und Schreibweise

**Stand.** Heute gemischt: deutsche Docstrings in ASCII-Umschreibung
(`Vollstaendigkeit`), englische Funktionsnamen, Notebooks und README auf Deutsch
mit Umlauten und Schweizer Schreibweise (`ss` statt `ß`).

**Vorschlag**, im Wesentlichen das Bestehende festgeschrieben:

- Prosa (Notebooks, `docs/`, README): **Deutsch mit Umlauten**, Schweizer Schreibweise
- Code: englische Bezeichner, deutsche Erklärungen — im Quelltext in
  ASCII-Umschreibung, damit Encoding nie zum Thema wird
- Variablennamen immer ASCII, auch in Notebooks

`Entscheid: Machen wir so`

---

## 7 · Zusammenarbeit

### 7.1 Wie kommen wir zum gleichen Datenstand?

**Stand.** `data/` ist vollständig aus Git ausgeschlossen — richtig so, allein
Chicago und Census belegen rund 70 MB. Jeder von uns lädt also selbst.

**Das Problem dabei:** Die Läufe sind **nicht identisch**. Wer heute lädt,
bekommt einen anderen `run_id` und durch die Delta-Logik andere Zeilen als wer
morgen lädt. Für Bronze ist das gewollt. Für einen gemeinsamen Auswertungsstand
ist es eine Fehlerquelle — wir würden über verschiedene Zahlen reden.

**Vorschlag.** Ein **Referenzstand** wird verabredet und im Repository
festgehalten: Jahrgang, TIGER- und ACS-Vintage sowie die `run_id`, auf die sich
Ergebnisse beziehen. Ergänzend eine kurze Anleitung „so kommst du zum gleichen
Stand" in der README. Alternative, falls uns Speicher egal ist: die
Gold-Tabellen einchecken, weil sie klein sind.

`Entscheid: Bei einem Daily Load wird darauf geschaut T-1 geladen wird. Dies muss ausgewiesen werden.`

### 7.2 Tests

**Stand.** 633 Tests, seit dem 11.9. einheitlich nach Pipeline gegliedert:

```text
tests/
├── census_pipeline/    ├── detroit_pipeline/   ├── silver_pipeline/
├── chicago_pipeline/   ├── config/             └── weather_pipeline/
```

Die Detroit-Tests lagen zuvor als einzige flach in `tests/`. Der Umzug macht
`python -m pytest tests/detroit_pipeline` möglich — vorher liess sich eine
Pipeline nur über einzelne Dateinamen ansteuern.

**Erledigt: Testdateien einheitlich unter `tests/<pipeline>/`.**

**Erledigt: ein Runner statt zwei.** `run_tests_and_log.py` ist gelöscht — er
hatte keinen einzigen Aufrufer, keine Dokumentation nannte ihn, und seine
Ausgabe war ohnehin nicht versioniert. Geblieben ist `run_tests.py`: Text-Log
und strukturierter JSON-Report je Lauf unter `logs/tests/`.

**Der eigentliche Punkt ist aber nicht die Zahl der Runner.** Der Runner ist
**zweimal** auf `unittest discover` zurückgefallen und meldete danach SUCCESS
nach 39 von damals 448 Tests — ein grüner Lauf, der 91 % der Suite nie angefasst
hatte. Der Loader erkennt nur `TestCase`-Klassen; die Tests für Chicago,
Census, Wetter, Silver und die Referenztabellen sind Modulfunktionen mit
`assert`, und `unittest` lädt die `conftest.py` gar nicht.

Ein Runner weniger verhindert das nicht. Was es verhindert, ist
[`tests/test_run_tests.py`](../tests/test_run_tests.py): Der Runner bekommt
dort ein winziges Verzeichnis mit **je einem Test beider Stile** und muss beide
finden. Gemessen wird die Fähigkeit, nicht der Bestand — der Test veraltet
also nicht mit jeder neuen Testdatei. Gegenprobe: Dreht man den Runner auf
`unittest discover` zurück, fallen vier dieser Tests.

Dafür kann `run_tests.py` jetzt auf ein anderes Verzeichnis gerichtet werden
(`--test-dir`, `--log-dir`). Ohne das liesse sich nur prüfen, was er auf der
echten Suite tut — und das hiesse, pytest in pytest zu starten.

Anspruch für neue Pipelines: Tests laufen ohne Netz und ohne Schlüssel, so wie
die bestehenden.

**Weiterhin offen: keine CI.** Niemand führt diese Tests bei einem Push aus;
das Abgabedokument nennt es unter DataOps als Lücke. Ein Runner mit
maschinenlesbarem Report ist die Vorarbeit dafür, mehr nicht.

### 7.3 Rollen und Reihenfolge

**Frage.** Wer macht was, und in welcher Reihenfolge? Vorschlag als
Diskussionsgrundlage:

| Schritt | Ergebnis | Wer | Bis |
| --- | --- | --- | --- |
| 1 | Dieses Dokument entschieden | beide | |
| 2 | Detroit-Datenqualität geprüft (Notebook wie 03) |Artan| |
| 3 | Detroit-Bronze angeglichen (falls 4.2 = A) |Artan, wenn Angleoich | |
| 4 | Silver: Dedup, Typen, räumlicher Join |Beide, besete Versio gewinnt | |
| 5 | NIBRS-Harmonisierung über beide Städte | Beide, beste Version gewinnt| |
| 6 | Gold: Aggregate und Raten | Beide überlegen Analyseszenarien | |
| 7 | Auswertungs-Notebook | Ausstehen | |
| 8 | Wetter-Pipeline (nur falls Variante C) | Umgesetzt durch Christian| |

Schritt 2 steht bewusst vorn: Erst wenn wir die Detroit-Daten so gut kennen wie
die Chicagoer, wissen wir, ob ein Vergleich überhaupt trägt.

`Entscheid: Machen wir sobald Artan bereit ist`

**Nachtrag 13.9.2026 — Verantwortliche je Datensatz.** Die Schritt-Tabelle
oben sagt, wer *baut*; sie sagt nicht, wen man fragt, wenn eine Quelle
klemmt. Das stand als Lücke in Tabelle 5.3 des Konzepts („niemand ist für
einen Datensatz benannt"). Stand nach der Arbeitsteilung vom 12.9.2026;
Stufennamen wie in `orchestration.run_all`. Ein Test hält die Tabelle
vollständig: jede Stufe des Run-Controllers muss hier stehen.

| Stufe | Datensatz | Modul | Verantwortlich | Belegt in |
| --- | --- | --- | --- | --- |
| `chicago` | `bronze/city=chicago` | `chicago_pipeline.download_chicago` | Christian | Notebooks 01–03 |
| `detroit` | `bronze/city=detroit` | `detroit_pipeline.extract_detroit` | Christian | Notebooks 11–13 |
| `tiger_tract` | `bronze/dataset=tiger_tract` | `census_pipeline.download_tiger` | Christian | Notebook 21 |
| `tiger_place` | `bronze/dataset=tiger_place` | `census_pipeline.download_tiger` | Christian | Notebook 21 |
| `acs` | `bronze/dataset=acs5_tract` | `census_pipeline.download_acs` | Christian | Notebook 21 |
| `noaa` | `bronze/dataset=noaa_ghcnd` | `weather_pipeline.download_noaa` | Christian | Notebook 22 |
| `tract`, `place`, `weather_day`, `crime_offense` | `silver/` | `silver_pipeline.*` | Christian | Konzept 8, Feldkatalog |
| `gold` | `gold/` (fünf Tabellen) | `gold_pipeline.build_gold` | Christian | Notebook 34, Konzept 5.2 |
| `analyse_db`, `tracts_geojson` | `serving/` | `serving.*` | Christian | Notebook 33 |
| — | Hypothesen (Kapitel 3, Notebook) | — | Artan | Konzept 3 |
| — | Konzept, Absprache, Leistungsnachweise, Präsentation | — | Artan | `docs/` |

Was die Tabelle **nicht** regelt: eine Stellvertretung. Fällt einer von uns
aus, übernimmt der andere — das ist bei zwei Personen keine Regel, sondern
der einzige Ausweg. Wer eine Quelle übernimmt, trägt sich hier ein.

### 7.4 Wann ist etwas fertig?

**Vorschlag** für eine gemeinsame Messlatte je Pipeline:

- [ ] Läuft über die Kommandozeile mit dokumentierten Argumenten
- [ ] Schreibt Raw und Bronze mit Manifest und Vollständigkeitsnachweis
- [ ] Tests vorhanden, laufen ohne Netz
- [ ] Ein Notebook zur Quelle, eines zur Ingestion
- [ ] In der README erwähnt

`Entscheid: Setzten wir so um`

---

## 8 · Offene Punkte für später

Nicht dringend, aber besser aufgeschrieben als vergessen:

- **Detroits Deliktkategorien** (32 Stück) gegen NIBRS abgeglichen? Für Chicago
  ist der Nachweis vollständig — alle 434 IUCR-Codes greifen, kein Fall ohne
  Zuordnung. Für Detroit steht der Gegenbeweis noch aus.
- **Zeitzonen.** Chicago liefert zonenlose Zeitstempel (lokale Zeit), unsere
  Läufe protokollieren UTC. Vor jeder Tagesauswertung klären, welche Zeit gilt —
  sonst wandern Fälle um Mitternacht in den falschen Tag.
- **Chicagos District `031`** existiert als Streifenbezirk nicht, hat aber 13
  Fälle. Nur relevant, falls jemand nach District gruppiert.
- **`case_number` ist kein Schlüssel** — 25 Fallnummern kommen mehrfach vor
  (ein Fall, mehrere Straftaten). Immer über `id` verknüpfen.
- **ACS-Fehlermargen.** Wir laden nur die Schätzwerte (`…E`), nicht die Margen
  (`…M`). Für Einwohnerzahlen als Nenner vertretbar, für Aussagen über
  Einkommensunterschiede nicht.
- **Mehrere Städte später?** Die Ablage ist über `city=` und `state=` dafür
  offen. Nichts zu tun, nur nicht verbauen.

---

## 9 · Zusammenfassung: die sechs Entscheide

Wenn die Zeit knapp ist, sind das die Punkte, ohne die es nicht weitergeht:

1. **Leitfrage** — A, B, C oder D? (2.1)
2. **Zeitraum** — nur 2024? (2.2)
3. **Detroit-Bronze** — angleichen oder nicht? (4.2)
4. **Silver-Werkzeug** — DuckDB oder geopandas? (5.3)
5. **Dokumentationsform** — Notebooks plus Markdown, HTML nur als Export? (6)
6. **Referenzstand** — worauf beziehen sich unsere Zahlen? (7.1)

---

## Anhang: Befehle zum aktuellen Stand

```bash
# Chicago, Jahrgang 2024 (erster Aufruf lädt voll, spätere als Delta)
python -m chicago_pipeline.download_chicago --year 2024

# Detroit, Jahrgang 2024
python -m detroit_pipeline.extract_detroit --year 2024

# Census: Geometrien und Attribute, beide Bundesstaaten
python -m census_pipeline.download_tiger --vintage 2024
python -m census_pipeline.download_acs   --vintage 2024

# Tests
python -m pytest
```
