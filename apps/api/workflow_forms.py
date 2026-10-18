"""Offline form mention review and tenant-scoped, never-final lexical candidates."""
import re
import unicodedata
from pathlib import PurePath
from .errors import DomainError
from .workflow_contracts import parse_extraction
from .workflow_discovery_models import WorkflowDiscoveryResult
from .workflow_evidence import resolve_citation
from .workflow_graph import CONDITIONAL
from .workflow_validation import WorkflowValidationEngine, OBLIGATION
from .workflow_forms_repository import FormCatalogRepository
from .workflow_forms_models import (FormMetadata, RegisteredFormCandidate, FormRelationIssue,
                                    WorkflowFormRelation, WorkflowFormsReport)


def normalized(value):
    return re.sub(r'[\W_]+', '', unicodedata.normalize('NFKC', value).casefold())


def overlaps(a, b):
    return any(x.block_id == y.block_id and x.chunk_id == y.chunk_id
               and max(x.start,y.start) < min(x.end,y.end)
               for x in a.evidence for y in b.evidence)


def named_in(name, text):
    # Avoid treating 신청서 as the mention of a different 취소신청서.
    pattern = r'(?<![가-힣A-Za-z0-9])' + re.escape(name) + r'(?=$|[^가-힣A-Za-z0-9]|(?:을|를|은|는|이|가|와|과|에|로|으로)(?:\s|[.,]))'
    return bool(re.search(pattern, text))


