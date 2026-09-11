# Juni und der 9. November

Chicago und Detroit, Jahrgang 2024. Fünf Deliktarten, zwei Zeitfenster — und ein
Samstag, der in beiden Städten dasselbe Muster zeigt.

Erstellt: 2026-09-11, nach der Crosswalk-Korrektur aus
[`ABGLEICH_ARTAN_2026-09-11.md`](ABGLEICH_ARTAN_2026-09-11.md).
Interaktive Fassung: <https://claude.ai/code/artifact/0037cd3c-f112-4e8c-94ad-a0551dce3dfe>

## Was verglichen wird

Gefragt waren **Assault**, **Stolen Vehicle** und **Fraud** — Detroits eigene
Kategorienamen, die Chicago nicht kennt. Vergleichbar werden sie erst über
NIBRS, den nationalen Standard, auf den beide Städte in `silver/crime_offense`
abgebildet sind.

Körperverletzung ist dabei **drei** Delikte, nicht eines:

| NIBRS | Was es meint | Chicago 2024 | Detroit 2024 |
| --- | --- | ---: | ---: |
| `13A` Aggravated Assault | Angriff mit Waffe oder schwerer Verletzung | 16 088 | 8 073 |
| `13B` Simple Assault | Angriff ohne Waffe, keine schwere Verletzung | 38 857 | 15 889 |
| `13C` Intimidation | Drohung **ohne** Berührung | 19 338 | 1 235 |
| `240` Motor Vehicle Theft | KFZ-Diebstahl | 22 101 | 8 511 |
| `26A`–`26G` | Betrug | 13 490 | 5 261 |

Die Trennung von `13B` und `13C` ist keine Feinheit: In Illinois ist *Assault*
die Drohung und *Battery* die Berührung. Eine frühere Fassung warf beides
zusammen; die Korrektur verschob 15 120 Chicago-Fälle.

Chicago hat rund **vier Mal so viele Einwohner** wie Detroit. Alle Raten beziehen
sich auf 100 000 Einwohner, gerechnet aus den Census-Tracts mit Delikten —
2 949 082 für Chicago, 738 065 für Detroit.

## Juni 2024

Der Juni ist **Chicagos stärkster Monat des Jahres** (334,5 Fälle pro Tag über
alle fünf Kategorien). Für Detroit gilt das nicht — dort liegt die Spitze im
Mai, der Juni fällt hinter Mai und September zurück.

| Kategorie | Chicago | pro Tag | je 100k | Detroit | pro Tag | je 100k |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `13A` schwer | 1 612 | 53,7 | 54,7 | 713 | 23,8 | **96,6** |
| `13B` einfach | 3 511 | 117,0 | 119,1 | 1 414 | 47,1 | **191,6** |
| `13C` Drohung | 1 656 | 55,2 | **56,2** | 88 | 2,9 | 11,9 |
| `240` KFZ | 2 084 | 69,5 | 70,7 | 748 | 24,9 | **101,3** |
| `26x` Betrug | 1 171 | 39,0 | 39,7 | 391 | 13,0 | **53,0** |

**Detroit liegt je Einwohner in vier von fünf Kategorien vorn**, am deutlichsten
bei schwerer Körperverletzung: 96,6 gegen 54,7 — fast das Doppelte.

**Die Ausnahme ist Bedrohung, und sie ist verdächtig.** Chicago zählt 56,2 je
100 000, Detroit 11,9 — ein Faktor 4,7 gegen die Richtung aller anderen Zahlen.
Das ist vermutlich kein Unterschied im Geschehen, sondern in der Erfassung:
Chicagos `13C` speist sich aus vier Quellcodes (`0560` Assault, `2820`
Telefondrohung, `3960` Intimidation, Stalking), Detroits aus einem einzigen
(`1303`). Vor einer inhaltlichen Deutung gehört das geprüft.

## Samstag, 9. November 2024

In der Summe unauffällig: Rang 230 von 366 Tagen in Chicago. Wer nur die
Gesamtzahl ansieht, übersieht den Tag. Die Zusammensetzung nicht — verglichen
wird gegen die übrigen 51 Samstage, nicht gegen alle Tage.

