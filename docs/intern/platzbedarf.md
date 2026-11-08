# Platzbedarf: gemessen und hochgerechnet

**Erzeugt, nicht geschrieben** — die Zahlen hier kommen aus einer Messung über `storage` und einer Rechnung je Quelle, nicht aus einem
Faktor. Geschrieben von [`tools/build_platzbedarf.py`](../../tools/build_platzbedarf.py), gerechnet in [`orchestration.platzbedarf`](../../src/crime/orchestration/platzbedarf.py).

```bash
python tools/build_platzbedarf.py
```

Die Frage dahinter ist FR-40: Was kostet der Mehrjahreslauf 2021–2026? Und daran hängt FR-52 — ob die Datenabgabe in Moodles 1-GB-Grenze
passt. Bis zum 4.10.2026 war die Antwort **ein Faktor**: 1'874'417 Zeilen gegen 348'341 sind das 5,38-Fache, aufgerundet 5,5, angewandt
auf ganz `data/`. Daran war dreierlei falsch — ein Zeilenverhältnis ist kein Byteverhältnis, nicht alles wächst mit den Jahren, und die
Basis war der angehäufte Bestand statt eines Jahrgangs. Aus dem einen Faktor sind vier Regeln geworden.

## 1 Gemessen: die Belegung je Schicht

Stand der Daten: Release `2026-11-07T13-12-32Z`. Gemessen über `storage.Storage.bytes_unter` — `.part`-Verzeichnisse zählen nicht,
und im Hybridmodus wird eine Datei, die lokal und auf SeaweedFS liegt, einmal gezählt. Dieses Dokument misst **nur lokal**.

**Dieselbe Tabelle steht in `docs/architektur-ist-und-ziel.md` (A.1) und als SVG-Text in `docs/architektur-einseiter.html`.**
`tests/test_platzbedarf_dokumente.py` hält beide gegen diese Messung; eine Stelle allein nachzuziehen genügt nicht.

| Schicht | Grösse | Dateien |
| --- | ---: | ---: |
| **raw** | 358,4 MB | 668 |
| **bronze** | 422,9 MB | 116 |
| **silver** | 213,7 MB | 22 |
| **gold** | 85,7 MB | 14 |
| **serving** | 1,3 MB | 15 |
| **releases** | 1'116,3 MB | 251 |
| zusammen | **2'198,4 MB** | 1086 |

## 2 Gerechnet: vier Regeln für 2021–2026

Basis ist **ein** Jahrgang je Quelle. In `bronze`, `raw` und `releases` liegt je Jahr ein eigener Lauf, ein Lauf ist also schon eine Basis. In `gold`, `serving` und `silver` stehen dagegen alle Jahrgänge in denselben Dateien — 2021–2026 in einem Stand —, und dort teilt die Rechnung die sechs Jahrgänge wieder heraus.
Basis **je Quelle und Vintage** ist dabei der *grösste* Lauf,
nicht die Summe ihrer Läufe: `raw/city=chicago` trägt heute 14 Läufe. Sie zu addieren
hiesse, das Anhäufen mitzurechnen — dieselbe Falle wie „den Bestand aus Bronze lesen“, diesmal in der Basis.

Die Zeilen je Stadt und Jahr sind gemessene Fremddaten und stehen mit Datum und Adresse in `config/zeilen_je_jahrgang.csv`
(gemessen am 2026-10-03).

| Regel | Wie sie rechnet | Basis je Jahrgang | 2021–2026 |
| --- | --- | ---: | ---: |
| **Taten** | Zeilen je Jahr × Bytes je Zeile | 227,8 MB | 506,8 MB |
| **Census** | distinkte ACS-Vintages × Kosten je Vintage | 372,5 MB | 376,8 MB |
| **konstant** | wächst nicht mit den Jahren | 25,0 MB | 25,0 MB |
| **Releases** | Inhalt eines Standes hochgerechnet, dann × 8 Stände | 181,4 MB | 7'789,9 MB |
| zusammen | | 806,6 MB | **8'698,4 MB** (8,70 GB) |

Warum die Regeln verschieden rechnen:

* **Taten** — Detroits Zeile kostet in Bronze rund dreimal so viel wie Chicagos. Ein Zeilenverhältnis über beide Städte hinweg
  wäre deshalb falsch; gerechnet wird je Stadt mit ihren eigenen Bytes je Zeile.
