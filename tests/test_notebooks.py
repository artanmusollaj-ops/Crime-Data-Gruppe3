"""Jedes Notebook muss wenigstens starten koennen - ohne es auszufuehren.

Am 19.9.2026 stellte sich heraus, dass ``12_detroit_bronze_ingestion.ipynb``
seit dem Umzug des Codes nach ``src/crime/`` in der **zweiten Zelle**
abbrach: Es suchte das Paket im Projekt-Root. Bemerkt hat es niemand, weil
der woechentliche Datenlauf genau die sechs ladenden Notebooks **nicht**
ausfuehrt - aus gutem Grund, sie haengen an sechs fremden Diensten.

Damit war ein Beleg der Abgabe monatelang kaputt, ohne dass ein roter Lauf
darauf zeigte. Diese Datei schliesst die Luecke von der anderen Seite: Sie
fuehrt nichts aus und braucht kein Netz, prueft aber, dass jedes Notebook
seine Pakete faende und dass jeder importierte Name existiert. Das haette
gereicht.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
import re

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((PROJECT_ROOT / "notebooks").glob("*.ipynb"))

# Die Pakete der Strecke. Nur ihre Importe werden geprueft - ob ``pandas``
# existiert, sagt uns die Testsuite ohnehin an anderer Stelle.
PAKETE = {p.name for p in (PROJECT_ROOT / "src" / "crime").iterdir()
          if p.is_dir() and not p.name.startswith(("_", "."))}

# Notebooks, die laden koennen, und ihr Schalter. Ob er aus sein MUSS, haengt
# davon ab, wohin sie schreiben - siehe den Test unten.
LADENDE = {
    "02_chicago_bronze_ingestion": "RUN_DOWNLOAD",
    "12_detroit_bronze_ingestion": "RUN_DOWNLOAD",
}


def code(pfad: Path) -> str:
    notizbuch = json.loads(pfad.read_text(encoding="utf-8"))
    return "\n".join("".join(z["source"]) for z in notizbuch["cells"]
                     if z["cell_type"] == "code")


def test_es_gibt_ueberhaupt_notebooks():
    """Ein Waechter, der nichts findet, ist gruen und wertlos."""
    assert len(NOTEBOOKS) >= 10, f"nur {len(NOTEBOOKS)} Notebooks gefunden"
    assert PAKETE, "keine Pakete unter src/crime gefunden"


@pytest.mark.parametrize("pfad", NOTEBOOKS, ids=lambda p: p.stem)
def test_die_wurzelprobe_zeigt_auf_einen_vorhandenen_pfad(pfad):
    """Der Fehler von Notebook 12: ``PROJECT_ROOT / 'detroit_pipeline'``.

    Die Notebooks suchen ihren Projekt-Root, indem sie auf einen Pfad
    darunter probieren. Zeigt diese Probe ins Leere, bricht das Notebook in
    der zweiten Zelle ab - und zwar unabhaengig davon, wo es gestartet wurde.
    """
    quelle = code(pfad)
    proben = re.findall(r"PROJECT_ROOT\s*/\s*((?:['\"][\w.]+['\"]\s*/\s*)*['\"][\w.]+['\"])"
                        r"\s*\)?\s*\.exists\(\)", quelle)
    if not proben:
        pytest.skip("keine Wurzelprobe - das Notebook findet seine Pfade anders")
    fehlend = []
    for probe in proben:
        teile = re.findall(r"['\"]([\w.]+)['\"]", probe)
        if not (PROJECT_ROOT.joinpath(*teile)).exists():
            fehlend.append("/".join(teile))
    assert not fehlend, (
        f"{pfad.name} probiert auf {fehlend} - diesen Pfad gibt es nicht. "
        "Das Notebook bricht beim Start ab."
    )


@pytest.mark.parametrize("pfad", NOTEBOOKS, ids=lambda p: p.stem)
def test_wer_die_strecke_importiert_legt_src_crime_auf_den_pfad(pfad):
    """Nur wer ein Paket der Strecke braucht, muss auch dorthin zeigen.

    ``32_nibrs_source`` legt bewusst den Projekt-Root auf den Pfad: Es
    importiert ``tests.config.*``, nicht die Strecke. Eine pauschale Regel
    haette es zu Unrecht durchfallen lassen.
    """
    quelle = code(pfad)
    braucht = {k.module.split(".")[0] for k in ast.walk(ast.parse(quelle))
               if isinstance(k, ast.ImportFrom) and k.module} | \
              {n.name.split(".")[0] for k in ast.walk(ast.parse(quelle))
               if isinstance(k, ast.Import) for n in k.names}
    if not (braucht & PAKETE):
        pytest.skip("importiert kein Paket der Strecke")
    assert re.search(r"['\"]src['\"]\s*/\s*['\"]crime['\"]", quelle), (
        f"{pfad.name} importiert {sorted(braucht & PAKETE)}, legt aber "
        "src/crime nirgends auf den Pfad"
    )


@pytest.mark.parametrize("pfad", NOTEBOOKS, ids=lambda p: p.stem)
def test_jeder_importierte_name_existiert(pfad):
    """Ein umbenannter Name faellt sonst erst beim Ausfuehren auf."""
    fehlend = []
    for knoten in ast.walk(ast.parse(code(pfad))):
        if not isinstance(knoten, ast.ImportFrom) or not knoten.module:
            continue
        if knoten.module.split(".")[0] not in PAKETE:
            continue
        try:
            modul = importlib.import_module(knoten.module)
        except ImportError as fehler:
            fehlend.append(f"{knoten.module} ({fehler})")
            continue
        for name in knoten.names:
            if not hasattr(modul, name.name):
                fehlend.append(f"{knoten.module}.{name.name}")
    assert not fehlend, f"{pfad.name} importiert, was es nicht gibt: {fehlend}"


@pytest.mark.parametrize("stem, schalter", sorted(LADENDE.items()))
def test_ein_ladendes_notebook_schreibt_nicht_unbemerkt_in_den_bestand(stem, schalter):
    """Entweder der Schalter ist aus - oder es schreibt in ein Wegwerfverzeichnis.

    ``02_chicago_bronze_ingestion`` laedt mit Absicht: Es setzt seinen
    ``DATA_ROOT`` auf einen Ordner unter ``tempfile.gettempdir()`` und raeumt
    danach auf. Dort ist ein eingeschalteter Download richtig und die
    Vorfuehrung waere ohne ihn wertlos.

    ``12_detroit_bronze_ingestion`` schreibt dagegen in den echten Bestand.
    Sein Schalter muss aus sein.
    """
    quelle = code(PROJECT_ROOT / "notebooks" / f"{stem}.ipynb")
    wegwerf = bool(re.search(r"tempfile\.(gettempdir|mkdtemp)|TemporaryDirectory", quelle))
    aus = bool(re.search(rf"^{schalter}\s*=\s*False", quelle, re.M))
    assert wegwerf or aus, (
        f"{stem}: {schalter} steht auf True und der Zielordner ist der echte "
        "Bestand - ein unbedachter Lauf erzeugt damit Bronze-Laeufe"
    )


def test_kein_notebook_speichert_seine_ausgaben():
    """Notebooks liegen ohne Ausgaben im Repository - alle vierzehn.

    ``test_notebook_sternschema.py`` verlangte das bis zum 20.9.2026 nur fuer
    Notebook 34, mit der Begruendung *"So halten es die uebrigen dreizehn
    auch."* Sie hielten es so, aber niemand prueft es - und beim Durchgehen der
    Notebooks in dieser Woche wurden sechs davon mit ``nbconvert --execute
    --inplace`` ausgefuehrt und mit ihren Ausgaben eingecheckt, ohne dass etwas
    rot wurde.

    Warum die Konvention gilt: Eine gespeicherte Ausgabe ist eine Zahl, die
    niemand nachrechnet. Sie veraltet still, sie blaeht jeden Diff auf, und sie
    behauptet einen Stand, den die Datei daneben laengst nicht mehr hat. Wer
    die Zahlen sehen will, fuehrt das Notebook aus.
    """
    mit: dict[str, list[int]] = {}
    for pfad in NOTEBOOKS:
        zellen = json.loads(pfad.read_text(encoding="utf-8"))["cells"]
        treffer = [i for i, z in enumerate(zellen)
                   if z["cell_type"] == "code" and z.get("outputs")]
        if treffer:
            mit[pfad.name] = treffer
    assert not mit, (
        f"Notebooks mit gespeicherter Ausgabe: {mit}. "
        "Leeren mit: jupyter nbconvert --clear-output --inplace notebooks/<datei>.ipynb"
    )
