"""Tests fuer das Drift-Werkzeug.

Eine Zusage steht ueber allen: **Es scheitert nie.** Der Datenlauf ruft es
nach den Tests, auch wenn die Strecke abgebrochen ist - dann steht "nicht
gebaut" in der Zeile, und der Lauf bleibt lesbar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

import drift as dr


KOPF = """# Titel

## Der Stand in Zahlen

| | |
| --- | ---: |
| Tests | **752** |
| `silver/crime_offense` | 347'957 Zeilen (Detroit: eine Anklage) |
| `gold/fact_offense` | **344'617** Zeilen (eine Tat) |
| Chicago | 251'516 Delikte · 2'661'953 Einwohner · **94,5** je 1'000 |
| Detroit | 84'658 Delikte · 638'635 Einwohner · **132,6** je 1'000 |
| Fallkorn (`counts_case`) | Chicago 259'243 · Detroit 80'229 Fälle; Detroit **124,6** je 1'000 |

---

## 13.09.2026 · Irgendein Eintrag (#66)
"""


def test_der_kopf_wird_gelesen():
    dok = dr.dokumentiert(KOPF)
    assert dok["silver_rows"] == 347957
    assert dok["gold_rows"] == 344617
    assert dok["chicago_rate"] == 94.5
    assert dok["detroit_einwohner"] == 638635
    assert dok["detroit_faelle"] == 80229
    assert dok["detroit_rate_fallkorn"] == 124.6


def test_dieselben_muster_wie_die_waechter():
    """Was hier gelesen wird, muss auch AENDERUNGEN.md heute hergeben."""
    echt = Path(__file__).resolve().parents[2] / "docs" / "AENDERUNGEN.md"
    dok = dr.dokumentiert(echt.read_text(encoding="utf-8"))
    assert set(dok) == {s for s, *_ in dr.GROESSEN}, (
        f"nicht gefunden: {sorted({s for s, *_ in dr.GROESSEN} - set(dok))}"
    )


def baue_daten(data_root: Path) -> None:
    con = duckdb.connect()
    for tabelle, sql in (
        ("silver/dataset=crime_offense",
         "SELECT * FROM (VALUES (1), (2), (3), (4)) AS t(x)"),
        ("gold/dataset=fact_offense",
         "SELECT * FROM (VALUES "
         "('chicago', 'T1', true), ('chicago', 'T1', false), "
         "('detroit', 'T2', true)) AS t(reporting_city, tract_geoid, counts_case)"),
        ("gold/dataset=dim_tract",
         "SELECT * FROM (VALUES ('T1', 'chicago', 1000), ('T2', 'detroit', 500)) "
         "AS t(geoid, city, population)"),
    ):
        ordner = data_root / tabelle
        ordner.mkdir(parents=True)
        con.execute(f"COPY ({sql}) TO '{ordner / 'part-0001.parquet'}' (FORMAT PARQUET)")
    con.close()


def test_gemessen_liest_die_tabellen(tmp_path):
    baue_daten(tmp_path)
    mess = dr.gemessen(tmp_path)
    assert mess["silver_rows"] == 4
    assert mess["gold_rows"] == 3
    assert mess["chicago_delikte"] == 2 and mess["chicago_einwohner"] == 1000
    assert mess["chicago_rate"] == 2.0            # 2 * 1000 / 1000
    assert mess["chicago_faelle"] == 1
    assert mess["detroit_rate"] == 2.0 and mess["detroit_rate_fallkorn"] == 2.0


def test_ohne_daten_ist_nichts_gemessen_und_nichts_kaputt(tmp_path):
    assert dr.gemessen(tmp_path) == {}
    text = dr.tabelle(dr.zeilen(dr.dokumentiert(KOPF), {}))
    assert "nicht gebaut" in text and "347'957" in text


def test_die_drift_ist_eine_zahl_mit_vorzeichen():
    (z,) = [z for z in dr.zeilen({"silver_rows": 100}, {"silver_rows": 103})
            if z.schluessel == "silver_rows"]
    assert z.drift == 3 and z.prozent == 3.0
    assert "| +3 | +3,00 |" in dr.tabelle([z])


def test_main_scheitert_nie_und_schreibt_beides(tmp_path, monkeypatch, capsys):
    aenderungen = tmp_path / "AENDERUNGEN.md"
    aenderungen.write_text(KOPF, encoding="utf-8")
    summary = tmp_path / "summary.md"
    ausgabe = tmp_path / "out" / "drift.json"
    monkeypatch.setattr(sys, "argv", [
        "drift", "--data-root", str(tmp_path / "leer"), "--aenderungen", str(aenderungen),
        "--summary", str(summary), "--json", str(ausgabe),
    ])
    assert dr.main() == 0
    assert "Drift gegen den dokumentierten Stand" in capsys.readouterr().out
    assert "nicht gebaut" in summary.read_text(encoding="utf-8")
    ergebnis = json.loads(ausgabe.read_text(encoding="utf-8"))
    assert ergebnis["measures"]["silver_rows"] == {
        "documented": 347957, "measured": None, "drift": None, "drift_percent": None,
    }


def test_der_fingerabdruck_kommt_aus_dem_gesamtmanifest(tmp_path):
    """Der erste Datenlauf zeigte "fingerprint None": das Werkzeug las einen
    Schluessel, den run_all nie schreibt. Gelesen wird jetzt derselbe Name,
    den der Controller schreibt - und der Test haelt beide zusammen."""
    import run_all
    assert '"input_fingerprint"' in Path(run_all.__file__).read_text(encoding="utf-8")
    (tmp_path / "pipeline_run.json").write_text(
        json.dumps({"input_fingerprint": "b1c239ec75b7ee656d74ff006413884049f5bc50"}),
        encoding="utf-8")
    assert dr.fingerabdruck_von(tmp_path) == "b1c239ec75b7ee65"
    assert dr.fingerabdruck_von(tmp_path / "leer") is None
