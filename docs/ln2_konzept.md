# Leistungsnachweis 1: Konzept und Umsetzung

**Vergleichbare Kriminalitätsdaten für Chicago und Detroit**

CAS Data Engineering · Gruppe 3 · Christian Antonucci, Artan Musollaj

---

Dieses Dokument ist die **Arbeitsfassung** zu Leistungsnachweis 1: Es beschreibt,
was gebaut wurde und warum es so gebaut wurde. Die Abgabe selbst entsteht als
eigenes Word-Dokument und wird aus diesem hier geschrieben.

**Warum die Fassung hier die belastbarere ist.** Jede Zahl darin wird von der
Testsuite gegen die gebauten Daten gehalten; eine veraltete Zahl lässt einen
Test fallen. Im Word-Dokument gilt das nicht mehr — dort ist eine Zahl so
aktuell wie der Tag, an dem sie kopiert wurde. Wer überträgt, überträgt am
besten kurz vor der Abgabe und prüft danach `python -m pytest -m referenzstand`.

Zwei weitere Dokumente ergänzen dieses und fliessen **nicht** in die Abgabe ein:
[`projektabsprache.md`](intern/projektabsprache.md) hält die technischen Entscheide mit
ihrer Begründung, [`leistungsnachweise.md`](intern/leistungsnachweise.md) stellt die
Anforderungen dem Stand gegenüber. Wo eine Aussage hier auf einer Messung
beruht, steht der Verweis auf das Notebook, das sie erzeugt — die Zahlen sind
nachrechenbar, nicht abgeschrieben.

> **Was Entwurf ist und was gebaut.** Kapitel 3 (Forschungsfragen und
> Hypothesen) ist Entwurf, weil der Entscheid offen ist. Kapitel 5.2 (Serving)
> ist zur Hälfte gebaut: Die Auswertungsumgebung steht, die Gold-Tabellen
> darunter sind entworfen — LN1 verlangt für den Lebenszyklus ausdrücklich den
> Entwurf. Alle übrigen Kapitel beschreiben Umgesetztes, und wo etwas fehlt,
> steht es dort.

---

## 1 · Kurzfassung

Kriminalitätsstatistiken einzelner US-Städte sind öffentlich und detailliert
verfügbar, aber untereinander kaum vergleichbar. Dieses Projekt baut die
Datengrundlage, die einen belastbaren Vergleich zwischen Chicago und Detroit
überhaupt erst erlaubt: harmonisierte Delikte über den nationalen
NIBRS-Standard, eine gemeinsame Raumeinheit über Census Tracts, Einwohnerzahlen
als Nenner für Raten — und Wetter als dritte Zeitachse.

Umgesetzt sind **fünf Quellen in vier Ingestion-Pipelines**, eine
Speicherarchitektur aus unveränderlichen Läufen, und **alle vier
Silver-Tabellen** — seit `crime_offense` sprechen beide Städte dieselbe
Deliktsprache, liegen auf derselben Zeitachse und tragen dieselbe
Raumeinheit. Darauf steht das **Gold-Sternschema** aus einer Faktentabelle
und fünf Dimensionen (5.2), darauf die Auswertungsumgebung. Die Schichten
liegen wahlweise lokal oder auf einem gemeinsamen Objektspeicher (7.4).
Jede Quelle weist ihre Vollständigkeit nach, statt sie zu behaupten.
**1'850 automatisierte Tests** laufen ohne Netzzugriff und ohne Schlüssel.

Gebaut sind die **sechs Jahrgänge 2021 bis 2026**; 2026 ist ein Teiljahr und
als solches gekennzeichnet (`dim_date.year_is_complete`).

| | |
| --- | --- |
| Chicago, Jahrgänge 2021–2026 | 1'383'653 Delikte |
| Detroit, Jahrgänge 2021–2026 | 491'725 Anklagen zu 468'297 Taten |
| Census Tracts, Illinois und Michigan | 6'282 je ACS-Vintage, vier Vintages — mit Geometrie und Sozialdaten |
| Wetter, zwei Stationen | 55'497 Stadt-Tage, zurück bis 1942 |

**Raten gelten je Jahr, nicht je Bestand.** Wo unten eine Rate je 1'000
Einwohner steht, nennt sie ihren Jahrgang — 2024, den jüngsten vollständigen.
Sechs Jahre Zähler auf einem Jahr Nenner ergäben 500,7 für Chicago, und diese
Zahl sieht aus wie eine Zahl.

**Drei Befunde sind dabei entstanden, die keine Fehlermeldung erzeugt hätten.**
Der räumliche Join reproduziert Detroits eigene Tract-Angabe nicht (8.4). Der
erste Chicago-Crosswalk lieferte gültige NIBRS-Codes für das falsche Delikt
(8.5). Und Detroits Jahrgang 2024 enthielt 66 Fälle aus 2023, weil das
Abfragefenster in UTC statt in Ortszeit gezogen war (8.6). Alle drei waren
formal einwandfrei; sichtbar wurden sie erst durch eine Prüfung gegen etwas,
das wahr sein muss.

---

## 2 · Problemstellung und Ausgangslage

Jede Stadt erfasst Kriminalität nach eigenen Regeln. Chicago verwendet den
**IUCR**-Schlüssel mit 434 Codes, Detroit eigene Deliktkategorien — 32 an der
Zahl. Die Raumeinheiten unterscheiden sich ebenso: Chicago führt Community
Areas, Wards und Beats, Detroit Precincts, Scout Car Areas und Council
Districts. Keine dieser Einheiten existiert in der anderen Stadt.

Absolute Fallzahlen sagen zudem wenig, solange die Bevölkerung des betrachteten
Gebiets unbekannt ist. Ein Innenstadtbezirk mit tausend Einwohnern und
zehntausend Pendlern ist mit einem Wohnquartier nicht vergleichbar, wenn man
nur zählt.

**Warum diese beiden Städte.** Chicago und Detroit liegen beide im Mittleren
Westen, unterscheiden sich in ihrer wirtschaftlichen Entwicklung aber
grundlegend: Chicago als wachsende Metropole, Detroit nach jahrzehntelangem
Bevölkerungsrückgang und der Insolvenz von 2013. Beide veröffentlichen ihre
Falldaten offen und feingranular.

**Der Weg zur Vergleichbarkeit** führt über drei Übersetzungen:

1. **Delikte** — beide Schlüsselsysteme auf **NIBRS** abbilden, den nationalen
   Standard des FBI
2. **Raum** — Koordinaten auf **Census Tracts** abbilden, die einzige
   Raumeinheit, die für beide Städte nach derselben Methodik definiert ist
3. **Nenner** — Einwohnerzahlen aus dem **American Community Survey**, damit aus
   Fallzahlen Raten werden

Erst danach ist die eigentliche Frage überhaupt stellbar. Dieses Projekt baut
diese Grundlage — es ist ein Data-Engineering-Projekt, keine kriminologische
Studie.

---

## 3 · Forschungsfragen und Hypothesen

> **Der Wortlaut dieses Kapitels ist der abgegebene.** Er steht erzeugt in
> [`forschungsfragen.md`](forschungsfragen.md), aus der eingereichten Fassung
> gezogen; `tests/test_forschungsfragen.py` hält dieses Kapitel dagegen. Wer
> hier eine Frage oder eine Hypothese umformuliert, lässt den Wächter fallen —
> und das ist der Zweck: Der Wortlaut wurde eingereicht und bewertet, er ist
> Beleg und nicht Entwurf.

### 3.1 Zwei Ebenen von Fragen

Die Forschungsfragen dieses Leistungsnachweises sind **Fragen des Data
Engineering**, nicht der Kriminologie. Geprüft wird, ob die Daten für ihren
Zweck taugen und wie das nachgewiesen wird — nicht, welche Stadt gefährlicher
ist.

Das Modul Transformation stützt diese Lesart: Es definiert Datenqualität
ausdrücklich als **Funktion des Verwendungszwecks**. Genau daraus folgt aber,
dass beide Ebenen gebraucht werden. Die **Anwendungsebene** legt fest, wofür die
Daten taugen müssen, und liefert damit den Massstab für „gut genug"; die
**Data-Engineering-Ebene** ist Gegenstand der Fragen und Hypothesen. Die
Anwendungsebene ist Rahmen, nicht Prüfgegenstand.

### 3.2 Forschungsfragen

Über den sechs Teilfragen steht eine:

> **Übergeordnete Forschungsfrage.** Wie lässt sich eine schlanke
> Batch-Datenplattform gestalten, die heterogene Kriminalitätsdaten aus Chicago
> und Detroit reproduzierbar beschafft, fachlich nachvollziehbar harmonisiert
> und qualitätsgesichert für analytische Anwendungen bereitstellt?

Die sechs Teilfragen zerlegen sie entlang der Strecke — Beschaffung,
Verarbeitung, Zeit, Deliktschema, Wiederherstellbarkeit, Technik:

| | Frage |
| --- | --- |
| **F1** | Wie werden Downloads trotz Pagination und veränderlicher Quellen abgesichert? |
| **F2** | Wie wirken sich wiederholte Lieferungen auf Silber und Gold aus? |
| **F3** | Wie werden lokale Tat-Tage trotz unterschiedlicher Zeitdarstellung korrekt gebildet? |
| **F4** | Welche Unterschiede bleiben trotz gemeinschaftlichen Deliktschemas bestehen? |
| **F5** | Welche Voraussetzungen benötigt die Wiederherstellung einer Kennzahl? |
| **F6** | Reichen Parquet und DuckDB für den Umfang aus? |

### 3.3 Hypothesen

Je Frage eine Hypothese, alle falsifizierbar, alle mit einem Verfahren aus dem
Modul prüfbar, alle mit den vorliegenden Daten durchführbar. Die Spalte
„Ergebnis" ist die Beantwortung aus Kapitel 11 der Abgabe: **Alle sechs halten,
zwei mit Einschränkung.** Der Rechenweg steht in
[`../notebooks/36_hypothesen.ipynb`](../notebooks/36_hypothesen.ipynb), das jede
Zahl darin selbst nachrechnet.

| | Hypothese | Ergebnis |
| --- | --- | --- |
| **H1** | Bei einem erfolgreichen Lauf entspricht die gelieferte Menge genau der vorab ermittelten Erwartungsmenge; bei Quellen ohne Identifikator-Menge tritt ein gleichwertiger Nachweis an ihre Stelle. | hält, wörtlich für Chicago und Detroit; die drei Referenzquellen belegen Vollständigkeit gleichwertig |
| **H2** | Zweimalige Verarbeitung identischer Eingaben und Regeln erzeugt dieselben fachlichen Tabelleninhalte und Kennzahlen. | hält; drei Neubauten, sechs Tabellen, identischer sortierter Inhalt |
| **H3** | Die lokale Tageszuordnung und die fachlichen Abfragegrenzen sind unabhängig von der Zeitzone des ausführenden Rechners. Nichtexistierende oder mehrdeutige lokale Quellzeiten werden ausdrücklich als Sonderfälle ausgewiesen. | hält in beiden Teilen; die Ausweisung wurde am 16.09.2026 ergänzt |
| **H4** | Codebasierte und versionierte Zuordnungen machen mehr fachlich relevante Mehrdeutigkeiten sichtbar als eine alleinige Zuordnung nach Kategoriebezeichnung. | hält deutlich; 71 % der Zeilen unter mehrdeutiger Bezeichnung |
| **H5** | Ein fixierter Eingabestand mit erhaltenen Referenzdateien, Code, Konfiguration und Abhängigkeiten liefert bei erneutem Aufbau dieselben fachlichen Ergebnisse. | hält für den gepinnten Stand; zweite Umgebung offen |
| **H6** | Silver, Gold und Serving lassen sich auf dem festgelegten Referenzrechner in weniger als zehn Minuten aufbauen. | hält; Median 27 bis 31 Sekunden |

**Die Grenze des Nachweises gehört dazu** und steht in der Abgabe direkt unter
dieser Tabelle: Der Vollständigkeitsnachweis aus H1 betrifft die
**Mitgliedschaft** der Datensätze, nicht einen transaktional eingefrorenen
Attributzustand der externen Quelle. Ein Datensatz kann sich während des
Downloads ändern.

**H2 und H4 sprechen die Begriffe des Moduls präzise an.** Ein *Duplikat* ist in
jedem Attribut identisch, eine *Dublette* meint dieselbe Sache mit abweichenden
Werten; H2 zeigt an Chicagos absichtlich überlappenden Delta-Läufen, dass der
Überlapp nur Duplikate erzeugt (8.3). H4 trennt *Code* von *Bezeichnung* — und
zeigt, dass eine hohe Zuordnungsquote kein Beleg richtiger Zuordnung ist (8.5).
Beide Unterscheidungen lassen sich an den vorliegenden Daten mit einem belegten
Ergebnis zeigen statt mit einer Definition.

### 3.4 Qualitätsdimensionen als Massstab

Ob die Daten „für ihren Zweck taugen", braucht einen Massstab. Angelehnt an
ISO 8000, jede Dimension mit einer Kennzahl, die sich berechnen lässt:

| Dimension | Kennzahl |
| --- | --- |
| Vollständigkeit (Lauf) | geladene gegen erwartete Zeilen |
| Vollständigkeit (Feld) | Füllgrad je Pflichtspalte |
| Eindeutigkeit | Anteil doppelter Schlüssel nach Deduplikation |
| Gültigkeit | Anteil Werte im erlaubten Bereich |
| Konsistenz | Anteil Zeilen ohne Feldwiderspruch |
| Genauigkeit | Anteil verortbarer Fälle |
| Aktualität | Abstand des jüngsten Änderungszeitpunkts |

