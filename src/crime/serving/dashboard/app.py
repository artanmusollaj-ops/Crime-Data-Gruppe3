"""Der Webteil des Dashboards: eine Seite, zwei Abfragen, keine Anmeldung.

Die Anmeldung uebernimmt auf ``srv01`` Cloudflare Access vor Traefik, wie fuer
alles unter ``urbancrime-*``. Das Dashboard schreibt nichts und liest nur den
Bestand; eine eigene Pruefung haette nichts zu schuetzen, was die Access-
Anwendung nicht schon schuetzt.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from serving.dashboard import Bestand, EingabeFehler
from storage import for_root

_STATISCH = Path(__file__).parent / "static"
#: Woher die Hintergrundkacheln kommen; ``static/karte.js`` laedt von dort.
KACHELHOST = "https://tile.openstreetmap.org"

_log = logging.getLogger(__name__)


def vorladen_vorgabe() -> bool:
    """``DASHBOARD_VORLADEN`` aus der Umgebung; der Verbund auf srv01 setzt es."""
    return (os.getenv("DASHBOARD_VORLADEN") or "").strip().lower() in {"1", "true", "ja"}


def create_app(data_root: Path | str | None = None, *, bestand: Bestand | None = None,
               vorladen: bool | None = None) -> Flask:
    """Die App. Mit ``vorladen`` baut sie den Bestand gleich im Hintergrund auf.

    Ohne Vorladen baute die erste Anfrage nach einem Start den Bestand und
    wartete rund 20 Sekunden (auf ``srv01`` gemessen am 27.11.2026). Wer
    danach kam, merkte nichts. Mit Vorladen beginnt der Aufbau beim Start.
    Nur wer in den ersten Sekunden kommt, wartet noch, und zwar auf denselben
    Aufbau statt auf einen eigenen. Ein eingeschobener ``bestand`` (Tests)
    laedt nie vor und wird nicht beobachtet.
    """
    app = Flask(__name__, static_folder=None)
    wurzel = for_root(data_root or os.getenv("DASHBOARD_DATA_ROOT")).local_root
    zustand = {"bestand": bestand}
    sperre = threading.Lock()

    def daten() -> Bestand:
        # Unter der Sperre, weil gunicorn mit vier Threads laeuft: Ohne sie
        # luden die ersten gleichzeitigen Anfragen den Bestand mehrfach
        # nebeneinander. Laeuft das Vorladen noch, wartet die Anfrage hier
        # auf dessen Ergebnis. Neue Releases laedt Bestand.beobachten im
        # Hintergrund nach; keine Anfrage prueft mehr selbst.
        with sperre:
            if zustand["bestand"] is None:
                zustand["bestand"] = Bestand(wurzel)
                zustand["bestand"].beobachten()
            return zustand["bestand"]

    def vorlade() -> None:
        try:
            daten()
        except Exception:  # dann laedt die erste Anfrage, wie vor dem 27.11.2026
            _log.exception("Dashboard: Vorladen gescheitert")

    if bestand is None and (vorladen_vorgabe() if vorladen is None else vorladen):
        threading.Thread(target=vorlade, name="dashboard-vorladen", daemon=True).start()

    @app.after_request
    def kopfzeilen(antwort):
        antwort.headers.update({
            "X-Content-Type-Options": "nosniff",
            # Bilder auch von OpenStreetMap: die Hintergrundkacheln der Karten
            # (static/karte.js). Skripte, Stile und Abrufe bleiben bei 'self'.
            "Content-Security-Policy": ("default-src 'self'; "
                                        f"img-src 'self' {KACHELHOST}; frame-ancestors 'none'"),
            # Nur der Ursprung, nie Pfad oder Auswahl: Die Kachelserver von
            # OpenStreetMap verlangen einen Referer (static/karte.js).
            "Referrer-Policy": "strict-origin",
        })
        if request.path.startswith("/api/"):
            antwort.headers["Cache-Control"] = "no-store"
        return antwort

    @app.errorhandler(EingabeFehler)
    def eingabefehler(fehler):
        return jsonify({"fehler": str(fehler)}), 400

    @app.errorhandler(FileNotFoundError)
    def fehlt(fehler):
        return jsonify({"fehler": str(fehler)}), 503

    @app.get("/healthz")
    def gesund():
        # Gesund auch waehrend des Ladens: Der Dienst steht, und eine Anfrage
        # wartete nur. Ob der Bestand schon da ist, steht daneben.
        return jsonify({"status": "ok", "bestand": zustand["bestand"] is not None})

    @app.get("/")
    def seite():
        return send_from_directory(_STATISCH, "index.html")

    @app.get("/zeitverlauf")
    def seite_zeitverlauf():
        return send_from_directory(_STATISCH, "zeitverlauf.html")

    @app.get("/geografie")
    def seite_geografie():
        return send_from_directory(_STATISCH, "geografie.html")

    @app.get("/deliktstruktur")
    def seite_deliktstruktur():
        return send_from_directory(_STATISCH, "deliktstruktur.html")

    @app.get("/datenqualitaet")
    def seite_datenqualitaet():
        return send_from_directory(_STATISCH, "datenqualitaet.html")

    @app.get("/sozial")
    def seite_sozial():
        return send_from_directory(_STATISCH, "sozial.html")

    @app.get("/wetter")
    def seite_wetter():
        return send_from_directory(_STATISCH, "wetter.html")

    @app.get("/quellbewegung")
    def seite_quellbewegung():
        return send_from_directory(_STATISCH, "quellbewegung.html")

    @app.get("/static/<path:name>")
    def statisch(name):
        return send_from_directory(_STATISCH, name)

    @app.get("/api/optionen")
    def optionen():
        return jsonify(daten().optionen())

    @app.get("/api/ueberblick")
    def ueberblick():
        bestand = daten()
        return jsonify(bestand.ueberblick(bestand.auswahl(request.args.to_dict(), "ueberblick")))

    @app.get("/api/zeitverlauf")
    def zeitverlauf():
        bestand = daten()
        return jsonify(bestand.zeitverlauf(bestand.auswahl(request.args.to_dict(), "zeitverlauf")))

    @app.get("/api/karten")
    def karten():
        # Die Umrisse aendern sich nur mit dem Bestand; der Browser holt sie
        # einmal je Seite, die Raten bei jeder Auswahl. ``raum=bezirk`` gibt
        # die Polizeibezirke, ``{}`` bei einem Release ohne sie.
        bestand = daten()
        if request.args.get("raum") == "bezirk":
            return jsonify(bestand.karten_bezirke or {})
        if request.args.get("raum") == "stadtteil":
            return jsonify(bestand.karten_stadtteile or {})
        return jsonify(bestand.karten)

    @app.get("/api/geografie")
    def geografie():
        bestand = daten()
        werte = request.args.to_dict()
        return jsonify(bestand.geografie(bestand.auswahl(werte, "geografie"),
                                         werte.get("ansicht"), raum=werte.get("raum"),
                                         kennzahl=werte.get("kennzahl")))

    @app.get("/api/deliktstruktur")
    def deliktstruktur():
        bestand = daten()
        return jsonify(bestand.deliktstruktur(bestand.auswahl(request.args.to_dict(), "deliktstruktur")))

    @app.get("/api/datenqualitaet")
    def datenqualitaet():
        bestand = daten()
        antwort = bestand.datenqualitaet(bestand.auswahl(request.args.to_dict(), "datenqualitaet"))
        # Der Weg zu den Nachweisen, wenn die Konsole erreichbar ist.
        antwort["konsole"] = os.getenv("DASHBOARD_KONSOLE_URL") or None
        return jsonify(antwort)

    @app.get("/api/sozial")
    def sozialdaten():
        return jsonify(daten().sozialbrett(request.args.to_dict()))

    @app.get("/api/wetter")
    def wetterdaten():
        bestand = daten()
        return jsonify(bestand.wetterbrett(bestand.auswahl(request.args.to_dict(), "wetter")))

    @app.get("/api/quellbewegung")
    def quellbewegung():
        return jsonify(daten().quellbewegung(request.args.to_dict()))

    return app
