# Die abgegebenen Forschungsfragen und Hypothesen

**Erzeugt, nicht geschrieben.** Der Wortlaut hier ist aus der eingereichten Fassung gezogen —
[`tools/build_forschungsfragen.py`](../tools/build_forschungsfragen.py) liest Kapitel 3 und Kapitel 11 des abgegebenen PDF
(`Leistungsnachweis_1_Konzept_Gruppe_3.pdf`, erstellt am 24.09.2026).

```bash
python tools/build_forschungsfragen.py
```

**Der Wortlaut ist Beleg, nicht Entwurf.** Diese sechs Fragen und sechs Hypothesen wurden
eingereicht und bewertet; sie werden hier nicht umformuliert, gekürzt oder verbessert.
Wer eine Formulierung ändern will, ändert sie in einer neuen Abgabe — nicht hier.

**Warum diese Datei im Repository liegt und das PDF nicht.** Das abgegebene PDF bleibt
ungetrackt (`.gitignore`, Entscheid vom 5.10.2026). Damit ist die Lage dieselbe wie bei
[`intern/platzbedarf.md`](intern/platzbedarf.md): Der Generator läuft dort, wo die Quelle
liegt, das erzeugte Dokument ist die versionierte Fassung, und der Reproduktionswächter
in `tests/test_forschungsfragen.py` überspringt sauber, wenn die Quelle fehlt. Was **immer**
läuft, sind die Vergleiche gegen dieses Dokument: Notebook 36 und Kapitel 3 von
[`ln2_konzept.md`](ln2_konzept.md) müssen es wörtlich zitieren.

**Stand der Quelle.** Erstellt am 24.09.2026, SHA-256 `f5848080ab14bc7bf0266af6b8707f32e25d71cb6cfd90451e220583b15e516e`.
Ein Erzeugungsdatum steht hier bewusst nicht: Es hiesse, dass ein zweiter Lauf eine andere
Datei liefert, und der Wächter darauf könnte nie grün sein.

## 1 Die übergeordnete Forschungsfrage

> **Übergeordnete Frage:** Wie lässt sich eine schlanke Batch-Datenplattform
> gestalten, die heterogene Kriminalitätsdaten aus Chicago und Detroit
> reproduzierbar beschafft, fachlich nachvollziehbar harmonisiert und
> qualitätsgesichert für analytische Anwendungen bereitstellt?

## 2 Die sechs Teilfragen und ihre Hypothesen

Je Frage eine Hypothese, beide im Wortlaut der Abgabe. Die Nummern `F1`–`F6` und `H1`–`H6`
sind die der Abgabe und gelten im ganzen Repository.

### F1

> **F1:** Wie werden Downloads trotz Pagination und veränderlicher Quellen
> abgesichert?
>
> **H1:** Bei einem erfolgreichen Lauf entspricht die gelieferte Menge genau
> der vorab ermittelten Erwartungsmenge; bei Quellen ohne
> Identifikator-Menge tritt ein gleichwertiger Nachweis an ihre Stelle.

### F2

> **F2:** Wie wirken sich wiederholte Lieferungen auf Silber und Gold aus?
>
> **H2:** Zweimalige Verarbeitung identischer Eingaben und Regeln erzeugt
> dieselben fachlichen Tabelleninhalte und Kennzahlen.

### F3

> **F3:** Wie werden lokale Tat-Tage trotz unterschiedlicher Zeitdarstellung
> korrekt gebildet?
>
> **H3:** Die lokale Tageszuordnung und die fachlichen Abfragegrenzen sind
> unabhängig von der Zeitzone des ausführenden Rechners. Nichtexistierende
> oder mehrdeutige lokale Quellzeiten werden ausdrücklich als Sonderfälle
> ausgewiesen.

### F4

> **F4:** Welche Unterschiede bleiben trotz gemeinschaftlichen Deliktschemas
> bestehen?
>
> **H4:** Codebasierte und versionierte Zuordnungen machen mehr fachlich
> relevante Mehrdeutigkeiten sichtbar als eine alleinige Zuordnung nach
> Kategoriebezeichnung.

### F5

> **F5:** Welche Voraussetzungen benötigt die Wiederherstellung einer
> Kennzahl?
>
> **H5:** Ein fixierter Eingabestand mit erhaltenen Referenzdateien, Code,
> Konfiguration und Abhängigkeiten liefert bei erneutem Aufbau dieselben
> fachlichen Ergebnisse.

### F6

> **F6:** Reichen Parquet und DuckDB für den Umfang aus?
>
> **H6:** Silver, Gold und Serving lassen sich auf dem festgelegten
> Referenzrechner in weniger als zehn Minuten aufbauen.

## 3 Die Grenze des Nachweises

Sie steht in Kapitel 3 direkt unter der Tabelle und gehört zu F1:

> **Grenze:** Die Grenze des Nachweises ist ausdrücklich festzuhalten: Er
> betrifft die Mitgliedschaft der Datensätze, nicht einen transaktional
> eingefrorenen Attributzustand der externen Quelle. Ein Datensatz kann sich
> während des Downloads ändern.

## 4 Die Beantwortung aus Kapitel 11

Was die Abgabe als Ergebnis je Hypothese ausweist. Der Rechenweg dazu steht in
[`../notebooks/36_hypothesen.ipynb`](../notebooks/36_hypothesen.ipynb); dieses Dokument
hält fest, was **abgegeben** wurde, nicht was heute gemessen wird.

| | Hypothese | Ergebnis |
| --- | --- | --- |
| **H1** | Gelieferte Menge entspricht der Erwartungsmenge | hält, wörtlich für Chicago und Detroit; die drei Referenzquellen belegen Vollständigkeit gleichwertig |
| **H2** | Wiederholte Verarbeitung erzeugt denselben Inhalt | hält; drei Neubauten, sechs Tabellen, identischer sortierter Inhalt |
| **H3** | Tageszuordnung unabhängig von der Rechnerzeitzone, Sonderfälle ausgewiesen | hält in beiden Teilen; die Ausweisung wurde am 16.09.2026 ergänzt |
| **H4** | Codebasierte Zuordnung macht mehr Mehrdeutigkeiten sichtbar | hält deutlich; 71 % der Zeilen unter mehrdeutiger Bezeichnung |
| **H5** | Fixierter Eingabestand liefert dieselben Ergebnisse | hält für den gepinnten Stand; zweite Umgebung offen |
| **H6** | Aufbau in unter zehn Minuten | hält; Median 27 bis 31 Sekunden |

## 5 Nachziehen

```bash
python tools/build_forschungsfragen.py
python -m pytest tests/test_forschungsfragen.py tests/test_notebook_hypothesen.py
```

Die Wächter halten drei Stellen zusammen: dieses Dokument, Kapitel 3 von
[`ln2_konzept.md`](ln2_konzept.md) und die Zitate in Notebook 36. Weicht eine ab, nennt
der Wächter die Hypothese und beide Fassungen — genau die Prüfung, die bis zum
5.10.2026 fehlte und deshalb drei Fassungen nebeneinander stehen liess.
