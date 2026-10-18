"""Local manager-only orchestration of offline candidate extraction. No serving/publication API."""
from .errors import DomainError
from .workflow_contracts import assertions, parse_extraction
from .workflow_evidence import resolve_citation, validate_extraction
from .workflow_snapshot import WorkflowInputSnapshot, InputCoverage, UnprocessedChunk
from .workflow_discovery_models import (DiscoverySettings, ChunkOmission, OfflineExtractionReceipt,
                                        DiscoveryScope, WorkflowDiscoveryResult,
                                        OfflineWorkflowExtractionAdapter)


class WorkflowDiscoveryEngine:
    def __init__(self, inputs, adapter: OfflineWorkflowExtractionAdapter):
        if (getattr(adapter, 'test_only', None) is not True
                or getattr(adapter, 'network_access', None) is not False):
            raise DomainError('real_workflow_provider_not_enabled', 503)
        for key in ['model_id', 'rule_version']:
            value = getattr(adapter, key, None)
            if not isinstance(value, str) or not 1 <= len(value) <= 128:
                raise DomainError('invalid_offline_adapter', 422)
        self.inputs, self.adapter = inputs, adapter

    def run(self, principal, snapshot, settings=None):
        settings = DiscoverySettings.model_validate((settings or DiscoverySettings()).model_dump())
        snapshot = self.inputs.validate(principal, snapshot)
        metadata = (self.adapter.model_id, self.adapter.rule_version)
        if self.adapter.test_only is not True or self.adapter.network_access is not False:
            raise DomainError('real_workflow_provider_not_enabled', 503)
        # Each run records its own analysis scope; previous bookkeeping is not
        # treated as proof that this adapter processed any input.
        values = {k: getattr(snapshot, k) for k in WorkflowInputSnapshot.model_fields}
        values['coverage'] = InputCoverage(processed_chunk_ids=(),
            unprocessed=tuple(UnprocessedChunk(chunk_id=i) for i in snapshot.input_chunk_ids), status='incomplete')
        run_input = WorkflowInputSnapshot(**values)
        traversed = tuple(c.chunk_id for c in self.inputs.iter_chunks(
            principal, run_input, batch_size=settings.batch_size))
        if traversed != snapshot.input_chunk_ids:
            raise DomainError('workflow_input_traversal_incomplete', 422)
        requested = traversed[:settings.max_chunks]
        # Clone the input: a test adapter cannot mutate the engine's validation context.
        adapter_input = WorkflowInputSnapshot.model_validate_json(run_input.model_dump_json())
        try:
            receipt = self.adapter.extract_with_coverage(adapter_input, requested)
        except Exception:
            raise DomainError('offline_workflow_adapter_failed', 503) from None
        if ((self.adapter.model_id, self.adapter.rule_version) != metadata
                or self.adapter.test_only is not True or self.adapter.network_access is not False):
            raise DomainError('workflow_adapter_configuration_changed', 422)
        if not isinstance(receipt, OfflineExtractionReceipt):
            raise DomainError('invalid_offline_workflow_output', 422)
        try:
            receipt = OfflineExtractionReceipt.model_validate_json(receipt.model_dump_json())
            output = parse_extraction(receipt.extraction)
        except (ValueError, TypeError, AttributeError):
            raise DomainError('invalid_offline_workflow_output', 422) from None
        if adapter_input.model_dump_json() != run_input.model_dump_json():
            raise DomainError('workflow_adapter_mutated_input', 422)
        processed = receipt.processed_chunk_ids
        omitted_ids = [x.chunk_id for x in receipt.omissions]
        if (len(processed) != len(set(processed)) or len(omitted_ids) != len(set(omitted_ids))
                or set(processed) & set(omitted_ids)
                or not (set(processed) | set(omitted_ids)) <= set(requested)):
            raise DomainError('invalid_workflow_adapter_coverage', 422)
        # Validate against BOTH the live snapshot and the adapter's admitted scope.
        allowed = set(processed)
        for chunk in run_input.chunks:
            if chunk.chunk_id in allowed:
                primary = [s for s in chunk.evidence.spans if s.role == 'primary']
                if not primary or not all(s.source_kind == 'original_text' and s.quote.strip() for s in primary):
                    raise DomainError('unsupported_workflow_chunk_claimed_processed', 422)
        for workflow in output.workflows:
            for assertion in assertions(workflow):
                if any(e.chunk_id not in allowed for e in assertion.evidence):
                    raise DomainError('workflow_citation_outside_processed_scope', 422)
        output, validation = validate_extraction(self.inputs, principal, run_input, output)
        step_ids = {s.id for w in output.workflows for s in w.steps}
        role_keys = set()
        for role in receipt.roles:
            key = (role.step_id, role.role.model_dump_json())
            if role.step_id not in step_ids or key in role_keys:
                raise DomainError('invalid_workflow_role_candidate', 422)
            role_keys.add(key)
            for citation in role.role.evidence:
                if citation.chunk_id not in allowed:
                    raise DomainError('workflow_role_outside_processed_scope', 422)
                resolve_citation(run_input, citation)
            if not any(role.role.text in c.quote for c in role.role.evidence):
                raise DomainError('unsupported_workflow_role', 422)
        progressed = self.inputs.mark_processed(principal, run_input, processed)
        reasons = {x.chunk_id: x.reason for x in receipt.omissions}
        omissions = tuple(ChunkOmission(chunk_id=p.chunk_id,
            reason='scope_limit' if p.chunk_id not in requested else reasons.get(p.chunk_id, 'adapter_omitted'))
            for p in progressed.coverage.unprocessed)
        # Engine-owned partial marker: an adapter cannot hide omissions by omitting issues.
        if omissions:
            payload = output.model_dump()
            existing = {i.id for i in output.issues}
            existing.update(n.id for w in output.workflows for n in
                            [w, *w.steps, *w.conditions, *w.edges, *w.form_requirements])
            issue_id = 'engine_partial_input'
            while issue_id in existing:
                issue_id += '_'
            payload['issues'].append({'id': issue_id, 'target_ids': [], 'code': 'partial_input',
                'message': '분석하지 못한 청크가 있습니다. 전체 문서 추출 완료가 아닙니다.'})
            output = parse_extraction(payload)
        self.inputs.validate(principal, progressed)
        used_chunks = {citation.chunk_id for w in output.workflows for assertion in assertions(w)
                       for citation in assertion.evidence}
        used_chunks.update(c.chunk_id for role in receipt.roles for c in role.role.evidence)
        result = WorkflowDiscoveryResult(input_snapshot_id=snapshot.snapshot_id,
            institution_id=snapshot.institution_id, document_id=snapshot.document_id, version_id=snapshot.version_id,
            parse_attempt_id=snapshot.parse_attempt_id, chunk_job_id=snapshot.chunk_job_id,
            chunk_generation=snapshot.chunk_generation, model_id=self.adapter.model_id,
            rule_version=self.adapter.rule_version, input_settings_version=snapshot.settings.settings_version,
            prompt_contract_version=snapshot.settings.prompt_contract_version, settings=settings,
            candidate_state='NEEDS_REVIEW' if output.issues or omissions else 'DRAFT', extraction=output,
            roles=receipt.roles, evidence_refs=tuple(c.evidence for c in run_input.chunks if c.chunk_id in used_chunks),
            scope=DiscoveryScope(input_chunk_ids=snapshot.input_chunk_ids,
                traversed_chunk_ids=traversed, requested_chunk_ids=requested,
                processed_chunk_ids=progressed.coverage.processed_chunk_ids, omissions=omissions,
                status=progressed.coverage.status), validation=validation)
        if len(result.model_dump_json().encode('utf-8')) > 8388608:
            raise DomainError('workflow_discovery_result_limit', 413)
        return result
