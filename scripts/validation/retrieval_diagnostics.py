"""Read-only diagnostics against the real chunk search SQL. No search algorithm changes."""
import json
import time
from apps.api.chunk_service import SQLiteKeywordSearch
from apps.api.errors import DomainError
from apps.api.models import Principal
from scripts.validation.evaluation_fixtures import EvaluationQueryAdapter,LiveEvidenceResolver


JOIN='''FROM chunk_items i JOIN chunk_jobs j ON j.id=i.job_id
 JOIN versions v ON v.id=j.version_id JOIN documents d ON d.id=v.document_id'''
STAGES=[('institution','d.institution_id=?'),('registered','d.registered=1'),
 ('active_version','d.active_version_id=v.id'),
 ('current_chunk_generation','EXISTS(SELECT 1 FROM chunk_current c WHERE c.version_id=v.id AND c.job_id=j.id)'),
 ('chunk_completed',"j.state='completed'"),
 ('parse_attempt',"EXISTS(SELECT 1 FROM parse_jobs p WHERE p.id=j.parse_job_id AND p.attempt=j.parse_attempt AND p.state='completed')")]


class TraceSearch:
    def __init__(self,delegate):self.delegate=delegate;self.windows=[]
    def search(self,db,org,terms,limit):
        sql=[];db.connection.set_trace_callback(lambda statement:sql.append(statement))
        try:items=self.delegate.search(db,org,terms,limit)
        finally:db.connection.set_trace_callback(None)
        self.windows.append({'terms':list(terms),'limit':limit,'executed_sql':sql,
            'returned_chunk_ids':[x['chunk_id'] for x in items],
            'sql_score':None,'ordering':'document_created_at,version_id,chunk_order; no lexical relevance score'})
        return items


