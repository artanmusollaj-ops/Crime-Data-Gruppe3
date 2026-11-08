"""Das Brett »Soziales Umfeld« - Fallrate und Armut je Tract.

Die Faelle, in denen es eine falsche Aussage macht, ohne zu werfen: eine Rate,
die nicht die der »Geografie« ist, Fuenftel je Stadt statt gemeinsamer Baender,
und ein Tract ohne Armutswert, der als arm oder reich gezaehlt wird.
"""

from __future__ import annotations

import pytest

from serving.dashboard import Bestand, EingabeFehler
from serving.dashboard.app import create_app
from serving.dashboard.sozial import ARMUT, _band, spearman

from test_dashboard import TRACT_C, TRACT_D, TRACT_KLEIN, jahr, schreibe, stern


@pytest.fixture
def brett(tmp_path) -> Bestand:
    """Zwei bewohnte Chicagoer Tracts (5 % und 35 % Armut), ein Detroiter (35 %)."""
    taten = (jahr("chicago", 2024, "13A", TRACT_C, je=2)
             + jahr("chicago", 2024, "13A", TRACT_KLEIN)
             + jahr("detroit", 2024, "13A", TRACT_D))
    root = tmp_path
    stern(root, taten, kleine=True)
    # Die Armut nachtraeglich an dim_tract_acs: stern() schreibt sie nicht.
    import pyarrow.parquet as pq
    acs = pq.read_table(root / "gold" / "dataset=dim_tract_acs" / "part-0001.parquet").to_pydict()
    armut = {TRACT_C: 0.05, TRACT_D: 0.35, TRACT_KLEIN: 0.35}
    acs["poverty_rate"] = [armut.get(g) for g in acs["geoid"]]
    acs["median_household_income_usd"] = [80000 if g == TRACT_C else None for g in acs["geoid"]]
    schreibe(root, "dim_tract_acs", acs)
    import shutil
    shutil.copytree(root / "gold" / "dataset=dim_tract_acs",
                    next((root / "releases").glob("release=*")) / "gold" / "dataset=dim_tract_acs",
                    dirs_exist_ok=True)
    return Bestand(root)


def sozial(b: Bestand, **werte) -> dict:
    return b.sozialbrett({"jahr": "2024"} | werte)


def stadt(d: dict, name: str) -> dict:
    return next(s for s in d["staedte"] if s["stadt"] == name)


def test_die_rate_ist_die_der_geografie(brett):
    """Dieselbe Funktion, dieselbe Zahl - eine zweite Rechnung waere eine zweite Wahrheit."""
    geo = brett.geografie(brett.auswahl({"jahr": "2024"}))
    d = sozial(brett)
    for s in geo["staedte"]:
        assert {t["geoid"]: t["rate"] for t in s["tracts"]} == {
            t["geoid"]: t["rate"] for t in stadt(d, s["stadt"])["tracts"]}


def test_die_baender_sind_fuer_beide_staedte_dieselben(brett):
    d = sozial(brett)
    assert [b["band"] for b in d["armut"]] == [n for n, *_ in ARMUT]
    chicago = {b["band"]: b for b in stadt(d, "chicago")["baender"]}
    detroit = {b["band"]: b for b in stadt(d, "detroit")["baender"]}
    assert chicago["unter 10 %"]["tracts"] == 1 and detroit["30 bis 40 %"]["tracts"] == 1
    # 24 Faelle auf 2'000 Einwohner (Vintage 2024) im reichen Chicagoer Tract.
    assert chicago["unter 10 %"]["rate"] == 12.0


def test_ein_tract_ohne_armutswert_steht_in_keinem_band(brett):
    d = sozial(brett)
    chicago = stadt(d, "chicago")
    assert sum(b["tracts"] for b in chicago["baender"]) == 2, "der leere Tract zaehlt nicht"
    assert chicago["ohne_einkommen"] == 1


def test_die_armut_steht_in_prozent_am_tract(brett):
    t = next(t for t in stadt(sozial(brett), "detroit")["tracts"] if t["geoid"] == TRACT_D)
    assert (t["armut"], t["band"]) == (35.0, "30 bis 40 %")


def test_die_kartenart_ist_eine_wahl(brett):
    assert sozial(brett, karte="bivariat")["auswahl"]["karte"] == "bivariat"
    with pytest.raises(EingabeFehler):
        sozial(brett, karte="dreidimensional")
    client = create_app(bestand=brett).test_client()
    assert client.get("/api/sozial", query_string={"karte": "x"}).status_code == 400
    assert client.get("/api/sozial", query_string={"jahr": "2024"}).status_code == 200
    assert client.get("/sozial").status_code == 200


def test_die_baender_schliessen_unten_ein_und_oben_aus():
    assert _band(0.10) == "10 bis 20 %"
    assert _band(0.40) == "40 % und mehr"
    assert _band(None) is None


def test_spearman_ist_rangbasiert_und_braucht_zehn_paare():
    steigend = [(i, i ** 3) for i in range(12)]
    assert spearman(steigend) == 1.0
    assert spearman([(i, -i) for i in range(12)]) == -1.0
    assert spearman(steigend[:9]) is None
    # Gleichstaende bekommen den Mittelrang.
    assert spearman([(i // 2, i // 2) for i in range(12)]) == 1.0


def test_armut_und_rate_kommen_aus_demselben_vintage(brett):
    assert sozial(brett)["vintage"] == 2024


def test_ein_release_ohne_armut_laedt_und_zeigt_keine(tmp_path):
    """dim_tract_acs ohne poverty_rate: kein Band, kein Abbruch."""
    b = Bestand(stern(tmp_path, jahr("chicago", 2024, "13A", TRACT_C)))
    chicago = stadt(b.sozialbrett({"jahr": "2024"}), "chicago")
    assert all(t["armut"] is None for t in chicago["tracts"])
    assert sum(x["tracts"] for x in chicago["baender"]) == 0
