"""Die Statustabelle bleibt vollstaendig und erfindet nichts.

**Warum es sie gibt.** Das PRD sagt, *was* zu bauen ist, und sein Abschnitt 8
in welcher Reihenfolge. Was davon **steht**, sagte bis zum 17.10.2026 nichts -
es war ueber ``AENDERUNGEN.md`` und die Planungsdateien verteilt. Als Christian
fragte, womit weiterzumachen sei, musste der Stand fuer 64 Anforderungen
einzeln rekonstruiert werden. Das ist einmal in Ordnung und zweimal eine
Verschwendung.

**Warum es diesen Waechter braucht.** Eine Tabelle, die eine Anforderung
*nicht* nennt, sieht vollstaendig aus - das ist die teuerste Art, falsch zu
sein. Drei Zusagen werden gehalten:

* Jede Anforderung des PRD steht in der Tabelle.
* Die Tabelle nennt keine, die es im PRD nicht gibt.
* Jede Zeile traegt einen Stand **und** einen Beleg.

Was er **nicht** prueft: ob ein Stand stimmt. Das kann kein Test - ``erfuellt``
ist eine Behauptung ueber die Welt, und der Beleg daneben ist der Grund, warum
sie nachpruefbar ist. Dieser Waechter sorgt dafuer, dass der Beleg **dasteht**,
nicht dafuer, dass er trifft.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRD = (PROJECT_ROOT / "_bmad-output" / "initiative-ln2"
       / "prd-ln2-serving-betrieb" / "prd-ln2-serving-betrieb.md")
TABELLE = PROJECT_ROOT / "docs" / "intern" / "fr-stand.md"

#: Die Zeichen der Legende. Wer eines aendert, aendert die Legende mit.
STAENDE = frozenset("●◐○▣")


@pytest.fixture(scope="module")
def prd_nummern() -> set[str]:
    if not PRD.is_file():
        pytest.skip(f"{PRD} fehlt - das PRD liegt nicht im Repository")
    text = PRD.read_text(encoding="utf-8")
    # Nur die fett gesetzten Nennungen: So steht eine Anforderung im PRD,
    # wenn sie *definiert* wird. Eine Erwaehnung im Fliesstext ist keine.
    return set(re.findall(r"\*\*(FR-\d+)\*\*", text))


@pytest.fixture(scope="module")
def zeilen() -> dict[str, tuple[str, str]]:
    """Je Anforderung (Stand, Beleg) aus der Tabelle."""
    if not TABELLE.is_file():
        pytest.skip(f"{TABELLE} fehlt")
    gefunden = {}
    for zeile in TABELLE.read_text(encoding="utf-8").splitlines():
        # **Getrennt wie Markdown trennt**: an Pipes, die *nicht* maskiert
        # sind. Ein `\\|` gehoert zum Zellinhalt - `ES\\|QL` ist ein Wort und
        # keine Spaltengrenze. Die erste Fassung trennte an jedem Pipe und
        # las deshalb FR-27s Beleg als vier Zeichen; der Waechter meldete
        # eine richtig belegte Zeile als unbelegt.
        felder = [f.strip() for f in re.split(r"(?<!\\)\|", zeile)]
        if len(felder) < 5 or not re.fullmatch(r"FR-\d+", felder[1]):
            continue
        if felder[3] not in STAENDE:
            continue
        gefunden[felder[1]] = (felder[3], felder[4])
    return gefunden


def test_jede_anforderung_des_prd_steht_in_der_tabelle(prd_nummern, zeilen):
    fehlend = sorted(prd_nummern - set(zeilen),
                     key=lambda s: int(s.split("-")[1]))
    assert not fehlend, (
        f"nicht in der Tabelle: {fehlend}. Eine Tabelle, die eine "
        f"Anforderung nicht nennt, sieht vollstaendig aus.")


def test_die_tabelle_erfindet_keine_anforderung(prd_nummern, zeilen):
    """Ausser FR-19, und das mit Grund.

    Das PRD ueberspringt die Nummer. Die Tabelle fuehrt sie als
    zurueckgestellt mit genau dieser Begruendung - sonst waere die Luecke
    unsichtbar, und der naechste Leser zaehlt 63 und fragt sich, welche fehlt.
    """
    erfunden = sorted(set(zeilen) - prd_nummern - {"FR-19"},
                      key=lambda s: int(s.split("-")[1]))
    assert not erfunden, f"steht in der Tabelle, nicht im PRD: {erfunden}"
    assert "FR-19" in zeilen, "die Luecke bei FR-19 gehoert genannt"
    _stand, beleg = zeilen["FR-19"]
    assert "nicht" in beleg.lower() or "existiert" in beleg.lower(), (
        "FR-19 ist eine Luecke im PRD - der Beleg soll das sagen")


def test_jede_zeile_traegt_einen_beleg(zeilen):
    """Ein Stand ohne Beleg ist eine Meinung.

    Verlangt wird **Text**, nicht Wahrheit: ``nicht geprueft`` ist ein
    gueltiger Beleg und eine ehrliche Angabe. Leer ist keiner.
    """
    ohne = sorted((fr for fr, (_, beleg) in zeilen.items() if len(beleg) < 12),
                  key=lambda s: int(s.split("-")[1]))
    assert not ohne, f"Stand ohne Beleg: {ohne}"


def test_die_summen_stimmen(zeilen):
    """Die Zahlen unter der Tabelle werden gezaehlt, nicht geschaetzt.

    Sie stehen dort, weil sie die Frage beantworten, mit der dieses Dokument
    angefangen hat - *womit weitermachen?* Eine Summe, die nicht zur Tabelle
    passt, beantwortet sie falsch.
    """
    text = TABELLE.read_text(encoding="utf-8")
    gezaehlt = {z: sum(1 for s, _ in zeilen.values() if s == z)
                for z in STAENDE}
    for zeichen, name in (("●", "erfüllt"), ("◐", "teilweise"),
                          ("○", "offen"), ("▣", "zurückgestellt")):
        m = re.search(rf"\|\s*{zeichen} {name}\s*\|\s*(\d+)\s*\|", text)
        assert m, f"keine Summenzeile fuer '{zeichen} {name}'"
        assert int(m.group(1)) == gezaehlt[zeichen], (
            f"{zeichen} {name}: Tabelle sagt {m.group(1)}, gezaehlt "
            f"{gezaehlt[zeichen]}")
    m = re.search(r"\*\*zusammen\*\*\s*\|\s*\*\*(\d+)\*\*", text)
    assert m and int(m.group(1)) == len(zeilen), (
        f"Summe {m.group(1) if m else '?'}, Zeilen {len(zeilen)}")
