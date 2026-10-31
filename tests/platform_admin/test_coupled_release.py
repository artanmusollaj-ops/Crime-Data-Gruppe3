"""Real candidate/archive bytes, SQLite transitions and controlled Git failures."""

import base64
import copy
import io
import json
import shutil
import zipfile

import pytest

from platform_admin import candidates, gitops, release_flow, impact_archive, coupled_git
from platform_admin.store import Store, AdminError
from platform_admin.jobs import run_one, writer_lock
from platform_admin.web import create_app
from .helpers import PROJECT, bronze, synthetic_runner
from .test_ln2 import FakeObjects


@pytest.fixture(autouse=True)
def coupled_mode(monkeypatch, release_mode_for_legacy_tests):
    monkeypatch.setenv("ADMIN_RELEASE_MODE", "coupled")


class GitRemote:
    repo = "team/crime"
    branch = "main"

    def __init__(self, store):
        heads = {name: store.current(name)["id"] for name in ["mapping", "settings", "data"]}
        self.sources = release_flow.inventory(store, {"base_heads": heads})
        self.contents = {
            "config/" + name: text for name, text in store.current("mapping")["payload"].items()
        }
        self.main = "base"
        self.ref = None
        self.pr = None
        self.calls = []
        self.merges = 0
        self.commits = {"base": {"tree": {"sha": "base-tree"}, "parents": []}}
        self.clean = True
        self.strict = True
        self.expire_after_merge = False
        self.bad_merge_tree = False
        self.bad_merge_parent = False
        self.truncated = False
        self.tree_entries = []
        self.unreachable = False
        self.protected = True
        self.workflow_runs = [{"name": "tests", "status": "completed", "conclusion": "success"}]
        self.pr_head = "candidate-head"

    def call(self, method, path, value=None, missing=False):
        self.calls.append((method, path, value))
        if self.unreachable:
            raise OSError("network unavailable")
        if path.startswith("/actions/runs?head_sha="):
            # Only the runs of the exact head commit, as GitHub filters them.
            if path.split("head_sha=")[1].split("&")[0] != self.pr_head:
                return {"total_count": 0, "workflow_runs": []}
            return {"total_count": len(self.workflow_runs),
                    "workflow_runs": copy.deepcopy(self.workflow_runs)}
        if path.endswith("/protection") and not self.protected:
            # GitHub answers 404 for an unprotected branch, like GitHub.call.
            if missing:
                return None
            raise AdminError("GitHub verweigert GET (404)")
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path.startswith("/git/trees/") and "?recursive=1" in path:
            return {
                "truncated": self.truncated,
                "tree": [{"path": k, "sha": v, "type": "blob"} for k, v in self.sources.items()],
            }
        if path.startswith("/contents/"):
            content = self.contents.get(path.split("?")[0].removeprefix("/contents/"))
            return (
                None
                if content is None
                else {"content": base64.b64encode(content.encode()).decode()}
            )
        if path.startswith("/git/commits/") and method == "GET":
            return self.commits[path.rsplit("/", 1)[1]]
        if path == "/git/trees" and method == "POST":
            self.tree_entries = value["tree"]
            return {"sha": "candidate-tree"}
        if path == "/git/commits" and method == "POST":
            self.commits["candidate-head"] = {
                "tree": {"sha": value["tree"]},
                "parents": [{"sha": s} for s in value["parents"]],
            }
            return {"sha": "candidate-head"}
        if path.startswith("/git/ref/heads/engineering/"):
            return self.ref
        if path == "/git/refs":
            self.ref = {"object": {"sha": value["sha"]}}
            return self.ref
        if path.startswith("/pulls?"):
            return [self.pr] if self.pr else []
        if path == "/pulls" and method == "POST":
            self.pr = {
                "number": 1,
                "html_url": "https://github.com/team/crime/pull/1",
                "body": value.get("body"),
                "state": "open",
                "head": {"sha": "candidate-head"},
                "base": {"sha": "base", "ref": "main"},
                "merged": False,
                "mergeable": True,
                "mergeable_state": "clean",
            }
            return copy.deepcopy(self.pr)
        if path == "/pulls/1" and method == "GET":
            return {
                **copy.deepcopy(self.pr),
                "mergeable_state": "clean" if self.clean else "blocked",
            }
        if path == "/pulls/1" and method == "PATCH":
            self.pr["state"] = value["state"]
            return copy.deepcopy(self.pr)
        if path.endswith("/protection"):
            return {
                "required_status_checks": {"strict": self.strict, "contexts": ["required-ci"]},
                "required_pull_request_reviews": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews": True,
                },
                "enforce_admins": {"enabled": True},
            }
        if path == "/pulls/1/merge":
            assert value == {"sha": "candidate-head", "merge_method": "squash"}
            self.merges += 1
            self.main = "merged"
            self.commits["merged"] = {
                "tree": {"sha": "unexpected-tree" if self.bad_merge_tree else "candidate-tree"},
                "parents": [{"sha": "unexpected-base" if self.bad_merge_parent else "base"}],
            }
            self.pr.update(merged=True, state="closed", merge_commit_sha="merged")
            for entry in self.tree_entries:
                self.contents[entry["path"]] = entry["content"]
            if self.expire_after_merge:
                raise OSError("response lost after successful merge")
            return {"merged": True, "sha": "merged"}
        if path.startswith("/compare/"):
            return {"status": "ahead"}
        raise AssertionError((method, path, value))


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = Store(PROJECT, tmp_path / "data")
    store.initialize("bootstrap")
    gh = GitRemote(store)
    monkeypatch.setattr(gitops, "GitHub", lambda: gh)
    return store, gh