Der Verwendungszweck legt die Schwellen fest, und genau deshalb hängen die
beiden Ebenen aus 3.1 zusammen. Für eine Rate je Tract ist eine
Verortungsquote von 99,3 % gut — aber nur, solange die fehlenden 0,7 % nicht
systematisch verzerrt sind. Detroit liegt mit 99,7 % besser, doch die Quote
allein sagt nicht, ob sie trägt: Welche Fälle fehlen, hängt am Delikttyp, und
das ist gemessen. Der Befund steht in 8.7.

### 3.5 Woher diese Nummern kommen

Ein früherer Entwurf dieses Kapitels führte drei Forschungsfragen mit acht
Hypothesen in einem **eigenen Nummernkreis** — andere Fragen, andere
Hypothesen, dieselben Buchstaben. Massgeblich ist die eingereichte Fassung:
sechs Fragen F1 bis F6 mit je einer Hypothese H1 bis H6. Sie gelten im ganzen
Repository, auch in den Notebooks.

Was der Entwurf **gemessen** hat, ist damit nicht weg. Drei seiner Hypothesen
waren gerechnet, und ihre Befunde stehen im Analyseteil, wo sie hingehören —
als Befunde, nicht als Hypothesen:

| Befund | Wo er steht |
| --- | --- |
| Der räumliche Join reproduziert Detroits eigene Tract-Angabe nicht | 8.4 |
| Die Deliktschlüssel sind vollständig abgedeckt, aber nicht durchgehend abgebildet | 8.5 |
| Fehlende Koordinaten treten nicht zufällig auf, sondern hängen vom Delikttyp ab | 8.7 |

Dass eine Nummer wegfällt, ist kein Grund, eine Messung wegzuwerfen. Und dass
drei Fassungen derselben Fragen nebeneinander standen, ohne dass es auffiel,
ist der Grund für den Wächter aus dem Kasten oben.

---

## 4 · Vorgehen und Methoden

**Ordnungsrahmen** ist der Data-Engineering-Lebenszyklus nach Reis und Housley,
umgesetzt als Schichtenarchitektur `raw → bronze → silver → gold`.

**Datenbeschaffung.** Fünf öffentliche Quellen, jede mit eigenem
Vollständigkeitsnachweis statt blossem Vertrauen. Kein Scraping, keine
Browser-Automatisierung: alle fünf sind über dokumentierte Schnittstellen
erreichbar.

**Harmonisierung.** NIBRS als gemeinsame Deliktsprache, Census Tract als
gemeinsame Raumeinheit, ACS-Einwohnerzahlen als Nenner.

**Qualitätssicherung.** Prüfung je Quelle **vor** der Auswertung, automatisierte
Tests ohne Netzzugriff, unveränderliche Läufe mit Manifest. Jede Behauptung über
die Daten ist entweder gemessen oder als Vermutung gekennzeichnet.

**Werkzeug.** Python für die Ingestion, **DuckDB mit der `spatial`-Extension**
für Silver und Gold. Die Begründung steht in Kapitel 7.

---

## 5 · Der Data-Engineering-Lebenszyklus

Gefordert ist der **Entwurf**. Alle fünf Phasen sind inzwischen gebaut; der
Entwurf und was die Messung daran geändert hat, steht in 5.2.

### 5.1 Die fünf Phasen

| Phase | Umsetzung | Beleg |
| --- | --- | --- |
| **Generation** | Fünf Quellsysteme: Socrata-API (Chicago), ArcGIS REST (Detroit), HTTPS-Dateien (TIGER, NOAA), JSON-API (ACS). Je Quelle dokumentiert: Änderungsverhalten, Schlüsselbedarf, Formate | Notebooks 01, 21, 22 |
| **Ingestion** | Vier Pipelines, alle Batch. Chicago inkrementell über ein Wasserzeichen mit 14 Tagen Rückgriff; Census als eingefrorene Vintage; NOAA als Vollschnappschuss im Wochenrhythmus mit bedingtem Abruf | `src/crime/*_pipeline/` |
| **Storage** | Dateibasierte Schichten, Parquet mit festem Schema, Hive-Partitionen, unveränderliche Läufe mit Manifest je Schicht. Wo sie liegen — lokal, auf SeaweedFS oder beides — ist wählbar (7.4) | Kapitel 7 |
| **Transformation** | Bronze bewusst ohne Deutung. Silver deutet: Typen, Einheiten, Fehlwerte, Schlüssel. Alle vier Tabellen gebaut. **Gold** setzt darauf auf, ist aber in 5.2 beschrieben — es entstand aus der Serving-Entscheidung | Kapitel 8, Gold in 5.2 |
| **Serving** | Option A (Analytik) entschieden, Gold als Sternschema gebaut, Auswertungsdatenbank mit elf Sichten | 5.2 |

### 5.2 Serving: der Entwurf, und was die Messung daran geändert hat

Entschieden ist **Option A · Analytik**: eine Auswertungsumgebung auf der
Gold-Schicht.

**Der Entwurf sah zwei vorberechnete Würfel vor** — `fact_tract_month` und
`fact_city_day` — mit Geschwindigkeit als Begründung. Beim Bau wurde die
Begründung nachgemessen und fiel weg:

| Abfrage, direkt auf Silver | |
| --- | ---: |
| ein Delikt, ein Tag, eine Stadt | **0,6 ms** |
| ein Delikt, ein Monat, beide Städte | 0,9 ms |
| Rate je 1'000 Einwohner, Tract × Familie | 6,8 ms |
| Delikte je Tag mit Tagestemperatur | 3,4 ms |

Bei 348'000 Zeilen ist DuckDB nicht der Engpass; eine vorberechnete
Monatsspalte spart 0,2 Millisekunden. Der Preis der Aggregation ist dagegen
konkret: `fact_tract_month` kennt keine Tage, `fact_city_day` keine Tracts, und
beide fassen 59 Delikte zu 25 Familien zusammen. *„Nur Shoplifting am
9. November"* wäre nicht mehr zu beantworten — also genau das, wofür eine
Auswertungsplattform da ist.

