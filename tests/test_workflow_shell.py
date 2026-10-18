"""Jeder ``run:``-Block eines Workflows muss gueltige Shell sein.

Am 16.10.2026 scheiterte der Abbildbau auf GitHub an einer Zeile, die ich
beim Einfuegen zerschnitten hatte:

    /home/runner/work/_temp/...sh: line 18: unexpected EOF while looking for
    matching `''
    Error: Process completed with exit code 2.

Ein fehlendes Anfuehrungszeichen. Die YAML-Syntax war in Ordnung, die
Formpruefung in ``test_abbilder_workflow.py`` war gruen - sie liest Text und
fragt nicht, ob er sich ausfuehren laesst. Gemerkt hat es erst der Runner,
nach vier Minuten Bau.

``bash -n`` kostet Millisekunden und beantwortet genau diese Frage.

**Warum die Platzhalter.** ``${{ github.sha }}`` ist Workflow-Syntax und
keine Shell; ``bash`` liest ``${{`` als Beginn einer Ersetzung und meldete
einen Fehler, den es nicht gibt. Ersetzt wird deshalb vor dem Pruefen - und
zwar durch ein Wort ohne Sonderzeichen, damit der Platzhalter selbst nichts
kaputtmacht.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((PROJECT_ROOT / ".github" / "workflows").glob("*.yml"))

#: Workflow-Ausdruecke, die vor der Shell-Pruefung weichen.
AUSDRUCK = re.compile(r"\$\{\{[^}]*\}\}")

#: Welche Schale ein Schritt benutzt, wenn er nichts sagt. Fuer ``shell:
#: python`` oder ``pwsh`` ist ``bash -n`` die falsche Frage.
GEPRUEFTE_SCHALEN = {None, "bash", "sh"}


def schritte() -> list[tuple[str, str, str]]:
    """(Workflow, Schrittname, Skript) fuer jeden ``run:``-Block."""
    yaml = pytest.importorskip("yaml")
    gefunden = []
    for pfad in WORKFLOWS:
        inhalt = yaml.safe_load(pfad.read_text(encoding="utf-8"))
        for job in (inhalt.get("jobs") or {}).values():
            for schritt in job.get("steps") or []:
                skript = schritt.get("run")
                if skript and schritt.get("shell") in GEPRUEFTE_SCHALEN:
                    gefunden.append(
                        (pfad.name, schritt.get("name", "(ohne Namen)"), skript))
    return gefunden


def test_es_gibt_workflows_mit_run_bloecken():
    """Sonst prueft die Datei nichts und bleibt trotzdem gruen."""
    assert WORKFLOWS, "keine Workflows gefunden"
    assert len(schritte()) >= 5, "verdaechtig wenige run-Bloecke"


@pytest.mark.parametrize(
    "workflow,name,skript", schritte(),
    ids=lambda w: w if isinstance(w, str) and not w.startswith("#") else "")
def test_jeder_run_block_ist_gueltige_shell(
        workflow, name, skript, benutzbares_bash):
    fertig = subprocess.run(
        ["bash", "-n"], input=AUSDRUCK.sub("PLATZHALTER", skript),
        capture_output=True, text=True)
    assert fertig.returncode == 0, (
        f"{workflow} / {name}: der Block ist keine gueltige Shell - "
        f"der Runner merkt es erst nach dem Bau.\n{fertig.stderr.strip()}")


def test_kein_workflow_setzt_ein_zweites_q_vor_pytest():
    """Zwei ``-q`` schweigen, und dann fehlt die Zahl, um die es geht.

    ``pyproject.toml`` setzt ``-q`` in ``addopts``. Ein zweites auf der
    Kommandozeile macht pytest **doppelt** still: Die Schlusszeile
    *„N passed, M skipped, K deselected"* faellt weg. Genau sie fehlte am
    18.10.2026 in jedem CI-Protokoll - waehrend vier Waechter meldeten, die
    dokumentierte Testzahl stimme nicht mit der gesammelten ueberein. Der
    Lauf stritt ueber eine Zahl, die er selbst nicht nannte.

    Dasselbe hat mich im Arbeitsbaum eine Viertelstunde gekostet: Ein
    ``python -m pytest -q`` lieferte keine Zusammenfassung, und ich hielt es
    erst fuer einen kaputten Reporter.
    """
    treffer = [(workflow, name, zeile.strip())
               for workflow, name, skript in schritte()
               for zeile in skript.splitlines()
               # ``--quiet`` und ``-qq`` mit: Die erste Fassung suchte nur
               # ``-q`` und liess beide durch - eine Mutationsprobe hat es
               # gezeigt. Ein in ein Buendel gefaltetes ``-qrs`` faengt sie
               # nicht; so ruft es hier niemand, und ein Muster dafuer
               # wuerde auch ``-rs`` melden.
               if "pytest" in zeile
               and re.search(r"(?<!\S)(-q+|--quiet)(?!\S)", zeile)]
    assert not treffer, (
        "addopts in pyproject.toml setzt bereits -q; ein zweites unterdrueckt "
        "die Schlusszeile mit der Testzahl:\n"
        + "\n".join(f"  {w} / {n}: {z}" for w, n, z in treffer))
