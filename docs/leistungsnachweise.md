# Leistungsnachweise 1 und 2: Anforderungen, Stand, Lücken

Dieses Dokument stellt die Anforderungen der beiden Leistungsnachweise dem
tatsächlichen Projektstand gegenüber und benennt, was bis zur Abgabe fehlt.

Es ergänzt [`projektabsprache.md`](projektabsprache.md): Dort stehen die
technischen Entscheide (Bronze-Konventionen, Werkzeuge, Zusammenarbeit), hier
die Abgabe-Sicht. Wo ein Entscheid aus der Absprache eine Anforderung erfüllt,
ist er verlinkt.

Alle Zahlen sind am 6. September 2026 aus dem Repository erhoben.

---

## 1 · LN1 auf einen Blick

| Anforderung | Stand | Was fehlt |
| --- | --- | --- |
| **Problemstellung, Ausgangslage** | ○ nicht vorhanden | Text, ca. 1 Seite → Abschnitt 2.1 |
| **Forschungsfragen, Hypothesen** | ◐ Vorschlag steht, vier bereits vorgeprüft | Auswahl und Formulierung entscheiden → Abschnitt 2.2 / 2.3 |
| **Vorgehen und Methoden** | ◐ implizit im Code | Methodenteil ausformulieren → Abschnitt 2.4 |
| **Entwurf DE-Lebenszyklus** | ◐ gebaut, nicht benannt | Zuordnung dokumentieren → Abschnitt 3 |
| **Ingestion: Quellen, Beschaffung** | ● weitgehend fertig | Wetterquelle offen, Detroit-Quellnotebook fehlt |
| **Storage: Evaluation, Wahl, Implementierung** | ◐ implementiert, nicht evaluiert | Begründeter Vergleich → Abschnitt 4 |
| **Transformation 1: Analyse, Hypothesentest** | ◐ für Chicago fertig | Detroit-Qualität, eigentlicher Test → Abschnitt 5 |
| **Initiale Datenbereinigung** | ○ Silver ist leer | Dedup, Typen, Join → Abschnitt 5 |
| **Beantwortung der Forschungsfragen** | ○ | folgt aus allem davor |

● fertig ◐ teilweise ○ offen

**Die gute Nachricht:** Ingestion und Storage — die beiden praktisch
aufwendigsten Blöcke — stehen weitgehend. 233 Tests, vier Quellen, nachgewiesene
Vollständigkeit. Und weil die Hypothesen Fragen des Data Engineering sind
(Abschnitt 2.0), sind vier davon durch die bisherige Arbeit **bereits
vorgeprüft**: Wir haben Befunde, bevor wir die Hypothesen formuliert haben.

**Die Baustelle:** Der konzeptionelle Teil ist noch nicht aufgeschrieben, und
Silver ist leer. Ohne formulierte Hypothesen gibt es keinen ausweisbaren
Hypothesentest, auch wenn die Messungen längst vorliegen.

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
| **FF2** | Welches Qualitätsniveau erreichen die vier Quellen, gemessen an definierten Dimensionen — und genügt es dem festgelegten Verwendungszweck? | Datenqualität, Bewertung |
| **FF3** | Welche Bereinigungsschritte sind erforderlich, und wie stark verändern sie das Ergebnis? | Datenbereinigung 1 und 2 |

FF3 ist die interessanteste der drei: Sie zwingt dazu, die Wirkung jeder
Bereinigung zu messen statt sie nur durchzuführen — etwa den Unterschied
zwischen „Fälle ohne Koordinaten löschen" und „markieren".

### 2.3 Hypothesen (Vorschlag)

Alle falsifizierbar, alle mit einem Verfahren aus dem Modul prüfbar, alle mit
unseren Daten tatsächlich durchführbar. **Vier sind bereits vorgeprüft** — die
Zahlen stammen aus den Notebooks und den Läufen im Repository.

