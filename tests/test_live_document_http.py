"""Real loopback HTTP and subprocess restart, without external services or production auth bypass."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import httpx
from test_document_api import pdf


class LiveHTTPTests(unittest.TestCase):
    def test_real_http_and_process_restart(self):
        with tempfile.TemporaryDirectory(dir='work/phase2a') as directory:
            root = Path(directory)
            process = None
            try:
                for run in range(2):
                    ready = root / f'ready-{run}.json'
                    process = subprocess.Popen([sys.executable, 'scripts/validation/phase2a_http_server.py',
                        '--data-dir', str(root), '--ready-file', str(ready)],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    deadline = time.monotonic() + 15
                    while not ready.exists():
                        if process.poll() is not None or time.monotonic() > deadline:
                            self.fail('Uvicorn child failed to start within 15 seconds')
                        time.sleep(0.05)
                    address = json.loads(ready.read_text())['url']
                    with httpx.Client(base_url=address, timeout=3, trust_env=False) as client:
                        while True:
                            try:
                                health = client.get('/health')
                                break
                            except httpx.ConnectError:
                                if time.monotonic() > deadline:
                                    raise
                                time.sleep(0.05)
                        self.assertEqual(health.status_code, 200)
                        # Trusted mock principal is installed ONLY in this validation child.
                        if run == 0:
                            response = client.post('/documents?filename=live.pdf', content=pdf('live'),
                                headers={'Content-Type': 'application/pdf', 'X-Data-Classification': 'synthetic'})
                            self.assertEqual(response.status_code, 201, response.text)
                            meta = response.json()['document']
                            route = f"/documents/{meta['document_id']}/versions/{meta['id']}"
                            self.assertEqual(client.get(route + '/original').content, pdf('live'))
                        else:
                            restored = client.get('/documents?active_only=false').json()
                            self.assertEqual(restored[0]['id'], meta['id'])
                            self.assertEqual(client.get(route + '/original').content, pdf('live'))
                    process.terminate()
                    process.wait(timeout=5)
                    process = None
            finally:
                if process is not None:
                    process.kill()
                    process.wait(timeout=5)
                for path in root.rglob('*'):
                    if path.is_file():
                        path.chmod(0o666)
