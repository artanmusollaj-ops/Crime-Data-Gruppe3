"""Semantic overlap detection for submitted revisions, evaluated inside approval's transaction.

Mapping rows are indivisible review units. Settings use JSON paths with jobs keyed
by name. Drafts in another browser and arbitrary Git branches are not registered.
"""

import json

from .store import OVERRIDES, ROW_KEYS, AdminError, digest, row_key, rows, write_rows


def locations(resource, payload):
    if resource == "mapping":
        result = {}
        for name, content in payload.items():
            if name in ROW_KEYS:
                _, records = rows(content)
                label = "/".join(ROW_KEYS[name])
                for index, row in enumerate(records, 2):
                    result[f"config/{name} [{label}={row_key(name, row)}]"] = {
                        "value": row,
                        "line": index,
                    }
            else:
                result["config/" + name] = {"value": content, "line": None}
        return result
    result = {}

    def walk(value, path):
        if isinstance(value, dict) and value:
            for key, item in value.items():
                walk(item, path + "/" + str(key).replace("~", "~0").replace("/", "~1"))
        elif path == "/jobs" and isinstance(value, list):
            for job in value:
                walk(job, path + "/" + job["name"])
        else:
            result[path or "/"] = {"value": value, "line": None}

    walk(payload, "")
    return result


def changes(resource, before, after):
    old, new = locations(resource, before), locations(resource, after)
    return {
        key: {"location": key, "before": old.get(key), "after": new.get(key)}
        for key in sorted(old.keys() | new.keys())
        if (old.get(key) or {}).get("value") != (new.get(key) or {}).get("value")
        or (key in old) != (key in new)
    }


def revision(c, rid):
    raw = c.execute("SELECT * FROM revision WHERE id=?", (rid,)).fetchone()
    if not raw:
        raise AdminError("Revision nicht gefunden")
    value = dict(raw)
    value["payload"] = json.loads(value["payload"])
    if digest(value["payload"]) != value["sha256"]:
        raise AdminError("Revisionsinhalt stimmt nicht mit Pruefsumme ueberein")
    return value


def inspect(store, c, rid):
    r = revision(c, rid)
    if not r["parent"]:
        return {"revision_id": rid, "blocked": False, "stale": False, "changes": [], "overlaps": []}
    mine = changes(r["resource"], revision(c, r["parent"])["payload"], r["payload"])
    head = c.execute("SELECT revision FROM head WHERE resource=?", (r["resource"],)).fetchone()[0]
    overlaps = []
    for raw in c.execute(
        """SELECT r.id FROM revision r LEFT JOIN decision d ON d.revision=r.id
            WHERE r.resource=? AND r.id<>? AND r.parent IS NOT NULL AND d.id IS NULL""",
        (r["resource"], rid),
    ).fetchall():
        other = revision(c, raw[0])
        theirs = changes(r["resource"], revision(c, other["parent"])["payload"], other["payload"])
        matches = []
        for key, own in mine.items():
            for other_key, change in theirs.items():
                if (
                    key == other_key
                    or key.startswith(other_key + "/")
                    or other_key.startswith(key + "/")
                ):
                    matches.append({"location": key, "mine": own, "theirs": change})
        if not matches:
            continue
        impact = c.execute(
            "SELECT id,status,report_hash FROM impact WHERE revision_id=? ORDER BY created_at DESC LIMIT 1",
            (other["id"],),
        ).fetchone()
        overlaps.append(
            {
                "revision_id": other["id"],
                "actor": other["actor"],
                "reason": other["reason"],
                "created_at": other["created_at"],
                "impact": dict(impact) if impact else None,
                "locations": matches,
            }
        )
    return {
        "revision_id": rid,
        "stale": head != r["parent"],
        "current_revision": head,
        "blocked": bool(overlaps) or head != r["parent"],
        "changes": list(mine.values()),
        "overlaps": overlaps,
    }


def all_pending(store):
    with store.db() as c:
        c.execute("BEGIN")
        ids = [
            r[0]
            for r in c.execute("""SELECT r.id FROM revision r LEFT JOIN decision d ON d.revision=r.id
                                         WHERE r.parent IS NOT NULL AND d.id IS NULL""")
        ]
        return {rid: inspect(store, c, rid) for rid in ids}


def merge_payload(resource, base, proposed, current):
    """Three-way merge: preserve concurrent edits; reject divergent edits to one unit."""
    import copy

    if resource == "data":
        return copy.deepcopy(proposed)
    missing = object()

    def merge(old, own, latest, path):
        if own == old:
            return latest
        if latest == old or own == latest:
            return own
        if all(isinstance(v, dict) for v in (old, own, latest)):
            result = {}
            for key in old.keys() | own.keys() | latest.keys():
                value = merge(
                    old.get(key, missing),
                    own.get(key, missing),
                    latest.get(key, missing),
                    path + "/" + key,
                )
                if value is not missing:
                    result[key] = value
            return result
        raise AdminError(
            "Merge-Konflikt bei " + path + "; aktuellen Stand und Diff manuell abstimmen"
        )

    if resource == "mapping":
        result = copy.deepcopy(current)
        own_changes = changes(resource, base, proposed)
        current_locations = locations(resource, current)
        for location, change in own_changes.items():
            latest = current_locations.get(location)
            if latest != change["before"] and latest != change["after"]:
                # CSV position changes alone do not change the review unit.
                if (latest or {}).get("value") not in [
                    (change["before"] or {}).get("value"),
                    (change["after"] or {}).get("value"),
                ]:
                    raise AdminError("Merge-Konflikt bei " + location)
        for name, content in proposed.items():
            if content == base.get(name):
                continue
            if name not in ROW_KEYS:
                if current.get(name) not in (base.get(name), content):
                    raise AdminError("Merge-Konflikt bei config/" + name)
                result[name] = content
                continue
            fields, records = rows(current[name])
            _, before = rows(base[name])
            _, after = rows(content)
            old = {row_key(name, r): r for r in before}
            own = {row_key(name, r): r for r in after}
            live = {row_key(name, r): r for r in records}
            for code in old.keys() | own.keys():
                if old.get(code) != own.get(code):
                    if code in own:
                        live[code] = own[code]
                    else:
                        live.pop(code, None)
            # Overrides in key order, so two merges of the same rows agree;
            # every other file keeps the order it came in.
            records = [live[k] for k in sorted(live)] if name == OVERRIDES else list(live.values())
            result[name] = write_rows(name, fields, records)
        return result

    def normalized(payload):
        value = copy.deepcopy(payload)
        value["jobs"] = {j["name"]: j for j in value["jobs"]}
        return value

    result = merge(normalized(base), normalized(proposed), normalized(current), "")
    result["jobs"] = list(result["jobs"].values())
    return result


def rebase(store, rid, actor, reason):
    from .jobs import writer_lock

    with writer_lock(store):
        old = store.get(rid)
        if old["actor"].strip().casefold() != actor.strip().casefold():
            raise AdminError("Nur der Autor kann seinen Vorschlag ersetzen")
        current = store.current(old["resource"])
        payload = merge_payload(
            old["resource"], store.get(old["parent"])["payload"], old["payload"], current["payload"]
        )
        return store.propose(old["resource"], payload, current["id"], actor, reason, supersedes=rid)
