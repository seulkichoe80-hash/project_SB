"""Offline, server-owned mechanical diagnostics over current original evidence.

Authorization/source freshness failures raise the existing DomainError without
returning candidate content. Untrusted graph defects become review issues while
preserving the graph for review. Existing extraction/RAG contracts are unchanged.
"""
import json
import re
from typing import Literal
from pydantic import Field, ValidationError
from .errors import DomainError
from .workflow_contracts import (StrictModel, WorkflowCandidate, ReviewIssue,
    MAX_OUTPUT_BYTES, MAX_NODES)
from .workflow_discovery_models import WorkflowDiscoveryResult
from .workflow_evidence import resolve_citation
from .workflow_graph import graph_review
from .workflow_review import WorkflowReviewIssue, WorkflowReviewReport


class DiagnosticInput(StrictModel):
    # Deliberately no graph cross-reference validator: malformed references must
    # be diagnosable without relaxing the production extraction contract.
    schema_version: Literal['workflow-extraction-v1']
    workflows: list[WorkflowCandidate] = Field(max_length=20)
    issues: list[ReviewIssue] = Field(max_length=200)


DEADLINE = re.compile(r'\d+\s*(?:일|시간|개월|년|days?|hours?)', re.I)
AMOUNT = re.compile(r'(?:\d[\d,]*(?:\.\d+)?\s*(?:원|만원|억원|달러|USD)|\$\s*\d[\d,.]*)', re.I)
OBLIGATION = re.compile(r'반드시|하여야|해야|\bmust\b|\bshall\b', re.I)
NEGATION = re.compile(r'하지\s*않|아니|않아도|금지|면제|\bnot\b|\bexempt\b', re.I)
INJECTION = re.compile(r'ignore\s+(?:all\s+)?(?:previous|system)|system\s*prompt|지침.{0,12}무시|규칙.{0,12}변경|키.{0,8}출력', re.I)


