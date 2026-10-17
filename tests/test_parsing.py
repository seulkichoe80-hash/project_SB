import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import zipfile
import pdfplumber
import httpx
from defusedxml import ElementTree as ET
from xml.etree.ElementTree import SubElement
from fastapi.testclient import TestClient
from apps.api.main import create_app, authenticated_principal
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.parsing_service import EvidenceRequest, ParsingService
from apps.api.parsers import default_parsers
from apps.api.parsers.contracts import Anchor, validate_batch
from apps.api.worker import run_once

spec = importlib.util.spec_from_file_location('phase2b_pdf', Path('tests/fixtures/synthetic/phase2b_pdf.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
pdf = fixture.synthetic_pdf
HWPX = Path('tests/fixtures/synthetic/procedure-v2.hwpx')


def mutate_hwpx(changes):
    output = io.BytesIO()
    with zipfile.ZipFile(HWPX) as source, zipfile.ZipFile(output, 'w') as target:
        for name in source.namelist():
            payload = source.read(name)
            target.writestr(name, changes[name](payload) if name in changes else payload)
    return output.getvalue()


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.parsers = default_parsers()

    def test_pdf_paragraphs(self):
        blocks = self.parsers['pdf'].parse(pdf(), 'doc', 'v1')
        paragraphs = [b.text for b in blocks if b.block_type == 'paragraph']
        self.assertIn('Prepare the request.\nAttach the public form.', paragraphs)
        self.assertIn('Keep the original unchanged.', paragraphs)
        self.assertFalse(any('Stage' in text for text in paragraphs))

    def test_pdf_table_grid(self):
        blocks = self.parsers['pdf'].parse(pdf(), 'doc', 'v1')
        table = next(b for b in blocks if b.block_type == 'table')
        self.assertEqual(table.table_shape, (2,2))
        cells = [b for b in blocks if b.parent_block_id == table.block_id]
        self.assertEqual({(b.row,b.column):b.text for b in cells},
                         {(0,0):'Stage',(0,1):'Form',(1,0):'Submit',(1,1):'Request'})
        self.assertTrue(all(b.row_span == b.column_span == 1 for b in cells))

    def test_pdf_page_coordinates(self):
        blocks = self.parsers['pdf'].parse(pdf(), 'doc', 'v1')
        block = next(b for b in blocks if b.text == 'Second page evidence')
        self.assertEqual(block.source_anchor.page, 2)
        self.assertEqual(block.source_anchor.bbox[0], 50)
        self.assertTrue(45 < block.source_anchor.bbox[1] < 65)
        self.assertEqual(block.verification_status, 'structural_only')
        with pdfplumber.open(io.BytesIO(pdf())) as source:
            self.assertEqual(source.pages[1].crop(block.source_anchor.bbox).extract_text(), block.text)

    def test_pdf_merged_cell(self):
        blocks = self.parsers['pdf'].parse(pdf(merged_header=True), 'doc', 'v1')
        cells = [b for b in blocks if b.block_type == 'cell']
        self.assertEqual(len(cells), 3)
        self.assertEqual(next(b for b in cells if b.row == 0).column_span, 2)

    def test_no_invented_text_for_unextractable_page(self):
        with self.assertRaises(DomainError):
            self.parsers['pdf'].parse(pdf(blank_second_page=True), 'doc', 'v1')

    def test_hwpx_merged_cell(self):
        def merge(data):
            root = ET.fromstring(data)
            row = next(e for e in root.iter() if e.tag.endswith('}tr'))
            cells = [e for e in row if e.tag.endswith('}tc')]
            span = next(e for e in cells[0] if e.tag.endswith('}cellSpan'))
            span.set('colSpan','2')
            row.remove(cells[1])
            return ET.tostring(root)
        blocks = self.parsers['hwpx'].parse(mutate_hwpx({'Contents/section0.xml':merge}), 'doc', 'v1')
        cells = [b for b in blocks if b.block_type == 'cell']
        self.assertEqual(len(cells), 3)
        self.assertEqual(cells[0].column_span, 2)

    def test_hwpx_paragraphs_no_fake_page(self):
        blocks = self.parsers['hwpx'].parse(HWPX.read_bytes(), 'doc', 'v1')
        self.assertIn('1. 신청서를 작성한다.', [b.text for b in blocks])
        self.assertTrue(all(b.source_anchor.page is None and b.source_anchor.bbox is None for b in blocks))
        self.assertTrue(all(b.order_basis == 'xml_spine_preorder' for b in blocks))

    def test_hwpx_cells_and_table(self):
        blocks = self.parsers['hwpx'].parse(HWPX.read_bytes(), 'doc', 'v1')
        table = next(b for b in blocks if b.block_type == 'table')
        cells = [b for b in blocks if b.block_type == 'cell']
        self.assertEqual(table.table_shape, (2,2))
        self.assertEqual({(b.row,b.column):b.text for b in cells},
            {(0,0):'단계',(0,1):'필요 서류',(1,0):'신청',(1,1):'합성 신청서'})
        self.assertTrue(all(b.parent_block_id == table.block_id for b in cells))

    def test_hwpx_image_relationship_and_xml_roundtrip(self):
        blocks = self.parsers['hwpx'].parse(HWPX.read_bytes(), 'doc', 'v1')
        with zipfile.ZipFile(HWPX) as archive:
            for block in blocks:
                anchor = block.source_anchor
                node = ET.fromstring(archive.read(anchor.part))
                for index in anchor.xml_path:
                    node = node[index]
                self.assertEqual(node.tag, anchor.tag)
            image = next(b for b in blocks if b.block_type == 'image')
            self.assertEqual(image.asset_sha256, hashlib.sha256(archive.read(image.asset_ref)).hexdigest())
        self.assertEqual(image.context_relation, 'xml_containment')
        self.assertIn(image.parent_block_id, {b.block_id for b in blocks if b.block_type == 'paragraph'})
        self.assertEqual(image.text, '')

    def test_hwpx_explicit_heading(self):
        def change_header(data):
            root = ET.fromstring(data)
            style = next(e for e in root.iter() if e.tag.endswith('}style') and e.attrib.get('id') == '0')
            style.set('name', '제목 1')
            style.set('engName', 'Heading1')
            return ET.tostring(root)
        result = self.parsers['hwpx'].parse(mutate_hwpx({'Contents/header.xml': change_header}), 'doc', 'v1')
        self.assertTrue(any(b.block_type == 'heading' for b in result))

    def test_hwpx_spine_order_not_filename_sort(self):
        output = io.BytesIO()
        with zipfile.ZipFile(HWPX) as source, zipfile.ZipFile(output, 'w') as target:
            for name in source.namelist():
                if name == 'Contents/content.hpf':
                    root = ET.fromstring(source.read(name))
                    manifest = next(e for e in root if e.tag.endswith('}manifest'))
                    spine = next(e for e in root if e.tag.endswith('}spine'))
                    for child in list(spine):
                        spine.remove(child)
                    ns = '{http://www.idpf.org/2007/opf/}'
                    for section in ('section10','section2'):
                        SubElement(manifest, ns+'item', {'id':section,'href':f'Contents/{section}.xml'})
                        SubElement(spine, ns+'itemref', {'idref':section})
                    target.writestr(name, ET.tostring(root))
                else:
                    target.writestr(name, source.read(name))
            for section in ('section10','section2'):
                target.writestr(f'Contents/{section}.xml', source.read('Contents/section0.xml'))
        blocks = self.parsers['hwpx'].parse(output.getvalue(), 'doc', 'v1')
        parts = [b.source_anchor.part for b in blocks]
        self.assertEqual(parts[0], 'Contents/section10.xml')
        self.assertEqual(parts[-1], 'Contents/section2.xml')

    def test_corrupt_parsers_reject(self):
        for kind, data in [('pdf',b'broken'),('hwpx',b'broken')]:
            with self.subTest(kind=kind), self.assertRaises(DomainError):
                self.parsers[kind].parse(data, 'doc', 'v1')
        missing_image = mutate_hwpx({'Contents/section0.xml': lambda p:p.replace(b'BIN0001',b'MISSING')})
        with self.assertRaises(DomainError):
            self.parsers['hwpx'].parse(missing_image, 'doc', 'v1')

    def test_batch_rejects_fabricated_and_mixed_blocks(self):
        blocks = self.parsers['pdf'].parse(pdf(), 'doc', 'v1')
        for change in ({'text':'invented obligation'}, {'version_id':'v2'}, {'order_index':999}):
            forged = [blocks[0].model_copy(update=change)] + blocks[1:]
            with self.assertRaises(DomainError):
                validate_batch(forged, blocks, 'doc', 'v1')


class ParsingIntegrationTests(unittest.TestCase):
    def setUp(self):
        Path('work/phase2b').mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir='work/phase2b')
        self.root = Path(self.tmp.name)
        self.app = create_app(self.root, parsing_enabled=True)
        self.principal = Principal('test-manager','A','manager')
        self.worker = Principal('test-worker','A','worker')
        self.app.dependency_overrides[authenticated_principal] = lambda: self.principal
        self.client = TestClient(self.app, raise_server_exceptions=False)
        self.parsing = self.app.state.parsing

    def tearDown(self):
        self.client.close()
        for path in self.root.rglob('*'):
            if path.is_file():
                path.chmod(0o666)
        self.tmp.cleanup()

    def upload(self, data=None, name='manual.pdf', document=None):
        route = f'/documents/{document}/versions' if document else '/documents'
        response = self.client.post(route, params={'filename':name}, content=data or pdf(),
            headers={'Content-Type':'application/octet-stream','X-Data-Classification':'synthetic'})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['document']

    def route(self, meta):
        return f"/documents/{meta['document_id']}/versions/{meta['id']}"

    def parse(self, meta):
        self.assertEqual(run_once(self.parsing, self.worker), 'completed')
        response = self.client.get(self.route(meta)+'/blocks')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_auto_job_and_structured_storage_restart(self):
        meta = self.upload()
        route = self.route(meta)
        self.assertEqual(self.client.get(route+'/parsing').json()['state'], 'queued')
        self.assertEqual(self.client.get(route+'/blocks').status_code, 409)
        blocks = self.parse(meta)
        reopened = create_app(self.root, parsing_enabled=True)
        reopened.dependency_overrides[authenticated_principal] = lambda:self.principal
        with TestClient(reopened) as client:
            self.assertEqual(client.get(route+'/blocks').json(), blocks)
        self.assertTrue(all(b['document_id'] == meta['document_id'] and b['version_id'] == meta['id'] for b in blocks))

    def test_hwpx_integration(self):
        meta = self.upload(HWPX.read_bytes(), 'manual.hwpx')
        blocks = self.parse(meta)
        self.assertTrue(any(b['block_type'] == 'image' for b in blocks))

    def test_evidence_resolve_and_invalid_anchor(self):
        meta = self.upload()
        blocks = self.parse(meta)
        source = next(b for b in blocks if b['block_type'] == 'paragraph')
        route = self.route(meta)+'/evidence/resolve'
        response = self.client.post(route, json={'source_anchor':source['source_anchor'],'quote':source['text']})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()['structural_valid'])
        self.assertEqual(response.json()['semantic_accuracy'], 'NOT_VERIFIED')
        for fields in ({'page':99},{'bbox':[1,2,3,4]},{'selector':'nonexistent'}):
            bad = {**source['source_anchor'], **fields}
            self.assertEqual(self.client.post(route, json={'source_anchor':bad}).status_code, 422)
        self.assertEqual(self.client.post(route, json={'source_anchor':source['source_anchor'], 'quote':'invented'}).status_code, 422)

    def test_hwpx_anchor_rejects_missing_xml_path(self):
        meta = self.upload(HWPX.read_bytes(), 'manual.hwpx')
        source = self.parse(meta)[0]
        valid = {'source_anchor': source['source_anchor']}
        self.assertEqual(self.client.post(self.route(meta)+'/evidence/resolve', json=valid).status_code, 200)
        invalid = {'source_anchor': {**source['source_anchor'], 'xml_path':[999]}}
        self.assertEqual(self.client.post(self.route(meta)+'/evidence/resolve', json=invalid).status_code, 422)

    def test_cross_version_anchor_rejected(self):
        first = self.upload()
        old = self.parse(first)[0]['source_anchor']
        second = self.upload(pdf('Another version'), document=first['document_id'])
        self.parse(second)
        self.assertEqual(self.client.post(self.route(second)+'/evidence/resolve', json={'source_anchor':old}).status_code, 422)

    def test_duplicate_request_and_claim(self):
        meta = self.upload()
        results = [self.client.post(self.route(meta)+'/parsing').json() for _ in range(2)]
        self.assertEqual(results[0]['id'], results[1]['id'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _:self.parsing.claim(self.worker), range(2)))
        self.assertEqual(sum(c is not None for c in claims), 1)
        self.assertEqual(self.parsing.execute(self.worker, next(c for c in claims if c)), 'completed')
        self.assertEqual(self.client.post(self.route(meta)+'/parsing').json()['state'], 'completed')

    def test_parser_failure_retry_no_partial_results(self):
        meta = self.upload()
        with patch.object(self.parsing.parsers['pdf'], 'parse', side_effect=RuntimeError('do not log source')):
            self.assertEqual(run_once(self.parsing, self.worker), 'failed')
        status = self.client.get(self.route(meta)+'/parsing').json()
        self.assertEqual(status['state'], 'failed')
        self.assertEqual(status['error_code'], 'parse_internal_failure')
        self.assertEqual(self.client.get(self.route(meta)+'/blocks').status_code, 409)
        self.assertEqual(self.client.post(self.route(meta)+'/parsing/retry').status_code, 202)
        self.parse(meta)

    def test_publish_failure_rolls_back_all_blocks(self):
        meta = self.upload()
        with self.parsing.repo.transaction() as db:
            db.connection.execute("""CREATE TRIGGER abort_partial BEFORE INSERT ON source_blocks
                WHEN NEW.order_index=2 BEGIN SELECT RAISE(ABORT,'injected'); END""")
        self.assertEqual(run_once(self.parsing, self.worker), 'failed')
        with self.parsing.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT count(*) FROM source_blocks').fetchone()[0], 0)
            db.connection.execute('DROP TRIGGER abort_partial')
        self.assertEqual(self.client.get(self.route(meta)+'/blocks').status_code, 409)
        self.client.post(self.route(meta)+'/parsing/retry')
        self.parse(meta)

    def test_expired_worker_fenced_and_recovered(self):
        clock = [100.0]
        self.parsing.clock = lambda:clock[0]
        meta = self.upload()
        old = self.parsing.claim(self.worker)
        clock[0] += 31
        new = self.parsing.claim(self.worker)
        self.assertEqual(new['attempt'], 2)
        self.assertFalse(self.parsing.renew(old))
        self.assertEqual(self.parsing.execute(self.worker, old), 'stale')
        self.assertEqual(self.parsing.execute(self.worker, new), 'completed')
        self.assertEqual(self.client.get(self.route(meta)+'/parsing').json()['attempt'], 2)

    def test_worker_renew_and_expiration_cap(self):
        clock = [100.0]
        self.parsing.clock = lambda:clock[0]
        meta = self.upload()
        claim = self.parsing.claim(self.worker)
        clock[0] += 20
        self.assertTrue(self.parsing.renew(claim))
        clock[0] += 15
        self.assertEqual(self.parsing.recover(self.worker), 0)
        for _ in range(3):
            clock[0] += 31
            self.parsing.recover(self.worker)
            self.parsing.claim(self.worker)
        self.assertEqual(self.client.get(self.route(meta)+'/parsing').json()['state'], 'failed')

    def test_failed_new_version_keeps_previous_active(self):
        first = self.upload()
        self.parse(first)
        self.assertEqual(self.client.post(self.route(first)+'/activate').status_code, 200)
        second = self.upload(pdf('Fail new version'), document=first['document_id'])
        self.assertEqual(self.client.post(self.route(second)+'/activate').status_code, 409)
        with patch.object(self.parsing.parsers['pdf'], 'parse', side_effect=ValueError('test failure')):
            self.assertEqual(run_once(self.parsing, self.worker), 'failed')
        self.assertEqual(self.client.post(self.route(second)+'/activate').status_code, 409)
        self.assertEqual(self.client.get('/documents').json()[0]['id'], first['id'])

    def test_tenant_and_auth_extraction_isolation(self):
        meta = self.upload()
        block = self.parse(meta)[0]
        self.principal = Principal('other-manager','B','manager')
        route = self.route(meta)
        for suffix in ('/blocks','/parsing'):
            self.assertEqual(self.client.get(route+suffix).status_code, 404)
        for suffix, body in (('/parsing',{}),('/parsing/retry',{}),('/evidence/resolve',{'source_anchor':block['source_anchor']})):
            self.assertEqual(self.client.post(route+suffix, json=body).status_code, 404)
        self.assertIsNone(self.parsing.claim(Principal('other-worker','B','worker')))
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get(route+'/blocks').status_code, 401)

    def test_deregister_inflight_cannot_publish(self):
        meta = self.upload()
        claim = self.parsing.claim(self.worker)
        self.assertEqual(self.client.delete('/documents/'+meta['document_id']).status_code, 200)
        self.assertEqual(self.parsing.execute(self.worker, claim), 'stale')
        self.assertEqual(self.client.get(self.route(meta)+'/blocks').status_code, 404)
        with self.parsing.repo.transaction() as db:
            self.assertEqual(db.parsing.job(meta['id'])['state'], 'cancelled')

    def test_legacy_transition_cannot_bypass_parser(self):
        meta = self.upload()
        self.principal = self.worker
        response = self.client.post(self.route(meta)+'/transitions', json={'target':'queued','revision':0})
        self.assertEqual(response.status_code, 409)

    def test_legacy_database_backfill_preserves_original_and_active_pointer(self):
        # Existing Phase 2A records are backfilled, never recreated or silently activated.
        other_root = self.root/'legacy'
        legacy = create_app(other_root)
        manager = self.principal
        metadata, _ = legacy.state.service.register(manager,'old.pdf','application/pdf',pdf())
        queued = legacy.state.service.transition(manager, metadata['document_id'],metadata['id'],'queued',metadata['revision'])
        running = legacy.state.service.transition(self.worker,metadata['document_id'],metadata['id'],'processing',queued['revision'])
        completed = legacy.state.service.transition(self.worker,metadata['document_id'],metadata['id'],'completed',running['revision'],running['claim_token'])
        legacy.state.service.activate(manager,metadata['document_id'],metadata['id'])
        # Restore the exact Phase 2A schema boundary before migration (new tables are empty).
        with legacy.state.service.repo.transaction() as db:
            for table in ('source_blocks','parse_attempts','parse_jobs'):
                db.connection.execute('DROP TABLE '+table)
            db.connection.execute('PRAGMA user_version=1')
        original = legacy.state.service.store.read(metadata['id'], metadata['sha256'])
        updated = create_app(other_root, parsing_enabled=True)
        job = updated.state.parsing.status(manager, metadata['document_id'], metadata['id'])
        self.assertEqual(job['state'], 'queued')
        self.assertEqual(updated.state.service.list(manager)[0]['id'],metadata['id'])
        with updated.state.service.repo.transaction() as db:
            self.assertEqual(db.connection.execute('PRAGMA user_version').fetchone()[0],2)
        self.assertEqual(updated.state.service.store.read(metadata['id'],metadata['sha256']), original)
        self.assertEqual(run_once(updated.state.parsing, self.worker), 'completed')

    def test_reader_requires_active_version_and_failed_retry_is_explicit(self):
        first = self.upload()
        self.parse(first)
        self.principal = Principal('test-reader','A','reader')
        self.assertEqual(self.client.get(self.route(first)+'/blocks').status_code, 404)
        self.assertEqual(self.client.post(self.route(first)+'/parsing/retry').status_code, 403)
        self.principal = Principal('test-manager','A','manager')
        self.assertEqual(self.client.post(self.route(first)+'/parsing/retry').status_code, 409)
        self.client.post(self.route(first)+'/activate')
        self.principal = Principal('test-reader','A','reader')
        self.assertEqual(self.client.get(self.route(first)+'/blocks').status_code, 200)

    def test_corrupt_stored_original_and_wrong_worker_do_not_publish(self):
        meta = self.upload()
        claim = self.parsing.claim(self.worker)
        with self.assertRaises(DomainError):
            self.parsing.execute(Principal('foreign-worker','B','worker'), claim)
        path = self.app.state.service.store.path(meta['id'])
        path.chmod(0o666)
        path.write_bytes(b'tampered')
        self.assertEqual(self.parsing.execute(self.worker,claim), 'failed')
        self.assertEqual(self.client.get(self.route(meta)+'/blocks').status_code, 409)

    def test_direct_publication_rejects_forged_anchor(self):
        meta = self.upload()
        claim = self.parsing.claim(self.worker)
        blocks = default_parsers()['pdf'].parse(pdf(),meta['document_id'],meta['id'])
        blocks[0] = blocks[0].model_copy(update={'text':'invented legal obligation'})
        with self.assertRaises(DomainError):
            self.parsing.publish(self.worker,claim,blocks)
        self.assertEqual(self.client.get(self.route(meta)+'/blocks').status_code, 409)

    def test_claim_cannot_mix_another_document_version(self):
        first = self.upload()
        second = self.upload(pdf('Other document'))
        claim = self.parsing.claim(self.worker)
        self.assertEqual(claim['version_id'],first['id'])
        forged = {**claim,'document_id':second['document_id'],'version_id':second['id'],
                  'sha256':second['sha256'],'format':second['format']}
        self.assertEqual(self.parsing.execute(self.worker,forged),'stale')
        self.assertEqual(self.parsing.execute(self.worker,claim),'completed')
        self.assertEqual(self.client.get(self.route(second)+'/parsing').json()['state'],'queued')

    def test_worker_cli_restart_after_real_process_kill(self):
        meta = self.upload()
        ready = self.root/'claimed.json'
        process = subprocess.Popen([sys.executable,'scripts/validation/phase2b_claim_checkpoint.py',
            '--data-dir',str(self.root),'--ready-file',str(ready)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline = time.monotonic()+15
            while not ready.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    self.fail('checkpoint child did not claim job')
                time.sleep(.05)
            process.kill()
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        # Wait for the real one-second lease, without editing DB timestamps.
        deadline = time.monotonic()+5
        lease_until = self.client.get(self.route(meta)+'/parsing').json()['lease_until']
        while time.time() <= lease_until:
            if time.monotonic() > deadline:
                self.fail('lease did not expire')
            time.sleep(.05)
        self.assertEqual(self.client.get(self.route(meta)+'/parsing').json()['state'],'processing')
        result = subprocess.run([sys.executable,'-m','apps.api.worker','--data-dir',str(self.root),
            '--institution-id','A','--once'], capture_output=True, text=True, timeout=20,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'completed')
        self.assertEqual(self.client.get(self.route(meta)+'/parsing').json()['attempt'], 2)
        self.assertEqual(self.client.get(self.route(meta)+'/blocks').status_code, 200)

    def test_real_http_upload_worker_evidence_roundtrip(self):
        ready = self.root/'http-ready.json'
        process = subprocess.Popen([sys.executable,'scripts/validation/phase2b_http_server.py',
            '--data-dir',str(self.root),'--ready-file',str(ready)], stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline = time.monotonic()+15
            while not ready.exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    self.fail('HTTP child did not start')
                time.sleep(.05)
            url = json.loads(ready.read_text())['url']
            with httpx.Client(base_url=url,timeout=5,trust_env=False) as client:
                while True:
                    try:
                        health = client.get('/health')
                        break
                    except httpx.ConnectError:
                        if time.monotonic()>deadline:
                            raise
                        time.sleep(.05)
                self.assertTrue(health.json()['persistent_parsing'])
                response = client.post('/documents?filename=http.pdf',content=pdf(),headers={
                    'Content-Type':'application/pdf','X-Data-Classification':'synthetic'})
                self.assertEqual(response.status_code,201,response.text)
                meta = response.json()['document']
                worker = subprocess.run([sys.executable,'-m','apps.api.worker','--data-dir',str(self.root),
                    '--institution-id','A','--once'],capture_output=True,text=True,timeout=20,
                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                self.assertEqual(worker.returncode,0,worker.stderr)
                route = self.route(meta)
                self.assertEqual(client.get(route+'/parsing').json()['state'],'completed')
                blocks = client.get(route+'/blocks').json()
                response = client.post(route+'/evidence/resolve',json={'source_anchor':blocks[0]['source_anchor']})
                self.assertEqual(response.status_code,200,response.text)
                self.assertTrue(response.json()['structural_valid'])
            process.terminate()
            process.wait(timeout=5)
            ready = self.root/'http-ready-restarted.json'
            process = subprocess.Popen([sys.executable,'scripts/validation/phase2b_http_server.py',
                '--data-dir',str(self.root),'--ready-file',str(ready)], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            deadline = time.monotonic()+15
            while not ready.exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    self.fail('restarted HTTP child did not start')
                time.sleep(.05)
            with httpx.Client(base_url=json.loads(ready.read_text())['url'],timeout=5,trust_env=False) as client:
                while True:
                    try:
                        restored = client.get(route+'/blocks')
                        break
                    except httpx.ConnectError:
                        if time.monotonic()>deadline:
                            raise
                        time.sleep(.05)
                self.assertEqual(restored.status_code,200,restored.text)
                self.assertEqual(restored.json(),blocks)
                self.assertEqual(client.get(route+'/parsing').json()['attempt'],1)
        finally:
            process.terminate()
            process.wait(timeout=5)


if __name__ == '__main__':
    unittest.main()
