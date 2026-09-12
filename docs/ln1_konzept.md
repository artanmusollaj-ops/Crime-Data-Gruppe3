# Leistungsnachweis 1: Konzept und Umsetzung

**Vergleichbare Kriminalitätsdaten für Chicago und Detroit**

CAS Data Engineering · Gruppe 3 · Christian Antonucci, Artan Musollaj

---

Dieses Dokument ist die Abgabe zu Leistungsnachweis 1. Es beschreibt, was gebaut
wurde und warum es so gebaut wurde.

Zwei Dokumente ergänzen es und sind **nicht** Teil der Abgabe, sondern
Arbeitsgrundlage: [`projektabsprache.md`](projektabsprache.md) hält die
technischen Entscheide mit ihrer Begründung, [`leistungsnachweise.md`](leistungsnachweise.md)
stellt die Anforderungen dem Stand gegenüber. Wo eine Aussage hier auf einer
Messung beruht, steht der Verweis auf das Notebook, das sie erzeugt — die Zahlen
sind nachrechenbar, nicht abgeschrieben.

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
Speicherarchitektur aus unveränderlichen Läufen, und **alle drei
Silver-Tabellen** — seit `crime_offense` sprechen beide Städte dieselbe
Deliktsprache, liegen auf derselben Zeitachse und tragen dieselbe
Raumeinheit. Jede Quelle weist ihre Vollständigkeit nach, statt sie zu
behaupten. **621 automatisierte Tests** laufen ohne Netzzugriff und ohne
Schlüssel.

| | |
| --- | --- |
| Chicago, Jahrgang 2024 | 259'272 Delikte |
| Detroit, Jahrgang 2024 | 88'685 Anklagen zu 85'335 Taten |
| Census Tracts, Illinois und Michigan | 6'282, mit Geometrie und Sozialdaten |
| Wetter, zwei Stationen | 55'449 Stadt-Tage, zurück bis 1942 |

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

> **Entwurf.** Der Entscheid über Auswahl und Formulierung ist offen; siehe
> [`leistungsnachweise.md`](leistungsnachweise.md) Abschnitt 2.3.

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

| | Frage | Modulbezug |
| --- | --- | --- |
| **FF1** | Unter welchen Bedingungen lassen sich zwei unabhängig erhobene, unterschiedlich kodierte kommunale Kriminalitätsdatensätze so integrieren, dass ein valider Vergleich möglich wird? | Kompatibilität, Integration |
| **FF2** | Welches Qualitätsniveau erreichen die fünf Quellen, gemessen an definierten Dimensionen — und genügt es dem festgelegten Verwendungszweck? | Datenqualität, Bewertung |
| **FF3** | Welche Bereinigungsschritte sind erforderlich, und wie stark verändern sie das Ergebnis? | Datenbereinigung |

### 3.3 Hypothesen

Alle falsifizierbar, alle mit einem Verfahren aus dem Modul prüfbar, alle mit
den vorliegenden Daten durchführbar. **Sechs sind bereits gemessen** — vier
bestätigt oder vorgeprüft, **eine falsifiziert, eine teilweise falsifiziert.**

| | Hypothese | Verfahren | Stand |
| --- | --- | --- | --- |
| **H1** | Fehlende Koordinaten treten **nicht zufällig** auf, sondern hängen vom Delikttyp ab. | Chi-Quadrat-Unabhängigkeitstest | vorgeprüft: 4,3 % bei Delikten an Kindern gegen 0,4 % bei Diebstahl |
| **H2** | Der Überlapp der Delta-Läufe erzeugt ausschliesslich **Duplikate**, keine **Dubletten**. | Vergleich aller Attribute je Schlüssel | bestätigt |
| **H3** | Die Deliktschlüssel beider Städte lassen sich **vollständig** auf NIBRS abbilden. | Anwendung beider Crosswalks in `silver/crime_offense` | **teilweise falsifiziert**, siehe 8.5. Beide Städte sind **100 %** zugeordnet — aber nur **97,0 %** aller Fälle tragen ein echtes NIBRS-Delikt; 10'442 landen im Auffang `90Z`. Die Abdeckung stimmt, die Abbildung nicht |
| **H4** | Ein gepinntes Schema plus Auffangspalte fängt Schema-Drift **vollständig** auf. | Fingerabdruck über Feldtypen, Inhalt von `_extra` | bestätigt |
| **H5** | Auffällige Werte in den Verwaltungsschlüsseln sind **Artefakte**, keine echten Ausreisser. | Häufigkeitsanalyse plus Konsistenzregel | vorgeprüft |
| **H6** | Die Zusammenführung der drei Zeitachsen gelingt allein durch **Aggregation**; Imputation ist nicht nötig. | Granularitätsanalyse je Quelle | offen |
| **H7** | Unser räumlicher Join **reproduziert** die Tract-Zuordnung, die Detroit selbst mitliefert. | Übereinstimmungsquote | **falsifiziert**, siehe 8.4 |
| **H8** | Tract-Zellen mit auffällig hohen Fallzahlen sind echte **Ausreisser**, kein Noise. | Boxplot, Isolation Forest | offen |

