"""Source-backed semantic deltas. SQL compares identities and every stable field.

Counts preserve Main's metric: Silver contains allegations, counts marks offenses,
counts_case marks report representatives. Legacy Gold-only baselines are labelled.
Complete details are in Parquet; JSON previews are deliberately bounded.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from storage.duckdb import verbinde

from .store import AdminError, rows
from .checks import literal

FIELDS = {
    "city": "VARCHAR",
    "offense_id": "VARCHAR",
    "event_id": "VARCHAR",
    "occurred_at_utc": "TIMESTAMP",
    "occurred_at_local": "TIMESTAMP",
    "occurred_date_local": "DATE",
    "local_time_nonexistent": "BOOLEAN",
    "local_time_ambiguous": "BOOLEAN",
    "source_offense_code": "VARCHAR",
    "source_offense_description": "VARCHAR",
    "nibrs_code": "VARCHAR",
    "nibrs_description": "VARCHAR",
    "nibrs_group": "VARCHAR",
    "crime_against": "VARCHAR",
    "nibrs_match": "VARCHAR",
    "nibrs_mapped": "BOOLEAN",
    "mapping_status": "VARCHAR",
    "latitude": "DOUBLE",
    "longitude": "DOUBLE",
    "tract_geoid": "VARCHAR",
    "located": "BOOLEAN",
    "arrest": "BOOLEAN",
    "unfounded": "BOOLEAN",
    "offense_group_id": "VARCHAR",
    "counts": "BOOLEAN",
    "counts_reason": "VARCHAR",
    "counts_case": "BOOLEAN",
    "nibrs_category": "VARCHAR",
}


def query_rows(con, sql, limit=None):
    cur = con.execute(sql + (f" LIMIT {int(limit)}" if limit is not None else ""))
    names = [c[0] for c in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def table_hash(con, schema):
    h = hashlib.sha256(json.dumps(schema, default=str).encode())
    for batch in iter(lambda: con.fetchmany(1000), []):
        for (row,) in batch:
            h.update(row.encode())
            h.update(b"\n")
    return h.hexdigest()


def load_side(con, root, side, gold_only=False):
    root = Path(root)
    silver = root / "silver" / "dataset=crime_offense" / "part-0001.parquet"
    source = (
        silver
        if silver.exists() and not gold_only
        else root / "gold" / "dataset=fact_offense" / "part-0001.parquet"
    )
    con.execute(
        f"CREATE VIEW raw_{side} AS SELECT * FROM read_parquet({literal(source)},hive_partitioning=false)"
    )
    raw_fields = {r[0] for r in con.execute(f"DESCRIBE raw_{side}").fetchall()}
    dim = root / "gold" / "dataset=dim_offense" / "part-0001.parquet"
    con.execute(
        f"CREATE TABLE dim_{side} AS SELECT * FROM read_parquet({literal(dim)},hive_partitioning=false)"
    )
    if con.execute(
        f"SELECT count(*) FROM (SELECT nibrs_code FROM dim_{side} GROUP BY 1 HAVING count(*)>1)"
    ).fetchone()[0]:
        raise AdminError("Doppelte NIBRS-Dimension verhindert eindeutigen Impact-Vergleich")
    aliases = {"city": "reporting_city", "occurred_date_local": "date"}
    expressions, available = [], set()
    for field, typ in FIELDS.items():
        col = field if field in raw_fields else aliases.get(field)
        if field == "nibrs_category":
            expr = "CASE WHEN r.nibrs_code IS NULL THEN 'unmapped' ELSE d.nibrs_category END"
            available.add(field)
        elif col in raw_fields:
            expr = f'r."{col}"'
            available.add(field)
        elif field == "counts" and source != silver:
            expr = "TRUE"
            available.add(field)
        else:
            expr = "NULL"
        expressions.append(f'CAST({expr} AS {typ}) AS "{field}"')
    con.execute(
        f"CREATE TABLE {side} AS SELECT "
        + ",".join(expressions)
        + f" FROM raw_{side} r LEFT JOIN dim_{side} d USING(nibrs_code)"
    )
    if con.execute(
        f"SELECT count(*) FROM (SELECT city,offense_id FROM {side} GROUP BY 1,2 HAVING count(*)<>1 OR city IS NULL OR offense_id IS NULL OR trim(offense_id)='')"
    ).fetchone()[0]:
        raise AdminError("Ungueltige oder doppelte offense_id im Impact-Vergleich")
    return available


def mapping_changes(metadata):
    before = metadata["mapping_before"]["payload"]
    after = metadata["mapping_after"]["payload"]
    changes = []
    for city, name, key in [
        ("chicago", "iucr_nibrs_mapping.csv", "iucr"),
        ("detroit", "micr_nibrs_mapping.csv", "micr_code"),
    ]:
        old = {r[key]: r for r in rows(before[name])[1]}
        new = {r[key]: r for r in rows(after[name])[1]}
        for code in sorted(old.keys() | new.keys()):
            if old.get(code) != new.get(code):
                changes.append(
                    {
                        "city": city,
                        "source_code": code,
                        "before": old.get(code),
                        "after": new.get(code),
                    }
                )
    return changes


def compare(baseline, candidate, output, metadata, before_quality, after_quality):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    con = verbinde()
    try:
        legacy = bool(
            baseline
            and not (
                Path(baseline) / "silver" / "dataset=crime_offense" / "part-0001.parquet"
            ).exists()
        )
        available_after = load_side(con, candidate, "after", gold_only=legacy)
        if baseline:
            available_before = load_side(con, baseline, "before", gold_only=legacy)
        else:
            con.execute("CREATE TABLE before AS SELECT * FROM after WHERE FALSE")
            available_before = available_after
        comparable = sorted(available_before & available_after - {"city", "offense_id"})
        fields = ",".join(
            f'CASE WHEN b."{f}" IS DISTINCT FROM a."{f}" THEN {literal(f)} END' for f in comparable
        )
        changed = " OR ".join(f'b."{f}" IS DISTINCT FROM a."{f}"' for f in comparable)
        con.execute(f"""CREATE TABLE differences AS
            SELECT coalesce(b.city,a.city) AS city,coalesce(b.offense_id,a.offense_id) AS offense_id,
                CASE WHEN b.offense_id IS NULL THEN 'added' WHEN a.offense_id IS NULL THEN 'removed'
                     ELSE 'updated' END AS change_type,
                b.occurred_date_local AS date_before,a.occurred_date_local AS date_after,
                b.source_offense_code AS source_code_before,a.source_offense_code AS source_code_after,
                b.nibrs_code AS nibrs_before,a.nibrs_code AS nibrs_after,
                b.nibrs_category AS category_before,a.nibrs_category AS category_after,
                b.mapping_status AS mapping_before,a.mapping_status AS mapping_after,
                b.counts AS counts_before,a.counts AS counts_after,
                b.counts_case AS counts_case_before,a.counts_case AS counts_case_after,
                CASE WHEN b.offense_id IS NOT NULL AND a.offense_id IS NOT NULL
                     THEN list_filter([{fields}], x -> x IS NOT NULL) ELSE []::VARCHAR[] END AS changed_fields,
                CASE WHEN b.offense_id IS NOT NULL THEN to_json(b) END AS before_json,
                CASE WHEN a.offense_id IS NOT NULL THEN to_json(a) END AS after_json
            FROM before b FULL OUTER JOIN after a USING(city,offense_id)
            WHERE b.offense_id IS NULL OR a.offense_id IS NULL OR ({changed})""")
        con.execute(
            f"COPY (SELECT * FROM differences ORDER BY city,offense_id) TO {literal(output / 'impact_records.parquet')} (FORMAT PARQUET)"
        )
        kinds = dict(
            con.execute("SELECT change_type,count(*) FROM differences GROUP BY 1").fetchall()
        )
        changes_by_field = dict(
            con.execute(
                "SELECT field,count(*) FROM differences,unnest(changed_fields) t(field) GROUP BY 1"
            ).fetchall()
        )
        totals = {}
        for side in ("before", "after"):
            row = con.execute(
                f"SELECT count(*),count(*) FILTER(WHERE counts),count(*) FILTER(WHERE counts_case) FROM {side}"
            ).fetchone()
            totals[side] = {"records": row[0], "offenses": row[1], "cases": row[2]}
        summary = {
            "added": kinds.get("added", 0),
            "removed": kinds.get("removed", 0),
            "updated": kinds.get("updated", 0),
            "affected_records": sum(kinds.values()),
            "net_records": totals["after"]["records"] - totals["before"]["records"],
            "before": totals["before"],
            "after": totals["after"],
            "delta": {k: totals["after"][k] - totals["before"][k] for k in totals["after"]},
            "field_changes": changes_by_field,
        }
        transitions = query_rows(
            con,
            """SELECT city,nibrs_before,nibrs_after,category_before,category_after,count(*) AS records
            FROM differences WHERE change_type='updated' AND
            (nibrs_before IS DISTINCT FROM nibrs_after OR category_before IS DISTINCT FROM category_after)
            GROUP BY 1,2,3,4,5 ORDER BY 1,2,3""",
        )
        mapping_transitions = query_rows(
            con,
            """SELECT city,mapping_before,mapping_after,count(*) AS records
            FROM differences WHERE change_type='updated' AND mapping_before IS DISTINCT FROM mapping_after
            GROUP BY 1,2,3 ORDER BY 1,2,3""",
        )
        partitions = []
        changed_tables = []
        for period in ("day", "week", "month"):
            table = "comparison_" + period
            for side, root in [("before", baseline), ("after", candidate)]:
                if root:
                    path = Path(root) / "serving" / f"dataset={table}" / "part-0001.parquet"
                    con.execute(
                        f"CREATE TABLE {table}_{side} AS SELECT * FROM read_parquet({literal(path)},hive_partitioning=false)"
                    )
                else:
                    path = Path(candidate) / "serving" / f"dataset={table}" / "part-0001.parquet"
                    con.execute(
                        f"CREATE TABLE {table}_{side} AS SELECT * FROM read_parquet({literal(path)},hive_partitioning=false) WHERE FALSE"
                    )
            from .checks import period_column

            for side in ("before", "after"):
                start = period_column(con, f"{table}_{side}", period)
                if start != "period_start":
                    con.execute(f'ALTER TABLE {table}_{side} RENAME "{start}" TO period_start')
            # NULL-safe keys are essential for unmapped categories/families.
            keys = ("reporting_city", "period_start", "nibrs_category", "nibrs_family")
            join = " AND ".join(f"b.{k} IS NOT DISTINCT FROM a.{k}" for k in keys)
            extra = ",".join(f"coalesce(a.{k},b.{k}) AS {k}" for k in keys)
            con.execute(f"""CREATE TABLE delta_{period} AS SELECT {literal(period)} AS period,{extra},
                coalesce(b.offenses,0) AS offenses_before,coalesce(a.offenses,0) AS offenses_after,
                coalesce(a.offenses,0)-coalesce(b.offenses,0) AS offenses_delta,
                coalesce(b.cases,0) AS cases_before,coalesce(a.cases,0) AS cases_after,
                coalesce(a.cases,0)-coalesce(b.cases,0) AS cases_delta
                FROM {table}_before b FULL OUTER JOIN {table}_after a ON {join}
                WHERE b.offenses IS DISTINCT FROM a.offenses OR b.cases IS DISTINCT FROM a.cases""")
            partitions.append(f"SELECT * FROM delta_{period}")
        con.execute("CREATE TABLE partition_delta AS " + " UNION ALL ".join(partitions))
        con.execute(
            f"COPY (SELECT * FROM partition_delta ORDER BY period,reporting_city,period_start,nibrs_category,nibrs_family) TO {literal(output / 'impact_by_partition.parquet')} (FORMAT PARQUET)"
        )
        quality_sql = []
        for side in ("before", "after"):
            con.execute(f"""CREATE TABLE gate_{side} AS SELECT city,occurred_date_local AS date,
                count(*) AS records, count(*) FILTER(WHERE counts) AS offenses,
                count(*) FILTER(WHERE counts_case) AS cases,
                count(*) FILTER(WHERE mapping_status='exact') AS exact,
                count(*) FILTER(WHERE mapping_status='ambiguous') AS ambiguous,
                count(*) FILTER(WHERE mapping_status='fallback_90Z') AS fallback_90z,
                count(*) FILTER(WHERE mapping_status='unmapped' OR nibrs_code IS NULL) AS unmapped
                FROM {side} GROUP BY 1,2""")
        metrics = ["records", "offenses", "cases", "exact", "ambiguous", "fallback_90z", "unmapped"]
        expr = []
        for m in metrics:
            expr.extend(
                [
                    f"coalesce(b.{m},0) AS {m}_before",
                    f"coalesce(a.{m},0) AS {m}_after",
                    f"coalesce(a.{m},0)-coalesce(b.{m},0) AS {m}_delta",
                ]
            )
        old_threshold = metadata["settings_before"]["payload"]["maximum_unmapped_ratio"]
        new_threshold = metadata["settings_after"]["payload"]["maximum_unmapped_ratio"]
        for m in ("exact", "ambiguous", "fallback_90z", "unmapped"):
            expr.extend(
                [
                    f"100.0*b.{m}/nullif(b.records,0) AS {m}_percent_before",
                    f"100.0*a.{m}/nullif(a.records,0) AS {m}_percent_after",
                    f"100.0*a.{m}/nullif(a.records,0)-100.0*b.{m}/nullif(b.records,0) AS {m}_percentage_points",
                ]
            )
        expr.extend(
            [
                f"b.unmapped*1.0/nullif(b.records,0)>{old_threshold} AS held_before",
                f"a.unmapped*1.0/nullif(a.records,0)>{new_threshold} AS held_after",
            ]
        )
        quality_sql.append(
            "SELECT coalesce(b.city,a.city) AS city,coalesce(b.date,a.date) AS date,"
            + ",".join(expr)
            + " FROM gate_before b FULL OUTER JOIN gate_after a ON b.city=a.city AND b.date IS NOT DISTINCT FROM a.date"
        )
        con.execute("CREATE TABLE quality_delta AS " + quality_sql[0])
        con.execute(
            f"COPY (SELECT * FROM quality_delta ORDER BY city,date) TO {literal(output / 'impact_quality.parquet')} (FORMAT PARQUET)"
        )
        for side, root in [("before", baseline), ("after", candidate)]:
            path = (
                Path(root or candidate)
                / "serving"
                / "dataset=partition_quality"
                / "part-0001.parquet"
            )
            con.execute(
                f"CREATE TABLE monthly_{side} AS SELECT * FROM read_parquet({literal(path)},hive_partitioning=false)"
                + (" WHERE FALSE" if root is None else "")
            )
        monthly_fields = [
            r[0]
            for r in con.execute("DESCRIBE monthly_after").fetchall()
            if r[0] not in {"reporting_city", "month"}
        ]
        monthly_queries = []
        for field in monthly_fields:
            monthly_queries.append(f"""SELECT coalesce(b.reporting_city,a.reporting_city) AS city,
                coalesce(b.month,a.month) AS month, {literal(field)} AS metric,
                CAST(b.{field} AS DOUBLE) AS value_before,CAST(a.{field} AS DOUBLE) AS value_after,
                CAST(a.{field} AS DOUBLE)-CAST(b.{field} AS DOUBLE) AS delta
                FROM monthly_before b FULL OUTER JOIN monthly_after a
                ON b.reporting_city=a.reporting_city AND b.month IS NOT DISTINCT FROM a.month""")
        con.execute("CREATE TABLE monthly_quality_delta AS " + " UNION ALL ".join(monthly_queries))
        con.execute(
            f"COPY (SELECT * FROM monthly_quality_delta ORDER BY city,month,metric) TO {literal(output / 'impact_quality_month.parquet')} (FORMAT PARQUET)"
        )
        quality_totals = {}
        for side in ("before", "after"):
            quality_totals[side] = query_rows(
                con,
                f"""SELECT city,sum(records) AS records,sum(offenses) AS offenses,sum(cases) AS cases,
                100.0*sum(exact)/nullif(sum(records),0) AS exact_percent,
                100.0*sum(ambiguous)/nullif(sum(records),0) AS ambiguous_percent,
                100.0*sum(fallback_90z)/nullif(sum(records),0) AS fallback_90z_percent,
                100.0*sum(unmapped)/nullif(sum(records),0) AS unmapped_percent FROM gate_{side} GROUP BY 1 ORDER BY 1""",
            )
        # Compare full logical contents of published Gold/Serving tables, including
        # denominator/dimension changes that do not alter offense membership.
        for rel in sorted(Path(candidate).glob("*/dataset=*/part-0001.parquet")):
            if rel.parent.parent.name not in {"gold", "serving"}:
                continue
            relative = rel.relative_to(candidate)
            old = Path(baseline) / relative if baseline else None

            def fingerprint(path):
                schema = con.execute(
                    f"DESCRIBE SELECT * FROM read_parquet({literal(path)},hive_partitioning=false)"
                ).fetchall()
                con.execute(
                    f"SELECT to_json(t) FROM read_parquet({literal(path)},hive_partitioning=false) t ORDER BY to_json(t)"
                )
                return table_hash(con, schema)

            if old is None or not old.exists() or fingerprint(old) != fingerprint(rel):
                changed_tables.append(relative.parent.as_posix())
        coverage = query_rows(
            con,
            """SELECT city,min(date) AS date_start,max(date) AS date_end FROM
            (SELECT city,date_before AS date FROM differences UNION ALL SELECT city,date_after FROM differences)
            GROUP BY 1 ORDER BY 1""",
        )
        source_codes = query_rows(
            con,
            """SELECT city,source_code,count(DISTINCT offense_id) AS records FROM
            (SELECT city,offense_id,source_code_before AS source_code FROM differences
             UNION ALL SELECT city,offense_id,source_code_after FROM differences)
            WHERE source_code IS NOT NULL GROUP BY 1,2 ORDER BY 1,2""",
        )
        partition_count = con.execute("SELECT count(*) FROM partition_delta").fetchone()[0]
        affected_counted = con.execute(
            "SELECT count(*) FROM differences WHERE coalesce(counts_before,FALSE) OR coalesce(counts_after,FALSE)"
        ).fetchone()[0]
        summary["affected_offenses"] = affected_counted
        summary["partition_cells_changed"] = partition_count
        if baseline is None:
            text = f"Erster Kandidatenstand: {totals['after']['offenses']} Delikte und {totals['after']['cases']} Faelle. Kein freigegebener Baseline-Release vorhanden."
        else:
            text = f"Diese Revision betrifft {affected_counted} gezaehlte Delikte ({summary['affected_records']} Datensaetze): +{summary['added']} neu, -{summary['removed']} entfallen, {summary['updated']} inhaltlich geaendert. Deliktdifferenz {summary['delta']['offenses']:+d}; Falldifferenz {summary['delta']['cases']:+d}."
        text += (
            " Alle Quality Gates bestanden."
            if after_quality["ok"]
            else " Quality Gates nicht bestanden; Freigabe gesperrt."
        )
        return {
            "schema_version": 1,
            "metadata": metadata,
            "summary": summary,
            "summary_text": text,
            "comparison_scope": "bootstrap"
            if baseline is None
            else "legacy_gold_only"
            if legacy
            else "full_silver",
            "limitations": (
                [
                    "Baseline enthaelt kein Silver: nur gezaehlte Gold-Delikte vergleichbar; Anklagen und Silver-exklusive Felder nicht vollstaendig vergleichbar."
                ]
                if legacy
                else []
            )
            + (
                [
                    "Baseline-Konfiguration ohne Release-Audit: fruehere Settings/Mapping nur aus Kontrollstand; keine gesicherte historische Gate-Schwelle."
                ]
                if metadata.get("baseline_config_provenance")
                == "control_heads_no_release_config_proof"
                else []
            ),
            "compared_fields": comparable,
            "not_compared_fields": sorted(set(FIELDS) - set(comparable) - {"city", "offense_id"}),
            "mapping_changes": mapping_changes(metadata),
            "affected_source_codes": source_codes,
            "affected_city_periods": coverage,
            "category_transitions": transitions,
            "mapping_quality_transitions": mapping_transitions,
            "quality_before": before_quality,
            "quality_after": after_quality,
            "quality_totals": quality_totals,
            "quality_monthly_preview": query_rows(
                con, "SELECT * FROM monthly_quality_delta ORDER BY city,month,metric", 150
            ),
            "quality_thresholds": {"before": old_threshold, "after": new_threshold},
            "partition_preview": query_rows(
                con,
                "SELECT * FROM partition_delta ORDER BY period,reporting_city,period_start,nibrs_category",
                100,
            ),
            "quality_preview": query_rows(
                con, "SELECT * FROM quality_delta ORDER BY city,date", 100
            ),
            "record_preview": query_rows(
                con, "SELECT * FROM differences ORDER BY city,offense_id", 25
            ),
            "preview_limits": {
                "partitions": 100,
                "quality_city_days": 100,
                "records": 25,
                "monthly_quality_metrics": 150,
            },
            "changed_tables": changed_tables,
            "artifacts": {
                "records": "impact_records.parquet",
                "partition_delta": "impact_by_partition.parquet",
                "quality_delta": "impact_quality.parquet",
                "monthly_quality_delta": "impact_quality_month.parquet",
            },
        }
    finally:
        con.close()
