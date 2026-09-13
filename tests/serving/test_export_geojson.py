"""Tests fuer den GeoJSON-Export der Tract-Umrisse.

Sie laufen ohne Netz und ohne die echten Daten: Silver und Gold werden zur
Laufzeit als kleine Parquet-Dateien erzeugt.

Zwei Eigenschaften sind wichtiger als alles andere und stehen deshalb als
eigene Tests da. Erstens: **in den Eigenschaften steht keine Kennzahl.** Waere
die Einwohnerzahl mit in der Datei, haette die Karte eine zweite Quelle, die
veralten kann, ohne dass man es ihr ansieht. Zweitens: **das Vereinfachen darf
keine Flaeche zerstoeren.** Ein Loch in der Karte faellt niemandem auf - es
sieht aus wie ein Tract ohne Delikte.
"""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

duckdb = pytest.importorskip("duckdb")

# Erst nach importorskip: Das Modul braucht duckdb, und ohne duckdb soll die
# Datei uebersprungen werden statt beim Import zu scheitern.
import export_geojson as eg  # noqa: E402


PARQUET = "part-0001.parquet"


def quadrat(x: float, y: float, seite: float = 0.02, ecken: int = 40) -> bytes:
    """Ein Quadrat mit vielen Stuetzpunkten je Kante, als WKB.

    Die zusaetzlichen Punkte liegen exakt auf der Geraden - Douglas-Peucker
    muss sie also wegwerfen koennen, ohne die Form zu aendern. Genau das macht
    sie zur Messlatte fuer die Vereinfachung.
    """
    punkte: list[tuple[float, float]] = []
    for i in range(ecken):
        punkte.append((x + seite * i / ecken, y))
    for i in range(ecken):
        punkte.append((x + seite, y + seite * i / ecken))
    for i in range(ecken):
        punkte.append((x + seite - seite * i / ecken, y + seite))
    for i in range(ecken):
        punkte.append((x, y + seite - seite * i / ecken))
    punkte.append(punkte[0])
    wkt = "POLYGON((" + ", ".join(f"{a} {b}" for a, b in punkte) + "))"
    con = duckdb.connect()
    try:
        con.execute("INSTALL spatial; LOAD spatial")
        return con.execute(f"SELECT ST_AsWKB(ST_GeomFromText('{wkt}'))").fetchone()[0]
    finally:
        con.close()


def schichten(data_root: Path, staedte: list[str | None]) -> None:
    """Legt silver/tract und gold/dim_tract mit je einer Flaeche je Stadt an."""
    geoids = [f"1700000000{i}" for i in range(len(staedte))]
    geometrien = [quadrat(-87.6 + 0.05 * i, 41.8) for i in range(len(staedte))]

    silber = data_root / "silver" / "dataset=tract" / "vintage=2024"
    silber.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({"geoid": pa.array(geoids), "geometry": pa.array(geometrien, pa.binary())}),
        silber / PARQUET,
    )

    gold = data_root / "gold" / "dataset=dim_tract"
    gold.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.table({
            "geoid": pa.array(geoids),
            "city": pa.array(staedte, pa.string()),
            "tract_name": pa.array([f"Tract {i}" for i in range(len(staedte))]),
            "population": pa.array([1000] * len(staedte), pa.int64()),
        }),
        gold / PARQUET,
    )


