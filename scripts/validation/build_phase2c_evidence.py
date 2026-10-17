"""Synthetic local chunk/EvidenceRef/search evidence. No models or external services."""
import argparse
import json
from pathlib import Path
import runpy
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.api.models import Principal
from apps.api.repository import Repository
from apps.api.service import DocumentService
from apps.api.storage import LocalOriginalStore
from apps.api.parsing_service import ParsingService
from apps.api.worker import run_once
from apps.api.chunk_service import ChunkService
from apps.api.chunking import ChunkConfig,EvidenceRef

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists() or args.data_dir.exists():
        parser.error('choose new data/output paths')
    docs=DocumentService(Repository(args.data_dir/'metadata.sqlite3'),LocalOriginalStore(args.data_dir/'originals'),True)
    parsing=ParsingService(docs)
    chunks=ChunkService(parsing)
    manager=Principal('synthetic-manager','evidence-organization','manager')
    worker=Principal('synthetic-worker','evidence-organization','worker')
    pdf=runpy.run_path('tests/fixtures/synthetic/phase2b_pdf.py')['synthetic_pdf']()
    inputs=[('manual.pdf',pdf),('manual.hwpx',Path('tests/fixtures/synthetic/procedure-v2.hwpx').read_bytes())]
    result={'date_kst':'2026-10-17','synthetic_only':True,'documents':[],'semantic_verification':'NOT_VERIFIED'}
    for filename,data in inputs:
        meta,_=docs.register(manager,filename,'application/octet-stream',data)
        assert run_once(parsing,worker)=='completed'
        job=chunks.enqueue(manager,meta['document_id'],meta['id'],ChunkConfig())
        assert chunks.execute(worker,chunks.claim(worker))=='completed'
        items=chunks.list(manager,meta['document_id'],meta['id'])
        for c in items:
            resolved=chunks.resolve(manager,meta['document_id'],meta['id'],c['chunk_id'],EvidenceRef.model_validate(c['evidence']))
            assert resolved['structural_valid']
        docs.activate(manager,meta['document_id'],meta['id'])
        assert docs.store.read(meta['id'],meta['sha256'])==data
        result['documents'].append({'document_id':meta['document_id'],'version_id':meta['id'],
            'format':meta['format'],'sha256':meta['sha256'],'original_unchanged':True,
            'resolved_chunks':len(items),'chunks':items})
    result['keyword_hits']={q:len(chunks.search(manager,q)) for q in ('Prepare','신청','manual.pdf')}
    assert all(result['keyword_hits'].values())
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'resolved':{d['format']:d['resolved_chunks'] for d in result['documents']},
                      'keyword_hits':result['keyword_hits']},ensure_ascii=False))
