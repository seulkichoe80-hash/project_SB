"""Independent chunk worker; claims survive process death. No external calls."""
import argparse
from pathlib import Path
import time
from .repository import Repository
from .storage import LocalOriginalStore
from .service import DocumentService
from .parsing_service import ParsingService
from .chunk_service import ChunkService
from .models import Principal

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--institution-id',required=True)
    parser.add_argument('--once',action='store_true')
    args = parser.parse_args()
    from .runtime_settings import ensure_start_environment
    ensure_start_environment('chunk_worker')
    docs = DocumentService(Repository(args.data_dir/'metadata.sqlite3'),LocalOriginalStore(args.data_dir/'originals'),True)
    service = ChunkService(ParsingService(docs))
    principal = Principal('local-chunk-worker',args.institution_id,'worker')
    try:
        while True:
            claim = service.claim(principal)
            result = service.execute(principal,claim) if claim else 'idle'
            print(result,flush=True)
            if args.once:
                raise SystemExit(0 if result in ('completed','idle') else 1)
            if not claim:
                time.sleep(.5)
    except KeyboardInterrupt:
        pass
