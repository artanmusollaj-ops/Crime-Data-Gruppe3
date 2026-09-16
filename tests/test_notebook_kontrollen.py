"""Prueft die Landkarte in ``notebooks/35_kontrollen.ipynb``.

Das Notebook fuehrt die Kontrollen der Strecke an einem Fall vor und schliesst
mit einer Liste aller Kontrollen: Schicht, Ort im Code, was geprueft wird,
hart oder weich. Diese Liste ist der Teil, der am leichtesten veraltet - sie
nennt Funktionsnamen, und Namen aendern sich.

Das Notebook prueft sich beim Ausfuehren selbst. Nur laeuft es lediglich im
woechentlichen Datenlauf, und bis dahin waere eine umbenannte Funktion eine
Woche lang unbemerkt. Deshalb steht dieselbe Pruefung hier: Sie braucht keine
gebauten Daten und laeuft auf jedem Pull Request mit.
"""

from __future__ import annotations

import ast
import importlib
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = PROJECT_ROOT / "notebooks" / "35_kontrollen.ipynb"
QUELLE = PROJECT_ROOT / "src" / "crime"

if str(QUELLE) not in sys.path:
    sys.path.insert(0, str(QUELLE))


@pytest.fixture(scope="module")
def zellen() -> list[dict]:
    if not NOTEBOOK.is_file():
        pytest.skip(f"{NOTEBOOK} fehlt")
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


@pytest.fixture(scope="module")
def kontrollen(zellen) -> list[tuple[str, str, str, str]]:
    """Die Liste aus dem Notebook, ohne sie auszufuehren.

    Gelesen wird der AST: Die Liste ist ein reines Literal, und
    ``literal_eval`` kann daraus nichts anderes machen als Daten.
    """
    for zelle in zellen:
        if zelle["cell_type"] != "code":
            continue
        text = "".join(zelle["source"])
        if "KONTROLLEN = [" not in text:
            continue
        for knoten in ast.parse(text).body:
            if (isinstance(knoten, ast.Assign)
                    and getattr(knoten.targets[0], "id", "") == "KONTROLLEN"):
                return ast.literal_eval(knoten.value)
    pytest.fail("keine Zelle mit KONTROLLEN im Notebook gefunden")


def aufloesen(ort: str) -> object | None:
    """``paket.modul.name`` oder ``paket.modul.Klasse.name`` nachschlagen."""
    modulname, _, rest = ort.rpartition(".")
    try:
        traeger = importlib.import_module(modulname)
    except ModuleNotFoundError:
        modulname, _, klasse = modulname.rpartition(".")
        try:
            traeger = getattr(importlib.import_module(modulname), klasse, None)
        except ModuleNotFoundError:
            return None
    return getattr(traeger, rest, None) if traeger is not None else None


def test_jede_genannte_kontrolle_existiert_im_code(kontrollen):
    """Der Fall, fuer den es diesen Test gibt.

    Beim Schreiben der Liste stand ``detroit_arcgis.get_object_ids`` darin -
    die Funktion ist aber eine Methode von ``ArcGISClient``. Das Notebook hat
    es beim ersten Lauf gemeldet; ohne diese Pruefung waere es erst eine Woche
    spaeter aufgefallen.
    """
    fehlend = [ort for _, ort, _, _ in kontrollen if aufloesen(ort) is None]
    assert not fehlend, (
        "diese Namen stehen in der Landkarte, aber nicht im Code: "
        + ", ".join(fehlend)
    )


def test_jede_kontrolle_ist_hart_oder_weich(kontrollen):
    """Die Unterscheidung ist die Aussage der Liste, nicht Beiwerk."""
    falsch = [(ort, wie) for _, ort, _, wie in kontrollen
              if wie not in ("hart", "weich")]
    assert not falsch, f"weder hart noch weich: {falsch}"


def test_jede_schicht_der_strecke_kommt_vor(kontrollen):
    """Eine Schicht ohne Kontrolle waere ein Befund, kein Versehen."""
    erwartet = {"Ingestion", "Ablage", "Silver", "Gold", "Serving",
                "Orchestrierung"}
    vorhanden = {schicht for schicht, _, _, _ in kontrollen}
    assert erwartet <= vorhanden, f"ohne Kontrolle: {sorted(erwartet - vorhanden)}"


def test_keine_kontrolle_steht_doppelt(kontrollen):
    orte = [ort for _, ort, _, _ in kontrollen]
    doppelt = sorted({o for o in orte if orte.count(o) > 1})
    assert not doppelt, f"mehrfach in der Landkarte: {doppelt}"


def test_das_publish_gate_ist_als_hart_gefuehrt(kontrollen):
    """Die einzige Kontrolle, die eine Veroeffentlichung verhindert.

    Sie als weich zu fuehren waere die Art Fehler, die ein Leser uebernimmt,
    ohne sie nachzupruefen.
    """
    gate = [k for k in kontrollen if k[1].endswith("pruefe_gate")]
    assert gate, "das Publish-Gate fehlt in der Landkarte"
    assert all(k[3] == "hart" for k in gate), gate


