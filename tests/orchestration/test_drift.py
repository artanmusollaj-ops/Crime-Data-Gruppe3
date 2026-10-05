"""Tests fuer das Drift-Werkzeug.

Zwei Zusagen: Fehlende Tabellen sind keine Drift - dann steht "nicht gebaut"
in der Zeile, und der Lauf bleibt lesbar. Und rot wird es **nur ueber der
Toleranz**: Raten ab 0,1 je 1'000, Zahlen ueber 1 Prozent. Das Wochenrauschen
der Quellen liegt darunter, ein Ausfall darueber.
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
| Fallebene (`counts_case`) | Chicago 259'243 · Detroit 80'229 Fälle; Detroit **124,6** je 1'000 |

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
    assert dok["detroit_rate_fallebene"] == 124.6


def test_dieselben_muster_wie_die_waechter():
    """Was hier gelesen wird, muss auch AENDERUNGEN.md heute hergeben."""
    echt = Path(__file__).resolve().parents[2] / "docs" / "intern" / "AENDERUNGEN.md"
    dok = dr.dokumentiert(echt.read_text(encoding="utf-8"))
    assert set(dok) == {s for s, *_ in dr.GROESSEN}, (
        f"nicht gefunden: {sorted({s for s, *_ in dr.GROESSEN} - set(dok))}"
    )


def baue_daten(data_root: Path) -> None:
    con = duckdb.connect()
    for tabelle, sql in (
        ("silver/dataset=crime_offense",
         "SELECT * FROM (VALUES (1), (2), (3), (4)) AS t(x)"),
        # ``date`` und ``population_vintage`` sind seit dem 4.10.2026 Pflicht:
        # Die Messung filtert auf gold_pipeline.RATENJAHR und nimmt den Nenner,
        # den die Taten dieses Jahres selbst nennen. Die vierte Zeile liegt
        # ausserhalb und darf in keiner Zahl auftauchen - sonst prueft die
        # Zeile unten den Filter nicht.
        ("gold/dataset=fact_offense",
         "SELECT * FROM (VALUES "
         "('chicago', 'T1', true, DATE '2024-03-01', 2024), "
         "('chicago', 'T1', false, DATE '2024-03-02', 2024), "
         "('detroit', 'T2', true, DATE '2024-03-03', 2024), "
         "('chicago', 'T1', true, DATE '2021-03-01', 2021)) "
         "AS t(reporting_city, tract_geoid, counts_case, date, "
         "population_vintage)"),
        # Seit Vertrag 6 traegt dim_tract die Stadtzuordnung und ihr
        # Referenz-Vintage, die Einwohnerzahl steht in dim_tract_acs je Vintage.
        ("gold/dataset=dim_tract",
         "SELECT * FROM (VALUES ('T1', 'chicago', 2024), ('T2', 'detroit', 2024)) "
         "AS t(geoid, city, reference_vintage)"),
        ("gold/dataset=dim_tract_acs",
         "SELECT * FROM (VALUES ('T1', 2024, 1000), ('T2', 2024, 500), "
         "('T1', 2021, 1200), ('T2', 2021, 600)) "
         "AS t(geoid, vintage, population)"),
    ):
        ordner = data_root / tabelle
        ordner.mkdir(parents=True)
        con.execute(f"COPY ({sql}) TO '{ordner / 'part-0001.parquet'}' (FORMAT PARQUET)")
    con.close()


def test_gemessen_liest_die_tabellen(tmp_path):
    """Bestand kumuliert, Stadtzahlen je Jahr - und der Filter greift wirklich.

    ``gold_rows`` zaehlt alle vier Zeilen, die Stadtzahlen nur die drei aus
    ``RATENJAHR``. Die vierte liegt in 2021 und haengt an einem anderen
    Nenner; taucht sie in ``chicago_delikte`` auf, fehlt der Jahresfilter.
    """
    baue_daten(tmp_path)
    mess = dr.gemessen(tmp_path)
    assert mess["silver_rows"] == 4
    assert mess["gold_rows"] == 4
    assert mess["chicago_delikte"] == 2 and mess["chicago_einwohner"] == 1000
    assert mess["chicago_rate"] == 2.0            # 2 * 1000 / 1000
    assert mess["chicago_faelle"] == 1
    assert mess["detroit_rate"] == 2.0 and mess["detroit_rate_fallebene"] == 2.0


def test_ohne_daten_ist_nichts_gemessen_und_nichts_kaputt(tmp_path):
    assert dr.gemessen(tmp_path) == {}
    text = dr.tabelle(dr.zeilen(dr.dokumentiert(KOPF), {}))
    assert "nicht gebaut" in text and "347'957" in text


def test_die_drift_ist_eine_zahl_mit_vorzeichen():
    (z,) = [z for z in dr.zeilen({"silver_rows": 100}, {"silver_rows": 103})
            if z.schluessel == "silver_rows"]
    assert z.drift == 3 and z.prozent == 3.0
    assert "| +3 | +3,00 | **überschritten** |" in dr.tabelle([z])


# --------------------------------------------------------------------------
# Die Toleranz
# --------------------------------------------------------------------------


def zeile(schluessel: str, dok: float, mess: float) -> dr.Zeile:
    (z,) = [z for z in dr.zeilen({schluessel: dok}, {schluessel: mess})
            if z.schluessel == schluessel]
    return z


def test_das_wochenrauschen_liegt_unter_der_toleranz():
    """Der Lauf vom 13.9.: +343 Zeilen (0,10 %), Raten unveraendert."""
    assert not zeile("silver_rows", 347957, 348300).ueber()
    assert not zeile("detroit_rate", 132.6, 132.6).ueber()
    assert not zeile("chicago_faelle", 259243, 259585).ueber()


def test_eine_rate_die_sich_in_der_ersten_stelle_bewegt_ist_zu_weit():
    """0,1 ist die Rundung, in der die Rate zitiert wird."""
    assert zeile("detroit_rate", 132.6, 132.7).ueber()
    assert zeile("detroit_rate", 132.6, 132.5).ueber()
    assert not zeile("detroit_rate", 132.6, 132.64).ueber()


def test_eine_zahl_ueber_einem_prozent_ist_zu_weit():
    assert zeile("gold_rows", 100000, 101001).ueber()
    assert zeile("gold_rows", 100000, 98999).ueber()
    assert not zeile("gold_rows", 100000, 101000).ueber()


def test_nicht_gebaut_ist_keine_drift():
    assert not zeile("gold_rows", 100000, None).ueber()  # type: ignore[arg-type]


def test_die_tabelle_nennt_die_ueberschreitung():
    text = dr.tabelle([zeile("detroit_rate", 132.6, 140.0)])
    assert "**überschritten**" in text and "1 Grösse(n) über der Toleranz" in text
    assert "Alle Grössen innerhalb" in dr.tabelle([zeile("detroit_rate", 132.6, 132.6)])


def test_main_wird_rot_ueber_der_toleranz(tmp_path, monkeypatch, capsys):
    baue_daten(tmp_path)          # 4 Silver-Zeilen ...
    aenderungen = tmp_path / "AENDERUNGEN.md"
    aenderungen.write_text(KOPF, encoding="utf-8")   # ... dokumentiert 347'957
    ausgabe = tmp_path / "drift.json"
    argv = ["drift", "--data-root", str(tmp_path), "--aenderungen", str(aenderungen),
            "--json", str(ausgabe)]
    monkeypatch.setattr(sys, "argv", argv)
    assert dr.main() == 1
    assert "::error::Drift ueber der Toleranz" in capsys.readouterr().out
    ergebnis = json.loads(ausgabe.read_text(encoding="utf-8"))
    assert ergebnis["within_tolerance"] is False
    assert ergebnis["measures"]["silver_rows"]["exceeded"] is True

    monkeypatch.setattr(sys, "argv", argv + ["--nur-melden"])
    assert dr.main() == 0


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
        "exceeded": False,
    }
    assert ergebnis["within_tolerance"] is True, "nicht gebaut ist keine Drift"


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
