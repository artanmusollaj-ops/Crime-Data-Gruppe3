"""Baut die Silver-Tabelle ``police_area``: ein Polizeibezirk je Zeile.

    python -m silver_pipeline.build_police_area

Gelesen wird je Stadt der juengste fertige Lauf aus
``bronze/dataset=gebiete/ebene=polizeibezirk`` (``gebiete_pipeline``). Was hier
gedeutet wird und in Bronze bewusst nicht:

1. **Ein Bezirk, eine Zeile.** Chicagos District 31 kommt als drei Polygone,
   Detroits Precinct 07 als zwei. Sie werden zu einer Geometrie vereinigt;
   ``source_polygons`` sagt, aus wie vielen.
2. **Ein Schluessel fuer beide Staedte.** Chicago fuehrt ``"1"``, Detroit
   ``"02"``. ``area_id`` ist die Zahl ohne fuehrende Null, als Text - dieselbe
   Form, in die ``crime_offense`` die Angabe der Polizei bringt
   (``police_area_source``). Erst damit lassen sich beide vergleichen.
3. **Ein lesbarer Name**, ``District 1`` und ``Precinct 2``; der Text der
   Quelle steht daneben (``source_name``).
4. **Die Flaeche** auf dem Ellipsoid in Quadratkilometern, damit eine Dichte
   moeglich ist, ohne die Geometrie zu lesen.

Wozu: ``crime_offense`` ordnet jede Tat mit Koordinate ihrem Bezirk zu
(``police_area``), und Gold legt die Einwohner der Tracts auf die Bezirke um.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import duckdb

from manifeste import code_stand, eingabe_abdruck
from silver_pipeline import (
    BRONZE_LAYER,
    PARQUET_FILE,
    SILVER_LAYER,
    STUDIENSTAEDTE,
    TransformError,
    connect,
    newest_complete_run,
    publish,
    schema_of,
)
from storage import StorageError, for_root

TABLE = "police_area"

# Der Deutungsvertrag; jede Erhoehung gehoert in AENDERUNGEN.md,
# "Vertragsversionen". Ein Test prueft das.
CONTRACT_VERSION = 1

GEBIETE_DATASET = "gebiete"
EBENE = "polizeibezirk"

#: Wie ein Bezirk je Stadt heisst - das Wort der Stadt, nicht unseres.
BEZEICHNUNG = {"chicago": "District", "detroit": "Precinct"}

#: Ueberlappen zwei Bezirke derselben Stadt um mehr als diesen Anteil der
#: kleineren Flaeche, bricht der Bau ab: Eine Tat laege dann in zwei Bezirken.
#: Detroits Layer ist grob gezeichnet; seine Raender ueberlappen um Bruchteile
#: eines Promilles.
UEBERLAPPUNG_MAX = 0.005

log = logging.getLogger("silver_police_area")


class Source(NamedTuple):
    city: str
    run_id: str
    parquet: str   # lokal oder s3://, siehe storage.resolve_read_path


def staedte() -> list[str]:
    return sorted(name.lower() for name in STUDIENSTAEDTE.values())


def table_dir(data_root: Path) -> Path:
    return data_root / SILVER_LAYER / f"dataset={TABLE}"


def newest_bronze_run(data_root: Path, stadt: str) -> Source:
    ablage = for_root(data_root)
    prefix = f"{BRONZE_LAYER}/dataset={GEBIETE_DATASET}/ebene={EBENE}/city={stadt}"
    lauf = newest_complete_run(ablage, prefix, what=f"Polizeibezirke {stadt}")
    return Source(stadt, lauf.verzeichnis.name,
                  ablage.resolve_read_path(lauf.relativ, PARQUET_FILE))


def build_query(quellen: list[Source]) -> str:
    teile = " UNION ALL ".join(
        f"SELECT '{q.city}' AS city, gebiet_id, gebiet_name, geometry "
        f"FROM read_parquet('{q.parquet}')" for q in quellen)
    bezeichnung = ", ".join(f"('{s}', '{w}')" for s, w in sorted(BEZEICHNUNG.items()))
    return f"""
    WITH roh AS ({teile}),
    bezeichnung(city, wort) AS (VALUES {bezeichnung}),
    norm AS (
        SELECT city,
               CAST(TRY_CAST(trim(gebiet_id) AS INTEGER) AS VARCHAR) AS area_id,
               trim(gebiet_name) AS source_name,
               ST_GeomFromWKB(geometry) AS geom
        FROM roh
        WHERE TRY_CAST(trim(gebiet_id) AS INTEGER) > 0 AND geometry IS NOT NULL
    ),
    vereint AS (
        SELECT city, area_id, min(source_name) AS source_name,
               count(*) AS source_polygons,
               ST_Union_Agg(geom) AS geom
        FROM norm GROUP BY city, area_id
    )
    SELECT
        v.city                                              AS city,
        v.area_id                                           AS area_id,
        b.wort || ' ' || v.area_id                          AS area_name,
        v.source_name                                       AS source_name,
        CAST(v.source_polygons AS INTEGER)                  AS source_polygons,
        -- ST_Area_Spheroid erwartet Breite vor Laenge; GeoJSON fuehrt
        -- Laenge vor Breite.
        round(ST_Area_Spheroid(ST_FlipCoordinates(v.geom)) / 1e6, 3) AS area_km2,
        ST_Y(ST_Centroid(v.geom))                           AS centroid_lat,
        ST_X(ST_Centroid(v.geom))                           AS centroid_lon,
        ST_AsWKB(v.geom)                                    AS geometry
    FROM vereint v
    JOIN bezeichnung b USING (city)
    ORDER BY city, TRY_CAST(area_id AS INTEGER)
    """


def reconcile(con: duckdb.DuckDBPyConnection, relation: str,
              quellen: list[Source]) -> dict[str, Any]:
    """Jede Stadt da, jede Geometrie gueltig, kein Bezirk doppelt, kaum Ueberlappung."""
    je_stadt = {s: n for s, n in con.execute(
        f"SELECT city, count(*) FROM {relation} GROUP BY 1").fetchall()}
    fehlend = [s for s in staedte() if not je_stadt.get(s)]
    if fehlend:
        raise TransformError(f"keine Polizeibezirke fuer: {fehlend}")
    doppelt = con.execute(f"SELECT count(*) FROM (SELECT city, area_id FROM {relation} "
                          "GROUP BY ALL HAVING count(*) > 1)").fetchone()[0]
    if doppelt:
        raise TransformError(f"{doppelt} Bezirke kommen doppelt vor")
    ungueltig = [r[0] + " " + r[1] for r in con.execute(
        f"SELECT city, area_id FROM {relation} "
        "WHERE NOT ST_IsValid(ST_GeomFromWKB(geometry))").fetchall()]
    if ungueltig:
        raise TransformError(f"ungueltige Geometrie: {ungueltig}")
    verworfen = {q.city: con.execute(
        f"SELECT count(*) FROM read_parquet('{q.parquet}') "
        "WHERE NOT coalesce(TRY_CAST(trim(gebiet_id) AS INTEGER) > 0, false) "
        "OR geometry IS NULL").fetchone()[0] for q in quellen}
    ueberlappung = con.execute(f"""
        WITH g AS (SELECT city, area_id, ST_GeomFromWKB(geometry) AS geom FROM {relation})
        SELECT a.city, a.area_id, b.area_id,
               ST_Area(ST_Intersection(a.geom, b.geom))
                 / least(ST_Area(a.geom), ST_Area(b.geom)) AS anteil
        FROM g a JOIN g b ON a.city = b.city AND a.area_id < b.area_id
                          AND ST_Intersects(a.geom, b.geom)
        ORDER BY anteil DESC LIMIT 1""").fetchone()
    groesste = round(ueberlappung[3], 6) if ueberlappung else 0.0
    if groesste > UEBERLAPPUNG_MAX:
        raise TransformError(
            f"{ueberlappung[0]}: Bezirke {ueberlappung[1]} und {ueberlappung[2]} "
            f"ueberlappen um {groesste:.2%} der kleineren Flaeche")
    return {
        "verified": True,
        "row_count": sum(je_stadt.values()),
        "areas_per_city": dict(sorted(je_stadt.items())),
        "source_rows_without_id_or_geometry": verworfen,
        "largest_overlap_share": groesste,
    }


def build_manifest(con: duckdb.DuckDBPyConnection, relation: str,
                   quellen: list[Source], started: datetime) -> dict[str, Any]:
    nachweis = reconcile(con, relation, quellen)
    herkunft = [{"layer": BRONZE_LAYER, "dataset": GEBIETE_DATASET, "ebene": EBENE,
                 "city": q.city, "run_id": q.run_id} for q in quellen]
    return {
        "status": "complete",
        "contract_version": CONTRACT_VERSION,
        "code_version": code_stand(),
        "layer": SILVER_LAYER,
        "table": TABLE,
        "grain": "ein Polizeibezirk (Chicago District, Detroit Precinct)",
        "built_at_utc": started.isoformat().replace("+00:00", "Z"),
        "tool": f"duckdb {duckdb.__version__} mit spatial",
        "format": "parquet (snappy, Geometrie als WKB in EPSG:4326)",
        "row_count": nachweis["row_count"],
        "join_key": ["city", "area_id"],
        "derived_from": herkunft,
        "input_fingerprint": eingabe_abdruck(herkunft),
        "reconciliation": nachweis,
        "schema": schema_of(con, relation),
        "notes": {
            "area_id": "Zahl ohne fuehrende Null als Text, wie police_area_source "
                       "in crime_offense",
            "extra_column": "_extra wird nicht uebernommen und bleibt in Bronze",
        },
    }


def build(data_root: Path) -> Path:
    started = datetime.now(timezone.utc)
    quellen = [newest_bronze_run(data_root, s) for s in staedte()]
    for q in quellen:
        log.info("Quelle: %s %s", q.city, q.run_id)
    con = connect(spatial=True)
    try:
        con.execute(f"CREATE TEMP TABLE police_area_silver AS {build_query(quellen)}")
        manifest = build_manifest(con, "police_area_silver", quellen, started)
        ziel = publish(con, "police_area_silver", table_dir(data_root), manifest,
                       ordnung="city, area_id")
    finally:
        con.close()
    for_root(data_root).publish_table(ziel)
    return ziel


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    return parser.parse_args()


def main() -> int:
    args = arguments()
    from storage.verwaltet import sperre
    sperre(for_root(args.data_root).local_root, worker_erlaubt=True)
    from storage.analysesitzung import schreibzugriff
    with schreibzugriff(for_root(args.data_root).local_root, invalidieren=True):
        try:
            ablage = for_root(args.data_root)
            ziel = build(ablage.local_root)
            manifest = ablage.tabellen_manifest(ziel)
            log.info("Silver-Tabelle geschrieben: %s", ziel)
            for stadt, n in manifest["reconciliation"]["areas_per_city"].items():
                log.info("  %s: %s Bezirke", stadt, n)
            return 0
        except (TransformError, StorageError, OSError, duckdb.Error) as error:
            log.error("Silver-Aufbau fehlgeschlagen: %s", error)
            return 1
        except KeyboardInterrupt:
            log.error("Abgebrochen; es wurde keine Tabelle veroeffentlicht")
            return 130


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)
    raise SystemExit(main())
