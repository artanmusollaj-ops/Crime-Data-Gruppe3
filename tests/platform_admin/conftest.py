"""Existing suites exercise the explicitly supported separate/local mode.
The coupled suite overrides this fixture and covers the secure default.
"""

import copy

import pytest


@pytest.fixture(autouse=True)
def release_mode_for_legacy_tests(monkeypatch):
    monkeypatch.setenv("ADMIN_RELEASE_MODE", "separate")


@pytest.fixture(autouse=True)
def git_protection_from_test_only(monkeypatch):
    """No test inherits ADMIN_GIT_SCHUTZ from the developer's shell."""
    monkeypatch.delenv("ADMIN_GIT_SCHUTZ", raising=False)


@pytest.fixture(autouse=True)
def default_settings_baseline(monkeypatch):
    """Every console test starts from DEFAULT_SETTINGS, not from the repository.

    Since 7.11.2026 ``config/platform_admin_settings.json`` is in Git (six
    jobs, 2021-2026). The suites here are built around the defaults - job
    positions, the 2024 scope and its nine build commands - and 87 of them
    failed once Store.initialize read the real file. That the real file is
    valid and imported is held by ``tests/test_konsole_einstellungen.py``.
    """
    from platform_admin import store

    monkeypatch.setattr(store, "repository_settings",
                        lambda project: copy.deepcopy(store.DEFAULT_SETTINGS))
