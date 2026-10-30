import copy
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from platform_admin import jobs
from platform_admin.store import AdminError, Store, validate_settings, DEFAULT_SETTINGS
from platform_admin.web import make_server
from tests.platform_admin.helpers import approve, synthetic_runner, bronze

PROJECT = Path(__file__).resolve().parents[2]


@pytest.fixture
def store(tmp_path):
    result = Store(PROJECT, tmp_path / "data")
    result.initialize("bootstrap")
    return result


def approve_settings(store, settings):
    rid = store.propose("settings", settings, store.current("settings")["id"], "Artan", "Testplan")
    approve(store, rid)
    return rid


def test_baseline_is_not_fabricated_approval(store):
    assert all(r["decision"] is None for r in store.history()["revisions"])
    assert not any(j["enabled"] for j in store.current("settings")["payload"]["jobs"])


def test_mapping_approval_is_versioned_and_second_person_required(store):
    old = store.current("mapping")
    proposal = store.propose_mapping(
        "detroit",
        "2403",
        "26B",
        old["id"],
        "Artan",
        "Synthetischer Reviewtest, keine fachliche Empfehlung",
    )
    assert store.current("mapping")["id"] == old["id"]
    with pytest.raises(AdminError, match="zweite Person"):
        store.decide(proposal, "approve", "Artan", "Self")
    approve(store, proposal)
    current = store.current("mapping")
    assert current["id"] == proposal and current["sha256"] != old["sha256"]
    r = next(r for r in store.history()["revisions"] if r["id"] == proposal)
    assert r["actor"] == "Artan" and r["reviewer"] == "Christian" and r["decided_at"]
    assert "detroit,2403,26B," in current["payload"]["mapping_overrides.csv"]
    assert current["payload"]["micr_nibrs_mapping.csv"] == old["payload"]["micr_nibrs_mapping.csv"]
    path = store.materialize(proposal)
    assert path == store.materialize(proposal)
    (path / "micr_nibrs_mapping.csv").write_text("corrupted")
    with pytest.raises(AdminError, match="nachtraeglich"):
        store.materialize(proposal)


def test_stale_proposal_and_double_decision_rejected(store):
    settings = store.current("settings")
    a = store.propose("settings", settings["payload"], settings["id"], "A", "a")
    b = store.propose("settings", settings["payload"], settings["id"], "A", "b")
    approve(store, a, actor="B")
    with pytest.raises(AdminError, match="Veralteter"):
        store.decide(b, "approve", "B", "no")
    with pytest.raises(AdminError, match="bereits"):
        store.decide(a, "reject", "B", "no")


def test_scheduler_once_per_utc_day_and_disabled_by_default(store):
    instant = datetime(2026, 9, 18, 9, tzinfo=timezone.utc)
    assert jobs.schedule(store, instant=instant) == []
    settings = store.current("settings")["payload"]
    settings["jobs"][0]["enabled"] = True
    approve_settings(store, settings)
    assert len(jobs.schedule(store, instant=instant)) == 1
    assert jobs.schedule(store, instant=instant) == []
    approve_settings(store, settings)
    assert jobs.schedule(store, instant=instant) == []


def test_jobs_pin_revisions_and_use_existing_clis(store):
    jid = jobs.enqueue(store, "rebuild", "Artan")
    job = next(j for j in store.history()["jobs"] if j["id"] == jid)
    old = job["settings_revision"]
    approve_settings(store, store.current("settings")["payload"])
    assert job["settings_revision"] == old != store.current("settings")["id"]
    command_list = jobs.commands(store, {"task": "rebuild"}, Path("pinned"))
    assert len(command_list) == 9
    assert sum("--config-root" in c for c in command_list) == 2
    assert all("--data-root" in c for c in command_list)
    assert not any("download_" in " ".join(c) for c in command_list)


@pytest.mark.parametrize("task", ["checks", "rebuild", "replay"])
def test_quality_failure_never_publishes(store, task):
    settings = store.current("settings")["payload"]
    settings["jobs"] = [{"name": "test", "task": task, "enabled": False, "at_utc": "07:00"}]
    approve_settings(store, settings)
    jobs.enqueue(store, "test", "Artan")
    report = {"ok": False, "technical_ok": True, "quality_ok": False, "replay_ok": True}
    published = []
    result = jobs.run_one(
        store,
        runner=(lambda *_: None) if task == "checks" else synthetic_runner(),
        evaluator=lambda *_a, **_k: report,
    )
    assert result["status"] == "REVIEW_REQUIRED" and not published
    assert Path(store.history()["jobs"][0]["log_path"]).exists()


