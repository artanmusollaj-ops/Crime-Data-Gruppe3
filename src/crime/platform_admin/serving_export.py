"""Use the infrastructure's star-schema loaders on the exact approved release.

Elasticsearch switches each table alias independently. A failed subsequent
step is reported as PARTIAL; no distributed transaction is claimed.
"""
import json
import os
import sys
from pathlib import Path

from .store import AdminError


def publish(store, rid):
    from .candidates import active_id, release_path, verify_release
    from .operations import record_status, overview
    from .jobs import execute_commands, PipelineCommandError
    from storage.release import einsetzen

    if active_id(store) != rid:
        raise AdminError("Serving-Auftrag ist veraltet; aktuellen Release erneut einreihen")
    root = release_path(store, rid)
    verify_release(root)
    approval_path = root / "admin/approval.json"
    if not approval_path.exists() or json.loads(approval_path.read_text())["state"] != "APPROVED":
        raise AdminError("Serving verlangt einen freigegebenen Release; die uebernommene "
                         "Alt-Baseline hat keine nachtraegliche Freigabe.")
    folder = store.root / "serving" / rid
    folder.mkdir(parents=True, exist_ok=True)
    steps = [
        ("elasticsearch", "serving.load_elasticsearch", []),
        ("kibana", "serving.build_kibana", []),
        ("startseite", "serving.build_einstieg", ["--ziel", str(Path(os.getenv("ADMIN_START_ROOT", str(store.data / "startseite"))) / "index.html"),
                                                "--adressen", os.getenv("ADMIN_START_ADDRESSES", "lokal")]),
        ("analysis_check", "serving.pruefe_stand", ["--json"]),
    ]
    previous = overview(store)["services"].get("analysis", {})
    last = previous.get("release_id") if previous.get("status") == "SUCCEEDED" else previous.get("last_successful_release_id")
    record_status(store, "analysis", {"status": "RUNNING", "target_release_id": rid,
                                     "last_successful_release_id": last})
    try:
        # Compatible fixed local table paths for notebooks and stand checks.
        einsetzen(store.data, root)
        with (folder / "run.log").open("a", encoding="utf-8") as log:
            for name, module, args in steps:
                record_status(store, name, {"status": "RUNNING", "target_release_id": rid})
                execute_commands(store, [[sys.executable, "-m", module, "--data-root", str(store.data), *args]], log)
                record_status(store, name, {"status": "SUCCEEDED", "release_id": rid})
    except Exception as exc:
        record_status(store, "analysis", {"status": "PARTIAL", "target_release_id": rid,
                      "last_successful_release_id": last,
                      "log_path": str(folder / "run.log"), "error_type": type(exc).__name__})
        if isinstance(exc, PipelineCommandError):
            raise AdminError(str(exc)) from exc
        raise
    result = {"status": "SUCCEEDED", "release_id": rid, "log_path": str(folder / "run.log"),
              "clickhouse": "not_loaded_by_target_architecture"}
    record_status(store, "analysis", result)
    return result
