"""Extrahiert Detroit RMS Crime Features unveraendert in den Bronze Layer.

Beispiel:

    python -m detroit_arcgis_pipeline.extract_detroit --year 2024 \
        --output-dir data/bronze/detroit

Das Ergebnis besteht aus einer NDJSON-Datei und einem Run-Manifest. NDJSON
wird verwendet, weil jede API-Zeile sofort geschrieben werden kann und der
komplette Jahresbestand nicht im Arbeitsspeicher gehalten werden muss.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import logging
from pathlib import Path
from uuid import uuid4

from .detroit_arcgis import (
    ArcGISClient,
    DataQualityError,
    build_year_where,
)


def file_sha256(path: Path) -> str:
    """Berechnet die Checksumme des Bronze-Artefakts fuer Reproduzierbarkeit."""

    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_atomic(path: Path, payload: dict) -> None:
    """Schreibt JSON atomisch, damit nie ein halbes Manifest publiziert wird."""

    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary_path.replace(path)


def extract_year(
    year: int,
    output_dir: Path,
    *,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
) -> tuple[Path, Path]:
    """Fuehrt einen vollstaendigen, count-verifizierten Jahresdownload aus.

    Schritte:

    1. Layer-Schema und ArcGIS-Limits lesen.
    2. Server-Count und feste Object-ID-Liste fuer das Jahr abfragen.
    3. Features ID-basiert in Batches in eine temporaere NDJSON-Datei streamen.
    4. Downloadzahl und finalen Server-Count pruefen.
    5. Bronze-Datei atomisch veroeffentlichen und Manifest schreiben.
    """

    # Der optionale Client ermoeglicht einen isolierten Ingestion-Test ohne
    # Live-Netzwerk. Im produktiven Lauf wird automatisch der echte REST-Client
    # verwendet.
    client = client or ArcGISClient()
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)
    where = build_year_where(year)

    # SCHRITT 1: Metadaten liefern Object-ID-Feld, Seitengroesse und Schema-Hash.
    layer_info = client.get_layer_info()
    effective_batch_size = min(
        batch_size or layer_info.max_record_count,
        layer_info.max_record_count,
    )

    # SCHRITT 2: Count und ID-Liste definieren die erwartete Snapshot-Groesse.
    source_count_before = client.get_count(where)
    object_id_field, object_ids = client.get_object_ids(where)
    if object_id_field != layer_info.object_id_field:
        raise DataQualityError(
            "Object-ID-Feld in Metadaten und Query-Antwort unterscheidet sich"
        )
    if source_count_before != len(object_ids):
        raise DataQualityError(
            f"Source-Count {source_count_before} != ID-Count {len(object_ids)}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"detroit_rms_crime_{year}_{run_id}.ndjson"
    temporary_path = final_path.with_suffix(".ndjson.tmp")

    # SCHRITT 3: Jede rohe ArcGIS-Zeile wird inklusive technischer Provenance
    # sofort geschrieben. Fachliche Transformationen gehoeren nicht in Bronze.
    downloaded_count = 0
    offense_category_counts: dict[str, int] = {}
    try:
        with temporary_path.open("w", encoding="utf-8") as handle:
            for feature in client.iter_features(
                object_ids,
                object_id_field=object_id_field,
                batch_size=effective_batch_size,
                pause_seconds=pause_seconds,
            ):
                bronze_record = {
                    "attributes": feature.get("attributes") or {},
                    "geometry": feature.get("geometry"),
                    "_meta": {
                        "source_system": "detroit_rms_crime",
                        "dataset_id": "RMS_Crime_Incidents",
                        "layer_url": client.layer_url,
                        "pipeline_run_id": run_id,
                        "ingested_at": started_at.isoformat(),
                        "schema_fingerprint": layer_info.schema_fingerprint,
                    },
                }
                handle.write(json.dumps(bronze_record, ensure_ascii=False) + "\n")
                downloaded_count += 1
                raw_category = (feature.get("attributes") or {}).get(
                    "offense_category"
                )
                category = str(raw_category).strip() if raw_category is not None else ""
                category = category or "__MISSING__"
                offense_category_counts[category] = (
                    offense_category_counts.get(category, 0) + 1
                )
        if downloaded_count != len(object_ids):
            raise DataQualityError(
                f"Download-Count {downloaded_count} != ID-Count {len(object_ids)}"
            )
        temporary_path.replace(final_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise

    # SCHRITT 4: Der zweite Count dokumentiert, ob sich die Live-Quelle waehrend
    # des Laufs veraendert hat. Die feste ID-Liste bleibt der Snapshot-Vertrag.
    source_count_after = client.get_count(where)
    finished_at = datetime.now(timezone.utc)

    # SCHRITT 5: Das Manifest macht Vollstaendigkeit, Laufzeit, Filter und
    # Quellzustand maschinenlesbar und kann spaeter vom Monitoring gelesen werden.
    manifest = {
        "pipeline_run_id": run_id,
        "status": "SUCCESS",
        "source_system": "detroit_rms_crime",
        "dataset_id": "RMS_Crime_Incidents",
        "layer_url": client.layer_url,
        "year": year,
        "where": where,
        "object_id_field": object_id_field,
        "schema_fingerprint": layer_info.schema_fingerprint,
        "source_count_before": source_count_before,
        "snapshot_object_id_count": len(object_ids),
        "downloaded_count": downloaded_count,
        "offense_category_counts": dict(sorted(offense_category_counts.items())),
        "source_count_after": source_count_after,
        "source_changed_during_run": source_count_before != source_count_after,
        "batch_size": effective_batch_size,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "bronze_file": str(final_path),
        "bronze_sha256": file_sha256(final_path),
    }
    manifest_path = final_path.with_suffix(".manifest.json")
    write_json_atomic(manifest_path, manifest)
    return final_path, manifest_path


def format_load_summary(category_counts: dict[str, int], total: int) -> str:
    """Formatiert Kategorie- und Gesamtzahlen fuer Notebook, CLI und Tests.

    Die Summe der Kategorien wird bewusst gegen ``total`` validiert. Dadurch
    kann ein Fehler beim Zaehlen nicht unbemerkt in den Run-Report gelangen.
    """

    category_total = sum(category_counts.values())
    if category_total != total:
        raise DataQualityError(
            f"Kategoriesumme {category_total} != Gesamtzahl {total}"
        )
    lines = ["Geladene Datensaetze pro Deliktkategorie:"]
    width = max((len(category) for category in category_counts), default=10)
    for category, count in sorted(category_counts.items()):
        lines.append(f"  {category:<{width}} : {count:>8}")
    lines.append(f"  {'INSGESAMT':<{width}} : {total:>8}")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Definiert und validiert die Kommandozeilenparameter."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", required=True, type=int, help="Kalenderjahr")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/bronze/detroit"),
        help="Zielverzeichnis fuer Bronze und Manifest",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Optional kleinere Batch-Groesse; ArcGIS-Maximum wird respektiert",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=0.05,
        help="Pause zwischen Batches zur Schonung der API",
    )
    parser.add_argument("--log-level", default="INFO")
    return parser.parse_args()


def main() -> None:
    """Startet die Bronze-Extraktion als Kommandozeilenprogramm."""

    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bronze_path, manifest_path = extract_year(
        args.year,
        args.output_dir,
        batch_size=args.batch_size,
        pause_seconds=args.pause_seconds,
    )
    print(f"Bronze:  {bronze_path}")
    print(f"Manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print()
    print(
        format_load_summary(
            manifest["offense_category_counts"], manifest["downloaded_count"]
        )
    )


if __name__ == "__main__":
    main()
