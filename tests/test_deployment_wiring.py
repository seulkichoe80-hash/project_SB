"""Local/Fake composition and sanitized /api boundary, including real loopback PG when configured."""
import asyncio
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import create_app
from apps.api.auth import AuthSettings
from apps.api.proxy_boundary import ProxyPolicy,ProxyBoundary,OfflineSameOriginProxy
from apps.api.runtime_wiring import RuntimeBinding,compare_bindings
from apps.api.session_revalidation import FakeIdentityStatusTransport,SessionRevalidation
from apps.api.private_storage import PrivateOriginalStore,PrivateStorageSettings,FakeStorageTransport
from apps.api.repository import Repository
from apps.api.storage import LocalOriginalStore
from apps.api.formats import MAX_BYTES
from apps.api.identity_provider import UnconfiguredProvider
from apps.api.supabase_jwt import FakeCredential,FakeTokenTransport,FakeJWKSTransport,JWTSettings,SupabaseJWTVerifier,SupabaseJWTProviderAdapter
from test_deployment_auth import ISSUER,SUBJECTS,NOW,PASSWORD,sign,claims,public_key
from cryptography.hazmat.primitives.asymmetric import ec
from test_document_api import pdf

PROOF='synthetic-local-proxy-proof-not-a-service-key-123'
DSN=os.environ.get('SB_PG_TEST_DSN')


def policy(origin='https://local.test',**changes):
    return ProxyPolicy(origin=origin,backend_host='backend.test',trusted_peer_cidrs=('127.0.0.1/32',),shared_token=PROOF,**changes)


