# Leistungsnachweise 1 und 2: Anforderungen, Stand, Lücken

Dieses Dokument stellt die Anforderungen der beiden Leistungsnachweise dem
tatsächlichen Projektstand gegenüber und benennt, was bis zur Abgabe fehlt.

Es ergänzt [`projektabsprache.md`](projektabsprache.md): Dort stehen die
technischen Entscheide (Bronze-Konventionen, Werkzeuge, Zusammenarbeit), hier
die Abgabe-Sicht. Die **Abgabe selbst** entsteht als eigenes **Word-Dokument**;
geschrieben wird es aus [`ln1_konzept.md`](../ln1_konzept.md). Weder jenes noch
dieses ist damit Teil der Abgabe — beide sind Arbeitsgrundlage. Wo ein Entscheid aus der Absprache eine Anforderung erfüllt,
ist er verlinkt.

Alle Zahlen sind am 8. September 2026 aus dem Repository erhoben. Die
Entscheide der Sitzung vom 8.9.2026 sind in Abschnitt 9 abgeglichen; die
technischen stehen in [`projektabsprache.md`](projektabsprache.md).

---

## 1 · LN1 auf einen Blick

| Anforderung | Stand | Was fehlt |
| --- | --- | --- |
| **Problemstellung, Ausgangslage** | ● geschrieben | [`ln1_konzept.md`](../ln1_konzept.md) Kapitel 2 |
| **Forschungsfragen, Hypothesen** | ◐ Vorschlag steht, vier bereits vorgeprüft | Auswahl und Formulierung entscheiden → Abschnitt 2.2 / 2.3 |
| **Vorgehen und Methoden** | ◐ implizit im Code | Methodenteil ausformulieren → Abschnitt 2.4 |
| **Entwurf DE-Lebenszyklus** | ● benannt | Abschnitt 3; ausführlich in [`ln1_konzept.md`](../ln1_konzept.md) Kapitel 5 |
| **Ingestion: Quellen, Beschaffung** | ● fertig | fünf Quellen, je ein Quellnotebook |
| **Storage: Evaluation, Wahl, Implementierung** | ● fertig | gemessen in Notebook 31 (NDJSON gegen Parquet), verschriftlicht in [`ln1_konzept.md`](../ln1_konzept.md) Kapitel 7 |
| **Transformation 1: Analyse, Hypothesentest** | ◐ Qualität beider Städte fertig | der eigentliche Hypothesentest → Abschnitt 5 |
| **Initiale Datenbereinigung** | ● fertig | vier Silver-Tabellen, `crime_offense` mit 348'311 Zeilen |
| **Beantwortung der Forschungsfragen** | ○ | folgt aus allem davor |

● fertig ◐ teilweise ○ offen

**Die gute Nachricht:** Ingestion und Storage — die beiden praktisch
aufwendigsten Blöcke — stehen. 1'496 Tests, fünf Quellen in vier Pipelines,
nachgewiesene Vollständigkeit. Und weil die Hypothesen Fragen des Data Engineering sind
(Abschnitt 2.0), sind fünf davon durch die bisherige Arbeit **bereits
gemessen**: Wir haben Befunde, bevor wir die Hypothesen formuliert haben — und
mit H7 auch eine falsifizierte.

**Die Baustelle:** Der konzeptionelle Teil steht inzwischen in
[`ln1_konzept.md`](../ln1_konzept.md), Silver und Gold sind gebaut. Offen ist die
Auswahl und Formulierung der Hypothesen. Ohne formulierte Hypothesen gibt es
keinen ausweisbaren Hypothesentest, auch wenn die Messungen längst vorliegen.

---

## 2 · Konzeptionalisierung

### 2.0 Zwei Ebenen von Fragen — und welche geprüft wird

Ein Missverständnis, das früh geklärt gehört: Die Forschungsfragen und
Hypothesen dieses Leistungsnachweises sind **Fragen des Data Engineering**,
nicht der Kriminologie. Bewertet wird, ob die Daten für ihren Zweck taugen und
wie das nachgewiesen wird — nicht, ob Chicago oder Detroit gefährlicher ist.

