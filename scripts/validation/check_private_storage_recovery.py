"""Offline synthetic application + Fake object restore drill; no cloud credentials/HTTP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from apps.api.main import create_app
from apps.api.repository import Repository
from apps.api.private_storage import PrivateOriginalStore,PrivateStorageSettings,FakeStorageTransport
from apps.api.storage_backup import StorageBackupService,BackupAuthority,save_bundle,load_bundle
from apps.api.models import Principal
from apps.api.chunking import ChunkConfig,EvidenceRef
from test_workflow_discovery import synthetic_hwpx


def run(backend,root):
    started=time.monotonic()
    if root.exists():raise ValueError('new_private_drill_directory_required')
    root.mkdir(mode=0o700,parents=True)
    settings=PrivateStorageSettings(project_url='https://'+'a'*20+'.supabase.co',bucket='private-originals',server_key='synthetic-offline-private-server-key')
    def setup(name):
        if backend=='postgresql':
            from apps.api.postgres import PostgresDatabase,PostgresRepository
            db=PostgresDatabase(os.environ.get('SB_PG_TEST_DSN',''),'sb_storage_drill_'+secrets.token_hex(8),local_test=True)
            db.migrate();repo=PostgresRepository(db)
        else:repo=Repository(root/name/'metadata.sqlite3')
        store=PrivateOriginalStore(repo,settings,FakeStorageTransport())
        return create_app(root/name,repository=repo,store=store,parsing_enabled=True),store
    manager=Principal('synthetic-manager','synthetic-institution','manager')
    worker=Principal('synthetic-worker',manager.institution_id,'worker')
    reader=Principal('synthetic-reader',manager.institution_id,'reader')
    operator=BackupAuthority((manager.institution_id,))
    source,store=setup('source')
    raw=synthetic_hwpx(['업무명: 합성 별 자료 접수','1. 신청자는 별신청서를 제출한다.','2. 담당자는 자료를 확인한다.'])
    meta,_=source.state.service.register(manager,'synthetic-recovery.hwpx','application/hwp+zip',raw)
    parsing=source.state.parsing;assert parsing.execute(worker,parsing.claim(worker))=='completed'
    chunks=source.state.chunks;chunks.enqueue(manager,meta['document_id'],meta['id'],ChunkConfig())
    assert chunks.execute(worker,chunks.claim(worker))=='completed'
    source.state.service.activate(manager,meta['document_id'],meta['id'])
    jobs=source.state.workflows;jobs.enqueue(manager,meta['document_id'],meta['id'])
    old_claim=jobs.claim(worker);assert old_claim is not None
    bundle=StorageBackupService(store.repo,store).create(operator)
    expected=save_bundle(bundle,root/'backup')
    # New repository, new empty Fake provider; original provider memory is not used to restore.
    target,target_store=setup('target')
    loaded=load_bundle(root/'backup',expected,operator)
    restore=StorageBackupService(target_store.repo,target_store)
    restored=restore.restore(operator,loaded,expected)
    assert target.state.workflows.execute(worker,old_claim)=='stale'
    claim=target.state.workflows.claim(worker);assert claim is not None
    assert target.state.workflows.execute(worker,claim)=='completed'
    result=target.state.workflows.current(manager,meta['document_id'],meta['id'])
    assert result['result'].forms.semantic_verification=='NOT_VERIFIED'
    assert not result['result'].forms.publishable
    original,current=target.state.service.original(reader,meta['document_id'],meta['id'])
    assert original==raw and current['sha256']==hashlib.sha256(raw).hexdigest()
    chunk=target.state.chunks.list(reader,meta['document_id'],meta['id'])[0]
    resolved=target.state.chunks.resolve(reader,meta['document_id'],meta['id'],chunk['chunk_id'],EvidenceRef.model_validate(chunk['evidence']))
    assert resolved['structural_valid']
    return {'backend':backend,'status':'PASS','disk_manifest_verified':True,'new_empty_target_restored':restored['status'],
            'original_hash_match':True,'evidence_structural_valid':True,'old_worker_claim_fenced':True,'worker_resumed':True,
            'semantic_verification':'NOT_VERIFIED','published_workflows':0,'backup_scope':'application_schema_and_fake_objects',
            'excluded_components':['provider_budget_separate_schema'],'actual_external_provider_calls':0,'actual_spend_usd':0,
            'seconds':round(time.monotonic()-started,3)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--backend',choices=('sqlite','postgresql'),required=True)
    p.add_argument('--data-dir',type=Path,required=True);args=p.parse_args()
    print(json.dumps(run(args.backend,args.data_dir),ensure_ascii=False,indent=2))
