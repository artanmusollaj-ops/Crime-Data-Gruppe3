"""Die Dashboards - geprueft, bevor sie jemand oeffnet.

Der Grossteil braucht kein Kibana: Ob eine Tafel anzeigbar ist, entscheidet
sich an ihrem JSON, und das ist eine reine Funktion. Kibana selbst prueft
davon **nichts** - es nimmt jedes wohlgeformte Objekt an und zeigt eine leere
Kachel, wenn ein Verweis ins Leere geht.

Drei Pruefungen fassen die laufenden Dienste an. Die wichtigste davon stellt
jede Tafel als echte Elasticsearch-Abfrage und sieht nach, ob etwas
zurueckkommt: Ein Dashboard, das sauber importiert und leer bleibt, ist bei
erzeugten Dashboards der Normalfall - hier faellt er auf.
"""

from __future__ import annotations

import json
import os

import pytest

from gold_pipeline import RATENJAHR
from serving import build_kibana as bk
from serving import load_elasticsearch as le
from serving.load_clickhouse import LadeFehler


ZAEHLEN = bk.Kennzahl("anzahl", "Delikte", "count")
FENSTER = ("2024-01-01T00:00:00.000Z", "2025-01-01T23:59:59.999Z")

#: Eine ES|QL-Abfrage, die keinen Verbund braucht - fuer die Faelle, in denen
#: nur die Form der Tafel geprueft wird und nicht der Nennerindex.
EINFACH = bk.Abfrage("FROM fact_offense | WHERE counts | STATS n = COUNT(*)",
                     (bk.Spalte("n", "Zeilen"),))

#: Ein Ausschluss, den ``EINFACH`` auch wirklich vollzieht - sonst bricht
#: schon ``Tafel.__post_init__`` ab, und die Form-Pruefungen traefen ihn
#: statt dessen, was sie pruefen wollen.
BELEGT = bk.Ausschluss("Zeilen ohne `counts`", "WHERE counts")

#: Alle Tafeln, einmal mit ihrer Brettkennung - die Grundlage der beiden
#: parametrisierten Pruefungen weiter unten.
ALLE_TAFELN = [(b.kennung, t) for b in bk.BRETTER for t in b.tafeln]
TAFELNAMEN = [f"{k}-{t.kennung}" for k, t in ALLE_TAFELN]


def brett(*tafeln: bk.Tafel) -> bk.Brett:
    return bk.Brett("probe", "Probe", "", tafeln, FENSTER)


# --------------------------------------------------------------------------
# Was gar nicht erst gebaut werden darf
# --------------------------------------------------------------------------


def test_eine_unentschiedene_art_bricht_ab():
    with pytest.raises(LadeFehler, match="nicht entschieden"):
        bk.Tafel("t", "T", "wolkendiagramm", ZAEHLEN)


def test_eine_zahl_gruppiert_nicht():
    with pytest.raises(LadeFehler, match="gruppiert nicht"):
        bk.Tafel("t", "T", "zahl", ZAEHLEN,
                 eimer=(bk.Eimer("e", "E", "terms", "reporting_city"),))


def test_ein_balken_ohne_gruppierung_bricht_ab():
    with pytest.raises(LadeFehler, match="mindestens eine"):
        bk.Tafel("t", "T", "balken", ZAEHLEN)


def test_eine_zu_breite_tafel_bricht_ab():
    with pytest.raises(LadeFehler, match="Raster"):
        bk.Tafel("t", "T", "zahl", ZAEHLEN, breite=60)


def test_ein_dashboard_ohne_zeitfenster_bricht_ab():
    """Der Fehler, der sich als leeres Dashboard tarnt."""
    ohne = bk.Brett("p", "P", "", (bk.Tafel("t", "T", "zahl", ZAEHLEN),))
    with pytest.raises(LadeFehler, match="letzten 15"):
        bk.dashboard_objekt(ohne)


# --------------------------------------------------------------------------
# Die Tafel
# --------------------------------------------------------------------------


