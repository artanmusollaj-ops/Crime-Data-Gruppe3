"""Cron enqueues ingestion plus an impact build; it never activates a release."""
import argparse
import json
import uuid
from pathlib import Path
from storage import for_root

from .store import Store, AdminError, encode, now


def enqueue_batch(store, mode, actor, slot=None):
    from .operations import schema
    from .integration import scope_years

    if mode not in {"full", "delta"}:
        raise AdminError("Batch-Modus muss full oder delta sein")
    schema(store)
    with store.db() as con:
        con.execute("BEGIN IMMEDIATE")
        heads = dict(con.execute("SELECT resource,revision FROM head").fetchall())
        settings = store.get(heads["settings"])["payload"]
        payload = {"mode": mode, "years": scope_years(settings), "heads": heads, "slot": slot}
        if slot:
            for row in con.execute("SELECT id,payload FROM operation WHERE kind='batch'"):
                if json.loads(row[1]).get("slot") == slot:
                    return row[0]
        if con.execute("SELECT 1 FROM operation WHERE kind='batch' AND status IN ('QUEUED','RUNNING')").fetchone():
            raise AdminError("Ein Betriebsimport ist bereits eingereiht oder laeuft")
        oid = uuid.uuid4().hex
        con.execute("INSERT INTO operation VALUES (?,?,?,?,?,'QUEUED',?,NULL,NULL)",
                    (oid, "batch", encode(payload), actor, "Geplanter Quellenlauf mit Impact-Review", now()))
        return oid


def execute(store, row, payload):
    from orchestration.run_all import auswahl
    from .jobs import execute_commands, enqueue
    from .run_evidence import inventory, capture

    with store.db() as con:
        heads = dict(con.execute("SELECT resource,revision FROM head").fetchall())
    if heads != payload["heads"]:
        raise AdminError("Batch-Konfiguration ist veraltet; neuen Batch einreihen.")
    folder = store.root / "jobs" / row["id"]
    folder.mkdir(exist_ok=True, parents=True)
    import sys
    commands = [[sys.executable, "-m", "orchestration.vorpruefung"]]
    for stage in auswahl(False, "ingestion", payload["years"]):
        command = stage.befehl(store.data)
        if payload["mode"] == "full":
            if stage.modul == "chicago_pipeline.download_chicago":
                command.append("--full")
            elif stage.modul == "detroit_pipeline.extract_detroit":
                command[command.index("--mode") + 1] = "full"
        commands.append(command)
    before = {city: inventory(store, city) for city in ("chicago", "detroit")}
    try:
        with (folder / "run.log").open("w", encoding="utf-8") as log:
            execute_commands(store, commands, log)
    finally:
        for city in before:
            city_folder = folder / city
            city_folder.mkdir(exist_ok=True)
            capture(store, city, before[city], city_folder, row, payload)
    impact = enqueue(store, "rebuild", row["actor"])
    return {"impact_id": impact, "log_path": str(folder / "run.log"),
            "note": "Quellen geladen. Kandidat eingereiht; Freigabe bleibt erforderlich."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--mode", choices=("full", "delta"), default="delta")
    parser.add_argument("--slot", help="Idempotenzschluessel, etwa Tagesdatum; Retry mit neuem Schluessel")
    parser.add_argument("--operator", default="scheduler")
    args = parser.parse_args()
    store = Store(args.project_root, for_root(args.data_root).local_root)
    print(enqueue_batch(store, args.mode, args.operator, args.slot))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
