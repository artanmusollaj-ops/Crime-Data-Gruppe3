# Was wir verlieren, wenn wir Läufe löschen

**Stand: 16.9.2026. Zur gemeinsamen Entscheidung am Freitag, 18.9.2026.**

Für die Auswertung zählt der aktuelle Stand. Die Quellen bewegen sich aber:
Detroit ändert Einträge noch Jahre nach der Tat, Chicago liefert Deltas. Diese
Bewegung ist selbst ein Gegenstand — *was ändert sich, wie oft, welcher Art,
und was verschwindet.* Heute steckt diese Information implizit in den
Bronze-Läufen. Sobald `orchestration.aufraeumen` einen löscht, ist sie weg.

Dieses Dokument misst, was auf dem Spiel steht, und schlägt vor, wie man es
behält, ohne die Läufe aufzuheben.

---

## 1 · Was tatsächlich passiert, gemessen

Detroit hat zwei vollständige Schnappschüsse desselben Bestands, geladen am
11.9. um 12:50 und am 12.9. um 09:34 — rund 21 Stunden auseinander. Sie lassen
sich Zeile für Zeile vergleichen.

| | Zeilen |
| --- | ---: |
| in beiden Schnappschüssen | 88'685 |
| neu hinzugekommen | 0 |
| verschwunden | 0 |
| **mit echter Inhaltsänderung** | **102** |
| nur `updated_at` bewegt, sonst nichts | 147 |

Welche Felder sich geändert haben:

| Feld | Zeilen | Bedeutung |
| --- | ---: | --- |
| `ESRI_OID` | 88'677 | interne ArcGIS-Zeilennummer, **ohne Aussage** |
| `updated_at` | 249 | Änderungsstempel der Quelle |
| `offense_description` | 160 | davon **150 reine Leerzeichen** |
| `updated_in_ibr_at` | 121 | Stempel der IBR-Meldung |
| `case_status` | 89 | Ermittlungsstand |
| `state_offense_code` | 14 | **der Deliktcode selbst** |
| `offense_category` | 1 | |

### Die vierzehn Codeänderungen haben ein Muster

```text
3072 -> 3002    4801 -> 4800    1178 -> 1108    2099 -> 2000
1201 -> 1200    5001 -> 5000    1174 -> 1104    7070 -> 7000
```

Durchweg vom spezifischen zum allgemeinen Code. Das ist keine Korrektur
einzelner Tippfehler, das sieht nach einer Regel aus.

`3072` ist dabei kein beliebiger Code. Er trägt **1'404 Anklagen** in
`silver/crime_offense` und davon **1'365 zählende Taten** in
`gold/fact_offense` — alle mit `mapping_status = ambiguous`. Eine Umcodierung
dort verschiebt die NIBRS-Zuordnung und damit die Vergleichszahl.

---

## 2 · Die Falle: ein naiver Vergleich ist Rauschen

| Vergleich | geänderte Zeilen |
| --- | ---: |
| alle Felder, wie geliefert | 88'677 |
| ohne `ESRI_OID`, ohne Zeitstempel, Text getrimmt | **102** |

Der Unterschied ist Faktor 870. Zwei Quellen erzeugen ihn:

**`ESRI_OID` ändert sich bei praktisch jeder Zeile.** Es ist die Zeilennummer
der ArcGIS-Antwort, nicht die Identität des Falls. Das Projekt weiss das
bereits — Absprache 8.1 hält fest, dass die fachliche Identität aus
Quellsystem und Vorfall-ID entsteht, nicht aus `ESRI_OID`.

**150 der 160 Beschreibungsänderungen sind Leerzeichen.** Die Quelle füllt
inzwischen auf feste Breite auf. Echt sind zehn, darunter eine Umklassierung
von `BURGLARY - FORCED ENTRY` zu `DAMAGE TO PROPERTY`.

Wer das nicht normalisiert, erzeugt ein Änderungsprotokoll, in dem die zehn
echten Fälle nicht zu finden sind.

---

## 3 · Was heute verlorengeht

Nichts — noch. `aufraeumen` meldet *„10 Läufe, 0 entbehrlich"*, weil alle im
Referenzstand gepinnt sind. Die Frage ist, was beim ersten echten Aufräumen
passiert.

Die Rechnung ist unangenehm: Zwei Detroit-Schnappschüsse belegen **31,9 MB**,
um **102 geänderte Zeilen** zu bewahren. Bei einem Lauf pro Woche wächst das
linear, und irgendwann räumt jemand auf. Dann ist der Vergleichspunkt weg, und
mit ihm die Antwort auf jede Frage nach Veränderung.

---

## 4 · Der Vorschlag

**Nicht die Läufe aufheben, sondern den Unterschied herausziehen, bevor sie
gelöscht werden dürfen.**

