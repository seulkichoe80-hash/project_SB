"""Fresh synthetic files, deterministic mocks, real parsers/chunks/snapshot service."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hwpx import HwpxDocument
import test_parsing as fixtures
import test_chunking
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.workflow_contracts import parse_extraction
from apps.api.workflow_snapshot import WorkflowInputService
from apps.api.workflow_discovery import WorkflowDiscoveryEngine
from apps.api.workflow_discovery_models import DiscoverySettings
from apps.api.workflow_offline_adapter import DeterministicWorkflowAdapter


def synthetic_hwpx(lines):
    doc = HwpxDocument.new()
    for line in lines:
        doc.add_paragraph(line)
    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / 'new-synthetic.hwpx'
        doc.save_to_path(target)
        return target.read_bytes()


def synthetic_pdf(lines):
    """Project-authored ASCII PDF, built in memory with no font download."""
    def escape(text):
        return text.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')
    stream = '\n'.join(f'BT /F1 10 Tf 40 {760-i*18} Td ({escape(line)}) Tj ET'
                       for i, line in enumerate(lines)).encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 600 800] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    data, offsets = b'%PDF-1.4\n', []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(data));data += f'{n} 0 obj\n'.encode() + obj + b'\nendobj\n'
    start = len(data)
    data += f'xref\n0 {len(objects)+1}\n0000000000 65535 f \n'.encode()
    data += b''.join(f'{x:010d} 00000 n \n'.encode() for x in offsets)
    return data + f'trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n'.encode()


class TransformAdapter(DeterministicWorkflowAdapter):
    """Explicit deterministic test response injection, never a real provider."""
    def __init__(self, transform):
        self.transform = transform
    def extract_with_coverage(self, snapshot, chunk_ids):
        return self.transform(super().extract_with_coverage(snapshot, chunk_ids), snapshot, chunk_ids)


class WorkflowDiscoveryTests(unittest.TestCase):
    setUp = fixtures.ParsingIntegrationTests.setUp
    tearDown = fixtures.ParsingIntegrationTests.tearDown
    upload = fixtures.ParsingIntegrationTests.upload
    route = fixtures.ParsingIntegrationTests.route
    parse = fixtures.ParsingIntegrationTests.parse
    prepare = test_chunking.ChunkIntegrationTests.prepare

    def ready(self, lines=None, fmt='hwpx', config=None):
        lines = lines or ['업무명: 은빛 표본 접수', '1. 신청자는 은빛신청서를 제출한다.',
                          '2. 검토자는 자료를 검토한다.']
        data = synthetic_hwpx(lines) if fmt == 'hwpx' else synthetic_pdf(lines)
        meta, _, _ = self.prepare(data, 'fresh.'+fmt, config=config)
        self.inputs = WorkflowInputService(self.app.state.chunks)
        return meta, self.inputs.capture(self.principal, meta['document_id'], meta['id'])

    def run_engine(self, snapshot, adapter=None, settings=None):
        return WorkflowDiscoveryEngine(self.inputs, adapter or DeterministicWorkflowAdapter()).run(
            self.principal, snapshot, settings)

    def test_unseen_names_without_business_registry(self):
        for name in ['은하수 장비 반출', '모래시계 표본 교환', '솔빛 보존 신청']:
            _, snapshot = self.ready(['업무명: '+name, '1. 방문자는 자료를 제출한다.'])
            result = self.run_engine(snapshot)
            self.assertEqual(result.extraction.workflows[0].title.text, name)
            self.assertNotIn(name, Path('apps/api/workflow_offline_adapter.py').read_text())
            self.assertEqual(result.scope.status, 'complete')

    def test_fresh_pdf_parsing_and_candidate_evidence(self):
        _, snapshot = self.ready(['Workflow: Zircon sample exchange',
                                  '1. Applicant submits the Zircon form.',
                                  '2. Reviewer must review the file within 3 days.'], fmt='pdf')
        result = self.run_engine(snapshot);workflow = result.extraction.workflows[0]
        self.assertEqual(workflow.title.text, 'Zircon sample exchange')
        self.assertEqual(len(workflow.steps), 2)
        self.assertEqual(workflow.steps[1].deadline.text, 'within 3 days')
        self.assertTrue(workflow.steps[1].obligations)
        self.assertEqual(len(workflow.edges), 1)
        self.assertEqual(workflow.edges[0].relation, 'precedes')
        self.assertTrue(any('Reviewer' in r.role.text for r in result.roles))
        self.assertTrue(any('Zircon form' == f.title.text for f in workflow.form_requirements))
        self.assertEqual(result.scope.processed_chunk_ids, snapshot.input_chunk_ids)

    def test_multiple_workflows_and_repeated_titles_keep_distinct_ids(self):
        _, snapshot = self.ready(['업무명: 별빛 업무', '1. 담당자는 자료를 제출한다.',
                                  '업무명: 달빛 업무', '1. 담당자는 자료를 기록한다.',
                                  '업무명: 별빛 업무', '1. 담당자는 자료를 보관한다.'])
        workflows = self.run_engine(snapshot).extraction.workflows
        self.assertEqual([w.title.text for w in workflows], ['별빛 업무', '달빛 업무', '별빛 업무'])
        self.assertEqual(len({w.id for w in workflows}), 3)
        self.assertEqual(len({s.id for w in workflows for s in w.steps}), 3)

    def test_titleless_steps_use_original_text_and_unclear_order(self):
        _, snapshot = self.ready(['담당자는 자료를 확인한다.', '신청자는 자료를 제출한다.'])
        result = self.run_engine(snapshot);workflow = result.extraction.workflows[0]
        self.assertEqual(workflow.title.text, '담당자는 자료를 확인한다.')
        self.assertEqual(workflow.edges, [])
        self.assertTrue(any('명시 제목' in i.message for i in result.extraction.issues))

    def test_nonprocedural_document_returns_empty_candidates(self):
        _, snapshot = self.ready(['업무명: 색상 통계 자료', '파란색 42개, 노란색 18개.',
                                  '연도별 분포 도표.', '이 자료는 색상 분포를 설명한다.'])
        result = self.run_engine(snapshot)
        self.assertEqual(result.extraction.workflows, [])
        self.assertEqual(result.scope.status, 'complete')
        self.assertTrue(any(i.code == 'no_workflow_found' for i in result.extraction.issues))

    def test_chunk_boundary_step_is_one_step_with_grounded_fragments(self):
        text = '1. 담당자는 ' + '합성 자료의 표식을 확인하고 ' * 12 + '기록한다.'
        _, snapshot = self.ready(['업무명: 경계 검증', text], config={'max_chars': 64})
        result = self.run_engine(snapshot);step = result.extraction.workflows[0].steps[0]
        self.assertGreater(len(step.actions), 1)
        self.assertEqual(''.join(a.text for a in step.actions), text)
        self.assertEqual(len(result.extraction.workflows[0].steps), 1)
        self.assertEqual(result.scope.status, 'complete')

    def test_conditions_rejection_and_repeat_do_not_become_linear(self):
        _, snapshot = self.ready(['업무명: 예외 처리', '1. 담당자는 자료를 검토한다.',
            '2. 자료가 누락된 경우 1단계로 돌아가 보완을 요청하고 반려한다.', '3. 담당자는 자료를 보관한다.'])
        workflow = self.run_engine(snapshot).extraction.workflows[0]
        self.assertEqual(len(workflow.conditions), 1)
        self.assertEqual(len(workflow.edges), 1)
        edge = workflow.edges[0]
        self.assertEqual((edge.source, edge.target, edge.relation),
                         (workflow.steps[1].id, workflow.steps[0].id, 'conditional'))
        self.assertIn('보완', workflow.conditions[0].statement.text)

    def test_condition_subject_is_not_a_responsible_role(self):
        _, snapshot = self.ready(['업무명: 역할 검토', '1. 담당자는 자료를 검토한다.',
                                  '2. 자료가 누락된 경우 보완을 요청하고 반려한다.'])
        roles = [r.role.text for r in self.run_engine(snapshot).roles]
        self.assertIn('담당자', roles)
        self.assertNotIn('자료', roles)

    def test_ambiguous_branch_and_number_gap_have_no_invented_edges(self):
        _, snapshot = self.ready(['업무명: 분기 미확인', '1. 담당자는 자료를 접수한다.',
            '3. 담당자는 자료를 확인한다.', '4. 누락된 경우 보완을 요청한다.', '5. 담당자는 자료를 보관한다.'])
        result = self.run_engine(snapshot)
        self.assertEqual(result.extraction.workflows[0].edges, [])
        self.assertTrue(any(i.code == 'unclear_order' for i in result.extraction.issues))

    def test_role_deadline_obligation_and_form_are_only_grounded_candidates(self):
        _, snapshot = self.ready(['업무명: 도서 표본', '1. 접수 담당자는 반드시 별빛신청서를 3일 이내 제출한다.'])
        result = self.run_engine(snapshot);step = result.extraction.workflows[0].steps[0]
        self.assertEqual(result.roles[0].role.text, '접수 담당자')
        self.assertEqual(step.deadline.text, '3일 이내')
        self.assertEqual(step.obligations[0].text, step.actions[0].text)
        self.assertEqual(result.extraction.workflows[0].form_requirements[0].title.text, '별빛신청서')
        self.assertTrue(any(i.code == 'form_unresolved' for i in result.extraction.issues))

    def test_no_deadline_or_obligation_is_invented(self):
        _, snapshot = self.ready();result = self.run_engine(snapshot)
        for step in result.extraction.workflows[0].steps:
            self.assertIsNone(step.deadline)
            self.assertEqual(step.obligations, [])

    def test_result_is_deterministic_and_protocol_compatible(self):
        _, snapshot = self.ready();adapter = DeterministicWorkflowAdapter()
        a = self.run_engine(snapshot, adapter);b = self.run_engine(snapshot, adapter)
        self.assertEqual(a, b)
        self.assertEqual(parse_extraction(adapter.extract(snapshot)), a.extraction)
        self.assertEqual(a.model_id, adapter.model_id)
        self.assertEqual(a.prompt_contract_version, snapshot.settings.prompt_contract_version)

    def test_exported_result_schema_matches_model(self):
        from apps.api.workflow_discovery_models import WorkflowDiscoveryResult
        schema = json.loads(Path('schemas/workflow-discovery-v1.schema.json').read_text())
        self.assertEqual(schema, {'$schema': 'https://json-schema.org/draft/2020-12/schema',
                                  **WorkflowDiscoveryResult.model_json_schema()})

    def test_output_never_approves_or_publishes(self):
        _, snapshot = self.ready();result = self.run_engine(snapshot)
        self.assertIn(result.candidate_state, ['DRAFT', 'NEEDS_REVIEW'])
        self.assertEqual(result.validation.semantic_verification, 'NOT_VERIFIED')
        self.assertEqual(result.validation.administrator_approval, 'NOT_REQUESTED')
        self.assertFalse(result.validation.publishable)
        self.assertTrue(result.test_only)

    def test_result_carries_full_canonical_evidence_refs(self):
        _, snapshot = self.ready();result = self.run_engine(snapshot)
        canonical = {c.chunk_id: c.evidence for c in snapshot.chunks}
        self.assertTrue(result.evidence_refs)
        self.assertEqual(len({e.chunk_id for e in result.evidence_refs}), len(result.evidence_refs))
        for ref in result.evidence_refs:
            self.assertEqual(ref, canonical[ref.chunk_id])
            self.assertEqual(ref.semantic_verification, 'NOT_VERIFIED')
            self.assertTrue(ref.source_anchor)

    def test_limit_and_partial_block_are_explicit(self):
        _, snapshot = self.ready(['업무명: 부분 입력', '1. 담당자는 ' + '원문 표식을 확인하고 ' * 16 + '기록한다.'],
                                  config={'max_chars': 64})
        result = self.run_engine(snapshot, settings=DiscoverySettings(max_chunks=2))
        self.assertEqual(result.scope.traversed_chunk_ids, snapshot.input_chunk_ids)
        self.assertEqual(result.scope.status, 'incomplete')
        self.assertEqual(result.extraction.workflows, [])
        self.assertIn('partial_block', {o.reason for o in result.scope.omissions})
        self.assertIn('scope_limit', {o.reason for o in result.scope.omissions})
        self.assertTrue(any(i.code == 'partial_input' for i in result.extraction.issues))

    def test_unsupported_image_is_not_marked_processed(self):
        meta, _, _ = self.prepare(fixtures.HWPX.read_bytes(), 'image.hwpx')
        self.inputs = WorkflowInputService(self.app.state.chunks)
        snapshot = self.inputs.capture(self.principal, meta['document_id'], meta['id'])
        result = self.run_engine(snapshot)
        image_ids = {c.chunk_id for c in snapshot.chunks if c.kind == 'image'}
        self.assertTrue(image_ids)
        self.assertTrue(image_ids <= {x.chunk_id for x in result.scope.omissions})
        self.assertEqual(result.scope.status, 'incomplete')

    def test_adapter_omissions_cannot_be_hidden(self):
        _, snapshot = self.ready()
        def omitted(receipt, *_):
            empty = parse_extraction({'schema_version': 'workflow-extraction-v1', 'workflows': [],
                'issues': [{'id': 'none', 'target_ids': [], 'code': 'no_workflow_found', 'message': '미확인'}]})
            return receipt.model_copy(update={'extraction': empty, 'roles': (), 'processed_chunk_ids': (), 'omissions': ()})
        result = self.run_engine(snapshot, TransformAdapter(omitted))
        self.assertEqual(result.scope.status, 'incomplete')
        self.assertEqual({o.reason for o in result.scope.omissions}, {'adapter_omitted'})
        self.assertTrue(any(i.code == 'partial_input' for i in result.extraction.issues))

    def test_duplicate_workflow_and_step_ids_are_rejected(self):
        _, snapshot = self.ready()
        for target in ['workflow', 'step']:
            def duplicate(receipt, *_):
                output = receipt.extraction.model_copy(deep=True)
                if target == 'workflow':output.workflows.append(output.workflows[0])
                else:output.workflows[0].steps.append(output.workflows[0].steps[0])
                return receipt.model_copy(update={'extraction': output})
            with self.subTest(target=target), self.assertRaises(DomainError):self.run_engine(snapshot, TransformAdapter(duplicate))

    def test_unknown_citation_and_ungrounded_claim_are_rejected(self):
        _, snapshot = self.ready()
        for target in ['citation', 'claim']:
            def invalid(receipt, *_):
                output = receipt.extraction.model_copy(deep=True)
                title = output.workflows[0].title
                if target == 'citation':title.evidence[0] = title.evidence[0].model_copy(update={'chunk_id': 'missing'})
                else:output.workflows[0] = output.workflows[0].model_copy(update={'title': title.model_copy(update={'text': '근거 없는 999일 법적 의무'})})
                return receipt.model_copy(update={'extraction': output})
            with self.subTest(target=target), self.assertRaises(DomainError):self.run_engine(snapshot, TransformAdapter(invalid))

    def test_bad_receipt_and_exceptions_are_safe_failures(self):
        _, snapshot = self.ready()
        for transform in [lambda *_: {}, lambda *_: (_ for _ in ()).throw(ValueError('sensitive-test-only'))]:
            with self.subTest(transform=type(transform).__name__), self.assertRaises(DomainError) as e:
                self.run_engine(snapshot, TransformAdapter(transform))
            self.assertNotIn('sensitive-test-only', str(e.exception))

    def test_duplicate_unknown_and_overlapping_coverage_rejected(self):
        _, snapshot = self.ready()
        for ids in [('missing',), (snapshot.input_chunk_ids[0],) * 2]:
            adapter = TransformAdapter(lambda r, *_: r.model_copy(update={'processed_chunk_ids': ids}))
            with self.subTest(ids=ids), self.assertRaises(DomainError):self.run_engine(snapshot, adapter)

    def test_citation_must_be_inside_declared_processed_scope(self):
        _, snapshot = self.ready()
        adapter = TransformAdapter(lambda r, *_: r.model_copy(update={'processed_chunk_ids': ()}))
        with self.assertRaisesRegex(DomainError, 'outside_processed_scope'):self.run_engine(snapshot, adapter)

    def test_bad_role_reference_or_invented_role_rejected(self):
        _, snapshot = self.ready()
        for change in ['step_id', 'text']:
            def invalid(receipt, *_):
                role = receipt.roles[0]
                if change == 'step_id':role = role.model_copy(update={'step_id': 'absent'})
                else:role = role.model_copy(update={'role': role.role.model_copy(update={'text': '허위 슈퍼관리자'})})
                return receipt.model_copy(update={'roles': (role,)})
            with self.subTest(change=change), self.assertRaises(DomainError):self.run_engine(snapshot, TransformAdapter(invalid))

    def test_mutated_adapter_input_rejected_without_changing_original_snapshot(self):
        _, snapshot = self.ready();before = snapshot.model_dump_json()
        def mutate(receipt, supplied, *_):
            supplied.chunks[0].evidence.spans.append(supplied.chunks[0].evidence.spans[0])
            return receipt
        with self.assertRaisesRegex(DomainError, 'mutated_input'):self.run_engine(snapshot, TransformAdapter(mutate))
        self.assertEqual(snapshot.model_dump_json(), before)

    def test_stale_generation_is_rejected(self):
        from apps.api.chunking import ChunkConfig
        meta, snapshot = self.ready();chunks = self.app.state.chunks
        chunks.enqueue(self.principal, meta['document_id'], meta['id'], ChunkConfig(max_chars=64))
        self.assertEqual(chunks.execute(self.worker, chunks.claim(self.worker)), 'completed')
        with self.assertRaises(DomainError):self.run_engine(snapshot)

    def test_change_during_adapter_call_is_rejected(self):
        meta, snapshot = self.ready()
        def deregister(receipt, *_):
            self.app.state.service.deregister(self.principal, meta['document_id']);return receipt
        with self.assertRaises(DomainError):self.run_engine(snapshot, TransformAdapter(deregister))

    def test_foreign_document_citation_and_foreign_principal_rejected(self):
        _, first = self.ready();_, second = self.ready(['업무명: 다른 자료', '1. 담당자는 원본을 보관한다.'])
        other = DeterministicWorkflowAdapter().extract(second)
        adapter = TransformAdapter(lambda r, *_: r.model_copy(update={'extraction': other, 'roles': ()}))
        with self.assertRaises(DomainError):self.run_engine(first, adapter)
        engine = WorkflowDiscoveryEngine(self.inputs, DeterministicWorkflowAdapter())
        with self.assertRaises(DomainError):engine.run(Principal('foreign', 'B', 'manager'), first)

    def test_model_flags_cannot_enable_real_providers(self):
        self.ready()
        for field, value in [('test_only', False), ('network_access', True)]:
            adapter = DeterministicWorkflowAdapter();setattr(adapter, field, value)
            with self.subTest(field=field), self.assertRaises(DomainError):WorkflowDiscoveryEngine(self.inputs, adapter)

    def test_same_document_different_version_output_is_rejected(self):
        meta, first = self.ready()
        newer, _, _ = self.prepare(synthetic_hwpx(['업무명: 개정 자료', '1. 담당자는 새 자료를 보관한다.']),
                                    'revision.hwpx', meta['document_id'])
        second = self.inputs.capture(self.principal, newer['document_id'], newer['id'])
        other = DeterministicWorkflowAdapter().extract(second)
        with self.assertRaises(DomainError):
            self.run_engine(first, TransformAdapter(lambda r, *_: r.model_copy(update={'extraction': other, 'roles': ()})))
        self.app.state.service.activate(self.principal, newer['document_id'], newer['id'])
        with self.assertRaises(DomainError):self.run_engine(first)

    def test_adapter_provenance_cannot_change_during_extraction(self):
        _, snapshot = self.ready()
        adapter = TransformAdapter(lambda r, *_: r)
        def changed(receipt, *_):
            adapter.rule_version = 'changed-after-start';return receipt
        adapter.transform = changed
        with self.assertRaisesRegex(DomainError, 'configuration_changed'):self.run_engine(snapshot, adapter)

    def test_nontext_cannot_be_falsely_claimed_processed(self):
        meta, _, _ = self.prepare(fixtures.HWPX.read_bytes(), 'image.hwpx')
        self.inputs = WorkflowInputService(self.app.state.chunks)
        snapshot = self.inputs.capture(self.principal, meta['document_id'], meta['id'])
        adapter = TransformAdapter(lambda r, _, ids: r.model_copy(update={'processed_chunk_ids': ids, 'omissions': ()}))
        with self.assertRaisesRegex(DomainError, 'unsupported_workflow_chunk'):self.run_engine(snapshot, adapter)

    def test_early_traversal_truncation_is_rejected(self):
        _, snapshot = self.ready()
        with patch.object(self.inputs, 'iter_chunks', return_value=iter(snapshot.chunks[:-1])):
            with self.assertRaisesRegex(DomainError, 'traversal_incomplete'):self.run_engine(snapshot)

    def test_database_and_original_are_unchanged(self):
        meta, snapshot = self.ready()
        def dump():
            with self.app.state.service.repo.transaction() as db:return '\n'.join(db.connection.iterdump())
        before = dump();original = self.app.state.service.store.read(meta['id'], meta['sha256'])
        self.run_engine(snapshot)
        self.assertEqual(dump(), before)
        self.assertEqual(self.app.state.service.store.read(meta['id'], meta['sha256']), original)