def proposed(store, reason="change"):
    before = store.current("settings")
    value = copy.deepcopy(before["payload"])
    value["maximum_unmapped_ratio"] = 0.04
    return store.propose("settings", value, before["id"], "engineer", reason)


def built(store):
    rid = proposed(store)
    bronze(store.data)
    result = run_one(store, runner=synthetic_runner())
    assert result["status"] == "AWAITING_REVIEW", result
    return rid, dict(next(i for i in store.history()["impacts"] if i["id"] == result["id"]))


def reviewed(store):
    rid, row = built(store)
    store.decide(
        rid,
        "approve",
        "reviewer",
        "Reviewed exact archived impact",
        impact_id=row["id"],
        report_hash=row["report_hash"],
    )
    return rid, dict(next(i for i in store.history()["impacts"] if i["id"] == row["id"]))


def open_review(store):
    rid, row = reviewed(store)
    with writer_lock(store):
        gitops.open_pr(store, rid, "engineer")
    return rid, row


def merge_review(store, rid):
    with writer_lock(store):
        return gitops.merge_pr(store, rid, "release-manager")


def publish(store, iid):
    with writer_lock(store):
        return candidates.finish_publication(store, iid)


def test_coupled_is_default(monkeypatch):
    monkeypatch.delenv("ADMIN_RELEASE_MODE")
    assert release_flow.mode() == "coupled"


