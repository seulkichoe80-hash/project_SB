"""Persist and re-resolve every sample block using public/synthetic inputs only."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from apps.api.models import Principal
from apps.api.repository import Repository
from apps.api.service import DocumentService
from apps.api.storage import LocalOriginalStore
from apps.api.parsing_service import ParsingService, EvidenceRequest
from apps.api.worker import run_once

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists() or args.data_dir.exists():
        parser.error('choose new output and data directories')
    docs = DocumentService(Repository(args.data_dir/'metadata.sqlite3'),LocalOriginalStore(args.data_dir/'originals'),True)
    parsing = ParsingService(docs)
    principal = Principal('synthetic-evidence-manager','evidence-institution','manager')
    worker = Principal('synthetic-evidence-worker','evidence-institution','worker')
    pdf = runpy.run_path('tests/fixtures/synthetic/phase2b_pdf.py')['synthetic_pdf']()
    files = [('generated-two-page.pdf',pdf),('procedure-v2.hwpx',Path('tests/fixtures/synthetic/procedure-v2.hwpx').read_bytes())]
    evidence = {'kind':'synthetic-only','documents':[],'visual_hancom':'NOT_RUN','semantic_accuracy':'NOT_VERIFIED'}
    for filename,data in files:
        meta,_ = docs.register(principal,filename,'application/octet-stream',data)
        assert run_once(parsing,worker) == 'completed'
        blocks = parsing.blocks(principal,meta['document_id'],meta['id'])
        for block in blocks:
            request = EvidenceRequest.model_validate({'source_anchor':block['source_anchor']})
            assert parsing.resolve(principal,meta['document_id'],meta['id'],request)['structural_valid']
        assert docs.store.read(meta['id'],meta['sha256']) == data
        evidence['documents'].append({'metadata':docs.get(principal,meta['document_id'],meta['id']),
            'original_sha256':hashlib.sha256(data).hexdigest(),'original_unchanged':True,
            'job':parsing.status(principal,meta['document_id'],meta['id']),
            'anchors_resolved':len(blocks),'blocks':blocks})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({d['metadata']['format']:{'blocks':len(d['blocks']),'anchors_resolved':d['anchors_resolved']}
                      for d in evidence['documents']}))
