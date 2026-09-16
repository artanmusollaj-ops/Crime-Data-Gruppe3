"""Prueft ``notebooks/36_hypothesen.ipynb`` - die Nachweise zu H1 bis H6.

Das Notebook misst die sechs Hypothesen aus Kapitel 3 des Konzepts und haelt
fest, welche halten und welche nicht. Es braucht die gebauten Schichten und
laeuft deshalb im woechentlichen Datenlauf, nicht auf einem Pull Request.

Was hier geprueft wird, ist das, was ohne gebaute Daten pruefbar bleibt: dass
alle sechs Hypothesen vorkommen, dass jede ein Ergebnis nennt, dass das
Notebook keine Ausgaben mitspeichert - und dass die beiden Stellen, an denen
es dem Code widerspricht, noch stimmen.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = PROJECT_ROOT / "notebooks" / "36_hypothesen.ipynb"
OFFENSE = PROJECT_ROOT / "src" / "crime" / "silver_pipeline" / "build_crime_offense.py"


@pytest.fixture(scope="module")
def zellen() -> list[dict]:
    if not NOTEBOOK.is_file():
        pytest.skip(f"{NOTEBOOK} fehlt")
    return json.loads(NOTEBOOK.read_text(encoding="utf-8"))["cells"]


@pytest.fixture(scope="module")
def text(zellen) -> str:
    return "\n".join("".join(z["source"]) for z in zellen)


def test_alle_sechs_hypothesen_kommen_vor(text):
    """Eine fehlende waere eine unbeantwortete Anforderung des Konzepts."""
    fehlend = [f"H{n}" for n in range(1, 7) if f"# H{n} ·" not in text]
    assert not fehlend, f"diese Hypothesen fehlen als Abschnitt: {fehlend}"


def test_jede_hypothese_nennt_ihr_ergebnis(text):
    """Eine Messung ohne Befund ist eine Tabelle, kein Nachweis."""
    ohne = [f"H{n}" for n in range(1, 7)
            if not re.search(rf"\*\*Ergebnis: H{n}", text)]
    assert not ohne, f"ohne ausgewiesenes Ergebnis: {ohne}"


def test_die_bilanz_fuehrt_alle_sechs(text):
    """Die Schlusstabelle ist das, was jemand abschreibt."""
    anfang = text.index("# Bilanz")
    bilanz = text[anfang:]
    fehlend = [f"H{n}" for n in range(1, 7) if f"**H{n}**" not in bilanz]
    assert not fehlend, f"in der Bilanz fehlen: {fehlend}"


def test_das_notebook_haelt_die_hypothesen_woertlich_fest(text):
    """Es zitiert sie, statt auf ein Dokument zu verweisen, das anderswo liegt.

    Die H1 bis H6 stehen in Artans Konzeptfassung, nicht im Repository. Ohne
    das Zitat waere das Notebook in einem halben Jahr nicht mehr lesbar.
    """
    zitate = re.findall(r"^> \*\*H\d:\*\*", text, re.M)
    assert len(zitate) >= 5, (
        f"nur {len(zitate)} Hypothesen sind woertlich zitiert"
    )


def test_der_docstring_behauptet_nicht_mehr_reconcile_zaehle_die_randfaelle():
    """Der Fehler, den das Notebook gefunden hat.

    Der Modul-Docstring sagte, ``reconcile`` zaehle die Faelle in der nicht
    existenten Stunde. Das tut er nicht - ``checks`` enthaelt keinen solchen
    Zaehler. Der Satz ist am 16.9.2026 korrigiert worden; dieser Test haelt
    fest, dass er nicht zurueckkommt, solange es den Zaehler nicht gibt.
    """
    quelle = OFFENSE.read_text(encoding="utf-8")
    kopf = quelle[:quelle.index('"""', quelle.index('"""') + 3)]
    behauptet = re.search(r"``reconcile`` zaehlt sie(?! nicht)", kopf)
    assert behauptet is None, (
        "der Docstring behauptet wieder, reconcile zaehle die Zeitzonen-"
        "Randfaelle. Entweder den Zaehler bauen oder den Satz lassen."
    )
    assert "nicht ausgewiesen" in kopf, (
        "der Docstring soll offen sagen, dass die beiden Randfaelle heute "
        "nicht ausgewiesen werden"
    )


def test_das_notebook_speichert_keine_ausgaben(zellen):
    """So halten es die uebrigen dreizehn auch."""
    mit = [i for i, z in enumerate(zellen)
           if z["cell_type"] == "code" and z.get("outputs")]
    assert not mit, f"Zellen mit gespeicherter Ausgabe: {mit}"


def test_das_notebook_sagt_was_es_nicht_zeigt(text):
    """Die Grenze gehoert zum Nachweis, sonst ist er eine Behauptung."""
    assert "Was dieses Notebook nicht zeigt" in text


def test_es_misst_mit_wiederholung(text):
    """Kapitel 4 verlangt mindestens drei Wiederholungen mit Median und Spannweite."""
    for wort in ("Median", "Spannweite"):
        assert wort in text, f"{wort} fehlt - Kapitel 4 verlangt beides"
    assert "for lauf in (1, 2, 3)" in text, "es wird nicht dreimal gemessen"
