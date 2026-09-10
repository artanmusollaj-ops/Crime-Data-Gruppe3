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
> ist Entwurf, weil die Phase entschieden aber noch nicht gebaut ist — LN1
> verlangt für den Lebenszyklus ausdrücklich den Entwurf. Alle übrigen Kapitel
> beschreiben Umgesetztes, und wo etwas fehlt, steht es dort.

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
behaupten. **451 automatisierte Tests** laufen ohne Netzzugriff und ohne
Schlüssel.

| | |
| --- | --- |
| Chicago, Jahrgang 2024 | 259'272 Delikte |
| Detroit, Jahrgang 2024 | 88'695 Delikte |
| Census Tracts, Illinois und Michigan | 6'282, mit Geometrie und Sozialdaten |
| Wetter, zwei Stationen | 55'449 Stadt-Tage, zurück bis 1942 |

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
| **H3** | Die Deliktschlüssel beider Städte lassen sich **vollständig** auf NIBRS abbilden. | Anwendung beider Crosswalks in `silver/crime_offense` | **teilweise falsifiziert**, siehe 8.5. Chicago **100 %** zugeordnet, Detroit **95,0 %**. Aber nur **96,0 %** aller Fälle tragen ein echtes NIBRS-Delikt — 9'588 landen im Auffang `90Z`, 4'470 gar nicht |
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

### 5.2 Serving: der Entwurf

Entschieden ist **Option A · Analytik**: eine Auswertungsumgebung auf der
Gold-Schicht. Gebaut ist sie nicht; gefordert ist der Entwurf, und der folgt aus
den Entscheiden zwingend.

#### Wer konsumiert

| Konsument | Zugriff | Korn |
| --- | --- | --- |
| Dashboard (primär) | über Sichten in einer DuckDB-Datei | aggregiert |
| Ad-hoc-Auswertung im Team | SQL auf dieselben Sichten | aggregiert, bei Bedarf Silver |

Kein externer Dienst, keine API, keine Nutzerverwaltung. Das Serving endet an
der Auswertungsumgebung.

#### Was geliefert wird: zwei Gold-Tabellen, weil zwei Körner

| Tabelle | Korn | Zellen (Obergrenze) | Wofür |
| --- | --- | --- | --- |
| `fact_tract_month` | `geoid` × Monat × Kategorie | 6'282 × 12 × 22 ≈ 1,66 Mio | räumlicher Vergleich, Raten |
| `fact_city_day` | Stadt × Tag × Kategorie, plus Wetter des Tages | 2 × 366 × 22 ≈ 16'100 | Wetter braucht Tagesauflösung |

Die Obergrenzen sind theoretisch. Tatsächlich besetzt sind höchstens so viele
Zellen wie es Delikte gibt — rund 348'000 für 2024 —, realistisch deutlich
weniger, weil sich Delikte auf wenige Kategorien und Tracts konzentrieren. Die
ganze Gold-Schicht bleibt damit klein genug für eine Datei ohne Serverbetrieb;
das ist derselbe Grund, der in Kapitel 7 gegen PostgreSQL sprach.

**Kategorien.** Gruppiert wird über die 22 Kategorien aus
`config/crime_category_mapping.csv`, die als vergleichbar markiert sind. Alle 22
sind in **beiden** Städten belegt — das ist die Voraussetzung dafür, dass eine
Zelle überhaupt vergleichbar ist. Die sechs übrigen Kategorien bleiben in Silver
erhalten und sind aus Gold ausgeschlossen.

**Die zweite Tabelle folgt aus einer Spannung zwischen zwei Entscheiden.**
Variante D hält Wetter im Scope, Option A macht Gold monatlich. Eine
Monatsmittelung zerstört aber genau das Signal, das eine Wetterfrage braucht —
der Effekt eines heissen Tages überlebt sie nicht. Ohne `fact_city_day` zahlt
die Wetterquelle nur auf FF2 und H6 ein und nicht auf die Auswertung.

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
| **DataOps** | 451 Tests, alle ohne Netz und ohne Schlüssel; Schreiben über `.part` und atomares Umbenennen, sodass ein abgebrochener Lauf keinen halben Stand hinterlässt | keine CI, keine Alarmierung |
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

Vier Quellen legen Bronze als Parquet ab, Detroit als NDJSON. Ob das
zusammengeführt werden soll, ist keine Geschmacksfrage, sondern messbar.
Verglichen wurden **dieselben Daten in beiden Formaten** — Detroits Bronze-Lauf
mit 88'695 Zeilen, gelesen über DuckDB.

| Format | Grösse |
| --- | --- |
| NDJSON, wie ausgeliefert | 125,3 MB |
| NDJSON + gzip | 11,7 MB |
| **Parquet snappy** | **6,5 MB** |

