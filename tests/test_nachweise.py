"""Die ausgefuehrten Notebooks unter ``docs/nachweise/`` gegen die Notebooks.

Die Beurteilung von LN1 hat den Replay und die Benchmarks als "nicht durch
gespeicherte Notebook-Ausgaben belegt" gewertet. ``tools/build_nachweise.py``
legt die Ausgaben seither neben die Notebooks, nicht in sie hinein. Dieser
Waechter sorgt dafuer, dass ein Nachweis nicht still veraltet: Aendert sich
der Code eines Notebooks, stimmt sein Abdruck im juengsten Nachweis nicht
mehr, und der Test nennt das Werkzeug, das ihn erneuert.

Gerechnet wird nur mit Dateien im Repository - kein Kernel, keine Daten. Im
frischen Klon und auf jedem Pull Request laeuft er also mit.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from pathlib import Path

import pytest

PROJEKT = Path(__file__).resolve().parents[1]
NACHWEISE = PROJEKT / "docs" / "nachweise"
WERKZEUG = PROJEKT / "tools" / "build_nachweise.py"


def werkzeug():
    spec = importlib.util.spec_from_file_location("build_nachweise", WERKZEUG)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def juengster() -> Path:
    """Nach erstellt_utc, nicht nach Name - am selben Tag entschied sonst der Hash."""
    dateien = werkzeug().nach_erstellung(NACHWEISE)
    assert dateien, "Kein Nachweis abgelegt - python tools/build_nachweise.py"
    return dateien[-1].parent


def test_der_juengste_nachweis_ist_an_sein_release_gebunden():
    """Seit dem 7.11.2026: Silvers Fingerabdruck steht im derived_from des Releases."""
    stand = json.loads((juengster() / "nachweis.json").read_text(encoding="utf-8"))["datenstand"]
    assert stand["release_passt_zum_arbeitsstand"], (
        f"{juengster().name} ist an kein Release gebunden (letztes: {stand['release_aktuell']}). "
        "Erst ein Release bilden (run_all --release), dann den Nachweis erneuern.")


def test_der_juengste_nachweis_umfasst_genau_die_belegenden_notebooks():
    nachweis = json.loads((juengster() / "nachweis.json").read_text(encoding="utf-8"))
    assert tuple(nachweis["notebooks"]) == werkzeug().NOTEBOOKS


@pytest.mark.parametrize("name", werkzeug().NOTEBOOKS)
def test_der_nachweis_passt_zum_code_des_notebooks(name):
    """Markdown darf sich aendern, Code nicht - der bestimmt die Ausgabe."""
    nachweis = json.loads((juengster() / "nachweis.json").read_text(encoding="utf-8"))
    quelle = json.loads((PROJEKT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))
    assert nachweis["notebooks"][name]["code_sha256"] == werkzeug().code_abdruck(quelle), (
        f"Der Code von {name} hat sich seit dem Nachweis {juengster().name} geaendert. "
        "Erneuern: python tools/build_nachweise.py (braucht die gebauten Schichten)."
    )


@pytest.mark.parametrize("name", werkzeug().NOTEBOOKS)
def test_das_html_ist_das_im_nachweis_genannte(name):
    nachweis = json.loads((juengster() / "nachweis.json").read_text(encoding="utf-8"))
    html = (juengster() / f"{name}.html").read_bytes()
    assert hashlib.sha256(html).hexdigest() == nachweis["notebooks"][name]["html_sha256"]


def test_die_nachweise_werden_mit_lf_ausgecheckt():
    """Sonst stimmt auf Windows kein HTML-Hash (Lauf 42364142333)."""
    regeln = (PROJEKT / ".gitattributes").read_text(encoding="utf-8")
    assert "docs/nachweise/** text eol=lf" in regeln


def test_kein_nachweis_traegt_einen_rechnerpfad():
    """Ein Nachweis geht an Dritte: kein Heimverzeichnis, kein Temp-Pfad."""
    muster = re.compile(r"/Users/|/home/[a-z]|/var/folders/|/private/tmp/|[A-Z]:\\\\Users")
    treffer = [p.relative_to(NACHWEISE).as_posix()
               for p in sorted(NACHWEISE.rglob("*")) if p.is_file()
               and muster.search(p.read_text(encoding="utf-8"))]
    assert not treffer, f"Rechnerpfade in: {treffer}"


def test_jeder_nachweis_nennt_commit_datenstand_und_neubau():
    for datei in sorted(NACHWEISE.glob("*/nachweis.json")):
        n = json.loads(datei.read_text(encoding="utf-8"))
        assert re.fullmatch(r"[0-9a-f]{40}", n["commit"]), datei
        assert datei.parent.name.endswith("_" + n["commit"][:7]), datei
        assert n["datenstand"]["aufbau"]["exit"] == 0, datei
        assert n["datenstand"]["silver_crime_offense"]["input_fingerprint"], datei


def test_das_verzeichnis_folgt_aus_den_nachweisen():
    assert (NACHWEISE / "README.md").read_text(encoding="utf-8") == werkzeug().verzeichnis(), (
        "docs/nachweise/README.md ist erzeugt - python tools/build_nachweise.py "
        "schreibt es neu."
    )
