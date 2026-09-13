"""Tests fuer die amtliche Gliederung der NIBRS-Delikte.

``config/nibrs_offense_categories_2025.csv`` beantwortet eine Frage, die
``nibrs_offense_codes_2025.csv`` offenlaesst: Wie fasst NIBRS seine Delikte
zusammen? Das Projekt hatte dafuer lange die ersten beiden Zeichen des Codes
benutzt und sie "Deliktfamilie" genannt - eine Hilfskonstruktion, die an vier
Stellen nachweislich falsch ist.

Die Datei wird von ``tools/build_nibrs_categories.py`` aus dem NIBRS User
Manual 2025.0 gelesen, nicht von Hand gepflegt. Diese Tests pruefen dreierlei:
die Form der Datei, ihre Uebereinstimmung mit der Codeliste, und dass sie
wirklich etwas anderes sagt als das Praefix - sonst braeuchte es sie nicht.
"""

from __future__ import annotations

import csv
import subprocess
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
KATEGORIEN = PROJECT_ROOT / "config" / "nibrs_offense_categories_2025.csv"
CODELISTE = PROJECT_ROOT / "config" / "nibrs_offense_codes_2025.csv"
WERKZEUG = PROJECT_ROOT / "tools" / "build_nibrs_categories.py"

# Original: le.fbi.gov, "2025.0 NIBRS User Manual" vom 23.06.2025.
HANDBUCH = PROJECT_ROOT / "docs" / "nibrs-user-manual-2025-0-062625.pdf"
QUELLE = "nibrs_user_manual_2025_0"

# Original: fbi.gov, "NIBRS Offense Codes", Fassung 2011. Ueberholt, aber der
# einzige Beleg fuer die vier zurueckgezogenen Codes.
ALTE_LISTE = PROJECT_ROOT / "docs" / "NIBRS_Offense_Codes.pdf"
QUELLE_ALT = "nibrs_offense_codes_2011"
ZURUECKGEZOGEN = {"90A", "90E", "90H", "90I"}

SPALTEN = ["nibrs_code", "nibrs_category", "nibrs_group", "source"]

# Was das Handbuch ueber sich selbst sagt.
GROUP_A_KATEGORIEN = 28
GROUP_A_DELIKTE = 71
GROUP_B_KATEGORIEN = 10


@pytest.fixture(scope="module")
def zeilen() -> list[dict[str, str]]:
    with KATEGORIEN.open(encoding="utf-8") as datei:
        return list(csv.DictReader(datei))


@pytest.fixture(scope="module")
def amtlich() -> dict[str, dict[str, str]]:
    with CODELISTE.open(encoding="utf-8") as datei:
        return {z["nibrs_code"]: z for z in csv.DictReader(datei)}


@pytest.fixture(scope="module")
def nach_code(zeilen) -> dict[str, dict[str, str]]:
    return {z["nibrs_code"]: z for z in zeilen}


# --------------------------------------------------------------------------
# Form
# --------------------------------------------------------------------------


def test_datei_existiert():
    assert KATEGORIEN.exists(), (
        f"{KATEGORIEN} fehlt - python tools/build_nibrs_categories.py"
    )


def test_spalten_wie_vereinbart(zeilen):
    assert list(zeilen[0]) == SPALTEN


def test_code_ist_eindeutig(zeilen):
    codes = [z["nibrs_code"] for z in zeilen]
    doppelt = sorted({c for c in codes if codes.count(c) > 1})
    assert not doppelt, f"mehrfach: {doppelt}"


def test_jede_zeile_nennt_eine_kategorie(zeilen):
    leer = [z["nibrs_code"] for z in zeilen if not z["nibrs_category"].strip()]
    assert not leer, f"ohne Kategorie: {leer}"


def test_jede_zeile_nennt_ihr_dokument(zeilen):
    """Zwei Quellen in einer Datei - dann muss je Zeile dastehen, welche."""
    quellen = {z["source"] for z in zeilen}
    assert quellen == {QUELLE, QUELLE_ALT}, f"unerwartete Herkunft: {quellen}"


