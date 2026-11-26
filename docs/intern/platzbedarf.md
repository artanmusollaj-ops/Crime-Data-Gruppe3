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

Stand der Daten: Release `approved-9d265b70c6c34683b8cf7b5ae033f8a6-435090e1`. Gemessen über `storage.Storage.bytes_unter` — `.part`-Verzeichnisse zählen nicht,
und im Hybridmodus wird eine Datei, die lokal und auf SeaweedFS liegt, einmal gezählt. Dieses Dokument misst **nur lokal**.

**Dieselbe Tabelle steht in `docs/architektur-ist-und-ziel.md` (A.1) und als SVG-Text in `docs/architektur-einseiter.html`.**
`tests/test_platzbedarf_dokumente.py` hält beide gegen diese Messung; eine Stelle allein nachzuziehen genügt nicht.

| Schicht | Grösse | Dateien |
| --- | ---: | ---: |
| **raw** | 605,8 MB | 1419 |
| **bronze** | 650,3 MB | 396 |
| **silver** | 224,2 MB | 26 |
| **gold** | 91,0 MB | 22 |
| **serving** | 3,1 MB | 15 |
| **releases** | 2'051,0 MB | 397 |
| zusammen | **3'625,5 MB** | 2275 |

## 2 Gerechnet: vier Regeln für 2021–2026

Basis ist **ein** Jahrgang je Quelle. In `bronze` und `raw` liegt je Jahr ein eigener Lauf, ein Lauf ist also schon eine Basis. In `gold`, `releases`, `serving` und `silver` stehen dagegen alle Jahrgänge in denselben Dateien — 2021–2026 in einem Stand —, und dort teilt die Rechnung die sechs Jahrgänge wieder heraus.
Basis **je Quelle und Vintage** ist dabei der *grösste* Lauf,
nicht die Summe ihrer Läufe: `raw/city=chicago` trägt heute 74 Läufe. Sie zu addieren
hiesse, das Anhäufen mitzurechnen — dieselbe Falle wie „den Bestand aus Bronze lesen“, diesmal in der Basis.

Die Zeilen je Stadt und Jahr sind gemessene Fremddaten und stehen mit Datum und Adresse in `config/zeilen_je_jahrgang.csv`
(gemessen am 2026-10-03).

| Regel | Wie sie rechnet | Basis je Jahrgang | 2021–2026 |
| --- | --- | ---: | ---: |
| **Taten** | Zeilen je Jahr × Bytes je Zeile | 242,6 MB | 521,6 MB |
| **Census** | distinkte ACS-Vintages × Kosten je Vintage | 373,6 MB | 377,7 MB |
| **konstant** | wächst nicht mit den Jahren | 31,6 MB | 31,6 MB |
| **Releases** | Inhalt eines Standes hochgerechnet, dann × 8 Stände | 359,2 MB | 2'908,4 MB |
| zusammen | | 1'007,0 MB | **3'839,3 MB** (3,84 GB) |

Warum die Regeln verschieden rechnen:

* **Taten** — Detroits Zeile kostet in Bronze rund dreimal so viel wie Chicagos. Ein Zeilenverhältnis über beide Städte hinweg
  wäre deshalb falsch; gerechnet wird je Stadt mit ihren eigenen Bytes je Zeile.
* **Census** — es wachsen nicht die Jahre, sondern die **Vintages**. 2021–2026 braucht vier davon, nicht sechs:
  Für 2025 und 2026 gibt es kein ACS-5-Jahres-Vintage, sie borgen das von 2024 (`census_pipeline.vintage_for`).
* **konstant** — GHCN-Daily liefert immer die ganze Reihe einer Station. Ein längerer Bereich kostet dort keine Byte mehr als ein
  einzelner Jahrgang. Dasselbe gilt für Marken und Zeiger.
* **Releases** — `aufraeumen.RELEASES_N` = 8 Stände bleiben liegen. Ein Release ist dabei kein Fass mit einer Grösse, sondern eine
  eingefrorene Kopie von Gold und Serving; sein **Inhalt** wird zuerst hochgerechnet und erst dann mit der Zahl der Stände genommen.
  Gemessen ist der **grösste** der 14 liegenden Stände, 359,2 MB — die Stände unterscheiden sich
  untereinander um Zehntel-MB, und die grössere Zahl ist hier die ehrlichere.

## 3 Je Quelle: Basis, Regel, Ergebnis

