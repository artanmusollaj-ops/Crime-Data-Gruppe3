"""Baut die Silver-Tabelle ``place`` aus den TIGER-Ortsgrenzen.

Eine Zeile je Ort der beiden Bundesstaaten, mit Geometrie. Die Tabelle
beantwortet eine einzige Frage, die keine andere Quelle beantwortet: **Wo hoert
die Stadt auf?**

Ohne sie gibt es keinen Nenner. ``silver/tract`` deckt ganze Countys ab, und ein
County ist viel groesser als die Stadt darin - Cook County hat 5,18 Millionen
Einwohner, Chicago rund 2,7 Millionen. Wer eine Rate je Einwohner rechnen will,
braucht die Stadtgrenze; bis dahin war sie im Projekt eine Naeherung ueber
"Tracts, in denen Delikte liegen".

Aufruf aus dem Projekt-Root:

    python -m silver_pipeline.build_place

**Gefiltert wird hier nicht.** Die Tabelle fuehrt alle Orte beider
Bundesstaaten, nicht nur Chicago und Detroit. Das kostet wenig und macht eine
Falle sichtbar, die ein Filter verstecken wuerde: Illinois fuehrt neben
*Chicago city* auch ein *Detroit village*. Wer ueber den Namen joint, holt sich
einen Ort von 0,65 Quadratkilometern ins Ergebnis. Die Auswahl der beiden
Staedte trifft deshalb Gold, und zwar ueber die GEOID.

Was hier gedeutet wird und in Bronze bewusst nicht:

1. **Typen.** ``INTPTLAT`` kommt als ``'+41.8'``, ``INTPTLON`` als
   ``'-087.6'``; beide werden zu Zahlen.
2. **Art der Gebietseinheit.** ``LSAD`` und ``CLASSFP`` sind Codes. Sie bleiben
   erhalten, bekommen aber eine lesbare Entsprechung - ohne sie laesst sich
   nicht begruenden, warum *Chicago city* und nicht *Detroit village* gemeint
   ist.
3. **Qualitaetsmerkmale.** Orte ohne Landflaeche und ungueltige Geometrien
   werden benannt, nicht entfernt.

Nicht uebernommen wird ``_extra``; die Auffangspalte bleibt in Bronze.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import duckdb

from census_pipeline import STATES
from silver_pipeline import (
    BRONZE_LAYER,
    PARQUET_FILE,
    SILVER_LAYER,
    TransformError,
    connect,
    newest_complete_run,
    publish,
    read_manifest,
    schema_of,
)


TABLE = "place"
PLACE_DATASET = "tiger_place"
DEFAULT_VINTAGE = 2024

# Die beiden Staedte des Projekts, ueber ihre FIPS-Ortsnummer. Sie steht hier
# und nicht in Gold, weil ``reconcile`` nachweisen muss, dass beide ueberhaupt
# in der Auslieferung stecken - eine Tabelle ohne Chicago waere formal gueltig
# und fachlich wertlos.
STUDIENSTAEDTE = {
    "1714000": "Chicago",
    "2622000": "Detroit",
}

# LSAD sagt, welches Wort im Namen hinter dem Ortsnamen steht. Nur diese beiden
# Codes kommen bei unseren Staedten vor; alles andere bleibt als Code stehen.
# 25 = city, 47 = village.
LSAD_KLARTEXT = {"25": "city", "43": "town", "47": "village"}

log = logging.getLogger("silver_place")


class Source(NamedTuple):
    """Ein Bronze-Lauf, aus dem diese Tabelle entstanden ist."""

    dataset: str
    state: str
    run_id: str
    parquet: Path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vintage", type=int, default=DEFAULT_VINTAGE)
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument(
        "--state",
        action="append",
        choices=sorted(STATES),
        help="FIPS-Nummer; mehrfach moeglich. Ohne Angabe alle bekannten.",
    )
    args = parser.parse_args()
    args.state = args.state or sorted(STATES)
    return args


def table_dir(data_root: Path, vintage: int) -> Path:
    """Partitioniert nach Vintage, wie ``tract`` - die Quelle ist eingefroren."""
    return data_root / SILVER_LAYER / f"dataset={TABLE}" / f"vintage={vintage}"


def newest_bronze_run(data_root: Path, vintage: int, state: str) -> Source:
    parent = (
        data_root
        / BRONZE_LAYER
        / f"dataset={PLACE_DATASET}"
        / f"vintage={vintage}"
        / f"state={state}"
    )
    lauf = newest_complete_run(
        parent, what=f"{PLACE_DATASET}, Vintage {vintage}, Staat {state}"
    )
    return Source(PLACE_DATASET, state, lauf.name, lauf / PARQUET_FILE)


def build_query(quellen: list[Source]) -> str:
    """Eine Quelle, keine Verbindung - die Deutung liegt in den Spalten."""
    dateien = ", ".join(f"'{q.parquet}'" for q in quellen)
    staaten = ", ".join(
        f"('{fips}', '{name}')" for fips, name in sorted(STATES.items())
    )
    lsad = ", ".join(f"('{code}', '{wort}')" for code, wort in sorted(LSAD_KLARTEXT.items()))

    return f"""
    WITH place AS (
        SELECT * FROM read_parquet([{dateien}])
    ),
    states(state_fips, state_name) AS (VALUES {staaten}),
    lsad(lsad_code, lsad_text) AS (VALUES {lsad})
    SELECT
        p.GEOID                                     AS geoid,
        p.STATEFP                                   AS state_fips,
        s.state_name                                AS state_name,
        p.PLACEFP                                   AS place_fips,
        p.NAME                                      AS name,
        p.NAMELSAD                                  AS name_long,
        p.LSAD                                      AS lsad_code,
        l.lsad_text                                 AS lsad_text,
        p.CLASSFP                                   AS class_code,
        p.ALAND                                     AS land_area_m2,
        p.AWATER                                    AS water_area_m2,
        -- '+41.8' und '-087.6': TRY_CAST kommt mit fuehrendem Plus und
        -- fuehrenden Nullen zurecht, genau wie bei den Tracts.
        TRY_CAST(p.INTPTLAT AS DOUBLE)              AS centroid_lat,
        TRY_CAST(p.INTPTLON AS DOUBLE)              AS centroid_lon,
        p.geometry                                  AS geometry,
        list_filter([
            CASE WHEN p.geometry IS NULL THEN 'MISSING_GEOMETRY' END,
            CASE WHEN p.ALAND = 0 THEN 'ZERO_LAND_AREA' END,
            CASE WHEN l.lsad_text IS NULL THEN 'UNKNOWN_LSAD' END
        ], x -> x IS NOT NULL)                      AS quality_flags
    FROM place p
    LEFT JOIN states s ON s.state_fips = p.STATEFP
    LEFT JOIN lsad l ON l.lsad_code = p.LSAD
    ORDER BY geoid
    """


def reconcile(con: duckdb.DuckDBPyConnection, relation: str) -> dict[str, Any]:
    """Weist nach, dass die Tabelle taugt, wozu sie gebaut wurde.

    Zwei Nachweise, die ueber das Uebliche hinausgehen. Erstens: Beide
    Studienstaedte sind da. Zweitens: Ihre Geometrie ist gueltig - eine
    kaputte Stadtgrenze wuerde den raeumlichen Join in Gold stillschweigend
    leer laufen lassen, nicht scheitern.
    """
    zeilen = con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    doppelte = con.execute(
        f"SELECT count(*) FROM (SELECT geoid FROM {relation} "
        "GROUP BY geoid HAVING count(*) > 1)"
    ).fetchone()[0]
    ohne_geometrie = con.execute(
        f"SELECT count(*) FROM {relation} WHERE geometry IS NULL"
    ).fetchone()[0]
    ungueltig = con.execute(
        f"SELECT count(*) FROM {relation} "
        "WHERE geometry IS NOT NULL AND NOT ST_IsValid(ST_GeomFromWKB(geometry))"
    ).fetchone()[0]

    if doppelte:
        raise TransformError(f"{doppelte} GEOID kommen mehrfach vor")

    codes = ", ".join(f"'{c}'" for c in sorted(STUDIENSTAEDTE))
    gefunden = {
        zeile[0]: {"name": zeile[1], "name_long": zeile[2], "gueltig": zeile[3]}
        for zeile in con.execute(
            f"SELECT geoid, name, name_long, "
            f"ST_IsValid(ST_GeomFromWKB(geometry)) FROM {relation} "
            f"WHERE geoid IN ({codes})"
        ).fetchall()
    }
    fehlend = sorted(set(STUDIENSTAEDTE) - set(gefunden))
    if fehlend:
        raise TransformError(
            "Studienstadt fehlt in der Auslieferung: "
            + ", ".join(f"{c} ({STUDIENSTAEDTE[c]})" for c in fehlend)
        )
    falsch = {
        code: gefunden[code]["name"]
        for code in STUDIENSTAEDTE
        if gefunden[code]["name"] != STUDIENSTAEDTE[code]
    }
    if falsch:
        raise TransformError(f"GEOID zeigt auf einen anderen Ort: {falsch}")
    kaputt = [c for c in STUDIENSTAEDTE if not gefunden[c]["gueltig"]]
    if kaputt:
        raise TransformError(f"Stadtgrenze ist keine gueltige Geometrie: {kaputt}")

    # Wie viele Orte den Namen einer Studienstadt tragen. Ist die Zahl groesser
    # als eins, waere ein Join ueber den Namen mehrdeutig - genau deshalb
    # laeuft er ueber die GEOID.
    namen = ", ".join(f"'{n}'" for n in sorted(set(STUDIENSTAEDTE.values())))
    gleichnamig = {
        zeile[0]: zeile[1]
        for zeile in con.execute(
            f"SELECT name, count(*) FROM {relation} "
            f"WHERE name IN ({namen}) GROUP BY name ORDER BY name"
        ).fetchall()
    }

    return {
        "verified": True,
        "row_count": zeilen,
        "geoid_unique": True,
        "places_without_geometry": ohne_geometrie,
        "invalid_geometries": ungueltig,
        "study_cities": {
            code: gefunden[code]["name_long"] for code in sorted(STUDIENSTAEDTE)
        },
        "places_sharing_a_study_city_name": gleichnamig,
    }


def column_statistics(
    con: duckdb.DuckDBPyConnection, relation: str
) -> dict[str, Any]:
    row = con.execute(
        f"""
        SELECT count(*), count(centroid_lat), count(lsad_text),
               sum(CASE WHEN land_area_m2 = 0 THEN 1 ELSE 0 END)
        FROM {relation}
        """
    ).fetchone()
    return {
        "centroid_filled": row[1],
        "lsad_resolved": row[2],
        "zero_land_area_places": row[3],
        "lsad_unresolved": row[0] - row[2],
    }


def build_manifest(
    con: duckdb.DuckDBPyConnection,
    relation: str,
    vintage: int,
    sources: list[Source],
    started: datetime,
) -> dict[str, Any]:
    nachweis = reconcile(con, relation)
    return {
        "status": "complete",
        "layer": SILVER_LAYER,
        "table": TABLE,
        "grain": "ein Ort (Census Place)",
        "vintage": vintage,
        "built_at_utc": started.isoformat().replace("+00:00", "Z"),
        "tool": f"duckdb {duckdb.__version__} mit spatial",
        "format": "parquet (snappy, Geometrie als WKB in EPSG:4269)",
        "row_count": nachweis["row_count"],
        "join_key": "geoid",
        "derived_from": [
            {
                "layer": BRONZE_LAYER,
                "dataset": q.dataset,
                "state_fips": q.state,
                "run_id": q.run_id,
            }
            for q in sources
        ],
        "reconciliation": nachweis,
        "column_statistics": column_statistics(con, relation),
        "schema": schema_of(con, relation),
        "notes": {
            "kein_filter": (
                "Die Tabelle fuehrt alle Orte beider Bundesstaaten. Die "
                "Auswahl der Studienstaedte trifft Gold ueber die GEOID - "
                "ueber den Namen waere sie mehrdeutig, siehe "
                "places_sharing_a_study_city_name"
            ),
            "wozu": (
                "Stadtgrenze als Nenner: ein Tract weiss nicht, zu welcher "
                "Stadt er gehoert, und ein County ist groesser als die Stadt"
            ),
            "extra_column": "_extra wird nicht uebernommen und bleibt in Bronze",
        },
    }


def build(data_root: Path, vintage: int, states: list[str]) -> Path:
    started = datetime.now(timezone.utc)
    quellen = [newest_bronze_run(data_root, vintage, state) for state in states]
    for q in quellen:
        log.info("Quelle: %s %s %s", q.dataset, q.state, q.run_id)

    con = connect(spatial=True)
    try:
        con.execute(f"CREATE TEMP VIEW place_silver AS {build_query(quellen)}")
        manifest = build_manifest(con, "place_silver", vintage, quellen, started)
        ziel = publish(con, "place_silver", table_dir(data_root, vintage), manifest)
    finally:
        con.close()
    return ziel


def main() -> int:
    args = arguments()
    try:
        ziel = build(args.data_root, args.vintage, args.state)
        manifest = read_manifest(ziel)
        log.info("Silver-Tabelle geschrieben: %s", ziel)
        log.info("  Zeilen: %s", f"{manifest['row_count']:,}")
        nachweis = manifest["reconciliation"]
        for code, name in sorted(nachweis["study_cities"].items()):
            log.info("  Studienstadt %s: %s", code, name)
        for name, anzahl in sorted(
            nachweis["places_sharing_a_study_city_name"].items()
        ):
            if anzahl > 1:
                log.info(
                    "  Achtung: %s Orte heissen '%s' - deshalb wird ueber die "
                    "GEOID ausgewaehlt",
                    anzahl,
                    name,
                )
        return 0
    except (TransformError, OSError, duckdb.Error) as error:
        log.error("Silver-Aufbau fehlgeschlagen: %s", error)
        return 1
    except KeyboardInterrupt:
        log.error("Abgebrochen; es wurde keine Tabelle veroeffentlicht")
        return 130


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )
    raise SystemExit(main())
