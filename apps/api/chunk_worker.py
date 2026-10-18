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

def main(argv=None,runtime_binding=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--institution-id',required=True)
    parser.add_argument('--once',action='store_true')
    from .postgres_worker import add_postgres_arguments, worker_repository
    add_postgres_arguments(parser)
    args = parser.parse_args(argv)
    from .runtime_settings import ensure_start_environment
    ensure_start_environment('chunk_worker')
    from .runtime_wiring import worker_documents
    docs = worker_documents(args,'chunk_worker',runtime_binding)
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


if __name__=='__main__':main()
