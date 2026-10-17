import hashlib
import tempfile
import unittest
import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import create_app, authenticated_principal
from apps.api.models import Principal
from apps.api.storage import LocalOriginalStore
from apps.api.formats import MAX_BYTES


def pdf(text='synthetic'):
    # Complete synthetic one-page PDF, standard-library only, no embedded fonts.
    stream = f'BT /F1 12 Tf 40 100 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>',
               b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
               b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    data = b'%PDF-1.4\n'
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(data))
        data += f'{index} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(data)
    data += b'xref\n0 6\n0000000000 65535 f \n'
    data += b''.join(f'{offset:010d} 00000 n \n'.encode() for offset in offsets[1:])
    return data + f'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir='work/phase2a')
        self.root = Path(self.tmp.name)
        self.app = create_app(self.root)
        self.principal = Principal('test-manager', 'institution-a', 'manager')
        self.app.dependency_overrides[authenticated_principal] = lambda: self.principal
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.service = self.app.state.service

    def tearDown(self):
        self.client.close()
        # Windows read-only originals are deliberately retained until test-only fixture cleanup.
        for path in self.root.rglob('*'):
            if path.is_file():
                path.chmod(0o666)
        self.tmp.cleanup()

    def register(self, data=None, name='sample.pdf', document=None, expected=201):
        route = f'/documents/{document}/versions' if document else '/documents'
        response = self.client.post(route, params={'filename': name}, content=data or pdf(),
            headers={'Content-Type': 'application/octet-stream', 'X-Data-Classification': 'synthetic'})
        self.assertEqual(response.status_code, expected, response.text)
        return response.json().get('document')

    @staticmethod
    def path(meta):
        return f"/documents/{meta['document_id']}/versions/{meta['id']}"

    def move(self, meta, target, expected=200, token=None):
        previous = self.principal
        if target != 'queued':
            self.principal = Principal('test-worker', previous.institution_id, 'worker')
        try:
            response = self.client.post(self.path(meta) + '/transitions', json={
                'target': target, 'revision': meta['revision'], 'claim_token': token})
            self.assertEqual(response.status_code, expected, response.text)
            return response.json()
        finally:
            self.principal = previous

    def complete(self, meta):
        queued = self.move(meta, 'queued')
        running = self.move(queued, 'processing')
        return self.move(running, 'completed', token=running['claim_token'])

    def activate(self, meta):
        response = self.client.post(self.path(meta) + '/activate')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_normal_pdf_metadata(self):
        result = self.register()
        self.assertEqual(result['format'], 'pdf')
        self.assertEqual(result['state'], 'registered')
        self.assertEqual(result['institution_id'], 'institution-a')
        self.assertEqual(result['number'], 1)
        self.assertIn('+00:00', result['created_at'])

    def test_normal_hwpx(self):
        source = Path('tests/fixtures/synthetic/procedure-v2.hwpx').read_bytes()
        result = self.register(source, 'sample.hwpx')
        self.assertEqual(result['format'], 'hwpx')
        self.assertEqual(result['mime'], 'application/hwp+zip')

    def test_unsupported_extension(self):
        self.register(name='file.exe', expected=415)

    def test_disguised_extension_and_mime(self):
        self.register(b'not a pdf', expected=415)
        self.register(pdf(), 'file.hwpx', expected=415)
        response = self.client.post('/documents?filename=sample.pdf', content=pdf(),
            headers={'Content-Type': 'text/plain', 'X-Data-Classification': 'synthetic'})
        self.assertEqual(response.status_code, 415)

    def test_same_filename_distinct_content(self):
        first = self.register()
        second = self.register(pdf('second'))
        self.assertNotEqual(first['document_id'], second['document_id'])
        self.assertNotEqual(first['id'], second['id'])

    def test_duplicate_content_idempotent(self):
        first = self.register()
        second = self.register(name='renamed.pdf', expected=200)
        third = self.register(document=first['document_id'], expected=200)
        self.assertEqual(first['id'], second['id'])
        self.assertEqual(first['id'], third['id'])

    def test_sha256_and_download(self):
        meta = self.register()
        self.assertEqual(meta['sha256'], hashlib.sha256(pdf()).hexdigest())
        response = self.client.get(self.path(meta) + '/original')
        self.assertEqual(response.content, pdf())
        self.assertEqual(hashlib.sha256(response.content).hexdigest(), meta['sha256'])

    def test_immutable_and_tamper_detection(self):
        meta = self.register()
        with self.assertRaises(FileExistsError):
            self.service.store.write(meta['id'], b'overwrite')
        path = self.service.store.path(meta['id'])
        path.chmod(0o666)  # Simulate privileged administrator bypass, not an API operation.
        path.write_bytes(b'tampered')
        self.assertEqual(self.client.get(self.path(meta) + '/original').status_code, 409)
        queued = self.move(meta, 'queued')
        running = self.move(queued, 'processing')
        self.move(running, 'completed', expected=409, token=running['claim_token'])

    def test_partial_write_failure_recovery(self):
        def fail_write(key, data):
            self.service.store.path(key).write_bytes(data[:10])
            raise OSError('injected failure')
        with patch.object(self.service.store, 'write', fail_write):
            self.register(expected=503)
        self.assertEqual(self.client.get('/documents?active_only=false').json(), [])
        self.assertEqual(self.service.reconcile()[0]['status'], 'failed')
        self.assertEqual(len(list((self.root / 'originals').iterdir())), 1)
        self.register()

    def test_database_failure_after_file_write(self):
        original = self.service.store.read
        def fail_db(key, digest):
            result = original(key, digest)
            # Publication fails after immutable write, inside a real SQLite transaction.
            with self.service.repo.transaction() as db:
                db.connection.execute("CREATE TRIGGER reject_version BEFORE INSERT ON versions BEGIN SELECT RAISE(ABORT,'injected'); END")
            return result
        with patch.object(self.service.store, 'read', fail_db):
            self.register(expected=503)
        self.assertEqual(self.client.get('/documents?active_only=false').json(), [])
        self.assertEqual(self.service.reconcile()[0]['status'], 'failed')
        with self.service.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT count(*) FROM documents').fetchone()[0], 0)
            db.connection.execute('DROP TRIGGER reject_version')
        self.register()

    def test_version_switch(self):
        first = self.activate(self.complete(self.register()))
        second = self.register(pdf('v2'), document=first['document_id'])
        self.assertEqual(second['number'], 2)
        self.assertEqual(self.client.post(self.path(second) + '/activate').status_code, 409)
        self.assertEqual(self.client.get('/documents').json()[0]['id'], first['id'])
        self.activate(self.complete(second))
        self.assertEqual(self.client.get('/documents').json()[0]['id'], second['id'])
        self.assertEqual(self.client.get(self.path(first) + '/original').content, pdf())

    def test_failed_candidate_keeps_old_active(self):
        first = self.activate(self.complete(self.register()))
        second = self.register(pdf('v2'), document=first['document_id'])
        running = self.move(self.move(second, 'queued'), 'processing')
        failed = self.move(running, 'failed', token=running['claim_token'])
        self.assertEqual(self.client.post(self.path(failed) + '/activate').status_code, 409)
        self.assertEqual(self.client.get('/documents').json()[0]['id'], first['id'])
        self.assertEqual(self.move(failed, 'queued')['state'], 'queued')

    def test_deregister_retains_original_and_blocks_jobs(self):
        first = self.activate(self.complete(self.register()))
        self.assertEqual(self.client.delete('/documents/' + first['document_id']).status_code, 200)
        self.assertEqual(self.client.get('/documents').json(), [])
        self.assertEqual(self.client.get(self.path(first) + '/original').content, pdf())
        self.assertEqual(self.client.post(self.path(first) + '/activate').status_code, 404)
        self.principal = Principal('reader', 'institution-a', 'reader')
        self.assertEqual(self.client.get(self.path(first) + '/original').status_code, 404)

    def test_cross_institution_read_and_mutation(self):
        first = self.register()
        self.principal = Principal('other-manager', 'institution-b', 'manager')
        self.assertEqual(self.client.get('/documents?active_only=false').json(), [])
        for suffix in ('', '/original'):
            self.assertEqual(self.client.get(self.path(first) + suffix).status_code, 404)
        self.assertEqual(self.client.post(self.path(first) + '/activate').status_code, 404)
        self.assertEqual(self.client.delete('/documents/' + first['document_id']).status_code, 404)
        self.register(pdf('v2'), document=first['document_id'], expected=404)
        self.assertEqual(self.client.post(self.path(first) + '/transitions',
            json={'target': 'queued', 'revision': 0}).status_code, 404)
        own = self.register()
        self.assertNotEqual(own['id'], first['id'])

    def test_unauthenticated_cannot_spoof_tenant(self):
        self.app.dependency_overrides.clear()
        for method, path in [('get', '/documents'), ('post', '/documents?filename=a.pdf'),
                             ('delete', '/documents/fake')]:
            response = getattr(self.client, method)(path, headers={'X-Institution-ID': 'institution-a',
                                                                  'Authorization': 'Bearer fake'})
            self.assertEqual(response.status_code, 401)

    def test_invalid_state_and_duplicate_claim(self):
        first = self.register()
        self.move(first, 'completed', expected=409)
        queued = self.move(first, 'queued')
        self.move(first, 'queued', expected=409)
        running = self.move(queued, 'processing')
        self.move(queued, 'processing', expected=409)
        self.move(running, 'completed', expected=409, token='wrong')
        done = self.move(running, 'completed', token=running['claim_token'])
        self.move(done, 'queued', expected=409)

    def test_restart_persistence(self):
        first = self.activate(self.complete(self.register()))
        restarted = create_app(self.root)
        restarted.dependency_overrides[authenticated_principal] = lambda: self.principal
        with TestClient(restarted) as client:
            self.assertEqual(client.get('/documents').json()[0]['id'], first['id'])
            self.assertEqual(client.get(self.path(first) + '/original').content, pdf())

    def test_size_and_path_and_classification(self):
        self.register(b'x' * (MAX_BYTES + 1), expected=413)
        for name in ('../file.pdf', 'C:\\file.pdf', 'a/b.pdf'):
            self.register(name=name, expected=400)
        self.assertEqual(self.client.post('/documents?filename=a.pdf', content=pdf()).status_code, 400)
        with self.assertRaises(Exception):
            self.service.store.path('../anything')

    def test_reader_cannot_register_or_process(self):
        first = self.register()
        self.principal = Principal('reader', 'institution-a', 'reader')
        self.register(expected=403)
        self.assertEqual(self.client.get('/documents?active_only=false').json(), [])
        self.assertEqual(self.client.get(self.path(first)).status_code, 404)
        self.assertEqual(self.client.post(self.path(first) + '/transitions',
            json={'target': 'processing', 'revision': 0}).status_code, 403)

    def test_concurrent_duplicate_upload_published_once(self):
        def upload(_):
            return self.service.register(self.principal, 'same.pdf', 'application/pdf', pdf())
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(upload, range(2)))
        self.assertEqual(results[0][0]['id'], results[1][0]['id'])
        self.assertEqual(len(self.service.list(self.principal, False)), 1)

    def test_malformed_pdf_structure(self):
        fake = b'%PDF-1.4\n/Catalog /Pages\nstartxref\n0\n%%EOF'
        self.register(fake, expected=415)
        self.register(pdf().replace(b'0000000009 00000 n', b'9999999999 00000 n'), expected=415)

    def test_unsafe_or_corrupt_hwpx(self):
        source = Path('tests/fixtures/synthetic/procedure-v2.hwpx').read_bytes()
        for filename, payload in [('../escape.xml', b'<x/>'), ('Contents/section0.xml', b'<!DOCTYPE a [<!ENTITY x SYSTEM "file:///secret">]><a>&x;</a>')]:
            stream = io.BytesIO()
            with zipfile.ZipFile(io.BytesIO(source)) as original, zipfile.ZipFile(stream, 'w') as target:
                for info in original.infolist():
                    if info.filename != filename:
                        target.writestr(info.filename, original.read(info.filename))
                target.writestr(filename, payload)
            self.register(stream.getvalue(), 'unsafe.hwpx', expected=415)

    def test_client_institution_does_not_set_authority(self):
        response = self.client.post('/documents?filename=a.pdf&institution_id=institution-b',
            content=pdf(), headers={'Content-Type': 'application/pdf',
            'X-Data-Classification': 'synthetic', 'X-Institution-ID': 'institution-b'})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['document']['institution_id'], 'institution-a')


if __name__ == '__main__':
    unittest.main()