def test_das_notebook_speichert_keine_ausgaben(zellen):
    """So halten es die uebrigen zwoelf auch - sonst waere jeder Lauf ein Diff."""
    mit = [i for i, z in enumerate(zellen)
           if z["cell_type"] == "code" and z.get("outputs")]
    assert not mit, f"Zellen mit gespeicherter Ausgabe: {mit}"


def test_das_notebook_braucht_keine_gebauten_daten(zellen):
    """Es erzeugt seine Beispiele selbst und laeuft deshalb ueberall.

    Ein Griff nach ``data/`` waere kein Fehler, machte das Notebook aber von
    einem Stand abhaengig, den ein frischer Klon nicht hat.
    """
    verdaechtig = []
    for i, zelle in enumerate(zellen):
        if zelle["cell_type"] != "code":
            continue
        text = "".join(zelle["source"])
        for muster in ('"data"', "'data'", 'PROJECT_ROOT / "data', "data/gold",
                       "data/silver", "data/bronze"):
            if muster in text:
                verdaechtig.append((i, muster))
    assert not verdaechtig, (
        f"greift auf gebaute Daten zu: {verdaechtig}. Das Notebook soll seine "
        "Beispiele selbst erzeugen."
    )


# --------------------------------------------------------------------------
# Die Landkarte gegen das, was docs/zaehlperspektiven.md ueber sie behauptet
# --------------------------------------------------------------------------
# Das Dokument eroeffnet seinen Abschnitt "Was die Pruefungen nicht beweisen"
# mit den Zahlen dieser Liste. Ein erster Entwurf sagte dort "42 Kontrollen,
# 31 davon brechen ab" - und war damit selbst ein Beispiel fuer das, wovor der
# Abschnitt warnt: Drei der 31 brechen naemlich nichts ab.

DOKUMENT = PROJECT_ROOT / "docs" / "zaehlperspektiven.md"

# Sie sind zu Recht als hart gefuehrt - "hart" ist die Einstufung der Sache,
# nicht ihrer Wirkung. Die beiden Konstanten sind die Schwellen, gegen die
# ``pruefe_gate`` und ``veraltete_quellen`` pruefen; ``gepinnte_laeufe``
# verhindert eine Loeschung, statt einen Bau abzubrechen.
OHNE_ABBRUCH = {
    "gold_pipeline.GATE_MINDESTENS",
    "orchestration.run_all.ERWARTETE_QUELLEN",
    "orchestration.aufraeumen.gepinnte_laeufe",
}


@pytest.fixture(scope="module")
def dokument() -> str:
    if not DOKUMENT.is_file():
        pytest.skip(f"{DOKUMENT} fehlt")
    return DOKUMENT.read_text(encoding="utf-8")


def zahl(text: str, muster: str) -> int:
    import re
    treffer = re.search(muster, text)
    assert treffer, f"nicht im Dokument gefunden: {muster}"
    return int(treffer.group(1))


def test_das_dokument_nennt_die_zahlen_der_landkarte(dokument, kontrollen):
    """Drei Zahlen, drei Stellen, an denen sie auseinanderlaufen koennen."""
    hart = [k for k in kontrollen if k[3] == "hart"]
    assert zahl(dokument, r"\*\*(\d+) Kontrollen\*\*") == len(kontrollen)
    assert zahl(dokument, r"(\d+) davon als hart") == len(hart)
    assert zahl(dokument, r"\*\*Abbrechen tun (\d+)\.\*\*") == len(hart) - len(OHNE_ABBRUCH)


def test_die_drei_ausnahmen_stehen_im_dokument(dokument, kontrollen):
    """Eine Zahl ohne die Namen dahinter waere nicht nachpruefbar."""
    for ort in sorted(OHNE_ABBRUCH):
        assert any(k[1] == ort and k[3] == "hart" for k in kontrollen), (
            f"{ort} steht nicht mehr als harte Kontrolle in der Landkarte"
        )
        assert f"`{ort.split('.')[-1]}`" in dokument, (
            f"{ort} wird im Dokument nicht als Ausnahme genannt"
        )


def test_die_beiden_schwellen_sind_wirklich_konstanten(kontrollen):
    """Wuerde eine davon zur Funktion, waere die Ausnahme keine mehr."""
    for ort in ("gold_pipeline.GATE_MINDESTENS",
                "orchestration.run_all.ERWARTETE_QUELLEN"):
        wert = aufloesen(ort)
        assert wert is not None, f"{ort} gibt es nicht mehr"
        assert not callable(wert), (
            f"{ort} ist jetzt aufrufbar - dann ist die Liste der Ausnahmen falsch"
        )


def test_gepinnte_laeufe_bricht_nichts_ab():
    """Sie schuetzt, sie beanstandet nicht - darauf beruht die Zahl 28."""
    import ast
    import inspect
    import textwrap
    quelle = textwrap.dedent(inspect.getsource(
        aufloesen("orchestration.aufraeumen.gepinnte_laeufe")))
    assert not any(isinstance(n, ast.Raise) for n in ast.walk(ast.parse(quelle))), (
        "gepinnte_laeufe wirft jetzt - dann bricht sie ab und gehoert zu den 28"
    )