Der Denkfehler bei „wir dürfen nichts löschen" ist das Verhältnis: 31,9 MB für
102 Zeilen. Wird der Unterschied bei der Ingestion extrahiert, bleibt eine
schmale Tabelle, und die Schnappschüsse sind danach entbehrlich.

### Die Tabelle

Eine neue Silver-Tabelle, **append-only**, eine Zeile je geändertem Feld:

| Spalte | Inhalt |
| --- | --- |
| `city`, `offense_id` | die fachliche Identität, **nicht** `ESRI_OID` |
| `run_id`, `beobachtet_am` | wann wir es gesehen haben |
| `art` | `neu`, `geaendert`, `verschwunden` |
| `feld`, `wert_alt`, `wert_neu` | nur bei `geaendert` |

Grössenordnung: rund 250 Zeilen je Schnappschusspaar. Bei einem Lauf pro Woche
sind das etwa 13'000 Zeilen im Jahr — ein Bruchteil eines Megabytes.

### Die neue Aufräumregel

> Ein Lauf darf erst gelöscht werden, wenn sein Unterschied herausgezogen ist.

Das fügt sich in die bestehende Regelkette von `orchestration.aufraeumen` ein,
neben *gepinnt bleibt*, *der jüngste und der davor*, *alles von Silver
Genannte* und *die Basis jedes Deltas*.

---

## 5 · Fünf Entscheidungen für Freitag

### 5.1 Welche Felder zählen als Änderung?

| Option | Folge |
| --- | --- |
| **A** alle Felder | 88'677 Zeilen je Paar, unbrauchbar |
| **B** ohne `ESRI_OID`, ohne Zeitstempel, Text getrimmt | 102 Zeilen je Paar |
| **C** nur fachliche Felder: Code, Kategorie, Beschreibung, Status, Ort, Zeit | etwas weniger als B |

**Empfehlung: B.** C verliert die Information, dass die Quelle eine Zeile
angefasst hat, ohne dass sich fachlich etwas änderte — und genau das ist eine
eigene Beobachtung. Die 147 Zeilen, bei denen sich nur `updated_at` bewegte,
sind ein Befund über die Meldepraxis, kein Rauschen.

### 5.2 Wollen wir Löschungen überhaupt erkennen können?

Löschungen sind nur zwischen **zwei vollständigen Schnappschüssen desselben
Bestands** erkennbar. Chicago hat einen Vollschnappschuss und vier Deltas —
dort lässt sich heute **nicht** sagen, ob etwas gelöscht wurde.

**Seit dem 18.9.2026 gilt das für beide Städte.** Detroit lud bis dahin bei
jedem Lauf den ganzen Jahrgang; fünf solche Schnappschüsse liegen vor (11.9.,
12.9., 17.9. und zweimal am 18.9.). Sie sind der Grund, warum wir überhaupt
messen konnten, dass `updated_at` jede inhaltliche Änderung mitträgt — und mit
diesem Ergebnis lädt Detroit seither ebenfalls Deltas. Die fünf bleiben als
Vergleichspaare erhalten; **neue kommen ohne Entscheidung keine mehr dazu.**

Konzept 6.3 empfiehlt bereits *„periodische Full Loads beziehungsweise
Bestandsabgleiche"*. Das hier wäre der konkrete Grund dafür.

**Empfehlung: ja, mit einem Vollschnappschuss je Stadt und Monat.** Ohne ihn
ist die Frage „was wird gelöscht" für beide Städte dauerhaft unbeantwortbar.
Der Aufruf steht bereit — `--mode full` lädt weiterhin den ganzen Jahrgang;
es fehlt nur der Beschluss, ihn regelmässig zu starten.

### 5.3 Wie oft laden wir?

Die Auflösung der Historie ist der Ladeabstand. Bei einem Lauf pro Woche sieht
man den Nettoeffekt der Woche; zwei Änderungen, die sich aufheben, sind
unsichtbar.

**Empfehlung: beim wöchentlichen Lauf bleiben.** Für die Frage „wie lange nach
der Tat ändert sich ein Datensatz" reicht Wochenauflösung. Täglich zu laden
wäre Aufwand ohne Erkenntnisgewinn, solange niemand eine Frage hat, die
Tagesauflösung braucht.

### 5.4 Wo liegt die Tabelle?

| Option | Folge |
| --- | --- |
| **A** Silver, vor der Harmonisierung | Änderungen in Quellbegriffen sichtbar, `3072 -> 3002` |
| **B** Silver, nach der Harmonisierung | Änderungen in NIBRS-Begriffen, aber Umcodierungen innerhalb desselben NIBRS-Codes verschwinden |

**Empfehlung: A.** Sonst sieht man nur die Änderungen, die es durch den
Crosswalk schaffen — und ausgerechnet die interessanten sind die, bei denen
sich die Zuordnung ändert.

