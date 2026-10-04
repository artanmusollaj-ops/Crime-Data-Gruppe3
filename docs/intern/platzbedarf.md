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

Stand der Daten: Release `2026-10-03T19-53-12Z`. Gemessen über `storage.Storage.bytes_unter` — `.part`-Verzeichnisse zählen nicht,
und im Hybridmodus wird eine Datei, die lokal und auf SeaweedFS liegt, einmal gezählt. Dieses Dokument misst **nur lokal**.

**Dieselbe Tabelle steht in `docs/architektur-ist-und-ziel.md` (A.1) und als SVG-Text in `docs/architektur-einseiter.html`.**
`tests/test_platzbedarf_dokumente.py` hält beide gegen diese Messung; eine Stelle allein nachzuziehen genügt nicht.

| Schicht | Grösse | Dateien |
| --- | ---: | ---: |
| **raw** | 143,5 MB | 286 |
| **bronze** | 162,2 MB | 52 |
| **silver** | 49,5 MB | 10 |
| **gold** | 15,3 MB | 12 |
| **serving** | 0,9 MB | 11 |
| **releases** | 254,1 MB | 139 |
| zusammen | **625,5 MB** | 510 |

## 2 Gerechnet: vier Regeln für 2021–2026

Basis ist der Jahrgang 2024, den die gebauten Läufe tragen. Basis **je Quelle und Vintage** ist dabei der *grösste* Lauf,
nicht die Summe ihrer Läufe: `raw/city=chicago` trägt heute acht Läufe. Sie zu addieren
hiesse, das Anhäufen mitzurechnen — dieselbe Falle wie „den Bestand aus Bronze lesen“, diesmal in der Basis.

Die Zeilen je Stadt und Jahr sind gemessene Fremddaten und stehen mit Datum und Adresse in `config/zeilen_je_jahrgang.csv`
(gemessen am 2026-10-03).

| Regel | Wie sie rechnet | Basis je Jahrgang | 2021–2026 |
| --- | --- | ---: | ---: |
| **Taten** | Zeilen je Jahr × Bytes je Zeile | 92,2 MB | 498,8 MB |
| **Census** | distinkte ACS-Vintages × Kosten je Vintage | 94,0 MB | 375,9 MB |
| **konstant** | wächst nicht mit den Jahren | 24,9 MB | 24,9 MB |
| **Releases** | Inhalt eines Standes hochgerechnet, dann × 8 Stände | 42,8 MB | 1'831,1 MB |
| zusammen | | 253,9 MB | **2'730,7 MB** (2,73 GB) |

Warum die Regeln verschieden rechnen:

* **Taten** — Detroits Zeile kostet in Bronze rund dreimal so viel wie Chicagos. Ein Zeilenverhältnis über beide Städte hinweg
  wäre deshalb falsch; gerechnet wird je Stadt mit ihren eigenen Bytes je Zeile.
* **Census** — es wachsen nicht die Jahre, sondern die **Vintages**. 2021–2026 braucht vier davon, nicht sechs:
  Für 2025 und 2026 gibt es kein ACS-5-Jahres-Vintage, sie borgen das von 2024 (`census_pipeline.vintage_for`).
* **konstant** — GHCN-Daily liefert immer die ganze Reihe einer Station. Ein längerer Bereich kostet dort keine Byte mehr als ein
  einzelner Jahrgang. Dasselbe gilt für Marken und Zeiger.
* **Releases** — `aufraeumen.RELEASES_N` = 8 Stände bleiben liegen. Ein Release ist dabei kein Fass mit einer Grösse, sondern eine
  eingefrorene Kopie von Gold und Serving; sein **Inhalt** wird zuerst hochgerechnet und erst dann mit der Zahl der Stände genommen.
  Gemessen ist der **grösste** der sechs liegenden Stände, 42,8 MB — die Stände unterscheiden sich
  untereinander um Zehntel-MB, und die grössere Zahl ist hier die ehrlichere.

## 3 Je Quelle: Basis, Regel, Ergebnis

Eine Zeile je Quelle und Schicht. „Läufe“ sagt, aus wie vielen Läufen der Bestand dieser Quelle besteht — die Basis ist der grösste
davon.

### `raw`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `city=chicago` | 8 | 17,6 MB | Taten: 1'382'937 Zeilen × 67,9 Bytes je Zeile | 93,9 MB |
| `city=detroit` | 7 | 10,4 MB | Taten: 491'480 Zeilen × 117,4 Bytes je Zeile | 57,7 MB |
| `dataset=acs5_tract` | 1 | 0,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage | 0,4 MB |
| `dataset=noaa_ghcnd` | 2 | 21,1 MB | konstant: wächst nicht mit den Jahren | 21,1 MB |
| `dataset=tiger_place` | 1 | 7,6 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 7,6 MB je Vintage | 30,4 MB |
| `dataset=tiger_tract` | 1 | 15,6 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 15,6 MB je Vintage | 62,4 MB |

### `bronze`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `city=chicago` | 8 | 16,7 MB | Taten: 1'382'937 Zeilen × 64,4 Bytes je Zeile | 89,1 MB |
| `city=detroit` | 8 | 16,8 MB | Taten: 491'480 Zeilen × 189,0 Bytes je Zeile | 92,9 MB |
| `dataset=acs5_tract` | 1 | 0,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage | 0,9 MB |
| `dataset=noaa_ghcnd` | 2 | 3,4 MB | konstant: wächst nicht mit den Jahren | 3,4 MB |
| `dataset=tiger_place` | 1 | 11,3 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 11,3 MB je Vintage | 45,1 MB |
| `dataset=tiger_tract` | 1 | 24,6 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 24,6 MB je Vintage | 98,4 MB |

