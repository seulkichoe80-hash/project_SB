"""Real loopback PostgreSQL startup/migration; provider I/O remains disabled."""
import concurrent.futures
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pydantic import SecretStr
from fastapi.testclient import TestClient
from apps.api.migration_runner import MigrationPlan, MigrationRunner, MigrationBlocked
from apps.api.runtime_factory import build_runtime, build_application
from apps.api.runtime_settings import RuntimeSettings, SettingsRejected, PRODUCTION_BLOCKERS
from apps.api.runtime_wiring import compare_bindings
from apps.api.postgres import PostgresDatabase, PostgresRepository, PostgresBudgetLedger, Connection
from apps.api.private_storage import PrivateStorageSettings, FakeStorageTransport
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.service import now
import test_document_api as documents
import test_private_storage as storage_cases
import test_deployment_preflight as preflight_cases

DSN=os.environ.get('SB_PG_TEST_DSN')
A=Principal('synthetic-factory-manager','A','manager')
B=Principal('synthetic-factory-other','B','manager')


def plan(**changes):
    suffix=secrets.token_hex(6)
    data={'database_url':SecretStr(DSN or 'postgresql://postgres@127.0.0.1:55432/sb_test'),
          'application_schema':'sb_factory_app_'+suffix,'budget_schema':'sb_factory_budget_'+suffix}
    data.update(changes)
    return MigrationPlan(**data)


class FactorySafetyTests(unittest.TestCase):
    def setUp(self):
        Path('work/runtime-factory-tests').mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='work/runtime-factory-tests');self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_sqlite_default_api_and_workers(self):
        api=build_runtime(self.root)
        for role in ('parse_worker','chunk_worker','workflow_worker'):
            w=build_runtime(self.root,role=role)
            self.assertEqual(compare_bindings(api,w),[]);self.assertIsNotNone(w.worker_service())
        self.assertFalse(api.provider.available)
    def test_application_factory_denies_anonymous(self):
        app=build_application(self.root)
        self.assertIsNotNone(app.state.runtime_binding)
        with TestClient(app) as client:self.assertEqual(client.get('/documents').status_code,401)
    def test_standard_api_uses_validated_origin_and_rejects_other_origin(self):
        from apps.api.main import create_app
        with patch.dict(os.environ,{'APP_ORIGIN':'https://configured.example'}):
            app=create_app(self.root)
        self.assertEqual(app.state.auth.settings.origin,'https://configured.example')
        with TestClient(app,base_url='https://configured.example') as client:
            self.assertEqual(client.post('/auth/csrf',headers={'Origin':'https://configured.example'}).status_code,200)
            self.assertEqual(client.post('/auth/csrf',headers={'Origin':'https://localhost'}).status_code,403)

    def test_settings_role_mismatch_before_files(self):
        with self.assertRaises(SettingsRejected):build_runtime(self.root/'untouched',role='workflow_worker',settings=RuntimeSettings(role='api'))
        self.assertFalse((self.root/'untouched').exists())
    def test_production_blocks_before_connect(self):
        from apps.api.runtime_settings import load_settings
        # Existing test's complete synthetic settings, not real credentials.
        settings=load_settings(preflight_cases.production())
        with patch.object(PostgresDatabase,'_connect',side_effect=AssertionError('no network')):
            with self.assertRaises(SettingsRejected) as error:build_runtime(self.root,settings=settings)
        self.assertTrue(set(PRODUCTION_BLOCKERS)<=set(error.exception.codes))
    def test_remote_migration_plan_blocked_before_socket(self):
        for p in (plan(target='production'),plan(database_url=SecretStr('postgresql://fake:fake@unapproved.invalid/db'))):
            with patch.object(socket.socket,'connect',side_effect=AssertionError('network')):
                with self.assertRaises(MigrationBlocked):MigrationRunner(p)
    def test_unsafe_same_reserved_or_tampered_schema(self):
        for change in ({'application_schema':'public'},{'budget_schema':'pg_bad'}, {'application_schema':'same','budget_schema':'same'}):
            with self.assertRaises(ValueError):plan(**change)
        broken=plan().model_copy(update={'budget_schema':'public'})
        with self.assertRaises(MigrationBlocked):MigrationRunner(broken)
    def test_bad_injected_settings_no_database_side_effects(self):
        with patch.object(PostgresDatabase,'_connect',side_effect=AssertionError('network')):
            for kwargs in ({'storage_transport':object()},{'identity_provider':object()},
                           {'private_settings':storage_cases.settings(),'storage_transport':FakeStorageTransport(private=False)}):
                with self.subTest(keys=list(kwargs)),self.assertRaises(ValueError):build_runtime(self.root,postgres_plan=plan(),migration_mode='apply',**kwargs)
    def test_worker_auth_injection_rejected_before_files(self):
        with self.assertRaises(ValueError):build_runtime(self.root/'missing',role='parse_worker',proxy_policy=object())
        self.assertFalse((self.root/'missing').exists())
    def test_unknown_migration_policy_rejected(self):
        with self.assertRaises(ValueError):build_runtime(self.root,migration_mode='apply')
    def test_mock_http_factory_injection_without_credentials(self):
        from test_storage_http import transport
        peer=transport()
        api=build_runtime(self.root,private_settings=storage_cases.settings(),storage_transport=peer)
        worker=api.worker('parse_worker')
        self.assertEqual(compare_bindings(api,worker),[])
        self.assertIsNotNone(worker.worker_service())
    def test_cli_errors_redacted(self):
        from scripts.validation.runtime_migrate import main
        with patch.dict(os.environ,{'SB_PG_TEST_DSN':'postgresql://private-password@remote.invalid/db'}):
            out=io.StringIO()
            with redirect_stdout(out):result=main(['--application-schema','sb_app','--budget-schema','sb_budget','--mode','apply'])
        self.assertEqual(result,1);self.assertNotIn('private-password',out.getvalue());self.assertIn('BLOCKED',out.getvalue())
    def test_plan_and_runner_repr_redacted(self):
        p=plan();self.assertNotIn(p.database_url.get_secret_value(),repr(p))
        self.assertNotIn(p.database_url.get_secret_value(),repr(MigrationRunner(p)))


