"""Explicit synthetic loopback HTTP integration/benchmark of the real /search API.
No proxy/remote provider/data mutation on the canonical evaluation runtime.
"""
import argparse
from contextlib import contextmanager
import copy
import json
from pathlib import Path
import shutil
import socket
import sqlite3
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import httpx
import uvicorn
from apps.api.main import create_app
from apps.api.auth import AuthSettings
from apps.api.identity_provider import MockSupabaseTransport,SupabaseProviderAdapter
from apps.api.search_settings import SearchSettings
from scripts.validation.evaluation_fixtures import verify_frozen,EvaluationQueryAdapter,sha_file
from scripts.validation.score_v03b_predictions import load
from scripts.validation.retrieval_ablation import key,query_metrics,latency


@contextmanager
def server(runtime,enabled):
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);origin='http://127.0.0.1:'+str(sock.getsockname()[1])
    issuer='https://synthetic.invalid/auth/v1';accounts={'reader-a@example.test':('reader-a','A','reader'),
        'manager-a@example.test':('manager-a','A','manager'),'reader-b@example.test':('reader-b','B','reader')}
    def mock(method,path,headers,body):
        if method=='POST':
            a=accounts.get(body.get('email'))
            return (200,{'access_token':'synthetic-'+a[0],'expires_in':1800}) if a and body.get('password')=='synthetic-test-only' else (401,{})
        subject=headers.get('Authorization','').removeprefix('Bearer synthetic-')
        return (200,{'id':subject,'user_metadata':{'role':'manager','institution_id':'foreign-spoof'}}) if subject in {x[0] for x in accounts.values()} else (401,{})
    app=create_app(runtime,parsing_enabled=True,search_settings=SearchSettings(scored_or_enabled=enabled),
        identity_provider=SupabaseProviderAdapter(MockSupabaseTransport(mock),issuer),auth_settings=AuthSettings(origin=origin,secure_cookie=False))
    for subject,org,role in accounts.values():app.state.auth.store.provision(issuer,subject,org,'합성기관 '+org,role,role=='manager')
    svc=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',log_level='error',access_log=False))
    thread=threading.Thread(target=svc.run,kwargs={'sockets':[sock]},daemon=True);thread.start()
    try:
        deadline=time.monotonic()+10
        while not svc.started:
            if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('loopback_server_failed')
            time.sleep(.01)
        yield origin,app
    finally:
        svc.should_exit=True;thread.join(timeout=10);sock.close()
        if thread.is_alive():raise RuntimeError('loopback_server_did_not_stop')


def login(origin,email):
    c=httpx.Client(base_url=origin,timeout=60,trust_env=False)
    csrf=c.post('/auth/csrf',headers={'Origin':origin}).json()['csrf_token']
    r=c.post('/auth/login',headers={'Origin':origin,'X-CSRF-Token':csrf},json={'email':email,'password':'synthetic-test-only'})
    assert r.status_code==200
    me=c.get('/auth/me').json();assert me['role']==('manager' if email.startswith('manager') else 'reader')
    assert me['institution_id']==('B' if email.startswith('reader-b') else 'A')
    return c,me['csrf_token']