* **Census** — es wachsen nicht die Jahre, sondern die **Vintages**. 2021–2026 braucht vier davon, nicht sechs:
  Für 2025 und 2026 gibt es kein ACS-5-Jahres-Vintage, sie borgen das von 2024 (`census_pipeline.vintage_for`).
* **konstant** — GHCN-Daily liefert immer die ganze Reihe einer Station. Ein längerer Bereich kostet dort keine Byte mehr als ein
  einzelner Jahrgang. Dasselbe gilt für Marken und Zeiger.
* **Releases** — `aufraeumen.RELEASES_N` = 8 Stände bleiben liegen. Ein Release ist dabei kein Fass mit einer Grösse, sondern eine
  eingefrorene Kopie von Gold und Serving; sein **Inhalt** wird zuerst hochgerechnet und erst dann mit der Zahl der Stände genommen.
  Gemessen ist der **grösste** der zehn liegenden Stände, 181,4 MB — die Stände unterscheiden sich
  untereinander um Zehntel-MB, und die grössere Zahl ist hier die ehrlichere.

## 3 Je Quelle: Basis, Regel, Ergebnis

Eine Zeile je Quelle und Schicht. „Läufe“ sagt, aus wie vielen Läufen der Bestand dieser Quelle besteht — die Basis ist der grösste
davon.

### `raw`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `city=chicago` | 14 | 17,9 MB | Taten: 1'382'937 Zeilen × 69,1 Bytes je Zeile | 95,6 MB |
| `city=detroit` | 13 | 10,7 MB | Taten: 491'480 Zeilen × 121,0 Bytes je Zeile | 59,5 MB |
| `dataset=acs5_tract` | 4 | 0,4 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage | 0,4 MB |
| `dataset=noaa_ghcnd` | 3 | 21,1 MB | konstant: wächst nicht mit den Jahren | 21,1 MB |
| `dataset=tiger_place` | 4 | 30,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 7,6 MB je Vintage | 30,2 MB |
| `dataset=tiger_tract` | 4 | 62,4 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 15,6 MB je Vintage | 62,4 MB |

### `bronze`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `city=chicago` | 14 | 17,2 MB | Taten: 1'382'937 Zeilen × 66,3 Bytes je Zeile | 91,6 MB |
| `city=detroit` | 14 | 17,2 MB | Taten: 491'480 Zeilen × 194,2 Bytes je Zeile | 95,5 MB |
| `dataset=acs5_tract` | 4 | 0,9 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage | 0,9 MB |
| `dataset=noaa_ghcnd` | 3 | 3,4 MB | konstant: wächst nicht mit den Jahren | 3,4 MB |
| `dataset=tiger_place` | 4 | 44,8 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 11,2 MB je Vintage | 44,8 MB |
| `dataset=tiger_tract` | 4 | 98,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 24,5 MB je Vintage | 98,1 MB |

### `silver`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `dataset=crime_offense` | 1 | 79,0 MB | Taten: 1'874'417 Zeilen × 42,1 Bytes je Zeile | 79,0 MB |
| `dataset=place` | 1 | 44,9 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 11,2 MB je Vintage | 44,9 MB |
| `dataset=source_change` | 1 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile | 0,1 MB |
| `dataset=tract` | 1 | 89,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 22,3 MB je Vintage | 89,2 MB |
| `dataset=weather_day` | 1 | 0,4 MB | konstant: wächst nicht mit den Jahren | 0,4 MB |

### `gold`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `dataset=dim_city_day` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |
| `dataset=dim_date` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=dim_offense` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=dim_tract` | 1 | 0,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage | 0,8 MB |
| `dataset=dim_tract_acs` | 1 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage | 2,0 MB |
| `dataset=dim_tract_geo` | 1 | 0,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage | 0,6 MB |
| `dataset=fact_offense` | 1 | 84,8 MB | Taten: 1'874'417 Zeilen × 45,2 Bytes je Zeile | 84,8 MB |

