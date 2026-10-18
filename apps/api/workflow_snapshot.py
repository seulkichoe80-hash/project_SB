"""Read-only, serializable analysis inputs. No DB migration, model call or publication."""
from typing import Literal
from pydantic import Field, model_validator
from .chunking import Chunk, ChunkConfig, build_chunks, digest
from .parsers import default_parsers
from .parsers.contracts import Block, validate_batch
from .errors import DomainError
from .workflow_contracts import Identifier, StrictModel


class SnapshotSettings(StrictModel):
    settings_version: Identifier = 'workflow-input-settings-v1'
    prompt_contract_version: Identifier = 'workflow-extraction-prompt-v1'
    max_snapshot_bytes: int = Field(default=33554432, ge=1024, le=67108864)


class UnprocessedChunk(StrictModel):
    chunk_id: Identifier
    reason: Literal['not_processed'] = 'not_processed'


class InputCoverage(StrictModel):
    processed_chunk_ids: tuple[Identifier, ...]
    unprocessed: tuple[UnprocessedChunk, ...]
    status: Literal['incomplete', 'complete']


class SnapshotContent(StrictModel):
    schema_version: Literal['workflow-input-v1'] = 'workflow-input-v1'
    input_scope: Literal['selected_document_version_all_chunks'] = 'selected_document_version_all_chunks'
    institution_id: str = Field(min_length=1, max_length=200)
    document_id: Identifier
    version_id: Identifier
    original_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    selected_active_version_id: str | None
    version_revision: int = Field(ge=0)
    parse_job_id: Identifier
    parse_attempt: int = Field(ge=1)
    parse_attempt_id: str
    parser_method: str
    chunk_job_id: Identifier
    chunk_generation: int = Field(ge=1)
    chunk_config: ChunkConfig
    settings: SnapshotSettings
    input_chunk_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=20000)
    chunks: tuple[Chunk, ...] = Field(min_length=1, max_length=20000)
    source_blocks: tuple[Block, ...] = Field(min_length=1, max_length=20000)


class WorkflowInputSnapshot(SnapshotContent):
    snapshot_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    coverage: InputCoverage

    @model_validator(mode='after')
    def integrity(self):
        content = SnapshotContent.model_validate({k: getattr(self, k) for k in SnapshotContent.model_fields})
        if digest(content.model_dump(mode='json')) != self.snapshot_id:
            raise ValueError('snapshot_digest_mismatch')
        ids = self.input_chunk_ids
        if len(ids) != len(set(ids)) or ids != tuple(c.chunk_id for c in self.chunks):
            raise ValueError('snapshot_chunk_mismatch')
        processed = self.coverage.processed_chunk_ids
        pending = tuple(p.chunk_id for p in self.coverage.unprocessed)
        processed_set, pending_set = set(processed), set(pending)
        if len(processed) != len(processed_set) or len(pending) != len(pending_set):
            raise ValueError('duplicate_coverage_chunk')
        if processed_set & pending_set or processed_set | pending_set != set(ids):
            raise ValueError('incomplete_coverage_accounting')
        if processed != tuple(i for i in ids if i in processed_set) or pending != tuple(i for i in ids if i in pending_set):
            raise ValueError('invalid_coverage_order')
        if self.coverage.status != ('incomplete' if pending else 'complete'):
            raise ValueError('invalid_coverage_status')
        return self


