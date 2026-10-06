"""Die Adressen der drei Dienste kommen aus der Umgebung (FR-14).

Bis zum 6.10.2026 standen ``localhost:18123``, ``:19200`` und ``:15601`` als
Konstanten im Code und waren **nur** per Kommandozeile zu uebersteuern. Das
genuegte, solange ein Mensch sie tippt. Im Verbund heisst Elasticsearch
``http://elasticsearch:9200``, und ein Container tippt nichts.

Drei Zusagen, fuer jeden der drei Lader dieselben:

* ohne alles gilt die Konstante - der Entwicklungsrechner aendert sich nicht,
* die Umgebung ersetzt sie,
* ein getipptes ``--url`` sticht die Umgebung.

Die Vorgabe wird dabei **beim Aufruf** gelesen und nicht beim Import. Wuerde
sie beim Import gelesen, saehe sie die Umgebung des Interpreterstarts - und
``monkeypatch.setenv`` in diesem Modul waere ohne Wirkung, ohne dass ein Test
davon rot wuerde.
"""

from __future__ import annotations

import pytest

from serving import build_kibana as bk
from serving import load_clickhouse as ch
from serving import load_elasticsearch as es
from serving import pruefe_stand as ps


#: Modul, Variablenname und die Adresse, die ohne Umgebung gilt.
LADER = [
    pytest.param(ch, "CLICKHOUSE_URL", id="clickhouse"),
    pytest.param(es, "ELASTICSEARCH_URL", id="elasticsearch"),
    pytest.param(bk, "KIBANA_URL", id="kibana"),
]


@pytest.mark.parametrize("modul, variable", LADER)
def test_der_name_der_variablen_steht_im_modul(modul, variable):
    """Sie heisst nach dem Dienst - und der Name ist Teil der Schnittstelle."""
    assert modul.UMGEBUNGSVARIABLE == variable


@pytest.mark.parametrize("modul, variable", LADER)
def test_ohne_umgebung_gilt_die_konstante(modul, variable):
    """Wer lokal arbeitet, merkt von der Aenderung nichts."""
    assert modul.vorgabe_url({}) == modul.STANDARD_URL
    assert modul.vorgabe_url({variable: ""}) == modul.STANDARD_URL
    assert modul.vorgabe_url({variable: "   "}) == modul.STANDARD_URL


@pytest.mark.parametrize("modul, variable", LADER)
def test_die_umgebung_ersetzt_sie(modul, variable):
    assert modul.vorgabe_url({variable: "http://dienst:9999"}) == "http://dienst:9999"


@pytest.mark.parametrize("modul, variable", LADER)
def test_die_vorgabe_wird_beim_aufruf_gelesen(modul, variable, monkeypatch):
    """Nicht beim Import - sonst waere die Variable im Container wirkungslos."""
    monkeypatch.setenv(variable, "http://aus-der-umgebung:1234")
    assert modul.kommandozeile().parse_args([]).url == "http://aus-der-umgebung:1234"


@pytest.mark.parametrize("modul, variable", LADER)
def test_ein_getipptes_url_sticht_die_umgebung(modul, variable, monkeypatch):
    """Die Reihenfolge, die der Plan verlangt: CLI vor Umgebung vor Konstante."""
    monkeypatch.setenv(variable, "http://aus-der-umgebung:1234")
    gewaehlt = modul.kommandozeile().parse_args(["--url", "http://getippt:5678"]).url
    assert gewaehlt == "http://getippt:5678"


def test_die_pruefung_liest_dieselben_vorgaben_wie_die_lader():
    """Sonst beschickt man die Dienste an einer Adresse und prueft sie an einer anderen.

    ``serving.pruefe_stand`` fragt alle drei Orte, ob sie noch dasselbe
    zeigen. Haette es eigene Vorgaben, waere sein Befund im Verbund
    regelmaessig "nicht erreichbar" - und das sieht wie ein Ausfall aus, nicht
    wie ein falsch verdrahteter Bericht.
    """
    assert ps.clickhouse_vorgabe is ch.vorgabe_url
    assert ps.elasticsearch_vorgabe is es.vorgabe_url
    assert ps.kibana_vorgabe is bk.vorgabe_url


def test_die_pruefung_nimmt_die_umgebung_und_laesst_sich_uebersteuern(monkeypatch):
    """Dieselbe Reihenfolge wie bei den Ladern, an allen drei Adressen."""
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://aus-der-umgebung:1234")
    monkeypatch.setenv("KIBANA_URL", "http://kibana:5601")
    zerleger = ps.kommandozeile()
    ohne = zerleger.parse_args([])
    assert ohne.elasticsearch == "http://aus-der-umgebung:1234"
    assert ohne.kibana == "http://kibana:5601"
    assert ohne.clickhouse == ch.STANDARD_URL, "ohne Variable bleibt die Konstante"
    getippt = zerleger.parse_args(["--elasticsearch", "http://getippt:5678"])
    assert getippt.elasticsearch == "http://getippt:5678"