def test_gruppierungen_stehen_vor_der_kennzahl():
    tafel = bk.Tafel("t", "T", "balken", ZAEHLEN,
                     eimer=(bk.Eimer("stadt", "Stadt", "terms",
                                     "reporting_city"),))
    # Lens erwartet die Eimer zuerst; andersherum wird aus dem Balken eine
    # einzige Saeule.
    assert tafel.reihenfolge == ["stadt", "anzahl"]
    assert set(tafel.reihenfolge) == set(tafel.spalten)


def test_ein_textfeld_wird_auf_dem_unterfeld_gruppiert():
    eimer = bk.Eimer("t", "Text", "terms", "source_offense_description",
                     unterfeld_keyword=True)
    # Auf ``text`` laesst sich nicht gruppieren - die Tafel bliebe leer.
    assert eimer.feldname == "source_offense_description.keyword"
    assert eimer.aggregation["terms"]["field"].endswith(".keyword")


def test_nach_schluessel_sortiert_heisst_in_beiden_darstellungen_dasselbe():
    eimer = bk.Eimer("s", "Stunde", "terms", "hour_of_day", 24,
                     ordnung="schluessel")
    lens = eimer.lens_spalte("anzahl")
    assert lens["params"]["orderBy"]["type"] == "alphabetical"
    assert lens["params"]["orderDirection"] == "asc"
    assert eimer.aggregation["terms"]["order"] == {"_key": "asc"}


def test_nach_anzahl_sortiert_zeigt_auf_die_kennzahl():
    eimer = bk.Eimer("d", "Delikt", "terms", "nibrs_code", 15)
    lens = eimer.lens_spalte("anzahl")
    assert lens["params"]["orderBy"] == {"type": "column", "columnId": "anzahl"}
    assert eimer.aggregation["terms"]["order"] == {"_count": "desc"}


def test_unique_count_setzt_seine_genauigkeit_selbst():
    """``cardinality`` schaetzt - und sagt es der Kachel nicht."""
    kz = bk.Kennzahl("t", "Tracts", "unique_count", "tract_geoid")
    assert kz.aggregation["cardinality"]["precision_threshold"] == bk.GENAUIGKEIT


def test_count_ist_keine_aggregation():
    # Elasticsearch liefert die Zeilenzahl als doc_count mit; eine eigene
    # Aggregation dafuer waere Unsinn.
    assert ZAEHLEN.aggregation is None
    assert bk.Tafel("t", "T", "zahl", ZAEHLEN).aggregation == {"size": 0}


def test_die_aggregation_verschachtelt_in_der_reihenfolge_der_eimer():
    tafel = bk.Tafel("t", "T", "balken", ZAEHLEN, eimer=(
        bk.Eimer("monat", "Monat", "date_histogram", "occurred_at_utc"),
        bk.Eimer("stadt", "Stadt", "terms", "reporting_city")))
    aggs = tafel.aggregation["aggs"]
    assert set(aggs) == {"monat"}
    assert set(aggs["monat"]["aggs"]) == {"stadt"}


# --------------------------------------------------------------------------
# Was Kibana nicht prueft
# --------------------------------------------------------------------------


def test_eine_spalte_die_niemand_anzeigt_faellt_auf():
    """Der Fehler, den Kibana wortlos durchlaesst.

    Ein XY-Diagramm zeigt genau einen Gruppierungs- und einen
    Aufteilungsverweis. Eine dritte Gruppierung liegt dann in den Spalten,
    wird aber nirgends verwendet - die Kachel erscheint, ohne sie zu zeigen.
    """
    tafel = bk.Tafel("t", "T", "balken", ZAEHLEN, eimer=(
        bk.Eimer("a", "A", "terms", "reporting_city"),
        bk.Eimer("b", "B", "terms", "mapping_status"),
        bk.Eimer("c", "C", "terms", "geo_status")))
    with pytest.raises(LadeFehler, match="nicht verwendet"):
        bk.pruefe_tafel(tafel)


