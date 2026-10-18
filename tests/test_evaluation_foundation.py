"""Offline evaluation integrity, arithmetic and retrieval; no actual AI accuracy claims."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pydantic import ValidationError
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.chunking import ChunkConfig
from scripts.validation.evaluation_fixtures import (reproduce,verify_frozen,services,LiveEvidenceResolver,
    EvaluationQueryAdapter,check_answer_key,SOURCE,HISTORICAL,normalized_chunks)
from scripts.validation.evaluation_metrics import (Labels,GoldCase,Prediction,HumanReview,prf,evaluate_case,
    summarize,proposed_gold)
from scripts.validation.run_v03b_evaluation import review_pack


class EvaluationGenerationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import scripts.validation.evaluation_fixtures as module
        import secrets
        cls.base=module.ROOT/'work'/'v03b-tests'/secrets.token_hex(8);cls.base.mkdir(parents=True)
        cls.runtime=cls.base/'runtime';cls.out=cls.base/'output'
        cls.generation=reproduce(cls.runtime,cls.out)
    def setUp(self):
        self.chunks=services(self.runtime);self.g=copy.deepcopy(self.generation)
        self.resolver=LiveEvidenceResolver(self.chunks,self.g)
        self.query=EvaluationQueryAdapter(self.chunks,self.resolver)
    def test_original_hashes_and_57_chunks(self):
        self.assertEqual(len(self.g['documents']),7);self.assertEqual(self.g['coverage']['actual_chunks'],57)
        self.assertTrue(all(d['original_sha256_match'] and d['normalized_chunk_content_match'] and d['exact_historical_id_replay_match'] for d in self.g['comparison']))
    def test_new_versions_jobs_and_frozen_snapshot(self):
        for d in self.g['documents']:
            c=next(c for c in self.g['comparison'] if c['logical_id']==d['logical_id'])
            self.assertTrue(c['document_id_changed'] and c['version_id_changed'])
            s=d['snapshot'];self.assertEqual(s['chunk_generation'],1);self.assertEqual(s['parse_attempt'],1)
            self.assertTrue(s['parse_job_id'] and s['chunk_job_id'] and s['snapshot_id'])
    def test_real_parser_chunker_replay(self):
        r=verify_frozen(self.g,self.out);self.assertEqual(sum(d['chunks'] for d in r),57)
    def test_tampered_original_replay_fails(self):
        # Alter a copied freeze only; never modify original or shared test corpus.
        with tempfile.TemporaryDirectory() as t:
            d=copy.deepcopy(self.g);d['documents']=d['documents'][:1]
            p=Path(t)/d['documents'][0]['frozen_original'];p.parent.mkdir();p.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError,'hash'):verify_frozen(d,t)
    def test_current_refs_resolve_and_semantics_pending(self):
        n=0
        for q in self.g['queries']:
            for r in q['expected_evidence_refs']:
                x=self.resolver(q['organization_id'],r);self.assertTrue(x['structural_valid']);self.assertEqual(x['semantic_verification'],'NOT_VERIFIED');n+=1
        self.assertEqual(n,48)
    def test_forbidden_refs_are_recorded_but_not_accessible(self):
        for q in self.g['queries']:
            for r in q.get('forbidden_evidence_refs',[]):
                with self.assertRaises(DomainError):self.resolver(q['organization_id'],r)
        self.assertEqual(self.g['coverage']['relinked'],51)
    def test_old_ref_is_not_current(self):
        old=json.loads(HISTORICAL.read_text())['queries'][0]['expected_evidence_refs'][0]
        with self.assertRaises(DomainError):self.resolver('A',old)
    def test_forged_quote_rejected(self):
        r=copy.deepcopy(self.g['queries'][0]['expected_evidence_refs'][0]);r['spans'][0]['quote']='forged'
        with self.assertRaises(DomainError):self.resolver('A',r)
    def test_question_answer_immutability(self):
        h=json.loads(HISTORICAL.read_text());s=json.loads(SOURCE.read_text());self.assertTrue(check_answer_key(s,h))
        h['queries'][0]['expected_answer']='fabricated'
        with self.assertRaisesRegex(ValueError,'mismatch'):check_answer_key(s,h)
    def test_duplicate_gold_question_rejected(self):
        h=json.loads(HISTORICAL.read_text());h['queries'][1]=copy.deepcopy(h['queries'][0])
        with self.assertRaises(ValueError):check_answer_key(json.loads(SOURCE.read_text()),h)
    def test_do_not_overwrite_existing_generation(self):
        with self.assertRaises(ValueError):reproduce(self.runtime,self.out)
    def test_all_7_long_questions_preserved(self):
        long=[q for q in self.g['queries'] if len(q['question'].split())>8];self.assertEqual(len(long),7)
        for q in long:
            r=self.query.search(Principal('r',q['organization_id'],'reader'),q['question'])
            self.assertNotEqual(r['status'],'retrieval_failed');self.assertEqual(r['question'],q['question'])
            self.assertEqual(' '.join(r['windows']).split(),q['question'].split())
            self.assertTrue(all(len(w)<=200 and len(w.split())<=8 for w in r['windows']))
    def test_product_contract_still_rejects_long_question(self):
        q=self.g['queries'][0]
        with self.assertRaises(DomainError):self.chunks.search(Principal('r','A','reader'),q['question'])
    def test_question_windows_character_and_word_bounds(self):
        q=' '.join(['한'*90]*9);w=self.query.windows(q)
        self.assertTrue(all(len(x)<=200 for x in w));self.assertEqual(' '.join(w),q)
        with self.assertRaises(ValueError):self.query.windows('a'*201)
        with self.assertRaises(ValueError):self.query.windows('a '*129)
        with self.assertRaises(ValueError):self.query.windows(' ')
    def test_short_question_not_rewritten(self):
        self.assertEqual(self.query.windows('출장 신청서 자료'),['출장 신청서 자료'])
    def test_retrieval_nohits_not_ai_failure(self):
        r=self.query.search(Principal('r','A','reader'),'UNSEENZXQ')
        self.assertEqual(r['status'],'no_hits');self.assertFalse(r['ai_performance_eligible'])
    def test_retrieval_error_distinct_and_no_leaking_raw_exception(self):
        with patch.object(self.chunks,'search',side_effect=DomainError('stale_evaluation_generation')):
            r=self.query.search(Principal('r','A','reader'),'자료')
        self.assertEqual(r['status'],'retrieval_failed');self.assertEqual(r['results'],[])
    def test_retrieval_foreign_result_fails_closed(self):
        foreign=next(d for d in self.g['documents'] if d['organization_id']=='B')['chunks'][0]
        with patch.object(self.chunks,'search',return_value=[foreign]):r=self.query.search(Principal('r','A','reader'),'자료')
        self.assertEqual(r['status'],'retrieval_failed');self.assertFalse(r['results'])
    def test_reader_search_allowed_worker_denied(self):
        self.assertEqual(self.query.search(Principal('r','A','reader'),'자료')['actual_model_calls'],0)
        for p in (None,Principal('w','A','worker')):
            with self.assertRaises(DomainError):self.query.search(p,'자료')
    def test_no_external_socket_dns_calls(self):
        with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')):
            self.query.search(Principal('r','A','reader'),'자료');verify_frozen(self.g,self.out)
    def test_review_40_rows_no_automatic_human_judgments(self):
        rows,page,csv=review_pack(self.g);self.assertEqual(len(rows),40)
        self.assertTrue(all(r['verdict'] is None and r['reviewer'] is None and r['reviewed_at'] is None for r in rows))
        self.assertIn('reviewer,reviewed_at,verdict,reason',csv)
        self.assertIn('FORBIDDEN_TO_QUESTION_TENANT',page)
    def test_review_html_escapes_document_instructions(self):
        g=copy.deepcopy(self.g);g['queries'][0]['question']='<script>alert(1)</script>'
        _,page,_=review_pack(g);self.assertNotIn('<script>',page);self.assertIn('&lt;script&gt;',page)
    def test_z_stale_generation_and_retirement_fail(self):
        # Use a separate generation so mutation cannot affect shared fixtures or other tests.
        runtime=self.base/'stale-runtime';out=self.base/'stale-output';g=reproduce(runtime,out);c=services(runtime)
        resolver=LiveEvidenceResolver(c,g);d=g['documents'][0];p=Principal('m','A','manager');w=Principal('w','A','worker')
        ref=d['chunks'][0]['evidence'];c.enqueue(p,d['document_id'],d['version_id'],ChunkConfig(max_chars=799,context_chars=0));self.assertEqual(c.execute(w,c.claim(w)),'completed')
        with self.assertRaises(DomainError):resolver('A',ref)
        with c.repo.transaction() as db:db.connection.execute('UPDATE documents SET registered=0 WHERE id=?',(d['document_id'],))
        with self.assertRaises(DomainError):resolver('A',ref)


    def file_score(self,rows,*,labels=None):
        from scripts.validation.score_v03b_predictions import score_files
        pred=self.base/'predictions.json';pred.write_text(json.dumps(rows))
        label_path=None
        if labels is not None:
            label_path=self.base/'labels.json';label_path.write_text(json.dumps(labels))
        return score_files(self.out,pred,labels=label_path)
    def test_file_scorer_empty_results_not_run_40(self):
        r=self.file_score([]);self.assertEqual(r['status_counts'],{'NOT_RUN':40});self.assertEqual(r['human']['pending'],40)
        self.assertIsNone(r['automatic']['steps']['f1']);self.assertFalse(r['provenance']['inference_executed'])
    def test_file_scorer_unknown_duplicate_predictions_rejected(self):
        q=self.g['queries'][0]['id']
        with self.assertRaises(ValueError):self.file_score([{'id':'unknown'}])
        with self.assertRaises(ValueError):self.file_score([{'id':q},{'id':q}])
    def test_file_scorer_malformed_output_not_hidden_as_retrieval_failure(self):
        q=self.g['queries'][0]['id'];r=self.file_score([{'id':q,'unexpected':'forged'}])
        self.assertEqual(r['status_counts'],{'INVALID_OUTPUT':1,'NOT_RUN':39})
    def test_file_scorer_foreign_gold_tenant_is_data_invalid(self):
        labels=[proposed_gold(q) for q in self.g['queries']];labels[0]['organization_id']='B'
        r=self.file_score([],labels=labels);self.assertEqual(r['status_counts'],{'DATA_INVALID':1,'NOT_RUN':39})
    def test_file_scorer_bad_gold_ref_and_duplicate_gold(self):
        labels=[proposed_gold(q) for q in self.g['queries']];labels[0]['labels']['steps'][0]['evidence_refs'][0]['chunk_id']='missing'
        r=self.file_score([],labels=labels);self.assertEqual(r['status_counts']['DATA_INVALID'],1)
        labels[1]=copy.deepcopy(labels[0])
        with self.assertRaises(ValueError):self.file_score([],labels=labels)
    def test_frozen_path_traversal_rejected(self):
        g=copy.deepcopy(self.g);g['documents'][0]['frozen_original']='../../private'
        with self.assertRaises(ValueError):verify_frozen(g,self.out)
    def test_json_duplicate_keys_nonfinite_rejected(self):
        from scripts.validation.score_v03b_predictions import load
        p=self.base/'invalid.json'
        for text in ('{"a":1,"a":2}','{"a":NaN}'):
            p.write_text(text)
            with self.assertRaises(ValueError):load(p)


    def test_duplicate_or_malformed_search_results_are_not_ranked(self):
        item=self.g['documents'][0]['chunks'][0]
        for results in ([item,item],[{'evidence':{}}]):
            with patch.object(self.chunks,'search',return_value=results):r=self.query.search(Principal('r','A','reader'),'자료')
            self.assertEqual(r['status'],'retrieval_failed');self.assertFalse(r['results'])
    def test_new_active_version_invalidates_evidence(self):
        from scripts.validation.build_phase2c2b_goldset import hwpx
        from apps.api.worker import run_once
        runtime=self.base/'version-runtime';out=self.base/'version-output';g=reproduce(runtime,out);c=services(runtime)
        resolver=LiveEvidenceResolver(c,g);d=g['documents'][0];p=Principal('m','A','manager');w=Principal('w','A','worker')
        ref=d['chunks'][0]['evidence']
        meta,_=c.documents.register(p,'new-version.hwpx','application/octet-stream',hwpx(['합성 새 버전']),document_id=d['document_id'])
        self.assertEqual(run_once(c.parsing,w),'completed');c.enqueue(p,d['document_id'],meta['id'],ChunkConfig());self.assertEqual(c.execute(w,c.claim(w)),'completed')
        c.documents.activate(p,d['document_id'],meta['id'])
        with self.assertRaises(DomainError):resolver('A',ref)


    def test_global_xml_namespace_state_cannot_change_frozen_originals(self):
        from xml.etree import ElementTree as ET
        # XML prefix registrations are process-global; the production generator must be isolated.
        with patch.dict(ET._namespace_map):
            ET.register_namespace('evaluation_prefix','http://www.hancom.co.kr/hwpml/2011/paragraph')
            g=reproduce(self.base/'namespace-runtime',self.base/'namespace-output')
        self.assertTrue(all(d['original_sha256_match'] and d['exact_historical_id_replay_match'] for d in g['comparison']))


class EvaluationMetricTests(unittest.TestCase):
    def setUp(self):
        self.ref={'organization_id':'A','token':'valid'}
        self.gold={'id':'q','organization_id':'A','answer_status':'answerable','labels':{'steps':[{'id':'s1','text':'제출한다','evidence_refs':[self.ref]},{'id':'s2','text':'확인한다','evidence_refs':[self.ref]}],
            'relations':[{'source':'s1','target':'s2','kind':'next'}],
            'deadlines':[{'id':'d1','text':'3일','evidence_refs':[self.ref]}],'conditions':[],'forms':[]}}
        self.pred={'id':'q','status':'generated','labels':copy.deepcopy(self.gold['labels']),'claims':[{'id':'c','text':'제출한다','evidence_refs':[self.ref]}],
            'elapsed_seconds':.2,'run_kind':'metric_fixture'}
    def resolver(self,org,ref):
        if org!=ref.get('organization_id') or ref.get('token')!='valid':raise ValueError('invalid')
        return {'structural_valid':True,'evidence':{'spans':[{'role':'primary','quote':'신청자는 제출한다. 담당자는 확인한다. 3일 이내'}]}}
    def score(self):return evaluate_case(self.gold,self.pred,self.resolver)
    def test_precision_recall_f1_math(self):
        x=prf(['a','b'],['a','c','d']);self.assertEqual(x['tp'],1);self.assertAlmostEqual(x['precision'],1/3);self.assertEqual(x['recall'],.5);self.assertEqual(x['f1'],.4)
    def test_empty_denominators_are_null(self):
        self.assertIsNone(prf([],[])['f1']);self.assertEqual(prf(['a'],[])['recall'],0);self.assertIsNone(prf(['a'],[])['precision'])
    def test_perfect_fixture_not_ai_performance(self):
        r=self.score();self.assertEqual(r['automatic']['steps']['f1'],1);self.assertIsNone(r['semantic_accuracy']);self.assertFalse(r['approved_goldset'])
        self.assertFalse(summarize([r])['actual_ai_performance_claimed'])
    def test_missing_and_extra_steps(self):
        self.pred['labels']['steps'][1]['text']='무관한 주장';r=self.score()['automatic']['steps']
        self.assertEqual((r['tp'],r['fp'],r['fn']),(1,1,1))
    def test_reversed_order_not_correct(self):
        self.pred['labels']['relations'][0].update(source='s2',target='s1');r=self.score()['automatic']['order'];self.assertEqual(r['f1'],0)
    def test_branch_rejection_loop_measured_separately(self):
        for kind in ('conditional','return','supplement','repeat'):
            g=copy.deepcopy(self.gold);p=copy.deepcopy(self.pred);g['labels']['relations']=[{'source':'s2','target':'s1','kind':kind}];p['labels']['relations']=copy.deepcopy(g['labels']['relations'])
            r=evaluate_case(g,p,self.resolver);self.assertEqual(r['automatic']['branches']['f1'],1)
    def test_unannotated_is_not_zero_or_pass(self):
        for f in ('relations','deadlines','conditions','forms'):self.gold['labels'][f]=None
        r=self.score()['automatic'];self.assertEqual(r['branches']['status'],'NOT_ANNOTATED');self.assertEqual(r['deadlines']['status'],'NOT_ANNOTATED')
    def test_deadline_condition_form_metrics(self):
        for field in ('deadlines','conditions','forms'):
            self.gold['labels'][field]=[{'id':field,'text':'서식 A' if field=='forms' else field,'evidence_refs':[self.ref]}]
            self.pred['labels'][field]=copy.deepcopy(self.gold['labels'][field])
        r=self.score()['automatic'];self.assertTrue(all(r[f]['f1']==1 for f in ('deadlines','conditions','forms')))
    def test_invalid_foreign_gold_is_data_error(self):
        self.gold['labels']['steps'][0]['evidence_refs'][0]={'organization_id':'B','token':'valid'}
        r=self.score();self.assertEqual(r['status'],'DATA_INVALID');self.assertIsNone(r['automatic'])
    def test_missing_gold_evidence_is_not_ai_failure(self):
        self.gold['labels']['steps'][0]['evidence_refs']=[];self.assertEqual(self.score()['status'],'DATA_INVALID')
    def test_invalid_prediction_evidence_counted(self):
        self.pred['claims'][0]['evidence_refs']=[{'organization_id':'B','token':'invalid'}]
        r=self.score()['automatic'];self.assertLess(r['evidence_structural']['rate'],1);self.assertEqual(r['unsupported_claim_proxy']['rate'],1)
    def test_unsupported_claim_not_semantic_certification(self):
        self.pred['claims'][0]['text']='무조건 99일 이내 승인';r=self.score()
        self.assertEqual(r['automatic']['unsupported_claim_proxy']['rate'],1);self.assertIsNone(r['semantic_accuracy'])
    def test_retrieval_failure_generation_failure_not_scored(self):
        for status in ('retrieval_failed','generation_failed','invalid_output'):
            self.pred['status']=status;r=self.score();self.assertIsNone(r['automatic']);self.assertTrue(r['excluded_from_ai_metrics'])
    def test_duplicate_ids_and_invalid_relation_rejected(self):
        for mutation in ('duplicate','edge'):
            p=copy.deepcopy(self.pred)
            if mutation=='duplicate':p['labels']['steps'][1]['id']='s1'
            else:p['labels']['relations'][0]['source']='unknown'
            with self.assertRaises(ValidationError):evaluate_case(self.gold,p,self.resolver)
    def test_extra_model_approval_field_rejected(self):
        self.pred['semantic_verification']='VERIFIED'
        with self.assertRaises(ValidationError):self.score()
    def test_nan_boolean_usage_and_unproven_cost_rejected(self):
        for field,value in [('elapsed_seconds',float('nan')),('input_tokens',True),('estimated_cost_micro',100)]:
            p=copy.deepcopy(self.pred);p[field]=value
            with self.assertRaises(ValidationError):Prediction.model_validate(p)
    def test_fake_usage_distinct_from_measured_provider_usage(self):
        self.pred.update(token_basis='FAKE_USAGE',input_tokens=5,output_tokens=7,estimated_cost_micro=4,pricing={'input_rate_micro':100000,'output_rate_micro':500000,'price_version':'simulation-only'})
        self.assertEqual(self.score()['measurement']['token_basis'],'FAKE_USAGE')
    def test_human_reviews_empty_not_approved(self):
        r=summarize([self.score()]);self.assertEqual(r['human']['pending'],1);self.assertIsNone(r['human']['exact_accuracy']);self.assertFalse(r['goldset_approved'])
    def test_human_review_labels_and_reasons_required(self):
        for verdict in ['정확','부분정확','오답','판정불가']:
            h=HumanReview(query_id='q',reviewer='independent-reviewer',reviewed_at='2026-10-18T10:00:00+00:00',verdict=verdict,reason='test record only')
            r=summarize([self.score()],[h]);self.assertEqual(r['human']['submitted_reviews'],1)
        with self.assertRaises(ValidationError):HumanReview(query_id='q',reviewer=' ',reviewed_at='2026-10-18',verdict='정확',reason='')
    def test_human_scores_separate_and_partial_not_full_credit(self):
        r=self.score();h={'query_id':'q','reviewer':'test-only reviewer','reviewed_at':'2026-10-18T10:00:00+00:00','verdict':'부분정확','reason':'test record only','supported_claims':0,'unsupported_claims':1}
        x=summarize([r],[h]);self.assertEqual(x['human']['exact_accuracy'],0);self.assertEqual(x['human']['unsupported_claim_rate'],1);self.assertEqual(r['automatic']['steps']['f1'],1)
    def test_unknown_duplicate_review_and_case_rejected(self):
        r=self.score();h={'query_id':'x','reviewer':'r','reviewed_at':'2026-10-18T10:00:00+00:00','verdict':'정확','reason':'test only'}
        with self.assertRaises(ValueError):summarize([r],[h])
        with self.assertRaises(ValueError):summarize([r,r])
    def test_missing_claim_citation_fails_proxy(self):
        self.pred['claims'][0]['evidence_refs']=[];r=self.score()['automatic'];self.assertEqual(r['unsupported_claim_proxy']['rate'],1)

    def test_aggregate_micro_counts_and_unknown_coverage(self):
        x=summarize([self.score()]);self.assertEqual(x['automatic']['steps']['tp'],2);self.assertEqual(x['automatic']['order']['exact_set_accuracy'],1)
    def test_same_item_in_claim_and_step_does_not_double_unsupported(self):
        self.pred['claims']=[copy.deepcopy(self.pred['labels']['steps'][0])];self.pred['claims'][0]['text']='지원 없음'
        self.pred['labels']['steps'][0]=copy.deepcopy(self.pred['claims'][0]);r=self.score()
        self.assertEqual(r['automatic']['unsupported_claim_proxy']['unsupported'],1)

    def test_cost_estimate_integer_rounding_and_rate_version(self):
        from scripts.validation.evaluation_metrics import Pricing
        p=Pricing(input_rate_micro=1,output_rate_micro=1,price_version='test-only')
        self.assertEqual(p.estimate(1,0),1);self.assertEqual(p.estimate(0,0),0)
        with self.assertRaises(ValidationError):Pricing(input_rate_micro=True,output_rate_micro=0,price_version='x')
    def test_unverified_estimated_cost_rejected(self):
        p=copy.deepcopy(self.pred);p.update(token_basis='FAKE_USAGE',input_tokens=1,output_tokens=1,estimated_cost_micro=999,pricing={'input_rate_micro':1,'output_rate_micro':1,'price_version':'test-only'})
        with self.assertRaises(ValidationError):Prediction.model_validate(p)