def test_full_coupled_flow_preserves_heads_until_publication(setup):
    store, gh = setup
    old = store.current("settings")["id"]
    rid, row = open_review(store)
    assert row["status"] == "AWAITING_GIT"
    assert candidates.active_id(store) is None and store.current("settings")["id"] == old
    with pytest.raises(AdminError):
        publish(store, row["id"])
    d = merge_review(store, rid)
    current = store.history()["impacts"][0]
    assert current["status"] == "APPROVED_PENDING_PUBLICATION"
    assert candidates.active_id(store) is None and store.current("settings")["id"] == old
    release = publish(store, row["id"])
    assert release == candidates.active_id(store) and store.current("settings")["id"] == rid
    audit = json.loads(
        (candidates.release_path(store, release) / "admin/approval.json").read_text()
    )
    assert audit["git_evidence"]["merge_sha"] == "merged"
    assert audit["git_evidence"]["report_hash"] == row["report_hash"]
    assert audit["git_evidence"]["archive_hash"] == store.history()["archives"][0]["manifest_hash"]
    assert candidates.file_hash(
        candidates.release_path(store, release) / "gold/dataset=fact_offense/part-0001.parquet"
    ) == candidates.file_hash(
        __import__("pathlib").Path(row["candidate_path"])
        / "gold/dataset=fact_offense/part-0001.parquet"
    )
    assert {e["action"] for e in store.history()["release_events"]} == {
        "REVIEW_APPROVED",
        "MERGE_REQUESTED",
        "MERGE_VERIFIED",
        "PUBLISHED",
    }
    assert d["state"] == "MERGED" and gh.merges == 1


def test_no_pr_before_review(setup):
    store, gh = setup
    rid, _row = built(store)
    with pytest.raises(AdminError):
        gitops.open_pr(store, rid, "engineer")
    assert not any(m == "POST" for m, p, v in gh.calls)


@pytest.mark.parametrize(
    "failure",
    [
        "main_before_pr",
        "main_before_merge",
        "head",
        "ci",
        "protection",
        "merge_tree",
        "merge_parent",
        "self",
    ],
)
def test_merge_and_baseline_gates(setup, failure):
    store, gh = setup
    rid, _row = reviewed(store)
    old = store.current("settings")["id"]
    if failure == "main_before_pr":
        gh.main = "another"
        with pytest.raises(AdminError, match="Main/Repository"):
            gitops.open_pr(store, rid, "engineer")
        return
    gitops.open_pr(store, rid, "engineer")
    if failure == "main_before_merge":
        gh.main = "another"
    if failure == "head":
        gh.pr["head"]["sha"] = "changed"
    if failure == "ci":
        gh.clean = False
    if failure == "protection":
        gh.strict = False
    if failure == "merge_tree":
        gh.bad_merge_tree = True
    if failure == "merge_parent":
        gh.bad_merge_parent = True
    with writer_lock(store), pytest.raises(AdminError):
        gitops.merge_pr(store, rid, "engineer" if failure == "self" else "release-manager")
    assert candidates.active_id(store) is None and store.current("settings")["id"] == old
    assert store.history()["impacts"][0]["status"] == "AWAITING_GIT"


def test_lost_merge_response_is_resumable_without_second_merge(setup):
    store, gh = setup
    rid, row = open_review(store)
    gh.expire_after_merge = True
    with pytest.raises(OSError):
        merge_review(store, rid)
    assert store.history()["impacts"][0]["status"] == "AWAITING_GIT"
    gh.expire_after_merge = False
    merge_review(store, rid)
    publish(store, row["id"])
    assert gh.merges == 1


def test_unrequested_external_merge_is_not_activated(setup):
    store, gh = setup
    rid, _row = open_review(store)
    gh.call("PUT", "/pulls/1/merge", {"sha": "candidate-head", "merge_method": "squash"})
    with pytest.raises(AdminError, match="Externer Merge"):
        merge_review(store, rid)
    assert candidates.active_id(store) is None


def test_switching_environment_cannot_bypass_pinned_gate(setup, monkeypatch):
    store, _gh = setup
    rid, row = open_review(store)
    monkeypatch.setenv("ADMIN_RELEASE_MODE", "separate")
    with pytest.raises(AdminError):
        publish(store, row["id"])
    assert release_flow.requires_git(row, store.get(rid))