@pytest.mark.parametrize("brettname,tafel", ALLE_TAFELN, ids=TAFELNAMEN)
def test_jede_echte_tafel_zeigt_alles_was_sie_traegt(brettname, tafel):
    """Gilt fuer beide Sorten Tafel, und zwar aus demselben Grund.

    Eine Lens-Tafel traegt ihre Spalten als ``Kennzahl`` und ``Eimer``, eine
    ES|QL-Tafel als die Spalten, die ihre Abfrage liefert. In beiden Faellen
    fragt ``pruefe_tafel`` dasselbe: Zeigt die Darstellung jede Spalte an,
    die die Tafel mitbringt? Eine, die niemand anzeigt, ist in Kibana nicht
    sichtbar und faellt dort auch nicht auf.
    """
    bk.pruefe_tafel(tafel)
    assert tafel.ist_esql == (tafel.abfrage is not None), brettname


# --------------------------------------------------------------------------
# ES|QL - die Tafeln, die rechnen
# --------------------------------------------------------------------------


def test_eine_esql_tafel_ohne_abfrage_bricht_ab():
    with pytest.raises(LadeFehler, match="braucht eine Abfrage"):
        bk.Tafel("t", "T", "esql_tabelle", frage="F", ausschluesse=(BELEGT,))


def test_eine_lens_tafel_mit_abfrage_bricht_ab():
    """Sonst stuende die Abfrage da und niemand stellte sie."""
    with pytest.raises(LadeFehler, match="bliebe unbenutzt"):
        bk.Tafel("t", "T", "zahl", ZAEHLEN, abfrage=EINFACH)


def test_eine_esql_tafel_mit_kennzahl_bricht_ab():
    with pytest.raises(LadeFehler, match="zweite Beschreibung"):
        bk.Tafel("t", "T", "esql_tabelle", ZAEHLEN, abfrage=EINFACH,
                 frage="F", ausschluesse=(BELEGT,))


def test_eine_lens_tafel_ohne_kennzahl_bricht_ab():
    with pytest.raises(LadeFehler, match="braucht eine Kennzahl"):
        bk.Tafel("t", "T", "zahl")


def test_eine_esql_tafel_ohne_frage_oder_ausschluesse_bricht_ab():
    """FR-27 als Bedingung des Bauens, nicht als gute Absicht."""
    with pytest.raises(LadeFehler, match="ohne 'frage'"):
        bk.Tafel("t", "T", "esql_tabelle", abfrage=EINFACH,
                 ausschluesse=(BELEGT,))
    with pytest.raises(LadeFehler, match="ohne 'ausschluesse'"):
        bk.Tafel("t", "T", "esql_tabelle", abfrage=EINFACH, frage="F")


def test_eine_rate_ohne_nenner_oder_jahr_bricht_ab():
    """Die Zahl, die nichts bedeutet: 500,7 statt 94,5.

    Sechs Jahrgaenge Zaehler auf einem Jahr Nenner. Die Abfrage wirft dabei
    nichts, das Ergebnis sieht aus wie eine Rate - deshalb ist das Jahr eine
    Bedingung und keine Empfehlung.
    """
    mit_rate = bk.Abfrage(
        "FROM fact_offense | WHERE counts | EVAL rate = 1.0 | KEEP rate",
        (bk.Spalte("rate", "Rate", ist_rate=True),))
    with pytest.raises(LadeFehler, match="Nenner und ihr Jahr"):
        bk.Tafel("t", "T", "esql_tabelle", abfrage=mit_rate, frage="F",
                 ausschluesse=(BELEGT,), jahr=RATENJAHR)
    with pytest.raises(LadeFehler, match="Nenner und ihr Jahr"):
        bk.Tafel("t", "T", "esql_tabelle", abfrage=mit_rate, frage="F",
                 ausschluesse=(BELEGT,), nenner="N")


def test_ein_verbund_auf_einen_index_ohne_lookup_modus_bricht_ab():
    """Der Fehler, den sonst erst der Leser der Kachel sieht.

    ``LOOKUP JOIN`` verlangt ``index.mode: lookup`` am rechten Index.
    Elasticsearch antwortet sonst mit *„Lookup Join requires a single lookup
    mode index"* - beim Oeffnen des Dashboards, nicht beim Bauen.
    """
    standard = next(i.name for i in le.INDIZES if not i.nachschlag)
    with pytest.raises(LadeFehler, match="lookup"):
        bk.Abfrage(f"FROM fact_offense | LOOKUP JOIN {standard} ON geoid",
                   (bk.Spalte("n", "N"),))


