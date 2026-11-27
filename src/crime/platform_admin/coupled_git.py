"""Fail-closed review -> exact Git merge -> immutable data publication."""

import json
from urllib.parse import quote

from .store import AdminError, encode
from . import gitops
from .release_flow import event, verify_waiting


def binding(store, row, d, client, *, publication=False):
    report, archive = verify_waiting(store, row, publication=publication)
    provenance = report["metadata"].get("git_provenance")
    if not provenance or not d or not d.get("coupled"):
        raise AdminError("Gekoppelter Git-Nachweis fehlt")
    expected = (
        row["id"],
        row["report_hash"],
        row["candidate_manifest_hash"],
        archive["manifest_hash"],
    )
    actual = (
        d.get("impact_id"),
        d.get("report_hash"),
        d.get("candidate_manifest_hash"),
        d.get("archive_hash"),
    )
    if actual != expected:
        raise AdminError("Commit/Impact/Archiv-Bindung stimmt nicht")
    if (d["repository"], d["base_branch"], d["base_sha"]) != (
        provenance["repository"],
        provenance["base_branch"],
        provenance["base_sha"],
    ):
        raise AdminError("Git-Basis entspricht nicht Simulation")
    if (client.repo, client.branch) != (d["repository"], d["base_branch"]):
        raise AdminError("Repository-Ziel veraendert")
    return report


def verify_merged(client, d, pr):
    if not d.get("merge_actor"):
        raise AdminError(
            "Externer Merge ohne protokollierten Mergeauftrag; keine automatische Aktivierung"
        )
    if (
        not pr.get("merged")
        or pr["head"]["sha"] != d["commit_sha"]
        or pr["base"]["ref"] != d["base_branch"]
    ):
        raise AdminError("PR nicht unveraendert gemergt")
    sha = pr["merge_commit_sha"]
    commit = client.call("GET", "/git/commits/" + sha)
    if commit["tree"]["sha"] != d["commit_tree"] or [p["sha"] for p in commit["parents"]] != [
        d["base_sha"]
    ]:
        raise AdminError(
            "Merge-Ergebnis weicht vom geprueften Baum/Basiscommit ab; Aktivierung gesperrt"
        )
    head = client.call("GET", "/git/ref/heads/" + client.branch)["object"]["sha"]
    if head != sha:
        comparison = client.call("GET", "/compare/" + sha + "..." + head)
        if comparison.get("status") not in {"ahead", "identical"}:
            raise AdminError("Mergecommit liegt nicht mehr in Main")
    return {
        "repository": d["repository"],
        "base_branch": d["base_branch"],
        "base_sha": d["base_sha"],
        "pr_number": d["number"],
        "commit_sha": d["commit_sha"],
        "tree_sha": d["commit_tree"],
        "merge_sha": sha,
        "merge_actor": d["merge_actor"],
        "impact_id": d["impact_id"],
        "report_hash": d["report_hash"],
        "archive_hash": d["archive_hash"],
        "candidate_manifest_hash": d["candidate_manifest_hash"],
    }


def merge(store, revision, row, actor, client=None):
    """Called with writer_lock; authorization is persisted BEFORE remote mutation."""
    from .candidates import prepare_approved_release, file_hash

    if actor.strip().casefold() == revision["actor"].strip().casefold():
        raise AdminError("Merge muss durch zweite Person erfolgen")
    gh = client or gitops.GitHub()
    d = gitops.saved(store, revision["id"])
    if row["status"] == "PUBLISHED" and d and d.get("state") == "MERGED":
        return d
    binding(store, row, d, gh)
    if not d.get("number"):
        raise AdminError("PR fehlt")
    pr = gh.call("GET", "/pulls/" + str(d["number"]))
    if pr["head"]["sha"] != d["commit_sha"] or pr["base"]["ref"] != gh.branch:
        raise AdminError("PR-Head/Basis veraendert; neuer Impact erforderlich")
    if not pr.get("merged"):
        d["git_protection"] = gitops.check_protection(gh, d["commit_sha"])
        if (
            gh.call("GET", "/git/ref/heads/" + gh.branch)["object"]["sha"] != d["base_sha"]
            or pr["base"]["sha"] != d["base_sha"]
        ):
            raise AdminError(
                "Main seit Simulation veraendert; keine alte Impact-Freigabe verwenden"
            )
        if (
            pr.get("state") != "open"
            or pr.get("draft")
            or pr.get("mergeable") is not True
            or pr.get("mergeable_state") != "clean"
        ):
            raise AdminError("PR nicht mergebereit: CI/Review/Konflikte pruefen")
        # The exported commit must still have the tree returned when it was created.
        head_commit = gh.call("GET", "/git/commits/" + d["commit_sha"])
        if head_commit["tree"]["sha"] != d["commit_tree"] or [
            p["sha"] for p in head_commit["parents"]
        ] != [d["base_sha"]]:
            raise AdminError("PR-Commitbaum veraendert")
        d.update(state="MERGE_REQUESTED", merge_actor=actor)
        gitops.save(store, d)
        with store.db() as c:
            event(
                c,
                row,
                "MERGE_REQUESTED",
                actor,
                "Exakten PR-Head mergen",
                {"commit_sha": d["commit_sha"]},
            )
        result = gh.call(
            "PUT",
            "/pulls/" + str(d["number"]) + "/merge",
            {"sha": d["commit_sha"], "merge_method": "squash"},
        )
        if not result.get("merged"):
            raise AdminError("GitHub hat Merge nicht ausgefuehrt")
        d.update(state="MERGED_UNVERIFIED", merge_sha=result["sha"])
        gitops.save(store, d)
        pr = gh.call("GET", "/pulls/" + str(d["number"]))
    evidence = verify_merged(gh, d, pr)
    # A network failure above leaves the reviewer-approved candidate INACTIVE.
    binding(store, row, d, gh)
    with store.db() as c:
        decision = dict(
            c.execute("SELECT * FROM decision WHERE revision=?", (revision["id"],)).fetchone()
        )
    if row["status"] == "APPROVED_PENDING_PUBLICATION":
        return d
    target = prepare_approved_release(store, row, decision, git_evidence=evidence)
    d.update(
        state="MERGED",
        merge_sha=evidence["merge_sha"],
        evidence=evidence,
        release_id=target.name.removeprefix("release="),
    )
    with store.db() as c:
        c.execute("BEGIN IMMEDIATE")
        status = c.execute("SELECT status FROM impact WHERE id=?", (row["id"],)).fetchone()[0]
        if status != "AWAITING_GIT":
            raise AdminError("Releasezustand waehrend Merge veraendert")
        c.execute(
            "UPDATE impact SET status='APPROVED_PENDING_PUBLICATION',published_release_id=?,published_manifest_hash=? WHERE id=?",
            (d["release_id"], file_hash(target / "release.json"), row["id"]),
        )
        c.execute(
            "UPDATE git_change SET state=?,document=? WHERE revision=?",
            (d["state"], encode(d), revision["id"]),
        )
        event(
            c,
            row,
            "MERGE_VERIFIED",
            actor,
            "Geprueften Release zur Publikation vorbereitet",
            evidence,
        )
    return d


