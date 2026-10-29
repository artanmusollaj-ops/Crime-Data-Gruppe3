"""Semantic deltas and real candidate lifecycle, without fetching source APIs."""

import json
import shutil
import threading
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import duckdb
import pytest

from platform_admin import candidates, jobs
from platform_admin.impact import compare
from platform_admin.store import Store, AdminError
from platform_admin.web import make_server
from tests.platform_admin.helpers import PROJECT, datasets, bronze, synthetic_runner, approve


@pytest.fixture
def store(tmp_path):
    result = Store(PROJECT, tmp_path / "data")
    result.initialize("bootstrap")
    bronze(result.data)
    return result


def mapping_proposal(store, city="detroit", code="2403", target="26A"):
    return store.propose_mapping(
        city,
        code,
        target,
        store.current("mapping")["id"],
        "Artan",
        "Synthetischer fachlicher Beleg",
    )


def bootstrap(store):
    jid = jobs.enqueue(store, "rebuild", "Artan")
    rid = next(i["revision_id"] for i in store.history()["impacts"] if i["id"] == jid)
    return approve(store, rid)


def metadata(store):
    return {
        "mapping_before": store.current("mapping"),
        "mapping_after": store.current("mapping"),
        "settings_before": store.current("settings"),
        "settings_after": store.current("settings"),
    }


def report_for(store, rid):
    row = next(i for i in store.history()["impacts"] if i["revision_id"] == rid)
    return row, json.loads(Path(row["report_path"]).read_text())


def test_category_change_not_new_offense_and_both_partition_cells(store, tmp_path):
    base = datasets(tmp_path / "base")
    after = datasets(
        tmp_path / "after",
        lambda c: c.execute(
            "UPDATE silver_crime SET nibrs_code='26A',mapping_status='ambiguous' WHERE offense_id='D1'"
        ),
    )
    report = compare(base, after, tmp_path / "report", metadata(store), None, {"ok": True})
    assert report["summary"]["added"] == report["summary"]["removed"] == 0
    assert report["summary"]["updated"] == 1
    assert report["summary"]["delta"]["offenses"] == 0
    assert report["category_transitions"][0]["nibrs_before"] == "90Z"
    assert report["category_transitions"][0]["nibrs_after"] == "26A"
    assert report["mapping_quality_transitions"][0]["mapping_after"] == "ambiguous"
    assert report["summary"]["partition_cells_changed"] == 6
    with duckdb.connect() as c:
        rows = c.execute(
            "SELECT period,sum(offenses_delta),sum(abs(offenses_delta)) FROM read_parquet(?) GROUP BY 1",
            [str(tmp_path / "report" / "impact_by_partition.parquet")],
        ).fetchall()
        assert all(net == 0 and moved == 2 for _, net, moved in rows)


def test_added_removed_updated_offenses_and_date_movement(store, tmp_path):
    base = datasets(tmp_path / "base")

    def changes(c):
        c.execute("DELETE FROM silver_crime WHERE offense_id='C2'")
        c.execute(
            "INSERT INTO silver_crime SELECT * REPLACE('D2' AS offense_id,'D2' AS event_id) FROM silver_crime WHERE offense_id='D1'"
        )
        c.execute(
            "UPDATE silver_crime SET occurred_date_local=DATE '2024-07-02',occurred_at_local=TIMESTAMP '2024-07-02 14:00:00',tract_geoid='NEW' WHERE offense_id='D1'"
        )

    after = datasets(tmp_path / "after", changes)
    report = compare(base, after, tmp_path / "report", metadata(store), None, {"ok": True})
    assert (
        report["summary"]["added"] == 1
        and report["summary"]["removed"] == 1
        and report["summary"]["updated"] == 1
    )
    assert report["summary"]["field_changes"]["occurred_date_local"] == 1
    assert report["summary"]["field_changes"]["tract_geoid"] == 1
    assert report["summary"]["net_records"] == 0
    assert report["summary"]["delta"]["cases"] == 0