Das Modul Transformation stützt diese Lesart: Es behandelt Kompatibilität,
Integration, Datenqualität, Bereinigung, Ausreisser — und definiert
Datenqualität ausdrücklich als **Funktion des Verwendungszwecks** („ein
vereinbartes Niveau der Datenqualität ermöglicht es den richtigen Personen, die
richtigen Entscheidungen zu treffen", ISO-8000-Grundsätze).

Genau daraus folgt aber, dass wir **beide** Ebenen brauchen:

| Ebene | Rolle | Beispiel |
| --- | --- | --- |
| **Anwendungsebene** | legt fest, *wofür* die Daten taugen müssen, und liefert damit den Massstab für „gut genug" | „Fallzahlen je Tract und NIBRS-Kategorie, bezogen auf die Einwohnerzahl, für einen Vergleich beider Städte" |
| **Data-Engineering-Ebene** | ist Gegenstand der Forschungsfragen und Hypothesen — hier wird gemessen und getestet | „Sind fehlende Koordinaten zufällig verteilt?" |

Die Anwendungsebene ist also **Rahmen**, nicht Prüfgegenstand: Ohne sie gibt es
keinen Qualitätsmassstab, mit ihr allein aber keinen Hypothesentest im Sinne des
Moduls. In der Präsentation gehört sie in die Problemstellung, nicht in die
Hypothesen.

### 2.1 Problemstellung und Ausgangslage (Entwurf)

Vorschlag als Ausgangstext, gemeinsam zu schärfen:

> Kriminalitätsstatistiken einzelner US-Städte sind öffentlich und detailliert
> verfügbar, aber untereinander kaum vergleichbar. Jede Stadt verwendet eigene
> Deliktschlüssel (Chicago: IUCR, Detroit: eigene Kategorien), eigene
> Raumeinheiten (Community Areas, Precincts) und eigene Erfassungssysteme.
> Absolute Fallzahlen sagen zudem wenig aus, solange die Bevölkerung des
> betrachteten Gebiets unbekannt ist.
>
> Chicago und Detroit sind für einen Vergleich besonders interessant: zwei
> Städte des Mittleren Westens mit sehr unterschiedlicher wirtschaftlicher
> Entwicklung — Chicago als wachsende Metropole, Detroit nach jahrzehntelangem
> Bevölkerungsrückgang und Insolvenz 2013.
>
> Das Projekt baut die Datengrundlage, die einen belastbaren Vergleich
> überhaupt erst erlaubt: harmonisierte Delikte über den nationalen
> NIBRS-Standard, eine gemeinsame Raumeinheit über Census Tracts und
> Einwohnerzahlen als Nenner für Raten.

### 2.2 Forschungsfragen (Vorschlag)

Drei Fragen entlang der Modulinhalte — Integration, Bewertung, Bereinigung:

| | Frage | Modulbezug |
| --- | --- | --- |
| **FF1** | Unter welchen Bedingungen lassen sich zwei unabhängig erhobene, unterschiedlich kodierte kommunale Kriminalitätsdatensätze so integrieren, dass ein valider Vergleich möglich wird? | Kompatibilität, Integration |
| **FF2** | Welches Qualitätsniveau erreichen die fünf Quellen, gemessen an definierten Dimensionen — und genügt es dem festgelegten Verwendungszweck? | Datenqualität, Bewertung |
| **FF3** | Welche Bereinigungsschritte sind erforderlich, und wie stark verändern sie das Ergebnis? | Datenbereinigung 1 und 2 |

FF3 ist die interessanteste der drei: Sie zwingt dazu, die Wirkung jeder
Bereinigung zu messen statt sie nur durchzuführen — etwa den Unterschied
zwischen „Fälle ohne Koordinaten löschen" und „markieren".

### 2.3 Hypothesen (Vorschlag)

Alle falsifizierbar, alle mit einem Verfahren aus dem Modul prüfbar, alle mit
unseren Daten tatsächlich durchführbar. **Fünf sind bereits gemessen** — vier
vorgeprüft oder bestätigt, eine falsifiziert. Die Zahlen stammen aus den
Notebooks, den Läufen im Repository und der Silver-Tabelle `tract`.

| | Hypothese | Verfahren | Stand |
| --- | --- | --- | --- |
| **H1** | Fehlende Koordinaten treten **nicht zufällig** auf, sondern hängen vom Delikttyp ab (MNAR statt MCAR). | Chi-Quadrat-Unabhängigkeitstest | vorgeprüft: 4,3 % bei Delikten an Kindern gegen 0,4 % bei Diebstahl |
| **H2** | Der Überlapp der Delta-Läufe erzeugt ausschliesslich **Duplikate** (in allen Attributen identisch), keine **Dubletten**. | Vergleich aller Attribute je Schlüssel | **bestätigt**: 42 von 42 mehrfachen `id` in jedem Attribut identisch |
| **H3** | Die Deliktschlüssel beider Städte lassen sich **vollständig** auf NIBRS abbilden. | Abgleich gegen die Mapping-Tabelle | Chicago bestätigt (0 von 259'625 ohne Zuordnung), Detroit offen |
| **H4** | Ein gepinntes Schema plus Auffangspalte fängt Schema-Drift **vollständig** auf, ohne Datenverlust. | Fingerabdruck über Feldtypen, Inhalt von `_extra` | bestätigt: Chicago driftfrei, TIGER fängt `GEOIDFQ` auf |
| **H5** | Auffällige Werte in den Verwaltungsschlüsseln sind **Artefakte** (systematische Erfassungsfehler), keine echten Ausreisser. | Häufigkeitsanalyse plus feldübergreifende Konsistenzregel | vorgeprüft: District `031`, 13 Fälle, deren `beat` auf 016/024 zeigt |
| **H6** | Die Zusammenführung der drei Zeitachsen gelingt allein durch **Aggregation**; **Imputation** ist nicht nötig. | Granularitätsanalyse je Quelle | offen — ACS ist eine 5-Jahres-Schätzung und dürfte die Ausnahme sein |
| **H7** | Unser räumlicher Join **reproduziert** die Tract-Zuordnung, die Detroit selbst mitliefert. | Übereinstimmungsquote gegen `census_block_2020_geoid` | **falsifiziert**: 83,35 % von 88'278 Zeilen; Ursache liegt in Detroits Daten |
| **H8** | Tract-Zellen mit auffällig hohen Fallzahlen sind echte **Ausreisser** (Hotspots), kein **Noise**. | Tukey-Boxplot univariat, Isolation Forest multivariat | offen |

**H7 sah wie ein Glücksfall aus und ist gemessen worden — mit einem anderen
Ergebnis als erwartet.** Die Ausgangslage: Detroit liefert in 99,5 % der Zeilen
eine 15-stellige `census_block_2020_geoid`, deren erste elf Stellen die
Tract-GEOID sind, 275 Tracts. Damit schien eine **unabhängige Referenz** für
unseren selbst gerechneten Punkt-in-Polygon-Join vorzuliegen; Chicago liefert
nichts Vergleichbares.

Der Vergleich gegen `silver/tract` (8.9.2026, DuckDB mit `spatial`):

| | |
| --- | --- |
| vergleichbare Zeilen | 88'278 |
| von uns nicht verortet | 0 |
| **übereinstimmend** | **73'578 — 83,35 %** |
| abweichend | 14'700, davon 337 in einem anderen County |

**83 % ist keine Reproduktion, H7 ist in dieser Form falsifiziert.** Die
naheliegenden Erklärungen greifen nicht:

- **Kein Vintage-Problem.** Alle 275 von Detroit genannten Tracts existieren in
  TIGER 2024.
- **Keine Frage des Koordinatensystems.** Der Unterschied zwischen NAD83 und
  WGS84 liegt bei ein bis zwei Metern und erklärt keine 17 %.
- **Keine Grenzungenauigkeit.** 337 Fälle landen in einem anderen *County*.

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
> **Der Schluss auf H7 gehört damit nochmals angesehen** — die Bewertung bleibt
> Artans.


Der Join selbst ist nachweislich sauber: 88'278 Quellzeilen ergeben 88'278
Zeilen nach dem Join, Tracts überlappen also nicht und jeder Punkt liegt in
genau einem. Daraus folgt zwingend, dass der Punkt dort, wo Detroit ein anderes
Tract nennt, **nicht in Detroits eigenem Tract liegt**. Der Widerspruch besteht
zwischen Detroits Koordinaten und Detroits `census_block_2020_geoid`, nicht
zwischen Detroit und uns.

**Die Ursache ist offen.** Plausibel wäre, dass eine der beiden Angaben aus
Datenschutzgründen versetzt veröffentlicht wird, wie es kommunale
Polizeidatensätze häufig tun — das ist eine Vermutung und keine Messung. Als
Referenz zur Validierung unseres Joins taugt Detroits GEOID jedenfalls nicht,
solange das nicht geklärt ist.

**Ob H7 in dieser Form verwendet wird, ist noch offen** und hängt an der
Hypothesen-Auswahl weiter unten. Für den Leistungsnachweis ist eine
falsifizierte Hypothese allerdings nicht das schlechtere Ergebnis: Sie zeigt,
dass geprüft und nicht bestätigt wurde. Fällt die Wahl darauf, gehört das
Ergebnis in die Limitationen (Abschnitt 10.3) — und die Frage nach der Ursache
ist der Punkt, an dem im Kolloquium nachgefragt wird (Abschnitt 10.4).

**H2 und H5 sprechen die Begriffe des Moduls präzise an.** Ein *Duplikat* ist in
jedem Attribut identisch, eine *Dublette* meint dieselbe Sache mit abweichenden
Werten; *Noise* hat eine systematische Ursache (Artefakt) oder stammt aus
fehlerhafter Erfassung, ein *Ausreisser* ist eine echte Beobachtung. Genau diese
Unterscheidungen lassen sich an unseren Daten zeigen — mit einem belegten
Ergebnis statt einer Definition von der Folie.

**Zur Auswahl:** H1 bis H5 sind Pflicht, sie decken fehlende Daten, Duplikate,
Kompatibilität, Schema und Noise ab. H6 bis H8 sind Kür und passen zeitlich eher
in LN2.

`Entscheid Forschungsfragen: ______________________________`

`Entscheid Hypothesen: ____________________________________`

### 2.3.1 Qualitätsdimensionen, an denen wir messen

FF2 braucht einen Massstab. Vorschlag, angelehnt an ISO 8000 — jede Dimension
mit einer Kennzahl, die sich tatsächlich berechnen lässt:

| Dimension | Kennzahl | Stand Chicago |
| --- | --- | --- |
| Vollständigkeit (Lauf) | geladene gegen erwartete Zeilen | 259'272 = 259'272 |
| Vollständigkeit (Feld) | Füllgrad je Pflichtspalte | 100 % |
| Eindeutigkeit | Anteil doppelter Schlüssel nach Dedup | 0 % |
| Gültigkeit | Anteil Werte im erlaubten Bereich | 100 % (Jahr, Koordinaten, `community_area`) |
| Konsistenz | Anteil Zeilen ohne Feldwiderspruch | 99,993 % (17 von 259'625) |
| Genauigkeit | Anteil verortbarer Fälle | 99,19 % |
| Aktualität | Abstand des jüngsten `updated_on` | im Manifest |

Der Verwendungszweck legt die Schwellen fest: Für eine Rate je Tract ist eine
Verortungsquote von 99,19 % gut — aber nur, solange die fehlenden 0,81 % nicht
systematisch verzerrt sind. Genau das prüft H1, und genau deshalb hängen die
beiden Ebenen aus Abschnitt 2.0 zusammen.

### 2.3.2 Was bei einer inhaltlichen Auswertung dazugehört

Falls ihr **zusätzlich** inhaltlich auswertet (für Gold oder für LN2 Option B),
gehören diese Einschränkungen in jede Ergebnisdarstellung. Sie sind keine
Hypothesen, sondern Methodenkritik:

- **Ökologischer Fehlschluss.** Ein Zusammenhang auf Tract-Ebene erlaubt keine
  Aussage über einzelne Personen.
- **Tatort ≠ Wohnort.** Ein Innenstadt-Tract mit wenigen Einwohnern und vielen
  Pendlern bekommt eine überhöhte Rate.
- **Erfassung ≠ Kriminalität.** Gemessen wird angezeigte und erfasste
  Kriminalität, nicht Kriminalität.
- **Ungleiche Datenlücken.** In Wayne County fehlt bei 9,6 % der Tracts der
  Einkommenswert und 6,4 % haben keine Einwohner; in Cook County sind es 1,7 %
  und 0,3 %. Auch die Geo-Lücke ist ungleich: 0,81 % in Chicago gegen 0,29 % in
  Detroit. Die Verzerrung ist also **nicht symmetrisch** zwischen den Städten.

### 2.4 Vorgehen und Methoden

Vorschlag für die Gliederung:

1. **Vorgehensmodell** — Data-Engineering-Lebenszyklus nach Reis/Housley als
   Ordnungsrahmen, Schichtenarchitektur raw → bronze → silver → gold
2. **Datenbeschaffung** — vier öffentliche Quellen, jede mit eigenem
   Vollständigkeitsnachweis statt blossem Vertrauen
3. **Harmonisierung** — NIBRS als gemeinsame Deliktsprache, Census Tract als
   gemeinsame Raumeinheit
4. **Qualitätssicherung** — Prüfung je Quelle vor der Auswertung, automatisierte
   Tests, unveränderliche Läufe mit Manifest
5. **Auswertungsmethoden** — deskriptive Statistik, Rangkorrelation, Regression,
   Konzentrationsmasse

### 2.5 Was die Entscheide vom 8.9.2026 für Fragen und Hypothesen bedeuten

Der Scope-Entscheid ist **Variante D** ([Absprache 2.1](projektabsprache.md)):
deskriptiver Vergleich *plus* sozioökonomischer Zusammenhang *plus*
Wettereinfluss. Das ist die umfangreichste der vier Varianten. Die Begründung im
Entscheid ist pragmatisch — „ein Grossteil der Daten ist schon heruntergeladen,
eine Integration sollte nicht mehr so aufwändig sein" —, und für die Ingestion
trifft das zu: alle fünf Quellen liegen in Bronze.

Für Fragen und Hypothesen folgt daraus:

| | Wirkung von Variante D |
| --- | --- |
| **FF1** Integration | unverändert. Die Harmonisierung war ohnehin der Kern |
| **FF2** Qualitätsniveau | betrifft jetzt **fünf** Quellen statt vier. NOAA bringt eigene Dimensionen mit: vier Tage Nachlauf, Belegung der Messgrössen erst ab 1958, Flag-Spalten mit je Station verschiedener Feldzahl (siehe Notebook 22) |
| **FF3** Bereinigung | gewinnt einen Fall dazu: Werte in Zehnteln als Text, leere Felder gegen `0` bei Niederschlag, Spurenmengen mit Messflag `T` |
| **H6** drei Zeitachsen | wird von Kür zu **Pflicht**. Mit Wetter im Scope sind es tatsächlich drei Achsen: Tatzeitpunkt, ACS-5-Jahres-Fenster, Wettertag |
| **H1 bis H5** | unverändert Pflicht |
| **H7, H8** | bleiben Kür |

**Der Zeitraum ist auf 2024 festgelegt** ([Absprache 2.2](projektabsprache.md)).
Die vorgeprüften Zahlen zu H1 bis H5 stammen aus dem Chicago-Vollbestand von
259'625 Fällen; für den ausweisbaren Test müssen sie auf 2024 neu gerechnet oder
der Bezug ausdrücklich benannt werden.

**Eine Einschränkung, die aus 7.1 folgt.** Der Entscheid verlangt, dass bei einem
Daily Load T-1 geladen wird und dies ausgewiesen wird. Für NOAA ist das **nicht
erfüllbar**: Die Quelle veröffentlicht mit rund vier Tagen Nachlauf. Das ist
keine Schwäche der Pipeline, sondern eine Eigenschaft des qualitätsgeprüften
Datensatzes — es gehört als Ausnahme in die Dimension *Aktualität*
(Abschnitt 2.3.1) und in die Limitationen (Abschnitt 10.3).

---

## 3 · Der Data-Engineering-Lebenszyklus

Gefordert ist der **Entwurf**. Vieles davon existiert bereits, es ist nur nicht
unter diesen Begriffen dokumentiert. Diese Tabelle ist die Vorlage dafür.

| Phase | Was wir haben | Beleg | Lücke |
| --- | --- | --- | --- |
| **Generation** | Fünf Quellsysteme: Socrata (Chicago), ArcGIS REST (Detroit), HTTPS-Dateien (TIGER und NOAA), JSON-API (ACS). Je Quelle dokumentiert: Aktualisierungsverhalten, Schlüsselbedarf, Formate | Notebooks 01, 11, 21, 22, 32 | – |
| **Ingestion** | Vier Pipelines. Batch, kein Streaming. Chicago inkrementell über Wasserzeichen mit 14 Tagen Rückgriff; Census als eingefrorene Vintage; NOAA als Vollschnappschuss im Wochenrhythmus mit bedingtem Abruf | `src/crime/*_pipeline/` | – |
| **Storage** | Dateibasierte Schichten, Parquet mit festem Schema, Hive-Partitionen, unveränderliche Läufe mit Manifest. Ablage wahlweise lokal, SeaweedFS über S3 oder hybrid | `data/`, Abschnitt 4, [`storage-architektur.md`](../storage-architektur.md) | – |
| **Transformation** | Bronze bewusst ohne Transformation. Silver und Gold gebaut, Qualitätsanalyse beider Städte fertig | Notebook 03, 13, 34 | – |
| **Serving** | Option **A · Analytik** gewählt: Auswertungsdatenbank auf der Gold-Schicht | Abschnitt 6, Notebook 33 | gebaut: dreizehn Sichten über Silver, Gold und die vier Vergleichstabellen in Serving; das Dashboard darauf fehlt |

### Unterströmungen

| Unterströmung | Was wir haben | Lücke |
| --- | --- | --- |
| **Security** | Schlüssel nur in `.env`, nie im Manifest oder in abgelegten URLs; drei Tests prüfen das. `.env` und `data/` aus Git ausgeschlossen, `requirements.lock` pinnt jede Abhängigkeit exakt | kein Vulnerability-Scan der Abhängigkeiten; Datenschutzabschnitt schriftlich |
| **Data Management** | Manifest je Lauf, Herkunftsnachweis über `derived_from` und `input_fingerprint` durchgehend bis Gold, unveränderliche Läufe, Schema-Fingerabdruck gegen Drift, `_extra` gegen Datenverlust. Feldkatalog aus den Manifesten erzeugt, Aufbewahrungsregel mit `orchestration.aufraeumen` | das Aufräumen ist ein Handgriff, kein Automatismus |
| **DataOps** | 1'496 automatisierte Tests, alle ohne Netz und ohne Schlüssel, auf jedem Pull Request in GitHub Actions über zwei Betriebssysteme und zwei Python-Versionen; dazu der wöchentliche Datenlauf | keine Alarmierung ausser dem roten Lauf selbst |
| **Data Architecture** | Vier Schichten, gepinnte Schemata, Trennung von Beweis (raw) und Ableitung (bronze). Zwei Architekturbilder, aus dem Code erzeugt ([`architektur.md`](../architektur.md)) | Vintage 2024 hart verdrahtet |
| **Orchestration** | `orchestration.run_all`: 13 Stufen in Reihenfolge, Abbruch beim ersten Fehler, Gesamtmanifest über alle Eingabe-Läufe | der geplante Lauf ist wöchentlich, die Quellen ändern sich täglich; keine Wiederaufnahme nach Abbruch, bewusst |
| **Software Engineering** | Modulare Pakete, Typannotationen, ausführliche Docstrings, Fehlerbehandlung mit Wiederholungen | – |

**Beide damaligen Lücken sind geschlossen.** Für die Orchestrierung war der
bescheidene Ansatz angesetzt — ein Skript, das die Pipelines in der richtigen
Reihenfolge aufruft und protokolliert. Genau das ist `orchestration.run_all`
geworden. Airflow oder Prefect wären für vier Batch-Läufe unangemessen; das
lässt sich in der Präsentation gut begründen. Beim Serving stehen dreizehn Sichten und vier vorberechnete Vergleichstabellen;
offen ist allein das Dashboard darauf, und das gehört bewusst in LN2.

---

## 3a · Bezug zum Modul Transformation

Die Modulinhalte lassen sich fast lückenlos auf unser Projekt abbilden. Diese
Tabelle taugt als Gliederung für den Transformationsteil der Präsentation.

| Modulinhalt | Bei uns | Stand |
| --- | --- | --- |
| **Kombination von Streams** | Alle fünf Quellen sind Batch. Bewusst begründen statt weglassen: Ein Tumbling-Window ist der Batch-Fall der ereignisbasierten Verarbeitung | zu formulieren |
| **Watermark, verspätete Daten** | Unser 14-Tage-Lookback ist funktional die Toleranz für verspätet eintreffende Änderungen | vorhanden, zu benennen |
| **Verteiltes Setting (MapReduce, Spark)** | Nicht verwendet. Bei rund 350'000 Zeilen und 70 MB wäre es unangemessen — „so einfach und selbstisolierend wie möglich" | Begründung schreiben |
| **Formatbedingte Kompatibilität** | Bronze hält alles als Text; Typisierung erst in Silver. Führende Nullen in `iucr`, `beat`, `district` müssen erhalten bleiben | umgesetzt |
| **Inhaltliche Kompatibilität** | Zwei Deliktsprachen über NIBRS; zwei Koordinatenbezugssysteme (WGS84 gegen NAD83) | teilweise |
| **Zeitliche Kompatibilität, Granularität** | Vier Granularitäten: Fall (Zeitpunkt, Punkt), ACS (Tract, 5 Jahre), TIGER (Tract, Vintage), Wetter (Tag, Station) | offen — siehe H6 |
| **Imputation gegen Aggregation** | Fälle werden aggregiert; die ACS-5-Jahres-Schätzung auf ein Jahr zu beziehen ist dagegen eine Annahme, die offengelegt gehört | offen |
| **Integration: concat, append** | Chicago und Detroit zu einer Faktentabelle | offen |
| **Integration: join, merge** | Fall auf Tract (räumlich), Tract auf ACS (über `GEOID`) | offen |
| **Datenqualität: Data Governance** | Manifest je Lauf, Herkunft über `derived_from`, unveränderliche Läufe | umgesetzt |
| **Datenqualität: Datenprofil** (ISO/TS 8000-81) | Das Notebook `03_chicago_data_quality` ist genau das | umgesetzt für Chicago |
| **Datenqualität: Datenregeln** (ISO/TS 8000-82) | Die zwölf Prüfungen plus die 233 automatisierten Tests | umgesetzt |
| **Fehlende Daten: Identifikation** | Chicago sauber (keine nicht-standardmässigen Marker); Detroit hat 15 solche in `offense_description`; ACS nutzt `-666666666` | geprüft |
| **Fehlende Daten: Behandlung** | Entscheidung gegen Löschen, für Markieren — begründet durch H1 | begründet |
| **Duplikate gegen Dubletten** | 42 echte Duplikate aus dem Delta-Überlapp, keine Dubletten | geprüft, siehe H2 |
| **Noise gegen Ausreisser** | District `031` als Artefakt; Hotspots als echte Ausreisser | teilweise, siehe H5, H8 |
| **Tukey-Boxplot, Isolation Forest** | Anwendbar auf Fallzahlen je Tract | offen, siehe H8 |
| **Prognosen (Approximation, Extrapolation)** | Nicht im Scope. Bei Tracts ohne ACS-Wert wäre Imputation die Alternative — wir weisen sie stattdessen aus | zu begründen |

**Ein Begriff, zwei Bedeutungen — bitte in der Präsentation auflösen.** Das Modul
verwendet *Wasserzeichen* im Streaming-Sinn: eine Schwelle, ab der eintreffende
Daten als verspätet gelten. Unsere Chicago-Ingestion verwendet denselben Begriff
für den Fortschrittsmerker der inkrementellen Ladung, also das höchste bisher
gesehene `updated_on`. Beides ist üblich, aber im selben Vortrag ohne Erklärung
verwirrend. Der inhaltliche Berührungspunkt ist der Lookback: Er entscheidet, wie
weit zurück wir verspätete Änderungen noch aufsammeln — das ist funktional die
Toleranz, die ein Streaming-Wasserzeichen setzt.

---

## 4 · Storage: die geforderte Evaluation

Gefordert ist **Evaluation, Wahl und Implementierung**. Die Evaluation besteht
aus zwei Fragen, die oft vermischt werden:

1. **Die Speicherumgebung** — Dateien plus DuckDB, PostgreSQL/PostGIS oder
   Cloud? Dazu unten die Anforderungen und Optionen.
2. **Das Format innerhalb der Schichten** — NDJSON oder Parquet? Diese Frage
   ist **gemessen** und in
   [`notebooks/31_storage_evaluation.ipynb`](../../notebooks/31_storage_evaluation.ipynb)
   reproduzierbar.

### Das Bronze-Format: gemessen, nicht behauptet

Der Entscheid zu [Absprache 4.1](projektabsprache.md) verlangte genau diese
Messung: *„Es wird angeschaut was performanter ist."* Verglichen wurden
dieselben Daten in beiden Formaten — Detroits Bronze-Lauf, 88'685 Zeilen, das
ausgelieferte NDJSON gegen daraus erzeugtes Parquet, gelesen über DuckDB.

| Format | Grösse | gegen NDJSON |
| --- | --- | --- |
| NDJSON, wie ausgeliefert | 89,4 MB | 100 % |
| NDJSON + gzip | 10,9 MB | 12,2 % |
| **Parquet snappy** | **6,5 MB** | **7,3 %** |
| Parquet zstd | 4,8 MB | 5,4 % |

| Abfrage | NDJSON | Parquet | Faktor |
| --- | --- | --- | --- |
| Zeilen zählen | 0,088 s | 0,000 s | aus den Metadaten |
| eine Spalte lesen | 0,090 s | 0,000 s | 617× |
| nach Kategorie gruppieren | 0,091 s | 0,001 s | 110× |
| **fünf Spalten, alle Zeilen** | **0,139 s** | **0,029 s** | **4,9×** |
| alle Spalten materialisieren | 0,541 s | 0,428 s | 1,3× |

**Die vierte Zeile ist die, die zählt.** Genau das tut die Silver-Schicht:
wenige Felder aus jeder Zeile lesen. NDJSONs Zeiten sind über die ersten
Abfragen konstant, weil JSON keine Spaltenauswahl kennt — wer ein Feld braucht,
parst die ganze Datei. Beim vollständigen Materialisieren schrumpft der
Vorsprung auf 1,3×, weil dort das Aufbauen der Ergebniszeilen dominiert.

**Was für NDJSON spricht, damit es genannt ist.** Die Sorge, DuckDB könnte das
Schema je nach Stichprobe anders erraten, **trifft nicht zu**: 100 Zeilen,
2'048 Zeilen und die ganze Datei ergeben dasselbe Schema. Und NDJSON ist ohne
Werkzeug lesbar — ein `head` zeigt eine Zeile, für Parquet braucht es DuckDB
oder pyarrow. Für die Fehlersuche an einer neuen Quelle ist das ein echter
Vorteil.

**Der stärkste Befund ist nicht die Geschwindigkeit.** Detroits NDJSON
übernahm bis zum 11.9.2026 zwei Rollen gleichzeitig: Beweisstück und abgeleitete
Tabelle. Zieht man es auf die Konvention der anderen drei Quellen nach, kostet
die zusätzliche Schicht nichts, sie spart:

```text
heute        Bronze NDJSON                89,4 MB
nachgezogen  Raw    NDJSON + gzip          10,9 MB
             Bronze Parquet snappy          6,5 MB
             zusammen                       17,4 MB   → 81 % weniger
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

**Ergebnis:** Parquet in Bronze, NDJSON komprimiert in Raw. Damit ist auch
[Absprache 4.2](projektabsprache.md) entsperrt, deren Entscheid „Hängt von 4.1
ab" lautete.

**Grenzen der Messung:** warmer Betriebssystem-Cache, also ohne den
Plattenzugriff, der Parquet zusätzlich begünstigen würde; eine Maschine, ein
Datensatz; nur der Lesepfad. Die Grössenordnungen sind belastbar, die exakten
Faktoren nicht übertragbar.

### Die Speicherumgebung

Die zweite Frage ist von der ersten unabhängig: Auch mit Parquet als Format
bleibt offen, was darüber liegt. Vorschlag für die Argumentation:

#### Anforderungen an die Speicherumgebung

1. Rohdaten unveränderlich und beweissicher ablegen
2. Spaltenorientierte Auswertung über einige Millionen Zeilen
3. Geometrien speichern und räumlich verknüpfen
4. Schemastabilität über viele Läufe hinweg
5. Ohne Serverbetrieb lauffähig, damit beide im Team lokal arbeiten können
6. Nachvollziehbar und versionierbar für die Abgabe

#### Optionen

| Option | Stärken | Schwächen | Bewertung |
| --- | --- | --- | --- |
| **Parquet-Dateien mit Hive-Partitionen** (heutiger Stand) | kein Server, spaltenorientiert, offenes Format, git-freundlich in der Struktur | keine Transaktionen, kein SQL out of the box | erfüllt 1–6 |
| **PostgreSQL + PostGIS** | ausgereifter Raumbezug, echtes SQL, Transaktionen | Serverbetrieb, Einrichtung bei beiden, Rohdaten passen schlecht hinein | 5 nicht erfüllt |
| **DuckDB** | SQL direkt auf Parquet, `spatial`-Extension, eine Datei, kein Server | jung, nicht für parallele Schreiber gedacht | ergänzt die erste Option |
| **Cloud (S3, BigQuery)** | skaliert, praxisnah | Kosten, Zugänge, für 70 MB unangemessen | verworfen |

#### Vorschlag

**Zweistufig:** Dateibasierte Schichten in Parquet als Speicher, **DuckDB als
Abfrageschicht** darüber. Begründung: Die Ablage bleibt offen, portabel und
unveränderlich; DuckDB liefert SQL und den räumlichen Join, ohne dass jemand
einen Server betreiben muss. Für ein Projekt dieser Grössenordnung — rund
350'000 Fälle und 6'282 Tracts — ist das angemessen, und die Wahl lässt sich
sauber gegen die Alternativen begründen.

Zu implementieren wären dann: die Silver- und Gold-Tabellen als Parquet plus
eine DuckDB-Datei mit Sichten darauf.

Siehe auch [Absprache 5.3](projektabsprache.md).

`Entscheid: DuckDB — übernommen aus [Absprache 5.3](projektabsprache.md), dort am 8.9.2026 entschieden. Die schriftliche Evaluation fehlt weiterhin.`

**Was dieser Entscheid nicht abdeckt.** [Absprache 4.1](projektabsprache.md)
hat das **Bronze-Format** offengelassen: „Es wird angeschaut was performanter
ist. Wenn Parquet besser ist, wird es umgesetzt." Detroit liegt heute als
NDJSON, Chicago und Census als Parquet. Die Evaluation in diesem Abschnitt muss
diesen Vergleich deshalb mit abdecken — nicht nur Parquet gegen PostgreSQL und
DuckDB, sondern auch NDJSON gegen Parquet innerhalb von Bronze. [Absprache
4.2](projektabsprache.md) („Hängt von 4.1 ab") wartet auf dasselbe Ergebnis.

---

## 5 · Transformation Teil 1: was bis LN1 fehlt

Gefordert sind **Analyse der Datengrundlage**, **Hypothesentest** und
**initiale Datenbereinigung**.

| Schritt | Stand | Aufwand |
| --- | --- | --- |
| Datenqualität Chicago | ● fertig, 12 Prüfungen | – |
| Datenqualität Detroit | ● fertig, 14 Prüfungen | – |
| Datenqualität Census | ◐ im Quellnotebook enthalten | gering |
| Silver: Dedup und Typen | ● fertig | – |
| Silver: räumlicher Join auf Tracts | ● fertig, 99,3 % / 99,7 % verortet | – |
| NIBRS-Harmonisierung beider Städte | ● fertig, beide Städte 100 % zugeordnet — aber H3 teilweise falsifiziert (Konzept 8.5) | – |
| Gold: Raten je Tract | ● fertig, Sternschema mit `fact_offense` und vier Dimensionen | – |
| Hypothesentest H1–H4 | ○ | ~1 Tag |

**Offen ist noch der Hypothesentest** — rund ein Arbeitstag. Die Wetterquelle
und die Präsentation kommen dazu.

**Reihenfolge-Empfehlung — eingelöst, mit einem geteilten Ergebnis.** Die
Detroit-Qualität kam zuerst, und die Frage war berechtigt: Der Geoausfall ist in
beiden Städten nicht zufällig, aber er ist **nicht durchweg derselbe**. Auf
gemeinsamer NIBRS-Achse gemessen (Notebook 34, Abschnitt 5.2):

* **Sexualdelikte** fehlen in beiden Städten deutlich überproportional —
  Chicago beim 12,0-Fachen des Stadtschnitts, Detroit beim 5,2-Fachen. Gleiche
  Richtung, vermutlich gleiche Ursache: die zurückgehaltene Adresse. Dieser
  Teil der Lücke verzerrt den Vergleich **nicht**, er trifft beide Seiten.
* **Betrug** fehlt dagegen nur in Chicago: 3,78 % gegen 0,19 % — Faktor 20
  zwischen den Städten. Hier ist Chicagos Zahl die untererfasste.

> **Nachgemessen am 20.09.2026 (Christian).** Die Faktoren sind auf den
> aktuellen Stand gehoben (zuvor 6,5 / 5,1 / 3,5 % / Faktor 18). Die Richtung
> und damit die Argumentation ändern sich nicht — Chicagos Sexualdelikte
> fallen sogar deutlicher aus als bisher notiert.

Für den Vergleich der Gesamtraten trägt das (0,81 % gegen 0,29 % Ausfall
verschieben keine Rangfolge); für einen Vergleich **je Delikttyp** muss bei
Betrug die Abdeckung danebenstehen.

---

## 6 · LN2: die Serving-Entscheidung

Drei Optionen stehen zur Wahl. Der Entscheid gehört **jetzt** getroffen, obwohl
er erst für LN2 zählt: Er bestimmt, was die Gold-Schicht enthalten muss, und die
bauen wir schon für LN1.

| | Was zu liefern ist | Passt zu unseren Daten | Aufwand | Risiko |
| --- | --- | --- | --- | --- |
| **A · Analytik** | Deployment-Umgebung, z. B. Dashboard auf der Gold-Schicht | sehr gut — Gold ist ohnehin geplant (inzwischen gebaut) | mittel | gering |
| **B · Machine Learning** | mindestens zwei Regressions- oder Klassifikationsmodelle mit Vergleich | gut: Zielgrösse Kriminalitätsrate je Tract, Merkmale aus ACS und Wetter | mittel–hoch | mittel |
| **C · KI-Anwendung** | Applikation mit LLM, z. B. Agentic AI | Daten wären Kontext, nicht Kern | hoch | hoch, Data-Engineering-Anteil gering |

### Einschätzung

**Option B ist gut machbar**, und die Datenlage trägt sie: 1'332 Tracts in Cook
County, 627 in Wayne County — genug Beobachtungen für eine Regression der
Kriminalitätsrate auf sozioökonomische Merkmale, und der Modellvergleich (etwa
lineare Regression gegen Random Forest) ist klar abgrenzbar und bewertbar. B
zahlt ausserdem direkt auf FF2 ein und macht die Wetterdaten nützlich.

**Option A ist die sichere Wahl** und zeigt den Lebenszyklus vollständig bis zum
Endnutzer, ist inhaltlich aber weniger anspruchsvoll.

**Option C** würde ich nicht empfehlen: Der Aufwand liegt dort in der
Applikation, nicht im Data Engineering, und genau das wird bewertet.

**Vorschlag: B**, mit A als Rückfallebene, falls die Zeit knapp wird — ein
Dashboard auf derselben Gold-Schicht ist deutlich schneller gebaut als Modelle.

**Wichtig für die Gold-Schicht:** Fällt die Wahl auf B, muss Gold eine
**Merkmalstabelle je Tract** enthalten — eine Zeile je Tract mit Zielgrösse und
allen Merkmalen. Fällt sie auf A, genügen Aggregate je Tract, Monat und
Kategorie. Das ist der Grund, weshalb der Entscheid nicht warten kann.

`Entscheid: Option A ist unser Hauptziel`

---

## 7 · Arbeitspakete bis LN1

| # | Paket | Ergebnis | Wer | Bis |
| --- | --- | --- | --- | --- |
| 1 | Forschungsfragen und Hypothesen festlegen | Abschnitt 2 entschieden | beide | |
| 2 | ~~Serving-Option wählen~~ | erledigt am 8.9.2026: **Option A** | beide | ✓ |
| 3 | Problemstellung und Methodenteil schreiben | Präsentationstext | | |
| 4 | Lebenszyklus dokumentieren | Diagramm + Tabelle aus Abschnitt 3 | | |
| 5 | Storage-Evaluation verschriftlichen | Abschnitt 4 als Präsentationsteil | | |
| 6 | ~~Datenqualität Detroit~~ | erledigt am 12.9.2026: Notebook 13 | Christian | ✓ |
| 7 | ~~Detroit-Bronze angleichen~~ | erledigt am 12.9.2026: Raw-Schicht und `city=`-Partition wie Chicago | Christian | ✓ |
| 8 | ~~Silver: Dedup, Typen, räumlicher Join~~ | erledigt: `silver/crime_offense`, 348'311 Zeilen | Christian | ✓ |
| 9 | ~~NIBRS-Harmonisierung über beide Städte~~ | erledigt: beide Crosswalks angewandt, H3 dabei teilweise falsifiziert | Christian | ✓ |
| 10 | ~~Gold: Raten je Tract~~ | erledigt: Sternschema, Chicago 94,5 / Detroit 132,7 je 1'000 | Christian | ✓ |
| 11 | Hypothesentest H1–H4 | Notebook mit Ergebnissen | | |
| 12 | Präsentation | Abgabe | beide | |

Pakete 1 und 2 blockieren alles andere und sollten in der ersten Sitzung
erledigt werden.

---

## 8 · Risiken

| Risiko | Auswirkung | Gegenmassnahme |
| --- | --- | --- |
| Hypothesen zu spät festgelegt | Transformation ohne Ziel, Nacharbeit | Paket 1 zuerst |
| Detroit-Daten tragen den Vergleich nicht | FF1 nicht beantwortbar | Paket 6 früh, notfalls Fragestellung anpassen |
| NIBRS-Zuordnung für Detroit unvollständig | Kategorien nicht vergleichbar | früh prüfen; Chicago ist zu 100 % belegt, Detroit offen |
| Ungleiche ACS-Lücken zwischen den Städten | verzerrter Vergleich | ausweisen statt wegrechnen; Sensitivitätsrechnung |
| ~~Serving-Entscheid zu spät~~ | ~~Gold zweimal gebaut~~ | entfallen: Option A ist entschieden, das Gold-Schema steht damit fest |
| Verschiedene Datenstände im Team | widersprüchliche Zahlen | Referenzstand vereinbaren, [Absprache 7.1](projektabsprache.md) |

---

## 9 · Stand der Entscheide

Die Sitzung vom **8.9.2026** hat 17 der 18 Entscheide in
[`projektabsprache.md`](projektabsprache.md) beantwortet. Für dieses Dokument
ergibt sich folgender Stand:

| | Punkt | Stand | Woher |
| --- | --- | --- | --- |
| 1 | **Forschungsfragen** — FF1 bis FF3 übernehmen oder anders schneiden? | ○ **offen** | [Absprache 5.2](projektabsprache.md) sagt ausdrücklich „Forschungsfragen noch definieren" |
| 2 | **Hypothesen** — H1 bis H5 Pflicht, H6 bis H8 Kür? | ○ **offen** | – |
| 3 | **Serving-Option** — A, B oder C? | ● **A · Analytik** | Abschnitt 6; gebaut als Sternschema auf Deliktebene statt als Aggregat — die Messung dazu in Notebook 34 |
| 4 | **Wetterquelle** — im Scope? | ● **ja** | [Absprache 2.1](projektabsprache.md) Variante **D**; Quelle gebaut, getestet, geladen, dokumentiert |
| 5 | **Storage-Begründung** | ● **erledigt** | Notebook 31 misst NDJSON gegen Parquet, Kapitel 7 schreibt es aus; das Bronze-Format ist mit [Absprache 4.1](projektabsprache.md) auf Parquet entschieden |
| 6 | **Arbeitsteilung** | ● **geregelt am 12.9.2026** | Christian: Silver, Gold, Pipeline. Artan: Dokumentation, Präsentation, Hypothesen |

Dazu zwei Entscheide, die in dieser Liste bisher fehlten und weiterhin offen
sind — beide in Abschnitt 10.1: **Sichtbarkeit** des Repositorys und **Ablage**
der Abgabe. Sie hängen an der Abgabeform, nicht an der Technik.

**Drei echte Entscheidungen bleiben also: 1, 2 und 6.** Die ersten beiden
hängen zusammen und beide am selben Punkt: Die **Form** von Gold steht seit dem
Serving-Entscheid fest — Aggregate je Tract, Monat und Kategorie —, aber sein
**Inhalt** hängt an den Forschungsfragen. Genau das sagt
[Absprache 5.2](projektabsprache.md) mit „Muss noch definiert werden.
Forschungsfragen noch definieren."

**Eine Spannung, die aus zwei Entscheiden zusammen entsteht.** Abschnitt 6 hat
Option **B** vorgeschlagen, unter anderem mit der Begründung, sie „macht die
Wetterdaten nützlich". Gewählt ist **A**, während [Absprache
2.1](projektabsprache.md) mit Variante **D** das Wetter im Scope behält. Damit
muss das Wetter seinen Platz in einem Aggregat-Gold verdienen — etwa als
Dimension neben Tract, Monat und Kategorie. Sonst trägt die Wetterquelle nur zu
FF2 und H6 bei, nicht zum Serving. Das ist kein Widerspruch, aber es gehört beim
Entwurf des Gold-Schemas entschieden.

### Was aus der Sitzung noch nicht eingearbeitet ist

Diese Antworten aus der Absprache verändern Aussagen in diesem Dokument. Sie
sind hier vermerkt, aber die betroffenen Abschnitte noch nicht ausformuliert:

| Entscheid | Wirkung hier |
| --- | --- |
| **2.1 Variante D** | grösster Umfang von vier Varianten: Vergleich *plus* Sozioökonomie *plus* Wetter. Betrifft Abschnitt 2.5 |
| **2.2 Zeitraum 2024** | fixiert die Datenbasis der Hypothesentests |
| **2.4 Geo-Lücke** | „Detroit wird noch analysiert" — Vorarbeit für H1 und H7 |
| **4.1 / 4.2 Bronze-Format** | die Storage-Evaluation in Abschnitt 4 braucht den Vergleich NDJSON gegen Parquet |
| **5.1 Silver zweifach** | „Zwei Version, Abgleich welche besser" — ein Arbeitspaket, das in Abschnitt 7 fehlt |
| **7.1 T-1 ausweisen** | liefert den fehlenden Schwellenwert für die Dimension *Aktualität* in Abschnitt 2.3.1 |

---

## 10 · Abgabe und Kolloquium

**Ablauf.** Am Vortag bis 14:00 Uhr Upload von kommentiertem Code, **Daten** und
Präsentation auf Moodle. Am Kolloquiumstag rund 30 Minuten Präsentation je
Gruppe — **zu gleichen Teilen unter den Mitgliedern aufgeteilt** —, danach
15 Minuten Diskussion mit Fragen von Kursteilnehmenden und Prüfenden.

### 10.1 Abgabe über das Repository statt über Moodle

Statt eines Uploads geben wir das GitHub-Repository an. Daraus folgen ein
Blocker, eine Einsicht und eine Empfehlung.

#### Blocker: Das Repository ist nicht öffentlich erreichbar

`https://github.com/artanmusollaj-ops/Crime-Data-Gruppe3` antwortet mit
**HTTP 404**. GitHub antwortet auf private Repositories genau so — es ist also
vermutlich privat, nicht gelöscht. Solange das gilt, nützt der Link den
Prüfenden nichts.

Zwei Wege: **öffentlich schalten** oder die Prüfenden **als Mitarbeitende
einladen**. Vor dem Öffentlichmachen habe ich die Historie geprüft: Es wurde nie
ein Schlüssel committet, nur eine `.env.example`, und die Suche nach
`SOCRATA_APP_TOKEN` oder `CENSUS_API_KEY` im gesamten Verlauf bleibt leer. Aus
dieser Sicht spricht nichts gegen ein öffentliches Repository.

`Entscheid Sichtbarkeit: __________________________________`

#### Einsicht: Nur zwei der fünf Quellen müssen überhaupt abgelegt werden

Entscheidend ist, welche Quelle sich **byte-identisch reproduzieren** lässt:

| Quelle | Verhalten | Konsequenz |
| --- | --- | --- |
| **TIGER** | Vintage eingefroren | reproduziert identisch → **nicht ablegen**, nachladen |
| **ACS** | Vintage eingefroren | reproduziert identisch → **nicht ablegen**, nachladen |
| **Chicago** | lebende Quelle, `updated_on` wandert | driftet → **Referenzstand nötig** |
| **Detroit** | lebende Quelle | driftet → **Referenzstand nötig** |

Damit schrumpft das, was wirklich festgehalten werden muss, auf die beiden
Falldatenquellen. Und hier hilft die Bronze-Angleichung ein zweites Mal:

```text
Detroit NDJSON   89,4 MB
Detroit Parquet   16,0 MB     der echte Lauf vom 11.9., ZSTD, mit Nutzlast
```

Chicago Bronze (16,7 MB) plus Detroit als Parquet (16,0 MB) ergeben einen
Referenzstand von rund **33 MB** — handlich genug, dass die Frage nach externem
Speicher gar nicht erst entsteht.

#### Die Daten gehören **nicht** in die Git-Historie

Wichtige Unterscheidung: Ein **Release-Asset** hängt am Repository, liegt aber
ausserhalb der Versionsgeschichte. Das ist etwas anderes als `git add`.

| | Committen | Release-Asset |
| --- | --- | --- |
| liegt in `.git` | ja, **dauerhaft** | nein |
| jeder Clone lädt es mit | ja | nein |
| nach dem Löschen weg | nein, bleibt in der Historie | ja |
| Limit | 100 MB je Datei, Warnung ab 50 MB | 2 GB je Datei |

Der Grund gegen das Committen liegt in unserer eigenen Architektur: Die Pipeline
erzeugt absichtlich **immer neue unveränderliche Läufe**. Jeder weitere Lauf
liesse das Repository dauerhaft um weitere rund 25 MB wachsen, denn Parquet ist
binär und lässt sich nicht als Änderung speichern. `.git` liegt heute schon bei
69 MB.

**Ausnahme: die Manifeste.** Alle 15 zusammen wiegen 64 KB, sind Text, lassen
sich sinnvoll vergleichen und sind die Beweiskette. Sie gehören ins Repository.
Dabei ist eine Git-Eigenheit zu beachten — geprüft, nicht vermutet: Mit dem
heutigen Muster `data/*/city=*/` greift eine Ausnahme wie `!**/manifest.json`
**nicht**, weil Git eine Datei nicht wieder einschliessen kann, wenn ein
übergeordnetes Verzeichnis ausgeschlossen ist. Es braucht die Dateivariante:

```gitignore
data/*/city=*/**
!data/*/city=*/**/
!**/manifest.json
```

#### Empfehlung: GitHub Release als Ablage, kein Drittanbieter

Ein **Release** im eigenen Repository nimmt Dateien bis 2 GB auf, ist versioniert
und liegt ausserhalb der Git-Historie — kein fremdes Speicherkonto, kein Link,
der veralten kann.

Die Alternativen, der Vollständigkeit halber:

| Variante | Beurteilung |
| --- | --- |
| **Git LFS** | technisch möglich, aber Einrichtung, Kontingent und die Prüfenden bräuchten LFS lokal — unnötige Hürde |
| **SwitchDrive der Hochschule** | institutionell sauber, aber Zugriffsrechte und Linkpflege liegen bei uns |
| **Nur Skript, kein Referenzstand** | am einfachsten — aber die Zahlen der Präsentation sind später nicht mehr nachvollziehbar, weil die Falldaten driften |

#### Die beiden Entscheide hängen zusammen

Ein herunterladbares ZIP ist genau das, was ein Release-Asset ist. Der Haken:
**Release-Assets erben die Sichtbarkeit des Repositories.** Bei einem privaten
Repository verlangt auch der Release-Link eine Anmeldung.

| ZIP liegt auf | funktioniert bei **privatem** Repo? |
| --- | --- |
| GitHub Release | **nein** — Anmeldung nötig |
| SwitchDrive oder OneDrive mit Freigabelink | ja, unabhängig vom Repo |
| Moodle | ja, unabhängig vom Repo |

Das ist in dreissig Sekunden selbst nachprüfbar: Release-Link in einem privaten
Browserfenster öffnen, also abgemeldet.

Daraus ergeben sich zwei stimmige Kombinationen:

**A · Repository öffentlich, Daten als Release.** Ein Link deckt Code,
Dokumentation und Daten ab. Keine Zugriffsverwaltung am Prüfungstag, kein
fremder Dienst, kein Link, der abläuft. Nach der Bewertung lässt sich das
Repository wieder auf privat stellen.

**B · Repository privat, ZIP über SwitchDrive oder Moodle.** Funktioniert, hat
aber am Tag, an dem es zählt, zwei Fehlerquellen statt einer: Die Prüfenden
brauchen eine GitHub-Einladung **und** der externe Link muss leben.

Ich halte A für die robustere Variante — schlicht, weil weniger schiefgehen kann.

#### Vor dem Öffentlichmachen zu klären

- **Secrets:** geprüft, die Historie ist sauber (nur `.env.example`, keine
  Schlüsselmuster).
- **Lizenz:** Es gibt keine `LICENSE`-Datei. Ohne Lizenz gilt „alle Rechte
  vorbehalten" — für eine Kursabgabe vertretbar, aber es sollte eine bewusste
  Entscheidung sein.
- **Quellennennung:** Die Notebooks führen die Quellen sauber auf, die README
  nicht. Wer fremde Daten weiterverbreitet, sollte sie benennen. Alle vier
  Quellen sind offen — Census-Daten sind als US-Regierungswerk gemeinfrei,
  Chicago und Detroit stehen unter Open-Data-Bedingungen —, aber ein kurzer
  Abschnitt „Datenquellen und Nutzungsbedingungen" in der README gehört dazu.
  Das zahlt zugleich auf die Unterströmung **Data Governance** ein.

Dazu ein Skript mit zwei Betriebsarten:

| Aufruf | Was passiert | Wofür |
| --- | --- | --- |
| `fetch_data.py --referenz` | lädt den Referenzstand aus dem Release | Zahlen der Präsentation nachvollziehen |
| `fetch_data.py --neu-laden` | lässt alle vier Pipelines gegen die Originalquellen laufen | zeigt, dass die Ingestion funktioniert |

**Die Manifeste sind der Abgleich zwischen beiden.** Sie tragen SHA-256 je
Datei, Zeilenzahl, Wasserzeichen und Vollständigkeitsnachweis. Das Skript kann
nach einem Neuladen also sagen: „dein Lauf 259'281 Zeilen, Referenz 259'272 —
neun Datensätze sind seither dazugekommen". Das ist **mehr wert als
byte-identische Daten**: Die Drift wird beziffert statt versteckt, und genau das
ist die ehrliche Antwort auf die Prüfungsfrage „wie reproduzierbar ist euer
Lauf?".

Nebenbei schliesst dasselbe Skript die Lücke **Orchestrierung** aus Abschnitt 3 —
es ist der dokumentierte Ablauf, in dem die Pipelines zu laufen haben.

`Entscheid Ablage: ________________________________________`

### 10.2 Zeitbudget: 15 Minuten pro Person

Bei zwei Personen bleiben je 15 Minuten. Unser Stoff ist ein Vielfaches davon —
fünf Quellen, vier Pipelines, 633 Tests, Qualitätsanalyse, Lebenszyklus,
Speicherevaluation, Hypothesen. Ohne harte Auswahl wird es eine Aufzählung ohne
Tiefe.

Vorschlag für die Aufteilung, an der geforderten Gliederung entlang:

| Block | Minuten | Inhalt |
| --- | --- | --- |
| Organisation und Projektgestaltung | 3 | Aufgabenteilung, Werkzeuge, Arbeitsweise |
| Problemstellung, Forschungsfragen, Hypothesen | 5 | Abschnitt 2 |
| Lebenszyklus und Architektur | 5 | ein Bild, nicht zehn |
| Ingestion und Storage | 6 | Vollständigkeitsnachweis als roter Faden |
| Transformation und Resultate | 7 | Hypothesentests mit Zahlen |
| Limitationen | 4 | siehe 10.3 |

**Wichtig:** Die Aufteilung in gleiche Redezeit heisst nicht, dass jede Person
nur ihren Teil kennen muss. In der Diskussion richten sich Fragen an die Gruppe,
nicht an das Kapitel. Beide müssen den ganzen Stand erklären können.

### 10.3 Limitationen sind unser Heimspiel

„Limitationen" steht als eigener Punkt auf der Agenda. Erfahrungsgemäss ist das
der Teil, bei dem Gruppen ins Schwimmen geraten — weil man Schwächen erst sucht,
wenn man danach gefragt wird.

Wir sind in der umgekehrten Lage: Unsere Limitationen sind **gemessen**, mit
Zahlen und mit Begründung. Das gehört selbstbewusst vorgetragen, nicht
entschuldigend:

- 0,81 % der Chicago-Fälle ohne Koordinaten — und der Ausfall ist nach
  Delikttyp verzerrt, 4,3 % gegen 0,4 %
- Detroit dagegen nur 0,29 % — die Verzerrung ist zwischen den Städten **nicht
  symmetrisch**
- ACS fehlt in Wayne County bei 9,6 % der Tracts, in Cook County bei 1,7 %
- `case_number` ist kein Schlüssel, District `031` ist ein Erfassungsartefakt
- ACS ist eine 5-Jahres-Schätzung, die Fälle sind tagesgenau
- Tract-Grenzen brechen zwischen Zensus 2010 und 2020

Wer Limitationen so beziffern kann, zeigt damit vor allem eines: dass er seine
Daten kennt.

### 10.4 Womit in der Diskussion zu rechnen ist

15 Minuten Fragen. Diese hier halte ich für wahrscheinlich — die Antworten
stehen alle in diesen beiden Dokumenten, sie müssen nur sitzen:

| Frage | Wo die Antwort steht |
| --- | --- |
| Warum kein Spark, kein Hadoop, keine Cloud? | Abschnitt 3a und 4 — Grössenordnung, ROI |
| Warum Dateien und keine Datenbank? | Abschnitt 4, Optionsvergleich |
| Wie stellt ihr sicher, dass ein Lauf vollständig ist? | id-Liste vorher, Abgleich danach; ZIP-CRC; ACS gegen TIGER |
| Was genau meint ihr mit Wasserzeichen? | **Achtung, zwei Bedeutungen** — Abschnitt 3a |
| 0,81 % fehlen — warum löscht ihr sie nicht einfach? | H1, MNAR statt MCAR |
| Ist das nicht ein ökologischer Fehlschluss? | Abschnitt 2.3.2 |
| Warum Census Tracts und nicht Community Areas? | Vergleichbarkeit zwischen den Städten |
| Wie reproduzierbar ist ein Lauf? | ehrlich: Raw ja, Delta-Läufe nein — deshalb der Referenzstand |
| **Warum hat Bronze drei verschiedene Formen?** | **schwächster Punkt — siehe unten** |
| Wer hat was gemacht? | Rollentabelle, [Absprache 7.3](projektabsprache.md) |
| Was würdet ihr heute anders machen? | vorher überlegen, nicht improvisieren |

**Die Bronze-Frage kommt.** „Storage: Evaluation, Wahl und Implementierung" ist
Prüfungsinhalt, und drei nebeneinanderstehende Konventionen fallen auf. Zwei
Wege: bis LN1 angleichen (Arbeitspaket 7), oder in der Präsentation selbst
ansprechen — bekannt, hier die Begründung, hier der Plan. Selbst benennen ist
fast immer besser, als ertappt zu werden.

### 10.5 Vor der Abgabe

- [ ] Repository öffentlich oder Prüfende eingeladen — heute antwortet es mit 404
- [ ] Referenzstand als Release veröffentlicht, `fetch_data.py` einmal auf einem fremden Rechner getestet
- [ ] `python -m pytest` läuft grün auf **beiden** Rechnern
- [ ] Notebooks laufen von oben nach unten durch, ohne gespeicherte Outputs
- [ ] README beschreibt, wie man den Stand reproduziert
- [ ] Rollentabelle ausgefüllt — sie ist Präsentationsinhalt
- [ ] Präsentation einmal mit Uhr durchgesprochen, je 15 Minuten
- [ ] Fragenkatalog aus 10.4 gemeinsam durchgegangen

**Zum Zeitplan:** Die Abgabe ist am Vortag um 14:00 Uhr. Der letzte sinnvolle
Arbeitstag ist damit zwei Tage vor dem Kolloquium — am Vortag gehört die Zeit
dem Packen, dem Hochladen und dem Durchsprechen, nicht dem Programmieren.
