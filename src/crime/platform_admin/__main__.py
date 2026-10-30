"""Local admin UI and worker. Nothing runs until explicitly started."""

import argparse
import getpass
import json
import secrets
import time
from pathlib import Path
from storage import for_root

from .jobs import enqueue
from .store import AdminError, Store


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "action",
        choices=[
            "init",
            "enable-managed",
            "serve",
            "worker",
            "enqueue",
            "status",
            "impact",
            "decide",
            "publish-approved",
            "abandon-impact",
            "recover-operation",
            "recover-job",
            "restore-backup",
        ],
    )
    p.add_argument("--project-root", type=Path, default=Path.cwd())
    p.add_argument("--data-root", type=Path, default=Path("data"))
    p.add_argument("--operator", default=getpass.getuser())
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--once", action="store_true", help="Ein Scheduler-Tick und maximal ein Job")
    p.add_argument("--name", help="Konfigurierter Jobname fuer enqueue")
    p.add_argument("--operation-id")
    p.add_argument("--job-id")
    p.add_argument("--archive", type=Path)
    p.add_argument("--restore-to", type=Path)
    p.add_argument("--revision", help="Revision fuer Impact oder Entscheidung")
    p.add_argument("--impact-id", help="Genau angezeigter Impact-Lauf")
    p.add_argument("--report-hash", help="SHA-256 des angezeigten Auswirkungsberichts")
    p.add_argument("--choice", choices=["approve", "reject"])
    p.add_argument("--reason", help="Entscheidungsbegruendung")
    args = p.parse_args()
    if not args.operator.strip():
        p.error("--operator darf nicht leer sein")
    if args.action == "restore-backup":
        from .object_store import restore_archive

        if not args.archive or not args.restore_to:
            p.error("--archive und --restore-to erforderlich")
        print(restore_archive(args.archive, args.restore_to))
        return 0
    store = Store(args.project_root, for_root(args.data_root).local_root)
    if args.action in {"serve", "worker"}:
        from .gitops import protection_mode

        try:
            protection_mode()  # A mistyped ADMIN_GIT_SCHUTZ stops the start.
        except AdminError as exc:
            p.error(str(exc))
    try:
        if args.action == "recover-job":
            from .jobs import recover_import
            print(json.dumps(recover_import(store, args.job_id, args.operator, args.reason or "")))
        elif args.action == "recover-operation":
            from .operations import recover

            recover(store, args.operation_id, args.operator, args.reason or "")
        elif args.action == "enable-managed":
            from .integration import enable
            print(json.dumps(enable(store, args.operator), ensure_ascii=False))
        elif args.action == "init":
            store.initialize(args.operator)
            print("Baseline importiert. Alle Zeitplaene sind standardmaessig deaktiviert.")
        elif args.action == "serve":
            from .web import make_server

            store.current("settings")  # Fail clearly when not initialized.
            token = secrets.token_urlsafe(32)
            server = make_server(store, args.operator, token, args.port)
            print(
                f"Lokale Engineering-Konsole: http://127.0.0.1:{server.server_port}/#token={token}",
                flush=True,
            )
            print(
                "Token nicht teilen. Operator ist eine lokale Namensangabe, kein SSO-Login.",
                flush=True,
            )
            try:
                server.serve_forever()
            finally:
                server.server_close()
        elif args.action == "impact":
            print(store.retry_impact(args.revision, args.operator))
        elif args.action == "decide":
            print(
                json.dumps(
                    store.decide(
                        args.revision,
                        args.choice,
                        args.operator,
                        args.reason or "",
                        impact_id=args.impact_id,
                        report_hash=args.report_hash,
                    ),
                    ensure_ascii=False,
                )
            )
        elif args.action == "abandon-impact":
            from .candidates import abandon

            print(
                json.dumps(
                    abandon(store, args.impact_id, args.operator, args.reason or ""),
                    ensure_ascii=False,
                )
            )
        elif args.action == "publish-approved":
            from .candidates import finish_publication
            from .jobs import writer_lock

            with writer_lock(store):
                print(finish_publication(store, args.impact_id))
        elif args.action == "enqueue":
            print(enqueue(store, args.name, args.operator))
        elif args.action == "status":
            print(json.dumps(store.history(), indent=2, ensure_ascii=False))
        elif args.action == "worker":
            while True:
                from .operations import tick

                result = tick(store)
                if result:
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                if args.once:
                    return (
                        0
                        if not result
                        or result.get("status", "SUCCEEDED") in {"SUCCEEDED", "AWAITING_REVIEW"}
                        else 2
                    )
                time.sleep(10)
    except AdminError as exc:
        print(f"Admin: {exc}")
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