def diagnose_question(chunks,generation,question,*,top_k=10):
    started=time.perf_counter();q=question;org=q['organization_id'];principal=Principal('diagnostic-reader',org,'reader')
    resolver=LiveEvidenceResolver(chunks,generation)
    result={'id':q['id'],'question':q['question'],'organization_id':org,'answer_status':q['answer_status'],
        'generation_id':generation['generation_id'],'classification':'UNKNOWN','confirmed':[],'uncertain':[],
        'expected_ref_count':len(q['expected_evidence_refs']),'top_k':top_k,
        'matching_rule':'exact (document_id,version_id,chunk_id), unique required citations; text is not the ID key',
        'actual_model_calls':0,'semantic_verification':'NOT_VERIFIED'}
    def key(ref):return (ref['document_id'],ref['version_id'],ref['chunk_id'])
    expected={key(r) for r in q['expected_evidence_refs']}
    try:
        with chunks.repo.transaction() as db:
            total=db.connection.execute('SELECT COUNT(*) FROM chunk_items').fetchone()[0]
            result['stored_chunk_rows']=total;result['manifest_chunk_count']=sum(len(d['chunks']) for d in generation['documents'])
            counts={};filters=[]
            for name,condition in STAGES:
                filters.append(condition);counts[name]=db.connection.execute('SELECT COUNT(*) '+JOIN+' WHERE '+' AND '.join(filters),(org,)).fetchone()[0]
            result['filter_counts']=counts
            eligible=[dict(r) for r in db.connection.execute('SELECT i.chunk_id,i.payload,i.search_text,j.id AS chunk_job_id,j.generation,j.version_id,v.document_id '+JOIN+' WHERE '+' AND '.join(filters),(org,))]
            result['indexed_rows']=[{k:r[k] for k in ('chunk_id','document_id','version_id','chunk_job_id','generation')} for r in eligible]
            keys={key(r) for r in eligible};result['expected_present_in_eligible_index']=[list(x) for x in sorted(expected&keys)]
            result['expected_missing_from_eligible_index']=[list(x) for x in sorted(expected-keys)]
            windows=EvaluationQueryAdapter.windows(q['question']);probes=[];raw_candidates=set()
            for window in windows:
                terms=window.casefold().split();term_probes=[]
                for term in terms:
                    matches=db.chunks.search(org,[term],20000)
                    term_probes.append({'term':term,'eligible_sql_hits':len(matches),
                        'expected_hits':len(expected&{key(i['evidence']) for i in matches})})
                raw=db.chunks.search(org,terms,20000);limited=db.chunks.search(org,terms,50)
                ids={key(i['evidence']) for i in raw};raw_candidates|=ids
                probes.append({'window':window,'tokens':terms,'term_probes':term_probes,
                    'raw_sql_count_before_limit':len(raw),'sql_count_after_limit_50':len(limited),
                    'raw_candidate_ids':[list(i) for i in sorted(ids)],'expected_hits_before_limit':len(ids&expected),
                    'expected_hits_after_limit':len(expected&{key(i['evidence']) for i in limited}),
                    'sql_score':None,'all_terms_AND':True})
            result['window_probes']=probes;result['expected_raw_candidates']=[list(x) for x in sorted(expected&raw_candidates)]
        # Run the unchanged service/adapter with a wrapper recording its actual executed SQL.
        original=chunks.search_adapter;trace=TraceSearch(original);chunks.search_adapter=trace
        try:r=EvaluationQueryAdapter(chunks,resolver).search(principal,q['question'],top_k)
        finally:chunks.search_adapter=original
        result['actual_search_trace']=trace.windows;result['retrieval_status']=r['status']
        final={key(x['evidence']) for x in r['results']};result['top_k_chunk_ids']=[list(x) for x in sorted(final)]
        rrf={}
        for window in trace.windows:
            for rank,chunk_id in enumerate(window['returned_chunk_ids'],1):rrf[chunk_id]=rrf.get(chunk_id,0)+1/(60+rank)
        result['top_k_rrf_scores']=[{'chunk_id':item['chunk_id'],'rrf_score':rrf.get(item['chunk_id'])} for item in r['results']]
        result['expected_hits_at_k']=len(expected&final)
        result['recall_at_k']=len(expected&final)/len(expected) if expected else None
        result['top_k_loss']=bool(expected&raw_candidates-final)
        invalid=[]
        for ref in q['expected_evidence_refs']:
            try:resolver(org,ref)
            except (DomainError,ValueError):invalid.append(ref['chunk_id'])
        result['invalid_expected_refs']=invalid
        manifest_org=[d for d in generation['documents'] if d['organization_id']==org]
        expected_rows=sum(len(d['chunks']) for d in manifest_org)
        result['expected_tenant_chunks']=expected_rows
        if total==0:
            result.update(classification='DATA',confirmed=['empty_chunk_index'])
        elif expected_rows and counts['parse_attempt']!=expected_rows:
            result.update(classification='SCOPE',confirmed=['eligible_scope_count_differs_from_frozen_generation'])
        elif invalid or expected-keys:
            result.update(classification='EVALUATION',confirmed=['gold_ref_missing_or_not_current'])
        elif q['answer_status']=='abstain' and not expected:
            result.update(classification='EVALUATION',confirmed=['expected_abstention_is_not_a_positive_retrieval_miss'])
        elif all(any(t['eligible_sql_hits']==0 for t in p['term_probes']) for p in probes):
            result.update(classification='TOKENIZATION',confirmed=['every_window_contains_absent_literal_token','AND_search_eliminates_all_candidates'])
            result['uncertain']=['Relative contribution of Korean morphology, punctuation, paraphrase and source wording is not separately proven.']
        elif not raw_candidates:
            result.update(classification='RETRIEVAL',confirmed=['tokens_exist_but_do_not_cooccur_in_one_indexed_chunk'])
        elif expected and not expected&final:
            result.update(classification='RETRIEVAL',confirmed=['expected_chunk_not_in_final_top_k'])
        elif expected<=final:
            result.update(classification='EVALUATION',confirmed=['retrieval_succeeded_not_a_current_miss'])
        else:result['uncertain']=['insufficient_evidence_for_unique_cause']
        result['secondary_findings']={'no_token_hits':[t['term'] for p in probes for t in p['term_probes'] if not t['eligible_sql_hits']],
            'expected_abstention':q['answer_status']=='abstain','index_exists':total>0,
            'scope_matches_frozen_count':counts['parse_attempt']==expected_rows,
            'top_k_not_causal_when_sql_empty':not raw_candidates}
    except (DomainError,ValueError) as error:
        result['diagnostic_error_code']=error.code if isinstance(error,DomainError) else 'invalid_evaluation_query'
        result['classification']='UNKNOWN';result['uncertain'].append('diagnosis_did_not_complete')
    result['seconds']=time.perf_counter()-started
    return result


def diagnose_all(chunks,generation):
    rows=[diagnose_question(chunks,generation,q) for q in generation['queries']]
    return {'scope':'synthetic local read-only search diagnostics; no algorithm or gold changes','cases':rows,
        'counts':{k:sum(r['classification']==k for r in rows) for k in ['DATA','SCOPE','TOKENIZATION','RETRIEVAL','EVALUATION','UNKNOWN']},
        'actual_provider_calls':0,'actual_spend_usd':0}
