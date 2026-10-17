"""Manager-only job API contracts; claim capabilities and raw snapshots stay internal."""
from typing import Literal
from pydantic import Field
from .workflow_contracts import StrictModel, Identifier
from .workflow_snapshot import SnapshotSettings
from .workflow_discovery_models import DiscoverySettings, WorkflowDiscoveryResult
from .workflow_forms_models import WorkflowFormsReport


class WorkflowJobRequest(StrictModel):
    settings: DiscoverySettings = Field(default_factory=DiscoverySettings)
    snapshot_settings: SnapshotSettings = Field(default_factory=SnapshotSettings)


class WorkflowStoredResult(StrictModel):
    schema_version: Literal['workflow-job-result-v1'] = 'workflow-job-result-v1'
    discovery: WorkflowDiscoveryResult
    forms: WorkflowFormsReport


class WorkflowJobEvent(StrictModel):
    state: Literal['queued','processing','completed','failed','cancelled']
    attempt: int
    error_code: str | None
    error_category: Literal['RETRYABLE','PERMANENT','STALE_INPUT'] | None
    created_at: float


class WorkflowJobStatus(StrictModel):
    id: Identifier
    document_id: Identifier
    version_id: Identifier
    input_snapshot_id: str
    generation: int
    state: Literal['queued','processing','completed','failed','cancelled']
    attempt: int
    max_attempts: Literal[3] = 3
    events: list[WorkflowJobEvent] = Field(default_factory=list,max_length=100)
    lease_until: float | None
    error_code: str | None
    error_category: Literal['RETRYABLE','PERMANENT','STALE_INPUT'] | None
    semantic_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'
    administrator_approval: Literal['NOT_REQUESTED'] = 'NOT_REQUESTED'
    publishable: Literal[False] = False


from .workflow_contracts import WorkflowCandidate
from .workflow_review import WorkflowReviewIssue
from .workflow_forms_models import WorkflowFormRelation,FormRelationIssue
from .chunking import EvidenceRef


class WorkflowQueryEnvelope(StrictModel):
    schema_version: Literal['workflow-query-v1'] = 'workflow-query-v1'
    generation_id: Identifier
    job_id: Identifier
    semantic_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'
    administrator_approval: Literal['NOT_REQUESTED'] = 'NOT_REQUESTED'
    publishable: Literal[False] = False


class WorkflowCandidateResponse(WorkflowQueryEnvelope):
    candidates: list[WorkflowCandidate] = Field(max_length=20)


class WorkflowIssueResponse(WorkflowQueryEnvelope):
    issues: list[WorkflowReviewIssue|FormRelationIssue] = Field(max_length=25000)


class WorkflowFormResponse(WorkflowQueryEnvelope):
    form_links: list[WorkflowFormRelation] = Field(max_length=1000)


class WorkflowEvidenceResponse(WorkflowQueryEnvelope):
    evidence_refs: list[EvidenceRef] = Field(max_length=20000)
