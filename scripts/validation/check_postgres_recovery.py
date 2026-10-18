"""Seed/check a synthetic loopback recovery case. Server stop/start is an explicit operator step."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from apps.api.postgres import PostgresDatabase,PostgresRepository,PostgresBudgetLedger
from apps.api.storage import LocalOriginalStore
from apps.api.service import DocumentService
from apps.api.parsing_service import ParsingService
from apps.api.chunk_service import ChunkService
from apps.api.chunking import ChunkConfig
from apps.api.workflow_jobs import WorkflowJobService
from apps.api.provider_budget import Reservation
from apps.api.models import Principal
from test_workflow_discovery import synthetic_hwpx

A=Principal('synthetic-recovery-manager','A','manager')
W=Principal('synthetic-recovery-worker','A','worker')


def database(schema):return PostgresDatabase(os.environ.get('SB_PG_TEST_DSN',''),schema,local_test=True)

def pipeline(db,root,now):
    docs=DocumentService(PostgresRepository(db),LocalOriginalStore(root/'originals'),True)
    parsing=ParsingService(docs);chunks=ChunkService(parsing)
    return docs,parsing,chunks,WorkflowJobService(chunks,clock=lambda:now,lease_seconds=1)


def seed(root):
    if root.exists():raise ValueError('new_recovery_path_required')
    root.mkdir(parents=True)
    suffix=secrets.token_hex(6);app=database('sb_recovery_app_'+suffix);cost=database('sb_recovery_cost_'+suffix)
    app.migrate();cost.migrate('budget')
    docs,parsing,chunks,jobs=pipeline(app,root,1000)
    raw=synthetic_hwpx(['업무명: 합성 복구 접수','1. 신청자는 복구신청서를 제출한다.','2. 담당자는 제출 자료를 확인한다.'])
    meta,_=docs.register(A,'synthetic-recovery.hwpx','application/hwp+zip',raw)
    assert parsing.execute(W,parsing.claim(W))=='completed'
    chunks.enqueue(A,meta['document_id'],meta['id'],ChunkConfig());assert chunks.execute(W,chunks.claim(W))=='completed'
    docs.activate(A,meta['document_id'],meta['id'])
    job=jobs.enqueue(A,meta['document_id'],meta['id']);assert jobs.claim(W) is not None
    ledger=PostgresBudgetLedger(cost,clock=lambda:1000,ttl=1);ledger.provision(A,1000);ledger.open_job(A,'job',1000)
    claim=ledger.reserve(A,'job','request','a'*64,Reservation(10,10,1000000,1000000,2,100));ledger.start(A,claim)
    state={'app_schema':app.schema,'budget_schema':cost.schema,'document':meta['document_id'],'version':meta['id'],
           'sha256':hashlib.sha256(raw).hexdigest(),'workflow_job':job['id']}
    (root/'state.json').write_text(json.dumps(state,indent=2)+'\n')
    return {'stage':'SEEDED','workflow_state':'processing','budget_state':'in_flight','actual_external_provider_calls':0}


def check(root):
    state=json.loads((root/'state.json').read_text());app=database(state['app_schema']);cost=database(state['budget_schema'])
    docs,parsing,chunks,jobs=pipeline(app,root,1002)
    raw,meta=docs.original(A,state['document'],state['version'])
    assert meta['active'] and hashlib.sha256(raw).hexdigest()==state['sha256']
    claim=jobs.claim(W);assert claim['attempt']==2
    assert jobs.execute(W,claim)=='completed';assert jobs.execute(W,claim)=='stale'
    result=jobs.current(A,state['document'],state['version'])
    assert result['result'].forms.semantic_verification=='NOT_VERIFIED'
    assert not result['result'].forms.publishable
    ledger=PostgresBudgetLedger(cost,clock=lambda:1002,ttl=1);assert ledger.recover(A)==1
    assert ledger.request(A,'request')['state']=='uncertain';assert ledger.balance(A)['held']==20
    ledger.reconcile(A,'request',4,2,'b'*64)
    balance=ledger.balance(A);assert (balance['held'],balance['spent'])==(0,6)
    return {'stage':'RECOVERED','original_sha_match':True,'active_version_preserved':True,'workflow_attempt':claim['attempt'],
            'workflow_completed_once':True,'duplicate_completion_rejected':True,'uncertain_hold_after_restart':20,
            'reconciled_held':0,'simulated_spent_micro_usd':6,'actual_external_provider_calls':0,'actual_spend_usd':0}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=('seed','check'));p.add_argument('--data-dir',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(seed(a.data_dir) if a.stage=='seed' else check(a.data_dir),ensure_ascii=False,indent=2))
