"""Kein Stufenmodul liest seinen Schlussbericht aus dem Dateisystem.

``publish_table`` und ``publish_run`` entfernen im s3-Modus die lokale
Arbeitskopie - im Protokoll steht je Tabelle *„Local working copy removed
(STORAGE_BACKEND=s3)"*. Der Pfad, den ``build`` zurueckgibt, zeigt danach ins
Leere. Vier Module lasen ihn trotzdem, um ihren Schlussbericht zu schreiben,
und **jeder Lauf endete dort mit „Invalid manifest" und Exitcode 1, obwohl
die Tabelle sauber publiziert war**.

Zweimal ist ein Serverlauf genau daran gestorben: am 12.10.2026 bei ``silver
tract_2021`` - damals ohne erkennbare Ursache, die Meldung nannte nur den
Pfad - und am 15.10.2026 wieder, diesmal mit der Erklaerung.

Der Test ist bewusst **statisch**: Er liest den Quelltext, statt die Module
auszufuehren. Ein Lauf im s3-Modus braeuchte SeaweedFS, und genau deshalb
ist der Fehler so lange durchgerutscht - lokal faellt er nie auf.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Die Module, die eine Tabelle publizieren und danach daraus berichten.
#: Gelesen wird der Quelltext, damit ein fuenftes Modul nicht stillschweigend
#: danebenfaellt - es taucht hier auf, sobald es ``publish_table`` ruft.
STUFEN = sorted(
    p for p in (PROJECT_ROOT / "src" / "crime").rglob("build_*.py")
    if "publish_table" in p.read_text(encoding="utf-8")
    or "publish(" in p.read_text(encoding="utf-8")
)


def test_es_gibt_ueberhaupt_stufenmodule():
    """Sonst prueft die Datei nichts und bleibt trotzdem gruen."""
    assert len(STUFEN) >= 4, [p.name for p in STUFEN]


@pytest.mark.parametrize("pfad", STUFEN, ids=lambda p: p.stem)
def test_main_liest_das_manifest_ueber_die_ablage(pfad):
    """In ``main`` darf kein ``read_manifest`` auf einem Pfad stehen.

    Erlaubt ist ``ablage.tabellen_manifest(...)``; die Ablage weiss, wo das
    Manifest nach dem Publizieren liegt. Verboten ist jeder Aufruf von
    ``read_manifest`` **innerhalb von ``main``** - ausserhalb ist er in
    Ordnung, dort geht es um Eingaben, die noch nicht publiziert sind.
    """
    baum = ast.parse(pfad.read_text(encoding="utf-8"), filename=str(pfad))
    haupt = next((k for k in baum.body
                  if isinstance(k, ast.FunctionDef) and k.name == "main"), None)
    if haupt is None:
        pytest.skip(f"{pfad.name} hat kein main()")

    schuldig = [
        k.func.id for k in ast.walk(haupt)
        if isinstance(k, ast.Call) and isinstance(k.func, ast.Name)
        and k.func.id == "read_manifest"
    ]
    assert not schuldig, (
        f"{pfad.name}: main() ruft read_manifest auf einem Pfad - im "
        f"s3-Modus ist die lokale Kopie dann weg, und der Lauf endet mit "
        f"'Invalid manifest' trotz sauberer Publikation. "
        f"Stattdessen: for_root(...).tabellen_manifest(ziel)")
