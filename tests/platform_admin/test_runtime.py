"""Where the console takes its role bindings from on the server."""

import json

import pytest

from platform_admin.runtime import settings


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    monkeypatch.delenv("ADMIN_ROLE_BINDINGS", raising=False)
    monkeypatch.delenv("ADMIN_ROLE_BINDINGS_FILE", raising=False)


def test_bindings_come_from_the_environment(monkeypatch):
    # srv01 passes secrets and settings through the stack's .env; a file would
    # need a mount that exists nowhere else in the stack.
    monkeypatch.setenv("ADMIN_ROLE_BINDINGS", '{"sub-1": ["viewer"]}')
    assert settings()["ADMIN_ROLE_BINDINGS"] == {"sub-1": ["viewer"]}


def test_a_file_still_works(monkeypatch, tmp_path):
    path = tmp_path / "roles.json"
    path.write_text(json.dumps({"sub-2": ["reviewer"]}))
    monkeypatch.setenv("ADMIN_ROLE_BINDINGS_FILE", str(path))
    assert settings()["ADMIN_ROLE_BINDINGS"] == {"sub-2": ["reviewer"]}


def test_both_at_once_is_refused(monkeypatch, tmp_path):
    path = tmp_path / "roles.json"
    path.write_text("{}")
    monkeypatch.setenv("ADMIN_ROLE_BINDINGS_FILE", str(path))
    monkeypatch.setenv("ADMIN_ROLE_BINDINGS", "{}")
    with pytest.raises(ValueError, match="nur eines"):
        settings()


def test_nothing_set_means_nobody_has_a_role():
    assert settings()["ADMIN_ROLE_BINDINGS"] == {}


def test_the_compose_healthcheck_gets_an_answer(tmp_path):
    """docker-compose.srv01.yml asks /healthz with Host: admin and no login.
    If Access-mode authentication or host checking refused it, the service
    would be "unhealthy" while it runs."""
    from platform_admin.store import Store
    from platform_admin.web import create_app

    from .helpers import PROJECT

    store = Store(PROJECT, tmp_path / "data")
    store.initialize("bootstrap")
    app = create_app(store, config={
        "ADMIN_AUTH": "cloudflare",
        "CF_ACCESS_ISSUER": "https://team.cloudflareaccess.com",
        "CF_ACCESS_AUD": "aud",
        "ADMIN_PUBLIC_ORIGIN": "https://urbancrime-admin.datenwerft.ch",
    })
    response = app.test_client().get("/healthz", headers={"Host": "admin"})
    assert response.status_code == 200
    assert app.test_client().get("/api/state", headers={"Host": "admin"}).status_code in {401, 403}