def test_replay_mismatch_is_failure_even_with_green_quality(store):
    settings = store.current("settings")["payload"]
    settings["jobs"] = [{"name": "replay", "task": "replay", "enabled": False, "at_utc": "07:00"}]
    approve_settings(store, settings)
    jobs.enqueue(store, "replay", "A")
    report = {"ok": False, "technical_ok": True, "quality_ok": True, "replay_ok": False}
    result = jobs.run_one(store, runner=synthetic_runner(), evaluator=lambda *_a, **_k: report)
    assert result["status"] == "FAILED"


def test_writer_lock_prevents_concurrent_admin_workers(store):
    with jobs.writer_lock(store):
        with pytest.raises(AdminError, match="Worker-Lock"):
            jobs.run_one(store)
    assert not (store.root / "worker.lock").exists()


def test_worker_records_subprocess_failure(store):
    bronze(store.data)
    jobs.enqueue(store, "rebuild", "A")

    def fail(*_):
        raise RuntimeError("synthetic failure")

    result = jobs.run_one(store, runner=fail)
    assert result["status"] == "FAILED"
    assert result["result"]["error"] == "synthetic failure"
    # An old pre-upgrade direct rebuild must fail before any global write.
    with store.db() as c:
        c.execute(
            """INSERT INTO job(id,name,mapping_revision,settings_revision,spec,actor,status,queued_at)
                    VALUES(?,?,?,?,?,?,'QUEUED',?)""",
            (
                "legacy-rebuild",
                "legacy",
                store.current("mapping")["id"],
                store.current("settings")["id"],
                json.dumps({"task": "rebuild"}),
                "A",
                "2026-01-01T00:00:00Z",
            ),
        )
    calls = []
    old = jobs.run_one(store, runner=lambda *_: calls.append(True))
    assert old["status"] == "FAILED" and not calls


def test_command_failure_exposes_stage_dependency_and_remediation(store, tmp_path, monkeypatch):
    log_path = tmp_path / "run.log"
    command = ["python", "-m", "silver_pipeline.build_tract", "--data-root", "data"]

    def failed(*_args, **kwargs):
        kwargs["stdout"].write(
            "ERROR Silver-Aufbau fehlgeschlagen: Kein vollstaendiger Bronze-Lauf "
            "fuer tiger_tract, Vintage 2024, Staat 17.\n"
        )
        return type("Result", (), {"returncode": 1})()

    monkeypatch.setattr(jobs.subprocess, "run", failed)
    with log_path.open("w", encoding="utf-8") as log:
        with pytest.raises(jobs.PipelineCommandError) as raised:
            jobs.execute_commands(store, [command], log)
    error = raised.value
    result = error.result(log_path)
    assert result["stage"] == "Silver · Census-Tracts"
    assert "tiger_tract / Vintage 2024 / Staat 17" in result["missing_dependency"]
    assert "download_tiger" in result["remediation"]


@pytest.mark.parametrize(
    "message,dependency",
    [
        ("HTTP 429 Too Many Requests", "API-Anfragekontingent"),
        ("ModuleNotFoundError: No module named 'duckdb'", "Python-Projekt"),
        ("PermissionError: permission denied", "Schreib-/Leseberechtigung"),
        ("OSError: No space left on device", "freier Speicherplatz"),
    ],
)
def test_log_diagnosis_classifies_operational_failures(tmp_path, message, dependency):
    log = tmp_path / "run.log"
    log.write_text("ERROR " + message + "\n", encoding="utf-8")
    _cause, found, remedy = jobs._log_diagnosis(log, "serving.build_analysis_db")
    assert dependency in found
    assert remedy


@pytest.mark.parametrize(
    "key,value", [("maximum_unmapped_ratio", 1.1), ("scope_end_exclusive", "2023-01-01")]
)
def test_settings_validation(key, value):
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    settings[key] = value
    with pytest.raises((AdminError, ValueError)):
        validate_settings(settings)


def test_web_auth_origin_and_no_arbitrary_job(store):
    server = make_server(store, "Artan", "secret", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert b"Engineering-Konsole" in urlopen(url).read()
        with pytest.raises(HTTPError) as exc:
            urlopen(url + "/api/state")
        assert exc.value.code == 401
        headers = {"Authorization": "Bearer secret", "Content-Type": "application/json"}
        data = json.load(urlopen(Request(url + "/api/state", headers=headers)))
        assert data["operator"] == "Artan"
        with pytest.raises(HTTPError) as exc:
            urlopen(
                Request(url + "/api/state", headers={**headers, "Origin": "https://evil.invalid"})
            )
        assert exc.value.code == 403
        with pytest.raises(HTTPError) as exc:
            urlopen(Request(url + "/api/job", data=b'{"name":"rm -rf"}', headers=headers))
        assert exc.value.code == 400
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
