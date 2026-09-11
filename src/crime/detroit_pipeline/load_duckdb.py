"""Import complete Parquet runs into DuckDB Bronze, idempotent at run level.

This is NOT an offense upsert: overlapping runs are intentionally retained.
Only one external writer process should own the local database at a time.
"""
import argparse
import json
from pathlib import Path
import duckdb
from .bronze_manifest import validate_manifest
from .detroit_arcgis import DataQualityError

def load_run(manifest_path: Path, database: Path) -> str:
    """Verify first, then commit records and run ledger together or roll back both."""
    file, m = validate_manifest(manifest_path)
    database = Path(database)
    database.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(database)) as con:
        con.execute('BEGIN TRANSACTION')
        try:
            con.execute('CREATE SCHEMA IF NOT EXISTS bronze')
            con.execute('CREATE SCHEMA IF NOT EXISTS metadata')
            con.execute('''CREATE TABLE IF NOT EXISTS metadata.bronze_runs (
                source_system VARCHAR, source_run_id VARCHAR, sha256 VARCHAR,
                manifest JSON, imported_at TIMESTAMPTZ DEFAULT current_timestamp,
                PRIMARY KEY(source_system, source_run_id))''')
            con.execute('''CREATE TABLE IF NOT EXISTS bronze.detroit_records (
                source_system VARCHAR NOT NULL, source_run_id VARCHAR NOT NULL,
                source_record_id VARCHAR, ingested_at_utc TIMESTAMPTZ,
                feature JSON, extra JSON, artifact_sha256 VARCHAR)''')
            key = [m['source_system'], m['pipeline_run_id']]
            old = con.execute('SELECT sha256 FROM metadata.bronze_runs WHERE source_system=? AND source_run_id=?', key).fetchone()
            if old:
                if old[0] != m['bronze_sha256']:
                    raise DataQualityError('Run-ID bereits mit anderen Bytes importiert')
                con.execute('COMMIT')
                return 'SKIPPED'
            con.execute('''INSERT INTO bronze.detroit_records
                SELECT source_system, pipeline_run_id,
                    json_extract_string(_feature_json, '$.attributes.incident_entry_id'),
                    ingested_at_utc, CAST(_feature_json AS JSON), CAST(_extra AS JSON), ?
                FROM read_parquet(?)''', [m['bronze_sha256'], str(file)])
            actual = con.execute('SELECT count(*) FROM bronze.detroit_records WHERE source_system=? AND source_run_id=?', key).fetchone()[0]
            if actual != m['downloaded_count']:
                raise DataQualityError('DuckDB-Count stimmt nicht')
            con.execute('INSERT INTO metadata.bronze_runs(source_system,source_run_id,sha256,manifest) VALUES (?,?,?,?)', key + [m['bronze_sha256'], json.dumps(m)])
            con.execute('COMMIT')
            return 'IMPORTED'
        except BaseException:
            con.execute('ROLLBACK')
            raise

def main():
    """Accept explicit manifests, never recursively ingest arbitrary data files."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', required=True, nargs='+', type=Path)
    p.add_argument('--database', type=Path, default=Path('data/warehouse/crime.duckdb'))
    a = p.parse_args()
    for path in a.manifest:
        print(f'{path}: {load_run(path, a.database)}')

if __name__ == '__main__':
    main()
