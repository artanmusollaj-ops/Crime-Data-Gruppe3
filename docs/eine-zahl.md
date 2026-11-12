# 94,5 — eine Zahl und ihre Herkunft

Dieses Dokument rollt **eine einzige Zahl** rückwärts auf, von der Folie bis
zu den Bytes, die die Stadt Chicago geliefert hat. Sieben Stufen, und auf dem
Weg kommt **jede wesentliche Entscheidung dieses Projekts genau einmal vor**.

Die Zahl ist die Rate **für den Jahrgang 2024**, und das ist keine Fussnote:
Seit dem 4.10.2026 liegen sechs Jahrgänge (2021–2026) in derselben
Faktentabelle. Wer sie alle zählt und durch die Einwohner eines Jahres teilt,
erhält 509,7 — eine Zahl, die nicht zu hoch ist, sondern nichts bedeutet.
Jede Zahl auf den Stufen 0 bis 4 ist deshalb auf 2024 eingegrenzt; die Stufen
5 bis 7 verfolgen die Herkunft der ganzen Tabelle.

Es ist damit auch die Antwort auf die Frage, die eine Abgabe verdient: *Woher
wisst ihr das?*

> Alle Zahlen hier sind gemessen, nicht getippt. `tests/test_eine_zahl.py`
> hält sie gegen die gebauten Daten — wer eine Schicht neu baut und dieses
> Dokument vergisst, fällt durch.

---

## Stufe 0 · Die Zahl

> **Jahrgang 2024 — Chicago: 94,5 Fälle je 1'000 Einwohner. Detroit: 124,7.**

Das ist der Satz, der auf eine Folie kommt. Absolute Zahlen legen das
Gegenteil nahe — Chicago meldet dreimal so viele Delikte wie Detroit. Erst der
Nenner dreht das Bild.

Gezählt wird ein **Fall**: ein Vorfall mit seinem schwersten Delikt, nach
derselben Regel für beide Städte (Stufe 4). Auf der Tatebene, die jedes Delikt
eines Vorfalls zählt, stehen dieselben Städte bei 94,5 und 134,0.

## Stufe 1 · Die Rechnung

```text
251'482 Fälle  /  2'661'953 Einwohner  ×  1000  =  94,47
```

Zwei Fragen stecken darin, und beide sind Entscheidungen: **Welche Einwohner?**
und **welche Fälle?**

## Stufe 2 · Der Nenner — welche Tracts sind Chicago?

**782 Census Tracts** mit zusammen 2'661'953 Einwohnern.

Tracts liegen nicht sauber in Stadtgrenzen, sie überschreiten sie. Deshalb die
**Mehrheitsregel**: Ein Tract gehört zur Stadt, wenn mehr als die Hälfte
seiner Fläche darin liegt. Gemessen reicht der Flächenanteil der 782 Tracts
von **0,515 bis 1,000** — der knappste hängt an anderthalb Prozentpunkten.

**22 Tracts berühren eine der beiden Städte und gehören ihr trotzdem nicht.**
Das ist keine Feinheit: Diese Randtracts sind überdurchschnittlich
deliktdicht, und weil sie herausfallen, ist Chicagos Rate um gut einen Punkt
untertrieben — **94,5 statt 95,6** (Konzept 9, gemessen in Notebook 34).

Die Einwohnerzahl selbst ist die ACS-Variable `B01003_001E`, eine
**5-Jahres-Schätzung**, keine Zählung. **Drei** der 782 Tracts haben null
Einwohner — Flughafen, Industrie, Sondernutzung. Für sie ist keine Rate
definiert.

Der Nenner hängt am **ACS-Jahrgang**: `dim_tract_acs` führt für jeden der
782 Tracts vier Schätzungen (2021 bis 2024), und `fact_offense.population_vintage`
sagt je Tat, welche für sie gilt. Die 2'661'953 hier sind die Schätzung
**2024** — dieselbe, die `dim_tract.reference_vintage` für die Stadtzuordnung
nennt. Für 2021 wären es 2'693'319, und mit ihnen eine andere Rate.

