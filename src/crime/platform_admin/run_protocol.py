"""The worker's run protocol, in the format the cron data run writes.

Under the console, storage.verwaltet blocks orchestration.run_all, and with it
the only writer of data/pipeline_run.json. serving.betriebsstand renders that
file for Prometheus and the Grafana board; without a writer the board would
show the last cron run forever and look green. So the worker writes it, in the
same format, after every tick that ran a command - and renders the metrics
file right after, also when the tick failed (the cron run does both from a
trap for the same reason).
"""
import os
from datetime import datetime, timezone
from pathlib import Path

#: Where a module belongs in the protocol, by package; the cron run takes the
#: group from orchestration.run_all.STUFEN, which knows only its own stages.
GROUPS = {
    "chicago_pipeline": "ingestion", "detroit_pipeline": "ingestion",
    "census_pipeline": "ingestion", "weather_pipeline": "ingestion",
    "silver_pipeline": "silver", "gold_pipeline": "gold", "serving": "serving",
}


#: Steps whose failure the cron run reports but does not count against the
#: run ("|| echo WARNUNG" there, serving_export.follow_up here).
WARN_ONLY = {"orchestration.drift", "orchestration.sicherungssatz"}


def succeeded(collected, status):
    """Green like the cron run: no failed result, no failed counting step."""
    return status not in {"FAILED", "PARTIAL"} and all(
        s["exit"] == 0 for s in collected if s["modul"] not in WARN_ONLY
    )


def stages(collected):
    return [
        {
            "gruppe": GROUPS.get(s["modul"].split(".")[0], "orchestration"),
            "name": s["modul"].rsplit(".", 1)[-1],
            "modul": s["modul"],
            "args": s["args"],
            "exit": -1 if s["exit"] is None else s["exit"],
            "sekunden": s.get("sekunden", 0.0),
        }
        for s in collected
    ]


def release(store):
    """The active release as the cron protocol names it, or {}."""
    from .candidates import active_id, release_path
    import json

    rid = active_id(store)
    if not rid:
        return {}
    manifest = json.loads((release_path(store, rid) / "release.json").read_text(encoding="utf-8"))
    return {
        "release_id": rid,
        "files": len(manifest.get("files", {})),
        "bytes": manifest.get("bytes"),
        # The console mirrors every release to S3 itself (object_store).
        "published": os.getenv("ADMIN_OBJECT_STORE", "local") == "s3",
    }


def write(store, collected, started, *, ok, error=None):
    from orchestration.run_all import aktualitaet, schreibe_manifest, zeilenzahlen
    from storage import StorageError

    try:
        freshness = aktualitaet(store.data)
        rows = zeilenzahlen(store.data) if ok else {}
    except StorageError as exc:
        freshness, rows, error = {}, {}, error or str(exc)
    manifest = {
        "status": "complete" if ok else "failed",
        "origin": "platform_admin",
        "error": error,
        "release": release(store),
        "started_at_utc": started.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "stages": stages(collected),
        "source_freshness": freshness,
        "output_rows": rows,
    }
    schreibe_manifest(store.data, manifest)
    return manifest


def render_metrics(store):
    """serving.betriebsstand on the protocol just written; never raises."""
    from serving import betriebsstand

    target = Path(os.getenv("ADMIN_START_ROOT", str(store.data / "startseite"))) / "metrics"
    try:
        betriebsstand.main(["--data-root", str(store.data), "--ziel", str(target)])
    except Exception:  # the report about a run is not the run
        return None
    return target
