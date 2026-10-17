import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_chunking as chunk_fixtures
import test_parsing as parsing_fixtures
from pydantic import ValidationError
from apps.api.chunking import ChunkConfig, build_chunks
from apps.api.errors import DomainError
from apps.api.models import Principal
from apps.api.workflow_contracts import (MAX_OUTPUT_BYTES, WorkflowExtraction, WorkflowValidation,
                                         parse_extraction)
from apps.api.workflow_evidence import LegacyEvidenceAdapter, validate_extraction
from apps.api.workflow_snapshot import (WorkflowInputService, WorkflowInputSnapshot, SnapshotSettings)


def example(citation=None):
    quote = '신청서를 제출한다.'
    citation = citation or {'chunk_id': 'c1', 'block_id': 'b1', 'start': 0, 'end': len(quote), 'quote': quote}
    assertion = {'text': citation['quote'], 'evidence': [citation]}
    step = lambda key: {'id': key, 'label': copy.deepcopy(assertion), 'actions': [copy.deepcopy(assertion)],
                        'deadline': None, 'obligations': []}
    return {'schema_version': 'workflow-extraction-v1', 'workflows': [{
        'id': 'w1', 'title': copy.deepcopy(assertion), 'steps': [step('s1'), step('s2')],
        'conditions': [{'id': 'cond1', 'statement': copy.deepcopy(assertion), 'step_ids': ['s2']}],
        'edges': [{'id': 'edge1', 'source': 's1', 'target': 's2', 'relation': 'conditional',
                   'condition_ids': ['cond1'], 'explanation': copy.deepcopy(assertion)}],
        'form_requirements': [{'id': 'form1', 'title': copy.deepcopy(assertion),
                              'requirement': copy.deepcopy(assertion), 'step_ids': ['s1']}]}],
        'issues': [{'id': 'issue1', 'target_ids': ['w1'], 'code': 'semantic_review_required', 'message': '의미 검토 필요'}]}


