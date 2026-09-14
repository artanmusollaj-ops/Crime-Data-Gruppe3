#!/usr/bin/env python3
"""Erzeugt die Code-Referenz aus den Docstrings.

    python tools/build_referenz.py

Schreibt ``docs/referenz/`` - eine Seite je Modul, mit Suche und Quelltext.
Das Verzeichnis **ist versioniert**, wie die Crosswalks, der Feldkatalog und
die Architekturbilder: Ein erzeugtes Artefakt gehoert in das Repository, wenn
ein zweiter Lauf dieselbe Datei liefert. Dann ist es pruefbar, und es ist da,
auch wenn jemand nichts installieren will.

**Warum es das braucht.** Dieses Projekt hat mehr Erklaerung als Code: rund
11'600 Zeilen Prosa gegen 10'569 Zeilen Produktionscode. Der groesste Teil
davon steht in Docstrings - und damit an der einzigen Stelle, an der man ihn
nur findet, wenn man ohnehin schon weiss, wo man suchen muss. Wer das Projekt
verstehen will, ohne zehn Pakete durchzublaettern, hatte bisher nichts.
``docs/architektur.md`` zeigt den Aufbau, ``docs/eine-zahl.md`` den Weg einer
Zahl - dies hier ist das Nachschlagewerk dazwischen.

**Was das Werkzeug zusaetzlich tut.** pdoc allein erzeugt als Startseite eine
nackte Modulliste mit Fremdlogo. Die wird hier ersetzt: Die zehn Pakete
stehen nach ihrer **Tiefe im Importgraph** gruppiert - Fundament, was darauf
aufbaut, und so weiter - und jede Kurzbeschreibung ist die erste Zeile des
jeweiligen Paket-Docstrings. Beides ist abgeleitet, nicht gepflegt: Ein neues
Paket erscheint von selbst an der richtigen Stelle, und es gibt keine zweite
Beschreibung, die veralten koennte.

**Warum der Hash-Seed festgenagelt wird.** Manche Vorgabewerte im Code sind
Mengen, und pdoc druckt sie mit ``repr``. Die Reihenfolge einer Menge von
Zeichenketten haengt an deren Hashwerten, und die sind je Prozess zufaellig -
``frozenset({'complete', 'success'})`` im einen Lauf, ``frozenset({'success',
'complete'})`` im naechsten. Von fuenf Laeufen hintereinander unterschieden
sich bis zu vier Dateien, ohne dass sich eine Zeile Code geaendert haette.
``main`` startet den Prozess deshalb einmal neu, mit ``PYTHONHASHSEED=0``.

Gefunden wurde das erst, als die Referenz ins Repository sollte. Der erste
Waechter baute zweimal **im selben Prozess** - und derselbe Prozess hat
denselben Seed. Er war gruen, weil er die Frage nicht gestellt hat.

**Was nicht in die Referenz gehoert.** ``pdoc_vorlage/`` ergaenzt pdocs Regel
um einen Fall: Mitglieder, deren Quelldatei ausserhalb von ``src/crime``
liegt, werden nicht gezeigt. Betroffen ist genau eines - das ``__init__``, das
Python dem ``typing.Protocol`` ``S3Client`` anhaengt. pdoc haette neun Zeilen
CPython in die Seite geschrieben, mit den Zeilennummern aus ``typing.py``.
Die verschieben sich zwischen Patchversionen, und daran fiel der Waechter auf
CI durch, waehrend er lokal gruen war.

**Was die Marke soll.** ``erzeugt-mit.json`` haelt fest, welcher Interpreter
und welche pdoc-Version die abgelegten Seiten geschrieben haben. Die Ausgabe
ist naemlich nur *innerhalb* einer Python-Version byteweise gleich: 3.13
schreibt ``pathlib._local.Path``, wo 3.12 noch ``pathlib.Path`` schreibt, und
zeigt fuer ``__init__`` einen Quelltext, den 3.12 nicht hat. Neunzehn von
fuenfundzwanzig Dateien sind deshalb zwischen 3.12 und 3.13 verschieden. Der
Waechter vergleicht Bytes nur, wenn er auf derselben Version laeuft, und sagt
sonst, warum er es nicht tut.

**Was der Waechter prueft.** ``tests/test_referenz.py`` haelt fest, dass jedes
Paket einen Docstring hat, dass die Startseite jedes Paket nennt, und dass ein
zweiter Lauf dieselben Dateien liefert - dieselbe Regel wie bei den
Crosswalks, beim Feldkatalog und bei den Architekturbildern.
"""

