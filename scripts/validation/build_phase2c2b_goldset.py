"""Prepare independently reviewable synthetic sources and real, locally resolved EvidenceRefs.
No model output is accepted as a source or answer. No network capability is used.
"""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path
import runpy
import sys
import time
import zipfile
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from apps.api.models import Principal
from apps.api.repository import Repository
from apps.api.service import DocumentService
from apps.api.storage import LocalOriginalStore
from apps.api.parsing_service import ParsingService
from apps.api.worker import run_once
from apps.api.chunk_service import ChunkService
from apps.api.chunking import ChunkConfig, EvidenceRef


def hwpx(paragraphs):
    """New derivative package; the original synthetic template is never edited."""
    template=ROOT/'tests/fixtures/synthetic/procedure-v2.hwpx'
    output=io.BytesIO()
    with zipfile.ZipFile(template) as original,zipfile.ZipFile(output,'w') as target:
        for entry in original.infolist():
            data=original.read(entry.filename)
            if entry.filename=='Contents/section0.xml':
                section=ET.fromstring(data)
                first=copy.deepcopy(section[0])
                for node in first.iter():
                    if node.tag.endswith('}t'):node.text='합성 평가자료: 실제 행정 규정이 아님'
                for child in list(section):section.remove(child)
                section.append(first)
                hp='{http://www.hancom.co.kr/hwpml/2011/paragraph}'
                for n,text in enumerate(paragraphs,1):
                    p=ET.SubElement(section,hp+'p',{'id':str(9000+n),'paraPrIDRef':'0','styleIDRef':'0','pageBreak':'0','columnBreak':'0','merged':'0'})
                    run=ET.SubElement(p,hp+'run',{'charPrIDRef':'0'})
                    ET.SubElement(run,hp+'t').text=text
                data=ET.tostring(section,encoding='utf-8',xml_declaration=True)
            target.writestr(entry,data)
    return output.getvalue()


def build(inputs, data_dir, output):
    started=time.perf_counter()
    if data_dir.exists() or output.exists():raise ValueError('new data/output paths required')
    data_dir.mkdir(parents=True)
    docs=DocumentService(Repository(data_dir/'metadata.sqlite3'),LocalOriginalStore(data_dir/'originals'),True)
    parsing=ParsingService(docs);chunks=ChunkService(parsing)
    registry={};manifest=[];queries=[]
    for spec in inputs['documents']:
        manager=Principal('goldset-manager',spec['organization_id'],'manager')
        worker=Principal('goldset-worker',spec['organization_id'],'worker')
        paragraphs=[spec['title']]+[c['text'] for c in spec['clauses']]
        data=hwpx(paragraphs)
        meta,_=docs.register(manager,spec['id']+'.hwpx','application/octet-stream',data)
        assert run_once(parsing,worker)=='completed'
        chunks.enqueue(manager,meta['document_id'],meta['id'],ChunkConfig(max_chars=800,context_chars=0))
        assert chunks.execute(worker,chunks.claim(worker))=='completed'
        docs.activate(manager,meta['document_id'],meta['id'])
        items=chunks.list(manager,meta['document_id'],meta['id'])
        by_clause={}
        for clause in spec['clauses']:
            matches=[c for c in items if c['text']==clause['text']]
            assert len(matches)==1,(spec['id'],clause['id'])
            item=matches[0]
            resolved=chunks.resolve(manager,meta['document_id'],meta['id'],item['chunk_id'],EvidenceRef.model_validate(item['evidence']))
            assert resolved['structural_valid']
            by_clause[clause['id']]=item['evidence']
        registry[spec['id']]={'meta':meta,'refs':by_clause,'organization_id':spec['organization_id']}
        manifest.append({'source':spec,'document_id':meta['document_id'],'version_id':meta['id'],
                         'sha256':hashlib.sha256(data).hexdigest(),'format':'hwpx','chunks':items,
                         'original_unchanged':docs.store.read(meta['id'],meta['sha256'])==data,
                         'visual_order':'NOT_VERIFIED','human_review':'PENDING'})
        for q in spec['queries']:
            refs=[by_clause[c] for c in q['clauses']]
            procedure=[{'step':i+1,'action':s['action'],'evidence_refs':[by_clause[c] for c in s['clauses']]} for i,s in enumerate(q['procedure'])]
            queries.append({**q,'organization_id':spec['organization_id'],'answer_status':'answerable',
                            'expected_evidence_refs':refs,'expected_procedure':procedure,
                            'abstain_if':['필수 원문 근거 미검색','기관/활성 버전 불일치','근거 충돌을 해소할 정보 없음']})
        (data_dir/(spec['id']+'.hwpx')).write_bytes(data)
    # Existing English PDF is an additional format control, not a Korean benchmark substitute.
    pdf=runpy.run_path(str(ROOT/'tests/fixtures/synthetic/phase2b_pdf.py'))['synthetic_pdf']()
    manager=Principal('goldset-manager','A','manager');worker=Principal('goldset-worker','A','worker')
    meta,_=docs.register(manager,'pdf-format-control.pdf','application/octet-stream',pdf)
    assert run_once(parsing,worker)=='completed'
    chunks.enqueue(manager,meta['document_id'],meta['id'],ChunkConfig())
    assert chunks.execute(worker,chunks.claim(worker))=='completed'
    docs.activate(manager,meta['document_id'],meta['id'])
    controls=chunks.list(manager,meta['document_id'],meta['id'])
    for c in controls:assert chunks.resolve(manager,meta['document_id'],meta['id'],c['chunk_id'],EvidenceRef.model_validate(c['evidence']))['structural_valid']
    manifest.append({'logical_id':'pdf-control','organization_id':'A','document_id':meta['document_id'],'version_id':meta['id'],
                     'sha256':meta['sha256'],'format':'pdf','chunks':controls,'original_unchanged':docs.store.read(meta['id'],meta['sha256'])==pdf})
    for q in inputs['safety_queries']:
        queries.append({**q,'expected_evidence_refs':[],'expected_procedure':[],
                        'forbidden_evidence_refs':[registry[d]['refs'][c] for d,c in q.get('forbidden_sources',[])]})
    assert len(queries)>=30 and len({q['id'] for q in queries})==len(queries)
    result={'scope':'synthetic-only; proposed human-reviewable answer key, no AI performance measured',
            'source_sha256':hashlib.sha256(json.dumps(inputs,ensure_ascii=False,sort_keys=True).encode()).hexdigest(),
            'human_review':'PENDING_INDEPENDENT_REVIEW','documents':manifest,'queries':queries,
            'counts':{'documents':len(manifest),'queries':len(queries),'answerable':sum(q['answer_status']=='answerable' for q in queries)},
            'data_dir':str(data_dir.relative_to(ROOT)),'elapsed_seconds':time.perf_counter()-started,'actual_model_calls':0}
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-dir',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    source=json.loads((ROOT/'tests/fixtures/synthetic/phase2c2b-sources.json').read_text(encoding='utf-8'))
    result=build(source,args.data_dir.resolve(),args.output.resolve())
    print(json.dumps({'counts':result['counts'],'elapsed_seconds':result['elapsed_seconds'],'model_calls':0}))