class WorkflowContractTests(unittest.TestCase):
    def test_strict_json_roundtrip_preserves_null(self):
        model = parse_extraction(json.dumps(example(), ensure_ascii=False))
        self.assertEqual(model.model_dump(), example())
        self.assertIsNone(model.workflows[0].steps[0].deadline)

    def test_extra_and_missing_fields_at_each_level(self):
        for change in ['extra', 'missing']:
            for target in ['root', 'workflow', 'step', 'condition', 'edge', 'form', 'issue', 'assertion', 'citation']:
                p = example(); w = p['workflows'][0]
                obj = {'root': p, 'workflow': w, 'step': w['steps'][0], 'condition': w['conditions'][0],
                       'edge': w['edges'][0], 'form': w['form_requirements'][0], 'issue': p['issues'][0],
                       'assertion': w['title'], 'citation': w['title']['evidence'][0]}[target]
                if change == 'extra':
                    obj['semantic_verification'] = 'VERIFIED'
                else:
                    del obj[next(iter(obj))]
                with self.subTest(change=change, target=target), self.assertRaises(ValidationError):
                    parse_extraction(p)

    def test_invalid_json_duplicate_keys_nonfinite_and_oversize(self):
        for raw in ['{', '[]', '{"workflows":[],"workflows":[]}', '{"x":NaN}', ' ' * (MAX_OUTPUT_BYTES + 1)]:
            with self.subTest(raw_type=raw[:20]), self.assertRaises(ValueError):
                parse_extraction(raw)

    def test_wrong_scalar_types_and_blank_assertion(self):
        for value in [False, 1, None, '   ']:
            p = example();p['workflows'][0]['title']['text'] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                parse_extraction(p)
        p = example();p['workflows'][0]['title']['evidence'][0]['start'] = False
        with self.assertRaises(ValidationError):parse_extraction(p)

    def test_duplicate_ids_across_all_node_kinds(self):
        for target in ['steps', 'conditions', 'edges', 'form_requirements']:
            p = example();p['workflows'][0][target][0]['id'] = 'w1'
            with self.subTest(target=target), self.assertRaisesRegex(ValueError, 'duplicate_workflow_id'):
                parse_extraction(p)
        p = example();p['issues'][0]['id'] = 'w1'
        with self.assertRaises(ValueError):parse_extraction(p)

    def test_invalid_step_condition_and_issue_references(self):
        for change in ['source', 'target', 'condition', 'condition_step', 'form_step', 'issue', 'duplicate_step_ref', 'condition_target']:
            p = example();w = p['workflows'][0]
            if change in ['source', 'target']:w['edges'][0][change] = 'absent'
            elif change == 'condition':w['edges'][0]['condition_ids'] = ['absent']
            elif change == 'condition_step':w['conditions'][0]['step_ids'] = ['absent']
            elif change == 'form_step':w['form_requirements'][0]['step_ids'] = ['absent']
            elif change == 'issue':p['issues'][0]['target_ids'] = ['absent']
            elif change == 'duplicate_step_ref':w['conditions'][0]['step_ids'] = ['s2', 's2']
            else:w['conditions'][0]['step_ids'] = ['s1']
            with self.subTest(change=change), self.assertRaises(ValidationError):parse_extraction(p)

    def test_invalid_relation_self_edge_and_condition_semantics(self):
        for relation in ['exec', 'precedes', 'requires']:
            p = example();p['workflows'][0]['edges'][0]['relation'] = relation
            with self.subTest(relation=relation), self.assertRaises(ValidationError):parse_extraction(p)
        p = example();p['workflows'][0]['edges'][0]['target'] = 's1'
        with self.assertRaises(ValidationError):parse_extraction(p)

    def test_empty_or_duplicate_evidence_and_invalid_offset(self):
        for kind in ['empty', 'duplicate', 'bounds']:
            p = example();a = p['workflows'][0]['title']
            if kind == 'empty':a['evidence'] = []
            elif kind == 'duplicate':a['evidence'] *= 2
            else:a['evidence'][0]['end'] += 1
            with self.subTest(kind=kind), self.assertRaises(ValidationError):parse_extraction(p)

    def test_node_and_output_size_limits(self):
        p = example();w = p['workflows'][0]
        w['steps'] = [copy.deepcopy(w['steps'][0]) for _ in range(201)]
        with self.assertRaises(ValidationError):parse_extraction(p)
        p = example();base = p['workflows'][0];p['workflows'] = [];p['issues'] = []
        for n in range(20):
            w = copy.deepcopy(base);w['id'] = f'w{n}';w['edges'] = [];w['conditions'] = [];w['form_requirements'] = []
            w['steps'] = [{**copy.deepcopy(base['steps'][0]), 'id': f's{n}_{i}'} for i in range(50)]
            p['workflows'].append(w)
        with self.assertRaisesRegex(ValidationError, 'workflow_node_limit'):parse_extraction(p)
        p = example();p['issues'] = [{'id': f'i{i}', 'target_ids': [], 'code': 'conflict', 'message': '가' * 4000} for i in range(30)]
        with self.assertRaisesRegex(ValidationError, 'workflow_output_limit'):parse_extraction(p)

    def test_no_discovery_requires_explicit_issue(self):
        self.assertEqual(parse_extraction({'schema_version': 'workflow-extraction-v1', 'workflows': [],
            'issues': [{'id': 'i', 'target_ids': [], 'code': 'no_workflow_found', 'message': '미확인'}]}).workflows, [])
        with self.assertRaises(ValidationError):
            parse_extraction({'schema_version': 'workflow-extraction-v1', 'workflows': [], 'issues': []})

    def test_no_semantic_approval_or_publication(self):
        state = WorkflowValidation()
        self.assertEqual(state.semantic_verification, 'NOT_VERIFIED')
        self.assertFalse(state.publishable)
        for field, value in [('semantic_verification', 'VERIFIED'), ('administrator_approval', 'APPROVED'),
                             ('semantic_review_required', False), ('publishable', True)]:
            with self.subTest(field=field), self.assertRaises(ValidationError):
                WorkflowValidation.model_validate({**state.model_dump(), field: value})

    def test_adapter_model_instances_are_revalidated(self):
        model = parse_extraction(example())
        model.workflows[0].steps.append(model.workflows[0].steps[0])
        with self.assertRaises(ValidationError):parse_extraction(model)

    def test_exported_schemas_match_models(self):
        for name, model in [('workflow-extraction-v1', WorkflowExtraction),
                            ('workflow-input-snapshot-v1', WorkflowInputSnapshot), ('workflow-validation-v1', WorkflowValidation)]:
            expected = {'$schema': 'https://json-schema.org/draft/2020-12/schema', **model.model_json_schema()}
            self.assertEqual(json.loads((Path('schemas')/(name+'.schema.json')).read_text()), expected)


