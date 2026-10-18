"""Operational HTTP/configuration paths, using MockTransport and loopback DB only."""
import json
import os
from pathlib import Path
import secrets
import socket
import tempfile
import unittest
from unittest.mock import patch
import httpx
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr
from fastapi.testclient import TestClient
from apps.api.runtime_settings import load_settings,preflight,peer_issues,SettingsRejected,ensure_start_environment
from apps.api.operational_mapping import prepare_operational_adapters
from apps.api.provider_http import ProviderNetworkPolicy,SupabaseAuthHTTPTransport,SupabaseJWKSTransport
from apps.api.storage_http import SupabaseStorageHTTPTransport,StorageHTTPFailure
from apps.api.identity_provider import ProviderUnavailable
from apps.api.private_storage import object_path
from apps.api.migration_runner import MigrationRunner,MigrationBlocked,MigrationPlan
from apps.api.supabase_transport import SupabaseSettings
from apps.api.supabase_jwt import SupabaseJWTVerifier,JWTSettings
from apps.api.runtime_factory import build_runtime
from apps.api.main import create_app
from apps.api.auth import AuthSettings
from apps.api.auth_bootstrap import InitialAdministrator,bootstrap_initial_administrator,CONFIRMATION
from apps.api.session_revalidation import SessionRevalidation,FakeIdentityStatusTransport
import test_deployment_preflight as contracts
import test_deployment_auth as jwt
import test_storage_http as storage
import test_document_api as documents
DSN=os.environ.get('SB_PG_TEST_DSN')
PROJECT='https://'+'a'*20+'.supabase.co'


def env(**changes):
    data=contracts.production()
    data.update(DB_APPLICATION_SCHEMA='sb_operational_app',DB_BUDGET_SCHEMA='sb_operational_budget',
                STORAGE_GATEWAY_API_KEY='synthetic-public-gateway-not-real',SUPABASE_NETWORK_ENABLED='false')
    data.update(changes);return data


class HTTPPeer:
    def __init__(self):
        self.key=ec.generate_private_key(ec.SECP256R1());self.keys=[jwt.public_key(self.key)]
        self.token=jwt.sign(self.key);self.calls=[];self.auth_status=200;self.jwks_status=200
    def token_request(self,r):
        self.calls.append(r.method+' '+r.url.path)
        assert r.method=='POST' and r.url.path=='/auth/v1/token' and r.url.query==b'grant_type=password'
        return httpx.Response(self.auth_status,json={'token_type':'bearer','access_token':self.token,'expires_in':600,
                      'user':{'id':jwt.SUBJECTS[0],'user_metadata':{'role':'manager','institution_id':'FOREIGN'}}})
    def jwks_request(self,r):
        self.calls.append(r.method+' '+r.url.path)
        assert r.method=='GET' and r.url.path=='/auth/v1/.well-known/jwks.json'
        assert r.headers.get('authorization') is None and r.headers.get('cookie') is None
        return httpx.Response(self.jwks_status,json={'keys':self.keys})
    def bundle(self,settings=None,store=None):
        b=prepare_operational_adapters(settings or load_settings(env()),storage_mock=httpx.MockTransport(store or storage.ObjectServer()),
               auth_mock=httpx.MockTransport(self.token_request),jwks_mock=httpx.MockTransport(self.jwks_request))
        b.identity.verifier.clock=lambda:jwt.NOW
        return b