def test_global_review_reservation_blocks_other_release(setup):
    store, _gh = setup
    _rid, _row = reviewed(store)
    other = store.propose(
        "data", {"task": "rebuild"}, store.current("data")["id"], "other", "new source data"
    )
    result = run_one(store, runner=synthetic_runner())
    assert result["status"] == "AWAITING_REVIEW"
    ir = next(i for i in store.history()["impacts"] if i["id"] == result["id"])
    with pytest.raises(AdminError, match="Publikation"):
        store.decide(
            other,
            "approve",
            "reviewer",
            "cannot overtake",
            impact_id=ir["id"],
            report_hash=ir["report_hash"],
        )
    assert candidates.active_id(store) is None


def test_withdraw_closes_pr_retains_evidence_and_allows_new_proposal(setup):
    store, gh = setup
    rid, row = open_review(store)
    with writer_lock(store):
        result = coupled_git.withdraw(store, rid, "reviewer", "Main changed; new simulation")
    assert result["status"] == "WITHDRAWN" and gh.pr["state"] == "closed"
    assert store.history()["revisions"][0]["decision"] == "approve"
    impact_archive.checked(store, row["id"])
    assert proposed(store, "resubmitted") != rid
    with pytest.raises(AdminError):
        merge_review(store, rid)


def test_cannot_withdraw_after_merge(setup):
    store, _gh = setup
    rid, _row = open_review(store)
    merge_review(store, rid)
    with writer_lock(store), pytest.raises(AdminError):
        coupled_git.withdraw(store, rid, "reviewer", "undo")


def test_publication_failure_keeps_old_heads_and_retries(setup, monkeypatch):
    from platform_admin import object_store

    store, _gh = setup
    old = store.current("settings")["id"]
    rid, row = open_review(store)
    merge_review(store, rid)
    monkeypatch.setenv("ADMIN_OBJECT_STORE", "s3")
    monkeypatch.setattr(object_store, "Objects", lambda: FakeObjects())
    with store.db() as c:
        c.execute("UPDATE impact_archive SET remote_verified_at='tested'")
    monkeypatch.setattr(
        object_store, "publish_release", lambda *a: (_ for _ in ()).throw(OSError("s3 offline"))
    )
    with pytest.raises(OSError):
        publish(store, row["id"])
    assert candidates.active_id(store) is None and store.current("settings")["id"] == old
    monkeypatch.setattr(object_store, "publish_release", lambda *a: None)
    publish(store, row["id"])
    assert store.current("settings")["id"] == rid


def test_crash_after_pointer_switch_recovers(setup, monkeypatch):
    from storage.release import setze_aktuell
    import storage.release

    store, _gh = setup
    rid, row = open_review(store)
    merge_review(store, rid)

    def crash(path, manifest):
        setze_aktuell(path, manifest)
        raise OSError("after pointer")

    monkeypatch.setattr(storage.release, "setze_aktuell", crash)
    with pytest.raises(OSError):
        publish(store, row["id"])
    assert store.current("settings")["id"] != rid
    monkeypatch.setattr(storage.release, "setze_aktuell", setze_aktuell)
    publish(store, row["id"])
    assert store.current("settings")["id"] == rid


def test_missing_git_at_publication_is_closed(setup):
    store, gh = setup
    rid, row = open_review(store)
    merge_review(store, rid)
    gh.unreachable = True
    with pytest.raises(OSError):
        publish(store, row["id"])
    assert candidates.active_id(store) is None


def test_archive_survives_job_directory_removal_and_downloads(setup):
    store, _gh = setup
    rid, row = built(store)
    archive, _manifest = impact_archive.checked(store, row["id"])
    data = impact_archive.zip_bytes(store, row["id"])
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        assert {
            "impact_report.json",
            "impact_by_partition.parquet",
            "revision.json",
            "archive_manifest.json",
        } <= set(z.namelist())
        assert json.loads(z.read("revision.json"))["id"] == rid
    shutil.rmtree(store.root / "jobs" / row["id"])
    app = create_app(store, operator="viewer", token="secret", config={"ADMIN_AUTH": "local"})
    client = app.test_client()
    headers = {"Authorization": "Bearer secret"}
    assert client.get("/api/impact-archive?id=" + row["id"], headers=headers).status_code == 200
    assert (
        client.get("/api/impact?id=" + row["id"], headers=headers).json["report_hash"]
        == row["report_hash"]
    )
    assert archive["revision_id"] == rid