---

### 5.5 Was von den Releases bleibt?

Seit dem 17.9.2026 bildet jeder grüne Gesamtlauf ein **Release** — der ganze
veröffentlichte Stand unter einer Kennung, unveränderlich, mit Prüfsummen
(`ausblick.md` 6). Damit gibt es eine zweite Historie neben der, um die es in
diesem Papier geht: nicht *was die Quellen geändert haben*, sondern *was wir
wann gesagt haben*. Sie wird heute nur angehäuft; `aufraeumen` fasst
Releases nicht an, weder lokal noch auf SeaweedFS.

Gemessen am 17.9.: ein Release hat **42,3 MB** — 14 MB Parquet plus eine
26,5 MB grosse selbständige Datenbank. Wöchentlich ein Release ergibt rund
**2,2 GB im Jahr**; täglich rund 15 GB. Zum Vergleich liegen heute 93 MB
Raw, 93 MB Bronze und 49 MB Silver auf SeaweedFS.

Drei Möglichkeiten:

| | was bleibt | was es kostet | was verlorengeht |
| --- | --- | --- | --- |
| **alles** | jedes Release | ~2 GB/Jahr bei wöchentlichem Lauf | nichts — aber die Liste wird lang |
| **gepinnt + die letzten n** | Referenzstände (Abgabe, Folie) für immer, dazu die n jüngsten | ~n × 42 MB plus die gepinnten | Zwischenstände, die niemand zitiert hat |
| **nur der aktuelle** | ein Release | 42 MB | jede Möglichkeit, eine ältere Aussage nachzubauen |

**Empfehlung:** *gepinnt + die letzten n*, mit demselben Register wie für
Läufe (`config/referenzstand.csv`, Regel 0 von `aufraeumen`) und n = 8 —
zwei Monate wöchentlicher Releases. Das ist dieselbe Logik wie bei Raw und
Bronze, nur eine Schicht höher: Was eine veröffentlichte Zahl trägt, bleibt;
was niemand zitiert hat, darf gehen. Zu bauen wäre eine Regel in
`aufraeumen`, die `releases/` kennt — lokal **und** auf SeaweedFS, denn
anders als Läufe liegen Releases dort als der gemeinsame Stand. Nicht vor
Freitag; bis dahin wird nichts gelöscht.

**Was die Entscheidung nicht ersetzt:** die Tabelle aus Abschnitt 4. Ein
Release hält fest, was *wir* gesagt haben; die Änderungstabelle hält fest,
was die *Stadt* geändert hat. Beides ist eine Historie, keines ist die andere.

## 6 · Was das für die Forschung öffnet

Vier Fragen, die die Gold-Schicht heute nicht stellen kann:

1. **Wie lange nach der Tat hört ein Datensatz auf, sich zu ändern?** Eine
   Stabilitätskurve je Delikttyp. Sie sagt, ab wann ein Jahrgang als
   abgeschlossen gelten darf.
2. **Welche Delikttypen werden umklassiert, und in welche Richtung?** Die
   vierzehn gemessenen Fälle deuten auf spezifisch → allgemein.
3. **Was wird gelöscht, und hängt das am Delikttyp?** Detroit führt bereits
   ein `unfounded`-Kennzeichen; eine Löschung ist etwas anderes.
4. **Revidieren Chicago und Detroit unterschiedlich stark?** Das ist die
   unangenehmste. Wenn ja, ist es eine Bedrohung der Vergleichbarkeit, die
   heute unsichtbar ist — und ein eigener Befund, der direkt an der
   Forschungsfrage hängt.

---

## 7 · Aufwand und Grenzen

**Aufwand:** geschätzt ein Arbeitstag. Eine Vergleichsfunktion, eine
Silver-Tabelle, die neue Vorbedingung in `aufraeumen`, Tests.

**Was es nicht löst:**

* **Die Historie beginnt mit der Beobachtung, nicht mit der Tat.** Ein Fall
  vom Januar 2024, den wir erstmals im September 2026 gesehen haben, hat bei
  uns keine Vorgeschichte. Das gehört in jede Auswertung, sonst liest es sich
  wie eine Aussage über die Polizei statt über unsere Pipeline.
* **Was zwischen zwei Läufen zweimal geändert wurde, sieht man einmal.**
* **Es ersetzt keine versionierte Ablage von Silver und Gold.** Das ist Stufe
  C aus [`ausblick.md`](../ausblick.md) Abschnitt 1 und bleibt eine eigene,
  teurere Frage.

---

## 8 · Was am Freitag zu entscheiden ist

1. Bauen wir es? **Vorher nicht aufräumen** — die Vergleichspunkte sind noch
   da, aber nur solange die Läufe gepinnt bleiben.
