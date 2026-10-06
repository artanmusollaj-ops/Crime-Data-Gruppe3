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

from serving import build_kibana as bk
from serving import load_elasticsearch as le
from serving.load_clickhouse import LadeFehler


ZAEHLEN = bk.Kennzahl("anzahl", "Delikte", "count")
FENSTER = ("2024-01-01T00:00:00.000Z", "2025-01-01T23:59:59.999Z")


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


@pytest.mark.parametrize(
    "tafel", [t for b in bk.BRETTER for t in b.tafeln],
    ids=[f"{b.kennung}-{t.kennung}" for b in bk.BRETTER for t in b.tafeln])
def test_jede_echte_tafel_zeigt_alles_was_sie_traegt(tafel):
    bk.pruefe_tafel(tafel)


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


@pytest.mark.parametrize(
    "tafel", [t for b in bk.BRETTER for t in b.tafeln],
    ids=[f"{b.kennung}-{t.kennung}" for b in bk.BRETTER for t in b.tafeln])
def test_jede_tafel_bekommt_auch_wirklich_daten(tafel, elastic):
    """Die Pruefung, die das Bild ersetzt.

    Dieselbe Beschreibung, aus der das Lens-Dokument entsteht, wird hier als
    Elasticsearch-Abfrage gestellt. Kommt nichts zurueck, bleibt die Kachel
    leer - und das faellt hier auf und nicht im Vortrag.
    """
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
