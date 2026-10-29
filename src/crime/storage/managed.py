"""Single-host writer ownership for CLI entrypoints; no UI dependencies."""
import json
import os
from pathlib import Path


def managed(data_root):
    return (Path(data_root) / "admin/managed.json").is_file()


def guard(data_root, *, allow_worker=False):
    root = Path(data_root)
    if not managed(root):
        return
    if allow_worker:
        try:
            token = json.loads((root / "admin/worker.lock").read_text())["token"]
            if token and token == os.getenv("ADMIN_WRITER_TOKEN"):
                return
        except (OSError, ValueError, KeyError):
            pass
    raise RuntimeError("Verwalteter Datenbestand: Aktion ueber die Engineering-Konsole "
                       "oder 'python -m platform_admin.batch' einreihen. "
                       "Direkte Schreiber und destruktives Aufraeumen sind gesperrt.")
