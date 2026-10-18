"""Offline extraction receipts and server-only candidate envelope; never approval."""
from typing import Literal, Protocol
from pydantic import Field
from .chunking import EvidenceRef
from .workflow_contracts import (StrictModel, Identifier, GroundedAssertion, WorkflowExtraction,
                                 WorkflowExtractionAdapter, WorkflowValidation)
from .workflow_snapshot import WorkflowInputSnapshot


class DiscoverySettings(StrictModel):
    contract_version: Literal['workflow-discovery-v1'] = 'workflow-discovery-v1'
    max_chunks: int = Field(default=20000, ge=1, le=20000)
    batch_size: int = Field(default=32, ge=1, le=200)


class StepRoleCandidate(StrictModel):
    step_id: Identifier
    role: GroundedAssertion


class ChunkOmission(StrictModel):
    chunk_id: Identifier
    reason: Literal['scope_limit', 'partial_block', 'unsupported_content', 'adapter_omitted']


class OfflineExtractionReceipt(StrictModel):
    extraction: WorkflowExtraction
    processed_chunk_ids: tuple[Identifier, ...] = Field(max_length=20000)
    omissions: tuple[ChunkOmission, ...] = Field(max_length=20000)
    roles: tuple[StepRoleCandidate, ...] = Field(max_length=1000)


class OfflineWorkflowExtractionAdapter(WorkflowExtractionAdapter, Protocol):
    network_access: Literal[False]
    rule_version: str
    def extract_with_coverage(self, snapshot: WorkflowInputSnapshot,
                              chunk_ids: tuple[str, ...]) -> OfflineExtractionReceipt: ...


class DiscoveryScope(StrictModel):
    input_chunk_ids: tuple[Identifier, ...]
    traversed_chunk_ids: tuple[Identifier, ...]
    requested_chunk_ids: tuple[Identifier, ...]
    processed_chunk_ids: tuple[Identifier, ...]
    omissions: tuple[ChunkOmission, ...]
    status: Literal['complete', 'incomplete']


class WorkflowDiscoveryResult(StrictModel):
    contract_version: Literal['workflow-discovery-v1'] = 'workflow-discovery-v1'
    input_snapshot_id: str
    institution_id: str
    document_id: Identifier
    version_id: Identifier
    parse_attempt_id: str
    chunk_job_id: Identifier
    chunk_generation: int
    model_id: str
    rule_version: str
    input_settings_version: str
    prompt_contract_version: str
    settings: DiscoverySettings
    test_only: Literal[True] = True
    candidate_state: Literal['DRAFT', 'NEEDS_REVIEW']
    extraction: WorkflowExtraction
    roles: tuple[StepRoleCandidate, ...]
    evidence_refs: tuple[EvidenceRef, ...] = Field(max_length=20000)
    scope: DiscoveryScope
    validation: WorkflowValidation