def test_retry_creates_distinct_archives(setup):
    store, _gh = setup
    rid, row = built(store)
    first = impact_archive.zip_bytes(store, row["id"])
    store.retry_impact(rid, "engineer")
    run_one(store, runner=synthetic_runner())
    archives = store.history()["archives"]
    assert len(archives) == 2
    assert len({a["impact_id"] for a in archives}) == 2 and {
        a["revision_id"] for a in archives
    } == {rid}
    assert impact_archive.zip_bytes(store, row["id"]) == first


def test_failed_attempt_is_archived(setup):
    store, _gh = setup
    rid = proposed(store)
    result = run_one(store, runner=synthetic_runner())
    assert result["status"] == "FAILED"
    record, manifest = impact_archive.checked(store, result["id"])
    assert record["revision_id"] == rid and manifest["report_hash"] is None
    assert "run.log" in manifest["files"] and "attempt.json" in manifest["files"]


def test_archive_tampering_blocks_review(setup):
    from pathlib import Path

    store, _gh = setup
    rid, row = built(store)
    record, _manifest = impact_archive.checked(store, row["id"])
    (Path(record["path"]) / "impact_report.json").write_text("{}")
    with pytest.raises(AdminError, match="Archivnachweis"):
        store.decide(
            rid,
            "approve",
            "reviewer",
            "tampered",
            impact_id=row["id"],
            report_hash=row["report_hash"],
        )


def test_s3_archive_failure_blocks_then_can_retry_without_rebuild(setup, monkeypatch):
    from platform_admin import object_store

    store, _gh = setup
    objects = FakeObjects()
    rid = proposed(store)
    bronze(store.data)
    monkeypatch.setenv("ADMIN_OBJECT_STORE", "s3")
    monkeypatch.setattr(object_store, "Objects", lambda: objects)
    original = objects.immutable
    objects.immutable = lambda *a: (_ for _ in ()).throw(OSError("offline"))
    result = run_one(store, runner=synthetic_runner())
    assert result["status"] == "ARCHIVE_PENDING"
    with pytest.raises(AdminError):
        store.decide(
            rid,
            "approve",
            "reviewer",
            "not archived",
            impact_id=result["id"],
            report_hash=store.history()["impacts"][0]["report_hash"],
        )
    objects.immutable = original
    impact_archive.retry(store, result["id"])
    assert store.history()["impacts"][0]["status"] == "READY"
    record, _manifest = impact_archive.checked(store, result["id"], require_remote=True)
    assert objects.calls[-1].endswith("archive_manifest.json") and record["remote_verified_at"]


@pytest.mark.parametrize("failure", ["source", "truncated", "settings"])
def test_runtime_must_match_git_before_simulation(setup, failure):
    store, gh = setup
    if failure == "source":
        gh.sources["src/crime/unreviewed.py"] = "different"
    if failure == "truncated":
        gh.truncated = True
    if failure == "settings":
        gh.contents["config/platform_admin_settings.json"] = "{}"
    rid = proposed(store)
    bronze(store.data)
    result = run_one(store, runner=synthetic_runner())
    assert result["status"] == "FAILED"
    assert store.history()["archives"][0]["revision_id"] == rid


def test_new_source_data_does_not_need_pr(setup):
    store, gh = setup
    rid = store.propose(
        "data", {"task": "rebuild"}, store.current("data")["id"], "engineer", "new data"
    )
    bronze(store.data)
    result = run_one(store, runner=synthetic_runner())
    row = next(i for i in store.history()["impacts"] if i["id"] == result["id"])
    store.decide(
        rid,
        "approve",
        "reviewer",
        "reviewed data",
        impact_id=row["id"],
        report_hash=row["report_hash"],
    )
    assert candidates.active_id(store) is not None
    assert not any(method in {"POST", "PUT"} for method, path, value in gh.calls)


