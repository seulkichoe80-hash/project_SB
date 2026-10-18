"""Mechanical review results; never a semantic certificate or publication grant."""
from typing import Literal
from pydantic import Field
from .chunking import EvidenceRef
from .workflow_contracts import StrictModel, Identifier, Text, WorkflowCandidate

ReviewCode = Literal[
    'INVALID_FORMAT', 'OUTPUT_LIMIT', 'DUPLICATE_ID', 'INVALID_REFERENCE',
    'DUPLICATE_EDGE', 'ORPHAN_NODE', 'UNUSED_CONDITION', 'UNCLEAR_ORDER',
    'UNSUPPORTED_CYCLE', 'EVIDENCED_REPEAT', 'INVALID_EVIDENCE',
    'UNSUPPORTED_ASSERTION', 'UNSUPPORTED_DEADLINE', 'UNSUPPORTED_AMOUNT',
    'UNSUPPORTED_OBLIGATION', 'POSSIBLE_CONTEXT_MISMATCH', 'POSSIBLE_CONFLICT',
    'DOCUMENT_INSTRUCTION', 'PARTIAL_INPUT', 'EXTRACTION_REVIEW',
]


class WorkflowReviewIssue(StrictModel):
    target_ids: tuple[Identifier, ...] = Field(max_length=1000)
    code: ReviewCode
    severity: Literal['ERROR', 'WARNING', 'INFO']
    evidence_refs: tuple[EvidenceRef, ...] = Field(max_length=20000)
    reason: Text
    auto_block: bool


class WorkflowReviewReport(StrictModel):
    schema_version: Literal['workflow-review-v1'] = 'workflow-review-v1'
    input_snapshot_id: str
    institution_id: str
    document_id: Identifier
    version_id: Identifier
    parse_attempt_id: str
    chunk_job_id: Identifier
    chunk_generation: int
    status: Literal['PASS', 'NEEDS_REVIEW', 'REJECTED']
    format_validation: Literal['PASS', 'REJECTED']
    evidence_validation: Literal['PASS', 'REJECTED', 'NOT_RUN']
    graph_validation: Literal['PASS', 'NEEDS_REVIEW', 'NOT_RUN']
    candidates: tuple[WorkflowCandidate, ...] = Field(max_length=20)
    issues: tuple[WorkflowReviewIssue, ...] = Field(max_length=5000)
    semantic_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'
    semantic_review_required: Literal[True] = True
    administrator_approval: Literal['NOT_REQUESTED'] = 'NOT_REQUESTED'
    publishable: Literal[False] = False
