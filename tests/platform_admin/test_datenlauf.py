"""The console worker does what docker/srv01-datenlauf.sh does (decision 30.10.2026).

Once the stock is managed, storage.verwaltet blocks the cron data run; every
step it took must happen in the worker, or it silently stops happening.
"""

import pytest

from platform_admin import candidates, jobs, operations, serving_export
from platform_admin.store import AdminError

from .test_ln2 import approved_revision, store  # noqa: F401 - fixture


def run(store, monkeypatch, failure=None):  # noqa: F811
    calls = []

    def execute(work, commands, log):
        for command in commands:
            calls.append(command)
            if command[2] == failure:
                raise AdminError("Test failure in " + failure)

    monkeypatch.setattr(jobs, "execute_commands", execute)
    _rid, _row = approved_revision(store)
    active = candidates.active_id(store)
    return active, calls


def modules(calls):
    return [c[2] for c in calls]


def test_drift_and_backup_set_follow_the_analysis_check(store, monkeypatch):  # noqa: F811
    active, calls = run(store, monkeypatch)
    serving_export.publish(store, active)
    order = modules(calls)
    assert order.index("serving.pruefe_stand") < order.index("orchestration.drift")
    assert order.index("orchestration.drift") < order.index("orchestration.sicherungssatz")
    drift = next(c for c in calls if c[2] == "orchestration.drift")
    assert "--nur-melden" in drift
    assert drift[drift.index("--json") + 1] == str(store.data / "drift.json")
    assert "--holen" in next(c for c in calls if c[2] == "orchestration.sicherungssatz")


@pytest.mark.parametrize("failing", ["orchestration.drift", "orchestration.sicherungssatz"])
def test_a_failing_follow_up_does_not_fail_the_publication(store, monkeypatch, failing):  # noqa: F811
    """As in the cron run: a drift over tolerance is work for the documents,
    an incomplete backup set a problem for the next backup - neither turns a
    green data run red after the fact."""
    active, _calls = run(store, monkeypatch, failing)
    assert serving_export.publish(store, active)["status"] == "SUCCEEDED"
    services = operations.overview(store)["services"]
    name = "drift" if failing == "orchestration.drift" else "sicherungssatz"
    assert services[name]["status"] == "WARNING"
    assert services["analysis"]["status"] == "SUCCEEDED"


def test_no_follow_up_after_a_failed_serving_step(store, monkeypatch):  # noqa: F811
    """The cron run stops at the first failure; drift and backup set describe
    a release that is in place, not one that failed halfway."""
    active, calls = run(store, monkeypatch, "serving.build_kibana")
    with pytest.raises(AdminError):
        serving_export.publish(store, active)
    assert "orchestration.drift" not in modules(calls)
    assert "orchestration.sicherungssatz" not in modules(calls)


def test_on_the_server_nothing_is_loaded_into_elastic(store, monkeypatch):  # noqa: F811
    """srv01 has no Elasticsearch and no Kibana since 1.11.2026 (C-9).

    The dashboard reads the store itself; the worker puts the release in
    place, rebuilds the landing page and lets pruefe_stand ask the dashboard -
    the same steps docker/srv01-datenlauf.sh takes, in the same order.
    """
    monkeypatch.setenv("SERVING_BETRIEB", "server")
    active, calls = run(store, monkeypatch)
    serving_export.publish(store, active)
    order = modules(calls)
    assert "serving.load_elasticsearch" not in order
    assert "serving.build_kibana" not in order
    assert order.index("serving.build_einstieg") < order.index("serving.pruefe_stand")
    services = operations.overview(store)["services"]
    assert services["analysis"]["status"] == "SUCCEEDED"
    assert "elasticsearch" not in services and "kibana" not in services


def test_locally_both_loaders_stay(store, monkeypatch):  # noqa: F811
    active, calls = run(store, monkeypatch)
    serving_export.publish(store, active)
    assert modules(calls)[:2] == ["serving.load_elasticsearch", "serving.build_kibana"]