def test_prepared_release_can_resume_after_database_transition_crash(setup):
    store, _gh = setup
    rid, row = open_review(store)
    first = merge_review(store, rid)
    with store.db() as c:
        c.execute(
            "UPDATE impact SET status='AWAITING_GIT',published_release_id=NULL,published_manifest_hash=NULL WHERE id=?",
            (row["id"],),
        )
    second = merge_review(store, rid)
    assert second["release_id"] == first["release_id"]
    publish(store, row["id"])


def test_new_endpoints_enforce_roles_and_authentication(setup):
    store, _gh = setup
    # Local transport still requires a token for archive access; cloud roles are
    # enforced centrally by WRITE_ROLES, tested using signed JWTs in test_ln2.
    client = create_app(
        store, operator="engineer", token="secret", config={"ADMIN_AUTH": "local"}
    ).test_client()
    assert client.get("/api/impact-archive?id=unknown").status_code == 401
    from platform_admin.auth import WRITE_ROLES

    assert WRITE_ROLES["/api/git-withdraw"] == {"reviewer"}
    assert "viewer" not in WRITE_ROLES["/api/archive-retry"]


def test_review_and_merge_events_are_archived_without_rewriting_report(setup):
    from pathlib import Path

    store, _gh = setup
    rid, row = open_review(store)
    record, _manifest = impact_archive.checked(store, row["id"])
    before = (Path(record["path"]) / "archive_manifest.json").read_bytes()
    merge_review(store, rid)
    impact_archive.persist_events(store, row["id"])
    files = list((Path(record["path"]) / "events").glob("*.json"))
    assert {json.loads(p.read_text())["action"] for p in files} == {
        "REVIEW_APPROVED",
        "MERGE_REQUESTED",
        "MERGE_VERIFIED",
    }
    assert (Path(record["path"]) / "archive_manifest.json").read_bytes() == before


def test_quarantined_merge_can_be_withdrawn_only_after_corrective_git_change(setup):
    store, gh = setup
    rid, _row = open_review(store)
    gh.bad_merge_tree = True
    with pytest.raises(AdminError):
        merge_review(store, rid)
    with writer_lock(store), pytest.raises(AdminError):
        coupled_git.withdraw(store, rid, "reviewer", "quarantined")
    from platform_admin.store import DEFAULT_SETTINGS, encode

    gh.contents["config/platform_admin_settings.json"] = encode(DEFAULT_SETTINGS)
    gh.main = "corrective-commit"
    with writer_lock(store):
        result = coupled_git.withdraw(
            store, rid, "reviewer", "Corrective PR merged; active baseline restored"
        )
    assert result["status"] == "WITHDRAWN"
    assert candidates.active_id(store) is None


def test_local_archive_failure_before_snapshot_can_retry(setup, monkeypatch):
    store, _gh = setup
    proposed(store)
    bronze(store.data)
    original = impact_archive.persist
    monkeypatch.setattr(
        impact_archive, "persist", lambda *a, **kw: (_ for _ in ()).throw(OSError("disk full"))
    )
    result = run_one(store, runner=synthetic_runner())
    assert result["status"] == "ARCHIVE_PENDING"
    assert store.history()["archives"] == []
    monkeypatch.setattr(impact_archive, "persist", original)
    impact_archive.retry(store, result["id"])
    assert store.history()["impacts"][0]["status"] == "READY"
    impact_archive.checked(store, result["id"])


# ADMIN_GIT_SCHUTZ: produktiv (default) checks GitHub's branch protection;
# entwicklung replaces it with the console's own check of the PR head.


