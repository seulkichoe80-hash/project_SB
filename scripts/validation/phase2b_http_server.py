"""Loopback-only HTTP test harness with an explicit mock principal; never deploy."""
import argparse
import json
from pathlib import Path
import socket
import sys
import uvicorn
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.api.main import create_app, authenticated_principal
from apps.api.models import Principal

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--ready-file',type=Path,required=True)
    args = parser.parse_args()
    app = create_app(args.data_dir,parsing_enabled=True)
    app.dependency_overrides[authenticated_principal] = lambda:Principal('explicit-http-test','A','manager')
    sock = socket.socket()
    sock.bind(('127.0.0.1',0))
    sock.listen(128)
    args.ready_file.write_text(json.dumps({'url':f'http://127.0.0.1:{sock.getsockname()[1]}'}))
    uvicorn.Server(uvicorn.Config(app,access_log=False,log_level='critical')).run(sockets=[sock])
