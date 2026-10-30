"""LN2 security, durable operations and remote boundary regression tests."""

import base64
import copy
import io
import json
import tarfile
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from platform_admin.store import Store, AdminError
from platform_admin.web import create_app
from platform_admin import gitops, object_store, operations
from .helpers import PROJECT, approve


@pytest.fixture
def store(tmp_path):
    s = Store(PROJECT, tmp_path / "data")
    s.initialize("bootstrap")
    return s


@pytest.fixture
def signed_client(store, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(
        jwt.PyJWKClient,
        "get_signing_key_from_jwt",
        lambda self, raw: SimpleNamespace(key=key.public_key()),
    )
    app = create_app(
        store,
        config={
            "ADMIN_AUTH": "cloudflare",
            "CF_ACCESS_ISSUER": "https://team.cloudflareaccess.com",
            "CF_ACCESS_AUD": "our-aud",
            "ADMIN_PUBLIC_ORIGIN": "https://admin.example.org",
            "ADMIN_ROLE_BINDINGS": {
                "viewer": ["viewer"],
                "eng": ["engineer"],
                "reviewer": ["reviewer"],
            },
            "ADMIN_METRICS_TOKEN": "metrics-secret",
        },
    )

    def headers(sub="viewer", **claims):
        payload = dict(
            iss="https://team.cloudflareaccess.com",
            aud="our-aud",
            sub=sub,
            email="display@example.org",
            iat=int(time.time()),
            exp=int(time.time()) + 300,
        )
        payload.update(claims)
        return {
            "Cf-Access-Jwt-Assertion": jwt.encode(payload, key, algorithm="RS256"),
            "Origin": "https://admin.example.org",
            "X-Admin-Request": "1",
        }

    return app.test_client(), headers


def test_identity_is_signed_subject_not_supplied_actor(signed_client):
    client, headers = signed_client
    response = client.get("/api/state", base_url="https://admin.example.org", headers=headers())
    assert response.status_code == 200
    assert response.json["operator"] == "viewer"
    assert response.json["identity"] == "display@example.org"
    assert response.json["roles"] == ["viewer"]


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "other"},
        {"iss": "https://evil.cloudflareaccess.com"},
        {"exp": 0},
        {"sub": "unassigned"},
    ],
)
def test_jwt_rejects_wrong_scope_expired_or_unassigned(signed_client, claims):
    client, headers = signed_client
    assert client.get(
        "/api/state", base_url="https://admin.example.org", headers=headers(**claims)
    ).status_code in {401, 403}


