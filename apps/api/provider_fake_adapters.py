"""Evaluation-only implementations of the existing protocols, all backed by FakeTransport.
They do not enable the production factory or change any offline/approval contract.
"""
import hashlib
import json
from functools import wraps
from pydantic import Field
from .chunking import Chunk, EvidenceRef
from .errors import DomainError
from .rag_adapters import Generation, EmbeddingSpec, checked_vectors
from .workflow_contracts import parse_extraction, WorkflowExtraction, assertions
from .workflow_evidence import validate_extraction
from .workflow_snapshot import WorkflowInputSnapshot
from .workflow_discovery_models import OfflineExtractionReceipt
from .provider_safety import SafetyModel, approved_simulation_input, encoded


def guarded_input(method):
    @wraps(method)
    def call(*args, **kwargs):
        try:return method(*args, **kwargs)
        except DomainError:raise
        except Exception:raise DomainError('invalid_provider_adapter_input',422) from None
    return call


class SimulationDocumentPermission(SafetyModel):
    institution_id: str
    document_id: str
    version_id: str
    original_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    classification: str = Field(pattern=r'^(synthetic|public)$')


def check_permission(principal, permission, meta):
    if type(permission) is not SimulationDocumentPermission or (
        permission.institution_id,permission.document_id,permission.version_id,permission.original_sha256
    ) != (principal.institution_id,meta['document_id'],meta['id'],meta['sha256']):
        raise DomainError('provider_document_permission_denied',403)
    try:SimulationDocumentPermission.model_validate(permission.model_dump(warnings=False))
    except Exception:raise DomainError('provider_document_permission_denied',403) from None
    if not meta['active'] or not meta['registered']:
        raise DomainError('provider_document_not_current',409)


class FakeWorkflowExtractionAdapter:
    test_only=True
    network_access=False
    rule_version='provider-safety-fake-v1'

    def __init__(self, inputs, gateway, principal, job, request_id, permission):
        self.inputs,self.gateway,self.principal=inputs,gateway,principal
        self.job,self.request_id,self.permission=job,request_id,permission
        self.model_id=gateway.settings.model

    @guarded_input
    def extract(self, snapshot):
        return self.extract_with_coverage(snapshot,snapshot.input_chunk_ids).extraction

    @guarded_input
    def extract_with_coverage(self, snapshot, chunk_ids):
        snapshot=self.inputs.validate(self.principal,WorkflowInputSnapshot.model_validate_json(snapshot.model_dump_json(warnings=False)),require_active=True)
        meta=self.inputs.documents.get(self.principal,snapshot.document_id,snapshot.version_id)
        check_permission(self.principal,self.permission,meta)
        requested=tuple(chunk_ids)
        if len(requested)!=len(set(requested)) or not requested or not set(requested)<=set(snapshot.input_chunk_ids):
            raise DomainError('provider_invalid_chunk_scope',422)
        sources=[]
        for chunk in snapshot.chunks:
            if chunk.chunk_id not in requested:continue
            spans=[s.model_dump(mode='json') for s in chunk.evidence.spans if s.source_kind=='original_text' and s.role=='primary']
            if not spans:raise DomainError('provider_unsupported_source',422)
            sources.append({'chunk_id':chunk.chunk_id,'spans':spans})
        payload={'task':'extract_verbatim_candidates_only','prompt_contract_version':snapshot.settings.prompt_contract_version,
                 'untrusted_sources':sources,'schema':WorkflowExtraction.model_json_schema()}
        approval=approved_simulation_input(self.principal,payload,classification=self.permission.classification,
                                          manifest_version='snapshot-'+snapshot.snapshot_id)
        def validate(value):
            output=parse_extraction(value)
            if any(c.chunk_id not in requested for w in output.workflows for a in assertions(w) for c in a.evidence):
                raise DomainError('provider_citation_outside_scope',422)
            output,_=validate_extraction(self.inputs,self.principal,snapshot,output)
            return output
        output,_=self.gateway.invoke(self.principal,self.job,self.request_id,'workflow',payload,approval,validate)
        return OfflineExtractionReceipt(extraction=output,processed_chunk_ids=requested,omissions=(),roles=())