| | Hypothese | Verfahren | Stand |
| --- | --- | --- | --- |
| **H1** | Fehlende Koordinaten treten **nicht zufällig** auf, sondern hängen vom Delikttyp ab (MNAR statt MCAR). | Chi-Quadrat-Unabhängigkeitstest | vorgeprüft: 4,3 % bei Delikten an Kindern gegen 0,4 % bei Diebstahl |
| **H2** | Der Überlapp der Delta-Läufe erzeugt ausschliesslich **Duplikate** (in allen Attributen identisch), keine **Dubletten**. | Vergleich aller Attribute je Schlüssel | **bestätigt**: 42 von 42 mehrfachen `id` in jedem Attribut identisch |
| **H3** | Die Deliktschlüssel beider Städte lassen sich **vollständig** auf NIBRS abbilden. | Abgleich gegen die Mapping-Tabelle | Chicago bestätigt (0 von 259'272 ohne Zuordnung), Detroit offen |
| **H4** | Ein gepinntes Schema plus Auffangspalte fängt Schema-Drift **vollständig** auf, ohne Datenverlust. | Fingerabdruck über Feldtypen, Inhalt von `_extra` | bestätigt: Chicago driftfrei, TIGER fängt `GEOIDFQ` auf |
| **H5** | Auffällige Werte in den Verwaltungsschlüsseln sind **Artefakte** (systematische Erfassungsfehler), keine echten Ausreisser. | Häufigkeitsanalyse plus feldübergreifende Konsistenzregel | vorgeprüft: District `031`, 13 Fälle, deren `beat` auf 016/024 zeigt |
| **H6** | Die Zusammenführung der drei Zeitachsen gelingt allein durch **Aggregation**; **Imputation** ist nicht nötig. | Granularitätsanalyse je Quelle | offen — ACS ist eine 5-Jahres-Schätzung und dürfte die Ausnahme sein |
| **H7** | Unser räumlicher Join **reproduziert** die Tract-Zuordnung, die Detroit selbst mitliefert. | Übereinstimmungsquote gegen `census_block_2020_geoid` | offen — Referenz vorhanden für 88'278 Zeilen |
| **H8** | Tract-Zellen mit auffällig hohen Fallzahlen sind echte **Ausreisser** (Hotspots), kein **Noise**. | Tukey-Boxplot univariat, Isolation Forest multivariat | offen |

**H7 ist ein Glücksfall und war mir bis eben nicht bewusst:** Detroit liefert in
99,5 % der Zeilen eine 15-stellige `census_block_2020_geoid` mit — die ersten
elf Stellen sind die Tract-GEOID, 275 Tracts, alle korrekt in Wayne County.
Damit existiert für Detroit eine **unabhängige Referenz**, gegen die sich unser
selbst gerechneter Punkt-in-Polygon-Join messen lässt. Chicago liefert nichts
Vergleichbares. Wir können den Join also an Detroit validieren und ihn danach
begründet auf Chicago anwenden — das ist deutlich stärker als ein Join, den
niemand geprüft hat.

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
| Konsistenz | Anteil Zeilen ohne Feldwiderspruch | 99,993 % (17 von 259'272) |
| Genauigkeit | Anteil verortbarer Fälle | 99,33 % |
| Aktualität | Abstand des jüngsten `updated_on` | im Manifest |

Der Verwendungszweck legt die Schwellen fest: Für eine Rate je Tract ist eine
Verortungsquote von 99,33 % gut — aber nur, solange die fehlenden 0,67 % nicht
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
  und 0,3 %. Auch die Geo-Lücke ist ungleich: 0,67 % in Chicago gegen 0,29 % in
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

---

## 3 · Der Data-Engineering-Lebenszyklus

Gefordert ist der **Entwurf**. Vieles davon existiert bereits, es ist nur nicht
unter diesen Begriffen dokumentiert. Diese Tabelle ist die Vorlage dafür.

| Phase | Was wir haben | Beleg | Lücke |
| --- | --- | --- | --- |
| **Generation** | Vier Quellsysteme: Socrata (Chicago), ArcGIS REST (Detroit), HTTPS-Dateien (TIGER), JSON-API (ACS). Je Quelle dokumentiert: Aktualisierungsverhalten, Schlüsselbedarf, Formate | Notebooks 01, 06 | Detroit-Quellnotebook, NOAA |
| **Ingestion** | Vier Pipelines. Batch, kein Streaming. Chicago inkrementell über Wasserzeichen mit 14 Tagen Rückgriff; Census als eingefrorene Vintage | `src/crime/*_pipeline/` | Wetter offen |
| **Storage** | Dateibasierte Schichten, Parquet mit festem Schema, Hive-Partitionen, unveränderliche Läufe mit Manifest | `data/`, Abschnitt 4 | Evaluation schriftlich, Silver/Gold leer |
| **Transformation** | Bronze bewusst ohne Transformation. Qualitätsanalyse für Chicago fertig | Notebook 03 | Silver und Gold komplett |
| **Serving** | – | – | **komplett offen**, siehe Abschnitt 6 |

### Unterströmungen

| Unterströmung | Was wir haben | Lücke |
| --- | --- | --- |
| **Security** | Schlüssel nur in `.env`, nie im Manifest oder in abgelegten URLs; `.env` und `data/` aus Git ausgeschlossen | Datenschutz-Abschnitt schriftlich |
| **Data Management** | Manifest je Lauf, Herkunftsnachweis über `derived_from`, unveränderliche Läufe, Schema-Fingerabdruck gegen Drift, `_extra` gegen Datenverlust | Katalog/Glossar der Felder |
| **DataOps** | 233 automatisierte Tests, alle ohne Netz und ohne Schlüssel | keine CI, keine Alarmierung |
| **Data Architecture** | Vier Schichten, gepinnte Schemata, Trennung von Beweis (raw) und Ableitung (bronze) | Architekturdiagramm |
| **Orchestration** | – | **grösste Lücke**: heute manuelle Aufrufe, keine Reihenfolge, keine Wiederholbarkeit |
| **Software Engineering** | Modulare Pakete, Typannotationen, ausführliche Docstrings, Fehlerbehandlung mit Wiederholungen | – |

**Die zwei echten Lücken sind Serving und Orchestrierung.** Für die
Orchestrierung reicht in diesem Rahmen ein bescheidener Ansatz — ein `Makefile`
oder ein Skript, das die Pipelines in der richtigen Reihenfolge aufruft und
protokolliert. Airflow oder Prefect wären für vier Batch-Läufe unangemessen; das
lässt sich in der Präsentation gut begründen.

---

## 3a · Bezug zum Modul Transformation

Die Modulinhalte lassen sich fast lückenlos auf unser Projekt abbilden. Diese
Tabelle taugt als Gliederung für den Transformationsteil der Präsentation.

| Modulinhalt | Bei uns | Stand |
| --- | --- | --- |
| **Kombination von Streams** | Alle vier Quellen sind Batch. Bewusst begründen statt weglassen: Ein Tumbling-Window ist der Batch-Fall der ereignisbasierten Verarbeitung | zu formulieren |
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

Gefordert ist **Evaluation, Wahl und Implementierung**. Implementiert ist etwas,
die Evaluation fehlt schriftlich. Vorschlag für die Argumentation:

### Anforderungen an die Speicherumgebung

1. Rohdaten unveränderlich und beweissicher ablegen
2. Spaltenorientierte Auswertung über einige Millionen Zeilen
3. Geometrien speichern und räumlich verknüpfen
4. Schemastabilität über viele Läufe hinweg
5. Ohne Serverbetrieb lauffähig, damit beide im Team lokal arbeiten können
6. Nachvollziehbar und versionierbar für die Abgabe

### Optionen

| Option | Stärken | Schwächen | Bewertung |
| --- | --- | --- | --- |
| **Parquet-Dateien mit Hive-Partitionen** (heutiger Stand) | kein Server, spaltenorientiert, offenes Format, git-freundlich in der Struktur | keine Transaktionen, kein SQL out of the box | erfüllt 1–6 |
| **PostgreSQL + PostGIS** | ausgereifter Raumbezug, echtes SQL, Transaktionen | Serverbetrieb, Einrichtung bei beiden, Rohdaten passen schlecht hinein | 5 nicht erfüllt |
| **DuckDB** | SQL direkt auf Parquet, `spatial`-Extension, eine Datei, kein Server | jung, nicht für parallele Schreiber gedacht | ergänzt die erste Option |
| **Cloud (S3, BigQuery)** | skaliert, praxisnah | Kosten, Zugänge, für 70 MB unangemessen | verworfen |

### Vorschlag

**Zweistufig:** Dateibasierte Schichten in Parquet als Speicher, **DuckDB als
Abfrageschicht** darüber. Begründung: Die Ablage bleibt offen, portabel und
unveränderlich; DuckDB liefert SQL und den räumlichen Join, ohne dass jemand
einen Server betreiben muss. Für ein Projekt dieser Grössenordnung — rund
350'000 Fälle und 6'282 Tracts — ist das angemessen, und die Wahl lässt sich
sauber gegen die Alternativen begründen.

Zu implementieren wären dann: die Silver- und Gold-Tabellen als Parquet plus
eine DuckDB-Datei mit Sichten darauf.

Siehe auch [Absprache 5.3](projektabsprache.md).

`Entscheid: ______________________________________________`

---

## 5 · Transformation Teil 1: was bis LN1 fehlt

Gefordert sind **Analyse der Datengrundlage**, **Hypothesentest** und
**initiale Datenbereinigung**.

| Schritt | Stand | Aufwand |
| --- | --- | --- |
| Datenqualität Chicago | ● fertig, 12 Prüfungen | – |
| Datenqualität Detroit | ○ offen | ~½ Tag, Notebook 03 als Vorlage |
| Datenqualität Census | ◐ im Quellnotebook enthalten | gering |
| Silver: Dedup und Typen | ○ | ~½ Tag |
| Silver: räumlicher Join auf Tracts | ○ | ~1 Tag, inklusive Umprojektion |
| NIBRS-Harmonisierung beider Städte | ◐ Chicago belegt, Detroit offen | ~1 Tag |
| Gold: Raten je Tract | ○ | ~½ Tag |
| Hypothesentest H1–H4 | ○ | ~1 Tag |

**Realistisch rund fünf Arbeitstage zu zweit** — ohne Präsentation und ohne die
Wetterquelle.

**Reihenfolge-Empfehlung:** Detroit-Qualität zuerst. Erst wenn wir die
Detroit-Daten so gut kennen wie die Chicagoer, wissen wir, ob der Vergleich
trägt. Wäre etwa der Detroit-Geoausfall ähnlich verzerrt wie der Chicagoer, aber
in anderen Kategorien, würde jeder Städtevergleich schief — und das wollen wir
vor der Auswertung wissen, nicht danach.

---

## 6 · LN2: die Serving-Entscheidung

Drei Optionen stehen zur Wahl. Der Entscheid gehört **jetzt** getroffen, obwohl
er erst für LN2 zählt: Er bestimmt, was die Gold-Schicht enthalten muss, und die
bauen wir schon für LN1.

| | Was zu liefern ist | Passt zu unseren Daten | Aufwand | Risiko |
| --- | --- | --- | --- | --- |
| **A · Analytik** | Deployment-Umgebung, z. B. Dashboard auf der Gold-Schicht | sehr gut — Gold ist ohnehin geplant | mittel | gering |
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

`Entscheid: ______________________________________________`

---

## 7 · Arbeitspakete bis LN1

| # | Paket | Ergebnis | Wer | Bis |
| --- | --- | --- | --- | --- |
| 1 | Forschungsfragen und Hypothesen festlegen | Abschnitt 2 entschieden | beide | |
| 2 | Serving-Option wählen | bestimmt das Gold-Schema | beide | |
| 3 | Problemstellung und Methodenteil schreiben | Präsentationstext | | |
| 4 | Lebenszyklus dokumentieren | Diagramm + Tabelle aus Abschnitt 3 | | |
| 5 | Storage-Evaluation verschriftlichen | Abschnitt 4 als Präsentationsteil | | |
| 6 | Datenqualität Detroit | Notebook analog 03 | | |
| 7 | Detroit-Bronze angleichen (falls beschlossen) | einheitliche Schicht | | |
| 8 | Silver: Dedup, Typen, räumlicher Join | eine Faktentabelle | | |
| 9 | NIBRS-Harmonisierung über beide Städte | gemeinsame Kategorien | | |
| 10 | Gold: Raten je Tract | Auswertungstabelle | | |
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
| Serving-Entscheid zu spät | Gold zweimal gebaut | Paket 2 in der ersten Sitzung |
| Verschiedene Datenstände im Team | widersprüchliche Zahlen | Referenzstand vereinbaren, [Absprache 7.1](projektabsprache.md) |

---

## 9 · Zusammenfassung: was in der ersten Sitzung entschieden werden muss

1. **Forschungsfragen** — FF1 bis FF3 (Data Engineering) übernehmen oder anders schneiden?
2. **Hypothesen** — H1 bis H5 als Pflicht, H6 bis H8 als Kür? Und in welcher Formulierung?
3. **Serving-Option** — A, B oder C? Bestimmt das Gold-Schema.
4. **Wetterquelle** — im Scope? Entscheidet über FF3 und H5.
5. **Storage-Begründung** — Parquet plus DuckDB, oder anders?
6. **Arbeitsteilung** — Tabelle in Abschnitt 7 ausfüllen.

Die technischen Entscheide zu Bronze, Silver und Zusammenarbeit stehen in
[`projektabsprache.md`](projektabsprache.md) und können in derselben Sitzung
mitgenommen werden.
