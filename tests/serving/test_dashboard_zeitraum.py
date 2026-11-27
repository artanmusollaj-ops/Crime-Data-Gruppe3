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
Seit Stufe 3 (24.11.2026) stehen dort alle sieben.
Dass die alten Links nach dem Umbau dieselben Zahlen liefern, ist zusaetzlich
am Release vom 20.11.2026 belegt: 515 verschiedene Antworten, gleich bis auf
die neuen Felder der Auswahl (``AENDERUNGEN.md``, 24.11.2026).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import serving.dashboard as dashboard
import serving.dashboard.zeitraum as zr
from serving.dashboard import Auswahl, EingabeFehler, monatsende
from serving.dashboard.app import create_app
from test_dashboard import RELEASE, bestand  # noqa: F401  (Fixture)

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


def test_alle_bretter_rechnen_tage():
    """Stufe 3: Jedes Brett, das eine Auswahl nimmt, nimmt auch Tage."""
    assert dashboard.FREIE_BRETTER == set(BRETTER)


@pytest.mark.parametrize("brett", BRETTER)
@pytest.mark.parametrize(("von", "bis"), [
    ("2024-07-04", "2024-07-04"),   # ein Tag: Tagesachse
    ("2024-06-01", "2024-08-15"),   # 76 Tage: Tagesachse
    ("2023-12-01", "2024-03-31"),   # ueber den Jahreswechsel: Wochenachse
    ("2023-01-01", "2025-03-10"),   # mehr als zwei Jahre: Monatsachse, kein Vorjahr
])
def test_jedes_brett_nimmt_einen_freien_zeitraum(bestand, brett, von, bis):  # noqa: F811
    client = create_app(bestand=bestand).test_client()
    antwort = client.get(f"/api/{brett}?stadt=alle&von={von}&bis={bis}")
    assert antwort.status_code == 200, antwort.get_data(as_text=True)[:300]
    a = antwort.json["auswahl"]
    assert (a["tag_von"], a["tag_bis"], a["ganze_monate"]) == (von, bis, False)


def test_ein_brett_ausserhalb_der_liste_lehnt_den_freien_zeitraum_ab(
        bestand, monkeypatch):  # noqa: F811
    """Abgelehnt, nicht auf Monate gerundet: sonst rechnete es still anders."""
    monkeypatch.setattr(dashboard, "FREIE_BRETTER", frozenset())
    client = create_app(bestand=bestand).test_client()
    antwort = client.get("/api/geografie?stadt=alle&von=2024-06-01&bis=2024-08-15")
    assert antwort.status_code == 400
    assert "ganze Monate" in antwort.json["fehler"]
    # Ueber eine Jahresgrenze ebenso, auch aus ganzen Monaten.
    ueber = client.get("/api/geografie?stadt=alle&von=2023-12-01&bis=2024-01-31")
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
        "Ganzer Zeitraum": ("2023-01-01", "2025-03-10"),
    }
    # Jede Vorgabe ist eine gueltige Auswahl - fuer ein Brett, das Tage rechnet.
    for von, bis in vorgaben.values():
        a = Auswahl(tag_von=date.fromisoformat(von), tag_bis=date.fromisoformat(bis))
        a.pruefe(bestand.jahre, bestand.kategorien)


def test_die_vorgabeliste_zeigt_die_aktive_vorgabe():
    """Die Liste springt nicht mehr auf »Vorgabe …« zurueck.

    Christian wollte am 27.11.2026 sehen, welche Vorgabe gerade filtert, auch
    nach dem Neuladen und auf dem naechsten Brett. ``passendeVorgabe`` sucht
    die Vorgabe, die den Zeitraum genau trifft; im Browser geprueft am selben
    Tag (Wahl, Neuladen, Datum von Hand, »Ganzer Zeitraum«).
    """
    js = (Path(dashboard.__file__).parent / "static" / "gemeinsam.js").read_text(encoding="utf-8")
    koerper = re.search(r"function zeitwahl\(o, brett, url\) \{(.*?)\n\}\n", js, re.S).group(1)
    assert 'vorgabe.value = "";' not in koerper, "die Liste springt nach der Wahl zurueck"
    assert "export function passendeVorgabe(" in js
    # Nach dem Aufbau, nach einer Wahl und nach jeder Aenderung eines Datums.
    assert koerper.count("zeigeVorgabe()") >= 2
    assert '[tagVon, tagBis].forEach((f) => f.addEventListener("change", zeigeVorgabe));' in koerper


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


