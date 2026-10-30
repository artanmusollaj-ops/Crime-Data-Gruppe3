"""Execute production SQL against synthetic Parquet, including corrupt results."""

import json
from datetime import date
from pathlib import Path

import duckdb
import pytest

from platform_admin.checks import TABLES, assess, evaluate, fingerprints
from platform_admin import jobs, candidates
from tests.platform_admin.helpers import bronze
from platform_admin.store import DEFAULT_SETTINGS, Store
from gold_pipeline import build_gold as gold
from serving import build_comparison as comparison
from tests.gold_pipeline.test_build_gold import baue


def derive_comparisons(con):
    con.execute("""CREATE OR REPLACE TABLE basis AS SELECT f.reporting_city, f.date,
        f.counts_case,f.mapping_status,f.geo_status,f.local_time_ambiguous,
        CASE WHEN f.nibrs_code IS NULL THEN 'unmapped' ELSE d.nibrs_category END AS nibrs_category,
        f.nibrs_family,f.nibrs_code FROM fact_offense f LEFT JOIN dim_offense d USING(nibrs_code)""")
    for period in ("day", "week", "month"):
        con.execute(
            f"CREATE OR REPLACE TABLE comparison_{period} AS "
            + comparison.zeitraum_query(f"CAST(date_trunc('{period}',date) AS DATE)")
        )
    con.execute("CREATE OR REPLACE TABLE partition_quality AS " + comparison.QUALITAET_QUERY)


def write_tables(con, root):
    for name, rel in TABLES.items():
        folder = root / rel
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / "part-0001.parquet"
        con.execute(f"COPY {name} TO '{target}' (FORMAT PARQUET)")
        (folder / "manifest.json").write_text(
            json.dumps(
                {
                    "status": "complete",
                    "built_at_utc": "2026-09-18T12:00:00Z",
                    "row_count": con.execute(f"SELECT count(*) FROM {name}").fetchone()[0],
                    "contract_version": 1,
                }
            ),
            encoding="utf-8",
        )


@pytest.fixture
def tables(tmp_path):
    con = duckdb.connect()
    con.execute("LOAD spatial")
    offense = baue(
        con,
        tmp_path,
        [
            ("C1", "chicago", date(2024, 6, 1), "13A", "17031010100"),
            ("C2", "chicago", date(2024, 6, 2), "240", "17031010100"),
            ("D1", "detroit", date(2024, 6, 1), "13A", "26163500100"),
        ],
    )
    con.execute(f"CREATE TABLE silver_crime AS SELECT * FROM read_parquet('{offense.pfad}')")
    con.execute("CREATE OR REPLACE TABLE dim_city_day AS SELECT DISTINCT * FROM dim_city_day")
    derive_comparisons(con)
    yield con
    con.close()


def test_exact_replay_parquet_roundtrip(tmp_path, tables):
    root = tmp_path / "data"
    write_tables(tables, root)
    first = evaluate(root)
    assert first["ok"], json.dumps(first, default=str)
    write_tables(tables, root)
    again = evaluate(root, before=first, expect_identical=True)
    assert again["ok"] and not again["changed_tables"]


def test_corrected_date_and_category_recalculate_old_and_new_cells(tmp_path, tables):
    before = fingerprints(tables)
    tables.execute("""UPDATE silver_crime SET nibrs_code='240', occurred_date_local=DATE '2024-07-09',
        occurred_at_local=TIMESTAMP '2024-07-09 14:00:00' WHERE offense_id='D1'""")
    # An existing dim_date built from min/max must be rebuilt after a moved date.
    path = tmp_path / "corrected_silver.parquet"
    tables.execute(f"COPY silver_crime TO '{path}' (FORMAT PARQUET)")
    source = gold.Quelle("crime_offense", path)
    tables.execute("CREATE OR REPLACE TABLE dim_date AS " + gold.dim_date_query(source))
    tables.execute("CREATE OR REPLACE TABLE fact_offense AS " + gold.fact_offense_query(source))
    derive_comparisons(tables)
    result = assess(tables, DEFAULT_SETTINGS)
    assert result["technical_ok"], json.dumps(result)
    assert (
        tables.execute(
            "SELECT offenses FROM comparison_day WHERE reporting_city='detroit' AND period_start=DATE '2024-06-01'"
        ).fetchall()
        == []
    )
    assert (
        tables.execute(
            "SELECT offenses FROM comparison_day WHERE reporting_city='detroit' AND period_start=DATE '2024-07-09'"
        ).fetchone()[0]
        == 1
    )
    root = tmp_path / "data"
    write_tables(tables, root)
    check = evaluate(root, before={"tables": before}, expect_identical=True)
    assert not check["replay_ok"]  # Deliberate correction is NOT an identical replay.
    assert "comparison_month" in check["changed_tables"]
    assert check["tables"]["fact_offense"]["rows"] == 3


