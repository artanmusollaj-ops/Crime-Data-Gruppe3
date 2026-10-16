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


# ---------------------------------------------------------------------------
# Lesen auf SeaweedFS
# ---------------------------------------------------------------------------
# Am 16.10.2026 brach der Lauf auf ``srv01`` bei ``silver source_change`` ab:
# "Bucket 'urban-crime' not found". Dieses Modul nahm den Pfad, wie er kam, und
# gab ihn an pyarrow - bei ``s3://...`` loeste pyarrow die Adresse ueber seine
# eigene S3-Erkennung auf, ohne Endpunkt und ohne Schluessel.
#
# Geprueft wird **ohne Netz**, mit einem Stellvertreter: Wichtig ist, dass ein
# Dateisystem aus der Konfiguration gebaut und der Praefix abgeschnitten wird.
# Ein Test, der wirklich auf SeaweedFS liest, liefe in CI nicht - und auf dem
# Entwicklungsrechner gegen die gemeinsame Ablage, was er nicht darf.


def test_ein_lokaler_pfad_geht_ohne_dateisystem_durch(tmp_path):
    datei = tmp_path / "x.parquet"
    pq.write_table(pa.table({"a": [1]}), datei)
    from storage import parquet as sp

    assert sp.spalten(datei) == ("a",)


def test_ein_s3_pfad_wird_ueber_die_konfigurierte_ablage_gelesen(monkeypatch):
    """Endpunkt, Schluessel und Pfadstil kommen aus der Konfiguration.

    Weicht das von ``storage.duckdb.secret_sql`` ab, liest DuckDB etwas
    anderes als dieses Modul - und das waere schlimmer als ein Fehler.
    """
    import pyarrow.fs as pafs

    from storage import parquet as sp

    from storage import Config, Storage, set_storage

    set_storage(Storage(Config(
        backend="s3", s3_endpoint="ablage.example:8333",
        s3_access_key="schluessel", s3_secret_key="geheim")))

    gebaut = {}
    gelesen = {}

    class FalschesDateisystem:
        def __init__(self, **kwargs):
            gebaut.update(kwargs)

    class FalscheDatei:
        def __init__(self, pfad, filesystem=None):
            gelesen["pfad"] = pfad
            gelesen["filesystem"] = filesystem

        @property
        def schema_arrow(self):
            return pa.schema([("a", pa.int64())])

    monkeypatch.setattr(pafs, "S3FileSystem", FalschesDateisystem)
    monkeypatch.setattr(sp.pq, "ParquetFile", FalscheDatei)

    assert sp.spalten("s3://urban-crime/silver/dataset=x/part-0001.parquet") == ("a",)

    assert gelesen["pfad"] == "urban-crime/silver/dataset=x/part-0001.parquet", \
        "der s3://-Praefix muss weg - pyarrow erwartet bucket/key"
    assert gelesen["filesystem"] is not None, \
        "ohne Dateisystem loest pyarrow die Adresse selbst auf, ohne Endpunkt"
    assert gebaut["access_key"] == "schluessel"
    assert gebaut["secret_key"] == "geheim"
    assert "ablage.example:8333" in gebaut["endpoint_override"]
    assert gebaut["force_virtual_addressing"] is False, \
        "SeaweedFS kennt keine Bucket-Subdomains - Pfadstil, wie im DuckDB-Secret"


def test_endpunkt_und_pfadstil_stimmen_mit_dem_duckdb_secret_ueberein(monkeypatch):
    """Zwei Wege in dieselbe Ablage - sie muessen dasselbe sagen.

    Nicht die Zeichenketten werden verglichen, sondern dass beide denselben
    Endpunkt und beide den Pfadstil nennen. Wer einen davon aendert, ohne den
    anderen, faellt hier.
    """
    import pyarrow.fs as pafs

    from storage import parquet as sp
    from storage.duckdb import secret_sql

    from storage import Config, Storage, set_storage

    config = Config(backend="s3", s3_endpoint="ablage.example:8333",
                    s3_access_key="k", s3_secret_key="s")
    set_storage(Storage(config))

    gebaut = {}
    monkeypatch.setattr(pafs, "S3FileSystem",
                        lambda **kw: gebaut.update(kw) or object())
    monkeypatch.setattr(sp.pq, "ParquetFile",
                        lambda pfad, filesystem=None: type(
                            "D", (), {"schema_arrow": pa.schema([])})())
    sp.spalten("s3://urban-crime/x.parquet")

    sql = secret_sql(config)
    assert config.s3_endpoint in gebaut["endpoint_override"]
    assert f"ENDPOINT '{config.s3_endpoint}'" in sql
    assert "URL_STYLE 'path'" in sql
    assert gebaut["force_virtual_addressing"] is False
