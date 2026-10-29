"""Link runs by manifest hashes, not by coincidental timestamps or city names."""
import hashlib
import json
from .store import AdminError, now


def inventory(store, city):
    from .integration import manifest_paths, manifest_text
    return {p: hashlib.sha256(manifest_text(store, p).encode()).hexdigest()
            for p in manifest_paths(store, city)}


def capture(store, city, before, folder, job, spec):
    after = inventory(store, city)
    links = [{"manifest_path": p, "sha256": sha} for p, sha in after.items() if before.get(p) != sha]
    result = {"job_id": job["id"], "city": city, "captured_at": now(), "parameters": spec, "runs": links}
    (folder / "source_runs.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_json(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def redact(value):
    if isinstance(value, dict):
        return {k: ("[redacted]" if any(word in k.lower() for word in ("token", "secret", "password", "authorization", "url")) else redact(v)) for k,v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


def evidence(store, city, run_path):
    if city not in {"chicago", "detroit"}:
        raise AdminError("Unbekannte Stadt")
    root = (store.data / "bronze" / ("city=" + city)).resolve()
    path = (store.data / run_path).resolve()
    if not path.is_relative_to(root) or path.name != "manifest.json" or any(x.startswith(".") for x in path.relative_to(root).parts):
        raise AdminError("Ungueltiger Quelllaufpfad")
    try:
        from .integration import manifest_text
        raw = manifest_text(store, path.relative_to(store.data).as_posix()).encode()
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise ValueError("Manifest ist kein Objekt")
    except (OSError, ValueError) as exc:
        raise AdminError("Quelllaufmanifest nicht lesbar") from exc
    sha = hashlib.sha256(raw).hexdigest()
    relative = path.relative_to(store.data).as_posix()
    linked_jobs, impacts = [], []
    with store.db() as c:
        jobs = [dict(j) for j in c.execute("SELECT id,name,status,started_at,finished_at FROM job")]
        attempts = [dict(i) for i in c.execute("SELECT id,status,published_release_id,candidate_release_id FROM impact")]
    for job in jobs:
        folder = store.root / "jobs" / job["id"]
        proof = safe_json(folder / "source_runs.json")
        if any(x.get("manifest_path") == relative and x.get("sha256") == sha for x in proof.get("runs", [])):
            linked_jobs.append({**job, "parameters": proof.get("parameters"), "log_available": (folder / "run.log").is_file()})
    snapshot_key = relative.removeprefix("bronze/")
    for attempt in attempts:
        snapshot = safe_json(store.root / "jobs" / attempt["id"] / "source_snapshot.json")
        if snapshot.get("files", {}).get(snapshot_key) == sha:
            impacts.append(attempt)
    return {"run_path": relative, "manifest_sha256": sha, "manifest": redact(manifest),
            "jobs": linked_jobs, "impacts": impacts, "historical_source_available": False,
            "note": "Verknuepfungen beruhen auf gespeicherten Manifest-Hashes. Fehlende Verweise bedeuten nicht dokumentiert. Der berechnete Hash beweist allein keine historische Unveraendertheit."}
