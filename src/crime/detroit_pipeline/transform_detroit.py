"""Parst einen Detroit-Bronze-Snapshot in eine Silver-nahe Tabelle.

Beispiele:

    python -m detroit_pipeline.transform_detroit \
        data/bronze/city=detroit/full/year=2024/run_UUID/part-0001.parquet \
        --output data/silver/detroit_crime_2024.parquet

    python -m detroit_pipeline.transform_detroit INPUT.parquet \
        --output OUTPUT.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Iterable

from .detroit_arcgis import DataQualityError, parse_detroit_feature
from .bronze_manifest import validate_manifest
import pyarrow.parquet as pq


def iter_bronze_records(path: Path) -> Iterable[dict]:
    """Read verified Parquet batches; legacy NDJSON is an explicit migration fallback."""

    if path.suffix == '.parquet':
        checked, manifest = validate_manifest(path.parent / 'manifest.json')
        if path.resolve() != checked.resolve():
            raise DataQualityError('Datei nicht im Manifest referenziert')
        with pq.ParquetFile(path) as pf:
            for batch in pf.iter_batches(batch_size=2000):
                for row in batch.to_pylist():
                    feature = json.loads(row['_feature_json'])
                    feature['_meta'] = {
                        'source_system': row['source_system'],
                        'pipeline_run_id': row['pipeline_run_id'],
                        'ingested_at': row['ingested_at_utc'].isoformat(),
                        'schema_fingerprint': manifest['schema_fingerprint'],
                    }
                    yield feature
        return
    if path.suffix not in ('.ndjson', '.jsonl'):
        raise DataQualityError('Erwartet Parquet oder Legacy-NDJSON')

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise DataQualityError(
                    f"Ungueltiges JSON in {path}, Zeile {line_number}"
                ) from exc


def parse_records(path: Path) -> tuple[list[dict], dict]:
    """Transformiert Bronze-Zeilen und sammelt Data-Quality-Kennzahlen.

    Der Parser verwirft keine Zeile. Nicht gemappte Kategorien und ungueltige
    Datensaetze bleiben erhalten, werden jedoch von ``analysis_eligible``
    ausgeschlossen.
    """

    rows: list[dict] = []
    mapping_counts: dict[str, int] = {}
    quality_flag_counts: dict[str, int] = {}
    eligible_count = 0
    event_keys: set[str] = set()
    offense_keys: set[str] = set()

    for bronze_record in iter_bronze_records(path):
        metadata = bronze_record.get("_meta") or {}
        row = parse_detroit_feature(
            bronze_record,
            pipeline_run_id=str(metadata.get("pipeline_run_id") or "UNKNOWN"),
            ingested_at=str(metadata.get("ingested_at") or "UNKNOWN"),
        )
        rows.append(row)
        mapping = str(row["mapping_status"])
        mapping_counts[mapping] = mapping_counts.get(mapping, 0) + 1
        if row["analysis_eligible"]:
            eligible_count += 1
        if row["event_key"]:
            event_keys.add(row["event_key"])
        if row["offense_key"]:
            if row["offense_key"] in offense_keys:
                raise DataQualityError(
                    f"Doppelter offense_key: {row['offense_key']}"
                )
            offense_keys.add(row["offense_key"])
        for flag in filter(None, str(row["quality_flags"]).split(";")):
            quality_flag_counts[flag] = quality_flag_counts.get(flag, 0) + 1

    report = {
        "input_file": str(path),
        "silver_rows": len(rows),
        "distinct_events": len(event_keys),
        "distinct_offenses": len(offense_keys),
        "analysis_eligible_rows": eligible_count,
        "mapping_counts": mapping_counts,
        "quality_flag_counts": quality_flag_counts,
        "transformed_at": datetime.now(timezone.utc).isoformat(),
    }
    return rows, report


def write_csv_atomic(rows: list[dict], path: Path) -> None:
    """Schreibt Silver als portables CSV und publiziert die Datei atomisch."""

    if not rows:
        raise DataQualityError("Keine Zeilen zum Schreiben vorhanden")
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    temporary_path.replace(path)


def write_jsonl_atomic(rows: list[dict], path: Path) -> None:
    """Schreibt Silver als typbewahrendes NDJSON ohne Zusatzabhaengigkeiten."""

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    with temporary_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary_path.replace(path)


def write_parquet_atomic(rows: list[dict], path: Path) -> None:
    """Schreibt komprimiertes Parquet; benoetigt das optionale ``pyarrow``."""

    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise RuntimeError(
            "Parquet-Ausgabe benoetigt pyarrow: pip install pyarrow"
        ) from exc

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    table = pa.Table.from_pylist(rows)
    pq.write_table(table, temporary_path, compression="zstd")
    temporary_path.replace(path)


def transform(bronze_path: Path, output_path: Path) -> tuple[Path, Path]:
    """Fuehrt Parsing, Qualitaetsbericht und atomische Ausgabe aus."""

    # SCHRITT 1: Bronze wird gelesen und zeilenweise fachlich normalisiert.
    rows, report = parse_records(bronze_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # SCHRITT 2: Die Dateiendung bestimmt das Ausgabeformat. Parquet ist fuer
    # Analytics empfohlen; CSV/NDJSON erleichtern Inspektion und Debugging.
    suffix = output_path.suffix.lower()
    if suffix == ".parquet":
        write_parquet_atomic(rows, output_path)
    elif suffix == ".csv":
        write_csv_atomic(rows, output_path)
    elif suffix in {".jsonl", ".ndjson"}:
        write_jsonl_atomic(rows, output_path)
    else:
        raise ValueError("Output muss .parquet, .csv, .jsonl oder .ndjson sein")

    # SCHRITT 3: Der Qualitaetsbericht wird neben Silver gespeichert und kann
    # durch CI, Monitoring oder ein Data-Quality-Dashboard ausgewertet werden.
    report["output_file"] = str(output_path)
    report_path = output_path.with_suffix(output_path.suffix + ".quality.json")
    temporary_report = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary_report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_report.replace(report_path)
    return output_path, report_path


def parse_args() -> argparse.Namespace:
    """Definiert die CLI-Parameter fuer die Transformation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bronze_path", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    """Startet die Bronze-nach-Silver-Transformation."""

    args = parse_args()
    output_path, report_path = transform(args.bronze_path, args.output)
    print(f"Silver:  {output_path}")
    print(f"Quality: {report_path}")


if __name__ == "__main__":
    main()
