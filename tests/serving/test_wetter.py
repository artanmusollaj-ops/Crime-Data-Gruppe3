"""Das Brett »Wetter« - Faelle je Tag neben dem Wetter.

Die Faelle, in denen es eine falsche Aussage macht, ohne zu werfen: die
Jahreszeit als Wettereffekt, ein Tag nach dem Datenende als Tag ohne Fall,
ein Tag ohne Fall als Luecke statt als Null.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from serving.dashboard import Bestand
from serving.dashboard.app import create_app
from serving.dashboard.wetter import ABWEICHUNG, _band, _effekt

from test_dashboard import TRACT_C, TRACT_D, schreibe, stern


def tage(von: date, bis: date):
    while von <= bis:
        yield von
        von += timedelta(days=1)


def mit_wetter(root, *, detroit_bis=date(2024, 2, 29)) -> Bestand:
    """Chicago Jan-Feb 2024: gerade Tage 10 °C und zwei Faelle, ungerade 0 °C und einer.

    Detroit hat Wetter fuer beide Monate, Faelle aber nur bis ``detroit_bis``.
    Am 15.1. hat Chicago keinen einzigen Fall - ein Tag mit Null, keine Luecke.
    """
    wetter, taten = [], []
    for t in tage(date(2024, 1, 1), date(2024, 2, 29)):
        warm = t.day % 2 == 0
        for stadt in ("chicago", "detroit"):
            wetter.append((stadt, t, 10.0 if warm else 0.0, 12.0 if t.day == 3 else 0.0))
        if t != date(2024, 1, 15):
            taten += [("chicago", t, "13A", TRACT_C)] * (2 if warm else 1)
        if t <= detroit_bis:
            taten.append(("detroit", t, "13A", TRACT_D))
    # Ein Raub, damit es die Kategorie gibt - in Detroit, nicht in Chicago.
    taten.append(("detroit", date(2024, 1, 10), "120", TRACT_D))
    schreibe(root, "dim_city_day", {
        "city": [w[0] for w in wetter], "date": [w[1] for w in wetter],
        "temp_max_c": [w[2] for w in wetter], "temp_min_c": [w[2] - 5 for w in wetter],
        "precipitation_mm": [w[3] for w in wetter], "snowfall_mm": [0.0] * len(wetter),
        "precipitation_trace": [False] * len(wetter),
        "station_name": ["O'HARE" if w[0] == "chicago" else "DETROIT METRO" for w in wetter],
    })
    return Bestand(stern(root, taten))


@pytest.fixture
def brett(tmp_path) -> Bestand:
    return mit_wetter(tmp_path, detroit_bis=date(2024, 1, 31))


def auswahl(b: Bestand, **werte) -> dict:
    return b.wetterbrett(b.auswahl({"jahr": "2024", "bis": "2"} | werte))


def stadt(d: dict, name: str) -> dict:
    return next(s for s in d["staedte"] if s["stadt"] == name)


def test_waermere_tage_als_der_monat_haben_mehr_faelle(brett):
    chicago = stadt(auswahl(brett), "chicago")
    assert chicago["effekt"]["je_grad"] > 5
    assert chicago["effekt"]["r"] > 0.9
    kaelter = next(z for z in chicago["abweichung"] if z["band"] == "bis 5 K kälter")
    assert kaelter["prozent"] < 0


def test_ein_tag_nach_dem_datenende_ist_kein_tag_ohne_fall(brett):
    """Detroits Faelle enden am 31.1.; das Wetter laeuft weiter."""
    assert stadt(auswahl(brett), "detroit")["tage"] == 31
    assert stadt(auswahl(brett), "chicago")["tage"] == 60


def test_ein_tag_ohne_fall_im_fenster_ist_eine_null(brett):
    """Der 15.1. hat in Chicago keinen Fall - er zaehlt mit, als Null."""
    chicago = stadt(auswahl(brett, bis="1"), "chicago")
    assert chicago["tage"] == 31
    assert chicago["faelle_je_tag"] == round((15 * 2 + 16 * 1 - 1) / 31, 1)


def test_die_rohe_verteilung_zeigt_faelle_je_tag_nach_temperatur(brett):
    roh = {z["band"]: z for z in stadt(auswahl(brett), "chicago")["temperatur"]}
    assert roh["10 bis 20 °C"]["faelle_je_tag"] == 2.0
    assert roh["0 bis 10 °C"]["tage"] == 31, "16 ungerade Tage im Januar, 15 im Februar"


def test_nasse_tage_sind_ab_fuenf_millimetern_nass(brett):
    nass = {z["band"]: z for z in stadt(auswahl(brett), "chicago")["niederschlag"]}
    assert nass["nass"]["tage"] == 2, "der 3. Januar und Februar mit je 12 mm"
    assert nass["trocken"]["tage"] == 58


def test_die_kategorie_filtert_die_faelle(brett):
    d = auswahl(brett, kategorie="Robbery")
    assert stadt(d, "chicago")["faelle_je_tag"] == 0
    assert stadt(d, "detroit")["faelle_je_tag"] == round(1 / 31, 1)


def test_ohne_wetter_im_release_laedt_das_dashboard(tmp_path):
    from test_dashboard import jahr
    b = Bestand(stern(tmp_path, jahr("chicago", 2024, "13A", TRACT_C)))
    assert b.wetterbrett(b.auswahl({}))["vorhanden"] is False


def test_die_baender_schliessen_unten_ein_und_oben_aus():
    assert _band(-5.0, ABWEICHUNG) == "bis 5 K kälter"
    assert _band(5.0, ABWEICHUNG) == "5 K und mehr wärmer"
    assert _band(None, ABWEICHUNG) is None


def test_der_effekt_braucht_genug_tage():
    assert _effekt([(1.0, 0.1)] * 5) is None


def test_die_api_antwortet(brett):
    client = create_app(bestand=brett).test_client()
    antwort = client.get("/api/wetter", query_string={"jahr": "2024", "bis": "2"})
    assert antwort.status_code == 200 and antwort.get_json()["vorhanden"] is True
    assert client.get("/wetter").status_code == 200
