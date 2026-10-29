# Integrierte Engineering-Konsole

Paket: **Crime_Data_2026-10-26_v1.0**

Startpunkt ist [docs/ENGINEERING_KONSOLE.md](docs/ENGINEERING_KONSOLE.md); [docs/handbuch/ENGINEERING_KONSOLE.pdf](docs/handbuch/ENGINEERING_KONSOLE.pdf) enthält dieselbe Anleitung.

- Lokal: Installation mit `python -m pip install -e ".[admin,dev]"`, Konfiguration prüfen, `init`, `enable-managed`, dann Webserver und Worker in getrennten Terminals starten.
- Server: Infrastrukturstand als Basis beibehalten. Das neue `docker-compose.console.yml` ist ein Zusatz zur srv01-Datei. Ein eigener Übernahmeablauf und der Ersatz des bisherigen Cron-Einstiegs sind erforderlich.
- Änderungen: [docs/INTEGRATION_2026-10-26.md](docs/INTEGRATION_2026-10-26.md).
- Nachweise und Grenzen: [docs/TESTNACHWEIS_KONSOLE.md](docs/TESTNACHWEIS_KONSOLE.md).

Das Paket ist vorbereitet und lokal getestet; es wurde nicht auf srv01 ausgerollt. Es ersetzt Elasticsearch nicht und führt keinen zusätzlichen parallelen Silver-Worker ein.