def test_identity_scoped_by_city_and_full_content_not_order(store, tmp_path):
    def changes(c):
        c.execute(
            "UPDATE silver_crime SET offense_id='same',event_id='same' WHERE offense_id IN ('C1','D1')"
        )

    base = datasets(tmp_path / "base", changes)
    after = datasets(tmp_path / "after", changes)
    report = compare(base, after, tmp_path / "report", metadata(store), None, {"ok": True})
    assert report["summary"]["affected_records"] == 0
    assert report["changed_tables"] == []


def test_counts_case_and_uncounted_allegations_are_separate_metrics(store, tmp_path):
    def charges(c):
        c.execute(
            "INSERT INTO silver_crime SELECT * REPLACE('D-charge' AS offense_id,FALSE AS counts,FALSE AS counts_case) FROM silver_crime WHERE offense_id='D1'"
        )

    base = datasets(tmp_path / "base", charges)

    def change(c):
        charges(c)
        c.execute(
            "UPDATE silver_crime SET source_offense_description='NEW ALLEGATION' WHERE offense_id='D-charge'"
        )
        c.execute("UPDATE silver_crime SET counts_case=FALSE WHERE offense_id='D1'")

    after = datasets(tmp_path / "after", change)
    report = compare(base, after, tmp_path / "report", metadata(store), None, {"ok": True})
    assert report["summary"]["updated"] == 2 and report["summary"]["affected_offenses"] == 1
    assert report["summary"]["delta"]["offenses"] == 0 and report["summary"]["delta"]["cases"] == -1


def test_null_key_aggregate_does_not_appear_twice(store, tmp_path):
    def unmapped(c):
        c.execute(
            "UPDATE silver_crime SET nibrs_code=NULL,mapping_status='unmapped' WHERE offense_id='D1'"
        )

    base = datasets(tmp_path / "base", unmapped)
    after = datasets(tmp_path / "after", unmapped)
    report = compare(base, after, tmp_path / "report", metadata(store), None, {"ok": False})
    assert report["summary"]["partition_cells_changed"] == 0
    assert report["summary"]["affected_records"] == 0


def test_bootstrap_then_full_silver_comparison_and_isolated_approval(store):
    first = bootstrap(store)
    before = candidates.active_id(store)
    original_mapping = store.current("mapping")["id"]
    rid = mapping_proposal(store)
    result = jobs.run_one(
        store,
        runner=synthetic_runner(
            lambda c: c.execute(
                "UPDATE silver_crime SET nibrs_code='26A',mapping_status='ambiguous' WHERE offense_id='D1'"
            )
        ),
    )
    assert result["status"] == "AWAITING_REVIEW"
    row, report = report_for(store, rid)
    assert report["comparison_scope"] == "full_silver"
    assert report["summary"]["updated"] == 1 and report["summary"]["added"] == 0
    assert candidates.active_id(store) == before
    assert store.current("mapping")["id"] == original_mapping
    assert not (store.data / "gold").exists() and not (store.data / "silver").exists()
    store.decide(
        rid,
        "approve",
        "Christian",
        "Bericht geprueft",
        impact_id=row["id"],
        report_hash=row["report_hash"],
    )
    assert store.current("mapping")["id"] == rid
    assert candidates.active_id(store) != before
    published = candidates.release_path(store, candidates.active_id(store))
    audit = json.loads((published / "admin" / "approval.json").read_text())
    assert audit["decisions"][-1]["impact_report_sha256"] == row["report_hash"]
    assert audit["decisions"][-1]["impact_id"] == row["id"]
    assert (published / "silver" / "dataset=crime_offense" / "part-0001.parquet").exists()
    assert (published / "admin" / "impact_records.parquet").read_bytes() == (
        Path(row["candidate_path"]) / "admin" / "impact_records.parquet"
    ).read_bytes()
    assert candidates.verify_release(published)
    assert first["candidate_release_id"]


