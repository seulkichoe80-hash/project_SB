"""Real opt-in loopback PostgreSQL contract tests. No external services or real identities."""
import copy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from apps.api.postgres import PostgresDatabase, PostgresRepository, PostgresBudgetLedger, PostgresFailure, compile_query
from apps.api.models import Principal
from apps.api.errors import DomainError
import test_parsing as parsing_cases
import test_workflow_jobs as workflow_cases
import test_workflow_forms as form_cases
import test_workflow_discovery as synthetic
import test_rag_contracts as rag_cases
import test_provider_safety as budget_cases

DSN = os.environ.get('SB_PG_TEST_DSN')


def database(kind='application'):
    db = PostgresDatabase(DSN, 'sb_test_' + secrets.token_hex(8), local_test=True)
    db.migrate(kind)
    return db


class PostgreSQLDialectTests(unittest.TestCase):
    def test_quoted_literals_and_parameters(self):
        self.assertEqual(compile_query("SELECT '?', ?, '100%'"), "SELECT '?', %s, '100%%'")
    def test_upserts_are_explicit(self):
        self.assertIn('ON CONFLICT DO NOTHING', compile_query('INSERT OR IGNORE INTO identities(id) VALUES(?)'))
        self.assertIn('DO UPDATE', compile_query('INSERT OR REPLACE INTO auth_login_limits VALUES(?,?,?)'))
    def test_config_secret_redaction_and_local_guard(self):
        for dsn in ('postgresql://private-marker@remote.example/db','postgresql://private-marker@localhost/db'):
            with self.assertRaisesRegex(ValueError,'invalid_postgres_configuration') as e:
                PostgresDatabase(dsn,'valid_schema',local_test=True)
            self.assertNotIn('private-marker',str(e.exception))
    def test_schema_identifier_injection_rejected(self):
        with self.assertRaises(ValueError):PostgresDatabase('postgresql://u@127.0.0.1:55432/db','public;DROP SCHEMA public',local_test=True)