async def echo(scope,receive,send):
    if scope['type']!='http':
        while True:
            m=await receive()
            await send({'type':'lifespan.startup.complete' if m['type']=='lifespan.startup' else 'lifespan.shutdown.complete'})
            if m['type']=='lifespan.shutdown':return
    h=dict(scope['headers']);body=b''
    while True:
        msg=await receive();body+=msg.get('body',b'')
        if not msg.get('more_body',False):break
    path=scope['path'];headers=[(b'content-type',b'application/json')];status=200
    if path=='/redirect':status=307;headers.append((b'location',b'/documents'))
    if path=='/external':status=302;headers.append((b'location',b'https://forbidden.invalid/'))
    if path=='/cookies':headers.extend([(b'set-cookie',b'a=1; Path=/; Secure; HttpOnly; SameSite=Lax'),(b'set-cookie',b'b=2; Path=/; Secure; HttpOnly; SameSite=Lax')])
    if path=='/slow':await asyncio.sleep(2)
    payload=json.dumps({'path':path,'scheme':scope['scheme'],'host':h.get(b'host',b'').decode(),'client':scope['client'][0],
        'size':len(body),'authorization_forwarded':h.get(b'authorization')==b'synthetic-auth-marker',
        'cookie_forwarded':b'cookie' in h,'csrf_forwarded':h.get(b'x-csrf-token')==b'synthetic-csrf',
        'proxy_secret_present':b'x-sb-proxy-token' in h,'forwarded_present':any(k.startswith(b'x-forwarded-') for k in h)}).encode()
    await send({'type':'http.response.start','status':status,'headers':headers});await send({'type':'http.response.body','body':payload})


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.p=policy();self.backend=ProxyBoundary(echo,self.p)
        self.edge=OfflineSameOriginProxy(self.backend,self.p)
        self.c=TestClient(self.edge,base_url='https://local.test',client=('127.0.0.2',10))
    def tearDown(self):self.c.close()
    def direct(self,**changes):
        h={'X-Forwarded-Host':'local.test','X-Forwarded-Proto':'https','X-Forwarded-For':'127.0.0.2','X-SB-Proxy-Token':PROOF,**changes}
        return h
    def test_prefix_https_auth_cookie_csrf_and_secret_stripping(self):
        r=self.c.get('/api/inspect',headers={'Authorization':'synthetic-auth-marker','Cookie':'synthetic=x','X-CSRF-Token':'synthetic-csrf'})
        self.assertEqual(r.status_code,200);v=r.json();self.assertEqual((v['path'],v['scheme'],v['host']),('/inspect','https','local.test'))
        self.assertTrue(v['authorization_forwarded'] and v['cookie_forwarded'] and v['csrf_forwarded'])
        self.assertFalse(v['proxy_secret_present'] or v['forwarded_present'])
    def test_client_forwarded_spoof_sanitized(self):
        r=self.c.get('/api/inspect',headers={'X-Forwarded-For':'192.0.2.1','X-Forwarded-Host':'evil.invalid','X-Forwarded-Proto':'http','Forwarded':'for=evil','X-SB-Proxy-Token':'wrong'})
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['client'],'127.0.0.2')
    def test_backend_requires_peer_and_proof(self):
        for peer,proof in (('127.0.0.3',PROOF),('127.0.0.1','wrong')):
            with TestClient(self.backend,base_url='http://backend.test',client=(peer,5)) as c:self.assertEqual(c.get('/inspect',headers=self.direct(**{'X-SB-Proxy-Token':proof})).status_code,403)
    def test_bad_forwarded_host_proto_chain(self):
        with TestClient(self.backend,base_url='http://backend.test',client=('127.0.0.1',5)) as c:
            for change in ({'X-Forwarded-Host':'evil.invalid'},{'X-Forwarded-Proto':'http'},{'X-Forwarded-For':'127.0.0.1, 192.0.2.1'},{'Forwarded':'for=evil'}):
                self.assertEqual(c.get('/inspect',headers=self.direct(**change)).status_code,400)
    def test_public_host_http_and_prefix_rejected(self):
        self.assertEqual(self.c.get('/api/inspect',headers={'Host':'evil.invalid'}).status_code,400)
        self.assertEqual(self.c.get('/apievil/inspect').status_code,404)
        with TestClient(self.edge,base_url='http://local.test',client=('127.0.0.2',5)) as c:self.assertEqual(c.get('/api/inspect').status_code,400)
    def test_cross_origin_and_missing_mutation_origin(self):
        for h in ({},{'Origin':'https://evil.invalid'},{'Origin':self.p.origin,'Sec-Fetch-Site':'cross-site'}):self.assertEqual(self.c.post('/api/inspect',headers=h).status_code,403)
        self.assertEqual(self.c.post('/api/inspect',headers={'Origin':self.p.origin},content=b'x').status_code,200)
    def test_no_public_cors(self):
        r=self.c.options('/api/inspect',headers={'Origin':'https://evil.invalid','Access-Control-Request-Method':'POST'})
        self.assertEqual(r.status_code,403);self.assertNotIn('access-control-allow-origin',r.headers)
    def test_duplicate_security_headers_rejected(self):
        r=self.c.get('/api/inspect',headers=[('Host','local.test'),('Host','evil.invalid')]);self.assertNotEqual(r.status_code,200)
    def test_redirect_no_follow_and_prefix_rewrite(self):
        r=self.c.get('/api/redirect',follow_redirects=False);self.assertEqual(r.status_code,307);self.assertEqual(r.headers['location'],'/api/documents')
        self.assertEqual(self.c.get('/api/external',follow_redirects=False).status_code,502)
    def test_multiple_cookie_headers_preserved(self):self.assertEqual(len(self.c.get('/api/cookies').headers.get_list('set-cookie')),2)
    def test_upload_exact_20mib_and_one_over(self):
        data=b'x'*MAX_BYTES;r=self.c.post('/api/inspect',headers={'Origin':self.p.origin},content=data)
        self.assertEqual(r.status_code,200);self.assertEqual(r.json()['size'],MAX_BYTES)
        self.assertEqual(self.c.post('/api/inspect',headers={'Origin':self.p.origin},content=data+b'x').status_code,413)
    def test_unknown_length_stream_limit_and_framing(self):
        p=policy(max_bytes=5)
        with TestClient(OfflineSameOriginProxy(ProxyBoundary(echo,p),p),base_url=p.origin,client=('127.0.0.2',5)) as c:
            self.assertEqual(c.post('/api/inspect',headers={'Origin':p.origin},content=iter([b'abc',b'def'])).status_code,413)
            self.assertNotEqual(c.post('/api/inspect',headers={'Origin':p.origin,'Content-Length':'bad'},content=b'a').status_code,200)
    def test_rate_limit_and_deadline(self):
        p=policy(requests_per_minute=2,timeout_seconds=1)
        with TestClient(OfflineSameOriginProxy(ProxyBoundary(echo,p),p),base_url=p.origin,client=('127.0.0.2',5)) as c:
            self.assertEqual(c.get('/api/slow').status_code,504)
            self.assertEqual(c.get('/api/inspect').status_code,200)
            r=c.get('/api/inspect');self.assertEqual(r.status_code,429);self.assertIn('retry-after',r.headers)
    def test_policy_no_wildcard_http_or_unbounded_limit(self):
        from pydantic import ValidationError
        base=self.p.model_dump()
        for change in ({'origin':'http://local.test'},{'trusted_peer_cidrs':('0.0.0.0/0',)},{'shared_token':'short'},{'max_bytes':MAX_BYTES+1},{'backend_host':'backend.test:99999'}):
            with self.assertRaises(ValidationError):ProxyPolicy(**(base|change))