def test_no_approval_without_impact_or_same_operator_case_variation(store):
    rid = mapping_proposal(store)
    with pytest.raises(AdminError, match="zweite Person"):
        store.decide(rid, "approve", " ARTAN ", "self")
    with pytest.raises(AdminError, match="Berichtshash"):
        store.decide(rid, "approve", "Christian", "no impact")
    assert candidates.active_id(store) is None


@pytest.mark.parametrize("artifact", ["impact_report.json", "impact_records.parquet"])
def test_tampered_evidence_blocks_approval(store, artifact):
    rid = mapping_proposal(store)
    jobs.run_one(store, runner=synthetic_runner())
    row, _ = report_for(store, rid)
    (Path(row["candidate_path"]) / "admin" / artifact).write_bytes(b"corrupt")
    with pytest.raises(AdminError, match="veraendert"):
        store.decide(
            rid,
            "approve",
            "Christian",
            "check",
            impact_id=row["id"],
            report_hash=row["report_hash"],
        )
    assert candidates.active_id(store) is None


def test_quality_failure_persisted_and_cannot_be_approved(store):
    rid = mapping_proposal(store)
    result = jobs.run_one(
        store,
        runner=synthetic_runner(
            lambda c: c.execute(
                "UPDATE silver_crime SET nibrs_code=NULL,mapping_status='unmapped' WHERE offense_id='D1'"
            )
        ),
    )
    assert result["status"] == "REVIEW_REQUIRED"
    row, report = report_for(store, rid)
    assert row["status"] == "BLOCKED" and not report["review_ready"]
    with pytest.raises(AdminError, match="freigabefaehiger"):
        store.decide(
            rid,
            "approve",
            "Christian",
            "check",
            impact_id=row["id"],
            report_hash=row["report_hash"],
        )
    assert (Path(row["report_path"]).parent / "impact_quality.parquet").exists()


def test_failed_attempt_and_retry_history_are_both_retained(store):
    rid = mapping_proposal(store)

    def fail(*_):
        raise RuntimeError("synthetic failure")

    failed = jobs.run_one(store, runner=fail)
    assert failed["status"] == "FAILED"
    iid = store.retry_impact(rid, "Artan")
    assert iid != failed["id"]
    jobs.run_one(store, runner=synthetic_runner())
    attempts = [i for i in store.history()["impacts"] if i["revision_id"] == rid]
    assert len(attempts) == 2 and {i["status"] for i in attempts} == {"FAILED", "READY"}
    assert all((store.root / "jobs" / i["id"] / "result.json").exists() for i in attempts)


def test_stale_baseline_and_counterpart_config_block_old_candidate(store):
    rid = mapping_proposal(store)
    jobs.run_one(store, runner=synthetic_runner())
    old, _ = report_for(store, rid)
    settings = store.current("settings")
    other = store.propose("settings", settings["payload"], settings["id"], "Other", "counterpart")
    approve(store, other)
    with pytest.raises(AdminError, match="Baseline oder Konfiguration"):
        store.decide(
            rid,
            "approve",
            "Christian",
            "stale",
            impact_id=old["id"],
            report_hash=old["report_hash"],
        )
    store.retry_impact(rid, "Artan")
    jobs.run_one(store, runner=synthetic_runner())
    row, _ = report_for(store, rid)
    assert row["id"] != old["id"]
    store.decide(
        rid,
        "approve",
        "Christian",
        "new baseline reviewed",
        impact_id=row["id"],
        report_hash=row["report_hash"],
    )


def test_rejection_cancels_queued_candidate_and_preserves_active_release(store):
    rid = mapping_proposal(store)
    store.decide(rid, "reject", "Christian", "bad mapping")
    assert store.history()["jobs"][0]["status"] == "CANCELLED"
    assert jobs.run_one(store) is None
    assert candidates.active_id(store) is None
    with pytest.raises(AdminError, match="bereits"):
        store.retry_impact(rid, "Artan")