@unittest.skipUnless(DSN, 'BLOCKED: isolated loopback PostgreSQL SB_PG_TEST_DSN not configured')
class PostgreSQLWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.database = database(); self.pg_repo = PostgresRepository(self.database)
        self.factory_patch = patch('apps.api.main.Repository',return_value=self.pg_repo)
        self.factory_patch.start(); self.addCleanup(self.factory_patch.stop)
        parsing_cases.ParsingIntegrationTests.setUp(self)
    tearDown = parsing_cases.ParsingIntegrationTests.tearDown
    upload = workflow_cases.WorkflowJobTests.upload
    route = workflow_cases.WorkflowJobTests.route
    parse = workflow_cases.WorkflowJobTests.parse
    prepare = workflow_cases.WorkflowJobTests.prepare
    ready = workflow_cases.WorkflowJobTests.ready
    run_engine = workflow_cases.WorkflowJobTests.run_engine
    sample = workflow_cases.WorkflowJobTests.sample
    source = workflow_cases.WorkflowJobTests.source
    form = workflow_cases.WorkflowJobTests.form
    setup_job = workflow_cases.WorkflowJobTests.setup_job
    status = workflow_cases.WorkflowJobTests.status
    process = workflow_cases.WorkflowJobTests.process
    current = workflow_cases.WorkflowJobTests.current
    rows = workflow_cases.WorkflowJobTests.rows

    def test_schema_idempotency_and_non_destructive_migration(self):
        self.assertFalse(self.database.migrate())
        meta=self.upload();self.assertFalse(self.database.migrate())
        self.assertEqual(self.app.state.service.get(self.principal,meta['document_id'],meta['id'])['sha256'],meta['sha256'])
    def test_two_concurrent_workers_claim_once(self):
        self.setup_job(); barrier=threading.Barrier(2)
        def claim(_):barrier.wait();return self.jobs.claim(self.worker)
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(claim,range(2)))
        self.assertEqual(sum(c is not None for c in claims),1)
    def test_two_concurrent_parse_claims(self):
        self.upload();barrier=threading.Barrier(2)
        def claim(_):barrier.wait();return self.parsing.claim(self.worker)
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(claim,range(2)))
        self.assertEqual(sum(c is not None for c in claims),1)
    def test_two_concurrent_chunk_claims(self):
        meta=self.upload();self.parse(meta)
        self.client.post(self.route(meta)+'/chunk-jobs',json={})
        with ThreadPoolExecutor(max_workers=2) as pool:claims=list(pool.map(lambda _:self.app.state.chunks.claim(self.worker),range(2)))
        self.assertEqual(sum(c is not None for c in claims),1)
    def test_transaction_partial_insert_rolls_back(self):
        with self.assertRaises(RuntimeError):
            with self.pg_repo.transaction() as db:
                db.create_document('synthetic-rollback','A','now')
                raise RuntimeError('injected')
        with self.pg_repo.transaction() as db:self.assertIsNone(db.document('A','synthetic-rollback'))
    def test_workflow_partial_generation_failure_rolls_back(self):
        self.setup_job(form=True)
        from apps.api.postgres import Connection
        original=Connection.execute
        def broken(connection,sql,args=()):
            if sql.startswith('INSERT INTO workflow_form_links'):raise PostgresFailure('injected_write_failure')
            return original(connection,sql,args)
        with patch.object(Connection,'execute',broken):self.assertEqual(self.process(),'failed')
        for table in ('workflow_generations','workflow_candidates','workflow_review_issues','workflow_form_links'):
            self.assertEqual(self.rows(table),[])
    def test_parallel_active_versions_remain_scoped(self):
        one,_,_=self.prepare(synthetic.synthetic_hwpx(['업무명: 하나','1. 담당자는 자료를 제출한다.']),'one.hwpx')
        two,_,_=self.prepare(synthetic.synthetic_hwpx(['업무명: 둘','1. 담당자는 자료를 보관한다.']),'two.hwpx',one['document_id'])
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda m:self.app.state.service.activate(self.principal,m['document_id'],m['id']),(one,two)))
        with self.pg_repo.transaction() as db:self.assertIn(db.document('A',one['document_id'])['active_version_id'],(one['id'],two['id']))
    def test_trigger_rejects_cross_document_active_version(self):
        one=self.upload();other=self.upload(synthetic.synthetic_pdf(['different']), 'other.pdf')
        with self.assertRaises(PostgresFailure):
            with self.pg_repo.transaction() as db:db.activate(one['document_id'],other['id'])
    def test_sql_injection_and_literal_percent(self):
        meta,_,_=self.prepare();self.app.state.service.activate(self.principal,meta['document_id'],meta['id'])
        self.assertEqual(self.app.state.chunks.search(self.principal,"%' OR 1=1--"),[])
        with self.pg_repo.transaction() as db:
            self.assertEqual(db.connection.execute("SELECT '?', ?, '100%'",('bound',)).fetchone()[1],'bound')
    def test_original_hash_failure_is_not_published(self):
        self.setup_job();target=self.app.state.service.store.path(self.snapshot.version_id)
        target.chmod(0o644);target.write_bytes(b'tampered')
        self.assertEqual(self.process(),'failed');self.assertEqual(self.rows('workflow_generations'),[])
    def test_independent_worker_cli_uses_same_db(self):
        meta=self.upload()
        p=subprocess.run([sys.executable,'-B','-m','apps.api.worker','--data-dir',str(self.root),
                          '--institution-id','A','--once','--postgres-local-test','--postgres-schema',self.database.schema],
                         capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout.strip(),'completed')
        self.assertEqual(self.client.get(self.route(meta)+'/parsing').json()['state'],'completed')
    def test_repository_reopen_persists_results(self):
        self.setup_job();self.process()
        repo=PostgresRepository(PostgresDatabase(DSN,self.database.schema,local_test=True))
        with repo.transaction() as db:self.assertEqual(db.connection.execute('SELECT count(*) FROM workflow_generations').fetchone()[0],1)
    def test_constraint_failure_redacts_values(self):
        self.upload()
        with self.assertRaises(PostgresFailure) as e:
            with self.pg_repo.transaction() as db:db.connection.execute('INSERT INTO documents VALUES(?,?,?,?,?)',('private-marker','A',1,'no-version','now'))
        self.assertNotIn('private-marker',str(e.exception))

    def test_duplicate_column_labels_preserve_positional_values(self):
        with self.pg_repo.transaction() as db:
            row=db.connection.execute("SELECT 11 AS duplicate, 22 AS duplicate").fetchone()
            self.assertEqual(tuple(row),(11,22));self.assertEqual(row[0],11);self.assertEqual(row[1],22)
            self.assertEqual(row['duplicate'],11)
    def test_unknown_newer_schema_fails_closed(self):
        with self.database._connect() as raw:
            self.database._path(raw)
            raw.execute("INSERT INTO migrations VALUES(2,'application','unknown')")
        with self.assertRaises(PostgresFailure):PostgresRepository(self.database)
        with self.assertRaises(PostgresFailure):self.database.migrate()
    def test_migration_checksum_tamper_is_rejected(self):
        with self.database._connect() as raw:
            self.database._path(raw);raw.execute("UPDATE migrations SET checksum='tampered'")
        with self.assertRaises(PostgresFailure):PostgresRepository(self.database)
    def test_application_and_budget_schema_cannot_mix(self):
        with self.assertRaises(PostgresFailure):PostgresBudgetLedger(self.database)
    def test_unknown_schema_is_not_adopted(self):
        db=PostgresDatabase(DSN,'sb_unknown_'+secrets.token_hex(8),local_test=True)
        from psycopg import sql
        with db._connect() as raw:
            raw.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(db.schema)))
            db._path(raw);raw.execute('CREATE TABLE user_owned(id integer)')
        with self.assertRaises(PostgresFailure):db.migrate()
        with db._connect() as raw:
            db._path(raw);self.assertIsNotNone(raw.execute("SELECT to_regclass('user_owned') AS name").fetchone()['name'])

    def test_two_worker_processes_complete_once(self):
        self.setup_job()
        cmd=[sys.executable,'-B','-m','apps.api.workflow_worker','--data-dir',str(self.root),
             '--institution-id','A','--once','--postgres-local-test','--postgres-schema',self.database.schema]
        one=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        two=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        results=[one.communicate(timeout=30),two.communicate(timeout=30)]
        self.assertEqual(one.returncode,0,results[0][1]);self.assertEqual(two.returncode,0,results[1][1])
        self.assertEqual(sorted(r[0].strip() for r in results),['completed','idle'])
        self.assertEqual(len(self.rows('workflow_generations')),1)


