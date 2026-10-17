"""Test-only durable chunk claim checkpoint for process-kill recovery verification."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.api.models import Principal
from apps.api.repository import Repository
from apps.api.service import DocumentService
from apps.api.storage import LocalOriginalStore
from apps.api.parsing_service import ParsingService
from apps.api.chunk_service import ChunkService

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--ready-file',type=Path,required=True)
    args=parser.parse_args()
    docs=DocumentService(Repository(args.data_dir/'metadata.sqlite3'),LocalOriginalStore(args.data_dir/'originals'),True)
    service=ChunkService(ParsingService(docs),lease_seconds=1)
    claim=service.claim(Principal('checkpoint-worker','A','worker'))
    if not claim:
        raise SystemExit(1)
    args.ready_file.write_text(json.dumps({'state':'claimed','lease_until':service.clock()+1}))
    while True:
        time.sleep(.2)