# --------------------------------------------------------------------------
# The run protocol and the metrics file - written after every tick that did
# work, also when it failed (the cron run does it from a trap).
# --------------------------------------------------------------------------

import json  # noqa: E402
import sys  # noqa: E402

from serving import betriebsstand  # noqa: E402


def tick_running(store, monkeypatch, tmp_path, commands, result):  # noqa: F811
    """Replace the tick's work with real commands through execute_commands."""
    monkeypatch.setenv("ADMIN_START_ROOT", str(tmp_path / "startseite"))

    def work(_store):
        folder = tmp_path / "job"
        folder.mkdir(exist_ok=True)
        with (folder / "run.log").open("a", encoding="utf-8") as log:
            jobs.execute_commands(store, commands, log)
        return result

    monkeypatch.setattr(operations, "_tick", work)


def protocol(store):  # noqa: F811
    return json.loads((store.data / "pipeline_run.json").read_text(encoding="utf-8"))


def test_a_tick_that_worked_leaves_protocol_and_metrics(store, monkeypatch, tmp_path):  # noqa: F811
    tick_running(store, monkeypatch, tmp_path, [[sys.executable, "-m", "this"]],
                 {"id": "j", "status": "SUCCEEDED"})
    operations.tick(store)
    run = protocol(store)
    assert run["status"] == "complete"
    assert [(s["name"], s["exit"]) for s in run["stages"]] == [("this", 0)]
    assert run["stages"][0]["sekunden"] >= 0
    metrics = (tmp_path / "startseite" / "metrics").read_text(encoding="utf-8")
    assert "_lauf_bekannt 1" in metrics and "_lauf_erfolgreich 1" in metrics
    # The metrics file reads what the cron run's protocol carries - one format.
    assert "_stufe_exit" in betriebsstand.metriken(run)


def test_a_failed_tick_is_reported_too(store, monkeypatch, tmp_path):  # noqa: F811
    tick_running(store, monkeypatch, tmp_path,
                 [[sys.executable, "-m", "this"], [sys.executable, "-m", "kein_solches_modul"]],
                 {"id": "j", "status": "SUCCEEDED"})
    with pytest.raises(jobs.PipelineCommandError):
        operations.tick(store)
    run = protocol(store)
    assert run["status"] == "failed"
    assert [(s["name"], s["exit"] != 0) for s in run["stages"]] == [
        ("this", False), ("kein_solches_modul", True)]
    assert (tmp_path / "startseite" / "metrics").is_file()


def test_an_idle_tick_keeps_the_last_protocol(store, monkeypatch, tmp_path):  # noqa: F811
    """Every five minutes a tick finds nothing to do. Overwriting the last
    run with "nothing" would hide exactly the failure the protocol is for."""
    monkeypatch.setenv("ADMIN_START_ROOT", str(tmp_path / "startseite"))
    monkeypatch.setattr(operations, "_tick", lambda _store: None)
    operations.tick(store)
    assert not (store.data / "pipeline_run.json").exists()


def test_an_incomplete_backup_set_does_not_turn_the_run_red():
    """The cron run: "|| echo WARNUNG". Same rule for the worker."""
    from platform_admin.run_protocol import succeeded

    gelaufen = [{"modul": "serving.pruefe_stand", "exit": 0},
                {"modul": "orchestration.drift", "exit": 0},
                {"modul": "orchestration.sicherungssatz", "exit": 1}]
    assert succeeded(gelaufen, "SUCCEEDED")
    assert not succeeded([{"modul": "serving.pruefe_stand", "exit": 1}], "SUCCEEDED")
    assert not succeeded(gelaufen, "PARTIAL")


# --------------------------------------------------------------------------
# Scheduled data runs are approved by the quality gate (decision 30.10.2026):
# the cron run published every week without review; the console keeps that,
# with the gate in front. Mapping and settings changes keep four eyes.
# --------------------------------------------------------------------------

from platform_admin import auto_approval  # noqa: E402

from .helpers import bronze, synthetic_runner  # noqa: E402


