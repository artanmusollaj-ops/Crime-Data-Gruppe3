"""Persistent personal views over shared revisions; assignment never grants approval."""
from .store import AdminError, now


def overview(store, actor):
    with store.db() as c:
        return {
            "assignments": [dict(r) for r in c.execute("SELECT * FROM review_assignment")],
            "read": [dict(r) for r in c.execute("SELECT * FROM review_read WHERE actor=?", (actor,))],
        }


def update(store, rid, actor, action):
    if action not in {"claim", "release", "read"}:
        raise AdminError("Unbekannte Inbox-Aktion")
    with store.db() as c:
        c.execute("BEGIN IMMEDIATE")
        rev = c.execute("SELECT * FROM revision WHERE id=?", (rid,)).fetchone()
        if not rev or not rev["parent"]:
            raise AdminError("Aenderungsantrag nicht gefunden")
        if action == "read":
            c.execute("INSERT OR REPLACE INTO review_read VALUES(?,?,?)", (rid, actor, now()))
        else:
            if c.execute("SELECT 1 FROM decision WHERE revision=?", (rid,)).fetchone():
                raise AdminError("Antrag bereits entschieden")
            assigned = c.execute("SELECT actor FROM review_assignment WHERE revision_id=?", (rid,)).fetchone()
            if assigned and assigned[0] != actor:
                raise AdminError("Review bereits von einer anderen Person uebernommen")
            if action == "claim":
                if rev["actor"].strip().casefold() == actor.strip().casefold():
                    raise AdminError("Eigene Antraege koennen nicht zum Review uebernommen werden")
                c.execute("INSERT OR REPLACE INTO review_assignment VALUES(?,?,?)", (rid, actor, now()))
            else:
                if not assigned:
                    raise AdminError("Keine eigene Zuweisung vorhanden")
                c.execute("DELETE FROM review_assignment WHERE revision_id=?", (rid,))
        c.execute("INSERT INTO review_inbox_event(revision_id,actor,action,created_at) VALUES(?,?,?,?)", (rid,actor,action,now()))
    return {"revision_id": rid, "action": action}