### `silver`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `dataset=crime_offense` | 1 | 15,3 MB | Taten: 1'874'417 Zeilen × 43,8 Bytes je Zeile | 82,2 MB |
| `dataset=place` | 1 | 11,3 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 11,3 MB je Vintage | 45,3 MB |
| `dataset=source_change` | 1 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,3 Bytes je Zeile | 0,5 MB |
| `dataset=tract` | 1 | 22,4 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 22,4 MB je Vintage | 89,5 MB |
| `dataset=weather_day` | 1 | 0,4 MB | konstant: wächst nicht mit den Jahren | 0,4 MB |

### `gold`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `dataset=dim_city_day` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |
| `dataset=dim_date` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,1 MB |
| `dataset=dim_offense` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,0 MB |
| `dataset=dim_tract` | 1 | 0,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage | 0,8 MB |
| `dataset=dim_tract_acs` | 1 | 0,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage | 0,5 MB |
| `dataset=fact_offense` | 1 | 15,0 MB | Taten: 1'874'417 Zeilen × 42,9 Bytes je Zeile | 80,5 MB |

### `serving`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `analyse.duckdb` | 1 | 0,3 MB | Taten: 1'874'417 Zeilen × 0,8 Bytes je Zeile | 1,5 MB |
| `dataset=comparison_day` | 1 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,2 Bytes je Zeile | 0,3 MB |
| `dataset=comparison_month` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,1 MB |
| `dataset=comparison_week` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile | 0,1 MB |
| `dataset=partition_quality` | 1 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile | 0,1 MB |
| `tracts.geojson` | 1 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage | 2,2 MB |
| `tracts.manifest.json` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |

### `releases`

| Quelle | Läufe | Basis je Jahrgang | Regel | 2021–2026 |
| --- | ---: | ---: | --- | ---: |
| `gold/dataset=dim_city_day` | 6 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,1 MB |
| `gold/dataset=dim_date` | 6 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,4 MB |
| `gold/dataset=dim_offense` | 6 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,4 MB |
| `gold/dataset=dim_tract` | 6 | 0,2 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,2 MB je Vintage, dann × 8 Stände | 6,5 MB |
| `gold/dataset=dim_tract_acs` | 6 | 0,1 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,1 MB je Vintage, dann × 8 Stände | 4,1 MB |
| `gold/dataset=fact_offense` | 6 | 15,0 MB | Taten: 1'874'417 Zeilen × 43,1 Bytes je Zeile, dann × 8 Stände | 646,1 MB |
| `release.json` | 6 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,1 MB |
| `serving/analyse.duckdb` | 6 | 26,8 MB | Taten: 1'874'417 Zeilen × 76,8 Bytes je Zeile, dann × 8 Stände | 1'151,6 MB |
| `serving/dataset=comparison_day` | 6 | 0,1 MB | Taten: 1'874'417 Zeilen × 0,2 Bytes je Zeile, dann × 8 Stände | 2,3 MB |
| `serving/dataset=comparison_month` | 6 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,6 MB |
| `serving/dataset=comparison_week` | 6 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,1 Bytes je Zeile, dann × 8 Stände | 1,0 MB |
| `serving/dataset=partition_quality` | 6 | 0,0 MB | Taten: 1'874'417 Zeilen × 0,0 Bytes je Zeile, dann × 8 Stände | 0,4 MB |
| `serving/tracts.geojson` | 6 | 0,5 MB | Census: 4 Vintages (2021, 2022, 2023, 2024) × 0,5 MB je Vintage, dann × 8 Stände | 17,5 MB |
| `serving/tracts.manifest.json` | 6 | 0,0 MB | konstant: wächst nicht mit den Jahren, dann × 8 Stände | 0,0 MB |
| `AKTUELL.json` | 1 | 0,0 MB | konstant: wächst nicht mit den Jahren | 0,0 MB |

## 4 Was daraus folgt

* **2021–2026 braucht 2'730,7 MB (2,73 GB)**. Dieselbe Rechnung für **einen** Jahrgang (2024) ergibt 553,4 MB — 2021–2026 ist also
  das **4,93-Fache eines Jahrgangs** und nicht das 5,5-Fache. Verglichen wird dabei Rechnung mit Rechnung: Das heutige
  `data/` (625,5 MB) hält acht `city=chicago`-Läufe und sechs Release-Stände und ist mit keiner
  der beiden Zahlen vergleichbar — genau diese Verwechslung steckte im alten Faktor.
* **Ohne `releases/` sind es 899,7 MB** (0,90 GB), ohne `releases/` **und** `raw/` noch 633,8 MB (0,63 GB).
  Das sind die Zahlen, die für FR-52 zählen: Eine Abgabe braucht nicht acht Stände, und sie braucht die
  Beweisstücke nicht mitzuschicken.
* **Moodles Grenze von 1 GB**: Der ganze Bestand liegt mit 2,73 GB weit darüber. Ohne `releases/` liegt er mit 0,90 GB knapp darunter, ohne `raw/` dazu mit 0,63 GB deutlich. Reserve ist das keine: Ein Jahrgang mehr hebt ihn wieder darüber.
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
