"""Baut die Silver-Tabelle ``tract`` aus TIGER-Geometrie und ACS-Attributen.

Eine Zeile je Census Tract, mit Geometrie und den sozio-oekonomischen
Kennzahlen desselben Tracts. Diese Tabelle ist die Dimension, an der die
Falldaten spaeter haengen, und sie ist der einzige Silver-Baustein, der von
keiner offenen Entscheidung abhaengt: Beide Quellen liegen als eingefrorene
Vintage, teilen den Schluessel ``GEOID`` und brauchen keine Zeitachse.

Aufruf aus dem Projekt-Root:

    python -m silver_pipeline.build_tract

Was hier gedeutet wird und in Bronze bewusst nicht:

1. **Typen.** Der ACS liefert alle Werte als Text. Hier werden sie zu Zahlen.
2. **Fehlwerte.** ``-666666666`` heisst "keine Schaetzung moeglich" und wird
   zu ``NULL``. In Bronze bleibt der Code stehen, damit die Quelle
   nachvollziehbar bleibt.
3. **Abgeleitete Groessen.** Die Armutsquote ergibt sich aus zwei Spalten und
   ist bei Tracts ohne Einwohner nicht definiert - dort ``NULL`` statt einer
   Division durch null.
4. **Qualitaetsmerkmale.** Fehlendes Einkommen und Tracts ohne Einwohner
   werden benannt, nicht entfernt. Wer sie herausfiltern will, tut das in der
   Auswertung und sieht dabei, wie viele es sind.

Nicht uebernommen wird ``_extra``. Die Auffangspalte bleibt in Bronze; eine
dortige Groesse hierher zu heben kostet eine Aenderung an diesem Modul und
keinen neuen Ladelauf.
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
from manifeste import code_stand, eingabe_abdruck
from storage import StorageError, for_root
from silver_pipeline import (
    ACS_MISSING_VALUE,
    BRONZE_LAYER,
    PARQUET_FILE,
    SILVER_LAYER,
    TransformError,
    connect,
    newest_complete_run,
    publish,
    schema_of,
)


TABLE = "tract"

# Die Typen sind so schmal wie die Sache: ein Haushaltseinkommen und eine
# Personenzahl je Tract passen in INTEGER (Maximum 2,1 Mrd; gemessen 250'001
# beziehungsweise 5'819). BIGINT waere das Achtfache an Platz fuer nichts.
# Die Einwohnerzahl bleibt bewusst BIGINT - sie ist der Nenner jeder Rate,
# und dort ist Vorsicht mehr wert als vier Byte.

# Der Deutungsvertrag: Was diese Tabelle bedeutet - Granularität, Regeln, Spalten -
# nicht, wie der Code sie baut. Steigt die Zahl, sind aeltere Staende anders
# zu lesen. Jede Erhoehung gehoert in AENDERUNGEN.md, siehe
# "Vertragsversionen"; ein Test prueft das.
CONTRACT_VERSION = 2

TIGER_DATASET = "tiger_tract"
ACS_DATASET = "acs5_tract"
DEFAULT_VINTAGE = 2024

log = logging.getLogger("silver_tract")


class Source(NamedTuple):
    """Ein Bronze-Lauf, der in diese Tabelle eingeht."""

    dataset: str
    state: str
    run_id: str
    parquet: str   # lokal oder s3://, siehe storage.resolve_read_path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    parser.add_argument("--vintage", type=int, default=DEFAULT_VINTAGE)
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
    """Wohin die Tabelle geschrieben wird.

    Partitioniert nach Vintage, weil die beiden Quellen eingefroren sind und
    eine neue Vintage eine andere Tabelle ist - nicht eine neuere Version
    derselben.
    """
    return data_root / SILVER_LAYER / f"dataset={TABLE}" / f"vintage={vintage}"


def newest_bronze_run(
    data_root: Path, dataset: str, vintage: int, state: str
) -> Source:
    """Der juengste vollstaendige Bronze-Lauf dieser Quelle."""
    ablage = for_root(data_root)
    prefix = f"{BRONZE_LAYER}/dataset={dataset}/vintage={vintage}/state={state}"
    lauf = newest_complete_run(
        ablage, prefix, what=f"{dataset}, Vintage {vintage}, Staat {state}"
    )
    return Source(dataset, state, lauf.verzeichnis.name,
                  ablage.resolve_read_path(lauf.relativ, PARQUET_FILE))


def build_query(tiger: list[Source], acs: list[Source]) -> str:
    """Die Abfrage, die aus zwei Bronze-Quellen eine Silver-Zeile macht.

    Der Join ist ein voller aeusserer Join und ausdruecklich kein innerer: Ein
    Tract, der nur in einer der beiden Quellen steht, soll auffallen und nicht
    stillschweigend verschwinden. Ob es solche gibt, prueft ``reconcile``.
    """
    tiger_dateien = ", ".join(f"'{quelle.parquet}'" for quelle in tiger)
    acs_dateien = ", ".join(f"'{quelle.parquet}'" for quelle in acs)
    staaten = ", ".join(
        f"('{fips}', '{name}')" for fips, name in sorted(STATES.items())
    )

    return f"""
    WITH tiger AS (
        SELECT * FROM read_parquet([{tiger_dateien}])
    ),
    acs AS (
        SELECT * FROM read_parquet([{acs_dateien}])
    ),
    states(state_fips, state_name) AS (
        VALUES {staaten}
    )
    SELECT
        coalesce(t.GEOID, a.GEOID)                        AS geoid,
        t.STATEFP                                         AS state_fips,
        s.state_name                                      AS state_name,
        t.COUNTYFP                                        AS county_fips,
        t.TRACTCE                                         AS tract_code,
        t.NAMELSAD                                        AS name,
        t.ALAND                                           AS land_area_m2,
        t.AWATER                                          AS water_area_m2,
        -- INTPTLAT kommt als '+42.0' beziehungsweise '-083.1'; TRY_CAST
        -- kommt mit dem fuehrenden Plus und den fuehrenden Nullen zurecht.
        TRY_CAST(t.INTPTLAT AS DOUBLE)                    AS centroid_lat,
        TRY_CAST(t.INTPTLON AS DOUBLE)                    AS centroid_lon,
        t.geometry                                        AS geometry,
        TRY_CAST(a.B01003_001E AS BIGINT)                 AS population,
        CASE WHEN a.B19013_001E = '{ACS_MISSING_VALUE}' THEN NULL
             ELSE TRY_CAST(a.B19013_001E AS INTEGER) END AS median_household_income_usd,
        TRY_CAST(a.B17001_002E AS INTEGER)                AS population_below_poverty,
        -- Ohne Einwohner ist eine Quote nicht definiert. NULL statt Division
        -- durch null, und die absolute Zahl bleibt trotzdem erhalten.
        CASE WHEN TRY_CAST(a.B01003_001E AS BIGINT) > 0
             THEN TRY_CAST(a.B17001_002E AS DOUBLE)
                  / TRY_CAST(a.B01003_001E AS DOUBLE)
             END                                          AS poverty_rate,
        list_filter([
            CASE WHEN t.GEOID IS NULL THEN 'MISSING_GEOMETRY' END,
            CASE WHEN a.GEOID IS NULL THEN 'MISSING_ACS_ATTRIBUTES' END,
            CASE WHEN a.B19013_001E = '{ACS_MISSING_VALUE}'
                 THEN 'MISSING_MEDIAN_INCOME' END,
            CASE WHEN TRY_CAST(a.B01003_001E AS BIGINT) = 0
                 THEN 'ZERO_POPULATION' END
        ], x -> x IS NOT NULL)                            AS quality_flags
    FROM tiger t
    FULL OUTER JOIN acs a ON t.GEOID = a.GEOID
    LEFT JOIN states s ON s.state_fips = t.STATEFP
    ORDER BY geoid
    """


def reconcile(con: duckdb.DuckDBPyConnection, relation: str) -> dict[str, Any]:
    """Weist nach, dass die Tabelle beide Quellen deckungsgleich abbildet.

    Der Nachweis dieser Schicht ist ein anderer als in Bronze: Dort wird
    belegt, dass eine Auslieferung ganz angekommen ist. Hier wird belegt, dass
    beim Zusammenfuehren keine Zeile verloren ging und keine erfunden wurde.
    """
    zeilen = con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    ohne_geometrie = con.execute(
        f"SELECT count(*) FROM {relation} "
        "WHERE list_contains(quality_flags, 'MISSING_GEOMETRY')"
    ).fetchone()[0]
    ohne_acs = con.execute(
        f"SELECT count(*) FROM {relation} "
        "WHERE list_contains(quality_flags, 'MISSING_ACS_ATTRIBUTES')"
    ).fetchone()[0]
    doppelte = con.execute(
        f"SELECT count(*) FROM (SELECT geoid FROM {relation} "
        "GROUP BY geoid HAVING count(*) > 1)"
    ).fetchone()[0]
    ungueltige_geometrie = con.execute(
        f"SELECT count(*) FROM {relation} "
        "WHERE geometry IS NOT NULL AND NOT ST_IsValid(ST_GeomFromWKB(geometry))"
    ).fetchone()[0]

    if doppelte:
        raise TransformError(
            f"{doppelte} GEOID kommen mehrfach vor; geoid muss eindeutig sein"
        )
    if ohne_geometrie:
        raise TransformError(
            f"{ohne_geometrie} Tracts haben ACS-Attribute, aber keine "
            "Geometrie - ohne Geometrie ist kein raeumlicher Join moeglich"
        )

    return {
        "verified": True,
        "row_count": zeilen,
        "geoid_unique": True,
        "tracts_without_geometry": ohne_geometrie,
        "tracts_without_acs_attributes": ohne_acs,
        "invalid_geometries": ungueltige_geometrie,
    }


def column_statistics(
    con: duckdb.DuckDBPyConnection, relation: str
) -> dict[str, Any]:
    """Fuellgrade und Auffaelligkeiten, die in den Bericht gehoeren."""
    row = con.execute(
        f"""
        SELECT
            count(*)                                            AS zeilen,
            count(population)                                   AS mit_einwohnern,
            count(median_household_income_usd)                  AS mit_einkommen,
            count(poverty_rate)                                 AS mit_quote,
            sum(CASE WHEN population = 0 THEN 1 ELSE 0 END)     AS ohne_einwohner,
            sum(population)                                     AS einwohner_summe
        FROM {relation}
        """
    ).fetchone()
    zeilen = row[0]
    return {
        "population_filled": row[1],
        "median_income_filled": row[2],
        "poverty_rate_defined": row[3],
        "zero_population_tracts": row[4],
        "population_total": row[5],
        "median_income_missing_share": round(1 - row[2] / zeilen, 6) if zeilen else None,
    }


def build_manifest(
    con: duckdb.DuckDBPyConnection,
    relation: str,
    vintage: int,
    sources: list[Source],
    started: datetime,
) -> dict[str, Any]:
    """Das Manifest der Tabelle, mit Herkunft und Nachweis."""
    nachweis = reconcile(con, relation)
    herkunft = [
        {
            "layer": BRONZE_LAYER,
            "dataset": quelle.dataset,
            "state_fips": quelle.state,
            "run_id": quelle.run_id,
        }
        for quelle in sources
    ]
    return {
        "status": "complete",
        "contract_version": CONTRACT_VERSION,
        "code_version": code_stand(),
        "layer": SILVER_LAYER,
        "table": TABLE,
        "grain": "ein Census Tract",
        "vintage": vintage,
        "built_at_utc": started.isoformat().replace("+00:00", "Z"),
        "tool": f"duckdb {duckdb.__version__} mit spatial",
        "format": "parquet (snappy, Geometrie als WKB in EPSG:4269)",
        "row_count": nachweis["row_count"],
        "join_key": "geoid",
        # Ohne diese Herkunft ist der Referenzstand aus Absprache 7.1 nicht
        # belegbar: Sie nennt genau die Bronze-Laeufe, aus denen diese
        # Tabelle entstanden ist.
        "derived_from": herkunft,
        # Ein Abdruck ueber die Eingaben: Wer diese Tabelle benutzt, nennt ihn
        # und sagt damit, auf welchem Stand er ruht - ein Pfad koennte das nicht.
        "input_fingerprint": eingabe_abdruck(herkunft),
        "reconciliation": nachweis,
        "column_statistics": column_statistics(con, relation),
        "schema": schema_of(con, relation),
        "notes": {
            "acs_missing_value": (
                f"{ACS_MISSING_VALUE} aus dem ACS ist hier zu NULL "
                "aufgeloest; in Bronze steht der Code unveraendert"
            ),
            "poverty_rate": (
                "bei Tracts ohne Einwohner NULL, die absoluten Zahlen "
                "bleiben erhalten"
            ),
            "extra_column": "_extra wird nicht uebernommen und bleibt in Bronze",
        },
    }


def build(data_root: Path, vintage: int, states: list[str]) -> Path:
    """Baut die Tabelle und liefert das veroeffentlichte Verzeichnis."""
    started = datetime.now(timezone.utc)
    tiger = [
        newest_bronze_run(data_root, TIGER_DATASET, vintage, state)
        for state in states
    ]
    acs = [
        newest_bronze_run(data_root, ACS_DATASET, vintage, state)
        for state in states
    ]
    for quelle in tiger + acs:
        log.info("Quelle: %s %s %s", quelle.dataset, quelle.state, quelle.run_id)

    con = connect(spatial=True)
    try:
        con.execute(f"CREATE TEMP VIEW tract_silver AS {build_query(tiger, acs)}")
        manifest = build_manifest(
            con, "tract_silver", vintage, tiger + acs, started
        )
        ziel = publish(
            con, "tract_silver", table_dir(data_root, vintage), manifest
        )
    finally:
        con.close()
    # Erst nach Bau und Manifest, nie davor: Was hier ankommt, hat bestanden.
    for_root(data_root).publish_table(ziel)
    return ziel


def main() -> int:
    args = arguments()
    from storage.verwaltet import sperre
    sperre(for_root(args.data_root).local_root, worker_erlaubt=True)
    from storage.analysesitzung import schreibzugriff
    with schreibzugriff(for_root(args.data_root).local_root, invalidieren=True):
        try:
            # Ueber die Ablage und nicht ueber den Pfad: ``publish_table``
            # entfernt im s3-Modus die lokale Arbeitskopie, und dieser
            # Schlussbericht las sie trotzdem - jeder Lauf endete dort mit
            # "Invalid manifest" und Exitcode 1, obwohl die Tabelle sauber
            # publiziert war. Siehe ``Storage.tabellen_manifest``.
            ablage = for_root(args.data_root)
            ziel = build(ablage.local_root, args.vintage, args.state)
            manifest = ablage.tabellen_manifest(ziel)
            log.info("Silver-Tabelle geschrieben: %s", ziel)
            log.info("  Zeilen: %s", f"{manifest['row_count']:,}")
            statistik = manifest["column_statistics"]
            log.info(
                "  Einwohner insgesamt: %s, Tracts ohne Einwohner: %s",
                f"{statistik['population_total']:,}",
                statistik["zero_population_tracts"],
            )
            log.info(
                "  ohne Median-Einkommen: %s (%.1f %%)",
                manifest["row_count"] - statistik["median_income_filled"],
                statistik["median_income_missing_share"] * 100,
            )
            return 0
        except (TransformError, StorageError, OSError, duckdb.Error) as error:
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
