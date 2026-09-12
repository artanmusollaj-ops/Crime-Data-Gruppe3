"""Prueft, dass ``docs/feldkatalog.md`` vollstaendig und reproduzierbar ist.

Ein Feldkatalog ist die Sorte Dokument, die still veraltet: Eine Spalte kommt
dazu, niemand denkt daran, und der Katalog behauptet weiter den alten Stand.
Genau das ist in diesem Projekt schon zweimal mit Zahlen passiert.

Deshalb wird er **erzeugt** - Spaltennamen und Typen aus den Manifesten der
gebauten Tabellen, die Bedeutung aus ``tools/build_feldkatalog.py``. Diese
Tests halten drei Zusagen fest:

1. Jede gebaute Spalte hat eine Beschreibung.
2. Keine Beschreibung zeigt ins Leere.
3. Ein zweiter Lauf liefert dieselbe Datei.

Ohne ``data/`` wird uebersprungen: Die Spalten stehen in den Manifesten, und in
einem frischen Klon gibt es die nicht. Was auch dort laeuft, ist die Form.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KATALOG = PROJECT_ROOT / "docs" / "feldkatalog.md"
WERKZEUG = PROJECT_ROOT / "tools" / "build_feldkatalog.py"

sys.path.insert(0, str(PROJECT_ROOT / "tools"))
import build_feldkatalog as bf  # noqa: E402


@pytest.fixture(scope="module")
def gebaut() -> list[tuple[str, str, dict]]:
    tabellen = bf.manifeste()
    if not tabellen:
        pytest.skip("keine gebauten Tabellen unter data/")
    return tabellen


# --------------------------------------------------------------------------
# Form - laeuft auch ohne data/
# --------------------------------------------------------------------------


def test_der_katalog_liegt_im_repository():
    assert KATALOG.exists(), (
        f"{KATALOG} fehlt - python tools/build_feldkatalog.py"
    )


def test_das_werkzeug_liegt_daneben():
    assert WERKZEUG.exists()


def test_keine_beschreibung_ist_leer():
    """Eine leere Beschreibung waere schlimmer als eine fehlende Spalte.

    Sie sieht nach Vollstaendigkeit aus und sagt nichts.
    """
    leer = [
        schluessel for schluessel, text in
        list(bf.GEMEINSAM.items()) + list(bf.JE_TABELLE.items())
        if not text.strip()
    ]
    assert not leer, f"leere Beschreibungen: {leer}"


# --------------------------------------------------------------------------
# Vollstaendigkeit - braucht die gebauten Tabellen
# --------------------------------------------------------------------------


def test_jede_gebaute_spalte_hat_eine_beschreibung(gebaut):
    fehlend = [
        f"{schicht}/{name}.{spalte}"
        for schicht, name, manifest in gebaut
        for spalte in manifest.get("schema", {})
        if bf.beschreibung(name, spalte) is None
    ]
    assert not fehlend, (
        f"{len(fehlend)} Spalten ohne Beschreibung: {fehlend}. In "
        "tools/build_feldkatalog.py eintragen."
    )


def test_jede_beschreibung_zeigt_auf_eine_echte_spalte(gebaut):
    """Sonst waechst der Katalog um Spalten, die es nicht mehr gibt."""
    echt = {
        (name, spalte)
        for _, name, manifest in gebaut
        for spalte in manifest.get("schema", {})
    }
    verwaist = [
        f"{tabelle}.{spalte}" for tabelle, spalte in bf.JE_TABELLE
        if (tabelle, spalte) not in echt
    ]
    assert not verwaist, f"Beschreibungen ohne Spalte: {verwaist}"

    namen = {spalte for _, spalte in echt}
    ungenutzt = sorted(set(bf.GEMEINSAM) - namen)
    assert not ungenutzt, f"gemeinsame Beschreibungen ohne Spalte: {ungenutzt}"


def test_jede_spalte_steht_auch_im_dokument(gebaut):
    """Der Katalog im Repository muss den gebauten Stand zeigen.

    Faellt dieser Test, ist er nicht neu erzeugt worden - die Beschreibungen
    koennen dann stimmen und das Dokument trotzdem veraltet sein.
    """
    text = KATALOG.read_text(encoding="utf-8")
    fehlend = [
        f"{name}.{spalte}"
        for _, name, manifest in gebaut
        for spalte in manifest.get("schema", {})
        if f"| `{spalte}` |" not in text
    ]
    assert not fehlend, (
        f"{len(fehlend)} Spalten fehlen im Dokument, zuerst {fehlend[:5]}. "
        "python tools/build_feldkatalog.py"
    )


def test_das_korn_jeder_tabelle_steht_drin(gebaut):
    text = KATALOG.read_text(encoding="utf-8")
    for _, name, manifest in gebaut:
        assert f"### `{name}`" in text, f"{name} fehlt im Katalog"
        korn = manifest.get("grain")
        if korn:
            assert korn in text, f"Korn von {name} fehlt: {korn}"


# --------------------------------------------------------------------------
# Reproduzierbarkeit
# --------------------------------------------------------------------------


def test_ein_zweiter_lauf_liefert_dieselbe_datei(gebaut):
    """Wie bei den drei Crosswalk-Werkzeugen: erzeugt heisst wiederholbar."""
    vorher = KATALOG.read_text(encoding="utf-8")
    fertig = subprocess.run(
        [sys.executable, str(WERKZEUG)],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    assert fertig.returncode == 0, fertig.stderr
    assert KATALOG.read_text(encoding="utf-8") == vorher, (
        "Ein zweiter Lauf liefert eine andere Datei - dann ist der Katalog "
        "nicht reproduzierbar aus den Manifesten abgeleitet"
    )
