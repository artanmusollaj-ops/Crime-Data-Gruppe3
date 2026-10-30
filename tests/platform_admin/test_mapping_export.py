"""What a mapping change exports to Git, byte for byte.

The crosswalks under config/ are generated (tools/build_*_mapping.py) and held
against their generators; a console change inside them would break that test
on every pull request, and nothing could ever be merged. A reviewed correction
is one row in mapping_overrides.csv instead, which silver applies on top.
"""

import shutil

from platform_admin import gitops
from platform_admin.store import Store

from .helpers import PROJECT


def export(store, city, code, target):
    parent = store.current("mapping")["id"]
    rid = store.propose_mapping(city, code, target, parent, "engineer", "Probe")
    return gitops.changes(store, store.get(rid))


def test_a_mapping_change_exports_one_override_row_and_no_crosswalk(tmp_path):
    store = Store(PROJECT, tmp_path / "data")
    store.initialize("bootstrap")

    (path, (before, after)), = export(store, "chicago", "0110", "09B").items()

    assert path == "config/mapping_overrides.csv"
    assert before == (PROJECT / path).read_text(encoding="utf-8")
    assert "\r" not in after, "LF like the repository copy"
    assert after.splitlines()[1:] == ["chicago,0110,09B,Probe"]


def test_choosing_the_crosswalk_target_again_removes_the_override(tmp_path):
    project = tmp_path / "project"
    shutil.copytree(PROJECT / "config", project / "config")
    (project / "config" / "mapping_overrides.csv").write_text(
        "city,source_code,nibrs_code,reason\nchicago,0110,09B,earlier review\n",
        encoding="utf-8")
    store = Store(project, tmp_path / "data")
    store.initialize("bootstrap")

    (_path, (before, after)), = export(store, "chicago", "0110", "09A").items()

    assert before.splitlines()[1:] == ["chicago,0110,09B,earlier review"]
    assert after.splitlines()[1:] == [], "09A is the crosswalk's own target"
