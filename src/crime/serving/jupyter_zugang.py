"""Jupyter vertraut der Anmeldung bei Cloudflare Access.

Bis zum 27.11.2026 verlangte der Notebook-Server nach der Anmeldung bei
Access zusaetzlich sein Token. Fuer die Pruefenden hiess das: anmelden, dann
ein 64 Zeichen langes Geheimnis aus einer Datei auf dem Server abtippen, das
sie nicht sehen koennen. Jetzt gilt: Wer mit einer **gueltigen, signierten**
Access-Marke kommt, ist angemeldet, als die E-Mail-Adresse darin.

Was das nicht lockert:

* Geprueft wird die Marke selbst, nicht nur, dass ein Kopf da ist: Signatur
  gegen die oeffentlichen Schluessel des Teams, Aussteller, Zielgruppe
  (``aud`` der Access-Anwendung ueber ``urbancrime-*``) und Ablauf. Wer am
  Tunnel vorbei direkt auf den Container kaeme, kann den Kopf setzen, aber
  keine Marke unterschreiben.
* Ohne gueltige Marke gilt weiter das Token. Der Zugang ueber einen
  ``ssh``-Tunnel und der Weg ohne Access bleiben, wie sie waren.
* Ohne ``CF_ACCESS_ISSUER`` und ``CF_ACCESS_AUD`` in der Umgebung bleibt alles
  beim Token; ``docker/jupyter_server_config.py`` setzt den Baustein dann gar
  nicht ein.

Dieselbe Pruefung macht die Engineering-Konsole
(``platform_admin.auth``); sie ist hier nachgebaut und nicht importiert, damit
das Analyse-Abbild nicht am Code der Konsole haengt.

Quellen: Cloudflare, "Validate JWTs"
(https://developers.cloudflare.com/cloudflare-one/access-controls/applications/http-apps/authorization-cookie/validating-json/)
fuer Kopf ``Cf-Access-Jwt-Assertion``, Schluesseladresse ``/cdn-cgi/access/certs``
und die zu pruefenden Felder; jupyter_server, "Identity Providers"
(https://jupyter-server.readthedocs.io/en/latest/operators/security.html#identity-providers)
fuer ``ServerApp.identity_provider_class`` und ``IdentityProvider.get_user``.
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

#: Der Kopf, in dem Cloudflare Access die Marke an den Dienst weiterreicht.
KOPF = "Cf-Access-Jwt-Assertion"

_log = logging.getLogger(__name__)


class ZugangsFehler(ValueError):
    """Die Einstellungen fuer Access sind unvollstaendig oder falsch."""


def aussteller_pruefen(aussteller: str) -> str:
    """Die Teamdomain, ohne Schraegstrich am Ende; sonst ZugangsFehler.

    Dieselbe Regel wie in der Konsole: nur ``https://<team>.cloudflareaccess.com``,
    ohne Pfad, Port, Abfrage oder Fragment. Ein anderer Aussteller hiesse,
    Schluessel von einer fremden Adresse zu laden und ihnen zu glauben.
    """
    aussteller = (aussteller or "").strip().rstrip("/")
    url = urlsplit(aussteller)
    if (url.scheme != "https" or not url.hostname
            or not url.hostname.endswith(".cloudflareaccess.com")
            or url.path or url.query or url.fragment or url.port):
        raise ZugangsFehler("CF_ACCESS_ISSUER muss die HTTPS-Teamdomain sein")
    return aussteller


def eingerichtet(umgebung: Mapping[str, str] | None = None) -> bool:
    """Sind Aussteller und Zielgruppe gesetzt? Dann gilt die Access-Anmeldung."""
    umgebung = os.environ if umgebung is None else umgebung
    return bool((umgebung.get("CF_ACCESS_ISSUER") or "").strip()
                and (umgebung.get("CF_ACCESS_AUD") or "").strip())


def pruefer(aussteller: str, zielgruppe: str,
            schluessel_fuer: Callable[[str], Any] | None = None
            ) -> Callable[[str], dict]:
    """Eine Funktion, die eine Marke prueft und ihre Angaben liefert.

    ``schluessel_fuer`` nimmt die rohe Marke und gibt den Schluessel, mit dem
    sie signiert ist. Vorgabe: die Schluessel des Teams, von
    ``<aussteller>/cdn-cgi/access/certs`` geholt und zwischengespeichert
    (``jwt.PyJWKClient``). Tests geben ihren eigenen.
    """
    import jwt

    aussteller = aussteller_pruefen(aussteller)
    zielgruppe = (zielgruppe or "").strip()
    if not zielgruppe:
        raise ZugangsFehler("CF_ACCESS_AUD fehlt")
    if schluessel_fuer is None:
        client = jwt.PyJWKClient(aussteller + "/cdn-cgi/access/certs", timeout=10)

        def schluessel_fuer(roh: str):
            return client.get_signing_key_from_jwt(roh).key

    def pruefe(roh: str) -> dict:
        angaben = jwt.decode(
            roh, schluessel_fuer(roh), algorithms=["RS256"],
            issuer=aussteller, audience=zielgruppe,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
        if not isinstance(angaben.get("sub"), str) or not angaben["sub"]:
            raise jwt.InvalidTokenError("sub fehlt")
        return angaben

    return pruefe


def identitaet(kopfzeilen: Mapping[str, str],
               pruefe: Callable[[str], dict]) -> dict | None:
    """Wer die Anfrage stellt, laut Access-Marke - oder None.

    None heisst nur: nicht ueber Access angemeldet. Was dann gilt, entscheidet
    der Aufrufer (hier: das Token). Eine ungueltige Marke wird protokolliert,
    aber nie als Anmeldung genommen.
    """
    roh = kopfzeilen.get(KOPF) or ""
    if not roh:
        return None
    try:
        angaben = pruefe(roh)
    except Exception as fehler:  # jede Ablehnung ist dieselbe: keine Anmeldung
        _log.warning("Access-Marke abgelehnt: %s", type(fehler).__name__)
        return None
    name = angaben.get("email") or angaben["sub"]
    return {"username": name, "name": name, "display_name": name}


def identitaetsklasse(basis: type | None = None, nutzer: type | None = None,
                      pruefe: Callable[[str], dict] | None = None,
                      umgebung: Mapping[str, str] | None = None) -> type:
    """Die Klasse fuer ``ServerApp.identity_provider_class``.

    Gebaut erst hier und nicht beim Import, weil ``jupyter_server`` nur im
    Analyse-Abbild liegt; die Strecke und die Tests kommen ohne aus. Tests
    geben ``basis``, ``nutzer`` und ``pruefe`` selbst.
    """
    if basis is None or nutzer is None:
        from jupyter_server.auth.identity import IdentityProvider, User
        basis, nutzer = basis or IdentityProvider, nutzer or User
    if pruefe is None:
        umgebung = os.environ if umgebung is None else umgebung
        pruefe = pruefer(umgebung.get("CF_ACCESS_ISSUER", ""),
                         umgebung.get("CF_ACCESS_AUD", ""))

    class AccessIdentityProvider(basis):
        """Erst die Access-Marke, dann wie bisher das Token."""

        async def get_user(self, handler):
            gefunden = identitaet(handler.request.headers, pruefe)
            if gefunden is not None:
                return nutzer(**gefunden)
            ergebnis = super().get_user(handler)
            if inspect.isawaitable(ergebnis):
                ergebnis = await ergebnis
            return ergebnis

    return AccessIdentityProvider
