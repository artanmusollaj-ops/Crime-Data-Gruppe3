"""Baut die Silver-Tabelle ``weather_day`` aus den NOAA-Stationsreihen.

Eine Zeile je **Stadt und Tag**. Das ist ein anderes Korn als die
Faktentabelle, und genau deshalb ist es eine eigene Tabelle: Ein Wetterwert
an jedes Delikt derselben Stadt und desselben Tages zu haengen wuerde Zeilen
vervielfachen, und jede spaetere Aggregation ueber Wetter zaehlte falsch.
Verbunden wird erst in Gold, dort auf dem Aggregationskorn.

Aufruf aus dem Projekt-Root:

    python -m silver_pipeline.build_weather_day

Was hier gedeutet wird und in Bronze bewusst nicht:

1. **Einheiten.** GHCN-Daily fuehrt Temperatur und Niederschlag in Zehnteln,
   Schneefall dagegen direkt in Millimetern. ``"  214"`` sind 21,4 Grad
   Celsius. An echten Rekorden geprueft: Das Maximum 400 ergibt 40,0 Grad,
   das Minimum -328 ergibt -32,8 Grad, der Tagesniederschlag 1742 ergibt
   174,2 Millimeter, der Schneefall 472 bleibt 472 Millimeter.
2. **Fehlwerte.** Ein leeres Feld ist keine Null. Bei Niederschlag ist das
   der entscheidende Unterschied: kein Messwert ist nicht dasselbe wie kein
   Regen.
3. **Spurenmengen.** Das Messflag ``T`` heisst "messbar vorhanden, aber unter
   der Auflösung". Der Wert steht dann als ``0`` da, was fachlich etwas
   anderes ist als trocken. Deshalb eine eigene Spalte.
4. **Qualitaetsflags.** Die zweite Position von ``M,Q,S`` ist NOAAs
   Beanstandung. Sie ist fast immer leer, aber nicht immer: O'Hare hat vier
   ``SNOW``-Zeilen mit ``I`` zwischen 1999 und 2011. Beanstandete Werte
   werden benannt und nicht entfernt.
5. **Eine Station je Stadt.** Absprache 3 hat das so entschieden. Diese
   Tabelle nimmt deshalb je Stadt die Flughafenstation und nennt im Manifest,
   welche das war und welche geladenen Stationen uebergangen wurden - damit
   ein zugeschaltetes Midway nicht stillschweigend verschwindet.

Die Feldzahl der ``_ATTRIBUTES``-Spalten wird **nicht** unterstellt: Sie ist
je Groesse und je Station verschieden - drei bei ``TMAX``, vier bei ``PRCP``,
und bei Detroits ``SNOW`` wieder drei. ``split_part`` liefert bei fehlendem
Feld einen leeren Text, was hier zu ``NULL`` wird; ein Parser mit fester
Feldzahl wuerde stattdessen Positionen verschieben.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

import duckdb

from storage import StorageError, for_root
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
from weather_pipeline import STATIONS

TABLE = "weather_day"
NOAA_DATASET = "noaa_ghcnd"

# Zehntelgrad Celsius beziehungsweise Zehntelmillimeter. SNOW steht schon in
# Millimetern und wird deshalb nicht geteilt.
TENTHS = 10.0
TRACE_FLAG = "T"

# Die Reihen reichen bis 1942 zurueck und sind dort lueckenhaft. Fuer das
# Projekt zaehlt aber nur, ob sie im Zeitraum der Falldaten vollstaendig sind -
# Chicago liefert Faelle ab 2001. Das Manifest weist beides aus.
COVERAGE_CUTOFF = "2001-01-01"

log = logging.getLogger("silver_weather_day")


class Source(NamedTuple):
    """Ein Bronze-Lauf, der in diese Tabelle eingeht."""

    station: str
    city: str
    run_id: str
    parquet: str   # lokal oder s3://, siehe storage.resolve_read_path


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    parser.add_argument(
        "--station",
        action="append",
        choices=sorted(STATIONS),
        help=(
            "Stations-ID; mehrfach moeglich. Ohne Angabe je Stadt die "
            "Flughafenstation. Zwei Stationen derselben Stadt sind ein Fehler, "
            "weil das Korn Stadt und Tag ist."
        ),
    )
    args = parser.parse_args()
    args.station = args.station or [
        sid for sid, info in STATIONS.items() if info["default"]
    ]
    return args


def table_dir(data_root: Path) -> Path:
    """Wohin die Tabelle geschrieben wird.

    Ohne Vintage-Partition: Die Reihen wachsen taeglich, es gibt keinen
    eingefrorenen Jahrgang wie bei Census.
    """
    return data_root / SILVER_LAYER / f"dataset={TABLE}"


def newest_bronze_run(data_root: Path, station: str) -> Source:
    """Der juengste vollstaendige Bronze-Lauf dieser Station."""
    ablage = for_root(data_root)
    prefix = f"{BRONZE_LAYER}/dataset={NOAA_DATASET}/station={station}"
    lauf = newest_complete_run(ablage, prefix, what=f"{NOAA_DATASET}, Station {station}")
    stadt = STATIONS.get(station, {}).get("city")
    if stadt is None:
        raise TransformError(f"Unbekannte Station: {station}")
    return Source(station, stadt, lauf.verzeichnis.name,
                  ablage.resolve_read_path(lauf.relativ, PARQUET_FILE))


def collect_sources(data_root: Path, stations: list[str]) -> list[Source]:
    """Je Stadt genau eine Station - sonst bricht das Korn.

    Absprache 3 hat "eine Station je Stadt" entschieden. Zwei Stationen
    derselben Stadt wuerden zwei Zeilen fuer denselben Tag ergeben; das faellt
    hier auf und nicht erst beim Zaehlen in Gold.
    """
    quellen = [newest_bronze_run(data_root, station) for station in stations]
    je_stadt: dict[str, list[Source]] = {}
    for quelle in quellen:
        je_stadt.setdefault(quelle.city, []).append(quelle)
    doppelt = {
        stadt: [q.station for q in liste]
        for stadt, liste in je_stadt.items()
        if len(liste) > 1
    }
    if doppelt:
        raise TransformError(
            "Mehr als eine Station je Stadt, das Korn ist Stadt und Tag: "
            f"{doppelt}. Absprache 3 sieht eine Station je Stadt vor."
        )
    return quellen


def skipped_stations(data_root: Path, used: list[Source]) -> list[dict[str, str]]:
    """Geladene Stationen, die diese Tabelle uebergeht.

    Sie gehoeren ins Manifest: Wer Midway zuschaltet und die Stadtzeile
    unveraendert sieht, soll nachlesen koennen, warum.
    """
    genutzt = {quelle.station for quelle in used}
    ablage = for_root(data_root)
    prefix = f"{BRONZE_LAYER}/dataset={NOAA_DATASET}"
    stationen = sorted({
        lauf.relativ[len(prefix) + 1:].split("/")[0].removeprefix("station=")
        for lauf in ablage.laeufe(prefix, "station=*/run_*/manifest.json")
    })
    uebergangen = []
    for station in stationen:
        if station in genutzt:
            continue
        uebergangen.append(
            {
                "station_id": station,
                "city": STATIONS.get(station, {}).get("city", "unbekannt"),
                "reason": "je Stadt wird eine Station verwendet (Absprache 3)",
            }
        )
    return uebergangen


def measurement_sql(column: str, *, tenths: bool) -> str:
    """Wert und Flags einer Messgroesse in Silver-Form.

    Der Teiler steht hier und nicht in der Auswertung, damit die Einheit an
    genau einer Stelle festgelegt ist.
    """
    teiler = f" / {TENTHS}" if tenths else ""
    return f"TRY_CAST({column} AS DOUBLE){teiler}"


def flag_sql(column: str, position: int) -> str:
    """Eine Position aus ``M,Q,S[,Beobachtungszeit]``.

    ``split_part`` liefert bei fehlendem Feld einen leeren Text - deshalb
    ``nullif``. Die Feldzahl wird nicht unterstellt, sie ist je Groesse und je
    Station verschieden.
    """
    return f"nullif(split_part({column}_ATTRIBUTES, ',', {position}), '')"


def build_query(sources: list[Source]) -> str:
    """Die Abfrage, die aus Stationsreihen Stadt-Tage macht."""
    lesen = " UNION ALL ".join(
        f"SELECT '{quelle.city}' AS city, '{quelle.station}' AS station_id, * "
        f"FROM read_parquet('{quelle.parquet}')"
        for quelle in sources
    )
    return f"""
    WITH roh AS ({lesen})
    SELECT
        city,
        CAST(DATE AS DATE)                          AS date,
        station_id,
        NAME                                        AS station_name,
        {measurement_sql('TMAX', tenths=True)}      AS temp_max_c,
        {measurement_sql('TMIN', tenths=True)}      AS temp_min_c,
        {measurement_sql('PRCP', tenths=True)}      AS precipitation_mm,
        {measurement_sql('SNOW', tenths=False)}     AS snowfall_mm,
        -- Spurenmenge: messbar vorhanden, aber unter der Auflösung. Der Wert
        -- steht als 0 da, was fachlich etwas anderes ist als trocken.
        coalesce({flag_sql('PRCP', 1)} = '{TRACE_FLAG}', FALSE) AS precipitation_trace,
        coalesce({flag_sql('SNOW', 1)} = '{TRACE_FLAG}', FALSE) AS snowfall_trace,
        list_filter([
            CASE WHEN TRY_CAST(TMAX AS DOUBLE) IS NULL
                   OR TRY_CAST(TMIN AS DOUBLE) IS NULL
                 THEN 'MISSING_TEMPERATURE' END,
            CASE WHEN TRY_CAST(PRCP AS DOUBLE) IS NULL
                 THEN 'MISSING_PRECIPITATION' END,
            CASE WHEN TRY_CAST(SNOW AS DOUBLE) IS NULL
                 THEN 'MISSING_SNOWFALL' END,
            -- Zweite Position von M,Q,S ist NOAAs Beanstandung. Fast immer
            -- leer, aber nicht immer.
            CASE WHEN {flag_sql('TMAX', 2)} IS NOT NULL THEN 'SUSPECT_TEMP_MAX' END,
            CASE WHEN {flag_sql('TMIN', 2)} IS NOT NULL THEN 'SUSPECT_TEMP_MIN' END,
            CASE WHEN {flag_sql('PRCP', 2)} IS NOT NULL THEN 'SUSPECT_PRECIPITATION' END,
            CASE WHEN {flag_sql('SNOW', 2)} IS NOT NULL THEN 'SUSPECT_SNOWFALL' END
        ], x -> x IS NOT NULL)                      AS quality_flags
    FROM roh
    ORDER BY city, date
    """


def reconcile(
    con: duckdb.DuckDBPyConnection, relation: str, sources: list[Source]
) -> dict[str, Any]:
    """Weist nach, dass das Korn haelt und keine Zeile verloren ging."""
    quellzeilen = sum(
        con.execute(
            f"SELECT count(*) FROM read_parquet('{quelle.parquet}')"
        ).fetchone()[0]
        for quelle in sources
    )
    zeilen = con.execute(f"SELECT count(*) FROM {relation}").fetchone()[0]
    doppelte = con.execute(
        f"SELECT count(*) FROM (SELECT city, date FROM {relation} "
        "GROUP BY city, date HAVING count(*) > 1)"
    ).fetchone()[0]
    ohne_datum = con.execute(
        f"SELECT count(*) FROM {relation} WHERE date IS NULL"
    ).fetchone()[0]

    if doppelte:
        raise TransformError(
            f"{doppelte} Kombinationen aus Stadt und Tag kommen mehrfach vor; "
            "das Korn dieser Tabelle ist Stadt und Tag"
        )
    if ohne_datum:
        raise TransformError(f"{ohne_datum} Zeilen ohne lesbares Datum")
    if zeilen != quellzeilen:
        raise TransformError(
            f"Zeilenzahl weicht ab: {quellzeilen} in Bronze, {zeilen} in Silver"
        )

    return {
        "verified": True,
        "bronze_rows": quellzeilen,
        "row_count": zeilen,
        "city_date_unique": True,
        "rows_without_date": ohne_datum,
    }


def coverage(con: duckdb.DuckDBPyConnection, relation: str) -> list[dict[str, Any]]:
    """Abdeckung je Stadt, samt der Luecken in der taeglichen Reihe.

    Die Reihe soll taeglich sein, ist es aber nicht ueberall: Fehlende Tage
    werden gezaehlt und ausgewiesen, statt sie in einer Auswertung als
    Nullwerte zu erscheinen.
    """
    return [
        {
            "city": row[0],
            "station_id": row[1],
            "first_date": row[2].isoformat(),
            "last_date": row[3].isoformat(),
            "row_count": row[4],
            "expected_days": row[5],
            "missing_days": row[5] - row[4],
            "temperature_filled": row[6],
            "precipitation_filled": row[7],
            "trace_precipitation_days": row[8],
            "suspect_rows": row[9],
            # Gemessen wird die Dichte zwischen erstem und letztem Tag im
            # Fenster, nicht der Abstand zum Stichtag: Sonst zaehlte eine
            # Reihe, die erst 2024 beginnt, zwei Jahrzehnte Abwesenheit als
            # Luecken. Dass sie spaet beginnt, verraet first_date.
            "since_cutoff": {
                "cutoff": COVERAGE_CUTOFF,
                "row_count": row[10],
                "first_date": row[11].isoformat() if row[11] else None,
                "last_date": row[12].isoformat() if row[12] else None,
                "expected_days": row[13],
                "missing_days": (row[13] - row[10]) if row[13] else 0,
                "temperature_filled": row[14],
            },
        }
        for row in con.execute(
            f"""
            SELECT city, any_value(station_id), min(date), max(date), count(*),
                   datediff('day', min(date), max(date)) + 1,
                   count(temp_max_c),
                   count(precipitation_mm),
                   sum(CASE WHEN precipitation_trace THEN 1 ELSE 0 END),
                   sum(CASE WHEN len(list_filter(quality_flags,
                        x -> starts_with(x, 'SUSPECT_'))) > 0 THEN 1 ELSE 0 END),
                   -- dieselben Kennzahlen nochmal ab dem Stichtag
                   count(*) FILTER (date >= DATE '{COVERAGE_CUTOFF}'),
                   min(date) FILTER (date >= DATE '{COVERAGE_CUTOFF}'),
                   max(date) FILTER (date >= DATE '{COVERAGE_CUTOFF}'),
                   datediff('day',
                       min(date) FILTER (date >= DATE '{COVERAGE_CUTOFF}'),
                       max(date) FILTER (date >= DATE '{COVERAGE_CUTOFF}')) + 1,
                   count(temp_max_c) FILTER (date >= DATE '{COVERAGE_CUTOFF}')
            FROM {relation} GROUP BY city ORDER BY city
            """
        ).fetchall()
    ]


def build_manifest(
    con: duckdb.DuckDBPyConnection,
    relation: str,
    sources: list[Source],
    skipped: list[dict[str, str]],
    started: datetime,
) -> dict[str, Any]:
    nachweis = reconcile(con, relation, sources)
    return {
        "status": "complete",
        "layer": SILVER_LAYER,
        "table": TABLE,
        "grain": "eine Stadt an einem Tag",
        "built_at_utc": started.isoformat().replace("+00:00", "Z"),
        "tool": f"duckdb {duckdb.__version__}",
        "format": "parquet (snappy)",
        "row_count": nachweis["row_count"],
        # Wetter wird nicht raeumlich verbunden, sondern ueber Stadt und Tag.
        "join_keys": ["city", "date"],
        "derived_from": [
            {
                "layer": BRONZE_LAYER,
                "dataset": NOAA_DATASET,
                "station_id": quelle.station,
                "city": quelle.city,
                "run_id": quelle.run_id,
            }
            for quelle in sources
        ],
        "skipped_stations": skipped,
        "reconciliation": nachweis,
        "coverage": coverage(con, relation),
        "schema": schema_of(con, relation),
        "notes": {
            "units": (
                "temp_max_c und temp_min_c in Grad Celsius, precipitation_mm "
                "und snowfall_mm in Millimetern. Die Quelle fuehrt Temperatur "
                "und Niederschlag in Zehnteln, Schneefall schon in Millimetern"
            ),
            "trace": (
                "precipitation_trace bedeutet messbarer Niederschlag unter der "
                "Auflösung; der Wert ist dann 0 und nicht fehlend"
            ),
            "missing_vs_zero": (
                "ein leeres Quellfeld wird NULL und nicht 0 - bei Niederschlag "
                "der entscheidende Unterschied"
            ),
            "coverage_before_1970": (
                "die Reihen reichen bis 1942 zurueck und sind dort "
                "lueckenhaft; ab dem Stichtag in coverage.since_cutoff ist "
                "sie vollstaendig"
            ),
            "source_lag": (
                "GHCN-Daily veroeffentlicht mit rund vier Tagen Nachlauf; ein "
                "T-1-Anspruch nach Absprache 7.1 ist hier nicht erfuellbar"
            ),
            "extra_column": "_extra wird nicht uebernommen und bleibt in Bronze",
        },
    }


def build(data_root: Path, stations: list[str]) -> Path:
    """Baut die Tabelle und liefert das veroeffentlichte Verzeichnis."""
    started = datetime.now(timezone.utc)
    sources = collect_sources(data_root, stations)
    for quelle in sources:
        log.info("Quelle: %s (%s) %s", quelle.station, quelle.city, quelle.run_id)
    uebergangen = skipped_stations(data_root, sources)
    for eintrag in uebergangen:
        log.info(
            "uebergangen: %s (%s) - %s",
            eintrag["station_id"],
            eintrag["city"],
            eintrag["reason"],
        )

    con = connect()
    try:
        con.execute(f"CREATE TEMP VIEW weather_silver AS {build_query(sources)}")
        manifest = build_manifest(
            con, "weather_silver", sources, uebergangen, started
        )
        ziel = publish(con, "weather_silver", table_dir(data_root), manifest)
    finally:
        con.close()
    for_root(data_root).publish_table(ziel)
    return ziel


def main() -> int:
    args = arguments()
    try:
        ziel = build(for_root(args.data_root).local_root, args.station)
        manifest = read_manifest(ziel)
        log.info("Silver-Tabelle geschrieben: %s", ziel)
        log.info("  Zeilen: %s", f"{manifest['row_count']:,}")
        for abdeckung in manifest["coverage"]:
            log.info(
                "  %s (%s): %s bis %s, %s Zeilen, %s fehlende Tage, "
                "%s Tage mit Spurenmenge, %s beanstandet",
                abdeckung["city"],
                abdeckung["station_id"],
                abdeckung["first_date"],
                abdeckung["last_date"],
                f"{abdeckung['row_count']:,}",
                abdeckung["missing_days"],
                f"{abdeckung['trace_precipitation_days']:,}",
                abdeckung["suspect_rows"],
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