from __future__ import annotations

import argparse
import ast
import html
import json
import os
import shutil
import subprocess
import sys
import warnings
from pathlib import Path
from typing import NamedTuple

PROJEKT = Path(__file__).resolve().parents[1]
QUELLE = PROJEKT / "src" / "crime"
ZIEL = PROJEKT / "docs" / "referenz"
VORLAGE = Path(__file__).resolve().parent / "pdoc_vorlage"
MARKE = "erzeugt-mit.json"

# Irgendein fester Wert; 0 ist der uebliche. Entscheidend ist nur, dass er
# ueber Laeufe hinweg derselbe bleibt.
HASHSEED = "0"

sys.path.insert(0, str(QUELLE))
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Die Gruppen sind die vier Gruppen des Gesamtlaufs, plus die beiden Pakete,
# die zu keiner Stufe gehoeren. Wo ein Paket steht, sagt also
# orchestration.run_all.STUFEN - dieselbe Quelle, aus der das Datenflussbild
# entsteht. Eine eigene Liste hier waere die zweite Wahrheit, die als erste
# veraltet.
#
# Ein erster Versuch gruppierte nach der Tiefe im Importgraph. Das ergab
# lesbare Zahlen und falsche Namen: orchestration landete unter "Ableitung",
# gold_pipeline in einer Ebene ohne Titel. Die Tiefe bedeutet etwas anderes
# als die Schicht - naemlich wer wessen Code importiert, und das ist im
# Architekturbild schon die Pointe.
#
# Die Gruppenzeile nennt die Zahl der Stufen, nicht die Aufgabe der Schicht.
# Ein erster Entwurf schrieb "macht aus mehreren Quellen vergleichbare
# Tabellen" ueber silver_pipeline - und genau derselbe Satz stand einen
# Zentimeter darunter nochmal, als Docstring des Pakets. Was die Schicht tut,
# sagt der Docstring; die Gruppe sagt, wie viel Lauf sie ist.
FUNDAMENTTEXT = "keine Stufe im Lauf - alles andere haengt daran"

# Dieselbe Palette wie die Architekturbilder, damit die Referenz nicht wie ein
# fremdes Werkzeug aussieht.
STIL = """
:root {
  --grund: #ffffff; --text: #14304a; --matt: #5b7086;
  --linie: #d7dee6; --signal: #c2410c; --feld: #f6f8fa;
}
@media (prefers-color-scheme: dark) {
  :root {
    --grund: #0f1922; --text: #dde5ee; --matt: #94a6b8;
    --linie: #27384a; --signal: #dda05c; --feld: #16222e;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--grund); color: var(--text);
  font: 16px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
main { max-width: 52rem; margin: 0 auto; padding: 3rem 1.5rem 5rem; }
h1 { font-size: 1.9rem; line-height: 1.25; margin: 0 0 .4rem; text-wrap: balance; }
h2 {
  font-size: .78rem; letter-spacing: .09em; text-transform: uppercase;
  color: var(--matt); margin: 2.6rem 0 .2rem; font-weight: 600;
}
h2 span { text-transform: none; letter-spacing: 0; font-weight: 400; }
p { margin: .4rem 0; }
.vorspann { color: var(--matt); max-width: 40rem; }
.gruppe { border-top: 1px solid var(--linie); margin-top: .7rem; }
.paket {
  display: grid; grid-template-columns: 13rem 1fr; gap: 0 1.5rem;
  padding: .75rem 0; border-bottom: 1px solid var(--linie); align-items: baseline;
}
.paket a {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .95rem; color: var(--signal); text-decoration: none;
}
.paket a:hover, .paket a:focus { text-decoration: underline; }
.paket p { color: var(--matt); font-size: .95rem; margin: 0; }
.zaehler {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: .8rem; color: var(--matt);
}
.fuss {
  margin-top: 3.5rem; padding-top: 1.2rem; border-top: 1px solid var(--linie);
  color: var(--matt); font-size: .9rem;
}
.fuss a { color: var(--signal); }
code {
  background: var(--feld); padding: .1rem .35rem; border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .88em;
}
@media (max-width: 34rem) { .paket { grid-template-columns: 1fr; gap: .15rem; } }
"""


