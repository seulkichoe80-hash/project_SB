from contextlib import closing
import hashlib
import json
import secrets
import sqlite3
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from apps.api.main import create_app
from apps.api.auth import AuthSettings
from apps.api.auth_store import AuthStore
from apps.api.identity_provider import SupabaseProviderAdapter, MockSupabaseTransport, ProviderUnavailable
from apps.api.models import Principal
from test_document_api import pdf

ISSUER='https://synthetic.example/auth/v1'
class AuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir='work/stage4b2');self.root=Path(self.tmp.name);self.calls=[];self.now=[100000.]
        def transport(method,path,headers,body):
            self.calls.append((method,path))
            if method=='POST':return 200,{'access_token':body['email'],'expires_in':600,'refresh_token':'synthetic-unused'}
            return 200,{'id':headers['Authorization'].split(' ',1)[1],'user_metadata':{'role':'worker','institution_id':'B'}}
        self.provider=SupabaseProviderAdapter(MockSupabaseTransport(transport),ISSUER)
        self.app=create_app(self.root,parsing_enabled=True,identity_provider=self.provider,auth_settings=AuthSettings(origin='https://local.test'),auth_clock=lambda:self.now[0])
        self.store=self.app.state.auth.store
        self.a=self.store.provision(ISSUER,'manager@test','A','합성기관 A','manager',True)
        self.reader=self.store.provision(ISSUER,'reader@test','A','합성기관 A')
        self.b=self.store.provision(ISSUER,'foreign@test','B','합성기관 B','manager',True)
        self.client=TestClient(self.app,base_url='https://local.test')
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def login(self,email='manager@test',client=None,extra=None):
        c=client or self.client;h={'Origin':'https://local.test'};csrf=c.post('/auth/csrf',headers=h).json()['csrf_token'];h['X-CSRF-Token']=csrf
        r=c.post('/auth/login',headers=h,json={'email':email,'password':'synthetic-test-only',**(extra or {})})
        return r
    def headers(self,user=None):return {'Origin':'https://local.test','X-CSRF-Token':(user or self.client.get('/auth/me').json())['csrf_token']}
    def test_missing_auth_all_protected_routes(self):
        for method,path in [('GET','/documents'),('GET','/search?q=x'),('GET','/documents/d/versions/v/original'),('GET','/documents/d/versions/v/parsing'),('GET','/documents/d/versions/v/chunks'),('POST','/documents/d/versions/v/evidence/resolve')]:
            self.assertEqual(self.client.request(method,path,json={} if method=='POST' else None).status_code,401,path)
    def test_login_verified_identity_cookie_and_no_provider_tokens(self):
        r=self.login();self.assertEqual(r.status_code,200);self.assertEqual(r.json()['role'],'manager');self.assertEqual(r.json()['institution_id'],'A')
        cookie=r.headers.get('set-cookie');self.assertIn('HttpOnly',cookie);self.assertIn('Secure',cookie);self.assertIn('SameSite=lax',cookie);self.assertNotIn('access_token',r.text)
        self.assertEqual(self.calls,[('POST','/auth/v1/token?grant_type=password'),('GET','/auth/v1/user')])
    def test_reader_cannot_mutate(self):
        r=self.login('reader@test');self.assertEqual(r.status_code,200)
        self.assertEqual(self.client.post('/documents?filename=x.pdf',content=pdf(),headers={**self.headers(),'Content-Type':'application/pdf','X-Data-Classification':'synthetic'}).status_code,403)
    def test_cross_org_document_original_jobs_evidence(self):
        meta,_=self.app.state.service.register(Principal(self.b,'B','manager'),'x.pdf','application/pdf',pdf())
        self.login();base=f"/documents/{meta['document_id']}/versions/{meta['id']}"
        for tail in ['', '/original','/parsing','/blocks','/chunks']:
            self.assertEqual(self.client.get(base+tail).status_code,404,tail)
        # Valid body shape is obtained from the real parser so authorization is tested, not Pydantic rejection.
        from apps.api.parsers import default_parsers
        anchor=default_parsers()['pdf'].parse(pdf(),meta['document_id'],meta['id'])[0].source_anchor.model_dump(mode='json')
        self.assertEqual(self.client.post(base+'/evidence/resolve',json={'source_anchor':anchor},headers=self.headers()).status_code,404)
        self.assertEqual(self.client.delete('/documents/'+meta['document_id'],headers=self.headers()).status_code,404)
        self.assertEqual(self.client.get('/documents').json(),[])
    def test_csrf_and_origin(self):
        self.login()
        for headers in [{},{'Origin':'https://evil.test','X-CSRF-Token':self.headers()['X-CSRF-Token']},{'Origin':'https://local.test','X-CSRF-Token':'forged'}]:
            self.assertEqual(self.client.post('/auth/logout',headers=headers).status_code,403)
        self.assertEqual(self.client.get('/auth/me').status_code,200)
    def test_login_csrf_and_replay(self):
        self.assertEqual(self.client.post('/auth/csrf',headers={'Origin':'https://evil.test'}).status_code,403)
        h={'Origin':'https://local.test'};h['X-CSRF-Token']=self.client.post('/auth/csrf',headers=h).json()['csrf_token']
        body={'email':'manager@test','password':'synthetic'}
        self.assertEqual(self.client.post('/auth/login',headers=h,json=body).status_code,200)
        self.assertIn(self.client.post('/auth/login',headers=h,json=body).status_code,[401,403])
    def test_expiry_and_idle(self):
        self.login();self.now[0]+=601;self.assertEqual(self.client.get('/auth/me').status_code,401)
    def test_idle_expiry(self):
        self.app.state.auth.settings=AuthSettings(origin='https://local.test',idle=10)
        self.login();self.now[0]+=11;self.assertEqual(self.client.get('/documents').status_code,401)
    def test_logout_and_old_cookie_replay(self):
        self.login();cookie=self.client.cookies.get('__Host-seomuitda');h=self.headers();self.assertEqual(self.client.post('/auth/logout',headers=h).status_code,200)
        self.client.cookies.set('__Host-seomuitda',cookie);self.assertEqual(self.client.get('/documents').status_code,401)
    def test_forged_and_duplicate_cookie(self):
        for value in ['bad','x'*43]:self.assertEqual(self.client.get('/auth/me',headers={'Cookie':'__Host-seomuitda='+value}).status_code,401)
        self.login();value=self.client.cookies.get('__Host-seomuitda');self.assertEqual(self.client.get('/auth/me',headers={'Cookie':f'__Host-seomuitda={value}; __Host-seomuitda={value}'}).status_code,401)
    def test_user_disabled(self):
        self.login()
        with self.store.transaction() as db:db.execute('UPDATE identities SET active=0 WHERE id=?',(self.a,))
        self.assertEqual(self.client.get('/documents').status_code,401)
    def test_org_disabled(self):
        self.login()
        with self.store.transaction() as db:db.execute("UPDATE organizations SET active=0 WHERE id='A'")
        self.assertEqual(self.client.get('/documents').status_code,401)
    def test_membership_removed_and_sessions_revoked(self):
        reader=TestClient(self.app,base_url='https://local.test');self.login('reader@test',reader);self.login()
        r=self.client.patch('/auth/memberships/'+self.reader,headers=self.headers(),json={'role':'reader','active':False})
        self.assertEqual(r.status_code,200);self.assertEqual(reader.get('/auth/me').status_code,401);reader.close()
    def test_membership_admin_scope(self):
        self.login('reader@test');self.assertEqual(self.client.get('/auth/memberships').status_code,403)
        self.login();self.assertEqual(self.client.patch('/auth/memberships/'+self.b,headers=self.headers(),json={'role':'reader','active':False}).status_code,404)
    def test_worker_and_org_injection_rejected(self):
        self.assertEqual(self.login(extra={'institution_id':'B','role':'worker'}).status_code,422)
        self.login();self.assertEqual(self.client.patch('/auth/memberships/'+self.reader,headers=self.headers(),json={'role':'worker','active':True}).status_code,422)
    def test_self_admin_change_rejected(self):
        self.login();self.assertEqual(self.client.patch('/auth/memberships/'+self.a,headers=self.headers(),json={'role':'reader','active':False}).status_code,409)
    def test_provider_unconfigured_or_error(self):
        from apps.api.identity_provider import UnconfiguredProvider
        self.app.state.auth.provider=UnconfiguredProvider();self.assertEqual(self.login().status_code,503);self.assertEqual(self.client.get('/auth/me').status_code,401)
        self.assertEqual(self.client.get('/auth/status').json(),{'provider_available':False,'remote_enabled':False})
    def test_provider_exception_sanitized(self):
        self.app.state.auth.provider=SupabaseProviderAdapter(MockSupabaseTransport(lambda *a:(_ for _ in ()).throw(ValueError('sensitive'))),ISSUER)
        r=self.login();self.assertEqual(r.status_code,503);self.assertNotIn('sensitive',r.text)
    def test_unknown_identity_not_auto_provisioned(self):self.assertEqual(self.login('unknown@test').status_code,403)
    def test_login_rotation_and_repeat(self):
        for _ in range(3):self.assertEqual(self.login().status_code,200);self.assertEqual(self.client.post('/auth/logout',headers=self.headers()).status_code,200)
    def test_session_restart_and_hash_storage(self):
        self.login();cookie=self.client.cookies.get('__Host-seomuitda')
        app=create_app(self.root,identity_provider=self.provider,auth_settings=AuthSettings(origin='https://local.test'),auth_clock=lambda:self.now[0])
        c=TestClient(app,base_url='https://local.test');c.cookies.set('__Host-seomuitda',cookie);self.assertEqual(c.get('/auth/me').status_code,200);c.close()
        with self.store.transaction() as db:
            values=str([tuple(r) for r in db.execute('SELECT * FROM sessions')])+str([tuple(r) for r in db.execute('SELECT * FROM auth_audit_events')])
        self.assertNotIn(cookie,values);self.assertNotIn('synthetic-test-only',values);self.assertNotIn('synthetic-unused',values)
    def test_additive_migration_backup_restore(self):
        p=self.root/'legacy.sqlite3';db=sqlite3.connect(p);db.execute('CREATE TABLE original_data(value BLOB)');db.execute('INSERT INTO original_data VALUES(?)',(b'immutable',));db.commit();db.close()
        store=AuthStore(p);self.assertTrue(store.backup.exists())
        with closing(sqlite3.connect(p)) as db:self.assertEqual(db.execute('SELECT value FROM original_data').fetchone()[0],b'immutable')
        restored=self.root/'restore.sqlite3'
        with closing(sqlite3.connect(store.backup)) as src,closing(sqlite3.connect(restored)) as dst:src.backup(dst)
        with closing(sqlite3.connect(restored)) as db:
            self.assertEqual(db.execute('SELECT value FROM original_data').fetchone()[0],b'immutable');self.assertIsNone(db.execute("SELECT 1 FROM sqlite_master WHERE name='identities'").fetchone())
    def test_safe_settings(self):
        with self.assertRaises(ValueError):AuthSettings(origin='http://public.example',secure_cookie=False)
    def test_validation_does_not_echo_password(self):
        r=self.login(extra={'role':'manager'});self.assertEqual(r.status_code,422);self.assertNotIn('synthetic-test-only',r.text)

    def test_existing_document_blocks_and_original_survive_migration_restore(self):
        from apps.api.repository import Repository
        from apps.api.storage import LocalOriginalStore
        from apps.api.service import DocumentService
        from apps.api.parsing_service import ParsingService
        root=self.root/'legacy-app';repo=Repository(root/'metadata.sqlite3');store=LocalOriginalStore(root/'originals')
        service=DocumentService(repo,store,True);manager=Principal('trusted-test','A','manager');worker=Principal('trusted-worker','A','worker')
        meta,_=service.register(manager,'preserved.pdf','application/pdf',pdf())
        parsing=ParsingService(service);claim=parsing.claim(worker);self.assertEqual(parsing.execute(worker,claim),'completed')
        def snapshot(path):
            with closing(sqlite3.connect(path)) as db:
                return {t:db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for t in ['documents','versions','source_blocks','parse_jobs','parse_attempts']}
        before=snapshot(repo.path);auth=AuthStore(repo.path);self.assertEqual(snapshot(repo.path),before)
        self.assertEqual(snapshot(auth.backup),before)
        self.assertEqual(hashlib.sha256(service.original(manager,meta['document_id'],meta['id'])[0]).hexdigest(),meta['sha256'])

    def test_login_throttle_and_challenge_expiry(self):
        for _ in range(10):self.assertEqual(self.login('unknown@test').status_code,403)
        self.assertEqual(self.login().status_code,429)
        self.now[0]+=301;self.assertEqual(self.login().status_code,200)

    def test_permission_rechecked_on_every_request(self):
        self.login()
        with self.store.transaction() as db:db.execute("UPDATE memberships SET role='reader',institution_admin=0 WHERE user_id=?",(self.a,))
        self.assertEqual(self.client.get('/auth/me').json()['role'],'reader')
        self.assertEqual(self.client.delete('/documents/no-document',headers=self.headers()).status_code,403)

    def test_unconfigured_provider_rejects_persisted_session(self):
        self.login()
        from apps.api.identity_provider import UnconfiguredProvider
        self.app.state.auth.provider=UnconfiguredProvider()
        self.assertEqual(self.client.get('/documents').status_code,401)

    def test_login_rotation_rejects_previous_sid(self):
        self.login();old=self.client.cookies.get('__Host-seomuitda');self.login();self.assertNotEqual(old,self.client.cookies.get('__Host-seomuitda'))
        self.assertEqual(self.client.get('/auth/me',headers={'Cookie':'__Host-seomuitda='+old}).status_code,401)

    def test_session_search_and_chunk_evidence_tenant_boundary(self):
        from apps.api.chunking import ChunkConfig
        b=Principal(self.b,'B','manager');worker=Principal('trusted-test-worker','B','worker')
        service=self.app.state.service;parsing=self.app.state.parsing;chunks=self.app.state.chunks
        meta,_=service.register(b,'foreign.pdf','application/pdf',pdf('foreignneedle'))
        self.assertEqual(parsing.execute(worker,parsing.claim(worker)),'completed')
        chunks.enqueue(b,meta['document_id'],meta['id'],ChunkConfig())
        self.assertEqual(chunks.execute(worker,chunks.claim(worker)),'completed')
        service.activate(b,meta['document_id'],meta['id'])
        item=chunks.list(b,meta['document_id'],meta['id'])[0]
        self.login();self.assertEqual(self.client.get('/search?q=foreignneedle').json()['results'],[])
        url=f"/documents/{meta['document_id']}/versions/{meta['id']}/chunks/{item['chunk_id']}/evidence/resolve"
        self.assertEqual(self.client.post(url,headers=self.headers(),json=item['evidence']).status_code,404)
        self.assertEqual(hashlib.sha256(service.original(b,meta['document_id'],meta['id'])[0]).hexdigest(),meta['sha256'])
