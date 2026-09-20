# Vier Arten zu zählen

Dieselbe Tabelle beantwortet die Frage *„wie viele?"* auf vier verschiedene
Weisen, und alle vier sind richtig. Wer sie verwechselt, bekommt keine
Fehlermeldung — nur eine andere Zahl.

Dieses Dokument sagt, welche vier das sind, warum sie auseinanderfallen, und
**was sich aus ihnen nicht addieren lässt**. Der letzte Abschnitt nennt, was
die Prüfungen der Strecke *nicht* beweisen; das gehört dazu, sonst liest sich
eine geprüfte Zahl wie eine bewiesene.

> **Herkunft.** Die Gliederung stammt aus Artans SQL-Prüfsammlung vom
> 16.9.2026 (Branch `sql_check_scripts`, `README.md` Abschnitte 4 und 5). Die
> Skripte selbst sind nicht übernommen worden — vier ihrer Prüfungen stehen
> seit dem 17.9. im Bau, drei davon hart (siehe
> [`AENDERUNGEN.md`](intern/AENDERUNGEN.md)). Die
> Überlegungen dahinter sind es wert, zu bleiben. **Alle Zahlen hier sind am
> Referenzstand neu gemessen**, nicht aus dem Branch übernommen; die dortigen
> waren zwei Läufe alt.

---

## 1 · Die vier Perspektiven

| | Chicago | Detroit | was eine Zeile ist |
| --- | ---: | ---: | --- |
| **Anklagen** — alle Silver-Zeilen | 259'625 | 88'686 | eine Anklage |
| **Taten** — `counts` | 259'625 | 85'448 | eine Tat |
| **Fälle** — `counts_case` | 259'596 | 80'230 | ein Fall, sein schwerstes Delikt |
| **Vorfälle** — `count(DISTINCT event_id)` | 259'596 | 80'230 | ein Vorfall |

`gold/fact_offense` ist die zweite Zeile: **345'073 Taten**. Gold nimmt nur,
was `counts` trägt.

**Chicago fällt zwischen den ersten beiden Zeilen nicht auseinander**, weil die
Quelle bereits eine Zeile je Delikt liefert. Detroit liefert Anklagen: ein
Vorfall mit einer Tat kann drei Anklagen tragen. Ohne die Auswahl über `counts`
zählte Detroit **3,8 % zu hoch** — und zwar nicht gleichmässig über die
Kategorien, sondern dort am stärksten, wo die Staatsanwaltschaft breit anklagt.

Der Unterschied zwischen Taten und Fällen ist ein anderer: Er ist keine
Korrektur, sondern eine **Frage**. „Wie viele Einbrüche gab es?" und „in wie
vielen Fällen ging es um einen Einbruch?" sind verschiedene Fragen, und die
Kriminalstatistik beantwortet traditionell die zweite (Hierarchieregel des UCR
Handbook). Beide Spalten stehen deshalb nebeneinander, statt dass eine gewinnt.

Dass die letzten beiden Zeilen identisch sind, ist **kein Zufall, sondern eine
geprüfte Zusage**: `reconcile` bricht ab, wenn `counts_case` nicht genau einmal
je Vorfall mit zählender Tat gesetzt ist.

---

## 2 · Was sich nicht addieren lässt

### Kategorien summieren sich nicht zur Gesamtzahl

Ein Vorfall kann Delikte aus mehreren NIBRS-Familien enthalten — ein Überfall
mit Fahrzeugdiebstahl ist beides. Zählt man Vorfälle **je Familie** und addiert
das Ergebnis, erscheint dieser Vorfall zweimal.

| | Vorfälle | davon in mehr als einer Familie | je Familie summiert |
| --- | ---: | ---: | ---: |
| Chicago | 259'596 | 0 (0,0 %) | 259'596 — passt |
| Detroit | 80'230 | 6'758 (8,4 %) | 87'607 — **7'377 zu viel (9,2 %)** |

Chicagos Null ist keine bessere Datenlage, sondern dieselbe
Granularitäts-Eigenheit wie oben: Ein Chicagoer „Vorfall" ist fast immer ein
Delikt.