def lies(ziel: Path) -> dict:
    return json.loads(ziel.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Form und Inhalt
# --------------------------------------------------------------------------


def test_das_ergebnis_ist_eine_feature_collection(tmp_path):
    schichten(tmp_path / "data", ["chicago", "detroit"])
    inhalt = lies(eg.build(tmp_path / "data"))
    assert inhalt["type"] == "FeatureCollection"
    assert len(inhalt["features"]) == 2
    assert {f["type"] for f in inhalt["features"]} == {"Feature"}


def test_nur_die_studienstaedte(tmp_path):
    """Tracts ohne Stadtzuordnung gehoeren nicht auf die Karte.

    ``dim_tract`` deckt beide Countys ab. Ohne den Filter zeigte die Karte die
    Vorstaedte mit - und der Betrachter haelt sie fuer Teil der Stadt.
    """
    schichten(tmp_path / "data", ["chicago", None, "detroit", None])
    inhalt = lies(eg.build(tmp_path / "data"))
    assert len(inhalt["features"]) == 2
    assert {f["properties"]["city"] for f in inhalt["features"]} == {"chicago", "detroit"}


def test_alle_nimmt_auch_die_ohne_stadt(tmp_path):
    schichten(tmp_path / "data", ["chicago", None, None])
    inhalt = lies(eg.build(tmp_path / "data", alle=True))
    assert len(inhalt["features"]) == 3


def test_die_geoid_ist_eindeutig_und_die_id(tmp_path):
    """Ueber sie verbindet die Karte mit den Zahlen - sie muss tragen."""
    schichten(tmp_path / "data", ["chicago", "detroit", "chicago"])
    inhalt = lies(eg.build(tmp_path / "data"))
    ids = [f["id"] for f in inhalt["features"]]
    assert len(set(ids)) == len(ids)
    assert all(f["id"] == f["properties"]["geoid"] for f in inhalt["features"])


def test_in_den_eigenschaften_steht_keine_kennzahl(tmp_path):
    """Die wichtigste Zusage dieser Datei.

    ``dim_tract`` fuehrt ``population`` und die Fixture schreibt es mit. Landet
    es trotzdem in der Karte, gibt es die Einwohnerzahl an zwei Orten - und die
    Karte zeigt nach einem Gold-Neubau still den alten Nenner.
    """
    schichten(tmp_path / "data", ["chicago"])
    inhalt = lies(eg.build(tmp_path / "data"))
    eigenschaften = set(inhalt["features"][0]["properties"])
    assert eigenschaften == set(eg.EIGENSCHAFTEN)
    assert "population" not in eigenschaften


# --------------------------------------------------------------------------
# Vereinfachung
# --------------------------------------------------------------------------


def test_vereinfachen_verkleinert_und_behaelt_die_form(tmp_path):
    """160 Stuetzpunkte je Quadrat, davon tragen vier die Form."""
    schichten(tmp_path / "data", ["chicago"])
    voll = lies(eg.build(tmp_path / "data", toleranz=0))
    einfach = lies(eg.build(tmp_path / "data"))

    def punkte(inhalt: dict) -> int:
        return sum(len(ring) for f in inhalt["features"]
                   for ring in f["geometry"]["coordinates"])

    assert punkte(einfach) < punkte(voll) / 10
    assert punkte(einfach) == 5  # vier Ecken, der erste Punkt wiederholt


def test_zu_grobe_toleranz_faellt_auf_statt_ein_loch_zu_lassen(tmp_path):
    """Verschwindet eine Flaeche, sieht die Karte aus wie ein Tract ohne Fall."""
    schichten(tmp_path / "data", ["chicago"])
    with pytest.raises(RuntimeError, match="ungueltig oder leer"):
        eg.build(tmp_path / "data", toleranz=5.0)


# --------------------------------------------------------------------------
# Herkunft und Veroeffentlichung
# --------------------------------------------------------------------------


def test_das_manifest_nennt_quelle_und_toleranz(tmp_path):
    schichten(tmp_path / "data", ["chicago", "detroit"])
    ziel = eg.build(tmp_path / "data", toleranz=0.0001)
    manifest = json.loads(
        ziel.with_name(eg.MANIFEST_NAME).read_text(encoding="utf-8")
    )
    assert manifest["features"] == 2
    assert manifest["toleranz_grad"] == 0.0001
    assert manifest["nur_studienstaedte"] is True
    assert manifest["eigenschaften"] == list(eg.EIGENSCHAFTEN)
    assert "dataset=tract" in manifest["derived_from"]["silver_tract"]


def test_ein_gescheiterter_lauf_laesst_nichts_halbes_zurueck(tmp_path):
    schichten(tmp_path / "data", ["chicago"])
    ziel = eg.build(tmp_path / "data")
    vorher = ziel.read_text(encoding="utf-8")

    with pytest.raises(RuntimeError):
        eg.build(tmp_path / "data", toleranz=5.0)

    assert ziel.read_text(encoding="utf-8") == vorher
    assert not list(ziel.parent.glob(".*.part"))


def test_fehlende_quellen_nennen_den_naechsten_schritt(tmp_path):
    with pytest.raises(RuntimeError, match="build_tract"):
        eg.build(tmp_path / "data")

    schichten(tmp_path / "data", ["chicago"])
    (tmp_path / "data" / "gold" / "dataset=dim_tract" / PARQUET).unlink()
    with pytest.raises(RuntimeError, match="build_gold"):
        eg.build(tmp_path / "data")


def test_ohne_stadtzuordnung_wird_der_grund_genannt(tmp_path):
    """Gold ohne Ortsgrenzen gebaut - dann ist city ueberall NULL."""
    schichten(tmp_path / "data", [None, None])
    with pytest.raises(RuntimeError, match="Studienstaedte"):
        eg.build(tmp_path / "data")