def test_ein_verbund_auf_einen_unbekannten_index_bricht_ab():
    with pytest.raises(LadeFehler, match="kein geladener Index"):
        bk.Abfrage("FROM fact_offense | LOOKUP JOIN gibt_es_nicht ON geoid",
                   (bk.Spalte("n", "N"),))


def test_ein_kleingeschriebener_verbund_faellt_nicht_durch():
    """ES|QL nimmt ``lookup join`` an - der Waechter muss es auch lesen.

    Nachgestellt am 11.10.2026: Mit einem Muster nur fuer Grossbuchstaben
    entstand die kleingeschriebene Fassung **ohne Fehler** und meldete
    ``nachschlagindizes == ()``. Derselbe unbekannte Index wurde gross
    geschrieben sauber abgelehnt - die Pruefung liess sich also durch
    Kleinschreibung umgehen.
    """
    klein = "FROM fact_offense | lookup join gibt_es_nicht on geoid"
    with pytest.raises(LadeFehler, match="kein geladener Index"):
        bk.Abfrage(klein, (bk.Spalte("n", "N"),))

    standard = next(i.name for i in le.INDIZES if not i.nachschlag)
    with pytest.raises(LadeFehler, match="lookup"):
        bk.Abfrage(f"FROM fact_offense | lookup join {standard} on geoid",
                   (bk.Spalte("n", "N"),))


def test_ein_ausschluss_ohne_beleg_in_der_abfrage_bricht_ab():
    """Der Fehler, den drei Kacheln mit einem geteilten Tupel hatten.

    Die Stadtkachel nannte *„Tracts ohne Einwohner"*, waehrend ihre Abfrage
    sie mitzaehlt - 1'447 Chicagoer und 361 Detroiter Taten. Die Zahl war
    richtig, der Text war falsch, und kein Test sah hin.
    """
    with pytest.raises(LadeFehler, match="vollzieht ihn aber nicht"):
        bk.Tafel("t", "T", "esql_tabelle", abfrage=EINFACH, frage="F",
                 ausschluesse=(bk.Ausschluss("Tracts ohne Einwohner",
                                             "population > 0"),))


def test_der_nachschlagindex_wird_aus_der_abfrage_gelesen():
    """Keine zweite Liste neben der Abfrage - die veraltete still."""
    assert bk.RATE_JE_STADT.nachschlagindizes == ("dim_tract_acs",)
    assert le.NACH_NAME["dim_tract_acs"].nachschlag is True


def test_eine_esql_tafel_hat_keine_search_aggregation():
    """Sie wirft, statt ``{"size": 0}`` zu liefern.

    Eine leere Aggregation waere der gefaehrlichere Weg:
    ``test_jede_tafel_bekommt_auch_wirklich_daten`` stellte sie, bekaeme
    Treffer und winkte die Kachel als "zeigt Daten" durch, ohne dass ihre
    Abfrage je gelaufen waere.
    """
    tafel = bk.BRETTER[-1].tafeln[0]
    with pytest.raises(LadeFehler, match="_query"):
        tafel.aggregation


