# Die Pflichtbestandteile von LN2 und wo sie stehen

Die Modulunterlagen verlangen für LN2 sechs Bestandteile, P1 bis P6 (Folie 30,
wörtlich im PRD, Abschnitt 2). FR-56 verlangt zu jedem eine **benannte
Fundstelle**: eine Stelle, die man öffnen kann und die den Bestandteil
belegt, nicht nur ankündigt. Angelegt am 23.11.2026.

**Warum es diese Tabelle gibt.** Bis hierher stand nirgends, wo P1 bis P6 zu
finden sind. `fr-stand.md` führte FR-56 als „nicht geprüft“, weil kein
Wächter die sechs Fundstellen hielt. Eine Prüferin sucht aber genau so: Sie
nimmt die Folie und schlägt nach.

**Was der Wächter prüft** (`tests/test_pflichtbestandteile.py`):

- Jeder Bestandteil steht genau einmal da, mit seinem Wortlaut.
- Jede Fundstelle existiert, als Datei und, wo ein Anker steht, als
  Überschrift darin.
- Ein **belegt** zeigt auf keine Überschrift mit „Entwurf“ oder „Vorschlag“.
- `fr-stand.md` führt FR-56 erst dann als erfüllt, wenn kein Bestandteil
  mehr **fehlt**.

Was er **nicht** prüft: ob die Stelle inhaltlich trägt. Das steht in der
letzten Spalte, als Satz, den man nachlesen kann.

**Stand:** belegt · teilweise (Fundstelle da, aber mit benannter Lücke) ·
fehlt (keine Fundstelle).

| | Pflichtbestandteil (Folie 30, wörtlich) | Stand | Fundstelle | Was dort steht |
| --- | --- | --- | --- | --- |
| P1 | „Generell: Berücksichtigung der Feedbacks des 1. Leistungsnachweises“ | fehlt | — | Die Rückmeldung kam am 3.11.2026 (Note 5.75). Eingearbeitet ist sie nicht. Was aus jedem Kritikpunkt wurde, steht seit dem 23.11.2026 als Vorschlag in [`textvorschlag-fr-58.md`](textvorschlag-fr-58.md) — ein Vorschlag, noch keine Fundstelle. Das ist FR-58, offen bei Artan. „Was aus LN1 offen war“ in `ln2_konzept.md` ist keine Fundstelle: Es nennt, was bei der Abgabe von LN1 fehlte, nicht die Rückmeldung darauf |
| P2 | „Finaler Data Engineering – Lebenszyklus · Phasen: Generation, Ingestion, Storage, Transformation, Serving, Unterströmungen“ | teilweise | [`ln2_konzept.md`, 5.1](../ln2_konzept.md#51-die-fünf-phasen), [5.3](../ln2_konzept.md#53-unterströmungen) | Alle sechs Phasen sind beschrieben und je Phase belegt: fünf in 5.1, die Unterströmungen in 5.3. **Die Lücke:** Kapitel 5 beginnt mit „Gefordert ist der Entwurf“, und 5.2 heisst „der Entwurf“. Das ist der Wortlaut von LN1. „Final“ verlangt LN2, das ist FR-57 |
| P3 | „Transformation Teil 2 · Abschliessende Datenanalyse und –bereinigung, Hypothesentest“ | belegt | [`36_hypothesen.ipynb`](../../notebooks/36_hypothesen.ipynb), [`35_kontrollen.ipynb`](../../notebooks/35_kontrollen.ipynb), [Nachweise](../nachweise/README.md), [`ln2_konzept.md`, 3.3](../ln2_konzept.md#33-hypothesen) | Notebook 36 testet H1 bis H6, Notebook 35 spielt die Kontrollen an einem Fall durch. Beide liegen ausgeführt unter `nachweise/`. Die Befunde der Bereinigung stehen in `ln2_konzept.md` 8.4 bis 8.7. Ein eigenes Kapitel „Transformation Teil 2“ hat das Konzept nicht. Die Gliederung entsteht im Word-Dokument |
| P4 | „Abschliessende Transformation der Daten für die Phase Serving“ | belegt | [`ln2_konzept.md`, „Was geliefert wird“](../ln2_konzept.md#was-geliefert-wird-elf-gold-tabellen), [`sternschema-und-wuerfel.md`](../sternschema-und-wuerfel.md), [`34_gold_sternschema.ipynb`](../../notebooks/34_gold_sternschema.ipynb) | Die elf Gold-Tabellen als Sternschema, die Wahl gegen den Würfel mit Messung, und Notebook 34 rechnet sie nach. Die Vergleichstabellen in Serving baut `serving.build_comparison` |
| P5 | „Serving · Option A) Anwendungsfall Analytik: Entwicklung einer Deployment-Umgebung“ | belegt | [`storage-architektur.md`, 16](../storage-architektur.md#16--die-strecke-auf-srv01), [`ln2_konzept.md`, „Was gebaut ist“](../ln2_konzept.md#was-gebaut-ist-die-auswertungsdatenbank), [`docker-compose.srv01.yml`](../../docker-compose.srv01.yml) | Die Strecke läuft auf `srv01`: sieben Dienste, darunter Dashboard, Jupyter und die Engineering-Konsole, mit gemessenen Speichergrenzen, wöchentlichem Datenlauf und Sicherung. Die Auswertungsdatenbank und das Dashboard beschreibt das Konzept |
| P6 | „Beantwortung der Forschungsfragen“ | belegt | [`ln2_konzept.md`, 3.3](../ln2_konzept.md#33-hypothesen), [`36_hypothesen.ipynb`](../../notebooks/36_hypothesen.ipynb) | Je Forschungsfrage eine Hypothese. Die Spalte „Ergebnis“ beantwortet alle sechs: Alle halten, zwei mit Einschränkung. Notebook 36 rechnet jede Zahl darin nach |

## Was daraus folgt

- **P1 ist der einzige Bestandteil ohne Fundstelle.** Solange das so ist,
  bleibt FR-56 teilweise erfüllt. Er wird erfüllt, sobald FR-58 eine Stelle
  hat, die die Kritikpunkte von LN1 einzeln beantwortet. Diese Stelle kommt
  dann hier in die Zeile P1.
- **P2 hängt an einem Wort.** Die sechs Phasen stehen, aber Kapitel 5 nennt
  sich selbst den Entwurf. Das zu ändern ist Artans Text (FR-57).
- **Alle Fundstellen liegen in Arbeitsfassungen.** Abgegeben wird ein
  Word-Dokument, das aus `ln2_konzept.md` entsteht. Steht die Gliederung
  fest, gehört hier die Kapitelnummer der Abgabe daneben.