def pakete() -> list[str]:
    """Jedes Verzeichnis unter ``src/crime/`` mit einer ``__init__.py``.

    Dieselbe Regel, nach der setuptools die Pakete findet
    (``[tool.setuptools.packages.find]``). Eine neue Pipeline braucht deshalb
    hier keinen Eintrag - sonst waere dies die Liste, die als erste veraltet.
    """
    return sorted(
        p.name for p in QUELLE.iterdir()
        if p.is_dir() and (p / "__init__.py").is_file()
    )


def beschreibung(paket: str) -> str:
    """Die erste Zeile des Paket-Docstrings, ohne den Schlusspunkt zu verlieren.

    Gelesen wird der AST, nicht das importierte Modul: Die Startseite soll
    auch dann noch entstehen, wenn ein Import Zeit oder Zugriff braucht.
    """
    quelle = (QUELLE / paket / "__init__.py").read_text(encoding="utf-8")
    text = ast.get_docstring(ast.parse(quelle)) or ""
    return text.strip().split("\n")[0].strip()


def modulzahl(paket: str) -> int:
    """Wie viele Module das Paket hat, ``__init__.py`` mitgezaehlt."""
    return sum(
        1 for p in (QUELLE / paket).rglob("*.py")
        if "__pycache__" not in p.parts
    )


def stufen_je_paket() -> dict[str, list[str]]:
    """Welche Gruppe des Gesamtlaufs welche Pakete benutzt.

    Gelesen aus ``orchestration.run_all.STUFEN``: Jede Stufe nennt ein Modul,
    und dessen erster Namensteil ist das Paket.
    """
    from orchestration.run_all import STUFEN

    zuordnung: dict[str, list[str]] = {}
    for stufe in STUFEN:
        paket = stufe.modul.split(".")[0]
        if paket not in zuordnung.setdefault(stufe.gruppe, []):
            zuordnung[stufe.gruppe].append(paket)
    return zuordnung


def stufenzahl(gruppe: str) -> int:
    """Wie viele Stufen des Gesamtlaufs zu dieser Gruppe gehoeren."""
    from orchestration.run_all import STUFEN

    return sum(1 for stufe in STUFEN if stufe.gruppe == gruppe)


def gruppiert() -> list[tuple[str, str, list[str]]]:
    """Die Pakete in der Reihenfolge des Gesamtlaufs, mit Titel und Erklaerung.

    Zuerst das Fundament, dann die vier Gruppen von ``run_all``, zuletzt alles,
    was zu keiner Stufe gehoert und nicht Fundament ist. Ein neues Paket
    erscheint damit von selbst an der richtigen Stelle, sobald es eine Stufe
    bekommt - und solange es keine hat, faellt es unter *Steuerung* auf, statt
    stillschweigend zu verschwinden.
    """
    from build_architekturbilder import FUNDAMENT
    from orchestration.run_all import GRUPPEN

    alle = pakete()
    je_gruppe = stufen_je_paket()
    ergebnis: list[tuple[str, str, list[str]]] = []
    vergeben: set[str] = set()

    fundament = [p for p in alle if p in FUNDAMENT]
    if fundament:
        ergebnis.append(("Fundament", FUNDAMENTTEXT, fundament))
        vergeben.update(fundament)

    for gruppe in GRUPPEN:
        drin = [p for p in je_gruppe.get(gruppe, []) if p in alle and p not in vergeben]
        if not drin:
            continue
        anzahl = stufenzahl(gruppe)
        ergebnis.append((
            gruppe.capitalize(),
            f"{anzahl} {'Stufe' if anzahl == 1 else 'Stufen'} im Gesamtlauf",
            drin,
        ))
        vergeben.update(drin)

    rest = [p for p in alle if p not in vergeben]
    if rest:
        gesamt = sum(stufenzahl(g) for g in GRUPPEN)
        ergebnis.append(("Steuerung", f"faehrt die {gesamt} Stufen und raeumt auf", rest))
    return ergebnis


