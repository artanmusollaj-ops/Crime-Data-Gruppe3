"""Package source and documentation, excluding data, credentials and test caches."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

EXCLUDE = {".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
           "pytest-of-root", "data", "logs", "tmp", "dist", "build"}
MANIFEST = "docs/LIEFERUMFANG_KONSOLE.json"


def inventory(root):
    result = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root)
        if (not path.is_file() or path.is_symlink() or any(p in EXCLUDE or p.endswith(".egg-info") for p in rel.parts)
                or path.name == ".env" or path.suffix in {".pyc", ".pyo"} or rel.as_posix() == MANIFEST):
            continue
        result[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--version", default="Crime_Data_2026-10-26_v1.0")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    before, after = inventory(args.baseline.resolve()), inventory(root)
    report = {"package": args.version,
              "infrastructure_commit": "e193d97555211965f2d8df00648dc8da89c135c0",
              "console_base": "Crime_Data_2026-10-09_v3.0",
              "new": [p for p in sorted(after) if p not in before],
              "modified": [p for p in sorted(after) if p in before and after[p] != before[p]],
              "removed": sorted(before.keys() - after.keys()),
              "unchanged_count": sum(before.get(p) == sha for p, sha in after.items()),
              "files_sha256": after,
              "note": "Manifest excludes itself. No data, credentials, venv or test caches."}
    (root / MANIFEST).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / (args.version + ".zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for rel in sorted([*after, MANIFEST]):
            archive.write(root / rel, "Crime-Data-Gruppe3/" + rel)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity failed")
    print(json.dumps({"path": str(target.resolve()), "bytes": target.stat().st_size,
                      "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "new": len(report["new"]), "modified": len(report["modified"]),
                      "removed": report["removed"]}, indent=2))


if __name__ == "__main__":
    main()