**Gold behält deshalb die Granularität** und wird statt dessen abfragbar gemacht: ein
Sternschema mit einer Faktentabelle je Delikt und vier kleinen Dimensionen.
Aufgesetzt wird auf `silver/crime_offense` — was dort gedeutet und
zusammengeführt wurde, steht in [8.2](#82-was-silver-deutet); Gold ordnet es
an, deutet aber nichts Neues.
Jede Frage ist damit ein Filter und ein `GROUP BY` auf einer Tabelle; die
Oberfläche baut die `WHERE`-Klausel aus den Auswahlfeldern, und die Dimensionen
tragen die Auswahllisten gleich mit.

Nachgerechnet in
[`notebooks/34_gold_sternschema.ipynb`](../notebooks/34_gold_sternschema.ipynb).

#### Was gebaut ist: die Auswertungsdatenbank


`python -m serving.build_analysis_db` erzeugt `data/serving/analyse.duckdb` —
eine DuckDB-Datei mit **Sichten** über die Schichten. Wer auswerten will,
öffnet sie und schreibt SQL:

```sql
SELECT c.tract_geoid, count(*) * 100000.0 / any_value(t.population) AS rate
FROM crime_offense c JOIN tract t ON c.tract_geoid = t.geoid
GROUP BY 1 ORDER BY rate DESC;
```

Seit Gold gebaut ist, führt sie **elf Sichten**: die vier Silver-Tabellen, die
fünf des Sternschemas und zwei Hilfssichten — `tabellen` und `herkunft` sagen,
was man vor sich hat, ohne dass man das Repository kennen muss. Für die neun
Datensichten war nichts zu tun: `discover()` sucht in beiden Schichten und
nimmt auf, was da ist.

Daneben liegt `tracts.geojson`: die **1'055 Tract-Umrisse** der beiden Städte
für eine Karte, weil `dim_tract` nur Zentroide führt und die Polygone in
`silver/tract` als WKB liegen — ein Format, das kein Browser liest.

**Die Datei hält keine Daten, nur Namen** — 0,3 MB gegen 45,1 MB für dieselben
Daten als kopierte Tabellen. Das war eine gemessene Entscheidung, keine
Geschmacksfrage, und sie fiel nicht über Geschwindigkeit:

| Ad-hoc-Abfrage | Sichten | Kopie |
| --- | ---: | ---: |
| Filter und Gruppierung | 1,8 ms | 2,3 ms |
| Join Delikt × Tract | 3,6 ms | 4,3 ms |
| Drei-Wege-Join | 4,4 ms | 5,1 ms |

Sichten sind sogar knapp schneller; einen Unterschied von einer halben
Millisekunde nimmt niemand wahr. Den Ausschlag geben drei Eigenschaften, die
sich nicht messen lassen: Eine Kopie **kann veralten** — nach einem
Silver-Neubau zeigt sie den alten Stand, ohne dass man es ihr ansieht. Sie ist
eine **zweite Wahrheit** neben den Schichten, was Kapitel 7.2 ausdrücklich
ausschliesst. Und sie kostet gut das 200-fache an Platz.

> **Nachgemessen am 20.09.2026 (Christian).** Die Messung stammt von drei
> Silver-Tabellen; seither ist `place` dazugekommen. Auf dem heutigen Stand sind
> es **vier Tabellen mit 412'264 Zeilen und 49,4 MB Parquet**. Die Zeiten halten
> sich (Sichten weiter gleich schnell bis knapp schneller, Ergebnisse identisch
> geprüft), der Platzunterschied wächst: Sichten 0,3 MB gegen Kopie rund 62 MB,
> also **gut das 200-fache** statt des 150-fachen. Notebook 33 rechnet den Faktor
> jetzt selbst aus, damit er nicht wieder veraltet.


**Eigene Abfragen und eigene Tabellen.** Die Datei ist eine echte Datenbank;
wer ein Zwischenergebnis behalten will, legt daneben `CREATE TABLE meins AS
SELECT …` an. Die Sichten bleiben Sichten. Zwei gleichzeitige Schreiber gehen
nicht — DuckDB kennt nur einen; bei zwei Personen mit je eigener Datei und
`ATTACH` ist auch das gelöst.

Messung und Methodik: [`notebooks/33_serving_evaluation.ipynb`](../notebooks/33_serving_evaluation.ipynb).


#### Wer konsumiert

| Konsument | Zugriff | Granularität |
| --- | --- | --- |
| Dashboard (primär) | über Sichten in einer DuckDB-Datei | aggregiert |
| Ad-hoc-Auswertung im Team | SQL auf dieselben Sichten | aggregiert, bei Bedarf Silver |

Kein externer Dienst, keine API, keine Nutzerverwaltung. Das Serving endet an
der Auswertungsumgebung.

#### Was geliefert wird: sechs Gold-Tabellen

| Tabelle | Granularität | Zeilen |
| --- | --- | ---: |
| `fact_offense` | **eine Tat** | 1'851'950 |
| `dim_tract` | ein Census Tract, mit **Stadtzuordnung** | 6'282 |
| `dim_tract_acs` | ein Census Tract in **einem ACS-Vintage**, mit Einwohnerzahl, Medianeinkommen und Armutsquote | 25'128 |
| `dim_offense` | ein NIBRS-Delikt | 85 |
| `dim_date` | ein Kalendertag | 2'103 |
| `dim_city_day` | Stadt und Tag, mit dem Wetter | 4'196 |

**Warum die Einwohnerzahl eine eigene Tabelle hat (Vertrag 6).** Bis zum
3.10.2026 stand sie in `dim_tract`, und das ging, solange ein Jahrgang gebaut
war: Eine Tabelle mit einer Zeile je Tract kann nur **eine** Einwohnerzahl
tragen. Über sechs Jahrgänge bekäme jede Tat denselben Nenner, auch die von
2021 — und das Ergebnis sähe vollständig aus. `dim_tract` behält die
Stadtzuordnung und nennt mit `reference_vintage`, aus welchem Jahrgang sie
kommt; `fact_offense.population_vintage` sagt je Zeile, welcher Nenner für sie
gilt. Verbunden wird `dim_tract_acs` über `geoid` **und** Vintage — wer nur
den Tract verbindet, bekommt je Tract so viele Zeilen, wie Vintages geladen
sind, und eine vierfache Einwohnerzahl.

Die ganze Schicht bleibt klein genug für eine Datei ohne Serverbetrieb — das
ist derselbe Grund, der in Kapitel 7 gegen PostgreSQL sprach.

`dim_date` wird erzeugt und nicht aus den Fakten abgeleitet: Ein Tag ohne
Delikt ist eine Aussage und darf nicht fehlen, sonst zeigt eine Zeitreihe eine
Lücke als Nicht-Ereignis.

**Zurückgezogene Codes müssen auflösbar sein.** Vier NIBRS-Codes hat das FBI
gestrichen; die MICR-Quellen führen sie weiter, und zwei stehen in den
Falldaten. Sie wegzulassen hiesse, dass ein Filter über die Dimension rund
tausend Delikte verliert, ohne zu scheitern — sie nur als `retired` zu
markieren sagt aber nur, *dass* der Code weg ist, nicht *wohin*.

| Code | | Auflösung | heute | Fälle |
| --- | --- | --- | --- | ---: |
| `11B` | Sodomy | **umgeschlüsselt** | `11A` | 179 |
| `11C` | Sexual Assault With An Object | **umgeschlüsselt** | `11A` | 26 |
| `90A` | Bad Checks | **ersetzt** | `26A` | 50 |
| `90I` | Runaway | **keine Straftat** | — | 969 |
| `90E` | Drunkenness | offen | — | 0 |
| `90H` | Peeping Tom | offen | — | 0 |

`11B` und `11C` sind **nicht zurückgezogen** — sie dürfen gemeldet werden —,
werden vom FBI aber seit der Fassung 2023.0 auf `11A Rape` umgeschlüsselt; in
der Codeliste des User Manual stehen sie mit *„Converts to 11A"*. Wer sie in
einer Auswertung stehen lässt, zählt anders als das FBI.

`90A` ist belegt: Die ILCS-Tabelle führt `720-5/17-1(B)` *Deceptive Practices –
Bad Checks* unter `26A`. Bei `90I` ist das Fehlen eines Nachfolgers selbst die
Antwort — Weglaufen ist keine Straftat, und genau deshalb wurde der Code
gestrichen; die ILCS-Tabelle kennt nur das *Beherbergen* (`720-5/10-6` → `90Z`).

Die beiden offenen kommen 2024 nicht vor, und **der Bau erzwingt, dass das so
bleibt**: Ein Code mit `resolution = 'unresolved'`, der in den Fakten auftaucht,
lässt den Lauf scheitern. Erscheint er in einem späteren Jahrgang, muss jemand
einen Beleg nachtragen, statt ihn stillschweigend mitlaufen zu lassen.

**Kategorien.** Gruppiert wird über die **amtliche NIBRS-Deliktkategorie**:
28 Group-A- und 10 Group-B-Kategorien aus dem *NIBRS User Manual 2025.0*.
[`tools/build_nibrs_categories.py`](../tools/build_nibrs_categories.py) liest
sie aus dem Handbuch nach `config/nibrs_offense_categories_2025.csv`;
`dim_offense` trägt sie als `nibrs_category`.

**Hier stand zuvor eine Hilfskonstruktion.** Gruppiert wurde über die ersten
beiden Zeichen des Codes — `13` für Körperverletzung, `23` für Diebstahl — mit
der Begründung, das sei „die Gliederung, die der Standard selbst vorgibt". Das
war falsch, und zwar an vier Stellen:

| | |
| --- | --- |
| `11` **und** `36` | sind **beide** *Sex Offenses* |
| `58`, `61`, `62` | sind **alle drei** *Commerce Violations* |
| `10` | zerfällt in **drei**: Kidnapping/Abduction, Treason, Espionage |
| `90` | zerfällt in **zehn** Group-B-Kategorien, ohne Sammelnamen |

Das Präfix bleibt als technischer Schlüssel erhalten; wer gruppiert, nimmt die
Kategorie. In den Falldaten 2024 sind **30 Kategorien** belegt, **23 davon in
beiden Städten**, und diese 23 decken **99,5 %** der Fälle (auf Tatebene, siehe
5.2). Die übrigen kommen
nur in einer Stadt vor — Embezzlement, Pornografie, Bestechung, Menschenhandel
und Tierquälerei in Chicago, Bad Checks und Runaway in Detroit.

Die Kategorien werden **gelesen, nicht gepflegt**: Ein zweiter Lauf des Skripts
liefert dieselbe Datei, und ein Test prüft das. Vier zurückgezogene Codes, die
das Handbuch nicht mehr führt, kommen aus der Fassung 2011 derselben Liste;
jede Zeile nennt ihr Dokument.

> **Zuvor stand hier eine eigene Kategorienliste**,
> `config/crime_category_mapping.csv`, die Chicagos `fbi_code` (SRS) und
> Detroits `offense_category` auf 22 gemeinsame Kategorien abbildete. Sie ist
> entfernt: Seit beide Städte über NIBRS laufen, wäre sie eine zweite,
> handgepflegte Übersetzung neben der belegten — und die 20 Familien leisten
> dasselbe, ohne gepflegt werden zu müssen.

#### Die Granularität: Detroits Zeilen sind Anklagen, Chicagos sind Delikte

**Das ist der einzige Stellenwechsel zwischen Silver und Gold** — und er war
nötig, weil die beiden Städte verschieden feine Zeilen liefern. Ein Überfall mit
Schüssen und geraubtem Auto steht bei Detroit als **fünf** Zeilen, bei Chicago
als **eine**:

```
Zeile 1218143-1302   Anklage: AGGRAVATED ASSAULT      Tat: AGGRAVATED ASSAULT
Zeile 1218143-1304   Anklage: NON-FATAL SHOOTING      Tat: AGGRAVATED ASSAULT
Zeile 1218158-1201   Anklage: CARJACKING              Tat: CARJACKING
Zeile 1218158-2401   Anklage: MOTOR VEHICLE THEFT     Tat: AGGRAVATED ASSAULT
Zeile 1218218-1302   Anklage: AGGRAVATED ASSAULT      Tat: AGGRAVATED ASSAULT
```

**Welches Feld die Tat trägt, sagen die Daten selbst.** Bei Vorfällen mit
mehreren Zeilen ist `offense_description` in **38,4 %** der Fälle konstant,
`charge_description` nur in **2,3 %**. Die Tat ist also `offense_description`;
der Rest der Zeile beschreibt die einzelne Anklage.

**Silver behält jede Anklage** — sie ist eine Tatsache — und markiert je Tat
eine Zeile mit `counts`. Gewählt wird die Zeile, deren Anklage die Tat selbst
ist; sie trägt damit schon den richtigen MICR-Code, und es braucht keine
Zuordnung über Text. Das trifft auf **99,99 %** der Gruppen zu. Für die
übrigen 55 entscheidet die **Hierarchie des MICR-Handbuchs**, in der 1 Mord ist
und 16 Sachbeschädigung: Es gilt die schwerste Anklage.

| | Detroit, 2021–2026 |
| --- | ---: |
| Zeilen in Silver (eine Anklage) | 491'725 |
| davon zählend (**eine Tat**) | **468'297** |
| Unterschied | −23'428 = **−4,8 %** |

Gold nimmt nur die zählenden. Wer die Anklagen braucht — *„wie oft wurde
zusätzlich Sachbeschädigung angezeigt"* — findet sie vollständig in
`silver/crime_offense`, mit `counts` und `counts_reason` je Zeile.

**Ein zweites Granularität seit 13.9.2026: der Fall.** Das Tatebene gleicht Detroits
Anklagen an — aber nicht die Zählweise der beiden Städte. Chicago führt je
Vorfall **ein** Delikt (die einzigen Mehrfachzeilen sind Mordopfer, ein
Datensatz je Opfer), Detroit führt je Vorfall **jedes** Delikt. `counts_case`
markiert je Fall die Zeile mit dem schwersten Delikt — für beide Städte nach
derselben Rangfolge (`FALLKORN_RANG`: die Hierarchieregel des UCR Handbook,
auf NIBRS übersetzt), bei gleichem Delikt die früheste Zeile.

| | Chicago | Detroit |
| --- | ---: | ---: |
| Taten (`counts`), 2021–2026 | 1'383'653 | 468'297 |
| Fälle (`counts_case`), 2021–2026 | 1'383'475 | 443'443 |
| Taten je Fall | 1,000 | **1,056** |
| Rate je 1'000, Tatebene, **2024** | 94,5 | 133,1 |
| Rate je 1'000, Fallebene, **2024** | 94,5 | **124,6** |

Beide Masse liegen in Gold; die Tatzahlen ändern sich nicht. Welche Zählweise
die Aussage trägt, ist ein Entscheid — Chicagos Zählweise ist das Fallebene.

**Gefunden hat das Artan**, an einer Zeile mit `offense_category` LARCENY und
`offense_description` *CSC 3rd Degree*. Sie gehört zu einem Vorfall mit zwei
Anklagen zu einer Tat — die Larceny-Anklage und die CSC-Anklage. Ohne diese
Auswahl hätte der Vergleich Detroit systematisch zu hoch gezählt.

**Das Wetter bleibt tagesgenau.** Das war am alten Entwurf richtig: Eine
Monatsmittelung zerstört genau das Signal, das eine Wetterfrage braucht. Aus
`fact_city_day` wurde deshalb `dim_city_day` — dieselbe Auflösung, aber als
Dimension neben der Faktentabelle statt als eigener Würfel.

#### Die Stadtgrenze: der Nenner, den es vorher nicht gab

Bis zu dieser Schicht konnte das Projekt **keine Rate je Einwohner belegen**.
`silver/tract` deckt ganze Countys ab, und ein Tract sagt nicht, zu welcher
Stadt er gehört: Cook County hat 5,18 Millionen Einwohner, Chicago rund 2,7
Millionen. Der Juni-Bericht behalf sich mit *„Tracts, in denen Delikte liegen"*
und nannte das ausdrücklich eine Näherung.

`silver/place` liefert jetzt die Ortsgrenzen aus TIGER/Line. Tracts liegen
allerdings nicht sauber darin, sondern überschreiten sie. Drei Regeln wären
denkbar:

| Regel | Chicago | Detroit |
| --- | ---: | ---: |
| alle berührten Tracts | 3'080'550 | 884'691 |
| Flächengewichtung | 2'651'921 | 638'570 |
| **Mehrheitsregel** | **2'661'953** | **638'635** |
| Zensus 2020 | 2'746'388 | 639'111 |

Gewählt ist die **Mehrheitsregel**: Ein Tract gehört zu der Stadt, die mehr als
die Hälfte seiner Fläche bedeckt. Sie gibt jedem Tract genau eine Stadt — die
Voraussetzung dafür, dass sich Fälle ohne Doppelzählung summieren lassen — und
liegt praktisch gleichauf mit der Flächengewichtung. Detroit trifft sie auf
**0,07 %** genau; der grössere Abstand bei Chicago ist der Unterschied zwischen
einer ACS-Schätzung und einer Zählung, nicht ein Fehler der Regel.
`dim_tract.city_area_share` hält den Anteil in jeder Zeile fest, damit sich
beides nachrechnen lässt.

**Der Preis ist gemessen:** 2,9 % der Delikte liegen in Tracts, die keiner der
beiden Städte zugeordnet sind — Fälle knapp jenseits der Stadtgrenze. Zähler
und Nenner folgen derselben Grenze, der Rand verzerrt also beide Seiten
gleichsinnig.

Damit ist die Frage beantwortet, die das Projekt von Anfang an stellen wollte —
**für den Jahrgang 2024**, mit der ACS-Schätzung desselben Jahrgangs als
Nenner:

| | Delikte | Einwohner | je 1'000 |
| --- | ---: | ---: | ---: |
| Chicago | 251'517 | 2'661'953 | **94,5** |
| Detroit | 84'987 | 638'635 | **133,1** |

Absolute Fallzahlen hätten das Gegenteil nahegelegt.

**Ein Ort heisst nicht eindeutig.** Illinois führt neben *Chicago city* auch ein
*Detroit village* von 0,65 Quadratkilometern. Die Auswahl der beiden Städte
läuft deshalb über die FIPS-Ortsnummer und nicht über den Namen; ein Test hält
fest, dass es diese Falle wirklich gibt.

#### Welche Kennzahlen

| Kennzahl | Herkunft |
| --- | --- |
| Fallzahl, absolut | `crime_offense` |
| Einwohner | `tract`, ACS — über 2024 konstant |
| Rate je 1'000 Einwohner | abgeleitet |
| **Abdeckungsquote je Zelle** | Anteil verorteter Fälle, aus denen die Zelle entstand |

#### Was das Serving zeigen muss

Drei Eigenschaften der Daten dürfen im Dashboard nicht verschwinden, sonst wird
aus einer belegten Zahl eine irreführende:

- **Raten ohne Nenner.** 109 Tracts haben null Einwohner — Wasserflächen,
  Flughäfen, Industrie. Dort ist die Rate `NULL` und nicht null; die absolute
  Zahl bleibt sichtbar.
- **Nicht verortete Fälle** fehlen in jeder Tract-Zelle: 0,70 % in Chicago,
  0,29 % in Detroit. Deshalb steht die Abdeckungsquote **neben jeder Rate** und
  nicht in einer Fussnote.
- **Die Lücken sind ungleich zwischen den Städten** — beim Einkommen 9,6 % der
  Tracts in Wayne County gegen 1,7 % in Cook County. Ein Vergleich ohne
  Abdeckungsangabe wäre systematisch verzerrt, nicht nur ungenau.

#### Aktualität

Gold wird aus Silver **neu gebaut** und nicht inkrementell fortgeschrieben; ein
Lauf ist damit reproduzierbar, solange der Referenzstand feststeht (Kapitel 10).

Ein Anspruch, stets den Vortag zu zeigen, ist nicht einheitlich erfüllbar: Die
Falldaten geben ihn her, NOAA nicht — dort liegen rund vier Tage Nachlauf. Das
Dashboard weist den Stand je Quelle aus, statt einen gemeinsamen zu behaupten.

#### Was ausdrücklich nicht geliefert wird

- **Keine vorberechneten Aggregate in Gold.** Gold behält die Granularität — eine
  Zeile je Tat, mit Zeitpunkt und Koordinate. Aggregiert wird in der Abfrage,
  nicht im Speicher; die Messung dazu steht weiter oben in diesem Kapitel.
  Seit dem 17.9.2026 liegen in **Serving** vier aus Gold abgeleitete
  Vergleichstabellen (`comparison_day`, `comparison_week`, `comparison_month`,
  `partition_quality`) — nicht, weil sie schneller wären, sondern als Teil
  des Veröffentlichungsstands, den ein Dashboard liest, und als gebauter
  Gegenentwurf zum Stern. Sie sind jederzeit aus Gold neu erzeugbar und
  summieren sich nachweislich auf die Faktentabelle; die Quelle der Wahrheit
  bleibt der Stern.
- **Keine Merkmalstabelle je Tract für Modelle.** Das wäre Option B, und die ist
  nicht gewählt.
- **Was das Dashboard zeigt, ist eine engere Auswahl als Gold.** Die
  Faktentabelle trägt `offense_id`, den genauen Zeitpunkt und die Koordinate —
  nötig für flexible Auswertung, aber nichts, was auf eine Folie gehört. Eine
  veröffentlichte Ansicht zeigt Aggregate je Tract und Zeitraum, ohne
  Identifikatoren und ohne Punktkoordinaten.

> **Korrektur, 12.9.2026.** Hier stand bis heute *„Keine zeilenweisen
> Falldaten. Gold ist aggregiert."* Das war ein Überbleibsel des
> Würfel-Entwurfs und widersprach der Messung, die ihn verworfen hat: Gold
> behält die Granularität, genau das ist die Entscheidung. Siehe
> [`AENDERUNGEN.md`](intern/AENDERUNGEN.md).

### 5.3 Unterströmungen

| Unterströmung | Umsetzung | Lücke |
| --- | --- | --- |
| **Security** | Schlüssel nur in `.env`, nie in einem Manifest oder einer abgelegten URL; drei Tests prüfen das. `.env` und `data/` aus der Versionierung ausgeschlossen, die Historie enthält keinen committeten Schlüssel. `requirements.lock` pinnt jede Abhängigkeit exakt | kein Vulnerability-Scan der Abhängigkeiten; Datenschutzabschnitt schriftlich |
| **Data Management** | Manifest je Lauf und Schicht, Herkunft über `derived_from` und `run_id` — durchgehend bis Gold: jede abgeleitete Tabelle trägt einen `input_fingerprint` über ihre Eingaben, nennt Vorgänger mit Bauzeitpunkt und Abdruck statt nur mit Pfad, Referenzdateien mit SHA-256. Jedes Manifest nennt ausserdem `contract_version` (was geladen oder gedeutet wird) und `code_version` (welcher Commit, und ob der Arbeitsbaum sauber war), gegen ein Register in `AENDERUNGEN.md` getestet. Unveränderliche Läufe, Schema-Fingerabdruck gegen Drift, `_extra` gegen Datenverlust. Feldkatalog mit 133 Spalten, erzeugt aus den Manifesten und getestet. Gesamtmanifest je Lauf mit allen Eingabe-Läufen und Fingerabdruck. Verantwortliche je Datensatz in Absprache 7.3, gegen die Stufenliste getestet. Aufbewahrungsregel mit `orchestration.aufraeumen`: **gepinnt** bleibt (Register `config/referenzstand.csv`, versioniert), dazu der jüngste Lauf und der davor, alles von Silver Genannte und die Basis jedes Deltas; gelöscht wird nur auf Wunsch, Raw und Bronze zusammen. `--pinnen` leitet den Referenzstand aus den Gold-Manifesten ab, statt ihn tippen zu lassen. Datenablage wahlweise lokal, SeaweedFS (S3) oder hybrid (`storage`): lesen lokal zuerst, S3 als Rückfall; schreiben lokal, prüfen, gezielt publizieren, `manifest.json` zuletzt. Ein veralteter lokaler Stand einer abgeleiteten Tabelle wird beim Lesen gemeldet und beim Publizieren abgelehnt — verglichen werden `built_at_utc` und die Bronze-Läufe aus `derived_from` | das Aufräumen ist ein Handgriff, kein Automatismus; ein Stand wird gepinnt, wenn jemand daran denkt; Detroits Lauf vom 11.9. bleibt bewusst ohne Raw-Gegenstück — er ist der vorherige Schnappschuss, der die Instabilität der Quelle belegt; die Ablage lädt nichts automatisch herunter und synchronisiert nicht zurück — bewusst, Version 1 |
| **DataOps** | 1'850 Tests ohne Netz und Schlüssel, auf jedem Pull Request in GitHub Actions — Linux und Windows, Python 3.11 und 3.13; `ruff` davor. Schreiben über `.part` und atomares Umbenennen. Publish-Gate: Gold entsteht nur, wenn die Abdeckung Schwellen hält | die 102 datengebundenen Wächter laufen auf Pull Requests nicht — dafür gibt es seit dem 13.9. den wöchentlichen Datenlauf (`datenlauf.yml`), der alle Quellen lädt, die Strecke baut und dann die ganze Suite fährt; er braucht `CENSUS_API_KEY` als Repository-Secret und ist bis zum ersten grünen Lauf eine Einrichtung, kein Nachweis. Aktualität wird im Datenlauf gegen eine Schwelle von acht Tagen geprüft, **nach der Ingestion und vor dem Ableiten** — eine Quelle, die nichts Neues liefert oder ganz fehlt, lässt ihn scheitern, bevor Gold darauf entsteht; keine Alarmierung ausser dem roten Lauf selbst |
| **Data Architecture** | Vier Schichten, gepinnte Schemata, Trennung von Beweis (`raw`) und Ableitung (`bronze`), sprechende Partitionsschlüssel. `mapping_status` und `geo_status` machen die Vergleichbarkeit je Zeile abfragbar. Ein Manifest-Leser (`manifeste`) für alle Schichten statt elf. Zwei Architekturbilder, **aus dem Code erzeugt** — Abhängigkeiten und Datenfluss, mit einem Test gegen Zyklen ([`architektur.md`](architektur.md)) | Vintage 2024 hart verdrahtet — für mehrere Jahrgänge muss sie je Jahr mitlaufen |
| **Orchestration** | `orchestration.run_all`: 14 Stufen in Reihenfolge, Abbruch beim ersten Fehler, Gesamtmanifest mit allen Bronze-Läufen und Fingerabdruck über die Eingaben | der geplante Lauf ist wöchentlich (`datenlauf.yml`, montags), die Quellen ändern sich täglich; ausserhalb davon startet er, wenn jemand daran denkt; keine Wiederaufnahme, bewusst |
| **Software Engineering** | Modulare Pakete je Quelle, Typannotationen, Docstrings die das Warum festhalten, Fehlerbehandlung mit Wiederholungen. `ruff` mit Pyflakes und `raise … from`, Lockfile, CI-Matrix über zwei Betriebssysteme | die sechs Notebooks, die Zahlen belegen, laufen seit dem 13.9. im wöchentlichen Datenlauf — nicht auf Pull Requests, weil sie `data/` brauchen. Notebook 32 war bis dahin einen Tag lang still kaputt. Die sechs ladenden Notebooks laufen bewusst nirgends automatisch |

**Zur Orchestrierung.** Airflow oder Prefect wären bei fünf Quellen und vier
Batch-Pipelines Aufwand ohne Erkenntnisgewinn. Gebaut ist deshalb ein Skript,
das die Läufe in der richtigen Reihenfolge aufruft und protokolliert — die
Reihenfolge ist real, weil `silver/tract` beide Census-Quellen braucht und
`crime_offense` zusätzlich `tract`. Was fehlt, ist der Anstoss: Nichts startet
den Lauf von selbst.

**Wozu diese Tabelle einen Wächter hat.** Sie ist dreimal veraltet, während die
Arbeit lief, die sie beschreibt — ein Feldkatalog als Lücke, den es schon gab;
eine Orchestrierung als „bewusst offen", die gebaut war. `tests/test_unterstroemungen.py`
hält jede Zeile gegen das Artefakt, das sie behauptet oder vermisst.

---

## 6 · Datenbeschaffung: die fünf Quellen

| Quelle | Zugriff | Änderungsverhalten | Schlüssel |
| --- | --- | --- | --- |
| **Chicago Crimes** | Socrata REST, paginiert | wächst laufend, Datensätze werden korrigiert | Token optional |
| **Detroit RMS Crime** | ArcGIS REST | wächst laufend | keiner |
| **Census TIGER/Line** | ZIP über HTTPS | eine Vintage pro Jahr, danach eingefroren | keiner |
| **Census ACS 5-Jahres** | JSON-API | dito | Schlüssel nötig |
| **NOAA GHCN-Daily** | CSV je Station über HTTPS | wächst täglich um eine Zeile | keiner |

### 6.1 Vollständigkeit wird nachgewiesen, nicht behauptet

Jede Quelle erlaubt einen anderen Nachweis, und jede Pipeline nutzt den, den
ihre Quelle hergibt:

| Quelle | Nachweis |
| --- | --- |
| Chicago | serverseitiger Count vor dem Laden, danach Abgleich gegen die geschriebenen Zeilen |
| Detroit | Object-IDs vorher festschreiben, sortieren, danach gegen die empfangenen Features abgleichen |
| TIGER | CRC32 je Mitgliedsdatei des ZIP, plus die vier Pflichtdateien eines Shapefiles |
| ACS | Antwort selbst prüfen, weil die API bei fehlendem Schlüssel mit **HTTP 200** und einer HTML-Seite antwortet |
| NOAA | `Content-Length` gegen empfangene Bytes, CSV-Zeilen gegen Parquet-Zeilen, und die Prüfung, dass jede Zeile die angefragte Station nennt |

Die ACS-Zeile ist die unangenehmste Eigenheit aller fünf Quellen: Code, der nur
den Statuscode prüft, hält eine Fehlerseite für einen Erfolg und schreibt einen
leeren Lauf.

### 6.2 Drei Änderungsverhalten, drei Ladestrategien

**Ereignisquellen** (Chicago, Detroit) wachsen um einzelne Datensätze und
korrigieren ältere. Beide laden deshalb inkrementell über ein Wasserzeichen auf
dem Änderungsfeld der Quelle — Chicago auf `updated_on`, Detroit seit dem
18.9.2026 auf `updated_at` innerhalb des Tatjahrgangs —, jeweils mit **14 Tagen
bewusstem Überlapp**; Korrekturen an älteren Fällen werden so erfasst. Der Preis
sind Duplikate, die Silver auflöst; H2 prüft, dass es tatsächlich Duplikate und
keine Dubletten sind.

**Eingefrorene Quellen** (TIGER, ACS) haben kein Änderungsdatum und brauchen
keins. An die Stelle des Wasserzeichens tritt die einfachere Frage: Ist diese
Vintage für diesen Bundesstaat schon geladen?

**Die Wetterquelle** liegt dazwischen: Sie wächst täglich um eine Zeile, wird
aber immer als ganze Datei ausgeliefert. Jeder Lauf ist ein vollständiger
Schnappschuss. Weil das so ist, erzeugt selteneres Laden **keine Lücke** — der
nächste Lauf bringt die Zwischenzeit mit. Geladen wird deshalb im
Wochenrhythmus, mit bedingtem Abruf über `If-None-Match`: Hat NOAA nichts neu
veröffentlicht, kommen null Bytes statt elf Megabyte.

Dass die Quelle **nicht** nur anhängt, ist gemessen: Zwei Schnappschüsse im
Abstand eines Tages zeigten je Station zwei neue Zeilen, nichts Gelöschtes — und
in Detroit **eine nachträglich geänderte Zeile**. Ein Delta, das nur das
Dateiende anhängt, hätte diese Korrektur übersehen.

---

## 7 · Storage: Evaluation, Wahl, Implementierung

### 7.1 Anforderungen

1. Rohdaten unveränderlich und beweissicher ablegen
2. Spaltenorientierte Auswertung über einige Hunderttausend Zeilen
3. Geometrien speichern und räumlich verknüpfen
4. Schemastabilität über viele Läufe
5. Ohne Serverbetrieb lauffähig, damit beide im Team lokal arbeiten
6. Nachvollziehbar und versionierbar für die Abgabe

### 7.2 Die Speicherumgebung

| Option | Stärken | Schwächen | Bewertung |
| --- | --- | --- | --- |
| **Parquet-Dateien mit Hive-Partitionen** | kein Server, spaltenorientiert, offenes Format | keine Transaktionen, kein SQL ohne Zusatz | erfüllt 1–6 |
| **PostgreSQL + PostGIS** | ausgereifter Raumbezug, echtes SQL, Transaktionen | Serverbetrieb bei beiden; Rohdaten passen schlecht hinein | 5 nicht erfüllt |
| **DuckDB** | SQL direkt auf Parquet, `spatial`-Extension, kein Server | nicht für parallele Schreiber gedacht | ergänzt Option 1 |
| **Cloud (S3, BigQuery)** | skaliert, praxisnah | Kosten, Zugänge, für diese Datenmenge unangemessen | verworfen |

**Wahl: zweistufig.** Dateibasierte Schichten in Parquet als Speicher, **DuckDB
als Abfrageschicht** darüber. Die Ablage bleibt offen, portabel und
unveränderlich; DuckDB liefert SQL und den räumlichen Join, ohne dass jemand
einen Server betreibt.

> **Nachtrag 13.9.2026: die verworfene Zeile ist zur Hälfte zurück.** Oben
> steht *„Cloud (S3, BigQuery) — verworfen"*, und das galt der Frage nach
> **Skalierung**; daran hat sich nichts geändert, für 350'000 Zeilen wäre sie
> unangemessen. Zurückgekommen ist S3 für eine andere Frage, die in dieser
> Tabelle nicht vorkam: **Wie kommen zwei Leute an denselben Stand?** `data/`
> ist aus der Versionierung ausgeschlossen (7.4), also lud bis hierher jeder
> selbst — mit eigenen `run_id`s und, durch die Delta-Logik, anderen Zeilen.
> Seit dem 13.9. gibt es dafür einen gemeinsamen veröffentlichten Bestand auf
> **SeaweedFS**, angesprochen über die S3-Schnittstelle. Die beiden Einwände
> der Tabelle treffen ihn nicht: Er läuft selbstgehostet, es entstehen keine
> Kosten und keine fremden Zugänge. Und die Wahl darüber bleibt unberührt —
> es sind dieselben Parquet-Dateien in derselben Struktur, gelesen von
> demselben DuckDB. Wählbar ist nur, **wo** sie liegen (7.4).

### 7.3 Das Format innerhalb der Schichten — gemessen

Vier Quellen legten Bronze als Parquet ab, Detroit als NDJSON. Ob das
zusammengeführt werden soll, ist keine Geschmacksfrage, sondern messbar.
Verglichen wurden **dieselben Daten in beiden Formaten** — Detroits Bronze-Lauf
mit 88'685 Zeilen, gelesen über DuckDB.

> **Die Messung ist umgesetzt und bleibt nachrechenbar.** Detroit schreibt seit
> dem 11.9. Parquet; der alte NDJSON-Bestand ist gelöscht, damit niemand
> versehentlich darauf zugreift. Das Vergleichs-NDJSON erzeugt das Notebook
> deshalb zur Laufzeit aus der Spalte `_feature_json`, die die Antwort der
> Quelle unverändert aufbewahrt. Es ist damit etwas kleiner als die frühere
> Bronze-Datei, der die Pipeline je Zeile noch einen `_meta`-Block anfügte —
> der Vergleich selbst ist derselbe.

| Format | Grösse |
| --- | --- |
| NDJSON, wie ausgeliefert | 89,4 MB |
| NDJSON + gzip | 10,9 MB |
| **Parquet snappy** | **6,5 MB** |
| Parquet zstd | 4,8 MB |

| Abfrage | NDJSON | Parquet | Faktor |
| --- | --- | --- | --- |
| Zeilen zählen | 0,088 s | 0,000 s | aus den Metadaten |
| nach Kategorie gruppieren | 0,091 s | 0,001 s | 110× |
| **fünf Spalten, alle Zeilen** | **0,139 s** | **0,029 s** | **4,9×** |
| alle Spalten materialisieren | 0,541 s | 0,428 s | 1,3× |

Die dritte Zeile ist die, die zählt: Genau das tut die Silver-Schicht. NDJSONs
Zeiten sind über die ersten Abfragen konstant, weil **JSON keine Spaltenauswahl
kennt** — wer ein Feld braucht, parst die ganze Datei.

**Was für NDJSON spricht**, damit es genannt ist: Die Sorge, DuckDB könnte das
Schema je nach Stichprobe anders erraten, **trifft nicht zu** — drei
Stichprobengrössen ergeben dasselbe Schema. Und NDJSON ist ohne Werkzeug
lesbar, was für die Fehlersuche an einer neuen Quelle ein echter Vorteil ist.
Genau deshalb bleibt es in Raw.

**Der stärkste Befund ist nicht die Geschwindigkeit.** Detroits NDJSON übernahm
bis zum 11.9.2026 zwei Rollen gleichzeitig: Beweisstück und abgeleitete Tabelle. Getrennt
nach der Konvention der anderen vier Quellen kostet die zusätzliche Schicht
nichts — sie spart:

```text
vorher       Bronze NDJSON             89,4 MB
getrennt     Raw    NDJSON + gzip      10,9 MB
             Bronze Parquet snappy      6,5 MB
             zusammen                   17,4 MB   → 81 % weniger
```

> **Nachgerechnet am 19.09.2026 (Christian).** Das sind die Zahlen der
> *Evaluation*, also des Modells. In der Umsetzung liegen Raw und Bronze
> zusammen bei **27,1 MB** statt 17,4 — das sind **70 % weniger**, nicht 81 %.
> Bronze traf das Modell fast genau (6,0 statt 6,5 MB), trägt aber zusätzlich
> `_feature_json` mit dem geparsten Quellfeature und kommt damit auf 16,7 MB.
> Diese Spalte kam nach der Evaluation dazu und ist Absicht: Raw hält die
> HTTP-Bytes als Beweis, `_feature_json` die auswertbare Fassung. Die 81 %
> bleiben als Messergebnis richtig, sind aber nicht der erreichte Wert;
> Notebook 31 Abschnitt 9 rechnet beides gegeneinander.

Messung und Methodik: [`notebooks/31_storage_evaluation.ipynb`](../notebooks/31_storage_evaluation.ipynb).
Die Messung läuft mit warmem Betriebssystem-Cache und **unterschätzt damit
Parquet**, weil der Plattenzugriff wegfällt.

**Was daraus wurde.** Detroits Ingestion schreibt seit dem 11.9. Parquet, in
Laufverzeichnissen mit Manifest und Prüfsumme, und bringt einen eigenen
Datenvertrag mit: eingefrorenes Schema aus den Layer-Metadaten, `_feature_json`
als verlustfreie Nutzlast, `_extra` für Typdrift. **Alle fünf Quellen liegen
damit auf derselben Konvention**: Raw als Beweis, Bronze als Parquet, je Lauf
ein Verzeichnis mit Manifest.

Den NDJSON-Rückfall der Silver-Schicht gibt es **nicht mehr**. Er ist mit dem
Zeitzonen-Befund (8.6) bewusst entfernt worden: Jene Bestände hatten ihr
Jahresfenster in UTC statt in Detroiter Ortszeit gezogen, enthielten also 66
Fälle aus 2023 und vermissten 56 vom Jahresende 2024. Ein Rückfall hätte sie
weiter eingelesen — mit einer Warnung im Log, die man überliest. Lieber ein
klarer Fehler und ein neuer Full Load.

### 7.4 Implementierung

```text
data/
├── raw/      unverändert, Byte für Byte wie ausgeliefert
├── bronze/   daraus abgeleitetes Parquet mit gepinntem Schema
├── silver/   gedeutet: Typen, Einheiten, Fehlwerte, harmonisierte Schlüssel
├── gold/     Sternschema: fact_offense und fünf Dimensionen
└── serving/  Auswertungsumgebung: analyse.duckdb und tracts.geojson
```

Partitioniert wird mit sprechenden Schlüsseln, deren erster die Quelle benennt:
`city=chicago/ingest_date=…`, `dataset=tiger_tract/vintage=2024/state=17`,
`dataset=noaa_ghcnd/station=USW00094846`. Der Schlüssel folgt der Sache: Wetter
ist kein Merkmal eines Bundesstaats, sondern einer Station.

**Läufe sind unveränderlich.** Ein Lauf wird nie überschrieben; ein neuer Lauf
ist ein neues Verzeichnis. Geschrieben wird in ein verstecktes
`.part`-Verzeichnis und erst nach erfolgreicher Prüfung atomar umbenannt —
**Raw zuerst**, weil ein Raw-Lauf ohne Bronze-Zwilling eine Wiederholung kostet,
nie eine Lücke.

**Silver ist die Ausnahme:** abgeleitet und jederzeit neu erzeugbar, deshalb
wird sie ersetzt statt angehäuft. Das Manifest nennt trotzdem die Herkunft.

#### Wo diese Struktur liegt, ist wählbar — seit 13.9.2026

*Der vollständige Aufbau steht in
[`storage-architektur.md`](storage-architektur.md); hier das Nötige.*

Alles oben Beschriebene gilt unverändert; neu ist nur, dass `data/` nicht der
einzige Ort ist. Ein Pfad wird intern **relativ** adressiert
(`bronze/city=chicago/ingest_date=…/run_…/part-0001.parquet`), und
`STORAGE_BACKEND` entscheidet, was daraus wird:

| Modus | Lesen | Schreiben |
| --- | --- | --- |
| `local` (Vorgabe) | `data/…` | `data/…` — der bisherige Zustand, unverändert |
| `hybrid` | lokal, wenn die Datei da ist, **sonst** `s3://urban-crime/…` | lokal, prüfen, **dann** gezielt publizieren |
| `s3` | immer SeaweedFS | lokal als Arbeitskopie, prüfen, publizieren, Kopie entfernen |

**Hybrid ist der Modus für die Zusammenarbeit** und beantwortet die Frage aus
Absprache 7.1, wie zwei Leute an denselben Stand kommen. SeaweedFS trägt den
gemeinsamen **veröffentlichten** Bestand, `data/` ist Arbeitskopie. Wer eine
Tabelle lokal nicht hat, liest sie von dort — ohne vorher etwas zu
synchronisieren.

Drei Regeln machen daraus mehr als einen Netzordner:

1. **Veröffentlicht wird erst nach der Prüfung.** Gebaut wird lokal, dann
   laufen die bestehenden Kontrollen (Vollständigkeitsnachweis, `reconcile`,
   Publish-Gate), und erst danach geht der Lauf oder die Tabelle hoch — je
   Lauf einzeln, `manifest.json` **zuletzt**. Damit ist das Manifest oben
   dasselbe Signal wie das atomare Umbenennen lokal: Es ist da, also ist der
   Lauf vollständig. Was scheitert, erreicht den gemeinsamen Bestand nie.
2. **Läufe bleiben unveränderlich.** Liegt ein Objekt schon oben und ist
   identisch, wird es übersprungen; liegt es mit anderem Inhalt dort, ist das
   ein Fehler. Nichts wird still überschrieben. Nach jedem Upload wird das
   Objekt zurückgelesen — Grösse und, wo der Dienst ein ETag liefert, die
   Prüfsumme.
3. **Ein veralteter eigener Stand wird erkannt.** Silver und Gold *werden*
   ersetzt, dort greift Regel 2 nicht. Stattdessen vergleicht die Ablage
   `built_at_utc` und die Bronze-Läufe aus `derived_from`: Wer eine Tabelle
   von letzter Woche liest, bekommt eine Warnung; wer sie publizieren will,
   eine Absage. Sonst verdrängte ein alter Stand einen neuen, ohne Spur.

**Immer lokal bleibt `data/serving/`** — die Auswertungsdatenbank ist
abgeleitet, klein und trägt Pfade, die nur auf einem Rechner gelten. Ihre
Sichten zeigen je nach Modus auf lokale oder auf S3-Dateien.

**Was bewusst nicht gebaut ist:** kein automatisches Herunterladen (was lokal
fehlt, wird von S3 *gelesen*, nicht kopiert), keine Synchronisation zurück,
kein gleichzeitiges Schreiben in beide Richtungen. Die Ablage ist damit keine
verteilte Datenbank, sondern das, was das Projekt braucht: ein Ort für den
Stand, auf den sich beide beziehen.

---

## 8 · Transformation Teil 1: Bereinigung und Qualität

> **Wo die vierte Schicht steht.** Dieses Kapitel beschreibt Bronze und Silver.
> **Gold** ist in [5.2](#52-serving-der-entwurf-und-was-die-messung-daran-geändert-hat)
> beschrieben, nicht hier — es entstand aus der Serving-Entscheidung und nicht
> aus einer Qualitätsfrage. Die Reihenfolge der Schichten ist trotzdem
> Bronze → Silver → Gold → Serving; Kapitel 7.4 zeigt sie als Verzeichnisbaum.

### 8.1 Was Bronze bewusst nicht tut

Bronze deutet nicht. Werte behalten den Typ, den die Quelle liefert: Chicagos
`arrest` bleibt ein JSON-Boolean, NOAAs `"  214"` bleibt Text mit
Leerzeichen, der ACS-Fehlwert `-666666666` bleibt stehen. Alles Unerwartete
landet in einer Auffangspalte `_extra`, statt verworfen zu werden.

Das ist keine Bequemlichkeit, sondern die Voraussetzung dafür, dass Bronze
jederzeit neu deutbar ist. Beim Chicago-Schemafehler liess sich Bronze neu
ableiten, ohne die API erneut zu befragen.

### 8.2 Was Silver deutet

Die Quellen haben **verschiedene Granularitäten**. Sie in eine Tabelle zu zwingen
würde Zeilen vervielfachen — ein Wetterwert an jedem Delikt derselben Stadt und
desselben Tages — oder Information wegwerfen. Deshalb vier Tabellen. `tract`
und `place` liegen je **Vintage** einmal; die Zeilenzahl unten ist die eines
Vintage, und gebaut sind vier (2021–2024):

| Tabelle | Eine Zeile ist | Stand |
| --- | --- | --- |
| `tract` | ein Census Tract **in einem ACS-Vintage** | **gebaut**, 6'282 Zeilen |
| `place` | ein Ort (Stadtgrenze) **in einem TIGER-Vintage** | **gebaut**, 2'206 Zeilen |
| `weather_day` | eine Stadt an einem Tag | **gebaut**, 55'497 Zeilen |
| `crime_offense` | eine **Anklage**; je Tat zählt eine (`counts`), je Fall eine (`counts_case`, 5.2) | **gebaut**, 1'875'378 Zeilen |

`tract` verbindet TIGER-Geometrie mit ACS-Attributen. Gedeutet wird: Text zu
Zahlen, `-666666666` zu `NULL`, die Armutsquote abgeleitet — und bei Tracts ohne
Einwohner `NULL` statt einer Division durch null, wobei die absoluten Zahlen
erhalten bleiben.

`weather_day` löst die Einheiten auf. GHCN-Daily führt Temperatur und
Niederschlag in Zehnteln, Schneefall dagegen schon in Millimetern; an echten
Rekorden plausibilisiert. Ein leeres Feld wird `NULL` und **nicht** `0` — bei
Niederschlag der entscheidende Unterschied. Das Messflag `T` für Spurenmengen
bekommt eine eigene Spalte, weil `0` mit `T` nicht „trocken" heisst.

`crime_offense` ist die Tabelle, die den Vergleich trägt — 1'875'378 Zeilen,
1'383'653 aus Chicago und 491'725 aus Detroit. Detroits Zeilen sind Anklagen; je
Tat ist eine als zählend markiert, und Gold nimmt nur diese (5.2). Sie leistet drei Übersetzungen auf
einmal, und jede davon ist ein eigener Fehlerherd:

| | Chicago | Detroit |
| --- | --- | --- |
| Delikte | `iucr` → NIBRS, **100 %** der Fälle | `state_offense_code` → NIBRS, **100 %** |
| Zeit | `date` ist **Ortszeit ohne Zonenangabe** | Millisekunden seit Epoch, also UTC |
| Raum | Punkt-in-Polygon gegen `tract`, **99,3 %** verortet | dito, **99,7 %** |

**Die Zeitachse ist der unauffälligste und gefährlichste Punkt.** Chicagos
`date` sieht aus wie ein Zeitstempel, ist aber Lokalzeit ohne Zone;
`2024-01-01T00:56:00.000` heisst 06:56 UTC im Winter und 05:56 im Sommer.
Detroits Feld ist bereits UTC. Wer beide als gleichartig behandelt, vergleicht
Städte, die je nach Jahreszeit eine oder zwei Stunden auseinanderliegen — und
sieht es keinem Wert an. Die Tabelle führt deshalb `occurred_at_utc` für den
Vergleich, `occurred_at_local` für die Frage, was in der Stadt Ortszeit war,
und `occurred_date_local` für den Join auf `weather_day`.

**Alle Tabellen benennen Auffälligkeiten statt sie zu entfernen.** `tract`
und `weather_day` in einer Spalte `quality_flags`, `crime_offense` über
`located`, `nibrs_mapped` und `unfounded`. Unverortete Fälle, Fälle ohne
NIBRS-Zuordnung und Detroits zurückgezogene Fälle bleiben in der Tabelle. Wer
filtern will, filtert in der Auswertung und sieht dabei, wie viele Zeilen es
betrifft.

### 8.3 Deduplikation: Duplikate, keine Dubletten

Der heutige Chicago-Stand besteht aus drei Läufen:

| Lauf | Typ | Zeilen |
| --- | --- | --- |
| `run_20260905T174633859259Z` | Vollschnappschuss | 259'272 |
| `run_20260905T175700006411Z` | Delta | 42 |
| `run_20260906T090714439584Z` | Delta | 42 |

Zusammen 259'356 Zeilen, aber nur **259'272 verschiedene `id`**. Die 84
zusätzlichen Zeilen sind der bewusste 14-Tage-Überlapp: Beide Delta-Läufe fanden
Datensätze, die der Schnappschuss schon enthielt.

Dass diese Mehrfachen **Duplikate** sind — in jedem Attribut identisch — und
keine **Dubletten**, ist H2. Die Zahl der Mehrfachen hängt davon ab, wie viele
Läufe gelesen werden; sie ist eine Eigenschaft der Architektur und keine
Ungenauigkeit. Welche Läufe den Referenzstand bilden, ist deshalb ausdrücklich
festzulegen.

Nebenbei: `case_number` ist **kein** Schlüssel. 1'383'653 Delikte verteilen sich
auf 1'383'475 Fallnummern — ein Fall kann mehrere Straftaten umfassen. Verknüpft
wird über `id`.

### 8.4 Ein falsifizierter Befund: der räumliche Join

Dies ist einer der drei Befunde aus 3.5 — gemessen unter einer Hypothese eines
früheren Entwurfs, die in der Abgabe nicht mehr steht. Der Befund bleibt, die
Nummer fällt weg.

Detroit liefert in 99,5 % der Zeilen eine eigene 15-stellige
`census_block_2020_geoid` mit, deren erste elf Stellen die Tract-GEOID sind.
Damit schien eine **unabhängige Referenz** für den selbst gerechneten
Punkt-in-Polygon-Join vorzuliegen — Chicago liefert nichts Vergleichbares.

Gemessen gegen `silver/tract`:

| | |
| --- | --- |
| vergleichbare Zeilen | 88'278 |
| von uns nicht verortet | 0 |
| **übereinstimmend** | **73'578 — 83,35 %** |
| abweichend | 14'700, davon 337 in einem anderen County |

**83 % ist keine Reproduktion. Die Annahme ist in dieser Form falsifiziert.** Die
naheliegenden Erklärungen greifen nicht: Alle 275 von Detroit genannten Tracts
existieren in TIGER 2024, es ist also kein Vintage-Problem; der Unterschied
zwischen NAD83 und WGS84 liegt bei ein bis zwei Metern; und 337 Fälle in einem
anderen County sind keine Grenzungenauigkeit.

> **Nachgemessen am 19.09.2026 (Christian).** Die Grenzlage erklärt den
> Unterschied doch: Von den abweichenden Fällen liegen **93,0 % näher als rund
> 9 Meter** an genau dem Tract, das Detroit nennt, und 49,4 % näher als einen
> Meter — der Punkt sitzt also auf der gemeinsamen Kante beider Tracts. Ursache
> ist die Verortung auf Strassenachsen: TIGER schneidet Tract-Grenzen entlang
> derselben Strassen, auf die beide Städte ihre Koordinaten setzen. Dazu kommt,
> dass NAD83 und WGS84 ein bis zwei Meter auseinanderliegen und die Pipeline
> **nicht** umrechnet. Die Zahlen stammen aus der Neuberechnung auf dem
> aktuellen Stand (79'874 vergleichbare Zeilen, 83,44 % Übereinstimmung);
> Notebook 21, Abschnitte 5.3 und 6.7, misst denselben Effekt an beiden Städten.
> **Der Schluss auf diesen Befund gehört damit nochmals angesehen** — die
> Bewertung bleibt Artans.


Der Join selbst ist nachweislich sauber: 88'278 Quellzeilen ergeben 88'278
Zeilen nach dem Join, Tracts überlappen also nicht und jeder Punkt liegt in
genau einem. Daraus folgt zwingend, dass der Punkt dort, wo Detroit ein anderes
Tract nennt, **nicht in Detroits eigenem Tract liegt**. Der Widerspruch besteht
zwischen Detroits Koordinaten und Detroits eigener GEOID, nicht zwischen Detroit
und uns.

**Die Ursache ist offen.** Möglich wäre, dass eine der beiden Angaben aus
Datenschutzgründen versetzt veröffentlicht wird, wie es kommunale
Polizeidatensätze häufig tun — das ist eine Vermutung und keine Messung. Als
Referenz zur Validierung taugt Detroits GEOID jedenfalls nicht, solange das
nicht geklärt ist.

Dass eine Annahme fällt, ist kein schlechteres Ergebnis als eine bestätigte:
Sie zeigt, dass geprüft und nicht angenommen wurde.

### 8.5 Ein zweiter, teilweise falsifizierter Befund: die NIBRS-Abbildung

Der zweite Befund aus 3.5, und der, an dem F4 hängt: Der frühere Entwurf nahm
an, die Deliktschlüssel beider Städte liessen sich **vollständig** auf
NIBRS abbilden. Seit `silver/crime_offense` beide Crosswalks auf die Falldaten
anwendet, ist das gemessen — und die Antwort hängt daran, was „vollständig"
heissen soll.

Gemessen auf Tatebene über die 1'851'950 Delikte der Jahrgänge 2021–2026:

| | Chicago | Detroit | zusammen |
| --- | ---: | ---: | ---: |
| Delikte (Tatebene) | 1'383'653 | 468'297 | 1'851'950 |
| Quellcode im Crosswalk bekannt | **100 %** | **100 %** | **100 %** |
| davon Auffang `90Z` | 41'324 | 16'127 | 57'451 |
| **mit einem echten NIBRS-Delikt** | **97,0 %** | **96,6 %** | **96,9 %** |

> **Nachgemessen am 20.09.2026 (Christian).** Die Zahlen sind auf den aktuellen
> Stand gehoben; zuvor standen hier 344'617 Delikte und 10'442 im Auffang. Der
> Zuwachs kommt aus Detroits Delta-Läufen und den nachgezogenen Chicago-Deltas,
> nicht aus einer geänderten Zuordnung. **Die Prozentsätze und damit die
> Aussage sind unverändert.**

**Abdeckung ja, Abbildung nein.** Kein Chicago-Code fällt stillschweigend
heraus, das war die eigentliche Sorge. Aber 10'476 Fälle tragen ein Delikt, das
NIBRS nicht kennt: Verstösse gegen Registrierungspflichten, Bewährungsauflagen,
Illinois-Eigenheiten wie *Criminal Fortification*. Sie landen auf `90Z All Other
Offenses` — ein Code, der gültig ist, für einen Deliktvergleich aber nichts
aussagt.

Für Chicago ist der Anteil im Katalog viel höher als in den Fällen: **69 der 434
Katalogzeilen** sind Auffangzeilen (15,9 %), in den Falldaten nur 2,97 %. Die
Delikte ohne NIBRS-Entsprechung sind also überwiegend seltene — gut für den
Vergleich, aber gemessen und nicht angenommen.

**Detroits offene Fälle sind ein anderer Fall.** Dort steht kein Auffangcode,
sondern gar keiner, weil Detroit in `state_offense_code` **zwei Codelisten
mischt**: die *Offense File Class* (was ist passiert) und den *Arrest Charge*
(womit wird jemand beschuldigt). Das MICR-Handbuch führt beide getrennt, 833
Arrest Charges unter 104 File Classes.

Detroit veröffentlicht beide in einem vierstelligen Feld. File Classes sind
fünfstellig und werden gekürzt (`13001` → `1301`), Arrest Charges sind von Haus
aus vierstellig — **54 Kürzel sind dadurch doppeldeutig**: `0901` ist zugleich
die gekürzte File Class `09001` *Murder* und der Arrest Charge *Family, Gun*.
Für alle 54 stützt Detroits eigene Beschreibung die File-Class-Lesart; keine
einzige widerspricht ihr.

23 Codes waren jedoch **nur** Arrest Charge und damit in einer File-Class-Tabelle
nicht auffindbar. Sie sind über den Weg Arrest Charge → File Class → NIBRS
angeschlossen, nachgerechnet in
[`tools/extend_micr_arrest_charges.py`](../tools/extend_micr_arrest_charges.py):
20 von 23, was Detroit von 94,96 % auf **98,10 %** hob. Die letzten drei
folgen gleich darunter.

**Drei blieben lange offen**, weil Detroits eigene Beschreibung dem Handbuch
widerspricht — 1'647 Fälle:

| Code | Fälle | Detroit sagt | Handbuch sagt |
| --- | ---: | --- | --- |
| `3072` | 1'447 | RETAIL FRAUD – **THEFT** | Retail Fraud **Misrepresentation** 2nd Degree, File Class `30001` |
| `5421` | 100 | ACCIDENT, HIT & RUN | Operating **ORV** Under the Influence, File Class `54002` |
| `5422` | 100 | ACCIDENT, HIT & RUN | Permitted Person Under the Influence, File Class `54002` |

Der Unterschied ist erheblich: bei `3072` steht 26A *False Pretenses* gegen 23C
*Shoplifting*. Hier zu raten wäre genau der Fehler gewesen, der den
Chicago-Crosswalk 106 Zeilen gekostet hat — gültige Codes für das falsche
Delikt. Die Notiz lautete deshalb: *nur Detroit kann das auflösen.*

**Detroit hat es aufgelöst — in zwei Feldern, die wir nicht gelesen hatten.**
Der Layer liefert zu jeder Zeile ausser dem vierstelligen Code auch
`arrest_charge`, die **fünfstellige File Class**, und `charge_description`,
deren Bezeichnung im Klartext. Beide sind über alle 1'647 Zeilen eindeutig:

| Code | Detroits `arrest_charge` | Detroits `charge_description` | Name dieser File Class im Handbuch |
| --- | --- | --- | --- |
| `3072` | `30002` | *Retail Fraud – Theft* | **Retail Fraud – Theft** |
| `5421`, `5422` | `54001` | *Accident, Hit & Run* | **Hit and Run Motor Vehicle Accident** |

Zwei unabhängige Spalten sagen dasselbe, und die genannte File Class trägt im
Handbuch genau den Namen, den Detroit schreibt. Damit ist die Zuordnung **nicht
geraten, sondern belegt** — nur eben aus der Quelle statt aus dem Dokument. Die
Herkunftsspalte sagt das: `detroit_charge_file_class` statt
`micr_arrest_charge_1110_2024`.

**Das schliesst Detroits Lücke ganz**: von 98,10 % auf **100 %**. `3072` bringt
1'447 Fälle nach `23C Shoplifting` und verdoppelt Detroits Shoplifting-Zahl
beinahe — von 1'740 auf 3'187. `5421` und `5422` gehen mit je 100 Fällen nach
`90Z`.

Nachgerechnet wird das in
[`notebooks/11_detroit_source.ipynb`](../notebooks/11_detroit_source.ipynb),
Abschnitt 7.1; drei Tests halten fest, dass diese drei Zeilen — und nur sie —
vom Handbuch abweichen und ihren Beleg mitführen.

**Ein Vorbehalt bleibt.** Bei 40 der 1'447 Zeilen weicht `offense_description`
von `charge_description` ab: Die Anklage lautet auf Retail Fraud, der Vorfall
ist als Körperverletzung oder Sachbeschädigung erfasst. Das ist kein
Widerspruch, sondern die Granularität der Quelle — eine Zeile ist eine Anklage, nicht
der Vorfall.

**Was die Tabelle über die Hypothese hinaus zeigt.** Zum ersten Mal lassen sich
beide Städte nebeneinanderstellen, ohne dass eine Zahl etwas anderes bedeutet
als die daneben:

Die sechs häufigsten NIBRS-Delikte über die Jahrgänge 2021–2026, auf der
Tatebene, ohne den Auffangcode `90Z`:

| NIBRS | Delikt | Chicago | Detroit |
| --- | --- | ---: | ---: |
| `13B` | Simple Assault | 206'608 | 86'602 |
| `23H` | All Other Larceny | 199'634 | 21'337 |
| `290` | Destruction/Damage/Vandalism | 156'306 | 56'572 |
| `240` | Motor Vehicle Theft | 115'604 | 44'485 |
| `13C` | Intimidation | 104'180 | 7'755 |
| `13A` | Aggravated Assault | 86'134 | 46'654 |

Absolut sind das keine vergleichbaren Zahlen — Chicago hat rund viermal so
viele Einwohner. Vergleichbar werden sie erst mit dem Nenner aus `tract`, und
das gehört nach Gold. Aber die **Kategorien** sind jetzt dieselben, und das war
die Voraussetzung.

**Warum das überhaupt auffiel.** Die erste Fassung des Chicago-Crosswalks
entstand aus einem Join über den I-UCR-Code auf eine nach ILCS-Statut
geschlüsselte Codetabelle der Illinois State Police. Beide Systeme benutzen
vierstellige Kürzel, meinen damit aber Verschiedenes. Der Join lieferte deshalb
**gültige NIBRS-Codes für das falsche Delikt** — `1140 EMBEZZLEMENT` zeigte auf
`250 Counterfeiting/Forgery`, vier Prostitutionszeilen auf `11A Rape`. Eine
Prüfung auf Gültigkeit hätte das nie gefunden; aufgefallen ist es erst beim
Vergleich der Deliktbeschreibungen beider Seiten.

Die Zuordnung entsteht seither aus Chicagos eigener Beschreibung des Delikts
gegen die amtliche Codeliste, festgehalten in
[`tools/build_iucr_nibrs_mapping.py`](../tools/build_iucr_nibrs_mapping.py).
106 der 434 Zeilen bekamen dabei einen anderen Code.

**Die Lehre ist allgemeiner als der Fall.** Ein Schlüssel, der in zwei Systemen
dieselbe Form hat, ist deshalb noch nicht derselbe Schlüssel. Ein Join darüber
scheitert nicht — er liefert ein plausibles, prüfbar formgültiges und falsches
Ergebnis. Gegen diese Fehlerklasse hilft keine Schemaprüfung, sondern nur ein
Abgleich der Semantik: hier der Deliktbeschreibungen, die beide Seiten
mitliefern.

### 8.6 Ein Befund ohne Hypothese: die Zeitzone

Zu diesem gehört keine Hypothese — er fiel bei der Arbeit an und ist der
lehrreichste des Projekts, weil derselbe Fehler **zweimal** auftrat, an zwei
verschiedenen Stellen, in zwei verschiedenen Formen. Beide Male war das
Ergebnis typrichtig und inhaltlich falsch.

#### Erster Fall: das Abfragefenster

Detroits Ingestion holte das Jahr 2024 mit einem Filter dieser Art:

```sql
incident_occurred_at >= TIMESTAMP '2024-01-01 00:00:00'
AND incident_occurred_at <  TIMESTAMP '2025-01-01 00:00:00'
```

Gemeint war: der 1. Januar in Detroit. Bekommen hat man: der 1. Januar in UTC.
Die Quelle sagt selbst, welche der beiden Lesarten gilt — der ArcGIS-Layer
deklariert seine Datumsfelder ausdrücklich:

```json
"dateFieldsTimeReference": {
  "timeZone": "UTC", "timeZoneIANA": "Etc/UTC", "respectsDaylightSaving": false
}
```

Detroit liegt fünf Stunden hinter UTC. `2024-01-01 00:00 UTC` ist dort erst der
**31. Dezember 2023 um 19:00**. Das Fenster war also um fünf Stunden verschoben:
Es nahm den Abend des 31.12.2023 mit und liess den Abend des 31.12.2024 weg.

**Gemessen am alten und am neuen Bestand:**

| | Zeilen | Ortszeit Detroit |
| --- | ---: | --- |
| nur im alten Lauf | 66 | alle 31.12.**2023** ab 19:00 |
| nur im neuen Lauf | 56 | alle 31.12.**2024** ab 19:00 |

Die entscheidende Kontrolle ist die einfachste: Wie viele Fälle eines
Jahrgangs 2024 liegen nach Ortszeit **nicht** im Jahr 2024?

| | |
| --- | --- |
| alter Lauf | 66 |
| **neuer Lauf** | **0** |

Der Fix zieht die Fenstergrenzen in Detroiter Ortszeit und rechnet **jede
Grenze einzeln** nach UTC um — nötig, weil ein Tag mit Zeitumstellung 23 oder
25 Stunden hat und ein fester Versatz deshalb nicht genügt. Das Manifest führt
seither beide Fassungen mit: `window_start_local 2024-01-01T00:00:00-05:00`
und `window_start_utc 2024-01-01T05:00:00+00:00`.

#### Zweiter Fall: die gemeinsame Zeitachse

Beim Bau von `crime_offense` trat dasselbe in anderer Gestalt auf (8.2):
Chicago liefert `date` als **Ortszeit ohne Zonenangabe**, Detroit
Millisekunden seit Epoch, also einen echten Zeitpunkt. Zwei Delikte um
`08:30` sind damit **nicht gleichzeitig** — sie liegen je nach Jahreszeit eine
oder zwei Stunden auseinander. Ein Vergleich nach Tageszeit wäre ohne
Umrechnung wertlos gewesen — und F3 fragt genau danach.

#### Was daraus folgt

**Ein Zeitstempel ohne Zone ist kein Zeitstempel.** `2024-01-01T00:56:00.000`
sieht in beiden Quellen gleich aus und bedeutet Verschiedenes — in Chicago eine
Ortszeit, in Detroit gäbe es das Feld in dieser Form gar nicht. Kein
Schemacheck, keine Typprüfung und kein Vollständigkeitsnachweis findet das: Die
Werte sind gültige Zeitstempel, die Zeilenzahlen stimmen, das Manifest meldet
Erfolg.

**Gefunden hat es eine Prüfung gegen etwas, das wahr sein muss.** Ein Jahrgang
2024 enthält keine Fälle aus 2023 — diese Aussage ist unabhängig vom Code
prüfbar und deshalb die einzige, die den Fehler sichtbar macht. Sie kostet eine
Zeile SQL und ist dieselbe Bauart wie die Semantikprüfung aus 8.5: nicht die
Form prüfen, sondern das, was die Daten über sich behaupten.

**Die Fehlerklasse ist die gefährlichste im ganzen Projekt**, weil sie
geräuschlos ist. Der ISP-Join (8.5), das Zeitfenster und Detroits zwei
Codelisten (8.5) haben dasselbe Muster: formal einwandfrei, inhaltlich falsch,
und keiner von ihnen hat je eine Fehlermeldung erzeugt.

### 8.7 Ein zweiter Befund ohne Hypothese: die fehlenden Koordinaten

Der dritte Befund aus 3.5, und derjenige, der den Massstab aus 3.4 trägt:
**Fehlende Koordinaten treten nicht zufällig auf, sondern hängen vom
Delikttyp ab.** Gemessen mit einem Chi-Quadrat-Unabhängigkeitstest, je Stadt
in Notebook 03 und 13 — und seit Gold auf der **gemeinsamen** NIBRS-Achse in
Notebook 34, Abschnitt 5.2. Erst sie macht die Frage vergleichbar: Je Stadt
steht sie sonst in deren eigenen Kategorien, Chicago kennt „Delikte an
Kindern", Detroit „Family Offense".

Verglichen wird nicht der Prozentsatz, sondern das **Vielfache des
Stadtschnitts** — Chicago verliert insgesamt 0,81 % der Fälle, Detroit 0,29 %.

| | Chicago | Detroit |
| --- | ---: | ---: |
| Sexualdelikte, Vielfaches des Stadtschnitts | **12,0×** | **5,2×** |
| Betrug, Anteil ohne Koordinate | **3,78 %** | 0,19 % |
| Betrug, Vielfaches des Stadtschnitts | 4,7× | 0,7× |

**Eine Kategorie trägt in beiden Städten**, und es ist dieselbe: Sexualdelikte.
Die Ursache liegt nahe und ist in beiden Systemen dieselbe — bei diesen
Delikten wird die Adresse zurückgehalten. Weil die Richtung übereinstimmt,
verzerrt dieser Teil der Lücke den Städtevergleich **nicht** systematisch.

**Eine zweite Kategorie trägt nur in Chicago**, und das ist der eigentliche
Befund: Betrug, mit einem Faktor 20 zwischen den Städten. Plausibel ist, dass
Chicago Betrug ohne Tatort mitführt, den es telefonisch oder online gab;
Detroits Erfassung über den Vorfallsbericht verlangt eine Adresse. Das ist
eine Vermutung und keine Messung.

**Was daraus folgt.** Ein Vergleich der *Gesamtraten* trägt: 0,81 % gegen
0,29 % Ausfall verschieben keine Rangfolge. Ein Vergleich **je Delikttyp**
trägt für Sexualdelikte, weil die Verzerrung gleichgerichtet ist — aber
**nicht für Betrug**. Daraus folgt auch die Entscheidung, fehlende Koordinaten
zu **markieren statt zu löschen**: Ein nicht zufälliger Ausfall lässt sich
nicht wegwerfen, ohne die Auswertung zu verzerren. `geo_status` zeigt deshalb
je Zeile, was fehlt, statt die Zeile wegzulassen.

---

## 9 · Grenzen

**Zur Datengrundlage**

- **Erfassung ist nicht Kriminalität.** Gemessen wird angezeigte und erfasste
  Kriminalität. Unterschiedliche Anzeigebereitschaft zwischen Städten und
  Delikten bleibt unsichtbar.
- **Tatort ist nicht Wohnort.** Ein Innenstadt-Tract mit wenigen Einwohnern und
  vielen Pendlern bekommt eine überhöhte Rate.
- **Ökologischer Fehlschluss.** Ein Zusammenhang auf Tract-Ebene erlaubt keine
  Aussage über einzelne Personen.
- **Die Datenlücken sind nicht symmetrisch.** In Wayne County fehlt bei 9,6 %
  der Tracts der Einkommenswert, in Cook County bei 1,7 %. Auch die Geo-Lücke
  unterscheidet sich: 1,48 % in Chicago gegen 0,15 % in Detroit. Eine Verzerrung
  wirkt damit ungleich auf die beiden Städte.
- **Die Städte zählen verschieden.** Chicago führt je Vorfall ein Delikt
  (Mordopfer ausgenommen: ein Datensatz je Opfer), Detroit jedes Delikt eines
  Vorfalls — 5,6 % mehr Taten als Fälle. Im Jahrgang 2024 liegt Detroit auf
  Tatebene bei 133,1 je 1'000, auf Fallebene (`counts_case`, beide Städte
  dieselbe Regel) bei 124,6; Chicago in beiden bei 94,5. Die Reihenfolge
  bleibt, der Abstand schrumpft. Beide Masse sind in Gold; welches die Aussage trägt, ist zu
  entscheiden (5.2).

**Zu den Quellen**

- **Der ACS ist eine 5-Jahres-Schätzung** und hat eine gröbere Zeitachse als
  die Falldaten. Seit Vertrag 6 liegt er je Vintage in `dim_tract_acs`, und
  `fact_offense.population_vintage` nennt je Tat den für sie gültigen — aber
  nur bis 2024: Die Raten für 2025 und 2026 ruhen auf der Bevölkerung von
  2024, weil es keine neuere Veröffentlichung gibt. Innerhalb eines Jahrgangs
  ist der Nenner konstant.
- **Wir laden nur die Schätzwerte, nicht die Fehlermargen.** Für Einwohnerzahlen
  als Nenner vertretbar, für Aussagen über Einkommensunterschiede nicht.
- **NOAA veröffentlicht mit rund vier Tagen Nachlauf.** Ein Anspruch, stets den
  Vortag zu haben, ist bei dieser Quelle strukturell nicht erfüllbar.
- **Die Wetterreihen sind vor 1970 lückenhaft** — Detroit fehlen 4'451 Tage,
  alle davor. Ab 2001 ist die Reihe für beide Städte lückenlos. Die vier
  ausgewerteten Grössen sind ausserdem erst ab Ende 1958 belegt.
- **Eine Station ist kein Stadtmittel.** Gemessen wird am Flughafen, nicht in
  der Innenstadt; städtische Wärmeinseln liegen im Sommer mehrere Grad darüber.

**Zur Umsetzung**

- **Keine Parallelität und keine Wiederaufnahme.** Der Controller fährt die Stufen seriell und bricht beim ersten Fehler ab; ein abgebrochener Lauf wird neu gestartet, nicht fortgesetzt. Bei Minuten Laufzeit ist das billiger als ein Zustandsautomat.
- **Die Mehrheitsregel schliesst Grenzfälle aus, und zwar nicht neutral.**
  5'249 Chicagoer Delikte liegen innerhalb der Stadtgrenze, aber in einem
  Tract, der mehrheitlich zur Nachbargemeinde gehört. Weil diese Randtracts
  überdurchschnittlich deliktdicht sind — 227 je 1'000 gegen 94,5 im
  Stadtschnitt —, ist Chicagos Rate um gut einen Punkt untertrieben: 94,5
  statt 95,6. Detroit ist praktisch nicht betroffen (12 Fälle). Gemessen in
  Notebook 34, Abschnitt 3.2.
- **Keine Alarmierung ausser dem roten Lauf.** Der wöchentliche Datenlauf
  scheitert, wenn eine Quelle älter als acht Tage ist oder die Strecke bricht —
  aber niemand wird angerufen. Wer es erfahren will, muss auf *Actions* sehen.
- **Die Dokumente beschreiben einen Referenzstand, nicht den Tag.** Ein
  frischer Lauf baut andere Zahlen — die Quellen bewegen sich wöchentlich.
  Der Datenlauf hält die dokumentierten Zahlen deshalb nicht gegen den
  frischen Stand (das wäre jede Woche rot), sondern weist die Abweichung je
  Grösse als **Drift** aus (`orchestration.drift`, in der Job-Zusammenfassung)
  und wird erst über einer Toleranz rot — Raten ab 0,1 je 1'000, Zahlen über
  1 %. Das ist der Moment, den Referenzstand nachzuziehen; bis dahin ist die
  Drift eine Zahl, kein Alarm.

---

## 10 · Reproduktion

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest                       # 1'748 Tests, 12 davon übersprungen
python -m pytest -m ""                 # mit den Referenzwächtern: 1'850
```

Daten laden — jede Pipeline schreibt einen neuen, unveränderlichen Lauf:

```bash
python -m chicago_pipeline.download_chicago --year 2024
python -m detroit_pipeline.extract_detroit --mode delta --years 2024
python -m census_pipeline.download_tiger --auslieferung tract
python -m census_pipeline.download_tiger --auslieferung place
python -m census_pipeline.download_acs   # braucht CENSUS_API_KEY in .env
python -m weather_pipeline.download_noaa
```

**Beide TIGER-Aufrufe sind nötig.** `tract` ist die Raumeinheit, `place` die
Stadtgrenze; ohne die zweite bekommt `dim_tract` keine Stadtzuordnung, und die
Rate je Einwohner hat keinen Nenner. Der Aufruf ohne `--auslieferung` lädt nur
Tracts und scheitert dabei nicht — er liefert still ein Gold ohne Städte.

Oder in einem Aufruf, mit Protokoll und Herkunft:

```bash
python -m orchestration.run_all
```

Silver, Gold und die Auswertungsumgebung einzeln ableiten — die Reihenfolge
gilt, `build_crime_offense` braucht `tract`:

```bash
python -m silver_pipeline.build_tract
python -m silver_pipeline.build_place
python -m silver_pipeline.build_weather_day
python -m silver_pipeline.build_crime_offense
python -m gold_pipeline.build_gold
python -m serving.build_analysis_db
python -m serving.export_geojson
```

**Wichtig zur Reproduzierbarkeit.** Die Falldaten wachsen laufend, ein Lauf von
heute liefert andere Zeilen als einer von letzter Woche. Byte-identisch
reproduzierbar sind nur die eingefrorenen Quellen TIGER und ACS. Für einen
gemeinsamen Auswertungsstand ist deshalb festzulegen, **welche Läufe** gelten —
die Zahlen in diesem Dokument beziehen sich auf die in 8.3 genannten
Chicago-Läufe und die zugehörigen Läufe der übrigen Quellen.

`data/` ist vollständig aus der Versionierung ausgeschlossen.

**Ohne eigenen Ladelauf.** Seit dem 13.9. liegt der veröffentlichte Stand auf
SeaweedFS (7.4). Wer `STORAGE_BACKEND=hybrid` samt Schlüsseln in `.env` setzt,
braucht die Quellen **nicht** selbst zu laden: Was lokal fehlt, wird von dort
gelesen. Der Referenzstand ist damit kein Zettel mehr, sondern ein Ort —
welche Läufe er umfasst, sagt das Manifest jeder Tabelle unter
`derived_from`.

```bash
python -m storage                                  # prüft die Verbindung und den eigenen Stand
python -m orchestration.run_all --ohne-ingestion    # Silver, Gold und Serving daraus ableiten
```

---

## 11 · Wo was liegt

### 11.1 Der Code

| Was | Wo |
| --- | --- |
| Ingestion, vier Pipelines | `src/crime/{chicago,detroit,census,weather}_pipeline/` |
| **Der eine Manifest-Leser** | `src/crime/manifeste/` — findet fertige Läufe und gebaute Tabellen für Ingestion, Silver, Controller und Werkzeuge |
| **Der ganze Lauf, in Reihenfolge** | `src/crime/orchestration/run_all.py` → `data/pipeline_run.json` |
| **Was von Raw und Bronze bleiben muss** | `src/crime/orchestration/aufraeumen.py` — zeigt je Quelle, was bleibt und warum; löscht nur mit `--loeschen` |
| **Wo die Daten liegen** | `src/crime/storage/` — `STORAGE_BACKEND=local`, `hybrid` oder `s3`. Aufbau: [`storage-architektur.md`](storage-architektur.md), Bedienung: README 2.5 |
| Silver-Aufbau | `src/crime/silver_pipeline/` |
| Gold-Aufbau | `src/crime/gold_pipeline/build_gold.py` → `data/gold/` |
| **Auswertungsumgebung** | `src/crime/serving/build_analysis_db.py` → `data/serving/analyse.duckdb` |
| **Tract-Umrisse für eine Karte** | `src/crime/serving/export_geojson.py` → `data/serving/tracts.geojson` |
| **Der Städtevergleich selbst** | `src/crime/silver_pipeline/build_crime_offense.py` → `data/silver/dataset=crime_offense/` |
| Tests | `tests/`, nach Pipeline gegliedert |

### 11.2 Die Notebooks: der Rechenweg

| Was | Wo |
| --- | --- |
| Quelle Chicago erklärt | [`notebooks/01_chicago_source.ipynb`](../notebooks/01_chicago_source.ipynb) |
| Chicago-Ingestion vorgeführt | [`notebooks/02_chicago_bronze_ingestion.ipynb`](../notebooks/02_chicago_bronze_ingestion.ipynb) |
| Datenqualität Chicago | [`notebooks/03_chicago_data_quality.ipynb`](../notebooks/03_chicago_data_quality.ipynb) |
| Quelle Detroit erklärt | [`notebooks/11_detroit_source.ipynb`](../notebooks/11_detroit_source.ipynb) |
| Datenqualität Detroit | [`notebooks/13_detroit_data_quality.ipynb`](../notebooks/13_detroit_data_quality.ipynb) |
| Detroit-Ingestion vorgeführt | [`notebooks/12_detroit_bronze_ingestion.ipynb`](../notebooks/12_detroit_bronze_ingestion.ipynb) |
| Quelle Census erklärt | [`notebooks/21_census_source.ipynb`](../notebooks/21_census_source.ipynb) |
| Quelle Wetter erklärt | [`notebooks/22_weather_source.ipynb`](../notebooks/22_weather_source.ipynb) |
| Storage-Messung | [`notebooks/31_storage_evaluation.ipynb`](../notebooks/31_storage_evaluation.ipynb) |
| Serving-Messung: Sichten oder Kopie | [`notebooks/33_serving_evaluation.ipynb`](../notebooks/33_serving_evaluation.ipynb) |
| Referenzquelle NIBRS, Mapping-Herkunft | [`notebooks/32_nibrs_source.ipynb`](../notebooks/32_nibrs_source.ipynb) |
| Gold-Sternschema, Stadtzuordnung | [`notebooks/34_gold_sternschema.ipynb`](../notebooks/34_gold_sternschema.ipynb) |

### 11.3 Vertiefungen, die in die Abgabe einfliessen

Diese Dokumente vertiefen einzelne Kapitel. **Ihr Inhalt wandert in das
Word-Dokument**; verwiesen wird von dort nicht zurück (Entscheid vom
19.9.2026). Geschrieben sind sie trotzdem für jemanden, der das Projekt nicht
kennt — was sich nicht ohne uns lesen lässt, lässt sich auch nicht übertragen.

| Was | Wo |
| --- | --- |
| **Ist- und Ziel-Architektur** | [`architektur-ist-und-ziel.md`](architektur-ist-und-ziel.md) — Teil A, was gebaut ist; Teil B, wohin es geht (Container, Zugang, Auswertung, Sicherung, Cloud) |
| **Dieselbe Architektur auf einer A4-Seite** | [`architektur-einseiter.html`](architektur-einseiter.html) — zum Ausdrucken, mit zwei gezeichneten Bildern |
| **Der Aufbau in zwei Bildern** | [`architektur.md`](architektur.md) — Abhängigkeiten und Datenfluss, erzeugt von [`tools/build_architekturbilder.py`](../tools/build_architekturbilder.py), dazu ein Lesepfad |
| **Vier Arten zu zählen** | [`zaehlperspektiven.md`](zaehlperspektiven.md) — Anklage, Tat, Fall, Vorfall; welche Zahl welche Frage beantwortet und was sich nicht addiert |
| **Eine Zahl über sieben Schichten** | [`eine-zahl.md`](eine-zahl.md) — eine einzelne Zahl von der Quelle bis Gold zurückverfolgt |
| **Die Datenablage im Aufbau** | [`storage-architektur.md`](storage-architektur.md) — die drei Modi, was zugesichert wird, die API und die Fehlerbilder |
| **Würfel und Sternschema erklärt** | [`sternschema-und-wuerfel.md`](sternschema-und-wuerfel.md) — die beiden Bauweisen mit Diagrammen, als Vorlage für die Präsentation. Dieselbe Darstellung mit durchgehendem Layout: [`sternschema-und-wuerfel.html`](sternschema-und-wuerfel.html) |
| **Feldkatalog** | [`feldkatalog.md`](feldkatalog.md) — 192 Spalten in 15 Tabellen, erzeugt von [`tools/build_feldkatalog.py`](../tools/build_feldkatalog.py) |
| **Was nach LN1 kommt** | [`ausblick.md`](ausblick.md) — Lineage und Stichtagskonsistenz, Versionierung der Ladelogik, Skalierung, Cloud; mit Messwerten und Reihenfolge |

### 11.4 Amtliche Quellen und die daraus erzeugten Crosswalks

| Was | Wo |
| --- | --- |
| **NIBRS-Codeliste, amtlich** | `config/nibrs_offense_codes_2025.csv` — 81 Codes aus Anhang A von [`nibrs_technical_specification_2025.pdf`](quellen/nibrs_technical_specification_2025.pdf) |
| IUCR nach NIBRS (Chicago) | `config/iucr_nibrs_mapping.csv`, erzeugt von [`tools/build_iucr_nibrs_mapping.py`](../tools/build_iucr_nibrs_mapping.py); Katalog vom [Datenportal der Stadt](https://data.cityofchicago.org/resource/c7ck-438e.json) |
| MICR nach NIBRS (Detroit) | `config/micr_nibrs_mapping.csv`, erweitert von [`tools/extend_micr_arrest_charges.py`](../tools/extend_micr_arrest_charges.py); Quellen [`micr_manual_1110_2024.pdf`](quellen/micr_manual_1110_2024.pdf) und [`micr_appendix_f_2009.pdf`](quellen/micr_appendix_f_2009.pdf) |
| Codetabelle Illinois State Police | [`isp_nibrs_code_table_2026.xlsx`](quellen/isp_nibrs_code_table_2026.xlsx) — nach ILCS-Statut geschlüsselt, **nicht** als Crosswalk verwendbar, siehe 8.5 |
| **Amtliche Deliktkategorien** | `config/nibrs_offense_categories_2025.csv`, gelesen von [`tools/build_nibrs_categories.py`](../tools/build_nibrs_categories.py) aus [`nibrs-user-manual-2025-0-062625.pdf`](quellen/nibrs-user-manual-2025-0-062625.pdf) — 28 + 10 Kategorien |
| Die vier zurückgezogenen Codes | [`NIBRS_Offense_Codes.pdf`](quellen/NIBRS_Offense_Codes.pdf), Fassung 2011 — überholt, aber der einzige Beleg für `90A`, `90E`, `90H`, `90I` |
| Zweite Abschrift der Codeliste | [`illinois_nibrs_iepd_2023.xlsx`](quellen/illinois_nibrs_iepd_2023.xlsx), Blatt `OffenseCode` — Illinois' eigene Abschrift derselben FBI-Liste; belegt alle 81 Bezeichnungen statt zehn Stichproben |

### 11.5 Interne Arbeitsgrundlagen — fliessen nicht ein

Diese Dokumente setzen voraus, dass man am Projekt arbeitet. Sie stehen hier,
damit die Ablage vollständig beschrieben ist, **nicht** als Anhang: Sie halten
offene Entscheide, Lücken und den Arbeitsverlauf fest und sind für uns
geschrieben, nicht für eine Leserin der Abgabe. Wird das Repository mit
abgegeben, liegen sie zwar bei — aber niemand wird darauf verwiesen.

| Was | Wo |
| --- | --- |
| Technische Entscheide | [`projektabsprache.md`](intern/projektabsprache.md) |
| Anforderungen gegen Stand, offene Lücken | [`leistungsnachweise.md`](intern/leistungsnachweise.md) |
| Was sich wann geändert hat | [`AENDERUNGEN.md`](intern/AENDERUNGEN.md) — ein Eintrag je Pull Request, mit den Zahlen und ihrer Begründung |
| Was beim Aufräumen verlorenginge | [`datenhistorie.md`](intern/datenhistorie.md) — Entscheidungspapier zur Aufbewahrung |
| Was die Strecke an Platz braucht | [`platzbedarf.md`](intern/platzbedarf.md) — gemessen je Schicht und je Quelle auf 2021–2026 hochgerechnet, **erzeugt** |
| Detroit-Pipeline Schritt für Schritt | [`DETROIT_PIPELINE_ANLEITUNG.md`](intern/DETROIT_PIPELINE_ANLEITUNG.md) |

Die Einteilung dieses Kapitels ist auch in [`docs/README.md`](README.md)
festgehalten und wird dort von `tests/test_dokumentwegweiser.py` geprüft.

**Keine dieser Konfigurationsdateien wird von Hand gepflegt** — jede wird
von einem Werkzeug erzeugt, und seit dem 12.9. prüft je ein Test, dass sich das
wiederholen lässt: Das Werkzeug läuft in ein temporäres Verzeichnis, und das
Ergebnis muss byteweise mit der versionierten Datei übereinstimmen.

Ohne diese Prüfung war die Zusage eine Behauptung: Wer eine Zuordnung von Hand
in die CSV geschrieben hätte, wäre durch alle übrigen Tests gekommen — sie
prüfen die Datei, nicht ihre Herkunft. Chicagos Werkzeug läuft dabei mit
`--offline`, liest den Katalog also aus der versionierten Datei: Geprüft werden
die **Zuordnungsregeln**, nicht ob sich Chicagos Katalog bewegt hat. Diese
zweite Frage stellt Notebook 32 live gegen das Portal — als Test hätte sie
zwanzig Sekunden gekostet und an einer Netzverbindung gehangen.

---

## Offen für LN1

Damit dieses Dokument vollständig ist, fehlen:

- **Ein Notebook, das den Vergleich über alle Hypothesen rechnet.** Die Rate je
  Einwohner steht seit Gold zur Verfügung (5.2) und ist in Notebook 34
  gerechnet; ein Notebook, das den ganzen Vergleich daraus aufbaut, fehlt noch

**Erledigt seit der Abgabe.** Der *Entscheid über Forschungsfragen und
Hypothesen* steht: F1 bis F6 mit H1 bis H6, Wortlaut in
[`forschungsfragen.md`](forschungsfragen.md). Gold war bewusst so gebaut, dass
er nichts daran ändert — die Granularität bleibt, und jede Frage ist ein Filter
darauf (5.2). Und das *Notebook, das die Hypothesen rechnet*, ist
[`../notebooks/36_hypothesen.ipynb`](../notebooks/36_hypothesen.ipynb); es misst
alle sechs und zitiert sie wörtlich.
