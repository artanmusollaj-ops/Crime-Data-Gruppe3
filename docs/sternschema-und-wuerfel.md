# Würfel oder Stern

> Der Entwurf sah zwei vorberechnete Würfel vor. Gebaut wurde ein Sternschema.
> Was die beiden Bauweisen sind, worin sie sich unterscheiden — und warum die
> Messung den Entwurf gekippt hat.

| | |
| --- | --- |
| Faktentabelle | 1'887'009 Zeilen (Jahrgänge 2021–2026) |
| Dimensionen | 5 · 37'794 Zeilen |
| Verworfen | 2 Würfel |
| Gerechnet in | [`notebooks/34_gold_sternschema.ipynb`](../notebooks/34_gold_sternschema.ipynb) |

Dieselbe Darstellung als Seite mit durchgehendem Layout:
[`sternschema-und-wuerfel.html`](sternschema-und-wuerfel.html).

---

## 1 · Der Würfel: vorher zählen

**Ein Würfel ist eine Tabelle, in der das Zählen schon passiert ist.**

Man wählt die **Achsen** — im ursprünglichen Entwurf Tract, Monat und
Deliktfamilie — und die **Feinheit** jeder Achse. Dann wird für jede
Kombination einmal gezählt und das Ergebnis abgelegt. Der Fachbegriff ist
*OLAP-Cube*; drei Achsen ergeben das Bild, das ihm den Namen gab.

![Ein vorberechneter Würfel mit den Achsen Tract, Monat und Deliktfamilie. Eine
Zelle ist hervorgehoben und hält eine fertige Zahl; der Tag und das einzelne
Delikt sind darin nicht mehr enthalten.](bilder/wuerfel.svg)

*Der Würfel. Achsen und Feinheit werden **vor** der ersten Frage gewählt.
Danach steht in jeder Zelle eine fertige Zahl — und nur noch sie.*

Der Gewinn ist offensichtlich: *„Wie viele Diebstähle im März in
Tract 170318391?"* ist ein Nachschlagen, keine Rechnung. Der Preis steht unter
der Grafik — was in der Zelle zusammengefasst wurde, ist nicht versteckt und
nicht langsam, sondern **weg**. Kein Filter holt es zurück.

> **Zwei harte Regeln**
>
> **Nach unten geht nichts.** Ein Monatswürfel kennt keinen 9. November. Wer
> den Tag braucht, braucht einen anderen Würfel.
>
> **Was keine Achse ist, existiert nicht.** Der zweite Entwurf `fact_city_day`
> hat keine Tract-Achse. Die Frage *„in welchem Tract"* ist dort nicht schwer
> zu beantworten, sondern unmöglich.

Genau deshalb brauchte der Entwurf schon **zwei** Würfel: einen mit Tract ohne
Tag, einen mit Tag ohne Tract. Jede weitere Frage hätte einen dritten
verlangt — und jeder Würfel ist ein eigener Bauauftrag, ein eigener Test und
eine eigene Stelle, an der Zahlen auseinanderlaufen können.

---

## 2 · Das Sternschema: die Granularität behalten

**Eine Faktentabelle im feinsten Granularität, kleine Dimensionen daneben.**

Das Sternschema dreht die Reihenfolge um: erst speichern, dann zählen. In der
Mitte steht **eine** Tabelle mit einer Zeile je Tat. Sie trägt nur
**Schlüssel** und **Messgrössen**. Alles Beschreibende liegt aussen in
**Dimensionstabellen** — und der Name kommt schlicht vom Bild.

![Das Sternschema: die Faktentabelle fact_offense in der Mitte, darum die vier
Dimensionen dim_tract, dim_offense, dim_date und dim_city_day, je über einen
Schlüssel verbunden.](bilder/stern.svg)

*Das Sternschema. Die Faktentabelle trägt Schlüssel und Messgrössen, die
Dimensionen die Bedeutung. Jede Kante ist ein JOIN-Schlüssel.*

### Warum die Dimensionen getrennt stehen

**Die Faktentabelle bleibt schlank.** Stünde in jeder der 1'887'009 Zeilen der
Text `Larceny/Theft Offenses`, läge derselbe Satz zehntausendfach auf der
Platte. Statt dessen steht dort `23C` — drei Zeichen — und die Bedeutung genau
einmal in `dim_offense`.