**H2 und H5 sprechen die Begriffe des Moduls präzise an.** Ein *Duplikat* ist in
jedem Attribut identisch, eine *Dublette* meint dieselbe Sache mit abweichenden
Werten; *Noise* hat eine systematische Ursache, ein *Ausreisser* ist eine echte
Beobachtung. Diese Unterscheidungen lassen sich an den vorliegenden Daten mit
einem belegten Ergebnis zeigen statt mit einer Definition.

### 3.4 Qualitätsdimensionen als Massstab

FF2 braucht einen Massstab. Angelehnt an ISO 8000, jede Dimension mit einer
Kennzahl, die sich berechnen lässt:

| Dimension | Kennzahl |
| --- | --- |
| Vollständigkeit (Lauf) | geladene gegen erwartete Zeilen |
| Vollständigkeit (Feld) | Füllgrad je Pflichtspalte |
| Eindeutigkeit | Anteil doppelter Schlüssel nach Deduplikation |
| Gültigkeit | Anteil Werte im erlaubten Bereich |
| Konsistenz | Anteil Zeilen ohne Feldwiderspruch |
| Genauigkeit | Anteil verortbarer Fälle |
| Aktualität | Abstand des jüngsten Änderungszeitpunkts |

Der Verwendungszweck legt die Schwellen fest. Für eine Rate je Tract ist eine
Verortungsquote von 99,3 % gut — aber nur, solange die fehlenden 0,7 % nicht
systematisch verzerrt sind. Genau das prüft H1, und genau deshalb hängen die
beiden Ebenen aus 3.1 zusammen.

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

Gefordert ist der **Entwurf**. Drei Phasen sind gebaut, Transformation zu zwei
Dritteln, Serving ist entworfen und noch nicht gebaut — der Entwurf steht
in 5.2.

### 5.1 Die fünf Phasen

| Phase | Umsetzung | Beleg |
| --- | --- | --- |
| **Generation** | Fünf Quellsysteme: Socrata-API (Chicago), ArcGIS REST (Detroit), HTTPS-Dateien (TIGER, NOAA), JSON-API (ACS). Je Quelle dokumentiert: Änderungsverhalten, Schlüsselbedarf, Formate | Notebooks 01, 21, 22 |
| **Ingestion** | Vier Pipelines, alle Batch. Chicago inkrementell über ein Wasserzeichen mit 14 Tagen Rückgriff; Census als eingefrorene Vintage; NOAA als Vollschnappschuss im Wochenrhythmus mit bedingtem Abruf | `src/crime/*_pipeline/` |
| **Storage** | Dateibasierte Schichten, Parquet mit festem Schema, Hive-Partitionen, unveränderliche Läufe mit Manifest je Schicht | Kapitel 7 |
| **Transformation** | Bronze bewusst ohne Deutung. Silver deutet: Typen, Einheiten, Fehlwerte, Schlüssel. Zwei von drei Tabellen gebaut | Kapitel 8 |
| **Serving** | Option A (Analytik) entschieden, Gold entworfen und noch nicht gebaut | 5.2 |

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

**Gold behält deshalb das Korn** und wird statt dessen abfragbar gemacht: ein
Sternschema mit einer Faktentabelle je Delikt und vier kleinen Dimensionen.
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

Seit Gold gebaut ist, führt sie **neun Sichten**: die vier Silver-Tabellen und
die fünf des Sternschemas. Dazu war nichts zu tun — `discover()` sucht in
beiden Schichten und nimmt auf, was da ist.

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
ausschliesst. Und sie kostet das 150-fache an Platz.