@unittest.skipUnless(DSN,'BLOCKED: isolated loopback PostgreSQL unavailable')
class PostgreSQLFactoryTests(unittest.TestCase):
    def setUp(self):
        Path('work/runtime-factory-tests').mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='work/runtime-factory-tests');self.root=Path(self.tmp.name)
        self.plan=plan();self.runner=MigrationRunner(self.plan)
    def tearDown(self):self.tmp.cleanup()
    def test_standard_api_repository_constructor_injection_is_preserved(self):
        from apps.api.main import create_app
        self.runner.run(mode='apply')
        repo=PostgresRepository(self.runner.application)
        with patch('apps.api.main.Repository',return_value=repo):app=create_app(self.root)
        self.assertIs(app.state.service.repo,repo)
        self.assertIs(app.state.runtime_binding.repo,repo)

    def test_new_apply_reapply_and_verify(self):
        first=self.runner.run(mode='apply');self.assertEqual([s['applied'] for s in first['steps']],[True]*3)
        self.assertEqual([s['applied'] for s in self.runner.run(mode='apply')['steps']],[False]*3)
        self.assertEqual(self.runner.run()['status'],'READY')
    def test_verify_on_empty_database_never_creates_schema(self):
        with self.assertRaises(MigrationBlocked) as error:self.runner.run()
        self.assertEqual(error.exception.stage,'application')
        with self.runner.application._connect() as db:
            self.assertIsNone(db.execute('SELECT schema_name FROM information_schema.schemata WHERE schema_name=%s',(self.plan.application_schema,)).fetchone())
    def test_concurrent_apply_serializes_all_three_steps(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            results=list(pool.map(lambda _:MigrationRunner(self.plan).run(mode='apply'),range(3)))
        self.assertEqual(sum(sum(s['applied'] for s in r['steps']) for r in results),3)
        self.assertEqual(self.runner.run()['status'],'READY')
    def test_failure_budget_phase_resumes_without_dropping_application(self):
        original=PostgresDatabase.migrate
        def fail(db,kind='application'):
            if kind=='budget':raise RuntimeError('synthetic-secret-not-to-be-logged')
            return original(db,kind)
        with patch.object(PostgresDatabase,'migrate',fail),self.assertRaises(MigrationBlocked) as error:self.runner.run(mode='apply')
        self.assertEqual(error.exception.stage,'budget');self.assertNotIn('synthetic-secret',str(error.exception));self.assertIsNone(error.exception.__context__)
        self.runner.application.verify('application')
        self.assertEqual([s['applied'] for s in self.runner.run(mode='apply')['steps']],[False,True,True])
    def test_partial_storage_failure_rolls_back_only_that_step(self):
        original=Connection.execute
        def fail(db,sql,args=()):
            if sql.strip().startswith('CREATE TABLE private_storage_restores'):raise RuntimeError('synthetic')
            return original(db,sql,args)
        with patch.object(Connection,'execute',fail),self.assertRaises(MigrationBlocked) as error:self.runner.run(mode='apply')
        self.assertEqual(error.exception.stage,'storage')
        with self.runner.application.transaction() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=? AND table_name='private_storage_schema'",(self.plan.application_schema,)).fetchone()[0],0)
        self.assertEqual([s['applied'] for s in self.runner.run(mode='apply')['steps']],[False,False,True])
    def test_existing_checksum_rejected_without_overwrite(self):
        self.runner.run(mode='apply')
        with self.runner.budget.transaction() as db:db.execute('UPDATE migrations SET checksum=?',('0'*64,))
        with self.assertRaises(MigrationBlocked) as error:self.runner.run(mode='apply')
        self.assertEqual(error.exception.stage,'budget')
        self.assertEqual(error.exception.code,'postgres_migration_version_mismatch')
        with self.runner.budget.transaction() as db:self.assertEqual(db.execute('SELECT checksum FROM migrations').fetchone()[0],'0'*64)
    def test_storage_checksum_rejected_on_verify(self):
        self.runner.run(mode='apply')
        with self.runner.application.transaction() as db:db.execute('UPDATE private_storage_schema SET checksum=?',('0'*64,))
        with self.assertRaises(MigrationBlocked) as error:self.runner.run()
        self.assertEqual(error.exception.stage,'storage')
    def test_application_worker_budget_and_data_survive_restart(self):
        api=build_runtime(self.root,postgres_plan=self.plan,migration_mode='apply')
        doc=api.documents().register(A,'synthetic.pdf','application/pdf',documents.pdf())[0]
        api.budget_ledger.provision(A,1000);api.budget_ledger.open_job(A,'synthetic-job',100)
        from apps.api.provider_budget import Reservation
        api.budget_ledger.reserve(A,'synthetic-job','synthetic-request','a'*64,Reservation(10,10,1000000,1000000,2,100))
        self.runner.run(mode='apply')
        worker=build_runtime(self.root,role='parse_worker',postgres_plan=self.plan,api_peer=api)
        self.assertEqual(compare_bindings(api,worker),[])
        body,_=worker.documents().original(A,doc['document_id'],doc['id']);self.assertEqual(body,documents.pdf())
        with self.assertRaises(DomainError):worker.documents().original(B,doc['document_id'],doc['id'])
        self.assertEqual(worker.budget_ledger.balance(A)['cap'],1000)
        self.assertEqual(worker.budget_ledger.balance(A)['held'],40)
        with self.assertRaises(DomainError):worker.budget_ledger.balance(B)
    def test_factory_worker_entrypoints_process_real_document_pipeline(self):
        from apps.api.worker import main as parse
        from apps.api.chunk_worker import main as chunk
        from apps.api.workflow_worker import main as workflow
        from apps.api.parsing_service import ParsingService
        from apps.api.chunk_service import ChunkService
        from apps.api.chunking import ChunkConfig
        from apps.api.workflow_jobs import WorkflowJobService
        api=build_runtime(self.root,postgres_plan=self.plan,migration_mode='apply')
        docs=api.documents();meta=docs.register(A,'synthetic.pdf','application/pdf',documents.pdf())[0]
        args=['--data-dir',str(self.root),'--institution-id','A','--once']
        with redirect_stdout(io.StringIO()):self.assertEqual(parse(args,runtime_binding=api.worker('parse_worker')),0)
        chunks=ChunkService(ParsingService(docs));chunks.enqueue(A,meta['document_id'],meta['id'],ChunkConfig())
        with redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as result:chunk(args,runtime_binding=api.worker('chunk_worker'))
        self.assertEqual(result.exception.code,0)
        docs.activate(A,meta['document_id'],meta['id'])
        service=WorkflowJobService(chunks);job=service.enqueue(A,meta['document_id'],meta['id'])
        with redirect_stdout(io.StringIO()):self.assertEqual(workflow(args,runtime_binding=api.worker('workflow_worker')),0)
        self.assertEqual(service.status(A,meta['document_id'],meta['id'],job['id'])['state'],'completed')

    def test_concurrent_factory_initialization(self):
        def create(role):return build_runtime(self.root,role=role,postgres_plan=self.plan,migration_mode='apply')
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:api,worker=list(pool.map(create,['api','parse_worker']))
        self.assertEqual(compare_bindings(api,worker),[])
    def test_different_budget_schema_blocked(self):
        api=build_runtime(self.root,postgres_plan=self.plan,migration_mode='apply')
        other=plan(application_schema=self.plan.application_schema)
        with patch.object(PostgresDatabase,'_connect',side_effect=AssertionError('no DB before consistency check')):
            with self.assertRaises(ValueError):
                build_runtime(self.root,role='parse_worker',postgres_plan=other,migration_mode='apply',api_peer=api)
    def test_default_startup_verify_does_not_auto_apply(self):
        with self.assertRaises(MigrationBlocked):build_runtime(self.root,postgres_plan=self.plan)
    def test_initial_administrator_and_membership_preserved(self):
        from apps.api.auth_bootstrap import InitialAdministrator,bootstrap_initial_administrator,CONFIRMATION
        self.runner.run(mode='apply');store=PostgresRepository(self.runner.application).auth_store()
        request=InitialAdministrator(issuer='https://'+'a'*20+'.supabase.co/auth/v1',subject='11111111-1111-4111-8111-111111111111',institution_id='A',institution_name='synthetic institution')
        result=bootstrap_initial_administrator(store,request,confirmation=CONFIRMATION)
        self.runner.run(mode='apply')
        with store.transaction() as db:
            row=db.execute('SELECT role,active,institution_admin FROM memberships WHERE user_id=?',(result['user_id'],)).fetchone()
            self.assertEqual(tuple(row),('manager',1,1))
    def test_runner_cli_real_local_apply_and_verify(self):
        command=[sys.executable,'-B','scripts/validation/runtime_migrate.py','--application-schema',self.plan.application_schema,'--budget-schema',self.plan.budget_schema]
        env={**os.environ,'SB_PG_TEST_DSN':DSN}
        for mode in ('apply','verify'):
            result=subprocess.run(command+['--mode',mode],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout);self.assertEqual(json.loads(result.stdout)['status'],'READY')