**Die Dimensionen tragen die Auswahllisten.** Eine Oberfläche, die „Delikt
wählen" anbieten will, liest 85 Zeilen aus `dim_offense` statt 1'887'009
Faktenzeilen zu durchsuchen. Dasselbe gilt für Städte, Tage und Tracts.

**`dim_date` wird erzeugt, nicht abgeleitet.** Ein Tag ohne Delikt hat keine
Faktenzeile. Käme die Zeitachse aus den Fakten, fehlte dieser Tag — und eine
Zeitreihe zeigte eine Lücke, wo eine Null stehen müsste. Die Dimension kennt
alle 2'140 Tage von 2021 bis 2026, ob etwas passiert ist oder nicht — und sagt
mit `year_is_complete`, welcher Jahrgang ganz in den Daten liegt.

---

## 3 · Was die Wahl kostet, in Zeilen

**Der Unterschied zwischen den Bauweisen ist kein Feinschliff.**

> **Dieser Abschnitt rechnet am Jahrgang 2024**, dem Stand, an dem die
> Entscheidung fiel. Die Würfelzahlen stammen aus Notebook 34, das beide
> Bauweisen gebaut und gemessen hat; nachgerechnet sind sie über die sechs
> Jahrgänge nicht, und eine hochgerechnete Zahl wäre hier das Falsche — die
> Entscheidung fiel an diesen Zeilen. Das Verhältnis ist das Argument, nicht
> der Absolutwert: Der Schritt zum Würfel kostet zwei Größenordnungen mehr als
> der Schritt von Silver zu Gold, und daran ändert ein Jahrgang mehr nichts.

![Vier Granularitäten im Vergleich: Silver hält 348'329 Anklagen, Gold 345'091 Taten,
die verworfenen Würfel nur noch 95'219 beziehungsweise 11'156 vorberechnete
Zellen.](bilder/granularitaet.svg)

*Was eine Zeile ist. Der Schritt von Silver zu Gold kostet 3'340 Zeilen, der
Schritt zum Würfel 249'398 — und mit ihnen jede feinere Frage.*

| Tabelle | eine Zeile ist | Zeilen |
| --- | --- | ---: |
| `silver/crime_offense` | eine Anklage | 348'329 |
| `gold/fact_offense` | eine Tat | 345'091 |
| ~~`fact_tract_month`~~ | Tract × Monat × Familie | 95'219 |
| ~~`fact_city_day`~~ | Stadt × Tag × Familie | 11'156 |

Silver hält jede **Anklage**, Gold jede **Tat**. Das ist ein kleiner Schritt —
3'340 Zeilen, Detroits Mehrfachanklagen zum selben Vorfall. Er ist nötig, weil
Detroit sonst 3,8 % zu hoch zählt.

Der Schritt zum Würfel ist ein anderes Kaliber: **249'398 Zeilen**, und mit
ihnen jede Frage, die feiner ist als Monat und Deliktfamilie.

---

## 4 · Die Messung, die entschieden hat

**Die Begründung für die Würfel war Geschwindigkeit. Sie hielt nicht.**

Notebook 34 stellt dieselben Fragen **direkt auf der Silver-Tabelle** — ohne
Vorberechnung, ohne Index, ohne Würfel. Jede realistische Frage liegt im
einstelligen Millisekundenbereich; selbst die pathologische Gruppierung über
alle vier Achsen bleibt unter einer Zehntelsekunde.

> **Der Befund**
>
> **Der Engpass ist nicht die Datenmenge.** Bei 1'887'009 Zeilen gewinnt eine
> Vorberechnung nichts, was ein Mensch bemerken würde. Sie kostet aber genau
> die Beweglichkeit, für die eine Auswertungsplattform da ist.

Das ist der ehrliche Teil der Geschichte: Die Entscheidung fiel nicht, weil
Sternschemata schöner sind, sondern weil **die angenommene Ersparnis bei dieser
Datenmenge nicht existiert**. Bei zweihundert Millionen Zeilen sähe die
Rechnung anders aus — siehe Abschnitt 6.

