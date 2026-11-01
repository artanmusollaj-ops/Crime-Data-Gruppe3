"""Das eigene Dashboard - Brett »Überblick«.

Die Faelle, in denen ein Dashboard eine falsche Zahl zeigt, ohne zu werfen:
eine Rate mit anderem Nenner als die Dokumente, ein fehlender Monat als
Null, ein Teiljahr gegen ein ganzes Vorjahr. Jeder hat hier einen Test.
Gebaut wird ein kleiner Stern, daraus mit ``build_comparison`` die
Vergleichstabelle - dieselbe Kette wie im Datenlauf.
"""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_comparison as bc
from gold_pipeline import raten_je_stadt
from serving.dashboard import KATEGORIE_DE, UEBRIGE, Bestand, EingabeFehler
from serving.dashboard.app import _STATISCH, create_app

PROJEKT = Path(__file__).resolve().parents[2]
TRACT_C, TRACT_D, TRACT_AUSSEN = "17031010100", "26163500100", "17031999900"


def schreibe(root: Path, tabelle: str, spalten: dict[str, list]) -> None:
    ziel = root / "gold" / f"dataset={tabelle}"
    ziel.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table(spalten), ziel / "part-0001.parquet")
    (ziel / "manifest.json").write_text(json.dumps({
        "status": "complete", "built_at_utc": "2026-10-31T10:00:00+00:00",
        "input_fingerprint": f"fp-{tabelle}", "derived_from": {}}), encoding="utf-8")


def stern(root: Path, taten: list[tuple[str, date, str, str]]) -> Path:
    """(meldende Stadt, Datum, NIBRS-Code, Tract) je Tat; jede Tat ein Fall."""
    schreibe(root, "fact_offense", {
        "offense_id": [f"o{i}" for i in range(len(taten))],
        "reporting_city": [t[0] for t in taten],
        "date": [t[1] for t in taten],
        "nibrs_code": [t[2] for t in taten],
        "nibrs_family": [t[2][:2] for t in taten],
        "counts_case": [True] * len(taten),
        "mapping_status": ["exact"] * len(taten),
        "geo_status": ["outside_city" if t[3] == TRACT_AUSSEN else "inside_city" for t in taten],
        "local_time_ambiguous": [False] * len(taten),
        "tract_geoid": [t[3] for t in taten],
        "population_vintage": [2024 if t[1].year >= 2024 else 2023 for t in taten],
    })
    schreibe(root, "dim_offense", {
        "nibrs_code": ["13A", "23C", "120"],
        "nibrs_category": ["Assault Offenses", "Larceny/Theft Offenses", "Robbery"],
    })
    schreibe(root, "dim_tract", {
        "geoid": [TRACT_C, TRACT_D, TRACT_AUSSEN],
        "city": ["chicago", "detroit", None],
        "reference_vintage": [2024, 2024, 2024],
    })
    schreibe(root, "dim_tract_acs", {
        "geoid": [TRACT_C, TRACT_D, TRACT_AUSSEN] * 2,
        "vintage": [2023] * 3 + [2024] * 3,
        "population": [1900, 900, 50, 2000, 1000, 50],
    })
    bc.build(root)
    return root


def jahr(stadt: str, j: int, code: str, tract: str, monate=range(1, 13), je=1) -> list:
    return [(stadt, date(j, m, 1), code, tract) for m in monate for _ in range(je)]


@pytest.fixture
def bestand(tmp_path) -> Bestand:
    taten = (
        jahr("chicago", 2023, "13A", TRACT_C, je=2)
        + jahr("chicago", 2024, "13A", TRACT_C, je=3)
        + jahr("chicago", 2024, "23C", TRACT_C)
        # Gemeldet von Chicago, aber ausserhalb: zaehlt, geht nicht in die Rate.
        + jahr("chicago", 2024, "120", TRACT_AUSSEN, monate=[5])
        + jahr("detroit", 2023, "13A", TRACT_D)
        + jahr("detroit", 2024, "13A", TRACT_D, je=2)
        # 2025: Detroit nur bis Maerz, und der Maerz nur bis zum 10.
        + jahr("chicago", 2025, "13A", TRACT_C, monate=range(1, 4))
        + jahr("detroit", 2025, "13A", TRACT_D, monate=range(1, 3))
        + [("detroit", date(2025, 3, 10), "13A", TRACT_D)]
    )
    return Bestand(stern(tmp_path, taten))


