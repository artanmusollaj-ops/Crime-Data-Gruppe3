"""Haelt die Tabelle 5.3 in ``ln1_konzept.md`` gegen die Artefakte.

Die Tabelle beschreibt je Unterstroemung, was umgesetzt ist und was fehlt. Sie
ist dreimal veraltet, waehrend die Arbeit lief, die sie beschreibt: ein
Feldkatalog als Luecke, den es schon gab; eine Orchestrierung als "bewusst
offen", die gebaut war. Genau die Sorte Drift, die bei den Zahlen dreimal
passiert ist - nur in Worten.

Woerter lassen sich nicht gegen Parquet halten. Aber jede Zeile behauptet oder
vermisst etwas, das als Datei existiert oder nicht. Das ist pruefbar:

* Was die Spalte *Umsetzung* nennt, muss es geben.
* Was die Spalte *Luecke* nennt, darf es nicht geben.

Der Test kennt die Zuordnung Stichwort -> Artefakt. Kommt ein Artefakt dazu,
gehoert es hier eingetragen - dann faellt die Tabelle beim naechsten Mal nicht
mehr still zurueck.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
KONZEPT = PROJECT_ROOT / "docs" / "ln1_konzept.md"

# Stichwort in der Tabelle -> Datei, die es beweist. Klein geschrieben; die
# Suche ist unabhaengig von Gross- und Kleinschreibung.
ARTEFAKTE: dict[str, Path] = {
    "feldkatalog": PROJECT_ROOT / "docs" / "feldkatalog.md",
    "run_all": PROJECT_ROOT / "src" / "crime" / "orchestration" / "run_all.py",
    "orchestration.run_all": PROJECT_ROOT / "src" / "crime" / "orchestration" / "run_all.py",
    "github actions": PROJECT_ROOT / ".github" / "workflows" / "tests.yml",
    "datenlauf": PROJECT_ROOT / ".github" / "workflows" / "datenlauf.yml",
    "manifeste": PROJECT_ROOT / "src" / "crime" / "manifeste" / "__init__.py",
    "aufraeumen": PROJECT_ROOT / "src" / "crime" / "orchestration" / "aufraeumen.py",
    "drift": PROJECT_ROOT / "src" / "crime" / "orchestration" / "drift.py",
    "requirements.lock": PROJECT_ROOT / "requirements.lock",
    "lockfile": PROJECT_ROOT / "requirements.lock",
    "ruff": PROJECT_ROOT / "pyproject.toml",   # plus [tool.ruff], siehe unten
    "gesamtmanifest": PROJECT_ROOT / "src" / "crime" / "orchestration" / "run_all.py",
    "mapping_status": PROJECT_ROOT / "src" / "crime" / "gold_pipeline" / "__init__.py",
    "geo_status": PROJECT_ROOT / "src" / "crime" / "gold_pipeline" / "__init__.py",
    "publish-gate": PROJECT_ROOT / "src" / "crime" / "gold_pipeline" / "__init__.py",
}

# Was in der Spalte *Luecke* nicht mehr stehen darf, sobald es das Artefakt
# gibt. Die Formulierungen sind die, die tatsaechlich dort standen.
UEBERHOLTE_LUECKEN: dict[str, str] = {
    "feldkatalog": "feldkatalog",
    "bewusst offen": "run_all",
    "von hand in der richtigen reihenfolge": "run_all",
    "keine ci": "github actions",
    "kein lockfile": "lockfile",
    "kein linter": "ruff",
    "keine aufbewahrungsregel": "aufraeumen",
}


@pytest.fixture(scope="module")
def zeilen() -> dict[str, tuple[str, str]]:
    """Die sechs Zeilen der Tabelle: Name -> (Umsetzung, Luecke)."""
    text = KONZEPT.read_text(encoding="utf-8")
    anfang = text.index("### 5.3 Unterströmungen")
    ende = text.index("\n---\n", anfang)
    block = text[anfang:ende]
    gefunden = {}
    for zeile in block.splitlines():
        m = re.match(r"^\| \*\*(.+?)\*\* \| (.+?) \| (.+?) \|$", zeile)
        if m:
            gefunden[m.group(1)] = (m.group(2), m.group(3))
    assert len(gefunden) == 6, f"erwartet sechs Unterstroemungen, gefunden {list(gefunden)}"
    return gefunden


def test_jede_umsetzung_hat_ihr_artefakt(zeilen):
    """Was die Tabelle als gebaut nennt, muss als Datei da sein."""
    fehlend = []
    for name, (umsetzung, _) in zeilen.items():
        klein = umsetzung.lower()
        for stichwort, pfad in ARTEFAKTE.items():
            if stichwort in klein and not pfad.exists():
                fehlend.append(f"{name}: nennt '{stichwort}', aber {pfad.name} fehlt")
    assert not fehlend, fehlend


def test_ruff_ist_konfiguriert_wenn_die_tabelle_es_nennt(zeilen):
    """'ruff' im Text reicht nicht - die Konfiguration muss stehen."""
    genannt = any("ruff" in u.lower() for u, _ in zeilen.values())
    if not genannt:
        pytest.skip("die Tabelle nennt ruff nicht")
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.ruff" in pyproject, "die Tabelle nennt ruff, pyproject.toml kennt es nicht"


def test_keine_luecke_nennt_etwas_das_es_gibt(zeilen):
    """Die Drift, die dreimal passiert ist: eine Luecke, die laengst geschlossen war."""
    veraltet = []
    for name, (_, luecke) in zeilen.items():
        klein = luecke.lower()
        for formulierung, stichwort in UEBERHOLTE_LUECKEN.items():
            if formulierung in klein and ARTEFAKTE[stichwort].exists():
                veraltet.append(
                    f"{name}: Luecke sagt '{formulierung}', aber "
                    f"{ARTEFAKTE[stichwort].name} existiert"
                )
    assert not veraltet, veraltet


def test_die_testzahl_in_der_tabelle_stimmt(zeilen):
    """Dieselbe Zahl wie im README und in AENDERUNGEN.md - eine dritte Stelle."""
    umsetzung, _ = zeilen["DataOps"]
    m = re.search(r"([0-9']+) Tests", umsetzung)
    assert m, "die DataOps-Zeile nennt keine Testzahl"
    genannt = int(m.group(1).replace("'", ""))
    fertig = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-o", "addopts=",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    treffer = re.search(r"([0-9]+) tests? collected", fertig.stdout)
    if treffer is None:
        pytest.skip("Sammellauf lieferte keine Zahl")
    assert genannt == int(treffer.group(1)), (
        f"5.3 nennt {genannt} Tests, gesammelt werden {treffer.group(1)}"
    )


# --------------------------------------------------------------------------
# Verantwortliche je Datensatz (Absprache 7.3)
# --------------------------------------------------------------------------

ABSPRACHE = PROJECT_ROOT / "docs" / "projektabsprache.md"


def verantwortliche() -> dict[str, str]:
    """Die Tabelle in Absprache 7.3: Stufe -> Verantwortlicher.

    Eine Zeile kann mehrere Stufen nennen (``tract``, ``place``, ...); jede
    davon zaehlt einzeln.
    """
    text = ABSPRACHE.read_text(encoding="utf-8")
    anfang = text.index("Verantwortliche je Datensatz")
    ende = text.index("### 7.4", anfang)
    zeilen = re.findall(r"^\| (.+?) \| .+? \| .+? \| (.+?) \| .+? \|$",
                        text[anfang:ende], re.M)
    gefunden = {}
    for stufen, wer in zeilen:
        for stufe in re.findall(r"`([a-z_]+)`", stufen):
            gefunden[stufe] = wer.strip()
    return gefunden


def test_jede_stufe_des_run_controllers_hat_einen_verantwortlichen():
    """Die Luecke aus Tabelle 5.3: niemand war fuer einen Datensatz benannt.

    Gemessen wird gegen ``run_all.STUFEN`` - kommt eine Stufe dazu, faellt der
    Test, bis jemand sie in der Absprache uebernimmt.
    """
    import run_all

    benannt = verantwortliche()
    assert benannt, "keine Tabelle 'Verantwortliche je Datensatz' in Absprache 7.3"
    fehlend = [s.name for s in run_all.STUFEN if s.name not in benannt]
    assert not fehlend, f"Stufen ohne Verantwortlichen in Absprache 7.3: {fehlend}"


def test_jeder_verantwortliche_ist_einer_von_uns():
    """Ein Name, der nicht im Team ist, ist ein Tippfehler - oder eine Luecke."""
    fremd = {s: w for s, w in verantwortliche().items()
             if w not in {"Christian", "Artan", "beide"}}
    assert not fremd, f"unbekannte Verantwortliche: {fremd}"
