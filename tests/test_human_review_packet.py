"""Offline review tools; submitted fixture judgments are never human approval."""
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest
from scripts.validation.human_review_packet import build, check, FIELDS

SOURCE = Path('outputs/v03b/isolated-evaluation')

class HumanReviewPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.temp.name) / 'packet'
        cls.data = build(SOURCE, cls.out)
    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()
    def write_rows(self, rows):
        path = Path(self.temp.name) / 'submission.csv'
        with path.open('w', newline='') as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)
        return path
    def blank(self):
        return [{k: '' for k in FIELDS} | {'query_id': r['query_id']} for r in self.data['rows']]
    def test_tenant_scope(self):
        g = json.loads((SOURCE / 'generation.json').read_text())
        orgs = {d['document_id']: d['organization_id'] for d in g['documents']}
        self.assertEqual(len(self.data['rows']), 10)
        for r in self.data['rows']:
            self.assertIsNone(r['verdict'])
            self.assertTrue(all(orgs[d['document_id']] == r['organization_id'] for d in r['context']))
            self.assertTrue(all(e['reference']['organization_id'] == r['organization_id'] for e in r['evidence']))
    def test_pending_and_offline(self):
        result = check(self.out / 'packet.json', self.out / 'judgments.csv')
        self.assertEqual(result['completed'], 0)
        self.assertEqual(len(result['pending_ids']), 10)
        page = (self.out / 'review.html').read_text()
        self.assertIn('default-src', page)
        self.assertNotIn('<script', page)
    def test_overwrite(self):
        with self.assertRaisesRegex(ValueError, 'new_output'): build(SOURCE, self.out)
    def test_invalid_submissions(self):
        for case in ['duplicate', 'foreign', 'partial', 'naive', 'blank', 'verdict']:
            with self.subTest(case=case):
                rows = self.blank()
                if case == 'duplicate': rows[1]['query_id'] = rows[0]['query_id']
                elif case == 'foreign': rows[0]['query_id'] = 'unknown'
                else:
                    rows[0].update(reviewer='synthetic-test', reviewed_at='2026-10-18T12:00:00+00:00', verdict='정확', reason='unit-test only')
                    if case == 'partial': rows[0]['reason'] = ''
                    if case == 'naive': rows[0]['reviewed_at'] = '2026-10-18T12:00:00'
                    if case == 'blank': rows[0]['reviewer'] = '  '
                    if case == 'verdict': rows[0]['verdict'] = 'APPROVED'
                with self.assertRaises(ValueError): check(self.out / 'packet.json', self.write_rows(rows))
    def test_submission_not_approval(self):
        rows = self.blank()
        rows[0].update(reviewer='synthetic-test', reviewed_at='2026-10-18T12:00:00+00:00', verdict='부분정확', reason='unit-test only')
        result = check(self.out / 'packet.json', self.write_rows(rows))
        self.assertEqual(result['completed'], 1)
        self.assertEqual(result['goldset_status'], 'PROVISIONAL')
        self.assertFalse(result['human_identity_verified'])
        self.assertFalse(result['semantic_accuracy_pass'])
