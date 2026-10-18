"""Synthetic evaluation generations; never changes the historical answer key or product search."""
import copy
import hashlib
import json
import re
from pathlib import Path
import time
import subprocess
import sys
from apps.api.chunking import Chunk, ChunkConfig, EvidenceRef, build_chunks, canonical, digest
from apps.api.errors import DomainError
from apps.api.models import Principal
from apps.api.parsers import default_parsers
from apps.api.parsing_service import ParsingService
from apps.api.repository import Repository
from apps.api.service import DocumentService
from apps.api.storage import LocalOriginalStore
from apps.api.workflow_snapshot import WorkflowInputService
from apps.api.chunk_service import ChunkService

ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'tests/fixtures/synthetic/phase2c2b-sources.json'
HISTORICAL=ROOT/'outputs/phase2c2b/GOLDSET_REVIEW.json'


def sha_file(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def services(data_dir):
    docs=DocumentService(Repository(Path(data_dir)/'metadata.sqlite3'),LocalOriginalStore(Path(data_dir)/'originals'),True)
    return ChunkService(ParsingService(docs))


def logical_id(doc):return doc.get('logical_id') or doc['source']['id']


def normalized_chunks(chunks):
    """Compare content/locations/quotes, excluding intentionally new UUID-derived identifiers."""
    def clean(value):
        if isinstance(value,dict):
            return {k:clean(v) for k,v in value.items() if k not in {'organization_id','document_id','version_id','chunk_id','source_block_ids','block_id','table_block_id','cell_block_id'}}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    return clean(chunks)


def check_answer_key(source, historical):
    """Fail instead of silently repairing ambiguous/mismatched proposed answers."""
    expected={q['id']:{**q,'organization_id':s['organization_id'],'answer_status':'answerable'}
              for s in source['documents'] for q in s['queries']}
    expected.update({q['id']:q for q in source['safety_queries']})
    if len(expected)!=40 or len(historical['queries'])!=40 or len({q['id'] for q in historical['queries']})!=40:
        raise ValueError('evaluation_question_count_or_duplicate')
    for q in historical['queries']:
        e=expected.get(q['id'])
        if not e or any(q.get(k)!=v for k,v in e.items()):raise ValueError('historical_answer_key_mismatch')
    return True


def reproduce(data_dir, output_dir):
    """Fresh DB/versions/jobs; frozen copies plus live resolved citations for all 40 rows."""
    started=time.perf_counter();data_dir=Path(data_dir).resolve();output_dir=Path(output_dir).resolve()
    if data_dir.exists() or output_dir.exists():raise ValueError('new_generation_paths_required')
    source=json.loads(SOURCE.read_text());historical=json.loads(HISTORICAL.read_text());check_answer_key(source,historical)
    # ElementTree namespace registrations in an embedding process can change serialized ZIP bytes.
    # The existing generator runs in a fresh interpreter; inherited socket guards remain active.
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/validation/build_phase2c2b_goldset.py'),
        '--data-dir',str(data_dir),'--output',str(output_dir/'generation.json')],
        check=True,capture_output=True,text=True,timeout=60,cwd=ROOT)
    result=json.loads((output_dir/'generation.json').read_text())
    chunks=services(data_dir);snapshots=WorkflowInputService(chunks)
    old={logical_id(d):d for d in historical['documents']};comparison=[];by_version={}
    corpus=output_dir/'corpus';corpus.mkdir()
    for doc in result['documents']:
        name=logical_id(doc);org=doc.get('organization_id') or doc['source']['organization_id']
        manager=Principal('evaluation-manager',org,'manager');reader=Principal('evaluation-reader',org,'reader')
        snap=snapshots.capture(manager,doc['document_id'],doc['version_id'])
        if snap.selected_active_version_id!=doc['version_id']:raise ValueError('inactive_evaluation_version')
        doc['snapshot']=snap.model_dump(mode='json');doc['organization_id']=org;doc['logical_id']=name
        filename=name+'.'+doc['format'];raw=chunks.documents.store.read(doc['version_id'],doc['sha256'])
        (corpus/filename).write_bytes(raw);doc['frozen_original']='corpus/'+filename
        doc['resolved_chunk_count']=0
        for c in doc['chunks']:
            ref=EvidenceRef.model_validate(c['evidence']);resolved=chunks.resolve(reader,ref.document_id,ref.version_id,ref.chunk_id,ref)
            if not resolved['structural_valid']:raise ValueError('unresolved_chunk')
            doc['resolved_chunk_count']+=1
        previous=old[name]
        historical_blocks=default_parsers()[doc['format']].parse(raw,previous['document_id'],previous['version_id'])
        historical_replay=build_chunks(historical_blocks,org,snap.chunk_config)
        comparison.append({'logical_id':name,'original_sha256_match':doc['sha256']==previous['sha256'],
            'exact_historical_id_replay_match':[c.model_dump(mode='json') for c in historical_replay]==previous['chunks'],
            'old_chunk_count':len(previous['chunks']),'new_chunk_count':len(doc['chunks']),
            'normalized_chunk_content_match':normalized_chunks(doc['chunks'])==normalized_chunks(previous['chunks']),
            'document_id_changed':doc['document_id']!=previous['document_id'],
            'version_id_changed':doc['version_id']!=previous['version_id'],
            'reason':'New UUID-scoped document/version and parse/chunk jobs; compare locations/content without those IDs.'})
        by_version[doc['version_id']]=doc
    old_q={q['id']:q for q in historical['queries']};relinks=[]
    for q in result['queries']:
        for field in ('expected_evidence_refs','forbidden_evidence_refs'):
            refs=q.get(field,[]);before=old_q[q['id']].get(field,[])
            if len(refs)!=len(before):raise ValueError('reference_count_changed')
            for prior,current in zip(before,refs):
                doc=by_version[current['version_id']]
                owner=Principal('evaluation-reader',doc['organization_id'],'reader')
                if field=='expected_evidence_refs' and q['organization_id']!=owner.institution_id:raise ValueError('foreign_gold_evidence')
                chunks.resolve(owner,current['document_id'],current['version_id'],current['chunk_id'],EvidenceRef.model_validate(current))
                if normalized_chunks([{'evidence':prior}])!=normalized_chunks([{'evidence':current}]):
                    raise ValueError('citation_content_changed')
                relinks.append({'query_id':q['id'],'role':field,'old_chunk_id':prior['chunk_id'],'new_chunk_id':current['chunk_id'],
                    'status':'STRUCTURALLY_RESOLVED','semantic_verification':'NOT_VERIFIED',
                    'accessible_to_question_tenant':owner.institution_id==q['organization_id']})
        q['human_review']='PENDING_INDEPENDENT_REVIEW'
    result.update({'schema_version':'evaluation-generation-v1','source_file_sha256':sha_file(SOURCE),
        'historical_file_sha256':sha_file(HISTORICAL),'generation_id':digest([d['snapshot']['snapshot_id'] for d in result['documents']]),
        'comparison':comparison,'reference_relinks':relinks,'elapsed_seconds':time.perf_counter()-started,
        'coverage':{'expected_chunks':57,'actual_chunks':sum(len(d['chunks']) for d in result['documents']),
            'relinked':len(relinks),'failed':0,'unverified':0},
        'semantic_verification':'NOT_VERIFIED','human_review':'PENDING_INDEPENDENT_REVIEW',
        'data_dir':str(data_dir),'actual_model_calls':0})
    (output_dir/'generation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    return result


def verify_frozen(generation, output_dir):
    """Replay real parser+chunker using pinned version IDs; byte-level canonical equality."""
    results=[]
    for d in generation['documents']:
        name=logical_id(d)
        if not re.fullmatch(r'[a-z][a-z0-9-]{0,80}',name) or d['format'] not in ('pdf','hwpx') or d['frozen_original']!='corpus/'+name+'.'+d['format']:
            raise ValueError('invalid_frozen_original_path')
        path=(Path(output_dir)/d['frozen_original'])
        if path.is_symlink() or path.resolve().parent!=(Path(output_dir)/'corpus').resolve():raise ValueError('invalid_frozen_original_path')
        raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=d['sha256']:raise ValueError('frozen_original_hash_mismatch')
        s=d['snapshot'];blocks=default_parsers()[d['format']].parse(raw,d['document_id'],d['version_id'])
        if [b.model_dump(mode='json') for b in blocks]!=s['source_blocks']:raise ValueError('parser_replay_mismatch')
        rebuilt=build_chunks(blocks,d['organization_id'],ChunkConfig.model_validate(s['chunk_config']))
        if [c.model_dump(mode='json') for c in rebuilt]!=d['chunks']:raise ValueError('chunk_replay_mismatch')
        results.append({'logical_id':logical_id(d),'hash_match':True,'parser_match':True,'chunk_match':True,'chunks':len(rebuilt)})
    return results


class LiveEvidenceResolver:
    """Frozen generation is not proof of live activity: revalidate snapshot and tenant on every use."""
    def __init__(self,chunks,generation):
        self.chunks=chunks;self.generation=copy.deepcopy(generation)
        self.by_version={d['version_id']:d for d in self.generation['documents']}
    def __call__(self,organization_id,raw):
        from apps.api.workflow_snapshot import WorkflowInputSnapshot
        ref=EvidenceRef.model_validate(raw);doc=self.by_version.get(ref.version_id)
        if not doc or ref.organization_id!=organization_id or doc['organization_id']!=organization_id:
            raise DomainError('foreign_evaluation_evidence',404)
        manager=Principal('evaluation-manager',organization_id,'manager')
        current=WorkflowInputService(self.chunks).capture(manager,doc['document_id'],doc['version_id'])
        frozen=WorkflowInputSnapshot.model_validate_json(canonical(doc['snapshot']))
        if current.snapshot_id!=frozen.snapshot_id or current.selected_active_version_id!=ref.version_id:
            raise DomainError('stale_evaluation_generation',409)
        return self.chunks.resolve(Principal('evaluation-reader',organization_id,'reader'),ref.document_id,ref.version_id,ref.chunk_id,ref)


class EvaluationQueryAdapter:
    """Question-only contiguous windows, never answer-driven rewrite or silent truncation.

    This is a retrieval protocol variant, not equivalent to the product's whole-question AND.
    It does not claim semantic relevance or call a model.
    """
    version='evaluation-window-rrf-v1'
    def __init__(self,chunks,resolver):self.chunks,self.resolver=chunks,resolver
    @staticmethod
    def windows(question):
        if not isinstance(question,str) or not question.strip() or len(question)>2000 or len(question.split())>128:
            raise ValueError('evaluation_question_limit')
        terms=question.split();parts=[];current=[]
        for term in terms:
            if len(term)>200:raise ValueError('evaluation_term_limit')
            if current and (len(current)==8 or len(' '.join(current+[term]))>200):
                parts.append(' '.join(current));current=[]
            current.append(term)
        if current:parts.append(' '.join(current))
        return parts
    def search(self,principal,question,limit=10):
        if principal is None or principal.role not in ('reader','manager'):raise DomainError('evaluation_access_denied',403)
        if type(limit) is not int or not 1<=limit<=20:raise ValueError('evaluation_result_limit')
        started=time.perf_counter();windows=self.windows(question);scores={};items={}
        try:
            for w in windows:
                seen=set()
                for rank,item in enumerate(self.chunks.search(principal,w,50),1):
                    Chunk.model_validate(item)
                    ref=item['evidence'];key=(ref['document_id'],ref['version_id'],ref['chunk_id'])
                    if key in seen:raise DomainError('duplicate_evaluation_result',422)
                    seen.add(key)
                    self.resolver(principal.institution_id,ref)
                    items[key]=item;scores[key]=scores.get(key,0)+1/(60+rank)
            keys=sorted(items,key=lambda k:(-scores[k],k))[:limit]
            for k in keys:self.resolver(principal.institution_id,items[k]['evidence'])
        except (DomainError,ValueError) as error:
            return {'status':'retrieval_failed','error_code':error.code if isinstance(error,DomainError) else 'invalid_evaluation_result','question':question,'windows':windows,'results':[],
                'seconds':time.perf_counter()-started,'protocol':self.version,'ai_performance_eligible':False}
        return {'status':'retrieved' if keys else 'no_hits','question':question,'windows':windows,
            'results':[items[k] for k in keys],'seconds':time.perf_counter()-started,'protocol':self.version,
            'ai_performance_eligible':False,'actual_model_calls':0}