## Stufe 3 · Der Zähler — welche Delikte zählen mit?

Chicago meldet **259'686** Delikte im Jahrgang 2024. In die Rate gehen
**251'512**. Der Unterschied ist vollständig erklärt:

| `geo_status` | Delikte | was es bedeutet |
| --- | ---: | --- |
| `inside_city` | 251'512 | zählt |
| `outside_city` | 6'010 | liegt in einem Tract, der nicht zu Chicago gehört |
| `missing_coordinate` | 2'163 | die Stadt hat keine Koordinate geliefert |
| `no_tract` | 1 | Koordinate in keinem Tract |
| **Summe** | **259'686** | |

Die Summe geht **exakt** auf. Das ist der Zweck der Spalte: Was fehlt, wird
gezählt und benannt, nicht stillschweigend weggelassen.

Dieselbe Frage stellt sich für die Deliktart. Chicago liefert IUCR-Codes, die
über einen Crosswalk auf NIBRS abgebildet werden — und wie sicher das ist,
steht je Zeile:

| `mapping_status` | Zeilen | |
| --- | ---: | --- |
| `exact` | 248'243 | ein amtliches Dokument belegt die Zuordnung |
| `fallback_90Z` | 7'719 | Auffangcode, weil keine Kategorie passt |
| `ambiguous` | 3'721 | mehrere wären vertretbar, wir haben entschieden |
| `unmapped` | 3 | |

## Stufe 4 · Gold ← Silver: welche Zeile zählt?

`gold/fact_offense` nimmt aus `silver/crime_offense` nur die Zeilen mit
`counts`. Für Chicago sind das im Jahrgang 2024 alle **259'686** — eine
Chicagoer Zeile ist bereits ein Delikt. Für Detroit sind es 86'236 von 88'704
Zeilen: Detroit führt je Delikt einer Anzeige eine Zeile, und Nebendelikte
zählen nach der Hierarchieregel nicht mit.

Auf **Fallebene** bleiben in Chicago 259'656 Zeilen, also 30 weniger. Die
Differenz sind Mordfälle: Chicago führt je **Opfer** einen Datensatz. **25
Chicagoer Fälle** haben mehr als eine Zeile, und es sind ausnahmslos diese.

In Detroit ist der Abstand grösser: 86'236 Delikte gehören zu 80'248 Fällen.
Dieselbe Regel, zwei verschiedene Erfassungspraxen — genau deshalb steht sie
für beide Städte im Code und nicht als Chicago-Sonderfall.

Welche Granularität man wählt, verschiebt beide Städte — und Detroit stärker:

| | Tatebene | Fallebene |
| --- | ---: | ---: |
| Chicago | 94,5 | **94,5** |
| Detroit | 134,0 | **124,7** |

Vorn steht die Fallebene (E-2): Sie bringt beide Städte auf einen Massstab.
Anteile je Deliktart rechnen dagegen auf der Tatebene, denn nur dort
addieren sich die Kategorien.

## Stufe 5 · Silver ← Bronze: die Herkunftskette

Das Gold-Manifest sagt nicht nur *woher*, sondern *welcher Stand*:

```text
gold/fact_offense          Vertrag 8, Eingabeabdruck 9fd415fc26d14f70…
└── silver/crime_offense    Eingabeabdruck b90a1fe43e3706df…
    ├── Chicago Bronze     run_20261110T125951603079Z   Vollschnappschuss 2021
    │                      run_20261110T130257815163Z   Vollschnappschuss 2022
    │                      run_20261110T130535147853Z   Vollschnappschuss 2023
    │                      run_20261110T131057453169Z   Vollschnappschuss 2024
    │                      … 2 weitere, 2025 und 2026
    ├── Detroit Bronze     bca68e85-…  73a0467b-…  … 4 weitere
    ├── silver/tract       Eingabeabdruck 215d02b2753944d9…
    │   ├── TIGER          run_20260906T121504814962Z   (FIPS 17 und 26)
    │   └── ACS 5-Jahre    run_20260906T121507392858Z   (FIPS 17 und 26)
    └── Crosswalks         iucr_nibrs_mapping.csv       sha256 ed361200…
                           micr_nibrs_mapping.csv       sha256 35b292ac…
                           nibrs_offense_codes_2025.csv sha256 6f650716…
                           mapping_overrides.csv        sha256 f64d574c…
```