@pytest.mark.parametrize("brettname,tafel", ALLE_TAFELN, ids=TAFELNAMEN)
def test_jede_esql_tafel_nennt_frage_und_ausschluesse(brettname, tafel):
    """FR-27 - fuer die neuen Kacheln eingeloest, fuer die alten offen.

    Die vierzehn Kacheln der drei alten Bretter zeigen Zaehlungen und
    Anteile; ihre Angaben sind zurueckgestellt (siehe ``deferred-work.md``).
    Jede ES|QL-Kachel traegt sie von Anfang an, und eine mit einer Rate
    zusaetzlich Nenner und Jahr.
    """
    if not tafel.ist_esql:
        assert not tafel.frage, f"{brettname}: FR-27 war zurueckgestellt"
        return
    assert tafel.frage and tafel.ausschluesse
    assert tafel.erlaeuterung.startswith("Frage: ")
    assert "Nicht enthalten:" in tafel.erlaeuterung
    # Jede Kachel nennt **ihre eigenen** Ausschluesse: Was dasteht, muss
    # diese Abfrage auch vollziehen. Ein geteiltes Tupel ueber drei Kacheln
    # liess die Stadtkachel einen Ausschluss fuehren, den sie nicht macht.
    for ausschluss in tafel.ausschluesse:
        assert ausschluss.beleg in tafel.abfrage.esql, (
            f"{brettname}/{tafel.kennung}: '{ausschluss.text[:40]}…' steht "
            f"im Text, '{ausschluss.beleg}' aber nicht in der Abfrage")
    if tafel.zeigt_rate:
        assert tafel.nenner, f"{brettname}/{tafel.kennung}: Rate ohne Nenner"
        assert tafel.jahr == RATENJAHR
        # Der Hinweis, den die Rate fuer 2025 und 2026 braucht: Es gibt
        # kein neueres ACS, der Nenner bleibt der von 2024.
        for spaeter in (RATENJAHR + 1, RATENJAHR + 2):
            assert str(spaeter) in tafel.nenner, (
                f"{tafel.kennung}: der Nenner sagt nicht, was fuer "
                f"{spaeter} gilt")


def test_die_rate_steht_im_dashboard_und_nicht_woanders():
    """Die Beschreibung des Ueberblicks sagte das Gegenteil.

    Bis zum 11.10.2026 stand dort, die Rate je 1'000 Einwohner stehe *„in
    der DuckDB-Auswertung, nicht hier"* - waehrend
    ``test_die_rate_je_1000_einwohner_ist_aus_elasticsearch_allein_rechenbar``
    das Gegenteil zusicherte. Eine der beiden Aussagen musste fallen.
    """
    ueberblick = next(b for b in bk.BRETTER if b.kennung == "crime-ueberblick")
    assert "nicht hier" not in ueberblick.beschreibung
    raten = [b for b in bk.BRETTER if any(t.zeigt_rate for t in b.tafeln)]
    assert len(raten) == 1, "genau ein Brett traegt die Raten"
    assert str(RATENJAHR) in raten[0].beschreibung


@pytest.mark.parametrize("brettname,tafel", ALLE_TAFELN, ids=TAFELNAMEN)
def test_jede_ratenkachel_nennt_die_abweichung_zu_den_dokumenten(brettname,
                                                                 tafel):
    """E5 gehoert dorthin, wo die Zahl steht - nicht nur aufs Brett.

    Das Dashboard stellt die Fallebene voran, die Abgabedokumente fuehren
    die Tatebene. Wer eine Kachel einzeln oeffnet oder ihr Informationsfeld
    liest, sieht die Brettbeschreibung nicht; der Hinweis muss deshalb an
    der Kachel haengen. ``deferred-work.md`` stuetzt sich ausdruecklich
    darauf, dass er dort steht.
    """
    if not tafel.zeigt_rate:
        return
    hinweis = " ".join(tafel.vorbehalte)
    assert "Tatebene" in hinweis and "Fallebene" in hinweis, (
        f"{brettname}/{tafel.kennung}: die Kachel sagt nicht, dass die "
        f"Dokumente die Tatebene fuehren")
    # Und sie sagt **warum**, nicht nur **dass**. Bis zum 11.10.2026 stand
    # dort, beide Masse seien zwei Lesarten derselben Daten - das ist zu
    # freundlich: Chicago erfasst je Fall nur das schwerste Delikt, Detroit
    # jedes (``docs/feldkatalog.md``, ``counts_case``). Ein Vergleich auf der
    # Tatebene misst damit den Erfassungsunterschied mit. Ohne diesen Grund
    # liest sich die Tatebene wie eine gleichwertige zweite Lesart, und genau
    # das ist sie nicht.
    for wort in ("schwerste", "jedes"):
        assert wort in hinweis, (
            f"{brettname}/{tafel.kennung}: der Vorbehalt nennt nicht, dass "
            f"Chicago je Fall nur das schwerste Delikt erfasst und Detroit "
            f"jedes - ohne das steht die Tatebene als gleichwertig daneben")
    # Keine festen Raten im Kacheltext: Eine Zahl, die hier steht, misst
    # beim naechsten Release niemand nach - die Regel steht im Modul selbst.
    assert "133,1" not in tafel.erlaeuterung
    assert "124,6" not in tafel.erlaeuterung