def run(generation_dir,output_dir):
    start=time.perf_counter();directory=Path(generation_dir).resolve();out=Path(output_dir).resolve()
    if out.exists():raise ValueError('new_output_path_required')
    g=load(directory/'generation.json');verify_frozen(g,directory);source=Path(g['data_dir'])
    if not (source/'metadata.sqlite3').exists():raise ValueError('existing_canonical_runtime_required')
    out.mkdir(parents=True);runtime=ROOT/'work/v03d/http-runtimes'/out.name
    runtime.parent.mkdir(parents=True,exist_ok=True)
    if runtime.exists():raise ValueError('new_http_runtime_required')
    runtime.mkdir(parents=True)
    a=sqlite3.connect(source/'metadata.sqlite3');b=sqlite3.connect(runtime/'metadata.sqlite3')
    try:a.backup(b)
    finally:a.close();b.close()
    shutil.copytree(source/'originals',runtime/'originals')
    assertions=[];reports={};raw_contract=[]
    with server(runtime,True) as (origin,app):
        assert not app.state.auth.provider.remote_enabled
        with httpx.Client(base_url=origin,trust_env=False) as anonymous:
            assert anonymous.get('/search',params={'q':'자료','strategy':'scored_or'}).status_code==401
        assertions.append('anonymous_401_default_deny')
        ca,ta=login(origin,'reader-a@example.test');cb,tb=login(origin,'reader-b@example.test');cm,tm=login(origin,'manager-a@example.test')
        try:
            for c in (ca,cm):
                r=c.get('/search',params={'q':'일정표'});assert r.status_code==200 and r.json()['method']=='sqlite_keyword_substring_v1'
                assert set(r.json())=={'method','results'} and r.headers['cache-control']=='no-store'
            assertions+=['reader_and_manager_default_literal_schema','no_store_cookie_contract']
            assert ca.post('/auth/logout').status_code==403
            assert ca.post('/auth/logout',headers={'Origin':'https://foreign.invalid','X-CSRF-Token':ta}).status_code==403
            assertions.append('csrf_origin_mutation_guards_unchanged')
            expected_C=load(ROOT/'outputs/v03c2/experiment-final/results.json')['methods']['C']['cases']
            expected_C={q['id']:q for q in expected_C}
            for method in ('literal','scored_or'):
                cases=[];timings=[];hashes=[];requests=0
                for repeat in range(3):
                    one=[]
                    for q in g['queries']:
                        client=ca if q['organization_id']=='A' else cb
                        began=time.perf_counter();items={};scores={};http_count=0
                        windows=EvaluationQueryAdapter.windows(q['question']) if method=='literal' else [q['question']]
                        for window in windows:
                            response=client.get('/search',params={'q':window,'strategy':method,'limit':50 if method=='literal' else 10});http_count+=1
                            assert response.status_code==200,(method,q['id'],response.status_code)
                            payload=response.json();assert payload['method']==('sqlite_keyword_substring_v1' if method=='literal' else 'sqlite_scored_or_v1')
                            for rank,item in enumerate(payload['results'],1):
                                ref=item['evidence'];assert ref['organization_id']==q['organization_id']
                                k=key(item);items[k]=item;scores[k]=scores.get(k,0)+1/(60+rank)
                        ranked=sorted(items,key=lambda k:(-scores[k],k))[:10] if method=='literal' else list(items)
                        duration=time.perf_counter()-began;requests+=http_count
                        if q['answer_status']=='answerable':timings.append(duration)
                        expected={key({'evidence':e}) for e in q['expected_evidence_refs']}
                        forbidden={key({'evidence':e}) for e in q.get('forbidden_evidence_refs',[])}
                        assert not forbidden&set(ranked)
                        if method=='scored_or':
                            old=[(x['document_id'],x['version_id'],x['chunk_id']) for x in expected_C[q['id']]['ranked'][:10]]
                            assert ranked==old,('C2_API_order_changed',q['id'])
                        row={'id':q['id'],'ranking':[list(k) for k in ranked],'requests_per_question':http_count,
                            'metrics':query_metrics(expected,ranked) if expected else None,
                            'candidate_count':len(ranked),'forbidden_hits':0,'answer_generated':False}
                        one.append(row)
                    from apps.api.chunking import digest
                    hashes.append(digest(one))
                    if repeat==0:cases=one
                assert len(set(hashes))==1
                positive=[q for q in cases if q['metrics'] is not None]
                reports[method]={'cases':cases,'metrics':{k:sum(q['metrics'][k] for q in positive)/36 for k in ['hit_at_5','hit_at_10','recall_at_5','recall_at_10','mrr_at_10']},
                    'no_results':sum(q['metrics']['no_results'] for q in positive),'latency_full_http_question':latency(timings),
                    'http_requests_3_repeats':requests,'repeat_hashes':hashes,'positive_queries':36,'abstain_queries':4}
            for q in g['queries']:
                if len(q['question'].split())>8:
                    client=ca if q['organization_id']=='A' else cb
                    assert client.get('/search',params={'q':q['question']}).status_code==400
                    raw_contract.append({'id':q['id'],'literal_raw_status':400,'scored_or_raw_status':200,'reason':'old 8-word contract preserved; benchmark literal uses C1/C2 windows'})
            assertions+=['3_repeat_determinism_both_API_paths','C2_C_top10_order_equivalence_all_40','tenant_and_forbidden_ref_isolation_40','literal_long_query_contract_unchanged']
            # Fresh evidence resolution through authenticated product route, using CSRF contract.
            q=g['queries'][0];ref=q['expected_evidence_refs'][0]
            path=f"/documents/{ref['document_id']}/versions/{ref['version_id']}/chunks/{ref['chunk_id']}/evidence/resolve"
            good=ca.post(path,json=ref,headers={'Origin':origin,'X-CSRF-Token':ta});assert good.status_code==200 and good.json()['structural_valid']
            bad=copy.deepcopy(ref);bad['spans'][0]['quote']='forged'
            assert ca.post(path,json=bad,headers={'Origin':origin,'X-CSRF-Token':ta}).status_code==422
            assert cb.post(path,json=ref,headers={'Origin':origin,'X-CSRF-Token':tb}).status_code==404
            assertions.append('HTTP_evidence_structural_valid_forged422_foreign404')
            old_cookie=ca.cookies.get('seomuitda-dev');assert ca.post('/auth/logout',headers={'Origin':origin,'X-CSRF-Token':ta}).status_code==200
            ca.cookies.set('seomuitda-dev',old_cookie,domain='127.0.0.1',path='/')
            assert ca.get('/search',params={'q':'자료','strategy':'scored_or'}).status_code==401
            assertions.append('logout_and_old_cookie_replay_401')
        finally:ca.close();cb.close();cm.close()
    with server(runtime,False) as (origin,app):
        c,token=login(origin,'reader-a@example.test')
        try:
            assert c.get('/search',params={'q':'자료','strategy':'scored_or','feature_flag':'1'}).status_code==503
            assert c.get('/search',params={'q':'일정표'}).status_code==200
        finally:c.close()
    assertions.append('flag_off_503_and_default_literal200')
    result={'status':'PASS','assertions':assertions,'assertion_count':len(assertions),'methods':reports,'raw_literal_contract':raw_contract,
        'generation_id':g['generation_id'],'source_manifest_sha256':sha_file(directory/'generation.json'),
        'auth':'real BFF cookies and CSRF with explicit local MockSupabaseTransport; no dependency override',
        'transport':'real loopback TCP uvicorn/httpx; proxies disabled; no in-process ASGI transport',
        'corpus_runtime':'isolated SQLite backup and copied originals; canonical runtime unchanged',
        'response_claims_or_answers_generated':0,'actual_provider_calls':0,'actual_spend_usd':0,'seconds':time.perf_counter()-start}
    (out/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--synthetic-loopback-test',action='store_true',required=True);p.add_argument('--generation-dir',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True)
    args=p.parse_args();r=run(args.generation_dir,args.output_dir);print(json.dumps({'status':r['status'],'checks':r['assertion_count'],'methods':{k:v['metrics'] for k,v in r['methods'].items()},'seconds':r['seconds']},ensure_ascii=False,indent=2))
