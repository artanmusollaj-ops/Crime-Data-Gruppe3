"""Vier vorberechnete Tabellen fuer das Dashboard - aus Gold, nicht statt Gold.

    python -m serving.build_comparison [--data-root data]

``comparison_day``, ``comparison_week`` und ``comparison_month`` zaehlen
Taten und Faelle je Stadt, Zeitraum und NIBRS-Kategorie. ``partition_quality``
sagt je Stadt und Monat, wie gut die Zuordnungen sind, auf denen diese Zahlen
ruhen.

**Warum es sie gibt, obwohl Gold sie nicht braucht.** Notebook 34 hat gemessen,
dass eine Vorberechnung bei 344'617 Zeilen nichts spart, was ein Mensch
bemerkt; Konzept 5.2 hielt deshalb fest, Gold aggregiere nicht. Beides gilt
weiter - **Gold** aggregiert nicht. Diese Tabellen liegen in **Serving**: Sie
sind das, was ein Dashboard liest und was ein Release enthaelt, und sie sind
jederzeit aus dem Stern neu zu erzeugen. Der externe Rat vom 17.9.2026 hat sie
als Teil des Veroeffentlichungsstands vorgeschlagen, und fuer ein
Studienprojekt zaehlt, dass beide Bauweisen gebaut nebeneinander stehen -
nicht nur die gemessene Entscheidung fuer eine davon.

**Was sie duerfen und was nicht.** Sie beantworten die Fragen, auf die sie
gebaut sind: je Stadt, Kategorie und Tag, Woche oder Monat. Was keine Achse
ist, existiert in ihnen nicht - kein Tract, kein einzelner Code, keine
Stunde. Wer das braucht, fragt den Stern; ``docs/sternschema-und-wuerfel.md``
sagt, warum das die richtige Reihenfolge ist.

**Die Gegenprobe.** Jede der drei Vergleichstabellen muss sich auf die
Faktentabelle aufsummieren - Taten wie Faelle. Das geht, weil jede Zeile von
``fact_offense`` genau eine Kategorie traegt und ``counts_case`` genau eine
Zeile je Fall markiert (siehe ``docs/zaehlperspektiven.md``). Stimmt die Summe
nicht, ist die Tabelle falsch gebaut, und der Bau bricht ab.

**Teilperioden sind ausgewiesen.** Die letzte Woche des Jahrgangs hat zwei
Tage; wer sie neben eine volle stellt, sieht einen Einbruch, der keiner ist.
``days_in_window`` sagt je Woche und Monat, wie viele Kalendertage im
Zeitfenster der Daten liegen; ``days_in_period`` sagt, wie viele die Periode
hat.
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from manifeste import MANIFEST, code_stand, eingabe_abdruck, read_manifest, referenz
from serving import SERVING_LAYER
from silver_pipeline import PARQUET_FILE, TransformError, connect, publish, schema_of
from storage import for_root


LOG = logging.getLogger("build_comparison")

# Der Deutungsvertrag dieser Tabellen. Steigt die Zahl, sind aeltere Staende
# anders zu lesen; jede Erhoehung gehoert in AENDERUNGEN.md.
CONTRACT_VERSION = 1

GOLD_LAYER = "gold"
TABELLEN = ("comparison_day", "comparison_week", "comparison_month",
            "partition_quality")

# Woran eine Woche beginnt. ISO: Montag. Das Fenster der Daten beginnt am
# 1. Januar - nur 2024 faellt beides zusammen.
WOCHENBEGINN = "week"


def table_dir(data_root: Path, table: str) -> Path:
    return data_root / SERVING_LAYER / f"dataset={table}"


# ---------------------------------------------------------------------------
# Quellen
# ---------------------------------------------------------------------------


def gold_quelle(data_root: Path, tabelle: str) -> tuple[str, dict[str, Any]]:
    """Lesepfad und Manifest einer Gold-Tabelle - lokal oder S3."""
    ablage = for_root(data_root)
    rel_dir = f"{GOLD_LAYER}/dataset={tabelle}"
    if not ablage.exists(rel_dir, MANIFEST):
        raise TransformError(
            f"gold/{tabelle} ist nicht gebaut ({ablage.local_path(rel_dir)}). "
            "Zuerst: python -m gold_pipeline.build_gold"
        )
    lokal = ablage.local_path(rel_dir, MANIFEST)
    manifest = (read_manifest(lokal) if lokal.exists()
                else json.loads(ablage.read_text(rel_dir, MANIFEST)))
    return ablage.resolve_read_path(rel_dir, PARQUET_FILE), manifest


# ---------------------------------------------------------------------------
# Die Abfragen
# ---------------------------------------------------------------------------


def basis_query(fakten: str, delikte: str) -> str:
    """Eine Tat je Zeile, mit ihrer Kategorie - die gemeinsame Grundlage."""
    return f"""
        SELECT f.reporting_city, f.date, f.counts_case,
               f.mapping_status, f.geo_status, f.local_time_ambiguous,
               -- Eine Tat ohne NIBRS-Code (mapping_status = unmapped) hat
               -- keine Kategorie, zaehlt aber. Sie bekommt ihre eigene, damit
               -- die Summen aufgehen und niemand sie beim Filtern verliert.
               CASE WHEN f.nibrs_code IS NULL THEN 'unmapped'
                    ELSE d.nibrs_category END AS nibrs_category,
               f.nibrs_family, f.nibrs_code
        FROM read_parquet('{fakten}') f
        LEFT JOIN read_parquet('{delikte}') d USING (nibrs_code)
    """


def zeitraum_query(periode: str) -> str:
    """Taten und Faelle je Stadt, Periode und Kategorie.

    ``periode`` ist ein DuckDB-Ausdruck ueber ``date``: der Tag selbst, der
    Montag der Woche oder der Monatserste.
    """
    return f"""
        SELECT reporting_city,
               {periode} AS period_start,
               nibrs_category, nibrs_family,
               count(*)                    AS offenses,
               count(*) FILTER (counts_case) AS cases
        FROM basis
        GROUP BY 1, 2, 3, 4
        ORDER BY 1, 2, 3, 4
    """


def mit_fenster(relation: str, periodenende: str) -> str:
    """Ergaenzt Periodenlaenge und die Tage, die im Datenfenster liegen.

    Das Datenfenster ist ``min(date)`` bis ``max(date)`` der Faktentabelle.
    Eine Woche, die am 30. Dezember beginnt, hat sieben Tage, aber nur zwei im
    Fenster - und genau das steht dann daneben. ``periodenende`` ist ein
    Ausdruck ueber ``period_start`` fuer den letzten Tag der Periode.
    """
    return f"""
        SELECT r.reporting_city, r.period_start,
               ({periodenende})::DATE                                 AS period_end,
               r.nibrs_category, r.nibrs_family, r.offenses, r.cases,
               date_diff('day', r.period_start, ({periodenende})::DATE) + 1
                                                                       AS days_in_period,
               date_diff('day', greatest(r.period_start, fenster.von),
                                least(({periodenende})::DATE, fenster.bis)) + 1
                                                                       AS days_in_window
        FROM {relation} r,
             (SELECT min(date) AS von, max(date) AS bis FROM basis) fenster
        ORDER BY 1, 2, 4, 5
    """


QUALITAET_QUERY = """
    SELECT reporting_city,
           date_trunc('month', date)::DATE                             AS month,
           count(*)                                                    AS offenses,
           round(100.0 * count(*) FILTER (mapping_status = 'exact')        / count(*), 2) AS share_exact,
           round(100.0 * count(*) FILTER (mapping_status = 'ambiguous')    / count(*), 2) AS share_ambiguous,
           round(100.0 * count(*) FILTER (mapping_status = 'fallback_90Z') / count(*), 2) AS share_fallback_90z,
           round(100.0 * count(*) FILTER (mapping_status = 'unmapped')     / count(*), 2) AS share_unmapped,
           round(100.0 * count(*) FILTER (geo_status = 'inside_city')        / count(*), 2) AS share_inside_city,
           round(100.0 * count(*) FILTER (geo_status = 'outside_city')       / count(*), 2) AS share_outside_city,
           round(100.0 * count(*) FILTER (geo_status = 'no_tract')           / count(*), 2) AS share_no_tract,
           round(100.0 * count(*) FILTER (geo_status = 'missing_coordinate') / count(*), 2) AS share_missing_coordinate,
           count(*) FILTER (local_time_ambiguous)                      AS local_time_ambiguous
    FROM basis
    GROUP BY 1, 2
    ORDER BY 1, 2
