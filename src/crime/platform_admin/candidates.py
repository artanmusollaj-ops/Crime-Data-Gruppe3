"""Isolated candidate builds, immutable evidence and explicit local publication.

SQLite records the decision before the active pointer is changed. An interruption
between those operations leaves APPROVED_PENDING_PUBLICATION and is retryable.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from pathlib import Path
from types import SimpleNamespace

from .store import AdminError, encode, now


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def active_id(store):
    path = store.data / "releases" / "AKTUELL.json"
    if not path.exists():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    rid = value["release_id"]
    if not isinstance(rid, str) or not rid or Path(rid).name != rid or "/" in rid or "\\" in rid:
        raise AdminError("Ungueltige Releasekennung")
    expected = f"releases/release={rid}"
    if value.get("path") != expected:
        raise AdminError("Releasezeiger hat unerwarteten Pfad")
    return rid


def release_path(store, rid):
    return store.data / "releases" / f"release={rid}" if rid else None


def verify_release(path):
    path = Path(path)
    manifest = json.loads((path / "release.json").read_text(encoding="utf-8"))
    if manifest.get("status") != "complete" or not manifest.get("files"):
        raise AdminError("Unvollstaendiges Release")
    for rel, entry in manifest["files"].items():
        target = (path / rel).resolve()
        if not target.is_relative_to(path.resolve()) or not target.is_file():
            raise AdminError("Releaseartefakt fehlt oder ungueltiger Pfad")
        if file_hash(target) != entry["sha256"]:
            raise AdminError(f"Releaseartefakt wurde veraendert: {rel}")
    return manifest


def queue_in_transaction(store, c, rid, actor):
    raw = c.execute("SELECT * FROM revision WHERE id=?", (rid,)).fetchone()
    if not raw:
        raise AdminError("Revision nicht gefunden")
    if c.execute("SELECT 1 FROM impact WHERE status='APPROVED_PENDING_PUBLICATION'").fetchone():
        raise AdminError("Genehmigte Publikation zuerst fortsetzen")
    r = dict(raw)
    r["payload"] = json.loads(r["payload"])
    from .store import digest

    if digest(r["payload"]) != r["sha256"]:
        raise AdminError("Revisionsinhalt stimmt nicht mit Pruefsumme ueberein")
    if not r["parent"]:
        raise AdminError("Baseline-Import ist kein Anpassungsvorschlag")
    if c.execute("SELECT 1 FROM decision WHERE revision=?", (rid,)).fetchone():
        raise AdminError("Revision wurde bereits entschieden")
    if c.execute(
        "SELECT 1 FROM impact WHERE revision_id=? AND status IN ('QUEUED','RUNNING')", (rid,)
    ).fetchone():
        raise AdminError("Impact-Lauf fuer diese Revision bereits eingereiht")
    heads = dict(c.execute("SELECT resource,revision FROM head").fetchall())
    if heads.get(r["resource"]) != r["parent"]:
        raise AdminError("Veralteter Vorschlag; neu auf aktuellem Stand vorschlagen")
    mapping = rid if r["resource"] == "mapping" else heads["mapping"]
    settings = rid if r["resource"] == "settings" else heads["settings"]
    from .release_flow import mode

    policy = mode()
    jid = uuid.uuid4().hex
    baseline = active_id(store)
    spec = {
        "task": "impact",
        "release_policy": policy if r["resource"] in {"mapping", "settings"} else "data",
        "git_provenance_required": policy == "coupled",
        "revision_id": rid,
        "base_heads": heads,
        "baseline_release_id": baseline,
        "candidate_release_id": "candidate-" + jid,
        "expect_identical": r["resource"] == "data" and r["payload"]["task"] == "replay",
    }
    c.execute(
        """INSERT INTO job(id,name,mapping_revision,settings_revision,spec,actor,status,queued_at)
        VALUES(?,?,?,?,?,?,'QUEUED',?)""",
        (jid, "impact_" + rid[:12], mapping, settings, encode(spec), actor, now()),
    )
    c.execute(
        """INSERT INTO impact(id,revision_id,baseline_release_id,candidate_release_id,status,spec,created_at)
        VALUES(?,?,?,?,'QUEUED',?,?)""",
        (jid, rid, baseline, spec["candidate_release_id"], encode(spec), now()),
    )
    return jid


def sources_snapshot(store, target):
    """Copy, never hardlink, the complete Bronze input; detect concurrent writes."""
    from .integration import remote_snapshot

    remote = remote_snapshot(store, target)
    if remote is not None:
        return remote
    source = store.data / "bronze"
    if not source.is_dir():
        raise AdminError("Keine lokalen Bronze-Daten fuer den Kandidatenaufbau vorhanden")

    def inventory(root):
        return {
            p.relative_to(root).as_posix(): file_hash(p)
            for p in sorted(root.rglob("*"))
            if p.is_file() and not any(x.startswith(".") for x in p.relative_to(root).parts)
        }

    before = inventory(source)
    if not any(p.endswith("/manifest.json") for p in before):
        raise AdminError("Keine Bronze-Manifeste vorhanden")
    for rel in before:
        dest = target / "bronze" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / rel, dest)
    if inventory(source) != before or inventory(target / "bronze") != before:
        raise AdminError("Bronze wurde waehrend der Snapshot-Erstellung veraendert; erneut pruefen")
    return {"files": before, "sha256": hashlib.sha256(encode(before).encode()).hexdigest()}


def build(store, job, spec, folder, runner, evaluator):
    from .jobs import commands
    from .impact import compare
    from orchestration.release import datenbank
    from storage.release import erstelle

    from .progress import record

    provenance = None
    if spec.get("git_provenance_required"):
        from .release_flow import capture

        provenance = capture(store, spec)
    baseline = release_path(store, spec["baseline_release_id"])
    baseline_manifest = verify_release(baseline) if baseline else None
    root = folder / "data"
    root.mkdir()
    record(folder, "bronze_snapshot", "RUNNING", "Bronze-Eingaben kopieren und verifizieren")
    source = sources_snapshot(store, root)
    record(folder, "bronze_snapshot", "SUCCEEDED", "Snapshot gesichert; fachliche Eingabepruefung folgt im Build")
    (folder / "source_snapshot.json").write_text(json.dumps(source, indent=2), encoding="utf-8")
    candidate = SimpleNamespace(project=store.project, data=root)
    config = store.materialize(job["mapping_revision"])
    settings = store.get(job["settings_revision"])["payload"]
    from .integration import scope_years, copy_history

    years = scope_years(settings)
    copy_history(store, root, baseline)
    with (folder / "run.log").open("w", encoding="utf-8") as log:
        runner(candidate, commands(candidate, {"task": "rebuild", "years": years}, config), log)
    if provenance:
        from .release_flow import check_build_unchanged

        check_build_unchanged(store, spec, provenance)
    record(folder, "quality", "RUNNING")
    quality = evaluator(root, settings)
    record(folder, "quality", "SUCCEEDED" if quality["ok"] else "BLOCKED")
    audit = {}
    if baseline:
        audit_path = baseline / "admin" / "approval.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.exists() else {}
        old_settings = (audit.get("settings") or {}).get("payload")
        before_quality = (
            evaluator(baseline, old_settings)
            if (baseline / "silver" / "dataset=crime_offense").exists()
            else audit.get("quality")
        )
    else:
        before_quality = None
    metadata = {
        "git_provenance": provenance,
        "release_policy": spec.get("release_policy", "legacy"),
        "revision": store.get(spec["revision_id"]),
        "mapping_before": audit.get("mapping") or store.get(spec["base_heads"]["mapping"]),
        "mapping_after": store.get(job["mapping_revision"]),
        "settings_before": audit.get("settings") or store.get(spec["base_heads"]["settings"]),
        "settings_after": store.get(job["settings_revision"]),
        "baseline_release_id": spec["baseline_release_id"],
        "baseline_manifest_sha256": file_hash(baseline / "release.json") if baseline else None,
        "candidate_release_id": spec["candidate_release_id"],
        "source_snapshot_sha256": source["sha256"],
        "created_at_utc": now(),
        "impact_id": job["id"],
    }
    metadata["baseline_config_provenance"] = (
        "release_audit"
        if audit.get("mapping") and audit.get("settings")
        else "control_heads_no_release_config_proof"
        if baseline
        else "initial_control_heads"
    )
    record(folder, "impact", "RUNNING")
    report = compare(baseline, root, folder, metadata, before_quality, quality)
    record(folder, "impact", "SUCCEEDED")
    identical = report["summary"]["affected_records"] == 0 and not report["changed_tables"]
    if spec["expect_identical"] and (baseline is None or not identical):
        quality["replay_ok"] = False
        quality["ok"] = False
    report["quality_after"] = quality
    report["review_ready"] = bool(quality["ok"])
    report["replay_expected_identical"] = spec["expect_identical"]
    # Verify the immutable baseline stayed intact during the potentially long build.
    if baseline and (verify_release(baseline) != baseline_manifest):
        raise AdminError("Baseline waehrend des Kandidatenaufbaus veraendert")
    report_path = folder / "impact_report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8"
    )
    report_hash = file_hash(report_path)

    def supplement(work, core):
        shutil.copytree(
            root / "silver" / "dataset=crime_offense", work / "silver" / "dataset=crime_offense"
        )
        admin = work / "admin"
        history = root / "silver" / "dataset=source_change"
        if history.exists():
            shutil.copytree(history, work / "silver" / "dataset=source_change")
        datenbank(work, core)
        admin.mkdir()
        shutil.copytree(config, admin / "config")
        for name in (
            "impact_report.json",
            "impact_by_partition.parquet",
            "impact_records.parquet",
            "impact_quality.parquet",
            "impact_quality_month.parquet",
            "source_snapshot.json",
        ):
            shutil.copyfile(folder / name, admin / name)
        (admin / "approval.json").write_text(
            json.dumps(
                {
                    "job": job,
                    "quality": quality,
                    "mapping": metadata["mapping_after"],
                    "settings": metadata["settings_after"],
                    "impact_report_sha256": report_hash,
                    "state": "CANDIDATE",
                    "decisions": [],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

    path = erstelle(
        root, kennung_=spec["candidate_release_id"], ergaenze=supplement, activate=False,
        jahre=years
    )
    status = "READY" if quality["ok"] else "BLOCKED"
    with store.db() as c:
        c.execute(
            """UPDATE impact SET status=?,report_hash=?,report_path=?,candidate_path=?,finished_at=?,candidate_manifest_hash=?
                     WHERE id=?""",
            (
                status,
                report_hash,
                str(report_path),
                str(path),
                now(),
                file_hash(path / "release.json"),
                job["id"],
            ),
        )
    return {
        "ok": quality["ok"],
        "technical_ok": quality["technical_ok"],
        "quality_ok": quality["quality_ok"],
        "replay_ok": quality.get("replay_ok", True),
        "impact_id": job["id"],
        "impact_status": status,
        "summary": report["summary"],
        "report_hash": report_hash,
        "candidate_path": str(path),
        "note": "Kandidat bleibt inaktiv bis zur Vier-Augen-Freigabe.",
    }


def checked_impact(store, row):
    report = Path(row["report_path"])
    if file_hash(report) != row["report_hash"]:
        raise AdminError("Auswirkungsbericht wurde veraendert")
    candidate_manifest = Path(row["candidate_path"]) / "release.json"
    if (
        not row.get("candidate_manifest_hash")
        or file_hash(candidate_manifest) != row["candidate_manifest_hash"]
    ):
        raise AdminError("Kandidatenmanifest wurde veraendert")
    manifest = verify_release(row["candidate_path"])
    copied = Path(row["candidate_path"]) / "admin" / "impact_report.json"
    if file_hash(copied) != row["report_hash"]:
        raise AdminError("Kandidat und Auswirkungsbericht stimmen nicht ueberein")
    if manifest["release_id"] != row["candidate_release_id"]:
        raise AdminError("Falscher Kandidatenstand")
    return json.loads(report.read_text(encoding="utf-8"))


def decide(store, rid, choice, actor, reason, impact_id=None, report_hash=None):
    from .jobs import writer_lock

    if choice not in {"approve", "reject"} or not actor.strip() or not reason.strip():
        raise AdminError("approve/reject, Bearbeiter und Begruendung erforderlich")
    actor = actor.strip()
    r = store.get(rid)
    if r["actor"].strip().casefold() == actor.casefold():
        raise AdminError("Freigabe/Ablehnung muss durch eine zweite Person erfolgen")
    with writer_lock(store):
        with store.db() as c:
            c.execute("BEGIN IMMEDIATE")
            if c.execute("SELECT 1 FROM decision WHERE revision=?", (rid,)).fetchone():
                raise AdminError("Revision wurde bereits entschieden")
            if not r["parent"]:
                raise AdminError("Baseline-Import ist kein Anpassungsvorschlag")
            heads = dict(c.execute("SELECT resource,revision FROM head").fetchall())
            if choice == "approve" and heads.get(r["resource"]) != r["parent"]:
                raise AdminError("Veralteter Vorschlag; neu auf aktuellem Stand vorschlagen")
            row = None
            if choice == "approve":
                from .conflicts import inspect

                conflict = inspect(store, c, rid)
                if conflict["overlaps"]:
                    names = ", ".join(sorted({o["actor"] for o in conflict["overlaps"]}))
                    raise AdminError(
                        "Ueberlappende offene Vorschlaege von "
                        + names
                        + "; markierte Stellen pruefen und konkurrierende Vorschlaege zuerst ablehnen"
                    )
                if not impact_id or not report_hash:
                    raise AdminError(
                        "Freigabe verlangt den angezeigten Impact-Lauf und Berichtshash"
                    )
                found = c.execute(
                    "SELECT * FROM impact WHERE id=? AND revision_id=?", (impact_id, rid)
                ).fetchone()
                row = dict(found) if found else None
                if not row or row["status"] != "READY" or row["report_hash"] != report_hash:
                    raise AdminError(
                        "Kein freigabefaehiger gepruefter Kandidat fuer diesen Bericht"
                    )
                spec = json.loads(row["spec"])
                if heads != spec["base_heads"] or active_id(store) != row["baseline_release_id"]:
                    raise AdminError(
                        "Baseline oder Konfiguration veraendert; Impact erneut berechnen"
                    )
                report = checked_impact(store, row)
                from .impact_archive import checked
                import os

                _archive, archived = checked(
                    store,
                    impact_id,
                    require_remote=os.getenv("ADMIN_OBJECT_STORE", "local") == "s3",
                )
                if archived["report_hash"] != report_hash:
                    raise AdminError("Archiv und angezeigter Bericht stimmen nicht ueberein")
                from .release_flow import requires_git, mode

                if (
                    requires_git(row, r)
                    or mode() == "coupled"
                    or spec.get("git_provenance_required")
                ) and not report["metadata"].get("git_provenance"):
                    raise AdminError(
                        "Git-Buildnachweis fehlt; neuen Impact im gekoppelten Modus berechnen"
                    )
                if not report.get("review_ready"):
                    raise AdminError("Kandidat besteht die Quality Gates nicht")
                if row["baseline_release_id"]:
                    baseline = release_path(store, row["baseline_release_id"])
                    verify_release(baseline)
                    if (
                        file_hash(baseline / "release.json")
                        != report["metadata"]["baseline_manifest_sha256"]
                    ):
                        raise AdminError("Baseline-Pruefsumme hat sich veraendert")
            if (
                choice == "approve"
                and c.execute(
                    "SELECT 1 FROM impact WHERE status IN ('APPROVED_PENDING_PUBLICATION','AWAITING_GIT')"
                ).fetchone()
            ):
                raise AdminError("Genehmigte Publikation zuerst fortsetzen")
            decision = {
                "id": uuid.uuid4().hex,
                "revision": rid,
                "decision": choice,
                "actor": actor,
                "reason": reason.strip(),
                "decided_at": now(),
                "impact_id": impact_id,
                "impact_report_sha256": report_hash,
            }
            if choice == "approve" and requires_git(row, r):
                c.execute("UPDATE impact SET status='AWAITING_GIT' WHERE id=?", (impact_id,))
                from .release_flow import event

                event(
                    c,
                    row,
                    "REVIEW_APPROVED",
                    actor,
                    reason,
                    {"report_hash": report_hash, "archive_hash": _archive["manifest_hash"]},
                )
            elif choice == "approve":
                target = prepare_approved_release(store, row, decision)
                c.execute("UPDATE head SET revision=? WHERE resource=?", (rid, r["resource"]))
                c.execute(
                    "UPDATE impact SET status='APPROVED_PENDING_PUBLICATION',published_release_id=?,published_manifest_hash=? WHERE id=?",
                    (
                        target.name.removeprefix("release="),
                        file_hash(target / "release.json"),
                        impact_id,
                    ),
                )
            else:
                c.execute(
                    "UPDATE impact SET status='REJECTED' WHERE revision_id=? AND status NOT IN ('FAILED','BLOCKED')",
                    (rid,),
                )
                c.execute(
                    "UPDATE job SET status='CANCELLED',finished_at=? WHERE id IN (SELECT id FROM impact WHERE revision_id=?) AND status='QUEUED'",
                    (now(), rid),
                )
            c.execute(
                "INSERT INTO decision(id,revision,decision,actor,reason,decided_at,impact_id,impact_report_sha256) VALUES (?,?,?,?,?,?,?,?)",
                tuple(
                    decision[k]
                    for k in (
                        "id",
                        "revision",
                        "decision",
                        "actor",
                        "reason",
                        "decided_at",
                        "impact_id",
                        "impact_report_sha256",
                    )
                ),
            )
        import os

        if (
            choice == "approve"
            and not requires_git(row, r)
            and os.getenv("ADMIN_DEFER_PUBLICATION") != "1"
        ):
            finish_publication(store, impact_id)
        return decision


def prepare_approved_release(store, row, decision, git_evidence=None):
    """Copy the exact reviewed files; never rebuild between review and publication."""
    from storage.release import release_manifest
    from datetime import datetime, timezone

    rid = "approved-" + row["id"] + "-" + decision["id"][:8]
    target = release_path(store, rid)
    if target.exists():
        if git_evidence is None:
            raise AdminError("Vorbereiteter Release existiert bereits; Wiederanlauf kontrollieren")
        # Crash after immutable directory rename, before the DB transition.
        existing = verify_release(target)
        candidate = verify_release(row["candidate_path"])
        expected = {
            k: v["sha256"] for k, v in candidate["files"].items() if k != "admin/approval.json"
        }
        actual = {
            k: v["sha256"] for k, v in existing["files"].items() if k != "admin/approval.json"
        }
        audit = json.loads((target / "admin/approval.json").read_text())
        if (
            actual != expected
            or audit.get("git_evidence") != git_evidence
            or decision not in audit.get("decisions", [])
        ):
            raise AdminError("Vorbereiteter Release passt nicht zu Kandidat/Merge")
        return target
    work = target.with_name("." + target.name + ".part")
    if work.exists():
        shutil.rmtree(work)
    shutil.copytree(row["candidate_path"], work)
    try:
        verify_release(work)
        checked_impact(store, row)
        (work / "release.json").unlink()
        audit_path = work / "admin" / "approval.json"
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        with store.db() as c:
            prior = [
                dict(r)
                for r in c.execute(
                    "SELECT * FROM decision WHERE revision IN (?,?)",
                    (audit["mapping"]["id"], audit["settings"]["id"]),
                )
            ]
        audit.update(
            state="APPROVED",
            decisions=prior + [decision],
            baseline_release_id=row["baseline_release_id"],
            candidate_release_id=row["candidate_release_id"],
            git_evidence=git_evidence,
        )
        audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
        # Keep the reviewed DuckDB bytes, including its candidate identity.
        # approval.json links that identity to this publication; data is never rebuilt.
        candidate_manifest = json.loads((Path(row["candidate_path"]) / "release.json").read_text())
        manifest = release_manifest(work, rid, datetime.now(timezone.utc), candidate_manifest.get("years", ()))
        (work / "release.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        work.rename(target)
    except BaseException:
        shutil.rmtree(work, ignore_errors=True)
        raise
    return target


def finish_publication(store, impact_id):
    """Called under writer_lock; also handles a crash after pointer replacement."""
    from storage.release import setze_aktuell

    with store.db() as c:
        found = c.execute("SELECT * FROM impact WHERE id=?", (impact_id,)).fetchone()
        row = dict(found) if found else None
        if not row or row["status"] != "APPROVED_PENDING_PUBLICATION":
            raise AdminError("Keine genehmigte ausstehende Publikation")
        decision = c.execute(
            "SELECT * FROM decision WHERE revision=?", (row["revision_id"],)
        ).fetchone()
        if not decision or decision["decision"] != "approve":
            raise AdminError("Keine persistierte Freigabe fuer Publikation")
        if active_id(store) not in {row["baseline_release_id"], row["published_release_id"]}:
            raise AdminError(
                "Aktiver Release veraendert; ausstehende Publikation nicht uebernehmen"
            )
        revision = store.get(row["revision_id"])
        from .release_flow import requires_git

        coupled = requires_git(row, revision)
        if coupled:
            from .coupled_git import publication_evidence

            publication_evidence(store, row)
        target = release_path(store, row["published_release_id"])
        if (
            not row.get("published_manifest_hash")
            or file_hash(target / "release.json") != row["published_manifest_hash"]
        ):
            raise AdminError("Genehmigtes Releasemanifest wurde veraendert")
        manifest = verify_release(target)
        if coupled:
            from .impact_archive import persist_events

            persist_events(store, row["id"])
        import os

        if os.getenv("ADMIN_OBJECT_STORE", "local") == "s3":
            from .object_store import publish_release

            publish_release(store, target, row["baseline_release_id"])
        setze_aktuell(store.data / "releases" / "AKTUELL.json", manifest)
        if coupled:
            c.execute(
                "UPDATE head SET revision=? WHERE resource=?",
                (row["revision_id"], revision["resource"]),
            )
            from .release_flow import event

            event(
                c,
                row,
                "PUBLISHED",
                decision["actor"],
                "Geprueften gemergten Release aktiviert",
                {"release_id": row["published_release_id"]},
            )
        c.execute("UPDATE impact SET status='PUBLISHED' WHERE id=?", (impact_id,))
    return row["published_release_id"]


def abandon(store, impact_id, actor, reason):
    """Explicit recovery after the operator verified the old process has stopped."""
    from .jobs import writer_lock

    if not actor.strip() or not reason.strip():
        raise AdminError("Bearbeiter und Abbruchbegruendung erforderlich")
    with writer_lock(store):
        with store.db() as c:
            c.execute("BEGIN IMMEDIATE")
            impact = c.execute("SELECT * FROM impact WHERE id=?", (impact_id,)).fetchone()
            job = c.execute("SELECT * FROM job WHERE id=?", (impact_id,)).fetchone()
            if not impact or not job or impact["status"] != "RUNNING" or job["status"] != "RUNNING":
                raise AdminError("Nur nachweislich abgebrochene RUNNING-Impact-Laeufe markieren")
            recovery = {
                "ok": False,
                "error_type": "ExplicitAbandonment",
                "error": reason.strip(),
                "recovered_by": actor.strip(),
                "recovered_at": now(),
                "impact_id": impact_id,
            }
            folder = store.root / "jobs" / impact_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / "recovery.json").write_text(
                json.dumps(recovery, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            if not (folder / "result.json").exists():
                (folder / "result.json").write_text(
                    json.dumps(recovery, indent=2, ensure_ascii=False), encoding="utf-8"
                )
            with (folder / "run.log").open("a", encoding="utf-8") as log:
                log.write("\n" + encode(recovery) + "\n")
            c.execute(
                "UPDATE impact SET status='FAILED',error=?,finished_at=? WHERE id=?",
                (encode(recovery), now(), impact_id),
            )
            c.execute(
                "UPDATE job SET status='FAILED',result=?,finished_at=?,log_path=? WHERE id=?",
                (encode(recovery), now(), str(folder / "run.log"), impact_id),
            )
        from .impact_archive import persist, mark_pending

        try:
            persist(store, impact_id)
        except Exception as exc:
            mark_pending(store, impact_id, exc)
    return recovery
