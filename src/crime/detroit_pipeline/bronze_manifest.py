"""Admission gate shared by the parser and DuckDB import."""
import json
from pathlib import Path
from . import detroit_arcgis
from .detroit_arcgis import DataQualityError
from .extract_detroit import file_sha256
from .bronze_parquet import schema_hash
import pyarrow.parquet as pq

def validate_manifest(manifest_path):
    """Accept only complete, local contract-v2 runs with matching bytes and schema."""
    path = Path(manifest_path)
    if any(p.startswith('.') and p.endswith('.partial') for p in path.parts):
        raise DataQualityError('Unveroeffentlichter Lauf')
    m = json.loads(path.read_text(encoding='utf-8'))
    if (m.get('status') != 'SUCCESS' or m.get('bronze_contract_version') != 2
            or m.get('storage_format') != 'PARQUET'
            or m.get('source_system') != detroit_arcgis.SOURCE_SYSTEM
            or not m.get('snapshot_membership_verified')):
        raise DataQualityError(
            f'Kein vollstaendiger {detroit_arcgis.QUELLE.anzeigename}-Parquet-Lauf Version 2')
    if m.get('bronze_file') != 'part-0001.parquet':
        raise DataQualityError('Unerwarteter Artefaktpfad')
    file = path.parent / m['bronze_file']
    if file_sha256(file) != m['bronze_sha256']:
        raise DataQualityError('Bronze-Pruefsumme stimmt nicht')
    with pq.ParquetFile(file) as pf:
        counts = [m['downloaded_count'], m['snapshot_object_id_count'],
                  m['source_count_before'], pf.metadata.num_rows,
                  sum(m['offense_category_counts'].values())]
        if len(set(counts)) != 1:
            raise DataQualityError('Count-Gate fehlgeschlagen')
        if schema_hash(pf.schema_arrow) != m['storage_schema_fingerprint']:
            raise DataQualityError('Speicherschema stimmt nicht')
        for batch in pf.iter_batches(columns=['source_system', 'pipeline_run_id', 'ingested_at_utc']):
            for row in batch.to_pylist():
                if (row['source_system'] != m['source_system']
                        or row['pipeline_run_id'] != m['pipeline_run_id']
                        or row['ingested_at_utc'].isoformat() != m['started_at']):
                    raise DataQualityError('Lineage passt nicht zum Manifest')
    return file, m