def startseite() -> str:
    """Die Startseite, die pdocs nackte Modulliste ersetzt."""
    zeilen = [
        "<!doctype html>",
        '<html lang="de"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Code-Referenz &ndash; Crime-Data-Gruppe3</title>",
        f"<style>{STIL}</style>",
        "</head><body><main>",
        "<h1>Code-Referenz</h1>",
        '<p class="vorspann">Jedes Paket, jedes Modul, jede Funktion &ndash; mit '
        "dem Docstring, der dort steht, und dem Quelltext daneben. Die Seiten "
        "sind durchsuchbar. Erzeugt aus dem Code, nicht gepflegt.</p>",
    ]
    for name, erklaerung, drin in gruppiert():
        zeilen.append(f"<h2>{html.escape(name)} <span>&middot; {html.escape(erklaerung)}</span></h2>")
        zeilen.append('<div class="gruppe">')
        for paket in drin:
            zeilen.append(
                f'<div class="paket"><div><a href="{paket}.html">{paket}</a>'
                f'<div class="zaehler">{modulzahl(paket)} Module</div></div>'
                f"<p>{html.escape(beschreibung(paket))}</p></div>"
            )
        zeilen.append("</div>")
    zeilen += [
        '<p class="fuss">Erzeugt von <code>tools/build_referenz.py</code>. '
        "Wie der Aufbau zusammenh&auml;ngt, steht in "
        '<a href="../architektur.md">architektur.md</a>; woher eine Zahl kommt, '
        'in <a href="../eine-zahl.md">eine-zahl.md</a>.</p>',
        "</main></body></html>",
    ]
    return "\n".join(zeilen) + "\n"


class Ergebnis(NamedTuple):
    """Was ein Bau geschrieben hat, und was pdoc dabei nicht deuten konnte."""

    dateien: list[Path]
    warnungen: list[str]


