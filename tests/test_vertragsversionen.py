"""Jede Vertragsversion muss erklaert sein.

Eine Versionsnummer ohne Begruendung ist schlimmer als keine: Sie sieht nach
Ordnung aus. Steht in einem Jahr eine 3 im Manifest und niemand weiss, wofuer,
hat die Zahl nichts geleistet - ausser Vertrauen zu erwecken.

Geprueft wird deshalb beides: dass jede Quelle und jede abgeleitete Tabelle
eine Version **hat**, und dass genau diese Zahl im Register unter
"Vertragsversionen" in AENDERUNGEN.md **steht**. Wer eine Version erhoeht und
das Register vergisst, faellt hier durch.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AENDERUNGEN = PROJECT_ROOT / "docs" / "AENDERUNGEN.md"

# Datensatz im Register -> Modul, das seinen Vertrag haelt. Beide
# TIGER-Auslieferungen kommen aus demselben Modul und teilen sich die Version.
MODULE = {
    "bronze/city=chicago": "chicago_pipeline.download_chicago",
    "bronze/city=detroit": "detroit_pipeline.extract_detroit",
    "bronze/dataset=tiger_tract": "census_pipeline.download_tiger",
    "bronze/dataset=tiger_place": "census_pipeline.download_tiger",
    "bronze/dataset=acs5_tract": "census_pipeline.download_acs",
    "bronze/dataset=noaa_ghcnd": "weather_pipeline.download_noaa",
    "silver/tract": "silver_pipeline.build_tract",
    "silver/place": "silver_pipeline.build_place",
    "silver/weather_day": "silver_pipeline.build_weather_day",
    "silver/crime_offense": "silver_pipeline.build_crime_offense",
    "gold/*": "gold_pipeline.build_gold",
}


@pytest.fixture(scope="module")
def register() -> dict[str, int]:
    """Das Register: Datensatz -> genannte Version."""
    text = AENDERUNGEN.read_text(encoding="utf-8")
    anfang = text.index("## Vertragsversionen")
    ende = text.index("\n---\n", anfang)
    gefunden = {}
    for zeile in text[anfang:ende].splitlines():
        treffer = re.match(r"^\| (`[^|]+`) \| \*{0,2}([0-9]+)\*{0,2} \|", zeile)
        if treffer:
            for name in re.findall(r"`([^`]+)`", treffer.group(1)):
                gefunden[name.strip().lstrip("…")] = int(treffer.group(2))
    assert gefunden, "kein Register 'Vertragsversionen' in AENDERUNGEN.md"
    return gefunden


@pytest.mark.parametrize("datensatz, modul", sorted(MODULE.items()))
def test_jede_quelle_hat_eine_vertragsversion(datensatz, modul):
    gemodul = importlib.import_module(modul)
    assert hasattr(gemodul, "CONTRACT_VERSION"), (
        f"{modul} hat keine CONTRACT_VERSION - jede Quelle und jede abgeleitete "
        "Tabelle braucht eine, sonst ist 'ab wann anders geladen' nicht beantwortbar"
    )
    assert isinstance(gemodul.CONTRACT_VERSION, int)
    assert gemodul.CONTRACT_VERSION >= 1


@pytest.mark.parametrize("datensatz, modul", sorted(MODULE.items()))
def test_die_version_steht_im_register(datensatz, modul, register):
    """Der eigentliche Waechter: eine Zahl ohne Begruendung ist wertlos."""
    assert datensatz in register, (
        f"{datensatz} fehlt im Register 'Vertragsversionen' in AENDERUNGEN.md"
    )
    gemodul = importlib.import_module(modul)
    assert register[datensatz] == gemodul.CONTRACT_VERSION, (
        f"{datensatz}: Code sagt Version {gemodul.CONTRACT_VERSION}, das Register "
        f"sagt {register[datensatz]}. Wer erhoeht, schreibt dazu, was der Vertrag "
        "jetzt festlegt - sonst weiss es in einem Jahr niemand mehr."
    )


def test_das_register_erfindet_keinen_datensatz(register):
    unbekannt = sorted(set(register) - set(MODULE))
    assert not unbekannt, f"im Register, aber ohne Code: {unbekannt}"


def test_detroits_vertrag_steht_auf_zwei():
    """Die Ausnahme mit Geschichte: seit dem Zeitzonen-Fix vom 11.9.2026.

    Detroit hatte die Idee vor allen anderen - die Zahl steht seither in den
    Daten. Wer sie auf 1 zuruecksetzt, behauptet, die Laeufe vor dem Fix und
    danach seien gleich zu lesen. Sie sind es nicht: 66 Faelle aus 2023.
    """
    from detroit_pipeline import extract_detroit

    assert extract_detroit.CONTRACT_VERSION == 2


# --------------------------------------------------------------------------
# Der Code-Stand
# --------------------------------------------------------------------------


def test_der_code_stand_nennt_commit_und_sauberkeit():
    from manifeste import code_stand

    stand = code_stand()
    assert set(stand) == {"git_commit", "git_dirty"}
    if stand["git_commit"] is not None:
        assert re.fullmatch(r"[0-9a-f]{40}", stand["git_commit"])
        assert isinstance(stand["git_dirty"], bool)


def test_ohne_git_scheitert_kein_lauf(monkeypatch):
    """Ein installiertes Paket hat kein Repository - das darf nichts kosten."""
    import subprocess

    import manifeste

    def kein_git(*a, **kw):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", kein_git)
    manifeste.code_stand.cache_clear()
    try:
        assert manifeste.code_stand() == {"git_commit": None, "git_dirty": None}
    finally:
        manifeste.code_stand.cache_clear()


@pytest.mark.parametrize("schicht, tabelle", [
    ("silver", "dataset=crime_offense"),
    ("gold", "dataset=fact_offense"),
])
def test_die_gebauten_manifeste_tragen_beides(schicht, tabelle):
    """Auf gebauten Daten: Die Angaben muessen wirklich ankommen."""
    pfad = PROJECT_ROOT / "data" / schicht / tabelle / "manifest.json"
    if not pfad.exists():
        pytest.skip(f"{schicht}/{tabelle} nicht gebaut")
    manifest = json.loads(pfad.read_text(encoding="utf-8"))
    assert manifest["contract_version"] >= 1
    assert set(manifest["code_version"]) == {"git_commit", "git_dirty"}
