"""Kein Stufenmodul liest eine Schicht ueber einen offenen Pfad.

**Warum es diesen Waechter gibt.** Am 16. und 17.10.2026 fielen **acht** Faelle
desselben Musters auf, einer nach dem anderen, jeder erst auf ``srv01``:

===  ===============================================  ========================
 1   ``aufraeumen`` Regel 2 (``genannt_in_silver``)    las Silver lokal
 2   ``aufraeumen`` Regel 4 (``bereits_gezogen``)      las die Tabelle lokal
 3   ``storage.parquet``                               gab den Pfad an pyarrow
 4   ``storage.release.sammle``                        globte ``data_root``
 5   ``build_source_change``, das Bestehende           ``alt.is_file()``
 6   dieselbe Datei, Schema und Vertrag                ``manifest.json`` lokal
 7   ``pruefe_gold``                                   baute den Pfad selbst
 8   ``herkunft_von``, die tract-Referenz              ``Path("s3://...")``
===  ===============================================  ========================

Immer derselbe Grund: Im ``local``-Modus ist der Griff **still korrekt**, und
die Suite laeuft im ``local``-Modus. Jeder einzeln behoben, und der naechste
war schon da. Sieben Korrekturen an einem Tag sind kein Zufall mehr, sondern
ein Muster - und ein Muster gehoert gewacht, nicht einzeln gejagt.

**Die Begruendung steht an der Stelle, nicht in einer Liste hier.** Wer einen
Dateisystemgriff auf eine Schicht braucht, schreibt den Grund als Kommentar
darueber und nennt darin ``lokal mit Absicht``. Dieselbe Regel, die
``AGENTS.md`` fuer Quellenangaben setzt: an der Stelle, die sie verwendet,
nicht in einem separaten Verzeichnis. Eine zentrale Liste veraltet, sobald
jemand Code verschiebt; ein Kommentar wandert mit.

**Was der Waechter nicht kann.** Er sieht Dateisystem-*Praedikate*
(``is_file``, ``exists``, ``glob``, ...) auf einem Ausdruck, der nach einer
Schicht aussieht. Er sieht **nicht**, ob eine Zeichenkette, die er fuer einen
Pfad haelt, spaeter an DuckDB geht. Fall 8 faengt er, weil dort ``Path(...)``
und ``.exists()`` stehen; haette dort nur ``read_parquet(f"{pfad}")``
gestanden, waere er blind. Das ist die Grenze, und sie ist genannt, damit
niemand den Waechter fuer mehr haelt, als er ist.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUELLE = PROJECT_ROOT / "src" / "crime"

#: Das Wort, das einen Griff freigibt - zusammen mit einem Grund daneben.
MARKE = "lokal mit Absicht"

#: Dateisystem-Praedikate. ``stat`` und ``open`` fehlen bewusst: Sie kommen
#: fast nur auf Pfaden vor, die schon durch ein Praedikat gegangen sind, und
#: haetten den Waechter verrauscht, ohne einen der acht Faelle zu finden.
PRAEDIKATE = frozenset({"is_file", "is_dir", "exists", "glob", "rglob",
                        "iterdir"})

#: Woran ein Ausdruck nach einer Schicht aussieht. Absichtlich grob: Ein
#: falscher Treffer kostet eine Kommentarzeile, ein verpasster kostet einen
#: Lauf auf ``srv01``.
MARKEN = (
    "raw", "bronze", "silver", "gold", "serving", "releases",
    "SILVER_LAYER", "BRONZE_LAYER", "GOLD_LAYER", "RELEASES",
    "data_root", "datenwurzel", "verzeichnis", "wurzel",
    "table_dir", "tabellenverzeichnis",
)

#: Zwei Pakete sind ausgenommen, und zwar aus einem Grund und nicht aus
#: Bequemlichkeit:
#:
#: ``storage``   ist die Ablage. Es *ist* die Stelle, die das Dateisystem
#:               anfasst; ein Waechter, der ihr das verbietet, verbietet ihr
#:               ihre Aufgabe.
#: ``manifeste`` liest die lokale Haelfte, die ``Storage.laeufe`` ihm gibt -
#:               die ferne Haelfte liest die Ablage und reicht die Manifeste
#:               als Daten herein. Beide Faelle 1 und 6 lagen *nicht* hier,
#:               sondern bei den Aufrufern, die am Paket vorbei lasen.
AUSGENOMMEN = ("storage", "manifeste")


def dateien() -> list[Path]:
    return [p for p in sorted(QUELLE.rglob("*.py"))
            if p.relative_to(QUELLE).parts[0] not in AUSGENOMMEN]


def benannte_pfade(quelle: str, baum: ast.AST) -> set[str]:
    """Namen, die aus einem Schichtausdruck zugewiesen wurden.

    **Der blinde Fleck, den die erste Fassung hatte.** Fall 5 - der teuerste
    des Tages - war geschrieben als

        alt = verzeichnis / PARQUET_FILE
        ... if alt.is_file() else ...

    Der Empfaenger heisst ``alt`` und traegt keine Schichtmarke; ein Waechter,
    der nur den unmittelbaren Ausdruck ansieht, laeuft daran vorbei. Eine
    Mutationsprobe hat genau das gezeigt, bevor dieser Durchgang dazukam.

    Verfolgt wird eine Ebene: Wer einen Schichtpfad einem Namen gibt, macht
    den Namen zu einem Schichtpfad. Mehr Ebenen koennte man rechnen, aber
    jede weitere kauft weniger und kostet Genauigkeit - und wer den Pfad
    zweimal umbenennt, um dem Waechter zu entgehen, laesst sich nicht von
    einem Waechter abhalten.
    """
    gefunden: set[str] = set()
    for knoten in ast.walk(baum):
        if not isinstance(knoten, (ast.Assign, ast.AnnAssign)):
            continue
        wert = ast.get_source_segment(quelle, knoten.value) if knoten.value else ""
        if not wert or not any(m in wert for m in MARKEN):
            continue
        # **Nur Pfade, nicht die Ablage selbst.** ``ablage = for_root(data_root)``
        # traegt die Marke ``data_root``, ist aber ein ``Storage`` - und
        # ``ablage.exists(...)`` ist genau der Aufruf, den dieser Waechter
        # *verlangt*. Die erste Fassung mit Zuweisungsverfolgung hat 28
        # richtige Aufrufe als Fehler gemeldet, darunter sechs in
        # ``build_source_change``, das gerade deswegen umgestellt wurde.
        #
        # Ein Pfad erkennt man daran, dass er **gebaut** wird: mit ``/``, aus
        # ``Path(...)``, ueber ``local_path(...)`` oder ``.parent``. Ein
        # ``for_root(...)`` hat keines davon.
        if not any(z in wert for z in ("/", "Path(", "local_path(", ".parent")):
            continue
        ziele = (knoten.targets if isinstance(knoten, ast.Assign)
                 else [knoten.target])
        for ziel in ziele:
            if isinstance(ziel, ast.Name):
                gefunden.add(ziel.id)
    return gefunden


def griffe(pfad: Path) -> list[tuple[int, str, str]]:
    """(Zeile, Praedikat, Empfaenger) je Dateisystemgriff auf eine Schicht."""
    quelle = pfad.read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    marken = tuple(MARKEN) + tuple(benannte_pfade(quelle, baum))
    gefunden = []
    for knoten in ast.walk(baum):
        if not (isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Attribute)
                and knoten.func.attr in PRAEDIKATE):
            continue
        empfaenger = ast.get_source_segment(quelle, knoten.func.value) or ""
        # Ganze Woerter: ``alt`` darf nicht in ``alterssatz`` treffen.
        woerter = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", empfaenger))
        if any(m in empfaenger for m in MARKEN) or (woerter & set(marken)):
            gefunden.append((knoten.lineno, knoten.func.attr, empfaenger))
    return gefunden


def freigegeben(quelle: str, zeile: int, fenster: int = 8) -> bool:
    """Steht die Marke in den Zeilen darueber - oder in derselben Zeile?

    **Ohne Ruecksicht auf Gross- und Kleinschreibung.** Eine Begruendung
    beginnt einen Satz und faengt darum gross an; ein Waechter, der daran
    scheitert, prueft Rechtschreibung statt Sache. Beim ersten Durchgang hat
    er genau das getan - sechzehn richtig begruendete Stellen blieben rot.
    """
    zeilen = quelle.splitlines()
    anfang = max(0, zeile - 1 - fenster)
    return MARKE.lower() in "\n".join(zeilen[anfang:zeile]).lower()


@pytest.mark.parametrize("pfad", dateien(), ids=lambda p: p.name)
def test_jeder_dateisystemgriff_auf_eine_schicht_ist_begruendet(pfad):
    quelle = pfad.read_text(encoding="utf-8")
    ohne_grund = [
        f"{pfad.relative_to(PROJECT_ROOT)}:{zeile}  .{pred}() auf {empf[:40]!r}"
        for zeile, pred, empf in griffe(pfad)
        if not freigegeben(quelle, zeile)
    ]
    assert not ohne_grund, (
        "Dateisystemgriff auf eine Schicht ohne Begruendung:\n  "
        + "\n  ".join(ohne_grund)
        + f"\n\nIm 's3'-Modus liegt lokal nichts: Die Arbeitskopie wird nach "
          f"dem Publizieren entfernt. Entweder ueber die Ablage lesen "
          f"(for_root(...).exists / .resolve_read_path / .tabellen_manifest) "
          f"- oder, wenn der Griff wirklich lokal gehoert, einen Kommentar "
          f"darueber mit '{MARKE}' und dem Grund."
    )


#: Woran eine **Ablageadresse** zu erkennen ist - eine Zeichenkette, die im
#: ``s3``-Modus ``s3://bucket/...`` lautet und lokal ein Pfad ist.
#: ``resolve_read_path`` ist ihr einziger Erzeuger; die Felder, die sie
#: weitertragen, heissen ``pfad`` oder ``paths``.
ADRESSE = ("resolve_read_path", ".pfad", ".paths", "pfade")


def path_um_adressen(pfad: Path) -> list[tuple[int, str]]:
    """``Path(...)`` um etwas, das eine Ablageadresse sein kann."""
    quelle = pfad.read_text(encoding="utf-8")
    gefunden = []
    for knoten in ast.walk(ast.parse(quelle)):
        if not (isinstance(knoten, ast.Call)
                and isinstance(knoten.func, ast.Name)
                and knoten.func.id == "Path" and knoten.args):
            continue
        arg = ast.get_source_segment(quelle, knoten.args[0]) or ""
        if any(a in arg for a in ADRESSE):
            gefunden.append((knoten.lineno, arg))
    return gefunden


@pytest.mark.parametrize("pfad", dateien(), ids=lambda p: p.name)
def test_keine_ablageadresse_wird_in_Path_gewickelt(pfad):
    """``Path("s3://bucket/x")`` macht aus dem Doppel-Slash ein einfaches.

    **Fall 8 vom 17.10.2026**, und der Waechter oben faengt ihn nicht: Dort
    stand ``Path(tract.pfad).parent`` und darunter ``.exists()``. Der Ausdruck
    nennt keine Schicht, also lief die Schichtregel daran vorbei - der Fehler
    ist auch ein anderer. Er heisst: eine **Adresse** als **Pfad** behandeln.

    Die Folgen waren zwei auf einmal. ``.exists()`` war immer falsch, also
    blieb das Manifest leer und die Herkunftskette von ``crime_offense`` nach
    Bronze unlesbar. Und der Pfad, der ins Manifest kam, war verstuemmelt:
    ``s3:/urban-crime/...`` mit einem Slash - er sieht aus wie eine Adresse
    und ist keine.

    Dass es auffiel, war Glueck: Ich hatte denselben Griff am selben Morgen in
    einem Messskript, dort behoben und nicht gefragt, ob er im Produktivcode
    auch steht.
    """
    quelle = pfad.read_text(encoding="utf-8")
    ohne_grund = [
        f"{pfad.relative_to(PROJECT_ROOT)}:{zeile}  Path({arg[:40]})"
        for zeile, arg in path_um_adressen(pfad)
        if not freigegeben(quelle, zeile)
    ]
    assert not ohne_grund, (
        "Ablageadresse in Path gewickelt:\n  " + "\n  ".join(ohne_grund)
        + f"\n\nIm 's3'-Modus ist das eine Adresse, kein Pfad: Path macht "
          f"aus 's3://' ein 's3:/'. Entweder die Zeichenkette weitergeben - "
          f"oder, wenn der Wert wirklich lokal ist, einen Kommentar darueber "
          f"mit '{MARKE}' und dem Grund."
    )


def test_der_waechter_findet_ueberhaupt_etwas():
    """Sonst waere er gruen, weil er nichts sucht.

    Gezaehlt werden **alle** Griffe, auch die begruendeten: Faellt diese Zahl
    auf null, hat jemand die Erkennung gebrochen und nicht das Problem geloest.
    """
    alle = sum(len(griffe(p)) for p in dateien())
    assert alle >= 10, (
        f"nur {alle} Griffe gefunden - die Erkennung greift nicht mehr")


def test_jede_marke_steht_ueber_einem_griff():
    """Eine Freigabe ohne Griff ist eine, die irgendwann niemand mehr versteht.

    Dasselbe Prinzip wie bei ``SCHUTZ`` in ``test_dokumentzahlen``: Wer
    aufraeumt und den Griff entfernt, soll die Begruendung mitnehmen.
    """
    verwaist = []
    for pfad in dateien():
        quelle = pfad.read_text(encoding="utf-8")
        # **Beide Regeln.** Die erste Fassung zaehlte nur die
        # Schichtpraedikate und hielt die Begruendung in ``build_gold`` fuer
        # verwaist - sie steht ueber einem ``Path(...)``, nicht ueber einem
        # ``.exists()``. Ein Waechter, der seine eigene zweite Regel nicht
        # kennt, meldet richtige Arbeit als Fehler.
        zeilen = ({z for z, _, _ in griffe(pfad)}
                  | {z for z, _ in path_um_adressen(pfad)})
        for i, text in enumerate(quelle.splitlines(), start=1):
            if MARKE.lower() not in text.lower():
                continue
            if not any(i < z <= i + 8 for z in zeilen):
                verwaist.append(f"{pfad.relative_to(PROJECT_ROOT)}:{i}")
    assert not verwaist, (
        f"Freigabe ohne Griff darunter: {verwaist} - die Begruendung ist "
        f"stehengeblieben, der Griff ist weg")
