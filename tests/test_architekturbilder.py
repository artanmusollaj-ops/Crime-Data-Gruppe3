"""Prueft die beiden erzeugten Architekturbilder.

Konzept 5.3 fuehrte lange *"kein Diagramm der Abhaengigkeitskanten"* als
Luecke. Ein von Hand gezeichnetes Bild waere sie los - und am Tag darauf
falsch. Die Bilder werden deshalb aus dem Code erzeugt, und hier steht, was
das wert sein muss:

* Ein zweiter Lauf liefert dieselbe Datei - sonst ist "erzeugt" eine
  Behauptung. Dieselbe Pruefung wie bei den Crosswalks und beim Feldkatalog.
* Der Importgraph hat **keine Zyklen**. Das ist keine Eigenschaft des Bildes,
  sondern der Architektur; das Bild macht sie nur sichtbar.
* Was die Bildbeschreibung behauptet, stimmt mit dem Code ueberein.
"""

from __future__ import annotations

import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest


PROJEKT = Path(__file__).resolve().parents[1]
WERKZEUG = PROJEKT / "tools" / "build_architekturbilder.py"
BILDER = PROJEKT / "docs" / "bilder"
PAKETE = BILDER / "architektur-pakete.svg"
FLUSS = BILDER / "architektur-datenfluss.svg"

sys.path.insert(0, str(PROJEKT / "tools"))


@pytest.fixture(scope="module")
def werkzeug():
    import build_architekturbilder

    return build_architekturbilder


def test_beide_bilder_liegen_im_repository():
    for pfad in (PAKETE, FLUSS):
        assert pfad.exists(), f"{pfad} fehlt - erzeugen mit {WERKZEUG.name}"


@pytest.mark.parametrize("pfad", [PAKETE, FLUSS], ids=["pakete", "datenfluss"])
def test_es_ist_wohlgeformtes_svg(pfad):
    wurzel = ET.fromstring(pfad.read_text(encoding="utf-8"))
    assert wurzel.tag.endswith("svg")
    assert wurzel.get("viewBox"), "ohne viewBox skaliert es nicht"
    assert wurzel.get("role") == "img" and wurzel.get("aria-label"), (
        "ein Bild ohne Beschreibung ist fuer einen Screenreader nichts"
    )


def test_ein_zweiter_lauf_liefert_dieselben_dateien():
    """Wie bei den drei Crosswalk-Werkzeugen: erzeugt heisst wiederholbar."""
    vorher = {p: p.read_text(encoding="utf-8") for p in (PAKETE, FLUSS)}
    fertig = subprocess.run([sys.executable, str(WERKZEUG)],
                            capture_output=True, text=True, cwd=PROJEKT)
    assert fertig.returncode == 0, fertig.stderr or fertig.stdout
    for pfad, alt in vorher.items():
        assert pfad.read_text(encoding="utf-8") == alt, (
            f"{pfad.name} sieht nach einem zweiten Lauf anders aus - dann ist "
            "es nicht reproduzierbar aus dem Code abgeleitet"
        )


def test_der_importgraph_hat_keine_zyklen(werkzeug):
    """Die Aussage des Bildes, und sie gilt dem Code, nicht der Zeichnung.

    Ein Zyklus zwischen zwei Paketen liesse sich zeichnen - er waere nur nicht
    mehr auf Schichten abzubilden, und das Bild loege ueber den Aufbau.
    """
    kanten = werkzeug.importgraph()
    besucht: set[str] = set()

    def weg(paket: str, unterwegs: tuple[str, ...]) -> list[str] | None:
        if paket in unterwegs:
            return list(unterwegs[unterwegs.index(paket):]) + [paket]
        if paket in besucht:
            return None
        besucht.add(paket)
        for ziel in sorted(kanten.get(paket, ())):
            gefunden = weg(ziel, unterwegs + (paket,))
            if gefunden:
                return gefunden
        return None

    for paket in sorted(kanten):
        zyklus = weg(paket, ())
        assert zyklus is None, f"Zyklus im Importgraph: {' -> '.join(zyklus)}"


def test_die_fundamente_haengen_an_nichts(werkzeug):
    """``manifeste`` ist Blatt, ``storage`` benutzt nur ``manifeste``.

    Darauf ruht die Schichtung - und darauf, dass beide von fast allem
    benutzt werden. Zoege eines von ihnen eine Abhaengigkeit nach oben, waere
    das Band im Bild eine Luege.
    """
    kanten = werkzeug.importgraph()
    assert kanten["manifeste"] == set()
    assert kanten["storage"] == {"manifeste"}


def test_die_bildbeschreibung_nennt_die_echten_zahlen(werkzeug):
    """Sonst steht im ``aria-label`` eine Zahl von gestern."""
    kanten = werkzeug.importgraph()
    beschreibung = ET.fromstring(PAKETE.read_text(encoding="utf-8")).get("aria-label")
    assert f"{len(kanten)} Paketen" in beschreibung, beschreibung

    stufen = re.search(r"(\d+) Stufen", FLUSS.read_text(encoding="utf-8"))
    from orchestration import run_all

    assert stufen, "das Datenflussbild nennt keine Stufenzahl"
    assert sum(1 for _ in run_all.STUFEN) == 13


def test_jedes_paket_steht_im_bild(werkzeug):
    """Kommt ein Paket dazu, muss es auftauchen - sonst beschreibt das Bild
    ein Projekt, das es nicht mehr gibt."""
    svg = PAKETE.read_text(encoding="utf-8")
    fehlend = [p for p in werkzeug.importgraph() if f">{p}<" not in svg]
    assert not fehlend, f"nicht im Bild: {fehlend}"