| Frage | woran sie im Würfel scheitert |
| --- | --- |
| „nur Ladendiebstahl" | beide Würfel fassen Delikte zu *Familien* zusammen |
| „der 9. November" | `fact_tract_month` kennt nur Monate |
| „in welchem Tract" | `fact_city_day` kennt nur die Stadt |

---

## 5 · Wie sich das anfühlt: dieselbe Frage, zweimal

**Ladendiebstähle am 9. November, je Tract.**

Im Sternschema ist das ein Filter und ein `GROUP BY`:

```sql
-- läuft auf data/serving/analyse.duckdb
SELECT t.tract_name, count(*) AS delikte
FROM   fact_offense f
JOIN   dim_offense  o ON o.nibrs_code  = f.nibrs_code
JOIN   dim_tract    t ON t.geoid       = f.tract_geoid
WHERE  f.date = DATE '2024-11-09'
  AND  o.nibrs_description = 'Shoplifting'
GROUP  BY 1 ORDER BY delikte DESC;
```

Im Würfel gibt es diese Abfrage nicht. Man käme bis hierher:

```sql
-- fact_tract_month, der verworfene Entwurf
SELECT geoid, delikte
FROM   fact_tract_month
WHERE  monat   = '2024-11'   -- der 9. ist nicht mehr da
  AND  familie = '23';       -- Larceny gesamt, nicht Shoplifting
```

Das Ergebnis wäre nicht ungenau, sondern eine **andere Zahl** — alle Diebstähle
eines ganzen Monats statt einer Deliktart an einem Tag. Genau solche
Verwechslungen sind der Grund, warum die Granularität in der Dokumentation an jeder
Tabelle dransteht.

---

## 6 · Wann ein Würfel trotzdem richtig ist

**Die Entscheidung gilt für diese Daten, nicht allgemein.**

Ein Würfel gewinnt, wenn drei Dinge zusammenkommen: **die Datenmenge ist gross
genug**, dass die Rechenzeit spürbar wird; **die Fragen sind bekannt und
stabil**; und **viele Leute stellen dieselbe Frage gleichzeitig**. Ein
Tagesreport für hundert Filialen ist der klassische Fall — jeden Morgen
dieselbe Auswertung, jeden Morgen dieselben Achsen.

Bei uns trifft keines der drei zu: ein Jahrgang zweier Städte, eine
Auswertungsplattform, die explizit für *unvorhergesehene* Fragen gebaut wird,
und ein einstelliger Nutzerkreis. Das Sternschema behält die Granularität und bleibt
trotzdem schnell — und wenn die Daten einmal um zwei Grössenordnungen wachsen,
lässt sich ein Würfel jederzeit *daraus* erzeugen. Umgekehrt geht es nicht.

### Was das für die Abgabe heisst

1. Gold ist ein Sternschema mit der Granularität **eine Tat** — nicht, weil es
   Lehrbuchform ist, sondern weil die Messung die Alternative widerlegt hat.
2. Der verworfene Entwurf bleibt dokumentiert. Eine Entscheidung ohne die
   verworfene Variante ist keine Entscheidung, sondern eine Behauptung.
3. Die Grenze ist benannt: Bei deutlich mehr Daten kehrt sich die Rechnung um,
   und der Würfel liesse sich aus dem Stern jederzeit nachbauen.
4. **Seit dem 17.9.2026 gibt es ihn trotzdem — in Serving, nicht in Gold.**
   Vier Vergleichstabellen (`comparison_day`, `comparison_week`,
   `comparison_month`, `partition_quality`) werden aus dem Stern abgeleitet,
   summieren sich nachweislich auf ihn und liegen im Veröffentlichungsstand
   für das Dashboard. Nicht, weil die Messung oben falsch wäre — sie steht —,
   sondern weil für ein Studienprojekt zählt, dass beide Bauweisen **gebaut**
   nebeneinander stehen. Die Quelle der Wahrheit bleibt der Stern.

---

Gerechnet in [`notebooks/34_gold_sternschema.ipynb`](../notebooks/34_gold_sternschema.ipynb),
Stand 12. September 2026. Alle Zahlen stammen aus `data/gold/` und werden von
`tests/test_abgabedokumente.py` gegen die Dokumente geprüft.