def publication_evidence(store, row, client=None):
    gh = client or gitops.GitHub()
    d = gitops.saved(store, row["revision_id"])
    binding(store, row, d, gh, publication=True)
    if d["state"] != "MERGED":
        raise AdminError("Verifizierter Merge fehlt")
    pr = gh.call("GET", "/pulls/" + str(d["number"]))
    evidence = verify_merged(gh, d, pr)
    if evidence != d.get("evidence"):
        raise AdminError("Merge-Nachweis veraendert")
    from .candidates import release_path

    audit = json.loads(
        (release_path(store, row["published_release_id"]) / "admin/approval.json").read_text()
    )
    if audit.get("git_evidence") != evidence:
        raise AdminError("Release ist nicht an Merge gebunden")
    return evidence


def withdraw(store, rid, actor, reason, client=None):
    """Withdraw before publication, requiring a corrective baseline after a merge."""
    revision = store.get(rid)
    if actor.strip().casefold() == revision["actor"].strip().casefold():
        raise AdminError("Ruecknahme verlangt zweite Person")
    with store.db() as c:
        raw = c.execute(
            "SELECT i.* FROM impact i JOIN decision d ON d.impact_id=i.id WHERE d.revision=? AND d.decision='approve'",
            (rid,),
        ).fetchone()
    if not raw or raw["status"] != "AWAITING_GIT":
        raise AdminError("Nur Freigaben im Status AWAITING_GIT zurueckziehen")
    row = dict(raw)
    d = gitops.saved(store, rid)
    if d:
        gh = client or gitops.GitHub()
        if (gh.repo, gh.branch) != (d["repository"], d["base_branch"]):
            raise AdminError("Repository-Ziel veraendert")
        prs = (
            [gh.call("GET", "/pulls/" + str(d["number"]))]
            if d.get("number")
            else gh.call(
                "GET",
                "/pulls?state=all&head="
                + quote(gh.repo.split("/")[0] + ":" + d["branch"], safe="")
                + "&base="
                + gh.branch,
            )
        )
        for pr in prs:
            if pr.get("merged"):
                # A quarantined merge can be abandoned only after a reviewed
                # corrective Git change restored all active configurations and
                # the deployed runtime again matches current main.
                from .release_flow import capture

                try:
                    corrected = capture(store, json.loads(row["spec"]), client=gh)
                except AdminError as exc:
                    raise AdminError(
                        "Bereits gemergt: Publikation fortsetzen oder zuerst per Korrektur-PR aktive Konfiguration wiederherstellen und Main deployen"
                    ) from exc
                d["corrective_base_sha"] = corrected["base_sha"]
                continue
            if pr.get("state") == "open":
                gh.call("PATCH", "/pulls/" + str(pr["number"]), {"state": "closed"})
            actual = gh.call("GET", "/pulls/" + str(pr["number"]))
            if actual.get("merged") or actual.get("state") != "closed":
                raise AdminError("PR nicht sicher geschlossen")
        d["state"] = "WITHDRAWN"
        gitops.save(store, d)
    with store.db() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute(
            "UPDATE impact SET status='WITHDRAWN' WHERE id=? AND status='AWAITING_GIT'",
            (row["id"],),
        )
        event(
            c,
            row,
            "REVIEW_WITHDRAWN",
            actor,
            reason,
            {
                "report_hash": row["report_hash"],
                "corrective_base_sha": d.get("corrective_base_sha") if d else None,
            },
        )
        c.execute(
            "UPDATE operation SET status='CANCELLED' WHERE kind IN ('git-open','git-merge') AND payload=? AND status='QUEUED'",
            (encode({"id": rid}),),
        )
    return {
        "revision": rid,
        "status": "WITHDRAWN",
        "next": "Neuen Vorschlag einreichen und neu simulieren",
    }
