"""Diagnose all 40 fixed questions; run answer-independent Fake extraction separately."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.validation.evaluation_fixtures import services,sha_file,verify_frozen
from scripts.validation.score_v03b_predictions import load
from scripts.validation.retrieval_diagnostics import diagnose_all
from scripts.validation.fixed_context_evaluation import run_fixed_context
from scripts.validation.evaluation_metrics import HumanReview


PRIORITY=[('travel-a-01','기본 다중 단계와 여러 근거의 연결'),('travel-b-01','동일 업무명의 기관별 권한·내용 차이'),
 ('leave-a-01','다른 업무의 단계/역할 대조'),('purchase-a-01','구매 단계와 서류 관계'),
 ('meeting-a-01','문서 단위 holdout 후보의 독립 검토'),('form-a-01','서식명·사용 목적·단계 관계'),
 ('travel-a-04','조건·보완·보류와 임의 직선화 방지'),('safety-01','원문 없는 정확한 기한 단정 방지'),
 ('safety-03','타기관 근거 접근 차단'),('safety-04','타기관/옛 자료 공개 지시 거부')]


def human_plan(generation,review_dir):
    rows=load(Path(review_dir)/'review-rows.json');by_id={q['id']:q for q in generation['queries']}
    if len(rows)!=40 or {r['query_id'] for r in rows}!=set(by_id):raise ValueError('review_question_coverage_mismatch')
    # Read-only progress: do not assign human judgments or turn generated state into approval.
    completed=[];invalid_reviews=[]
    for r in rows:
        if all(r.get(k) for k in ('reviewer','reviewed_at','verdict','reason')):
            try:HumanReview.model_validate({k:r[k] for k in ('query_id','reviewer','reviewed_at','verdict','reason')})
            except ValueError:invalid_reviews.append(r['query_id'])
            else:completed.append(r)
    pending=[r['query_id'] for r in rows if r not in completed]
    return {'source_review_dir':str(review_dir),'source_sha256':sha_file(Path(review_dir)/'review-rows.json'),
        'invalid_review_ids':invalid_reviews,'completed':len(completed),'total':40,'progress':len(completed)/40,'pending_ids':pending,
        'judgments_generated':0,'goldset_status':'PROVISIONAL','selection_rule':'6 source manuals + conditional supplementation + unsupported deadline + 2 tenant safety cases; not selected by model scores',
        'priority_10':[{'order':i,'id':q,'reason':why,'review_link':str(Path(review_dir)/'review.html')+'#'+q,
            'evidence_locations':[{'version_id':r['version_id'],'chunk_id':r['chunk_id'],
                'selectors':[a['selector'] for a in r['source_anchor']]} for r in by_id[q]['expected_evidence_refs']],
            'verdict':None,'reviewer':None,'reviewed_at':None,'reason_for_verdict':None} for i,(q,why) in enumerate(PRIORITY,1)],
        'remaining_priority':'safety-02 금액/법령 보류, 나머지30문항, 그래프/기한/조건/서식 주석과 PDF 시각 확인; 실제 인간 검토 후 결정'}


def run(generation_dir,output_dir,*,data_dir=None):
    started=time.perf_counter();generation_dir=Path(generation_dir).resolve();out=Path(output_dir).resolve()
    if out.exists():raise ValueError('new_output_path_required')
    g=load(generation_dir/'generation.json');runtime=Path(data_dir or g['data_dir'])
    if not (runtime/'metadata.sqlite3').is_file():raise ValueError('existing_evaluation_runtime_required')
    verify_frozen(g,generation_dir)
    out.mkdir(parents=True);chunks=services(runtime)
    diag=diagnose_all(chunks,g)
    (out/'diagnostics.json').write_text(json.dumps(diag,ensure_ascii=False,indent=2)+'\n')
    fixed=run_fixed_context(chunks,g)
    (out/'fixed-context.json').write_text(json.dumps(fixed,ensure_ascii=False,indent=2)+'\n')
    plan=human_plan(g,generation_dir)
    (out/'human-review-plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    summary={'status':'PASS' if len(diag['cases'])==40 and not diag['counts']['UNKNOWN'] else 'NEEDS_REVIEW',
        'source_generation_id':g['generation_id'],'source_generation_sha256':sha_file(generation_dir/'generation.json'),
        'diagnostic_counts':diag['counts'],'fixed_context_questions':fixed['question_count'],
        'fixed_context_chunks':{k:len(v['chunks']) for k,v in fixed['context_packets'].items()},
        'fake_document_invocations':fixed['fake_document_invocations'],'human_review_completed':plan['completed'],
        'human_review_pending':len(plan['pending_ids']),'goldset_status':'PROVISIONAL','semantic_accuracy_pass':False,
        'actual_provider_calls':0,'actual_spend_usd':0,'seconds':time.perf_counter()-started}
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--generation-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--data-dir',type=Path)
    a=p.parse_args();print(json.dumps(run(a.generation_dir,a.output_dir,data_dir=a.data_dir),ensure_ascii=False,indent=2))
