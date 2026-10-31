"""Erzeugt das PDF-Handbuch der Engineering-Konsole aus dem Markdown.

    python tools/build_konsole_pdf.py

**Warum ein Werkzeug.** Das PDF wird gebraucht, um Anleitungen weiterzugeben
(Entscheidung vom 30.10.2026). Das erste kam aus einem ReportLab-Skript, das
nie im Repository lag, und war nach vier Tagen in vier Abschnitten ueberholt -
neu erzeugen konnte es niemand. Jetzt ist das Markdown die einzige Quelle, und
das PDF entsteht daraus: Markdown nach HTML mit dem Markdown-Leser, den pdoc
mitbringt (schon im Lockfile), HTML nach PDF mit demselben headless Chrome,
den ``tools/build_dashboardbilder.py`` fuer die Bildschirmfotos nimmt.

**Wie man sieht, dass es zum Markdown passt.** Der Titel des PDFs traegt
die ersten 16 Zeichen des SHA-256 des Markdowns. Byteweise gleich ist das PDF
zweier Laeufe nicht - Chrome schreibt das Erstellungsdatum hinein -, aber der
Inhalt, aus dem es entstand, ist benannt; ``tests/test_konsole_handbuch.py``
vergleicht ihn mit dem heutigen Markdown.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
from pathlib import Path

PROJEKT = Path(__file__).resolve().parents[1]
QUELLE = PROJEKT / "docs" / "intern" / "ENGINEERING_KONSOLE.md"
ZIEL = PROJEKT / "docs" / "intern" / "handbuch" / "ENGINEERING_KONSOLE.pdf"

STIL = """
@page { size: A4; margin: 18mm 16mm; }
body { font: 10.5pt/1.45 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       color: #1d2b36; }
h1 { font-size: 20pt; margin: 0 0 4pt; }
h2 { font-size: 14pt; margin: 18pt 0 6pt; border-bottom: 1px solid #cfd8de;
     break-after: avoid; }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; break-after: avoid; }
table { border-collapse: collapse; width: 100%; margin: 6pt 0; font-size: 9.5pt;
        break-inside: avoid; }
th, td { border: 1px solid #cfd8de; padding: 3pt 5pt; text-align: left;
         vertical-align: top; }
th { background: #eef3f6; }
code { font: 9pt ui-monospace, Menlo, Consolas, monospace; background: #f2f5f7;
       padding: 0 2pt; }
pre { background: #f2f5f7; padding: 6pt; white-space: pre-wrap;
      break-inside: avoid; }
pre code { padding: 0; }
a { color: #0b5f73; text-decoration: none; }
"""


def kennung(markdown: bytes) -> str:
    """Die ersten 16 Zeichen des SHA-256 - genug, um eine Fassung zu nennen."""
    return hashlib.sha256(markdown).hexdigest()[:16]


def html(markdown: bytes) -> str:
    from pdoc import markdown2

    rumpf = markdown2.markdown(markdown.decode("utf-8"),
                               extras=["tables", "fenced-code-blocks", "header-ids"])
    titel = f"Engineering-Konsole · Quelle {kennung(markdown)}"
    return (f'<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">'
            f"<title>{titel}</title><style>{STIL}</style></head>"
            f"<body>{rumpf}</body></html>")


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from build_dashboardbilder import browser

    markdown = QUELLE.read_bytes()
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as arbeit:
        seite = Path(arbeit) / "handbuch.html"
        seite.write_text(html(markdown), encoding="utf-8")
        subprocess.run(
            [browser(), "--headless=new", "--disable-gpu", "--no-sandbox",
             f"--user-data-dir={Path(arbeit) / 'browser'}",
             "--no-pdf-header-footer", f"--print-to-pdf={ZIEL}", seite.as_uri()],
            check=True, capture_output=True, timeout=120)
    print(f"{ZIEL.relative_to(PROJEKT)}: {ZIEL.stat().st_size:,} Bytes, "
          f"Quelle {kennung(markdown)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
