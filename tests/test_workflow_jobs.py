"""Durable SQLite workflows, local processes and authenticated manager APIs."""
import copy
import json
import sqlite3
import subprocess
import sys
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
import test_workflow_forms as previous
import test_workflow_discovery as synthetic
from apps.api.main import create_app,authenticated_principal
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.workflow_jobs import WorkflowJobService
from apps.api.workflow_jobs_models import WorkflowJobRequest
from apps.api.workflow_discovery_models import DiscoverySettings


class WorkflowJobTests(unittest.TestCase):
    setUp=previous.WorkflowFormTests.setUp
    tearDown=previous.WorkflowFormTests.tearDown
    upload=previous.WorkflowFormTests.upload
    route=previous.WorkflowFormTests.route
    parse=previous.WorkflowFormTests.parse
    prepare=previous.WorkflowFormTests.prepare
    ready=previous.WorkflowFormTests.ready
    run_engine=previous.WorkflowFormTests.run_engine
    sample=previous.WorkflowFormTests.sample
    source=previous.WorkflowFormTests.source
    form=previous.WorkflowFormTests.form

    def setup_job(self,form=False):
        self.source()
        if form:self.form()
        self.jobs=self.app.state.workflows
        self.now=[1000.];self.jobs.clock=lambda:self.now[0]
        self.base=f'/documents/{self.snapshot.document_id}/versions/{self.snapshot.version_id}/workflow'
        return self.jobs.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id)

    def status(self,job):
        return self.jobs.status(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])

    def process(self):
        claim=self.jobs.claim(self.worker);self.assertIsNotNone(claim)
        return self.jobs.execute(self.worker,claim)

    def current(self):return self.jobs.current(self.principal,self.snapshot.document_id,self.snapshot.version_id)

    def rows(self,table):
        assert table in ['workflow_jobs','workflow_generations','workflow_candidates','workflow_review_issues','workflow_form_links']
        with self.jobs.repo.transaction() as db:return [dict(r) for r in db.connection.execute('SELECT * FROM '+table)]

    def test_normal_complete_atomic_components(self):
        job=self.setup_job(form=True)
        self.assertEqual(job['state'],'queued');self.assertEqual(self.process(),'completed')
        self.assertEqual(self.status(job)['state'],'completed')
        self.assertEqual(len(self.rows('workflow_generations')),1)
        self.assertTrue(self.rows('workflow_candidates'));self.assertTrue(self.rows('workflow_review_issues'))
        self.assertTrue(self.rows('workflow_form_links'))
        result=self.current()['result']
        self.assertEqual(result.forms.relations[0].match_status,'CANDIDATES')
        self.assertFalse(result.forms.publishable)

    def test_same_input_deduplicated(self):
        first=self.setup_job()
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs=list(pool.map(lambda _:self.jobs.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id),range(2)))
        self.assertEqual({j['id'] for j in jobs},{first['id']})
        self.assertEqual(len(self.rows('workflow_jobs')),1)
        self.process()
        self.assertEqual(self.jobs.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id)['id'],first['id'])

    def test_claim_exclusive_and_fenced(self):
        self.setup_job();one=self.jobs.claim(self.worker)
        self.assertIsNone(self.jobs.claim(self.worker))
        forged=dict(one,claim_token='not-the-capability')
        self.assertFalse(self.jobs.renew(forged));self.assertEqual(self.jobs.execute(self.worker,forged),'stale')
        self.assertEqual(self.jobs.execute(self.worker,one),'completed')
        self.assertEqual(self.jobs.execute(self.worker,one),'stale')

    def test_cancel_queued(self):
        job=self.setup_job();self.assertEqual(self.client.post(self.base+'/jobs/'+job['id']+'/cancel').json()['state'],'cancelled')
        self.assertIsNone(self.jobs.claim(self.worker))
        with self.assertRaises(DomainError):self.jobs.retry(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])

    def test_cancel_processing_fences_worker(self):
        job=self.setup_job();claim=self.jobs.claim(self.worker)
        self.jobs.cancel(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])
        self.assertEqual(self.jobs.execute(self.worker,claim),'stale');self.assertEqual(self.rows('workflow_generations'),[])

    def test_invalid_transitions(self):
        job=self.setup_job()
        self.assertEqual(self.client.post(self.base+'/jobs/'+job['id']+'/retry').status_code,409)
        self.process()
        for action in ['retry','cancel']:
            self.assertEqual(self.client.post(self.base+'/jobs/'+job['id']+'/'+action).status_code,409)

    def test_lease_expiry_recovery_and_old_worker(self):
        job=self.setup_job();claim=self.jobs.claim(self.worker);self.now[0]+=121
        self.assertFalse(self.jobs.renew(claim))
        fresh=self.jobs.claim(self.worker);self.assertEqual(fresh['attempt'],2)
        self.assertEqual(self.jobs.execute(self.worker,claim),'stale')
        self.assertEqual(self.jobs.execute(self.worker,fresh),'completed')
        self.assertEqual(self.status(job)['attempt'],2)

    def test_renew_before_expiry(self):
        self.setup_job();claim=self.jobs.claim(self.worker);self.now[0]+=100
        self.assertTrue(self.jobs.renew(claim));self.now[0]+=100
        self.assertIsNone(self.jobs.claim(self.worker))
        self.assertEqual(self.jobs.execute(self.worker,claim),'completed')

    def test_max_lease_attempts(self):
        job=self.setup_job()
        for _ in range(3):self.assertIsNotNone(self.jobs.claim(self.worker));self.now[0]+=121
        self.assertIsNone(self.jobs.claim(self.worker));self.assertEqual(self.status(job)['state'],'failed')
        self.assertEqual(self.status(job)['error_code'],'lease_expired')
        with self.assertRaises(DomainError):self.jobs.retry(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])

    def test_retryable_failure_and_retry(self):
        job=self.setup_job()
        with patch.object(self.jobs.engine,'run',side_effect=RuntimeError('secret must not appear')):
            self.assertEqual(self.process(),'failed')
        status=self.status(job);self.assertEqual(status['error_category'],'RETRYABLE');self.assertNotIn('secret',json.dumps(status))
        self.jobs.retry(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])
        self.assertEqual(self.process(),'completed')
        history=self.status(job)['events']
        self.assertTrue(any(e['state']=='failed' and e['error_code']=='workflow_internal_failure' for e in history))
        self.assertEqual(history[-1]['state'],'completed')

    def test_permanent_failure_no_retry(self):
        job=self.setup_job()
        with patch.object(self.jobs.engine,'run',side_effect=DomainError('invalid_offline_workflow_output')):
            self.assertEqual(self.process(),'failed')
        self.assertEqual(self.status(job)['error_category'],'PERMANENT')
        with self.assertRaises(DomainError):self.jobs.retry(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])

    def test_partial_insert_rollback(self):
        job=self.setup_job(form=True)
        with self.jobs.repo.transaction() as db:
            db.connection.execute("CREATE TRIGGER injected_failure BEFORE INSERT ON workflow_form_links BEGIN SELECT RAISE(ABORT,'injected'); END")
        self.assertEqual(self.process(),'failed')
        for table in ['workflow_generations','workflow_candidates','workflow_review_issues','workflow_form_links']:
            self.assertEqual(self.rows(table),[],table)
        self.assertEqual(self.status(job)['error_category'],'RETRYABLE')
        with self.jobs.repo.transaction() as db:db.connection.execute('DROP TRIGGER injected_failure')
        self.jobs.retry(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id']);self.assertEqual(self.process(),'completed')

    def test_active_change_during_processing(self):
        job=self.setup_job();original=self.jobs.engine.run
        def changed(*args):
            result=original(*args)
            meta,_,_=self.prepare(synthetic.synthetic_hwpx(['업무명: 새 버전','1. 담당자는 자료를 기록한다.']),'new.hwpx',self.snapshot.document_id)
            self.app.state.service.activate(self.principal,meta['document_id'],meta['id'])
            return result
        with patch.object(self.jobs.engine,'run',side_effect=changed):self.assertEqual(self.process(),'failed')
        self.assertEqual(self.rows('workflow_generations'),[]);self.assertEqual(self.status(job)['error_category'],'STALE_INPUT')

    def test_deregister_during_processing(self):
        self.setup_job();original=self.jobs.engine.run
        def changed(*args):
            result=original(*args);self.app.state.service.deregister(self.principal,self.snapshot.document_id);return result
        with patch.object(self.jobs.engine,'run',side_effect=changed):self.assertEqual(self.process(),'failed')
        self.assertEqual(self.rows('workflow_generations'),[])

    def test_chunk_generation_during_processing(self):
        from apps.api.chunking import ChunkConfig
        self.setup_job();original=self.jobs.engine.run
        def changed(*args):
            result=original(*args);chunks=self.app.state.chunks
            chunks.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id,ChunkConfig(max_chars=64))
            chunks.execute(self.worker,chunks.claim(self.worker));return result
        with patch.object(self.jobs.engine,'run',side_effect=changed):self.assertEqual(self.process(),'failed')
        self.assertEqual(self.rows('workflow_generations'),[])

    def test_final_transaction_checks_freshness(self):
        self.setup_job();original=self.jobs._fresh;calls=0
        def changed(db,*args):
            nonlocal calls
            calls+=1
            if calls==2:db.connection.execute('UPDATE documents SET active_version_id=NULL WHERE id=?',(self.snapshot.document_id,))
            return original(db,*args)
        with patch.object(self.jobs,'_fresh',side_effect=changed):self.assertEqual(self.process(),'failed')
        self.assertEqual(self.rows('workflow_generations'),[])

    def test_catalog_change_invalidates_queued_input(self):
        job=self.setup_job();self.form()
        self.assertEqual(self.process(),'failed');self.assertEqual(self.status(job)['error_category'],'STALE_INPUT')
        new=self.jobs.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id)
        self.assertNotEqual(new['id'],job['id'])
        self.assertEqual(self.process(),'completed')

    def test_old_completed_not_exposed_after_deregister(self):
        self.setup_job();self.process();self.app.state.service.deregister(self.principal,self.snapshot.document_id)
        self.assertEqual(self.client.get(self.base+'/candidates').status_code,404)

    def test_old_completed_not_exposed_after_active_change(self):
        self.setup_job();self.process()
        meta,_,_=self.prepare(synthetic.synthetic_hwpx(['새 합성 자료']),'new.hwpx',self.snapshot.document_id)
        self.app.state.service.activate(self.principal,meta['document_id'],meta['id'])
        self.assertEqual(self.client.get(self.base+'/candidates').status_code,409)

    def test_catalog_change_hides_stale_links(self):
        self.setup_job(form=True);self.process()
        self.form(filename='duplicate.hwpx',text='다른 서식')
        self.assertEqual(self.client.get(self.base+'/form-links').status_code,409)

    def test_foreign_jobs_and_candidates_blocked(self):
        job=self.setup_job();self.process();self.principal=Principal('foreign','B','manager')
        for path in [self.base+'/jobs/'+job['id'],self.base+'/candidates',self.base+'/review-issues',self.base+'/form-links']:
            self.assertEqual(self.client.get(path).status_code,404,path)

    def test_reader_all_workflow_routes_blocked(self):
        job=self.setup_job();self.principal=Principal('reader','A','reader')
        for method,path in [('POST','/jobs'),('GET','/jobs/'+job['id']),('POST','/jobs/'+job['id']+'/retry'),('POST','/jobs/'+job['id']+'/cancel'),('GET','/candidates'),('GET','/review-issues'),('GET','/form-links')]:
            self.assertEqual(self.client.request(method,self.base+path,json={} if method=='POST' else None).status_code,403)

    def test_api_end_to_end_views(self):
        job=self.setup_job(form=True);r=self.client.post(self.base+'/jobs',json={})
        self.assertEqual(r.status_code,202);self.assertEqual(r.json()['id'],job['id'])
        self.assertNotIn('claim_hash',r.text);self.assertNotIn('snapshot',r.json())
        self.process();r=self.client.get(self.base+'/candidates');self.assertEqual(r.status_code,200)
        candidate=r.json()['candidates'][0]['id']
        for path in ['/candidates/'+candidate,'/review-issues','/form-links','/candidates/'+candidate+'/evidence']:
            response=self.client.get(self.base+path);self.assertEqual(response.status_code,200,response.text)
            self.assertFalse(response.json()['publishable']);self.assertEqual(response.headers['cache-control'],'no-store')
        self.assertEqual(self.client.get(self.base+'/candidates/missing').status_code,404)

    def test_unknown_job_and_wrong_version(self):
        job=self.setup_job()
        self.assertEqual(self.client.get(self.base+'/jobs/missing').status_code,404)
        self.assertEqual(self.client.get(self.base.replace(self.snapshot.version_id,'missing')+'/jobs/'+job['id']).status_code,404)

    def test_forged_claim_scope_blocked(self):
        self.setup_job();claim=self.jobs.claim(self.worker)
        with self.assertRaises(DomainError):self.jobs.execute(Principal('other','B','worker'),claim)
        with self.assertRaises(DomainError):self.jobs.execute(self.worker,dict(claim,institution_id='B'))

    def test_server_restart_preserves_results(self):
        self.setup_job(form=True);self.process()
        reopened=create_app(self.root,parsing_enabled=True)
        reopened.dependency_overrides[authenticated_principal]=lambda:self.principal
        with TestClient(reopened) as client:
            response=client.get(self.base+'/candidates')
            self.assertEqual(response.status_code,200,response.text)
            self.assertTrue(response.json()['candidates'])
            self.assertTrue(client.get(self.base+'/form-links').json()['form_links'])

    def test_worker_cli_separate_process_completes(self):
        job=self.setup_job()
        result=subprocess.run([sys.executable,'-B','-m','apps.api.workflow_worker','--data-dir',str(self.root),
                               '--institution-id','A','--once'],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'completed')
        self.assertEqual(self.status(job)['state'],'completed');self.assertTrue(self.current()['result'].discovery.extraction.workflows)

    def test_killed_worker_claim_recovers_in_new_service(self):
        import time
        self.setup_job();ready=self.root/'workflow-worker-claimed'
        code='''import sys,time
from pathlib import Path
from apps.api.repository import Repository
from apps.api.storage import LocalOriginalStore
from apps.api.service import DocumentService
from apps.api.parsing_service import ParsingService
from apps.api.chunk_service import ChunkService
from apps.api.workflow_jobs import WorkflowJobService
from apps.api.models import Principal
root=Path(sys.argv[1]); docs=DocumentService(Repository(root/'metadata.sqlite3'),LocalOriginalStore(root/'originals'),True)
jobs=WorkflowJobService(ChunkService(ParsingService(docs)),lease_seconds=1)
assert jobs.claim(Principal('doomed','A','worker'))
(root/'workflow-worker-claimed').write_text('claimed')
time.sleep(60)
'''
        process=subprocess.Popen([sys.executable,'-B','-c',code,str(self.root)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+10
            while not ready.exists() and time.monotonic()<deadline:
                if process.poll() is not None:self.fail(process.stderr.read().decode())
                time.sleep(.02)
            self.assertTrue(ready.exists());process.kill();process.wait(timeout=5)
            self.jobs=WorkflowJobService(self.app.state.chunks,clock=lambda:time.time()+5)
            claim=self.jobs.claim(self.worker);self.assertEqual(claim['attempt'],2)
            self.assertEqual(self.jobs.execute(self.worker,claim),'completed')
        finally:
            if process.poll() is None:process.kill();process.wait(timeout=5)
            process.stderr.close()

    def test_backup_restore_generation_and_schema_idempotence(self):
        from apps.api.repository import Repository
        from apps.api.storage import LocalOriginalStore
        from apps.api.service import DocumentService
        from apps.api.parsing_service import ParsingService
        from apps.api.chunk_service import ChunkService
        self.setup_job(form=True);self.process();target=self.root/'restored.sqlite3'
        with sqlite3.connect(self.jobs.repo.path) as src,sqlite3.connect(target) as dst:src.backup(dst)
        docs=DocumentService(Repository(target),LocalOriginalStore(self.root/'originals'),True)
        restored=WorkflowJobService(ChunkService(ParsingService(docs)))
        result=restored.current(self.principal,self.snapshot.document_id,self.snapshot.version_id)
        self.assertTrue(result['result'].forms.relations)
        with restored.repo.transaction() as db:
            self.assertEqual(db.connection.execute("SELECT version FROM schema_extensions WHERE name='workflow_jobs'").fetchone()[0],1)
            self.assertEqual(db.connection.execute('PRAGMA user_version').fetchone()[0],2)

    def test_component_tamper_rejected(self):
        self.setup_job();self.process()
        with self.jobs.repo.transaction() as db:db.connection.execute("UPDATE workflow_candidates SET payload='{}'")
        self.assertEqual(self.client.get(self.base+'/candidates').status_code,422)

    def test_payload_hash_tamper_rejected(self):
        self.setup_job();self.process()
        with self.jobs.repo.transaction() as db:db.connection.execute("UPDATE workflow_generations SET payload='{}'")
        self.assertEqual(self.client.get(self.base+'/candidates').status_code,422)

    def test_forged_adapter_evidence_never_saved(self):
        self.setup_job();original=self.jobs.engine.run
        def forged(*args):
            result=original(*args)
            evidence=result.extraction.workflows[0].title.evidence[0]
            evidence.__dict__['start']=9999;evidence.__dict__['end']=9999+len(evidence.quote)
            return result
        with patch.object(self.jobs.engine,'run',side_effect=forged):self.assertEqual(self.process(),'failed')
        self.assertEqual(self.rows('workflow_generations'),[])

    def test_job_snapshot_scope_corruption_blocked(self):
        self.setup_job()
        with self.jobs.repo.transaction() as db:db.connection.execute("UPDATE workflow_jobs SET input_snapshot_id=?",('a'*64,))
        self.assertEqual(self.process(),'failed');self.assertEqual(self.rows('workflow_generations'),[])

    def test_stale_generation_after_rechunk_not_served(self):
        from apps.api.chunking import ChunkConfig
        self.setup_job();self.process();chunks=self.app.state.chunks
        chunks.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id,ChunkConfig(max_chars=64))
        chunks.execute(self.worker,chunks.claim(self.worker))
        self.assertEqual(self.client.get(self.base+'/candidates').status_code,409)

    def test_cancellation_while_engine_running(self):
        job=self.setup_job();original=self.jobs.engine.run
        def cancel(*args):
            result=original(*args)
            self.jobs.cancel(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id']);return result
        with patch.object(self.jobs.engine,'run',side_effect=cancel):self.assertEqual(self.process(),'stale')
        self.assertEqual(self.rows('workflow_generations'),[])

    def test_newer_generation_not_overwritten_by_late_old_worker(self):
        self.setup_job();old=self.jobs.claim(self.worker)
        request=WorkflowJobRequest(settings=DiscoverySettings(batch_size=1))
        newer=self.jobs.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id,request)
        newclaim=self.jobs.claim(self.worker)
        self.assertEqual(self.jobs.execute(self.worker,newclaim),'completed')
        self.assertEqual(self.jobs.execute(self.worker,old),'completed')
        self.assertEqual(self.current()['job']['id'],newer['id'])

    def test_settings_extra_fields_rejected(self):
        self.setup_job()
        for payload in [{'provider':'remote'},{'settings':{'max_chunks':True}},{'snapshot_settings':{'max_snapshot_bytes':0}}]:
            self.assertEqual(self.client.post(self.base+'/jobs',json=payload).status_code,422)

    def test_no_claim_capability_in_public_status(self):
        job=self.setup_job();claim=self.jobs.claim(self.worker)
        text=json.dumps(self.client.get(self.base+'/jobs/'+job['id']).json())
        for secret in [claim['claim_token'],'claim_hash','snapshot"','settings"','catalog_hash']:
            self.assertNotIn(secret,text)

    def test_failure_attempt_limit_preserved_across_retry(self):
        job=self.setup_job()
        for attempt in range(1,4):
            with patch.object(self.jobs.engine,'run',side_effect=RuntimeError('transient')):self.assertEqual(self.process(),'failed')
            self.assertEqual(self.status(job)['attempt'],attempt)
            if attempt<3:self.jobs.retry(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])
        with self.assertRaises(DomainError):self.jobs.retry(self.principal,self.snapshot.document_id,self.snapshot.version_id,job['id'])

    def test_claim_cannot_be_created_by_manager(self):
        self.setup_job()
        with self.assertRaises(DomainError):self.jobs.claim(self.principal)


    def test_empty_workflow_generation_is_valid_review_result(self):
        self.source(['자료 안내','이 자료는 합성 표본의 색상에 관한 설명이다.'])
        self.jobs=self.app.state.workflows
        self.jobs.enqueue(self.principal,self.snapshot.document_id,self.snapshot.version_id)
        self.assertEqual(self.process(),'completed')
        result=self.current()['result']
        self.assertEqual(result.discovery.extraction.workflows,[])
        self.assertTrue(result.forms.source_review.issues)

    def test_original_hash_failure_never_publishes(self):
        job=self.setup_job()
        with patch.object(self.jobs.inputs.documents.store,'read',side_effect=DomainError('original_integrity_failure')):
            self.assertEqual(self.process(),'failed')
        self.assertEqual(self.rows('workflow_generations'),[])
        self.assertEqual(self.status(job)['error_category'],'PERMANENT')

    def test_migration_foreign_keys_and_integrity(self):
        self.setup_job(form=True);self.process()
        with self.jobs.repo.transaction() as db:
            self.assertEqual(db.connection.execute('PRAGMA foreign_key_check').fetchall(),[])
            self.assertEqual(db.connection.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            db.connection.execute("UPDATE schema_extensions SET version=99 WHERE name='workflow_jobs'")
        with self.assertRaises(RuntimeError):WorkflowJobService(self.app.state.chunks)


import test_auth as auth_fixture

class WorkflowAuthenticationTests(unittest.TestCase):
    setUp=auth_fixture.AuthTests.setUp
    tearDown=auth_fixture.AuthTests.tearDown
    login=auth_fixture.AuthTests.login
    headers=auth_fixture.AuthTests.headers
    base='/documents/missing/versions/missing/workflow'

    def test_all_new_routes_require_real_session(self):
        for method,path in [('POST','/jobs'),('GET','/jobs/j'),('POST','/jobs/j/retry'),('POST','/jobs/j/cancel'),('GET','/candidates'),('GET','/candidates/c'),('GET','/review-issues'),('GET','/form-links'),('GET','/candidates/c/evidence')]:
            self.assertEqual(self.client.request(method,self.base+path,json={} if method=='POST' else None).status_code,401)

    def test_mutations_preserve_csrf_and_origin(self):
        self.login()
        for path in ['/jobs','/jobs/j/retry','/jobs/j/cancel']:
            self.assertEqual(self.client.post(self.base+path,json={}).status_code,403)
            self.assertEqual(self.client.post(self.base+path,json={},headers={**self.headers(),'Origin':'https://foreign.invalid'}).status_code,403)
            self.assertEqual(self.client.post(self.base+path,json={},headers=self.headers()).status_code,404)

    def test_reader_session_blocked(self):
        self.login('reader@test')
        self.assertEqual(self.client.post(self.base+'/jobs',json={},headers=self.headers()).status_code,403)
        self.assertEqual(self.client.get(self.base+'/candidates').status_code,403)

    def test_revoked_session_cannot_query(self):
        self.login();self.client.post('/auth/logout',headers=self.headers())
        self.assertEqual(self.client.get(self.base+'/candidates').status_code,401)

    def test_authenticated_manager_actual_job_flow(self):
        from apps.api.chunking import ChunkConfig
        self.login();headers={**self.headers(),'x-data-classification':'synthetic','Content-Type':'application/hwp+zip'}
        response=self.client.post('/documents?filename=new.hwpx',content=synthetic.synthetic_hwpx([
            '업무명: 실제 쿠키 시험','1. 담당자는 자료를 제출한다.']),headers=headers)
        self.assertEqual(response.status_code,201,response.text)
        meta=response.json()['document'];base=f"/documents/{meta['document_id']}/versions/{meta['id']}"
        worker=Principal('trusted-local','A','worker');manager=Principal(self.a,'A','manager')
        self.assertEqual(self.app.state.parsing.execute(worker,self.app.state.parsing.claim(worker)),'completed')
        chunks=self.app.state.chunks;chunks.enqueue(manager,meta['document_id'],meta['id'],ChunkConfig())
        self.assertEqual(chunks.execute(worker,chunks.claim(worker)),'completed')
        self.assertEqual(self.client.post(base+'/activate',headers=self.headers()).status_code,200)
        response=self.client.post(base+'/workflow/jobs',json={},headers=self.headers())
        self.assertEqual(response.status_code,202,response.text)
        jobs=self.app.state.workflows;self.assertEqual(jobs.execute(worker,jobs.claim(worker)),'completed')
        response=self.client.get(base+'/workflow/candidates');self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['candidates']);self.assertFalse(response.json()['publishable'])


class WorkflowJobSchemaTests(unittest.TestCase):
    def test_exported_schemas(self):
        from pathlib import Path
        from pydantic import TypeAdapter
        from apps.api.workflow_jobs_models import (WorkflowJobRequest,WorkflowJobStatus,WorkflowStoredResult,
            WorkflowCandidateResponse,WorkflowIssueResponse,WorkflowFormResponse,WorkflowEvidenceResponse)
        models={'workflow-job-request-v1':WorkflowJobRequest,'workflow-job-status-v1':WorkflowJobStatus,
                'workflow-job-result-v1':WorkflowStoredResult}
        for name,model in models.items():
            self.assertEqual(json.loads(Path('schemas/'+name+'.schema.json').read_text()),model.model_json_schema())
        expected=TypeAdapter(WorkflowCandidateResponse|WorkflowIssueResponse|WorkflowFormResponse|WorkflowEvidenceResponse).json_schema()
        self.assertEqual(json.loads(Path('schemas/workflow-query-v1.schema.json').read_text()),expected)