**Was das für eine Auswertung heisst:** Anteile je Kategorie werden auf der
**Tatebene** gerechnet (dort summiert sich alles), Vorfallzahlen je Kategorie
dagegen nie addiert, sondern jede direkt aus den Einzelzeilen. Genau deshalb
zählen die vier Vergleichstabellen in `serving/` (`comparison_day`, `_week`,
`_month`) **Taten und Fälle**, nie Vorfälle — und ihre Summen gehen
nachweislich auf die Faktentabelle auf.

### Tage summieren sich nicht zu Monaten

Dieselbe Falle eine Ebene tiefer: Ein Vorfall, dessen Delikte über Mitternacht
reichen, erscheint an zwei Kalendertagen.

| | Tage summiert | Monate summiert | Jahr direkt |
| --- | ---: | ---: | ---: |
| Chicago | 259'600 | 259'596 | 259'596 |
| Detroit | 80'232 | 80'230 | 80'230 |

Vier Chicagoer und zwei Detroiter Vorfälle. Die Abweichung ist winzig — und
genau deshalb gefährlich: Sie fällt bei keiner Plausibilitätsprüfung auf,
verschwindet aber auch nicht, wenn man feiner gruppiert.

### `event_id` darf fehlen — und NULL zählt nicht mit

`event_id` ist die **Fallnummer der Quelle**. Liefert die Quelle keine, steht
NULL, und der Bau behandelt die Zeile über `coalesce(event_id, offense_id)` als
ihren eigenen Fall. Das ist Absicht: Sonst fielen alle Zeilen ohne Nummer in
einen einzigen Fall zusammen.

Für eine Abfrage von Hand ist das eine Falle, denn `count(DISTINCT event_id)`
überspringt NULL stillschweigend — die Zeile verschwindet aus der Zählung, ohne
dass irgendwo etwas fehlt. **Wer je Vorfall zählt, zählt
`count(DISTINCT coalesce(event_id, offense_id))`**, so wie der Bau es tut.

Am Referenzstand betrifft das **keine einzige Zeile**: Beide Quellen liefern
durchgehend Fallnummern. Die Zahl steht trotzdem in jedem Silver-Manifest unter
`checks.per_city.<stadt>.ohne_event_id` — dass sie heute null ist, heisst
nicht, dass sie null sein muss.

### Der Rand des Zeitfensters ist eine Teilperiode

Wochen beginnen am Montag, der Jahrgang beginnt am 1. Januar. Das passt
selten zusammen.

* **2024** beginnt an einem Montag — die erste Woche ist ausnahmsweise
  vollständig: 6'694 Taten.
* Die letzte Woche (ab Montag, 30.12.) enthält nur **zwei Tage**: 1'647 Taten.

Wer die Wochenreihe ohne Hinweis zeichnet, sieht am Jahresende einen Einbruch
um drei Viertel, der keiner ist. **Der Beginn einer Periode ist nicht das
Tatdatum**: Eine Woche kann mit einem Datum vor dem 1. Januar beschriftet sein,
obwohl jede Tat darin im Jahrgang liegt.

---

## 3 · Was die Prüfungen nicht beweisen

Die Landkarte in
[`notebooks/35_kontrollen.ipynb`](../notebooks/35_kontrollen.ipynb) führt
**42 Kontrollen**, 31 davon als hart. **Abbrechen tun 28.** Bei den übrigen
dreien ist „hart" die Einstufung der Sache, nicht ihrer Wirkung:
`GATE_MINDESTENS` und `ERWARTETE_QUELLEN` sind die Schwellen, gegen die andere
Kontrollen prüfen — nicht der Abbruch selbst —, und `gepinnte_laeufe` bricht
nichts ab, sondern **schützt**: Ein Referenzstand wird beim Aufräumen
übergangen.

