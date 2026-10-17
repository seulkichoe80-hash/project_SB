"""Synthetic-only retrieval contract evaluation; no provider calls or semantic PASS."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from test_rag_contracts import RAGTests
import test_parsing as fixtures
from apps.api.rag_adapters import DeterministicEmbedding, ExtractiveTestLLM
from apps.api.rag_service import RAGService
from apps.api.models import Principal
from scripts.validation.evaluate_retrieval import score


def evaluate():
    harness=RAGTests();harness.setUp()
    try:
        dataset=json.loads((ROOT/'tests/fixtures/synthetic/rag-goldset.json').read_text(encoding='utf-8'))
        by_doc={};manifest=[];registry={}
        for entry in dataset['documents']:
            data=fixtures.pdf() if entry['id']=='pdf' else fixtures.HWPX.read_bytes()
            meta,chunks=harness.active(data,entry['id']+'.'+entry['id'])
            by_doc[entry['id']]=chunks
            manifest.append({'logical_id':entry['id'],'sha256':hashlib.sha256(data).hexdigest(),
                             'metadata':meta,'chunks':chunks,'source':'project-authored synthetic fixture'})
            for c in chunks:registry[c['chunk_id']]={'tenant_id':'A','active':True}
        harness.rag.index(harness.principal)
        queries=[];rankings={mode:{} for mode in ('keyword','vector','hybrid')};latency={mode:[] for mode in rankings}
        for row in dataset['queries']:
            expected=[c['chunk_id'] for c in by_doc[row['document']] if row['expected_quote'] and row['expected_quote'] in c['text']]
            if row['expected_quote'] and not expected:raise ValueError('unresolved expected quote: '+row['id'])
            q={'id':row['id'],'expected':expected,'allowed_tenants':['B'] if row.get('foreign') else ['A']}
            queries.append(q)
            principal=Principal('synthetic-reader','B','reader') if row.get('foreign') else harness.principal
            for mode in rankings:
                start=time.perf_counter();result=harness.rag.search(principal,row['query'],5,mode)
                latency[mode].append(time.perf_counter()-start)
                rankings[mode][row['id']]=[r['chunk']['chunk_id'] for r in result['results']]
        return {'scope':'synthetic development subset; NOT real embedding evaluation; human review pending',
                'test_only':True,'dataset':dataset,'manifest':manifest,
                'embedding_spec':harness.rag.embedding.spec.model_dump(),'queries':queries,'rankings':rankings,
                'metrics':{mode:score(queries,r,registry,mode='metric_fixture') for mode,r in rankings.items()},
                'latency_seconds':latency,'actual_model_calls':0,'full_goldset':'NOT_RUN'}
    finally:harness.tearDown()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('existing evidence must not be overwritten')
    result=evaluate();args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result['metrics']))