def test_aus_der_fassung_2011_kommen_genau_die_zurueckgezogenen(zeilen):
    """Sonst schleicht sich veralteter Stand in die aktuelle Gliederung.

    Die Fassung 2011 ist ueberholt: 22 statt 28 Kategorien, und ``11A`` heisst
    dort noch *Forcible Rape*. Aus ihr darf deshalb nur kommen, was das
    Handbuch nicht mehr fuehrt.
    """
    alt = {z["nibrs_code"] for z in zeilen if z["source"] == QUELLE_ALT}
    assert alt == ZURUECKGEZOGEN, (
        f"unerwartet aus 2011: {sorted(alt - ZURUECKGEZOGEN)}, "
        f"fehlend: {sorted(ZURUECKGEZOGEN - alt)}"
    )


def test_die_alte_liste_liegt_im_repository():
    assert ALTE_LISTE.exists(), (
        f"{ALTE_LISTE} fehlt - ohne sie sind vier Codes ohne Kategorie"
    )


def test_quelldokument_liegt_im_repository():
    assert HANDBUCH.exists(), (
        f"{HANDBUCH} fehlt - ohne Quelle ist die Gliederung unbelegt"
    )
    assert HANDBUCH.stat().st_size > 1_000_000


# --------------------------------------------------------------------------
# Gegen die Codeliste und gegen das Handbuch
# --------------------------------------------------------------------------


def test_deckt_die_codeliste_genau_ab(zeilen, amtlich):
    """Die Codeliste plus die vier zurueckgezogenen, nicht mehr und nicht weniger."""
    gelesen = {z["nibrs_code"] for z in zeilen}
    erwartet = set(amtlich) | ZURUECKGEZOGEN
    assert gelesen == erwartet, (
        f"fehlend: {sorted(erwartet - gelesen)}, "
        f"zusaetzlich: {sorted(gelesen - erwartet)}"
    )


def test_die_gruppe_widerspricht_der_codeliste_nicht(zeilen, amtlich):
    """Zwei Quellen, dieselbe Aussage - sonst liest eine von beiden falsch."""
    uneinig = {
        z["nibrs_code"]: (z["nibrs_group"], amtlich[z["nibrs_code"]]["nibrs_group"])
        for z in zeilen
        if z["nibrs_code"] in amtlich
        and z["nibrs_group"] != amtlich[z["nibrs_code"]]["nibrs_group"]
    }
    assert not uneinig, f"Gruppe widerspricht der Codeliste: {uneinig}"


def test_die_zahlen_stimmen_mit_dem_handbuch(zeilen):
    """Das Handbuch sagt: 28 Group-A-Kategorien, 71 Delikte, 10 Group-B.

    Das ist der Nachweis, dass das Skript die Vorlage ganz gelesen hat und
    nicht halb. Ein Parser, der eine Seite ueberspringt, faellt hier.
    """
    aktuell = [z for z in zeilen if z["source"] == QUELLE]
    a = [z for z in aktuell if z["nibrs_group"] == "A"]
    b = [z for z in aktuell if z["nibrs_group"] == "B"]
    assert len({z["nibrs_category"] for z in a}) == GROUP_A_KATEGORIEN
    assert len(a) == GROUP_A_DELIKTE
    assert len({z["nibrs_category"] for z in b}) == GROUP_B_KATEGORIEN


@pytest.mark.parametrize(
    "code,kategorie",
    [
        ("13A", "Assault Offenses"),
        ("23C", "Larceny/Theft Offenses"),
        ("26A", "Fraud Offenses"),
        ("35A", "Drug/Narcotic Offenses"),
        ("720", "Animal Cruelty"),
        ("64A", "Human Trafficking"),
        ("90Z", "All Other Offenses"),
    ],
)
def test_stichproben(nach_code, code, kategorie):
    assert nach_code[code]["nibrs_category"] == kategorie


