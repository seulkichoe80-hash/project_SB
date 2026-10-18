"""Opt-in product search and preserved literal/RAG boundary; no external providers."""
import copy
import json
from pathlib import Path
import secrets
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import create_app,authenticated_principal
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.search_settings import SearchSettings,normalize_search,scored_terms
from apps.api.chunking import ChunkConfig
from scripts.validation.evaluation_fixtures import ROOT,reproduce
from scripts.validation.retrieval_ablation import normalize,AblationSearch,key


class SearchSettingTests(unittest.TestCase):
    def test_flag_defaults_and_exact_enable(self):
        with patch.dict('os.environ',{},clear=True):self.assertFalse(SearchSettings.from_environment().scored_or_enabled)
        with patch.dict('os.environ',{'SB_ENABLE_SCORED_OR_SEARCH':'1'}):self.assertTrue(SearchSettings.from_environment().scored_or_enabled)
        for value in ('true','yes','1 ','invalid'):
            with patch.dict('os.environ',{'SB_ENABLE_SCORED_OR_SEARCH':value}):
                with self.assertRaises(ValueError):SearchSettings.from_environment()
    def test_settings_strict_and_no_model_copy_bypass(self):
        with self.assertRaises(ValueError):SearchSettings(scored_or_enabled='true')
        with self.assertRaises(ValueError):SearchSettings(extra_field=True)
    def test_identical_preregistered_normalization(self):
        for value in ['출장의，신청서를？','Ａ B\tC','서식명（A）','资料_확인!',"' OR -- %"]:
            self.assertEqual(normalize_search(value),normalize(value))
    def test_query_envelope_and_dedup(self):
        self.assertEqual(scored_terms('자료 자료'),['자료']);self.assertEqual(scored_terms('???'),[])
        for q in (' ',None,'a '*129,'x'*201):
            with self.assertRaises(ValueError):scored_terms(q)


class ProductScoredSearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=ROOT/'work/v03d-tests'/secrets.token_hex(8);cls.base.mkdir(parents=True)
        cls.g=reproduce(cls.base/'runtime',cls.base/'output')
    def setUp(self):
        self.app=create_app(self.base/'runtime',parsing_enabled=True,search_settings=SearchSettings(scored_or_enabled=True))
        self.principal=Principal('synthetic-reader','A','reader')
        self.app.dependency_overrides[authenticated_principal]=lambda:self.principal
        self.client=TestClient(self.app);self.chunks=self.app.state.chunks
    def tearDown(self):self.client.close()
    def search(self,q='자료',strategy='scored_or',limit=10):return self.client.get('/search',params={'q':q,'strategy':strategy,'limit':limit})
    def test_default_response_unchanged_even_flag_on(self):
        r=self.client.get('/search',params={'q':'일정표'});self.assertEqual(r.status_code,200)
        self.assertEqual(set(r.json()),{'method','results'});self.assertEqual(r.json()['method'],'sqlite_keyword_substring_v1')
        self.assertEqual(r.json()['results'],self.chunks.search(self.principal,'일정표'))
    def test_opt_in_response_same_chunk_schema(self):
        r=self.search();self.assertEqual(r.status_code,200);self.assertEqual(r.json()['method'],'sqlite_scored_or_v1')
        self.assertTrue(r.json()['results']);self.assertEqual(set(r.json()['results'][0]),set(self.g['documents'][0]['chunks'][0]))
        self.assertEqual(r.headers['cache-control'],'no-store')
    def test_disabled_flag_not_client_activatable(self):
        app=create_app(self.base/'runtime',parsing_enabled=True,search_settings=SearchSettings())
        app.dependency_overrides[authenticated_principal]=lambda:self.principal
        with TestClient(app) as c:
            r=c.get('/search',params={'q':'자료','strategy':'scored_or','feature_flag':'1'},headers={'SB_ENABLE_SCORED_OR_SEARCH':'1'})
            self.assertEqual(r.status_code,503);self.assertEqual(r.json()['error'],'scored_or_search_not_enabled')
            self.assertEqual(c.get('/search',params={'q':'일정표'}).status_code,200)
    def test_flag_only_from_server_configuration(self):
        with patch.dict('os.environ',{'SB_ENABLE_SCORED_OR_SEARCH':'1'}):
            app=create_app(self.base/'runtime',parsing_enabled=True)
        self.assertTrue(app.state.chunks.search_settings.scored_or_enabled)
        self.assertEqual(app.state.chunks.search_adapter.__class__.__name__,'SQLiteKeywordSearch')
    def test_long_C_and_preserved_literal_limit(self):
        q=self.g['queries'][0]['question'];self.assertEqual(self.search(q).status_code,200)
        self.assertEqual(self.search(q,'literal').status_code,400)
    def test_unknown_strategy_limits_and_missing_query(self):
        self.assertEqual(self.search(strategy='auto').status_code,422)
        self.assertEqual(self.search(limit=51).status_code,400);self.assertEqual(self.search(q='x'*201).status_code,400)
        self.assertEqual(self.client.get('/search').status_code,422)
    def test_API_order_matches_experiment_C(self):
        scorer=AblationSearch(self.chunks,self.g)
        try:
            for q in [self.g['queries'][0]['question'],'자료','회의 종료 뒤 주관자가 해야 할 일은 무엇인가요?']:
                expected=[key(x['chunk']) for x in scorer.search(self.principal,q,'C',10)['results']]
                actual=[key(x) for x in self.search(q).json()['results']];self.assertEqual(actual,expected)
        finally:scorer.close()
    def test_tenant_and_role_isolation(self):
        for org in ('A','B'):
            self.principal=Principal('r',org,'reader');r=self.search('출장 자료 신청 확인');self.assertEqual(r.status_code,200)
            self.assertTrue(all(x['evidence']['organization_id']==org for x in r.json()['results']))
        self.principal=Principal('w','A','worker');self.assertEqual(self.search().status_code,403)
    def test_default_deny_auth_still_active(self):
        self.app.dependency_overrides.clear();self.assertEqual(self.search().status_code,401)
    def test_SQL_injection_no_answer_generation(self):
        for q in ["자료' OR 1=1 --",'"; DROP TABLE chunk_items; --','% _ \\']:
            r=self.search(q);self.assertEqual(r.status_code,200)
            self.assertNotIn('claims',r.json());self.assertNotIn('answer',r.json())
            self.assertTrue(all(x['evidence']['organization_id']=='A' for x in r.json()['results']))
        self.assertTrue(self.search('자료').json()['results'])
    def test_negative_queries_remain_candidates_not_answers(self):
        for q in self.g['queries'][-4:]:
            self.principal=Principal('r',q['organization_id'],'reader');r=self.search(q['question']);self.assertEqual(r.status_code,200)
            forbidden={key({'evidence':e}) for e in q.get('forbidden_evidence_refs',[])}
            self.assertFalse(forbidden&{key(x) for x in r.json()['results']});self.assertNotIn('answer',r.json())
    def test_forged_payload_and_duplicate_results_blocked(self):
        item=copy.deepcopy(self.g['documents'][0]['chunks'][0]);item['evidence']['spans'][0]['quote']='forged'
        with patch.object(self.chunks.scored_adapter,'search',return_value=[item]):self.assertEqual(self.search().status_code,409)
        item=self.g['documents'][0]['chunks'][0]
        with patch.object(self.chunks.scored_adapter,'search',return_value=[item,item]):self.assertEqual(self.search().status_code,409)
    def test_foreign_adapter_result_blocked(self):
        item=self.g['documents'][-2]['chunks'][0]
        with patch.object(self.chunks.scored_adapter,'search',return_value=[item]):self.assertEqual(self.search().status_code,409)
    def test_lease_generation_change_during_evidence_validation_blocked(self):
        g=reproduce(self.base/'changed-runtime',self.base/'changed-output')
        app=create_app(self.base/'changed-runtime',parsing_enabled=True,search_settings=SearchSettings(scored_or_enabled=True));c=app.state.chunks
        p=Principal('r','A','reader');original=c.resolve;changed=[False]
        def resolve(*a,**kw):
            result=original(*a,**kw)
            if not changed[0]:
                changed[0]=True;d=g['documents'][0];m=Principal('m','A','manager');w=Principal('w','A','worker')
                c.enqueue(m,d['document_id'],d['version_id'],ChunkConfig(max_chars=799,context_chars=0));self.assertEqual(c.execute(w,c.claim(w)),'completed')
            return result
        with patch.object(c,'resolve',side_effect=resolve):
            with self.assertRaises(DomainError):c.search(p,'출장',10,strategy='scored_or')
    def test_corpus_caps_no_partial_results(self):
        for settings in [SearchSettings(scored_or_enabled=True,max_scanned_chunks=1),SearchSettings(scored_or_enabled=True,max_scanned_bytes=1024)]:
            app=create_app(self.base/'runtime',parsing_enabled=True,search_settings=settings)
            with self.assertRaises(DomainError) as r:app.state.chunks.search(self.principal,'자료',10,strategy='scored_or')
            self.assertEqual(r.exception.status,413)
    def test_literal_RAG_call_is_unchanged(self):
        with patch.object(self.chunks.scored_adapter,'search',side_effect=AssertionError('C not selected')):
            self.assertTrue(self.chunks.search(self.principal,'일정표'))
    def test_no_external_socket_or_DNS(self):
        with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')):
            self.assertEqual(self.search().status_code,200)

    def test_settings_copy_bypass_is_revalidated_at_factory(self):
        copied=SearchSettings().model_copy(update={'scored_or_enabled':'yes'})
        import warnings
        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter('always')
            with self.assertRaises(ValueError):create_app(self.base/'runtime',parsing_enabled=True,search_settings=copied)
        self.assertFalse(records)
    def test_retirement_and_version_switch_during_lookup_fail_closed(self):
        from scripts.validation.build_phase2c2b_goldset import hwpx
        from apps.api.worker import run_once
        for action in ('retire','switch'):
            root=self.base/(action+'-runtime');g=reproduce(root,self.base/(action+'-output'))
            app=create_app(root,parsing_enabled=True,search_settings=SearchSettings(scored_or_enabled=True));c=app.state.chunks
            d=g['documents'][0];p=Principal('r','A','reader');m=Principal('m','A','manager');w=Principal('w','A','worker')
            original=c.resolve;changed=[False]
            def resolve(*a,**kw):
                value=original(*a,**kw)
                if not changed[0]:
                    changed[0]=True
                    if action=='retire':c.documents.deregister(m,d['document_id'])
                    else:
                        meta,_=c.documents.register(m,'replacement.hwpx','application/octet-stream',hwpx(['합성 대체 지침']),document_id=d['document_id'])
                        self.assertEqual(run_once(c.parsing,w),'completed');c.enqueue(m,d['document_id'],meta['id'],ChunkConfig());self.assertEqual(c.execute(w,c.claim(w)),'completed');c.documents.activate(m,d['document_id'],meta['id'])
                return value
            with patch.object(c,'resolve',side_effect=resolve):
                with self.assertRaises(DomainError):c.search(p,'출장',10,strategy='scored_or')
    def test_original_integrity_error_rejects_result(self):
        with patch.object(self.chunks.documents.store,'read',side_effect=DomainError('original_integrity_failure',409)):
            self.assertEqual(self.search('일정표').status_code,409)