| Kategorie | Chicago | Sa-Median | Rang | Detroit | Sa-Median | Rang |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `13A` schwer | **56** | 46 | **10 / 52** | **33** | 24 | **8 / 52** |
| `13B` einfach | 101 | 115 | 40 / 52 | 45 | 48 | 33 / 52 |
| `13C` Drohung | 46 | 50 | 31 / 52 | 6 | 3 | 3 / 51 |
| `240` KFZ | 53 | 66 | 42 / 52 | **13** | 22 | **51 / 52** |
| `26x` Betrug | 33 | 31 | 17 / 52 | 15 | 10 | 10 / 52 |

**In beiden Städten gleichzeitig: viel schwere Körperverletzung, auffallend wenig
KFZ-Diebstahl.** Detroit hatte beim Fahrzeugdiebstahl den zweitschwächsten
Samstag des ganzen Jahres.

Das Wetter erklärt es nicht: in beiden Städten 13,3 °C Tagesmaximum, in Chicago
5,1 mm Niederschlag, in Detroit keiner.

**Wie bemerkenswert ist die Gleichzeitigkeit?** Wären die Städte unabhängig,
läge die Wahrscheinlichkeit, dass beide bei schwerer Körperverletzung unter die
besten zehn Samstage fallen, bei rund 4 %. Auffällig, aber kein Beweis — bei 52
Samstagen und fünf Kategorien findet man solche Zufälle. *Ein* Tag trägt keine
Aussage.

## Was der Befund über die Plattform sagt

Diese Frage war bis vor Kurzem nicht stellbar. Chicago und Detroit zählten unter
verschiedenen Schlüsseln, auf verschiedenen Zeitachsen und in verschiedenen
Raumeinheiten.

Dass hier überhaupt eine Gleichzeitigkeit sichtbar wird, hängt an drei
Übersetzungen, die alle drei nötig waren: die Delikte über NIBRS, die Zeit über
die **Ortszeit** beider Städte, der Raum über Census Tracts.

Die zweite ist die unauffälligste. Hätte Detroits Abfragefenster weiter in UTC
statt in Ortszeit gestanden, lägen 66 Fälle aus 2023 im Jahrgang — und der
9. November hätte in Detroit fünf Stunden zu früh begonnen.

## Grenzen

- **Ein Jahr, ein Monat, ein Tag.** Daraus folgt kein Muster. Der Bericht
  beschreibt, was in den Daten steht, nicht warum.
- **Der Nenner ist eine Näherung.** Gerechnet wird mit der Einwohnerzahl der
  Tracts mit Delikten. Für einen Vergleich *zwischen* den Städten brauchbar, als
  absolute Rate nicht.
- **Detroits Abdeckung ist inzwischen 100 %.** Die 1 647 Fälle, die zum Zeitpunkt
  dieses Berichts fehlten, sind seither über Detroits eigene Felder angeschlossen
  (Konzept 8.5). Sie gehen nach `23C Shoplifting` und `90Z` und berühren keine der
  drei hier untersuchten Kategorien; die Zahlen des Berichts bleiben gültig.
- **`13C` ist zwischen den Städten nicht vergleichbar**, siehe oben.
- **Anzeigeverhalten ist nicht Kriminalität.** Beide Datensätze zählen gemeldete
  Delikte.
- **Deliktkorn, nicht Fallkorn.** Gezählt werden Deliktzeilen. Für „wie viele
  Fälle" wäre über `event_id` zu deduplizieren.

## Grundlage

`silver/crime_offense`, 347 957 Delikte des Jahrgangs 2024, abgefragt über
`data/serving/analyse.duckdb`. Chicago aus drei Bronze-Läufen (Socrata
`ijzp-q8t2`, Stand 6.9.2026), Detroit aus dem Full Load vom 11.9.2026 (ArcGIS
`RMS_Crime_Incidents`). Deliktzuordnung über `config/iucr_nibrs_mapping.csv` und
`config/micr_nibrs_mapping.csv` gegen die NIBRS Technical Specification 2025.
Wetter aus `silver/weather_day` (NOAA GHCN-Daily).