class WorkflowInputService:
    def __init__(self, chunks):
        self.chunks = chunks
        self.documents = chunks.documents

    def _manager(self, principal):
        if principal is None:
            raise DomainError('authentication_required', 401)
        self.documents.role(principal, 'manager')

    def _read(self, principal, document_id, version_id, settings):
        with self.chunks.repo.transaction() as db:
            return self._read_in(db, principal, document_id, version_id, settings)

    def _read_in(self, db, principal, document_id, version_id, settings):
        """Same content read using an existing transaction (atomic workflow commit)."""
        doc, version, parsed, blocks = self.chunks.source(db, principal, document_id, version_id)
        attempt = db.connection.execute('SELECT state FROM parse_attempts WHERE job_id=? AND attempt=?',
                                        (parsed['id'], parsed['attempt'])).fetchone()
        if not attempt or attempt['state'] != 'completed':
            raise DomainError('parsing_attempt_not_ready')
        job = db.chunks.current(version_id)
        if (not job or job['state'] != 'completed' or job['parse_job_id'] != parsed['id']
                or job['parse_attempt'] != parsed['attempt']):
            raise DomainError('chunking_not_ready')
        items = db.chunks.items(job['id'])
        content = SnapshotContent(
            institution_id=principal.institution_id, document_id=document_id, version_id=version_id,
            original_sha256=version['sha256'], selected_active_version_id=doc['active_version_id'],
            version_revision=version['revision'], parse_job_id=parsed['id'], parse_attempt=parsed['attempt'],
            parse_attempt_id=f"{parsed['id']}:{parsed['attempt']}", parser_method=parsed['parser_method'],
            chunk_job_id=job['id'], chunk_generation=job['generation'],
            chunk_config=ChunkConfig.model_validate_json(job['config']), settings=settings,
            input_chunk_ids=tuple(c['chunk_id'] for c in items),
            chunks=tuple(Chunk.model_validate(c) for c in items),
            source_blocks=tuple(Block.model_validate(b) for b in blocks))
        return content

    def capture(self, principal, document_id, version_id, settings=None):
        self._manager(principal)
        settings = SnapshotSettings.model_validate((settings or SnapshotSettings()).model_dump())
        content = self._read(principal, document_id, version_id, settings)
        payload = content.model_dump(mode='json')
        from .chunking import canonical
        if len(canonical(payload).encode('utf-8')) > settings.max_snapshot_bytes:
            raise DomainError('workflow_snapshot_size_limit', 413)
        data = self.documents.store.read(version_id, content.original_sha256)
        # Reparse once per capture, then rebuild ALL canonical chunks. This detects
        # missing/duplicate/modified stored chunks rather than trusting their own count.
        kind = content.source_blocks[0].source_anchor.kind
        normal = default_parsers()[kind].parse(data, document_id, version_id)
        validate_batch(list(content.source_blocks), normal, document_id, version_id)
        rebuilt = build_chunks(list(content.source_blocks), principal.institution_id, content.chunk_config)
        # Grid metadata contains JSON arrays; compare canonical JSON rather than
        # Python tuple/list representations introduced by serialization.
        if [c.model_dump(mode='json') for c in rebuilt] != [c.model_dump(mode='json') for c in content.chunks]:
            raise DomainError('workflow_chunk_integrity', 422)
        if self._read(principal, document_id, version_id, settings) != content:
            raise DomainError('workflow_source_changed')
        return WorkflowInputSnapshot(**{k: getattr(content, k) for k in SnapshotContent.model_fields},
            snapshot_id=digest(payload), coverage=self._coverage(content.input_chunk_ids, ()))

    @staticmethod
    def _coverage(ids, processed):
        seen = set(processed)
        pending = tuple(UnprocessedChunk(chunk_id=i) for i in ids if i not in seen)
        return InputCoverage(processed_chunk_ids=tuple(i for i in ids if i in seen), unprocessed=pending,
                             status='incomplete' if pending else 'complete')

    def validate(self, principal, snapshot, *, require_active=False):
        self._manager(principal)
        snapshot = WorkflowInputSnapshot.model_validate_json(snapshot.model_dump_json())
        if principal.institution_id != snapshot.institution_id:
            raise DomainError('workflow_snapshot_not_found', 404)
        current = self.capture(principal, snapshot.document_id, snapshot.version_id, snapshot.settings)
        if current.snapshot_id != snapshot.snapshot_id:
            raise DomainError('stale_workflow_snapshot')
        if require_active and current.selected_active_version_id != current.version_id:
            raise DomainError('inactive_workflow_snapshot')
        return snapshot

    def iter_chunks(self, principal, snapshot, *, batch_size=32):
        if isinstance(batch_size, bool) or not isinstance(batch_size, int) or not 1 <= batch_size <= 200:
            raise DomainError('invalid_workflow_batch_size', 400)
        snapshot = self.validate(principal, snapshot)
        for index in range(0, len(snapshot.chunks), batch_size):
            self.validate(principal, snapshot)
            yield from snapshot.chunks[index:index + batch_size]
        self.validate(principal, snapshot)  # Consumers must finish iteration or explicitly revalidate.

    def mark_processed(self, principal, snapshot, chunk_ids):
        snapshot = self.validate(principal, snapshot)
        ids = list(chunk_ids)
        old = set(snapshot.coverage.processed_chunk_ids)
        if len(ids) != len(set(ids)) or old & set(ids) or not set(ids) <= set(snapshot.input_chunk_ids):
            raise DomainError('invalid_workflow_progress', 422)
        values = {k: getattr(snapshot, k) for k in WorkflowInputSnapshot.model_fields}
        values['coverage'] = self._coverage(snapshot.input_chunk_ids, old | set(ids))
        return WorkflowInputSnapshot(**values)
