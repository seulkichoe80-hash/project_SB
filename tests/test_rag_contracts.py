import copy
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import test_chunking as fixtures
from apps.api.errors import DomainError
from apps.api.models import Principal
from apps.api.rag_adapters import DeterministicEmbedding, EmbeddingSpec, ExtractiveTestLLM, Generation, checked_vectors
from apps.api.rag_service import RAGService


class AdapterTests(unittest.TestCase):
    def test_determinism_and_normalization(self):
        a=DeterministicEmbedding()
        self.assertEqual(a.embed(['출장 신청','', 'Prepare']),a.embed(['출장 신청','', 'Prepare']))
        for row in a.embed(['출장 신청','']):
            self.assertAlmostEqual(sum(x*x for x in row),1)
        self.assertTrue(a.spec.test_only)

    def test_dimension_finite_zero_count(self):
        for rows,count,dimension in [([[1]],1,4),([[0]*4],1,4),([[math.nan]*4],1,4),([[True]*4],1,4),([],1,4),([[1e308]*4],1,4)]:
            with self.subTest(rows=rows),self.assertRaises(DomainError):
                checked_vectors(rows,count,dimension)

    def test_extractive_empty(self):
        self.assertEqual(ExtractiveTestLLM().generate('missing',[]).status,'insufficient_evidence')

    def test_generation_rejects_extra_fields(self):
        with self.assertRaises(ValueError):
            Generation.model_validate({'status':'candidate','claims':[],'command':'execute'})


