"""Form existence and procedural applicability are separate, unapproved facts."""
from typing import Literal
from pydantic import Field
from .chunking import EvidenceRef
from .workflow_contracts import StrictModel, Identifier, Text, GroundedAssertion
from .workflow_review import WorkflowReviewReport


class FormMetadata(StrictModel):
    title: Text
    purpose: Text


class RegisteredFormCandidate(StrictModel):
    institution_id: str
    document_id: Identifier
    version_id: Identifier
    original_sha256: str
    original_name: Text
    metadata: FormMetadata
    catalog_revision: int = Field(ge=1)
    matched_on: tuple[Literal['filename', 'title', 'purpose'], ...]
    match_kind: Literal['EXACT_NAME', 'PARTIAL_NAME']
    existence: Literal['CURRENT_REGISTERED_FILE'] = 'CURRENT_REGISTERED_FILE'
    relationship_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'


class FormRelationIssue(StrictModel):
    target_id: Identifier
    code: Literal['INVALID_STEP_BINDING', 'UNSUPPORTED_FORM_CLAIM', 'NO_REGISTERED_MATCH',
                  'AMBIGUOUS_FORM', 'LEXICAL_MATCH_ONLY', 'CONDITIONAL_MENTION',
                  'MENTION_NOT_OBLIGATION', 'SOURCE_REVIEW_REQUIRED', 'CANDIDATE_LIMIT']
    severity: Literal['ERROR', 'WARNING', 'INFO']
    evidence_refs: tuple[EvidenceRef, ...]
    reason: Text
    auto_block: bool


class WorkflowFormRelation(StrictModel):
    workflow_id: Identifier
    requirement_id: Identifier
    step_ids: tuple[Identifier, ...]
    form_name: GroundedAssertion
    purpose: GroundedAssertion
    condition_ids: tuple[Identifier, ...]
    evidence_refs: tuple[EvidenceRef, ...]
    mention_kind: Literal['MENTION_ONLY', 'CONDITIONAL_MENTION', 'EXPLICIT_OBLIGATION_MENTION']
    required: Literal[None] = None
    match_status: Literal['UNLINKED', 'CANDIDATES', 'AMBIGUOUS', 'BLOCKED']
    relationship_status: Literal['NEEDS_REVIEW', 'BLOCKED']
    candidates: tuple[RegisteredFormCandidate, ...] = Field(max_length=50)
    issues: tuple[FormRelationIssue, ...] = Field(max_length=20)
    selected_form_id: Literal[None] = None
    administrator_approval: Literal['NOT_REQUESTED'] = 'NOT_REQUESTED'


class WorkflowFormsReport(StrictModel):
    schema_version: Literal['workflow-forms-v1'] = 'workflow-forms-v1'
    input_snapshot_id: str
    institution_id: str
    document_id: Identifier
    version_id: Identifier
    source_review: WorkflowReviewReport
    relations: tuple[WorkflowFormRelation, ...] = Field(max_length=1000)
    semantic_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'
    administrator_approval: Literal['NOT_REQUESTED'] = 'NOT_REQUESTED'
    publishable: Literal[False] = False
