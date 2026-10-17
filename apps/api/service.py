import hashlib
import secrets
import uuid
import time
from datetime import datetime, timezone
from .errors import DomainError
from .formats import inspect_file
from .models import Principal
from .repository import Repository
from .storage import LocalOriginalStore


def now():
    return datetime.now(timezone.utc).isoformat()


class DocumentService:
    def __init__(self, repository: Repository, store: LocalOriginalStore, parsing_enabled=False):
        self.repo, self.store = repository, store
        self.parsing_enabled = parsing_enabled

    @staticmethod
    def role(principal: Principal, *roles):
        if principal.role not in roles:
            raise DomainError('forbidden', 403)

    def document(self, db, principal, document_id, require_registered=True):
        row = db.document(principal.institution_id, document_id)
        if row is None or (require_registered and not row['registered']):
            raise DomainError('document_not_found', 404)
        return row

    def version(self, db, principal, document_id, version_id, require_registered=True):
        doc = self.document(db, principal, document_id, require_registered)
        row = db.version(document_id, version_id)
        if row is None:
            raise DomainError('version_not_found', 404)
        return doc, row

    @staticmethod
    def metadata(doc, version):
        fields = {k: v for k, v in dict(version).items() if k != 'claim_hash'}
        return {**fields, 'institution_id': doc['institution_id'],
                'active': bool(doc['registered'] and doc['active_version_id'] == version['id']),
                'registered': bool(doc['registered'])}

    def register(self, principal, filename, mime, data, document_id=None):
        self.role(principal, 'manager')
        fmt, canonical_mime = inspect_file(filename, mime, data)
        digest = hashlib.sha256(data).hexdigest()
        intent = uuid.uuid4().hex
        with self.repo.transaction() as db:
            if document_id:
                self.document(db, principal, document_id)
            else:
                # Same tenant/content upload is idempotent across filenames.
                old = db.duplicate(principal.institution_id, digest)
                if old:
                    doc, version = self.version(db, principal, old['document_id'], old['id'])
                    self.store.read(version['id'], version['sha256'])
                    return self.metadata(doc, version), True
            db.start_intent(intent, principal.institution_id, now())
        try:
            # Intent is durable before filesystem writes. Files never become visible until DB commit.
            self.store.write(intent, data)
            self.store.read(intent, digest)
            with self.repo.transaction() as db:
                if document_id:
                    doc = self.document(db, principal, document_id)
                    old = db.duplicate(principal.institution_id, digest, document_id)
                else:
                    # Serialize final publication, including concurrent duplicate submissions.
                    old = db.duplicate(principal.institution_id, digest)
                if old:
                    doc = self.document(db, principal, old['document_id'])
                    self.store.read(old['id'], old['sha256'])
                    db.finish_intent(intent, 'retained_duplicate', old['id'])
                    return self.metadata(doc, old), True
                if not document_id:
                    document_id = uuid.uuid4().hex
                    db.create_document(document_id, principal.institution_id, now())
                db.insert_version(intent, document_id, filename, len(data), canonical_mime, fmt, digest, now(), principal.subject)
                if self.parsing_enabled:
                    db.parsing.enqueue(intent, time.time())
                db.finish_intent(intent, 'committed', intent)
                db.event(intent, 'registered', principal.subject, now())
                doc, version = self.version(db, principal, document_id, intent)
                return self.metadata(doc, version), False
        except Exception:
            # Preserve partial/orphan originals for reconciliation; never publish them or delete originals.
            with self.repo.transaction() as db:
                db.finish_intent(intent, 'failed')
            raise

    def list(self, principal, active_only=True):
        active_only = active_only or principal.role != 'manager'
        with self.repo.transaction() as db:
            docs = db.documents(principal.institution_id)
            result = []
            for doc in docs:
                rows = db.versions(doc['id'])
                result.extend(self.metadata(doc, v) for v in rows
                              if not active_only or doc['active_version_id'] == v['id'])
            return result

    def get(self, principal, document_id, version_id):
        with self.repo.transaction() as db:
            doc, row = self.version(db, principal, document_id, version_id, False)
            if principal.role != 'manager' and (not doc['registered'] or doc['active_version_id'] != row['id']):
                raise DomainError('version_not_found', 404)
            return self.metadata(doc, row)

    def original(self, principal, document_id, version_id):
        meta = self.get(principal, document_id, version_id)
        if principal.role != 'manager' and not meta['active']:
            raise DomainError('version_not_found', 404)
        return self.store.read(version_id, meta['sha256']), meta

    def transition(self, principal, document_id, version_id, target, revision, claim_token=None):
        self.role(principal, *(['manager', 'worker'] if target == 'queued' else ['worker']))
        with self.repo.transaction() as db:
            doc, row = self.version(db, principal, document_id, version_id)
            if db.parsing.job(version_id):
                raise DomainError('parsing_job_managed')
            allowed = {'registered': {'queued'}, 'queued': {'processing'},
                       'processing': {'completed', 'failed'}, 'failed': {'queued'}, 'completed': set()}
            if row['revision'] != revision or target not in allowed[row['state']]:
                raise DomainError('invalid_state_transition')
            token = None
            claim_hash = None
            if row['state'] == 'processing':
                supplied = hashlib.sha256((claim_token or '').encode()).hexdigest()
                if not secrets.compare_digest(supplied, row['claim_hash'] or ''):
                    raise DomainError('invalid_claim')
            if target == 'processing':
                token = secrets.token_urlsafe(32)
                claim_hash = hashlib.sha256(token.encode()).hexdigest()
            if target == 'completed':
                self.store.read(version_id, row['sha256'])
            db.transition(version_id, target, claim_hash)
            db.event(version_id, target, principal.subject, now())
            _, updated = self.version(db, principal, document_id, version_id)
            return {**self.metadata(doc, updated), 'claim_token': token}

    def activate(self, principal, document_id, version_id):
        self.role(principal, 'manager')
        with self.repo.transaction() as db:
            _, row = self.version(db, principal, document_id, version_id)
            job = db.parsing.job(version_id)
            if job and job['state'] != 'completed':
                raise DomainError('parsing_not_ready')
            if row['state'] != 'completed':
                raise DomainError('version_not_ready')
            self.store.read(version_id, row['sha256'])
            db.activate(document_id, version_id)
            db.event(version_id, 'activated', principal.subject, now())
            doc, row = self.version(db, principal, document_id, version_id)
            return self.metadata(doc, row)

    def deregister(self, principal, document_id):
        self.role(principal, 'manager')
        with self.repo.transaction() as db:
            doc = self.document(db, principal, document_id)
            db.deregister(document_id, principal.subject, now())
            db.parsing.cancel_document(document_id, time.time())
        return {'document_id': doc['id'], 'registered': False}

    def reconcile(self):
        """Local operator-only diagnostic. No HTTP endpoint and no automatic deletion/recovery publication."""
        with self.repo.transaction() as db:
            return db.unfinished_intents()
