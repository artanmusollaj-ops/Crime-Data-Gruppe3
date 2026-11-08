"""Network-free genuine SQL/Parquet fixtures for candidate and audit tests."""

import json
from pathlib import Path

import duckdb

from platform_admin.checks import TABLES, literal
from serving.build_comparison import QUALITAET_QUERY, zeitraum_query

PROJECT = Path(__file__).resolve().parents[2]


def datasets(root, changes=None):
    """Build complete, small Silver/Gold/Serving datasets without Spatial."""
    root = Path(root)
    con = duckdb.connect()
    try:
        con.execute("""CREATE TABLE silver_crime AS SELECT * FROM (VALUES
            ('chicago','C1','C1',TIMESTAMP '2024-06-01 14:00:00',DATE '2024-06-01','0110','09A','exact','17031010100',TRUE,TRUE),
            ('chicago','C2','C2',TIMESTAMP '2024-06-02 14:00:00',DATE '2024-06-02','0910','240','exact','17031010100',TRUE,TRUE),
            ('detroit','D1','D1',TIMESTAMP '2024-06-01 14:00:00',DATE '2024-06-01','2403','90Z','fallback_90Z','26163500100',TRUE,TRUE))
            t(city,offense_id,event_id,occurred_at_local,occurred_date_local,source_offense_code,nibrs_code,mapping_status,tract_geoid,counts,counts_case)""")
        con.execute(
            "ALTER TABLE silver_crime ADD COLUMN source_offense_description VARCHAR DEFAULT 'TEST'"
        )
        con.execute("ALTER TABLE silver_crime ADD COLUMN occurred_at_utc TIMESTAMP")
        con.execute("UPDATE silver_crime SET occurred_at_utc=occurred_at_local")
        con.execute(
            "ALTER TABLE silver_crime ADD COLUMN local_time_ambiguous BOOLEAN DEFAULT FALSE"
        )
        con.execute(
            "ALTER TABLE silver_crime ADD COLUMN local_time_nonexistent BOOLEAN DEFAULT FALSE"
        )
        con.execute("ALTER TABLE silver_crime ADD COLUMN latitude DOUBLE DEFAULT 1.0")
        con.execute("ALTER TABLE silver_crime ADD COLUMN longitude DOUBLE DEFAULT 1.0")
        con.execute("ALTER TABLE silver_crime ADD COLUMN arrest BOOLEAN DEFAULT FALSE")
        if changes:
            changes(con)
        config = PROJECT / "config"
        con.execute(f"""CREATE TABLE dim_offense AS SELECT c.nibrs_code,c.nibrs_description,k.nibrs_category,left(c.nibrs_code,2) AS nibrs_family
            FROM read_csv({literal(config / "nibrs_offense_codes_2025.csv")},all_varchar=true) c
            JOIN read_csv({literal(config / "nibrs_offense_categories_2025.csv")},all_varchar=true) k USING(nibrs_code)""")
        con.execute(
            "CREATE TABLE dim_date AS SELECT DISTINCT occurred_date_local AS date FROM silver_crime"
        )
        con.execute(
            "CREATE TABLE dim_tract AS SELECT DISTINCT tract_geoid AS geoid FROM silver_crime"
        )
        con.execute(
            "CREATE TABLE dim_city_day AS SELECT DISTINCT city,occurred_date_local AS date FROM silver_crime"
        )
        con.execute("""CREATE TABLE fact_offense AS SELECT city AS reporting_city,offense_id,event_id,occurred_at_local,occurred_at_utc,occurred_date_local AS date,
            source_offense_code,source_offense_description,nibrs_code,left(nibrs_code,2) AS nibrs_family,mapping_status,tract_geoid,counts_case,
            latitude,longitude,arrest,local_time_ambiguous,'inside_city' AS geo_status FROM silver_crime WHERE counts""")
        con.execute("""CREATE TABLE basis AS SELECT f.*,CASE WHEN f.nibrs_code IS NULL THEN 'unmapped' ELSE d.nibrs_category END AS nibrs_category
                       FROM fact_offense f LEFT JOIN dim_offense d USING(nibrs_code)""")
        for period in ("day", "week", "month"):
            con.execute(
                f"CREATE TABLE comparison_{period} AS "
                + zeitraum_query(f"date_trunc('{period}',date)::DATE")
            )
        con.execute("ALTER TABLE comparison_day RENAME period_start TO date")
        con.execute("ALTER TABLE comparison_week RENAME period_start TO week_start")
        con.execute("ALTER TABLE comparison_month RENAME period_start TO month")
        con.execute("CREATE TABLE partition_quality AS " + QUALITAET_QUERY)
        for name, rel in TABLES.items():
            folder = root / rel
            folder.mkdir(parents=True, exist_ok=True)
            con.execute(f"COPY {name} TO {literal(folder / 'part-0001.parquet')} (FORMAT PARQUET)")
            (folder / "manifest.json").write_text(
                json.dumps(
                    {
                        "status": "complete",
                        "row_count": con.execute(f"SELECT count(*) FROM {name}").fetchone()[0],
                        "built_at_utc": "2026-10-02T12:00:00Z",
                        "contract_version": 1,
                    }
                ),
                encoding="utf-8",
            )
    finally:
        con.close()
    return root


def bronze(root):
    path = Path(root) / "bronze" / "city=chicago" / "ingest_date=2026-10-02" / "run_test"
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text('{"status":"complete"}', encoding="utf-8")
    (path / "source.json").write_text('{"immutable":"snapshot"}', encoding="utf-8")


def synthetic_runner(changes=None):
    def run(work, commands, log):
        assert len(commands) == 10
        assert any(c[2] == 'silver_pipeline.build_source_change' for c in commands)
        assert all(str(work.data) in c for c in commands)
        datasets(work.data, changes)
        log.write("Synthetic local SQL fixture build\n")

    return run


def approve(store, rid, actor="Christian", changes=None):
    from platform_admin.jobs import run_one

    bronze(store.data)
    wanted = next(i["id"] for i in store.history()["impacts"] if i["revision_id"] == rid)
    while True:
        result = run_one(store, runner=synthetic_runner(changes))
        assert result is not None
        assert result["status"] == "AWAITING_REVIEW", result
        if result["id"] == wanted:
            break
    row = next(
        i for i in store.history()["impacts"] if i["revision_id"] == rid and i["id"] == result["id"]
    )
    store.decide(
        rid,
        "approve",
        actor,
        "Synthetic test review",
        impact_id=row["id"],
        report_hash=row["report_hash"],
    )
    return row