def synthetic_binding(root,repo=None,origin='https://local.test'):
    repo=repo or Repository(root/'metadata.sqlite3');key=ec.generate_private_key(ec.SECP256R1())
    jwks=FakeJWKSTransport(ISSUER,{'keys':[public_key(key)]});tokens=[];records=[]
    for i in range(2):
        token=sign(key,claims(sub=SUBJECTS[i]));tokens.append(token)
        records.append(FakeCredential(f'user{i}@synthetic.invalid',PASSWORD,{'access_token':token,'expires_in':600,'token_type':'bearer','user':{'id':SUBJECTS[i]}}))
    provider=SupabaseJWTProviderAdapter(FakeTokenTransport(records),SupabaseJWTVerifier(JWTSettings(issuer=ISSUER),jwks,clock=lambda:NOW))
    status=FakeIdentityStatusTransport({(ISSUER,s):'active' for s in SUBJECTS[:2]})
    store=PrivateOriginalStore(repo,PrivateStorageSettings(project_url=ISSUER.removesuffix('/auth/v1'),bucket='private-originals',server_key='synthetic-storage-only-key'),FakeStorageTransport())
    binding=RuntimeBinding(root,repo,store,provider=provider,auth_settings=AuthSettings(origin=origin),proxy_policy=policy(origin),session_guard=SessionRevalidation(status,max_seconds=300))
    return binding,status,tokens


