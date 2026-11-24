"""Der Zeitraum der Leiste ist ein Tagesbereich (Stufe 2, 24.11.2026).

Bis hier kannte die Leiste nur Monate eines Jahres: ``jahr=2024&von=3&bis=5``.
Jetzt nimmt sie auch Tage: ``von=2024-06-01&bis=2024-08-31``. Was dabei still
falsch werden kann:

- ein alter Link, der anders antwortet als vorher - er steht in Notizen,
  Dokumenten und Lesezeichen;
- ein Datum, das unter mehreren Schreibweisen gilt, sodass dieselbe Auswahl
  mehrere Adressen hat;
- ein Brett, das einen freien Zeitraum annimmt, ihn aber in Monaten rechnet
  und dabei Tage dazu- oder wegnimmt, ohne dass es jemand sieht.

Darum: Ein Brett rechnet Tage erst, wenn es in ``FREIE_BRETTER`` steht, und
lehnt bis dahin jeden anderen Zeitraum als ganze Monate eines Jahres ab.
Dass die alten Links nach dem Umbau dieselben Zahlen liefern, ist zusaetzlich
am Release vom 20.11.2026 belegt: 515 verschiedene Antworten, gleich bis auf
die neuen Felder der Auswahl (``AENDERUNGEN.md``, 24.11.2026).
"""

from __future__ import annotations

from datetime import date

import pytest

import serving.dashboard as dashboard
from serving.dashboard import Auswahl, EingabeFehler, monatsende
from serving.dashboard.app import create_app
from test_dashboard import bestand  # noqa: F401  (Fixture)

#: Die Bretter, die eine Auswahl aus der Leiste nehmen, mit ihrem Namen in
#: ``FREIE_BRETTER``.
BRETTER = ["ueberblick", "zeitverlauf", "geografie", "deliktstruktur",
           "datenqualitaet", "wetter", "sozial"]


@pytest.mark.parametrize(("tag", "ende"), [
    (date(2024, 2, 10), date(2024, 2, 29)),
    (date(2025, 2, 1), date(2025, 2, 28)),
    (date(2024, 12, 31), date(2024, 12, 31)),
    (date(2024, 4, 30), date(2024, 4, 30)),
])
def test_das_monatsende(tag, ende):
    assert monatsende(tag) == ende


@pytest.mark.parametrize(("von", "bis", "ganz"), [
    (date(2024, 1, 1), date(2024, 12, 31), True),
    (date(2024, 3, 1), date(2024, 3, 31), True),
    (date(2024, 2, 1), date(2024, 2, 29), True),
    (date(2024, 2, 1), date(2024, 2, 28), False),
    (date(2024, 3, 2), date(2024, 3, 31), False),
    (date(2024, 12, 1), date(2025, 1, 31), False),
    (date(2024, 7, 4), date(2024, 7, 4), False),
])
def test_ganze_monate_eines_jahres(von, bis, ganz):
    assert Auswahl(tag_von=von, tag_bis=bis).ganze_monate is ganz


def test_die_antwort_nennt_jahr_und_monate_nur_bei_ganzen_monaten():
    alt = Auswahl(tag_von=date(2024, 3, 1), tag_bis=date(2024, 5, 31)).json
    assert (alt["jahr"], alt["von"], alt["bis"], alt["tage"]) == (2024, 3, 5, 92)
    frei = Auswahl(tag_von=date(2024, 7, 4), tag_bis=date(2024, 7, 4)).json
    assert (frei["jahr"], frei["von"], frei["bis"]) == (None, None, None)
    assert (frei["tag_von"], frei["tag_bis"], frei["tage"]) == ("2024-07-04", "2024-07-04", 1)


def test_ein_alter_link_meint_dieselben_tage_wie_der_neue(bestand):  # noqa: F811
    alt = bestand.auswahl({"jahr": "2024", "von": "3", "bis": "5"}, "ueberblick")
    neu = bestand.auswahl({"von": "2024-03-01", "bis": "2024-05-31"}, "ueberblick")
    assert alt == neu
    assert (alt.tag_von, alt.tag_bis) == (date(2024, 3, 1), date(2024, 5, 31))
    # Ohne Angabe wie bisher: das Ratenjahr, ganz.
    vorgabe = bestand.auswahl({})
    assert (vorgabe.tag_von, vorgabe.tag_bis) == (date(dashboard.RATENJAHR, 1, 1),
                                                  date(dashboard.RATENJAHR, 12, 31))


@pytest.mark.parametrize("brett", ["ueberblick", "zeitverlauf", "geografie",
                                   "deliktstruktur", "datenqualitaet"])
def test_beide_schreibweisen_liefern_dieselbe_antwort(bestand, brett):  # noqa: F811
    client = create_app(bestand=bestand).test_client()
    alt = client.get(f"/api/{brett}?stadt=alle&jahr=2024&von=2&bis=4")
    neu = client.get(f"/api/{brett}?stadt=alle&von=2024-02-01&bis=2024-04-30")
    assert alt.status_code == neu.status_code == 200
    assert alt.get_data() == neu.get_data()