### `serving`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `analyse.duckdb` | 1 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile | 0,3 MB |
| `dataset=comparison_day` | 1 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile | 0,3 MB |
| `dataset=comparison_month` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=comparison_week` | 1 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,1 MB |
| `dataset=partition_quality` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=rate_tract` | 1 | 0,0 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,0 MB je Vintage | 0,1 MB |
| `dataset=source_movement` | 1 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile | 0,1 MB |
| `tracts.geojson` | 1 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage | 2,2 MB |
| `tracts.manifest.json` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |

### `releases`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `gold/dataset=dim_city_day` | 10 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,3 MB |
| `gold/dataset=dim_date` | 10 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile, dann × 8 Stände | 0,9 MB |
| `gold/dataset=dim_offense` | 10 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,4 MB |
| `gold/dataset=dim_tract` | 10 | 0,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage, dann × 8 Stände | 6,5 MB |
| `gold/dataset=dim_tract_acs` | 10 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage, dann × 8 Stände | 16,2 MB |
| `gold/dataset=dim_tract_geo` | 10 | 0,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage, dann × 8 Stände | 4,4 MB |
| `gold/dataset=fact_offense` | 10 | 84,8 MB | Taten: 1'874'417 Zeilen × 243,5 Bytes je Zeile, dann × 8 Stände | 3'651,1 MB |
| `release.json` | 10 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,1 MB |
| `serving/analyse.duckdb` | 10 | 94,6 MB | Taten: 1'874'417 Zeilen × 271,7 Bytes je Zeile, dann × 8 Stände | 4'074,3 MB |
| `serving/dataset=comparison_day` | 10 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,7 Bytes je Zeile, dann × 8 Stände | 11,1 MB |
| `serving/dataset=comparison_month` | 10 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile, dann × 8 Stände | 1,6 MB |
| `serving/dataset=comparison_week` | 10 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,2 Bytes je Zeile, dann × 8 Stände | 3,4 MB |
| `serving/dataset=partition_quality` | 10 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile, dann × 8 Stände | 0,8 MB |
| `serving/dataset=rate_tract` | 10 | 0,0 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,0 MB je Vintage, dann × 8 Stände | 1,2 MB |
| `serving/tracts.geojson` | 10 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage, dann × 8 Stände | 17,5 MB |
| `serving/tracts.manifest.json` | 10 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,0 MB |
| `AKTUELL.json` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |

## 4 Was daraus folgt

* **2021–2026 braucht 8'698,4 MB (8,70 GB)**. Dieselbe Rechnung für **einen** Jahrgang (2024) ergibt 1'663,8 MB — 2021–2026 ist also
  das **5,23-Fache eines Jahrgangs** und nicht das 5,5-Fache. Verglichen wird dabei Rechnung mit Rechnung: Das heutige
  `data/` (2'198,4 MB) hält 14 `city=chicago`-Läufe und zehn Release-Stände und ist mit keiner
  der beiden Zahlen vergleichbar — genau diese Verwechslung steckte im alten Faktor.
* **Ohne `releases/` sind es 908,5 MB** (0,91 GB), ohne `releases/` **und** `raw/` noch 639,3 MB (0,64 GB).
  Das sind die Zahlen, die für FR-52 zählen: Eine Abgabe braucht nicht acht Stände, und sie braucht die
  Beweisstücke nicht mitzuschicken.
* **Moodles Grenze von 1 GB**: Der ganze Bestand liegt mit 8,70 GB weit darüber. Ohne `releases/` liegt er mit 0,91 GB knapp darunter, ohne `raw/` dazu mit 0,64 GB deutlich. Reserve ist das keine: Ein Jahrgang mehr hebt ihn wieder darüber.
  Entschieden ist das nicht hier, sondern in FR-52 — entweder eine Stichprobe mit Link auf den Vollbestand oder die Abgabe über den
  Abgabebranch statt über Moodle.
* **Gerechnet ist ein Lauf je Quelle und Jahrgang**, nicht ein `data/`, das wochenlang mitläuft. Was darüber hinaus anfällt, ist eine
  Frage der Aufbewahrung und nicht der Hochrechnung: `python -m orchestration.aufraeumen` sagt, was weg darf.

## 5 Nachmessen

```bash
python -m orchestration.platzbedarf --data-root data
python -m orchestration.platzbedarf --jahre 2021-2026 --json
```

Nach jedem Neubau gehört `python tools/build_platzbedarf.py` dazu, sonst nennt `pytest -m referenzstand` die Stelle.
