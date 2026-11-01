"""Der Webteil des Dashboards: eine Seite, zwei Abfragen, keine Anmeldung.

Die Anmeldung uebernimmt auf ``srv01`` Cloudflare Access vor Traefik, wie fuer
alles unter ``urbancrime-*``. Das Dashboard schreibt nichts und liest nur den
Bestand; eine eigene Pruefung haette nichts zu schuetzen, was die Access-
Anwendung nicht schon schuetzt.
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from serving.dashboard import Bestand, EingabeFehler
from storage import for_root

_STATISCH = Path(__file__).parent / "static"


def create_app(data_root: Path | str | None = None, *, bestand: Bestand | None = None) -> Flask:
    app = Flask(__name__, static_folder=None)
    wurzel = for_root(data_root or os.getenv("DASHBOARD_DATA_ROOT")).local_root
    zustand = {"bestand": bestand}

    def daten() -> Bestand:
        # Erst bei der ersten Anfrage geladen: gunicorn startet schneller, und
        # /healthz antwortet, auch wenn der Bestand noch fehlt.
        if zustand["bestand"] is None:
            zustand["bestand"] = Bestand(wurzel)
        else:
            zustand["bestand"].aktuell()
        return zustand["bestand"]

    @app.after_request
    def kopfzeilen(antwort):
        antwort.headers.update({
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
            "Referrer-Policy": "no-referrer",
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
        return jsonify({"status": "ok"})

    @app.get("/")
    def seite():
        return send_from_directory(_STATISCH, "index.html")

    @app.get("/zeitverlauf")
    def seite_zeitverlauf():
        return send_from_directory(_STATISCH, "zeitverlauf.html")

    @app.get("/geografie")
    def seite_geografie():
        return send_from_directory(_STATISCH, "geografie.html")

    @app.get("/static/<path:name>")
    def statisch(name):
        return send_from_directory(_STATISCH, name)

    @app.get("/api/optionen")
    def optionen():
        return jsonify(daten().optionen())

    @app.get("/api/ueberblick")
    def ueberblick():
        bestand = daten()
        return jsonify(bestand.ueberblick(bestand.auswahl(request.args.to_dict())))

    @app.get("/api/zeitverlauf")
    def zeitverlauf():
        bestand = daten()
        return jsonify(bestand.zeitverlauf(bestand.auswahl(request.args.to_dict())))

    @app.get("/api/karten")
    def karten():
        # Die Umrisse aendern sich nur mit dem Bestand; der Browser holt sie
        # einmal je Seite, die Raten bei jeder Auswahl.
        return jsonify(daten().karten)

    @app.get("/api/geografie")
    def geografie():
        bestand = daten()
        return jsonify(bestand.geografie(bestand.auswahl(request.args.to_dict())))

    return app
