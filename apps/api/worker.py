"""Local trusted operator worker. Separate process, no HTTP background task or external API."""
import argparse
import os
from pathlib import Path
import threading
from .models import Principal
from .repository import Repository
from .service import DocumentService
from .storage import LocalOriginalStore
from .parsing_service import ParsingService


def run_once(service, principal):
    claim = service.claim(principal)
    if not claim:
        return 'idle'
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(max(.1, service.lease_seconds / 3)):
            try:
                if not service.renew(claim):
                    return
            except Exception:
                return  # Publication still checks unexpired ownership; never publish on a lost lease.
    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        return service.execute(principal, claim)
    finally:
        stop.set()
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--institution-id', required=True)
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--lease-seconds', type=float, default=30)
    parser.add_argument('--job-timeout-seconds', type=float, default=120)
    args = parser.parse_args()
    from .runtime_settings import ensure_start_environment
    ensure_start_environment('parse_worker')
    if not 1 <= args.lease_seconds <= 300 or not 1 <= args.job_timeout_seconds <= 3600:
        parser.error('lease must be 1..300, job timeout 1..3600 seconds')
    docs = DocumentService(Repository(args.data_dir / 'metadata.sqlite3'), LocalOriginalStore(args.data_dir / 'originals'), True)
    parsing = ParsingService(docs, lease_seconds=args.lease_seconds)
    principal = Principal('local-parser-worker', args.institution_id, 'worker')
    stop = threading.Event()
    try:
        while True:
            # A hung parser cannot renew forever. Process exit leaves an expiring durable claim.
            timeout = threading.Timer(args.job_timeout_seconds, lambda: os._exit(124))
            timeout.daemon = True
            timeout.start()
            try:
                result = run_once(parsing, principal)
            finally:
                timeout.cancel()
            print(result, flush=True)  # Fixed status only, never source content, keys or claim capabilities.
            if args.once:
                return 0 if result in ('completed', 'idle') else 1
            if result == 'idle':
                stop.wait(.5)
    except KeyboardInterrupt:
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
