import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import httpx
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import create_app,authenticated_principal
from apps.api.models import Principal
from apps.api.chunking import ChunkConfig, EvidenceRef, build_chunks
from apps.api.chunk_service import ChunkService
from apps.api.parsers import default_parsers
from apps.api.errors import DomainError
import test_parsing as fixtures


class ChunkUnitTests(unittest.TestCase):
    def setUp(self):
        self.blocks = default_parsers()['hwpx'].parse(fixtures.HWPX.read_bytes(),'doc','v1')

    def test_deterministic_and_source_scope(self):
        a = build_chunks(self.blocks,'A',ChunkConfig())
        b = build_chunks(self.blocks,'A',ChunkConfig())
        self.assertEqual(a,b)
        self.assertTrue(all(c.evidence.organization_id=='A' and c.evidence.version_id=='v1' for c in a))
        self.assertEqual(len({c.chunk_id for c in a}),len(a))

    def test_cells_not_duplicated_as_paragraphs(self):
        chunks = build_chunks(self.blocks,'A',ChunkConfig())
        primary = [s for c in chunks for s in c.evidence.spans if s.role=='primary']
        cells = [b for b in self.blocks if b.block_type=='cell']
        for cell in cells:
            self.assertEqual(sum(s.block_id==cell.block_id for s in primary),1)
            child_ids = {b.block_id for b in self.blocks if b.parent_block_id==cell.block_id}
            self.assertFalse(any(s.block_id in child_ids for s in primary))

    def test_table_grid_and_first_row_context(self):
        chunks = build_chunks(self.blocks,'A',ChunkConfig())
        rows = [c for c in chunks if c.kind=='table_row']
        self.assertEqual({(c.grid[0]['row'],c.grid[0]['column']) for c in rows},{(0,0),(0,1),(1,0),(1,1)})
        self.assertTrue(all(c.grid[0]['row_span']==c.grid[0]['column_span']==1 for c in rows))
        self.assertTrue(any(s.role=='first_row_context' and s.quote=='단계' for c in rows if c.grid[0]['row']==1 for s in c.evidence.spans))

    def test_long_text_exact_ranges(self):
        block = next(b for b in self.blocks if b.block_type=='paragraph' and b.text)
        block = block.model_copy(update={'text':'가나다'*500})
        chunks = build_chunks([block],'A',ChunkConfig(max_chars=64))
        self.assertTrue(all(len(c.text)<=64 for c in chunks))
        self.assertEqual(''.join(c.text for c in chunks),block.text)
        self.assertEqual([s.start for c in chunks for s in c.evidence.spans],list(range(0,1500,64)))

    def test_heading_context_and_image_no_ai_description(self):
        blocks = list(self.blocks)
        first = next(i for i,b in enumerate(blocks) if b.text)
        blocks[first] = blocks[first].model_copy(update={'block_type':'heading'})
        chunks = build_chunks(blocks,'A',ChunkConfig(context_chars=5))
        self.assertTrue(any(c.kind=='heading' for c in chunks))
        self.assertTrue(any(s.role=='title_context' for c in chunks for s in c.evidence.spans))
        image = next(c for c in chunks if c.kind=='image')
        self.assertEqual(image.text,'')
        self.assertEqual(image.evidence.verification_status,'structural_only')
        self.assertTrue(any(c.context_truncated for c in chunks))

    def test_mixed_versions_rejected(self):
        mixed = self.blocks+[self.blocks[0].model_copy(update={'version_id':'v2','block_id':'other'})]
        with self.assertRaises(DomainError):
            build_chunks(mixed,'A',ChunkConfig())

    def test_merged_table_span_preserved(self):
        blocks=default_parsers()['pdf'].parse(fixtures.pdf(merged_header=True),'doc','v1')
        chunks=build_chunks(blocks,'A',ChunkConfig())
        self.assertTrue(any(c.grid and c.grid[0]['column_span']==2 for c in chunks))