@pytest.mark.parametrize("werte", [
    # Nur genau JJJJ-MM-TT: sonst haette dieselbe Auswahl mehrere Adressen.
    {"von": "20240101", "bis": "20241231"},
    {"von": "2024-W01-1", "bis": "2024-12-31"},
    {"von": "2024-1-1", "bis": "2024-12-31"},
    {"von": "2024-02-30", "bis": "2024-03-31"},
    # Gemischt: ein Datum und ein Monat.
    {"von": "2024-03-01", "bis": "5"},
    {"jahr": "2024", "von": "3", "bis": "2024-05-31"},
    # Verkehrt herum, und ausserhalb der Jahrgaenge.
    {"von": "2024-05-31", "bis": "2024-03-01"},
    {"von": "2019-01-01", "bis": "2019-12-31"},
    {"von": "2024-01-01", "bis": "2030-12-31"},
])
def test_ein_falsches_datum_ist_ein_eingabefehler(bestand, werte):  # noqa: F811
    with pytest.raises(EingabeFehler):
        bestand.auswahl(werte, "ueberblick")


@pytest.mark.parametrize("brett", BRETTER)
def test_ein_brett_ohne_tage_lehnt_den_freien_zeitraum_ab(bestand, brett):  # noqa: F811
    """Abgelehnt, nicht auf Monate gerundet: sonst rechnete es still anders."""
    assert brett not in dashboard.FREIE_BRETTER
    client = create_app(bestand=bestand).test_client()
    antwort = client.get(f"/api/{brett}?stadt=alle&von=2024-06-01&bis=2024-08-15")
    assert antwort.status_code == 400
    assert "ganze Monate" in antwort.json["fehler"]
    # Ueber eine Jahresgrenze ebenso, auch aus ganzen Monaten.
    ueber = client.get(f"/api/{brett}?stadt=alle&von=2023-12-01&bis=2024-01-31")
    assert ueber.status_code == 400


def test_ein_freies_brett_nimmt_den_tag(bestand, monkeypatch):  # noqa: F811
    monkeypatch.setattr(dashboard, "FREIE_BRETTER", frozenset({"zeitverlauf"}))
    a = bestand.auswahl({"von": "2024-07-04", "bis": "2024-07-04"}, "zeitverlauf")
    assert (a.tag_von, a.tage, a.ganze_monate) == (date(2024, 7, 4), 1, False)
    with pytest.raises(EingabeFehler, match="ganze Monate"):
        bestand.auswahl({"von": "2024-07-04", "bis": "2024-07-04"}, "geografie")


def test_die_optionen_tragen_fenster_und_vorgaben(bestand):  # noqa: F811
    """Im Bestand reichen die Daten vom 1.1.2023 bis zum 10.3.2025 (Detroit)."""
    o = create_app(bestand=bestand).test_client().get("/api/optionen").json
    assert o["frei"] == sorted(dashboard.FREIE_BRETTER)
    assert o["tage"] == {"erster": "2023-01-01", "letzter": "2025-03-10"}
    vorgaben = {v["name"]: (v["von"], v["bis"]) for v in o["vorgaben"]}
    assert vorgaben == {
        "Letzter Tag": ("2025-03-10", "2025-03-10"),
        "Letzte 7 Tage": ("2025-03-04", "2025-03-10"),
        "Letzte 30 Tage": ("2025-02-09", "2025-03-10"),
        "Letzte 12 Monate": ("2024-03-11", "2025-03-10"),
        "Laufendes Jahr": ("2025-01-01", "2025-03-10"),
        # Der Sommer 2025 ist noch nicht vorbei.
        "Sommer 2024": ("2024-06-01", "2024-08-31"),
        "Ganzer Bestand": ("2023-01-01", "2025-03-10"),
    }
    # Jede Vorgabe ist eine gueltige Auswahl - fuer ein Brett, das Tage rechnet.
    for von, bis in vorgaben.values():
        a = Auswahl(tag_von=date.fromisoformat(von), tag_bis=date.fromisoformat(bis))
        a.pruefe(bestand.jahre, bestand.kategorien)


def test_die_zeitwahl_ist_auf_jedem_brett_mit_monaten(bestand):  # noqa: F811
    """Die Tageswahl baut ``gemeinsam.js``; sie braucht die drei Monatsfelder.

    Fehlt eines auf einer Seite, bietet diese Seite die Tageswahl stumm nicht
    an - auch nicht, wenn ihr Brett in ``FREIE_BRETTER`` steht.
    """
    client = create_app(bestand=bestand).test_client()
    for seite in ["/", "/zeitverlauf", "/geografie", "/deliktstruktur",
                  "/datenqualitaet", "/wetter", "/sozial"]:
        html = client.get(seite).get_data(as_text=True)
        for feld in ('id="von"', 'id="bis"', 'id="jahr"'):
            assert feld in html, (seite, feld)
