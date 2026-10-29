"""Pin an immutable local release once per notebook session."""
import json
from pathlib import Path

from storage.managed import managed


def approved_root(data_root: Path) -> Path:
    data_root = Path(data_root).resolve()
    pointer = data_root / "releases/AKTUELL.json"
    if not pointer.exists():
        if managed(data_root):
            raise RuntimeError("Noch kein aktiver Release. Rebuild und Freigabe in der Konsole abschliessen.")
        return data_root
    value = json.loads(pointer.read_text(encoding="utf-8"))
    rid = value["release_id"]
    if not isinstance(rid, str) or Path(rid).name != rid or "/" in rid or "\\" in rid:
        raise RuntimeError("Ungueltige Releasekennung")
    root = data_root / "releases" / ("release=" + rid)
    if value.get("path") != f"releases/release={rid}" or not root.is_dir():
        raise RuntimeError("Aktiver Release ist lokal nicht verfuegbar")
    if managed(data_root):
        approval = root / "admin/approval.json"
        if approval.exists():
            if json.loads(approval.read_text())["state"] != "APPROVED":
                raise RuntimeError("Kandidat ist nicht fuer Analysen freigegeben")
        else:
            adoption = json.loads((data_root / "admin/managed.json").read_text())
            if adoption.get("baseline_release_id") != rid:
                raise RuntimeError("Release besitzt weder Freigabe noch dokumentierte Baseline-Uebernahme")
    return root
