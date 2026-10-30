"""Das Handbuch der Engineering-Konsole: ein Markdown, ein PDF daraus.

Das PDF wird gebraucht, um Anleitungen weiterzugeben (Entscheidung vom
30.10.2026). Artans erstes PDF entstand aus einem Skript, das nicht im
Repository lag, und war vier Tage spaeter in vier Abschnitten ueberholt. Seither
erzeugt ``tools/build_konsole_pdf.py`` es aus dem Markdown und schreibt den
Hash des Markdowns in den Titel des PDFs. Dieser Waechter vergleicht ihn: Wer
das Markdown aendert und das PDF nicht neu erzeugt, sieht es hier - am Inhalt,
nicht an einem Datum.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HANDBUCH = PROJECT_ROOT / "docs" / "intern" / "ENGINEERING_KONSOLE.md"
PDF = PROJECT_ROOT / "docs" / "intern" / "handbuch" / "ENGINEERING_KONSOLE.pdf"
BEISPIEL = PROJECT_ROOT / "docs" / "console-settings.example.json"


def pdf_titel(daten: bytes) -> str:
    """Der /Title des PDFs - Chrome schreibt ihn als UTF-16 in Hex."""
    treffer = re.search(rb"/Title\s*<FEFF([0-9A-Fa-f]+)>", daten)
    assert treffer, "das PDF traegt keinen Titel"
    return bytes.fromhex(treffer.group(1).decode()).decode("utf-16-be")


def test_das_pdf_ist_aus_dem_heutigen_markdown_erzeugt():
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from build_konsole_pdf import kennung

    erwartet = kennung(HANDBUCH.read_bytes())
    titel = pdf_titel(PDF.read_bytes())
    assert erwartet in titel, (
        f"das PDF ist aelter als das Markdown ({titel!r}, erwartet {erwartet}) - "
        "python tools/build_konsole_pdf.py")


def test_die_kennung_haengt_am_inhalt():
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    from build_konsole_pdf import kennung

    assert kennung(b"a") != kennung(b"b")
    assert kennung(b"a") == kennung(b"a")
    assert kennung(b"a") == hashlib.sha256(b"a").hexdigest()[:16]


def test_das_beispiel_fuer_die_einstellungen_ist_gueltig():
    """Das Handbuch schickt jeden neuen Betrieb dorthin; ein ungueltiges
    Beispiel faellt erst bei 'init' auf dem Server auf."""
    from platform_admin.store import validate_settings

    beispiel = json.loads(BEISPIEL.read_text(encoding="utf-8"))
    validate_settings(beispiel)
    assert (beispiel["scope_start"], beispiel["scope_end_exclusive"]) == (
        "2021-01-01", "2027-01-01"), "der Studienzeitraum ist 2021 bis 2026"
