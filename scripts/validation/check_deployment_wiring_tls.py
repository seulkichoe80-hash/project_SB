"""Own loopback TLS server + in-process edge/API + Fake providers. No vendor deployment/requests."""
import argparse
from datetime import datetime,timedelta,timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import ssl
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import httpx
import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
from apps.api.main import create_app
from apps.api.proxy_boundary import OfflineSameOriginProxy
from apps.api.formats import MAX_BYTES
from test_deployment_wiring import synthetic_binding
from test_deployment_auth import ISSUER,SUBJECTS,NOW,PASSWORD
from test_document_api import pdf


def certificates(root):
    now=datetime.now(timezone.utc)
    ca_key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Synthetic Loopback Test CA')])
    ca=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).add_extension(x509.KeyUsage(True,False,False,False,False,True,True,False,False),critical=True).sign(ca_key,hashes.SHA256())
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    cert=x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.SubjectAlternativeName([x509.DNSName('localhost'),x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(ca_key,hashes.SHA256())
    data={'ca.pem':ca.public_bytes(serialization.Encoding.PEM),'cert.pem':cert.public_bytes(serialization.Encoding.PEM),'key.pem':key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())}
    for file,body in data.items():
        p=root/file
        with p.open('xb') as f:f.write(body)
        p.chmod(0o600)


def run(root):
    started=time.monotonic()
    if root.exists():raise ValueError('new_private_tls_directory_required')
    root.mkdir(parents=True,mode=0o700);certificates(root)
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128);port=sock.getsockname()[1]
    origin=f'https://localhost:{port}'
    binding,status,tokens=synthetic_binding(root,origin=origin)
    app=create_app(runtime_binding=binding,parsing_enabled=True,auth_clock=lambda:NOW)
    auth=app.state.auth.store;auth.provision(ISSUER,SUBJECTS[0],'A','합성 A','manager',True)
    edge=OfflineSameOriginProxy(app,binding.proxy_policy)
    config=uvicorn.Config(edge,ssl_keyfile=str(root/'key.pem'),ssl_certfile=str(root/'cert.pem'),proxy_headers=False,access_log=False,log_level='critical',lifespan='off')
    server=uvicorn.Server(config);thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
    cases=[]
    def check(name,condition):
        if not condition:raise AssertionError('local_tls_check_failed:'+name)
        cases.append(name)
    try:
        deadline=time.monotonic()+10
        while not server.started:
            if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('local_tls_not_started')
            time.sleep(.02)
        context=ssl.create_default_context(cafile=str(root/'ca.pem'))
        with socket.create_connection(('127.0.0.1',port),timeout=5) as raw:
            with context.wrap_socket(raw,server_hostname='localhost') as secured:version=secured.version()
        with httpx.Client(base_url=origin,verify=context,trust_env=False,timeout=20,follow_redirects=False) as client:
            check('verified_tls_health',client.get('/api/health').status_code==200 and context.check_hostname)
            try:
                with httpx.Client(verify=True,trust_env=False,timeout=5) as untrusted:untrusted.get(origin+'/api/health')
                check('unknown_ca_rejected',False)
            except httpx.ConnectError:check('unknown_ca_rejected',True)
            def login():
                headers={'Origin':origin};csrf=client.post('/api/auth/csrf',headers=headers).json()['csrf_token'];headers['X-CSRF-Token']=csrf
                return client.post('/api/auth/login',headers=headers,json={'email':'user0@synthetic.invalid','password':PASSWORD})
            response=login();check('fake_jwt_bff_login',response.status_code==200)
            check('secure_httponly_samesite_cookie',all(v in response.headers['set-cookie'] for v in ('Secure','HttpOnly','SameSite=lax')))
            h={'Origin':origin,'X-CSRF-Token':client.get('/api/auth/me').json()['csrf_token'],'Content-Type':'application/pdf','X-Data-Classification':'synthetic'}
            body=pdf()+b' '*(MAX_BYTES-len(pdf()))
            response=client.post('/api/documents?filename=synthetic-boundary.pdf',headers=h,content=body)
            check('20mib_upload_accepted',response.status_code==201);meta=response.json()['document']
            check('20mib_plus_one_rejected',client.post('/api/documents?filename=oversize.pdf',headers=h,content=body+b' ').status_code==413)
            data=client.get(f"/api/documents/{meta['document_id']}/versions/{meta['id']}/original").content
            check('original_sha_preserved',hashlib.sha256(data).hexdigest()==meta['sha256'])
            check('csrf_rejected',client.post('/api/auth/logout',headers={'Origin':origin}).status_code==403)
            check('host_rejected',client.get('/api/health',headers={'Host':'evil.invalid'}).status_code==400)
            response=client.get('/api/auth/me',headers={'Origin':'https://evil.invalid'})
            check('origin_and_cors_rejected',response.status_code==403 and 'access-control-allow-origin' not in response.headers)
            check('forwarded_spoof_sanitized',client.get('/api/auth/me',headers={'X-Forwarded-Proto':'http','X-Forwarded-Host':'evil.invalid','X-SB-Proxy-Token':'forged'}).status_code==200)
            status.set(ISSUER,SUBJECTS[0],'disabled');check('provider_disable_existing_session',client.get('/api/documents').status_code==401)
            status.set(ISSUER,SUBJECTS[0],'active');check('old_sid_not_revived',client.get('/api/documents').status_code==401)
            client.cookies.clear();check('explicit_new_login',login().status_code==200)
            csrf=client.get('/api/auth/me').json()['csrf_token']
            check('logout_and_protected_data_denied',client.post('/api/auth/logout',headers={'Origin':origin,'X-CSRF-Token':csrf}).status_code==200 and client.get('/api/documents').status_code==401)
        return {'status':'PASS','cases':cases,'count':len(cases),'tls_version':version,'certificate_hostname_verified':True,'certificate_chain_verified':True,
                'loopback_only':True,'upstream':'IN_PROCESS_ASGI_SIMULATION','storage_auth':'FAKE_ONLY','vendor_edge_verified':False,
                'max_upload_bytes':MAX_BYTES,'actual_external_provider_calls':0,'actual_spend_usd':0,'seconds':round(time.monotonic()-started,3)}
    finally:
        server.should_exit=True;thread.join(timeout=10);sock.close()
        if thread.is_alive():raise RuntimeError('owned_tls_server_did_not_stop')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data-dir',type=Path,required=True);a=p.parse_args()
    print(json.dumps(run(a.data_dir),indent=2))
