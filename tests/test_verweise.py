"""Kein Verweis zeigt ins Leere - ueber Dokumente, README und Notebooks.

Diese Datei entstand am 19.9.2026 als **Voraussetzung**, nicht als Nachtrag.
Die internen Dokumente sollten in einen eigenen Ordner, und die Dokumentnamen
stehen 448-mal in 143 Dateien. Ein Umzug ohne Netz haette Verweise still
zerrissen: Ein toter Link in einer Markdown-Datei sieht aus wie ein
funktionierender, bis jemand darauf klickt - und niemand klickt auf alle.

Geprueft werden **relative** Verweise. Externe URLs bleiben aussen vor; sie
haengen an fremden Servern, und ein Test, der rote Lampen wegen einer fremden
Wartung zeigt, wird bald ignoriert.

``docs/archiv/`` bleibt seit dem 5.10.2026 ebenfalls aussen vor - siehe
``AUSGENOMMEN``.
"""

from __future__ import annotations

import json
from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ein Markdown-Verweis: [Text](ziel). Anker und Suchteile fallen weg.
VERWEIS = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")

# Ordner unter ``docs/``, die dieser Waechter nicht ansieht.
#
# ``referenz`` sind 37 erzeugte pdoc-Seiten mit tausenden Verweisen, die
# ``tests/test_referenz.py`` bereits gegen ihre Startseite haelt.
#
# ``archiv`` kam am 5.10.2026 dazu, mit der vollstaendigen LN1-Fassung des
# Konzepts: Ein archiviertes Dokument ist ein **eingefrorener Stand**, und
# seine Verweise beschreiben die Welt von damals - sie zeigen auf Nachbarn
# eines anderen Ordners und auf Dateinamen, die es inzwischen nicht mehr gibt.
# Sie nachzuziehen hiesse, das Archiv zu aendern, und damit waere es keines
# mehr. ``tests/test_dokumentzahlen.py`` nimmt den Ordner aus demselben Grund
# aus (``AUSGENOMMEN``), und ``tests/test_dokumentwegweiser.py`` haelt
# weiterhin fest, dass jede Datei darin im Wegweiser steht.
#
# Was das kostet: Ein toter Verweis, der beim Archivieren entsteht, faellt
# hier nicht auf. Der Preis ist bewusst - er trifft nur Dokumente, die
# niemand mehr nachfuehrt.
AUSGENOMMEN = ("referenz", "archiv")


def quellen() -> list[tuple[Path, str]]:
    """Jede Datei, die Verweise enthalten kann - mit ihrem Text."""
    gefunden: list[tuple[Path, str]] = []
    for pfad in sorted(PROJECT_ROOT.glob("*.md")):
        gefunden.append((pfad, pfad.read_text(encoding="utf-8")))
    for pfad in sorted(PROJECT_ROOT.glob("docs/**/*.md")):
        if set(pfad.parts) & set(AUSGENOMMEN):
            continue
        gefunden.append((pfad, pfad.read_text(encoding="utf-8")))
    for pfad in sorted(PROJECT_ROOT.glob("notebooks/*.ipynb")):
        notizbuch = json.loads(pfad.read_text(encoding="utf-8"))
        text = "\n".join("".join(zelle["source"]) for zelle in notizbuch["cells"]
                         if zelle["cell_type"] == "markdown")
        gefunden.append((pfad, text))
    return gefunden


def tote_verweise(paare: list[tuple[Path, str]]) -> list[str]:
    tot = []
    for pfad, text in paare:
        for treffer in VERWEIS.finditer(text):
            ziel = treffer.group(1).split("#")[0]
            if not ziel or ziel.startswith(("http://", "https://", "mailto:")):
                continue
            if not (pfad.parent / ziel).resolve().exists():
                tot.append(f"{pfad.relative_to(PROJECT_ROOT)} -> {ziel}")
    return tot


def test_kein_verweis_zeigt_ins_leere():
    tot = tote_verweise(quellen())
    assert not tot, "tote Verweise:\n  " + "\n  ".join(tot)


def test_es_gibt_ueberhaupt_verweise_zu_pruefen():
    """Ein Test, der nichts findet, weil das Muster nicht passt, ist gruen.

    Genau so ein Test haette den Umzug am 19.9.2026 durchgewinkt. Deshalb
    zaehlt diese Zusage mit: Wenn die Sammlung leer laeuft, ist der Waechter
    kaputt, nicht das Repository sauber.
    """
    paare = quellen()
    # Am 19.9.2026: 31 Dateien mit 255 Verweisen. Die Schwellen liegen bewusst
    # deutlich darunter - sie sollen einen kaputten Sammler melden, nicht bei
    # jedem geloeschten Verweis anschlagen.
    assert len(paare) >= 25, f"nur {len(paare)} Dateien gesammelt"
    assert any("notebooks" in p.parts for p, _ in paare), "keine Notebooks gesammelt"
    assert any(p.parent.name == "docs" for p, _ in paare), "keine Dokumente gesammelt"
    verweise = sum(len(VERWEIS.findall(text)) for _, text in paare)
    assert verweise >= 200, f"nur {verweise} Verweise gefunden - passt das Muster noch?"
