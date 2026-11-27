"""Jupyter nimmt eine gueltige Access-Marke als Anmeldung, sonst das Token.

Seit dem 27.11.2026 (serving.jupyter_zugang). Die Marken hier sind echt
signiert, mit einem Schluessel, den der Test selbst erzeugt; geprueft wird
also die Signatur und nicht nur, dass ein Kopf da ist.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from serving import jupyter_zugang as jz

AUSSTELLER = "https://homeinegg.cloudflareaccess.com"
ZIELGRUPPE = "7b915eae-probe"
SERVERKONFIG = Path(__file__).resolve().parents[2] / "docker" / "jupyter_server_config.py"


@pytest.fixture(scope="module")
def schluessel():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def fremder_schluessel():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def pruefe(schluessel):
    return jz.pruefer(AUSSTELLER, ZIELGRUPPE,
                      schluessel_fuer=lambda roh: schluessel.public_key())


def marke(schluessel, **aenderung) -> str:
    jetzt = int(time.time())
    angaben = {"iss": AUSSTELLER, "aud": [ZIELGRUPPE], "sub": "1234-abcd",
               "email": "pruefende@example.org", "iat": jetzt, "exp": jetzt + 600}
    angaben.update(aenderung)
    angaben = {k: v for k, v in angaben.items() if v is not None}
    return jwt.encode(angaben, schluessel, algorithm="RS256")


def test_eine_gueltige_marke_meldet_die_person_an(schluessel, pruefe):
    wer = jz.identitaet({jz.KOPF: marke(schluessel)}, pruefe)
    assert wer == {"username": "pruefende@example.org", "name": "pruefende@example.org",
                   "display_name": "pruefende@example.org"}


def test_ohne_email_gilt_das_subjekt(schluessel, pruefe):
    assert jz.identitaet({jz.KOPF: marke(schluessel, email=None)}, pruefe)["username"] == "1234-abcd"


def test_ohne_kopf_ist_niemand_ueber_access_angemeldet(pruefe):
    assert jz.identitaet({}, pruefe) is None
    assert jz.identitaet({jz.KOPF: ""}, pruefe) is None


@pytest.mark.parametrize("fall", [
    "fremd_signiert", "abgelaufen", "fremde_zielgruppe", "fremder_aussteller",
    "ohne_ablauf", "ohne_subjekt", "unsigniert", "kein_jwt",
])
def test_eine_falsche_marke_ist_keine_anmeldung(fall, schluessel, fremder_schluessel, pruefe):
    roh = {
        "fremd_signiert": lambda: marke(fremder_schluessel),
        "abgelaufen": lambda: marke(schluessel, iat=int(time.time()) - 7200,
                                    exp=int(time.time()) - 3600),
        "fremde_zielgruppe": lambda: marke(schluessel, aud=["andere-anwendung"]),
        "fremder_aussteller": lambda: marke(schluessel, iss="https://boese.cloudflareaccess.com"),
        "ohne_ablauf": lambda: marke(schluessel, exp=None),
        "ohne_subjekt": lambda: marke(schluessel, sub=None),
        "unsigniert": lambda: jwt.encode({"iss": AUSSTELLER, "aud": ZIELGRUPPE, "sub": "x",
                                          "iat": int(time.time()),
                                          "exp": int(time.time()) + 600}, None,
                                         algorithm="none"),
        "kein_jwt": lambda: "kein.jwt.wert",
    }[fall]()
    assert jz.identitaet({jz.KOPF: roh}, pruefe) is None


@pytest.mark.parametrize("aussteller", [
    "http://homeinegg.cloudflareaccess.com", "https://beispiel.org",
    "https://homeinegg.cloudflareaccess.com/pfad", "https://homeinegg.cloudflareaccess.com:8443",
    "https://homeinegg.cloudflareaccess.com?x=1", "",
])
def test_nur_die_https_teamdomain_ist_ein_aussteller(aussteller):
    with pytest.raises(jz.ZugangsFehler):
        jz.pruefer(aussteller, ZIELGRUPPE, schluessel_fuer=lambda roh: None)


def test_ohne_zielgruppe_gibt_es_keinen_pruefer():
    with pytest.raises(jz.ZugangsFehler):
        jz.pruefer(AUSSTELLER, " ", schluessel_fuer=lambda roh: None)


@pytest.mark.parametrize("umgebung, erwartet", [
    ({"CF_ACCESS_ISSUER": AUSSTELLER, "CF_ACCESS_AUD": ZIELGRUPPE}, True),
    ({"CF_ACCESS_ISSUER": AUSSTELLER}, False),
    ({"CF_ACCESS_AUD": ZIELGRUPPE}, False),
    ({"CF_ACCESS_ISSUER": " ", "CF_ACCESS_AUD": ZIELGRUPPE}, False),
    ({}, False),
])
def test_eingerichtet_nur_mit_aussteller_und_zielgruppe(umgebung, erwartet):
    assert jz.eingerichtet(umgebung) is erwartet


# -- Die Klasse fuer jupyter_server, mit einer Attrappe als Grundlage ---------

class _Grundlage:
    """Steht fuer jupyter_servers IdentityProvider: die Token-Anmeldung."""

    def __init__(self, token_nutzer=None, asynchron=False):
        self.token_nutzer, self.asynchron = token_nutzer, asynchron

    def get_user(self, handler):
        if self.asynchron:
            async def spaeter():
                return self.token_nutzer
            return spaeter()
        return self.token_nutzer


class _Nutzer(SimpleNamespace):
    pass


def _anfrage(kopf=None):
    return SimpleNamespace(request=SimpleNamespace(headers=kopf or {}))


@pytest.mark.parametrize("asynchron", [False, True])
def test_die_klasse_nimmt_erst_die_marke_dann_das_token(schluessel, pruefe, asynchron):
    klasse = jz.identitaetsklasse(basis=_Grundlage, nutzer=_Nutzer, pruefe=pruefe)
    ohne_token = klasse(token_nutzer=None, asynchron=asynchron)
    mit_token = klasse(token_nutzer="token-nutzer", asynchron=asynchron)

    ueber_access = asyncio.run(ohne_token.get_user(_anfrage({jz.KOPF: marke(schluessel)})))
    assert ueber_access.username == "pruefende@example.org"
    assert asyncio.run(ohne_token.get_user(_anfrage())) is None
    assert asyncio.run(mit_token.get_user(_anfrage())) == "token-nutzer"
    # Eine falsche Marke ist keine Anmeldung, das Token gilt trotzdem.
    falsch = _anfrage({jz.KOPF: marke(schluessel, aud=["andere"])})
    assert asyncio.run(ohne_token.get_user(falsch)) is None
    assert asyncio.run(mit_token.get_user(falsch)) == "token-nutzer"


# -- Die Konfiguration im Abbild ------------------------------------------------

def _lade_konfig(monkeypatch, umgebung):
    for name in ("CF_ACCESS_ISSUER", "CF_ACCESS_AUD"):
        monkeypatch.delenv(name, raising=False)
    for name, wert in umgebung.items():
        monkeypatch.setenv(name, wert)
    monkeypatch.setattr(jz, "identitaetsklasse", lambda: "AccessIdentityProvider")

    class _Abschnitt(SimpleNamespace):
        def __getattr__(self, name):
            wert = _Abschnitt()
            setattr(self, name, wert)
            return wert

    c = _Abschnitt()
    exec(compile(SERVERKONFIG.read_text(encoding="utf-8"), str(SERVERKONFIG), "exec"),
         {"get_config": lambda: c, "__name__": "jupyter_server_config"})
    return c


def test_das_abbild_setzt_den_baustein_ein_wenn_access_eingerichtet_ist(monkeypatch):
    c = _lade_konfig(monkeypatch, {"CF_ACCESS_ISSUER": AUSSTELLER, "CF_ACCESS_AUD": ZIELGRUPPE})
    assert c.ServerApp.identity_provider_class == "AccessIdentityProvider"


def test_ohne_access_bleibt_es_beim_token(monkeypatch):
    c = _lade_konfig(monkeypatch, {})
    assert "identity_provider_class" not in vars(c.ServerApp)


def test_der_verbund_gibt_jupyter_aussteller_und_zielgruppe_mit():
    import yaml
    verbund = yaml.safe_load((SERVERKONFIG.parents[1] / "docker-compose.srv01.yml")
                             .read_text(encoding="utf-8"))
    umgebung = verbund["services"]["jupyter"]["environment"]
    assert {"CF_ACCESS_ISSUER", "CF_ACCESS_AUD", "JUPYTER_TOKEN"} <= set(umgebung)
    # Ohne Wert: Sie kommen aus der .env des Stapels, wie bei admin.
    assert all(umgebung[n] is None for n in ("CF_ACCESS_ISSUER", "CF_ACCESS_AUD"))