def test_die_rate_ist_die_der_dokumente(bestand):
    """Dieselbe Zahl wie gold_pipeline.raten_je_stadt - Nenner, Tract-Regel, Jahr."""
    rate = bestand.ueberblick(bestand.auswahl({"jahr": "2024"}))["raten"]["zeilen"][0]
    gold = bestand.data_root / "gold"

    def rel(t):
        return f"read_parquet('{gold}/dataset={t}/part-0001.parquet')"

    erwartet = {s: r for s, r in duckdb.connect().execute(
        "SELECT city, rate FROM (" + raten_je_stadt(rel("fact_offense"), rel("dim_tract"),
                                                   rel("dim_tract_acs"), 2024) + ")").fetchall()}
    assert rate["kategorie"] == "alle"
    assert rate["werte"] == erwartet == {"chicago": 24.0, "detroit": 24.0}


def test_gezaehlt_wird_nach_meldender_stadt(bestand):
    """Die Tat ausserhalb zaehlt bei Chicago mit, wie in comparison_month."""
    k = bestand.ueberblick(bestand.auswahl({"jahr": "2024", "stadt": "chicago"}))["kennzahlen"]
    assert k["delikte"] == 12 * 3 + 12 + 1
    assert k["faelle"] == k["delikte"]


def test_ein_jahr_mit_altem_vintage_nimmt_dessen_nenner(bestand):
    rate = bestand.ueberblick(bestand.auswahl({"jahr": "2023"}))["raten"]
    assert rate["einwohner"] == {"chicago": 1900, "detroit": 900}
    assert rate["zeilen"][0]["werte"] == {"chicago": round(24 * 1000 / 1900, 1),
                                          "detroit": round(12 * 1000 / 900, 1)}


def test_ein_fehlender_monat_ist_eine_luecke_keine_null(bestand):
    v = bestand.ueberblick(bestand.auswahl({"jahr": "2025", "bis": "6"}))["verlauf"]
    detroit = next(r for r in v["reihen"] if r["stadt"] == "detroit")
    assert detroit["werte"] == [1, 1, 1, None, None, None]
    assert detroit["status"][:3] == ["voll", "voll", "teil"]


def test_der_teilmonat_ist_nicht_vollstaendig(bestand):
    r = bestand.ueberblick(bestand.auswahl({"jahr": "2025", "bis": "3"}))
    assert r["kennzahlen"]["vollstaendige_monate"] == 2
    detroit = next(a for a in r["abdeckung"] if a["stadt"] == "detroit")
    assert detroit["status"] == "unvollstaendig"
    assert detroit["letzter_monat"] == "2025-03-01"


def test_zum_vorjahr_nur_ueber_vergleichbare_monate(bestand):
    """Jan-Dez 2025 hat zwei ganze Monate; nur sie stehen gegen 2024."""
    k = bestand.ueberblick(bestand.auswahl({"jahr": "2025"}))["kennzahlen"]
    assert k["vorjahr_monate"] == 2
    # 2025: je Monat 1 + 1; 2024: je Monat 3 + 1 + 2.
    assert k["vorjahr_prozent"] == round((4 - 12) * 100 / 12, 1)


def test_ohne_vorjahr_kein_vergleich(bestand):
    k = bestand.ueberblick(bestand.auswahl({"jahr": "2023"}))["kennzahlen"]
    assert k["vorjahr_prozent"] is None and k["vorjahr_monate"] == 0


def test_der_anteil_summiert_sich_je_stadt_auf_hundert(bestand):
    zeilen = bestand.ueberblick(bestand.auswahl(
        {"jahr": "2024", "mass": "anteil"}))["kategorien"]["zeilen"]
    for stadt in ("chicago", "detroit"):
        assert sum(z["werte"][stadt] for z in zeilen) == pytest.approx(100, abs=0.2)