class WorkflowInputTests(unittest.TestCase):
    setUp = parsing_fixtures.ParsingIntegrationTests.setUp
    tearDown = parsing_fixtures.ParsingIntegrationTests.tearDown
    upload = parsing_fixtures.ParsingIntegrationTests.upload
    route = parsing_fixtures.ParsingIntegrationTests.route
    parse = parsing_fixtures.ParsingIntegrationTests.parse
    prepare = chunk_fixtures.ChunkIntegrationTests.prepare

    def ready(self):
        meta, job, chunks = self.prepare(parsing_fixtures.HWPX.read_bytes(), 'manual.hwpx')
        self.inputs = WorkflowInputService(self.app.state.chunks)
        snapshot = self.inputs.capture(self.principal, meta['document_id'], meta['id'])
        return meta, job, chunks, snapshot

    def advance(self, meta):
        c = self.app.state.chunks
        c.enqueue(self.principal, meta['document_id'], meta['id'], ChunkConfig(max_chars=64))
        self.assertEqual(c.execute(self.worker, c.claim(self.worker)), 'completed')

    def citation(self, snapshot):
        for chunk in snapshot.chunks:
            for span in chunk.evidence.spans:
                if span.source_kind == 'original_text' and span.quote:
                    return {'chunk_id': chunk.chunk_id, 'block_id': span.block_id,
                            'start': span.start, 'end': span.end, 'quote': span.quote}
        self.fail('no textual citation')

    def test_capture_full_document_and_serialization(self):
        meta, job, chunks, snapshot = self.ready()
        self.assertEqual(snapshot.input_chunk_ids, tuple(c['chunk_id'] for c in chunks))
        self.assertEqual(snapshot.chunk_job_id, job['id'])
        self.assertEqual(snapshot.parse_attempt_id, f'{snapshot.parse_job_id}:{snapshot.parse_attempt}')
        self.assertEqual(snapshot.coverage.status, 'incomplete')
        self.assertEqual(len(snapshot.coverage.unprocessed), len(chunks))
        self.assertEqual([c.chunk_id for c in self.inputs.iter_chunks(self.principal, snapshot)], list(snapshot.input_chunk_ids))
        self.assertEqual(WorkflowInputSnapshot.model_validate_json(snapshot.model_dump_json()), snapshot)
        self.assertEqual(self.inputs.capture(self.principal, meta['document_id'], meta['id']), snapshot)

    def test_partial_complete_progress_and_duplicates(self):
        _, _, _, snapshot = self.ready()
        partial = self.inputs.mark_processed(self.principal, snapshot, snapshot.input_chunk_ids[:1])
        self.assertEqual(partial.coverage.status, 'incomplete')
        complete = self.inputs.mark_processed(self.principal, partial, snapshot.input_chunk_ids[1:])
        self.assertEqual(complete.coverage.status, 'complete')
        self.assertEqual(complete.snapshot_id, snapshot.snapshot_id)
        for ids in [[snapshot.input_chunk_ids[0]], ['missing'], ['missing', 'missing']]:
            with self.subTest(ids=ids), self.assertRaises(DomainError):self.inputs.mark_processed(self.principal, partial, ids)

    def test_progress_cannot_hide_missing_chunks(self):
        _, _, _, snapshot = self.ready();p = snapshot.model_dump(mode='json')
        p['coverage']['status'] = 'complete'
        with self.assertRaises(ValidationError):WorkflowInputSnapshot.model_validate_json(json.dumps(p))
        p['coverage']['unprocessed'] = []
        with self.assertRaises(ValidationError):WorkflowInputSnapshot.model_validate_json(json.dumps(p))

    def test_input_size_limit_and_batch_bounds(self):
        meta, _, _, snapshot = self.ready()
        with self.assertRaises(DomainError):
            self.inputs.capture(self.principal, meta['document_id'], meta['id'], SnapshotSettings(max_snapshot_bytes=1024))
        for size in [0, True, 201]:
            with self.subTest(size=size), self.assertRaises(DomainError):list(self.inputs.iter_chunks(self.principal, snapshot, batch_size=size))

    def test_foreign_reader_worker_and_anonymous_access(self):
        meta, _, _, snapshot = self.ready()
        for p in [None, self.worker, Principal('reader', 'A', 'reader'), Principal('foreign', 'B', 'manager')]:
            with self.subTest(principal=p), self.assertRaises(DomainError):self.inputs.validate(p, snapshot)
            with self.subTest(capture_principal=p), self.assertRaises(DomainError):self.inputs.capture(p, meta['document_id'], meta['id'])

    def test_existing_unicode_institution_identifiers_remain_supported(self):
        self.principal = Principal('manager', '합성기관-가', 'manager')
        self.worker = Principal('worker', '합성기관-가', 'worker')
        _, _, _, snapshot = self.ready()
        self.assertEqual(self.inputs.validate(self.principal, snapshot).institution_id, '합성기관-가')

    def test_selected_inactive_version_never_becomes_current_implicitly(self):
        meta, _, _, snapshot = self.ready()
        with self.assertRaises(DomainError):self.inputs.validate(self.principal, snapshot, require_active=True)
        self.app.state.service.activate(self.principal, meta['document_id'], meta['id'])
        with self.assertRaises(DomainError):self.inputs.validate(self.principal, snapshot)
        current = self.inputs.capture(self.principal, meta['document_id'], meta['id'])
        self.assertEqual(self.inputs.validate(self.principal, current, require_active=True), current)

    def test_new_active_version_invalidates_old_snapshot(self):
        meta, _, _, _ = self.ready()
        self.app.state.service.activate(self.principal, meta['document_id'], meta['id'])
        snapshot = self.inputs.capture(self.principal, meta['document_id'], meta['id'])
        newer, _, _ = self.prepare(parsing_fixtures.pdf('new version'), 'new.pdf', meta['document_id'])
        self.app.state.service.activate(self.principal, newer['document_id'], newer['id'])
        with self.assertRaises(DomainError):self.inputs.validate(self.principal, snapshot, require_active=True)

    def test_new_chunk_generation_and_mid_iteration_change(self):
        meta, _, _, snapshot = self.ready();iterator = self.inputs.iter_chunks(self.principal, snapshot, batch_size=1)
        next(iterator);self.advance(meta)
        with self.assertRaises(DomainError):next(iterator)
        with self.assertRaises(DomainError):self.inputs.mark_processed(self.principal, snapshot, [])

    def test_change_during_capture_is_rejected(self):
        meta, _, _, _ = self.ready()
        def changed(*args):
            result = build_chunks(*args);self.advance(meta);return result
        with patch('apps.api.workflow_snapshot.build_chunks', side_effect=changed), self.assertRaises(DomainError):
            self.inputs.capture(self.principal, meta['document_id'], meta['id'])

    def test_parse_attempt_change_and_institution_change(self):
        meta, _, _, snapshot = self.ready()
        with self.app.state.service.repo.transaction() as db:
            db.connection.execute('UPDATE parse_jobs SET attempt=attempt+1 WHERE id=?', (snapshot.parse_job_id,))
        with self.assertRaises(DomainError):self.inputs.validate(self.principal, snapshot)
        with self.app.state.service.repo.transaction() as db:
            db.connection.execute("UPDATE documents SET institution_id='B' WHERE id=?", (meta['document_id'],))
        with self.assertRaises(DomainError):self.inputs.validate(self.principal, snapshot)

    def test_deregister_and_original_hash_preservation(self):
        meta, _, _, snapshot = self.ready()
        store = self.app.state.service.store
        before = store.read(meta['id'], meta['sha256'])
        self.inputs.validate(self.principal, snapshot)
        self.app.state.service.deregister(self.principal, meta['document_id'])
        with self.assertRaises(DomainError):self.inputs.validate(self.principal, snapshot)
        self.assertEqual(store.read(meta['id'], meta['sha256']), before)
        self.assertEqual(hashlib.sha256(before).hexdigest(), snapshot.original_sha256)

    def test_missing_duplicate_or_forged_stored_chunks_rejected(self):
        from apps.api.chunk_repository import ChunkQueries
        meta, _, chunks, _ = self.ready()
        for payload in [chunks[:-1], chunks + chunks[:1], [{**chunks[0], 'text': 'forged'}, *chunks[1:]]]:
            with self.subTest(count=len(payload)), patch.object(ChunkQueries, 'items', return_value=payload), self.assertRaises((DomainError, ValidationError)):
                self.inputs.capture(self.principal, meta['document_id'], meta['id'])

    def test_tampered_original_and_snapshot_are_rejected(self):
        meta, _, _, snapshot = self.ready()
        forged = snapshot.model_copy(update={'original_sha256': '0' * 64})
        with self.assertRaises(ValidationError):self.inputs.validate(self.principal, forged)
        with patch.object(self.app.state.service.store, 'read', side_effect=DomainError('original_hash_mismatch')):
            with self.assertRaises(DomainError):self.inputs.validate(self.principal, snapshot)

    def test_actual_original_corruption_is_detected(self):
        meta, _, _, snapshot = self.ready()
        path = self.app.state.service.store.path(meta['id'])
        path.chmod(0o600)
        path.write_bytes(b'synthetic test-local corruption')
        with self.assertRaisesRegex(DomainError, 'original_integrity_failure'):
            self.inputs.validate(self.principal, snapshot)

    def test_capture_validation_and_progress_do_not_write_database(self):
        meta, _, _, snapshot = self.ready()
        def dump():
            with self.app.state.service.repo.transaction() as db:
                return '\n'.join(db.connection.iterdump())
        before = dump()
        self.inputs.capture(self.principal, meta['document_id'], meta['id'])
        self.inputs.validate(self.principal, snapshot)
        self.inputs.mark_processed(self.principal, snapshot, snapshot.input_chunk_ids)
        self.assertEqual(dump(), before)

    def test_valid_evidence_link_stays_unverified(self):
        _, _, _, snapshot = self.ready();payload = example(self.citation(snapshot))
        output, state = validate_extraction(self.inputs, self.principal, snapshot, payload)
        self.assertEqual(output.model_dump(), payload)
        self.assertEqual(state.semantic_verification, 'NOT_VERIFIED')
        self.assertFalse(state.publishable)
        self.assertEqual(state.administrator_approval, 'NOT_REQUESTED')

    def test_missing_foreign_or_false_evidence(self):
        _, _, _, snapshot = self.ready()
        for field, value in [('chunk_id', 'missing'), ('block_id', 'foreign'), ('quote', '가짜 근거')]:
            citation = self.citation(snapshot);citation[field] = value
            citation['end'] = citation['start'] + len(citation['quote'])
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_extraction(self.inputs, self.principal, snapshot, example(citation))

    def test_invented_deadline_and_obligation_are_blocked(self):
        _, _, _, snapshot = self.ready()
        for field in ['deadline', 'obligations']:
            payload = example(self.citation(snapshot));claim = copy.deepcopy(payload['workflows'][0]['title'])
            claim['text'] = '법적 의무로 999일 이내 반드시 제출한다.'
            payload['workflows'][0]['steps'][0][field] = claim if field == 'deadline' else [claim]
            with self.subTest(field=field), self.assertRaises(DomainError):
                validate_extraction(self.inputs, self.principal, snapshot, payload)

    def test_explicit_legacy_bridge_roundtrip_preserves_all_fields(self):
        _, _, _, snapshot = self.ready();c = self.citation(snapshot)
        legacy = {'tenant_id': 'A', 'document_id': snapshot.document_id, 'version_id': snapshot.version_id,
                  'element_id': '구형 문단/요소 이름', 'quote': c['quote']}
        adapter = LegacyEvidenceAdapter(self.inputs)
        bridge = adapter.to_current(self.principal, legacy, snapshot, chunk_id=c['chunk_id'], block_id=c['block_id'], start=c['start'])
        self.assertEqual(adapter.to_legacy(self.principal, bridge, snapshot).model_dump(), legacy)
        ref = next(x.evidence for x in snapshot.chunks if x.chunk_id == c['chunk_id'])
        self.assertEqual(bridge.evidence_ref, ref)
        self.assertEqual(bridge.evidence_ref.semantic_verification, 'NOT_VERIFIED')

    def test_legacy_scope_false_quote_and_lossy_bridge_rejected(self):
        _, _, _, snapshot = self.ready();c = self.citation(snapshot);adapter = LegacyEvidenceAdapter(self.inputs)
        legacy = {'tenant_id': 'A', 'document_id': snapshot.document_id, 'version_id': snapshot.version_id,
                  'element_id': 'legacy-e', 'quote': c['quote']}
        for field, value in [('tenant_id', 'B'), ('version_id', 'old'), ('quote', 'invented')]:
            with self.subTest(field=field), self.assertRaises(DomainError):
                adapter.to_current(self.principal, {**legacy, field: value}, snapshot,
                                   chunk_id=c['chunk_id'], block_id=c['block_id'], start=c['start'])
        bridge = adapter.to_current(self.principal, legacy, snapshot, chunk_id=c['chunk_id'], block_id=c['block_id'], start=c['start'])
        ref = bridge.evidence_ref.model_copy(update={'spans': []})
        with self.assertRaises(DomainError):adapter.to_legacy(self.principal, bridge.model_copy(update={'evidence_ref': ref}), snapshot)
