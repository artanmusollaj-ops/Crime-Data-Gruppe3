"""Jeder Aufruf von ``silver_pipeline.publish`` nennt eine Zeilenordnung (C-2).

Ohne ``ordnung`` schreibt ``COPY`` die physische Ordnung der Tabelle, und die
haengt am Abfrageplan, an ``threads`` und an ``preserve_insertion_order``. Bis
zum 22.11.2026 galt das fuer sechs der acht Aufrufer. Gemessen an Gold: zwei
Bauten in getrennten Prozessen, gleicher Inhalt, 14'947'218 gegen 15'001'199
Bytes. Wer einen neuen Aufruf ohne ``ordnung`` schreibt, faellt hier durch.
"""

from __future__ import annotations

import ast
from pathlib import Path

import duckdb
import pytest

from silver_pipeline import TransformError, publish


QUELLE = Path(__file__).resolve().parents[1] / "src" / "crime"

#: ``platform_admin.operations`` ruft eine gleichnamige, fremde Funktion auf
#: (Konsolen-Freigabe), nicht ``silver_pipeline.publish``.
FREMD = {"platform_admin/operations.py"}


def _aufrufe() -> list[tuple[str, int, bool]]:
    gefunden = []
    for pfad in sorted(QUELLE.rglob("*.py")):
        name = pfad.relative_to(QUELLE).as_posix()
        if name in FREMD:
            continue
        baum = ast.parse(pfad.read_text(encoding="utf-8"))
        for knoten in ast.walk(baum):
            if (isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Name)
                    and knoten.func.id == "publish"):
                mit = any(k.arg == "ordnung" for k in knoten.keywords)
                gefunden.append((name, knoten.lineno, mit))
    return gefunden


def test_der_waechter_findet_die_aufrufe():
    """Ein Sammler, der nichts findet, prueft nichts."""
    assert len(_aufrufe()) >= 8


def test_jeder_aufruf_nennt_eine_ordnung():
    ohne = [f"{n}:{z}" for n, z, mit in _aufrufe() if not mit]
    assert not ohne, f"publish ohne ordnung: {ohne}"


def test_eine_mehrdeutige_ordnung_bricht_ab(tmp_path):
    """Ein Schluessel, der nicht eindeutig ist, laesst die Folge wieder offen."""
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES (1, 'a'), (1, 'b')) v(k, x)")
    with pytest.raises(TransformError, match="nicht eindeutig"):
        publish(con, "t", tmp_path / "dataset=t", {}, ordnung="k")
    assert not (tmp_path / "dataset=t").exists()


def test_null_im_schluessel_ist_ein_wert(tmp_path):
    """NULL zaehlt wie ein Wert: zwei Zeilen mit (1, NULL) und (2, NULL) sind eindeutig."""
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT * FROM (VALUES (1, NULL), (2, NULL)) v(k, x)")
    ziel = publish(con, "t", tmp_path / "dataset=t", {}, ordnung="k, x")
    assert (ziel / "part-0001.parquet").exists()
