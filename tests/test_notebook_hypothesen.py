"""Prueft ``notebooks/36_hypothesen.ipynb`` - die Nachweise zu H1 bis H6.

Das Notebook misst die sechs Hypothesen aus Kapitel 3 des Konzepts und haelt
fest, welche halten und welche nicht. Es braucht die gebauten Schichten und
laeuft deshalb im woechentlichen Datenlauf, nicht auf einem Pull Request.

Was hier geprueft wird, ist das, was ohne gebaute Daten pruefbar bleibt: dass
alle sechs Hypothesen vorkommen, dass jede ein Ergebnis nennt, dass das
Notebook keine Ausgaben mitspeichert - und dass die beiden Stellen, an denen
es dem Code widerspricht, noch stimmen.

**Seit dem 5.10.2026 auch der Wortlaut.** Die Zitate werden gegen
``docs/forschungsfragen.md`` gehalten, das aus dem eingereichten PDF erzeugt
ist. Vorher pruefte dieser Test nur, dass fuenf Zitate *vorkommen* - gegen
nichts. Genau darin war eine Revision stehengeblieben; der Test dazu steht
unten und erzaehlt sie.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WERKZEUGE = PROJECT_ROOT / "tools"
if str(WERKZEUGE) not in sys.path:
    sys.path.insert(0, str(WERKZEUGE))

import build_forschungsfragen as bf  # noqa: E402

NOTEBOOK = PROJECT_ROOT / "notebooks" / "36_hypothesen.ipynb"
OFFENSE = PROJECT_ROOT / "src" / "crime" / "silver_pipeline" / "build_crime_offense.py"
FORSCHUNGSFRAGEN = PROJECT_ROOT / "docs" / "forschungsfragen.md"


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

    Ohne das Zitat waere das Notebook in einem halben Jahr nicht mehr lesbar.
    """
    zitate = re.findall(r"^> \*\*H\d:\*\*", text, re.M)
    assert len(zitate) >= 5, (
        f"nur {len(zitate)} Hypothesen sind woertlich zitiert"
    )


def test_die_zitate_stimmen_mit_der_abgegebenen_fassung_ueberein(text):
    """Woertlich heisst: gegen die Abgabe gehalten, nicht nur vorhanden.

    **Der Fehler, der diesen Test ausgeloest hat.** Bis zum 5.10.2026 pruefte
    der Test darueber nur, dass mindestens fuenf Zitate *vorkommen* - gegen
    nichts, weil die massgebliche Fassung nicht im Repository lag. Dieses
    Notebook zitierte deshalb monatelang eine Revision vor der Abgabe: Sein H1
    sagte "die Menge der gelieferten technischen IDs", das abgegebene "die
    gelieferte Menge ... bei Quellen ohne Identifikator-Menge tritt ein
    gleichwertiger Nachweis an ihre Stelle". Ausgerechnet die Einschraenkung,
    die dieses Notebook selbst gemessen hatte, fehlte in seinem Zitat.

    Massgeblich ist ``docs/forschungsfragen.md`` - aus dem eingereichten PDF
    erzeugt (``tools/build_forschungsfragen.py``). Der Vergleich braucht das
    PDF nicht und laeuft deshalb immer.
    """
    if not FORSCHUNGSFRAGEN.is_file():
        pytest.fail(
            f"{FORSCHUNGSFRAGEN} fehlt - python tools/build_forschungsfragen.py. "
            "Ohne das Dokument haengen die Zitate hier an nichts")
    abgegeben = bf.massgeblich(FORSCHUNGSFRAGEN)
    zitiert = bf.zitate_aus(text)

    fehlend = [m for m in bf.FRAGEN + bf.HYPOTHESEN if m not in zitiert]
    assert not fehlend, (
        f"diese Marken werden im Notebook nicht woertlich zitiert: {fehlend}")

    abweichend = [
        f"{m}\n    abgegeben: {abgegeben[m]}\n    Notebook:  {zitiert[m]}"
        for m in bf.FRAGEN + bf.HYPOTHESEN
        if m in zitiert and zitiert[m] != abgegeben[m]
    ]
    assert not abweichend, (
        "das Notebook zitiert nicht die abgegebene Fassung:\n  "
        + "\n  ".join(abweichend)
        + "\n\nMassgeblich ist docs/forschungsfragen.md - es wurde "
        "eingereicht und bewertet. Nachziehen heisst hier: das Zitat im "
        "Notebook aendern, nicht die Hypothese."
    )


def test_das_notebook_nennt_das_massgebliche_dokument(text):
    """Ein Zitat ohne Quelle ist eine Behauptung.

    Bis zum 5.10.2026 stand im Notebook, die Hypothesen stuenden "in Artans
    Konzeptfassung, die nicht im Repository liegt". Das stimmt nicht mehr - und
    ein Leser, der es glaubt, sucht am falschen Ort.
    """
    assert "forschungsfragen.md" in text, (
        "das Notebook nennt docs/forschungsfragen.md nicht - dann weiss "
        "niemand, woher die Zitate kommen und was sie belegt")
    assert "Artans\n> Konzeptfassung" not in text


def test_der_docstring_behauptet_nicht_mehr_reconcile_zaehle_die_randfaelle():
    """Der Fehler, den das Notebook gefunden hat.

    Der Modul-Docstring sagte, ``reconcile`` zaehle die Faelle in der nicht
    existenten Stunde. Das tat er nicht. Seit dem 16.9.2026 tut er es - und
    dieser Test haelt fest, dass Docstring und Code dasselbe sagen.
    """
    quelle = OFFENSE.read_text(encoding="utf-8")
    kopf = quelle[:quelle.index('"""', quelle.index('"""') + 3)]
    assert "je Zeile ausgewiesen" in kopf, (
        "der Docstring soll sagen, dass die beiden Randfaelle ausgewiesen werden"
    )
    for spalte in ("local_time_nonexistent", "local_time_ambiguous"):
        assert spalte in kopf, f"{spalte} wird im Docstring nicht genannt"
        assert f"count(*) FILTER ({spalte})" in quelle, (
            f"der Docstring nennt {spalte}, reconcile zaehlt es nicht"
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
