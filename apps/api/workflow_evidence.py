"""Explicit legacy/current evidence bridge and fail-closed structural output validation."""
from .chunking import EvidenceRef
from .errors import DomainError
from .workflow_contracts import (EvidenceCitation, StrictModel, Text,
                                 WorkflowValidation, assertions, parse_extraction)


class LegacyEvidence(StrictModel):
    tenant_id: str
    document_id: str
    version_id: str
    element_id: str
    quote: Text


class EvidenceBridge(StrictModel):
    legacy: LegacyEvidence
    citation: EvidenceCitation
    evidence_ref: EvidenceRef


def resolve_citation(snapshot, citation):
    chunk = next((c for c in snapshot.chunks if c.chunk_id == citation.chunk_id), None)
    block = next((b for b in snapshot.source_blocks if b.block_id == citation.block_id), None)
    if chunk is None or block is None or block.source_kind != 'original_text':
        raise DomainError('unknown_workflow_evidence', 422)
    if (citation.quote != block.text[citation.start:citation.end]
            or not any(s.block_id == block.block_id and s.source_kind == 'original_text'
                       and s.start <= citation.start < citation.end <= s.end for s in chunk.evidence.spans)):
        raise DomainError('workflow_quote_mismatch', 422)
    return chunk.evidence


class LegacyEvidenceAdapter:
    def __init__(self, inputs):
        self.inputs = inputs

    def to_current(self, principal, legacy, snapshot, *, chunk_id, block_id, start):
        snapshot = self.inputs.validate(principal, snapshot)
        legacy = LegacyEvidence.model_validate(legacy)
        if (legacy.tenant_id, legacy.document_id, legacy.version_id) != (
                snapshot.institution_id, snapshot.document_id, snapshot.version_id):
            raise DomainError('legacy_workflow_scope_mismatch', 422)
        # No implicit element_id->block_id guess. Caller supplies the exact mapping
        # and offset; the bridge retains every old field plus the full canonical ref.
        citation = EvidenceCitation(chunk_id=chunk_id, block_id=block_id, start=start,
                                    end=start + len(legacy.quote), quote=legacy.quote)
        return EvidenceBridge(legacy=legacy, citation=citation, evidence_ref=resolve_citation(snapshot, citation))

    def to_legacy(self, principal, bridge, snapshot):
        bridge = EvidenceBridge.model_validate_json(bridge.model_dump_json())
        expected = self.to_current(principal, bridge.legacy.model_dump(), snapshot,
            chunk_id=bridge.citation.chunk_id, block_id=bridge.citation.block_id, start=bridge.citation.start)
        if expected != bridge:
            raise DomainError('legacy_workflow_bridge_mismatch', 422)
        return bridge.legacy


def validate_extraction(inputs, principal, snapshot, payload):
    """No semantic approval. Only exact original wording is admitted in this stage."""
    snapshot = inputs.validate(principal, snapshot)
    output = parse_extraction(payload)
    for workflow in output.workflows:
        for assertion in assertions(workflow):
            for citation in assertion.evidence:
                resolve_citation(snapshot, citation)
            if not any(assertion.text in e.quote for e in assertion.evidence):
                raise DomainError('unsupported_workflow_assertion', 422)
    inputs.validate(principal, snapshot)
    return output, WorkflowValidation()
