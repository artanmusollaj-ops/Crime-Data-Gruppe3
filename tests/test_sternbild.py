"""Haelt das Sternbild gegen Gold - ``tools/build_sternbild.py``.

Bis zum 25.11.2026 war ``docs/bilder/stern.svg`` von Hand gezeichnet und zeigte
vier Dimensionen und 344'617 Taten, als Gold elf Tabellen und 1'895'123 Taten
hatte; die Kopie in ``sternschema-und-wuerfel.html`` einen dritten Stand.
Diese Tests halten:

1. Jede Gold-Tabelle steht im Bild - auch ohne ``data/``.
2. Die Seite traegt dasselbe Bild wie die Datei.
3. Ein zweiter Lauf in einem eigenen Prozess liefert dieselben Bytes; braucht
   die Gold-Manifeste und wird ohne sie uebersprungen.
4. Die Kopfzahlen von ``.md`` und ``.html`` passen zu den Manifesten.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WERKZEUG = PROJECT_ROOT / "tools" / "build_sternbild.py"
BILD = PROJECT_ROOT / "docs" / "bilder" / "stern.svg"
SEITE = PROJECT_ROOT / "docs" / "sternschema-und-wuerfel.html"
DOKUMENT = PROJECT_ROOT / "docs" / "sternschema-und-wuerfel.md"

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import build_sternbild as bs  # noqa: E402
from gold_pipeline import TABELLEN  # noqa: E402


def _block(html: str) -> str:
    treffer = re.search(re.escape(bs.ANFANG) + r"\n(.*?)" + re.escape(bs.ENDE), html, re.S)
    assert treffer, f"{SEITE.name}: kein Block {bs.ANFANG} … {bs.ENDE}"
    return treffer.group(1)


@pytest.fixture(scope="module")
def zeilen() -> dict[str, int]:
    gefunden = bs.zeilen_aus_manifesten()
    if not gefunden:
        pytest.skip("keine Gold-Manifeste unter data/gold/")
    return gefunden


def test_jede_gold_tabelle_hat_einen_platz_im_bild():
    assert set(TABELLEN) <= set(bs.LAGE), set(TABELLEN) - set(bs.LAGE)
    assert set(TABELLEN) <= set(bs.INHALT), set(TABELLEN) - set(bs.INHALT)
    ohne_kante = [t for t in TABELLEN
                  if t not in bs.SCHLUESSEL and t != "fact_offense"
                  and not t.startswith("bridge_")]
    assert not ohne_kante, f"Dimension ohne Schlüssel zur Faktentabelle: {ohne_kante}"


@pytest.mark.parametrize("pfad", [BILD, SEITE], ids=["svg", "html"])
def test_jede_gold_tabelle_steht_im_abgelegten_bild(pfad):
    bild = BILD.read_text(encoding="utf-8") if pfad == BILD else _block(
        SEITE.read_text(encoding="utf-8"))
    fehlt = [t for t in TABELLEN if f">{t}</text>" not in bild]
    assert not fehlt, f"{pfad.name} zeigt nicht: {fehlt} - python tools/build_sternbild.py"


def test_seite_und_datei_zeigen_dieselben_tabellen_und_zahlen():
    def kern(svg: str) -> list[str]:
        return re.findall(r">([^<]+)</text>", svg)
    assert kern(_block(SEITE.read_text(encoding="utf-8"))) == kern(
        BILD.read_text(encoding="utf-8"))


def test_ein_zweiter_lauf_liefert_dieselben_bytes(zeilen):
    # Eigener Prozess: Zwei Bauten im selben Prozess teilen den Hash-Seed.
    lauf = subprocess.run([sys.executable, str(WERKZEUG), "--pruefen"],
                          capture_output=True, text=True, cwd=PROJECT_ROOT)
    assert lauf.returncode == 0, lauf.stdout + lauf.stderr


def test_die_kopfzahlen_passen_zu_den_manifesten(zeilen):
    dims = [t for t in TABELLEN if t.startswith("dim_")]
    bruecken = [t for t in TABELLEN if t.startswith("bridge_")]
    erwartet = {
        "Faktentabelle": bs.zahl(zeilen["fact_offense"]),
        "Dimensionen": f"{len(dims)} · {bs.zahl(sum(zeilen[t] for t in dims))}",
        "Brücken": f"{len(bruecken)} · {bs.zahl(sum(zeilen[t] for t in bruecken))}",
    }
    md = DOKUMENT.read_text(encoding="utf-8")
    html = SEITE.read_text(encoding="utf-8")
    for feld, wert in erwartet.items():
        assert re.search(rf"^\| {feld} \| {re.escape(wert)} Zeilen", md, re.M), (
            f"{DOKUMENT.name}: Kopfzeile {feld} soll {wert} Zeilen nennen")
        assert f"<dt>{feld}</dt><dd>{wert} Zeilen" in html, (
            f"{SEITE.name}: Kopfzeile {feld} soll {wert} Zeilen nennen")
