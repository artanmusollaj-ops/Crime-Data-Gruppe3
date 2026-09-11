# Abgleich: Artans Vergleichsbericht gegen unsere Silver-Schicht

Erstellt: 2026-09-11. Gegenstand ist
[`CHICAGO_DETROIT_VERGLEICH_2024.md`](CHICAGO_DETROIT_VERGLEICH_2024.md), den Artan
aus dem gelieferten ZIP und den Live-APIs erstellt hat. Verglichen wird er gegen
`silver/crime_offense`, abgefragt über `data/serving/analyse.duckdb`.

**Ergebnis vorweg:** Die Zahlen decken sich, jede Abweichung ist erklärt — und
Artan hat einen echten Fehler in unserem Chicago-Crosswalk gefunden. Er ist
korrigiert.

## 1. Die beiden Berichte zählen Verschiedenes

| | Artans Bericht | unsere Silver-Schicht |
| --- | --- | --- |
| Datenstand | Live-APIs, 11.9.2026 | Bronze-Läufe 5./6.9. (Chicago), 11.9. (Detroit) |
| Hauptkennzahl | eindeutige **Fallnummer** (`case_number` / `report_number`) | eindeutige **Deliktzeile** (`offense_id`) |
| Detroit `UNFOUNDED` | ausgeschlossen | enthalten, über `unfounded` gekennzeichnet |
| Detroit-Zeitfenster | UTC-Filter, DST-korrekt gewählt | `occurred_date_local`, Ortszeit |

Beide Körner sind richtig; sie beantworten verschiedene Fragen. Absprache 5.2
legt für `crime_offense` ausdrücklich das Deliktkorn fest, weil Detroit die
1:n-Beziehung mitliefert. Artans Hinweis, dass Unterkategorien nicht blind zur
Gesamtfallzahl addiert werden dürfen, gilt für unsere Tabelle genauso.

Sein Detroit-Fenster ist bemerkenswert: Juni `04:00Z`, 9. November `05:00Z` — er
hat die Sommerzeit von Hand richtig aufgelöst. Genau das, was unsere Ingestion
seit dem Zeitzonen-Fix automatisch tut.

## 2. Detroit: deckungsgleich

Sobald man seinen `UNFOUNDED`-Filter anlegt, stimmt jede Zahl:

| Juni 2024 | Artan | wir | wir ohne `UNFOUNDED` |
| --- | ---: | ---: | ---: |
| Aggravated Assault `13A` | 713 | 713 | **713** |
| Simple Assault `13B` | 1412 | 1414 | **1412** |
| Intimidation `13C` | 88 | 88 | **88** |
| KFZ-Diebstahl `240` | 748 | 748 | **748** |
| Brandstiftung `200` | 40 | 40 | **40** |

Am 9. November dasselbe Bild; seine 12 KFZ-Fälle gegen unsere 13 sind die eine
`UNFOUNDED`-Zeile, die er selbst benennt.

Auch seine Detailangaben stimmen auf den Fall genau: Brandstiftung `2000` → 32
und `2099` → 8, Chicago `1206` → 38, `1750` → 31, `0485`+`0495` → 58.

**Nebenbei bestätigt das unsere Arrest-Charge-Erweiterung:** Acht der 40
Detroit-Brandstiftungen im Juni kommen aus `2099`, einem Arrest Charge Code. Ohne
die Erweiterung fehlten sie.

## 3. Chicago: Quelldrift, kein Fehler

Im Juni liegen wir bei `13A` und `13B` um je einen Fall tiefer. Gegen Chicagos
Live-API geprüft:

| Juni 2024 | Artan (11.9.) | Live-API heute | unser Bronze-Stand (6.9.) |
| --- | ---: | ---: | ---: |
| `13A` | 1613 | **1613** | 1612 |
| `13B` (alte Zuordnung) | 4800 | **4800** | 4799 |
| Quellzeilen gesamt | 23 245 | **23 245** | — |

Chicago hat zwischen dem 6. und 11. September zwei Juni-Fälle nachgemeldet. Am
9. November stimmen wir punktgenau überein — ein einzelner Tag bekam keine
Nachmeldung. Das ist dasselbe Verhalten, das H2 für die Delta-Läufe beschreibt.

## 4. Der Befund: `0560` war falsch zugeordnet

Artan schreibt, Chicagos `0560 ASSAULT / SIMPLE` → `13B` brauche einen
verifizierten Crosswalk, und nennt 1 319 betroffene Juni-Zeilen. **Er hat recht,
und der Beleg lag im Repository.**

Die ILCS-Tabelle der Illinois State Police
(`docs/isp_nibrs_code_table_2026.xlsx`) enthält zwei Zeilen der 13er-Familie,
deren Wortlaut wirklich zu Chicagos Katalog passt:

| ILCS | Wortlaut | I-UCR | IBR |
| --- | --- | --- | --- |
| `720-5/12-3` | Battery | `0460` | `13B` |
| `720-5/12-1` | **Assault** | `0560` | **`13C`** |

