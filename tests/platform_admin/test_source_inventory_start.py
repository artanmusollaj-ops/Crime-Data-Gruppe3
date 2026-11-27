"""The start page does not wait for every Bronze manifest.

Until 27.11.2026 ``source_status`` read all of them, one S3 GET after another:
136 manifests, 10.5 s on srv01, and ``refresh()`` held the whole page back
until they were in. It shows 20 runs per city.
"""
import json
import re
from pathlib import Path

import pytest
from platform_admin import integration, sources
from platform_admin.store import Store

from .helpers import PROJECT

INDEX = Path(sources.__file__).parent / "static" / "index.html"


@pytest.fixture
def store(tmp_path):
    result = Store(PROJECT, tmp_path / "data")
    result.initialize("bootstrap")
    return result


def _runs(store, city, count):
    for i in range(count):
        manifest = store.data / f"bronze/city={city}/year=2024/run_{i:03d}/manifest.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text(json.dumps({"run_id": f"{city}-{i:03d}", "status": "complete"}))
    hidden = store.data / f"bronze/city={city}/year=2024/.run_999.part/manifest.json"
    hidden.parent.mkdir(parents=True)
    hidden.write_text('{"run_id": "unfertig", "status": "complete"}')


def test_only_the_shown_runs_are_read(store, monkeypatch):
    for city in ("chicago", "detroit"):
        _runs(store, city, 25)
    read = []
    original = integration.manifest_text
    monkeypatch.setattr(integration, "manifest_text",
                        lambda s, rel: read.append(rel) or original(s, rel))
    result = sources.source_status(store)
    assert len(read) == 2 * sources.SHOWN_RUNS
    for item in result:
        city = item["city"]
        assert item["run_count"] == 25
        assert [r["run_id"] for r in item["runs"]] == [
            f"{city}-{i:03d}" for i in range(24, 4, -1)]


def test_an_unreadable_manifest_keeps_its_place(store):
    _runs(store, "detroit", 3)
    (store.data / "bronze/city=detroit/year=2024/run_002/manifest.json").write_text("{kaputt")
    runs = sources.source_status(store)[1]["runs"]
    assert [(r["run_id"], r["status"]) for r in runs] == [
        ("run_002", "INVALID_MANIFEST"), ("detroit-001", "complete"),
        ("detroit-000", "complete")]


def test_refresh_does_not_wait_for_the_source_inventory():
    html = INDEX.read_text(encoding="utf-8")
    body = re.search(r"async function refresh\(\)\{(.*?)\n\}\n", html, re.S).group(1)
    awaited = [line for line in body.splitlines()
               if "await" in line and "api('sources')" in line]
    assert not awaited, awaited
    assert "api('sources')" in body
