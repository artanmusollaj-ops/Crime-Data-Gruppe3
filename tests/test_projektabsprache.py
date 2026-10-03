"""Haelt die Stichtagszeile der Projektabsprache an den Nachtraegen fest.

`docs/intern/projektabsprache.md` ist ein Schnappschuss: Grundstand vom
6. September 2026, danach ausdruecklich datierte Bloecke ``Nachtrag <Datum>``
und ``Nachgemessen am <Datum>``. Die Zeile im Kopf sagt, wie das Papier zu
lesen ist - und nennt dafuer das Datum des jueingsten Nachtrags.

**Warum das einen Waechter braucht.** Die Zeile behauptete bis zum 3.10.2026,
*alle* Zahlen des Papiers seien am 6. September erhoben - waehrend es
Nachtraege bis zum 20. September trug, also zwei Wochen jueinger. Kein Test hat
das gesehen, weil es keine Zahl ist, sondern ein Satz ueber Zahlen. Genau die
Sorte Drift, die in diesem Repository schon dreimal in Zahlen und einmal in
Worten passiert ist.

Geprueft wird deshalb nicht der Fliesstext, sondern die eine nachpruefbare
Zusage darin: dass das genannte juengste Datum das juengste ist.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[1]
ABSPRACHE = PROJEKT / "docs" / "intern" / "projektabsprache.md"

#: Der Grundstand, wie die Stichtagszeile ihn nennt.
GRUNDSTAND = (2026, 9, 6)

MONATE = {
    "Januar": 1, "Februar": 2, "März": 3, "April": 4, "Mai": 5, "Juni": 6,
    "Juli": 7, "August": 8, "September": 9, "Oktober": 10, "November": 11,
    "Dezember": 12,
}

#: ``**Nachtrag 13.9.2026 —`` und ``> **Nachgemessen am 20.09.2026 (...)``.
#: Ein Datum ist verlangt; die Erwaehnungen in Backticks in der
#: Stichtagszeile selbst treffen das Muster dadurch nicht.
MARKER = re.compile(
    r"\*\*Nach(?:trag|gemessen)(?: am)? (\d{1,2})\.(\d{1,2})\.(\d{4})")

#: Der Wortlaut, auf den sich die Zeile festlegt: ``das juengste vom 20.
#: September``. Das Jahr nennt sie nicht - dass es eindeutig ist, prueft
#: ``test_alle_nachtraege_liegen_im_jahr_des_grundstands``.
JUENGSTES = re.compile(r"das jüngste vom (\d{1,2})\.\s*(" +
                       "|".join(MONATE) + r")")


@pytest.fixture(scope="module")
def text() -> str:
    if not ABSPRACHE.is_file():
        pytest.skip("docs/intern/projektabsprache.md fehlt")
    return ABSPRACHE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def nachtraege(text) -> list[tuple[int, int, int]]:
    """Alle datierten Nachtraege als ``(Jahr, Monat, Tag)``, sortierbar."""
    return sorted((int(j), int(m), int(t))
                  for t, m, j in MARKER.findall(text))


def test_das_muster_findet_ueberhaupt_nachtraege(nachtraege):
    """Ohne diese Probe koennte der Vergleich auf zwei leere Mengen fallen.

    Dieselbe Falle wie am 19.9.2026 beim Dokumentwegweiser: Das Muster traf
    nach einem Umzug nichts mehr, und der Vergleich zweier leerer Mengen war
    weiter gruen. Ein Waechter, der nichts findet, prueft nichts.
    """
    assert len(nachtraege) >= 3, (
        f"nur {len(nachtraege)} Nachtraege gefunden - greift MARKER noch?")


def test_jeder_marker_traegt_ein_datum(text, nachtraege):
    """Ein Nachtrag ohne Datum wuerde dem Vergleich still entgehen."""
    roh = len(re.findall(r"\*\*Nach(?:trag|gemessen)", text))
    assert roh == len(nachtraege), (
        f"{roh} Nachtrags-Marker, aber nur {len(nachtraege)} mit lesbarem "
        "Datum - einer traegt keines oder eine andere Schreibweise")


def test_alle_nachtraege_liegen_im_jahr_des_grundstands(nachtraege):
    """Sonst ist ``vom 20. September`` ohne Jahr nicht eindeutig.

    Faellt dieser Test, gehoert das Jahr in die Stichtagszeile - und dieses
    Muster hier nachgezogen.
    """
    fremd = sorted({j for j, _, _ in nachtraege} - {GRUNDSTAND[0]})
    assert not fremd, f"Nachtraege aus anderen Jahren: {fremd}"


def test_der_grundstand_ist_nicht_juenger_als_ein_nachtrag(nachtraege):
    """Ein Nachtrag *vor* dem Grundstand waere keiner."""
    assert nachtraege[0] >= GRUNDSTAND, (
        f"Nachtrag {nachtraege[0]} liegt vor dem Grundstand {GRUNDSTAND}")


def test_die_stichtagszeile_nennt_den_grundstand(text):
    assert "6. September 2026" in text, (
        "die Stichtagszeile nennt den Grundstand nicht mehr")


def test_die_stichtagszeile_nennt_das_juengste_datum(text, nachtraege):
    """Die Zusage, die zwei Wochen lang falsch war."""
    treffer = JUENGSTES.search(text)
    assert treffer, (
        "die Stichtagszeile nennt kein juengstes Datum in der Form "
        "'das juengste vom <Tag>. <Monat>'")
    genannt = (int(treffer.group(1)), MONATE[treffer.group(2)])
    juengster = nachtraege[-1]
    assert genannt == (juengster[2], juengster[1]), (
        f"die Zeile nennt den {genannt[0]}.{genannt[1]}., der juengste "
        f"Nachtrag ist vom {juengster[2]}.{juengster[1]}.{juengster[0]}")
