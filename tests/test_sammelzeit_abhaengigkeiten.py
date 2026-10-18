"""Was beim *Sammeln* fehlen kann, darf nicht undeklariert sein.

**Der Fall, der das ausgeloest hat.** ``tests/test_workflow_shell.py`` ruft
``pytest.importorskip("yaml")`` in einer Hilfsfunktion - und die steht in den
Argumentwerten eines ``@pytest.mark.parametrize``. Also laeuft sie nicht im
Test, sondern beim **Sammeln**, und ein ``Skipped`` dort nimmt nicht einen
Test heraus, sondern die ganze Datei: 23 Stueck.

PyYAML stand in keiner Abhaengigkeitsliste. Auf jedem Entwicklungsrechner war
es ueber irgendetwas anderes da, in GitHub Actions nicht - dort installiert
``requirements.txt`` genau die deklarierten Pakete. Folge: CI sammelte
dauerhaft **23 Tests weniger**, die vier Waechter ueber die dokumentierte
Testzahl verglichen ihre Zahl mit der kleineren, und der Pull-Request-Lauf war
vom 29.9. bis zum 18.10.2026 **auf jedem Lauf rot**. Drei Wochen, in denen ein
rotes CI nichts mehr bedeutete.

Der eigentliche Schaden war ein anderer: Die 23 pruefen die ``run:``-Bloecke
der Workflows durch ``bash -n``. Sie liefen ueberall - nur nicht dort, wo
diese Workflows ausgefuehrt werden.

**Was dieser Waechter deshalb prueft.** Jedes ``importorskip``, das beim
Sammeln greifen kann, muss auf ein Paket zeigen, das in ``pyproject.toml``
deklariert ist. ``importorskip`` **im Testkoerper** bleibt unberuehrt: Dort
ist es genau richtig - ein Test, der ohne ClickHouse nicht laufen kann, soll
sich ueberspringen und nicht die Datei mitnehmen.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS = PROJECT_ROOT / "tests"

#: Importname -> Name auf PyPI, wo beide auseinandergehen. Nur was gebraucht
#: wird; ein leerer Eintrag hier macht den Waechter stumm, kein Automatismus.
VERTEILUNG = {"yaml": "pyyaml"}


def _deklariert() -> set[str]:
    """Alle Abhaengigkeiten aus ``pyproject.toml``, normalisiert."""
    daten = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))
    projekt = daten["project"]
    roh = list(projekt.get("dependencies", []))
    for liste in projekt.get("optional-dependencies", {}).values():
        roh.extend(liste)
    # Vom Namen bis zum ersten Vergleichs-, Klammer- oder Trennzeichen.
    return {re.split(r"[<>=!~\[; ]", eintrag, maxsplit=1)[0].strip().lower()
            for eintrag in roh}


def _sammelzeit_aufrufe(quelle: str) -> set[str]:
    """Die ``importorskip``-Ziele, die beim Sammeln erreicht werden.

    Erreicht wird, was auf Modulebene steht - und was in einer Funktion
    steht, deren Name in einem ``parametrize`` auftaucht: Dessen
    Argumentwerte werden beim Sammeln ausgewertet.
    """
    baum = ast.parse(quelle)

    # Namen, die in einem parametrize-Dekorator vorkommen. Grob mit Absicht:
    # Ein Name zu viel macht den Waechter strenger, nicht blinder.
    aus_dekorator: set[str] = set()
    for knoten in ast.walk(baum):
        if not isinstance(knoten, ast.Call):
            continue
        name = ast.unparse(knoten.func)
        if "parametrize" not in name:
            continue
        for teil in ast.walk(knoten):
            if isinstance(teil, ast.Name):
                aus_dekorator.add(teil.id)

    ziele: set[str] = set()

    def besuche(knoten: ast.AST, in_funktion: str | None) -> None:
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef)):
                besuche(kind, kind.name)
                continue
            if (isinstance(kind, ast.Call)
                    and ast.unparse(kind.func).endswith("importorskip")
                    and kind.args
                    and isinstance(kind.args[0], ast.Constant)
                    and (in_funktion is None or in_funktion in aus_dekorator)):
                ziele.add(kind.args[0].value)
            besuche(kind, in_funktion)

    besuche(baum, None)
    return ziele


def test_jedes_sammelzeit_importorskip_zeigt_auf_eine_deklarierte_abhaengigkeit():
    deklariert = _deklariert()
    fehler = []
    for datei in sorted(TESTS.rglob("test_*.py")):
        for ziel in sorted(_sammelzeit_aufrufe(datei.read_text("utf-8"))):
            paket = VERTEILUNG.get(ziel, ziel).lower()
            if paket not in deklariert:
                fehler.append(
                    f"{datei.relative_to(PROJECT_ROOT)}: importorskip({ziel!r}) "
                    f"greift beim Sammeln, aber '{paket}' steht in keiner "
                    f"Abhaengigkeitsliste - fehlt es, verschwindet die ganze "
                    f"Datei aus der Sammlung")
    assert not fehler, "\n".join(fehler)


def test_die_sammelzeit_pakete_sind_hier_auch_wirklich_da():
    """Deklariert heisst nicht installiert.

    Der Waechter darueber liest ``pyproject.toml``; dieser hier fragt den
    Interpreter. Beides zusammen heisst: Die Testzahl dieses Laufs ist
    dieselbe, die ein anderer Rechner misst.
    """
    fehlen = []
    for datei in sorted(TESTS.rglob("test_*.py")):
        for ziel in sorted(_sammelzeit_aufrufe(datei.read_text("utf-8"))):
            if importlib.util.find_spec(ziel) is None:
                fehlen.append(f"{datei.relative_to(PROJECT_ROOT)}: {ziel}")
    assert not fehlen, (
        "nicht installiert, also sammelt dieser Lauf weniger Tests als "
        "dokumentiert: " + ", ".join(fehlen))