def decode(payload):
    if hasattr(payload, 'model_dump_json'):
        payload = payload.model_dump_json()
    if isinstance(payload, dict):
        payload = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    if not isinstance(payload, (str, bytes)):
        raise ValueError('invalid_payload')
    if len(payload.encode('utf-8') if isinstance(payload, str) else payload) > MAX_OUTPUT_BYTES:
        raise OverflowError('output_limit')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate_json_key')
            result[key] = value
        return result
    return DiagnosticInput.model_validate(json.loads(payload, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite'))))


class WorkflowValidationEngine:
    def __init__(self, inputs):
        self.inputs = inputs

    def validate(self, principal, snapshot, payload, *, evidence_refs=None):
        # Strict active-version gate is independent of manager preview privileges.
        snapshot = self.inputs.validate(principal, snapshot, require_active=True)
        discovery = isinstance(payload, WorkflowDiscoveryResult)
        coverage = None
        if discovery:
            # Round-trip validates nested lists even if caller mutated a frozen DTO.
            payload = WorkflowDiscoveryResult.model_validate_json(payload.model_dump_json())
            if (payload.input_snapshot_id, payload.institution_id, payload.document_id,
                payload.version_id, payload.parse_attempt_id, payload.chunk_job_id, payload.chunk_generation) != (
                snapshot.snapshot_id, snapshot.institution_id, snapshot.document_id,
                snapshot.version_id, snapshot.parse_attempt_id, snapshot.chunk_job_id, snapshot.chunk_generation):
                raise DomainError('workflow_review_scope_mismatch', 422)
            evidence_refs, coverage, payload = payload.evidence_refs, payload.scope, payload.extraction
        issues, refs_by_target = [], {}
        def emit(code, targets, severity, reason, block, refs=None):
            canonical = {}
            for ref in (refs if refs is not None else [r for t in targets for r in refs_by_target.get(t, [])]):
                canonical[ref.model_dump_json()] = ref
            issues.append(WorkflowReviewIssue(target_ids=tuple(targets), code=code,
                severity=severity, reason=reason, auto_block=block,
                evidence_refs=tuple(canonical.values())))
        def report(status, fmt, evidence, graph, candidates=()):
            # Detect de-registration, active version/generation changes during review.
            self.inputs.validate(principal, snapshot, require_active=True)
            return WorkflowReviewReport(input_snapshot_id=snapshot.snapshot_id,
                institution_id=snapshot.institution_id, document_id=snapshot.document_id,
                version_id=snapshot.version_id, parse_attempt_id=snapshot.parse_attempt_id,
                chunk_job_id=snapshot.chunk_job_id, chunk_generation=snapshot.chunk_generation,
                status=status, format_validation=fmt,
                evidence_validation=evidence, graph_validation=graph,
                candidates=tuple(candidates), issues=tuple(issues))
        try:
            extraction = decode(payload)
        except (ValueError, TypeError, ValidationError, OverflowError, RecursionError):
            emit('INVALID_FORMAT', (), 'ERROR', '필수 필드·타입·관계 타입·JSON 형식 또는 출력 한도가 유효하지 않습니다.', True)
            return report('REJECTED', 'REJECTED', 'NOT_RUN', 'NOT_RUN')
        objects = []
        for w in extraction.workflows:
            objects.extend([w, *w.steps, *w.conditions, *w.edges, *w.form_requirements])
        objects.extend(extraction.issues)
        ids = [o.id for o in objects]
        if len(ids) > MAX_NODES:
            emit('OUTPUT_LIMIT', (), 'ERROR', '객체 수 한도를 초과했습니다.', True)
        if len(ids) != len(set(ids)):
            emit('DUPLICATE_ID', (), 'ERROR', '업무·단계·조건·관계·검토 ID가 중복되었습니다.', True)
        if not extraction.workflows and not extraction.issues:
            emit('INVALID_FORMAT', (), 'ERROR', '빈 결과에는 추출 검토 사유가 필요합니다.', True)
        if issues:
            return report('REJECTED', 'REJECTED', 'NOT_RUN', 'NOT_RUN')
        # Re-resolve canonical original references; do not echo foreign/forged refs.
        used_refs, resolved_chunks = {}, set()
        assertion_records = []
        try:
            for w in extraction.workflows:
                for obj in [w, *w.steps, *w.conditions, *w.edges, *w.form_requirements]:
                    own = ([w.title] if obj is w else
                           [obj.label, *obj.actions, *obj.obligations, *([obj.deadline] if obj.deadline else [])]
                           if obj in w.steps else [obj.statement] if obj in w.conditions else
                           [obj.explanation] if obj in w.edges else [obj.title, obj.requirement])
                    target_refs = []
                    for assertion in own:
                        for citation in assertion.evidence:
                            ref = resolve_citation(snapshot, citation)
                            if citation.chunk_id not in resolved_chunks:
                                self.inputs.chunks.resolve(principal, snapshot.document_id,
                                    snapshot.version_id, citation.chunk_id, ref)
                                resolved_chunks.add(citation.chunk_id)
                            target_refs.append(ref)
                            used_refs[ref.model_dump_json()] = ref
                        assertion_records.append((obj.id, assertion))
                    refs_by_target[obj.id] = target_refs
            if evidence_refs is not None:
                from .chunking import EvidenceRef
                supplied = [EvidenceRef.model_validate_json(r.model_dump_json()) if isinstance(r, EvidenceRef)
                            else EvidenceRef.model_validate(r) for r in evidence_refs]
                keys = [r.model_dump_json() for r in supplied]
                if len(keys) != len(set(keys)) or set(keys) != set(used_refs):
                    raise DomainError('workflow_evidence_catalog_mismatch', 422)
        except (DomainError, ValueError, ValidationError):
            emit('INVALID_EVIDENCE', (), 'ERROR', '근거 span·원문·범위 또는 정규 EvidenceRef 목록이 일치하지 않습니다.', True, refs=[])
            return report('REJECTED', 'PASS', 'REJECTED', 'NOT_RUN')
        for target, assertion in assertion_records:
            quotes = '\n'.join(c.quote for c in assertion.evidence)
            supported = any(assertion.text in c.quote for c in assertion.evidence)
            for pattern in (DEADLINE, AMOUNT):
                if not set(pattern.findall(assertion.text)) <= set(pattern.findall(quotes)):
                    supported = False
            if not supported:
                code = ('UNSUPPORTED_DEADLINE' if DEADLINE.search(assertion.text) else
                        'UNSUPPORTED_AMOUNT' if AMOUNT.search(assertion.text) else
                        'UNSUPPORTED_OBLIGATION' if OBLIGATION.search(assertion.text) else 'UNSUPPORTED_ASSERTION')
                emit(code, (target,), 'ERROR', '후보 주장을 인용 원문에서 그대로 확인할 수 없습니다. 의역의 의미도 자동 승인하지 않습니다.', True)
            contexts = '\n'.join(b.text for b in snapshot.source_blocks
                                 if b.block_id in {c.block_id for c in assertion.evidence})
            if NEGATION.search(contexts) and not NEGATION.search(assertion.text):
                emit('POSSIBLE_CONTEXT_MISMATCH', (target,), 'WARNING', '인용 주변의 부정·면제·금지 문맥이 생략됐을 수 있습니다.', True)
            if INJECTION.search(contexts):
                emit('DOCUMENT_INSTRUCTION', (target,), 'WARNING', '문서에 규칙 변경 지시로 보이는 문자열이 있습니다. 자료로만 취급합니다.', True)
        for w in extraction.workflows:
            graph_review(w, emit)
            for step in w.steps:
                texts = [a.text for a in [*step.actions, *step.obligations, *([step.deadline] if step.deadline else [])]]
                deadlines = {m.group(0) for t in texts for m in DEADLINE.finditer(t)}
                opposite = any(OBLIGATION.search(t) for t in texts) and any(NEGATION.search(t) for t in texts)
                if len(deadlines) > 1 or opposite:
                    emit('POSSIBLE_CONFLICT', (step.id,), 'WARNING', '같은 단계에 상이한 기한 또는 상반된 의무 문맥이 있습니다. 적용 조건·규정 우선순위는 사람이 검토해야 합니다.', True)
        for old in extraction.issues:
            if not set(old.target_ids) <= set(ids) or len(old.target_ids) != len(set(old.target_ids)):
                emit('INVALID_REFERENCE', (old.id,), 'ERROR', '추출 검토 이슈의 대상 참조가 유효하지 않습니다.', True)
            else:
                emit('EXTRACTION_REVIEW', tuple(old.target_ids),
                     'INFO' if old.code == 'semantic_review_required' else 'WARNING',
                     old.message, old.code != 'semantic_review_required')
        if coverage is not None:
            expected = snapshot.input_chunk_ids
            processed, traversed = coverage.processed_chunk_ids, coverage.traversed_chunk_ids
            if (tuple(coverage.input_chunk_ids) != expected
                    or len(coverage.requested_chunk_ids) != len(set(coverage.requested_chunk_ids))
                    or not set(coverage.requested_chunk_ids) <= set(expected)
                    or not set(coverage.processed_chunk_ids) <= set(coverage.requested_chunk_ids)
                    or coverage.status != 'complete' or coverage.omissions or tuple(traversed) != expected
                    or len(processed) != len(set(processed)) or set(processed) != set(expected)
                    or not resolved_chunks <= set(processed)):
                emit('PARTIAL_INPUT', (), 'WARNING', '입력 청크가 모두 처리·순회되지 않았거나 처리 범위가 모순됩니다.', True)
        elif snapshot.coverage.status != 'complete':
            emit('PARTIAL_INPUT', (), 'WARNING', '추출 처리 범위를 확인할 수 없습니다. 입력 스냅샷의 처리가 불완전합니다.', True)
        graph_codes = {'INVALID_REFERENCE','DUPLICATE_EDGE','ORPHAN_NODE','UNUSED_CONDITION', 'UNCLEAR_ORDER','UNSUPPORTED_CYCLE'}
        graph_status = 'NEEDS_REVIEW' if any(i.code in graph_codes for i in issues) else 'PASS'
        return report('NEEDS_REVIEW' if any(i.auto_block for i in issues) else 'PASS',
                      'PASS', 'PASS', graph_status, extraction.workflows)
