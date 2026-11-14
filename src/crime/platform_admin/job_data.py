"""Which job holds the data of the active release, and when a job's data may go.

Every candidate is built in its own folder ``jobs/<id>/data`` (Bronze snapshot,
Silver, Gold). Notebooks 34 and 37 need exactly that folder for the release that
is active: the release itself carries no Bronze and only part of Silver.

**Pointer.** ``finish_publication`` records, for each release it activates, the
job whose folder holds its data (``jobs/ANALYSE.json``). The notebooks look up
the release named by ``releases/AKTUELL.json`` there, not the most recent entry,
so switching back to an older release also selects that release's data. The file
sits in ``jobs/`` because that is the only part of the console volume Jupyter
mounts, read-only.

**Retention.** A job's ``data/`` is a full copy of the inputs, hundreds of MB
each, and it also goes into the daily control backup. ``prune`` removes it once
nobody can need it again. The evidence next to it (run.log, impact report,
result.json) always stays. Protected are:

* running and queued jobs, and candidates whose decision or publication is
  still in progress;
* candidates in review (READY, BLOCKED) as long as their baseline is the active
  release - after that they can no longer be approved;
* the active release's job and the ``ADMIN_JOB_DATA_KEEP`` most recently
  activated ones before it (default 2 in total), so that switching back finds
  its data.

A folder an analysis session is reading is skipped and retried on the next tick.
"""

from __future__ import annotations

import json
import os
import shutil

from orchestration.analyse import ZEIGER as POINTER

from .store import AdminError, now

KEEP = 2

#: Impact states whose data is still needed whatever the active release is.
IN_PROGRESS = {"QUEUED", "RUNNING", "AWAITING_GIT", "APPROVED_PENDING_PUBLICATION",
               "ARCHIVE_PENDING"}
#: Candidates in review: needed while their baseline is still the active release.
IN_REVIEW = {"READY", "BLOCKED"}


def keep():
    value = int(os.getenv("ADMIN_JOB_DATA_KEEP", str(KEEP)))
    if value < 1:
        raise AdminError("ADMIN_JOB_DATA_KEEP muss mindestens 1 sein")
    return value


def pointer_path(store):
    return store.root / "jobs" / POINTER


def read_pointer(store):
    path = pointer_path(store)
    if not path.is_file():
        return {"version": 1, "releases": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_pointer(store, value):
    path = pointer_path(store)
    path.parent.mkdir(parents=True, exist_ok=True)
    work = path.with_name(path.name + ".part")
    work.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    work.replace(path)


def set_pointer(store, row):
    """Record that ``row``'s published release reads its data from ``row``'s job.

    Called by finish_publication after the active pointer moved, under the
    writer lock. Idempotent: a retried publication writes the same entry.
    """
    value = read_pointer(store)
    entry = value["releases"].get(row["published_release_id"])
    if entry is None or entry["impact_id"] != row["id"]:
        value["releases"][row["published_release_id"]] = {
            "impact_id": row["id"],
            "candidate_release_id": row["candidate_release_id"],
            "data": f"{row['id']}/data",
            "activated_at": now(),
        }
    else:
        entry["activated_at"] = now()
    _write_pointer(store, value)
    return value["releases"][row["published_release_id"]]


def protected(store):
    """Job ids whose data must stay, with the reason for each."""
    from .candidates import active_id

    active = active_id(store)
    reasons = {}
    with store.db() as c:
        for jid, status in c.execute("SELECT id,status FROM job"):
            if status in {"QUEUED", "RUNNING"}:
                reasons[jid] = "job " + status
        for iid, status, baseline in c.execute(
                "SELECT id,status,baseline_release_id FROM impact"):
            if status in IN_PROGRESS:
                reasons[iid] = "impact " + status
            elif status in IN_REVIEW and baseline == active:
                reasons[iid] = "review " + status
        # Auch ohne Zeiger-Eintrag: ein Release, das vor dem Job-Zeiger
        # aktiviert wurde, kennt seinen Job nur aus der Kontrolldatenbank.
        for (iid,) in c.execute("SELECT id FROM impact WHERE published_release_id=?", (active,)):
            reasons[iid] = "active release " + str(active)
    releases = read_pointer(store)["releases"]
    recent = sorted(releases.items(), key=lambda kv: kv[1]["activated_at"], reverse=True)
    if active in releases:
        reasons[releases[active]["impact_id"]] = "active release " + active
    for rid, entry in recent[:keep()]:
        reasons.setdefault(entry["impact_id"], "recent release " + rid)
    return reasons


def plan(store):
    """What ``prune`` would remove: ``[(job id, bytes)]``, nothing touched."""
    jobs = (store.root / "jobs").resolve()
    if not jobs.is_dir():
        return []
    keep_ids = protected(store)
    with store.db() as c:
        impacts = {r[0] for r in c.execute("SELECT id FROM impact")}
    found = []
    for jid in sorted(impacts - set(keep_ids)):
        data = jobs / jid / "data"
        if not data.is_dir() or not data.resolve().is_relative_to(jobs):
            continue
        size = sum(f.stat().st_size for f in data.rglob("*") if f.is_file())
        found.append((jid, size))
    return found


def prune(store, dry_run=False):
    """Remove ``jobs/<id>/data`` of every job that is not protected.

    Caller holds writer_lock. Returns the removed job ids - with ``dry_run``
    those that would go, nothing removed. Only impact jobs have a data folder;
    imports and batches write into the data root itself.
    """
    from storage.analysesitzung import AnalyseFehler, datensperre

    candidates = [jid for jid, _ in plan(store)]
    if dry_run:
        return candidates
    removed = []
    for jid in candidates:
        data = store.root / "jobs" / jid / "data"
        try:
            with datensperre(data, schreiben=True):
                shutil.rmtree(data)
        except AnalyseFehler:
            continue
        removed.append(jid)
    if removed:
        value = read_pointer(store)
        gone = set(removed)
        value["releases"] = {rid: e for rid, e in value["releases"].items()
                             if e["impact_id"] not in gone}
        _write_pointer(store, value)
    return removed
