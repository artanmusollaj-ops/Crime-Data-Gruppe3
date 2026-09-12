"""Regression tests for storage, publication, lineage and DuckDB run idempotency."""
import copy
import json
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import pyarrow.parquet as pq
import duckdb
from tests.detroit_pipeline.test_bronze_ingestion import FakeArcGISClient
from detroit_pipeline.extract_detroit import extract_year, extract_updated_window
from detroit_pipeline.bronze_manifest import validate_manifest
from detroit_pipeline.load_duckdb import load_run
from detroit_pipeline.detroit_arcgis import ArcGISLayerInfo, DataQualityError

class TypedClient(FakeArcGISClient):
    def get_layer_info(self):
        fields = {'ESRI_OID': 'esriFieldTypeOID',
                  'incident_entry_id': 'esriFieldTypeString',
                  'report_number': 'esriFieldTypeString',
                  'offense_category': 'esriFieldTypeString',
                  'incident_occurred_at': 'esriFieldTypeDate',
                  'updated_at': 'esriFieldTypeDate'}
        return ArcGISLayerInfo('ESRI_OID', 2000, 'typed-fixture', tuple(fields), tuple(fields.items()))

class ParquetContractTests(unittest.TestCase):
    def test_roundtrip_batches_nulls_unknown_fields_geometry(self):
        c = TypedClient()
        c.features[0]['attributes']['report_number'] = '000123'
        c.features[0]['attributes']['future_field'] = {'a': [None, True, 3]}
        c.features[1]['geometry'] = None
        c.features[3]['attributes']['updated_at'] = 1700000000000
        c.features[4]['attributes']['updated_at'] = 'changed-source-type'
        with TemporaryDirectory() as d:
            file, manifest = extract_year(2024, Path(d), client=c, batch_size=2)
            _, m = validate_manifest(manifest)
            with pq.ParquetFile(file) as pf:
                self.assertEqual(pf.metadata.num_row_groups, 3)
                rows = pf.read().to_pylist()
            self.assertEqual(rows[0]['attributes']['report_number'], '000123')
            self.assertIsNone(rows[4]['attributes']['updated_at'])
            self.assertEqual(json.loads(rows[4]['_extra'])['updated_at'], 'changed-source-type')
            # _feature_json haelt die Antwort der Quelle unveraendert. Das
            # ist der Vertrag von Bronze: gepinnte Spalten fuer die Auswertung,
            # daneben die Zeile so, wie sie kam.
            for feature, row in zip(c.features, rows):
                self.assertEqual(feature, json.loads(row['_feature_json']))
            self.assertEqual(m['rows_with_extra'], 2)

    def test_empty_run_is_valid_parquet_and_importable(self):
        c = TypedClient(); c.features = []
        with TemporaryDirectory() as d:
            _, m = extract_year(2024, Path(d), client=c)
            self.assertEqual(validate_manifest(m)[1]['downloaded_count'], 0)
            self.assertEqual(load_run(m, Path(d)/'empty.duckdb'), 'IMPORTED')

    def test_duplicate_and_unexpected_ids_fail_without_publication(self):
        for replacement in (1, 999):
            with self.subTest(replacement=replacement), TemporaryDirectory() as d:
                c = TypedClient()
                original = copy.deepcopy(c.features)
                bad = copy.deepcopy(original)
                bad[1]['attributes']['ESRI_OID'] = replacement
                with patch.object(c, 'iter_features', return_value=iter(bad)):
                    with self.assertRaises(DataQualityError):
                        extract_year(2024, Path(d), client=c)
                self.assertEqual(list(Path(d).iterdir()), [])

    def test_failure_during_manifest_or_final_count_publishes_nothing(self):
        for step in ('manifest', 'count'):
            with self.subTest(step=step), TemporaryDirectory() as d:
                c = TypedClient()
                target = 'detroit_pipeline.extract_detroit.write_json_atomic'
                context = patch(target, side_effect=OSError('disk')) if step == 'manifest' else patch.object(c, 'get_count', side_effect=[5, OSError('network')])
                with context, self.assertRaises(OSError):
                    extract_year(2024, Path(d), client=c)
                self.assertEqual(list(Path(d).iterdir()), [])

    def test_corrupted_artifact_rejected(self):
        with TemporaryDirectory() as d:
            f, m = extract_year(2024, Path(d), client=TypedClient())
            with f.open('ab') as handle:
                handle.write(b'corruption')
            with self.assertRaises(DataQualityError): validate_manifest(m)

    def test_run_replay_skipped_but_overlap_retained(self):
        with TemporaryDirectory() as d:
            root = Path(d); db = root/'crime.duckdb'
            _, m1 = extract_year(2024, root/'full', client=TypedClient())
            _, m2 = extract_updated_window(date(2026,9,1),date(2026,9,8),root/'daily',client=TypedClient())
            self.assertEqual(load_run(m1, db), 'IMPORTED')
            self.assertEqual(load_run(m1, db), 'SKIPPED')
            self.assertEqual(load_run(m2, db), 'IMPORTED')
            with duckdb.connect(str(db)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM bronze.detroit_records').fetchone()[0],10)
                self.assertEqual(con.execute('SELECT count(*) FROM metadata.bronze_runs').fetchone()[0],2)

    def test_duckdb_conflicting_identity_rejected(self):
        with TemporaryDirectory() as d:
            root=Path(d); db=root/'crime.duckdb'
            _, m = extract_year(2024, root, client=TypedClient())
            load_run(m, db)
            with duckdb.connect(str(db)) as con:
                con.execute("UPDATE metadata.bronze_runs SET sha256='different'")
            with self.assertRaises(DataQualityError): load_run(m, db)

    def test_duckdb_transaction_rolls_back_on_ledger_failure(self):
        with TemporaryDirectory() as d:
            root=Path(d); db=root/'crime.duckdb'
            _, m1=extract_year(2024, root/'a', client=TypedClient())
            _, m2=extract_year(2024, root/'b', client=TypedClient())
            load_run(m1, db)
            with duckdb.connect(str(db)) as con:
                con.execute('CREATE UNIQUE INDEX one_per_source ON metadata.bronze_runs(source_system)')
            with self.assertRaises(duckdb.ConstraintException): load_run(m2, db)
            with duckdb.connect(str(db)) as con:
                self.assertEqual(con.execute('SELECT count(*) FROM bronze.detroit_records').fetchone()[0], 5)

if __name__ == '__main__': unittest.main()
