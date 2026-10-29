"""Cross-version boundaries: real files/SQLite, controlled network adapters."""
import json
from pathlib import Path

import pytest
import storage
from platform_admin import candidates, integration, jobs, operations
from platform_admin.batch import enqueue_batch
from platform_admin.store import Store, AdminError
from storage.managed import guard
from .helpers import PROJECT, datasets


@pytest.fixture
def store(tmp_path):
    result = Store(PROJECT, tmp_path / "data")
    result.initialize("bootstrap")
    return result


def test_candidate_creation_never_repoints_active_release(store):
    from storage.release import erstelle
    datasets(store.data)
    first = erstelle(store.data, kennung_="baseline")
    before = (store.data / "releases/AKTUELL.json").read_bytes()
    candidate = erstelle(store.data, kennung_="candidate-test", activate=False)
    assert candidate.exists() and first.exists()
    assert (store.data / "releases/AKTUELL.json").read_bytes() == before


def test_multiyear_stage_expansion_and_history(store):
    commands = jobs.commands(store, {"task": "rebuild", "years": [2021, 2024, 2026]}, Path("config"))
    tract = [c[c.index("--vintage")+1] for c in commands if c[2] == "silver_pipeline.build_tract"]
    assert tract == ["2021", "2024"]
    assert sum(c[2] == "silver_pipeline.build_source_change" for c in commands) == 1
    assert all("--data-root" in c for c in commands)


def test_delta_and_daily_are_distinct(store):
    delta = jobs.commands(store, {"task": "delta_detroit", "years": [2023, 2024]}, Path("config"))[0]
    daily = jobs.commands(store, {"task": "daily_detroit", "reference_date": "2026-10-20"}, Path("config"))[0]
    assert delta[delta.index("--mode")+1] == "delta"
    assert "--reference-date" not in delta and "--years" in delta
    assert daily[daily.index("--mode")+1] == "daily"
    assert "--years" not in daily


def test_guard_requires_live_lock_token_even_without_env_flag(store, monkeypatch):
    integration.enable(store, "operator")
    with pytest.raises(RuntimeError, match="Verwalteter"):
        guard(store.data, allow_worker=True)
    with jobs.writer_lock(store):
        with pytest.raises(AdminError, match="Lock"):
            with jobs.writer_lock(Store(PROJECT, store.data)):
                pass
        token = json.loads((store.root / "worker.lock").read_text())["token"]
        monkeypatch.setenv("ADMIN_WRITER_TOKEN", token)
        guard(store.data, allow_worker=True)
        with pytest.raises(RuntimeError):
            guard(store.data)
    with pytest.raises(RuntimeError):
        guard(store.data, allow_worker=True)


def test_batch_deduplication_pins_approved_configuration(store):
    first = enqueue_batch(store, "full", "scheduler", "2026-10-26")
    assert enqueue_batch(store, "full", "scheduler", "2026-10-26") == first
    with pytest.raises(AdminError):
        enqueue_batch(store, "delta", "scheduler", "2026-10-27")
    row = operations.overview(store)["operations"][0]
    payload = json.loads(row["payload"])
    assert payload["heads"]["settings"] == store.current("settings")["id"]
    assert candidates.active_id(store) is None


def test_remote_snapshot_and_ui_use_s3_not_local_stale_cache(store):
    fake = storage.FakeS3Client()
    backend = storage.Storage(storage.Config(backend="s3", local_root=store.data), client=fake)
    storage.set_storage(backend)
    base = "bronze/city=detroit/year=2024/run_one/"
    fake.put(base + "manifest.json", b'{"status":"complete","run_id":"remote","mode":"delta"}')
    fake.put(base + "source.json", b'{"remote":true}')
    stale = store.data / base / "manifest.json"
    stale.parent.mkdir(parents=True)
    stale.write_text('{"status":"complete","run_id":"stale"}')
    target = store.root / "snapshot"
    target.mkdir()
    proof = candidates.sources_snapshot(store, target)
    assert proof["origin"] == "s3"
    assert json.loads((target / base / "manifest.json").read_text())["run_id"] == "remote"
    from platform_admin.sources import source_status
    assert source_status(store)[1]["runs"][0]["run_id"] == "remote"
    assert json.loads(stale.read_text())["run_id"] == "stale"


def test_source_history_is_carried_from_approved_baseline(store, tmp_path):
    baseline = tmp_path / "baseline"
    rel = "silver/dataset=source_change"
    (baseline / rel).mkdir(parents=True)
    (baseline / rel / "part-0001.parquet").write_bytes(b"approved-history")
    (store.data / rel).mkdir(parents=True)
    (store.data / rel / "part-0001.parquet").write_bytes(b"unreviewed-working-copy")
    target = tmp_path / "candidate"
    integration.copy_history(store, target, baseline)
    assert (target / rel / "part-0001.parquet").read_bytes() == b"approved-history"


def test_serving_outbox_reconciles_once_and_does_not_retry_failed_attempts(store, monkeypatch):
    from .test_ln2 import approved_revision
    _, row = approved_revision(store)
    monkeypatch.setenv("ADMIN_AUTO_SERVING", "true")
    integration.reconcile_serving(store)
    integration.reconcile_serving(store)
    ops = operations.overview(store)["operations"]
    assert len(ops) == 1
    assert json.loads(ops[0]["payload"])["id"] == row["published_release_id"]
    with store.db() as con:
        con.execute("UPDATE operation SET status='FAILED'")
    integration.reconcile_serving(store)
    assert len(operations.overview(store)["operations"]) == 1


def test_failed_service_is_not_reported_as_success_metric(store):
    operations.record_status(store, "analysis", {"status": "PARTIAL"})
    text = operations.metrics_text(store)
    assert 'crime_admin_service_ok{service="analysis"} 0' in text


def test_recovery_only_closes_abandoned_nonimpact_job(store):
    jid = jobs.enqueue(store, "chicago_full", "engineer")
    with store.db() as con:
        con.execute("UPDATE job SET status='RUNNING' WHERE id=?", (jid,))
    jobs.recover_import(store, jid, "operator", "All writers verified stopped")
    row = next(j for j in store.history()["jobs"] if j["id"] == jid)
    assert row["status"] == "FAILED"
    assert (store.root / "jobs" / jid / "recovery.json").exists()
    with pytest.raises(AdminError):
        jobs.recover_import(store, jid, "operator", "Duplicate recovery")


def test_local_backup_includes_management_and_serving_evidence(store, tmp_path):
    from platform_admin.object_store import backup, restore_archive
    integration.enable(store, "operator")
    (store.root / "serving").mkdir()
    (store.root / "serving/proof.txt").write_text("release-evidence")
    with jobs.writer_lock(store):
        info = backup(store)
    target = tmp_path / "restored"
    restore_archive(store.data / info["key"], target)
    assert (target / "admin/managed.json").exists()
    assert (target / "admin/serving/proof.txt").read_text() == "release-evidence"