@pytest.mark.parametrize("period", ["day", "week", "month"])
def test_opposite_aggregate_errors_do_not_cancel(tables, period):
    tables.execute(
        f"UPDATE comparison_{period} SET offenses=offenses + CASE WHEN reporting_city='detroit' THEN 1 ELSE -1 END WHERE nibrs_family='13'"
    )
    assert assess(tables, DEFAULT_SETTINGS)["checks"]["aggregate_" + period] == 4


def test_duplicate_dimension_detected_even_when_aggregate_rebuilt(tables):
    tables.execute("INSERT INTO dim_offense SELECT * FROM dim_offense WHERE nibrs_code='13A'")
    derive_comparisons(tables)
    result = assess(tables, DEFAULT_SETTINGS)
    assert not result["technical_ok"] and result["checks"]["dim_offense_key"] == 1


def test_silver_gold_same_count_wrong_identity_detected(tables):
    tables.execute("UPDATE fact_offense SET offense_id='WRONG' WHERE offense_id='D1'")
    assert assess(tables, DEFAULT_SETTINGS)["checks"]["silver_gold_membership"] == 2
    tables.execute("DELETE FROM fact_offense WHERE reporting_city='detroit'")
    assert assess(tables, DEFAULT_SETTINGS)["checks"]["fact_offense_cities"] == 1


def test_unmapped_city_day_is_held_not_silently_zeroed(tables):
    tables.execute(
        "UPDATE silver_crime SET nibrs_code=NULL,mapping_status='unmapped' WHERE city='detroit'"
    )
    result = assess(tables, DEFAULT_SETTINGS)
    assert not result["quality_ok"]
    assert result["held_city_days"][0]["unmapped"] == 1


def test_missing_or_mixed_gold_manifest_rejected(tmp_path, tables):
    root = tmp_path / "data"
    write_tables(tables, root)
    path = root / TABLES["dim_date"] / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["built_at_utc"] = "2020-01-01T00:00:00Z"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="demselben Bau"):
        evaluate(root)
    path.unlink()
    with pytest.raises(FileNotFoundError):
        evaluate(root)


def test_local_release_persists_mapping_and_review_audit(tmp_path, tables):
    root = tmp_path / "data"
    write_tables(tables, root)
    store = Store(Path(__file__).resolve().parents[2], root)
    store.initialize("bootstrap")
    bronze(root)
    jid = jobs.enqueue(store, "rebuild", "Artan")

    def copied_build(work, commands, log):
        import shutil

        for layer in ("silver", "gold", "serving"):
            shutil.copytree(root / layer, work.data / layer)

    result = jobs.run_one(store, runner=copied_build)
    assert result["status"] == "AWAITING_REVIEW", result
    impact = next(i for i in store.history()["impacts"] if i["id"] == jid)
    store.decide(
        impact["revision_id"],
        "approve",
        "Christian",
        "Pruefung",
        impact_id=jid,
        report_hash=impact["report_hash"],
    )
    target = candidates.release_path(store, candidates.active_id(store))
    assert (target / "serving" / "analyse.duckdb").exists()
    assert (target / "admin" / "approval.json").exists()
    manifest = json.loads((target / "release.json").read_text())
    assert "admin/approval.json" in manifest["files"]
    assert (root / "releases" / "AKTUELL.json").exists()


def test_gold_offense_group_is_scoped_by_city(tmp_path):
    with duckdb.connect() as con:
        con.execute("LOAD spatial")
        offense = baue(
            con,
            tmp_path,
            [
                ("same", "chicago", date(2024, 6, 1), "13A", "17031010100"),
                ("same", "detroit", date(2024, 6, 1), "13A", "26163500100"),
            ],
        )
        gold.reconcile(con, offense, 2024)