def test_publication_crash_after_decision_is_retryable(store, monkeypatch):
    rid = mapping_proposal(store)
    jobs.run_one(store, runner=synthetic_runner())
    row, _ = report_for(store, rid)
    import storage.release

    original = storage.release.setze_aktuell
    monkeypatch.setattr(
        storage.release,
        "setze_aktuell",
        lambda *_: (_ for _ in ()).throw(OSError("synthetic pointer failure")),
    )
    with pytest.raises(OSError):
        store.decide(
            rid,
            "approve",
            "Christian",
            "review",
            impact_id=row["id"],
            report_hash=row["report_hash"],
        )
    assert store.current("mapping")["id"] == rid
    assert store.history()["impacts"][0]["status"] == "APPROVED_PENDING_PUBLICATION"
    with pytest.raises(AdminError, match="Publikation zuerst"):
        mapping_proposal(store)
    monkeypatch.setattr(storage.release, "setze_aktuell", original)
    with jobs.writer_lock(store):
        candidates.finish_publication(store, row["id"])
    assert candidates.active_id(store)
    assert store.history()["impacts"][0]["status"] == "PUBLISHED"


def test_replay_rejects_deliberate_semantic_change(store):
    bootstrap(store)
    settings = store.current("settings")
    payload = settings["payload"]
    payload["jobs"].append(
        {"name": "replay", "task": "replay", "enabled": False, "at_utc": "09:00"}
    )
    rid = store.propose("settings", payload, settings["id"], "Artan", "add replay")
    approve(store, rid)
    jobs.enqueue(store, "replay", "Artan")
    result = jobs.run_one(
        store,
        runner=synthetic_runner(
            lambda c: c.execute(
                "UPDATE silver_crime SET source_offense_description='changed' WHERE offense_id='D1'"
            )
        ),
    )
    assert result["status"] == "FAILED" and not result["result"]["replay_ok"]


def test_legacy_gold_baseline_is_explicit_not_fabricated_full_comparison(store, tmp_path):
    base = datasets(tmp_path / "base")
    shutil.rmtree(base / "silver")
    after = datasets(tmp_path / "after")
    report = compare(base, after, tmp_path / "report", metadata(store), None, {"ok": True})
    assert report["comparison_scope"] == "legacy_gold_only"
    assert report["limitations"] and report["summary"]["updated"] == 0
    assert "local_time_nonexistent" in report["not_compared_fields"]


def test_chicago_commands_year_lookback_and_full_never_auto_release(store):
    for name, task in [("chicago_daily", "daily_chicago"), ("chicago_full", "full_chicago")]:
        jid = jobs.enqueue(store, name, "Artan")
        job = next(j for j in store.history()["jobs"] if j["id"] == jid)
        cmd = jobs.commands(store, json.loads(job["spec"]), Path("config"))[0]
        assert "chicago_pipeline.download_chicago" in cmd and "--year" in cmd and "2024" in cmd
        assert ("--full" in cmd) == (task == "full_chicago")
        assert "--lookback-days" not in cmd  # Current pipeline owns its 14-day lookback.
        result = jobs.run_one(store, runner=lambda *_: None)
        assert result["status"] == "SUCCEEDED" and candidates.active_id(store) is None


def test_detroit_commands_daily_and_multi_year_full_never_auto_release(store):
    settings = store.current("settings")
    full = next(job for job in settings["payload"]["jobs"] if job["name"] == "detroit_full")
    full["years"] = [2023, 2024]
    rid = store.propose(
        "settings", settings["payload"], settings["id"], "Artan", "Detroit Full konfigurieren"
    )
    approve(store, rid)
    active_before_imports = candidates.active_id(store)

    for name, task in [("detroit_daily", "daily_detroit"), ("detroit_full", "full_detroit")]:
        jid = jobs.enqueue(store, name, "Artan")
        job = next(j for j in store.history()["jobs"] if j["id"] == jid)
        cmd = jobs.commands(store, json.loads(job["spec"]), Path("config"))[0]
        assert "detroit_pipeline.extract_detroit" in cmd
        assert cmd[cmd.index("--mode") + 1] == ("daily" if task == "daily_detroit" else "full")
        assert ("--lookback-days" in cmd) == (task == "daily_detroit")
        assert ("--reference-date" in cmd) == (task == "daily_detroit")
        assert ("--years" in cmd) == (task == "full_detroit")
        if task == "full_detroit":
            assert cmd[cmd.index("--years") + 1 : cmd.index("--data-root")] == ["2023", "2024"]
        result = jobs.run_one(store, runner=lambda *_: None)
        assert result["status"] == "SUCCEEDED"
        assert candidates.active_id(store) == active_before_imports


