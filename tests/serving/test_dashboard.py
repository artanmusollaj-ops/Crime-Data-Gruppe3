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
import math
import re
from datetime import date, datetime, time
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


#: Zwei kleine Chicagoer Tracts, nur wo ein Test sie verlangt: 100 und 0 Einwohner.
TRACT_KLEIN, TRACT_LEER = "17031020100", "17031020200"
TRACT_STADT = {TRACT_C: "chicago", TRACT_D: "detroit",
               TRACT_KLEIN: "chicago", TRACT_LEER: "chicago"}


def quadrat(x: float, y: float) -> str:
    return f"POLYGON (({x} {y}, {x + 0.01} {y}, {x + 0.01} {y + 0.01}, {x} {y + 0.01}, {x} {y}))"


def stern(root: Path, taten: list[tuple], *, kleine: bool = False) -> Path:
    """(meldende Stadt, Datum, NIBRS-Code, Tract[, Uhrzeit[, Fall[, Zuordnung]]]) je Tat."""
    schreibe(root, "fact_offense", {
        "offense_id": [f"o{i}" for i in range(len(taten))],
        "reporting_city": [t[0] for t in taten],
        "date": [t[1] for t in taten],
        "nibrs_code": [t[2] for t in taten],
        "nibrs_family": [t[2][:2] for t in taten],
        # Das sechste Feld: False fuer eine weitere Anklage im selben Fall.
        "counts_case": [t[5] if len(t) > 5 else True for t in taten],
        # Das siebte Feld: der Zuordnungsstatus, sonst exact.
        "mapping_status": [t[6] if len(t) > 6 else "exact" for t in taten],
        # Wie in Gold: inside_city nur, wenn der Tract zur meldenden Stadt gehoert.
        "geo_status": ["inside_city" if TRACT_STADT.get(t[3]) == t[0] else "outside_city"
                       for t in taten],
        "local_time_ambiguous": [False] * len(taten),
        "tract_geoid": [t[3] for t in taten],
        # Die Uhrzeit ist das fuenfte Feld, wenn es eines gibt; sonst 18:05.
        "hour_of_day": [(t[4] if len(t) > 4 else time(18, 5)).hour for t in taten],
        "occurred_at_local": [datetime.combine(t[1], t[4] if len(t) > 4 else time(18, 5))
                              for t in taten],
        "population_vintage": [2024 if t[1].year >= 2024 else 2023 for t in taten],
    })
    schreibe(root, "dim_offense", {
        "nibrs_code": ["13A", "13B", "23C", "120"],
        "nibrs_description": ["Aggravated Assault", "Simple Assault", "Shoplifting", "Robbery"],
        "nibrs_category": ["Assault Offenses", "Assault Offenses", "Larceny/Theft Offenses",
                           "Robbery"],
    })
    klein = [TRACT_KLEIN, TRACT_LEER] if kleine else []
    schreibe(root, "dim_tract", {
        "geoid": [TRACT_C, TRACT_D, TRACT_AUSSEN, *klein],
        "city": ["chicago", "detroit", None, *["chicago"] * len(klein)],
        "reference_vintage": [2024] * (3 + len(klein)),
    })
    schreibe(root, "dim_tract_acs", {
        "geoid": [TRACT_C, TRACT_D, TRACT_AUSSEN, *klein] * 2,
        "vintage": [2023] * (3 + len(klein)) + [2024] * (3 + len(klein)),
        "population": [1900, 900, 50, *[100, 0][:len(klein)],
                       2000, 1000, 50, *[100, 0][:len(klein)]],
    })
    # Die Umrisse fuehren nur Tracts mit Stadt, wie in Gold.
    geo = [(TRACT_C, "chicago", -87.7, 41.8), (TRACT_D, "detroit", -83.1, 42.3)] + [
        (g, "chicago", -87.68 + i * 0.02, 41.8) for i, g in enumerate(klein)]
    schreibe(root, "dim_tract_geo", {
        "geoid": [g[0] for g in geo], "city": [g[1] for g in geo],
        "tract_name": [f"Census Tract {g[0][-6:-2].lstrip('0')}" for g in geo],
        "boundary_wkt": [quadrat(g[2], g[3]) for g in geo],
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


@pytest.mark.parametrize("pfad", ["/", "/zeitverlauf", "/geografie", "/deliktstruktur",
                                  "/datenqualitaet"])
def test_die_seite_kommt_ohne_inline_code_aus(bestand, pfad):
    """Die CSP erlaubt nur 'self'; ein Inline-Skript oder -Stil liefe nicht."""
    client = create_app(bestand=bestand).test_client()
    seite = client.get(pfad)
    assert seite.status_code == 200
    assert "default-src 'self'" in seite.headers["Content-Security-Policy"]
    html = seite.get_data(as_text=True)
    assert not re.search(r"<script(?![^>]*\bsrc=)", html)
    assert "<style" not in html and " style=" not in html
    for datei in re.findall(r'(?:src|href)="/static/([^"]+)"', html):
        assert (_STATISCH / datei).is_file()
        assert client.get("/static/" + datei).status_code == 200
    # Ein Modul laedt seine Nachbarn selbst; auch die muessen da sein.
    for skript in re.findall(r'src="/static/([^"]+\.js)"', html):
        for nachbar in re.findall(r'from "\./([^"]+)"', (_STATISCH / skript).read_text(encoding="utf-8")):
            assert (_STATISCH / nachbar).is_file(), nachbar


def test_alle_seiten_tragen_dieselben_reiter(bestand):
    """Die Leiste steht in jeder Seite einmal; sie darf nicht auseinanderlaufen."""
    client = create_app(bestand=bestand).test_client()

    def reiter(pfad):
        html = client.get(pfad).get_data(as_text=True)
        leiste = re.search(r'<nav class="reiter".*?</nav>', html, re.S).group(0)
        return re.findall(r">([^<>]+)</(?:a|span)>", leiste)

    assert reiter("/") == reiter("/zeitverlauf") == reiter("/geografie") == reiter(
        "/deliktstruktur") == reiter("/datenqualitaet") == [
        "Überblick", "Zeitverlauf", "Geografie", "Deliktstruktur", "Datenqualität"]


# --------------------------------------------------------------------------
# Das Fenster je Stadt
# --------------------------------------------------------------------------


def test_das_fenster_gilt_je_stadt(tmp_path):
    """comparison_month misst am gemeinsamen Fenster; das Dashboard je Stadt.

    Chicago endet am 20.3., Detroit am 2.4. Gemeinsam reicht das Fenster in
    den April, und comparison_month nennt Chicagos Maerz vollstaendig.
    """
    b = Bestand(stern(tmp_path, [
        ("chicago", date(2025, 1, 1), "13A", TRACT_C),
        ("chicago", date(2025, 3, 20), "13A", TRACT_C),
        ("detroit", date(2025, 1, 1), "13A", TRACT_D),
        ("detroit", date(2025, 4, 2), "13A", TRACT_D),
    ]))
    tage, im_fenster = b._cursor().execute(
        "SELECT max(tage), max(tage_im_fenster) FROM monate "
        "WHERE stadt = 'chicago' AND monat = DATE '2025-03-01'").fetchone()
    assert tage == im_fenster == 31
    abdeckung = {a["stadt"]: a for a in b.ueberblick(b.auswahl(
        {"jahr": "2025", "bis": "4"}))["abdeckung"]}
    # Der Februar liegt im Fenster: ein voller Monat ohne Tat, keine Luecke.
    assert abdeckung["chicago"]["monate"] == ["voll", "voll", "teil", "fehlt"]
    assert abdeckung["chicago"]["letzter_tag"] == "2025-03-20"
    assert abdeckung["detroit"]["monate"] == ["voll", "voll", "voll", "teil"]


# --------------------------------------------------------------------------
# Das Brett »Zeitverlauf«
# --------------------------------------------------------------------------


@pytest.fixture
def stunden(tmp_path) -> Bestand:
    """Chicago 2024 und 2025; Mittwoch, 1.1.2025, und Mittwoch, 8.1.2025."""
    taten = (
        jahr("chicago", 2024, "13A", TRACT_C, je=2)
        + [("chicago", date(2025, 1, 1), "13A", TRACT_C, time(18, 5)),
           ("chicago", date(2025, 1, 1), "13A", TRACT_C, time(18, 40)),
           ("chicago", date(2025, 1, 8), "13A", TRACT_C, time(18, 30)),
           # Platzhalter: genau Mitternacht und genau Mittag.
           ("chicago", date(2025, 1, 8), "23C", TRACT_C, time(0, 0)),
           ("chicago", date(2025, 1, 8), "23C", TRACT_C, time(12, 0)),
           # Eine Minute daneben ist keiner.
           ("chicago", date(2025, 1, 8), "23C", TRACT_C, time(0, 1)),
           # Eine zweite Anklage: eine Tat mehr, kein Fall mehr.
           ("chicago", date(2025, 1, 8), "13A", TRACT_C, time(18, 30), False)]
        + jahr("chicago", 2025, "13A", TRACT_C, monate=range(2, 4), je=4)
        + [("chicago", date(2025, 3, 31), "13A", TRACT_C)]
        + jahr("detroit", 2025, "13A", TRACT_D, monate=range(1, 4))
        + [("detroit", date(2025, 3, 31), "13A", TRACT_D)]
    )
    return Bestand(stern(tmp_path, taten))


def test_die_heatmap_teilt_durch_die_tage_und_laesst_platzhalter_weg(stunden):
    z = stunden.zeitverlauf(stunden.auswahl({"stadt": "chicago", "jahr": "2025", "bis": "1"}))
    h = z["staedte"][0]["heatmap"]
    mittwoch = h["werte"][2]
    # Zwei Mittwoche mit Daten: (2 + 1) Faelle um 18 Uhr / 2 Tage.
    assert mittwoch[18] == 1.5
    assert mittwoch[0] == 0.5          # 00:01 zaehlt
    assert mittwoch[12] == 0.0         # 12:00 nicht
    assert h["platzhalter"] == 2
    assert h["platzhalter_anteil"] == round(2 * 100 / 6, 1)
    assert sum(map(sum, h["werte"][:2] + h["werte"][3:])) == 0


def test_die_heatmap_folgt_der_kategorie(stunden):
    z = stunden.zeitverlauf(stunden.auswahl(
        {"stadt": "chicago", "jahr": "2025", "bis": "1", "kategorie": "Larceny/Theft Offenses"}))
    h = z["staedte"][0]["heatmap"]
    assert h["werte"][2][18] == 0.0 and h["werte"][2][0] == 0.5 and h["platzhalter"] == 2


def test_der_verlauf_zeigt_faelle_gegen_das_vorjahr(stunden):
    s = stunden.zeitverlauf(stunden.auswahl({"stadt": "chicago", "jahr": "2025", "bis": "3"}))
    chicago = s["staedte"][0]
    # Faelle, nicht Taten: Die zweite Anklage am 8.1. zaehlt nicht mit.
    assert chicago["jetzt"] == [6, 4, 5]
    assert chicago["vorjahr"] == [2, 2, 2]
    assert s["vergleich"] == {"jahr": 2025, "vorjahr": 2024, "vorjahr_vorhanden": True}


def test_der_index_beginnt_beim_ersten_vollen_monat(tmp_path):
    """Ein angebrochener Januar als 100 machte jeden Folgemonat zum Anstieg."""
    b = Bestand(stern(tmp_path, [
        ("chicago", date(2025, 1, 20), "13A", TRACT_C),
        *[("chicago", date(2025, m, d), "13A", TRACT_C)
          for m in (2, 3) for d in (1, 28)],
        ("chicago", date(2025, 3, 31), "13A", TRACT_C),
        ("detroit", date(2025, 1, 20), "13A", TRACT_D),
    ]))
    chicago = b.zeitverlauf(b.auswahl({"stadt": "chicago", "jahr": "2025", "bis": "3"}))["staedte"][0]
    assert chicago["status"] == ["teil", "voll", "voll"]
    assert chicago["index"]["basis"] == "2025-02-01"
    assert chicago["index"]["werte"] == [50.0, 100.0, 150.0]


def test_die_api_liefert_den_zeitverlauf(stunden):
    client = create_app(bestand=stunden).test_client()
    antwort = client.get("/api/zeitverlauf?jahr=2025&stadt=beide&bis=3")
    assert antwort.status_code == 200
    assert [s["zeitzone"] for s in antwort.json["staedte"]] == ["America/Chicago", "America/Detroit"]
    assert client.get("/api/zeitverlauf?jahr=1999").status_code == 400


# --------------------------------------------------------------------------
# Das Brett »Geografie«
# --------------------------------------------------------------------------


@pytest.fixture
def karte(tmp_path) -> Bestand:
    taten = (
        jahr("chicago", 2024, "13A", TRACT_C, je=3)
        + jahr("chicago", 2024, "23C", TRACT_C)
        # Eine zweite Anklage: zaehlt als Tat, nicht als Fall.
        + [("chicago", date(2024, 2, 1), "13A", TRACT_C, time(18, 5), False)]
        + jahr("chicago", 2024, "13A", TRACT_KLEIN, monate=[3])
        # Ausserhalb der Stadt: gemeldet, aber nicht auf der Karte.
        + jahr("chicago", 2024, "120", TRACT_AUSSEN, monate=[5, 6])
        + jahr("detroit", 2024, "13A", TRACT_D, je=2)
        # Von Detroit gemeldet, aber in einem Chicagoer Tract: auf keiner Karte.
        + [("detroit", date(2024, 7, 1), "13A", TRACT_C)]
    )
    return Bestand(stern(tmp_path, taten, kleine=True))


def test_die_tract_rate_ist_die_von_gold(karte):
    """Dieselbe Zahl wie gold_pipeline.raten_je_tract - Fallebene, inside_city."""
    from gold_pipeline import raten_je_tract
    gold = karte.data_root / "gold"

    def rel(t):
        return f"read_parquet('{gold}/dataset={t}/part-0001.parquet')"

    erwartet = {(s, g): r for s, g, _, r, *_ in duckdb.connect().execute(
        raten_je_tract(rel("fact_offense"), rel("dim_tract_acs"), 2024)).fetchall()}
    g = karte.geografie(karte.auswahl({"jahr": "2024"}))
    gezeigt = {(s["stadt"], t["geoid"]): t["rate"] for s in g["staedte"] for t in s["tracts"]
               if t["faelle"]}
    assert gezeigt == erwartet
    assert erwartet[("chicago", TRACT_C)] == 24.0     # 48 Faelle, nicht 49 Taten


def test_kleine_basis_ist_markiert_und_nicht_in_der_rangliste(karte):
    chicago = karte.geografie(karte.auswahl({"jahr": "2024", "stadt": "chicago"}))["staedte"][0]
    nach = {t["geoid"]: t for t in chicago["tracts"]}
    assert nach[TRACT_KLEIN]["geringe_basis"] and nach[TRACT_KLEIN]["rate"] == 10.0
    # Ohne Einwohner keine Rate - auch keine Null.
    assert nach[TRACT_LEER]["rate"] is None and nach[TRACT_LEER]["faelle"] == 0
    assert [t["geoid"] for t in chicago["hoechste"]] == [TRACT_C]
    assert chicago["geringe"] == 2


def test_ein_tract_ohne_fall_ist_eine_null(karte):
    g = karte.geografie(karte.auswahl({"jahr": "2024", "stadt": "chicago", "bis": "1"}))
    klein = next(t for t in g["staedte"][0]["tracts"] if t["geoid"] == TRACT_KLEIN)
    assert klein["faelle"] == 0 and klein["rate"] == 0.0


def test_was_keinen_ort_hat_wird_gezaehlt(karte):
    g = karte.geografie(karte.auswahl({"jahr": "2024"}))["staedte"]
    assert g[0]["verortung"]["outside_city"] == 2
    assert g[0]["verortung"]["inside_city"] == 12 * 4 + 1
    assert g[1]["verortung"]["outside_city"] == 1


def test_die_kategorie_filtert_die_karte(karte):
    g = karte.geografie(karte.auswahl(
        {"jahr": "2024", "stadt": "chicago", "kategorie": "Larceny/Theft Offenses"}))
    c = next(t for t in g["staedte"][0]["tracts"] if t["geoid"] == TRACT_C)
    assert c["faelle"] == 12 and c["rate"] == 6.0


def test_die_klassen_sind_gerundete_quantile_ohne_doppel():
    from serving.dashboard.geografie import klassengrenzen
    assert klassengrenzen([]) == []
    assert klassengrenzen([float(v) for v in range(1, 101)]) == [21.0, 41.0, 61.0, 81.0]
    # Viele gleiche Werte ergeben weniger Klassen, keine leeren.
    assert klassengrenzen([5.0] * 9 + [80.0]) == [5.0]
    assert klassengrenzen([0.123, 0.347, 1.26, 13.47, 13.47]) == [0.35, 1.3, 13.0]


def test_die_umrisse_werden_zu_pfaden(karte):
    k = karte.karten
    assert set(k) == {"chicago", "detroit"}
    assert len(k["chicago"]["tracts"]) == 3
    d = k["detroit"]["tracts"][0]["d"]
    assert d.startswith("M0.0 ") and d.endswith("Z") and d.count("L") == 4
    # Ein Quadrat in Grad ist in der Projektion hoeher als breit: cos(42,3 Grad).
    assert k["detroit"]["hoehe"] == pytest.approx(600 / math.cos(math.radians(42.305)), rel=1e-3)


def test_die_api_liefert_karten_und_raten(karte):
    client = create_app(bestand=karte).test_client()
    assert set(client.get("/api/karten").json) == {"chicago", "detroit"}
    g = client.get("/api/geografie?jahr=2024&stadt=detroit")
    assert g.status_code == 200 and g.json["staedte"][0]["tracts"][0]["rate"] == 24.0


# --------------------------------------------------------------------------
# Das Brett »Deliktstruktur«
# --------------------------------------------------------------------------


@pytest.fixture
def struktur(tmp_path) -> Bestand:
    zweite = ("chicago", date(2025, 2, 1), "13A", TRACT_C, time(18, 5), False)
    taten = (
        # Simple Assault (13B) ist haeufiger, aber alphabetisch nach Aggravated.
        jahr("chicago", 2024, "13B", TRACT_C, je=30)
        + jahr("chicago", 2024, "23C", TRACT_C, je=10)
        + jahr("chicago", 2025, "13B", TRACT_C, monate=range(1, 4), je=33)
        + jahr("chicago", 2025, "23C", TRACT_C, monate=range(1, 4), je=5)
        + jahr("chicago", 2025, "13A", TRACT_C, monate=range(1, 4), je=2)
        + [zweite] * 4
        + [("chicago", date(2025, 3, 31), "120", TRACT_C)]
        + jahr("detroit", 2024, "13A", TRACT_D, je=1)
        + jahr("detroit", 2025, "13A", TRACT_D, monate=range(1, 4), je=2)
        + [("detroit", date(2025, 3, 31), "13A", TRACT_D)]
    )
    return Bestand(stern(tmp_path, taten))


def test_die_struktur_zaehlt_vorgabemaessig_faelle(struktur):
    a = struktur.auswahl({"jahr": "2025", "bis": "3"})
    assert a.ebene == "faelle"
    faelle = struktur.deliktstruktur(a)
    delikte = struktur.deliktstruktur(struktur.auswahl({"jahr": "2025", "bis": "3", "ebene": "delikte"}))

    def koerper(d):
        return next(z for z in d["tabelle"] if z["kategorie"] == "Assault Offenses")["werte"]["chicago"]

    # Vier zweite Anklagen: Delikte, aber keine Faelle.
    assert koerper(delikte) - koerper(faelle) == 4
    assert faelle["ebene"] == "faelle" and delikte["ebene"] == "delikte"


def test_die_anteile_summieren_sich_auf_hundert(struktur, monkeypatch):
    import serving.dashboard.deliktstruktur as d
    monkeypatch.setattr(d, "IM_DIAGRAMM", 1)
    r = struktur.deliktstruktur(struktur.auswahl({"jahr": "2025", "bis": "3"}))
    chicago = next(x for x in r["anteile"] if x["stadt"] == "chicago")
    assert [t["name"] for t in chicago["teile"]] == ["Körperverletzung", UEBRIGE]
    assert sum(t["anteil"] for t in chicago["teile"]) == pytest.approx(100, abs=0.1)


def test_zum_vorjahr_je_stadt_und_erst_ab_der_mindestzahl(struktur):
    r = struktur.deliktstruktur(struktur.auswahl({"jahr": "2025", "bis": "3"}))
    zeilen = {z["kategorie"]: z for z in r["tabelle"]}
    # Chicago, Jan-Maerz vergleichbar (die Daten reichen bis zum 31.3.):
    # Koerperverletzung 2025 je Monat 33 + 2 (13A), 2024 je Monat 30.
    assert zeilen["Assault Offenses"]["vorjahr"]["chicago"] == round((35 - 30) * 100 / 30, 1)
    # Diebstahl 2024: 10 je Monat, drei Monate = 30 >= 20; 2025: 5 je Monat.
    assert zeilen["Larceny/Theft Offenses"]["vorjahr"]["chicago"] == -50.0
    # Detroit hatte 2024 nur 3 Faelle in diesen Monaten: kein Befund.
    assert zeilen["Assault Offenses"]["vorjahr"]["detroit"] is None
    # Raub hat kein Vorjahr.
    assert zeilen["Robbery"]["vorjahr"]["chicago"] is None


def test_zum_vorjahr_nur_ueber_vergleichbare_monate_der_stadt(tmp_path):
    """Detroit endet am 10.3.: Fuer Detroit zaehlen nur Jan und Feb."""
    b = Bestand(stern(tmp_path, (
        jahr("chicago", 2024, "13A", TRACT_C, je=25)
        + jahr("chicago", 2025, "13A", TRACT_C, monate=range(1, 4), je=25)
        + [("chicago", date(2025, 3, 31), "13A", TRACT_C)]
        + jahr("detroit", 2024, "13A", TRACT_D, je=20)
        + jahr("detroit", 2025, "13A", TRACT_D, monate=range(1, 3), je=20)
        + [("detroit", date(2025, 3, 10), "13A", TRACT_D)] * 2
    )))
    r = b.deliktstruktur(b.auswahl({"jahr": "2025", "bis": "3"}))
    assert {s["stadt"]: s["vergleichbare_monate"] for s in r["staedte"]} == {"chicago": 3, "detroit": 2}
    koerper = r["tabelle"][0]["vorjahr"]
    # Chicago: 75 + 1 gegen 75; Detroit ohne den angebrochenen Maerz: 40 gegen 40.
    assert koerper == {"chicago": round(1 * 100 / 75, 1), "detroit": 0.0}


def test_die_beispiele_sind_die_haeufigsten_delikte(struktur):
    assert struktur.beispiele["Assault Offenses"] == ["Simple Assault", "Aggravated Assault"]


def test_eine_unbekannte_ebene_ist_ein_eingabefehler(struktur):
    client = create_app(bestand=struktur).test_client()
    assert client.get("/api/deliktstruktur?ebene=taten").status_code == 400
    ok = client.get("/api/deliktstruktur?jahr=2025&bis=3&ebene=delikte")
    assert ok.status_code == 200 and ok.json["ebene"] == "delikte"


# --------------------------------------------------------------------------
# Das Brett »Datenqualität«
# --------------------------------------------------------------------------


@pytest.fixture
def qualitaet(tmp_path) -> Bestand:
    um_18 = time(18, 5)
    taten = (
        jahr("chicago", 2025, "13A", TRACT_C, monate=range(1, 4), je=30)
        + [("chicago", date(2025, 1, 5), "13A", TRACT_C, um_18, True, "fallback_90Z")] * 6
        + [("chicago", date(2025, 1, 5), "13A", TRACT_C, um_18, True, "unmapped")] * 2
        # Zweite Anklagen zaehlen mit: Das Gate misst Taten, nicht Faelle.
        + [("chicago", date(2025, 2, 5), "13A", TRACT_C, um_18, False, "ambiguous")] * 2
        + [("chicago", date(2025, 3, 31), "13A", TRACT_AUSSEN)] * 4
        + jahr("detroit", 2025, "13A", TRACT_D, monate=range(1, 5), je=10)
        + [("detroit", date(2025, 4, 30), "13A", TRACT_D)]
    )
    return Bestand(stern(tmp_path, taten))


def test_die_anteile_messen_taten_wie_das_gate(qualitaet):
    q = qualitaet.datenqualitaet(qualitaet.auswahl({"jahr": "2025", "stadt": "chicago", "bis": "3"}))
    chicago = q["staedte"][0]
    alle = 90 + 6 + 2 + 2 + 4
    assert chicago["delikte"] == alle
    assert chicago["zuordnung"] == {
        "exact": round(94 * 100 / alle, 2), "fallback_90Z": round(6 * 100 / alle, 2),
        "ambiguous": round(2 * 100 / alle, 2), "unmapped": round(2 * 100 / alle, 2)}
    assert chicago["verortung"]["outside_city"] == round(4 * 100 / alle, 2)
    assert q["kennzahlen"]["ohne_zuordnung"] == round(2 * 100 / alle, 2)


def test_die_schwellen_sind_die_des_gates(qualitaet, monkeypatch):
    import serving.dashboard.datenqualitaet as dq
    a = qualitaet.auswahl({"jahr": "2025", "stadt": "chicago", "bis": "3"})
    status = {p["aspekt"]: p["status"] for p in qualitaet.datenqualitaet(a)["pruefungen"]}
    # 1,92 % ohne Zuordnung reisst die 1 % des Gates.
    assert status["Ohne NIBRS-Zuordnung"] == "warnung"
    assert status["NIBRS-Zuordnung exakt"] == status["Verortung im Stadtgebiet"] == "ok"
    monkeypatch.setitem(dq.GATE_HOECHSTENS, "unmapped", 5.0)
    monkeypatch.setitem(dq.GATE_MINDESTENS, "inside_city", 99.0)
    status = {p["aspekt"]: (p["status"], p["schwelle"]) for p in qualitaet.datenqualitaet(a)["pruefungen"]}
    assert status["Ohne NIBRS-Zuordnung"] == ("ok", "höchstens 5 %")
    assert status["Verortung im Stadtgebiet"] == ("warnung", "mindestens 99 %")


def test_doppelte_delikt_ids_fallen_auf(qualitaet):
    a = qualitaet.auswahl({"jahr": "2025", "bis": "3"})
    assert qualitaet.datenqualitaet(a)["kennzahlen"]["doppelte_ids"] == 0
    ziel = qualitaet.data_root / "gold" / "dataset=fact_offense" / "part-0001.parquet"
    tabelle = pq.read_table(ziel)
    pq.write_table(pa.concat_tables([tabelle, tabelle.slice(0, 3)]), ziel)
    neu = Bestand(qualitaet.data_root)
    q = neu.datenqualitaet(a)
    assert q["kennzahlen"]["doppelte_ids"] == 3
    assert {p["aspekt"]: p["status"] for p in q["pruefungen"]}["Eindeutige Delikt-ID"] == "warnung"


def test_spaetere_monate_sind_nicht_erschienen_luecken_fehlen(qualitaet):
    """Chicago endet am 31.3., Detroit am 30.4.: Chicagos April fehlt, der Mai ist spaeter."""
    q = qualitaet.datenqualitaet(qualitaet.auswahl({"jahr": "2025", "bis": "6"}))
    monate = {s["stadt"]: s["monate"] for s in q["staedte"]}
    assert monate["chicago"] == ["voll", "voll", "voll", "fehlt", "spaeter", "spaeter"]
    assert monate["detroit"] == ["voll", "voll", "voll", "voll", "spaeter", "spaeter"]


def test_die_referenzdaten_nennen_vintage_und_umrisse(qualitaet):
    r = qualitaet.datenqualitaet(qualitaet.auswahl({"jahr": "2025", "bis": "3"}))["referenz"]
    assert r["acs_vintage"] == 2024 and r["tracts"] == {"chicago": 1, "detroit": 1}
    assert r["release"] is None


@pytest.mark.parametrize("brett", ["ueberblick", "zeitverlauf", "geografie", "deliktstruktur",
                                   "datenqualitaet"])
def test_jedes_brett_nimmt_jede_kategorie(qualitaet, brett):
    """Ein Parameter, den eine Abfrage nicht kennt, ist in DuckDB ein Fehler.

    Unter Last fiel er auf: Die Abfrage nach doppelten IDs bekam die Kategorie
    mit, filtert aber nicht nach ihr - 500 bei jeder Auswahl ausser »Alle«.
    """
    client = create_app(bestand=qualitaet).test_client()
    for werte in ("kategorie=Assault%20Offenses", "kategorie=Assault%20Offenses&stadt=detroit"):
        antwort = client.get(f"/api/{brett}?jahr=2025&bis=3&{werte}")
        assert antwort.status_code == 200, antwort.get_data(as_text=True)[:200]


def test_der_weg_zur_konsole_kommt_aus_der_umgebung(qualitaet, monkeypatch):
    client = create_app(bestand=qualitaet).test_client()
    assert client.get("/api/datenqualitaet?jahr=2025&bis=3").json["konsole"] is None
    monkeypatch.setenv("DASHBOARD_KONSOLE_URL", "https://konsole.example")
    assert client.get("/api/datenqualitaet?jahr=2025&bis=3").json["konsole"] == "https://konsole.example"


def test_gleichzeitige_erste_anfragen_laden_den_bestand_einmal(tmp_path, monkeypatch):
    """gunicorn laeuft mit vier Threads; die ersten Anfragen kommen zusammen."""
    import threading as th
    import time as zeit

    import serving.dashboard.app as app_modul

    stern(tmp_path, jahr("chicago", 2024, "13A", TRACT_C) + jahr("detroit", 2024, "13A", TRACT_D))
    geladen = []
    echt = app_modul.Bestand

    def langsam(wurzel):
        geladen.append(wurzel)
        zeit.sleep(0.2)
        return echt(wurzel)

    monkeypatch.setattr(app_modul, "Bestand", langsam)
    client = create_app(tmp_path).test_client()
    antworten = []
    faeden = [th.Thread(target=lambda: antworten.append(client.get("/api/optionen").status_code))
              for _ in range(4)]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    assert antworten == [200] * 4
    assert len(geladen) == 1