class ChunkIntegrationTests(unittest.TestCase):
    setUp = fixtures.ParsingIntegrationTests.setUp
    tearDown = fixtures.ParsingIntegrationTests.tearDown
    upload = fixtures.ParsingIntegrationTests.upload
    route = fixtures.ParsingIntegrationTests.route
    parse = fixtures.ParsingIntegrationTests.parse

    def prepare(self,data=None,name='manual.pdf',document=None,config=None):
        meta = self.upload(data,name,document)
        self.parse(meta)
        response = self.client.post(self.route(meta)+'/chunk-jobs',json=config or {})
        self.assertEqual(response.status_code,202,response.text)
        job = response.json()
        service = self.app.state.chunks
        claim = service.claim(self.worker)
        self.assertEqual(service.execute(self.worker,claim),'completed')
        chunks = self.client.get(self.route(meta)+'/chunks')
        self.assertEqual(chunks.status_code,200,chunks.text)
        return meta,job,chunks.json()

    def test_pdf_hwpx_chunks_and_evidence_roundtrip(self):
        for data,name in [(fixtures.pdf(),'manual.pdf'),(fixtures.HWPX.read_bytes(),'manual.hwpx')]:
            meta,_,chunks = self.prepare(data,name)
            for c in chunks:
                response = self.client.post(self.route(meta)+f"/chunks/{c['chunk_id']}/evidence/resolve",json=c['evidence'])
                self.assertEqual(response.status_code,200,response.text)
                self.assertTrue(response.json()['structural_valid'])
                self.assertEqual(response.json()['content_origin'],'original')
                self.assertEqual(response.json()['semantic_verification'],'NOT_VERIFIED')

    def test_missing_anchor_and_false_quote_rejected(self):
        meta,_,chunks = self.prepare()
        c = chunks[0]
        route = self.route(meta)+f"/chunks/{c['chunk_id']}/evidence/resolve"
        for key,value in [('chunk_id','missing'),('version_id','other')]:
            bad = copy.deepcopy(c['evidence'])
            bad[key] = value
            self.assertEqual(self.client.post(route,json=bad).status_code,422)
        for change in ('quote','source_anchor'):
            bad = copy.deepcopy(c['evidence'])
            if change=='quote':
                bad['spans'][0]['quote'] = 'invented'
            else:
                bad['spans'][0]['source_anchor']['page'] = 999
            self.assertEqual(self.client.post(route,json=bad).status_code,422)

    def test_org_read_mutation_and_evidence_blocked(self):
        meta,job,chunks = self.prepare()
        self.principal = Principal('other-manager','B','manager')
        self.assertEqual(self.client.get(self.route(meta)+'/chunks').status_code,404)
        self.assertEqual(self.client.post(self.route(meta)+'/chunk-jobs',json={}).status_code,404)
        self.assertEqual(self.client.get('/search?q=manual').json()['results'],[])
        c = chunks[0]
        self.assertEqual(self.client.post(self.route(meta)+f"/chunks/{c['chunk_id']}/evidence/resolve",json=c['evidence']).status_code,404)
        self.assertIsNone(self.app.state.chunks.claim(Principal('foreign-worker','B','worker')))

    def test_other_version_evidence_mixing(self):
        first,_,old = self.prepare()
        second,_,new = self.prepare(fixtures.pdf('New version'),document=first['document_id'])
        self.assertEqual(self.client.post(self.route(second)+f"/chunks/{new[0]['chunk_id']}/evidence/resolve",json=old[0]['evidence']).status_code,422)

    def test_keyword_filename_body_and_active_only(self):
        meta,_,_ = self.prepare()
        self.assertEqual(self.client.get('/search?q=Prepare').json()['results'],[])
        self.client.post(self.route(meta)+'/activate')
        for query in ('manual.pdf','Prepare','Second page'):
            response = self.client.get('/search',params={'q':query})
            self.assertEqual(response.status_code,200,response.text)
            self.assertTrue(response.json()['results'])
            self.assertTrue(all(c['evidence']['version_id']==meta['id'] for c in response.json()['results']))

    def test_hangul_and_heading_search(self):
        def heading(data):
            root = fixtures.ET.fromstring(data)
            style = next(e for e in root.iter() if e.tag.endswith('}style') and e.attrib.get('id')=='0')
            style.set('name','제목 1')
            style.set('engName','Heading1')
            return fixtures.ET.tostring(root)
        payload = fixtures.mutate_hwpx({'Contents/header.xml':heading})
        meta,_,_ = self.prepare(payload,'공개.hwpx',config={'context_chars':0})
        self.client.post(self.route(meta)+'/activate')
        self.assertTrue(self.client.get('/search',params={'q':'합성기관'}).json()['results'])

    def test_active_version_swap_and_deregister(self):
        first,_,_ = self.prepare()
        self.client.post(self.route(first)+'/activate')
        second,_,_ = self.prepare(fixtures.pdf('Replacement'),document=first['document_id'])
        self.client.post(self.route(second)+'/activate')
        hits = self.client.get('/search?q=manual').json()['results']
        self.assertTrue(hits)
        self.assertTrue(all(h['evidence']['version_id']==second['id'] for h in hits))
        self.client.delete('/documents/'+first['document_id'])
        self.assertEqual(self.client.get('/search?q=manual').json()['results'],[])
        self.assertEqual(self.client.get(self.route(first)+'/chunks').status_code,404)

    def test_idempotent_jobs_and_results(self):
        meta,job,items = self.prepare()
        again = self.client.post(self.route(meta)+'/chunk-jobs',json={}).json()
        self.assertEqual(again['id'],job['id'])
        self.assertIsNone(self.app.state.chunks.claim(self.worker))
        self.assertEqual(self.client.get(self.route(meta)+'/chunks').json(),items)

    def test_transaction_failure_no_partial_search_retry(self):
        meta = self.upload()
        self.parse(meta)
        job = self.client.post(self.route(meta)+'/chunk-jobs',json={}).json()
        with self.parsing.repo.transaction() as db:
            db.connection.execute("CREATE TRIGGER fail_chunks BEFORE INSERT ON chunk_items WHEN NEW.order_index=1 BEGIN SELECT RAISE(ABORT,'injected'); END")
        service = self.app.state.chunks
        self.assertEqual(service.execute(self.worker,service.claim(self.worker)),'failed')
        self.assertEqual(self.client.get(self.route(meta)+'/chunks').status_code,409)
        self.assertEqual(self.client.get('/search?q=manual').json()['results'],[])
        with self.parsing.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT count(*) FROM chunk_items').fetchone()[0],0)
            db.connection.execute('DROP TRIGGER fail_chunks')
        self.assertEqual(self.client.post(self.route(meta)+f"/chunk-jobs/{job['id']}/retry").status_code,202)
        self.assertEqual(service.execute(self.worker,service.claim(self.worker)),'completed')

    def test_expired_claim_recovery_and_stale_fence(self):
        meta = self.upload()
        self.parse(meta)
        self.client.post(self.route(meta)+'/chunk-jobs',json={})
        clock = [100.]
        service = self.app.state.chunks
        service.clock = lambda:clock[0]
        old = service.claim(self.worker)
        clock[0] += 121
        new = service.claim(self.worker)
        self.assertEqual(new['attempt'],2)
        self.assertEqual(service.execute(self.worker,old),'stale')
        self.assertEqual(service.execute(self.worker,new),'completed')

    def test_new_version_failure_keeps_old_active(self):
        first,_,_ = self.prepare()
        self.client.post(self.route(first)+'/activate')
        second = self.upload(fixtures.pdf('Bad chunk candidate'),document=first['document_id'])
        self.parse(second)
        self.client.post(self.route(second)+'/chunk-jobs',json={})
        service = self.app.state.chunks
        with patch('apps.api.chunk_service.build_chunks',side_effect=RuntimeError('injected')):
            self.assertEqual(service.execute(self.worker,service.claim(self.worker)),'failed')
        self.assertEqual(self.client.post(self.route(second)+'/activate').status_code,409)
        self.assertTrue(all(h['evidence']['version_id']==first['id'] for h in self.client.get('/search?q=manual').json()['results']))

    def test_sql_literals_and_query_limits(self):
        meta,_,_ = self.prepare()
        self.client.post(self.route(meta)+'/activate')
        for query in ('%', '_', "' OR 1=1 --"):
            self.assertEqual(self.client.get('/search',params={'q':query}).json()['results'],[])
        for query in ('','x'*201):
            self.assertEqual(self.client.get('/search',params={'q':query}).status_code,400)

    def test_reader_and_anonymous_controls(self):
        meta,_,_ = self.prepare()
        self.principal = Principal('reader','A','reader')
        self.assertEqual(self.client.get(self.route(meta)+'/chunks').status_code,404)
        self.assertEqual(self.client.post(self.route(meta)+'/chunk-jobs',json={}).status_code,403)
        self.app.dependency_overrides.clear()
        self.assertEqual(self.client.get('/search?q=manual').status_code,401)

    def test_search_adapter_cannot_bypass_active_filter_or_invent_text(self):
        meta,_,items=self.prepare()
        service=self.app.state.chunks
        class BadAdapter:
            def search(self,*args):
                return [items[0]]
        service.search_adapter=BadAdapter()
        self.assertEqual(self.client.get('/search?q=manual').status_code,409)
        self.client.post(self.route(meta)+'/activate')
        forged=copy.deepcopy(items[0])
        forged['text']='invented AI explanation'
        class ForgedAdapter:
            def search(self,*args):
                return [forged]
        service.search_adapter=ForgedAdapter()
        self.assertEqual(self.client.get('/search?q=manual').status_code,409)

    def test_server_reopen_and_worker_subprocess(self):
        meta = self.upload()
        self.parse(meta)
        self.client.post(self.route(meta)+'/chunk-jobs',json={})
        result = subprocess.run([sys.executable,'-m','apps.api.chunk_worker','--data-dir',str(self.root),
            '--institution-id','A','--once'],capture_output=True,text=True,timeout=20,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr)
        self.client.post(self.route(meta)+'/activate')
        expected = self.client.get('/search?q=manual').json()
        reopened = create_app(self.root,parsing_enabled=True)
        reopened.dependency_overrides[authenticated_principal] = lambda:self.principal
        with TestClient(reopened) as client:
            self.assertEqual(client.get('/search?q=manual').json(),expected)

    def test_cancel_during_chunking(self):
        meta = self.upload()
        self.parse(meta)
        self.client.post(self.route(meta)+'/chunk-jobs',json={})
        service = self.app.state.chunks
        claim = service.claim(self.worker)
        self.client.delete('/documents/'+meta['document_id'])
        self.assertEqual(service.execute(self.worker,claim),'stale')
        self.assertEqual(self.client.get('/search?q=manual').json()['results'],[])

    def test_actual_worker_kill_and_new_process_recovery(self):
        meta=self.upload()
        self.parse(meta)
        job=self.client.post(self.route(meta)+'/chunk-jobs',json={}).json()
        ready=self.root/'chunk-checkpoint.json'
        process=subprocess.Popen([sys.executable,'scripts/validation/phase2c_claim_checkpoint.py',
            '--data-dir',str(self.root),'--ready-file',str(ready)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            deadline=time.monotonic()+15
            while not ready.exists():
                if process.poll() is not None or time.monotonic()>deadline:
                    self.fail('chunk checkpoint did not start')
                time.sleep(.05)
            process.kill()
            process.wait(timeout=5)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
        lease=json.loads(ready.read_text())['lease_until']
        while time.time()<=lease:
            time.sleep(.05)
        result=subprocess.run([sys.executable,'-m','apps.api.chunk_worker','--data-dir',str(self.root),
            '--institution-id','A','--once'],capture_output=True,text=True,timeout=20,
            creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        self.assertEqual(result.returncode,0,result.stderr)
        status=self.client.get(self.route(meta)+f"/chunk-jobs/{job['id']}").json()
        self.assertEqual((status['state'],status['attempt']),('completed',2))

    def test_real_http_server_process_restart_search(self):
        meta,_,chunks=self.prepare()
        self.client.post(self.route(meta)+'/activate')
        expected=self.client.get('/search?q=manual').json()
        for index in range(2):
            ready=self.root/f'chunk-http-{index}.json'
            process=subprocess.Popen([sys.executable,'scripts/validation/phase2b_http_server.py',
                '--data-dir',str(self.root),'--ready-file',str(ready)],stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            try:
                deadline=time.monotonic()+15
                while not ready.exists():
                    if process.poll() is not None or time.monotonic()>deadline:
                        self.fail('HTTP process did not start')
                    time.sleep(.05)
                with httpx.Client(base_url=json.loads(ready.read_text())['url'],timeout=5,trust_env=False) as client:
                    while True:
                        try:
                            result=client.get('/search?q=manual')
                            break
                        except httpx.ConnectError:
                            if time.monotonic()>deadline:
                                raise
                            time.sleep(.05)
                    self.assertEqual(result.status_code,200,result.text)
                    self.assertEqual(result.json(),expected)
                    c=chunks[0]
                    resolved=client.post(self.route(meta)+f"/chunks/{c['chunk_id']}/evidence/resolve",json=c['evidence'])
                    self.assertEqual(resolved.status_code,200,resolved.text)
            finally:
                process.terminate()
                process.wait(timeout=5)


class FixtureRecoveryTests(unittest.TestCase):
    def test_safe_fixture_recovery_and_no_overwrite(self):
        spec = importlib.util.spec_from_file_location('restore','scripts/validation/restore_synthetic_fixtures.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(dir='work/phase2c') as tmp:
            root = Path(tmp)
            self.assertTrue(all(r['status']=='restored' for r in module.restore(root,True)))
            self.assertTrue(all(r['status']=='present' for r in module.restore(root,True)))
            (root/module.NAMES[0]).write_bytes(b'user-file')
            with self.assertRaises(ValueError):
                module.restore(root,True)
            self.assertEqual((root/module.NAMES[0]).read_bytes(),b'user-file')