# --------------------------------------------------------------------------
# Das Raster
# --------------------------------------------------------------------------


def test_kachel_um_kachel_ohne_ueberlappung():
    tafeln = tuple(bk.Tafel(f"t{i}", "T", "zahl", ZAEHLEN, breite=24, hoehe=8)
                   for i in range(4))
    gitter = bk.raster(tafeln)
    assert [(g["x"], g["y"]) for g in gitter] == [
        (0, 0), (24, 0), (0, 8), (24, 8)]


def test_die_zeilenhoehe_richtet_sich_nach_der_hoechsten_kachel():
    """Sonst schiebt Kibana ueberlappende Kacheln beim Oeffnen umeinander."""
    tafeln = (bk.Tafel("a", "A", "zahl", ZAEHLEN, breite=24, hoehe=8),
              bk.Tafel("b", "B", "zahl", ZAEHLEN, breite=24, hoehe=20),
              bk.Tafel("c", "C", "zahl", ZAEHLEN, breite=24, hoehe=8))
    assert bk.raster(tafeln)[2]["y"] == 20


def test_keine_kachel_ragt_ueber_das_raster_hinaus():
    for b in bk.BRETTER:
        for platz in bk.raster(b.tafeln):
            assert platz["x"] + platz["w"] <= bk.RASTER, b.kennung


# --------------------------------------------------------------------------
# Die erzeugten Objekte
# --------------------------------------------------------------------------


def test_die_datenansicht_zeigt_auf_den_alias():
    """Nicht auf einen Release-Index - sonst zeigen die Dashboards auf einen
    Stand, den der naechste Ladelauf stehen laesst."""
    ansicht = bk.datenansicht()
    assert ansicht["attributes"]["title"] == "fact_offense"
    assert "2026" not in ansicht["attributes"]["title"]
    assert ansicht["attributes"]["timeFieldName"] == "occurred_at_utc"


def test_jede_tafel_verweist_auf_die_datenansicht():
    for b in bk.BRETTER:
        for tafel in b.tafeln:
            verweise = bk.lens_objekt(tafel, b.kennung)["references"]
            assert [v["id"] for v in verweise] == [bk.ANSICHT]
            assert verweise[0]["name"].endswith(tafel.schicht)


def test_alle_kennungen_sind_eindeutig():
    """Drei Bretter haben je eine Tafel ``gesamt``, zwei davon heissen
    verschieden. Ohne den Brettnamen in der Kennung ueberschrieb das letzte
    Anlegen die anderen, und ein Brett trug den Titel eines fremden."""
    alle = bk.objekte(_mit_fenster())
    kennungen = [(o["type"], o["id"]) for o in alle]
    assert len(kennungen) == len(set(kennungen))


def test_die_verweise_des_dashboards_zeigen_auf_vorhandene_tafeln():
    alle = bk.objekte(_mit_fenster())
    assert bk.pruefe_verweise(None, alle) == []


def test_das_dashboard_haelt_sein_zeitfenster_fest():
    objekt = bk.dashboard_objekt(brett(bk.Tafel("t", "T", "zahl", ZAEHLEN)))
    assert objekt["attributes"]["timeRestore"] is True
    assert objekt["attributes"]["timeFrom"] == FENSTER[0]


def test_die_tafeln_stehen_als_text_im_dashboard():
    objekt = bk.dashboard_objekt(brett(bk.Tafel("t", "Titel", "zahl", ZAEHLEN)))
    tafeln = json.loads(objekt["attributes"]["panelsJSON"])
    assert tafeln[0]["panelRefName"] == "panel_p-t"
    assert objekt["references"][0]["name"] == "p-t:panel_p-t"