2. Welche Felder zählen (5.1)?
3. Monatlicher Vollschnappschuss je Stadt (5.2)?
4. Tabelle vor oder nach der Harmonisierung (5.4)?
5. Welche Releases bleiben — alle, gepinnt + die letzten n, oder nur das
   aktuelle (5.5)? Bis zur Entscheidung wird keines gelöscht.
6. **Wann ziehen wir den Referenzstand nach?** Er ist seit dem 17.9. überholt
   — siehe unten.

Punkt 1 ist der einzige, der Zeitdruck hat. Die übrigen drei lassen sich auch
später ändern, solange die Rohläufe noch liegen.

### Offen seit dem 17.9.2026: der Referenzstand ist überholt

Am Abend des 17.9. lief die Strecke erstmals seit dem 5.–8. September wieder
**mit Ingestion**. Die Quellen hatten sich in diesen zehn Tagen bewegt, und
der gebaute Stand steht seither vor dem dokumentierten:

| Grösse | dokumentiert | gemessen am 17.9. | Drift |
| --- | ---: | ---: | ---: |
| `silver/crime_offense` | 347'957 | 348'311 | +0,10 % |
| `gold/fact_offense` | 344'617 | 345'050 | +0,13 % |
| Chicago, je 1'000 | 94,5 | 94,5 | 0,0 |
| Detroit, je 1'000 (Tatebene) | 132,6 | **132,7** | +0,1 — über der Toleranz |
| Fallebene, beide Städte | unverändert | unverändert | 0,0 |

**Christian hat entschieden, den Referenzstand vorerst nicht nachzuziehen**
(17.9.2026). Er ist eine Verabredung des Teams, keine Zahl, die ein Lauf
verschiebt — und die Abgabedokumente stehen kurz vor der Besprechung. Die
Folge ist sichtbar und gewollt: Auf einem Rechner mit frisch gebauten Daten
sind **34 der 71 Wächter mit dem Marker `referenzstand` rot**. Das ist ihre
Aufgabe, nicht ein Fehler; `python -m orchestration.drift` sagt in einer
Tabelle, wie weit es auseinander ist. In CI und in einem frischen Klon ändert
sich nichts, dort gibt es keine Daten.

Seit dem 18.9.2026 stehen sie dabei nicht mehr im Weg: `python -m pytest`
wählt den Marker ab und ist grün, `python -m pytest -m referenzstand` ruft
genau diese 71 auf. Der Grund war ein praktischer — 34 rote Zeilen im
Standardlauf sahen aus wie eine kaputte Einrichtung, und ein echter
Fehlschlag wäre darin nicht aufgefallen.

Zu entscheiden ist, **wann** nachgezogen wird: jetzt, nach Freitag, oder erst
vor der Abgabe. Nachziehen heisst — in einem Zug — alle dokumentierten Zahlen
auf den neuen Stand, `aufraeumen --pinnen` für die neuen Läufe, und
`docs/feldkatalog.md` neu erzeugen. Bis dahin gilt: Was in den Dokumenten
steht, ist der Stand vom 17.9.2026, 16:05 UTC.

> **Nicht zu verwechseln: der Veröffentlichungsstand.** Für LN2 ist ein
> Release-Verzeichnis je freigegebenem Gold-Stand geplant, mit einem Verweis
> darauf — [`ausblick.md`](../ausblick.md) Abschnitt 6. Aufgehobene Releases sind
> eine Historie der **veröffentlichten Stände** und beantworten nicht, was
> dieses Dokument misst: was die **Quellen** zwischen zwei Läufen ändern. Ein
> Release hält fest, was wir gesagt haben; diese Tabelle hält fest, was die
> Stadt geändert hat. Beides ist nützlich, keines ersetzt das andere, und für
> Freitag steht nur das Zweite zur Entscheidung.

### Ausserdem am Freitag — nicht Teil dieses Papiers

Vier offene Punkte aus dem Chat, damit sie nicht verlorengehen:

6. ~~**Chicagos Beschreibung aus beiden IUCR-Hälften bauen?**~~ →
   **entschieden und umgesetzt am 19.9.2026.** `source_offense_description`
   trägt für Chicago jetzt `primary_type: description`, also `BATTERY: SIMPLE`
   statt `SIMPLE`. Der Anteil mehrdeutiger Beschreibungen fiel von **23,7 %
   auf null**. Gekostet hat es Silver-Vertrag 3, Gold-Vertrag 5, einen Neubau
   und ein neues Release.
7. **Die `ambiguous`-Zuordnungen durchgehen:** 20 in den Crosswalks, 16
   davon mit Zeilen im Jahrgang 2024 (5'140 Zeilen). Vier Entscheidungen sind
   getroffen, aber nicht belegt.
8. **H1 und H6 im Wortlaut** (Notebook 36, Bilanz).
9. **Ist „Anklage" der richtige Begriff** für Detroits Zeilen?
