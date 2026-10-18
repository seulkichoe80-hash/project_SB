"""Real SQL diagnostics and fixed-context isolation, no real providers or human approval."""
import copy
import json
from pathlib import Path
import secrets
import unittest
from unittest.mock import patch
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.chunking import canonical,digest,ChunkConfig
from scripts.validation.evaluation_fixtures import reproduce,services,ROOT
from scripts.validation.retrieval_diagnostics import diagnose_question,diagnose_all
from scripts.validation.fixed_context_evaluation import FixedContextBuilder,FakeFixedExtraction
from scripts.validation.run_v03c1_diagnostics import human_plan


class RetrievalDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'work/v03c1-tests'/secrets.token_hex(8);cls.base.mkdir(parents=True)
        cls.g=reproduce(cls.base/'runtime',cls.base/'output')
    def setUp(self):
        self.chunks=services(self.base/'runtime');self.generation=copy.deepcopy(self.g)
    def q(self,index=0):return copy.deepcopy(self.generation['queries'][index])
    def test_real_40_question_cause_counts(self):
        d=diagnose_all(self.chunks,self.generation);self.assertEqual(len(d['cases']),40)
        self.assertEqual(d['counts'],{'DATA':0,'SCOPE':0,'TOKENIZATION':36,'RETRIEVAL':0,'EVALUATION':4,'UNKNOWN':0})
    def test_index_exists_and_scope_49_8(self):
        a=diagnose_question(self.chunks,self.generation,self.q());b=diagnose_question(self.chunks,self.generation,self.q(30))
        self.assertEqual(a['stored_chunk_rows'],57);self.assertEqual(a['filter_counts']['parse_attempt'],49)
        self.assertEqual(b['filter_counts']['parse_attempt'],8)
    def test_tokens_are_actual_casefold_split_windows(self):
        r=diagnose_question(self.chunks,self.generation,self.q())
        self.assertEqual(len(r['window_probes']),2)
        self.assertEqual([t for w in r['window_probes'] for t in w['tokens']],self.q()['question'].casefold().split())
    def test_actual_sql_trace_and_no_lexical_score(self):
        r=diagnose_question(self.chunks,self.generation,self.q())
        self.assertTrue(all('LIKE' in w['executed_sql'][0] and w['sql_score'] is None for w in r['actual_search_trace']))
    def test_expected_chunks_present_before_token_filter(self):
        r=diagnose_question(self.chunks,self.generation,self.q());self.assertEqual(len(r['expected_present_in_eligible_index']),3)
        self.assertFalse(r['expected_missing_from_eligible_index']);self.assertEqual(r['expected_hits_at_k'],0)
    def test_missing_literal_token_is_verified_cause(self):
        r=diagnose_question(self.chunks,self.generation,self.q())
        self.assertTrue(all(any(t['eligible_sql_hits']==0 for t in w['term_probes']) for w in r['window_probes']))
        self.assertTrue(r['secondary_findings']['top_k_not_causal_when_sql_empty']);self.assertFalse(r['top_k_loss'])
    def test_negative_cases_are_not_positive_recall_failures(self):
        r=diagnose_question(self.chunks,self.generation,self.q(39))
        self.assertEqual(r['classification'],'EVALUATION');self.assertIsNone(r['recall_at_k']);self.assertEqual(r['expected_ref_count'],0)
    def test_known_short_keyword_retrieves_expected(self):
        q=self.q(1);q['question']='일정표'
        r=diagnose_question(self.chunks,self.generation,q);self.assertEqual(r['expected_hits_at_k'],1)
        self.assertIn('retrieval_succeeded_not_a_current_miss',r['confirmed'])
    def test_bad_matching_reference_is_evaluation_error(self):
        q=self.q();q['expected_evidence_refs'][0]['chunk_id']='wrong-id'
        r=diagnose_question(self.chunks,self.generation,q);self.assertEqual(r['classification'],'EVALUATION');self.assertTrue(r['invalid_expected_refs'])
    def test_fake_cross_tenant_gold_is_evaluation_error(self):
        q=self.q();q['expected_evidence_refs'][0]=copy.deepcopy(self.generation['queries'][30]['expected_evidence_refs'][0])
        r=diagnose_question(self.chunks,self.generation,q);self.assertEqual(r['classification'],'EVALUATION')
    def test_restores_search_adapter_even_when_failure(self):
        original=self.chunks.search_adapter
        with patch.object(original,'search',side_effect=DomainError('simulated_search_failure')):
            r=diagnose_question(self.chunks,self.generation,self.q())
        self.assertIs(self.chunks.search_adapter,original);self.assertEqual(r['retrieval_status'],'retrieval_failed')
    def test_missing_index_data_classification(self):
        # Empty isolated database, never delete any existing source/fixture/index.
        c=services(self.base/'empty-runtime');r=diagnose_question(c,self.generation,self.q())
        self.assertEqual(r['classification'],'DATA');self.assertEqual(r['stored_chunk_rows'],0)
    def test_scope_and_generation_change_classification(self):
        g=reproduce(self.base/'scope-runtime',self.base/'scope-output');c=services(self.base/'scope-runtime');d=g['documents'][0]
        with c.repo.transaction() as db:db.connection.execute('UPDATE documents SET registered=0 WHERE id=?',(d['document_id'],))
        r=diagnose_question(c,g,g['queries'][0]);self.assertEqual(r['classification'],'SCOPE')
    def test_all_tokens_exist_but_no_chunk_cooccurrence(self):
        q=self.q();q['question']='일정표 휴가';r=diagnose_question(self.chunks,self.generation,q)
        self.assertTrue(all(t['eligible_sql_hits']>0 for t in r['window_probes'][0]['term_probes']))
        self.assertEqual(r['classification'],'RETRIEVAL')
    def test_no_external_socket_or_dns_during_diagnosis(self):
        with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')):
            r=diagnose_question(self.chunks,self.generation,self.q());self.assertEqual(r['actual_model_calls'],0)
    def test_question_limits_unknown_not_speculative_cause(self):
        q=self.q();q['question']='x'*201;r=diagnose_question(self.chunks,self.generation,q)
        self.assertEqual(r['classification'],'UNKNOWN');self.assertTrue(r['uncertain'])
    def test_human_priority_10_and_zero_fake_human_judgments(self):
        # Reuse the real existing immutable review table; no generated human verdicts.
        plan=human_plan(self.generation,ROOT/'outputs/v03b/isolated-evaluation')
        self.assertEqual(plan['completed'],0);self.assertEqual(len(plan['pending_ids']),40)
        self.assertEqual(len({x['id'] for x in plan['priority_10']}),10);self.assertTrue(all(x['verdict'] is None for x in plan['priority_10']))


    def test_human_progress_invalid_judgment_stays_pending(self):
        source=json.loads((ROOT/'outputs/v03b/isolated-evaluation/review-rows.json').read_text())
        source[0].update(reviewer='test-only reviewer',reviewed_at='2026-10-18T00:00:00+00:00',verdict='AUTOMATIC_PASS',reason='not a human judgment')
        out=self.base/'invalid-review';out.mkdir();(out/'review-rows.json').write_text(json.dumps(source))
        plan=human_plan(self.generation,out);self.assertEqual(plan['completed'],0);self.assertEqual(len(plan['invalid_review_ids']),1)
    def test_sql_rrf_is_separate_from_lexical_score(self):
        q=self.q(1);q['question']='일정표';r=diagnose_question(self.chunks,self.generation,q)
        self.assertAlmostEqual(r['top_k_rrf_scores'][0]['rrf_score'],1/61)
        self.assertIsNone(r['window_probes'][0]['sql_score'])


class FixedContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'work/v03c1-fixed-tests'/secrets.token_hex(8);cls.base.mkdir(parents=True)
        cls.g=reproduce(cls.base/'runtime',cls.base/'output')
    def setUp(self):
        self.chunks=services(self.base/'runtime');self.builder=FixedContextBuilder(self.chunks,self.g)
    def test_complete_tenant_contexts_not_gold_chunk_subset(self):
        a=self.builder.build('A');b=self.builder.build('B');self.assertEqual(len(a['chunks']),49);self.assertEqual(len(b['chunks']),8)
        self.assertEqual(len(a['document_scopes']),6);self.assertEqual(len(b['document_scopes']),1)
        self.assertEqual(a['goldset_status'],'PROVISIONAL');self.assertEqual(a['semantic_verification'],'NOT_VERIFIED')
    def test_context_selection_independent_of_expected_answers(self):
        g=copy.deepcopy(self.g);g['queries']=[]
        other=FixedContextBuilder(self.chunks,g);self.assertEqual(other.build('A'),self.builder.build('A'))
    def test_context_never_calls_retrieval(self):
        with patch.object(self.chunks,'search',side_effect=AssertionError('search must not run')):
            p=self.builder.build('B');r=FakeFixedExtraction(self.builder).extract(p)
        self.assertFalse(r['publishable']);self.assertEqual(r['administrator_approval'],'NOT_REQUESTED')
    def test_missing_chunk_rejected_even_rehashed(self):
        p=self.builder.build('A');p['chunks'].pop();p['context_id']=digest({k:v for k,v in p.items() if k!='context_id'})
        with self.assertRaises(DomainError):self.builder.validate('A',p)
    def test_missing_document_rejected(self):
        p=self.builder.build('A');p['document_scopes'].pop()
        with self.assertRaises(DomainError):self.builder.validate('A',p)
    def test_foreign_packet_and_changed_version_rejected(self):
        p=self.builder.build('B')
        with self.assertRaises(DomainError):self.builder.validate('A',p)
        p['document_scopes'][0]['version_id']='old'
        with self.assertRaises(DomainError):self.builder.validate('B',p)
    def test_forged_quote_in_context_rejected(self):
        p=self.builder.build('B');p['chunks'][0]['evidence']['spans'][0]['quote']='fake'
        with self.assertRaises(DomainError):self.builder.validate('B',p)
    def prediction(self,packet):
        c=next(c for c in packet['chunks'] if c['text'])
        return {'id':'test','status':'generated','labels':{'steps':[{'id':'s','text':c['text'],'evidence_refs':[c['evidence']]}]},'claims':[],
            'elapsed_seconds':0.0,'run_kind':'fake_model'}
    def test_valid_prediction_uses_only_real_context(self):
        p=self.builder.build('B');r=self.builder.validate_prediction(p,self.prediction(p));self.assertEqual(r.run_kind,'fake_model')
    def test_foreign_output_evidence_blocked(self):
        p=self.builder.build('A');pred=self.prediction(p);pred['labels']['steps'][0]['evidence_refs']=[self.builder.build('B')['chunks'][0]['evidence']]
        with self.assertRaises(DomainError):self.builder.validate_prediction(p,pred)
    def test_unknown_and_tampered_output_evidence_blocked(self):
        p=self.builder.build('B');pred=self.prediction(p);pred['labels']['steps'][0]['evidence_refs'][0]['chunk_id']='fake'
        with self.assertRaises(DomainError):self.builder.validate_prediction(p,pred)
    def test_ungrounded_claim_rejected(self):
        p=self.builder.build('B');pred=self.prediction(p);pred['labels']['steps'][0]['text']='99일 이내 의무 승인'
        with self.assertRaises(DomainError):self.builder.validate_prediction(p,pred)
    def test_missing_prediction_evidence_rejected(self):
        p=self.builder.build('B');pred=self.prediction(p);pred['labels']['steps'][0]['evidence_refs']=[]
        with self.assertRaises(DomainError):self.builder.validate_prediction(p,pred)
    def test_generation_manifest_omission_rejected(self):
        g=copy.deepcopy(self.g);g['documents'].pop()
        with self.assertRaises(DomainError):FixedContextBuilder(self.chunks,g)
    def test_fake_extraction_deterministic_not_semantic_approval(self):
        p=self.builder.build('B');f=FakeFixedExtraction(self.builder);a=f.extract(p);b=f.extract(p)
        self.assertEqual(a,b);self.assertEqual(f.document_invocations,2);self.assertEqual(a['semantic_verification'],'NOT_VERIFIED');self.assertFalse(a['publishable'])
    def test_old_chunk_generation_after_packet_creation_rejected(self):
        g=reproduce(self.base/'changed-runtime',self.base/'changed-output');c=services(self.base/'changed-runtime');builder=FixedContextBuilder(c,g)
        packet=builder.build('B');doc=g['documents'][-2];p=Principal('m','B','manager');w=Principal('w','B','worker')
        c.enqueue(p,doc['document_id'],doc['version_id'],ChunkConfig(max_chars=799,context_chars=0));self.assertEqual(c.execute(w,c.claim(w)),'completed')
        with self.assertRaises(DomainError):builder.validate('B',packet)
    def test_no_socket_or_dns_for_fake_extraction(self):
        with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')):
            r=FakeFixedExtraction(self.builder).extract(self.builder.build('B'));self.assertFalse(r['publishable'])

    def test_retirement_after_packet_creation_rejected(self):
        g=reproduce(self.base/'retired-runtime',self.base/'retired-output');c=services(self.base/'retired-runtime');builder=FixedContextBuilder(c,g);packet=builder.build('B')
        doc=g['documents'][-2]
        with c.repo.transaction() as db:db.connection.execute('UPDATE documents SET registered=0 WHERE id=?',(doc['document_id'],))
        with self.assertRaises(DomainError):FakeFixedExtraction(builder).extract(packet)
    def test_live_active_version_change_rejected(self):
        from apps.api.worker import run_once
        from scripts.validation.build_phase2c2b_goldset import hwpx
        g=reproduce(self.base/'version-runtime',self.base/'version-output');c=services(self.base/'version-runtime');builder=FixedContextBuilder(c,g);packet=builder.build('B');doc=g['documents'][-2]
        p=Principal('m','B','manager');w=Principal('w','B','worker')
        meta,_=c.documents.register(p,'replacement.hwpx','application/octet-stream',hwpx(['합성 새 지침']),document_id=doc['document_id'])
        self.assertEqual(run_once(c.parsing,w),'completed');c.enqueue(p,doc['document_id'],meta['id'],ChunkConfig());self.assertEqual(c.execute(w,c.claim(w)),'completed');c.documents.activate(p,doc['document_id'],meta['id'])
        with self.assertRaises(DomainError):builder.validate('B',packet)
