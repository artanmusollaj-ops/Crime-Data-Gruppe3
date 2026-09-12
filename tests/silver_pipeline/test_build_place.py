"""Tests fuer die Silver-Tabelle ``place``.

Die Tabelle hat eine einzige Aufgabe - zu sagen, wo eine Stadt aufhoert - und
genau eine Falle: Illinois fuehrt neben *Chicago city* auch ein *Detroit
village*. Die Tests hier pruefen deshalb vor allem, dass die Auswahl ueber die
GEOID laeuft und dass die Tabelle es merkt, wenn eine Studienstadt fehlt oder
ihre Grenze keine brauchbare Geometrie ist.

Sie laufen ohne Netz und ohne die echten Bronze-Laeufe; die Quelle wird als
kleine Parquet-Datei zur Laufzeit erzeugt.
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import build_place as bp
from silver_pipeline import TransformError, connect


VINTAGE = 2024
STARTED = datetime(2026, 9, 12, 7, 0, 0, tzinfo=timezone.utc)

CHICAGO = "1714000"
DETROIT = "2622000"
# Der Stolperstein: derselbe Name, anderer Ort, anderer Bundesstaat.
DETROIT_VILLAGE = "1719681"


def wkb_square(x: float, y: float, size: float = 1.0) -> bytes:
    """Ein Quadrat als WKB-Polygon, little endian."""
    punkte = [(x, y), (x + size, y), (x + size, y + size), (x, y + size), (x, y)]
    return (
        struct.pack("<BII", 1, 3, 1)
        + struct.pack("<I", len(punkte))
        + b"".join(struct.pack("<dd", a, b) for a, b in punkte)
    )


def kaputtes_polygon() -> bytes:
    """Eine Acht - selbstueberschneidend und damit nicht ST_IsValid."""
    punkte = [(0, 0), (2, 2), (2, 0), (0, 2), (0, 0)]
    return (
        struct.pack("<BII", 1, 3, 1)
        + struct.pack("<I", len(punkte))
        + b"".join(struct.pack("<dd", a, b) for a, b in punkte)
    )


def place_table(eintraege) -> pa.Table:
    """Eine PLACE-Quelltabelle, wie Bronze sie schreibt."""
    geoids = [e[0] for e in eintraege]
    namen = [e[1] for e in eintraege]
    lsad = [e[2] for e in eintraege]
    geometrien = [e[3] for e in eintraege]
    n = len(eintraege)
    return pa.table({
        "STATEFP": pa.array([g[:2] for g in geoids]),
        "PLACEFP": pa.array([g[2:] for g in geoids]),
        "PLACENS": pa.array([f"0{i:06d}" for i in range(n)]),
        "GEOID": pa.array(geoids),
        "NAME": pa.array(namen),
        "NAMELSAD": pa.array([
            f"{name} {bp.LSAD_KLARTEXT.get(code, 'unbekannt')}"
            for name, code in zip(namen, lsad)
        ]),
        "LSAD": pa.array(lsad),
        "CLASSFP": pa.array(["C5"] * n),
        "MTFCC": pa.array(["G4110"] * n),
        "FUNCSTAT": pa.array(["A"] * n),
        "ALAND": pa.array([589_864_496] * n, type=pa.int64()),
        "AWATER": pa.array([17_575_510] * n, type=pa.int64()),
        "INTPTLAT": pa.array([f"+41.{8 + i}" for i in range(n)]),
        "INTPTLON": pa.array([f"-087.{6 + i}" for i in range(n)]),
        "geometry": pa.array(geometrien, pa.binary()),
        "_extra": pa.array([None] * n, type=pa.string()),
    })


VOLLSTAENDIG = [
    (CHICAGO, "Chicago", "25", wkb_square(0.0, 0.0, 4.0)),
    (DETROIT_VILLAGE, "Detroit", "47", wkb_square(20.0, 20.0, 0.1)),
    (DETROIT, "Detroit", "25", wkb_square(10.0, 10.0, 3.0)),
]


@pytest.fixture
def quelle(tmp_path: Path) -> Path:
    """Ein Bronze-Parquet, das der Builder lesen kann."""
    pfad = tmp_path / "place.parquet"
    pq.write_table(place_table(VOLLSTAENDIG), pfad)
    return pfad


def relation(con, pfad: Path, eintraege=None) -> str:
    """Legt die Silver-Sicht an und gibt ihren Namen zurueck."""
    if eintraege is not None:
        pq.write_table(place_table(eintraege), pfad)
    quellen = [bp.Source(bp.PLACE_DATASET, "17", "run_x", pfad)]
    con.execute(f"CREATE OR REPLACE TEMP VIEW place_silver AS {bp.build_query(quellen)}")
    return "place_silver"


@pytest.fixture
def con():
    verbindung = connect(spatial=True)
    yield verbindung
    verbindung.close()


# --------------------------------------------------------------------------
# Form und Deutung
# --------------------------------------------------------------------------


def test_spalten_wie_vereinbart(con, quelle):
    namen = [
        zeile[0]
        for zeile in con.execute(
            f"DESCRIBE SELECT * FROM {relation(con, quelle)}"
        ).fetchall()
    ]
    assert namen == [
        "geoid", "state_fips", "state_name", "place_fips", "name", "name_long",
        "lsad_code", "lsad_text", "class_code", "land_area_m2", "water_area_m2",
        "centroid_lat", "centroid_lon", "geometry", "quality_flags",
    ]


def test_koordinaten_werden_zu_zahlen(con, quelle):
    """'+41.8' und '-087.6' sind in der Quelle Text."""
    lat, lon = con.execute(
        f"SELECT centroid_lat, centroid_lon FROM {relation(con, quelle)} "
        f"WHERE geoid = '{CHICAGO}'"
    ).fetchone()
    assert lat == pytest.approx(41.8)
    assert lon == pytest.approx(-87.6)


def test_lsad_bekommt_einen_klartext(con, quelle):
    zeilen = dict(
        con.execute(
            f"SELECT geoid, lsad_text FROM {relation(con, quelle)}"
        ).fetchall()
    )
    assert zeilen[CHICAGO] == "city"
    assert zeilen[DETROIT_VILLAGE] == "village"


def test_unbekannter_lsad_wird_benannt_nicht_verworfen(con, quelle):
    eintraege = [(CHICAGO, "Chicago", "99", wkb_square(0.0, 0.0, 4.0)),
                 (DETROIT, "Detroit", "25", wkb_square(10.0, 10.0, 3.0))]
    zeile = con.execute(
        f"SELECT lsad_code, lsad_text, quality_flags "
        f"FROM {relation(con, quelle, eintraege)} WHERE geoid = '{CHICAGO}'"
    ).fetchone()
    assert zeile[0] == "99", "der Code der Quelle bleibt stehen"
    assert zeile[1] is None
    assert "UNKNOWN_LSAD" in zeile[2]


# --------------------------------------------------------------------------
# Der Nachweis - hier liegt der Wert dieser Tabelle
# --------------------------------------------------------------------------


def test_beide_studienstaedte_werden_gefunden(con, quelle):
    nachweis = bp.reconcile(con, relation(con, quelle))
    assert nachweis["study_cities"] == {
        CHICAGO: "Chicago city",
        DETROIT: "Detroit city",
    }


def test_fehlende_studienstadt_laesst_den_bau_scheitern(con, quelle):
    """Eine Tabelle ohne Chicago waere formal gueltig und fachlich wertlos."""
    ohne_chicago = [e for e in VOLLSTAENDIG if e[0] != CHICAGO]
    with pytest.raises(TransformError, match="Studienstadt fehlt"):
        bp.reconcile(con, relation(con, quelle, ohne_chicago))


def test_geoid_auf_dem_falschen_ort_faellt_auf(con, quelle):
    """Wenn der Census die Nummer neu vergibt, darf das nicht durchrutschen."""
    vertauscht = [
        (CHICAGO, "Schaumburg", "25", wkb_square(0.0, 0.0, 4.0)),
        (DETROIT, "Detroit", "25", wkb_square(10.0, 10.0, 3.0)),
    ]
    with pytest.raises(TransformError, match="anderen Ort"):
        bp.reconcile(con, relation(con, quelle, vertauscht))


def test_kaputte_stadtgrenze_faellt_auf(con, quelle):
    """Eine ungueltige Geometrie laesst den raeumlichen Join leer laufen, nicht scheitern."""
    kaputt = [
        (CHICAGO, "Chicago", "25", kaputtes_polygon()),
        (DETROIT, "Detroit", "25", wkb_square(10.0, 10.0, 3.0)),
    ]
    with pytest.raises(TransformError, match="gueltige Geometrie"):
        bp.reconcile(con, relation(con, quelle, kaputt))


def test_doppelte_geoid_faellt_auf(con, quelle):
    doppelt = VOLLSTAENDIG + [(CHICAGO, "Chicago", "25", wkb_square(0.0, 0.0, 4.0))]
    with pytest.raises(TransformError, match="mehrfach"):
        bp.reconcile(con, relation(con, quelle, doppelt))


def test_gleichnamige_orte_werden_gezaehlt(con, quelle):
    """Der Grund, warum ueber die GEOID ausgewaehlt wird, steht im Manifest.

    Zwei Orte heissen Detroit. Ein Join ueber den Namen haette in Gold ein
    Dorf von 0,65 Quadratkilometern als Stadtgrenze genommen - ohne Fehler,
    nur mit einem falschen Nenner.
    """
    nachweis = bp.reconcile(con, relation(con, quelle))
    assert nachweis["places_sharing_a_study_city_name"]["Detroit"] == 2
    assert nachweis["places_sharing_a_study_city_name"]["Chicago"] == 1


def test_kein_filter_auf_die_studienstaedte(con, quelle):
    """Alle Orte bleiben stehen; die Auswahl trifft Gold."""
    anzahl = con.execute(
        f"SELECT count(*) FROM {relation(con, quelle)}"
    ).fetchone()[0]
    assert anzahl == len(VOLLSTAENDIG)


# --------------------------------------------------------------------------
# Gegen die echte Auslieferung, wenn sie vorliegt
# --------------------------------------------------------------------------


def echte_tabelle() -> Path | None:
    pfad = (
        Path(__file__).resolve().parents[2]
        / "data" / "silver" / f"dataset={bp.TABLE}" / f"vintage={VINTAGE}"
        / "part-0001.parquet"
    )
    return pfad if pfad.exists() else None


def test_die_echte_tabelle_kennt_beide_staedte(con):
    pfad = echte_tabelle()
    if pfad is None:
        pytest.skip("keine gebaute silver/place-Tabelle vorhanden")
    zeilen = dict(
        con.execute(
            f"SELECT geoid, name_long FROM read_parquet('{pfad}') "
            f"WHERE geoid IN ('{CHICAGO}', '{DETROIT}')"
        ).fetchall()
    )
    assert zeilen == {CHICAGO: "Chicago city", DETROIT: "Detroit city"}


def test_die_falle_gibt_es_wirklich(con):
    """Das Detroit village ist keine erfundene Sorge."""
    pfad = echte_tabelle()
    if pfad is None:
        pytest.skip("keine gebaute silver/place-Tabelle vorhanden")
    orte = con.execute(
        f"SELECT geoid, name_long, state_name FROM read_parquet('{pfad}') "
        "WHERE name = 'Detroit' ORDER BY geoid"
    ).fetchall()
    assert len(orte) == 2, f"erwartet zwei Orte namens Detroit, gefunden: {orte}"
    assert ("1719681", "Detroit village", "illinois") in orte