class OperationalTests(unittest.TestCase):
    def test_env_mapping_and_preparation_no_io(self):
        with patch.object(socket.socket,'connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')):
            b=prepare_operational_adapters(load_settings(env()))
        self.assertEqual(b.migration_plan.application_schema,'sb_operational_app')
        self.assertEqual(b.migration_plan.budget_schema,'sb_operational_budget')
        self.assertFalse(b.identity.available);self.assertFalse(b.diagnostics()['startup_allowed'])
    def test_missing_mapping_reports_precise_codes_and_startup_denies(self):
        result=preflight(contracts.production())
        self.assertIn('application_budget_schemas_required',result['operational_mapping_issues'])
        self.assertIn('storage_gateway_key_required',result['operational_mapping_issues'])
        with self.assertRaises(SettingsRejected):prepare_operational_adapters(load_settings(contracts.production()))
        with patch.dict(os.environ,contracts.production(),clear=True),self.assertRaises(SettingsRejected) as error:ensure_start_environment('api')
        self.assertIn('application_budget_schemas_required',error.exception.codes)
    def test_schema_key_and_approval_conflicts(self):
        for change in ({'DB_BUDGET_SCHEMA':'sb_operational_app'},{'DB_APPLICATION_SCHEMA':'auth'},
                       {'STORAGE_GATEWAY_API_KEY':'synthetic-storage-key-not-real'},
                       {'SUPABASE_NETWORK_ENABLED':'true'}):
            with self.subTest(change=change),self.assertRaises(SettingsRejected):prepare_operational_adapters(load_settings(env(**change)))
    def test_peer_compares_schema_and_gateway_settings(self):
        api=load_settings(env());worker=load_settings(env(APP_ROLE='parse_worker'))
        self.assertEqual(peer_issues(api,worker),[])
        other=load_settings(env(APP_ROLE='parse_worker',DB_BUDGET_SCHEMA='different_budget'))
        self.assertIn('api_worker_contract_mismatch',peer_issues(api,other))
    def test_local_rejects_production_mapping(self):
        for change in ({'DB_APPLICATION_SCHEMA':'some_schema'},{'SUPABASE_NETWORK_ENABLED':'true'}):
            self.assertFalse(preflight({'APP_ENV':'local',**change})['startup_allowed'])
    def test_production_remains_blocked_when_mapping_complete(self):
        p=preflight(env());self.assertEqual(p['operational_mapping_issues'],[])
        self.assertFalse(p['startup_allowed']);self.assertEqual(len(p['implementation_blockers']),6)
        with self.assertRaises(MigrationBlocked):MigrationRunner(prepare_operational_adapters(load_settings(env())).migration_plan)
    def test_unapproved_auth_and_storage_fail_before_client_creation(self):
        b=prepare_operational_adapters(load_settings(env()))
        with patch('httpx.Client',side_effect=AssertionError('must not build client')):
            with self.assertRaises(ProviderUnavailable):b.identity.authenticate('synthetic@example.test','synthetic')
            with self.assertRaises(StorageHTTPFailure):b.storage.get(b.storage_settings.bucket,storage.PATH)
    def test_policy_scope_and_mock_subclass_rejected(self):
        class MockSubclass(httpx.MockTransport):pass
        for mock in (object(),MockSubclass(lambda _:httpx.Response(200))):
            with self.assertRaises(SettingsRejected):prepare_operational_adapters(load_settings(env()),auth_mock=mock)
        with self.assertRaises(ProviderUnavailable):ProviderNetworkPolicy(project_url=PROJECT,service='storage').authorize(PROJECT,'auth',None)
    def test_partial_mock_selection_cannot_mix_live_and_test_paths(self):
        with self.assertRaises(SettingsRejected) as error:
            prepare_operational_adapters(load_settings(env()),auth_mock=httpx.MockTransport(lambda _:httpx.Response(200)))
        self.assertIn('partial_mock_transports_forbidden',error.exception.codes)

    def test_disabled_approval_reference_does_not_grant_network(self):
        b=prepare_operational_adapters(load_settings(env(SUPABASE_APPROVAL_REF='SYNTHETIC_REFERENCE_ONLY')))
        self.assertFalse(b.storage.network_selected)
        with self.assertRaises(ProviderUnavailable):b.identity.authenticate('synthetic@example.test','synthetic')
    def test_mock_success_verifies_signature_and_metadata_not_authority(self):
        peer=HTTPPeer();b=peer.bundle()
        with patch.object(socket.socket,'connect',side_effect=AssertionError('network')):
            identity=b.identity.authenticate('synthetic@example.test','synthetic')
        self.assertEqual(identity.subject,jwt.SUBJECTS[0]);self.assertEqual(identity.issuer,jwt.ISSUER)
        self.assertFalse(hasattr(identity,'role'));self.assertFalse(b.identity.remote_enabled)
    def test_http_key_rotation_and_forgery(self):
        peer=HTTPPeer();b=peer.bundle();b.identity.authenticate('synthetic@example.test','synthetic')
        other=ec.generate_private_key(ec.SECP256R1());peer.token=jwt.sign(other)
        with self.assertRaises(ProviderUnavailable):b.identity.authenticate('synthetic@example.test','synthetic')
        peer.keys=[jwt.public_key(other)]
        self.assertEqual(b.identity.authenticate('synthetic@example.test','synthetic').subject,jwt.SUBJECTS[0])
    def test_expired_wrong_issuer_audience_rejected(self):
        peer=HTTPPeer();b=peer.bundle()
        for fields in ({'exp':jwt.NOW},{'iss':'https://untrusted.invalid/auth/v1'},{'aud':'wrong'}):
            peer.token=jwt.sign(peer.key,jwt.claims(**fields))
            with self.subTest(fields=fields),self.assertRaises(ProviderUnavailable):b.identity.authenticate('synthetic@example.test','synthetic')
    def test_auth_and_jwks_provider_failures(self):
        for status in (401,429,503,302):
            peer=HTTPPeer();b=peer.bundle();peer.auth_status=status
            with self.subTest(stage='token',status=status),self.assertRaises(ProviderUnavailable):b.identity.authenticate('synthetic@example.test','synthetic')
            peer.auth_status=200;peer.jwks_status=status
            with self.subTest(stage='jwks',status=status),self.assertRaises(ProviderUnavailable):b.identity.authenticate('synthetic@example.test','synthetic')
    def test_jwks_timeout_oversize_bad_json_and_redirect_no_retry(self):
        settings=SupabaseSettings(PROJECT,env()['SUPABASE_AUTH_API_KEY']);policy=ProviderNetworkPolicy(project_url=PROJECT,service='auth')
        for response in (httpx.Response(200,content=b'x'*65537,headers={'content-type':'application/json'}),
                         httpx.Response(200,content=b'invalid',headers={'content-type':'application/json'}),
                         httpx.Response(302,headers={'location':'https://evil.invalid'})):
            calls=[]
            def handler(r):calls.append(r);return response
            t=SupabaseJWKSTransport(settings,policy=policy,mock_transport=httpx.MockTransport(handler))
            verifier=SupabaseJWTVerifier(JWTSettings(issuer=settings.issuer),t,clock=lambda:jwt.NOW)
            with self.assertRaises(ProviderUnavailable):verifier.verify(HTTPPeer().token)
            self.assertEqual(len(calls),1)
        def timeout(_):raise httpx.ReadTimeout('synthetic-secret-never-log')
        t=SupabaseJWKSTransport(settings,policy=policy,mock_transport=httpx.MockTransport(timeout))
        with self.assertRaises(ProviderUnavailable) as error:t.request(settings.issuer,'/auth/v1/.well-known/jwks.json')
        self.assertIsNone(error.exception.__context__)
    def test_no_jwt_or_secret_log_leak(self):
        peer=HTTPPeer();b=peer.bundle()
        with self.assertLogs('httpx',level='INFO') as captured:b.identity.authenticate('synthetic@example.test','synthetic-password-marker')
        logged='\n'.join(captured.output)
        for value in (peer.token,env()['SUPABASE_AUTH_API_KEY'],'synthetic-password-marker'):self.assertNotIn(value,logged)
        self.assertNotIn(env()['STORAGE_SERVER_KEY'],repr(b))
    def test_policy_replacement_cannot_enable_real_client(self):
        peer=HTTPPeer();b=peer.bundle()
        b.identity.transport.policy=object()
        with patch('httpx.Client',side_effect=AssertionError('no client')),self.assertRaises(ProviderUnavailable):
            b.identity.authenticate('synthetic@example.test','synthetic')
        keys=b.identity.verifier.transport;keys.policy=object()
        with patch('httpx.Client',side_effect=AssertionError('no client')),self.assertRaises(ProviderUnavailable):
            keys.request(jwt.ISSUER,'/auth/v1/.well-known/jwks.json')

    def test_storage_protocol_reuse_and_uncertain_upload(self):
        peer=storage.ObjectServer();peer.timeout_after=True;b=HTTPPeer().bundle(store=peer)
        b.storage.put_if_absent(b.storage_settings.bucket,storage.PATH,b'synthetic original')
        b.storage.put_if_absent(b.storage_settings.bucket,storage.PATH,b'synthetic original')
        self.assertEqual(peer.methods.count('POST'),1)
        with self.assertRaises(StorageHTTPFailure):b.storage.get('foreign-bucket',storage.PATH)
        with self.assertRaises(StorageHTTPFailure):b.storage.list_page(b.storage_settings.bucket,'',0,100)
    def test_worker_mapping_does_not_construct_browser_provider(self):
        b=prepare_operational_adapters(load_settings(env(APP_ROLE='parse_worker')))
        self.assertFalse(b.identity.available)
        with self.assertRaises(SettingsRejected):prepare_operational_adapters(load_settings(env(APP_ROLE='parse_worker')),auth_mock=httpx.MockTransport(lambda _:httpx.Response(200)))
    def test_selected_live_policy_rejected_by_local_factory_before_db(self):
        b=prepare_operational_adapters(load_settings(env(SUPABASE_NETWORK_ENABLED='true',SUPABASE_APPROVAL_REF='SYNTHETIC_TEST_DO_NOT_CALL')))
        from apps.api.postgres import PostgresDatabase
        with patch.object(PostgresDatabase,'_connect',side_effect=AssertionError('no network')),self.assertRaises(ValueError):
            build_runtime(Path('work/not-created-live-policy'),private_settings=b.storage_settings,storage_transport=b.storage)


