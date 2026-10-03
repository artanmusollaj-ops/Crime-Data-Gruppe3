"""Haelt die Hive-Falle fest, gegen die ``storage.parquet`` gebaut ist.

Dreimal in zwei Wochen hat DuckDBs Hive-Ableitung hier etwas kaputt gemacht:
Spalten, die nur im Pfad stehen, tauchten als echte Spalten auf. Behoben wurde
es jedes Mal an der betroffenen Stelle, mit demselben Kommentar daneben.

Dieser Test prueft deshalb **beide** Seiten. Dass der Helfer die richtigen
Spalten liefert, ist die eine. Dass ``DESCRIBE`` sie weiterhin dazuerfindet,
ist die andere - und die ist die wichtigere: Faellt sie eines Tages, weil
DuckDB sein Verhalten aendert, dann soll das auffallen und nicht unbemerkt
bleiben. Ein Wald von Kommentaren, der vor einer Falle warnt, die es nicht
mehr gibt, ist genauso irrefuehrend wie eine fehlende Warnung.
"""

from __future__ import annotations

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from storage import parquet_schema, parquet_spalten


#: Drei Spalten, und zwei Verzeichnisse im Hive-Muster darueber - genau die
#: Form, in der Gold und die Releases liegen.
SPALTEN = ("a", "b", "c")


@pytest.fixture
def datei(tmp_path):
    """Eine Parquet-Datei unter ``dataset=.../release=.../part-0001.parquet``."""
    ziel = (tmp_path / "dataset=fact_offense"
            / "release=2026-01-01T00-00-00Z" / "part-0001.parquet")
    ziel.parent.mkdir(parents=True)
    pq.write_table(
        pa.table({"a": [1, 2], "b": ["x", "y"], "c": [1.5, 2.5]}), ziel)
    return ziel


def test_der_helfer_nennt_nur_die_spalten_der_datei(datei):
    assert parquet_spalten(datei) == SPALTEN


def test_der_helfer_nimmt_auch_eine_zeichenkette(datei):
    """Aufrufer uebergeben teils ``Path``, teils einen fertigen Pfad."""
    assert parquet_spalten(str(datei)) == SPALTEN


def test_das_schema_traegt_die_typen(datei):
    schema = parquet_schema(datei)
    assert [f.name for f in schema] == list(SPALTEN)
    assert str(schema.field("a").type) == "int64"


def test_describe_erfindet_die_pfadspalten_dazu(datei):
    """Die Falle selbst. Faellt dieser Test, hat DuckDB sich geaendert.

    Dann gehoeren die Warnungen in ``storage.parquet`` und an den
    Aufrufstellen nachgezogen - nicht dieser Test angepasst.
    """
    con = duckdb.connect()
    try:
        beschrieben = tuple(
            z[0] for z in
            con.execute(f"DESCRIBE SELECT * FROM read_parquet('{datei}')")
            .fetchall())
    finally:
        con.close()
    assert beschrieben == SPALTEN + ("dataset", "release")


def test_auch_eine_dateiliste_erfindet_sie_dazu(datei):
    """``read_parquet([...])`` ist nicht der Ausweg - dieselbe Ableitung."""
    con = duckdb.connect()
    try:
        beschrieben = tuple(
            z[0] for z in
            con.execute(f"DESCRIBE SELECT * FROM read_parquet(['{datei}'])")
            .fetchall())
    finally:
        con.close()
    assert beschrieben == SPALTEN + ("dataset", "release")


def test_ausgeschriebene_spalten_bleiben_unberuehrt(datei):
    """Wo die Abfrage die Spalten nennt, ist ``DESCRIBE`` weiter richtig.

    Deshalb bleibt ``silver_pipeline.schema_of`` wie es ist: seine Relationen
    projizieren ausgeschrieben, und die Manifeste sind nachweislich sauber.
    """
    liste = ", ".join(f'"{n}"' for n in SPALTEN)
    con = duckdb.connect()
    try:
        beschrieben = tuple(
            z[0] for z in
            con.execute(f"DESCRIBE SELECT {liste} "
                        f"FROM read_parquet('{datei}')").fetchall())
    finally:
        con.close()
    assert beschrieben == SPALTEN
