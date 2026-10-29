"""Existing suites exercise the explicitly supported separate/local mode.
The coupled suite overrides this fixture and covers the secure default.
"""

import pytest


@pytest.fixture(autouse=True)
def release_mode_for_legacy_tests(monkeypatch):
    monkeypatch.setenv("ADMIN_RELEASE_MODE", "separate")
