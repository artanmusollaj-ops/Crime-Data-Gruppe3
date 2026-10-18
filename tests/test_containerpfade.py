"""Ein Pfad, der woanders gilt, wird nicht wie einer von hier behandelt.

**Der Fall.** ``tests/test_jupyter_abbild.py`` prueft, dass der
Arbeitsbereich des Analyse-Abbilds unmittelbar unter ``PROJECT_ROOT``
liegt - beides Pfade *im Container*, und der ist Linux. Geschrieben stand
dort ``Path(bereich).parent``. ``Path`` ist auf Windows ``WindowsPath``,
und dort hat ``/app/arbeit`` die Eltern ``\\app``: Der Test fiel am
17.10.2026 auf dem Windows-Laeufer um, obwohl das Dockerfile richtig war.
Dieselbe Ursache traf vier weitere Tests, zwei davon ueber
``docker-compose.srv01.yml``.

**Warum das spaet auffaellt.** Der Windows-Job laeuft nur auf ``main``, also
nach dem Merge. Ein Pfad aus einem Dockerfile oder einer Compose-Datei ist
auf Linux unter beiden Konventionen gleich - der Fehler ist dort
unsichtbar und hier strukturell sichtbar.

**Die Regel.** Wer eine Dockerfile- oder Compose-Datei liest, nimmt fuer
die Pfade daraus ``PurePosixPath``. ``Path`` bleibt erlaubt fuer
``Path(__file__)`` - das ist ein Pfad dieser Maschine und gehoert ihrer
Konvention.
"""

from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTS = PROJECT_ROOT / "tests"

#: Woran erkannt wird, dass eine Datei ueber fremde Pfade urteilt: Sie baut
#: einen Pfad **zu** einer dieser Dateien, also ``WURZEL / "Dockerfile"``.
#:
#: **Nicht am Vorkommen des Wortes.** Die erste Fassung nahm jede Datei, in
#: der "Dockerfile" oder "docker-compose" irgendwo stand - und meldete
#: ``test_architektur_dokument.py`` zweimal, wo die Namen in einem Kommentar
#: und in einer Ausnahmeliste stehen und die beiden ``Path``-Griffe echte
#: Pfade dieser Maschine sind (eine Chrome-Binaerdatei, ein Ordner). Ein
#: Waechter, der Richtiges meldet, wird abgeschaltet.
QUELLEN = ("Dockerfile", "docker-compose")

#: Was ``Path(...)`` trotzdem umschliessen darf: diese Datei selbst.
ERLAUBT = ("__file__",)


def liest_fremde_datei(baum: ast.AST) -> bool:
    """Baut dieser Baum einen Pfad auf ein Dockerfile oder eine Compose-Datei?"""
    for knoten in ast.walk(baum):
        if (isinstance(knoten, ast.BinOp) and isinstance(knoten.op, ast.Div)
                and isinstance(knoten.right, ast.Constant)
                and isinstance(knoten.right.value, str)
                and knoten.right.value.startswith(QUELLEN)):
            return True
    return False


def betroffene_dateien() -> list[Path]:
    treffer = []
    for datei in sorted(TESTS.rglob("test_*.py")):
        if liest_fremde_datei(ast.parse(datei.read_text(encoding="utf-8"))):
            treffer.append(datei)
    return treffer


def test_es_gibt_ueberhaupt_dateien_die_fremde_pfade_lesen():
    """Sonst prueft dieser Waechter nichts und bleibt trotzdem gruen."""
    assert len(betroffene_dateien()) >= 3, (
        "keine oder zu wenige Dateien lesen Dockerfile/Compose - dann ist "
        "die Erkennung kaputt, nicht das Projekt sauber")


def test_pfade_aus_dockerfile_und_compose_gehen_nicht_durch_path():
    fehler = []
    for datei in betroffene_dateien():
        baum = ast.parse(datei.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if not (isinstance(knoten, ast.Call)
                    and ast.unparse(knoten.func) == "Path"
                    and knoten.args):
                continue
            argument = ast.unparse(knoten.args[0])
            if any(marke in argument for marke in ERLAUBT):
                continue
            fehler.append(
                f"{datei.relative_to(PROJECT_ROOT)}:{knoten.lineno}: "
                f"Path({argument}) - ein Pfad aus einem Dockerfile oder einer "
                f"Compose-Datei gilt im Container und damit unter POSIX. "
                f"PurePosixPath nehmen; auf Windows wird aus '/app/x' sonst "
                f"'\\\\app\\\\x'.")
    assert not fehler, "\n".join(fehler)
