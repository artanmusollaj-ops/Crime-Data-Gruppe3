# NIBRS als gemeinsame Klassifikation für Chicago und Detroit

## Ziel

Für das CAS-Data-Engineering-Projekt sollen die Kriminalitätsdaten von **Chicago** und **Detroit** trotz unterschiedlicher Quellsysteme vergleichbar gemacht werden.

Die Grundidee ist:

```text
Chicago ──→ NIBRS ←── Detroit
```

NIBRS dient dabei als gemeinsame, standardisierte Klassifikation für Straftaten.

---

## 1. Rohdaten unverändert übernehmen – Bronze Layer

Zuerst werden die Daten beider Städte so übernommen, wie sie von der jeweiligen Quelle geliefert werden.

### Chicago

Beispielhafte Felder:

```text
id
date
iucr
primary_type
description
fbi_code
latitude
longitude
```

### Detroit

Beispielhafte Felder:

```text
incident_id
offense_id
state_offense_code
offense_description
offense_category
latitude
longitude
```

In diesem Schritt werden die Daten **nicht vereinheitlicht**.

Die Bronze-Schicht bildet die ursprünglichen Quelldaten ab:

```text
data/
└── bronze/
    ├── chicago/
    └── detroit/
```

**Prinzip:**

> Bronze = unveränderte Source Truth.

---

## 2. Unterschiedliche Klassifikationssysteme verstehen

Chicago und Detroit verwenden unterschiedliche Systeme zur Beschreibung von Straftaten.

### Chicago

Chicago verwendet unter anderem:

```text
IUCR
FBI Code
primary_type
description
```

### Detroit

Detroit verwendet unter anderem:

```text
MICR / state_offense_code
offense_category
offense_description
```

Ein direkter Vergleich der Codes ist deshalb nicht möglich.

Beispiel:

```text
Chicago:
IUCR = 0820
Primary Type = THEFT

Detroit:
state_offense_code = 23005
Description = Larceny - Theft from Motor Vehicle
```

Die beiden Codes

```text
0820
23005
```

stammen aus unterschiedlichen Klassifikationssystemen und können nicht direkt miteinander verglichen werden.

---

## 3. NIBRS als gemeinsame Sprache verwenden

Anstatt Detroit auf das Chicago-System abzubilden, werden beide Quellen auf einen gemeinsamen Standard transformiert:

```text
Chicago ──→ NIBRS ←── Detroit
```

NIBRS kann dabei als gemeinsame semantische Sprache verstanden werden.

Beispiel für Detroit:

```text
Detroit MICR 23005
        ↓
NIBRS 23F
        ↓
Theft From Motor Vehicle
```

Chicago kann über einen eigenen Crosswalk ebenfalls auf einen passenden NIBRS-Code abgebildet werden.

Das Prinzip ist vergleichbar mit einer Übersetzung:

```text
Deutsch ──→ Englisch ←── Französisch
```

statt direkt:

```text
Deutsch ──→ Französisch
```

---

## 4. Referenz- und Mapping-Tabellen verwenden

Die Zuordnung zwischen den lokalen Codes und NIBRS sollte als separate Referenzdatei gespeichert werden.

### Detroit

Beispiel:

```text
micr_code | nibrs_code | nibrs_description
----------|------------|--------------------------
23005     | 23F        | Theft From Motor Vehicle
24001     | 240        | Motor Vehicle Theft
22001     | 220        | Burglary
```

### Chicago

Beispiel:

```text
iucr | nibrs_code | nibrs_description
-----|------------|--------------------------
.... | 23F        | Theft From Motor Vehicle
.... | 240        | Motor Vehicle Theft
.... | 220        | Burglary
```

Mögliche Ablage im Repository:

```text
config/
└── reference/
    ├── chicago_iucr_nibrs.csv
    └── detroit_micr_nibrs.csv
```

Die Zuordnung sollte möglichst **nicht hart im Python-Code programmiert** werden.

Ungünstig:

```python
if offense == "THEFT":
    category = "23F"
```

Besser:

```python
df.merge(mapping_table)
```

Damit werden die Regeln:

- nachvollziehbar
- versionierbar
- testbar
- austauschbar
- dokumentierbar

---

## 5. Detroit von Bronze nach Silver transformieren

Beispiel eines Detroit-Datensatzes im Bronze Layer:

```text
incident_id = D123
state_offense_code = 23005
offense_description = LARCENY FROM VEHICLE
```

Die Referenztabelle liefert:

```text
23005 → 23F → Theft From Motor Vehicle
```

Im Silver Layer könnte daraus entstehen:

```text
incident_id                 D123

source_system               MICR
source_offense_code         23005
source_offense_description  LARCENY FROM VEHICLE

nibrs_code                  23F
nibrs_description           Theft From Motor Vehicle
nibrs_group                 A
crime_against               PROPERTY
```

Wichtig ist, dass die Originalwerte erhalten bleiben.

Der lokale Quellcode:

```text
source_offense_code
```

wird nicht durch:

```text
nibrs_code
```

ersetzt.

Stattdessen werden beide Werte gespeichert.

Dadurch bleibt die **Provenienz** der Daten erhalten.

---

