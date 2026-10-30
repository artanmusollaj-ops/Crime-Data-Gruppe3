"""Scheduled data runs are approved by the quality gate, not by a person.

Decision of 30.10.2026: the cron data run published a release every week
without review, and the console keeps that - with its quality gate in front.
A candidate qualifies only if a scheduled batch queued it (origin "batch"):
then mappings and settings are the approved heads, and only the source data
moved. Anything a person proposed or queued keeps four eyes.

The approval goes through candidates.decide like any other, so every check
there still holds - archive, baseline, report hash, Git evidence, the gate
itself (review_ready). It is recorded under its own actor, never a person's.
"""
import json

from .store import AdminError

ACTOR = "quality-gate (automatic)"
REASON = ("Automatische Freigabe: geplanter Quellenlauf, Mappings und Einstellungen "
          "unveraendert, Qualitaetstor bestanden")


def run(store):
    """Approve the oldest qualifying candidate; return its impact id or None."""
    from . import candidates
    from .operations import record_status, schema

    schema(store)
    with store.db() as c:
        rows = c.execute(
            """SELECT i.id, i.revision_id, i.report_hash, r.payload FROM impact i
               JOIN revision r ON r.id = i.revision_id
               LEFT JOIN decision d ON d.revision = i.revision_id
               WHERE i.status = 'READY' AND r.resource = 'data' AND d.revision IS NULL
               ORDER BY i.created_at"""
        ).fetchall()
    for iid, rid, report_hash, payload in rows:
        if json.loads(payload).get("origin") != "batch":
            continue
        try:
            candidates.decide(store, rid, "approve", ACTOR, REASON,
                              impact_id=iid, report_hash=report_hash)
        except AdminError as exc:
            # Left for a person; the overview says why.
            record_status(store, "auto_approval", {"status": "REVIEW_REQUIRED",
                                                   "impact_id": iid, "reason": str(exc)})
            return None
        record_status(store, "auto_approval", {"status": "APPROVED", "impact_id": iid})
        return iid
    return None
