"""Prueft ``notebooks/34_gold_sternschema.ipynb`` ohne gebaute Daten.

Das Notebook belegt zwei Entscheidungen der Gold-Schicht und baut seit dem
17.9.2026 beide Bauweisen wirklich - den Stern und die beiden verworfenen
Wuerfel. Ausfuehren kann es nur, wer Silver und Gold gebaut hat; deshalb faehrt
es im woechentlichen Datenlauf.

**Warum es zusaetzlich hier geprueft wird.** Am 14.9.2026 um 12:34 UTC wurde
die doppelte Zuordnung GEOID -> Stadtname entflochten (9d287a1): ``silver``
fuehrt seither ``STUDIENSTAEDTE`` mit ``'Chicago'``, ``gold`` den abgeleiteten
``STADT_SCHLUESSEL`` mit ``'chicago'``. Das Notebook importierte weiter
``STUDIENSTAEDTE`` und griff mit ``werte['chicago']`` zu - ein ``KeyError``,
der den ganzen hinteren Teil des Notebooks totlegte. Der Datenlauf jenes Tages
lief um 06:05 UTC, also sechs Stunden davor, und der naechste ist montags.
Drei Tage lang war ein Beleg der Abgabe kaputt, ohne dass etwas rot wurde.

Der Kommentar an ``STADT_SCHLUESSEL`` hatte genau das vorhergesagt: *"Wer die
falsche importierte, bekam stillschweigend etwas anderes."*
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = PROJECT_ROOT / "notebooks" / "34_gold_sternschema.ipynb"
QUELLE = PROJECT_ROOT / "src" / "crime"

if str(QUELLE) not in sys.path:
    sys.path.insert(0, str(QUELLE))

# Spalten, die in Silver und Gold kleingeschriebene Stadtnamen tragen.
KLEIN_GESCHRIEBEN = ("t.city", "f.reporting_city", "reporting_city", "WHERE t.city")


@pytest.fixture(scope="module")
def zellen() -> list[dict]:
    if not NOTEBOOK.is_file():
        pytest.skip(f"{NOTEBOOK} fehlt")
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


@pytest.fixture(scope="module")
def code(zellen) -> str:
    return "\n".join("".join(z["source"]) for z in zellen if z["cell_type"] == "code")


@pytest.fixture(scope="module")
def text(zellen) -> str:
    return "\n".join("".join(z["source"]) for z in zellen)


def test_jeder_importierte_name_existiert(code):
    """Der allgemeine Fall: eine umbenannte Konstante faellt hier auf.

    Gelesen wird der AST, nicht der Text - ein Import in einer Zelle sieht
    genauso aus wie einer in einer Datei.
    """
    fehlend = []
    for zeile in code.splitlines():
        if not zeile.strip().startswith("from "):
            continue
        try:
            knoten = ast.parse(zeile.strip()).body[0]
        except SyntaxError:
            continue
        if not isinstance(knoten, ast.ImportFrom) or not knoten.module:
            continue
        if knoten.module.split(".")[0] not in {
            "silver_pipeline", "gold_pipeline", "storage", "manifeste",
            "orchestration", "serving",
        }:
            continue
        modul = importlib.import_module(knoten.module)
        fehlend += [f"{knoten.module}.{a.name}" for a in knoten.names
                    if not hasattr(modul, a.name)]
    assert not fehlend, (
        "diese Namen importiert das Notebook, aber es gibt sie nicht mehr: "
        + ", ".join(fehlend)
    )


def test_die_beiden_zuordnungen_unterscheiden_sich_wirklich():
    """Ohne diesen Unterschied waere der Test darunter sinnlos.

    Faende jemand die Doppelung stoerend und gliche die Schreibweise an, darf
    dieser Test auffallen - dann ist die Falle weg und die Pruefung kann es
    auch sein.
    """
    from gold_pipeline import STADT_SCHLUESSEL
    from silver_pipeline import STUDIENSTAEDTE

    assert set(STADT_SCHLUESSEL) == set(STUDIENSTAEDTE), (
        "die beiden Zuordnungen bilden nicht mehr dieselben GEOIDs ab"
    )
    assert set(STADT_SCHLUESSEL.values()) != set(STUDIENSTAEDTE.values()), (
        "beide tragen jetzt dieselben Werte - die Falle ist weg"
    )
    assert all(n == n.lower() for n in STADT_SCHLUESSEL.values())


def test_das_notebook_filtert_mit_dem_kleingeschriebenen_schluessel(code):
    """Der Fehler, fuer den es diese Datei gibt.

    ``STUDIENSTAEDTE`` darf im Notebook vorkommen - im Kommentar, der erklaert,
    warum es die falsche ist. Als **Wert** darf es nicht benutzt werden,
    solange das Notebook gegen kleingeschriebene Stadtspalten vergleicht.
    """
    benutzt = [z for z in code.splitlines()
               if "STUDIENSTAEDTE" in z and not z.lstrip().startswith("#")]
    assert not benutzt, (
        "das Notebook benutzt STUDIENSTAEDTE ('Chicago'), vergleicht aber gegen "
        "kleingeschriebene Stadtspalten. Richtig ist STADT_SCHLUESSEL. "
        "Betroffen: " + " | ".join(z.strip() for z in benutzt)
    )
    assert any(muster in code for muster in KLEIN_GESCHRIEBEN), (
        "das Notebook vergleicht nicht mehr gegen Stadtspalten - dann gilt "
        "diese Pruefung nicht mehr und kann weg"
    )
    assert "STADT_SCHLUESSEL" in code


def test_die_verworfenen_wuerfel_werden_wirklich_gebaut(code):
    """Seit dem 17.9.2026 ist die Ablehnung vorgefuehrt, nicht behauptet.

    Vorher zaehlte das Notebook nur, wie viele Zeilen die Wuerfel *haetten*.
    Fuer einen Leistungsnachweis ist der Unterschied zwischen einer Messung
    und einem gebauten Gegenentwurf genau der Punkt.
    """
    for wuerfel in ("fact_tract_month", "fact_city_day"):
        assert f"CREATE OR REPLACE TABLE {wuerfel}" in code, (
            f"{wuerfel} wird nicht mehr gebaut - dann ist die Ablehnung wieder "
            "eine Behauptung"
        )


def test_die_wuerfel_bleiben_im_notebook(code):
    """Gebaut zum Vorfuehren, nicht zum Ablegen - jedenfalls nicht in Gold.

    Seit dem 17.9.2026 gibt es in *Serving* vier Vergleichstabellen aus
    ``build_comparison``. Die beiden hier sind die urspruenglich geplanten
    Wuerfel und bleiben ein Beleg: Gold aggregiert nicht (Konzept 5.2).
    """
    assert "data/gold" not in code and "dataset=fact_tract_month" not in code
    gold = PROJECT_ROOT / "data" / "gold"
    if gold.is_dir():
        gebaut = {p.name for p in gold.iterdir() if p.is_dir()}
        verboten = {"dataset=fact_tract_month", "dataset=fact_city_day"}
        assert not (gebaut & verboten), f"in Gold gelandet: {sorted(gebaut & verboten)}"


def test_die_gegenprobe_der_wuerfel_steht_drin(code):
    """Ein Wuerfel ist nicht falsch, er ist aermer - das muss nachgerechnet sein."""
    assert "Gegenprobe" in code and "summieren sich auf" in code


def test_das_notebook_speichert_keine_ausgaben(zellen):
    """So halten es die uebrigen dreizehn auch."""
    mit = [i for i, z in enumerate(zellen)
           if z["cell_type"] == "code" and z.get("outputs")]
    assert not mit, f"Zellen mit gespeicherter Ausgabe: {mit}"


def test_die_abschnitte_sind_fortlaufend_nummeriert(text):
    """Beim Einfuegen von 2.1 ist die alte 2.1 zur 2.2 geworden."""
    unter = re.findall(r"^### (\d+)\.(\d+) ", text, re.M)
    je_abschnitt: dict[str, list[int]] = {}
    for haupt, neben in unter:
        je_abschnitt.setdefault(haupt, []).append(int(neben))
    for haupt, nummern in je_abschnitt.items():
        assert nummern == list(range(1, len(nummern) + 1)), (
            f"Abschnitt {haupt} ist nicht fortlaufend nummeriert: {nummern}"
        )
