"""Das Brett »Zeitverlauf«, Tafel »Tag und Nacht« - Faelle nach Sonnenstand.

Die Faelle, in denen die Tafel eine falsche Aussage macht, ohne zu werfen:
ein Sommerabend, der in UTC schon am Folgetag liegt und deshalb als Nacht
zaehlte; ein Platzhalter um 12:00 als heller Fall; eine Nacht, die je Stunde
gegen den laengeren Tag gestellt wird, ohne durch ihre Stunden zu teilen;
und ein aelteres Release, an dem das ganze Dashboard scheitert.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest

from serving.dashboard import Bestand
from serving.dashboard.app import create_app

from test_dashboard import TRACT_C, TRACT_D, schreibe, stern

JULI = [date(2024, 7, 1) + timedelta(days=i) for i in range(31)]
#: Sonnenauf- und -untergang in UTC, gerundet auf die Minute wie NOAA fuer
#: Anfang Juli: Chicago 05:20-20:29 CDT, Detroit 05:55-21:10 EDT. Der
#: Untergang liegt beide Male nach Mitternacht UTC, am UTC-Folgetag.
SONNE = {"chicago": (time(10, 20), time(1, 29)), "detroit": (time(9, 55), time(1, 10))}


def tageslaenge(stadt: str) -> float:
    auf, unter = SONNE[stadt]
    return ((unter.hour + 24 - auf.hour) * 60 + unter.minute - auf.minute) / 60


def sonnenstand(root, *, mit_sonne: bool = True) -> None:
    """``dim_city_day`` fuer Juli 2024; ohne Sonne wie ein Release mit Vertrag 8."""
    zeilen = [(s, t) for s in SONNE for t in JULI]
    spalten = {
        "city": [s for s, _ in zeilen], "date": [t for _, t in zeilen],
        "temp_max_c": [25.0] * len(zeilen), "temp_min_c": [15.0] * len(zeilen),
        "precipitation_mm": [0.0] * len(zeilen), "snowfall_mm": [0.0] * len(zeilen),
        "precipitation_trace": [False] * len(zeilen),
        "station_name": ["STATION"] * len(zeilen),
    }
    if mit_sonne:
        spalten |= {
            "sunrise_utc": [datetime.combine(t, SONNE[s][0]) for s, t in zeilen],
            "sunset_utc": [datetime.combine(t + timedelta(days=1), SONNE[s][1]) for s, t in zeilen],
            "daylight_hours": [tageslaenge(s) for s, _ in zeilen],
        }
    schreibe(root, "dim_city_day", spalten)


TATEN = [
    # 03:00 CDT ist vor dem Aufgang: dunkel.
    ("chicago", date(2024, 7, 1), "13A", TRACT_C, time(3, 0)),
    # Platzhalter: weder hell noch dunkel.
    ("chicago", date(2024, 7, 1), "13A", TRACT_C, time(0, 0)),
    ("chicago", date(2024, 7, 1), "13A", TRACT_C, time(12, 0)),
    # 30 Sekunden daneben ist keiner - Mittag ist hell.
    ("chicago", date(2024, 7, 1), "13A", TRACT_C, time(12, 0, 30)),
    # 20:28 CDT ist 01:28 UTC am 2.7. - vor dem Untergang um 01:29: hell.
    ("chicago", date(2024, 7, 1), "13A", TRACT_C, time(20, 28)),
    # 21:00 CDT ist 02:00 UTC am 2.7.: dunkel.
    ("chicago", date(2024, 7, 1), "13A", TRACT_C, time(21, 0)),
    # Eine weitere Anklage im selben Fall: eine Tat mehr, kein Fall mehr.
    ("chicago", date(2024, 7, 1), "13A", TRACT_C, time(14, 0), False),
    ("chicago", date(2024, 7, 31), "23C", TRACT_C, time(10, 0)),
    ("detroit", date(2024, 7, 1), "13A", TRACT_D, time(18, 5)),
    ("detroit", date(2024, 7, 31), "13A", TRACT_D, time(23, 0)),
]


@pytest.fixture
def brett(tmp_path) -> Bestand:
    sonnenstand(tmp_path)
    return Bestand(stern(tmp_path, TATEN))


def licht(b: Bestand, stadt: str = "chicago", **werte) -> dict:
    d = b.zeitverlauf(b.auswahl({"stadt": stadt, "jahr": "2024", "von": "7", "bis": "7"} | werte))
    return d["staedte"][0]


def gruppen(s: dict) -> dict[str, int]:
    return {g["gruppe"]: g["faelle"] for g in s["licht"]["gruppen"]}


def test_der_sommerabend_in_utc_am_folgetag_ist_hell(brett):
    """20:28 CDT ist hell, 21:00 dunkel - obwohl beide in UTC am 2.7. liegen."""
    assert gruppen(licht(brett))["hell"] == 3, "12:00:30, 20:28 und der 31.7. um 10:00"
    assert gruppen(licht(brett))["dunkel"] == 2, "03:00 und 21:00"


def test_platzhalter_sind_weder_hell_noch_dunkel(brett):
    assert gruppen(licht(brett))["unsicher"] == 2
    assert [g["name"] for g in licht(brett)["licht"]["gruppen"]] == [
        "Tageslicht", "Dunkelheit", "Uhrzeit unsicher"]


def test_hell_dunkel_und_unsicher_sind_die_faelle_des_bretts(brett):
    """Faelle, nicht Taten: Die zweite Anklage zaehlt nirgends."""
    s = licht(brett)
    assert sum(gruppen(s).values()) == s["licht"]["faelle"] == sum(s["jetzt"]) == 7
    assert [g["anteil"] for g in s["licht"]["gruppen"]] == [
        round(3 * 100 / 7, 1), round(2 * 100 / 7, 1), round(2 * 100 / 7, 1)]
    assert s["licht"]["dunkel_anteil"] == 40.0, "zwei von fuenf mit bekannter Uhrzeit"


def test_je_stunde_wird_durch_die_hellen_und_dunklen_stunden_geteilt(brett):
    """Der Juli hat gut fuenfzehn Stunden Licht und knapp neun Stunden Nacht."""
    s = licht(brett)["licht"]
    hell_h = 31 * tageslaenge("chicago")
    # Auf eine Stelle gerundet; 31 x 15,15 = 469,65 liegt genau auf der Kante.
    assert s["stunden"]["hell"] == pytest.approx(hell_h, abs=0.06)
    assert s["stunden"]["dunkel"] == pytest.approx(31 * 24 - hell_h, abs=0.06)
    assert s["je_stunde"] == {"hell": round(3 / hell_h, 2),
                              "dunkel": round(2 / (31 * 24 - hell_h), 2)}


def test_die_stunden_zaehlen_nur_tage_im_fenster_der_stadt(tmp_path):
    """Detroits Faelle enden am 1.7.; ein Tag danach hat keine Stunden."""
    sonnenstand(tmp_path)
    b = Bestand(stern(tmp_path, [t for t in TATEN if t[0] == "chicago"]
                      + [("detroit", date(2024, 7, 1), "13A", TRACT_D, time(18, 5))]))
    s = licht(b, "detroit")["licht"]
    assert s["stunden"]["hell"] == round(tageslaenge("detroit"), 1)


def test_der_dunkel_anteil_je_kategorie(brett):
    kategorien = {k["kategorie"]: k for k in licht(brett)["licht"]["kategorien"]}
    assert kategorien["Assault Offenses"]["dunkel_anteil"] == 50.0
    assert kategorien["Assault Offenses"]["faelle"] == 4, "ohne die beiden Platzhalter"
    assert kategorien["Larceny/Theft Offenses"]["dunkel_anteil"] == 0.0
    assert kategorien["Assault Offenses"]["name"] == "Körperverletzung"


def test_hoechstens_acht_kategorien(brett, monkeypatch):
    """Nach Faellen mit bekannter Uhrzeit geordnet, der Rest faellt weg."""
    import serving.dashboard.zeitverlauf as zv
    assert zv.LICHT_KATEGORIEN == 8
    monkeypatch.setattr(zv, "LICHT_KATEGORIEN", 1)
    assert [k["kategorie"] for k in licht(brett)["licht"]["kategorien"]] == ["Assault Offenses"]


def test_die_kategorie_filtert_die_tafel(brett):
    s = licht(brett, kategorie="Larceny/Theft Offenses")
    assert gruppen(s) == {"hell": 1, "dunkel": 0, "unsicher": 0}


def test_detroit_rechnet_in_seiner_eigenen_zone(brett):
    """23:00 EDT am 31.7. ist dunkel, 18:05 EDT am 1.7. hell."""
    assert gruppen(licht(brett, "detroit")) == {"hell": 1, "dunkel": 1, "unsicher": 0}


def test_ein_release_ohne_sonnenstand_laedt_und_nennt_den_grund(tmp_path):
    """Vertrag 8: dim_city_day ohne sunrise_utc. Das Wetter bleibt da."""
    sonnenstand(tmp_path, mit_sonne=False)
    b = Bestand(stern(tmp_path, TATEN))
    s = licht(b)
    assert s["licht"]["vorhanden"] is False
    assert "sunrise_utc" in s["licht"]["grund"] and "Vertrag 8" in s["licht"]["grund"]
    assert s["heatmap"]["platzhalter"] == 2, "die uebrige Seite rechnet weiter"
    assert b.wetterbrett(b.auswahl({"jahr": "2024", "von": "7", "bis": "7"}))["vorhanden"] is True


def test_ein_release_ohne_dim_city_day_laedt_und_nennt_den_grund(tmp_path):
    s = licht(Bestand(stern(tmp_path, TATEN)))
    assert s["licht"] == {"vorhanden": False,
                          "grund": "Dieses Release führt keine Tabelle dim_city_day."}


def test_die_api_liefert_die_tafel(brett):
    client = create_app(bestand=brett).test_client()
    antwort = client.get("/api/zeitverlauf?jahr=2024&stadt=beide&von=7&bis=7")
    assert antwort.status_code == 200
    assert [s["licht"]["vorhanden"] for s in antwort.json["staedte"]] == [True, True]
    seite = client.get("/zeitverlauf").get_data(as_text=True)
    assert 'id="tag-nacht"' in seite and "Tag und Nacht" in seite


def test_beide_staedte_zeigen_dieselben_kategorien(brett):
    """23C hat nur Chicago - in »Beide« steht sie auch bei Detroit, mit null Faellen."""
    d = brett.zeitverlauf(brett.auswahl({"stadt": "beide", "jahr": "2024", "von": "7", "bis": "7"}))
    je_stadt = {s["stadt"]: s["licht"]["kategorien"] for s in d["staedte"]}
    assert [k["kategorie"] for k in je_stadt["chicago"]] == [k["kategorie"] for k in je_stadt["detroit"]]
    detroit = {k["kategorie"]: k for k in je_stadt["detroit"]}
    assert len(detroit) == 2
    leer = [k for k in detroit.values() if k["faelle"] == 0]
    assert len(leer) == 1 and leer[0]["dunkel_anteil"] is None