class WorkflowFormService:
    def __init__(self, inputs):
        self.inputs = inputs
        self.documents = inputs.chunks.documents
        self.catalog = FormCatalogRepository(self.documents.repo)
        self.validator = WorkflowValidationEngine(inputs)

    def register_form(self, principal, document_id, version_id, metadata):
        """Explicit manager classification only; no workflow approval or HTTP API."""
        self.inputs._manager(principal)
        metadata = FormMetadata.model_validate_json(metadata.model_dump_json()) if isinstance(metadata, FormMetadata) else FormMetadata.model_validate(metadata)
        with self.documents.repo.transaction() as db:
            doc, version = self.documents.version(db, principal, document_id, version_id)
            if doc['active_version_id'] != version_id or version['state'] != 'completed':
                raise DomainError('inactive_form_version', 409)
            self.documents.store.read(version_id, version['sha256'])
            self.catalog.upsert(db, principal.institution_id, document_id, version_id, metadata.title, metadata.purpose)

    def _current(self, principal):
        self.inputs._manager(principal)
        with self.documents.repo.transaction() as db:
            return self.catalog.current(db, principal.institution_id)

    def resolve_candidate(self, principal, candidate):
        """Recheck stored/displayed candidates before later use; no ID-only trust."""
        self.inputs._manager(principal)
        candidate = RegisteredFormCandidate.model_validate_json(candidate.model_dump_json())
        if candidate.institution_id != principal.institution_id:
            raise DomainError('form_candidate_not_found', 404)
        row = next((r for r in self._current(principal) if r['document_id']==candidate.document_id), None)
        if row is None or (row['version_id'], row['revision'], row['sha256'], row['original_name'], row['title'], row['purpose']) != (
            candidate.version_id, candidate.catalog_revision, candidate.original_sha256, candidate.original_name,
            candidate.metadata.title, candidate.metadata.purpose):
            raise DomainError('stale_form_candidate', 409)
        self.documents.store.read(candidate.version_id, candidate.original_sha256)
        if row not in self._current(principal):
            raise DomainError('stale_form_candidate', 409)
        return candidate

    def match(self, principal, snapshot, payload):
        # Revalidate immutable DTOs and source before any catalog metadata is read.
        review = self.validator.validate(principal, snapshot, payload)
        if review.format_validation != 'PASS' or review.evidence_validation != 'PASS':
            raise DomainError('invalid_workflow_form_source', 422)
        try:
            extraction = parse_extraction(payload.extraction if isinstance(payload, WorkflowDiscoveryResult) else payload)
        except (ValueError, TypeError):
            raise DomainError('invalid_workflow_form_graph', 422) from None
        rows, relations = self._current(principal), []
        for workflow in extraction.workflows:
            steps = {s.id:s for s in workflow.steps}
            for form in workflow.form_requirements:
                canonical = {}
                for claim in [form.title, form.requirement]:
                    for citation in claim.evidence:
                        ref = resolve_citation(snapshot, citation)
                        canonical[ref.model_dump_json()] = ref
                refs, issues = tuple(canonical.values()), []
                def issue(code, reason, severity='WARNING'):
                    issues.append(FormRelationIssue(target_id=form.id, code=code, severity=severity,
                        reason=reason, evidence_refs=refs, auto_block=True))
                supported = all(any(claim.text in c.quote for c in claim.evidence)
                                for claim in [form.title, form.requirement])
                bound = all(s in steps and any(named_in(form.title.text, a.text)
                            and overlaps(form.requirement,a) for a in [steps[s].label,*steps[s].actions])
                            for s in form.step_ids)
                if not supported:
                    issue('UNSUPPORTED_FORM_CLAIM', '서식명 또는 사용 목적을 인용 원문에서 확인할 수 없습니다.', 'ERROR')
                if not bound:
                    issue('INVALID_STEP_BINDING', '서식 언급 원문과 지정 단계의 행위·근거가 연결되지 않습니다.', 'ERROR')
                conditions = tuple(c.id for c in workflow.conditions if set(c.step_ids) & set(form.step_ids)
                                   and overlaps(form.requirement,c.statement)
                                   and CONDITIONAL.search(c.statement.text))
                mention = ('CONDITIONAL_MENTION' if conditions or CONDITIONAL.search(form.requirement.text) else
                           'EXPLICIT_OBLIGATION_MENTION' if OBLIGATION.search(form.requirement.text) else 'MENTION_ONLY')
                issue('CONDITIONAL_MENTION' if mention=='CONDITIONAL_MENTION' else 'MENTION_NOT_OBLIGATION',
                      '조건·적용 범위와 서식 필요성은 검토 대상입니다. 원문 언급만으로 필수 서식을 확정하지 않습니다.')
                if any(i.auto_block for i in review.issues):
                    issue('SOURCE_REVIEW_REQUIRED', '원본 후보 검토에 차단 이슈가 있습니다. 서식 관계도 승인할 수 없습니다.')
                matches = []
                if supported and bound:
                    key = normalized(form.title.text)
                    for row in rows:
                        values = {'filename':normalized(PurePath(row['original_name']).stem),
                                  'title':normalized(row['title']), 'purpose':normalized(row['purpose'])}
                        on = tuple(k for k,v in values.items() if key and key in v)
                        if not on:
                            continue
                        self.documents.store.read(row['version_id'], row['sha256'])
                        matches.append(RegisteredFormCandidate(institution_id=principal.institution_id,
                            document_id=row['document_id'], version_id=row['version_id'],
                            original_sha256=row['sha256'], original_name=row['original_name'],
                            metadata=FormMetadata(title=row['title'],purpose=row['purpose']),
                            catalog_revision=row['revision'], matched_on=on,
                            match_kind='EXACT_NAME' if any(values[k]==key for k in ('title','filename')) else 'PARTIAL_NAME'))
                if not supported or not bound:
                    status = 'BLOCKED'
                elif not matches:
                    status = 'UNLINKED'
                    issue('NO_REGISTERED_MATCH', '같은 기관의 현재 활성 등록 서식 중 일치 후보가 없습니다. 등록 파일과의 연결은 없습니다.')
                else:
                    status = 'AMBIGUOUS' if len(matches)>1 else 'CANDIDATES'
                    issue('AMBIGUOUS_FORM' if len(matches)>1 else 'LEXICAL_MATCH_ONLY',
                          '동명·유사 후보를 사람이 검토해야 합니다.' if len(matches)>1 else '파일 존재만 확인했습니다. 해당 업무에 사용해야 하는 관계는 미확정입니다.')
                if len(matches)>50:
                    issue('CANDIDATE_LIMIT','후보 한도50개를 초과했습니다. 일부 후보만 제시하며 최종 선택은 차단합니다.')
                matches.sort(key=lambda c:(c.match_kind!='EXACT_NAME',c.document_id))
                relations.append(WorkflowFormRelation(workflow_id=workflow.id,requirement_id=form.id,
                    step_ids=tuple(form.step_ids),form_name=form.title,purpose=form.requirement,
                    condition_ids=conditions,evidence_refs=refs,mention_kind=mention,
                    match_status=status,relationship_status='BLOCKED' if status=='BLOCKED' else 'NEEDS_REVIEW',
                    candidates=tuple(matches[:50]),issues=tuple(issues)))
        # Re-read the registry to catch removals, renamed metadata and new ambiguity
        # during matching; source active version/generation is checked independently.
        if rows != self._current(principal):
            raise DomainError('form_catalog_changed',409)
        self.inputs.validate(principal,snapshot,require_active=True)
        return WorkflowFormsReport(input_snapshot_id=snapshot.snapshot_id,institution_id=snapshot.institution_id,
            document_id=snapshot.document_id,version_id=snapshot.version_id,source_review=review,
            relations=tuple(relations))
