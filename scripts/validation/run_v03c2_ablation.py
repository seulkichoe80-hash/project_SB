"""Run fixed-protocol local retrieval ablations; all model/answer generation absent."""
import argparse
import copy
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from apps.api.models import Principal
from apps.api.errors import DomainError
from scripts.validation.evaluation_fixtures import services,sha_file,verify_frozen,EvaluationQueryAdapter,LiveEvidenceResolver
from scripts.validation.score_v03b_predictions import load
from scripts.validation.retrieval_ablation import AblationSearch,METHODS,key,query_metrics,latency
from apps.api.chunking import digest


def run(generation_dir,output_dir,*,data_dir=None,repeats=3):
    if type(repeats) is not int or repeats!=3:raise ValueError('preregistered_three_repeats_required')
    started=time.perf_counter();directory=Path(generation_dir).resolve();out=Path(output_dir).resolve()
    if out.exists():raise ValueError('new_output_path_required')
    plan_path=ROOT/'outputs/v03c2/PREREGISTRATION.json';plan=load(plan_path)
    g=load(directory/'generation.json');runtime=Path(data_dir or g['data_dir'])
    if not (runtime/'metadata.sqlite3').is_file():raise ValueError('existing_runtime_required')
    if len(g['documents'])!=7 or sum(len(d['chunks']) for d in g['documents'])!=57 or len(g['queries'])!=40:raise ValueError('frozen_dataset_size_mismatch')
    verify_frozen(g,directory);chunks=services(runtime);resolver=LiveEvidenceResolver(chunks,g)
    for q in g['queries']:
        for ref in q['expected_evidence_refs']:resolver(q['organization_id'],ref)
    search=AblationSearch(chunks,g);records={m:[] for m in METHODS};timings={m:{'ranking':[],'end_to_end':[],'negative_ranking':[],'negative_end_to_end':[]} for m in METHODS}
    fingerprints={m:[] for m in METHODS};baseline_equivalent=True
    out.mkdir(parents=True)
    try:
        old=EvaluationQueryAdapter(chunks,resolver)
        for repeat in range(repeats):
            # All 57 citation proofs were primed during index build for every method equally.
            # Fresh pre/post snapshots still reparse sources for each request.
            by_method={m:[] for m in METHODS}
            # Rotate order deterministically to reduce systematic first-method warm-cache advantage.
            order=METHODS[repeat:]+METHODS[:repeat]
            for q in g['queries']:
                principal=Principal('ablation-reader',q['organization_id'],'reader')
                expected={key({'evidence':r}) for r in q['expected_evidence_refs']};forbidden={key({'evidence':r}) for r in q.get('forbidden_evidence_refs',[])}
                for m in order:
                    if m=='D' and not search.fts_supported:continue
                    result=search.search(principal,q['question'],m);ranked=[key(x['chunk']) for x in result['results']]
                    if any(x['chunk']['evidence']['organization_id']!=q['organization_id'] for x in result['results']) or forbidden&set(ranked):raise DomainError('ablation_scope_leak',422)
                    if repeat==0 and m=='A':
                        reference=old.search(principal,q['question'],20)
                        if ranked[:20]!=[key(i) for i in reference['results']]:raise ValueError('baseline_rankings_changed')
                    row={'id':q['id'],'organization_id':q['organization_id'],'question':q['question'],
                        'normalized_question':result['normalized_question'],'tokens':result['tokens'],
                        'ranked':[{'document_id':k[0],'version_id':k[1],'chunk_id':k[2],
                            'score':x['score'],'score_kind':x['score_kind']} for k,x in zip(ranked,result['results'])],
                        'answer_status':q['answer_status'],'response_status':result['response_status'],'answer_generated':False,
                        'tenant_violations':0,'forbidden_evidence_hits':0,'expected_count':len(expected),
                        'metrics':query_metrics(expected,ranked) if expected else None,
                        'missing_expected_at_10':[list(k) for k in sorted(expected-set(ranked[:10]))],
                        'semantic_accuracy':None,'goldset_status':'PROVISIONAL'}
                    by_method[m].append(row)
                    prefix='' if expected else 'negative_'
                    timings[m][prefix+'ranking'].append(result['ranking_seconds']);timings[m][prefix+'end_to_end'].append(result['end_to_end_seconds'])
            for m in METHODS:
                fingerprints[m].append(digest(by_method[m]))
                if repeat==0:records[m]=by_method[m]
        reports={}
        for m in METHODS:
            if m=='D' and not search.fts_supported:
                reports[m]={'status':'BLOCKED','reason':'fts5_unavailable','metrics':None};continue
            if len(set(fingerprints[m]))!=1:raise ValueError('nonreproducible_rankings_or_scores')
            positive=[r for r in records[m] if r['metrics'] is not None];negative=[r for r in records[m] if r['metrics'] is None]
            if len(positive)!=36 or len(negative)!=4:raise ValueError('evaluation_denominator_changed')
            metrics={k:sum(r['metrics'][k] for r in positive)/36 for k in ['hit_at_5','hit_at_10','recall_at_5','recall_at_10','mrr','mrr_at_10']}
            metrics['no_results']=sum(r['metrics']['no_results'] for r in positive)
            reports[m]={'status':'PASS','positive_queries':36,'abstain_queries':4,'metrics':metrics,
                'latency':{k:latency(v) for k,v in timings[m].items()},'repeat_fingerprints':fingerprints[m],
                'deterministic_rankings_and_scores':True,'cases':records[m],
                'negative_summary':{'queries_with_results':sum(bool(r['ranked']) for r in negative),
                    'tenant_violations':0,'forbidden_evidence_hits':0,'answers_generated':0,
                    'policy':'Hits are candidate context, not an answer or a semantic pass; no generation for every query.'}}
        for org,packet in search.packets.items():search.builder.validate(org,packet)
        eligible=[m for m in METHODS if reports[m]['status']=='PASS']
        # Safe research proposal only. Timing tie-break is not used to claim semantic validity.
        preferred=max(eligible,key=lambda m:(reports[m]['metrics']['recall_at_10'],reports[m]['metrics']['mrr'],-reports[m]['latency']['ranking']['mean_ms']))
        output={'scope':'offline synthetic provisional retrieval experiment; no LLM accuracy claim',
            'protocol':plan,'protocol_sha256':sha_file(plan_path),'source_generation_sha256':sha_file(directory/'generation.json'),
            'generation_id':g['generation_id'],'questions_sha256':digest(g['queries']),
            'sqlite_version':__import__('sqlite3').sqlite_version,'fts5_supported':search.fts_supported,
            'index_build_seconds':search.index_build_seconds,'repeats':repeats,'method_order_per_repeat':[list(METHODS[i:]+METHODS[:i]) for i in range(3)],
            'A_equivalent_to_existing_adapter':baseline_equivalent,'methods':reports,
            'research_candidate':preferred,'product_search_replaced':False,'goldset_status':'PROVISIONAL','human_review_pending':40,
            'semantic_accuracy':None,'actual_provider_calls':0,'actual_spend_usd':0,'seconds':time.perf_counter()-started}
        (out/'results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
        return output
    finally:search.close()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--generation-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--data-dir',type=Path)
    a=p.parse_args();r=run(a.generation_dir,a.output_dir,data_dir=a.data_dir)
    print(json.dumps({'methods':{m:v['metrics'] for m,v in r['methods'].items()},'candidate':r['research_candidate'],'seconds':r['seconds']},ensure_ascii=False,indent=2))
