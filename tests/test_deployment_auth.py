"""Real crypto on ephemeral synthetic keys; Fake JWT/JWKS + real BFF + SQLite/loopback PG."""
import base64
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import secrets
import tempfile
import unittest
from unittest.mock import patch
from uuid import UUID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec,rsa,padding,utils
from fastapi.testclient import TestClient
from pydantic import ValidationError
from apps.api.supabase_jwt import (JWTSettings,FakeJWKSTransport,FakeTokenTransport,FakeCredential,SupabaseJWTVerifier,SupabaseJWTProviderAdapter)
from apps.api.identity_provider import ProviderUnavailable
from apps.api.main import create_app
from apps.api.auth import AuthSettings
from apps.api.auth_bootstrap import InitialAdministrator,bootstrap_initial_administrator,CONFIRMATION
from apps.api.private_storage import PrivateOriginalStore,PrivateStorageSettings,FakeStorageTransport
from apps.api.repository import Repository
from apps.api.models import Principal
from apps.api.errors import DomainError
from test_document_api import pdf

ISSUER='https://'+'a'*20+'.supabase.co/auth/v1'
SUBJECTS=[str(UUID(int=x)) for x in range(1,5)]
DSN=os.environ.get('SB_PG_TEST_DSN')
PASSWORD='synthetic-offline-password-MUST-NOT-PRINT'
NOW=1000000