class FakeLLMAdapter:
    test_only=True

    def __init__(self, chunks, gateway, principal, job, request_id, permissions):
        self.chunks,self.gateway,self.principal=chunks,gateway,principal
        self.job,self.request_id=job,request_id
        self.permissions=tuple(permissions)
        self.model_id=gateway.settings.model

    def _current(self, item):
        chunk=Chunk.model_validate_json(encoded(item))
        ref=chunk.evidence
        if ref.organization_id!=self.principal.institution_id:
            raise DomainError('provider_foreign_evidence',403)
        meta=self.chunks.documents.get(self.principal,ref.document_id,ref.version_id)
        permission=next((p for p in self.permissions if p.document_id==ref.document_id and p.version_id==ref.version_id),None)
        check_permission(self.principal,permission,meta)
        canonical=self.chunks.list(self.principal,ref.document_id,ref.version_id)
        if item not in canonical:raise DomainError('provider_noncanonical_context',422)
        self.chunks.resolve(self.principal,ref.document_id,ref.version_id,ref.chunk_id,EvidenceRef.model_validate(ref))
        return item

    @guarded_input
    def generate(self, question, context):
        if not isinstance(question,str) or not question.strip() or len(question)>4000:
            raise DomainError('invalid_provider_question',422)
        context=json.loads(encoded(context))
        if not context:return Generation(status='insufficient_evidence')
        allowed={c['chunk_id']:self._current(c) for c in context}
        if len(allowed)!=len(context):raise DomainError('provider_duplicate_context',422)
        payload={'task':'verbatim_rag_candidates_only','question':question,'untrusted_context':context,
                 'schema':Generation.model_json_schema()}
        approval=approved_simulation_input(self.principal,payload,classification='public' if any(p.classification=='public' for p in self.permissions) else 'synthetic')
        def validate(value):
            result=Generation.model_validate(value,strict=True)
            if (result.status=='candidate')!=bool(result.claims):raise ValueError('status_mismatch')
            for claim in result.claims:
                if len(claim.chunk_ids)!=len(set(claim.chunk_ids)) or any(k not in allowed for k in claim.chunk_ids):
                    raise ValueError('unknown_citation')
                for key in claim.chunk_ids:self._current(allowed[key])
                if not any(claim.text in span['quote'] for key in claim.chunk_ids for span in allowed[key]['evidence']['spans'] if span['source_kind']=='original_text'):
                    raise ValueError('unsupported_claim')
            # Freshness is checked even on an insufficient-evidence response.
            for item in context:self._current(item)
            return result
        result,_=self.gateway.invoke(self.principal,self.job,self.request_id,'rag',payload,approval,validate)
        return result


class SimulationEmbeddingPermission(SafetyModel):
    institution_id: str
    text_hashes: tuple[str,...] = Field(min_length=1,max_length=20000)
    classification: str = Field(pattern=r'^(synthetic|public)$')


class FakeEmbeddingAdapter:
    test_only=True

    def __init__(self, gateway, principal, job, request_id, permission, dimension=64):
        self.gateway,self.principal,self.job,self.request_id=gateway,principal,job,request_id
        if type(permission) is not SimulationEmbeddingPermission or permission.institution_id!=principal.institution_id:
            raise DomainError('provider_embedding_scope_denied',403)
        try:permission=SimulationEmbeddingPermission.model_validate(permission.model_dump(warnings=False))
        except Exception:raise DomainError('provider_embedding_scope_denied',403) from None
        self.permission=permission
        self.spec=EmbeddingSpec(provider='fake-'+gateway.settings.provider,model=gateway.settings.model,dimension=dimension,test_only=True)

    @guarded_input
    def embed(self, texts):
        if type(texts) is not list or not 1<=len(texts)<=200 or any(type(t) is not str or not t.strip() for t in texts):
            raise DomainError('invalid_provider_embedding_input',422)
        if any(hashlib.sha256(t.encode()).hexdigest() not in self.permission.text_hashes for t in texts):
            raise DomainError('provider_embedding_manifest_mismatch',403)
        payload={'task':'embedding','texts':texts,'dimension':self.spec.dimension}
        approval=approved_simulation_input(self.principal,payload,classification=self.permission.classification)
        def validate(value):
            if type(value) is not list or any(type(v) is not list for v in value):raise ValueError('invalid_vectors')
            return checked_vectors(value,len(texts),self.spec.dimension)
        result,_=self.gateway.invoke(self.principal,self.job,self.request_id,'embedding',payload,approval,validate)
        return result
