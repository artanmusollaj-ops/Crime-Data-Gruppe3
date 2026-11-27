"""Prueft die Code-Referenz und das, wovon sie lebt: die Docstrings.

``tools/build_referenz.py`` macht aus den Docstrings ein durchsuchbares
Nachschlagewerk. Das Werkzeug ist dabei der kleinere Teil der Zusage. Der
groessere ist, dass es ueberhaupt etwas zu lesen gibt - ein Paket ohne
Docstring erzeugt eine leere Seite, und niemand merkt es, weil die Seite ja
entsteht. Genau so war es bei ``chicago_pipeline``: das Paket der wichtigsten
Quelle des Projekts, ohne eine Zeile Erklaerung, bis die Referenz es zeigte.

Die Referenz liegt im Repository, wie die Crosswalks, der Feldkatalog und die
Architekturbilder. Geprueft wird deshalb das Abgelegte selbst - und dass ein
frischer Bau dieselben Bytes liefert.

**Warum dieser Vergleich in einem eigenen Prozess laeuft.** Der erste Entwurf
baute zweimal hintereinander im Testprozess und verglich die Ergebnisse. Er
war gruen und wertlos: Manche Vorgabewerte im Code sind Mengen, pdoc druckt
sie mit ``repr``, und die Reihenfolge einer Menge von Zeichenketten haengt am
Hashwert - der ist je *Prozess* zufaellig, innerhalb eines Prozesses aber
fest. Zwei Baeufe im selben Prozess koennen also gar nicht abweichen. Erst
fuenf Laeufe in fuenf Prozessen zeigten bis zu vier verschiedene Dateien.
Seither setzt das Werkzeug ``PYTHONHASHSEED``, und dieser Test ruft es so auf,
wie ein Mensch es aufruft.
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest


PROJEKT = Path(__file__).resolve().parents[1]
QUELLE = PROJEKT / "src" / "crime"
WERKZEUGE = PROJEKT / "tools"
REFERENZ = PROJEKT / "docs" / "referenz"

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


# --------------------------------------------------- Die abgelegte Referenz


def _ausfallen(grund: str) -> None:
    """Ueberspringen - ausser im CI-Job ``referenz`` (``REFERENZ_PFLICHT=1``):
    Dort ist jeder Grund, nicht zu vergleichen, ein Fehler."""
    if os.getenv("REFERENZ_PFLICHT") == "1":
        pytest.fail(f"REFERENZ_PFLICHT=1, aber der Vergleich faellt aus: {grund}")
    pytest.skip(grund)


@pytest.fixture(scope="module")
def abgelegt() -> Path:
    """Das versionierte ``docs/referenz/``."""
    if not (REFERENZ / "index.html").is_file():
        _ausfallen(f"{REFERENZ} ist nicht gebaut - python tools/build_referenz.py")
    return REFERENZ


def test_jedes_paket_hat_eine_abgelegte_seite(abgelegt):
    fehlend = [p for p in br.pakete() if not (abgelegt / f"{p}.html").is_file()]
    assert not fehlend, (
        f"keine abgelegte Seite fuer: {fehlend}. Die Referenz ist aelter als "
        "der Code - python tools/build_referenz.py"
    )


def test_jeder_verweis_der_startseite_trifft(abgelegt):
    seite = (abgelegt / "index.html").read_text(encoding="utf-8")
    ziele = [z for z in re.findall(r'href="([^"]+)"', seite) if z.endswith(".html")]
    assert ziele, "die Startseite verweist auf nichts"
    tot = [z for z in ziele if not (abgelegt / z).is_file()]
    assert not tot, f"tote Verweise auf der Startseite: {tot}"


def test_die_seiten_tragen_keine_rechnerpfade(abgelegt):
    """Ein absoluter Pfad waere auf jedem Rechner ein anderer.

    Er waere damit nicht nur unreproduzierbar, sondern stuende auch in einem
    Verzeichnis, das im Repository liegt und weitergegeben wird.
    """
    heimat = str(Path.home())
    schuldig = [
        str(pfad.relative_to(abgelegt).as_posix())
        for pfad in abgelegt.rglob("*")
        if pfad.is_file() and pfad.suffix in (".html", ".js")
        and heimat in pfad.read_text(encoding="utf-8", errors="replace")
    ]
    assert not schuldig, f"diese Seiten nennen einen absoluten Pfad: {schuldig}"


def test_die_referenz_zeigt_keinen_fremden_quelltext(abgelegt):
    """Nur unser Code gehoert hinein - und nur er ist reproduzierbar.

    ``S3Client`` ist ein ``typing.Protocol``; Python haengt solchen Klassen ein
    ``__init__`` aus ``typing.py`` an, und pdoc zeigte dessen neun Zeilen
    CPython samt Zeilennummern. Die verschieben sich zwischen
    Patchversionen - der Byte-Vergleich war lokal gruen und auf CI rot, und
    die Ursache stand in einer von 12'000 Zeilen.

    Geprueft wird der Effekt, nicht die Ursache: Steht irgendwo Quelltext, den
    wir nicht geschrieben haben, faellt der Test.
    """
    # **Mit Wortgrenze, nicht als Teilzeichenkette.** ``FakeS3Client`` ist
    # unser Code, und sein ``__init__`` erscheint in der Referenz als
    # ``FakeS3Client.__init__`` - darin steckt ``S3Client.__init__``. Solange
    # das Doppel einen parameterlosen Konstruktor hatte, zeigte pdoc ihn gar
    # nicht und die Nadel traf zufaellig nichts; am 18.10.2026 bekam er einen
    # Parameter, und der Waechter meldete eigenen Code als fremden. Ein
    # Waechter, der Richtiges meldet, wird abgeschaltet.
    verraeter = (r"_no_init_or_replace_init", r"(?<![\w.])S3Client\.__init__")
    gefunden = {
        str(pfad.relative_to(abgelegt).as_posix()): [
            v for v in verraeter
            if re.search(v, pfad.read_text(encoding="utf-8"))
        ]
        for pfad in abgelegt.rglob("*.html")
    }
    schuldig = {name: was for name, was in gefunden.items() if was}
    assert not schuldig, (
        f"fremder Quelltext in der Referenz: {schuldig}. "
        "aus_fremdem_code() in tools/build_referenz.py greift nicht mehr."
    )


def test_der_filter_fuer_fremden_code_trifft_nur_fremden(abgelegt):
    """Er darf nicht zu viel wegnehmen.

    Ein erster Entwurf fragte nur, ob die Quelldatei unter ``src/crime``
    liegt - und warf damit auch alle ``NamedTuple``-Konstruktoren heraus, denn
    die tragen ``<string>`` als Quelldatei. Weg waren ``Lauf``, ``Tabelle``,
    ``Quelle`` und ``Standvergleich``.
    """
    erwartet = {
        "manifeste.html": ("Lauf.__init__", "Tabelle.__init__"),
        "storage.html": ("Standvergleich.__init__", "Boto3Client.__init__"),
        "gold_pipeline/build_gold.html": ("Quelle.__init__",),
    }
    for seite, namen in erwartet.items():
        inhalt = (abgelegt / seite).read_text(encoding="utf-8")
        fehlend = [n for n in namen if n not in inhalt]
        assert not fehlend, (
            f"{seite}: diese eigenen Konstruktoren fehlen: {fehlend} - "
            "der Filter nimmt zu viel weg"
        )


def test_ein_bekannter_docstring_steht_auch_in_der_referenz(abgelegt):
    """Die Probe aufs Exempel: Kommt der Text wirklich in der Seite an?

    Alles andere hier prueft Dateien und Namen. Dieser Test prueft, dass die
    Referenz tatsaechlich das zeigt, wofuer es sie gibt.
    """
    seite = (abgelegt / "silver_pipeline.html").read_text(encoding="utf-8")
    assert "Silver-Schicht" in seite
    assert "STUDIENSTAEDTE" in seite, "die Konstanten fehlen in der Referenz"


def test_die_marke_nennt_womit_gebaut_wurde(abgelegt):
    """Ohne sie waere nicht zu sagen, ob ein Byte-Vergleich ueberhaupt gilt."""
    marke = json.loads((abgelegt / br.MARKE).read_text(encoding="utf-8"))
    assert re.fullmatch(r"3\.\d+", marke["python"]), marke
    assert re.fullmatch(r"\d+\.\d+\.\d+", marke["pdoc"]), marke
    assert marke["plattform"] in ("posix", "nt"), marke


def test_ein_zweiter_lauf_liefert_dieselben_dateien(tmp_path, abgelegt):
    """Dieselbe Regel wie bei den Crosswalks, dem Feldkatalog und den Bildern.

    Der Bau laeuft als eigener Prozess - genau so, wie ein Mensch das Werkzeug
    aufruft, und nur so mit einem anderen Hash-Seed als der Testprozess.

    Verglichen wird nur dort, wo das Abgelegte auch entstanden sein koennte.
    pdocs Ausgabe unterscheidet sich zwischen Python-Versionen - 3.13 schreibt
    ``pathlib._local.Path``, wo 3.12 ``pathlib.Path`` schreibt, 19 von 25
    Dateien weichen ab - und zwischen Plattformen: Ein ``Path``-Vorgabewert
    heisst unter Windows ``WindowsPath`` und sonst ``PosixPath``, und pdoc
    druckt den Klassennamen mit. Beides laesst sich nicht wegkonfigurieren.

    Der Vergleich laeuft deshalb auf Linux und macOS mit der Python-Version
    aus der Marke. Ein Test, der auch unter Windows Bytes vergliche, waere
    dort dauerhaft rot, ohne dass etwas kaputt waere. Dieselbe Ueberlegung wie
    bei den drei PDF-Reproduktionen, die nur unter Linux laufen.

    **In CI im Job ``referenz``**, auf jedem Pull Request. Bis zum 14.11.2026
    stand hier "im 3.13-Job unter Ubuntu, auf jedem Push" - den gab es seit
    dem Zuschnitt vom 3.10.2026 nicht mehr, der Waechter uebersprang sich in
    jedem Job, und #236 und #239 kamen mit veralteten Seiten auf ``main``.
    Der Job setzt ``REFERENZ_PFLICHT=1``: Dort ist ein Ueberspringen ein
    Fehler, sonst faellt der Waechter beim naechsten Versionswechsel wieder
    still aus. ``tests/test_workflow_referenz.py`` haelt Job und Marke
    zusammen.
    """
    try:
        import pdoc
    except ImportError:
        _ausfallen("pdoc ist nicht installiert")
    marke = json.loads((abgelegt / br.MARKE).read_text(encoding="utf-8"))
    jetzt = f"{sys.version_info.major}.{sys.version_info.minor}"
    if (jetzt, pdoc.__version__, os.name) != (
        marke["python"], marke["pdoc"], marke["plattform"]
    ):
        _ausfallen(
            f"abgelegt mit Python {marke['python']}, pdoc {marke['pdoc']}, "
            f"{marke['plattform']}; hier laeuft Python {jetzt}, pdoc "
            f"{pdoc.__version__}, {os.name} - Bytes sind zwischen Versionen "
            "und Plattformen erwartbar verschieden"
        )

    ziel = tmp_path / "referenz"
    fertig = subprocess.run(
        [sys.executable, str(WERKZEUGE / "build_referenz.py"), "--ziel", str(ziel)],
        capture_output=True, text=True, cwd=PROJEKT,
    )
    assert fertig.returncode == 0, fertig.stderr[-2000:]

    frisch = {p.relative_to(ziel).as_posix() for p in ziel.rglob("*") if p.is_file()}
    alt = {p.relative_to(abgelegt).as_posix() for p in abgelegt.rglob("*") if p.is_file()}
    assert frisch == alt, (
        f"nur frisch: {sorted(frisch - alt)}; nur abgelegt: {sorted(alt - frisch)}. "
        "python tools/build_referenz.py"
    )
    anders = [
        rel for rel in sorted(alt)
        if _ohne_zeilenenden(abgelegt / rel) != _ohne_zeilenenden(ziel / rel)
    ]
    assert not anders, (
        f"{len(anders)} Datei(en) weichen vom frischen Bau ab: {anders[:5]}.\n"
        + _erste_abweichung(abgelegt / anders[0], ziel / anders[0])
        + "\nDie abgelegte Referenz ist aelter als der Code - "
        "python tools/build_referenz.py"
    )


def _erste_abweichung(abgelegt: Path, frisch: Path) -> str:
    """Die erste Zeile, in der sich zwei Seiten unterscheiden.

    Ohne sie sagt der Test nur *dass* etwas abweicht. Beim ersten roten Lauf
    war genau das das Problem: eine Datei, ein Name, und keine Ahnung, woran
    es liegt - die Ursache lag in einer von 12'000 Zeilen.
    """
    from difflib import unified_diff

    zeilen = list(unified_diff(
        _ohne_zeilenenden(abgelegt).decode("utf-8", "replace").splitlines(),
        _ohne_zeilenenden(frisch).decode("utf-8", "replace").splitlines(),
        fromfile="abgelegt", tofile="frisch", n=0, lineterm="",
    ))
    gekuerzt = [z[:400] for z in zeilen[:12]]
    return "\n".join(gekuerzt)


def _ohne_zeilenenden(pfad: Path) -> bytes:
    """Der Inhalt, unabhaengig davon, ob CRLF oder LF darin steht.

    ``.gitattributes`` legt die Referenz mit LF ab; ein Windows-Bau schreibt
    aber CRLF. Der Unterschied sagt nichts ueber den Inhalt aus.
    """
    return pfad.read_bytes().replace(b"\r\n", b"\n")


# --------------------------------------------------------------- Einbettung


def test_die_referenz_ist_versioniert():
    """Erzeugte Artefakte liegen in diesem Projekt im Repository.

    Dieselbe Regel wie bei den Crosswalks, dem Feldkatalog und den
    Architekturbildern: Was sich reproduzieren laesst, gehoert hinein - dann
    ist es pruefbar, und es ist da, ohne dass jemand etwas installiert.
    """
    verfolgt = subprocess.run(
        ["git", "ls-files", "docs/referenz"],
        capture_output=True, text=True, cwd=PROJEKT,
    )
    if verfolgt.returncode != 0:
        pytest.skip("kein git-Repository")
    dateien = [z for z in verfolgt.stdout.splitlines() if z.strip()]
    assert len(dateien) >= 25, (
        f"nur {len(dateien)} Dateien unter docs/referenz sind versioniert"
    )
    assert "docs/referenz/index.html" in dateien


def test_die_referenz_wird_mit_lf_abgelegt():
    """Sonst legt ein Windows-Bau sie mit CRLF ab und der Vergleich wackelt."""
    regeln = (PROJEKT / ".gitattributes").read_text(encoding="utf-8")
    assert re.search(r"^docs/referenz/\*\* .*eol=lf", regeln, re.M), (
        "die eol-Regel fuer docs/referenz fehlt in .gitattributes"
    )
    assert "config/" not in regeln.split("# Bewusst nur hier")[0], (
        "die Crosswalks unter config/ sind mit CRLF abgelegt und duerfen "
        "keine eol-Regel bekommen - drei Tests vergleichen ihre Bytes"
    )


def test_pdoc_ist_eine_entwicklungsabhaengigkeit():
    """Sonst scheitert der Bau bei dem, der ihn zum ersten Mal aufruft."""
    daten = tomllib.loads((PROJEKT / "pyproject.toml").read_text(encoding="utf-8"))
    dev = daten["project"]["optional-dependencies"]["dev"]
    assert any(e.startswith("pdoc") for e in dev), "pdoc fehlt unter [dev]"

    lock = (PROJEKT / "requirements.lock").read_text(encoding="utf-8")
    assert re.search(r"^pdoc==", lock, re.M), "pdoc fehlt in requirements.lock"