def b64(raw):return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()
def raw(value):return json.dumps(value,separators=(',',':')).encode()
def public_key(key,kid='key-1',alg='ES256'):
    p=key.public_key().public_numbers()
    if alg=='ES256':return {'kty':'EC','crv':'P-256','kid':kid,'alg':alg,'use':'sig','key_ops':['verify'],'x':b64(p.x.to_bytes(32,'big')),'y':b64(p.y.to_bytes(32,'big'))}
    return {'kty':'RSA','kid':kid,'alg':alg,'use':'sig','n':b64(p.n.to_bytes((p.n.bit_length()+7)//8,'big')),'e':b64(p.e.to_bytes((p.e.bit_length()+7)//8,'big'))}

def claims(**changes):return {'iss':ISSUER,'aud':'authenticated','sub':SUBJECTS[0],'role':'authenticated','iat':NOW,'exp':NOW+600,**changes}
def sign(key,payload=None,header=None):
    header=header or {'alg':'ES256','kid':'key-1','typ':'JWT'}
    payload=claims() if payload is None else payload
    message=b64(raw(header))+'.'+b64(payload if type(payload) is bytes else raw(payload))
    if isinstance(key,rsa.RSAPrivateKey):sig=key.sign(message.encode(),padding.PKCS1v15(),hashes.SHA256())
    else:
        r,s=utils.decode_dss_signature(key.sign(message.encode(),ec.ECDSA(hashes.SHA256())))
        sig=r.to_bytes(32,'big')+s.to_bytes(32,'big')
    return message+'.'+b64(sig)


class JWTVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.key=ec.generate_private_key(ec.SECP256R1());cls.rsa_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    def setUp(self):
        self.now=[NOW];self.jwks=FakeJWKSTransport(ISSUER,{'keys':[public_key(self.key)]})
        self.verifier=SupabaseJWTVerifier(JWTSettings(issuer=ISSUER),self.jwks,clock=lambda:self.now[0])
    def rejected(self,token):
        with self.assertRaises(ProviderUnavailable) as e:self.verifier.verify(token)
        self.assertEqual(str(e.exception),'')
    def test_valid_es256(self):self.assertEqual(self.verifier.verify(sign(self.key)).subject,SUBJECTS[0])
    def test_valid_rs256(self):
        self.jwks.replace({'keys':[public_key(self.rsa_key,alg='RS256')]})
        self.assertEqual(self.verifier.verify(sign(self.rsa_key,header={'alg':'RS256','kid':'key-1'})).ttl,600)
    def test_expiration_boundary(self):
        self.now[0]=NOW+600;self.rejected(sign(self.key))
    def test_fractional_remaining_ttl(self):
        self.now[0]=NOW+599.1;self.rejected(sign(self.key))
    def test_forged_signature(self):self.rejected(sign(ec.generate_private_key(ec.SECP256R1())))
    def test_tampered_payload(self):
        t=sign(self.key).split('.');t[1]=b64(raw(claims(sub=SUBJECTS[1])));self.rejected('.'.join(t))
    def test_issuer_audience_and_service_role(self):
        for change in ({'iss':ISSUER+'/'},{'iss':ISSUER.replace('a'*20,'b'*20)},{'aud':'service_role'},{'aud':['authenticated','other']},{'role':'service_role'},{'role':'worker'}):
            with self.subTest(change=tuple(change)):self.rejected(sign(self.key,claims(**change)))
    def test_missing_claims(self):
        for field in ('iss','aud','sub','role','iat','exp'):
            data=claims();del data[field];self.rejected(sign(self.key,data))
    def test_invalid_subject_anonymous(self):
        for change in ({'sub':'not-a-uuid'},{'sub':SUBJECTS[0].upper().replace('0000','ABCD',1)},{'is_anonymous':True},{'is_anonymous':'false'}):self.rejected(sign(self.key,claims(**change)))
    def test_future_iat_nbf_lifetime(self):
        for change in ({'iat':NOW+1},{'nbf':NOW+1},{'nbf':NOW-1},{'iat':0},{'exp':NOW+3601},{'exp':NOW},{'exp':NOW-1}):self.rejected(sign(self.key,claims(**change)))
    def test_time_types(self):
        for field in ('exp','iat','nbf'):
            for value in (True,False,1000000.0,'1000000',None):self.rejected(sign(self.key,claims(**{field:value})))
    def test_metadata_never_authority(self):
        identity=self.verifier.verify(sign(self.key,claims(user_metadata={'role':'manager','institution_id':'B'},app_metadata={'role':'worker'},email='admin@synthetic.invalid')))
        self.assertEqual(set(vars(identity)),{'issuer','subject','ttl'})
    def test_none_hs_and_unsupported_algorithm(self):
        for alg in ('none','HS256','ES384','RS512'):
            t=sign(self.key,header={'alg':alg,'kid':'key-1'});self.rejected(t)
    def test_jku_jwk_x5u_crit_rejected_without_fetch(self):
        for name in ('jku','jwk','x5u','crit','b64'):
            self.rejected(sign(self.key,header={'alg':'ES256','kid':'key-1',name:'https://forbidden.invalid'}))
        self.assertEqual(self.jwks.calls,[])
    def test_invalid_kid_typ_and_header_types(self):
        for h in ({'alg':'ES256'},{'alg':'ES256','kid':'../key'},{'alg':'ES256','kid':1},{'alg':'ES256','kid':'key-1','typ':'at+jwt'}):self.rejected(sign(self.key,header=h))
    def test_malformed_oversize_token(self):
        for t in ('',None,{},'a.b','a.b.c.d','x'*8193,'a=.b.c','a.b.c','a..c'):self.rejected(t)
    def test_duplicate_claim_and_header_keys(self):
        self.rejected(sign(self.key,b'{"exp":1000600,"exp":1000000}'))
        t=sign(self.key).split('.');t[0]=b64(b'{"alg":"ES256","alg":"none","kid":"key-1"}');self.rejected('.'.join(t))
    def test_noncanonical_base64_and_signature_length(self):
        t=sign(self.key).split('.');t[2]=b64(b'bad');self.rejected('.'.join(t))
        t=sign(self.key).split('.');t[0]+='=';self.rejected('.'.join(t))
    def test_rotation_add_remove_and_no_stale_keys(self):
        next_key=ec.generate_private_key(ec.SECP256R1());old=sign(self.key);new=sign(next_key,header={'alg':'ES256','kid':'key-2'})
        self.verifier.verify(old);self.jwks.replace({'keys':[public_key(self.key),public_key(next_key,'key-2')]})
        self.assertEqual(self.verifier.verify(new).subject,SUBJECTS[0])
        self.jwks.replace({'keys':[public_key(next_key,'key-2')]});self.rejected(old)
        self.assertEqual(self.verifier.verify(new).ttl,600)
    def test_unknown_kid_one_fetch_no_retry(self):
        self.rejected(sign(self.key,header={'alg':'ES256','kid':'unknown'}));self.assertEqual(len(self.jwks.calls),1)
    def test_jwks_outage_never_stale_fallback(self):
        self.verifier.verify(sign(self.key))
        for f in ('timeout','429','503','redirect','invalid_json','oversize'):
            self.jwks.faults=[f];self.rejected(sign(self.key))
    def test_duplicate_kid_and_empty_keys(self):
        for data in ({'keys':[]},{'keys':[public_key(self.key)]*2},{'keys':[public_key(self.key)]*9},{'keys':{},'next':'invalid'}):
            self.jwks.replace(data);self.rejected(sign(self.key))
    def test_private_or_key_usage_material_rejected(self):
        for change in ({'d':'private-forbidden'},{'key_ops':['sign']},{'use':'enc'},{'crv':'P-384'},{'kty':'RSA'},{'jku':'https://forbidden.invalid'},{'x':'x'},{'alg':'HS256'}):
            self.jwks.replace({'keys':[public_key(self.key)|change]});self.rejected(sign(self.key))
    def test_algorithm_confusion(self):
        self.jwks.replace({'keys':[public_key(self.key)]});self.rejected(sign(self.rsa_key,header={'alg':'RS256','kid':'key-1'}))
    def test_weak_rsa_key_rejected(self):
        weak=rsa.generate_private_key(public_exponent=65537,key_size=1024)
        self.jwks.replace({'keys':[public_key(weak,alg='RS256')]});self.rejected(sign(weak,header={'alg':'RS256','kid':'key-1'}))
    def test_strict_settings_and_fixed_issuer(self):
        for values in ({'issuer':'http://localhost/auth/v1'},{'issuer':ISSUER+'\n'},{'issuer':ISSUER,'algorithms':('HS256',)},{'issuer':ISSUER,'algorithms':()},{'issuer':ISSUER,'max_lifetime':True}):
            with self.assertRaises(ValidationError):JWTSettings(**values)
        with self.assertRaises(ValueError):SupabaseJWTVerifier(JWTSettings(issuer=ISSUER),FakeJWKSTransport(ISSUER+'x',{}))
    def test_non_fake_transport_rejected(self):
        class Pretend(FakeJWKSTransport):pass
        for transport in (object(),Pretend(ISSUER,{})):
            with self.assertRaises(ValueError):SupabaseJWTVerifier(JWTSettings(issuer=ISSUER),transport)
    def test_offline_concurrent_verification(self):
        token=sign(self.key)
        with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')),patch('httpx.Client',side_effect=AssertionError('HTTP')):
            with ThreadPoolExecutor(max_workers=4) as pool:result=list(pool.map(lambda _:self.verifier.verify(token).ttl,range(12)))
        self.assertEqual(result,[600]*12)


class JWTSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.key=ec.generate_private_key(ec.SECP256R1())
    def setUp(self):
        Path('work/deployment-auth-tests').mkdir(exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='work/deployment-auth-tests');self.root=Path(self.tmp.name);self.now=[NOW]
        self.jwks=FakeJWKSTransport(ISSUER,{'keys':[public_key(self.key)]})
        self.verifier=SupabaseJWTVerifier(JWTSettings(issuer=ISSUER),self.jwks,clock=lambda:self.now[0])
        records=[];self.tokens=[]
        for i in range(3):
            token=sign(self.key,claims(sub=SUBJECTS[i],user_metadata={'institution_id':'B','role':'manager'},app_metadata={'role':'worker'}));self.tokens.append(token)
            records.append(FakeCredential(f'user{i}@synthetic.invalid',PASSWORD,{'access_token':token,'expires_in':600,'token_type':'bearer','user':{'id':SUBJECTS[i]},'refresh_token':'synthetic-never-exposed'}))
        self.transport=FakeTokenTransport(records);self.provider=SupabaseJWTProviderAdapter(self.transport,self.verifier)
        self.repo=self.make_repo()
        self.store=PrivateOriginalStore(self.repo,PrivateStorageSettings(project_url=ISSUER.removesuffix('/auth/v1'),bucket='private-originals',server_key='synthetic-server-only-storage'),FakeStorageTransport())
        self.app=create_app(self.root,repository=self.repo,store=self.store,parsing_enabled=True,identity_provider=self.provider,auth_settings=AuthSettings(origin='https://local.test'),auth_clock=lambda:self.now[0])
        self.auth=self.app.state.auth.store
        self.manager=self.auth.provision(ISSUER,SUBJECTS[0],'A','합성 A','manager',True)
        self.reader=self.auth.provision(ISSUER,SUBJECTS[1],'A','합성 A')
        self.foreign=self.auth.provision(ISSUER,SUBJECTS[2],'B','합성 B','manager',True)
        self.client=TestClient(self.app,base_url='https://local.test')
    def make_repo(self):return Repository(self.root/'metadata.sqlite3')
    def tearDown(self):self.client.close();self.tmp.cleanup()
    def login(self,i=0,client=None,extra=None):
        c=client or self.client;h={'Origin':'https://local.test'}
        h['X-CSRF-Token']=c.post('/auth/csrf',headers=h).json()['csrf_token']
        return c.post('/auth/login',headers=h,json={'email':f'user{i}@synthetic.invalid','password':PASSWORD,**(extra or {})})
    def headers(self):return {'Origin':'https://local.test','X-CSRF-Token':self.client.get('/auth/me').json()['csrf_token']}
    def test_login_session_cookie_provider_tokens_never_browser(self):
        r=self.login();self.assertEqual(r.status_code,200);self.assertEqual(r.json()['institution_id'],'A')
        for flag in ('HttpOnly','Secure','SameSite=lax','Path=/'):self.assertIn(flag,r.headers['set-cookie'])
        self.assertTrue(all(t not in r.text+r.headers['set-cookie'] for t in self.tokens));self.assertTrue(PASSWORD not in r.text)
        self.assertEqual(self.client.get('/auth/status').json(),{'provider_available':True,'remote_enabled':False})
    def test_reader_metadata_cannot_elevate(self):
        r=self.login(1);self.assertEqual(r.json()['role'],'reader');self.assertFalse(r.json()['institution_admin'])
        self.assertEqual(self.client.get('/auth/memberships').status_code,403)
        self.assertEqual(self.client.post('/documents?filename=x.pdf',headers={**self.headers(),'Content-Type':'application/pdf','X-Data-Classification':'synthetic'},content=pdf()).status_code,403)
    def test_manager_upload_and_private_hash(self):
        self.login();r=self.client.post('/documents?filename=x.pdf',headers={**self.headers(),'Content-Type':'application/pdf','X-Data-Classification':'synthetic'},content=pdf())
        self.assertEqual(r.status_code,201);m=r.json()['document']
        r=self.client.get(f"/documents/{m['document_id']}/versions/{m['id']}/original")
        self.assertEqual(r.status_code,200);self.assertEqual(hashlib.sha256(r.content).hexdigest(),m['sha256'])
    def test_cross_institution_documents_and_evidence(self):
        p=Principal(self.foreign,'B','manager');worker=Principal('synthetic-worker','B','worker')
        meta,_=self.app.state.service.register(p,'foreign.pdf','application/pdf',pdf('foreignneedle'))
        parsing=self.app.state.parsing;self.assertEqual(parsing.execute(worker,parsing.claim(worker)),'completed')
        from apps.api.chunking import ChunkConfig
        chunks=self.app.state.chunks;chunks.enqueue(p,meta['document_id'],meta['id'],ChunkConfig());self.assertEqual(chunks.execute(worker,chunks.claim(worker)),'completed')
        self.app.state.service.activate(p,meta['document_id'],meta['id']);item=chunks.list(p,meta['document_id'],meta['id'])[0]
        self.login();base=f"/documents/{meta['document_id']}/versions/{meta['id']}"
        for tail in ('','/original','/chunks','/parsing','/workflow/candidates'):
            self.assertEqual(self.client.get(base+tail).status_code,404)
        self.assertEqual(self.client.post(base+f"/chunks/{item['chunk_id']}/evidence/resolve",headers=self.headers(),json=item['evidence']).status_code,404)
        self.assertEqual(self.client.get('/search?q=foreignneedle').json()['results'],[])
    def test_jwt_session_private_pipeline_and_reader_evidence(self):
        from test_workflow_discovery import synthetic_hwpx
        body=synthetic_hwpx(['업무명: 합성 별 접수','1. 신청자는 별신청서를 제출한다.','2. 담당자는 자료를 확인한다.'])
        self.login();headers=self.headers()
        response=self.client.post('/documents?filename=synthetic.hwpx',content=body,headers={**headers,'Content-Type':'application/hwp+zip','X-Data-Classification':'synthetic'})
        self.assertEqual(response.status_code,201);meta=response.json()['document'];base=f"/documents/{meta['document_id']}/versions/{meta['id']}"
        worker=Principal('synthetic-worker','A','worker');parsing=self.app.state.parsing
        self.assertEqual(parsing.execute(worker,parsing.claim(worker)),'completed')
        self.assertEqual(self.client.post(base+'/chunk-jobs',json={},headers=headers).status_code,202)
        chunks=self.app.state.chunks;self.assertEqual(chunks.execute(worker,chunks.claim(worker)),'completed')
        self.assertEqual(self.client.post(base+'/activate',headers=headers).status_code,200)
        jobs=self.app.state.workflows;jobs.enqueue(Principal(self.manager,'A','manager'),meta['document_id'],meta['id'])
        self.assertEqual(jobs.execute(worker,jobs.claim(worker)),'completed')
        current=jobs.current(Principal(self.manager,'A','manager'),meta['document_id'],meta['id'])
        self.assertEqual(current['result'].forms.semantic_verification,'NOT_VERIFIED');self.assertFalse(current['result'].forms.publishable)
        self.login(1);item=self.client.get(base+'/chunks').json()[0]
        evidence=self.client.post(base+f"/chunks/{item['chunk_id']}/evidence/resolve",headers=self.headers(),json=item['evidence'])
        self.assertEqual(evidence.status_code,200);self.assertTrue(evidence.json()['structural_valid'])
        self.assertEqual(hashlib.sha256(self.client.get(base+'/original').content).hexdigest(),hashlib.sha256(body).hexdigest())
    def test_bff_session_survives_app_recreation_without_provider_token(self):
        self.login();cookie=self.client.cookies.get('__Host-seomuitda')
        app=create_app(self.root,repository=self.repo,store=self.store,parsing_enabled=True,identity_provider=self.provider,auth_settings=AuthSettings(origin='https://local.test'),auth_clock=lambda:self.now[0])
        with TestClient(app,base_url='https://local.test') as client:
            response=client.get('/auth/me',headers={'Cookie':'__Host-seomuitda='+cookie})
            self.assertEqual(response.status_code,200);self.assertEqual(response.json()['institution_id'],'A')
    def test_bearer_jwt_alone_not_browser_auth(self):
        self.assertEqual(self.client.get('/documents',headers={'Authorization':'Bearer '+self.tokens[0]}).status_code,401)
    def test_invalid_expired_forged_issuer_audience_login_denied(self):
        for change in ({'exp':NOW},{'iss':ISSUER+'/'},{'aud':'service_role'}):
            self.provider.transport=FakeTokenTransport([FakeCredential('user0@synthetic.invalid',PASSWORD,{'access_token':sign(self.key,claims(**change)),'expires_in':600,'token_type':'bearer','user':{'id':SUBJECTS[0]}})])
            self.assertEqual(self.login().status_code,503)
        self.provider.transport=FakeTokenTransport([FakeCredential('user0@synthetic.invalid',PASSWORD,{'access_token':sign(ec.generate_private_key(ec.SECP256R1())),'expires_in':600,'token_type':'bearer','user':{'id':SUBJECTS[0]}})])
        self.assertEqual(self.login().status_code,503);self.assertEqual(self.client.get('/auth/me').status_code,401)
    def test_provider_and_jwks_errors_deny_new_login(self):
        for fault in ('timeout','429','503','redirect'):
            self.transport.faults=[fault];self.assertEqual(self.login().status_code,503)
        self.jwks.faults=['timeout'];self.assertEqual(self.login().status_code,503)
    def test_bad_response_subject_mismatch_and_ttl(self):
        good={'access_token':self.tokens[0],'expires_in':600,'token_type':'bearer','user':{'id':SUBJECTS[0]}}
        for change in ({'user':{'id':SUBJECTS[1]}},{'user':{'id':SUBJECTS[0],'banned_until':'synthetic-disabled'}},{'token_type':'other'},{'expires_in':True},{'expires_in':0},{'access_token':None}):
            self.provider.transport=FakeTokenTransport([FakeCredential('user0@synthetic.invalid',PASSWORD,good|change)])
            self.assertEqual(self.login().status_code,503)
    def test_unknown_user_no_automatic_domain_provisioning(self):
        with self.auth.transaction() as db:db.execute('UPDATE identities SET subject=? WHERE id=?',(SUBJECTS[3],self.manager))
        self.assertEqual(self.login().status_code,403)
    def test_inactive_user_org_membership(self):
        for table,key,col in (('identities',self.manager,'id'),('organizations','A','id'),('memberships',self.manager,'user_id')):
            with self.auth.transaction() as db:db.execute('UPDATE '+table+' SET active=0 WHERE '+col+'=?',(key,))
            self.assertEqual(self.login().status_code,403)
            with self.auth.transaction() as db:db.execute('UPDATE '+table+' SET active=1 WHERE '+col+'=?',(key,))
    def test_active_session_disable_and_role_change(self):
        self.login()
        with self.auth.transaction() as db:db.execute("UPDATE memberships SET role='reader',institution_admin=0 WHERE user_id=?",(self.manager,))
        self.assertEqual(self.client.get('/auth/me').json()['role'],'reader')
        self.assertEqual(self.client.delete('/documents/not-found',headers=self.headers()).status_code,403)
        with self.auth.transaction() as db:db.execute('UPDATE memberships SET active=0 WHERE user_id=?',(self.manager,))
        self.assertEqual(self.client.get('/documents').status_code,401)
    def test_provider_project_change_revokes_session_scope(self):
        self.login();self.provider.issuer=ISSUER.replace('a'*20,'b'*20)
        self.assertEqual(self.client.get('/auth/me').status_code,401)
    def test_added_ambiguous_membership_blocks_existing_session(self):
        self.login();self.auth.provision(ISSUER,SUBJECTS[0],'B','합성 B')
        self.assertEqual(self.client.get('/documents').status_code,401);self.assertEqual(self.login().status_code,403)
    def test_csrf_origin_and_cross_site(self):
        self.login();h=self.headers()
        for bad in ({},{**h,'Origin':'https://evil.invalid'},{**h,'X-CSRF-Token':'bad'},{**h,'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.client.post('/auth/logout',headers=bad).status_code,403)
        self.assertEqual(self.client.get('/auth/me').status_code,200)
    def test_logout_old_cookie_expiration(self):
        self.login();cookie=self.client.cookies.get('__Host-seomuitda');h=self.headers()
        self.assertEqual(self.client.post('/auth/logout',headers=h).status_code,200)
        self.client.cookies.set('__Host-seomuitda',cookie);self.assertEqual(self.client.get('/documents').status_code,401)
        self.client.cookies.clear();self.login();self.now[0]+=600;self.assertEqual(self.client.get('/documents').status_code,401)
    def test_membership_admin_revokes_reader_session(self):
        with TestClient(self.app,base_url='https://local.test') as reader:
            self.login(1,reader);self.login()
            r=self.client.patch('/auth/memberships/'+self.reader,headers=self.headers(),json={'role':'reader','active':False})
            self.assertEqual(r.status_code,200);self.assertEqual(reader.get('/documents').status_code,401)
    def test_worker_or_tenant_cannot_be_injected(self):
        self.assertEqual(self.login(extra={'role':'worker','institution_id':'B'}).status_code,422)
        self.login();self.assertEqual(self.client.patch('/auth/memberships/'+self.reader,headers=self.headers(),json={'role':'worker','active':True}).status_code,422)
    def test_admin_scope_foreign_membership(self):
        self.login();self.assertEqual(self.client.patch('/auth/memberships/'+self.foreign,headers=self.headers(),json={'role':'reader','active':False}).status_code,404)
    def test_admin_revocation_between_resolve_and_mutation(self):
        self.login();headers=self.headers();original=self.app.state.auth.resolve
        def revoke(request,mutation=None):
            p=original(request,mutation)
            with self.auth.transaction() as db:db.execute('UPDATE memberships SET institution_admin=0 WHERE user_id=?',(self.manager,))
            return p
        with patch.object(self.app.state.auth,'resolve',revoke):
            response=self.client.patch('/auth/memberships/'+self.reader,headers=headers,json={'role':'reader','active':False})
        self.assertEqual(response.status_code,403)
        with self.auth.transaction() as db:self.assertEqual(db.execute('SELECT active FROM memberships WHERE user_id=?',(self.reader,)).fetchone()[0],1)
    def test_database_and_logs_never_store_provider_credentials(self):
        stream=io.StringIO();handler=logging.StreamHandler(stream);logging.getLogger().addHandler(handler)
        try:
            self.login()
            with self.auth.transaction() as db:
                rows={t:[dict(r) for r in db.execute('SELECT * FROM '+t)] for t in ('sessions','auth_audit_events','identities')}
            text=json.dumps(rows)+stream.getvalue()+repr(self.provider)+repr(self.transport)+repr(self.jwks)
            self.assertTrue(PASSWORD not in text and all(token not in text for token in self.tokens))
            self.assertTrue('synthetic-never-exposed' not in text)
        finally:logging.getLogger().removeHandler(handler)
    def test_fully_offline_login(self):
        with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')),patch('httpx.Client',side_effect=AssertionError('HTTP')):
            self.assertEqual(self.login().status_code,200)
    def test_no_public_bootstrap_endpoint(self):self.assertEqual(self.client.post('/auth/bootstrap',json={}).status_code,404)
    def test_explicit_bootstrap_atomic_and_duplicate_refused(self):
        request=InitialAdministrator(issuer=ISSUER,subject=SUBJECTS[3],institution_id='C',institution_name='합성 C')
        result=bootstrap_initial_administrator(self.auth,request,confirmation=CONFIRMATION)
        self.assertTrue(result['institution_admin']);self.assertEqual(result['role'],'manager')
        with self.assertRaises(DomainError):bootstrap_initial_administrator(self.auth,request,confirmation=CONFIRMATION)
        with self.auth.transaction() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM memberships WHERE institution_id='C'").fetchone()[0],1)
    def test_bootstrap_confirmation_and_no_email_rules(self):
        request=InitialAdministrator(issuer=ISSUER,subject=SUBJECTS[3],institution_id='C',institution_name='합성 C')
        with self.assertRaises(DomainError):bootstrap_initial_administrator(self.auth,request,confirmation='')
        with self.assertRaises(ValidationError):InitialAdministrator(**request.model_dump(),email='admin@synthetic.invalid')
        with self.auth.transaction() as db:self.assertIsNone(db.execute("SELECT 1 FROM organizations WHERE id='C'").fetchone())
    def test_concurrent_initial_bootstrap_exactly_once(self):
        request=InitialAdministrator(issuer=ISSUER,subject=SUBJECTS[3],institution_id='C',institution_name='합성 C')
        def call(_):
            try:bootstrap_initial_administrator(self.auth,request,confirmation=CONFIRMATION);return 'created'
            except DomainError:return 'refused'
        with ThreadPoolExecutor(max_workers=2) as pool:self.assertCountEqual(list(pool.map(call,range(2))),['created','refused'])
    def test_bootstrap_partial_failure_rolls_back(self):
        from unittest.mock import patch
        from apps.api.auth_store import AuthStore
        request=InitialAdministrator(issuer=ISSUER,subject=SUBJECTS[3],institution_id='C',institution_name='합성 C')
        with patch.object(type(self.auth),'audit',side_effect=RuntimeError('synthetic-audit-failure')):
            with self.assertRaises(RuntimeError):bootstrap_initial_administrator(self.auth,request,confirmation=CONFIRMATION)
        with self.auth.transaction() as db:self.assertIsNone(db.execute("SELECT 1 FROM organizations WHERE id='C'").fetchone())
    def test_default_provider_remains_deny_all(self):
        app=create_app(self.root/'default')
        with TestClient(app,base_url='https://local.test') as c:self.assertEqual(c.get('/documents').status_code,401)
    def test_preflight_auth_implementation_not_operational_ready(self):
        from apps.api.runtime_settings import preflight,PRODUCTION_BLOCKERS
        self.assertEqual(preflight({})['jwt_verification'],'FAKE_JWKS_IMPLEMENTED_NOT_CONNECTED')
        self.assertIn('production_auth_runtime_and_operator_provisioning_not_verified',PRODUCTION_BLOCKERS)


@unittest.skipUnless(DSN,'BLOCKED: isolated loopback PostgreSQL not configured')
class PostgreSQLJWTSessionTests(JWTSessionTests):
    def make_repo(self):
        from apps.api.postgres import PostgresDatabase,PostgresRepository
        db=PostgresDatabase(DSN,'sb_auth_'+secrets.token_hex(8),local_test=True);db.migrate();return PostgresRepository(db)