@pytest.mark.parametrize("years", [[], [2024, 2024], [2000], [True], "2024"])
def test_detroit_full_years_are_strictly_validated(store, years):
    settings = store.current("settings")
    full = next(job for job in settings["payload"]["jobs"] if job["name"] == "detroit_full")
    full["years"] = years
    with pytest.raises(AdminError, match="Detroit Full"):
        store.propose("settings", settings["payload"], settings["id"], "Artan", "ungueltige Jahre")


def test_duplicate_candidate_identity_is_a_report_failure(store, tmp_path):
    base = datasets(tmp_path / "base")
    after = datasets(
        tmp_path / "after",
        lambda c: c.execute(
            "INSERT INTO silver_crime SELECT * FROM silver_crime WHERE offense_id='D1'"
        ),
    )
    with pytest.raises(AdminError, match="doppelte offense_id"):
        compare(base, after, tmp_path / "report", metadata(store), None, {"ok": False})


def test_http_impact_exports_auth_and_review_binding(store):
    rid = mapping_proposal(store)
    jobs.run_one(store, runner=synthetic_runner())
    row, _ = report_for(store, rid)
    server = make_server(store, "Christian", "secret", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer secret", "Content-Type": "application/json"}

    def read(path):
        return urlopen(Request(url + path, headers=headers)).read()

    try:
        report = json.loads(read("/api/impact?id=" + row["id"]))
        assert report["report_hash"] == row["report_hash"]
        assert (
            read("/api/impact-artifact?id=" + row["id"] + "&name=impact_records.parquet")[:4]
            == b"PAR1"
        )
        with pytest.raises(HTTPError):
            urlopen(url + "/api/impact?id=" + row["id"])
        with pytest.raises(HTTPError):
            read("/api/impact-artifact?id=" + row["id"] + "&name=../../control.sqlite")
        payload = json.dumps(
            {
                "id": rid,
                "choice": "approve",
                "reason": "HTTP review",
                "impact_id": row["id"],
                "report_hash": row["report_hash"],
            }
        ).encode()
        json.load(urlopen(Request(url + "/api/decision", data=payload, headers=headers)))
        assert candidates.active_id(store)
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def test_rewriting_candidate_manifest_cannot_bypass_report_binding(store):
    rid = mapping_proposal(store)
    jobs.run_one(store, runner=synthetic_runner())
    row, _ = report_for(store, rid)
    path = Path(row["candidate_path"]) / "admin" / "impact_records.parquet"
    path.write_bytes(b"corrupted and rehashed")
    manifest_path = Path(row["candidate_path"]) / "release.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"]["admin/impact_records.parquet"]["sha256"] = candidates.file_hash(path)
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(AdminError, match="Kandidatenmanifest"):
        store.decide(
            rid,
            "approve",
            "Christian",
            "check",
            impact_id=row["id"],
            report_hash=row["report_hash"],
        )


