"""Fotografiert die Kibana-Dashboards nach ``docs/bilder/``.

    python tools/build_dashboardbilder.py

**Wozu.** Die Dashboards stehen als Code in ``serving/build_kibana`` und sind
damit reproduzierbar - aber nur fuer den, der Docker startet. Fuer die Abgabe
und die Praesentation braucht es sie als Bild. Erzeugt statt abgelegt, damit
sie nicht heimlich veralten: Wer die Tafeln aendert, laesst das hier noch
einmal laufen, und die Bilder ziehen mit.

**Voraussetzungen, und die sind ehrlich unbequem.** Es braucht die laufenden
Dienste (``docker compose up -d``), geladene Daten
(``python -m serving.load_elasticsearch``), angelegte Dashboards
(``python -m serving.build_kibana``) und einen Chrome oder Chromium auf der
Maschine. Deshalb ist das ein Werkzeug und kein Test: Es gehoert in die Hand
dessen, der die Abgabe baut, und nicht in einen Lauf, der ueberall gruen sein
muss.

**Warum ein Browser und nicht Kibanas eigene Bildausgabe.** Die kann Kibana
nur mit einer kostenpflichtigen Lizenz (*Reporting*). Ein Browser im
Hintergrund kostet nichts und zeigt genau das, was ein Mensch auch saehe -
was hier der Punkt ist: Das Bild soll beweisen, dass die Tafeln wirklich
etwas anzeigen, und nicht nur, dass ihr JSON angenommen wurde.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[1]
ZIEL = PROJEKT / "docs" / "bilder"

#: Wo ein Chrome ueblicherweise liegt. Der erste, den es gibt, gewinnt.
BROWSER = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser",
)

#: Wie lange der Browser der Seite Zeit gibt, bevor er ausloest. Kibana laedt
#: seine Oberflaeche nach, stellt dann die Abfragen und zeichnet erst danach -
#: unter 20 Sekunden erwischt man regelmaessig leere Kacheln.
GEDULD_MS = 30_000


def browser() -> str:
    for kandidat in BROWSER:
        if Path(kandidat).is_file():
            return kandidat
        if gefunden := shutil.which(kandidat):
            return gefunden
    raise SystemExit(
        "Kein Chrome oder Chromium gefunden. Gesucht wurde an:\n  "
        + "\n  ".join(BROWSER))


def erreichbar(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/api/status", timeout=10) as antwort:
            return b'"available"' in antwort.read()
    except Exception:
        return False


def fotografiere(exe: str, url: str, ziel: Path, breite: int,
                 hoehe: int) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [exe, "--headless", "--disable-gpu", "--no-sandbox",
         "--hide-scrollbars", f"--window-size={breite},{hoehe}",
         f"--virtual-time-budget={GEDULD_MS}", f"--screenshot={ziel}", url],
        capture_output=True, timeout=180,
    )
    if not ziel.is_file():
        raise SystemExit(f"{ziel.name} ist nicht entstanden")


def main(argv: list[str] | None = None) -> int:
    sys.path.insert(0, str(PROJEKT / "src" / "crime"))
    from serving.build_kibana import BRETTER, STANDARD_URL

    zerleger = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    zerleger.add_argument("--url", default=STANDARD_URL)
    zerleger.add_argument("--breite", type=int, default=1500)
    zerleger.add_argument("--hoehe", type=int, default=1400)
    args = zerleger.parse_args(argv)

    if not erreichbar(args.url):
        raise SystemExit(
            f"Kibana antwortet unter {args.url} nicht mit 'available'.\n"
            f"  docker compose up -d\n"
            f"  python -m serving.load_elasticsearch\n"
            f"  python -m serving.build_kibana")

    exe = browser()
    for brett in BRETTER:
        ziel = ZIEL / f"dashboard-{brett.kennung}.png"
        fotografiere(exe, f"{args.url}/app/dashboards#/view/{brett.kennung}",
                     ziel, args.breite, args.hoehe)
        print(f"docs/bilder/{ziel.name} geschrieben "
              f"({ziel.stat().st_size // 1024} KB)")
        # Zwei Browser gleichzeitig auf demselben Profil vertragen sich nicht.
        time.sleep(1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