| Abfrage | NDJSON | Parquet | Faktor |
| --- | --- | --- | --- |
| Zeilen zählen | 0,112 s | 0,000 s | aus den Metadaten |
| nach Kategorie gruppieren | 0,114 s | 0,001 s | 137× |
| **fünf Spalten, alle Zeilen** | **0,158 s** | **0,026 s** | **6,0×** |
| alle Spalten materialisieren | 0,790 s | 0,615 s | 1,3× |

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
heute        Bronze NDJSON            125,3 MB
getrennt     Raw    NDJSON + gzip      11,7 MB
             Bronze Parquet snappy      6,5 MB
             zusammen                   18,3 MB   → 85 % weniger
```

Messung und Methodik: [`notebooks/31_storage_evaluation.ipynb`](../notebooks/31_storage_evaluation.ipynb).
Die Messung läuft mit warmem Betriebssystem-Cache und **unterschätzt damit
Parquet**, weil der Plattenzugriff wegfällt.

### 7.4 Implementierung

```text
data/
├── raw/     unverändert, Byte für Byte wie ausgeliefert
├── bronze/  daraus abgeleitetes Parquet mit gepinntem Schema
├── silver/  gedeutet: Typen, Einheiten, Fehlwerte, harmonisierte Schlüssel
└── gold/    auswertungsfertige Aggregate (noch leer)
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
| `weather_day` | eine Stadt an einem Tag | **gebaut**, 55'449 Zeilen |
| `crime_offense` | ein Delikt | **gebaut**, 347'967 Zeilen |

`tract` verbindet TIGER-Geometrie mit ACS-Attributen. Gedeutet wird: Text zu
Zahlen, `-666666666` zu `NULL`, die Armutsquote abgeleitet — und bei Tracts ohne
Einwohner `NULL` statt einer Division durch null, wobei die absoluten Zahlen
erhalten bleiben.

`weather_day` löst die Einheiten auf. GHCN-Daily führt Temperatur und
Niederschlag in Zehnteln, Schneefall dagegen schon in Millimetern; an echten
Rekorden plausibilisiert. Ein leeres Feld wird `NULL` und **nicht** `0` — bei
Niederschlag der entscheidende Unterschied. Das Messflag `T` für Spurenmengen
bekommt eine eigene Spalte, weil `0` mit `T` nicht „trocken" heisst.

`crime_offense` ist die Tabelle, die den Vergleich trägt — 347'967 Delikte,
259'272 aus Chicago und 88'695 aus Detroit. Sie leistet drei Übersetzungen auf
einmal, und jede davon ist ein eigener Fehlerherd:

| | Chicago | Detroit |
| --- | --- | --- |
| Delikte | `iucr` → NIBRS, **100 %** der Fälle | `state_offense_code` → NIBRS, **95,0 %** |
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

Gemessen über alle 347'967 Delikte des Jahrgangs 2024:

| | Chicago | Detroit | zusammen |
| --- | ---: | ---: | ---: |
| Delikte | 259'272 | 88'695 | 347'967 |
| Quellcode im Crosswalk bekannt | **100 %** | **95,0 %** | 98,7 % |
| davon Auffang `90Z` | 7'695 | 1'893 | 9'588 |
| **mit einem echten NIBRS-Delikt** | **97,0 %** | **92,8 %** | **96,0 %** |

**Abdeckung ja, Abbildung nein.** Kein Chicago-Code fällt stillschweigend
heraus, das war die eigentliche Sorge. Aber 9'588 Fälle tragen ein Delikt, das
NIBRS nicht kennt: Verstösse gegen Registrierungspflichten, Bewährungsauflagen,
Illinois-Eigenheiten wie *Criminal Fortification*. Sie landen auf `90Z All Other
Offenses` — ein Code, der gültig ist, für einen Deliktvergleich aber nichts
aussagt.

Für Chicago ist der Anteil im Katalog viel höher als in den Fällen: **70 der 434
Katalogzeilen** sind Auffangzeilen (16,1 %), in den Falldaten nur 2,97 %. Die
Delikte ohne NIBRS-Entsprechung sind also überwiegend seltene — gut für den
Vergleich, aber gemessen und nicht angenommen.

**Detroits 4'467 offene Fälle** sind ein anderer Fall: Dort steht kein
Auffangcode, sondern gar keiner, weil Detroit in `state_offense_code` zwei
Systeme mischt — File Classes und Arrest Charge Codes. Die 23 betroffenen Codes
sind benannt; der Weg dorthin führt über Arrest Charge → File Class → NIBRS.

