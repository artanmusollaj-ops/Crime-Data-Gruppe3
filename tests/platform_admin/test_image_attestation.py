"""The worker image must pass the same source check an impact job runs.

On 3.11.2026 the first impact job on srv01 failed with "Builddatei fehlt:
requirements.txt": ``release_flow.capture`` compares every in-scope file of
the worker against the Git tree of main, and the image never carried the
three build files. Locally the project root is the repository, so nothing
showed until the server ran it.
"""

import re
import subprocess
from pathlib import Path

import pytest

from platform_admin.release_flow import blob_hash, source_inventory, tree_mismatch
from platform_admin.store import AdminError


ROOT = Path(__file__).resolve().parents[2]
BUILD_FILES = ("pyproject.toml", "requirements.txt", "requirements.lock",
               "requirements-admin.lock", "Dockerfile", "Dockerfile.admin")


def project(tmp_path):
    (tmp_path / "src" / "crime" / "pkg").mkdir(parents=True)
    (tmp_path / "config").mkdir()
    (tmp_path / "src" / "crime" / "pkg" / "a.py").write_text("x = 1\n")
    (tmp_path / "config" / "c.csv").write_text("a,b\n")
    (tmp_path / "pyproject.toml").write_text("[project]\n")
    (tmp_path / "requirements.txt").write_text("duckdb\n")
    return tmp_path


def ls_tree(root):
    lines = []
    for path, sha in sorted(source_inventory(root).items()):
        lines.append(f"100644 blob {sha}\t{path}")
    return "\n".join(lines) + "\n"


def test_an_identical_tree_has_no_mismatch(tmp_path):
    root = project(tmp_path)
    assert tree_mismatch(root, ls_tree(root)) == []


def test_egg_info_from_the_editable_install_is_not_compared(tmp_path):
    root = project(tmp_path)
    tree = ls_tree(root)
    info = root / "src" / "crime" / "crime_data_gruppe3.egg-info"
    info.mkdir()
    (info / "PKG-INFO").write_text("Name: x\n")
    assert tree_mismatch(root, tree) == []


def test_a_build_file_missing_from_the_image_is_named(tmp_path):
    root = project(tmp_path)
    (root / "Dockerfile").write_text("FROM python:3.13\n")
    tree = ls_tree(root)
    (root / "Dockerfile").unlink()
    assert tree_mismatch(root, tree) == ["Dockerfile"]


def test_a_required_build_file_missing_fails_like_on_srv01(tmp_path):
    root = project(tmp_path)
    (root / "requirements.txt").unlink()
    with pytest.raises(AdminError, match="Builddatei fehlt: requirements.txt"):
        tree_mismatch(root, "")


def test_a_changed_file_is_named(tmp_path):
    root = project(tmp_path)
    tree = ls_tree(root)
    (root / "config" / "c.csv").write_text("a,b,c\n")
    assert tree_mismatch(root, tree) == ["config/c.csv"]


def test_blob_hash_matches_git():
    data = b"x = 1\n"
    expected = subprocess.run(["git", "hash-object", "--stdin"], input=data,
                              capture_output=True, check=True).stdout.decode().strip()
    assert blob_hash(data) == expected


def test_the_image_copies_every_tracked_build_file_into_app():
    """Each build file the check compares must land in /app."""
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    after_workdir = dockerfile.split("WORKDIR /app", 1)[1]
    copied = set()
    for line in re.findall(r"^COPY\s+(.+)$", after_workdir, re.M):
        copied.update(line.split()[:-1])
    tracked = [name for name in BUILD_FILES if (ROOT / name).is_file()]
    missing = [name for name in tracked if name not in copied]
    assert not missing, f"Not copied into /app: {missing}"
