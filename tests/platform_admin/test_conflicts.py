import copy
from pathlib import Path

import pytest

from platform_admin.conflicts import all_pending, changes
from platform_admin.store import AdminError, Store


@pytest.fixture
def store(tmp_path):
    result = Store(Path(__file__).resolve().parents[2], tmp_path / "data")
    result.initialize("bootstrap")
    return result


def test_overlapping_mapping_shows_author_line_and_blocks_approval(store):
    parent = store.current("mapping")["id"]
    a = store.propose_mapping("chicago", "0110", "09A", parent, "Alice", "Review A")
    b = store.propose_mapping("chicago", "0110", "26A", parent, "Bob", "Review B")
    check = all_pending(store)[a]
    assert check["blocked"] and not check["stale"]
    other = check["overlaps"][0]
    assert other["actor"] == "Bob" and other["revision_id"] == b
    assert other["impact"]["status"] == "QUEUED"
    item = other["locations"][0]
    assert "iucr=0110" in item["location"]
    assert item["mine"]["after"]["line"] >= 2
    assert item["theirs"]["after"]["value"]["ibr_code"] == "26A"
    with pytest.raises(AdminError, match="Ueberlappende.*Bob"):
        store.decide(a, "approve", "Reviewer", "Review")
    store.decide(b, "reject", "Reviewer", "Konkurrierende Variante verworfen")
    assert not all_pending(store)[a]["blocked"]
    assert b not in all_pending(store)


def test_settings_jobs_matched_by_name_not_position(store):
    base = store.current("settings")
    a = copy.deepcopy(base["payload"])
    a["jobs"][2]["lookback_days"] = 30
    b = copy.deepcopy(base["payload"])
    b["jobs"].reverse()
    b["jobs"][0]["at_utc"] = "09:00"
    ra = store.propose("settings", a, base["id"], "Alice", "Lookback")
    rb = store.propose("settings", b, base["id"], "Bob", "Zeitplan")
    assert not all_pending(store)[ra]["blocked"]
    assert not all_pending(store)[rb]["blocked"]
    next(job for job in b["jobs"] if job["name"] == "chicago_daily")["lookback_days"] = 90
    rc = store.propose("settings", b, base["id"], "Carol", "Lookback")
    check = all_pending(store)[ra]
    assert check["overlaps"][0]["revision_id"] == rc
    assert check["overlaps"][0]["locations"][0]["location"] == "/jobs/chicago_daily/lookback_days"


def test_different_rows_and_cities_are_independent(store):
    parent = store.current("mapping")["id"]
    a = store.propose_mapping("chicago", "0110", "09A", parent, "Alice", "A")
    store.propose_mapping("detroit", "2403", "26A", parent, "Bob", "B")
    assert not all_pending(store)[a]["blocked"]


def test_deleted_job_conflicts_with_field_change(store):
    base = store.current("settings")
    a = copy.deepcopy(base["payload"])
    a["jobs"] = [j for j in a["jobs"] if j["name"] != "chicago_daily"]
    b = copy.deepcopy(base["payload"])
    b["jobs"][2]["enabled"] = True
    ra = store.propose("settings", a, base["id"], "Alice", "Entfernen")
    store.propose("settings", b, base["id"], "Bob", "Aktivieren")
    assert all_pending(store)[ra]["blocked"]


def test_reordering_settings_jobs_alone_is_not_overlap():
    assert (
        changes(
            "settings",
            {"jobs": [{"name": "a"}, {"name": "b"}]},
            {"jobs": [{"name": "b"}, {"name": "a"}]},
        )
        == {}
    )


def test_three_way_settings_merge_preserves_other_changes(store):
    from platform_admin.conflicts import merge_payload

    base = store.current("settings")["payload"]
    mine, other = copy.deepcopy(base), copy.deepcopy(base)
    mine["jobs"][2]["lookback_days"] = 30
    other["jobs"][2]["enabled"] = True
    merged = merge_payload("settings", base, mine, other)
    job = next(j for j in merged["jobs"] if j["name"] == "chicago_daily")
    assert job["enabled"] and job["lookback_days"] == 30
    other["jobs"][2]["lookback_days"] = 90
    with pytest.raises(AdminError, match="Merge-Konflikt.*lookback_days"):
        merge_payload("settings", base, mine, other)


def test_rebase_replaces_own_revision_and_queues_new_impact_atomically(store):
    from platform_admin.conflicts import rebase

    base = store.current("settings")
    payload = copy.deepcopy(base["payload"])
    payload["maximum_unmapped_ratio"] = 0.02
    old = store.propose("settings", payload, base["id"], "Alice", "Quote")
    with pytest.raises(AdminError, match="Nur der Autor"):
        rebase(store, old, "Bob", "Unbefugt")
    new = rebase(store, old, "Alice", "Basis aktualisieren")
    history = store.history()
    assert next(r for r in history["revisions"] if r["id"] == old)["decision"] == "superseded"
    assert next(i for i in history["impacts"] if i["revision_id"] == old)["status"] == "SUPERSEDED"
    assert next(i for i in history["impacts"] if i["revision_id"] == new)["status"] == "QUEUED"
    assert not all_pending(store)[new]["blocked"]
    with pytest.raises(AdminError, match="bereits entschieden"):
        rebase(store, old, "Alice", "Noch einmal")
    assert len(store.history()["revisions"]) == len(history["revisions"])


def test_three_way_mapping_merge_preserves_independent_rows(store):
    from platform_admin.conflicts import merge_payload

    base = store.current("mapping")
    a = store.propose_mapping("chicago", "0110", "09A", base["id"], "Alice", "A")
    b = store.propose_mapping("detroit", "2403", "26A", base["id"], "Bob", "B")
    merged = merge_payload(
        "mapping", base["payload"], store.get(a)["payload"], store.get(b)["payload"]
    )
    assert merged["iucr_nibrs_mapping.csv"] == store.get(a)["payload"]["iucr_nibrs_mapping.csv"]
    assert merged["micr_nibrs_mapping.csv"] == store.get(b)["payload"]["micr_nibrs_mapping.csv"]
