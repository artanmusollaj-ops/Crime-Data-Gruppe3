# Der Aufbau, in zwei Bildern und einem Lesepfad

Dieses Projekt hat **mehr Erklärung als Code** — rund 11'600 Zeilen Prosa
gegen 10'569 Zeilen Produktionscode, verteilt auf 294 Docstrings, 475
Test-Docstrings und elf Dokumente. Was fehlte, war kein weiterer Text,
sondern ein **Weg hinein**. Der steht hier.

Beide Bilder werden von
[`tools/build_architekturbilder.py`](../tools/build_architekturbilder.py)
**aus dem Code erzeugt**, nicht gezeichnet. Ein Test prüft, dass ein zweiter
Lauf dieselbe Datei liefert — dieselbe Regel wie bei den Crosswalks und beim
Feldkatalog. Ein von Hand gezeichnetes Bild wäre am Tag darauf falsch.

---

## 1 · Wer wessen Code benutzt

![Abhängigkeiten zwischen den Paketen](bilder/architektur-pakete.svg)

Zehn Pakete, 19 Kanten, **keine Zyklen** — das prüft ein Test, denn es ist
eine Aussage über die Architektur und nicht über die Zeichnung.

**Warum nur drei Pfeile gezeichnet sind.** Sechzehn der neunzehn Kanten
zeigen auf `manifeste` und `storage`. Alle zu zeichnen ergibt ein Knäuel, in
dem die drei übrigen untergehen — und genau die tragen die Aussage. Die
beiden Fundamente stehen deshalb als Band darunter, und die Bildunterschrift
sagt, wer sie benutzt.

**Was das Bild über den Entwurf sagt.** `manifeste` hängt an nichts,
`storage` nur an `manifeste`. Darüber liegt alles andere, und zwischen den
fünf Ingestion-Paketen gibt es **keine einzige Kante**: Chicago weiss nichts
von Detroit. Sie teilen sich nur, wie ein Lauf aussieht (`manifeste`) und wo
er liegt (`storage`).

**Die Lücke, die dieses Bild geschlossen hat.** Konzept 5.3 führte unter
*Data Architecture* wochenlang *„kein Diagramm der Abhängigkeitskanten"*.

---

## 2 · Was beim Laufen geschieht

![Der Datenfluss in vier Gruppen](bilder/architektur-datenfluss.svg)

Erzeugt aus `orchestration.run_all.STUFEN` — die dreizehn Stufen sind im Code
bereits eine Datenstruktur, das Bild liest sie nur ab. Kommt eine Stufe dazu,
steht sie hier, ohne dass jemand daran denken muss.

### Die beiden Bilder sagen Verschiedenes — und das ist die Pointe

Im ersten Bild fehlt eine Kante von `silver_pipeline` zu
`chicago_pipeline`, obwohl Silver Chicagos Daten liest. Im zweiten Bild steht
sie. Kein Widerspruch, sondern der Entwurf:

> **Die Schichten hängen an Dateien, nicht aneinander.**

`silver_pipeline` liest Chicagos Bronze-Läufe über die Ablage — über
`manifest.json` und Parquet, nicht über einen Import. Die einzigen beiden
Code-Kanten nach unten (`census_pipeline`, `weather_pipeline`) holen
Konstanten: die Bundesstaatsnummern und die Stationskennungen.

Das ist der Grund, warum eine dritte Stadt keine Änderung an Silver
erzwingt — und warum der Storage-Umbau die Pipelines nicht angefasst hat.

---

## 3 · Ein Lesepfad

Wer zwanzig Minuten hat und verstehen will, wie das Ganze funktioniert, liest
diese sechs Stellen in dieser Reihenfolge. Zusammen sind es rund 400 Zeilen.

| | Wo | Was man danach weiss |
| --- | --- | --- |
| 1 | [`README.md`](../README.md), Abschnitt 2.0 | welche Befehle es gibt und was sie tun |
| 2 | `orchestration/run_all.py` → `STUFEN` | die ganze Strecke in einer Datenstruktur, mit der Reihenfolge und ihrer Begründung |
| 3 | `manifeste/__init__.py` → Modul-Docstring, `Lauf`, `fertige_laeufe` | was ein *Lauf* ist, warum es zwei Status-Vokabulare gibt und wie sie zusammenkommen |
| 4 | `silver_pipeline/build_crime_offense.py` → Modul-Docstring | die fünf Deutungen, die aus zwei Städten eine Tabelle machen — Delikt, Zeitzone, NIBRS, Raum, Granularität |
| 5 | dieselbe Datei → `build_query` | wie das in SQL aussieht: zwei Städte, zwei CTEs, ein `UNION ALL` |
| 6 | `gold_pipeline/build_gold.py` → `fact_offense_query` | der einzige Stellenwechsel zwischen Silver und Gold, und warum es ihn braucht |

Danach lohnen sich je nach Interesse:

* **Warum eine Zahl so ist, wie sie ist** → [`ln1_konzept.md`](ln1_konzept.md)
  Kapitel 5.2 (Serving und Gold), 8.5 und 8.6 (zwei Befunde, die keine
  Fehlermeldung erzeugt hätten)
* **Wo die Daten liegen** → [`storage-architektur.md`](storage-architektur.md)
* **Was eine Spalte bedeutet** → [`feldkatalog.md`](feldkatalog.md), erzeugt
  aus den Manifesten
* **Warum etwas so gekommen ist** → [`AENDERUNGEN.md`](AENDERUNGEN.md)

### Die Tests sind der zweite Lesepfad

475 Test-Docstrings, und sie sind keine Floskeln — sie sagen, *warum* eine
Zusage besteht:

> *„Die Drift, die dreimal passiert ist: eine Lücke, die längst geschlossen
> war."*
> *„Der Fall, für den es das Gate gibt."*

```bash
python -m pytest --collect-only -q
```

Das ist die Liste dessen, was dieses Projekt über sich selbst prüft.

### Und vier Befehle, die zeigen statt behaupten

```bash
python -m orchestration.run_all --trocken   # 13 Stufen, in Reihenfolge
python -m storage                            # wo die Daten liegen, welcher Stand
python -m orchestration.drift                # wie weit die Zahlen vom Referenzstand weg sind
python -m orchestration.aufraeumen           # was bleiben muss und warum
```