# Reuse unchanged acceptance cases against a real PG repository, not copies of their assertions.
for name in ('normal_complete_atomic_components','same_input_deduplicated','claim_exclusive_and_fenced',
             'cancel_queued','cancel_processing_fences_worker','invalid_transitions','lease_expiry_recovery_and_old_worker',
             'renew_before_expiry','max_lease_attempts','retryable_failure_and_retry','permanent_failure_no_retry',
             'active_change_during_processing','deregister_during_processing','chunk_generation_during_processing'):
    setattr(PostgreSQLWorkflowTests,'test_reused_'+name,getattr(workflow_cases.WorkflowJobTests,'test_'+name))


@unittest.skipUnless(DSN, 'BLOCKED: isolated loopback PostgreSQL SB_PG_TEST_DSN not configured')
class PostgreSQLBudgetTests(unittest.TestCase):
    def setUp(self):
        self.database=database('budget');self.now=1000.0
        self.ledger=PostgresBudgetLedger(self.database,clock=lambda:self.now,ttl=2)
        self.ledger.provision(budget_cases.A,1000);self.ledger.open_job(budget_cases.A,'job',1000)
        self.r=budget_cases.Reservation(10,10,1_000_000,1_000_000,2,100)
    reserve=budget_cases.LedgerTests.reserve
    settled=budget_cases.LedgerTests.settled
    assert_account=budget_cases.LedgerTests.assert_account
    def test_reopen_uncertain_charge_and_reconcile(self):
        claim=self.reserve();self.ledger.start(budget_cases.A,claim);self.ledger.unknown(budget_cases.A,claim)
        reopened=PostgresBudgetLedger(self.database,clock=lambda:self.now)
        self.assertEqual(reopened.balance(budget_cases.A)['held'],20)
        reopened.reconcile(budget_cases.A,'request',4,2,budget_cases.H('receipt'))
        self.assertEqual(reopened.balance(budget_cases.A)['spent'],6)
    def test_event_failure_rollback(self):
        claim=self.reserve();n=self.ledger.start(budget_cases.A,claim)
        from apps.api.postgres import Connection
        original=Connection.execute
        def fail(connection,sql,args=()):
            if sql.startswith('INSERT INTO provider_budget_events'):raise PostgresFailure('injected')
            return original(connection,sql,args)
        with patch.object(Connection,'execute',fail),self.assertRaises(PostgresFailure):
            self.ledger.record(budget_cases.A,claim,n,3,2,budget_cases.H('receipt'))
        self.assert_account(40,0)

    def test_separate_process_reservation_has_one_owner(self):
        code = """import os,json
from apps.api.postgres import PostgresDatabase,PostgresBudgetLedger
from apps.api.models import Principal
from apps.api.provider_budget import Reservation
p=Principal('synthetic-process','A','worker')
d=PostgresDatabase(os.environ['SB_PG_TEST_DSN'],os.environ['SB_PG_SCHEMA'],local_test=True)
l=PostgresBudgetLedger(d)
c=l.reserve(p,'job','shared','a'*64,Reservation(10,10,1000000,1000000,2,100))
print(json.dumps({'owner':c is not None}))
"""
        env=dict(os.environ,SB_PG_SCHEMA=self.database.schema)
        processes=[subprocess.Popen([sys.executable,'-B','-c',code],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for _ in range(4)]
        answers=[]
        for proc in processes:
            out,err=proc.communicate(timeout=30);self.assertEqual(proc.returncode,0,err)
            answers.append(json.loads(out)['owner'])
        self.assertEqual(sum(answers),1);self.assert_account(40,0)

    def test_fake_gateway_uses_postgres_atomic_ledger(self):
        from apps.api.provider_safety import ProviderSettings, ProviderSafetyGateway, FakeTransport, approved_simulation_input
        settings=ProviderSettings(provider='openai',model='fake-model-v1',max_input_tokens=10,max_output_tokens=10,
                                  input_rate_micro=1000000,output_rate_micro=1000000,request_cap_micro=100)
        gateway=ProviderSafetyGateway(settings,self.ledger,FakeTransport([budget_cases.complete()]))
        payload='x'  # Synthetic payload within the existing conservative byte/token budget.
        gateway.invoke(budget_cases.A,'job','gateway','rag',payload,approved_simulation_input(budget_cases.A,payload),lambda value:value)
        self.assert_account(0,7)

for name in ('reserve_settle_release_balances','duplicate_reservation_has_no_second_owner',
             'changed_fingerprint_or_job_is_conflict','changed_rate_policy_duplicate_rejected',
             'settlement_and_finish_are_idempotent','conflicting_settlement_does_not_recharge',
             'pre_send_cancel_releases_all','cancel_after_send_retains_only_uncertain_attempt',
             'reconcile_known_usage_and_repeated_receipt','worker_cannot_authorize_reconciliation',
             'expired_inflight_recovers_as_uncertain','expired_unsent_reservation_is_released',
             'cancel_between_retries_keeps_known_spend','cancel_job_blocks_new_requests_and_preserves_unknown',
             'retry_attempt_count_does_not_multiply','usage_over_reservation_cannot_create_untracked_spend',
             'account_and_job_limits','cross_institution_read_cancel_settle_not_found',
             'same_request_ids_are_namespaced_by_tenant','reader_and_anonymous_budget_access_denied',
             'concurrent_duplicate_has_exactly_one_owner','competing_jobs_cannot_overspend_account',
             'parallel_settlement_charges_once'):
    setattr(PostgreSQLBudgetTests,'test_reused_'+name,getattr(budget_cases.LedgerTests,'test_'+name))

import test_auth as auth_cases
from apps.api.rag_service import RAGService
from apps.api.rag_adapters import DeterministicEmbedding, ExtractiveTestLLM


@unittest.skipUnless(DSN, 'BLOCKED: isolated loopback PostgreSQL SB_PG_TEST_DSN not configured')
class PostgreSQLAuthTests(unittest.TestCase):
    def setUp(self):
        self.database=database();self.pg_repo=PostgresRepository(self.database)
        mock=patch('apps.api.main.Repository',return_value=self.pg_repo);mock.start();self.addCleanup(mock.stop)
        auth_cases.AuthTests.setUp(self)
    tearDown=auth_cases.AuthTests.tearDown
    login=auth_cases.AuthTests.login
    headers=auth_cases.AuthTests.headers

for name in ('missing_auth_all_protected_routes','login_verified_identity_cookie_and_no_provider_tokens',
             'reader_cannot_mutate','cross_org_document_original_jobs_evidence','csrf_and_origin',
             'login_csrf_and_replay','expiry_and_idle','idle_expiry','logout_and_old_cookie_replay',
             'forged_and_duplicate_cookie','user_disabled','org_disabled',
             'membership_removed_and_sessions_revoked','membership_admin_scope','worker_and_org_injection_rejected',
             'self_admin_change_rejected','provider_exception_sanitized','unknown_identity_not_auto_provisioned',
             'login_rotation_and_repeat','validation_does_not_echo_password','login_throttle_and_challenge_expiry',
             'permission_rechecked_on_every_request','login_rotation_rejects_previous_sid'):
    setattr(PostgreSQLAuthTests,'test_reused_'+name,getattr(auth_cases.AuthTests,'test_'+name))


@unittest.skipUnless(DSN, 'BLOCKED: isolated loopback PostgreSQL SB_PG_TEST_DSN not configured')
class PostgreSQLRAGTests(unittest.TestCase):
    def setUp(self):
        PostgreSQLWorkflowTests.setUp(self)
        self.rag=RAGService(self.app.state.chunks,DeterministicEmbedding(),ExtractiveTestLLM())
    tearDown=PostgreSQLWorkflowTests.tearDown
    upload=PostgreSQLWorkflowTests.upload
    route=PostgreSQLWorkflowTests.route
    parse=PostgreSQLWorkflowTests.parse
    prepare=PostgreSQLWorkflowTests.prepare
    active=rag_cases.RAGTests.active

for name in ('index_idempotence','keyword_vector_hybrid_evidence','hwpx_original_resolution',
             'other_organization_and_missing_auth','reader_cannot_index_worker_cannot_search',
             'old_version_and_deregister_excluded','model_dimension_generation_swap','failed_embedding_keeps_previous_generation',
             'interrupted_embedding_retry','original_tampered_during_embedding','changed_source_during_embedding',
             'forged_vector_payload_rejected','forged_anchor_and_version_rejected','duplicate_results_rejected',
             'tampered_original_blocks_search','answer_contract_and_missing_llm','unknown_citation_and_invented_claim',
             'no_context_abstains','irrelevant_vectors_do_not_become_answer','new_chunk_generation_excludes_old_vectors',
             'deregister_during_generation','invalid_queries','real_providers_disabled'):
    setattr(PostgreSQLRAGTests,'test_reused_'+name,getattr(rag_cases.RAGTests,'test_'+name))