Um diese 28 geht es hier — und sie beweisen etwas anderes, als ihre Zahl
vermuten lässt. **Eine bestandene harte Kontrolle zeigt, dass der Bau getan
hat, was ihm aufgetragen wurde. Sie zeigt nicht, dass das Ergebnis die
Wirklichkeit richtig beschreibt.** Beides zu verwechseln ist der Grund, warum
eine Liste von 28 grünen Prüfungen beruhigender wirkt, als sie sein darf.

Die folgenden sieben Punkte sagen, wo der Unterschied konkret liegt.

**Eine Zuordnungsquote ist keine Reviewquote.** `mapping_status` sagt, wie eine
Zeile zu ihrem NIBRS-Code gekommen ist — nicht, ob das fachlich stimmt. Am
Referenzstand:

| | exact | ambiguous | fallback_90Z | unmapped |
| --- | ---: | ---: | ---: | ---: |
| Chicago | 248'187 | 3'718 | 7'717 | 3 |
| Detroit | 81'325 | 1'365 | 2'758 | 0 |

Ein `exact` kann eine widersprüchliche Quellbeschreibung tragen, die noch
niemand gesehen hat; ein `fallback_90Z` kann für eine Auswertung völlig in
Ordnung sein. Silver führt **keinen Freigabestatus** — deshalb gibt es auch
keine Schwelle „ab 5 % Review nötig". Das Publish-Gate prüft Abdeckung, nicht
Richtigkeit.