Bei allen übrigen greift der Statut-Versatz aus Konzept 8.5 — dort ist der Join
wertlos. Hier nicht: Chicago nennt `0460` „BATTERY / SIMPLE" und `0560`
„ASSAULT / SIMPLE", beides deckt sich mit dem ILCS-Wortlaut.

Die Sache ist auch inhaltlich klar. Illinois trennt **Assault** (die Drohung,
ohne Berührung, 720 ILCS 5/12-1) von **Battery** (die Berührung, 5/12-3). NIBRS
trennt genauso: `13C Intimidation` ist die Drohung, `13B Simple Assault` der
Angriff. Wir hatten beides auf `13B` geworfen.

### Tragweite

| Chicago, Jahrgang 2024 | vorher | nachher |
| --- | ---: | ---: |
| `13B` Simple Assault | 53 977 | **38 857** |
| `13C` Intimidation | 4 218 | **19 338** |
| Verhältnis `13B` Chicago : Detroit | 3,40 : 1 | **2,45 : 1** |

15 120 Fälle, 28 % von Chicagos einfacher Körperverletzung.

### Was geändert wurde

- `0560` → `13C`, mit der ISP-Zeile als Beleg in
  [`tools/build_iucr_nibrs_mapping.py`](../tools/build_iucr_nibrs_mapping.py).
- `0545` und `0554` bleiben bei `13B`, sind aber jetzt als `nibrs_ermessen`
  markiert. Sie folgen derselben Logik — Chicago führt beide unter ASSAULT —,
  aber die ILCS-Tabelle kennt zu diesen Kürzeln keine Zeile. Ohne Beleg wird
  nicht umgebucht, sondern benannt. Betrifft 458 Fälle im Jahr.
- Zwei Tests halten beides fest, samt Herkunft des Belegs.

## 5. Seine übrigen Punkte

| Punkt | Bewertung |
| --- | --- |
| ASSAULT ist keine identische Quellkategorie; Chicago enthält BATTERY | **richtig**, und genau deshalb läuft der Vergleich über NIBRS statt über Kategorienamen |
| `1750` Child Abuse → `13B` ist Ermessen | **richtig**, so ist es in der Tabelle markiert |
| `0485` / `0495` prüfen: Alter oder Schutzstatus beweisen keine Waffe | **geprüft, bleibt `13A`.** Die ISP-Tabelle führt `0495` als *„Aggravated Battery – Great Bodily Harm or Permanent Disability or Disfigurement Person 60 YOA or Older"* und `0485` entsprechend für Kinder unter 13 — beide Statute verlangen **zusätzlich** schwere Körperverletzung, beide → `13A` |
| `1206` Mietfahrzeug → `240` ist Ermessen, 38 Juni-Fälle | **richtig**, so markiert |
| Detroit `2401` trennt Pkw/Lkw/Motorrad nicht | **richtig**, deshalb ist nur die breite Kategorie vergleichbar |
| Brandstiftung: Versuche einbeziehen, `1030`/`1035` sind Besitz | **richtig**, `1030`/`1035` liegen bei uns auf `520` Waffendelikt |
| `5003` zu unspezifisch | **offen** — bei uns auf `200`, das gehört nachgeprüft |
| Detroit-Textwidersprüche, Flag `SOURCE_CODE_DESCRIPTION_CONFLICT` | **richtig und noch offen**; Notebook 32 zeigt dasselbe Muster (55 von 97 Codes tragen mehrere Beschreibungen) |

## 6. Was offen bleibt

1. **`0545` und `0554`** — ohne ILCS-Zeile nicht entscheidbar.
2. **`5003` OTHER ARSON / EXPLOSIVE INCIDENT** → `200`, von Artan zu Recht als
   zu unspezifisch beanstandet.
3. **Ein Quality-Flag für Detroits Code-Text-Widersprüche**, wie er vorschlägt.
4. **Eine Zählsicht auf Fallnummer** neben dem Deliktkorn. Seine Kennzahl ist
   für „wie viele Fälle" die richtige; `crime_offense` liefert sie heute nicht
   fertig, `event_id` ist aber vorhanden.

## 7. Bemerkung zur Methode

Artans Bericht hat einen Fehler gefunden, den keine unserer Prüfungen gefunden
hat — weder die 504 Tests noch die Semantikprüfung aus Konzept 8.5. Der Grund:
Alle unsere Prüfungen vergleichen die Zuordnung mit **Chicagos eigener
Beschreibung**, und die sagt „ASSAULT / SIMPLE". Erst wer die Rechtslage dahinter
kennt, sieht, dass „Assault" in Illinois etwas anderes heisst als im
Alltagssprachgebrauch.

Das ist dieselbe Fehlerklasse wie in Konzept 8.5, eine Ebene tiefer:
nicht gleiche Form mit anderer Bedeutung, sondern **gleiches Wort mit anderer
Bedeutung**.

---

## 8. Nachtrag: die Gegenprobe systematisch gemacht

