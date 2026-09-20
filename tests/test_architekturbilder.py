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
    """Wie bei den drei Crosswalk-Werkzeugen: erzeugt heisst wiederholbar.

    Die Bilder werden danach wiederhergestellt - aus demselben Grund wie beim
    Feldkatalog: Das Werkzeug kennt kein Ausgabeverzeichnis, und ein
    scheiternder Test liess die neu erzeugten SVG im Arbeitsbaum liegen.
    """
    vorher = {p: p.read_text(encoding="utf-8") for p in (PAKETE, FLUSS)}
    try:
        fertig = subprocess.run([sys.executable, str(WERKZEUG)],
                                capture_output=True, text=True, cwd=PROJEKT)
        nachher = {p: p.read_text(encoding="utf-8") for p in vorher}
    finally:
        for pfad, text in vorher.items():
            pfad.write_text(text, encoding="utf-8")
    assert fertig.returncode == 0, fertig.stderr or fertig.stdout
    for pfad, text in vorher.items():
        assert nachher[pfad] == text, (
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
    """Sonst steht im ``aria-label`` eine Zahl von gestern.

    Bis zum 20.9.2026 pruefte dieser Test nur die **Paketzahl**. Die
    Kantenzahl stand derweil als feste ``19`` in der Fusszeile des Bildes,
    waehrend der Graph laengst auf 23 gewachsen war - und im Dokument daneben
    ebenso. Ein erzeugtes Bild, das eine Zahl mitfuehrt statt sie zu rechnen,
    ist ein gezeichnetes mit einem Generator davor.
    """
    kanten = werkzeug.importgraph()
    gesamt = sum(len(z) for z in kanten.values())
    svg = PAKETE.read_text(encoding="utf-8")

    beschreibung = ET.fromstring(svg).get("aria-label")
    assert f"{len(kanten)} Paketen" in beschreibung, beschreibung
    assert f"{gesamt} Kanten" in beschreibung, beschreibung
    assert f"der {gesamt} Kanten sind gezeichnet" in svg, (
        f"die Fusszeile des Bildes nennt nicht die gemessenen {gesamt} Kanten"
    )

    from orchestration import run_all

    stufen = re.search(r"(\d+) Stufen", FLUSS.read_text(encoding="utf-8"))
    assert stufen, "das Datenflussbild nennt keine Stufenzahl"
    assert int(stufen.group(1)) == sum(1 for _ in run_all.STUFEN), (
        "das Datenflussbild nennt eine andere Stufenzahl als run_all.STUFEN"
    )


def test_das_dokument_nennt_dieselben_kanten_wie_der_graph(werkzeug):
    """``architektur.md`` beschreibt das Bild - dann mit denselben Zahlen.

    Der Text trug ``19 Kanten``, ``drei Pfeile`` und ``fuenf
    Ingestion-Pakete``, als es 23, sechs und vier waren. Gefunden hat das ein
    Mensch beim Lesen, nicht die Suite.

    Geprueft werden die **Saetze**, nicht das blosse Vorkommen der Zahl: Ein
    erster Entwurf dieses Tests suchte "23 Kanten" irgendwo im Text und ging
    durch, obwohl die Aussage daneben auf 19 zurueckgedreht war - die Zahl
    stand noch an einer zweiten Stelle.
    """
    kanten = werkzeug.importgraph()
    gesamt = sum(len(z) for z in kanten.values())
    gezeichnet = sum(1 for p, ziele in kanten.items() if p not in werkzeug.FUNDAMENT
                     for z in ziele if z not in werkzeug.FUNDAMENT)
    ingestion = sum(1 for p in kanten
                    if p.endswith("_pipeline") and p not in ("silver_pipeline",
                                                             "gold_pipeline"))
    # Ohne Zeilenumbrueche: Die Saetze brechen im Dokument um, die Muster nicht.
    text = " ".join((PROJEKT / "docs" / "architektur.md")
                    .read_text(encoding="utf-8").split())
    wort = {v: k for k, v in ZAHLWORT.items()}

    for muster, erwartet, was in (
        (r"Pakete, (\d+) Kanten", gesamt, "die Zahl der Kanten"),
        (r"Warum nur (\w+) Pfeile gezeichnet sind", gezeichnet, "die gezeichneten Pfeile"),
        (r"(\w+) der (\d+) Kanten zeigen auf", gesamt - gezeichnet,
         "die Kanten auf die Fundamente"),
        (r"zwischen den (\w+) Ingestion-Paketen", ingestion, "die Ingestion-Pakete"),
        (r"die (\w+) übrigen untergehen", gezeichnet, "die uebrigen Kanten"),
    ):
        treffer = re.search(muster, text)
        assert treffer, f"{was}: der Satz zu /{muster}/ fehlt im Dokument"
        roh = treffer.group(1)
        genannt = int(roh) if roh.isdigit() else wort.get(roh.lower())
        assert genannt == erwartet, (
            f"{was}: das Dokument sagt {roh!r}, gemessen sind {erwartet}"
        )


# Das Dokument schreibt kleine Zahlen aus. Der Test muss beides lesen koennen.
ZAHLWORT = {
    1: "eine", 2: "zwei", 3: "drei", 4: "vier", 5: "fünf", 6: "sechs",
    7: "sieben", 8: "acht", 9: "neun", 10: "zehn", 11: "elf", 12: "zwölf",
    13: "dreizehn", 14: "vierzehn", 15: "fünfzehn", 16: "sechzehn",
    17: "siebzehn", 18: "achtzehn", 19: "neunzehn", 20: "zwanzig",
    21: "einundzwanzig", 22: "zweiundzwanzig", 23: "dreiundzwanzig",
}


def test_jedes_paket_steht_im_bild(werkzeug):
    """Kommt ein Paket dazu, muss es auftauchen - sonst beschreibt das Bild
    ein Projekt, das es nicht mehr gibt."""
    svg = PAKETE.read_text(encoding="utf-8")
    fehlend = [p for p in werkzeug.importgraph() if f">{p}<" not in svg]
    assert not fehlend, f"nicht im Bild: {fehlend}"
