"""Console persistence and evidence regression tests without pipeline binaries."""
import json
import tempfile
import unittest
from pathlib import Path

from platform_admin import inbox
from platform_admin.run_evidence import capture, evidence, inventory
from platform_admin.sources import source_code
from platform_admin.store import AdminError, Store

PROJECT = Path(__file__).resolve().parents[2]


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(PROJECT, Path(self.temp.name) / 'data')
        with self.store.db() as c:
            c.execute("INSERT INTO revision VALUES(?,?,?,?,?,?,?,?)", ('r1','mapping','baseline','{}','hash','Engineer','Reason','2026-10-09'))

    def test_assignment_persists_and_rejects_other_reviewer(self):
        inbox.update(self.store,'r1','Reviewer','claim')
        reopened = Store(PROJECT, self.store.data)
        self.assertEqual(inbox.overview(reopened,'Reviewer')['assignments'][0]['actor'],'Reviewer')
        with self.assertRaises(AdminError):
            inbox.update(reopened,'r1','Other','claim')
        with self.assertRaises(AdminError):
            inbox.update(reopened,'r1','Other','release')
        inbox.update(reopened,'r1','Reviewer','release')
        self.assertEqual(inbox.overview(reopened,'Reviewer')['assignments'],[])

    def test_own_claim_forbidden_and_read_is_personal(self):
        with self.assertRaises(AdminError):
            inbox.update(self.store,'r1','engineer','claim')
        inbox.update(self.store,'r1','Engineer','read')
        self.assertEqual(len(inbox.overview(self.store,'Engineer')['read']),1)
        self.assertEqual(inbox.overview(self.store,'Reviewer')['read'],[])
        with self.store.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM decision').fetchone()[0],0)

    def test_decided_and_missing_cannot_be_claimed(self):
        with self.store.db() as c:
            c.execute('INSERT INTO decision(id,revision,decision,actor,reason,decided_at) VALUES(?,?,?,?,?,?)',('d','r1','reject','Reviewer','Reason','now'))
        for rid in ['r1','missing']:
            with self.assertRaises(AdminError):
                inbox.update(self.store,rid,'Reviewer','claim')

    def test_hash_link_and_missing_history(self):
        rel='bronze/city=detroit/run1/manifest.json'
        p=self.store.data/rel
        p.parent.mkdir(parents=True)
        before=inventory(self.store,'detroit')
        p.write_text(json.dumps({'run_id':'run1','token':'private','status':'complete'}))
        folder=self.store.root/'jobs'/'j1'
        folder.mkdir(parents=True)
        with self.store.db() as c:
            c.execute('INSERT INTO job(id,name,mapping_revision,settings_revision,spec,actor,status,queued_at) VALUES(?,?,?,?,?,?,?,?)',('j1','detroit_full','m','s','{}','Engineer','SUCCEEDED','now'))
        capture(self.store,'detroit',before,folder,{'id':'j1'},{'task':'full_detroit','years':[2024]})
        result=evidence(self.store,'detroit',rel)
        self.assertEqual(result['jobs'][0]['id'],'j1')
        self.assertEqual(result['manifest']['token'],'[redacted]')
        self.assertFalse(result['historical_source_available'])
        p.write_text('{"run_id":"changed"}')
        self.assertEqual(evidence(self.store,'detroit',rel)['jobs'],[])

    def test_evidence_path_boundaries(self):
        for city,path in [('unknown','manifest.json'),('chicago','../manifest.json'),('chicago','bronze/city=detroit/manifest.json')]:
            with self.assertRaises(AdminError):
                evidence(self.store,city,path)

    def test_actual_full_daily_ranges(self):
        for city in ['chicago','detroit']:
            result=source_code(self.store,city)
            self.assertTrue(result['highlights']['full'])
            self.assertTrue(result['highlights']['daily'])
            n=len(result['code'].splitlines())
            for ranges in result['highlights'].values():
                self.assertTrue(all(1<=a<=b<=n for a,b in ranges))
        detroit=source_code(self.store,'detroit','detroit_pipeline/detroit_arcgis.py')
        lines=detroit['code'].splitlines()
        selected='\n'.join('\n'.join(lines[a-1:b]) for a,b in detroit['highlights']['daily'])
        self.assertIn('updated_at', selected)


if __name__=='__main__':
    unittest.main()
