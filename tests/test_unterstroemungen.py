"""Haelt die Unterstroemungs-Tabellen gegen die Artefakte, die sie behaupten.

Die Tabellen beschreiben je Unterstroemung, was umgesetzt ist und was fehlt.
Die in ``ln1_konzept.md`` ist dreimal veraltet, waehrend die Arbeit lief, die
sie beschreibt: ein Feldkatalog als Luecke, den es schon gab; eine
Orchestrierung als "bewusst offen", die gebaut war. Genau die Sorte Drift, die
bei den Zahlen dreimal passiert ist - nur in Worten.

**Warum hier zwei Dokumente stehen.** Dieselbe Tabelle gibt es ein zweites Mal,
in ``leistungsnachweise.md``. Sie war vom Waechter nicht erfasst - und genau
dort ist am 15.9.2026 wieder passiert, wogegen es ihn gibt: acht ueberholte
Aussagen auf einmal. "Keine CI", waehrend fuenf Jobs liefen. Ein
Architekturdiagramm als Luecke, das seit Wochen erzeugt wird. Orchestrierung
als *"groesste Luecke: heute manuelle Aufrufe"*, waehrend ``run_all`` dreizehn
Stufen faehrt. Das Dokument widersprach sich dabei selbst: Abschnitt 1 sagte
"Silver ist leer", zwei Zeilen darueber standen 347'957 Zeilen.

Ein Waechter, der nur eine von zwei gleichen Tabellen prueft, laesst die
andere genau so veralten wie die erste.

Woerter lassen sich nicht gegen Parquet halten. Aber jede Zeile behauptet oder
vermisst etwas, das als Datei existiert oder nicht. Das ist pruefbar:

* Was die Spalte *Umsetzung* nennt, muss es geben.
* Was die Spalte *Luecke* nennt, darf es nicht geben.

Geprueft wird ausserdem die Lebenszyklus-Tabelle in ``leistungsnachweise.md``
- vier Spalten statt drei, dieselbe Frage.

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
NACHWEISE = PROJECT_ROOT / "docs" / "intern" / "leistungsnachweise.md"

# Dokument -> (Ueberschrift der Unterstroemungs-Tabelle, erwartete Zeilenzahl).
TABELLEN: dict[str, tuple[Path, str]] = {
    "ln1_konzept 5.3": (KONZEPT, "### 5.3 Unterströmungen"),
    "leistungsnachweise 3": (NACHWEISE, "### Unterströmungen"),
}

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
    "architekturbilder": PROJECT_ROOT / "docs" / "bilder" / "architektur-pakete.svg",
    "architekturbild": PROJECT_ROOT / "docs" / "bilder" / "architektur-pakete.svg",
    "seaweedfs": PROJECT_ROOT / "src" / "crime" / "storage" / "__init__.py",
    "requirements.lock": PROJECT_ROOT / "requirements.lock",
    "lockfile": PROJECT_ROOT / "requirements.lock",
    "ruff": PROJECT_ROOT / "pyproject.toml",   # plus [tool.ruff], siehe unten
    "gesamtmanifest": PROJECT_ROOT / "src" / "crime" / "orchestration" / "run_all.py",
    "mapping_status": PROJECT_ROOT / "src" / "crime" / "gold_pipeline" / "__init__.py",
    "geo_status": PROJECT_ROOT / "src" / "crime" / "gold_pipeline" / "__init__.py",
    "publish-gate": PROJECT_ROOT / "src" / "crime" / "gold_pipeline" / "__init__.py",
    "notebook 11": PROJECT_ROOT / "notebooks" / "11_detroit_source.ipynb",
    "notebook 13": PROJECT_ROOT / "notebooks" / "13_detroit_data_quality.ipynb",
    "storage-architektur": PROJECT_ROOT / "docs" / "storage-architektur.md",
    "architektur.md": PROJECT_ROOT / "docs" / "architektur.md",
    "referenz": PROJECT_ROOT / "docs" / "referenz" / "index.html",
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
    "kein diagramm": "architekturbilder",
    # Dazugekommen am 15.9.2026, alle acht aus leistungsnachweise.md.
    "manuelle aufrufe": "run_all",
    "keine reihenfolge": "run_all",
    "keine wiederholbarkeit": "run_all",
    "keine zeitplanung": "datenlauf",
    "architekturdiagramm": "architekturbilder",
    "katalog/glossar der felder": "feldkatalog",
    "qualitätsanalyse detroit": "notebook 13",
    "detroit-quellnotebook": "notebook 11",
    # Der Feldkatalog wird aus den Manifesten gebauter Tabellen erzeugt. Gaebe
    # es Silver und Gold nicht, gaebe es ihn auch nicht - er ist damit der
    # versionierte Beleg fuer eine Aussage ueber Daten, die selbst nicht
    # versioniert sind.
    "silver/gold leer": "feldkatalog",
}


def tabelle_lesen(pfad: Path, ueberschrift: str) -> dict[str, tuple[str, str]]:
    """Die Zeilen einer Unterstroemungs-Tabelle: Name -> (Umsetzung, Luecke)."""
    text = pfad.read_text(encoding="utf-8")
    anfang = text.index(ueberschrift)
    ende = text.index("\n---\n", anfang)
    gefunden = {}
    for zeile in text[anfang:ende].splitlines():
        m = re.match(r"^\| \*\*(.+?)\*\* \| (.+?) \| (.+?) \|$", zeile)
        if m:
            gefunden[m.group(1)] = (m.group(2), m.group(3))
    assert len(gefunden) == 6, (
        f"{pfad.name}: erwartet sechs Unterstroemungen, gefunden {list(gefunden)}"
    )
    return gefunden


# Saetze im Fliesstext, die etwas als offen fuehren, das es gibt. Exakte
# Formulierungen, keine Suchmuster: Dieselben Dokumente erwaehnen vergangene
# Luecken absichtlich ("das stand als Luecke in Tabelle 5.3"), und ein
# unscharfer Treffer darauf waere ein falscher Alarm.
UEBERHOLTE_AUSSAGEN: dict[str, str] = {
    "Weiterhin offen: keine CI": "github actions",
    "Niemand führt diese Tests bei einem Push aus": "github actions",
}

ABGABEDOKUMENTE = (KONZEPT, NACHWEISE, PROJECT_ROOT / "docs" / "intern" / "projektabsprache.md")


def test_kein_fliesstext_fuehrt_etwas_als_offen_das_es_gibt():
    """Die Tabellen sind nicht die einzige Stelle, an der so etwas veraltet.

    ``projektabsprache.md`` fuehrte noch am 15.9.2026 *"Weiterhin offen: keine
    CI. Niemand fuehrt diese Tests bei einem Push aus"* - drei Tage nachdem
    die CI stand und waehrend sie denselben Satz gerade pruefte.
    """
    veraltet = [
        f"{pfad.name}: sagt '{satz}', aber {ARTEFAKTE[stichwort].name} existiert"
        for pfad in ABGABEDOKUMENTE
        for satz, stichwort in UEBERHOLTE_AUSSAGEN.items()
        if satz in pfad.read_text(encoding="utf-8") and ARTEFAKTE[stichwort].exists()
    ]
    assert not veraltet, veraltet


@pytest.fixture(scope="module", params=sorted(TABELLEN))
def benannte_zeilen(request) -> tuple[str, dict[str, tuple[str, str]]]:
    """Beide Tabellen, je einmal - mit ihrem Namen fuer die Fehlermeldung."""
    pfad, ueberschrift = TABELLEN[request.param]
    return request.param, tabelle_lesen(pfad, ueberschrift)


@pytest.fixture(scope="module")
def zeilen(benannte_zeilen) -> dict[str, tuple[str, str]]:
    return benannte_zeilen[1]


def test_jede_umsetzung_hat_ihr_artefakt(benannte_zeilen):
    """Was die Tabelle als gebaut nennt, muss als Datei da sein."""
    woher, zeilen = benannte_zeilen
    fehlend = []
    for name, (umsetzung, _) in zeilen.items():
        klein = umsetzung.lower()
        for stichwort, pfad in ARTEFAKTE.items():
            if stichwort in klein and not pfad.exists():
                fehlend.append(f"{woher}, {name}: nennt '{stichwort}', aber {pfad.name} fehlt")
    assert not fehlend, fehlend


def test_ruff_ist_konfiguriert_wenn_die_tabelle_es_nennt(zeilen):
    """'ruff' im Text reicht nicht - die Konfiguration muss stehen."""
    genannt = any("ruff" in u.lower() for u, _ in zeilen.values())
    if not genannt:
        pytest.skip("die Tabelle nennt ruff nicht")
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "[tool.ruff" in pyproject, "die Tabelle nennt ruff, pyproject.toml kennt es nicht"


def test_keine_luecke_nennt_etwas_das_es_gibt(benannte_zeilen):
    """Die Drift, die dreimal passiert ist: eine Luecke, die laengst geschlossen war."""
    woher, zeilen = benannte_zeilen
    assert not _veraltete_luecken(
        {name: luecke for name, (_, luecke) in zeilen.items()}, woher
    )


def test_keine_luecke_im_lebenszyklus_nennt_etwas_das_es_gibt():
    """Dieselbe Frage an die vierspaltige Tabelle in ``leistungsnachweise.md``.

    Dort standen am 15.9.2026 gleich drei ueberholte Luecken: ein
    Detroit-Quellnotebook, das es seit Monaten gibt, eine Qualitaetsanalyse
    Detroit ebenso, und "Silver/Gold leer" - zwei Zeilen unter einer Zahl, die
    347'957 Silver-Zeilen nennt.
    """
    text = NACHWEISE.read_text(encoding="utf-8")
    anfang = text.index("| Phase | Was wir haben | Beleg | Lücke |")
    ende = text.index("### Unterströmungen", anfang)
    luecken = {}
    for zeile in text[anfang:ende].splitlines():
        m = re.match(r"^\| \*\*(.+?)\*\* \| (.+?) \| (.+?) \| (.+?) \|$", zeile)
        if m:
            luecken[m.group(1)] = m.group(4)
    assert len(luecken) == 5, f"erwartet fuenf Phasen, gefunden {list(luecken)}"
    assert not _veraltete_luecken(luecken, "leistungsnachweise, Lebenszyklus")


def _veraltete_luecken(luecken: dict[str, str], woher: str) -> list[str]:
    """Jede Luecke, die etwas vermisst, das im Repository liegt."""
    return [
        f"{woher}, {name}: Luecke sagt '{formulierung}', aber "
        f"{ARTEFAKTE[stichwort].name} existiert"
        for name, luecke in luecken.items()
        for formulierung, stichwort in UEBERHOLTE_LUECKEN.items()
        if formulierung in luecke.lower() and ARTEFAKTE[stichwort].exists()
    ]


def test_die_testzahl_in_der_tabelle_stimmt(benannte_zeilen):
    """Dieselbe Zahl wie im README und in AENDERUNGEN.md - jetzt an vier Stellen."""
    woher, zeilen = benannte_zeilen
    umsetzung, _ = zeilen["DataOps"]
    m = re.search(r"([0-9']+) (?:automatisierte )?Tests", umsetzung)
    assert m, f"{woher}: die DataOps-Zeile nennt keine Testzahl"
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
        f"{woher} nennt {genannt} Tests, gesammelt werden {treffer.group(1)}"
    )


# --------------------------------------------------------------------------
# Verantwortliche je Datensatz (Absprache 7.3)
# --------------------------------------------------------------------------

ABSPRACHE = PROJECT_ROOT / "docs" / "intern" / "projektabsprache.md"


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
