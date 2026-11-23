"""Zu jedem Pflichtbestandteil P1 bis P6 gibt es eine Fundstelle, die es gibt.

FR-56 verlangt fuer jeden der sechs Bestandteile aus den Modulunterlagen
eine benannte Fundstelle. Bis zum 23.11.2026 stand nirgends, wo sie liegen,
und ``fr-stand.md`` fuehrte FR-56 deshalb als "nicht geprueft".

Eine Fundstelle verfaellt auf drei Arten, und jede bleibt ohne Waechter
unsichtbar:

- **Der Anker bricht.** Eine Ueberschrift wird umbenannt, und der Link fuehrt
  an den Anfang der Datei statt an die Stelle. GitHub meldet das nicht.
- **Die Stelle kuendigt nur an.** Das PRD verlangt ausdruecklich, dass kein
  Bestandteil "durch ein Dokument belegt [wird], das nur behauptet". Eine
  Ueberschrift mit "Entwurf" oder "Vorschlag" ist genau das.
- **Das Register luegt nach oben.** ``fr-stand.md`` setzt FR-56 auf erfuellt,
  obwohl ein Bestandteil noch fehlt, oder umgekehrt.

Was hier **nicht** geprueft wird: ob die Stelle inhaltlich traegt. Das steht
als Satz in der letzten Spalte des Registers.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGISTER = PROJECT_ROOT / "docs" / "intern" / "pflichtbestandteile.md"
FR_STAND = PROJECT_ROOT / "docs" / "intern" / "fr-stand.md"
#: Nicht im Repository (``_bmad-output`` ist ungetrackt). Wo es liegt, wird
#: der Wortlaut dagegen gehalten, sonst uebersprungen.
PRD = (PROJECT_ROOT / "_bmad-output" / "initiative-ln2" / "prd-ln2-serving-betrieb"
       / "prd-ln2-serving-betrieb.md")

STAENDE = ("belegt", "teilweise", "fehlt")
#: Woran eine Stelle zu erkennen ist, die nur ankuendigt.
ANKUENDIGUNG = re.compile(r"Entwurf|Vorschlag", re.I)
LINK = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def felder(zeile: str) -> list[str]:
    return [f.strip() for f in re.split(r"(?<!\\)\|", zeile)][1:-1]


def zeilen(text: str) -> dict[str, list[str]]:
    gefunden: dict[str, list[str]] = {}
    for z in text.splitlines():
        f = felder(z) if z.startswith("|") else []
        if len(f) == 5 and re.fullmatch(r"P\d", f[0]):
            assert f[0] not in gefunden, f"{f[0]} steht zweimal"
            gefunden[f[0]] = f
    return gefunden


def anker(ueberschrift: str) -> str:
    """Der Anker, den GitHub aus einer Ueberschrift macht.

    Kleinschreibung, Satzzeichen weg (Umlaute bleiben), jedes Leerzeichen
    ein Bindestrich. Aus "## 16 · Die Strecke auf `srv01`" wird darum
    "16--die-strecke-auf-srv01": Der Mittelpunkt faellt weg, die beiden
    Leerzeichen um ihn bleiben.
    """
    s = ueberschrift.strip().lower()
    s = re.sub(r"[^\w\- ]", "", s)
    return s.replace(" ", "-")


def ueberschriften(datei: Path) -> dict[str, str]:
    """Anker -> Ueberschrift, ausserhalb von Codebloecken."""
    gefunden: dict[str, str] = {}
    im_code = False
    for z in datei.read_text(encoding="utf-8").splitlines():
        if z.startswith("```"):
            im_code = not im_code
            continue
        m = None if im_code else re.match(r"#{1,6} (.+)", z)
        if m:
            gefunden.setdefault(anker(m.group(1)), m.group(1))
    return gefunden


@pytest.fixture(scope="module")
def register() -> dict[str, list[str]]:
    return zeilen(REGISTER.read_text(encoding="utf-8"))


def test_alle_sechs_stehen_da(register):
    assert sorted(register) == [f"P{i}" for i in range(1, 7)]


def test_jeder_stand_ist_einer_der_drei(register):
    falsch = {p: f[2] for p, f in register.items() if f[2] not in STAENDE}
    assert not falsch, f"erlaubt sind {STAENDE}: {falsch}"


def test_wer_nicht_fehlt_nennt_eine_fundstelle(register):
    """Und wer fehlt, nennt keine - sonst waere "fehlt" gelogen."""
    for p, f in register.items():
        links = LINK.findall(f[3])
        if f[2] == "fehlt":
            assert not links, f"{p} steht auf fehlt und nennt doch {links}"
        else:
            assert links, f"{p} steht auf {f[2]} ohne Fundstelle"


def test_jede_fundstelle_gibt_es(register):
    fehler = []
    for p, f in register.items():
        for ziel in LINK.findall(f[3]):
            pfad, _, marke = ziel.partition("#")
            datei = (REGISTER.parent / pfad).resolve()
            if not datei.exists():
                fehler.append(f"{p}: {pfad} gibt es nicht")
            elif marke and marke not in ueberschriften(datei):
                fehler.append(f"{p}: in {pfad} keine Ueberschrift zum Anker #{marke}")
    assert not fehler, "\n".join(fehler)


def test_belegt_zeigt_auf_keine_ankuendigung(register):
    """Das PRD: kein Punkt wird durch ein Dokument belegt, das nur behauptet."""
    fehler = []
    for p, f in register.items():
        if f[2] != "belegt":
            continue
        for ziel in LINK.findall(f[3]):
            pfad, _, marke = ziel.partition("#")
            if not marke:
                continue
            titel = ueberschriften((REGISTER.parent / pfad).resolve())[marke]
            if ANKUENDIGUNG.search(titel):
                fehler.append(f"{p}: {pfad} '{titel}'")
    assert not fehler, "belegt, aber die Stelle kuendigt nur an:\n" + "\n".join(fehler)


def test_fr_56_steht_so_wie_das_register(register):
    """Erfuellt genau dann, wenn kein Bestandteil mehr fehlt."""
    zeile = next(z for z in FR_STAND.read_text(encoding="utf-8").splitlines()
                 if z.startswith("| FR-56 |"))
    zeichen = felder(zeile)[2]
    fehlend = [p for p, f in register.items() if f[2] == "fehlt"]
    if fehlend:
        assert zeichen != "●", f"FR-56 steht auf erfuellt, aber es fehlt {fehlend}"
        for p in fehlend:
            assert p in zeile, f"FR-56 nennt nicht, dass {p} fehlt"
    else:
        assert zeichen == "●", "kein Bestandteil fehlt mehr - FR-56 nachziehen"


def test_der_wortlaut_ist_der_des_prd(register):
    if not PRD.is_file():
        pytest.skip("PRD nicht im Arbeitsbaum")
    prd = {f[0]: f[1] for z in PRD.read_text(encoding="utf-8").splitlines()
           if z.startswith("| P") and len(f := felder(z)) == 3
           and re.fullmatch(r"P\d", f[0])}

    def eben(s: str) -> str:
        return re.sub(r"\*\*", "", s).strip()

    abweichend = {p: (f[1], prd[p]) for p, f in register.items()
                  if eben(f[1]) != eben(prd.get(p, ""))}
    assert not abweichend, abweichend