def baue(ziel: Path = ZIEL) -> Ergebnis:
    """Erzeugt die Referenz nach ``ziel`` und liefert die geschriebenen Dateien.

    Das Zielverzeichnis wird vorher geleert. Sonst bliebe die Seite eines
    geloeschten Moduls stehen, und die Referenz behauptete Code, den es nicht
    mehr gibt - der Fehler, den ein erzeugtes Artefakt gerade vermeiden soll.

    **Warum die Warnungen eingesammelt statt durchgereicht werden.** pdoc
    meldet rund dreissig Typannotationen, die es nicht aufloesen kann. Sie
    haben zwei Ursachen, und keine davon betrifft die Docstrings:

    Die meisten sind Felder von ``NamedTuple``-Klassen. Mit ``from __future__
    import annotations`` sind Annotationen Zeichenketten, und pdoc sucht die
    Namen fuer das erzeugte ``__init__`` im falschen Namensraum.

    Die uebrigen vier kommen aus ``storage``: Die Methode ``list`` der drei
    S3-Klassen verdeckt im Klassenkoerper das eingebaute ``list``, weshalb
    ``list[Objekt]`` dort nicht mehr aufloesbar ist. Zur Laufzeit stoert das
    nichts - Annotationen werden nie ausgewertet, und ``typing.get_type_hints``
    sieht den Modulnamensraum, in dem ``list`` das eingebaute ist. Der Name
    bleibt, weil er die S3-Schnittstelle spiegelt; ihn umzubenennen waere eine
    Aenderung an drei Klassen und ihren Aufrufern, um eine Warnung
    loszuwerden.

    Dreissig Zeilen Warnung bei jedem Aufruf haetten dagegen genau eine
    Wirkung: Man liest sie nach dem dritten Mal nicht mehr - auch die nicht,
    die einmal etwas bedeutet.

    Wirklich schiefgehen kann nur eines, und das wird hier geprueft: dass ein
    Paket gar keine Seite bekommt, weil sein Import scheitert.
    """
    import pdoc
    import pdoc.render

    if ziel.exists():
        shutil.rmtree(ziel)

    pdoc.render.configure(
        docformat="markdown",
        footer_text="Crime-Data-Gruppe3 · erzeugt aus den Docstrings",
        search=True,
        show_source=True,
        template_directory=VORLAGE,
    )
    pdoc.render.env.globals["aus_fremdem_code"] = aus_fremdem_code
    with warnings.catch_warnings(record=True) as gesammelt:
        warnings.simplefilter("always")
        pdoc.pdoc(*pakete(), output_directory=ziel)

    (ziel / "index.html").write_text(startseite(), encoding="utf-8")
    (ziel / MARKE).write_text(
        json.dumps(erzeugt_mit(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    fehlend = [p for p in pakete() if not (ziel / f"{p}.html").is_file()]
    if fehlend:
        raise RuntimeError(
            "Fuer diese Pakete ist keine Seite entstanden - vermutlich "
            f"scheitert ihr Import: {', '.join(fehlend)}"
        )

    return Ergebnis(
        dateien=sorted(p for p in ziel.rglob("*") if p.is_file()),
        warnungen=[str(w.message) for w in gesammelt],
    )


def aus_fremdem_code(doc: object) -> bool:
    """Ob ein Mitglied aus einer Datei ausserhalb von ``src/crime`` stammt.

    Die Vorlage unter ``pdoc_vorlage/`` benutzt das, um genau einen Fall
    auszuschliessen: ``S3Client`` ist ein ``typing.Protocol``, und Python
    haengt solchen Klassen beim Erzeugen ein ``__init__`` aus ``typing.py``
    an. pdoc zeigt jedes ``__init__`` mit Parametern - hier also neun Zeilen
    CPython, mit deren Zeilennummern.

    Das war der Fehler, an dem der Waechter auf CI durchfiel, waehrend er
    lokal gruen war: Die Zeilennummern in ``typing.py`` verschieben sich
    zwischen CPython-Patchversionen. Auf 3.13.0 stand die Funktion bei Zeile
    1940, auf der Version des Linux-Runners anderswo.

    ``<string>`` als Quelldatei heisst *erzeugt*, nicht *fremd* - so tragen es
    die ``NamedTuple``-Konstruktoren, und die gehoeren in die Referenz.
    """
    datei = getattr(doc, "source_file", None)
    if datei is None:
        return False
    pfad = Path(datei)
    if not pfad.is_absolute() or not pfad.exists():
        return False
    return not pfad.resolve().is_relative_to(QUELLE.resolve())


def erzeugt_mit() -> dict[str, str]:
    """Womit die abgelegten Seiten geschrieben wurden.

    Steht als ``erzeugt-mit.json`` neben ihnen. Der Waechter vergleicht Bytes
    nur, wenn er auf denselben Versionen laeuft - die Ausgabe ist zwischen
    Python-Versionen nicht gleich, und ein Test, der das ignoriert, waere auf
    der halben Testmatrix rot, ohne dass etwas kaputt waere.
    """
    import pdoc

    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "pdoc": pdoc.__version__,
    }


def main(argv: list[str] | None = None) -> int:
    zerleger = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    zerleger.add_argument(
        "--ziel", type=Path, default=ZIEL,
        help="wohin geschrieben wird (Vorgabe: docs/referenz)",
    )
    argumente = zerleger.parse_args(argv)

    if os.environ.get("PYTHONHASHSEED") != HASHSEED:
        # Einmal neu starten, damit die Reihenfolge von Mengen feststeht.
        # Die Begruendung steht oben im Modul-Docstring.
        fertig = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             *(argv if argv is not None else sys.argv[1:])],
            env={**os.environ, "PYTHONHASHSEED": HASHSEED},
        )
        return fertig.returncode

    ziel = argumente.ziel
    dateien, warnungen = baue(ziel)
    seiten = [p for p in dateien if p.suffix == ".html"]
    groesse = sum(p.stat().st_size for p in dateien) / 1_048_576
    wohin = ziel if not ziel.is_relative_to(PROJEKT) else ziel.relative_to(PROJEKT)
    print(f"{len(seiten)} Seiten, {groesse:.1f} MB -> {wohin}")
    if warnungen:
        print(f"{len(warnungen)} Typannotationen konnte pdoc nicht aufloesen "
              "(NamedTuple-Felder und storage.list). Die Docstrings sind "
              "davon nicht betroffen; die Begruendung steht in baue().")
    print(f"Zum Ansehen: {(ziel / 'index.html').as_uri()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
