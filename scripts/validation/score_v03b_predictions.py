"""Score an offline prediction file; no inference, subprocess, SDK or network."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from pydantic import ValidationError
from scripts.validation.evaluation_fixtures import services,LiveEvidenceResolver,verify_frozen,sha_file
from scripts.validation.evaluation_metrics import proposed_gold,evaluate_case,summarize,GoldCase,Prediction,invalid_gold_items


def load(path):
    p=Path(path)
    if p.stat().st_size>64*1024*1024:raise ValueError('evaluation_file_limit')
    def unique(pairs):
        x={}
        for k,v in pairs:
            if k in x:raise ValueError('duplicate_json_key')
            x[k]=v
        return x
    def bad(_):raise ValueError('invalid_json_number')
    return json.loads(p.read_text(encoding='utf-8'),object_pairs_hook=unique,parse_constant=bad)


def score_files(generation_dir,predictions,*,data_dir=None,labels=None,human_reviews=None):
    directory=Path(generation_dir).resolve();g=load(directory/'generation.json')
    verify_frozen(g,directory)
    resolver=LiveEvidenceResolver(services(data_dir or g['data_dir']),g)
    rows=load(predictions)
    if not isinstance(rows,list) or len(rows)>40:raise ValueError('prediction_count_limit')
    query_ids={q['id'] for q in g['queries']};seen=set();by_id={}
    for row in rows:
        if not isinstance(row,dict) or row.get('id') not in query_ids or row['id'] in seen:raise ValueError('unknown_or_duplicate_prediction')
        seen.add(row['id']);by_id[row['id']]=row
    gold_rows=load(labels) if labels else [proposed_gold(q) for q in g['queries']]
    if not isinstance(gold_rows,list) or len(gold_rows)!=40 or {q['id'] for q in gold_rows}!=query_ids:raise ValueError('gold_case_coverage')
    if len({q['id'] for q in gold_rows})!=40:raise ValueError('duplicate_gold_case')
    question_org={q['id']:q['organization_id'] for q in g['queries']};records=[]
    for raw in gold_rows:
        key=raw['id']
        try:
            gold=GoldCase.model_validate(raw)
            if gold.organization_id!=question_org[key]:raise ValueError('gold_tenant_changed')
        except (ValidationError,ValueError):
            records.append({'id':key,'status':'DATA_INVALID','automatic':None,'human':None});continue
        invalid=invalid_gold_items(gold,resolver)
        if invalid:
            records.append({'id':key,'status':'DATA_INVALID','automatic':None,'human':None,'invalid_gold_items':invalid});continue
        if key not in by_id:
            records.append({'id':key,'status':'NOT_RUN','automatic':None,'human':None});continue
        try:p=Prediction.model_validate(by_id[key])
        except ValidationError:
            records.append({'id':key,'status':'INVALID_OUTPUT','automatic':None,'human':None});continue
        records.append(evaluate_case(gold,p,resolver))
    result=summarize(records,load(human_reviews) if human_reviews else ())
    result['provenance']={'generation_id':g['generation_id'],'generation_sha256':sha_file(directory/'generation.json'),
        'predictions_sha256':sha_file(predictions),'labels_sha256':sha_file(labels) if labels else None,
        'human_reviews_sha256':sha_file(human_reviews) if human_reviews else None,
        'external_provider_calls_by_scorer':0,'inference_executed':False}
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--generation-dir',type=Path,required=True);p.add_argument('--predictions',type=Path,required=True)
    p.add_argument('--data-dir',type=Path);p.add_argument('--labels',type=Path);p.add_argument('--human-reviews',type=Path);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('new output path required; preserve previous evidence')
    r=score_files(a.generation_dir,a.predictions,data_dir=a.data_dir,labels=a.labels,human_reviews=a.human_reviews)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'cases':r['case_count'],'status_counts':r['status_counts'],'inference_executed':False}))
