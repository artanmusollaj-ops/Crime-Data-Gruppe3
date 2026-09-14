"""Prueft die Code-Referenz und das, wovon sie lebt: die Docstrings.

``tools/build_referenz.py`` macht aus den Docstrings ein durchsuchbares
Nachschlagewerk. Das Werkzeug ist dabei der kleinere Teil der Zusage. Der
groessere ist, dass es ueberhaupt etwas zu lesen gibt - ein Paket ohne
Docstring erzeugt eine leere Seite, und niemand merkt es, weil die Seite ja
entsteht. Genau so war es bei ``chicago_pipeline``: das Paket der wichtigsten
Quelle des Projekts, ohne eine Zeile Erklaerung, bis die Referenz es zeigte.

Die Referenz selbst wird nicht versioniert. Geprueft wird deshalb nicht eine
abgelegte Datei, sondern dass ein Bau gelingt, jedes Paket erreicht und ein
zweiter Lauf dieselben Dateien liefert - dieselbe Regel wie bei den
Crosswalks, beim Feldkatalog und bei den Architekturbildern.
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

import pytest


PROJEKT = Path(__file__).resolve().parents[1]
QUELLE = PROJEKT / "src" / "crime"
WERKZEUGE = PROJEKT / "tools"

if str(WERKZEUGE) not in sys.path:
    sys.path.insert(0, str(WERKZEUGE))

import build_referenz as br  # noqa: E402


# ---------------------------------------------------------------- Docstrings


def test_jedes_paket_hat_einen_docstring():
    """Ohne ihn ist die Paketseite leer - und die Luecke faellt nicht auf.

    Das ist der eigentliche Waechter dieser Datei. ``chicago_pipeline`` hatte
    monatelang eine vollstaendig leere ``__init__.py``; im Quelltext faellt so
    etwas niemandem auf, weil man dort ohnehin gleich ins Modul springt.
    """
    ohne = [p for p in br.pakete() if not br.beschreibung(p)]
    assert not ohne, (
        f"Diese Pakete haben keinen Docstring in __init__.py: {ohne}. "
        "Die Startseite der Referenz zeigt daneben eine leere Zeile."
    )


def test_jede_beschreibung_ist_ein_ganzer_satz():
    """Die erste Zeile steht auf der Startseite und wird dort gelesen.

    Ein abgeschnittener Halbsatz sieht dort aus wie ein Fehler des Werkzeugs,
    nicht wie einer des Docstrings.
    """
    schlecht = {
        p: erste for p in br.pakete()
        if not (erste := br.beschreibung(p)).endswith((".", "!", "?"))
    }
    assert not schlecht, (
        "Die erste Zeile dieser Paket-Docstrings endet nicht als Satz: "
        f"{schlecht}"
    )


def test_jedes_modul_hat_einen_docstring():
    """Auch die Module, nicht nur die Pakete - sie sind der Inhalt."""
    ohne = []
    for pfad in sorted(QUELLE.rglob("*.py")):
        if "__pycache__" in pfad.parts:
            continue
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        if not ast.get_docstring(baum):
            ohne.append(str(pfad.relative_to(QUELLE).as_posix()))
    assert not ohne, f"Module ohne Docstring: {ohne}"


# ------------------------------------------------------------------ Aufbau


def test_die_pakete_sind_die_installierten():
    """Was die Referenz zeigt, muss das sein, was setuptools installiert.

    Beide suchen nach ``__init__.py`` unter ``src/crime``. Stuende hier eine
    eigene Liste, waere sie die erste Stelle, die eine neue Pipeline vergisst.
    """
    daten = tomllib.loads((PROJEKT / "pyproject.toml").read_text(encoding="utf-8"))
    assert daten["tool"]["setuptools"]["packages"]["find"]["where"] == ["src/crime"]
    erwartet = sorted(
        p.name for p in QUELLE.iterdir()
        if p.is_dir() and (p / "__init__.py").is_file()
    )
    assert br.pakete() == erwartet


def test_kein_paket_faellt_aus_der_gruppierung():
    """Jedes Paket steht genau einmal auf der Startseite.

    Der Fall, der das noetig macht: ein neues Paket, das noch keine Stufe in
    ``run_all`` hat. Es faellt dann unter *Steuerung* auf, statt lautlos zu
    fehlen.
    """
    gezeigt = [paket for _, _, drin in br.gruppiert() for paket in drin]
    assert sorted(gezeigt) == br.pakete()
    doppelt = [p for p in set(gezeigt) if gezeigt.count(p) > 1]
    assert not doppelt, f"mehrfach gruppiert: {doppelt}"


def test_die_gruppen_folgen_dem_gesamtlauf():
    """Die Reihenfolge ist die des Laufs, nicht das Alphabet."""
    from orchestration.run_all import GRUPPEN

    titel = [name for name, _, _ in br.gruppiert()]
    assert titel[0] == "Fundament", "das Fundament steht zuerst"
    assert titel[-1] == "Steuerung", "was keine Stufe hat, steht zuletzt"
    mittendrin = titel[1:-1]
    assert mittendrin == [g.capitalize() for g in GRUPPEN if g.capitalize() in mittendrin]


def test_die_stufenzahlen_stimmen():
    """Die Zahlen auf der Startseite kommen aus STUFEN, nicht aus der Hand."""
    from orchestration.run_all import GRUPPEN, STUFEN

    for gruppe in GRUPPEN:
        echt = sum(1 for s in STUFEN if s.gruppe == gruppe)
        assert br.stufenzahl(gruppe) == echt
    assert sum(br.stufenzahl(g) for g in GRUPPEN) == len(STUFEN), (
        "es gibt eine Stufe in einer Gruppe, die GRUPPEN nicht kennt"
    )


# --------------------------------------------------------------- Startseite


def test_die_startseite_nennt_jedes_paket():
    seite = br.startseite()
    for paket in br.pakete():
        assert f'href="{paket}.html"' in seite, f"{paket} fehlt auf der Startseite"
        assert br.beschreibung(paket) in seite, (
            f"die Beschreibung von {paket} steht nicht auf der Startseite"
        )


def test_die_startseite_wiederholt_keinen_docstring():
    """Eine Gruppenzeile, die den Docstring darunter wiederholt, ist Fuellung.

    Genau das passierte im ersten Entwurf: Ueber ``silver_pipeline`` stand
    *„macht aus mehreren Quellen vergleichbare Tabellen"* - und einen
    Zentimeter darunter derselbe Satz als Docstring des Pakets.
    """
    for _, erklaerung, drin in br.gruppiert():
        for paket in drin:
            beschreibung = br.beschreibung(paket).rstrip(".").lower()
            assert erklaerung.lower() not in beschreibung, (
                f"die Gruppenzeile wiederholt den Docstring von {paket}"
            )


def test_die_startseite_ist_wohlgeformt():
    """Jedes geoeffnete Tag wird geschlossen, in der richtigen Reihenfolge.

    Geprueft wird mit einem HTML-Parser, nicht mit einem XML-Parser: ``<meta
    charset>`` und ``<br>`` sind in HTML gueltig und in XML nicht - ein
    XML-Parser haette hier eine Zeile bemaengelt, die voellig in Ordnung ist.
    """
    from html.parser import HTMLParser

    leer = {"meta", "link", "br", "hr", "img", "input", "source", "col"}

    class Waage(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.stapel: list[str] = []
            self.fehler: list[str] = []

        def handle_starttag(self, tag: str, attrs: object) -> None:
            if tag not in leer:
                self.stapel.append(tag)

        def handle_endtag(self, tag: str) -> None:
            if tag in leer:
                return
            if not self.stapel:
                self.fehler.append(f"</{tag}> ohne oeffnendes Tag")
            elif self.stapel[-1] != tag:
                self.fehler.append(f"</{tag}> schliesst <{self.stapel[-1]}>")
            else:
                self.stapel.pop()

    waage = Waage()
    waage.feed(br.startseite())
    assert not waage.fehler, waage.fehler
    assert not waage.stapel, f"nie geschlossen: {waage.stapel}"


# ------------------------------------------------------------------- Bauen


@pytest.fixture(scope="module")
def gebaut(tmp_path_factory) -> tuple[br.Ergebnis, br.Ergebnis]:
    """Zwei Baeufe in getrennte Verzeichnisse - fuer alle Bau-Tests einer.

    Der Bau importiert jedes Modul und dauert gut eine Sekunde. Ihn je Test zu
    wiederholen waere die Art von Testsuite, die man irgendwann nicht mehr
    laufen laesst.
    """
    pytest.importorskip("pdoc")
    wurzel = tmp_path_factory.mktemp("referenz")
    return br.baue(wurzel / "a"), br.baue(wurzel / "b")


def test_jedes_paket_bekommt_eine_seite(gebaut):
    erst, _ = gebaut
    namen = {p.name for p in erst.dateien}
    for paket in br.pakete():
        assert f"{paket}.html" in namen, f"keine Seite fuer {paket}"


def test_ein_zweiter_lauf_liefert_dieselben_dateien(gebaut):
    """Dieselbe Regel wie bei den Crosswalks, dem Feldkatalog und den Bildern.

    Ein erzeugtes Artefakt, das sich bei jedem Lauf aendert, laesst sich nicht
    pruefen - und man merkt nicht mehr, ob eine Aenderung vom Code kommt oder
    vom Werkzeug.
    """
    erst, zweit = gebaut
    wurzel_a = _wurzel(erst)
    wurzel_b = _wurzel(zweit)
    rel_a = sorted(p.relative_to(wurzel_a).as_posix() for p in erst.dateien)
    rel_b = sorted(p.relative_to(wurzel_b).as_posix() for p in zweit.dateien)
    assert rel_a == rel_b, "der zweite Lauf schreibt andere Dateien"
    for rel in rel_a:
        assert (wurzel_a / rel).read_bytes() == (wurzel_b / rel).read_bytes(), (
            f"{rel} unterscheidet sich zwischen zwei Laeufen"
        )


def test_die_seiten_tragen_keine_rechnerpfade(gebaut):
    """Ein absoluter Pfad in der Ausgabe waere auf jedem Rechner ein anderer.

    Er waere damit nicht nur unreproduzierbar, sondern stuende auch in einem
    Artefakt, das man weitergibt.
    """
    erst, _ = gebaut
    wurzel = _wurzel(erst)
    heimat = str(Path.home())
    for pfad in erst.dateien:
        if pfad.suffix not in (".html", ".js"):
            continue
        inhalt = pfad.read_text(encoding="utf-8", errors="replace")
        assert heimat not in inhalt, (
            f"{pfad.relative_to(wurzel)} nennt einen absoluten Pfad"
        )


def test_jeder_verweis_der_startseite_trifft(gebaut):
    erst, _ = gebaut
    wurzel = _wurzel(erst)
    seite = (wurzel / "index.html").read_text(encoding="utf-8")
    ziele = [z for z in re.findall(r'href="([^"]+)"', seite) if z.endswith(".html")]
    assert ziele, "die Startseite verweist auf nichts"
    tot = [z for z in ziele if not (wurzel / z).is_file()]
    assert not tot, f"tote Verweise auf der Startseite: {tot}"


def test_ein_bekannter_docstring_steht_auch_in_der_referenz(gebaut):
    """Die Probe aufs Exempel: Kommt der Text wirklich in der Seite an?

    Alles andere hier prueft Dateien und Namen. Dieser Test prueft, dass die
    Referenz tatsaechlich das zeigt, wofuer es sie gibt.
    """
    erst, _ = gebaut
    seite = (_wurzel(erst) / "silver_pipeline.html").read_text(encoding="utf-8")
    assert "Silver-Schicht" in seite
    assert "STUDIENSTAEDTE" in seite, "die Konstanten fehlen in der Referenz"


def _wurzel(ergebnis: br.Ergebnis) -> Path:
    """Das Ausgabeverzeichnis eines Baus, aus seinen Dateien erschlossen."""
    return Path(*_gemeinsamer_anfang(ergebnis.dateien))


def _gemeinsamer_anfang(pfade: list[Path]) -> tuple[str, ...]:
    teile = [p.parts for p in pfade]
    gemeinsam: list[str] = []
    for stuecke in zip(*teile):
        if len(set(stuecke)) != 1:
            break
        gemeinsam.append(stuecke[0])
    return tuple(gemeinsam)


# --------------------------------------------------------------- Einbettung


def test_die_referenz_ist_nicht_versioniert():
    """7 MB erzeugtes HTML gehoeren nicht in die Historie.

    Sie waeren bei jeder geaenderten Zeile Docstring ein Diff ueber
    fuenfundzwanzig Dateien - und in einem Jahr der Grund, warum niemand mehr
    einen Pull Request liest.
    """
    regeln = (PROJEKT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert any(z.strip().rstrip("/") == "docs/referenz" for z in regeln), (
        "docs/referenz/ fehlt in .gitignore"
    )


def test_pdoc_ist_eine_entwicklungsabhaengigkeit():
    """Sonst scheitert der Bau bei dem, der ihn zum ersten Mal aufruft."""
    daten = tomllib.loads((PROJEKT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = daten["project"]["optional-dependencies"]["dev"]
    assert any(e.startswith("pdoc") for e in dev), "pdoc fehlt unter [dev]"

    lock = (PROJEKT / "requirements.lock").read_text(encoding="utf-8")
    assert re.search(r"^pdoc==", lock, re.M), "pdoc fehlt in requirements.lock"
