"""Extrahiert Detroit RMS Crime Features unveraendert in den Bronze Layer.

Beispiele:

    python -m detroit_pipeline.extract_detroit --mode full \
        --years 2024 2025 --output-dir data/bronze/detroit

    python -m detroit_pipeline.extract_detroit --mode daily \
        --lookback-days 14 --output-dir data/bronze/detroit

Das Ergebnis besteht aus Parquet und Manifest in einem gemeinsam publizierten
Run-Verzeichnis. Die Feature-Daten werden in begrenzten Batches geschrieben.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
import shutil
from pathlib import Path
from uuid import uuid4
import pyarrow as pa
import pyarrow.parquet as pq
from .bronze_parquet import schema_for, schema_hash, to_row

from .detroit_arcgis import (
    ArcGISClient,
    DataQualityError,
    build_local_date_window,
    build_updated_where,
    build_year_where,
    resolve_daily_window,
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


def _extract_where(
    where: str,
    output_dir: Path,
    *,
    file_stem: str,
    extraction_mode: str,
    date_field: str,
    window_start: date,
    window_end_exclusive: date,
    year: int | None = None,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
) -> tuple[Path, Path]:
    """Fuehrt einen count-verifizierten Snapshot fuer eine WHERE-Klausel aus.

    Schritte:

    1. Layer-Schema und ArcGIS-Limits lesen.
    2. Server-Count und feste Object-ID-Liste fuer das Jahr abfragen.
    3. Features ID-basiert in Batches in eine temporaere Parquet-Datei streamen.
    4. Downloadzahl und finalen Server-Count pruefen.
    5. Daten und Manifest gemeinsam als Run-Verzeichnis veroeffentlichen.
    """

    # Der optionale Client ermoeglicht einen isolierten Ingestion-Test ohne
    # Live-Netzwerk. Im produktiven Lauf wird automatisch der echte REST-Client
    # verwendet.
    client = client or ArcGISClient()
    if batch_size is not None and (type(batch_size) is not int or batch_size <= 0):
        raise ValueError('batch_size muss eine positive Ganzzahl sein')
    if pause_seconds < 0:
        raise ValueError('pause_seconds darf nicht negativ sein')
    run_id = str(uuid4())
    started_at = datetime.now(timezone.utc)

    # FULL und INCREMENTAL besitzen bewusst unterschiedliche fachliche
    # Zeitachsen. Diese Invarianten verhindern, dass ein spaeterer Umbau einen
    # Jahresbestand versehentlich nach Update-Zeit oder einen Daily Load nach
    # Tatzeit selektiert.
    extraction_contracts = {
        "FULL": {
            "date_field": "incident_occurred_at",
            "selection_basis": "INCIDENT_OCCURRENCE_TIME",
        },
        "INCREMENTAL": {
            "date_field": "updated_at",
            "selection_basis": "SOURCE_LAST_UPDATED_TIME",
        },
    }
    contract = extraction_contracts.get(extraction_mode)
    if contract is None:
        raise ValueError(f"Nicht unterstuetzter Extraction Mode: {extraction_mode}")
    if date_field != contract["date_field"]:
        raise DataQualityError(
            f"{extraction_mode} muss {contract['date_field']} verwenden, "
            f"nicht {date_field}"
        )

    # Abfrage und Manifest muessen denselben lokalen Fenstervertrag erfuellen.
    window = build_local_date_window(window_start, window_end_exclusive)
    if where != window.where(date_field):
        raise DataQualityError("WHERE-Klausel passt nicht zum Detroit-Zeitfenster")

    # SCHRITT 1: Metadaten liefern Object-ID-Feld, Seitengroesse und Schema-Hash.
    layer_info = client.get_layer_info()
    if date_field not in layer_info.fields:
        raise DataQualityError(
            f"Erforderliches Datumsfeld fehlt im ArcGIS-Schema: {date_field}"
        )
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

    if len(set(object_ids)) != len(object_ids):
        raise DataQualityError('Doppelte Snapshot-IDs')

    output_dir.mkdir(parents=True, exist_ok=True)
    # Short filenames avoid the former Windows manifest path overflow.
    final_dir = output_dir / f'run_{run_id}'
    work_dir = output_dir / f'.run_{run_id}.partial'
    final_path = final_dir / 'part-0001.parquet'
    manifest_path = final_dir / 'manifest.json'
    temporary_path = work_dir / 'part-0001.parquet'
    schema = schema_for(layer_info)
    work_dir.mkdir()

    # SCHRITT 3: Jede rohe ArcGIS-Zeile wird inklusive technischer Provenance
    # sofort geschrieben. Fachliche Transformationen gehoeren nicht in Bronze.
    downloaded_count = 0
    offense_category_counts: dict[str, int] = {}
    remaining_ids = set(object_ids)
    extra_rows = 0
    try:
        with pq.ParquetWriter(temporary_path, schema, compression='zstd') as writer:
            rows = []
            for feature in client.iter_features(
                object_ids,
                object_id_field=object_id_field,
                batch_size=effective_batch_size,
                pause_seconds=pause_seconds,
            ):
                oid = (feature.get('attributes') or {}).get(object_id_field)
                if type(oid) is not int or oid not in remaining_ids:
                    raise DataQualityError(f'Doppelte, unerwartete oder ungueltige ID: {oid}')
                remaining_ids.remove(oid)
                row = to_row(feature, schema, run_id, started_at)
                extra_rows += row['_extra'] is not None
                rows.append(row)
                if len(rows) >= effective_batch_size:
                    writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                    rows.clear()
                downloaded_count += 1
                raw_category = (feature.get("attributes") or {}).get(
                    "offense_category"
                )
                category = str(raw_category).strip() if raw_category is not None else ""
                category = category or "__MISSING__"
                offense_category_counts[category] = (
                    offense_category_counts.get(category, 0) + 1
                )
            if rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=schema))
        if downloaded_count != len(object_ids):
            raise DataQualityError(
                f"Download-Count {downloaded_count} != ID-Count {len(object_ids)}"
            )
        if remaining_ids or sum(offense_category_counts.values()) != downloaded_count:
            raise DataQualityError('Snapshot oder Kategoriesumme inkonsistent')
        with pq.ParquetFile(temporary_path) as parquet:
            if parquet.metadata.num_rows != downloaded_count:
                raise DataQualityError('Parquet-Zeilenzahl inkonsistent')
        # Publication is deliberately deferred until all metadata is ready.
        source_count_after = client.get_count(where)
        finished_at = datetime.now(timezone.utc)
        checksum = file_sha256(temporary_path)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise

    # SCHRITT 4: Der zweite Count dokumentiert, ob sich die Live-Quelle waehrend
    # des Laufs veraendert hat. Die feste ID-Liste bleibt der Snapshot-Vertrag.

    # SCHRITT 5: Das Manifest macht Vollstaendigkeit, Laufzeit, Filter und
    # Quellzustand maschinenlesbar und kann spaeter vom Monitoring gelesen werden.
    manifest = {
        "bronze_contract_version": 2,
        "storage_format": "PARQUET",
        "compression": "ZSTD",
        "immutable": True,
        "storage_schema_fingerprint": schema_hash(schema),
        "storage_schema": str(schema),
        "source_field_types": dict(layer_info.field_types),
        "rows_with_extra": extra_rows,
        "snapshot_membership_verified": True,
        "snapshot_ids_sha256": sha256(','.join(map(str, sorted(object_ids))).encode()).hexdigest(),
        "payload_contract": "_feature_json preserves parsed source JSON; not HTTP bytes",
        "files": [{"path": "part-0001.parquet", "sha256": checksum,
                   "size_bytes": temporary_path.stat().st_size}],
        "pipeline_run_id": run_id,
        "status": "SUCCESS",
        "source_system": "detroit_rms_crime",
        "dataset_id": "RMS_Crime_Incidents",
        "layer_url": client.layer_url,
        "extraction_mode": extraction_mode,
        "date_field": date_field,
        "selection_basis": contract["selection_basis"],
        "record_granularity": "INCIDENT_OFFENSE",
        "window_is_half_open": True,
        "captures_source_deletions": False,
        "window_start": window_start.isoformat(),
        "window_end_exclusive": window_end_exclusive.isoformat(),
        **window.manifest_fields(),
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
        "bronze_file": "part-0001.parquet",
        "bronze_sha256": checksum,
    }
    try:
        write_json_atomic(work_dir / 'manifest.json', manifest)
        work_dir.rename(final_dir)
    except BaseException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    return final_path, manifest_path


def extract_year(
    year: int,
    output_dir: Path,
    *,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
) -> tuple[Path, Path]:
    """Laedt einen vollstaendigen Kalenderjahresbestand nach Tatzeitpunkt."""

    window_start = date(year, 1, 1)
    window_end_exclusive = date(year + 1, 1, 1)
    return _extract_where(
        build_year_where(year),
        output_dir,
        file_stem=f"detroit_rms_crime_{year}",
        extraction_mode="FULL",
        date_field="incident_occurred_at",
        window_start=window_start,
        window_end_exclusive=window_end_exclusive,
        year=year,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
        client=client,
    )


def extract_updated_window(
    start_date: date,
    end_date_exclusive: date,
    output_dir: Path,
    *,
    batch_size: int | None = None,
    pause_seconds: float = 0.05,
    client: ArcGISClient | None = None,
) -> tuple[Path, Path]:
    """Laedt neue und geaenderte Records eines halb-offenen Daily-Fensters.

    Der Filter verwendet ``updated_at``. Dadurch werden auch Korrekturen an
    aelteren Delikten erfasst. Das bewusste 14-Tage-Overlap muss Silver
    idempotent per ``offense_key`` und neuestem Update-Zeitpunkt konsolidieren.
    """

    where = build_updated_where(start_date, end_date_exclusive)
    return _extract_where(
        where,
        output_dir,
        file_stem=(
            "detroit_rms_crime_incremental_"
            f"{start_date.isoformat()}_{end_date_exclusive.isoformat()}"
        ),
        extraction_mode="INCREMENTAL",
        date_field="updated_at",
        window_start=start_date,
        window_end_exclusive=end_date_exclusive,
        batch_size=batch_size,
        pause_seconds=pause_seconds,
        client=client,
    )


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


def parse_iso_date(value: str) -> date:
    """Liest ein reproduzierbares CLI-Referenzdatum im Format YYYY-MM-DD."""

    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Ungueltiges Datum {value!r}; erwartet wird YYYY-MM-DD"
        ) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Definiert und validiert die CLI fuer Full- und Daily-Laeufe.

    ``full`` benoetigt mindestens ein Jahr. ``daily`` verwendet standardmaessig
    die letzten 14 lokalen Detroit-Kalendertage bis einschliesslich des
    abgeschlossenen Detroit-Vortags. Ein explizites Referenzdatum erlaubt
    reproduzierbare Backfills und bezeichnet den letzten eingeschlossenen Tag.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("full", "daily"),
        help="Extraktionsmodus: full oder daily",
    )
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        help="Kalenderjahre fuer Full, z. B. --years 2024 2025",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=14,
        help="Anzahl lokaler Detroit-Kalendertage im Daily-Fenster",
    )
    parser.add_argument(
        "--reference-date",
        type=parse_iso_date,
        default=None,
        help=(
            "Optionaler letzter eingeschlossener Detroit-Tag (YYYY-MM-DD); "
            "ohne Angabe wird der abgeschlossene Vortag verwendet"
        ),
    )
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
    parser.add_argument(
        "--log-level",
        choices=("DEBUG", "INFO", "WARNING", "ERROR"),
        default="INFO",
    )
    args = parser.parse_args(argv)

    if args.mode == "full":
        if not args.years:
            parser.error("--years ist fuer --mode full erforderlich")
        if args.reference_date is not None:
            parser.error("--reference-date ist nur fuer --mode daily erlaubt")
    else:
        if args.years:
            parser.error("--years ist fuer --mode daily nicht erlaubt")
        if args.lookback_days <= 0:
            parser.error("--lookback-days muss groesser als 0 sein")

    if args.batch_size is not None and args.batch_size <= 0:
        parser.error("--batch-size muss groesser als 0 sein")
    if args.pause_seconds < 0:
        parser.error("--pause-seconds darf nicht negativ sein")
    return args


def print_extraction_result(bronze_path: Path, manifest_path: Path) -> None:
    """Gibt Artefaktpfade und die im Manifest gespeicherte Statistik aus."""

    print(f"Bronze:   {bronze_path}")
    print(f"Manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    print()
    print(
        format_load_summary(
            manifest["offense_category_counts"], manifest["downloaded_count"]
        )
    )


def main(argv: list[str] | None = None) -> int:
    """Startet einen Full- oder Daily-Bronze-Load als CLI-Job."""

    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.mode == "full":
        for year in args.years:
            logging.info("Starte Detroit Full Load fuer %s", year)
            bronze_path, manifest_path = extract_year(
                year=year,
                output_dir=args.output_dir / "full" / f"year={year}",
                batch_size=args.batch_size,
                pause_seconds=args.pause_seconds,
            )
            print_extraction_result(bronze_path, manifest_path)
        return 0

    daily_window = resolve_daily_window(
        reference_date=args.reference_date,
        lookback_days=args.lookback_days,
    )
    window_start = daily_window.start_local.date()
    window_end_exclusive = daily_window.end_local.date()
    run_date = window_end_exclusive - timedelta(days=1)

    logging.info(
        "Starte Detroit Daily Load: %s bis %s (exklusiv)",
        window_start,
        window_end_exclusive,
    )
    bronze_path, manifest_path = extract_updated_window(
        start_date=window_start,
        end_date_exclusive=window_end_exclusive,
        output_dir=(
            args.output_dir / "incremental" / f"run_date={run_date.isoformat()}"
        ),
        batch_size=args.batch_size,
        pause_seconds=args.pause_seconds,
    )
    print_extraction_result(bronze_path, manifest_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
