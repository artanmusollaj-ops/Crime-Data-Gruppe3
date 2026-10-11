"""Die Bruecke zwischen Dashboardzahl und Dokumentzahl - und sie war unbewacht.

``tests/test_abgabedokumente.py`` haelt die Rate je 1'000 Einwohner in
``ln2_konzept.md`` und ``README.md`` gegen ``gold_pipeline.raten_je_stadt``.
``tests/serving/test_build_kibana.py`` haelt jede Kachel dagegen, dass
ueberhaupt etwas zurueckkommt. Zwischen beiden lag bis zum 11.10.2026 nichts:
Das Dashboard konnte eine andere Zahl zeigen als die Abgabe, und es waere erst
jemandem aufgefallen, der beide nebeneinander liest - im Zweifel der Pruefenden.

Diese Datei schliesst die Luecke. Sie stellt die **Abfrage der Kachel** an
Elasticsearch und haelt ihr Ergebnis gegen dieselbe DuckDB-Abfrage, aus der die
Dokumente ihre Zahlen beziehen.

**Warum zwei Gegenproben dazugehoeren.** Der stille Fehler dieser Auswertung
ist nicht die Abfrage, sondern der Nenner, und er wirft nie. Drei Wege fuehren
zu einer Zahl, die man hinschreiben kann:

* ohne ``WHERE vintage == population_vintage`` zaehlt jede Tat viermal (vier
  ACS-Vintages liegen im Nennerindex) - 356,1 statt 94,5;
* mit ``SUM(population)`` statt ``MAX`` waechst der Nenner um den Faktor
  "Delikte je Tract" - 0,3 statt 94,5;
* ohne Jahresfilter stehen sechs Jahrgaenge Zaehler auf einem Jahr Nenner -
  500,7 statt 94,5.

Ein Waechter, der nur den richtigen Fall prueft, haette alle drei
durchgelassen: Die richtige Abfrage stimmt ja weiter. Geprueft wird deshalb
auch, dass die beiden ersten **falsch** herauskommen - sonst traegt die Abfrage
die Bedingung gar nicht mehr, und niemand merkt es.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from gold_pipeline import RATENJAHR, raten_je_stadt, raten_je_tract

from serving import build_kibana as bk
from serving import load_elasticsearch as le

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GOLD = PROJECT_ROOT / "data" / "gold"
ELASTICSEARCH = os.environ.get("ELASTICSEARCH_URL", "http://localhost:19200")

#: Dieselbe Toleranz wie in ``tests/test_abgabedokumente.py``: Beide Seiten
#: runden auf eine Nachkommastelle, und 0,05 ist genau die halbe Stelle.
TOLERANZ = 0.05


def _parquet(dataset: str) -> Path:
    return GOLD / f"dataset={dataset}" / "part-0001.parquet"


@pytest.fixture(scope="module")
def elastic():
    klient = le.HttpKlient(ELASTICSEARCH)
    try:
        klient.anfrage("GET", "/fact_offense/_count")
        klient.anfrage("GET", "/dim_tract_acs/_count")
    except Exception:
        pytest.skip(f"kein geladenes Sternschema unter {ELASTICSEARCH}")
    return klient


@pytest.fixture(scope="module")
def aus_gold():
    """Delikte, Faelle, Einwohner und beide Raten je Stadt - aus Parquet.

    Dieselbe Funktion, die hinter jeder Ratenzeile der Abgabedokumente steht.
    Eine zweite Fassung hier waere die Stelle, an der Dashboard und Dokument
    auseinanderlaufen koennten, ohne dass ein Test es sieht.
    """
    duckdb = pytest.importorskip("duckdb")
    pfade = [_parquet(n) for n in
             ("fact_offense", "dim_tract", "dim_tract_acs")]
    if not all(p.exists() for p in pfade):
        pytest.skip("Gold nicht gebaut")
    con = duckdb.connect()
    try:
        zeilen = con.execute(raten_je_stadt(
            *(f"read_parquet('{p}')" for p in pfade))).fetchall()
    finally:
        con.close()
    return {z[0]: dict(zip(
        ("delikte", "faelle", "einwohner", "rate", "rate_fallebene"), z[1:]))
        for z in zeilen}


def _esql(elastic, abfrage: str) -> dict[str, dict]:
    """Eine ES|QL-Abfrage, als ``{Stadt: {Spalte: Wert}}``."""
    antwort = elastic.anfrage("POST", "/_query", {"query": abfrage})
    namen = [s["name"] for s in antwort["columns"]]
    zeilen = [dict(zip(namen, w)) for w in antwort["values"]]
    return {z["stadt"]: z for z in zeilen}


@pytest.mark.referenzstand
def test_die_kachel_zeigt_dieselbe_rate_wie_die_dokumente(elastic, aus_gold):
    """Die Bruecke selbst: Elasticsearch gegen ``raten_je_stadt``.

    Gestellt wird nicht eine nachgebaute Abfrage, sondern genau die, die im
    Lens-Objekt der Kachel steht. Eine Kopie hier waere eine zweite Wahrheit,
    und sie wuerde gruen bleiben, waehrend das Dashboard etwas anderes zeigt.
    """
    gemessen = _esql(elastic, bk.RATE_JE_STADT.esql)
    assert set(gemessen) == set(aus_gold), (
        f"Dashboard nennt {sorted(gemessen)}, Gold {sorted(aus_gold)}")

    # Woran es liegen kann, wenn allein der Nenner abweicht: Die Kachel
    # summiert ueber die Tracts mit mindestens einer Tat im Jahrgang,
    # ``einwohner_je_stadt`` ueber jeden Tract mit Stadtzuordnung. Heute
    # dieselbe Menge; ein Tract-Jahr ohne Tat trennt die beiden, und dann
    # hat keine der beiden Seiten falsch gerechnet.
    getrennte_nenner = (
        "Weichen nur die Einwohner ab, kann es an der Grundmenge liegen: "
        "die Kachel summiert ueber Tracts mit mindestens einer Tat in "
        f"{RATENJAHR}, gold_pipeline.einwohner_je_stadt ueber jeden Tract "
        "mit Stadtzuordnung. Ein Tract-Jahr ohne Tat trennt die beiden, "
        "ohne dass eine Seite falsch rechnet.")

    for stadt, zeile in gemessen.items():
        erwartet = aus_gold[stadt]
        assert zeile["taten"] == erwartet["delikte"], stadt
        assert zeile["faelle"] == erwartet["faelle"], stadt
        assert zeile["einwohner"] == erwartet["einwohner"], (
            f"{stadt}: {getrennte_nenner}")
        assert zeile["rate_tatebene"] == pytest.approx(
            erwartet["rate"], abs=TOLERANZ), stadt
        assert zeile["rate_fallebene"] == pytest.approx(
            erwartet["rate_fallebene"], abs=TOLERANZ), stadt


def test_die_kachel_nennt_das_jahr_ihrer_rate():
    """Eine Rate ohne Zeitraum ist keine - und sie sieht aus wie eine.

    Der Jahresfilter steckt in der Abfrage, das Jahr steht an der Tafel.
    Beide muessen dasselbe sagen; stuende in der Abfrage ein anderes Jahr,
    traegt die Kachel eine richtige Zahl unter einer falschen Ueberschrift.

    **Ohne Dienste und ohne ``referenzstand``.** Das hier ist eine Aussage
    ueber den Code, nicht ueber die Daten. Mit den beiden Fixtures - die er
    anforderte und nie benutzte - uebersprang er sich ohne laufendes
    Elasticsearch und lief damit auf keinem Pull Request.
    """
    tafel = next(t for b in bk.BRETTER for t in b.tafeln
                 if t.abfrage is bk.RATE_JE_STADT)
    assert tafel.jahr == RATENJAHR
    assert f'"{RATENJAHR}-01-01"' in tafel.abfrage.esql
    assert str(RATENJAHR) in tafel.titel


@pytest.mark.referenzstand
def test_gegenprobe_ohne_vintage_filter_ergibt_eine_falsche_zahl(
        elastic, aus_gold):
    """Vier Vintages liegen im Nennerindex, und der Verbund geht ueber eines.

    ``LOOKUP JOIN`` verbindet ueber **ein** Feld und liefert deshalb vier
    Zeilen je Tat - 6'282 Tracts mal vier Jahrgaenge. Ohne das
    ``WHERE vintage == population_vintage`` danach vervierfacht sich der
    Zaehler, und das Ergebnis sieht aus wie eine Rate.
    """
    kaputt = bk.RATE_JE_STADT.esql.replace(
        "| WHERE vintage == population_vintage\n", "")
    assert kaputt != bk.RATE_JE_STADT.esql, (
        "die Gegenprobe greift nicht mehr - steht der Vintage-Filter noch "
        "in der Abfrage?")

    gemessen = _esql(elastic, kaputt)
    for stadt, zeile in gemessen.items():
        richtig = aus_gold[stadt]["rate"]
        assert abs(zeile["rate_tatebene"] - richtig) > TOLERANZ, (
            f"{stadt}: ohne Vintage-Filter kommt dieselbe Zahl heraus - "
            f"dann traegt der Filter nichts, und der Waechter oben beweist "
            f"nichts")


@pytest.mark.referenzstand
def test_gegenprobe_mit_summiertem_nenner_ergibt_eine_falsche_zahl(
        elastic, aus_gold):
    """Der Nenner wird je Tract **einmal** gezaehlt, nicht je Delikt.

    ``MAX(population)`` je ``(Stadt, Tract)`` ist der Punkt. ``SUM`` an
    derselben Stelle addiert die Einwohnerzahl so oft, wie der Tract Delikte
    hat - der Nenner wird dreistellig zu gross und die Rate winzig.
    """
    kaputt = bk.RATE_JE_STADT.esql.replace(
        "MAX(population)", "SUM(population)")
    assert kaputt != bk.RATE_JE_STADT.esql, (
        "die Gegenprobe greift nicht mehr - steht MAX(population) noch in "
        "der Abfrage?")

    gemessen = _esql(elastic, kaputt)
    for stadt, zeile in gemessen.items():
        richtig = aus_gold[stadt]["rate"]
        assert abs(zeile["rate_tatebene"] - richtig) > TOLERANZ, (
            f"{stadt}: SUM und MAX liefern dasselbe - dann wird je Tract "
            f"nur eine Zeile gruppiert, und die Bedingung traegt nichts")
        assert zeile["einwohner"] > aus_gold[stadt]["einwohner"], stadt


# --------------------------------------------------------------------------
# Dieselbe Bruecke eine Ebene tiefer - und die Tracts, die keine Rate bekommen
# --------------------------------------------------------------------------
#
# Die Kachel "Rate je Tract" wird fotografiert und landet in ``docs/bilder``;
# sie ist damit eine veroeffentlichte Zahl wie die Stadtrate. Bis zum
# 11.10.2026 hielt sie niemand gegen eine unabhaengige Quelle: Nachgemessen
# mit einer Mutationsprobe blieb alles gruen, als nur in dieser einen Abfrage
# ``MAX`` zu ``SUM`` wurde und als ``population > 0`` darin verschwand.


@pytest.fixture(scope="module")
def tracts_aus_gold():
    """Alle Tract-Raten aus Parquet, absteigend - ``{(stadt, geoid): Zeile}``."""
    duckdb = pytest.importorskip("duckdb")
    pfade = [_parquet(n) for n in ("fact_offense", "dim_tract_acs")]
    if not all(p.exists() for p in pfade):
        pytest.skip("Gold nicht gebaut")
    con = duckdb.connect()
    try:
        zeilen = con.execute(raten_je_tract(
            *(f"read_parquet('{p}')" for p in pfade))).fetchall()
    finally:
        con.close()
    namen = ("stadt", "geoid", "faelle", "rate_fallebene",
             "taten", "rate_tatebene", "einwohner")
    return [dict(zip(namen, z)) for z in zeilen]


def _esql_zeilen(elastic, abfrage: str) -> list[dict]:
    antwort = elastic.anfrage("POST", "/_query", {"query": abfrage})
    namen = [s["name"] for s in antwort["columns"]]
    return [dict(zip(namen, w)) for w in antwort["values"]]


@pytest.mark.referenzstand
def test_die_tract_kachel_zeigt_dieselbe_rate_wie_gold(elastic, tracts_aus_gold):
    """Je Tract dieselbe Zahl wie aus Parquet - und wirklich die hoechsten.

    Verglichen wird **je Tract** und nicht der Reihe nach: Bei gleichen Raten
    duerfen Elasticsearch und DuckDB verschiedene Zwanzig waehlen, ohne dass
    einer von beiden falsch rechnet. Dass es die hoechsten sind, prueft der
    zweite Teil - kein Tract aus Gold liegt ueber dem kleinsten gezeigten.
    """
    gezeigt = _esql_zeilen(elastic, bk.RATE_JE_TRACT.esql)
    assert gezeigt, "die Kachel zeigt keine Zeile"

    nach_tract = {(z["stadt"], z["geoid"]): z for z in tracts_aus_gold}
    for zeile in gezeigt:
        schluessel = (zeile["stadt"], zeile["geoid"])
        erwartet = nach_tract.get(schluessel)
        assert erwartet is not None, f"{schluessel} kennt Gold nicht"
        for spalte in ("faelle", "taten", "einwohner"):
            assert zeile[spalte] == erwartet[spalte], f"{schluessel}/{spalte}"
        for spalte in ("rate_fallebene", "rate_tatebene"):
            assert zeile[spalte] == pytest.approx(
                erwartet[spalte], abs=TOLERANZ), f"{schluessel}/{spalte}"

    kleinste_gezeigte = min(z["rate_fallebene"] for z in gezeigt)
    draussen = {(z["stadt"], z["geoid"]) for z in tracts_aus_gold} - set(
        (z["stadt"], z["geoid"]) for z in gezeigt)
    hoeher = [z for z in tracts_aus_gold
              if (z["stadt"], z["geoid"]) in draussen
              and z["rate_fallebene"] > kleinste_gezeigte + TOLERANZ]
    assert not hoeher, (
        f"{len(hoeher)} Tracts liegen hoeher als der kleinste gezeigte "
        f"({kleinste_gezeigte}) und fehlen auf der Kachel, z. B. "
        f"{hoeher[0]['geoid']} mit {hoeher[0]['rate_fallebene']}")


@pytest.mark.referenzstand
def test_kein_tract_ohne_einwohner_bekommt_eine_rate(elastic):
    """``population == 0`` heisst nicht "sichere Gegend", sondern "niemand da".

    Eine Null waere dort keine Rate, sondern eine Division durch null - und
    gezeigt liest sie sich als Sicherheit. Die beiden Kacheln teilen die
    Grundmenge deshalb auf: Rate fuer die bewohnten, Zaehlung fuer die
    anderen.
    """
    gezeigt = _esql_zeilen(elastic, bk.RATE_JE_TRACT.esql)
    ohne = [z for z in gezeigt if z["einwohner"] == 0]
    assert not ohne, (
        f"{len(ohne)} Tracts ohne Einwohner stehen in der Ratenkachel - "
        "steht 'population > 0' noch in der Abfrage?")

    gezaehlt = _esql_zeilen(elastic, bk.TRACTS_OHNE_EINWOHNER.esql)
    assert gezaehlt, "die Kachel fuer Tracts ohne Einwohner bleibt leer"
    assert all(z["tracts"] > 0 and z["taten"] > 0 for z in gezaehlt), gezaehlt


@pytest.mark.referenzstand
def test_gegenprobe_ohne_einwohnerfilter_holt_unbewohnte_tracts_herein(
        elastic):
    """Ohne ``population > 0`` steht ein unbewohnter Tract in der Ratenkachel.

    Die Gegenprobe zum Test darueber: Traegt die Bedingung nichts, kommt
    ohne sie dasselbe heraus - und dann beweist der Test nichts.
    """
    kaputt = bk.RATE_JE_TRACT.esql.replace(
        "AND population > 0", "AND population >= 0")
    assert kaputt != bk.RATE_JE_TRACT.esql, (
        "die Gegenprobe greift nicht mehr - steht 'population > 0' noch in "
        "der Abfrage?")

    gezeigt = _esql_zeilen(elastic, kaputt)
    assert any(z["einwohner"] == 0 for z in gezeigt), (
        "auch ohne den Filter steht kein unbewohnter Tract oben - dann "
        "traegt der Filter nichts, und der Test darueber beweist nichts")
