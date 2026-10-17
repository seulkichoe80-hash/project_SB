"""Test-only kill checkpoint after a durable worker claim. No HTTP authentication bypass."""
import argparse
import json
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from apps.api.models import Principal
from apps.api.repository import Repository
from apps.api.service import DocumentService
from apps.api.storage import LocalOriginalStore
from apps.api.parsing_service import ParsingService

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--ready-file',type=Path,required=True)
    args = parser.parse_args()
    docs = DocumentService(Repository(args.data_dir/'metadata.sqlite3'), LocalOriginalStore(args.data_dir/'originals'), True)
    service = ParsingService(docs, lease_seconds=1)
    claim = service.claim(Principal('checkpoint-worker','A','worker'))
    if not claim:
        raise SystemExit(1)
    args.ready_file.write_text(json.dumps({'checkpoint':'claimed','attempt':claim['attempt']}))
    while True:
        time.sleep(.2)