**Eigene Abfragen und eigene Tabellen.** Die Datei ist eine echte Datenbank;
wer ein Zwischenergebnis behalten will, legt daneben `CREATE TABLE meins AS
SELECT …` an. Die Sichten bleiben Sichten. Zwei gleichzeitige Schreiber gehen
nicht — DuckDB kennt nur einen; bei zwei Personen mit je eigener Datei und
`ATTACH` ist auch das gelöst.

Messung und Methodik: [`notebooks/33_serving_evaluation.ipynb`](../notebooks/33_serving_evaluation.ipynb).


#### Wer konsumiert

| Konsument | Zugriff | Korn |
| --- | --- | --- |
| Dashboard (primär) | über Sichten in einer DuckDB-Datei | aggregiert |
| Ad-hoc-Auswertung im Team | SQL auf dieselben Sichten | aggregiert, bei Bedarf Silver |

Kein externer Dienst, keine API, keine Nutzerverwaltung. Das Serving endet an
der Auswertungsumgebung.

#### Was geliefert wird: fünf Gold-Tabellen

| Tabelle | Korn | Zeilen |
| --- | --- | ---: |
| `fact_offense` | **eine Tat** | 344'607 |
| `dim_tract` | ein Census Tract, mit **Stadtzuordnung** und Einwohnerzahl | 6'282 |
| `dim_offense` | ein NIBRS-Delikt | 85 |
| `dim_date` | ein Kalendertag | 366 |
| `dim_city_day` | Stadt und Tag, mit dem Wetter | 732 |

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
beiden Städten**, und diese 23 decken **99,5 %** der Fälle (auf Tatkorn, siehe
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

#### Das Korn: Detroits Zeilen sind Anklagen, Chicagos sind Delikte

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
Zuordnung über Text. Das trifft auf **99,98 %** der Gruppen zu. Für die
übrigen 19 entscheidet die **Hierarchie des MICR-Handbuchs**, in der 1 Mord ist
und 16 Sachbeschädigung: Es gilt die schwerste Anklage.

| | Detroit |
| --- | ---: |
| Zeilen in Silver (eine Anklage) | 88'685 |
| davon zählend (**eine Tat**) | **85'335** |
| Unterschied | −3'350 = **−3,8 %** |

Gold nimmt nur die zählenden. Wer die Anklagen braucht — *„wie oft wurde
zusätzlich Sachbeschädigung angezeigt"* — findet sie vollständig in
`silver/crime_offense`, mit `counts` und `counts_reason` je Zeile.

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

**Der Preis ist gemessen:** 1,9 % der Delikte liegen in Tracts, die keiner der
beiden Städte zugeordnet sind — Fälle knapp jenseits der Stadtgrenze. Zähler
und Nenner folgen derselben Grenze, der Rand verzerrt also beide Seiten
gleichsinnig.

Damit ist die Frage beantwortet, die das Projekt von Anfang an stellen wollte:

| | Delikte | Einwohner | je 1'000 |
| --- | ---: | ---: | ---: |
| Chicago | 251'516 | 2'661'953 | **94,5** |
| Detroit | 84'648 | 638'635 | **132,5** |

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

- **Keine zeilenweisen Falldaten.** Gold ist aggregiert; wer einzelne Fälle
  braucht, geht auf Silver.
- **Keine Merkmalstabelle je Tract für Modelle.** Das wäre Option B, und die ist
  nicht gewählt.

### 5.3 Unterströmungen

| Unterströmung | Umsetzung | Lücke |
| --- | --- | --- |
| **Security** | Schlüssel nur in `.env`, nie in einem Manifest oder einer abgelegten URL; ein Test prüft das. `.env` und `data/` aus der Versionierung ausgeschlossen, die Historie enthält keinen committeten Schlüssel | Datenschutzabschnitt schriftlich |
| **Data Management** | Manifest je Lauf und Schicht, Herkunft über `derived_from` und `run_id`, unveränderliche Läufe, Schema-Fingerabdruck gegen Drift, `_extra` gegen Datenverlust | Feldkatalog |
| **DataOps** | 621 Tests, alle ohne Netz und ohne Schlüssel; Schreiben über `.part` und atomares Umbenennen, sodass ein abgebrochener Lauf keinen halben Stand hinterlässt | keine CI, keine Alarmierung |
| **Data Architecture** | Vier Schichten, gepinnte Schemata, Trennung von Beweis (`raw`) und Ableitung (`bronze`), sprechende Partitionsschlüssel | Architekturdiagramm |
| **Orchestration** | – | **bewusst offen**: die Pipelines werden von Hand in der richtigen Reihenfolge gestartet |
| **Software Engineering** | Modulare Pakete je Quelle, Typannotationen, Docstrings die das Warum festhalten, Fehlerbehandlung mit Wiederholungen bei Drosselung und Serverfehlern | – |

**Zur Orchestrierung.** Bei fünf Quellen und vier Batch-Pipelines wären Airflow
oder Prefect Aufwand ohne Erkenntnisgewinn. Angemessen wäre ein `Makefile` oder
ein Skript, das die Läufe in der richtigen Reihenfolge aufruft und protokolliert
— die Reihenfolge ist real, weil `silver/tract` beide Census-Quellen braucht und
`crime_offense` zusätzlich `tract`. Dass wir es nicht gebaut haben, ist eine
Abwägung und keine Auslassung; genannt gehört sie trotzdem.

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
korrigieren ältere. Chicago lädt deshalb inkrementell über ein Wasserzeichen auf
`updated_on`, mit **14 Tagen bewusstem Überlapp** — Korrekturen an älteren
Fällen werden so erfasst. Der Preis sind Duplikate, die Silver auflöst; H2
prüft, dass es tatsächlich Duplikate und keine Dubletten sind.

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

**Der stärkste Befund ist nicht die Geschwindigkeit.** Detroits NDJSON übernimmt
heute zwei Rollen gleichzeitig: Beweisstück und abgeleitete Tabelle. Getrennt
nach der Konvention der anderen vier Quellen kostet die zusätzliche Schicht
nichts — sie spart:

```text
vorher       Bronze NDJSON             89,4 MB
getrennt     Raw    NDJSON + gzip      10,9 MB
             Bronze Parquet snappy      6,5 MB
             zusammen                   17,4 MB   → 81 % weniger
```

Messung und Methodik: [`notebooks/31_storage_evaluation.ipynb`](../notebooks/31_storage_evaluation.ipynb).
Die Messung läuft mit warmem Betriebssystem-Cache und **unterschätzt damit
Parquet**, weil der Plattenzugriff wegfällt.

**Was daraus wurde.** Detroits Ingestion schreibt seit dem 11.9. Parquet, in
Laufverzeichnissen mit Manifest und Prüfsumme, und bringt einen eigenen
Datenvertrag mit: eingefrorenes Schema aus den Layer-Metadaten, `_feature_json`
als verlustfreie Nutzlast, `_extra` für Typdrift. Vier der fünf Quellen liegen
damit auf derselben Konvention. Die Silver-Schicht liest beide Formate — ein
Bestand von vor der Umstellung wird nicht unlesbar, das neue Layout hat aber
Vorrang.

### 7.4 Implementierung

```text
data/
├── raw/     unverändert, Byte für Byte wie ausgeliefert
├── bronze/  daraus abgeleitetes Parquet mit gepinntem Schema
├── silver/  gedeutet: Typen, Einheiten, Fehlwerte, harmonisierte Schlüssel
└── gold/    Sternschema: fact_offense und vier Dimensionen
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

---

## 8 · Transformation Teil 1: Bereinigung und Qualität

### 8.1 Was Bronze bewusst nicht tut

Bronze deutet nicht. Werte behalten den Typ, den die Quelle liefert: Chicagos
`arrest` bleibt ein JSON-Boolean, NOAAs `"  214"` bleibt Text mit
Leerzeichen, der ACS-Fehlwert `-666666666` bleibt stehen. Alles Unerwartete
landet in einer Auffangspalte `_extra`, statt verworfen zu werden.

Das ist keine Bequemlichkeit, sondern die Voraussetzung dafür, dass Bronze
jederzeit neu deutbar ist. Beim Chicago-Schemafehler liess sich Bronze neu
ableiten, ohne die API erneut zu befragen.

### 8.2 Was Silver deutet

Die Quellen haben **drei verschiedene Körner**. Sie in eine Tabelle zu zwingen
würde Zeilen vervielfachen — ein Wetterwert an jedem Delikt derselben Stadt und
desselben Tages — oder Information wegwerfen. Deshalb drei Tabellen:

| Tabelle | Eine Zeile ist | Stand |
| --- | --- | --- |
| `tract` | ein Census Tract | **gebaut**, 6'282 Zeilen |
| `place` | ein Ort (Stadtgrenze) | **gebaut**, 2'206 Zeilen |
| `weather_day` | eine Stadt an einem Tag | **gebaut**, 55'449 Zeilen |
| `crime_offense` | eine **Anklage**; je Tat zählt eine (5.2) | **gebaut**, 347'957 Zeilen |

`tract` verbindet TIGER-Geometrie mit ACS-Attributen. Gedeutet wird: Text zu
Zahlen, `-666666666` zu `NULL`, die Armutsquote abgeleitet — und bei Tracts ohne
Einwohner `NULL` statt einer Division durch null, wobei die absoluten Zahlen
erhalten bleiben.

`weather_day` löst die Einheiten auf. GHCN-Daily führt Temperatur und
Niederschlag in Zehnteln, Schneefall dagegen schon in Millimetern; an echten
Rekorden plausibilisiert. Ein leeres Feld wird `NULL` und **nicht** `0` — bei
Niederschlag der entscheidende Unterschied. Das Messflag `T` für Spurenmengen
bekommt eine eigene Spalte, weil `0` mit `T` nicht „trocken" heisst.

`crime_offense` ist die Tabelle, die den Vergleich trägt — 347'957 Zeilen,
259'272 aus Chicago und 88'685 aus Detroit. Detroits Zeilen sind Anklagen; je
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

**Alle drei Tabellen benennen Auffälligkeiten statt sie zu entfernen.** `tract`
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

Nebenbei: `case_number` ist **kein** Schlüssel. 259'272 Delikte verteilen sich
auf 259'243 Fallnummern — ein Fall kann mehrere Straftaten umfassen. Verknüpft
wird über `id`.

### 8.4 Ein falsifizierter Befund: H7

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

**83 % ist keine Reproduktion. H7 ist in dieser Form falsifiziert.** Die
naheliegenden Erklärungen greifen nicht: Alle 275 von Detroit genannten Tracts
existieren in TIGER 2024, es ist also kein Vintage-Problem; der Unterschied
zwischen NAD83 und WGS84 liegt unter einem Meter; und 337 Fälle in einem anderen
County sind keine Grenzungenauigkeit.

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

Dass eine Hypothese fällt, ist kein schlechteres Ergebnis als eine bestätigte:
Sie zeigt, dass geprüft und nicht angenommen wurde.

### 8.5 Ein zweiter, teilweise falsifizierter Befund: H3

H3 nahm an, die Deliktschlüssel beider Städte liessen sich **vollständig** auf
NIBRS abbilden. Seit `silver/crime_offense` beide Crosswalks auf die Falldaten
anwendet, ist das gemessen — und die Antwort hängt daran, was „vollständig"
heissen soll.

Gemessen auf Tatkorn über die 344'607 Delikte des Jahrgangs 2024:

| | Chicago | Detroit | zusammen |
| --- | ---: | ---: | ---: |
| Delikte (Tatkorn) | 259'272 | 85'335 | 344'607 |
| Quellcode im Crosswalk bekannt | **100 %** | **100 %** | **100 %** |
| davon Auffang `90Z` | 7'695 | 2'747 | 10'442 |
| **mit einem echten NIBRS-Delikt** | **97,0 %** | **96,8 %** | **97,0 %** |

**Abdeckung ja, Abbildung nein.** Kein Chicago-Code fällt stillschweigend
heraus, das war die eigentliche Sorge. Aber 10'442 Fälle tragen ein Delikt, das
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
Widerspruch, sondern die Körnung der Quelle — eine Zeile ist eine Anklage, nicht
der Vorfall.

**Was die Tabelle über die Hypothese hinaus zeigt.** Zum ersten Mal lassen sich
beide Städte nebeneinanderstellen, ohne dass eine Zahl etwas anderes bedeutet
als die daneben:

| NIBRS | Delikt | Chicago | Detroit |
| --- | --- | ---: | ---: |
| `13B` | Simple Assault | 38'857 | 15'889 |
| `23H` | All Other Larceny | 38'597 | 4'171 |
| `290` | Destruction/Damage/Vandalism | 28'596 | 11'786 |
| `240` | Motor Vehicle Theft | 22'101 | 8'511 |
| `13C` | Intimidation | 19'338 | 1'235 |
| `13A` | Aggravated Assault | 16'088 | 8'073 |

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
oder zwei Stunden auseinander. Ein Vergleich nach Tageszeit, wie ihn H6
braucht, wäre ohne Umrechnung wertlos gewesen.

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
  unterscheidet sich: 0,70 % in Chicago gegen 0,29 % in Detroit. Eine Verzerrung
  wirkt damit ungleich auf die beiden Städte.

**Zu den Quellen**

- **Der ACS ist eine 5-Jahres-Schätzung**, hat also keine Zeitachse im Sinne der
  Falldaten. Der Nenner ist über den Zeitraum konstant.
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

- **Keine Orchestrierung.** Bewusst, siehe Kapitel 5.
- **Der räumliche Join ist nicht unabhängig validiert**, weil die einzige
  verfügbare Referenz sich als widersprüchlich erwiesen hat (8.4).
- **Ein Notebook zur Detroit-Quelle fehlt.** Für Chicago, Census und Wetter
  existiert je eines.

---

## 10 · Reproduktion

```bash
python3 -m venv .venv && source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest                       # erwartet 621 bestandene Tests
```

Daten laden — jede Pipeline schreibt einen neuen, unveränderlichen Lauf:

```bash
python -m chicago_pipeline.download_chicago --year 2024
python -m detroit_pipeline.extract_detroit --year 2024
python -m census_pipeline.download_tiger
python -m census_pipeline.download_acs   # braucht CENSUS_API_KEY in .env
python -m weather_pipeline.download_noaa
```

Silver ableiten:

```bash
python -m silver_pipeline.build_tract
python -m silver_pipeline.build_weather_day
```

**Wichtig zur Reproduzierbarkeit.** Die Falldaten wachsen laufend, ein Lauf von
heute liefert andere Zeilen als einer von letzter Woche. Byte-identisch
reproduzierbar sind nur die eingefrorenen Quellen TIGER und ACS. Für einen
gemeinsamen Auswertungsstand ist deshalb festzulegen, **welche Läufe** gelten —
die Zahlen in diesem Dokument beziehen sich auf die in 8.3 genannten
Chicago-Läufe und die zugehörigen Läufe der übrigen Quellen.

`data/` ist vollständig aus der Versionierung ausgeschlossen.

---

## 11 · Wo was liegt

| Was | Wo |
| --- | --- |
| Ingestion, vier Pipelines | `src/crime/{chicago,detroit,census,weather}_pipeline/` |
| Silver-Aufbau | `src/crime/silver_pipeline/` |
| **Auswertungsumgebung** | `src/crime/serving/build_analysis_db.py` → `data/serving/analyse.duckdb` |
| **Der Städtevergleich selbst** | `src/crime/silver_pipeline/build_crime_offense.py` → `data/silver/dataset=crime_offense/` |
| Tests | `tests/`, nach Pipeline gegliedert |
| Quelle Chicago erklärt | [`notebooks/01_chicago_source.ipynb`](../notebooks/01_chicago_source.ipynb) |
| Chicago-Ingestion vorgeführt | [`notebooks/02_chicago_bronze_ingestion.ipynb`](../notebooks/02_chicago_bronze_ingestion.ipynb) |
| Datenqualität Chicago | [`notebooks/03_chicago_data_quality.ipynb`](../notebooks/03_chicago_data_quality.ipynb) |
| Quelle Detroit erklärt | [`notebooks/11_detroit_source.ipynb`](../notebooks/11_detroit_source.ipynb) |
| Detroit-Ingestion vorgeführt | [`notebooks/12_detroit_bronze_ingestion.ipynb`](../notebooks/12_detroit_bronze_ingestion.ipynb) |
| Quelle Census erklärt | [`notebooks/21_census_source.ipynb`](../notebooks/21_census_source.ipynb) |
| Quelle Wetter erklärt | [`notebooks/22_weather_source.ipynb`](../notebooks/22_weather_source.ipynb) |
| Storage-Messung | [`notebooks/31_storage_evaluation.ipynb`](../notebooks/31_storage_evaluation.ipynb) |
| Serving-Messung: Sichten oder Kopie | [`notebooks/33_serving_evaluation.ipynb`](../notebooks/33_serving_evaluation.ipynb) |
| Referenzquelle NIBRS, Mapping-Herkunft | [`notebooks/32_nibrs_source.ipynb`](../notebooks/32_nibrs_source.ipynb) |
| Gold-Sternschema, Stadtzuordnung | [`notebooks/34_gold_sternschema.ipynb`](../notebooks/34_gold_sternschema.ipynb) |
| Technische Entscheide | [`projektabsprache.md`](projektabsprache.md) |
| Anforderungen gegen Stand | [`leistungsnachweise.md`](leistungsnachweise.md) |
| Detroit-Pipeline im Detail | [`DETROIT_PIPELINE_ANLEITUNG.md`](DETROIT_PIPELINE_ANLEITUNG.md) |
| **NIBRS-Codeliste, amtlich** | `config/nibrs_offense_codes_2025.csv` — 81 Codes aus Anhang A von [`nibrs_technical_specification_2025.pdf`](nibrs_technical_specification_2025.pdf) |
| IUCR nach NIBRS (Chicago) | `config/iucr_nibrs_mapping.csv`, erzeugt von [`tools/build_iucr_nibrs_mapping.py`](../tools/build_iucr_nibrs_mapping.py); Katalog vom [Datenportal der Stadt](https://data.cityofchicago.org/resource/c7ck-438e.json) |
| MICR nach NIBRS (Detroit) | `config/micr_nibrs_mapping.csv`, erweitert von [`tools/extend_micr_arrest_charges.py`](../tools/extend_micr_arrest_charges.py); Quellen [`micr_manual_1110_2024.pdf`](micr_manual_1110_2024.pdf) und [`micr_appendix_f_2009.pdf`](micr_appendix_f_2009.pdf) |
| Codetabelle Illinois State Police | [`isp_nibrs_code_table_2026.xlsx`](isp_nibrs_code_table_2026.xlsx) — nach ILCS-Statut geschlüsselt, **nicht** als Crosswalk verwendbar, siehe 8.5 |
| **Amtliche Deliktkategorien** | `config/nibrs_offense_categories_2025.csv`, gelesen von [`tools/build_nibrs_categories.py`](../tools/build_nibrs_categories.py) aus [`nibrs-user-manual-2025-0-062625.pdf`](nibrs-user-manual-2025-0-062625.pdf) — 28 + 10 Kategorien |
| Die vier zurückgezogenen Codes | [`NIBRS_Offense_Codes.pdf`](NIBRS_Offense_Codes.pdf), Fassung 2011 — überholt, aber der einzige Beleg für `90A`, `90E`, `90H`, `90I` |
| Zweite Abschrift der Codeliste | [`illinois_nibrs_iepd_2023.xlsx`](illinois_nibrs_iepd_2023.xlsx), Blatt `OffenseCode` — Illinois' eigene Abschrift derselben FBI-Liste; belegt alle 81 Bezeichnungen statt zehn Stichproben |

**Keine dieser drei Konfigurationsdateien wird von Hand gepflegt** — jede wird
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

- **Entscheid über Forschungsfragen und Hypothesen** (Kapitel 3) — Gold ist
  bewusst so gebaut, dass er nichts daran ändert: Das Korn bleibt, und jede
  Frage ist ein Filter darauf (5.2)
- **Ein Notebook, das den Vergleich über alle Hypothesen rechnet.** Die Rate je
  Einwohner steht seit Gold zur Verfügung (5.2) und ist in Notebook 34
  gerechnet; ein Notebook, das den ganzen Vergleich daraus aufbaut, fehlt noch
- **Ein Notebook, das die Hypothesen rechnet** — die Zahlen zu H1, H2 und H5
  liegen heute in Notebook 03, H7 in 8.4; ein eigenes Notebook fehlt
- **Ein Notebook zur Datenqualität Detroits**, als Gegenstück zu Notebook 03
  für Chicago — Notebook 11 dokumentiert die Quelle, nicht die Qualität der
  geladenen Daten