Eine Zeile je Quelle und Schicht. „Läufe“ sagt, aus wie vielen Läufen der Bestand dieser Quelle besteht — die Basis ist der grösste
davon.

### `raw`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `city=chicago` | 74 | 17,9 MB | Taten: 1'382'937 Zeilen × 69,1 Bytes je Zeile | 95,6 MB |
| `city=detroit` | 73 | 10,7 MB | Taten: 491'480 Zeilen × 121,0 Bytes je Zeile | 59,5 MB |
| `dataset=acs5_tract` | 4 | 0,4 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage | 0,4 MB |
| `dataset=gebiete` | 5 | 3,5 MB | konstant: wächst nicht mit den Jahren | 3,5 MB |
| `dataset=noaa_ghcnd` | 6 | 21,1 MB | konstant: wächst nicht mit den Jahren | 21,1 MB |
| `dataset=tiger_place` | 4 | 30,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 7,6 MB je Vintage | 30,2 MB |
| `dataset=tiger_tract` | 4 | 62,4 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 15,6 MB je Vintage | 62,4 MB |

### `bronze`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `city=chicago` | 74 | 17,2 MB | Taten: 1'382'937 Zeilen × 66,3 Bytes je Zeile | 91,6 MB |
| `city=detroit` | 74 | 17,2 MB | Taten: 491'480 Zeilen × 194,2 Bytes je Zeile | 95,5 MB |
| `dataset=acs5_tract` | 4 | 0,9 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage | 0,9 MB |
| `dataset=gebiete` | 5 | 1,3 MB | konstant: wächst nicht mit den Jahren | 1,3 MB |
| `dataset=noaa_ghcnd` | 6 | 3,4 MB | konstant: wächst nicht mit den Jahren | 3,4 MB |
| `dataset=tiger_place` | 4 | 44,8 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 11,2 MB je Vintage | 44,8 MB |
| `dataset=tiger_tract` | 4 | 98,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 24,5 MB je Vintage | 98,1 MB |

### `silver`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `dataset=community_area` | 1 | 0,9 MB | konstant: wächst nicht mit den Jahren | 0,9 MB |
| `dataset=crime_offense` | 1 | 85,2 MB | Taten: 1'874'417 Zeilen × 45,4 Bytes je Zeile | 85,2 MB |
| `dataset=place` | 1 | 45,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 11,3 MB je Vintage | 45,2 MB |
| `dataset=police_area` | 1 | 0,4 MB | konstant: wächst nicht mit den Jahren | 0,4 MB |
| `dataset=source_change` | 1 | 1,9 MB | Taten: 1'874'417 Zeilen × 1,0 Bytes je Zeile | 1,9 MB |
| `dataset=tract` | 1 | 90,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 22,5 MB je Vintage | 90,1 MB |
| `dataset=weather_day` | 1 | 0,4 MB | konstant: wächst nicht mit den Jahren | 0,4 MB |

### `gold`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `dataset=bridge_tract_community_area` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |
| `dataset=bridge_tract_police_area` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |
| `dataset=dim_city_day` | 1 | 0,1 MB | konstant: wächst nicht mit den Jahren | 0,1 MB |
| `dataset=dim_community_area` | 1 | 0,2 MB | konstant: wächst nicht mit den Jahren | 0,2 MB |
| `dataset=dim_date` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=dim_offense` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=dim_police_area` | 1 | 0,1 MB | konstant: wächst nicht mit den Jahren | 0,1 MB |
| `dataset=dim_tract` | 1 | 0,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage | 0,8 MB |
| `dataset=dim_tract_acs` | 1 | 0,4 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,4 MB je Vintage | 1,8 MB |
| `dataset=dim_tract_geo` | 1 | 0,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage | 0,6 MB |
| `dataset=fact_offense` | 1 | 89,7 MB | Taten: 1'874'417 Zeilen × 47,9 Bytes je Zeile | 89,7 MB |

### `serving`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `analyse.duckdb` | 1 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile | 0,3 MB |
| `dataset=comparison_day` | 1 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile | 0,3 MB |
| `dataset=comparison_month` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=comparison_week` | 1 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,1 MB |
| `dataset=partition_quality` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=rate_tract` | 1 | 0,0 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,0 MB je Vintage | 0,2 MB |
| `dataset=source_movement` | 1 | 1,8 MB | Taten: 1'874'417 Zeilen × 1,0 Bytes je Zeile | 1,8 MB |
| `tracts.geojson` | 1 | 0,6 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,6 MB je Vintage | 2,2 MB |
| `tracts.manifest.json` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |

### `releases`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `admin/approval.json` | 14 | 0,2 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile, dann × 8 Stände | 2,0 MB |
| `admin/config` | 14 | 0,1 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,6 MB |
| `admin/impact_by_partition.parquet` | 14 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,3 MB |
| `admin/impact_quality.parquet` | 14 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile, dann × 8 Stände | 2,0 MB |
| `admin/impact_quality_month.parquet` | 14 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,1 MB |
| `admin/impact_records.parquet` | 14 | 1,4 MB | Taten: 1'874'417 Zeilen × 0,7 Bytes je Zeile, dann × 8 Stände | 10,9 MB |
| `admin/impact_report.json` | 14 | 0,7 MB | Taten: 1'874'417 Zeilen × 0,4 Bytes je Zeile, dann × 8 Stände | 5,4 MB |
| `admin/source_snapshot.json` | 14 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,3 MB |
| `gold/dataset=dim_city_day` | 14 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,3 MB |
| `gold/dataset=dim_date` | 14 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,2 MB |
| `gold/dataset=dim_offense` | 14 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,1 MB |
| `gold/dataset=dim_tract` | 14 | 0,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage, dann × 8 Stände | 6,5 MB |
| `gold/dataset=dim_tract_acs` | 14 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage, dann × 8 Stände | 16,2 MB |
| `gold/dataset=dim_tract_geo` | 14 | 0,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage, dann × 8 Stände | 4,5 MB |
| `gold/dataset=fact_offense` | 14 | 86,8 MB | Taten: 1'874'417 Zeilen × 46,3 Bytes je Zeile, dann × 8 Stände | 694,4 MB |
| `release.json` | 14 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,1 MB |
| `serving/analyse.duckdb` | 14 | 183,5 MB | Taten: 1'874'417 Zeilen × 97,9 Bytes je Zeile, dann × 8 Stände | 1'468,1 MB |
| `serving/dataset=comparison_day` | 14 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile, dann × 8 Stände | 2,1 MB |
| `serving/dataset=comparison_month` | 14 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,3 MB |
| `serving/dataset=comparison_week` | 14 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,7 MB |
| `serving/dataset=partition_quality` | 14 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,2 MB |
| `serving/dataset=rate_tract` | 14 | 0,0 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,0 MB je Vintage, dann × 8 Stände | 1,3 MB |
| `serving/dataset=source_movement` | 14 | 1,8 MB | Taten: 1'874'417 Zeilen × 1,0 Bytes je Zeile, dann × 8 Stände | 14,8 MB |
| `serving/tracts.geojson` | 14 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage, dann × 8 Stände | 17,5 MB |
| `serving/tracts.manifest.json` | 14 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,0 MB |
| `silver/dataset=crime_offense` | 14 | 80,5 MB | Taten: 1'874'417 Zeilen × 43,0 Bytes je Zeile, dann × 8 Stände | 644,1 MB |
| `silver/dataset=source_change` | 14 | 1,9 MB | Taten: 1'874'417 Zeilen × 1,0 Bytes je Zeile, dann × 8 Stände | 15,5 MB |
| `AKTUELL.json` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |

## 4 Was daraus folgt

* **2021–2026 braucht 3'839,3 MB (3,84 GB)**. Dieselbe Rechnung für **einen** Jahrgang (2024) ergibt 766,8 MB — 2021–2026 ist also
  das **5,01-Fache eines Jahrgangs** und nicht das 5,5-Fache. Verglichen wird dabei Rechnung mit Rechnung: Das heutige
  `data/` (3'625,5 MB) hält 74 `city=chicago`-Läufe und 14 Release-Stände und ist mit keiner
  der beiden Zahlen vergleichbar — genau diese Verwechslung steckte im alten Faktor.
* **Ohne `releases/` sind es 930,9 MB** (0,93 GB), ohne `releases/` **und** `raw/` noch 658,1 MB (0,66 GB).
  Das sind die Zahlen, die für FR-52 zählen: Eine Abgabe braucht nicht acht Stände, und sie braucht die
  Beweisstücke nicht mitzuschicken.
* **Moodles Grenze von 1 GB**: Der ganze Bestand liegt mit 3,84 GB weit darüber. Ohne `releases/` liegt er mit 0,93 GB knapp darunter, ohne `raw/` dazu mit 0,66 GB deutlich. Reserve ist das keine: Ein Jahrgang mehr hebt ihn wieder darüber.
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
