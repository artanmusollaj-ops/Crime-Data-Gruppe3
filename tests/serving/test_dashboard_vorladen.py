"""Das Dashboard baut seinen Bestand beim Start auf und laedt im Hintergrund nach.

Auf ``srv01`` gemessen am 27.11.2026: Der erste Aufruf nach einem Start baute
den Bestand und wartete 20,4 s, jeder Aufruf danach 0,1 s oder weniger. Die
Anfrage, die ein neues Release bemerkte, wartete genauso lange. Seither baut
``create_app(vorladen=True)`` beim Start vor, und ``Bestand.beobachten``
laedt neue Releases im Hintergrund nach.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
import yaml

import serving.dashboard as d
import serving.dashboard.app as app_modul
from serving.dashboard import Bestand
from serving.dashboard.app import create_app, vorladen_vorgabe
from test_dashboard import PROJEKT, RELEASE, TRACT_C, TRACT_D, freigeben, jahr, stern


def _warte(bedingung, sekunden=30.0):
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        if bedingung():
            return True
        time.sleep(0.02)
    return False


class _Attrappe:
    """Steht fuer Bestand: zaehlt, wie oft er gebaut, geprueft und beobachtet wird."""

    gebaut: list = []

    def __init__(self, wurzel):
        time.sleep(0.2)
        _Attrappe.gebaut.append(wurzel)
        self.geprueft = 0
        self.beobachtet = 0

    def beobachten(self, halt=None):
        self.beobachtet += 1

    def aktuell(self):
        self.geprueft += 1

    def optionen(self):
        return {"stand": {"release": "probe"}}


@pytest.fixture
def attrappe(monkeypatch):
    _Attrappe.gebaut = []
    monkeypatch.setattr(app_modul, "Bestand", _Attrappe)
    return _Attrappe


def test_mit_vorladen_steht_der_bestand_vor_der_ersten_anfrage(tmp_path, attrappe):
    client = create_app(tmp_path, vorladen=True).test_client()
    assert _warte(lambda: client.get("/healthz").json["bestand"])
    assert len(attrappe.gebaut) == 1
    assert client.get("/api/optionen").status_code == 200
    assert len(attrappe.gebaut) == 1, "die erste Anfrage baute den Bestand noch einmal"


def test_eine_anfrage_waehrend_des_vorladens_wartet_auf_dasselbe(tmp_path, attrappe):
    client = create_app(tmp_path, vorladen=True).test_client()
    antworten = [client.get("/api/optionen").status_code for _ in range(3)]
    assert antworten == [200] * 3
    assert len(attrappe.gebaut) == 1


def test_ohne_vorladen_laedt_erst_die_erste_anfrage(tmp_path, attrappe):
    client = create_app(tmp_path, vorladen=False).test_client()
    time.sleep(0.4)
    assert attrappe.gebaut == []
    assert client.get("/healthz").json == {"status": "ok", "bestand": False}
    assert client.get("/api/optionen").status_code == 200
    assert len(attrappe.gebaut) == 1


def test_anfragen_pruefen_nicht_selbst_auf_ein_neues_release(tmp_path, monkeypatch):
    instanzen = []

    class Zaehlend(_Attrappe):
        def __init__(self, wurzel):
            super().__init__(wurzel)
            instanzen.append(self)

    monkeypatch.setattr(app_modul, "Bestand", Zaehlend)
    client = create_app(tmp_path).test_client()
    for _ in range(5):
        assert client.get("/api/optionen").status_code == 200
    assert len(instanzen) == 1
    assert instanzen[0].geprueft == 0, "eine Anfrage hat selbst nachgeladen"
    assert instanzen[0].beobachtet == 1


def test_ein_eingeschobener_bestand_wird_weder_vorgeladen_noch_beobachtet(tmp_path, attrappe):
    eigener = _Attrappe(tmp_path)
    attrappe.gebaut.clear()
    client = create_app(bestand=eigener, vorladen=True).test_client()
    assert client.get("/api/optionen").status_code == 200
    assert attrappe.gebaut == [] and eigener.beobachtet == 0


def test_scheitert_das_vorladen_versucht_es_die_erste_anfrage(tmp_path):
    """Ohne Release meldet die API 503 wie bisher, und /healthz bleibt gruen."""
    client = create_app(tmp_path, vorladen=True).test_client()
    time.sleep(0.3)
    assert client.get("/healthz").status_code == 200
    antwort = client.get("/api/optionen")
    assert antwort.status_code == 503 and "AKTUELL.json" in antwort.json["fehler"]


@pytest.mark.parametrize("wert, erwartet", [
    ("1", True), ("true", True), ("ja", True), (" JA ", True),
    ("0", False), ("", False), (None, False),
])
def test_vorladen_kommt_aus_der_umgebung(monkeypatch, wert, erwartet):
    monkeypatch.delenv("DASHBOARD_VORLADEN", raising=False)
    if wert is not None:
        monkeypatch.setenv("DASHBOARD_VORLADEN", wert)
    assert vorladen_vorgabe() is erwartet


def test_der_verbund_laedt_vor():
    verbund = yaml.safe_load((PROJEKT / "docker-compose.srv01.yml").read_text(encoding="utf-8"))
    assert verbund["services"]["dashboard"]["environment"]["DASHBOARD_VORLADEN"] == "1"


# -- Nachladen im Hintergrund, am echten Bestand --------------------------------

@pytest.fixture
def echter(tmp_path) -> Bestand:
    stern(tmp_path, jahr("chicago", 2024, "13A", TRACT_C) + jahr("detroit", 2024, "13A", TRACT_D))
    return Bestand(tmp_path)


def _neues_release(bestand: Bestand, kennung: str) -> None:
    ziel = bestand.data_root / "serving" / "dataset=comparison_month" / "manifest.json"
    m = json.loads(ziel.read_text(encoding="utf-8"))
    m["built_at_utc"] = "2026-11-27T00:00:00+00:00"
    ziel.write_text(json.dumps(m), encoding="utf-8")
    freigeben(bestand.data_root, kennung)


def test_ein_neues_release_kommt_ohne_anfrage(echter, monkeypatch):
    monkeypatch.setattr(d, "PRUEFABSTAND_S", 0.05)
    halt = threading.Event()
    faden = echter.beobachten(halt)
    try:
        assert echter.stand["release"] == RELEASE
        _neues_release(echter, "2026-11-27T06-00-00Z")
        assert _warte(lambda: echter.stand["release"] == "2026-11-27T06-00-00Z")
    finally:
        halt.set()
        faden.join(timeout=10)
    assert not faden.is_alive()


def test_waehrend_des_nachladens_antwortet_der_alte_bestand(echter, monkeypatch):
    monkeypatch.setattr(d, "PRUEFABSTAND_S", 0.05)
    echt = Bestand._lade
    im_aufbau, weiter = threading.Event(), threading.Event()

    def gebremst(self):
        if getattr(self, "_con", None) is not None:  # nur das Nachladen bremsen
            im_aufbau.set()
            weiter.wait(10)
        echt(self)

    monkeypatch.setattr(Bestand, "_lade", gebremst)
    halt = threading.Event()
    faden = echter.beobachten(halt)
    try:
        _neues_release(echter, "2026-11-27T06-00-00Z")
        assert im_aufbau.wait(10)
        client = create_app(bestand=echter).test_client()
        antwort = client.get("/api/optionen")
        assert antwort.status_code == 200 and antwort.json["stand"]["release"] == RELEASE
        weiter.set()
        assert _warte(lambda: echter.stand["release"] == "2026-11-27T06-00-00Z")
    finally:
        weiter.set()
        halt.set()
        faden.join(timeout=10)


def test_ein_fehler_beim_nachladen_haelt_den_faden_nicht_an(echter, monkeypatch):
    monkeypatch.setattr(d, "PRUEFABSTAND_S", 0.02)
    versuche = []
    echt = Bestand.aktuell

    def erst_kaputt(self):
        versuche.append(1)
        if len(versuche) == 1:
            raise OSError("Eimer kurz weg")
        echt(self)

    monkeypatch.setattr(Bestand, "aktuell", erst_kaputt)
    halt = threading.Event()
    faden = echter.beobachten(halt)
    try:
        assert _warte(lambda: len(versuche) >= 3)
        assert faden.is_alive()
        assert echter.stand["release"] == RELEASE
    finally:
        halt.set()
        faden.join(timeout=10)
