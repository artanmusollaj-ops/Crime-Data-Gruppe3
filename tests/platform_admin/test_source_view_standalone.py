"""Read-only viewer security and provenance, runnable without DuckDB."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from platform_admin.sources import source_code, source_status
from platform_admin.store import AdminError


class SourceViewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.store = SimpleNamespace(project=root, data=root / 'data')
        self.code = root / 'src/crime/chicago_pipeline/download_chicago.py'
        self.code.parent.mkdir(parents=True)
        self.code.write_text('print("example")\n', encoding='utf-8')

    def test_current_source_and_hash(self):
        result = source_code(self.store, 'chicago')
        # The bytes, not read_text: on Windows write_text wrote CRLF, and
        # read_text would turn it back into LF (failed on main, 30.10.2026).
        self.assertEqual(result['code'], self.code.read_bytes().decode('utf-8'))
        self.assertEqual(len(result['sha256']), 64)
        self.assertFalse(result['historical_available'])

    def test_paths_and_cross_city_rejected(self):
        for module in ('../../.env', 'detroit_pipeline/extract_detroit.py'):
            with self.assertRaises(AdminError):
                source_code(self.store, 'chicago', module)
        for path in ('../manifest.json', 'bronze/city=detroit/manifest.json'):
            with self.assertRaises(AdminError):
                source_code(self.store, 'chicago', run_path=path)

    def test_manifest_has_no_invented_parameters_or_secrets(self):
        relative = 'bronze/city=chicago/run_demo/manifest.json'
        path = self.store.data / relative
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'run_id': 'demo', 'year': 2024, 'token': 'secret'}))
        result = source_code(self.store, 'chicago', run_path=relative)
        self.assertEqual(result['run'], {'run_id': 'demo', 'year': 2024})
        self.assertIn('nicht verfügbar', result['history_note'])

    def test_source_run_end_time_uses_the_manifest_field_for_each_city(self):
        start = '2026-11-14T09:06:11+00:00'
        end = '2026-11-14T09:07:12+00:00'
        for city, end_field in (('chicago', 'completed_at_utc'), ('detroit', 'finished_at')):
            for run_id, fields in (('complete', {end_field: end}), ('no_end', {})):
                path = self.store.data / f'bronze/city={city}/run_{run_id}/manifest.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'run_id': run_id, 'started_at': start, **fields}))

        for source in source_status(self.store):
            times = {run['run_id']: run['completed_at_utc'] for run in source['runs']}
            self.assertEqual(times, {'complete': end, 'no_end': None})

        module = self.store.project / 'src/crime/detroit_pipeline/extract_detroit.py'
        module.parent.mkdir()
        module.write_text('print("example")\n', encoding='utf-8')
        result = source_code(
            self.store, 'detroit', run_path='bronze/city=detroit/run_complete/manifest.json'
        )
        self.assertEqual(result['run']['finished_at'], end)

    def test_manifest_under_a_linked_data_root(self):
        # On macOS the temporary directory itself sits behind /var ->
        # /private/var; a Linux runner never sees that. A linked data root
        # reproduces it everywhere.
        real = Path(self.temp.name) / 'real-data'
        relative = 'bronze/city=chicago/run_demo/manifest.json'
        (real / relative).parent.mkdir(parents=True)
        (real / relative).write_text(json.dumps({'run_id': 'demo'}))
        linked = Path(self.temp.name) / 'linked-data'
        linked.symlink_to(real, target_is_directory=True)
        store = SimpleNamespace(project=self.store.project, data=linked)
        result = source_code(store, 'chicago', run_path=relative)
        self.assertEqual(result['run'], {'run_id': 'demo'})

    def test_symlink_outside_source_root_rejected(self):
        self.code.unlink()
        target = self.store.project / 'private.py'
        target.write_text('private')
        self.code.symlink_to(target)
        with self.assertRaises(AdminError):
            source_code(self.store, 'chicago')


if __name__ == '__main__':
    unittest.main()
