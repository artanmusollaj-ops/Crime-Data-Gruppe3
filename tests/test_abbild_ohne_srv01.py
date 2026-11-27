"""FR-46: Nichts im Abbild setzt ``srv01`` voraus.

**Warum es diesen Waechter gibt.** Am 14.11.2026 stand FR-46 auf "nicht
geprueft", und die Pruefung fand vier echte Annahmen im Code, der ins Abbild
geht: eine Vorgabe ``S3_ENDPOINT`` auf den Eimer von srv01, die Hostnamen und
Befehle der Serverfassung der Startseite, zwei Abhilfetexte in
``pruefe_stand`` und eine Meldung der Vorpruefung. Keine davon fiel auf
srv01 auf - dort stimmten sie ja. Auffallen wuerden sie erst in einer zweiten
Umgebung (FR-44, FR-47), und dann als still falscher Zugriff statt als
Fehler.

**Was er durchsucht.** Alles, was die ``COPY``-Anweisungen der beiden
Dockerfiles ins Abbild legen - die Liste wird aus den Anweisungen gelesen,
nicht abgeschrieben, damit ein neues ``COPY`` von selbst mitgeprueft wird:

* Python-Dateien (``src/``, ``docker/jupyter_server_config.py``): ihre
  Zeichenketten, ohne Docstrings und Kommentare.
* Notebooks: die Code-Zellen, ohne Kommentarzeilen.
* Shell-Skripte (``docker/jupyter-einstieg.sh``): ohne Kommentarzeilen.
* Die Dockerfiles selbst: ihre Anweisungen, ohne Kommentarzeilen.
* Alles Uebrige (``config/``, die Lock-Dateien, ``pyproject.toml``, die
  statischen Dateien unter ``src/``): der ganze Text.

**Nicht** durchsucht werden Kommentare und Docstrings: Sie nennen srv01 als
Beispiel oder als Geschichte und setzen nichts voraus. Aus demselben Grund
ausgenommen ist ``docs/intern/AENDERUNGEN.md``: Das ``Dockerfile`` kopiert es
nur als Herkunftsangabe, und es ist das Projektgedaechtnis - es erzaehlt,
was auf srv01 geschah, und muss srv01 deshalb nennen. Was srv01 braucht,
setzt ``docker-compose.srv01.yml``; die Datei liegt nicht im Abbild.

**Was er nicht kann.** Er sieht Zeichenketten, keine Bedeutung. Ein Hostname,
der aus Teilen zusammengesetzt wird, die einzeln unverdaechtig sind, entgeht
ihm - die Grenze ist genannt, damit niemand den Waechter fuer mehr haelt.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILES = (PROJECT_ROOT / "Dockerfile", PROJECT_ROOT / "Dockerfile.jupyter")
#: Kopiert, aber Geschichte und keine Annahme - Begruendung im Modul-Docstring.
AUSGENOMMEN = frozenset({"docs/intern/AENDERUNGEN.md"})
#: Was ``.dockerignore`` ohnehin aus dem Baukontext haelt und was nur der
#: Host erzeugt; es landet nie im Abbild.
NICHT_IM_KONTEXT = re.compile(r"(^|/)(__pycache__|[^/]+\.egg-info)(/|$)|\.py[cod]$")

#: Woran eine srv01-Annahme zu erkennen ist: der Maschinenname, die Domain,
#: an der alle Hostnamen haengen, der Ablagepfad des Hosts und das
#: Namensmuster der Dienste und Router - mit Bindestrich die Dienste und
#: Hostnamen, mit Unterstrich die Netze und Datentraeger, die Compose mit dem
#: Projektnamen voranstellt (``urbancrime_sicherung``).
MUSTER = re.compile(r"srv01|datenwerft|/srv/|urbancrime[-_]", re.IGNORECASE)


def zeichenketten(quelltext: str) -> list[tuple[int, str]]:
    """Jede Zeichenkette des Quelltexts mit Zeile, ohne Docstrings.

    Ein Docstring ist eine Zeichenkette, die allein als Anweisung steht -
    dazu zaehlt auch eine Erlaeuterung in Anfuehrungszeichen unter einer
    Zuweisung.
    Kommentare tauchen im Syntaxbaum gar nicht auf. Die Teile einer f-Zeichen-
    kette sind eigene Konstanten und werden je einzeln geprueft.
    """
    baum = ast.parse(quelltext)
    docstrings = {id(knoten.value) for knoten in ast.walk(baum)
                  if isinstance(knoten, ast.Expr)
                  and isinstance(knoten.value, ast.Constant)
                  and isinstance(knoten.value.value, str)}
    return [(knoten.lineno, knoten.value) for knoten in ast.walk(baum)
            if isinstance(knoten, ast.Constant)
            and isinstance(knoten.value, str)
            and id(knoten) not in docstrings]


def anweisungen(dockerfile: str) -> list[tuple[int, str]]:
    """Die Anweisungen eines Dockerfiles, Fortsetzungszeilen angehaengt.

    Kommentarzeilen fallen weg, auch zwischen Fortsetzungszeilen - Docker
    selbst behandelt sie dort genauso.
    """
    gefunden: list[tuple[int, str]] = []
    offen: tuple[int, list[str]] | None = None
    for nummer, zeile in enumerate(dockerfile.splitlines(), start=1):
        roh = zeile.strip()
        if not roh or roh.startswith("#"):
            continue
        if offen is None:
            offen = (nummer, [])
        offen[1].append(roh.rstrip("\\").strip())
        if not roh.endswith("\\"):
            gefunden.append((offen[0], " ".join(offen[1])))
            offen = None
    if offen is not None:
        gefunden.append((offen[0], " ".join(offen[1])))
    return gefunden


def befunde_python(pfad: Path) -> list[str]:
    name = pfad.relative_to(PROJECT_ROOT).as_posix()
    return [f"{name}:{zeile}: {wert[:80]!r}"
            for zeile, wert in zeichenketten(pfad.read_text(encoding="utf-8"))
            if MUSTER.search(wert)]


def befunde_dockerfile(pfad: Path) -> list[str]:
    name = pfad.relative_to(PROJECT_ROOT).as_posix()
    return [f"{name}:{zeile}: {text[:80]!r}"
            for zeile, text in anweisungen(pfad.read_text(encoding="utf-8"))
            if MUSTER.search(text)]


def kopierte_quellen() -> list[str]:
    """Die Quellen aller ``COPY``-Anweisungen beider Dockerfiles.

    Optionen (``--chown=...``) fallen weg, das letzte Wort ist das Ziel.
    ``COPY --from=...`` kopiert aus einer anderen Stufe, nicht aus dem
    Baukontext, und zaehlt nicht.
    """
    quellen: list[str] = []
    for dockerfile in DOCKERFILES:
        for _, anweisung in anweisungen(dockerfile.read_text(encoding="utf-8")):
            woerter = anweisung.split()
            if woerter[0].upper() != "COPY" or any(w.startswith("--from") for w in woerter):
                continue
            argumente = [w for w in woerter[1:] if not w.startswith("--")]
            quellen += argumente[:-1]
    return quellen


def dateien_im_abbild() -> list[Path]:
    """Jede Datei, die eine ``COPY``-Anweisung aus dem Baukontext mitnimmt."""
    gefunden: set[Path] = set()
    for quelle in kopierte_quellen():
        pfad = PROJECT_ROOT / quelle.rstrip("/")
        kandidaten = sorted(pfad.rglob("*")) if pfad.is_dir() else [pfad]
        for datei in kandidaten:
            name = datei.relative_to(PROJECT_ROOT).as_posix()
            if datei.is_file() and not NICHT_IM_KONTEXT.search(name) \
                    and name not in AUSGENOMMEN:
                gefunden.add(datei)
    return sorted(gefunden)


def python_im_abbild() -> list[Path]:
    return [p for p in dateien_im_abbild() if p.suffix == ".py"]


def zeilen_ohne_kommentar(text: str) -> list[tuple[int, str]]:
    return [(nummer, zeile) for nummer, zeile in enumerate(text.splitlines(), start=1)
            if zeile.strip() and not zeile.strip().startswith("#")]


def notebook_code(text: str) -> list[tuple[int, str]]:
    """Die Zeilen der Code-Zellen, ohne Kommentarzeilen; die Zeile ist die
    Nummer der Zelle (ab 1), denn im JSON gibt es keine Quelltextzeilen."""
    zellen = json.loads(text)["cells"]
    return [(nummer, zeile)
            for nummer, zelle in enumerate(zellen, start=1)
            if zelle.get("cell_type") == "code"
            for _, zeile in zeilen_ohne_kommentar("".join(zelle.get("source", [])))]


def befunde_uebrige(pfad: Path) -> list[str]:
    """Was weder Python noch Dockerfile ist, nach seiner Art gelesen."""
    name = pfad.relative_to(PROJECT_ROOT).as_posix()
    text = pfad.read_text(encoding="utf-8", errors="replace")
    if pfad.suffix == ".ipynb":
        zeilen = notebook_code(text)
        ort = "Zelle "
    elif pfad.suffix == ".sh":
        zeilen = zeilen_ohne_kommentar(text)
        ort = ""
    else:
        zeilen = list(enumerate(text.splitlines(), start=1))
        ort = ""
    return [f"{name}:{ort}{nummer}: {zeile.strip()[:80]!r}"
            for nummer, zeile in zeilen if MUSTER.search(zeile)]


# --------------------------------------------------------------------------
# Der Waechter
# --------------------------------------------------------------------------


def test_kein_srv01_literal_im_python_des_abbilds():
    dateien = python_im_abbild()
    assert len(dateien) > 50, f"nur {len(dateien)} Dateien gefunden - falscher Pfad?"
    befunde = [b for pfad in dateien for b in befunde_python(pfad)]
    assert not befunde, (
        "srv01-Annahmen im Abbild - der Wert gehoert in die Umgebung "
        "(docker-compose.srv01.yml oder .env), nicht in den Code:\n"
        + "\n".join(befunde))


def test_kein_srv01_in_den_uebrigen_kopierten_dateien():
    """``config/``, Lock-Dateien, Notebooks, Shell-Skript, statische Dateien."""
    dockerfiles = {p.resolve() for p in DOCKERFILES}
    dateien = [p for p in dateien_im_abbild()
               if p.suffix != ".py" and p.resolve() not in dockerfiles]
    befunde = [b for pfad in dateien for b in befunde_uebrige(pfad)]
    assert not befunde, "srv01-Annahmen im Abbild:\n" + "\n".join(befunde)


def test_die_kopierten_pfade_kommen_aus_den_copy_anweisungen():
    """Fehlte hier etwas, waere der Waechter an der Stelle blind, ohne es zu
    sagen - etwa wenn sich das Zerlegen der Anweisungen verschluckt."""
    namen = {p.relative_to(PROJECT_ROOT).as_posix() for p in dateien_im_abbild()}
    for erwartet in ("config/quellen.toml", "docker/jupyter-einstieg.sh",
                     "docker/jupyter_server_config.py", "pyproject.toml",
                     "notebooks/35_kontrollen.ipynb", "src/crime/storage/config.py"):
        assert erwartet in namen, f"{erwartet} fehlt in den durchsuchten Dateien"
    assert "docs/intern/AENDERUNGEN.md" in kopierte_quellen(), (
        "das Dockerfile kopiert AENDERUNGEN.md nicht mehr - dann ist die "
        "Ausnahme ueberfluessig")
    assert not namen & AUSGENOMMEN
    assert not [n for n in namen if NICHT_IM_KONTEXT.search(n)]


@pytest.mark.parametrize("pfad", DOCKERFILES, ids=lambda p: p.name)
def test_kein_srv01_in_den_anweisungen_der_dockerfiles(pfad):
    assert pfad.is_file(), f"{pfad.name} fehlt"
    befunde = befunde_dockerfile(pfad)
    assert not befunde, "srv01-Annahmen im Dockerfile:\n" + "\n".join(befunde)


# --------------------------------------------------------------------------
# Der Waechter gegen sich selbst: findet er, was er finden soll?
# --------------------------------------------------------------------------


def test_er_findet_ein_literal_und_nennt_die_zeile():
    quelltext = (
        '"""Laeuft auf srv01 - ein Docstring, kein Befund."""\n'
        "# https://x.datenwerft.ch - ein Kommentar, kein Befund\n"
        "def f():\n"
        '    """Auch hier: srv01."""\n'
        '    return "https://x.datenwerft.ch"\n'
        'G = f"docker compose -f docker-compose.{name}.yml -p urbancrime-{n}"\n'
        "X = 1\n"
        '"""Erlaeuterung unter X, nennt /srv/ - kein Befund."""\n'
    )
    treffer = [(z, w) for z, w in zeichenketten(quelltext) if MUSTER.search(w)]
    assert [z for z, _ in treffer] == [5, 6], treffer


def test_er_liest_dockerfile_anweisungen_ohne_kommentare():
    text = ("# srv01 baut nicht selbst - kein Befund\n"
            "FROM python:3.13\n"
            "RUN echo a \\\n"
            "    # Kommentar mitten drin, srv01\n"
            "    && echo /srv/urbancrime\n"
            "ENV X=1\n")
    gefunden = anweisungen(text)
    assert gefunden == [(2, "FROM python:3.13"),
                        (3, "RUN echo a && echo /srv/urbancrime"),
                        (6, "ENV X=1")], gefunden
    assert [z for z, t in gefunden if MUSTER.search(t)] == [3]


def test_er_liest_notebooks_und_skripte_ohne_kommentarzeilen():
    notebook = json.dumps({"cells": [
        {"cell_type": "markdown", "source": ["Auf srv01 gelaufen"]},
        {"cell_type": "code", "source": ["# srv01 - Kommentar\n",
                                         "pfad = '/srv/docker/x'\n"]},
    ]})
    assert [(z, t) for z, t in notebook_code(notebook) if MUSTER.search(t)] == [
        (2, "pfad = '/srv/docker/x'")]
    skript = "#!/bin/sh\n# laeuft auf srv01\ndocker network inspect urbancrime_sicherung\n"
    assert [z for z, t in zeilen_ohne_kommentar(skript) if MUSTER.search(t)] == [3]
