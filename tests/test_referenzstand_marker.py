"""Der Marker ``referenzstand`` und was der Standardlauf mit ihm tut.

Am 18.9.2026 meldete ``python -m pytest`` **34 Fehlschlaege**. Keiner davon war
ein Fehler: Alle 34 hielten eine dokumentierte Zahl gegen die *gebauten* Daten,
und die Daten waren seit dem gepinnten Referenzstand weitergelaufen. Ein
normaler Zwischenzustand - aber er liess die Suite rot aussehen und haette
einen echten Fehlschlag darin verschwinden lassen.

Seither waehlt der Standardlauf den Marker ab. Die Waechter sind nicht
abgeschaltet, sondern brauchen einen eigenen Aufruf:

    python -m pytest                     alles ausser dem Referenzstand
    python -m pytest -m referenzstand    genau diese Waechter
    python -m pytest -m ""               beides zusammen

Diese Datei haelt genau das fest. Ohne sie waere die Abwahl eine Zeile in
``pyproject.toml``, die jemand entfernt oder verschreibt, ohne dass es auffaellt
- und beides faellt in die falsche Richtung: Eine kaputte Markerangabe
(``-m "not referenzstadt"``) waehlt **nichts** ab, und die Suite waere wieder
rot; eine zu breite waehlt zu viel ab, und echte Waechter liefen nie mehr.
"""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MARKER = "referenzstand"


def sammelt(*zusatz: str) -> str:
    """Die Ausgabe eines eigenen ``--collect-only``-Prozesses.

    In einem eigenen Prozess, weil pytest sich nicht in sich selbst starten
    laesst. ``-p no:cacheprovider`` haelt ``.pytest_cache`` aus dem Repository.

    **Kein eigenes ``-q``.** Das steht schon in ``addopts``; ein zweites macht
    daraus ``-qq``, und dann druckt pytest statt der Summenzeile nur noch die
    Zahlen je Datei. Genau darueber ist der erste Entwurf dieser Datei
    gestolpert - beide Tests uebersprangen sich stillschweigend.
    """
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only",
         "-p", "no:cacheprovider", *zusatz],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    ).stdout


def sammle(*zusatz: str) -> tuple[int, int]:
    """(ausgewaehlt, abgewaehlt) - die Summenzeile als zwei Zahlen."""
    ausgabe = sammelt(*zusatz)
    treffer = re.search(r"(\d+)/(\d+) tests collected \((\d+) deselected\)", ausgabe)
    if treffer:
        return int(treffer.group(1)), int(treffer.group(3))
    treffer = re.search(r"(\d+) tests? collected", ausgabe)
    if treffer is None:
        pytest.skip(f"Sammellauf lieferte keine Zahl: {ausgabe[-300:]}")
    return int(treffer.group(1)), 0


def test_der_standardlauf_waehlt_den_referenzstand_ab():
    """Die Zeile in pyproject.toml - und dass sie wirkt, nicht nur dasteht."""
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert f"-m 'not {MARKER}'" in pyproject, (
        "addopts in pyproject.toml muss den Marker abwaehlen"
    )
    _, abgewaehlt = sammle()
    assert abgewaehlt > 0, (
        "der Standardlauf waehlt nichts ab - ein verschriebener Markername "
        "waehlt stillschweigend nichts aus, und die Suite ist wieder rot"
    )


def test_der_eigene_aufruf_findet_genau_diese_waechter():
    """``-m referenzstand`` muss die Umkehrung des Standardlaufs sein."""
    standard, abgewaehlt = sammle()
    nur_marker, _ = sammle("-m", MARKER)
    assert nur_marker == abgewaehlt, (
        f"der Standardlauf waehlt {abgewaehlt} ab, '-m {MARKER}' sammelt "
        f"{nur_marker} - die beiden Aufrufe teilen die Suite nicht sauber"
    )
    assert nur_marker > 0, f"'-m {MARKER}' findet keinen einzigen Waechter"
    ganz, _ = sammle("-m", "")
    assert standard + nur_marker == ganz, (
        f"{standard} + {nur_marker} != {ganz} - zusammen muessen sie die "
        "ganze Suite sein, sonst faellt etwas zwischen die beiden Aufrufe"
    )


def test_die_abgewaehlten_bleiben_in_der_summenzeile_sichtbar():
    """Stumm abwaehlen waere der naechste Verwirrungsgrund.

    Geprueft wird nicht die Einstellung, sondern die **Ausgabe**: Wer sie
    irgendwann weiter beruhigt (``-qq``, ``--no-summary``), macht aus
    abgewaehlten Waechtern unsichtbare - und niemand bemerkt, dass sie seit
    Monaten nicht mehr gelaufen sind.
    """
    ausgabe = sammelt()
    assert "deselected" in ausgabe, (
        "die Summenzeile nennt die abgewaehlten Tests nicht mehr:\n"
        + ausgabe[-300:]
    )


def test_die_dokumente_nennen_den_eigenen_aufruf():
    """Ein abgewaehlter Test, dessen Aufruf nirgends steht, ist ein geloeschter."""
    fehlend = [name for name, pfad in (
        ("README.md", PROJECT_ROOT / "README.md"),
        ("AENDERUNGEN.md", PROJECT_ROOT / "docs" / "intern" / "AENDERUNGEN.md"),
    ) if f"pytest -m {MARKER}" not in pfad.read_text(encoding="utf-8")]
    assert not fehlend, f"nennt den Aufruf nicht: {fehlend}"


def test_der_datenlauf_bleibt_bei_seiner_eigenen_abwahl():
    """Der Workflow darf sich nicht auf die Vorgabe verlassen.

    ``datenlauf.yml`` nennt ``-m "not referenzstand"`` selbst. Das ist jetzt
    doppelt - und soll es bleiben: Was in GitHub Actions laeuft, soll in der
    Workflow-Datei stehen und nicht in einer Vorgabe, die drei Verzeichnisse
    weiter jemand aendert.
    """
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "datenlauf.yml")
    assert f'-m "not {MARKER}"' in workflow.read_text(encoding="utf-8")
