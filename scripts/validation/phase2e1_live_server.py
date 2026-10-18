"""Explicit synthetic LOOPBACK validation only. Never an application login/deployment."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apps.api.main import create_app
from apps.api.auth import AuthSettings
from apps.api.identity_provider import SupabaseProviderAdapter,MockSupabaseTransport
from apps.api.models import Principal
from apps.api.chunking import ChunkConfig
from apps.api.workflow_forms_models import FormMetadata
from test_workflow_discovery import synthetic_hwpx


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--ready-file',type=Path,required=True)
    parser.add_argument('--synthetic-loopback-test',action='store_true',required=True);args=parser.parse_args()
    if args.ready_file.exists():parser.error('new ready path required')
    sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen(128)
    origin=f'http://127.0.0.1:{sock.getsockname()[1]}'
    issuer='https://synthetic.invalid/auth/v1'
    def mock(method,path,headers,body):
        if method=='POST':return 200,{'access_token':'synthetic-reviewer','expires_in':600}
        return 200,{'id':'synthetic-reviewer','user_metadata':{'role':'worker','institution_id':'B'}}
    with tempfile.TemporaryDirectory(prefix='sb-phase2e1-live-') as directory:
        root=Path(directory)
        # This existing development option refuses insecure cookies outside loopback.
        app=create_app(root,parsing_enabled=True,identity_provider=SupabaseProviderAdapter(MockSupabaseTransport(mock),issuer),
                       auth_settings=AuthSettings(origin=origin,secure_cookie=False))
        user_id=app.state.auth.store.provision(issuer,'synthetic-reviewer','A','합성 연구지원기관','manager',True)
        manager=Principal(user_id,'A','manager');worker=Principal('trusted-validation-worker','A','worker')
        def add(lines,name):
            meta,_=app.state.service.register(manager,name,'application/hwp+zip',synthetic_hwpx(lines))
            assert app.state.parsing.execute(worker,app.state.parsing.claim(worker))=='completed'
            chunks=app.state.chunks;chunks.enqueue(manager,meta['document_id'],meta['id'],ChunkConfig())
            assert chunks.execute(worker,chunks.claim(worker))=='completed'
            app.state.service.activate(manager,meta['document_id'],meta['id']);return meta
        manual=add(['업무명: 연구 자료 대여','1. 신청자는 자료대여신청서를 제출한다.',
                    '2. 담당자는 검토확인서를 작성한다.',
                    '3. 자료가 누락된 경우 담당자는 보완하여 1단계로 돌아가 자료를 제출한다.',
                    '4. 담당자는 결과보고서를 제출한다.'],'연구자료대여-합성.hwpx')
        for title,filename,description in [('자료대여신청서','자료대여신청서.hwpx','합성 대여 서식'),
            ('결과보고서','결과보고서-A.hwpx','합성 보고 서식 A'),('결과보고서','결과보고서-B.hwpx','합성 보고 서식 B')]:
            form=add([description,'입력란: 합성 자료'],filename)
            app.state.workflows.forms.register_form(manager,form['document_id'],form['id'],FormMetadata(title=title,purpose='합성 검토 자료'))
        wrapper=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
        wrapper.mount('/api',app);wrapper.mount('/',StaticFiles(directory=Path(__file__).resolve().parents[2]/'apps/web/dist',html=True))
        # Inherit a non-loopback Python socket guard into the independent worker.
        from scripts.validation.run_stage4b3a_checks import GUARD
        guard=root/'guard';guard.mkdir();(guard/'sitecustomize.py').write_text(GUARD)
        blocked=args.ready_file.with_suffix('.network-blocked.log').resolve()
        env={**os.environ,'PYTHONPATH':str(guard)+os.pathsep+os.environ.get('PYTHONPATH',''),'SB_NETWORK_GUARD_LOG':str(blocked)}
        process=subprocess.Popen([sys.executable,'-B','-m','apps.api.workflow_worker','--data-dir',str(root),'--institution-id','A'],
                                 env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        args.ready_file.write_text(json.dumps({'url':origin,'document_id':manual['document_id'],'version_id':manual['id'],
             'scope':'synthetic loopback mock identity; real BFF sessions/CSRF; no overrides; independent worker',
             'actual_external_provider_calls':0,'worker_pid':process.pid},ensure_ascii=False))
        try:uvicorn.Server(uvicorn.Config(wrapper,access_log=False,log_level='critical')).run(sockets=[sock])
        finally:
            process.terminate()
            try:process.wait(timeout=5)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
            for path in root.rglob('*'):
                if path.is_file():path.chmod(0o600)


if __name__=='__main__':main()
