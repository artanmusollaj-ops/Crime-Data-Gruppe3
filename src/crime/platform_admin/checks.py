"""Independent post-build checks and logical before/after snapshots.

The current Main metric is preserved: offenses = selected Gold rows,
cases = counts_case representatives, NOT distinct reports per category.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from storage import for_root

from storage.duckdb import verbinde

from .store import AdminError, DEFAULT_SETTINGS, now


TABLES = {
    "silver_crime": "silver/dataset=crime_offense",
    **{
        n: f"gold/dataset={n}"
        for n in ("fact_offense", "dim_offense", "dim_date", "dim_tract", "dim_city_day")
    },
    **{
        n: f"serving/dataset={n}"
        for n in ("comparison_day", "comparison_week", "comparison_month", "partition_quality")
    },
}


EXTRA_TABLES = {
    "dim_tract_acs": "gold/dataset=dim_tract_acs",
    "dim_tract_geo": "gold/dataset=dim_tract_geo",
    "rate_tract": "serving/dataset=rate_tract",
    "source_change": "silver/dataset=source_change",
}


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def load(con, root):
    manifests = {}
    tables = {**TABLES, **{n: p for n, p in EXTRA_TABLES.items() if (Path(root) / p).exists()}}
    for name, rel in tables.items():
        folder = Path(root) / rel
        manifests[name] = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if str(manifests[name].get("status", "")).lower() not in {"success", "complete"}:
            raise AdminError(f"{name}: unvollstaendiges Manifest")
        con.execute(
            f"CREATE VIEW {name} AS SELECT * FROM read_parquet("
            f"{literal(folder / 'part-0001.parquet')}, hive_partitioning=false)"
        )
        expected = manifests[name].get("row_count")
        actual = con.execute(f"SELECT count(*) FROM {name}").fetchone()[0]
        if expected is not None and actual != expected:
            raise AdminError(f"{name}: Manifest {expected}, Tabelle {actual}")
    gold_times = {
        manifests[n].get("built_at_utc")
        for n in tables
        if n.startswith("dim_") or n == "fact_offense"
    }
    if None in gold_times or len(gold_times) != 1:
        raise AdminError("Gold-Tabellen stammen nicht aus demselben Bau")
    return manifests


def fingerprints(con):
    """Sorted full row values, independent of physical Parquet order and compression."""
    result = {}
    available = {r[0] for r in con.execute("SHOW TABLES").fetchall()}
    for name in sorted((TABLES.keys() | EXTRA_TABLES.keys()) & available):
        h = hashlib.sha256()
        schema = con.execute(f"DESCRIBE {name}").fetchall()
        h.update(json.dumps(schema, default=str).encode())
        cursor = con.execute(f"SELECT to_json(t) FROM {name} t ORDER BY to_json(t)")
        count = 0
        while batch := cursor.fetchmany(1000):
            for (value,) in batch:
                h.update(value.encode())
                h.update(b"\n")
                count += 1
        result[name] = {"rows": count, "sha256": h.hexdigest()}
    return result


def period_column(con, table, period):
    """Published Serving uses date/week_start/month; older test fixtures used period_start."""
    columns = {r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()}
    actual = {"day": "date", "week": "week_start", "month": "month"}[period]
    if actual in columns:
        return actual
    if "period_start" in columns:
        return "period_start"
    raise AdminError(f"{table}: Zeitraumspalte fehlt")


def assess(con, settings):
    """Check keys, exact Silver->Gold membership, local date and aggregates per cell."""
    findings = {}
    queries = {
        "silver_identity": "SELECT city,offense_id FROM silver_crime GROUP BY 1,2 HAVING count(*)<>1 OR offense_id IS NULL OR trim(offense_id)=''",
        "gold_identity": "SELECT reporting_city,offense_id FROM fact_offense GROUP BY 1,2 HAVING count(*)<>1 OR offense_id IS NULL OR trim(offense_id)=''",
        "count_flags": "SELECT city,offense_id FROM silver_crime WHERE counts IS NULL OR counts_case IS NULL OR (counts_case AND NOT counts)",
        "report_representatives": "SELECT city,coalesce(event_id,offense_id) FROM silver_crime GROUP BY 1,2 HAVING count(*) FILTER(WHERE counts)>0 AND count(*) FILTER(WHERE counts_case)<>1",
        "local_date": "SELECT city,offense_id FROM silver_crime WHERE occurred_at_local IS NULL OR occurred_date_local IS DISTINCT FROM CAST(occurred_at_local AS DATE)",
        "scope": f"SELECT city,offense_id FROM silver_crime WHERE occurred_date_local < DATE {literal(settings['scope_start'])} OR occurred_date_local >= DATE {literal(settings['scope_end_exclusive'])}",
    }
    for table, city_column in [("silver_crime", "city"), ("fact_offense", "reporting_city")]:
        queries[table + "_cities"] = f"""(SELECT city FROM (VALUES ('chicago'),('detroit')) t(city)
            EXCEPT SELECT {city_column} FROM {table}) UNION ALL
            (SELECT DISTINCT {city_column} FROM {table}
             WHERE {city_column} IS NULL OR {city_column} NOT IN ('chicago','detroit'))"""
    # Compare content, not merely city totals. EXCEPT ALL also detects multiplicity.
    expected = "SELECT city,offense_id,event_id,nibrs_code,occurred_date_local,counts_case FROM silver_crime WHERE counts"
    actual = (
        "SELECT reporting_city,offense_id,event_id,nibrs_code,date,counts_case FROM fact_offense"
    )
    queries["silver_gold_membership"] = (
        f"({expected} EXCEPT ALL {actual}) UNION ALL ({actual} EXCEPT ALL {expected})"
    )
    for name, key in [
        ("dim_offense", "nibrs_code"),
        ("dim_date", "date"),
        ("dim_tract", "geoid"),
        ("dim_city_day", "city,date"),
    ]:
        queries[name + "_key"] = f"SELECT {key} FROM {name} GROUP BY ALL HAVING count(*)<>1"
    for name, col, foreign in [
        ("dim_offense", "nibrs_code", "nibrs_code"),
        ("dim_date", "date", "date"),
        ("dim_tract", "geoid", "tract_geoid"),
    ]:
        queries[name + "_orphans"] = (
            f"SELECT f.offense_id FROM fact_offense f LEFT JOIN {name} d ON d.{col}=f.{foreign} WHERE f.{foreign} IS NOT NULL AND d.{col} IS NULL"
        )
    for period in ("day", "week", "month"):
        expected = f"""SELECT f.reporting_city,CAST(date_trunc('{period}', f.date) AS DATE),
            CASE WHEN f.nibrs_code IS NULL THEN 'unmapped' ELSE d.nibrs_category END,
            f.nibrs_family, count(*), count(*) FILTER(WHERE f.counts_case)
            FROM fact_offense f LEFT JOIN dim_offense d USING(nibrs_code) GROUP BY 1,2,3,4"""
        actual = f"SELECT reporting_city,{period_column(con, 'comparison_' + period, period)},nibrs_category,nibrs_family,offenses,cases FROM comparison_{period}"
        queries["aggregate_" + period] = (
            f"({expected} EXCEPT ALL {actual}) UNION ALL ({actual} EXCEPT ALL {expected})"
        )
    for name, query in queries.items():
        n = con.execute(f"SELECT count(*) FROM ({query}) q").fetchone()[0]
        findings[name] = n
    ratios = con.execute("""SELECT city, CAST(occurred_date_local AS VARCHAR),
        count(*), count(*) FILTER(WHERE mapping_status='unmapped' OR nibrs_code IS NULL),
        count(DISTINCT event_id) FILTER(WHERE mapping_status='unmapped' OR nibrs_code IS NULL)
        FROM silver_crime GROUP BY 1,2 ORDER BY 1,2""").fetchall()
    held = [
        {"city": c, "date": d, "offenses": n, "unmapped": u, "affected_reports": r}
        for c, d, n, u, r in ratios
        if u / n > settings["maximum_unmapped_ratio"]
    ]
    return {
        "checks": findings,
        "held_city_days": held,
        "technical_ok": not any(findings.values()),
        "quality_ok": not held,
    }


def evaluate(root, settings=None, before=None, expect_identical=False):
    con = verbinde()
    try:
        manifests = load(con, root)
        result = assess(con, settings or DEFAULT_SETTINGS)
        result["tables"] = fingerprints(con)
        result["checked_at_utc"] = now()
        result["input_manifests"] = manifests
        result["changed_tables"] = (
            []
            if before is None
            else [name for name in before["tables"].keys() | result["tables"].keys()
                  if before["tables"].get(name) != result["tables"].get(name)]
        )
        if expect_identical and before is None:
            raise AdminError("Replay verlangt einen Vorher-Snapshot")
        result["replay_ok"] = not expect_identical or not result["changed_tables"]
        result["ok"] = result["technical_ok"] and result["quality_ok"] and result["replay_ok"]
        result["metric"] = "Main: offenses=counted Gold rows; cases=counts_case representatives"
        return result
    finally:
        con.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--before", type=Path)
    p.add_argument("--expect-identical", action="store_true")
    args = p.parse_args()
    before = json.loads(args.before.read_text()) if args.before else None
    result = evaluate(for_root(args.data_root).local_root, before=before, expect_identical=args.expect_identical)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("ok", "checks", "changed_tables")}, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
