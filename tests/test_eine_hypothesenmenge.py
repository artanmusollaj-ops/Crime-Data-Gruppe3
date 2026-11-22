"""Kein Dokument fuehrt eine zweite Hypothesenmenge, ohne es zu sagen (FR-54).

Abgegeben sind F1 bis F6 und H1 bis H6 (``docs/forschungsfragen.md``). Vor der
Abgabe lag ein Vorschlag mit FF1 bis FF3 und H1 bis H8 auf dem Tisch, und
gleiche Nummern meinten dort anderes. Am 22.11.2026 stand das im Konzept noch
einmal: "H2 zeigt ..., dass der Ueberlapp nur Duplikate erzeugt" - das war die
H2 des Vorschlags, nicht die abgegebene.

Geprueft wird das Erkennbare: Wer H7, H8 oder FF1 bis FF3 nennt, nennt die
Vorschlagsmenge und muss sie als solche kennzeichnen. Eine falsch zugeordnete
H1 bis H6 sieht dieser Waechter nicht; die Zitate in Konzept und Notebook 36
haelt ``test_notebook_hypothesen.py`` gegen den abgegebenen Wortlaut.
"""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS = PROJECT_ROOT / "docs"
MARKE = "Nicht die abgegebene Hypothesenmenge"
#: Verlauf und erzeugte Seiten - sie halten fest, was einmal war.
AUSGENOMMEN = ("archiv", "referenz", "nachweise", "AENDERUNGEN.md")
VORSCHLAG = re.compile(r"\b(H7|H8|FF[1-3])\b")


def test_die_vorschlagsmenge_ist_gekennzeichnet():
    ungekennzeichnet = []
    for pfad in sorted(DOCS.rglob("*.md")) + [PROJECT_ROOT / "README.md"]:
        if any(a in pfad.parts or pfad.name == a for a in AUSGENOMMEN):
            continue
        text = pfad.read_text(encoding="utf-8")
        if VORSCHLAG.search(text) and MARKE not in text:
            ungekennzeichnet.append(str(pfad.relative_to(PROJECT_ROOT)))
    assert not ungekennzeichnet, (
        f"nennen die Vorschlagsmenge ohne Hinweis «{MARKE}»: {ungekennzeichnet}")


def test_das_konzept_ordnet_die_duplikate_nicht_h2_zu():
    """Der Satz vom 22.11.2026 darf nicht zurueckkommen."""
    text = (DOCS / "ln2_konzept.md").read_text(encoding="utf-8")
    assert not re.search(r"H2 zeigt[^.]*Duplikat", text)