def _mit_fenster() -> tuple[bk.Brett, ...]:
    return tuple(bk.Brett(b.kennung, b.titel, b.beschreibung, b.tafeln, FENSTER)
                 for b in bk.BRETTER)


# --------------------------------------------------------------------------
# Gegen die laufenden Dienste
# --------------------------------------------------------------------------
#
#     docker compose up -d
#     python -m serving.load_elasticsearch && python -m serving.build_kibana
#
# Die Tafeln werden in einen eigenen Namensraum gelegt und danach weggeraeumt:
# Ein Test, der in die Kennungen des echten Standes greift, ueberschreibt ihn.

KIBANA = os.environ.get("KIBANA_URL", "http://localhost:15601")
ELASTICSEARCH = os.environ.get("ELASTICSEARCH_URL", "http://localhost:19200")


@pytest.fixture
def kibana():
    klient = bk.HttpKlient(KIBANA)
    try:
        zustand = klient.anfrage("GET", "/api/status")
        if zustand["status"]["overall"]["level"] != "available":
            pytest.skip("Kibana ist noch nicht bereit")
    except Exception:
        pytest.skip(f"kein Kibana unter {KIBANA}")
    angelegt: list[tuple[str, str]] = []
    try:
        yield klient, angelegt
    finally:
        for art, kennung in angelegt:
            try:
                klient.anfrage("DELETE", f"/api/saved_objects/{art}/{kennung}")
            except LadeFehler:
                pass


@pytest.fixture
def elastic():
    klient = le.HttpKlient(ELASTICSEARCH)
    try:
        klient.anfrage("GET", "/fact_offense/_count")
    except Exception:
        pytest.skip(f"kein geladenes fact_offense unter {ELASTICSEARCH}")
    return klient


def test_kibana_nimmt_die_erzeugten_objekte_an(kibana):
    klient, angelegt = kibana
    probe = bk.Brett("probe-brett", "Probe", "", (
        bk.Tafel("zahl", "Delikte", "zahl", ZAEHLEN, breite=24, hoehe=8),
        bk.Tafel("stadt", "Je Stadt", "balken", ZAEHLEN,
                 eimer=(bk.Eimer("s", "Stadt", "terms", "reporting_city", 5),)),
    ), FENSTER)
    alle = [bk.datenansicht()] + [
        bk.lens_objekt(t, probe.kennung) for t in probe.tafeln
    ] + [bk.dashboard_objekt(probe)]
    angelegt.extend((o["type"], o["id"]) for o in alle
                    if o["type"] != "index-pattern")

    ergebnis = bk.lege_an(klient, alle)
    assert ergebnis["dashboards"] == 1

    gelesen = klient.anfrage(
        "GET", f"/api/saved_objects/dashboard/{probe.kennung}")
    assert gelesen["attributes"]["timeRestore"] is True
    assert len(gelesen["references"]) == 2


def test_ein_verweis_ins_leere_wird_abgefangen(kibana):
    """Kibana legt das Dashboard auch dann an - beim Oeffnen steht dann
    *Could not locate that panel*."""
    klient, angelegt = kibana
    kaputt = bk.dashboard_objekt(
        brett(bk.Tafel("fehlt", "Fehlt", "zahl", ZAEHLEN)))
    # Gerade weil Kibana es anlegt, muss es auch wieder weg: Bis zum
    # 6.10.2026 verwarf dieser Test die Aufraeumliste (``klient, _``), und
    # das Brett "Probe" blieb im laufenden Kibana stehen - dort gefunden,
    # neben den drei echten. Dieselbe Sorte Rueckstand wie die 681
    # pruefung-Indizes in Elasticsearch, nur unauffaelliger, weil es eines
    # ist und nicht siebenhundert.
    angelegt.append((kaputt["type"], kaputt["id"]))
    with pytest.raises(LadeFehler, match="ins Leere"):
        bk.lege_an(klient, [bk.datenansicht(), kaputt])