@unittest.skipUnless(DSN,'BLOCKED isolated local PostgreSQL unavailable')
class OperationalPostgreSQLTests(unittest.TestCase):
    def setUp(self):
        Path('work/operational-code-tests').mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='work/operational-code-tests');self.root=Path(self.tmp.name)
        self.peer=HTTPPeer();self.bundle=self.peer.bundle()
        suffix=secrets.token_hex(6)
        self.plan=MigrationPlan(database_url=SecretStr(DSN),application_schema='sb_live_app_'+suffix,budget_schema='sb_live_budget_'+suffix)
        guard=SessionRevalidation(FakeIdentityStatusTransport({(jwt.ISSUER,jwt.SUBJECTS[0]):'active'}))
        self.binding=build_runtime(self.root,postgres_plan=self.plan,migration_mode='apply',
                private_settings=self.bundle.storage_settings,storage_transport=self.bundle.storage,
                identity_provider=self.bundle.identity,session_guard=guard,auth_settings=AuthSettings(origin='https://app.synthetic.example'))
        user=bootstrap_initial_administrator(self.binding.repo.auth_store(),InitialAdministrator(issuer=jwt.ISSUER,subject=jwt.SUBJECTS[0],institution_id='A',institution_name='synthetic institution'),confirmation=CONFIRMATION)
        self.user=user['user_id'];self.app=create_app(runtime_binding=self.binding,parsing_enabled=True,auth_clock=lambda:jwt.NOW)
        self.client=TestClient(self.app,base_url='https://app.synthetic.example');self.client.__enter__()
    def tearDown(self):self.client.__exit__(None,None,None);self.tmp.cleanup()
    def login(self):
        h={'Origin':'https://app.synthetic.example'}
        csrf=self.client.post('/auth/csrf',headers=h).json()['csrf_token']
        r=self.client.post('/auth/login',headers={**h,'X-CSRF-Token':csrf},json={'email':'synthetic@example.test','password':'synthetic'})
        self.assertEqual(r.status_code,200,r.text);return {**h,'X-CSRF-Token':r.json()['csrf_token']}
    def test_cookie_csrf_original_and_logout(self):
        h=self.login()
        bad=self.client.post('/documents?filename=x.pdf',content=documents.pdf(),headers={**h,'Origin':'https://evil.invalid','Content-Type':'application/pdf','X-Data-Classification':'synthetic'})
        self.assertEqual(bad.status_code,403)
        r=self.client.post('/documents?filename=x.pdf',content=documents.pdf(),headers={**h,'Content-Type':'application/pdf','X-Data-Classification':'synthetic'})
        self.assertEqual(r.status_code,201,r.text);m=r.json()['document']
        self.assertEqual(self.client.get(f"/documents/{m['document_id']}/versions/{m['id']}/original").content,documents.pdf())
        self.assertEqual(self.client.post('/auth/logout',headers=h).status_code,200)
        self.assertEqual(self.client.get('/documents').status_code,401)
    def test_membership_role_change_overrides_provider_metadata(self):
        h=self.login()
        with self.binding.repo.auth_store().transaction() as db:db.execute("UPDATE memberships SET role='reader',institution_admin=0 WHERE user_id=?",(self.user,))
        r=self.client.post('/documents?filename=x.pdf',content=documents.pdf(),headers={**h,'Content-Type':'application/pdf','X-Data-Classification':'synthetic'})
        self.assertEqual(r.status_code,403)
        with self.binding.repo.auth_store().transaction() as db:db.execute('UPDATE memberships SET active=0 WHERE user_id=?',(self.user,))
        self.assertEqual(self.client.get('/documents').status_code,401)
    def test_cross_institution_block_and_worker_evidence_pipeline(self):
        self.login()
        from apps.api.models import Principal
        foreign=Principal('synthetic-other','B','manager')
        m=self.binding.documents().register(foreign,'foreign.pdf','application/pdf',documents.pdf())[0]
        base=f"/documents/{m['document_id']}/versions/{m['id']}"
        for path in ('','/original','/chunks','/workflow/candidates'):self.assertEqual(self.client.get(base+path).status_code,404)
        worker=self.binding.worker('parse_worker').worker_service()
        p=Principal('synthetic-worker','B','worker');self.assertEqual(worker.execute(p,worker.claim(p)),'completed')
