"""Read-only source run inventory and code catalog for both cities."""

import ast
import hashlib
import json

from .store import AdminError, rows


def source_status(store):
    from .integration import manifest_paths, manifest_text
    result = []
    for city in ("chicago", "detroit"):
        runs = []
        root = store.data / "bronze" / f"city={city}"
        for relative in manifest_paths(store, city):
            path = store.data / relative
            if any(part.startswith(".") for part in path.relative_to(root).parts):
                continue
            try:
                value = json.loads(manifest_text(store, relative))
                runs.append(
                    {
                        "run_id": value.get("run_id", path.parent.name),
                        "status": value.get("status"),
                        "mode": value.get("mode", value.get("extraction_mode")),
                        "event_year": value.get("event_year", value.get("year")),
                        "years": value.get("years"),
                        "row_count": value.get(
                            "row_count", value.get("downloaded_count", value.get("rows"))
                        ),
                        "watermark": value.get("watermark"),
                        "completed_at_utc": value.get(
                            "completed_at_utc", value.get("completed_at", value.get("started_at"))
                        ),
                        "relative_path": path.relative_to(store.data).as_posix(),
                    }
                )
            except (OSError, ValueError):
                runs.append({"run_id": path.parent.name, "status": "INVALID_MANIFEST"})
        runs.sort(
            key=lambda x: x["relative_path"] if "relative_path" in x else x["run_id"], reverse=True
        )
        result.append({"city": city, "run_count": len(runs), "runs": runs[:20]})
    return result


def mapping_catalog(store, city):
    names = {
        "chicago": ("iucr_nibrs_mapping.csv", "iucr", "ibr_code"),
        "detroit": ("micr_nibrs_mapping.csv", "micr_code", "nibrs_code"),
    }
    if city not in names:
        raise AdminError("Unbekannte Stadt")
    name, key, target = names[city]
    records = rows(store.current("mapping")["payload"][name])[1]
    return [
        {
            "code": row[key],
            "target": row[target],
            "mapped": row["mapped"],
            "match": row["match"],
            "description": row.get(
                "description", row.get("micr_description", row.get("primary_description", ""))
            ),
            "note": row.get("note", ""),
        }
        for row in records
    ]


# Explicit, read-only allowlist. No request parameter is used as a file path.
SOURCE_FILES = {
    "chicago": ("chicago_pipeline/download_chicago.py",),
    "detroit": (
        "detroit_pipeline/extract_detroit.py",
        "detroit_pipeline/detroit_arcgis.py",
        "detroit_pipeline/bronze_parquet.py",
        "detroit_pipeline/bronze_manifest.py",
    ),
}


def source_code(store, city, module=None, run_path=None):
    allowed = SOURCE_FILES.get(city)
    if not allowed:
        raise AdminError("Unbekannte Stadt")
    module = module or allowed[0]
    if module not in allowed:
        raise AdminError("Quellmodul nicht freigegeben")
    root = (store.project / "src" / "crime").resolve()
    path = (root / module).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise AdminError("Freigegebene Quelldatei nicht vorhanden")
    raw = path.read_bytes()
    result = {
        "highlights": highlight_ranges(module, raw.decode("utf-8")),
        "city": city, "module": module, "modules": list(allowed),
        "code": raw.decode("utf-8"), "sha256": hashlib.sha256(raw).hexdigest(),
        "source_kind": "current_web_project",
        "version_note": "Aktueller Code des Webserver-Projekts; kein Nachweis des historischen Worker-Codes.",
        "historical_available": False,
    }
    if run_path:
        bronze = (store.data / "bronze" / ("city=" + city)).resolve()
        manifest = (store.data / run_path).resolve()
        if not manifest.is_relative_to(bronze) or manifest.name != "manifest.json":
            raise AdminError("Ungueltiger Quelllaufpfad")
        if any(part.startswith(".") for part in manifest.relative_to(bronze).parts):
            raise AdminError("Unvollstaendiger Quelllauf")
        try:
            from .integration import manifest_text
            value = json.loads(manifest_text(store, manifest.relative_to(store.data).as_posix()))
        except (OSError, ValueError) as exc:
            raise AdminError("Quelllaufmanifest nicht lesbar") from exc
        if not isinstance(value, dict):
            raise AdminError("Ungueltiges Quelllaufmanifest")
        # Only documented non-secret metadata, never arbitrary source URLs or credentials.
        fields = ("run_id", "status", "mode", "extraction_mode", "event_year", "year",
                  "years", "lookback_days", "reference_date", "started_at_utc",
                  "completed_at_utc", "started_at", "completed_at", "row_count",
                  "downloaded_count", "rows", "code_version")
        result["run"] = {key: value[key] for key in fields if key in value}
        result["run_path"] = run_path
        result["history_note"] = "Historischer Quellstand nicht verfügbar. Angezeigt wird aktueller Code. Fehlende Laufparameter sind im Manifest nicht dokumentiert."
    return result


def highlight_ranges(module, code):
    modes = {"full": [], "daily": [], "delta": []}
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return modes
    names = {"full": {"extract_year", "build_year_where", "build_date_where"},
             "daily": {"extract_delta", "build_delta_where", "previous_watermark", "delta_start"},
             "delta": {"extract_delta", "build_delta_where", "previous_watermark", "delta_start"}}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        for mode in modes:
            if node.name in names[mode]:
                modes[mode].append([node.lineno, node.end_lineno])
        if module == "detroit_pipeline/extract_detroit.py" and node.name == "main":
            for branch in node.body:
                if isinstance(branch, ast.If) and ast.unparse(branch.test) in {"args.mode == 'full'", 'args.mode == "full"'}:
                    modes["full"].append([branch.lineno, branch.end_lineno])
                if isinstance(branch, ast.If) and ast.unparse(branch.test) == "args.mode == 'delta'":
                    modes["daily"].append([branch.lineno, branch.end_lineno])
                    modes["delta"].append([branch.lineno, branch.end_lineno])
    if module == "chicago_pipeline/download_chicago.py":
        for line, text in enumerate(code.splitlines(), 1):
            if "updated_from = delta_start(" in text or 'mode = "delta" if updated_from' in text:
                for mode in modes:
                    modes[mode].append([line, line])
            if "if updated_from:" in text:
                modes["daily"].append([line, line + 1])
    return modes