Artans Fund warf die Frage auf, ob sich das nicht als Test bauen liesse. Das
Problem: Alle unsere bisherigen Tests vergleichen die Zuordnung mit **Chicagos
eigener Beschreibung** — und nach diesem Massstab war `ASSAULT / SIMPLE → 13B`
richtig. Nur eine unabhängige Quelle kann das aufdecken, und davon gibt es
genau eine: die ILCS-Tabelle der Illinois State Police.

Sie war schon einmal als Test im Repository und wurde entfernt (PR #23), weil
sie dort als pauschale Bestätigung benutzt wurde — falsch, denn sie ist nach
Statut geschlüsselt. Mit einem **semantischen Tor** davor trägt sie: verglichen
wird nur, wo sich der ILCS-Wortlaut mit Chicagos Beschreibung deckt.

| | |
| --- | ---: |
| Chicago-Codes mit deckender ISP-Zeile | **111** von 432 |
| stimmten überein | 97 |
| wichen ab | **14** |

### Was aus den 14 wurde

**Sechs umgebucht, der ISP folgend:**

| IUCR | Fälle | | vorher | jetzt | Grund |
| --- | ---: | --- | --- | --- | --- |
| `1185` | 33 | Deceptive Collection Practices | `26A` | **`26C`** | Statut ist *False Representation as Person Authorized to Enforce the Law* |
| `1573` | 10 | Criminal Sexual Abuse – Penetration | `11A` | **`36B`** | ISP bezieht es auf `11-1.50(b)`: Täter unter 17, Opfer 9–17 |
| `4740` | 1 | Unlawful Use of Body Armor | `520` | **`90Z`** | Körperschutz ist keine Waffe |
| `1574` | 1 | Fornication | `90Z` | **`90C`** | ISP ist spezifischer als der Auffang |
| `4810` | 0 | Compounding a Crime | `90Z` | **`510`** | Geld dafür nehmen, eine Tat nicht anzuzeigen |
| `1531` | 0 | Juvenile Pimping | `40B` | **`64A`** | ISP: `11-14.4` Promoting Juvenile Prostitution |

Zusammen 45 Fälle — gegen `0560` mit 15 120 ein Feinschliff.

**`1531` löste dabei eine Frage, die seit dem Aufbau des MICR-Crosswalks offen
war:** ob Minderjährigkeit allein Menschenhandel begründet. Die ISP-Tabelle
antwortet differenziert — **Fördern** einer minderjährigen Prostituierten ist
`64A`, **Freier sein** bleibt `40C` (`11-18.1(a)`). `1521` folgt `1531` als
Schlussfolgerung, weil Illinois beide 2013 in `11-14.4` zusammenfasste; die ISP
kennt zu dem Kürzel keine Zeile, deshalb bleibt es als Ermessen markiert.
`1526` ist damit **belegt** statt Ermessen.

**Acht bleiben als begründete Abweichung stehen:**

| IUCR | wir | ISP | warum wir abweichen |
| --- | --- | --- | --- |
| `0810`, `0820` | `23H` | `26A`/`23C` | ISP-Zeilen sind Retail-Theft-Statute, Chicago meint einfachen Diebstahl |
| `1505` | `40B` | `40A` | ISP-Zeile ist das Grunddelikt, Chicagos Call Operation die Förderung |
| `1030` | `520` | `90Z` | die Definition von `520` nennt *explosives, incendiary devices* ausdrücklich |
| `1145`, `1147` | `280` | `26E` | `280` ist wörtlich das Verkaufen in Kenntnis der Herkunft; beim Hehlen wird der Käufer nicht getäuscht |
| `3920` | `90Z` | `210` | `210` verlangt eine Drohung, Amtsmissbrauch hat die nicht zwingend |
| `4750` | `90Z` | `90F` | `90F` setzt ein Familienmitglied voraus |

### Der Test

`test_abweichungen_von_der_landespolizei_sind_begruendet` verlangt **nicht**
Übereinstimmung — dafür ist die Tabelle zu sehr nach Statut geschlüsselt. Er
verlangt, dass die Menge der Abweichungen genau der dokumentierten entspricht,
jede mit Begründung. Eine neue Abweichung lässt ihn fallen.

Genau das hat bei `0560` gefehlt: Der Code wäre auf der Liste gelandet, und
jemand hätte aufschreiben müssen, warum wir von der Landespolizei abweichen.
Dabei wäre aufgefallen, dass wir es nicht können.

**Gegenprobe:** Setzt man `0560` zurück auf `13B`, meldet der Test

```
neu abweichend: {'0560': ('13B', '13C')}
```

### Was er nicht leistet

Er deckt **111 von 432 Codes ab, also 26 %**, und für Detroit nichts — dort ist
der MICR-Test die Entsprechung. In der 13er-Familie hatten nur `0460` und `0560`
eine passende ISP-Zeile; ein falsches `051A` fände er nicht. Es ist kein Netz,
sondern ein zweites Augenpaar auf dem Viertel der Tabelle, das die Landespolizei
selbst beurteilt hat.
