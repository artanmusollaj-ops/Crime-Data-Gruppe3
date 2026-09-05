"""Make the hyphenated ingestion package importable as a plain module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "crime-pipeline"
    / "ingestion"
    / "download_chicago.py"
)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# "src/crime-pipeline" is not a valid package name, so the module is loaded by
# path once and registered under a stable name the tests can import.
_load_module("download_chicago", MODULE_PATH)
