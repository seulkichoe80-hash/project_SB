"""Offline controlled retrieval, SQL/FTS isolation and metric arithmetic tests."""
import copy
from pathlib import Path
import secrets
import sqlite3
import unittest
from unittest.mock import patch
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.chunking import ChunkConfig
from scripts.validation.evaluation_fixtures import ROOT,reproduce,services,EvaluationQueryAdapter,LiveEvidenceResolver
from scripts.validation.retrieval_ablation import AblationSearch,normalize,query_tokens,key,query_metrics,latency


class AblationMetricTests(unittest.TestCase):
    def test_normalization_is_predefined_and_not_particle_stripping(self):
        self.assertEqual(normalize('  출장의，신청서를？  '),'출장의 신청서를')
        self.assertEqual(normalize('Ａ  B\tC'),'a b c')
    def test_normalization_idempotent(self):
        s='ｘ・서식명（A）\n이름_확인!';self.assertEqual(normalize(normalize(s)),normalize(s))
    def test_raw_question_unchanged_and_no_answer_based_tokens(self):
        q='출장의 처리 순서를 알려주세요.';text,tokens=query_tokens(q,'A');self.assertEqual(text,q)
        self.assertEqual(query_tokens(q,'C')[1],['출장의','처리','순서를','알려주세요'])
    def test_distinct_or_tokens_and_no_silent_truncation(self):
        self.assertEqual(query_tokens('자료 자료 자료','C')[1],['자료'])
        with self.assertRaises(ValueError):query_tokens('a '*129,'C')
        with self.assertRaises(ValueError):query_tokens('x'*201,'D')
    def test_metrics_multi_evidence_all_denominators(self):
        x=query_metrics(['a','b','c'],['x','a','y','b','z','c'])
        self.assertEqual(x['hit_at_5'],1);self.assertAlmostEqual(x['recall_at_5'],2/3);self.assertEqual(x['recall_at_10'],1);self.assertEqual(x['mrr'],.5)
    def test_no_result_is_zero_positive_not_negative_denominator(self):
        x=query_metrics(['a'],[]);self.assertEqual(x['mrr'],0);self.assertEqual(x['hit_at_10'],0);self.assertTrue(x['no_results'])
        with self.assertRaises(ValueError):query_metrics([],['a'])
    def test_mrr_full_and_at_10_are_separate(self):
        x=query_metrics(['expected'],[str(i) for i in range(11)]+['expected']);self.assertEqual(x['mrr'],1/12);self.assertEqual(x['mrr_at_10'],0)
    def test_duplicate_ranked_evidence_rejected(self):
        with self.assertRaises(ValueError):query_metrics(['a'],['a','a'])
    def test_latency_nearest_rank_and_empty(self):
        r=latency([.001,.002,.003]);self.assertEqual(r['p50_ms'],2);self.assertEqual(r['p95_ms'],3);self.assertIsNone(latency([])['mean_ms'])


class RetrievalAblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'work/v03c2-tests'/secrets.token_hex(8);cls.base.mkdir(parents=True)
        cls.g=reproduce(cls.base/'runtime',cls.base/'output')
    def setUp(self):
        self.chunks=services(self.base/'runtime');self.search=AblationSearch(self.chunks,self.g);self.reader=Principal('r','A','reader')
    def tearDown(self):self.search.close()
    def test_index_rows_49_8_and_fts_support(self):
        self.assertEqual(self.search.connections['A'].execute('SELECT count(*) FROM items').fetchone()[0],49)
        self.assertEqual(self.search.connections['B'].execute('SELECT count(*) FROM items').fetchone()[0],8)
        self.assertTrue(self.search.fts_supported)
    def test_baseline_equivalent_to_existing_real_adapter(self):
        reference=EvaluationQueryAdapter(self.chunks,LiveEvidenceResolver(self.chunks,self.g))
        for q in ['일정표','자료','출장 신청서',self.g['queries'][0]['question']]:
            actual=self.search.search(self.reader,q,'A',20)
            expected=reference.search(self.reader,q,20)
            self.assertEqual([key(x['chunk']) for x in actual['results']],[key(x) for x in expected['results']])
    def test_A_B_and_OR_difference_measured_without_gold_query(self):
        self.assertFalse(self.search.search(self.reader,'일정표 없는문자열','A')['results'])
        self.assertTrue(self.search.search(self.reader,'일정표 없는문자열','C')['results'])
    def test_punctuation_normalization_does_not_strip_particle(self):
        a=self.search.search(self.reader,'일정표?','A');b=self.search.search(self.reader,'일정표?','B')
        self.assertFalse(a['results']);self.assertTrue(b['results'])
        self.assertEqual(self.search.search(self.reader,'일정표를','B')['tokens'],['일정표를'])
    def test_OR_score_distinct_terms_order_deterministic(self):
        a=self.search.search(self.reader,'일정표 자료 자료','C');b=self.search.search(self.reader,'일정표 자료','C')
        self.assertEqual(a['results'],b['results']);scores=[r['score'] for r in a['results']];self.assertEqual(scores,sorted(scores,reverse=True))
    def test_FTS_bm25_is_lower_is_better(self):
        r=self.search.search(self.reader,'자료 제출','D');self.assertTrue(r['results'])
        self.assertEqual([x['score'] for x in r['results']],sorted(x['score'] for x in r['results']))
        self.assertTrue(all(x['score_kind']=='sqlite_bm25_lower_is_better' for x in r['results']))
    def test_FTS_unsupported_is_explicit_not_fallback(self):
        self.search.fts_supported=False
        with self.assertRaises(DomainError) as c:self.search.search(self.reader,'자료','D')
        self.assertEqual(c.exception.code,'fts5_unavailable')
    def test_SQL_and_FTS_injection_is_literal_input(self):
        for mode in ('A','B','C','D'):
            for q in ["자료' OR 1=1 --",'" OR NEAR(*) - DROP TABLE items;','% _ \\','AND OR NOT NEAR']:
                r=self.search.search(self.reader,q,mode);self.assertFalse(r['answer_generated'])
                self.assertTrue(all(x['chunk']['evidence']['organization_id']=='A' for x in r['results']))
            self.assertEqual(self.search.connections['A'].execute('SELECT COUNT(*) FROM items').fetchone()[0],49)
    def test_all_modes_tenant_isolation(self):
        for m in ('A','B','C','D'):
            for p in (self.reader,Principal('r','B','reader')):
                r=self.search.search(p,'출장 자료 신청 확인',m)
                self.assertTrue(all(x['chunk']['evidence']['organization_id']==p.institution_id for x in r['results']))
    def test_foreign_scope_and_worker_denied(self):
        for p in (None,Principal('w','A','worker'),Principal('r','C','reader')):
            with self.assertRaises(DomainError):self.search.search(p,'자료','C')
    def test_invalid_method_and_limit_rejected(self):
        for m,k in [('unknown',5),('A',True),('C',58),('D',0)]:
            with self.assertRaises(ValueError):self.search.search(self.reader,'자료',m,k)
    def test_safe_abstention_response_even_with_results(self):
        r=self.search.search(self.reader,'자료','C');self.assertTrue(r['results'])
        self.assertFalse(r['answer_generated']);self.assertEqual(r['response_status'],'CANDIDATE_CONTEXT_ONLY_NO_ANSWER');self.assertEqual(r['semantic_verification'],'NOT_VERIFIED')
    def test_empty_normalized_query_returns_no_answer(self):
        for m in ('B','C','D'):
            r=self.search.search(self.reader,'???',m);self.assertFalse(r['results']);self.assertEqual(r['response_status'],'INSUFFICIENT_RETRIEVAL_NO_ANSWER')
    def test_rankings_and_scores_reproducible(self):
        for m in ('A','B','C','D'):
            a=self.search.search(self.reader,'출장 서식 자료',m);b=self.search.search(self.reader,'출장 서식 자료',m)
            self.assertEqual(a['results'],b['results'])
    def test_forged_index_payload_blocked(self):
        item=next(iter(self.search.items['A'].values()));item['evidence']['spans'][0]['quote']='forged'
        with self.assertRaises(DomainError):self.search.search(self.reader,'합성','C')
    def test_old_generation_or_retirement_after_rank_rejected(self):
        g=reproduce(self.base/'mutation-runtime',self.base/'mutation-output');c=services(self.base/'mutation-runtime');s=AblationSearch(c,g)
        try:
            original=s._rank
            def rank(org,q,m):
                r=original(org,q,m)
                with c.repo.transaction() as db:db.connection.execute('UPDATE documents SET registered=0 WHERE id=?',(g['documents'][0]['document_id'],))
                return r
            with patch.object(s,'_rank',side_effect=rank):
                with self.assertRaises(DomainError):s.search(self.reader,'자료','C')
        finally:s.close()
    def test_real_chunk_generation_change_rejected(self):
        g=reproduce(self.base/'generation-runtime',self.base/'generation-output');c=services(self.base/'generation-runtime');s=AblationSearch(c,g)
        try:
            d=g['documents'][0];p=Principal('m','A','manager');w=Principal('w','A','worker')
            c.enqueue(p,d['document_id'],d['version_id'],ChunkConfig(max_chars=799,context_chars=0));self.assertEqual(c.execute(w,c.claim(w)),'completed')
            with self.assertRaises(DomainError):s.search(self.reader,'자료','D')
        finally:s.close()
    def test_no_external_socket_dns_and_product_search_unchanged(self):
        before=self.chunks.search(Principal('r','A','reader'),'일정표')
        with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')):
            self.assertEqual(self.search.search(self.reader,'일정표','D')['actual_provider_calls'],0)
        self.assertEqual(before,self.chunks.search(Principal('r','A','reader'),'일정표'))