Die Läufe je Stadt sind **6**: je Jahrgang der Vollschnappschuss vom
10.11.2026, und danach noch kein Delta. Das Diagramm nennt die ersten und
zählt die übrigen. Derselbe Silver-Abdruck steht im Release
`2026-11-10T13-47-23Z` auf `srv01` — lokal und auf dem Server ist es
derselbe Stand.

Ein Pfad wäre hier zu wenig: Er zeigt auf das, was gerade dort liegt. Der
Abdruck sagt, **auf welchen Eingaben** der Stand ruht. Und die Kette hängt
nicht nur am Zähler — der Nenner hat seine eigene, und die Crosswalks hängen
mit ihrer Prüfsumme daran, weil eine geänderte Zuordnungstabelle die Zahlen
genauso verschiebt wie neue Daten.

Alle zwölf Kriminalitätsläufe dieses Stands sind in
`config/referenzstand.csv` als `LN2` gepinnt und überleben jedes Aufräumen,
ebenso die Census- und Wetterläufe dahinter — 19 Läufe zusammen. Die Läufe des LN1-Stands bleiben daneben
gepinnt: Ein Pin ist eine Zusage, die man nur geben soll, wenn man sie halten
will — und die abgegebene LN1-Fassung beruft sich auf sie.

## Stufe 6 · Bronze ← die Quelle

Der Vollschnappschuss des Jahrgangs 2024 vom 10. November, 13:10 bis
13:13 Uhr UTC:

```text
run_20261110T131057453169Z    mode = full_snapshot    259'686 Zeilen

Vollständigkeit   verified = true
                  Zählung vorher    259'686
                  Zählung nachher   259'686
                  geladen           259'686
                  Quelle hat sich während des Laufs nicht geändert
                  sha256 über die id-Menge   8daf7587…

Quellschema       22 Felder, Abdruck a79ce54c…
Abfrage           …/resource/ijzp-q8t2.json?$where=date >= '2024-01-01…'
Wasserzeichen     updated_on, höchster gesehener Wert 2026-11-09T15:54:27
```

Der Schemaabdruck ist derselbe wie beim LN1-Stand vom 5.9.2026: Die Stadt hat
in zwei Monaten kein Feld geändert. Gewachsen ist der Jahrgang trotzdem, von
259'272 auf 259'686 Zeilen — Meldungen zu 2024, die erst 2026 kamen.

**Vollständigkeit wird nicht behauptet, sondern nachgewiesen.** Vor dem
Download wird die Menge der `id` festgeschrieben und gehasht, geladen wird per
Keyset-Pagination, und danach muss die geladene Menge exakt der
festgeschriebenen entsprechen. Die zweite Zählung nach dem Lauf beantwortet
die Frage, die sonst offen bliebe: ob sich die Quelle unter uns bewegt hat.
Der Schemaabdruck macht sichtbar, wenn die Stadt ein Feld ändert.

## Stufe 7 · Raw — das Beweisstück

**26 Antworten, zusammen rund 17,6 MB**, Byte für Byte wie geliefert,
gzip-komprimiert:

```text
data/raw/city=chicago/ingest_date=2026-11-10/run_20261110T131057453169Z/
├── page-0001.json.gz        674'542 Bytes   sha256 2120afae…
├── …
├── page-0026.json.gz
└── manifest.json
```

Hier endet die Kette. Was darunter liegt, gehört der Stadt Chicago.

---

## Derselbe Weg an einem einzigen Fall

`JH100028` — der **erste Mordfall des Jahrgangs 2024**, und zugleich einer der
25 Chicagoer Fälle mit mehr als einer Zeile:

| | `offense_id` 27932 | `offense_id` 27933 |
| --- | --- | --- |
| Ortszeit | 2024-01-01 00:56 | 2024-01-03 20:59 |
| UTC | 2024-01-01 06:56 | 2024-01-04 02:59 |
| `hour_of_day` | 0 | 20 |
| IUCR | `0110` FIRST DEGREE MURDER | dito |
| NIBRS | `09A` Murder and Nonnegligent Manslaughter | dito |
| `mapping_status` | `exact` | `exact` |
| Tract | 17031690400 | dito |
| `geo_status` | `inside_city` | `inside_city` |
| **zählt als Tat** | ja | **ja** |
| **zählt als Fall** | ja | **nein** |

Ein Fall, zwei Opfer, zwei Zeilen. Auf Tatebene zählen beide, auf Fallebene
die frühere — das zweite Opfer starb zwei Tage später.

In diesem einen Fall stecken vier Entscheidungen des Projekts:

* **Zeitzone** — Chicago liefert `date` ohne Zonenangabe. 00:56 ist Ortszeit,
  06:56 ist UTC; beim zweiten Opfer springt die UTC-Zeit sogar auf den
  Folgetag. Ohne Umrechnung lägen die beiden Städte auf verschiedenen Achsen,
  und `hour_of_day` wäre falsch.
* **NIBRS** — `0110` ist Chicagos Hausklassifikation; `09A` ist die Achse, auf
  der Detroit vergleichbar wird.
* **Raum** — der Tract kam aus dem eigenen Punkt-in-Polygon-Join, nicht aus
  der Quelle. Sein Flächenanteil ist 1,000, er liegt ganz in Chicago.
* **Granularität** — dieselbe Zeile zählt je nach Frage einmal oder zweimal.

Der Tract 17031690400 trägt 656 Delikte auf 3'319 Einwohner: **197,6 je
1'000**, gut das Doppelte des Stadtschnitts. Auch das ist eine Zahl, die ohne
ihren Nenner nichts sagt.

---

## Was die Zahl nicht sagt

* **Erfassung ist nicht Kriminalität.** Gemessen wird, was angezeigt und
  erfasst wurde.
* **Tatort ist nicht Wohnort.** Ein Innenstadt-Tract mit wenigen Einwohnern
  und vielen Pendlern bekommt eine überhöhte Rate — siehe die 197,6 oben.
* **Der Nenner hat eine gröbere Zeitachse als der Zähler.** Die
  ACS-Schätzung liegt je Jahrgang vor, aber nur bis 2024: Die Raten für 2025
  und 2026 ruhen deshalb auf der Bevölkerung von 2024, und
  `fact_offense.population_vintage` schreibt das je Zeile hin, statt es einer
  Fussnote zu überlassen.
* **Die Mehrheitsregel ist nicht neutral.** 94,5 statt 95,6.

---

## Die Karte der Entscheidungen

| Stufe | Entscheidung | Wo sie steht |
| --- | --- | --- |
| 2 | Mehrheitsregel für die Stadtzuordnung | Konzept 5.2, Notebook 34 |
| 2 | ACS-Schätzung als Nenner, ohne Fehlermargen | Konzept 9 |
| 3 | `geo_status` statt stillem Weglassen | Konzept 5.3 |
| 3 | `mapping_status` als Güte der Zuordnung | Konzept 8.2 |
| 4 | Tat- und Fallebene nebeneinander | `AENDERUNGEN.md` #66 |
| 5 | Herkunft als Stand, nicht als Pfad | `AENDERUNGEN.md` #77 |
| 5 | Gepinnter Referenzstand | `AENDERUNGEN.md` #79 |
| 6 | Vollständigkeitsnachweis über die id-Menge | Konzept 6.1 |
| 6 | Schemaabdruck gegen Drift | Konzept 6.1 |
| 7 | Raw als Beweis, getrennt von Bronze | Konzept 7.3 |