def test_die_kategorie_filtert_alles(bestand):
    r = bestand.ueberblick(bestand.auswahl({"jahr": "2024", "kategorie": "Robbery"}))
    assert r["kennzahlen"]["delikte"] == 1
    assert [z["name"] for z in r["kategorien"]["zeilen"]] == ["Raub"]
    # Der Raub lag ausserhalb jedes Stadt-Tracts: gezaehlt, aber ohne Rate.
    assert r["raten"]["zeilen"][1]["werte"] == {"chicago": 0.0, "detroit": 0.0}


def test_der_rest_heisst_nicht_wie_nibrs_90z(monkeypatch, bestand):
    import serving.dashboard as d
    monkeypatch.setattr(d, "KATEGORIEN_IM_BALKEN", 1)
    namen = [z["name"] for z in bestand.ueberblick(
        bestand.auswahl({"jahr": "2024"}))["kategorien"]["zeilen"]]
    assert namen == ["Körperverletzung", UEBRIGE]
    assert UEBRIGE not in KATEGORIE_DE.values()


@pytest.mark.parametrize("werte", [
    {"stadt": "berlin"}, {"jahr": "1999"}, {"von": "5", "bis": "2"},
    {"kategorie": "Erfunden"}, {"mass": "prozent"}, {"jahr": "zwanzig"},
])
def test_eine_unbekannte_auswahl_ist_ein_eingabefehler(bestand, werte):
    with pytest.raises(EingabeFehler):
        bestand.auswahl(werte)


def test_jede_nibrs_kategorie_hat_einen_deutschen_namen():
    with (PROJEKT / "config" / "nibrs_offense_categories_2025.csv").open(encoding="utf-8") as f:
        kategorien = {r["nibrs_category"] for r in csv.DictReader(f)}
    assert kategorien - set(KATEGORIE_DE) == set()


def test_ein_neuer_stand_wird_nachgeladen(bestand, monkeypatch):
    import serving.dashboard as d
    monkeypatch.setattr(d, "PRUEFABSTAND_S", 0.0)
    ziel = bestand.data_root / "serving" / "dataset=comparison_month" / "manifest.json"
    m = json.loads(ziel.read_text(encoding="utf-8"))
    m["built_at_utc"] = "2026-11-01T00:00:00+00:00"
    ziel.write_text(json.dumps(m), encoding="utf-8")
    bestand.aktuell()
    assert bestand.stand["gebaut"] == "2026-11-01T00:00:00+00:00"


# --------------------------------------------------------------------------
# Der Webteil
# --------------------------------------------------------------------------


def test_die_api_antwortet_und_lehnt_ab(bestand):
    client = create_app(bestand=bestand).test_client()
    assert client.get("/api/optionen").json["jahre"] == [2023, 2024, 2025]
    ok = client.get("/api/ueberblick?jahr=2024&stadt=detroit")
    assert ok.status_code == 200 and ok.json["kennzahlen"]["delikte"] == 24
    assert ok.headers["Cache-Control"] == "no-store"
    falsch = client.get("/api/ueberblick?stadt=berlin")
    assert falsch.status_code == 400 and "berlin" in falsch.json["fehler"]


def test_ohne_daten_meldet_die_api_503_und_healthz_bleibt_gruen(tmp_path):
    client = create_app(tmp_path).test_client()
    assert client.get("/healthz").status_code == 200
    antwort = client.get("/api/optionen")
    assert antwort.status_code == 503 and "nicht gebaut" in antwort.json["fehler"]


def test_die_seite_kommt_ohne_inline_code_aus(bestand):
    """Die CSP erlaubt nur 'self'; ein Inline-Skript oder -Stil liefe nicht."""
    client = create_app(bestand=bestand).test_client()
    seite = client.get("/")
    assert "default-src 'self'" in seite.headers["Content-Security-Policy"]
    html = seite.get_data(as_text=True)
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html and " style=" not in html
    for datei in re.findall(r'(?:src|href)="/static/([^"]+)"', html):
        assert (_STATISCH / datei).is_file()
        assert client.get("/static/" + datei).status_code == 200