"""


# ---------------------------------------------------------------------------
# Nachweis
# ---------------------------------------------------------------------------


def reconcile(con: Any) -> dict[str, Any]:
    """Was die Tabellen ueber sich behaupten duerfen.

    Jede Vergleichstabelle muss sich auf die Faktentabelle aufsummieren,
    Taten wie Faelle - je Stadt. Eine Abweichung heisst nicht *ungenau*,
    sondern *falsch gebaut*: Der Join hat Zeilen verloren oder verdoppelt.
    """
    erwartet = {
        stadt: (taten, faelle)
        for stadt, taten, faelle in con.execute(
            "SELECT reporting_city, count(*), count(*) FILTER (counts_case) "
            "FROM basis GROUP BY 1"
        ).fetchall()
    }
    summen: dict[str, dict[str, Any]] = {}
    for tabelle in ("comparison_day", "comparison_week", "comparison_month"):
        gemessen = {
            stadt: (taten, faelle)
            for stadt, taten, faelle in con.execute(
                f"SELECT reporting_city, sum(offenses), sum(cases) "
                f"FROM {tabelle} GROUP BY 1"
            ).fetchall()
        }
        if gemessen != erwartet:
            raise TransformError(
                f"{tabelle} summiert sich nicht auf die Faktentabelle: "
                f"gemessen {gemessen}, erwartet {erwartet}. Der Join hat Zeilen "
                "verloren oder verdoppelt."
            )
        summen[tabelle] = {
            "rows": con.execute(f"SELECT count(*) FROM {tabelle}").fetchone()[0],
            "offenses": sum(t for t, _ in gemessen.values()),
            "cases": sum(f for _, f in gemessen.values()),
        }

    ohne_kategorie = con.execute(
        "SELECT count(*) FROM basis WHERE nibrs_category IS NULL "
        "AND nibrs_code IS NOT NULL"
    ).fetchone()[0]
    if ohne_kategorie:
        raise TransformError(
            f"{ohne_kategorie} Taten mit NIBRS-Code, aber ohne Kategorie - "
            "dim_offense kennt den Code nicht. Eine Kategorie-Summe verloere "
            "sie stillschweigend."
        )

    # Die Teilperioden am Rand: sie sind da, und sie sind ausgewiesen.
    teilperioden = {
        tabelle: con.execute(
            f"SELECT count(DISTINCT period_start) FROM {tabelle} "
            f"WHERE days_in_window < days_in_period"
        ).fetchone()[0]
        for tabelle in ("comparison_week", "comparison_month")
    }
    qualitaet = con.execute("SELECT sum(offenses) FROM partition_quality").fetchone()[0]
    if qualitaet != sum(t for t, _ in erwartet.values()):
        raise TransformError(
            f"partition_quality zaehlt {qualitaet} Taten, die Faktentabelle "
            f"{sum(t for t, _ in erwartet.values())}"
        )
    return {
        "per_city": {s: {"offenses": t, "cases": f} for s, (t, f) in erwartet.items()},
        "sums": summen,
        "partial_periods": teilperioden,
    }


# ---------------------------------------------------------------------------
# Manifest und Aufbau
# ---------------------------------------------------------------------------


GRANULARITAET = {
    "comparison_day": "eine Stadt, ein Tag, eine NIBRS-Kategorie",
    "comparison_week": "eine Stadt, eine Woche ab Montag, eine NIBRS-Kategorie",
    "comparison_month": "eine Stadt, ein Monat, eine NIBRS-Kategorie",
    "partition_quality": "eine Stadt, ein Monat",
}

NOTIZEN = {
    "additiv": (
        "offenses und cases summieren sich je Stadt auf fact_offense - "
        "jede Tat traegt genau eine Kategorie, counts_case markiert genau "
        "eine Zeile je Fall. Ueber Kategorien hinweg darf man deshalb "
        "addieren; ueber Tage zu Wochen nicht ohne Blick auf days_in_window"
    ),
    "keine_achse": (
        "kein Tract, kein einzelner NIBRS-Code, keine Stunde. Was hier keine "
        "Achse ist, existiert hier nicht - der Stern in gold/ hat es"
    ),
    "abgeleitet": (
        "jederzeit aus gold/fact_offense und gold/dim_offense neu erzeugbar; "
        "die Quelle der Wahrheit bleibt der Stern"
    ),
}


def build_manifest(con: Any, tabelle: str, herkunft: dict[str, Any],
                   begonnen: datetime, nachweis: dict[str, Any]) -> dict[str, Any]:
    zeilen = con.execute(f"SELECT count(*) FROM {tabelle}").fetchone()[0]
    return {
        "status": "complete",
        "contract_version": CONTRACT_VERSION,
        "code_version": code_stand(),
        "table": tabelle,
        "layer": SERVING_LAYER,
        "row_count": zeilen,
        "grain": GRANULARITAET[tabelle],
        "built_at_utc": begonnen.isoformat(),
        "derived_from": herkunft,
        "input_fingerprint": eingabe_abdruck(herkunft),
        "notes": NOTIZEN,
        "checks": nachweis,
        "schema": schema_of(con, tabelle),
    }


def build(data_root: Path) -> dict[str, Path]:
    """Baut die vier Tabellen und veroeffentlicht sie lokal, jede atomar.

    Publiziert wird hier **nicht** - Serving-Tabellen erreichen SeaweedFS nur
    als Teil eines Release (``storage.release``), nie an einem festen Pfad.
    """
    begonnen = datetime.now(timezone.utc)
    fakten, m_fakten = gold_quelle(data_root, "fact_offense")
    delikte, m_delikte = gold_quelle(data_root, "dim_offense")
    herkunft = {
        "gold_fact_offense": referenz(Path(fakten), m_fakten),
        "gold_dim_offense": referenz(Path(delikte), m_delikte),
    }

    con = connect()
    ziele: dict[str, Path] = {}
    try:
        from storage import duckdb as storage_duckdb
        ablage = for_root(data_root)
        if ablage.config.remote:
            storage_duckdb.s3_einrichten(con, ablage.config)

        con.execute(f"CREATE TABLE basis AS {basis_query(fakten, delikte)}")
        con.execute(f"CREATE TABLE comparison_day AS {zeitraum_query('date')}")
        con.execute(
            "CREATE TABLE _woche AS "
            + zeitraum_query(f"date_trunc('{WOCHENBEGINN}', date)::DATE")
        )
        con.execute(
            "CREATE TABLE comparison_week AS "
            + mit_fenster("_woche", "period_start + INTERVAL 6 DAY")
        )
        con.execute(
            "CREATE TABLE _monat AS "
            + zeitraum_query("date_trunc('month', date)::DATE")
        )
        con.execute(
            "CREATE TABLE comparison_month AS "
            + mit_fenster("_monat", "period_start + INTERVAL 1 MONTH - INTERVAL 1 DAY")
        )
        con.execute(f"CREATE TABLE partition_quality AS {QUALITAET_QUERY}")

        nachweis = reconcile(con)
        # Erst nach dem Nachweis bekommen die Perioden ihren sprechenden Namen.
        con.execute("ALTER TABLE comparison_day RENAME period_start TO date")
        con.execute("ALTER TABLE comparison_week RENAME period_start TO week_start")
        con.execute("ALTER TABLE comparison_week RENAME period_end TO week_end")
        con.execute("ALTER TABLE comparison_month RENAME period_start TO month")
        con.execute("ALTER TABLE comparison_month RENAME period_end TO month_end")
        for tabelle in TABELLEN:
            manifest = build_manifest(con, tabelle, herkunft, begonnen, nachweis)
            ziele[tabelle] = publish(con, tabelle, table_dir(data_root, tabelle), manifest)
            LOG.info("%s: %s Zeilen -> %s", tabelle,
                     f"{manifest['row_count']:,}", ziele[tabelle])
    finally:
        con.close()
    return ziele


def arguments() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Baut die vier Vergleichstabellen fuer das Dashboard aus Gold."
    )
    p.add_argument("--data-root", type=Path, default=None,
                   help="Wurzel der Schichten (Vorgabe: LOCAL_DATA_ROOT oder data)")
    p.add_argument("--verbose", action="store_true")
    return p.parse_args()


def main() -> int:
    args = arguments()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )
    try:
        ziele = build(for_root(args.data_root).local_root)
    except TransformError as fehler:
        LOG.error("%s", fehler)
        return 1
    LOG.info("Serving-Vergleichstabellen gebaut: %s", ", ".join(ziele))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