**Ein Abgleich mit derselben CSV prüft Umsetzung, nicht Fachlichkeit.** Die
Prüfung `gegen_crosswalk` stellt sicher, dass Silver das trägt, was der
Crosswalk *heute* sagt. Ob der Crosswalk recht hat, steht darin nicht. Dafür
gibt es nur die amtlichen Handbücher und die Zuordnungen, die als
`ambiguous` markiert sind, weil wir sie entschieden haben: **20 in den
Crosswalks, davon 16 mit Zeilen im Jahrgang 2024** (5'140 Zeilen). Die übrigen
vier sind Entscheidungen zu Codes, die 2024 nicht vorkommen — getroffen, aber
nicht belegt.

**Die Beschreibung ist nicht das Delikt.** Der Text in
`source_offense_description` identifiziert die Tat nicht — das tut der Code.

> **Behoben am 19.9.2026, Silver-Vertrag 3.** Chicagos IUCR-Bezeichnung hat
> zwei Hälften, und Silver führte nur die zweite. `SIMPLE` stand 31'565-mal
> und meinte einmal Körperverletzung (0460, 13B), einmal Bedrohung (0560,
> 13C); **23,3 % der Chicagoer Zeilen** trugen eine für sich genommen
> mehrdeutige Beschreibung. Seither steht dort `BATTERY: SIMPLE` —
> **beide Hälften, getrennt durch `: `**. Der Anteil mehrdeutiger
> Beschreibungen ist damit **null**.

Für Detroit bleibt der Befund bestehen, und er hat eine andere Ursache: Dort
sind es 54
Beschreibungen; `ASSAULT AND BATTERY/SIMPLE ASSAULT` deckt **26 verschiedene
NIBRS-Codes** über 16'837 Zeilen ab, weil die MICR-Beschreibung auf der Ebene
der Deliktklasse steht und der Code eine Ebene darunter.

Umgekehrt gilt dasselbe: **34 der 53** Chicagoer und **43 der 50** Detroiter
NIBRS-Codes tragen mehr als eine Beschreibung. Wer gleiche Texte zusammenlegt,
vermischt Delikte; wer verschiedene trennt, zerlegt eines.

**Was das für eine Auswertung heisst:** nie nach
`source_offense_description` gruppieren, immer nach `nibrs_code` oder
`source_offense_code`. Der Text ist zum Lesen da, nicht zum Zählen. Dass
Chicagos Beschreibung seit Vertrag 3 eindeutig ist, ändert daran nichts — für
Detroit gilt die Warnung unverändert, und eine Regel, die nur für eine Stadt
gilt, ist keine.

**Keine Lücke heisst nicht vollständig.** Silver hat null Zeilen ohne
Zeitpunkt. Das beweist nicht, dass die Quelle vollständig ist — eine Tat ohne
Datum wäre schon in Bronze am Jahresfilter hängengeblieben. Ebenso wenig
beweist ein lückenloser Kalender Meldevollständigkeit: Dass an jedem Tag etwas
gemeldet wurde, sagt nichts darüber, ob alles gemeldet wurde.

**Die Zeitprüfung hat eine blinde Stunde.** `reconcile` rechnet jeden
UTC-Zeitpunkt in die Ortszeit zurück und vergleicht. Beim Zurückstellen der Uhr
hat Detroit schon EST, während Chicago noch CDT hat — für genau eine Stunde im
Jahr fallen beide Zonen zusammen. 30 der 88'686 Detroiter Zeilen liegen darin.
Ein vertauschter Zonenname fiele trotzdem 88'656-fach auf.

**Eine mehrdeutige Ortszeit bleibt mehrdeutig.** Chicago liefert Wanduhrzeit
ohne Zone. Die 49 Zeilen in der doppelten Stunde tragen seit dem 16.9. ein
Kennzeichen — auflösen lässt sich die Mehrdeutigkeit nachträglich nicht.

**Was nur in Bronze steht, kann Silver nicht prüfen.** Silver führt 28
Spalten. Nicht darunter: der **Anklagetext** (`charge_description`,
`arrest_charge`), die **Quellkategorie** (`offense_category` in Detroit,
`primary_type` und `fbi_code` in Chicago) und der **Zeitpunkt der letzten
Quelländerung** (`updated_on`, `updated_at`). Sie fehlen nicht teilweise,
sondern ganz: Silver deutet, was für den Vergleich beider Städte nötig ist, und
lässt den Rest in Bronze stehen.

Ein Widerspruch in diesen Feldern braucht deshalb den Rückgriff auf Bronze —
und der ist umständlicher, als er klingt, denn **Silver führt keine
Zeilen-Herkunft**. Das Manifest nennt unter `derived_from` die Läufe, aus denen
die Tabelle entstanden ist (drei für Chicago, zwei für Detroit), aber nicht,
aus welchem eine bestimmte Zeile stammt. Für Detroit gibt es diesen einen Lauf
gar nicht: Beide Schnappschüsse enthalten **alle 88'685 Zeilen**. Wer
zurückverfolgen will, sucht den Schlüssel in den genannten Läufen — die
Zeilen-Lineage selbst liegt in den Bronze-Manifesten, nicht in Silver.

> **Das gilt für den Referenzstand, nicht für die Zukunft.** Seit dem 18.9.2026
> lädt Detroit Deltas über `updated_at`. Ein Delta-Lauf enthält nur die seither
> bewegten Zeilen, nicht den Bestand — die Aussage „beide Schnappschüsse
> enthalten alle Zeilen" trifft dann nur noch auf die fünf vollen Läufe vom
> 11. bis 18.9. zu. Der Rückgriff wird dadurch *leichter*: Wer wissen will, wann
> eine Zeile zuletzt bewegt wurde, findet sie ab dann in genau dem Delta-Lauf,
> der sie brachte.

---

## Wo das weiterführt

* Welche Kontrolle wo greift, an einem Fall vorgeführt:
  [`notebooks/35_kontrollen.ipynb`](../notebooks/35_kontrollen.ipynb)
* Warum Gold ein Stern und kein Würfel ist:
  [`docs/sternschema-und-wuerfel.md`](sternschema-und-wuerfel.md)
* Was jede Spalte bedeutet: [`docs/feldkatalog.md`](feldkatalog.md)
* Eine Zahl über sieben Schichten zurückverfolgt:
  [`docs/eine-zahl.md`](eine-zahl.md)

---

Gemessen am Referenzstand, 17. September 2026. Jede Zahl in diesem Dokument
wird von `tests/test_zaehlperspektiven.py` gegen die gebauten Schichten
geprüft — die Tests tragen `referenzstand` und laufen deshalb nicht im
wöchentlichen Datenlauf.