# --------------------------------------------------------------------------
# Stufe 3: die Regeln in serving.dashboard.zeitraum
# --------------------------------------------------------------------------


def _a(von: str, bis: str) -> Auswahl:
    return Auswahl(tag_von=date.fromisoformat(von), tag_bis=date.fromisoformat(bis))


@pytest.mark.parametrize(("von", "bis", "art"), [
    ("2024-07-04", "2024-07-04", "tag"),
    ("2024-06-01", "2024-08-31", "monat"),   # ganze Monate bleiben Monate, auch 92 Tage
    ("2024-06-02", "2024-08-31", "tag"),     # 91 Tage
    ("2024-06-01", "2024-08-30", "tag"),     # 91 Tage, nicht ganz
    ("2024-01-01", "2024-04-01", "tag"),     # 92 Tage
    ("2024-01-01", "2024-04-02", "woche"),   # 93 Tage
    ("2023-01-01", "2024-12-31", "woche"),   # 731 Tage, ueber zwei Jahre
    ("2023-01-01", "2025-01-01", "monat"),   # 732 Tage
])
def test_die_achse_folgt_der_spanne(von, bis, art):
    assert zr.koernung(_a(von, bis)) == art


def test_die_perioden_sind_am_zeitraum_abgeschnitten():
    """Der 1.10.2023 ist ein Sonntag: Die erste Woche ist einen Tag lang."""
    assert zr.perioden(date(2023, 10, 1), date(2023, 10, 10), "woche") == [
        (date(2023, 10, 1), date(2023, 10, 1)),
        (date(2023, 10, 2), date(2023, 10, 8)),
        (date(2023, 10, 9), date(2023, 10, 10))]
    assert zr.perioden(date(2024, 1, 15), date(2024, 3, 10), "monat") == [
        (date(2024, 1, 15), date(2024, 1, 31)),
        (date(2024, 2, 1), date(2024, 2, 29)),
        (date(2024, 3, 1), date(2024, 3, 10))]


def test_ein_angeschnittener_rand_ist_hohl_aber_keine_luecke(bestand):  # noqa: F811
    """Im Diagramm ``teil``, in der Abdeckung ``voll``: Es fehlen keine Daten."""
    # 102 Tage, also je Woche; vom Sonntag, 1.10.2023, bis Mittwoch, 10.1.2024.
    z = zr.Zeitraum(bestand._cursor(), _a("2023-10-01", "2024-01-10"), ["chicago"])
    assert z.koernung == "woche"
    status = z.status("chicago")
    assert status[0] == status[-1] == "teil" and set(status[1:-1]) == {"voll"}
    assert set(z.status("chicago", rand=False)) == {"voll"}


def test_der_vergleich_nimmt_nur_tage_in_beiden_jahren(bestand):  # noqa: F811
    """Chicago endet am 1.3.2025, Detroit am 10.3.2025 (Fixture ``bestand``)."""
    cur = bestand._cursor()
    z = zr.Zeitraum(cur, _a("2025-01-01", "2025-12-31"), ["chicago", "detroit"])
    assert z.vergleich() == (date(2025, 1, 1), date(2025, 3, 1))
    assert z.vergleich(["detroit"]) == (date(2025, 1, 1), date(2025, 3, 10))
    # 2023 ist das erste Jahr: Ein Jahr frueher liegt nichts.
    assert zr.Zeitraum(cur, _a("2023-03-01", "2023-05-31"), ["chicago"]).vergleich() is None
    # Ueber ein Jahr Spanne kein Vergleich, auch wenn Daten da waeren.
    lang = zr.Zeitraum(cur, _a("2024-01-01", "2025-01-01"), ["chicago"])
    assert not lang.vergleich_moeglich and lang.vergleich() is None


def test_personenjahre(bestand):  # noqa: F811
    """Ein ganzes Jahr ist die Einwohnerzahl; ein Tag ein 366stel davon (2024)."""
    cur = bestand._cursor()
    e = bestand._einwohner(cur, "chicago")
    v = bestand.vintage_je_jahr

    def pj(von, bis):
        return zr.Zeitraum(cur, _a(von, bis), ["chicago"]).personenjahre("chicago", e, v)

    assert pj("2024-01-01", "2024-12-31") == pytest.approx(e[v[2024]])
    assert pj("2024-07-04", "2024-07-04") == pytest.approx(e[v[2024]] / 366)
    # Ueber den Jahreswechsel je Tag mit dem Vintage seines Jahres.
    assert pj("2023-12-31", "2024-01-01") == pytest.approx(e[v[2023]] / 365 + e[v[2024]] / 366)
    # Nach dem Fenster (Chicago endet am 1.3.2025) zaehlt kein Tag mehr.
    assert pj("2025-01-01", "2025-12-31") == pytest.approx(e[v[2025]] * 60 / 365)
    # Ein Jahr mit zwei Vintages hat keines, und dann gibt es keine Rate.
    assert zr.Zeitraum(cur, _a("2024-01-01", "2024-12-31"), ["chicago"]).personenjahre(
        "chicago", e, {**v, 2024: None}) is None