**Was die Tabelle über die Hypothese hinaus zeigt.** Zum ersten Mal lassen sich
beide Städte nebeneinanderstellen, ohne dass eine Zahl etwas anderes bedeutet
als die daneben:

| NIBRS | Delikt | Chicago | Detroit |
| --- | --- | ---: | ---: |
| `13B` | Simple Assault | 53'977 | 15'894 |
| `23H` | All Other Larceny | 38'597 | 4'171 |
| `290` | Destruction/Damage/Vandalism | 28'596 | 11'782 |
| `240` | Motor Vehicle Theft | 22'101 | 8'517 |
| `13A` | Aggravated Assault | 16'088 | 8'071 |

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
python -m pytest                       # erwartet 451 bestandene Tests
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
| **Der Städtevergleich selbst** | `src/crime/silver_pipeline/build_crime_offense.py` → `data/silver/dataset=crime_offense/` |
| Tests | `tests/`, nach Pipeline gegliedert |
| Quelle Chicago erklärt | [`notebooks/01_chicago_source.ipynb`](../notebooks/01_chicago_source.ipynb) |
| Chicago-Ingestion vorgeführt | [`notebooks/02_chicago_bronze_ingestion.ipynb`](../notebooks/02_chicago_bronze_ingestion.ipynb) |
| Datenqualität Chicago | [`notebooks/03_chicago_data_quality.ipynb`](../notebooks/03_chicago_data_quality.ipynb) |
| Detroit-Ingestion vorgeführt | [`notebooks/05_detroit_bronze_ingestion.ipynb`](../notebooks/05_detroit_bronze_ingestion.ipynb) |
| Quelle Census erklärt | [`notebooks/21_census_source.ipynb`](../notebooks/21_census_source.ipynb) |
| Quelle Wetter erklärt | [`notebooks/22_weather_source.ipynb`](../notebooks/22_weather_source.ipynb) |
| Storage-Messung | [`notebooks/31_storage_evaluation.ipynb`](../notebooks/31_storage_evaluation.ipynb) |
| Referenzquelle NIBRS, Mapping-Herkunft | [`notebooks/32_nibrs_source.ipynb`](../notebooks/32_nibrs_source.ipynb) |
| Technische Entscheide | [`projektabsprache.md`](projektabsprache.md) |
| Anforderungen gegen Stand | [`leistungsnachweise.md`](leistungsnachweise.md) |
| Detroit-Pipeline im Detail | [`DETROIT_PIPELINE_ANLEITUNG.md`](DETROIT_PIPELINE_ANLEITUNG.md) |
| **NIBRS-Codeliste, amtlich** | `config/nibrs_offense_codes_2025.csv` — 81 Codes aus Anhang A von [`nibrs_technical_specification_2025.pdf`](nibrs_technical_specification_2025.pdf) |
| IUCR nach NIBRS (Chicago) | `config/iucr_nibrs_mapping.csv`, erzeugt von [`tools/build_iucr_nibrs_mapping.py`](../tools/build_iucr_nibrs_mapping.py); Katalog vom [Datenportal der Stadt](https://data.cityofchicago.org/resource/c7ck-438e.json) |
| MICR nach NIBRS (Detroit) | `config/micr_nibrs_mapping.csv`, Quellen [`micr_manual_1110_2024.pdf`](micr_manual_1110_2024.pdf) und [`micr_appendix_f_2009.pdf`](micr_appendix_f_2009.pdf) |
| Codetabelle Illinois State Police | [`isp_nibrs_code_table_2026.xlsx`](isp_nibrs_code_table_2026.xlsx) — nach ILCS-Statut geschlüsselt, **nicht** als Crosswalk verwendbar, siehe 8.5 |

---

## Offen für LN1

Damit dieses Dokument vollständig ist, fehlen:

- **Entscheid über Forschungsfragen und Hypothesen** (Kapitel 3) — er bestimmt,
  was in Gold gehört
- **Ein Notebook, das den Vergleich rechnet.** `crime_offense` liegt vor, die
  Zahlen je NIBRS-Code stehen im Manifest — aber die Rate je Einwohner, für die
  es `tract` als Nenner braucht, gehört nach Gold und fehlt noch
- **Ein Notebook, das die Hypothesen rechnet** — die Zahlen zu H1, H2 und H5
  liegen heute in Notebook 03, H7 in 8.4; ein eigenes Notebook fehlt
- **Die letzten 5 % von Detroit** — beide Seiten von H3 sind gemessen (8.5),
  aber 4'467 Detroit-Fälle tragen einen Arrest Charge Code statt einer File
  Class und bleiben ohne NIBRS-Delikt. Der Weg dorthin führt über
  Arrest Charge → File Class → NIBRS
- **Das Detroit-Quellnotebook**
