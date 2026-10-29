import json
import pytest
from serving.release_reader import approved_root


def test_session_is_pinned_and_candidate_rejected(tmp_path):
    (tmp_path / "admin").mkdir()
    (tmp_path / "admin/managed.json").write_text('{"baseline_release_id":"old"}')
    releases = tmp_path / "releases"
    old = releases / "release=old"
    new = releases / "release=new"
    old.mkdir(parents=True)
    (new / "admin").mkdir(parents=True)
    pointer = releases / "AKTUELL.json"
    pointer.write_text(json.dumps({"release_id":"old", "path":"releases/release=old"}))
    session_root = approved_root(tmp_path)
    pointer.write_text(json.dumps({"release_id":"new", "path":"releases/release=new"}))
    (new / "admin/approval.json").write_text('{"state":"CANDIDATE"}')
    with pytest.raises(RuntimeError, match="nicht.*freigegeben"):
        approved_root(tmp_path)
    (new / "admin/approval.json").write_text('{"state":"APPROVED"}')
    assert approved_root(tmp_path) == new
    assert session_root == old
