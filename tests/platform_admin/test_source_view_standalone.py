"""Read-only viewer security and provenance, runnable without DuckDB."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from platform_admin.sources import source_code
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
        self.assertEqual(result['code'], self.code.read_text())
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
