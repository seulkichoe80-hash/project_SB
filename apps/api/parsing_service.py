import hashlib
import secrets
import time
from pydantic import BaseModel, ConfigDict
from .errors import DomainError
from .service import now
from .parsers import default_parsers
from .parsers.contracts import Anchor, Block, validate_batch


class EvidenceRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    source_anchor: Anchor
    quote: str | None = None


class ParsingService:
    def __init__(self, documents, parsers=None, clock=time.time, lease_seconds=30, max_attempts=3):
        self.documents = documents
        self.repo, self.store = documents.repo, documents.store
        self.parsers = parsers or default_parsers()
        self.clock, self.lease_seconds, self.max_attempts = clock, lease_seconds, max_attempts

    @staticmethod
    def public_job(job):
        return {k:v for k,v in dict(job).items() if k not in ('claim_hash',)}

    def enqueue(self, principal, document_id, version_id, retry=False):
        self.documents.role(principal, 'manager')
        with self.repo.transaction() as db:
            self.documents.version(db, principal, document_id, version_id)
            job = db.parsing.enqueue(version_id, self.clock())
            if retry:
                if job['state'] != 'failed':
                    raise DomainError('job_not_failed')
                db.parsing.retry(job, self.clock())
                db.parsing.event(version_id, 'parse_retry', principal.subject, now())
                job = db.parsing.job(version_id)
            return self.public_job(job)

    def status(self, principal, document_id, version_id):
        with self.repo.transaction() as db:
            doc, _ = self.documents.version(db, principal, document_id, version_id)
            if principal.role != 'manager' and doc['active_version_id'] != version_id:
                raise DomainError('version_not_found', 404)
            job = db.parsing.job(version_id)
            if job is None:
                raise DomainError('parsing_job_not_found', 404)
            return self.public_job(job)

    def recover(self, principal):
        self.documents.role(principal, 'worker')
        with self.repo.transaction() as db:
            recovered = db.parsing.recover(principal.institution_id, self.clock(), self.max_attempts)
            for job in recovered:
                db.parsing.event(job['version_id'], 'parse_lease_expired', principal.subject, now())
            return len(recovered)

    def claim(self, principal):
        self.documents.role(principal, 'worker')
        self.recover(principal)
        token = secrets.token_urlsafe(32)
        with self.repo.transaction() as db:
            claim = db.parsing.claim(principal.institution_id, hashlib.sha256(token.encode()).hexdigest(),
                                     self.clock(), self.lease_seconds)
            if claim:
                db.parsing.event(claim['version_id'], 'parse_claim', principal.subject, now())
            # Hash acts as the internal fencing capability; never returned through HTTP or logged.
            return claim

    def renew(self, claim):
        with self.repo.transaction() as db:
            return db.parsing.renew(claim, self.clock(), self.lease_seconds)

    def publish(self, principal, claim, blocks):
        self.documents.role(principal, 'worker')
        with self.repo.transaction() as db:
            self.documents.version(db, principal, claim['document_id'], claim['version_id'])
            if not db.parsing.owned(claim, self.clock()):
                raise DomainError('stale_parse_claim')
        data = self.documents.read_original(principal,claim['version_id'], claim['sha256'])
        canonical = default_parsers()[claim['format']].parse(data, claim['document_id'], claim['version_id'])
        validate_batch(blocks, canonical, claim['document_id'], claim['version_id'])
        with self.repo.transaction() as db:
            self.documents.version(db, principal, claim['document_id'], claim['version_id'])
            if not db.parsing.owned(claim, self.clock()):
                raise DomainError('stale_parse_claim')
            db.parsing.publish(claim, blocks, self.parsers[claim['format']].method, self.clock())
            db.parsing.event(claim['version_id'], 'parse_completed', principal.subject, now())

    def execute(self, principal, claim):
        self.documents.role(principal, 'worker')
        try:
            with self.repo.transaction() as db:
                self.documents.version(db, principal, claim['document_id'], claim['version_id'])
                if not db.parsing.owned(claim, self.clock()):
                    raise DomainError('stale_parse_claim')
            data = self.documents.read_original(principal,claim['version_id'], claim['sha256'])
            blocks = self.parsers[claim['format']].parse(data, claim['document_id'], claim['version_id'])
            self.publish(principal, claim, blocks)
            return 'completed'
        except Exception as error:
            # Only fixed application error codes persist; never exception text or source bytes.
            code = error.code if isinstance(error, DomainError) else 'parse_internal_failure'
            with self.repo.transaction() as db:
                self.documents.version(db, principal, claim['document_id'], claim['version_id'], False)
                if not db.parsing.owned(claim, self.clock()):
                    return 'stale'
                db.parsing.fail(claim, code, self.clock())
                db.parsing.event(claim['version_id'], 'parse_failed', principal.subject, now())
            return 'failed'

    def blocks(self, principal, document_id, version_id):
        with self.repo.transaction() as db:
            doc, version = self.documents.version(db, principal, document_id, version_id)
            if principal.role != 'manager' and doc['active_version_id'] != version_id:
                raise DomainError('version_not_found', 404)
            job = db.parsing.job(version_id)
            if not job or job['state'] != 'completed':
                raise DomainError('parsing_not_ready')
            self.documents.read_original(principal,version_id, version['sha256'],db=db)
            return db.parsing.blocks(version_id)

    def resolve(self, principal, document_id, version_id, request):
        blocks = self.blocks(principal, document_id, version_id)
        anchor = request.source_anchor
        if anchor.document_id != document_id or anchor.version_id != version_id:
            raise DomainError('source_version_mismatch', 422)
        with self.repo.transaction() as db:
            _, version = self.documents.version(db, principal, document_id, version_id)
            if anchor.sha256 != version['sha256']:
                raise DomainError('source_hash_mismatch', 422)
            data = self.documents.read_original(principal,version_id, version['sha256'],db=db)
            canonical = default_parsers()[version['format']].parse(data, document_id, version_id)
            match = next((b for b in canonical if b.source_anchor == anchor), None)
            if match is None or not any(Block.model_validate(b) == match for b in blocks):
                raise DomainError('source_anchor_not_found', 422)
            if request.quote is not None and request.quote not in match.text:
                raise DomainError('quote_not_in_source', 422)
            return {'block': match.model_dump(mode='json'), 'structural_valid': True,
                    'semantic_accuracy': 'NOT_VERIFIED', 'visual_order': 'NOT_VERIFIED'}
