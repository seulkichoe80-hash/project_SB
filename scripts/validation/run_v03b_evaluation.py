"""Offline fixture reproduction/review pack. No inference or external network code."""
import argparse
import csv
import html
import io
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.validation.evaluation_fixtures import reproduce,verify_frozen,services,LiveEvidenceResolver,EvaluationQueryAdapter,sha_file
from scripts.validation.evaluation_metrics import proposed_gold,Prediction,evaluate_case,summarize
from apps.api.models import Principal


def write_json(path,data):path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def review_pack(generation):
    """All verdict fields remain empty. Source and answer key are explicit separate review material."""
    rows=[];sections=[];documents={d['version_id']:d for d in generation['documents']}
    for q in generation['queries']:
        references=q.get('expected_evidence_refs',[])+q.get('forbidden_evidence_refs',[])
        quotes=[]
        for ref in references:
            d=documents[ref['version_id']]
            quotes.append({'organization_id':d['organization_id'],'document_id':d['document_id'],'version_id':d['version_id'],
                'original':d['frozen_original'],'sha256':d['sha256'],'chunk_id':ref['chunk_id'],
                'scope':'expected' if ref in q.get('expected_evidence_refs',[]) else 'FORBIDDEN_TO_QUESTION_TENANT',
                'spans':ref['spans']})
        rows.append({'query_id':q['id'],'organization_id':q['organization_id'],'question':q['question'],
            'expected_answer':q['expected_answer'],'source_evidence':quotes,
            'proposed_steps':q.get('expected_procedure',[]),'abstain_if':q.get('abstain_if',[]),
            'reviewer':None,'reviewed_at':None,'verdict':None,'reason':None,'status':'PENDING_INDEPENDENT_REVIEW'})
        source='\n'.join(f"{r['scope']} | {r['organization_id']} | {r['original']} | version={r['version_id']} | SHA256={r['sha256']}\n"+
            '\n'.join(s['source_anchor']['selector']+' '+s['quote'] for s in r['spans']) for r in quotes)
        review_documents=[d for d in generation['documents'] if d['version_id'] in {r['version_id'] for r in quotes}] or [d for d in generation['documents'] if d['organization_id']==q['organization_id']]
        full_text=''.join('<details><summary>'+html.escape(d['logical_id'])+' 전체 구조화 원문</summary><a href="'+html.escape(d['frozen_original'],quote=True)+'" download>합성 원본 파일</a><pre>'+html.escape('\n'.join(b['source_anchor']['selector']+' | '+b['text'] for b in d['snapshot']['source_blocks']))+'</pre></details>' for d in review_documents)
        sections.append('<section id="'+html.escape(q['id'],quote=True)+'"><h2>'+html.escape(q['id'])+'</h2><p>'+html.escape(q['question'])+
            '</p><h3>기존 정답 초안 — 미승인</h3><p>'+html.escape(q['expected_answer'])+'</p><h3>원문·출처</h3><pre>'+html.escape(source or '원문에 정답 근거 없음: 보류 기준을 독립 검토해야 함')+
            '</pre>'+full_text+'<h3>판정</h3><p>미검토 · 정확 / 부분정확 / 오답 / 판정불가</p><p>review-rows.json 또는 review-sheet.csv의 별도 사본에 검토자·시간대 포함 검토일·판정 이유를 기록하세요. 이 화면은 승인을 저장하지 않습니다.</p></section>')
    page='<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>40문항 독립 인간 검토 대기표</title><style>body{font:18px/1.6 sans-serif;max-width:72rem;margin:auto;padding:1rem;color:#172b4d}section{border-top:2px solid #64748b;margin-top:2rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}a{color:#143e8f}</style><h1>합성 평가자료 독립 인간 검토</h1><p>40문항 모두 미검토. 자동 점수는 인간 승인이나 실제 AI 성능이 아닙니다. 타기관 금지 근거는 오프라인 평가 담당자 검토용이며 질의 사용자에게 반환할 자료가 아닙니다.</p><nav>'+ ' · '.join('<a href="#'+html.escape(q['id'])+'">'+html.escape(q['id'])+'</a>' for q in generation['queries'])+'</nav>'+''.join(sections)+'</html>'
    stream=io.StringIO();writer=csv.writer(stream);writer.writerow(['query_id','organization_id','question','expected_answer','reviewer','reviewed_at','verdict','reason','review_location'])
    for r in rows:writer.writerow([r['query_id'],r['organization_id'],r['question'],r['expected_answer'],'','','','','review.html#'+r['query_id']])
    return rows,page,stream.getvalue()