def data_candidate(store, origin):  # noqa: F811
    jobs.enqueue(store, "rebuild", "scheduler", origin=origin)
    bronze(store.data)
    result = jobs.run_one(store, runner=synthetic_runner())
    assert result["status"] == "AWAITING_REVIEW", result
    return next(i for i in store.history()["impacts"] if i["id"] == result["id"])


def impact(store, iid):  # noqa: F811
    return next(i for i in store.history()["impacts"] if i["id"] == iid)


def test_a_scheduled_data_candidate_is_approved_by_the_gate(store):  # noqa: F811
    row = data_candidate(store, "batch")
    assert auto_approval.run(store) == row["id"]
    revision = next(r for r in store.history()["revisions"] if r["id"] == row["revision_id"])
    assert revision["reviewer"] == auto_approval.ACTOR
    assert "Qualitaetstor" in revision["decision_reason"]
    after = impact(store, row["id"])
    # Published at once or on the next tick, depending on the release mode.
    assert after["status"] in {"APPROVED_PENDING_PUBLICATION", "PUBLISHED"}
    if after["status"] == "PUBLISHED":
        assert candidates.active_id(store) == after["published_release_id"]


def test_a_rebuild_somebody_asked_for_waits_for_a_person(store):  # noqa: F811
    row = data_candidate(store, None)
    assert auto_approval.run(store) is None
    assert impact(store, row["id"])["status"] == "READY"


def test_a_candidate_the_gate_refuses_waits_for_a_person(store, monkeypatch):  # noqa: F811
    row = data_candidate(store, "batch")

    def refuse(*args, **kwargs):
        raise AdminError("Kandidat besteht die Quality Gates nicht")

    monkeypatch.setattr(candidates, "decide", refuse)
    assert auto_approval.run(store) is None
    assert impact(store, row["id"])["status"] == "READY"
    status = operations.overview(store)["services"]["auto_approval"]
    assert status["status"] == "REVIEW_REQUIRED" and "Quality Gates" in status["reason"]


def test_every_tick_offers_the_gate_first(store, monkeypatch):  # noqa: F811
    called = []
    monkeypatch.setattr(auto_approval, "run", lambda s: called.append(s))
    operations.tick(store)
    assert called == [store]


# --------------------------------------------------------------------------
# Parity: every module the cron data run calls, the worker calls too
# --------------------------------------------------------------------------

import re  # noqa: E402

from .helpers import PROJECT  # noqa: E402

#: Modules of the cron run the worker replaces instead of calling - with why.
REPLACED = {
    "orchestration.run_all": "the worker runs the same stages through "
                             "run_all.auswahl (batch: ingestion, candidate: the rest)",
    "orchestration.release": "the console builds releases itself (storage.release.erstelle) "
                             "and puts them in place with storage.release.einsetzen",
}


def test_the_worker_covers_every_step_of_the_cron_run():
    """The next step added to srv01-datenlauf.sh must not land only there.

    Drift, backup set and the metrics file were exactly such steps: the cron
    run had them, the console did not, and switching over would have dropped
    them without a sound."""
    from orchestration.run_all import STUFEN

    script = (PROJECT / "docker" / "srv01-datenlauf.sh").read_text(encoding="utf-8")
    called = set(re.findall(r"python -m ([a-z_]+\.[a-z_]+)", script))
    source = "\n".join(p.read_text(encoding="utf-8")
                       for p in (PROJECT / "src/crime/platform_admin").glob("*.py"))
    stages = {s.modul for s in STUFEN}

    def covered(module):
        package, name = module.split(".")
        return (module in stages or f'"{module}"' in source
                or f"from {package} import {name}" in source)

    missing = sorted(m for m in called if not covered(m) and m not in REPLACED)
    assert not missing, f"the cron run calls, the worker does not: {missing}"
    stale = sorted(set(REPLACED) - called)
    assert not stale, f"exceptions for steps the cron run no longer has: {stale}"
    assert "auswahl(" in (PROJECT / "src/crime/platform_admin/batch.py").read_text()
    assert "auswahl(" in (PROJECT / "src/crime/platform_admin/jobs.py").read_text()
