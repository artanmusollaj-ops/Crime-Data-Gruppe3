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
AENDERUNGEN = PROJECT_ROOT / "docs" / "intern" / "AENDERUNGEN.md"

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
    "silver/source_change": "silver_pipeline.build_source_change",
    "gold/*": "gold_pipeline.build_gold",
    "serving/comparison_*": "serving.build_comparison",
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


def test_detroits_vertrag_faellt_nie_zurueck():
    """Die Ausnahme mit Geschichte - zwei Stufen, beide in den Daten sichtbar.

    Version 2 kam mit dem Zeitzonen-Fix vom 11.9.2026: Wer sie auf 1
    zuruecksetzt, behauptet, die Laeufe davor und danach seien gleich zu lesen.
    Sie sind es nicht - 66 Faelle aus 2023.

    Version 3 kam am 18.9.2026 mit dem Delta-Ladeweg. Vorher enthielt jeder
    Lauf den ganzen Jahrgang, seither nur noch das seit dem Wasserzeichen
    Geaenderte. Wer einen Bestand zaehlt, muss das wissen: Ein Lauf ist seither
    kein Bestand mehr, sondern eine Aenderungsmenge.

    Geprueft wird nur die Richtung. Dass die Zahl *genau* die ist, die das
    Register nennt, steht schon in ``test_die_version_steht_im_register``.
    """
    from detroit_pipeline import extract_detroit

    assert extract_detroit.CONTRACT_VERSION >= 3


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
    ("serving", "dataset=comparison_month"),
])
def test_die_gebauten_manifeste_tragen_beides(schicht, tabelle):
    """Auf gebauten Daten: Die Angaben muessen wirklich ankommen."""
    pfad = PROJECT_ROOT / "data" / schicht / tabelle / "manifest.json"
    if not pfad.exists():
        pytest.skip(f"{schicht}/{tabelle} nicht gebaut")
    manifest = json.loads(pfad.read_text(encoding="utf-8"))
    assert manifest["contract_version"] >= 1
    assert set(manifest["code_version"]) == {"git_commit", "git_dirty"}