def run(data_dir,output_dir):
    start=time.perf_counter();out=Path(output_dir).resolve();generation=reproduce(data_dir,out)
    write_json(out/'replay-verification.json',verify_frozen(generation,out))
    chunks=services(data_dir);resolver=LiveEvidenceResolver(chunks,generation);query=EvaluationQueryAdapter(chunks,resolver)
    retrieval=[];gold=[];calibration=[]
    for q in generation['queries']:
        r=query.search(Principal('evaluation-reader',q['organization_id'],'reader'),q['question']);r['id']=q['id'];retrieval.append(r)
        g=proposed_gold(q);gold.append(g)
        # Metric arithmetic calibration only: copy proposed labels, never present this as AI output.
        p=Prediction.model_validate({'id':q['id'],'status':'generated','labels':g['labels'],'claims':[],
            'elapsed_seconds':0.0,'run_kind':'metric_fixture'})
        calibration.append(evaluate_case(g,p,resolver))
    write_json(out/'retrieval.json',{'scope':'local keyword window retrieval only; no AI predictions','cases':retrieval,
        'over_8_terms':[q['id'] for q in generation['queries'] if len(q['question'].split())>8],
        'counts':{s:sum(r['status']==s for r in retrieval) for s in ['retrieved','no_hits','retrieval_failed']},'actual_model_calls':0})
    write_json(out/'proposed-labels.json',gold)
    write_json(out/'predictions-empty.json',[])
    write_json(out/'metric-calibration.json',summarize(calibration))
    rows,page,csv_text=review_pack(generation);write_json(out/'review-rows.json',rows)
    (out/'review.html').write_text(page,encoding='utf-8');(out/'review-sheet.csv').write_text(csv_text,encoding='utf-8')
    # Preserve full original text as frozen parser output alongside each question's linked excerpt.
    write_json(out/'parsed-originals.json',[{'logical_id':d['logical_id'],'organization_id':d['organization_id'],
        'document_id':d['document_id'],'version_id':d['version_id'],'sha256':d['sha256'],'source_blocks':d['snapshot']['source_blocks']} for d in generation['documents']])
    summary={'status':'PASS','scope':'fixture reproduction and metric arithmetic only; AI performance NOT_RUN',
        'documents':len(generation['documents']),'chunks':generation['coverage']['actual_chunks'],'questions':len(generation['queries']),
        'all_original_sha256_match':all(d['original_sha256_match'] for d in generation['comparison']),
        'all_exact_historical_replays_match':all(d['exact_historical_id_replay_match'] for d in generation['comparison']),
        'all_normalized_chunks_match':all(d['normalized_chunk_content_match'] for d in generation['comparison']),
        'references':generation['coverage'],'human_review_pending':len(rows),'actual_model_calls':0,'actual_spend_usd':0,
        'seconds':time.perf_counter()-start}
    if not summary['all_original_sha256_match'] or not summary['all_normalized_chunks_match']:
        summary['status']='NEEDS_REVIEW'
    write_json(out/'summary.json',summary)
    write_json(out/'artifact-hashes.json',{p.relative_to(out).as_posix():sha_file(p) for p in out.rglob('*') if p.is_file()})
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();print(json.dumps(run(args.data_dir,args.output_dir),ensure_ascii=False,indent=2))
