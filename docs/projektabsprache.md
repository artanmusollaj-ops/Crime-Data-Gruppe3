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
| **Detroit** | Pipeline fertig | 88'695 Fälle 2024, 1 Lauf, 32 Deliktkategorien | nur bronze |
| **Census TIGER** | Pipeline fertig, getestet | 3'265 Tracts Illinois, 3'017 Michigan (Vintage 2024) | raw + bronze |
| **Census ACS** | Pipeline fertig, getestet | dieselben Tracts, 3 Variablen | raw + bronze |
| **Wetter (NOAA)** | Pipeline fertig, getestet | 29'181 Tage O'Hare (ab 1946), 26'264 Detroit Metro (ab 1942) | raw + bronze |

Ergänzend: 272 Tests, 5 Notebooks, `config/iucr_nibrs_mapping.csv` mit 434
Codes, `data/silver/` und `data/gold/` bislang leer.

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

`Entscheid: ______________________________________________`

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

`Entscheid: ______________________________________________`

### 2.3 Räumliche Einheit

**Stand.** Die Census-Pipeline lädt Tracts, beide Städte liefern Koordinaten.
Chicagos `community_area` und Detroits Bezirke sind untereinander nicht
vergleichbar.

**Vorschlag.** **Census Tract** als gemeinsame Einheit, Stadt als übergeordnete
Ebene. Chicagos `community_area` zusätzlich mitführen, weil sie für lokale
Leser aussagekräftiger ist.

`Entscheid: ______________________________________________`

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

`Entscheid: ______________________________________________`

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

`Entscheid: ______________________________________________`

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

Gebremst wird das heute nur durch eine Sperre in der Ingestion — ein
Schnappschuss je Station und Abruftag, ein zweiter Lauf am selben Tag lädt nicht.
`--force` und Backfills laden trotzdem voll.

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
abzuraten. GHCN-Daily ist ein qualitätsgeprüfter Datensatz, dessen Prüfläufe
auch ältere Werte korrigieren können; ein Anhängen des Dateiendes würde solche
Korrekturen stillschweigend übersehen. Belegt ist das nicht, wir haben erst
einen Schnappschuss. Der zweite macht es messbar: Ein Vergleich der ersten
10 MB beider Läufe zeigt, ob die Historie stabil bleibt.

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

`Entscheid: ______________________________________________`

---

## 4 · Bronze: der grösste Abstimmungsbedarf

**Stand.** Wir haben heute **drei verschiedene Bronze-Konventionen**:

| | Chicago | Detroit | Census |
| --- | --- | --- | --- |
| Pfad | `bronze/city=chicago/ingest_date=…/run_…/` | `bronze/detroit/<name>_<uuid>.ndjson` | `bronze/dataset=…/vintage=…/state=…/run_…/` |
| Partition | Hive (`city`, `ingest_date`) | keine | Hive (`dataset`, `vintage`, `state`) |
| Format | Parquet (snappy) | NDJSON | Parquet (snappy) |
| Lauf-Kennung | `run_<UTC-Zeitstempel>` | UUID4 | `run_<UTC-Zeitstempel>` |
| Manifest | `manifest.json` je Schicht im Lauf-Ordner | `<name>.manifest.json` daneben | wie Chicago |
| Manifest-Felder | `completeness`, `watermark`, `source_schema`, `query` | `offense_category_counts`, `pipeline_run_id`, … | wie Chicago plus `crs` |
| Raw-Schicht | ja | **nein** | ja |
| Schema | gepinnt, 23 Spalten, `_extra` | verschachteltes JSON (`attributes`/`geometry`/`_meta`) | gepinnt, 14 bzw. 9 Spalten, `_extra` |

