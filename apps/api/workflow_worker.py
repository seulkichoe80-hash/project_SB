"""Trusted local offline workflow worker. Durable leases survive process death."""
import argparse
import os
from pathlib import Path
import threading
from .repository import Repository
from .storage import LocalOriginalStore
from .service import DocumentService
from .parsing_service import ParsingService
from .chunk_service import ChunkService
from .workflow_jobs import WorkflowJobService
from .worker import run_once
from .models import Principal


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--institution-id',required=True)
    parser.add_argument('--lease-seconds',type=float,default=120)
    parser.add_argument('--job-timeout-seconds',type=float,default=600)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if not 1<=args.lease_seconds<=300 or not 1<=args.job_timeout_seconds<=3600:
        parser.error('invalid lease or timeout')
    docs=DocumentService(Repository(args.data_dir/'metadata.sqlite3'),LocalOriginalStore(args.data_dir/'originals'),True)
    service=WorkflowJobService(ChunkService(ParsingService(docs)),lease_seconds=args.lease_seconds)
    principal=Principal('local-offline-workflow-worker',args.institution_id,'worker')
    stop=threading.Event()
    try:
        while True:
            timer=threading.Timer(args.job_timeout_seconds,lambda:os._exit(124));timer.daemon=True;timer.start()
            try:result=run_once(service,principal)
            finally:timer.cancel()
            print(result,flush=True) # fixed status, never claim tokens/source/error messages
            if args.once:return 0 if result in ('completed','idle') else 1
            if result=='idle':stop.wait(.5)
    except KeyboardInterrupt:return 0


if __name__=='__main__':raise SystemExit(main())