## 6. Chicago ebenfalls nach NIBRS transformieren

Ein Chicago-Datensatz könnte beispielsweise so aussehen:

```text
id = C987
iucr = 0820
primary_type = THEFT
description = $500 AND UNDER
fbi_code = 06
```

Nach der Transformation könnte daraus beispielsweise werden:

```text
incident_id                 C987

source_system               IUCR
source_offense_code         0820
source_offense_description  $500 AND UNDER

nibrs_code                  23H
nibrs_description           All Other Larceny
nibrs_group                 A
crime_against               PROPERTY
```

Damit behalten Chicago und Detroit ihre unterschiedlichen lokalen Codes:

```text
Chicago                           Detroit

0820                              23005
│                                 │
▼                                 ▼
23H                               23F
All Other Larceny                 Theft From Motor Vehicle
```

Beide Datensätze verwenden danach aber dieselbe NIBRS-Systematik.

---

## 7. Gemeinsames kanonisches Silver-Schema

Nach der Transformation können beide Städte in einem gemeinsamen Schema abgelegt werden.

Beispiel:

```text
city       incident_id  source_code  nibrs_code  crime_against
---------  -----------  -----------  ----------  -------------
Chicago    C001         0820         23H         PROPERTY
Chicago    C002         1310         13B         PERSON
Detroit    D001         23005        23F         PROPERTY
Detroit    D002         13002        13A         PERSON
```

Damit werden gemeinsame Analysen möglich.

Zum Beispiel:

```sql
SELECT
    city,
    nibrs_code,
    COUNT(*)
FROM crime_incidents
GROUP BY city, nibrs_code;
```

Oder:

```sql
SELECT
    city,
    crime_against,
    COUNT(*)
FROM crime_incidents
GROUP BY city, crime_against;
```

Damit können beispielsweise:

```text
Chicago PROPERTY crimes
vs.
Detroit PROPERTY crimes
```

auf Basis derselben Terminologie verglichen werden.

---

## 8. Gesamtprozess

```text
       CHICAGO                    DETROIT
          │                          │
          ▼                          ▼
       Bronze                     Bronze
     original data              original data
          │                          │
          │                          │
     IUCR mapping               MICR mapping
          │                          │
          └──────────┐    ┌──────────┘
                     ▼    ▼
                      NIBRS
                        │
                        ▼
                     SILVER
              common canonical schema
                        │
                        ▼
                      GOLD
                  analysis datasets
```

---

## 9. Bedeutung der einzelnen Schichten

### Bronze

Frage:

> Was hat uns die Quelle geliefert?

Eigenschaften:

- unveränderte Rohdaten
- lokale Quellcodes bleiben erhalten
- gute Nachvollziehbarkeit
- Basis für erneute Transformationen

### Silver

Frage:

> Was bedeuten diese Daten in einem gemeinsamen Modell?

Eigenschaften:

- vereinheitlichte Feldnamen
- NIBRS als gemeinsame Klassifikation
- Originalwerte bleiben zusätzlich erhalten
- Datenqualitätsregeln werden angewendet
- semantische Harmonisierung zwischen Chicago und Detroit

### Gold

Frage:

> Welche Informationen benötigen wir für Analyse, Reporting oder ML?

Mögliche Gold-Datensätze:

```text
crime_by_neighborhood
crime_by_hour
crime_by_category
violent_crime_rate
property_crime_rate
crime_trends
```

---

## 10. Warum dieser Ansatz aus Data-Engineering-Sicht sinnvoll ist

Der wichtigste Punkt ist, dass die Transformation nicht nur aus einer technischen Formatänderung wie:

```text
CSV → Parquet
```

besteht.

Stattdessen wird eine echte **semantische Transformation** durchgeführt:

```text
heterogene lokale Klassifikationen
              ↓
         Standardisierung
              ↓
             NIBRS
              ↓
      gemeinsames Datenmodell
```

Damit demonstriert das Projekt zentrale Data-Engineering-Themen:

- Data Ingestion
- Data Transformation
- Schema Harmonisation
- Semantic Mapping
- Reference Data
- Data Quality
- Data Provenance
- Reproducibility
- Canonical Data Models
- Serving für Analytics oder Machine Learning

NIBRS übernimmt dabei die Rolle einer **semantischen Interoperabilitätsschicht** zwischen Chicago und Detroit.

---

## 11. Empfohlene Regel für das Projekt

Eine wichtige Designregel sollte lauten:

> Originale Source-Klassifikationen niemals überschreiben. Standardisierte Klassifikationen werden zusätzlich gespeichert.

Beispiel:

```yaml
offense:
  source:
    system: "MICR"
    code: "23005"
    description: "Larceny - Theft from Motor Vehicle"

  nibrs:
    code: "23F"
    description: "Theft From Motor Vehicle"
    group: "A"
    crime_against: "PROPERTY"
```

Damit bleibt jederzeit nachvollziehbar:

```text
Woher kam die Klassifikation?
        ↓
Wie wurde sie standardisiert?
        ↓
Wie wird sie analytisch verwendet?
```

Das ist eine gute Grundlage für den weiteren Aufbau des Chicago-/Detroit-Datenmodells.
