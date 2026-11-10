"""Flask HTTP transport; domain checks remain in store/candidates/conflicts."""

import difflib
import json
import tempfile
from pathlib import Path

from flask import Flask, Response, g, request, send_file
from werkzeug.exceptions import HTTPException

from .jobs import enqueue
from .store import AdminError


def send(status, body, content_type="application/json; charset=utf-8"):
    data = body if isinstance(body, (bytes, str)) else json.dumps(body, ensure_ascii=False)
    return Response(data, status=status, content_type=content_type)


def create_app(store=None, *, operator=None, token=None, config=None):
    from .auth import install_auth
    from .gitops import protection_mode
    from .runtime import make_store, settings

    protection_mode()  # Refuse to start on a mistyped ADMIN_GIT_SCHUTZ.
    app = Flask(__name__, static_folder=None)
    app.config.update(settings())
    app.config.update(config or {})
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000
    store = store or make_store()
    app.extensions["admin_store"] = store
    install_auth(app, operator, token)

    @app.after_request
    def response_headers(response):
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'",
                "Referrer-Policy": "no-referrer",
            }
        )
        return response

    @app.errorhandler(AdminError)
    @app.errorhandler(ValueError)
    @app.errorhandler(KeyError)
    @app.errorhandler(TypeError)
    def bad_input(exc):
        return send(400, {"error": str(exc)})

    @app.errorhandler(HTTPException)
    def http_error(exc):
        return send(exc.code, {"error": exc.description})

    @app.errorhandler(Exception)
    def internal_error(exc):
        app.logger.error("Admin request failed: %s", type(exc).__name__)
        return send(500, {"error": "Interner Fehler; Worker-/Serverstatus pruefen"})

    @app.get("/healthz")
    def health():
        return send(200, {"status": "ok"})

    @app.get("/metrics")
    def metrics():
        from .operations import metrics_text

        return send(200, metrics_text(store), "text/plain; version=0.0.4")

    @app.get("/")
    @app.get("/api/<path:unused>")
    def get_request(unused=None):
        if request.path == "/":
            return send(
                200,
                (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8"),
                "text/html; charset=utf-8",
            )
        elif request.path == "/api/state":
            from .candidates import active_id
            from .conflicts import all_pending
            from .operations import overview

            return send(
                200,
                {
                    **store.history(),
                    "operator": g.actor,
                    "identity": g.identity,
                    "roles": sorted(g.roles),
                    "conflicts": all_pending(store),
                    "active_release_id": active_id(store),
                    "analysis_status": overview(store)["services"].get("analysis", {}),
                    "mapping": store.current("mapping"),
                    "settings": store.current("settings"),
                },
            )
        elif request.path == "/api/impact-archive":
            from .impact_archive import write_zip

            iid = request.args.get("id", "")
            # Zipped to an unlinked temporary file and streamed from there, so
            # memory stays flat however large the archive is (S-9).
            stream = tempfile.TemporaryFile()
            try:
                write_zip(store, iid, stream)
            except BaseException:
                stream.close()
                raise
            stream.seek(0)
            # IDs originate in the checked database record, not a filesystem path.
            return send_file(
                stream, mimetype="application/zip", as_attachment=True,
                download_name="impact-" + iid + ".zip",
            )
        elif request.path == "/api/operations":
            from .operations import overview

            return send(200, overview(store))
        elif request.path == "/api/source-evidence":
            from .run_evidence import evidence

            return send(200, evidence(store, request.args.get("city", ""), request.args.get("run", "")))
        elif request.path == "/api/inbox":
            from .inbox import overview

            return send(200, overview(store, g.actor))
        elif request.path == "/api/source-code":
            from .sources import source_code

            return send(200, source_code(
                store, request.args.get("city", ""),
                request.args.get("module"), request.args.get("run"),
            ))
        elif request.path == "/api/sources":
            from .sources import source_status

            return send(200, source_status(store))
        elif request.path == "/api/mapping-codes":
            from .sources import mapping_catalog

            return send(
                200, mapping_catalog(store, request.args.to_dict(flat=False).get("city", [""])[0])
            )
        elif request.path in {"/api/impact", "/api/impact-artifact"}:
            from .candidates import checked_impact

            params = request.args.to_dict(flat=False)
            iid = params.get("id", [""])[0]
            with store.db() as c:
                row = c.execute("SELECT * FROM impact WHERE id=?", (iid,)).fetchone()
            if not row:
                raise AdminError("Impact-Lauf nicht gefunden")
            row = dict(row)
            if not row["report_path"]:
                error = row["error"]
                try:
                    details = json.loads(error) if error else {}
                except (TypeError, json.JSONDecodeError):
                    details = {"error": error}
                message = details.get("error") or "Der Impact-Lauf ist fehlgeschlagen."
                return send(
                    200,
                    {
                        "status": row["status"],
                        **details,
                        "error": message,
                        "summary_text": message,
                    },
                )
            else:
                from .impact_archive import checked as checked_archive

                with store.db() as c:
                    has_archive = c.execute(
                        "SELECT 1 FROM impact_archive WHERE impact_id=?", (iid,)
                    ).fetchone()
                if has_archive:
                    archived, _manifest = checked_archive(store, iid)
                    artifact_root = Path(archived["path"])
                    report = json.loads((artifact_root / "impact_report.json").read_text())
                else:
                    report = checked_impact(store, row)
                    artifact_root = Path(row["candidate_path"]) / "admin"
                if request.path == "/api/impact":
                    return send(
                        200,
                        {
                            **report,
                            "report_hash": row["report_hash"],
                            "status": row["status"],
                        },
                    )
                else:
                    name = params.get("name", [""])[0]
                    if name not in {
                        "impact_report.json",
                        "impact_by_partition.parquet",
                        "impact_records.parquet",
                        "impact_quality.parquet",
                        "impact_quality_month.parquet",
                    }:
                        raise AdminError("Unbekanntes Impact-Artefakt")
                    # Streamed, not read: impact_records.parquet reaches 250 MB (S-9).
                    return send_file(
                        artifact_root / name,
                        mimetype="application/json"
                        if name.endswith(".json")
                        else "application/octet-stream",
                        conditional=False,
                        etag=False,
                    )
        elif request.path == "/api/job-log":
            jid = request.args.to_dict(flat=False).get("id", [""])[0]
            with store.db() as c:
                row = c.execute("SELECT log_path FROM job WHERE id=?", (jid,)).fetchone()
            if not row or not row["log_path"]:
                raise AdminError("Noch kein Jobprotokoll vorhanden")
            path = Path(row["log_path"])
            if not path.resolve().is_relative_to((store.root / "jobs").resolve()):
                raise AdminError("Ungueltiger Logpfad")
            with path.open("rb") as f:
                f.seek(max(0, path.stat().st_size - 100000))
                return send(
                    200,
                    {
                        "log": f.read().decode("utf-8", errors="replace"),
                        "tail_bytes": 100000,
                    },
                )
        elif request.path == "/api/diff":
            rid = request.args.to_dict(flat=False).get("id", [""])[0]
            rev = store.get(rid)
            parent = store.get(rev["parent"])["payload"] if rev["parent"] else {}

            def pretty(value):
                return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).splitlines()

            if rev["resource"] == "mapping":
                changes = []
                for name, text in rev["payload"].items():
                    changes += list(
                        difflib.unified_diff(
                            parent.get(name, "").splitlines(),
                            text.splitlines(),
                            fromfile="vorher/" + name,
                            tofile="nachher/" + name,
                        )
                    )
            else:
                changes = list(
                    difflib.unified_diff(
                        pretty(parent),
                        pretty(rev["payload"]),
                        fromfile="vorher",
                        tofile="nachher",
                    )
                )
            return send(200, {"diff": "\n".join(changes), "resource": rev["resource"],
                              "before": parent, "after": rev["payload"]})
        else:
            return send(404, {"error": "Unbekannter Pfad"})

    @app.post("/api/<path:unused>")
    def post_request(unused):
        if not request.is_json:
            raise AdminError("JSON erforderlich")
        value = request.get_json()
        if not isinstance(value, dict):
            raise AdminError("JSON-Objekt erforderlich")
        if request.path in {
            "/api/git-open",
            "/api/git-merge",
            "/api/git-withdraw",
            "/api/archive-retry",
            "/api/backup",
            "/api/serving",
        }:
            from .operations import submit

            result = submit(store, request.path.removeprefix("/api/"), value, g.actor)
        elif request.path in {"/api/review-claim", "/api/review-release", "/api/review-read"}:
            from .inbox import update

            result = update(store, value["id"], g.actor, request.path.removeprefix("/api/review-"))
        elif request.path == "/api/mapping":
            result = store.propose_mapping(
                value["city"],
                value["code"],
                value["target"],
                value["parent"],
                g.actor,
                value["reason"],
            )
        elif request.path == "/api/settings":
            result = store.propose(
                "settings", value["payload"], value["parent"], g.actor, value["reason"]
            )
        elif request.path == "/api/decision":
            result = store.decide(
                value["id"],
                value["choice"],
                g.actor,
                value["reason"],
                impact_id=value.get("impact_id"),
                report_hash=value.get("report_hash"),
            )
        elif request.path == "/api/rebase":
            from .conflicts import rebase

            result = rebase(store, value["id"], g.actor, value["reason"])
        elif request.path == "/api/impact-retry":
            result = store.retry_impact(value["id"], g.actor)
        elif request.path == "/api/publish-approved":
            import os

            if os.getenv("ADMIN_DEFER_PUBLICATION") == "1":
                return send(200, {"result": "Freigegebene Publikation wird vom Worker fortgesetzt"})
            from .candidates import finish_publication
            from .jobs import writer_lock

            with writer_lock(store):
                result = finish_publication(store, value["id"])
        elif request.path == "/api/job":
            result = enqueue(store, value["name"], g.actor)
        else:
            return send(404, {"error": "Unbekannte Aktion"})
        return send(200, {"result": result})

    return app


def make_server(store, operator, token, port=8765):
    """Compatibility entry for the local CLI; production uses Gunicorn."""
    from werkzeug.serving import make_server as wsgi_server, WSGIRequestHandler

    class QuietHandler(WSGIRequestHandler):
        def log(self, *_args, **_kwargs):
            pass

    app = create_app(store, operator=operator, token=token, config={"ADMIN_AUTH": "local"})
    return wsgi_server("127.0.0.1", port, app, threaded=True, request_handler=QuietHandler)