def test_production_is_the_default_and_needs_branch_protection(setup):
    store, gh = setup
    gh.protected = False
    rid, _row = open_review(store)
    with pytest.raises(AdminError, match="Main braucht"):
        merge_review(store, rid)
    assert gh.merges == 0


def test_development_merges_without_branch_protection_and_says_so(setup, monkeypatch):
    monkeypatch.setenv("ADMIN_GIT_SCHUTZ", "entwicklung")
    store, gh = setup
    gh.protected = False
    rid, row = open_review(store)
    d = merge_review(store, rid)
    assert gh.merges == 1 and d["git_protection"] == "entwicklung"
    assert not any(p.endswith("/protection") for _m, p, _v in gh.calls)
    evidence = next(e for e in gh.tree_entries if e["path"].startswith("config/admin_reviews/"))
    assert json.loads(evidence["content"])["git_protection"] == "entwicklung"
    assert "entwicklung" in gh.pr["body"]
    release = publish(store, row["id"])
    assert release == candidates.active_id(store)


@pytest.mark.parametrize(
    "runs",
    [
        [],
        [{"name": "tests", "status": "completed", "conclusion": "failure"}],
        [{"name": "tests", "status": "in_progress", "conclusion": None}],
        [{"name": "lint", "status": "completed", "conclusion": "success"},
         {"name": "tests", "status": "completed", "conclusion": "cancelled"}],
        [{"name": "windows", "status": "completed", "conclusion": "skipped"}],
    ],
    ids=["none", "failed", "running", "one-cancelled", "only-skipped"],
)
def test_development_never_merges_without_green_ci(setup, monkeypatch, runs):
    monkeypatch.setenv("ADMIN_GIT_SCHUTZ", "entwicklung")
    store, gh = setup
    gh.protected = False
    gh.workflow_runs = runs
    rid, _row = open_review(store)
    with pytest.raises(AdminError, match="CI"):
        merge_review(store, rid)
    assert gh.merges == 0 and candidates.active_id(store) is None


def test_development_accepts_skipped_runs_beside_a_green_one(setup, monkeypatch):
    monkeypatch.setenv("ADMIN_GIT_SCHUTZ", "entwicklung")
    store, gh = setup
    gh.protected = False
    gh.workflow_runs = [{"name": "tests", "status": "completed", "conclusion": "success"},
                     {"name": "windows", "status": "completed", "conclusion": "skipped"}]
    rid, _row = open_review(store)
    merge_review(store, rid)
    assert gh.merges == 1


def test_development_reads_workflow_runs_of_the_exact_head(setup, monkeypatch):
    # Green runs on another commit say nothing about this PR head; and the
    # console asks the Actions endpoint, the one a fine-grained token may read.
    monkeypatch.setenv("ADMIN_GIT_SCHUTZ", "entwicklung")
    store, gh = setup
    gh.protected = False
    gh.pr_head = "another-commit"
    rid, _row = open_review(store)
    with pytest.raises(AdminError, match="kein Lauf"):
        merge_review(store, rid)
    assert gh.merges == 0
    assert not any("/check-runs" in path for _m, path, _v in gh.calls)
    assert any(path.startswith("/actions/runs?head_sha=candidate-head")
               for _m, path, _v in gh.calls)


def test_an_unknown_protection_mode_is_refused(setup, monkeypatch):
    monkeypatch.setenv("ADMIN_GIT_SCHUTZ", "aus")
    with pytest.raises(AdminError, match="produktiv oder entwicklung"):
        gitops.protection_mode()
    with pytest.raises(AdminError, match="produktiv oder entwicklung"):
        create_app(setup[0], operator="x", token="t")


def test_the_overview_shows_the_protection_mode(setup, monkeypatch):
    from platform_admin import operations
    store, _gh = setup
    assert operations.overview(store)["git_protection"] == "produktiv"
    monkeypatch.setenv("ADMIN_GIT_SCHUTZ", "entwicklung")
    assert operations.overview(store)["git_protection"] == "entwicklung"