@pytest.mark.parametrize("brettname,tafel", ALLE_TAFELN, ids=TAFELNAMEN)
def test_jede_tafel_bekommt_auch_wirklich_daten(brettname, tafel, elastic):
    """Die Pruefung, die das Bild ersetzt.

    Dieselbe Beschreibung, aus der das Lens-Dokument entsteht, wird hier als
    Elasticsearch-Abfrage gestellt. Kommt nichts zurueck, bleibt die Kachel
    leer - und das faellt hier auf und nicht im Vortrag.

    **Zwei Wege, dieselbe Frage.** Eine Lens-Tafel geht ueber ``_search``
    und ihre Aggregation, eine ES|QL-Tafel ueber ``_query`` und ihre
    Abfrage. Der zweite Zweig prueft dabei mehr als "kommt etwas zurueck":
    Er haelt die Spaltennamen der Antwort gegen die, die die Tafel
    anzeigt - stimmen sie nicht ueberein, importiert die Kachel sauber und
    bleibt leer, weil Lens ueber ``fieldName`` abbildet.
    """
    if tafel.ist_esql:
        antwort = elastic.anfrage(
            "POST", "/_query", {"query": tafel.abfrage.esql})
        assert antwort["values"], f"{tafel.kennung}: keine Zeilen"
        geliefert = [s["name"] for s in antwort["columns"]]
        assert geliefert == tafel.reihenfolge, (
            f"{tafel.kennung}: die Abfrage liefert {geliefert}, die Kachel "
            f"zeigt {tafel.reihenfolge} - Lens bildet ueber den Feldnamen ab")
        return

    antwort = elastic.anfrage("POST", "/fact_offense/_search", tafel.aggregation)
    assert antwort["hits"]["total"]["value"] > 0, f"{tafel.kennung}: keine Zeilen"

    for eimer in tafel.eimer[:1]:
        eimer_liste = antwort["aggregations"][eimer.kennung]["buckets"]
        assert eimer_liste, f"{tafel.kennung}/{eimer.kennung}: keine Gruppen"
        assert any(b["doc_count"] > 0 for b in eimer_liste)

    if (kz := tafel.kennzahl.aggregation) is not None and not tafel.eimer:
        wert = antwort["aggregations"][tafel.kennzahl.kennung]["value"]
        assert wert > 0, f"{tafel.kennung}: {kz} liefert nichts"


def test_das_unterfeld_ist_noetig_und_nicht_vorsorglich(elastic):
    """Haelt die Entscheidung gegen die echte Abbildung im Index.

    Ein ``.keyword`` an einem Feld, das schon ``keyword`` ist, waere falsch -
    und ein fehlendes an einem ``text``-Feld macht die Kachel leer.
    """
    abbildung = elastic.anfrage("GET", "/fact_offense/_mapping")
    felder = next(iter(abbildung.values()))["mappings"]["properties"]
    for b in bk.BRETTER:
        for tafel in b.tafeln:
            for eimer in tafel.eimer:
                art = felder[eimer.feld]["type"]
                assert eimer.unterfeld_keyword == (art == "text"), (
                    f"{b.kennung}/{tafel.kennung}: {eimer.feld} ist {art}")


def test_der_nennerindex_laeuft_wirklich_im_lookup_modus(elastic):
    """Die Zusage aus ``INDIZES`` gegen den laufenden Dienst gehalten.

    ``index.mode`` laesst sich nur beim **Anlegen** setzen. Ein Index, der
    vor dieser Aenderung geladen wurde, steht weiter auf ``standard``, und
    die Rate-Kacheln bleiben leer, ohne dass irgendetwas rot wird - der
    Ladelauf selbst ist ja laengst durch.
    """
    name = le.NACH_NAME["dim_tract_acs"].name
    antwort = elastic.anfrage("GET", f"/{name}/_settings")
    modi = {i: e["settings"]["index"].get("mode") for i, e in antwort.items()}
    assert set(modi.values()) == {"lookup"}, (
        f"{modi} - erst 'python -m serving.load_elasticsearch' neu laufen "
        f"lassen; ein bestehender Index nimmt den Modus nicht mehr an")