def test_die_rate_eines_tages_ist_je_jahr(bestand):  # noqa: F811
    """1.3.2024: Chicago vier Faelle im Tract der Stadt, Detroit zwei."""
    r = bestand.ueberblick(bestand.auswahl({"von": "2024-03-01", "bis": "2024-03-01"},
                                           "ueberblick"))["raten"]
    cur = bestand._cursor()
    v = bestand.vintage_je_jahr[2024]
    e = {s: bestand._einwohner(cur, s)[v] for s in ("chicago", "detroit")}
    assert r["zeilen"][0]["werte"] == {"chicago": round(4 * 1000 * 366 / e["chicago"], 1),
                                       "detroit": round(2 * 1000 * 366 / e["detroit"], 1)}
    assert r["tage"] == {"chicago": 1, "detroit": 1}


def test_das_vorjahr_liegt_auf_derselben_achse(bestand):  # noqa: F811
    """Ein Vorjahrestag wird ein Jahr spaeter gelegt - Wochen und Tage passen dann."""
    z = bestand.zeitverlauf(bestand.auswahl({"stadt": "detroit", "von": "2024-02-25",
                                             "bis": "2024-03-05"}, "zeitverlauf"))
    detroit = z["staedte"][0]
    assert z["achse"]["koernung"] == "tag"
    tag = z["achse"]["perioden"].index("2024-03-01")
    # 2024: zwei Taten am 1.3.; 2023: eine am 1.3. - an derselben Stelle.
    assert detroit["jetzt"][tag] == 2 and detroit["vorjahr"][tag] == 1
    assert sum(detroit["jetzt"]) == 2 and sum(detroit["vorjahr"]) == 1
    assert z["vergleich"]["von"] == "2023-02-25" and z["vergleich"]["bis"] == "2023-03-05"


def test_ueber_mehr_als_ein_jahr_kein_vorjahr_und_ein_grund(bestand):  # noqa: F811
    z = bestand.zeitverlauf(bestand.auswahl({"von": "2023-01-01", "bis": "2025-03-10"},
                                            "zeitverlauf"))
    assert z["vergleich"]["vorjahr_vorhanden"] is False
    assert "mehr als ein Jahr" in z["vergleich"]["grund"]
    assert all(v is None for s in z["staedte"] for v in s["vorjahr"])
    k = bestand.ueberblick(bestand.auswahl({"von": "2023-01-01", "bis": "2025-03-10"},
                                           "ueberblick"))["kennzahlen"]
    assert k["vorjahr_prozent"] is None and k["vorjahr_moeglich"] is False


def test_eine_doppelte_id_ueber_zwei_monate_faellt_auf(bestand):  # noqa: F811
    """Bis Stufe 3 je Monat gezaehlt: Eine ID im Januar und im Februar fiel nicht auf."""
    ziel = (bestand.data_root / "releases" / f"release={RELEASE}" / "gold"
            / "dataset=fact_offense" / "part-0001.parquet")
    tabelle = pq.read_table(ziel)
    zeilen = tabelle.to_pylist()
    januar = next(z for z in zeilen if z["date"] == date(2024, 1, 1)
                  and z["reporting_city"] == "chicago")
    zeilen.append(januar | {"date": date(2024, 2, 1)})
    pq.write_table(pa.Table.from_pylist(zeilen, schema=tabelle.schema), ziel)
    neu = dashboard.Bestand(bestand.data_root)
    jahr = neu.datenqualitaet(neu.auswahl({"jahr": "2024", "stadt": "chicago"}, "datenqualitaet"))
    assert jahr["kennzahlen"]["doppelte_ids"] == 1
    # Im Januar allein ist die ID nur einmal da.
    jan = neu.datenqualitaet(neu.auswahl({"jahr": "2024", "bis": "1", "stadt": "chicago"},
                                         "datenqualitaet"))
    assert jan["kennzahlen"]["doppelte_ids"] == 0