Der Kommentar in `.gitignore` („Detroit legt (noch) flach ab") deutet darauf
hin, dass das bekannt und als Übergang gedacht war.

### 4.1 Was bedeutet „Bronze" bei uns?

**Frage.** Ist Bronze die unveränderte Landung oder schon eine tabellarische
Ableitung? Chicago und Census beantworten das mit **beidem**: Raw hält das
Original, Bronze ist die abgeleitete Tabelle. Detroits NDJSON übernimmt beide
Rollen gleichzeitig.

**Vorschlag.** **Zweischichtig, wie bei Chicago und Census.** Raw ist das
Beweisstück und unwiederbringlich; Bronze ist daraus jederzeit neu erzeugbar.
Diese Trennung hat sich bewährt: Beim Chicago-Schemafehler liess sich Bronze
neu ableiten, ohne die API erneut zu befragen.

`Entscheid: ______________________________________________`

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

`Entscheid: ______________________________________________`

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

`Entscheid: ______________________________________________`

---

## 5 · Silver und Gold

**Stand.** Beide Ordner sind leer. `transform_detroit.py` schreibt bereits
„Silver-nahe" Daten, ist aber noch nicht auf einen gemeinsamen Zielzustand
ausgerichtet.

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

`Entscheid: ______________________________________________`

### 5.2 Was gehört in Gold?

**Vorschlag.** Auswertungsfertige Aggregate, je nach Leitfrage:

- Fälle je `geoid` × Monat × NIBRS-Kategorie
- dazu Einwohner aus ACS und die abgeleitete Rate je 1'000 Einwohner
- Abdeckungsquote je Zelle, damit eine Rate nie ohne ihre Verlässlichkeit dasteht

**Zu klären:** Tracts mit **null Einwohnern** (Wasserflächen, Flughäfen,
Industrie — in Michigan 103 Stück). Dort ist eine Rate nicht definiert.
Vorschlag: Rate `null`, absolute Zahl trotzdem ausweisen, Zelle in Auswertungen
kenntlich machen.

`Entscheid: ______________________________________________`

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

`Entscheid: ______________________________________________`

### 6.1 Sprache und Schreibweise

**Stand.** Heute gemischt: deutsche Docstrings in ASCII-Umschreibung
(`Vollstaendigkeit`), englische Funktionsnamen, Notebooks und README auf Deutsch
mit Umlauten und Schweizer Schreibweise (`ss` statt `ß`).

**Vorschlag**, im Wesentlichen das Bestehende festgeschrieben:

- Prosa (Notebooks, `docs/`, README): **Deutsch mit Umlauten**, Schweizer Schreibweise
- Code: englische Bezeichner, deutsche Erklärungen — im Quelltext in
  ASCII-Umschreibung, damit Encoding nie zum Thema wird
- Variablennamen immer ASCII, auch in Notebooks

`Entscheid: ______________________________________________`

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

`Entscheid: ______________________________________________`

### 7.2 Tests

**Stand.** 240 Tests, aber ungleich verteilt: Chicago und Census liegen in
`tests/<pipeline>/`, die Detroit-Tests direkt in `tests/`.

`test_results.txt` ist mit PR #9 aus der Versionierung genommen und steht
zusammen mit `logs/` in `.gitignore`. Dabei kam heraus, dass beide Test-Runner
ihre Protokolle über `unittest discover` erzeugten und damit nur die zwölf
Detroit-Tests ausführten, den Lauf aber als Gesamterfolg meldeten — ein Bruch in
Chicago oder Census lief mit Exit-Code 0 durch. Beide laufen jetzt über pytest
und tun damit dasselbe.

**Vorschlag.** Testdateien einheitlich nach `tests/<pipeline>/`, also auch die
Detroit-Tests. Von den beiden Runnern einen behalten: `run_tests.py` schreibt
Text-Log und strukturierten JSON-Report unter `logs/tests/`,
`run_tests_and_log.py` hält die letzten fünf Läufe in einer Textdatei. Anspruch
für neue Pipelines: Tests laufen ohne Netz und ohne Schlüssel, so wie die
bestehenden.

`Entscheid: ______________________________________________`

### 7.3 Rollen und Reihenfolge

**Frage.** Wer macht was, und in welcher Reihenfolge? Vorschlag als
Diskussionsgrundlage:

| Schritt | Ergebnis | Wer | Bis |
| --- | --- | --- | --- |
| 1 | Dieses Dokument entschieden | beide | |
| 2 | Detroit-Datenqualität geprüft (Notebook wie 03) | | |
| 3 | Detroit-Bronze angeglichen (falls 4.2 = A) | | |
| 4 | Silver: Dedup, Typen, räumlicher Join | | |
| 5 | NIBRS-Harmonisierung über beide Städte | | |
| 6 | Gold: Aggregate und Raten | | |
| 7 | Auswertungs-Notebook | | |
| 8 | Wetter-Pipeline (nur falls Variante C) | | |

Schritt 2 steht bewusst vorn: Erst wenn wir die Detroit-Daten so gut kennen wie
die Chicagoer, wissen wir, ob ein Vergleich überhaupt trägt.

`Entscheid: ______________________________________________`

### 7.4 Wann ist etwas fertig?

**Vorschlag** für eine gemeinsame Messlatte je Pipeline:

- [ ] Läuft über die Kommandozeile mit dokumentierten Argumenten
- [ ] Schreibt Raw und Bronze mit Manifest und Vollständigkeitsnachweis
- [ ] Tests vorhanden, laufen ohne Netz
- [ ] Ein Notebook zur Quelle, eines zur Ingestion
- [ ] In der README erwähnt

`Entscheid: ______________________________________________`

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
