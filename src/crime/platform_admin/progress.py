"""Durable step evidence. A completed build is not a deployed release."""
import json
from pathlib import Path
from .store import now


def record(folder, step, status, detail=""):
    path = Path(folder) / "progress.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        value = {"steps": {}}
    value["updated_at"] = now()
    value["steps"][step] = {"status": status, "detail": detail, "at": value["updated_at"]}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def read(folder):
    try:
        return json.loads((Path(folder) / "progress.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"steps": {}}
