"""Explicit loopback-only synthetic demo, separate from production create_app defaults."""
import argparse
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from apps.api.main import create_app
from apps.api.auth import AuthSettings
from apps.api.identity_provider import MockSupabaseTransport, SupabaseProviderAdapter
from apps.api.models import Principal
from apps.api.chunking import ChunkConfig
from apps.api.workflow_forms_models import FormMetadata
from scripts.validation.run_stage4b3a_checks import GUARD


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--synthetic-loopback-test', action='store_true', required=True)
    parser.add_argument('--ready-file', type=Path, required=True)
    parser.add_argument('--assets-dir', type=Path, default=ROOT / 'tests/fixtures/synthetic/v01')
    args = parser.parse_args()
    if args.ready_file.exists(): parser.error('new ready path required')
    args.ready_file.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(); sock.bind(('127.0.0.1', 0)); sock.listen(128)
    origin = f'http://127.0.0.1:{sock.getsockname()[1]}'
    issuer = 'https://synthetic.invalid/auth/v1'
    accounts = {'v01-manager@example.test': 'v01-manager', 'v01-reader@example.test': 'v01-reader'}
    def mock(method, path, headers, body):
        if method == 'POST':
            subject = accounts.get(body.get('email'))
            if not subject or body.get('password') != 'synthetic-local-only': return 401, {}
            return 200, {'access_token': 'synthetic-' + subject, 'expires_in': 600}
        subject = headers.get('Authorization', '').removeprefix('Bearer synthetic-')
        return (200, {'id': subject, 'user_metadata': {'role': 'manager', 'institution_id': 'B'}}) if subject in accounts.values() else (401, {})
    with tempfile.TemporaryDirectory(prefix='sb-v01-demo-') as directory:
        root = Path(directory); guard = root / 'guard'; guard.mkdir()
        (guard / 'sitecustomize.py').write_text(GUARD)
        blocked = args.ready_file.with_suffix('.network-blocked.log').resolve()
        os.environ['SB_NETWORK_GUARD_LOG'] = str(blocked)
        exec(GUARD, {})  # Guard this server too; subprocesses inherit sitecustomize.
        env = {**os.environ, 'PYTHONPATH': str(guard) + os.pathsep + os.environ.get('PYTHONPATH', '')}
        app = create_app(root, parsing_enabled=True,
                         identity_provider=SupabaseProviderAdapter(MockSupabaseTransport(mock), issuer),
                         auth_settings=AuthSettings(origin=origin, secure_cookie=False))
        manager_id = app.state.auth.store.provision(issuer, 'v01-manager', 'A', '합성 연구지원기관', 'manager', True)
        app.state.auth.store.provision(issuer, 'v01-reader', 'A', '합성 연구지원기관', 'reader', False)
        manager = Principal(manager_id, 'A', 'manager'); worker = Principal('synthetic-setup-worker', 'A', 'worker')
        # Only form catalog prerequisites are seeded. Both manuals are uploaded over real HTTP by the browser.
        for title, filename in [('자료대여신청서', 'v01-request-form.hwpx'), ('결과보고서', 'v01-report-a.hwpx'), ('결과보고서', 'v01-report-b.hwpx')]:
            meta, _ = app.state.service.register(manager, filename, 'application/hwp+zip', (args.assets_dir / filename).read_bytes())
            assert app.state.parsing.execute(worker, app.state.parsing.claim(worker)) == 'completed'
            app.state.chunks.enqueue(manager, meta['document_id'], meta['id'], ChunkConfig())
            assert app.state.chunks.execute(worker, app.state.chunks.claim(worker)) == 'completed'
            app.state.service.activate(manager, meta['document_id'], meta['id'])
            app.state.workflows.forms.register_form(manager, meta['document_id'], meta['id'], FormMetadata(title=title, purpose='합성 검토 자료'))
        foreign, _ = app.state.service.register(Principal('synthetic-B-manager', 'B', 'manager'),
                                               'foreign-synthetic.hwpx', 'application/hwp+zip', (args.assets_dir / 'v01-manual.hwpx').read_bytes())
        wrapper = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
        wrapper.mount('/deny', create_app(root / 'deny', parsing_enabled=True))
        wrapper.mount('/api', app)
        wrapper.mount('/', StaticFiles(directory=ROOT / 'apps/web/dist', html=True))
        processes = []
        try:
            for module in ['worker', 'chunk_worker', 'workflow_worker']:
                processes.append(subprocess.Popen([sys.executable, '-B', '-m', 'apps.api.' + module,
                                  '--data-dir', str(root), '--institution-id', 'A'], env=env,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
            args.ready_file.write_text(json.dumps({'url': origin, 'data_dir': str(root), 'guard_dir': str(guard),
                'network_log': str(blocked), 'worker_pids': dict(zip(['parse', 'chunk', 'workflow'], [p.pid for p in processes])),
                'foreign_document': {'document_id': foreign['document_id'], 'id': foreign['id']},
                'scope': 'synthetic loopback mock identities; actual HTTP sessions and independent workers; no production auth changes'}))
            # SIGTERM shuts down Uvicorn; finally always stops only these owned workers.
            uvicorn.Server(uvicorn.Config(wrapper, log_level='critical', access_log=False)).run(sockets=[sock])
        finally:
            for process in processes:
                if process.poll() is None: process.terminate()
            for process in processes:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
            for path in root.rglob('*'):
                if path.is_file(): path.chmod(0o600)


if __name__ == '__main__': main()