# --------------------------------------------------------------------------
# Warum es die Datei ueberhaupt braucht
# --------------------------------------------------------------------------


def test_kategorie_und_praefix_fallen_auseinander(nach_code):
    """Die vier Stellen, an denen die Deliktfamilie in die Irre fuehrt.

    Waeren Kategorie und Praefix dasselbe, waere diese Datei ueberfluessig und
    ``left(nibrs_code, 2)`` genuegte. Diese Faelle belegen, dass es nicht so
    ist - und sie sind der Grund, warum Gold nach ``nibrs_category`` gruppiert.
    """
    def kat(code: str) -> str:
        return nach_code[code]["nibrs_category"]

    # Eine Kategorie ueber zwei Praefixe
    assert kat("11A") == kat("11D") == kat("36A") == kat("360") == "Sex Offenses"
    # Eine Kategorie ueber drei Praefixe
    assert kat("58A") == kat("61A") == kat("620") == "Commerce Violations"
    # Ein Praefix ueber drei Kategorien
    assert {kat("100"), kat("101"), kat("103")} == {
        "Kidnapping/Abduction", "Treason", "Espionage"
    }


def test_group_b_hat_keinen_sammelnamen(zeilen):
    """Die Familie 90 ist ein Praefix-Artefakt, keine NIBRS-Gruppierung."""
    b = {z["nibrs_category"] for z in zeilen
         if z["nibrs_group"] == "B" and z["source"] == QUELLE}
    assert len(b) == GROUP_B_KATEGORIEN
    assert "All Other Offenses" in b
    # Alle Group-B-Codes beginnen mit 90, verteilen sich aber auf zehn
    # Kategorien - ein gemeinsamer Name waere erfunden.
    assert all(z["nibrs_code"].startswith("90")
               for z in zeilen if z["nibrs_group"] == "B")


# --------------------------------------------------------------------------
# Reproduzierbarkeit
# --------------------------------------------------------------------------


def test_ein_zweiter_lauf_liefert_dieselbe_datei(tmp_path):
    """Die Datei ist gelesen, nicht gepflegt - also muss sie sich erzeugen lassen.

    Braucht ``pdftotext``; fehlt es, wird der Test uebersprungen statt rot.

    **Nur unter Linux.** Die Reproduktion ist gegen ``poppler-utils`` definiert,
    wie CI es installiert. Der erste Windows-Lauf in CI zeigte, dass dessen
    ``pdftotext -layout`` die Spalten anders setzt: Die Ueberschrift *Arson*
    stand nicht mehr auf Einrueckung 2-3, das Werkzeug meldete "Code ohne
    Kategorie". Das ist keine Schwaeche der Datei, sondern des Umwegs ueber
    ein Layout-Werkzeug - und der Umweg gilt fuer genau einen Build. Die
    beiden MICR-Tests sind davon nicht betroffen, sie laufen auch dort.
    """
    if sys.platform == "win32":
        pytest.skip("Reproduktion ist gegen poppler-utils unter Linux definiert")
    if not HANDBUCH.exists():
        pytest.skip("Handbuch liegt nicht vor")
    vorher = KATEGORIEN.read_text(encoding="utf-8")
    fertig = subprocess.run(
        [sys.executable, str(WERKZEUG)],
        capture_output=True, text=True, cwd=PROJECT_ROOT,
    )
    if fertig.returncode != 0 and "pdftotext nicht gefunden" in fertig.stderr:
        pytest.skip("pdftotext nicht verfuegbar")
    assert fertig.returncode == 0, fertig.stderr
    assert KATEGORIEN.read_text(encoding="utf-8") == vorher, (
        "Ein zweiter Lauf liefert eine andere Datei - dann ist sie nicht "
        "reproduzierbar aus dem Handbuch abgeleitet"
    )
