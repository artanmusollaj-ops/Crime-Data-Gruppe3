"""Haelt `docs/ausblick.md` an der Wirklichkeit fest.

Das Dokument besteht zur Haelfte aus Saetzen der Form *"hier fehlt etwas"*.
Genau die veralten, sobald jemand die Luecke schliesst - und dann steht in
einem Ausblick eine Aufgabe, die laengst erledigt ist. Dieselbe Drift, die
Tabelle 5.3 des Konzepts dreimal erwischt hat.

Geprueft wird deshalb: Solange das Dokument eine Luecke **behauptet**, muss
sie noch da sein. Wer eine schliesst, faellt hier durch und zieht den
Ausblick mit. Die Messwerte bleiben ungeprueft - sie tragen ein Datum und
beschreiben einen Stand, nicht eine Zusage.

Ist ein Punkt umgesetzt, verschwindet sein Waechter hier und die Zusage wird
dort geprueft, wo sie gilt: Die Herkunftskette (Punkt 1·A, erledigt am 14.9.)
haelt seither ``tests/gold_pipeline/test_build_gold.py`` fest.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUSBLICK = PROJECT_ROOT / "docs" / "ausblick.md"
QUELLE = PROJECT_ROOT / "src" / "crime"


@pytest.fixture(scope="module")
def text() -> str:
    assert AUSBLICK.exists(), f"{AUSBLICK} fehlt"
    return AUSBLICK.read_text(encoding="utf-8")


def code(*teile: str) -> str:
    return (QUELLE.joinpath(*teile)).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Die behaupteten Luecken
# --------------------------------------------------------------------------


def test_studienstaedte_ist_wirklich_doppelt_definiert(text):
    """Behauptet in Abschnitt 3. Wird es zusammengefuehrt, faellt der Satz."""
    if "doppelt definiert" not in text:
        pytest.skip("Das Dokument behauptet es nicht mehr")
    treffer = [
        p for p in ("gold_pipeline/__init__.py", "silver_pipeline/build_place.py")
        if "STUDIENSTAEDTE = " in code(*p.split("/"))
    ]
    assert len(treffer) == 2, (
        f"STUDIENSTAEDTE steht nur noch in {treffer} - der Ausblick sagt, es sei "
        "doppelt. Abschnitt 3 und die Reihenfolge in 5 anpassen."
    )


def test_der_s3_client_ist_wirklich_fest_verdrahtet(text):
    """Behauptet in Abschnitt 4: Region und Adressierungsstil sind fix."""
    if "fest verdrahtet" not in text:
        pytest.skip("Das Dokument behauptet es nicht mehr")
    backend = code("storage", "backend.py")
    assert 'region_name="us-east-1"' in backend, (
        "Die Region ist nicht mehr fest verdrahtet - Abschnitt 4 anpassen"
    )
    assert '"addressing_style": "path"' in backend, (
        "Der Adressierungsstil ist nicht mehr fest verdrahtet - Abschnitt 4 anpassen"
    )


def test_duckdb_hat_wirklich_keine_grenzen(text):
    """Behauptet in Abschnitt 3: kein memory_limit, keine threads-Einstellung."""
    if "memory_limit" not in text:
        pytest.skip("Das Dokument behauptet es nicht mehr")
    gesetzt = [
        str(p.relative_to(QUELLE))
        for p in QUELLE.rglob("*.py")
        if re.search(r"SET\s+(memory_limit|threads)", p.read_text(encoding="utf-8"))
    ]
    assert not gesetzt, (
        f"Es gibt jetzt Grenzen in {gesetzt} - Abschnitt 3 anpassen"
    )


def test_alle_quellen_haben_vertragsversionen(text):
    """Umgekehrter Waechter: Punkt 2 ist seit dem 14.9. gebaut.

    Vorher stand hier "nur fuer Detroit". Jetzt muessen es alle sein - wer
    eine Quelle ohne Vertrag laesst, macht aus einem erledigten Punkt wieder
    eine Luecke.
    """
    if "erledigt am 14.9." not in text:
        pytest.skip("Das Dokument fuehrt den Punkt nicht als erledigt")
    # Die drei Versionen liegen in drei Modulen - bronze_ und raw_ in
    # extract_detroit, window_ in detroit_arcgis. Gesucht wird deshalb im Paket.
    detroit = "".join(
        p.read_text(encoding="utf-8")
        for p in sorted((QUELLE / "detroit_pipeline").glob("*.py"))
    )
    fehlend = [v for v in ("bronze_contract_version", "raw_contract_version",
                           "window_contract_version") if v not in detroit]
    assert not fehlend, (
        f"Detroits Vertragsversionen {fehlend} sind weg - Abschnitt 2 verliert "
        "sein Vorbild"
    )
    ohne = [
        pfad for pfad in ("chicago_pipeline/download_chicago.py",
                          "census_pipeline/download_acs.py",
                          "census_pipeline/download_tiger.py",
                          "weather_pipeline/download_noaa.py")
        if "CONTRACT_VERSION" not in code(*pfad.split("/"))
    ]
    assert not ohne, (
        f"{ohne} haben keine Vertragsversion mehr - der Ausblick sagt, der "
        "Punkt sei erledigt"
    )


def test_die_herkunftskette_bleibt_geschlossen(text):
    """Umgekehrter Waechter: Punkt 1- A ist seit dem 14.9. gebaut.

    Das Dokument fuehrt ihn als erledigt - dann muss der Code es auch
    weiterhin tun. Wer ``herkunft_der_quelle`` entfernt, macht aus einem
    erledigten Punkt wieder eine Luecke, ohne es zu merken.
    """
    if "erledigt 14.9.2026" not in text:
        pytest.skip("Das Dokument fuehrt den Punkt nicht als erledigt")
    assert "def herkunft_der_quelle" in code("gold_pipeline", "build_gold.py"), (
        "Gold nennt seine Quelle wieder nur als Pfad - der Ausblick sagt, "
        "der Punkt sei erledigt"
    )
    assert "def eingabe_abdruck" in code("manifeste", "__init__.py"), (
        "Der Eingabe-Abdruck ist weg - Abschnitt 1 anpassen"
    )


def test_die_code_version_steht_in_den_manifesten(text):
    """Umgekehrter Waechter zu Vorschlag 1, gebaut am 14.9."""
    if "Code-Version in jedem Manifest" not in text:
        pytest.skip("Das Dokument fuehrt es nicht als erledigt")
    assert "def code_stand" in code("manifeste", "__init__.py"), (
        "code_stand ist weg - Abschnitt 2 anpassen"
    )
    gefunden = [
        str(p.relative_to(QUELLE))
        for p in QUELLE.rglob("*.py")
        if '"code_version": code_stand()' in p.read_text(encoding="utf-8")
    ]
    assert len(gefunden) >= 9, (
        f"nur {len(gefunden)} Manifeste tragen die Code-Version: {gefunden}"
    )


def test_aufraeumen_kennt_noch_keine_gepinnten_laeufe(text):
    """Stufe B aus Abschnitt 1."""
    if "Gepinnt bleibt" not in text:
        pytest.skip("Das Dokument schlaegt es nicht mehr vor")
    assert "gepinnt" not in code("orchestration", "aufraeumen.py").lower(), (
        "Das Aufraeumen kennt jetzt gepinnte Laeufe - Abschnitt 1, Stufe B ist erledigt"
    )


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


def test_die_verweise_zeigen_auf_vorhandene_dateien(text):
    """Ein Ausblick, der auf nichts zeigt, ist eine Behauptung."""
    fehlend = [
        z for z in re.findall(r"\]\(([a-z0-9_.-]+\.md)\)", text)
        if not (AUSBLICK.parent / z).exists()
    ]
    assert not fehlend, f"verlinkt, aber nicht vorhanden: {fehlend}"


def test_artans_punkte_sind_als_solche_gekennzeichnet(text):
    """Wer etwas beigetragen hat, soll es im Dokument wiederfinden."""
    assert text.count("Artan") >= 2, "Die Herkunft der beiden Punkte fehlt"


def test_das_konzept_verweist_auf_den_ausblick():
    konzept = (PROJECT_ROOT / "docs" / "ln1_konzept.md").read_text(encoding="utf-8")
    assert "ausblick.md" in konzept, "Kapitel 11 nennt den Ausblick nicht"