class RAGTests(unittest.TestCase):
    tearDown=fixtures.ChunkIntegrationTests.tearDown
    upload=fixtures.ChunkIntegrationTests.upload
    route=fixtures.ChunkIntegrationTests.route
    parse=fixtures.ChunkIntegrationTests.parse
    prepare=fixtures.ChunkIntegrationTests.prepare

    def setUp(self):
        fixtures.ChunkIntegrationTests.setUp(self)
        self.rag=RAGService(self.app.state.chunks,DeterministicEmbedding(),ExtractiveTestLLM())

    def active(self,data=None,name='manual.pdf',document=None):
        meta,_,items=self.prepare(data,name,document)
        self.assertEqual(self.client.post(self.route(meta)+'/activate').status_code,200)
        return meta,items

    def test_index_idempotence(self):
        self.active()
        self.assertEqual(self.rag.index(self.principal),self.rag.index(self.principal))
        with self.parsing.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT count(*) FROM vector_generations').fetchone()[0],1)

    def test_keyword_vector_hybrid_evidence(self):
        self.active();self.rag.index(self.principal)
        for mode in ('keyword','vector','hybrid'):
            result=self.rag.search(self.principal,'Prepare',mode=mode)
            self.assertTrue(result['results'])
            self.assertTrue(result['test_only'])
            for r in result['results']:
                self.assertEqual(r['chunk']['evidence']['organization_id'],'A')
        self.assertEqual(self.rag.search(self.principal,'Prepare'),self.rag.search(self.principal,'Prepare'))

    def test_hwpx_original_resolution(self):
        _,items=self.active(fixtures.fixtures.HWPX.read_bytes(),'manual.hwpx')
        self.rag.index(self.principal)
        result=self.rag.search(self.principal,'신청',mode='vector')
        self.assertTrue(result['results'])
        self.assertTrue(all(r['chunk']['evidence']['version_id']==items[0]['evidence']['version_id'] for r in result['results']))

    def test_other_organization_and_missing_auth(self):
        self.active();self.rag.index(self.principal)
        self.assertEqual(self.rag.search(Principal('reader','B','reader'),'Prepare')['results'],[])
        for method,args in [(self.rag.search,(None,'Prepare')),(self.rag.index,(None,))]:
            with self.assertRaises(DomainError) as e:method(*args)
            self.assertEqual(e.exception.status,401)

    def test_reader_cannot_index_worker_cannot_search(self):
        with self.assertRaises(DomainError):self.rag.index(Principal('r','A','reader'))
        with self.assertRaises(DomainError):self.rag.search(self.worker,'Prepare')

    def test_old_version_and_deregister_excluded(self):
        first,_=self.active();self.rag.index(self.principal)
        second,_=self.active(fixtures.fixtures.pdf('Replacement'),document=first['document_id'])
        self.assertEqual(self.rag.search(self.principal,'Prepare',mode='vector')['results'],[])
        self.rag.index(self.principal)
        self.assertTrue(all(x['chunk']['evidence']['version_id']==second['id'] for x in self.rag.search(self.principal,'Replacement')['results']))
        self.client.delete('/documents/'+first['document_id'])
        self.assertEqual(self.rag.search(self.principal,'Replacement')['results'],[])

    def test_restart_persists(self):
        self.active();self.rag.index(self.principal)
        reopened=RAGService(self.app.state.chunks,DeterministicEmbedding())
        self.assertEqual(self.rag.search(self.principal,'Prepare'),reopened.search(self.principal,'Prepare'))

    def test_separate_process_restart(self):
        self.active();self.rag.index(self.principal)
        script="""
from pathlib import Path
from apps.api.main import create_app
from apps.api.models import Principal
from apps.api.rag_service import RAGService
from apps.api.rag_adapters import DeterministicEmbedding
import sys
app=create_app(Path(sys.argv[1]),parsing_enabled=True)
rag=RAGService(app.state.chunks,DeterministicEmbedding())
assert rag.search(Principal('test-reader','A','reader'),'Prepare',mode='vector')['results']
print('vector restart ok')
"""
        run=subprocess.run([sys.executable,'-B','-c',script,str(self.root)],capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stderr)
        self.assertIn('vector restart ok',run.stdout)

    def test_model_dimension_generation_swap(self):
        self.active();old=self.rag.index(self.principal)
        other=RAGService(self.app.state.chunks,DeterministicEmbedding(32))
        with self.assertRaises(DomainError):other.search(self.principal,'Prepare',mode='vector')
        self.assertNotEqual(other.index(self.principal),old)
        self.assertTrue(other.search(self.principal,'Prepare',mode='vector')['results'])
        with self.assertRaises(DomainError):self.rag.search(self.principal,'Prepare',mode='vector')
        self.assertEqual(self.rag.index(self.principal),old)

    def test_failed_embedding_keeps_previous_generation(self):
        self.active();old=self.rag.index(self.principal)
        with patch.object(self.rag.embedding,'embed',side_effect=RuntimeError('injected')):
            with self.assertRaises(RuntimeError):self.rag.index(self.principal)
        self.assertEqual(self.rag.index(self.principal),old)
        self.assertTrue(self.rag.search(self.principal,'Prepare')['results'])

    def test_interrupted_embedding_retry(self):
        self.active();old=self.rag.index(self.principal)
        with patch.object(self.rag.embedding,'embed',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):self.rag.index(self.principal)
        self.assertEqual(self.rag.index(self.principal),old)

    def test_original_tampered_during_embedding(self):
        meta,_=self.active();original=self.rag.embedding.embed
        def tamper(texts):
            # Store path is internal: inject a failed integrity read after computation.
            self.parsing.documents.store.read=lambda *args: (_ for _ in ()).throw(DomainError('hash_mismatch'))
            return original(texts)
        with patch.object(self.rag.embedding,'embed',side_effect=tamper):
            with self.assertRaises(DomainError):self.rag.index(self.principal)
        with self.parsing.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT count(*) FROM vector_current').fetchone()[0],0)

    def test_publish_rollback_and_retry(self):
        meta,_=self.active();old=self.rag.index(self.principal)
        self.active(fixtures.fixtures.pdf('Replacement'),document=meta['document_id'])
        with self.parsing.repo.transaction() as db:
            db.connection.execute("CREATE TRIGGER vector_fail BEFORE INSERT ON vector_items BEGIN SELECT RAISE(ABORT,'injected'); END")
        with self.assertRaises(Exception):self.rag.index(self.principal)
        with self.parsing.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT generation_id FROM vector_current').fetchone()[0],old)
            self.assertEqual(db.connection.execute('SELECT count(*) FROM vector_generations').fetchone()[0],1)
            db.connection.execute('DROP TRIGGER vector_fail')
        self.assertNotEqual(self.rag.index(self.principal),old)

    def test_changed_source_during_embedding(self):
        meta,_=self.active();original=self.rag.embedding.embed
        def mutate(texts):
            self.client.delete('/documents/'+meta['document_id'])
            return original(texts)
        with patch.object(self.rag.embedding,'embed',side_effect=mutate):
            with self.assertRaises(DomainError):self.rag.index(self.principal)
        with self.parsing.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT count(*) FROM vector_generations').fetchone()[0],0)

    def test_forged_vector_payload_rejected(self):
        _,items=self.active();forged=copy.deepcopy(items[0]);forged['text']='invented'
        with patch.object(self.rag.store,'candidates',return_value=[forged]):
            with self.assertRaises(DomainError):self.rag.search(self.principal,'Prepare',mode='vector')

    def test_forged_anchor_and_version_rejected(self):
        _,items=self.active()
        for key,value in [('organization_id','B'),('version_id','missing'),('source_anchor',[])]:
            forged=copy.deepcopy(items[0]);forged['evidence'][key]=value
            with patch.object(self.rag.store,'candidates',return_value=[forged]):
                with self.assertRaises(DomainError):self.rag.search(self.principal,'Prepare',mode='vector')

    def test_duplicate_results_rejected(self):
        _,items=self.active()
        with patch.object(self.rag.store,'candidates',return_value=[items[0],items[0]]):
            with self.assertRaises(DomainError):self.rag.search(self.principal,'Prepare',mode='vector')

    def test_tampered_original_blocks_search(self):
        meta,_=self.active();self.rag.index(self.principal)
        with patch.object(self.parsing.documents.store,'read',side_effect=DomainError('hash_mismatch')):
            with self.assertRaises(DomainError):self.rag.search(self.principal,'Prepare')

    def test_answer_contract_and_missing_llm(self):
        self.active();self.rag.index(self.principal)
        result=self.rag.answer(self.principal,'Prepare')
        self.assertEqual(result['status'],'candidate')
        self.assertTrue(result['claims'][0]['evidence_refs'])
        self.assertEqual(result['claims'][0]['semantic_verification'],'NOT_VERIFIED')
        with self.assertRaises(DomainError):RAGService(self.app.state.chunks,DeterministicEmbedding()).answer(self.principal,'Prepare')

    def test_unknown_citation_and_invented_claim(self):
        self.active()
        for response in [{'status':'candidate','claims':[{'text':'invented deadline','chunk_ids':['unknown']}]}, {'status':'candidate','claims':[]}]:
            with patch.object(self.rag.llm,'generate',return_value=response):
                with self.assertRaises(DomainError):self.rag.answer(self.principal,'Prepare')
        def invented(question,context):
            return {'status':'candidate','claims':[{'text':'invented deadline','chunk_ids':[context[0]['chunk_id']]}]}
        with patch.object(self.rag.llm,'generate',side_effect=invented):
            with self.assertRaises(DomainError):self.rag.answer(self.principal,'Prepare')

    def test_no_context_abstains(self):
        self.assertEqual(self.rag.answer(self.principal,'missing')['status'],'insufficient_evidence')

    def test_irrelevant_vectors_do_not_become_answer(self):
        self.active();self.rag.index(self.principal)
        self.assertEqual(self.rag.answer(self.principal,'unmentioned-zebra-deadline')['status'],'insufficient_evidence')

    def test_new_chunk_generation_excludes_old_vectors(self):
        meta,_=self.active();self.rag.index(self.principal)
        response=self.client.post(self.route(meta)+'/chunk-jobs',json={'max_chars':64})
        self.assertEqual(response.status_code,202)
        chunks=self.app.state.chunks
        self.assertEqual(chunks.execute(self.worker,chunks.claim(self.worker)),'completed')
        self.assertEqual(self.rag.search(self.principal,'Prepare',mode='vector')['results'],[])
        self.rag.index(self.principal)
        self.assertTrue(self.rag.search(self.principal,'Prepare',mode='vector')['results'])

    def test_deregister_during_generation(self):
        meta,_=self.active()
        original=self.rag.llm.generate
        def mutate(question,context):
            self.client.delete('/documents/'+meta['document_id'])
            return original(question,context)
        with patch.object(self.rag.llm,'generate',side_effect=mutate):
            with self.assertRaises(DomainError):self.rag.answer(self.principal,'Prepare')

    def test_invalid_queries(self):
        for query,mode,limit in [('', 'hybrid',5),('x'*201,'hybrid',5),('x','unknown',5),('x','hybrid',0)]:
            with self.assertRaises(DomainError):self.rag.search(self.principal,query,limit,mode)

    def test_real_providers_disabled(self):
        embedding=DeterministicEmbedding();embedding.spec=EmbeddingSpec(test_only=False)
        with self.assertRaises(DomainError):RAGService(self.app.state.chunks,embedding)

