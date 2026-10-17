import secrets
import time
from .chunking import Block, Chunk, ChunkConfig, EvidenceRef, build_chunks, canonical, digest
from .errors import DomainError
from .parsers import default_parsers
from .parsers.contracts import validate_batch


class SQLiteKeywordSearch:
    def search(self,db,organization,terms,limit):
        return db.chunks.search(organization,terms,limit)


class ChunkService:
    def __init__(self,parsing,clock=time.time,lease_seconds=120,search_adapter=None):
        self.parsing = parsing
        self.documents = parsing.documents
        self.repo = parsing.repo
        self.clock,self.lease_seconds = clock,lease_seconds
        self.search_adapter = search_adapter or SQLiteKeywordSearch()

    @staticmethod
    def public(job):
        return {k:v for k,v in dict(job).items() if k != 'claim_hash'}

    def source(self,db,principal,document_id,version_id):
        doc,version = self.documents.version(db,principal,document_id,version_id)
        parsed = db.parsing.job(version_id)
        if not parsed or parsed['state'] != 'completed':
            raise DomainError('parsing_not_ready')
        payload = db.parsing.blocks(version_id)
        return doc,version,parsed,payload

    def enqueue(self,principal,document_id,version_id,config):
        self.documents.role(principal,'manager')
        with self.repo.transaction() as db:
            _,_,parsed,payload = self.source(db,principal,document_id,version_id)
            job = db.chunks.enqueue(version_id,parsed,canonical(config.model_dump()),digest(payload),self.clock())
            return self.public(job)

    def status(self,principal,document_id,version_id,job_id):
        with self.repo.transaction() as db:
            doc,_ = self.documents.version(db,principal,document_id,version_id)
            if principal.role != 'manager' and doc['active_version_id'] != version_id:
                raise DomainError('version_not_found',404)
            job = db.chunks.job(job_id)
            if not job or job['version_id'] != version_id:
                raise DomainError('chunk_job_not_found',404)
            return self.public(job)

    def retry(self,principal,document_id,version_id,job_id):
        self.documents.role(principal,'manager')
        self.status(principal,document_id,version_id,job_id)
        with self.repo.transaction() as db:
            self.documents.version(db,principal,document_id,version_id)
            job = db.chunks.job(job_id)
            if job['state'] != 'failed':
                raise DomainError('chunk_job_not_failed')
            db.chunks.retry(job_id)
            return self.public(db.chunks.job(job_id))

    def claim(self,principal):
        self.documents.role(principal,'worker')
        with self.repo.transaction() as db:
            return db.chunks.claim(principal.institution_id,secrets.token_hex(32),self.clock(),self.lease_seconds)

    def execute(self,principal,claim):
        self.documents.role(principal,'worker')
        try:
            with self.repo.transaction() as db:
                _,version,parsed,payload = self.source(db,principal,claim['document_id'],claim['version_id'])
                if not db.chunks.owned(claim,self.clock()):
                    return 'stale'
            data = self.documents.store.read(version['id'],version['sha256'])
            blocks = [Block.model_validate(b) for b in payload]
            normal = default_parsers()[version['format']].parse(data,claim['document_id'],version['id'])
            validate_batch(blocks,normal,claim['document_id'],version['id'])
            chunks = build_chunks(blocks,principal.institution_id,ChunkConfig.model_validate_json(claim['config']))
            if not chunks:
                raise DomainError('no_chunks')
            with self.repo.transaction() as db:
                _,version,current,latest = self.source(db,principal,claim['document_id'],claim['version_id'])
                if not db.chunks.owned(claim,self.clock()):
                    return 'stale'
                if current['id'] != claim['parse_job_id'] or current['attempt'] != claim['parse_attempt'] or digest(latest) != claim['input_hash']:
                    raise DomainError('source_generation_changed')
                titles = '\n'.join(b.text for b in blocks if b.block_type == 'heading')
                db.chunks.finish(claim,chunks,version['original_name'],titles)
            return 'completed'
        except Exception as error:
            code = error.code if isinstance(error,DomainError) else 'chunk_internal_failure'
            with self.repo.transaction() as db:
                self.documents.version(db,principal,claim['document_id'],claim['version_id'],False)
                if not db.chunks.owned(claim,self.clock()):
                    return 'stale'
                db.chunks.fail(claim,code)
            return 'failed'

    def list(self,principal,document_id,version_id):
        with self.repo.transaction() as db:
            doc,version,parsed,_ = self.source(db,principal,document_id,version_id)
            if principal.role != 'manager' and doc['active_version_id'] != version_id:
                raise DomainError('version_not_found',404)
            job = db.chunks.current(version_id)
            if not job or job['state'] != 'completed' or job['parse_attempt'] != parsed['attempt'] or job['parse_job_id'] != parsed['id']:
                raise DomainError('chunking_not_ready')
            self.documents.store.read(version_id,version['sha256'])
            return db.chunks.items(job['id'])

    def resolve(self,principal,document_id,version_id,chunk_id,evidence):
        if evidence.organization_id != principal.institution_id:
            raise DomainError('foreign_evidence',404)
        chunks = self.list(principal,document_id,version_id)
        chunk = next((Chunk.model_validate(c) for c in chunks if c['chunk_id'] == chunk_id),None)
        if chunk is None:
            raise DomainError('chunk_not_found',404)
        if chunk.evidence != evidence:
            raise DomainError('evidence_mismatch',422)
        with self.repo.transaction() as db:
            _,version,_,payload = self.source(db,principal,document_id,version_id)
            data = self.documents.store.read(version_id,version['sha256'])
            blocks = [Block.model_validate(b) for b in payload]
            normal = default_parsers()[version['format']].parse(data,document_id,version_id)
            validate_batch(blocks,normal,document_id,version_id)
            sources = {b.block_id:b for b in blocks}
            for span in evidence.spans:
                block = sources.get(span.block_id)
                if block is None or span.source_anchor != block.source_anchor or span.quote != block.text[span.start:span.end]:
                    raise DomainError('invalid_evidence_anchor',422)
            return {'evidence':evidence.model_dump(mode='json'),'source_blocks':[sources[i].model_dump(mode='json') for i in evidence.source_block_ids],
                    'structural_valid':True,'semantic_verification':'NOT_VERIFIED','content_origin':'original'}

    def search(self,principal,query,limit=20):
        terms = query.casefold().split()
        if not 1 <= len(terms) <= 8 or len(query)>200 or not 1 <= limit <= 50:
            raise DomainError('invalid_search_query',400)
        with self.repo.transaction() as db:
            results = self.search_adapter.search(db,principal.institution_id,terms,limit)
            checked = {}
            for item in results:
                Chunk.model_validate(item)
                ref = EvidenceRef.model_validate(item['evidence'])
                if ref.organization_id != principal.institution_id:
                    raise DomainError('invalid_search_evidence')
                key = (ref.document_id,ref.version_id)
                if key not in checked:
                    doc,version = self.documents.version(db,principal,*key)
                    if doc['active_version_id'] != version['id']:
                        raise DomainError('inactive_search_evidence')
                    current = db.chunks.current(version['id'])
                    if not current or current['state'] != 'completed':
                        raise DomainError('chunking_not_ready')
                    self.documents.store.read(version['id'],version['sha256'])
                    checked[key] = {c['chunk_id']:c for c in db.chunks.items(current['id'])}
                if checked[key].get(item['chunk_id']) != item:
                    raise DomainError('invalid_search_result')
            return results