def test_missing_jwt_and_spoofed_email_rejected(signed_client):
    client, _ = signed_client
    assert (
        client.get(
            "/api/state",
            base_url="https://admin.example.org",
            headers={"Cf-Access-Authenticated-User-Email": "reviewer"},
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "route",
    [
        "mapping",
        "settings",
        "decision",
        "rebase",
        "impact-retry",
        "publish-approved",
        "job",
        "git-open",
        "git-merge",
        "git-withdraw",
        "archive-retry",
        "backup",
        "serving",
    ],
)
def test_viewer_cannot_write_any_route(signed_client, route):
    client, headers = signed_client
    assert (
        client.post(
            "/api/" + route, json={}, base_url="https://admin.example.org", headers=headers()
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "header,value",
    [("Origin", "https://evil.invalid"), ("Origin", None), ("X-Admin-Request", None)],
)
def test_engineer_csrf_rejected(signed_client, header, value):
    client, headers = signed_client
    h = headers("eng")
    if value is None:
        h.pop(header)
    else:
        h[header] = value
    assert (
        client.post(
            "/api/settings", json={}, base_url="https://admin.example.org", headers=h
        ).status_code
        == 403
    )


def test_engineer_cannot_approve_and_actor_is_not_json(signed_client, store):
    client, headers = signed_client
    h = headers("eng")
    assert (
        client.post(
            "/api/decision", json={}, base_url="https://admin.example.org", headers=h
        ).status_code
        == 403
    )
    current = store.current("settings")
    payload = copy.deepcopy(current["payload"])
    payload["maximum_unmapped_ratio"] = 0.04
    response = client.post(
        "/api/settings",
        json={
            "payload": payload,
            "parent": current["id"],
            "reason": "test",
            "operator": "reviewer",
        },
        base_url="https://admin.example.org",
        headers=h,
    )
    assert response.status_code == 200
    assert store.get(response.json["result"])["actor"] == "eng"


def test_metrics_requires_separate_secret(signed_client):
    client, headers = signed_client
    assert (
        client.get("/metrics", base_url="http://admin:8000", headers=headers()).status_code == 401
    )
    response = client.get(
        "/metrics", base_url="http://admin:8000", headers={"Authorization": "Bearer metrics-secret"}
    )
    assert response.status_code == 200
    assert b"crime_admin_jobs" in response.data


def test_bad_json_and_body_limit(signed_client):
    client, headers = signed_client
    h = headers("eng")
    assert (
        client.post(
            "/api/settings", json=[], base_url="https://admin.example.org", headers=h
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/settings",
            data="x" * 1_000_001,
            content_type="application/json",
            base_url="https://admin.example.org",
            headers=h,
        ).status_code
        == 413
    )


def test_operations_deduplicate_and_preserve_failure(store, monkeypatch):
    oid = operations.submit(store, "backup", {"reason": "save"}, "operator")
    with pytest.raises(AdminError, match="bereits"):
        operations.submit(store, "backup", {"reason": "save"}, "operator")
    monkeypatch.setattr(
        object_store, "backup", lambda s: (_ for _ in ()).throw(RuntimeError("secret-value"))
    )
    result = operations.run_operation(store)
    assert result["id"] == oid and result["status"] == "FAILED"
    assert "secret-value" not in json.dumps(operations.overview(store))


def test_running_operation_needs_explicit_recovery(store):
    oid = operations.submit(store, "backup", {"reason": "save"}, "operator")
    with store.db() as c:
        c.execute("UPDATE operation SET status='RUNNING'")
    with pytest.raises(AdminError, match="Recovery"):
        operations.run_operation(store)
    operations.recover(store, oid, "operator", "Process confirmed stopped")
    assert operations.overview(store)["operations"][0]["status"] == "FAILED"


class FakeObjects:
    def __init__(self):
        self.data = {}
        self.calls = []
        self.fail = None

    def read(self, key):
        return self.data.get(key), "etag" if key in self.data else None

    def immutable(self, path, key):
        if self.fail == key:
            raise OSError("offline")
        body = Path(path).read_bytes()
        if key in self.data and self.data[key] != body:
            raise AdminError("changed")
        self.data[key] = body
        self.calls.append(key)

    def pointer(self, key, body, etag):
        assert etag == ("etag" if key in self.data else None)
        self.data[key] = body
        self.calls.append(key)


def approved_revision(store):
    current = store.current("settings")
    payload = copy.deepcopy(current["payload"])
    payload["maximum_unmapped_ratio"] = 0.04
    rid = store.propose("settings", payload, current["id"], "engineer", "test")
    row = approve(store, rid, actor="reviewer")
    return rid, next(i for i in store.history()["impacts"] if i["id"] == row["id"])


def test_s3_pointer_last_and_retry_and_stale_guard(store):
    _, row = approved_revision(store)
    from platform_admin.candidates import release_path

    target = release_path(store, row["published_release_id"])
    objects = FakeObjects()
    object_store.publish_release(store, target, None, objects)
    assert objects.calls[-1] == "releases/AKTUELL.json"
    object_store.publish_release(store, target, None, objects)
    objects.data["releases/AKTUELL.json"] = b'{"release_id":"someone-else"}'
    with pytest.raises(AdminError, match="Releasebasis"):
        object_store.publish_release(store, target, None, objects)


def test_s3_failure_does_not_switch_pointer(store):
    _, row = approved_revision(store)
    from platform_admin.candidates import release_path

    target = release_path(store, row["published_release_id"])
    objects = FakeObjects()
    objects.fail = "releases/" + target.name + "/release.json"
    with pytest.raises(OSError):
        object_store.publish_release(store, target, None, objects)
    assert "releases/AKTUELL.json" not in objects.data


def test_deferred_publication_preserves_old_pointer(store, monkeypatch):
    monkeypatch.setenv("ADMIN_DEFER_PUBLICATION", "1")
    _, row = approved_revision(store)
    from platform_admin.candidates import active_id, finish_publication

    assert row["status"] == "APPROVED_PENDING_PUBLICATION" and active_id(store) is None
    monkeypatch.setenv("ADMIN_OBJECT_STORE", "s3")
    monkeypatch.setattr(
        object_store, "publish_release", lambda *a: (_ for _ in ()).throw(OSError("offline"))
    )
    with pytest.raises(OSError):
        finish_publication(store, row["id"])
    assert active_id(store) is None
    assert store.history()["impacts"][0]["status"] == "APPROVED_PENDING_PUBLICATION"


def test_backup_and_restore_roundtrip(store, tmp_path):
    objects = FakeObjects()
    info = object_store.backup(store, objects)
    path = tmp_path / "backup.tar.gz"
    path.write_bytes(objects.data[info["key"]])
    dest = tmp_path / "restore"
    object_store.restore_archive(path, dest)
    import sqlite3

    with sqlite3.connect(dest / "admin/control.sqlite") as db:
        assert db.execute("SELECT count(*) FROM head").fetchone()[0] == 3
    with pytest.raises(AdminError, match="leer"):
        object_store.restore_archive(path, dest)


def test_restore_rejects_traversal(tmp_path):
    path = tmp_path / "bad.tar.gz"
    with tarfile.open(path, "w:gz") as t:
        member = tarfile.TarInfo("../outside")
        member.size = 1
        t.addfile(member, io.BytesIO(b"x"))
    with pytest.raises(AdminError, match="Unsicher"):
        object_store.restore_archive(path, tmp_path / "dest")
    assert not (tmp_path / "outside").exists()


class FakeGitHub:
    repo = "owner/repo"
    branch = "main"

    def __init__(self):
        self.calls = []
        self.main = "base"
        self.ref = None
        self.pr = None
        self.conflict = False
        self.clean = True
        self.protected = True
        self.merges = 0

    def call(self, method, path, value=None, missing=False):
        self.calls.append((method, path, value))
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if path.startswith("/contents/"):
            return {"content": base64.b64encode(b"{}").decode()} if self.conflict else None
        if path == "/git/commits/base":
            return {"tree": {"sha": "tree"}}
        if path == "/git/trees":
            return {"sha": "newtree"}
        if path == "/git/commits":
            return {"sha": "commit"}
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
                "html_url": "https://github.com/owner/repo/pull/1",
                "head": {"sha": "commit"},
                "base": {"sha": "base", "ref": "main"},
                "state": "open",
                "merged": False,
                "mergeable": True,
                "mergeable_state": "clean",
            }
            return self.pr
        if path == "/pulls/1":
            return {**self.pr, "mergeable_state": "clean" if self.clean else "blocked"}
        if path.endswith("/protection"):
            return {
                "required_status_checks": {"strict": self.protected, "contexts": ["ci"]},
                "required_pull_request_reviews": {
                    "required_approving_review_count": 1,
                    "dismiss_stale_reviews": True,
                },
                "enforce_admins": {"enabled": True},
            }
        if path == "/pulls/1/merge":
            assert value["sha"] == "commit"
            self.merges += 1
            self.pr.update(merged=True, merge_commit_sha="merged")
            return {"merged": True, "sha": "merged"}
        raise AssertionError((method, path))


def test_git_unapproved_rejected(store):
    with pytest.raises(AdminError):
        gitops.approved(store, store.current("settings")["id"])


def test_git_commit_ref_pr_and_idempotent_merge(store):
    rid, _ = approved_revision(store)
    gh = FakeGitHub()
    result = gitops.open_pr(store, rid, "engineer", gh)
    assert result["commit_sha"] == "commit" and result["number"] == 1
    entries = next(v["tree"] for m, p, v in gh.calls if p == "/git/trees")
    assert {x["path"] for x in entries} == {
        "config/platform_admin_settings.json",
        "config/admin_reviews/" + rid + ".json",
    }
    assert gitops.open_pr(store, rid, "engineer", gh) == result
    assert gitops.merge_pr(store, rid, "reviewer", gh)["state"] == "MERGED"
    gitops.merge_pr(store, rid, "reviewer", gh)
    assert gh.merges == 1


@pytest.mark.parametrize("failure", ["conflict", "main", "head", "ci", "protection", "self"])
def test_git_conflict_and_merge_gates(store, failure):
    rid, _ = approved_revision(store)
    gh = FakeGitHub()
    if failure == "conflict":
        gh.conflict = True
        with pytest.raises(AdminError, match="Git-Konflikt"):
            gitops.open_pr(store, rid, "engineer", gh)
        assert gh.ref is None
        return
    gitops.open_pr(store, rid, "engineer", gh)
    if failure == "main":
        gh.main = "new-main"
    if failure == "head":
        gh.pr["head"]["sha"] = "other"
    if failure == "ci":
        gh.clean = False
    if failure == "protection":
        gh.protected = False
    with pytest.raises(AdminError):
        gitops.merge_pr(store, rid, "engineer" if failure == "self" else "reviewer", gh)
    assert gh.merges == 0


@pytest.mark.parametrize("failure", [None, "serving.load_elasticsearch", "serving.build_kibana", "serving.pruefe_stand"])
def test_serving_switches_only_after_valid_build(store, monkeypatch, failure):
    from platform_admin import serving_export, jobs, candidates
    _rid, row = approved_revision(store)
    calls = []

    def execute(work, commands, log):
        for command in commands:
            calls.append(command[2])
            assert str(store.data) in command
            if command[2] == failure:
                raise AdminError("Test service failure")

    monkeypatch.setattr(jobs, "execute_commands", execute)
    active = candidates.active_id(store)
    if failure:
        with pytest.raises(AdminError):
            serving_export.publish(store, row["published_release_id"])
    else:
        assert serving_export.publish(store, active)["release_id"] == active
    assert candidates.active_id(store) == active
    assert calls[0] == "serving.load_elasticsearch"
    assert not any("clickhouse" in module for module in calls)
    status = operations.overview(store)["services"]
    assert status["analysis"]["status"] == ("PARTIAL" if failure else "SUCCEEDED")
    if failure == "serving.build_kibana":
        assert status["elasticsearch"]["release_id"] == active
        assert "analysis_check" not in status


def test_archive_complete_and_success_but_not_incomplete(store):
    objects = FakeObjects()
    for status in ["complete", "success", "running"]:
        folder = store.data / "bronze" / status
        folder.mkdir(parents=True)
        (folder / "manifest.json").write_text(json.dumps({"status": status}))
        (folder / "part.parquet").write_bytes(b"test-data")
    object_store.archive_inputs(store, objects)
    assert "bronze/complete/part.parquet" in objects.data
    assert "bronze/success/part.parquet" in objects.data
    assert not any("running" in key for key in objects.data)