class WiringTests(unittest.TestCase):
    def setUp(self):
        Path('work/deployment-wiring-tests').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='work/deployment-wiring-tests');self.root=Path(self.tmp.name)
        self.binding,self.status,self.tokens=synthetic_binding(self.root,self.repo())
        self.app=create_app(runtime_binding=self.binding,parsing_enabled=True,auth_clock=lambda:NOW)
        self.auth=self.app.state.auth.store
        self.manager=self.auth.provision(ISSUER,SUBJECTS[0],'A','합성 A','manager',True)
        self.reader=self.auth.provision(ISSUER,SUBJECTS[1],'A','합성 A')
        self.edge=OfflineSameOriginProxy(self.app,self.binding.proxy_policy)
        self.client=TestClient(self.edge,base_url='https://local.test',client=('127.0.0.2',5))
    def repo(self):return Repository(self.root/'metadata.sqlite3')
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def login(self,index=0):
        h={'Origin':'https://local.test'};h['X-CSRF-Token']=self.client.post('/api/auth/csrf',headers=h).json()['csrf_token']
        return self.client.post('/api/auth/login',headers=h,json={'email':f'user{index}@synthetic.invalid','password':PASSWORD})
    def headers(self):return {'Origin':'https://local.test','X-CSRF-Token':self.client.get('/api/auth/me').json()['csrf_token']}
    def test_binding_shares_store_worker_has_no_browser_auth(self):
        worker=self.binding.worker('parse_worker');self.assertEqual(compare_bindings(self.binding,worker),[])
        self.assertIs(worker.store,self.binding.store);self.assertIs(type(worker.provider),UnconfiguredProvider);self.assertIsNone(worker.proxy_policy)
    def test_wrong_fake_store_database_and_role_rejected(self):
        worker=self.binding.worker('parse_worker')
        worker.store=PrivateOriginalStore(self.binding.repo,self.binding.store.settings,FakeStorageTransport())
        self.assertIn('fake_storage_not_shared',compare_bindings(self.binding,worker))
        with self.assertRaises(ValueError):create_app(runtime_binding=worker)
        with self.assertRaises(ValueError):create_app(runtime_binding=self.binding,store=self.binding.store)
    def test_wrong_local_storage_target(self):
        repo=self.binding.repo;a=RuntimeBinding(self.root,repo,LocalOriginalStore(self.root/'one'))
        b=RuntimeBinding(self.root,repo,LocalOriginalStore(self.root/'two'),role='parse_worker')
        self.assertIn('api_worker_local_storage_mismatch',compare_bindings(a,b))
    def test_project_mismatch_not_silent_fallback(self):
        self.binding.provider.issuer=ISSUER.replace('a'*20,'b'*20)
        with self.assertRaises(ValueError):self.binding.validate()
    def test_production_blocks_before_adapter_start(self):
        from apps.api.runtime_settings import SettingsRejected
        with patch.dict(os.environ,{'APP_ENV':'production'}):
            with self.assertRaises(SettingsRejected):create_app(runtime_binding=self.binding)
    def test_settings_peer_limits_match(self):
        from apps.api.runtime_settings import load_settings,peer_issues
        a=load_settings({});w=load_settings({'APP_ROLE':'parse_worker','REQUEST_TIMEOUT_SECONDS':'30'})
        self.assertIn('api_worker_contract_mismatch',peer_issues(a,w))
    def test_cookie_csrf_origin_logout_through_proxy(self):
        r=self.login();self.assertEqual(r.status_code,200)
        for v in ('Secure','HttpOnly','SameSite=lax'):self.assertIn(v,r.headers['set-cookie'])
        self.assertEqual(self.client.post('/api/auth/logout',headers={'Origin':'https://local.test'}).status_code,403)
        h=self.headers();self.assertEqual(self.client.post('/api/auth/logout',headers=h).status_code,200)
        self.assertEqual(self.client.get('/api/documents').status_code,401)
    def test_provider_disabled_deleted_revoke_and_cannot_revive(self):
        self.login();self.status.set(ISSUER,SUBJECTS[0],'disabled')
        self.assertEqual(self.client.get('/api/documents').status_code,401)
        self.status.set(ISSUER,SUBJECTS[0],'active');self.assertEqual(self.client.get('/api/documents').status_code,401)
        self.client.cookies.clear();self.assertEqual(self.login().status_code,200)
        self.status.set(ISSUER,SUBJECTS[0],'deleted');self.assertEqual(self.client.get('/api/documents').status_code,401)
    def test_provider_outage_fails_safe_without_local_revival(self):
        self.login();self.status.unavailable=True;self.assertEqual(self.client.get('/api/documents').status_code,503)
        self.assertEqual(self.login().status_code,503);self.status.unavailable=False
        self.assertEqual(self.client.get('/api/documents').status_code,200)
    def test_membership_disabled_immediate(self):
        self.login()
        with self.auth.transaction() as db:db.execute('UPDATE memberships SET active=0 WHERE user_id=?',(self.manager,))
        self.status.unavailable=True;self.assertEqual(self.client.get('/api/documents').status_code,401)
    def test_session_maximum_is_capped(self):
        self.login()
        with self.auth.transaction() as db:self.assertEqual(db.execute('SELECT expires FROM sessions').fetchone()[0],NOW+300)
    def test_reader_cannot_upload_and_no_secret_response(self):
        r=self.login(1);h=self.headers()
        self.assertTrue(PROOF not in r.text and all(t not in r.text for t in self.tokens))
        self.assertEqual(self.client.post('/api/documents?filename=x.pdf',content=pdf(),headers={**h,'Content-Type':'application/pdf','X-Data-Classification':'synthetic'}).status_code,403)
    def test_api_worker_entrypoints_complete_pipeline(self):
        self.login();h=self.headers();r=self.client.post('/api/documents?filename=x.pdf',content=pdf(),headers={**h,'Content-Type':'application/pdf','X-Data-Classification':'synthetic'})
        self.assertEqual(r.status_code,201);m=r.json()['document'];base=f"/api/documents/{m['document_id']}/versions/{m['id']}"
        from apps.api.worker import main as parse
        from apps.api.chunk_worker import main as chunk
        args=['--data-dir',str(self.root),'--institution-id','A','--once']
        with redirect_stdout(io.StringIO()):
            self.assertEqual(parse(args,runtime_binding=self.binding.worker('parse_worker')),0)
            self.assertEqual(self.client.post(base+'/chunk-jobs',headers=h,json={}).status_code,202)
            with self.assertRaises(SystemExit) as result:chunk(args,runtime_binding=self.binding.worker('chunk_worker'))
            self.assertEqual(result.exception.code,0)
        self.assertEqual(self.client.post(base+'/activate',headers=h).status_code,200)
        self.assertEqual(self.client.get(base+'/original').content,pdf())
        from apps.api.worker import run_once
        from apps.api.models import Principal
        service=self.binding.worker('workflow_worker').worker_service()
        service.enqueue(Principal(self.manager,'A','manager'),m['document_id'],m['id'])
        self.assertEqual(run_once(service,Principal('synthetic-worker','A','worker')),'completed')
    def test_fake_workflow_worker_entrypoint_idle(self):
        from apps.api.workflow_worker import main
        with redirect_stdout(io.StringIO()):self.assertEqual(main(['--data-dir',str(self.root),'--institution-id','A','--once'],runtime_binding=self.binding.worker('workflow_worker')),0)
    def test_worker_refuses_diverged_store_before_claim(self):
        from apps.api.worker import main
        worker=self.binding.worker('parse_worker')
        worker.store=PrivateOriginalStore(self.binding.repo,self.binding.store.settings,FakeStorageTransport())
        with self.assertRaises(ValueError):main(['--data-dir',str(self.root),'--institution-id','A','--once'],runtime_binding=worker)
    def test_fake_worker_cannot_start_without_api_pair(self):
        worker=RuntimeBinding(self.root,self.binding.repo,self.binding.store,role='parse_worker')
        with self.assertRaises(ValueError):worker.worker_service()
    def test_worker_binding_directory_mismatch(self):
        from apps.api.worker import main
        with self.assertRaises(ValueError):main(['--data-dir',str(self.root/'other'),'--institution-id','A','--once'],runtime_binding=self.binding.worker('parse_worker'))
    def test_default_local_and_production_worker_block(self):
        from apps.api.worker import main
        from apps.api.runtime_settings import SettingsRejected
        with patch.dict(os.environ,{'APP_ENV':'production'}):
            with self.assertRaises(SettingsRejected):main(['--data-dir',str(self.root/'blocked'),'--institution-id','A','--once'])
        self.assertFalse((self.root/'blocked').exists())


@unittest.skipUnless(DSN,'BLOCKED: isolated loopback PG not configured')
class PostgreSQLWiringTests(WiringTests):
    def repo(self):
        from apps.api.postgres import PostgresDatabase,PostgresRepository
        db=PostgresDatabase(DSN,'sb_wiring_'+secrets.token_hex(8),local_test=True);db.migrate();return PostgresRepository(db)
    def test_remote_selection_blocked(self):
        self.binding.repo.database.local_test=False
        with self.assertRaises(ValueError):self.binding.validate()
    def test_different_postgres_schema_not_shared(self):
        from apps.api.postgres import PostgresDatabase,PostgresRepository
        db=PostgresDatabase(DSN,'sb_wiring_other_'+secrets.token_hex(8),local_test=True);db.migrate()
        other=RuntimeBinding(self.root,PostgresRepository(db),LocalOriginalStore(self.root/'other'),role='parse_worker')
        self.assertIn('api_worker_database_target_mismatch',compare_bindings(self.binding,other))