def test_all_eight_production_stage_clis_build_real_isolated_candidate(store, monkeypatch):
    """Exercise the actual entry points and SQL, including Spatial and GeoJSON."""
    import importlib
    import sys
    import pyarrow as pa
    from tests.silver_pipeline.test_build_crime_offense import (
        CHI,
        DET,
        POLYGONE,
        TRACT_CHICAGO,
        TRACT_DETROIT,
        schreibe_chicago,
        schreibe_detroit,
    )
    from tests.silver_pipeline.test_build_tract import tiger_table, acs_table, write_bronze_run
    from tests.silver_pipeline.test_build_place import place_table
    from tests.silver_pipeline.test_build_weather_day import (
        write_bronze_run as weather,
        noaa_table,
        OHARE,
        METRO,
    )

    shutil.rmtree(store.data / "bronze")
    chicago = CHI + [
        {
            **CHI[0],
            "id": str(10 + i),
            "case_number": "JA" + str(10 + i),
            "iucr": "0910",
            "description": "MOTOR VEHICLE THEFT",
        }
        for i in range(10)
    ]
    schreibe_chicago(store.data, chicago)
    schreibe_detroit(store.data, DET)
    # Current source-history contract requires real run timing evidence.
    for manifest in (store.data / "bronze").rglob("manifest.json"):
        value = json.loads(manifest.read_text())
        value.update(started_at="2026-10-01T00:00:00Z", started_at_utc="2026-10-01T00:00:00Z")
        manifest.write_text(json.dumps(value))
    with duckdb.connect() as con:
        con.execute("LOAD spatial")
        for state, geoid, city_id, city_name, lat, lon in [
            ("17", TRACT_CHICAGO, "1714000", "Chicago", 41.9, -87.6),
            ("26", TRACT_DETROIT, "2622000", "Detroit", 42.3, -83.1),
        ]:
            geometry = con.execute(
                "SELECT ST_AsWKB(ST_GeomFromText(?))", [POLYGONE[geoid]]
            ).fetchone()[0]
            tiger = tiger_table((geoid,))
            for key, value in [
                ("geometry", pa.array([geometry], pa.binary())),
                ("INTPTLAT", pa.array([str(lat)])),
                ("INTPTLON", pa.array([str(lon)])),
            ]:
                tiger = tiger.set_column(tiger.schema.get_field_index(key), key, value)
            write_bronze_run(store.data, "tiger_tract", state, tiger)
            write_bronze_run(
                store.data, "acs5_tract", state, acs_table((geoid,), ("1000",), ("50000",), ("10",))
            )
            write_bronze_run(
                store.data,
                "tiger_place",
                state,
                place_table([(city_id, city_name, "25", geometry)]),
            )
    for station in (OHARE, METRO):
        weather(
            store.data,
            station,
            noaa_table(
                station,
                [{"DATE": "2024-01-15", "PRCP": "0", "SNOW": "0", "TMAX": "214", "TMIN": "103"}],
            ),
        )
    rid = mapping_proposal(store, city="chicago", code="0110", target="13A")

    def actual_clis(work, commands, log):
        for command in commands:
            monkeypatch.setattr(sys, "argv", [command[2]] + command[3:])
            result = importlib.import_module(command[2]).main()
            assert result == 0, command
            log.write("Production CLI: " + command[2] + "\n")

    result = jobs.run_one(store, runner=actual_clis)
    assert result["status"] == "AWAITING_REVIEW", result
    row, report = report_for(store, rid)
    assert report["summary"]["after"]["offenses"] == 12
    candidate = Path(row["candidate_path"])
    assert (candidate / "serving" / "tracts.geojson").exists()
    with duckdb.connect(str(candidate / "serving" / "analyse.duckdb"), read_only=True) as con:
        assert con.execute(
            "SELECT nibrs_code,mapping_status FROM fact_offense WHERE reporting_city='chicago' AND offense_id='1'"
        ).fetchone() == ("13A", "ambiguous")
    assert candidates.active_id(store) is None
    assert not (store.data / "silver").exists()


def test_explicit_abandon_preserves_attempt_and_unlocks_retry(store):
    rid = mapping_proposal(store)
    iid = store.history()["impacts"][0]["id"]
    with store.db() as c:
        c.execute("UPDATE impact SET status='RUNNING' WHERE id=?", (iid,))
        c.execute("UPDATE job SET status='RUNNING' WHERE id=?", (iid,))
    assert (
        candidates.abandon(store, iid, "Operator", "Process verified stopped")["recovered_by"]
        == "Operator"
    )
    assert (store.root / "jobs" / iid / "recovery.json").exists()
    new = store.retry_impact(rid, "Artan")
    assert new != iid
    assert len(store.history()["impacts"]) == 2
