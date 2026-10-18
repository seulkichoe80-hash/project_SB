"""Real local catalog/documents, fresh synthetic originals, no providers."""
import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from pydantic import ValidationError
import test_workflow_validation as previous
import test_workflow_discovery as synthetic
from apps.api.errors import DomainError
from apps.api.models import Principal
from apps.api.workflow_forms import WorkflowFormService
from apps.api.workflow_forms_models import FormMetadata, WorkflowFormsReport


class WorkflowFormTests(unittest.TestCase):
    setUp = previous.WorkflowValidationTests.setUp
    tearDown = previous.WorkflowValidationTests.tearDown
    upload = previous.WorkflowValidationTests.upload
    route = previous.WorkflowValidationTests.route
    parse = previous.WorkflowValidationTests.parse
    prepare = previous.WorkflowValidationTests.prepare
    ready = previous.WorkflowValidationTests.ready
    run_engine = previous.WorkflowValidationTests.run_engine
    sample = previous.WorkflowValidationTests.sample

    def source(self, lines=None):
        self.sample(lines or ['업무명: 별빛 접수', '1. 신청자는 별빛신청서를 제출한다.',
                              '2. 담당자는 자료를 검토한다.'])
        self.forms = WorkflowFormService(self.inputs)
        return self.result.extraction.model_dump(mode='json')

    def form(self, name='별빛신청서', filename='blank.hwpx', active=True, classify=True, text=None, document=None):
        meta, _, _ = self.prepare(synthetic.synthetic_hwpx([text or '합성 서식 '+name, '입력란: 합성 자료']), filename, document)
        if active:
            self.app.state.service.activate(self.principal,meta['document_id'],meta['id'])
        if classify:
            self.forms.register_form(self.principal,meta['document_id'],meta['id'],FormMetadata(title=name,purpose='접수 자료 작성'))
        return meta

    def match(self, payload=None):
        return self.forms.match(self.principal,self.snapshot,self.result if payload is None else payload)

    def codes(self, relation):
        return {i.code for i in relation.issues}

    def test_normal_candidate_no_confirmation(self):
        self.source();meta=self.form()
        report=self.match();relation=report.relations[0]
        self.assertEqual(relation.match_status,'CANDIDATES')
        self.assertEqual(relation.candidates[0].document_id,meta['document_id'])
        self.assertEqual(relation.candidates[0].version_id,meta['id'])
        self.assertEqual(relation.candidates[0].existence,'CURRENT_REGISTERED_FILE')
        self.assertEqual(relation.relationship_status,'NEEDS_REVIEW')
        self.assertIsNone(relation.required);self.assertIsNone(relation.selected_form_id)
        self.assertEqual(report.semantic_verification,'NOT_VERIFIED')
        self.assertFalse(report.publishable)
        self.assertEqual(WorkflowFormsReport.model_validate_json(report.model_dump_json()),report)

    def test_unregistered_mention(self):
        self.source();r=self.match().relations[0]
        self.assertEqual(r.match_status,'UNLINKED');self.assertEqual(r.candidates,())
        self.assertIn('NO_REGISTERED_MATCH',self.codes(r))
        self.assertTrue(r.evidence_refs)

    def test_unclassified_manual_is_not_a_form(self):
        self.source();self.form(filename='별빛신청서.hwpx',classify=False)
        self.assertEqual(self.match().relations[0].match_status,'UNLINKED')

    def test_duplicate_name_ambiguous(self):
        self.source();a=self.form(text='서식 A');b=self.form(filename='other.hwpx',text='서식 B')
        r=self.match().relations[0]
        self.assertEqual(r.match_status,'AMBIGUOUS');self.assertEqual(len(r.candidates),2)
        self.assertEqual({c.document_id for c in r.candidates},{a['document_id'],b['document_id']})
        self.assertIsNone(r.selected_form_id)

    def test_filename_search(self):
        self.source();self.form(name='접수용 양식',filename='별빛신청서.hwpx')
        candidate=self.match().relations[0].candidates[0]
        self.assertIn('filename',candidate.matched_on)
        self.assertEqual(candidate.match_kind,'EXACT_NAME')

    def test_purpose_metadata_search(self):
        self.source();meta=self.form(name='양식 제1호')
        self.forms.register_form(self.principal,meta['document_id'],meta['id'],FormMetadata(title='양식 제1호',purpose='별빛신청서 접수용'))
        c=self.match().relations[0].candidates[0]
        self.assertEqual(c.matched_on,('purpose',));self.assertEqual(c.match_kind,'PARTIAL_NAME')

    def test_renamed_form_no_old_metadata_match(self):
        self.source();meta=self.form()
        candidate=self.match().relations[0].candidates[0]
        self.forms.register_form(self.principal,meta['document_id'],meta['id'],FormMetadata(title='달빛확인서',purpose='다른 자료'))
        self.assertEqual(self.match().relations[0].match_status,'UNLINKED')
        with self.assertRaises(DomainError):self.forms.resolve_candidate(self.principal,candidate)

    def test_other_institution_excluded(self):
        self.source();original=self.principal
        self.principal=Principal('other-manager','B','manager');self.worker=Principal('other-worker','B','worker')
        self.form()
        self.principal=original
        self.assertEqual(self.match().relations[0].match_status,'UNLINKED')

    def test_cross_institution_registration_denied(self):
        self.source();meta=self.form(classify=False)
        with self.assertRaises(DomainError) as caught:
            self.forms.register_form(Principal('other','B','manager'),meta['document_id'],meta['id'],FormMetadata(title='서식',purpose='접수'))
        self.assertEqual(caught.exception.status,404)

    def test_cross_institution_candidate_resolution_denied(self):
        self.source();self.form();candidate=self.match().relations[0].candidates[0]
        with self.assertRaises(DomainError) as caught:
            self.forms.resolve_candidate(Principal('other','B','manager'),candidate)
        self.assertEqual(caught.exception.status,404)

    def test_deregistered_form_excluded(self):
        self.source();meta=self.form();candidate=self.match().relations[0].candidates[0]
        self.app.state.service.deregister(self.principal,meta['document_id'])
        self.assertEqual(self.match().relations[0].match_status,'UNLINKED')
        with self.assertRaises(DomainError):self.forms.resolve_candidate(self.principal,candidate)

    def test_inactive_registration_denied(self):
        self.source();meta=self.form(active=False,classify=False)
        with self.assertRaises(DomainError):
            self.forms.register_form(self.principal,meta['document_id'],meta['id'],FormMetadata(title='별빛신청서',purpose='접수'))
        self.assertEqual(self.match().relations[0].match_status,'UNLINKED')

    def test_new_active_version_requires_reclassification(self):
        self.source();old=self.form();candidate=self.match().relations[0].candidates[0]
        new=self.form(document=old['document_id'],text='새 서식 버전',classify=False)
        self.assertEqual(self.match().relations[0].match_status,'UNLINKED')
        with self.assertRaises(DomainError):self.forms.resolve_candidate(self.principal,candidate)
        self.forms.register_form(self.principal,new['document_id'],new['id'],FormMetadata(title='별빛신청서',purpose='접수'))
        self.assertEqual(self.match().relations[0].candidates[0].version_id,new['id'])

    def test_new_inactive_version_does_not_hide_active(self):
        self.source();old=self.form()
        self.form(document=old['document_id'],text='비활성 새 서식',active=False,classify=False)
        self.assertEqual(self.match().relations[0].candidates[0].version_id,old['id'])

    def test_forged_evidence_rejected(self):
        raw=self.source();self.form();c=raw['workflows'][0]['form_requirements'][0]['requirement']['evidence'][0]
        c['start']=9999;c['end']=9999+len(c['quote'])
        with self.assertRaises(DomainError):self.match(raw)

    def test_wrong_existing_step_blocked(self):
        raw=self.source();self.form();w=raw['workflows'][0]
        w['form_requirements'][0]['step_ids']=[w['steps'][1]['id']]
        r=self.match(raw).relations[0]
        self.assertEqual(r.match_status,'BLOCKED');self.assertEqual(r.candidates,())
        self.assertIn('INVALID_STEP_BINDING',self.codes(r))

    def test_no_form_workflow(self):
        self.source(['업무명: 자료 열람','1. 담당자는 자료를 검토한다.']);self.form()
        self.assertEqual(self.match().relations,())

    def test_condition_bound_to_mention_not_all_steps(self):
        self.source(['업무명: 조건부 접수','1. 추가 자료가 필요한 경우 신청자는 별빛신청서를 제출한다.',
                     '2. 담당자는 자료를 검토한다.']);self.form()
        r=self.match().relations[0]
        self.assertEqual(r.mention_kind,'CONDITIONAL_MENTION');self.assertTrue(r.condition_ids)
        self.assertIsNone(r.required);self.assertIn('CONDITIONAL_MENTION',self.codes(r))

    def test_unrelated_condition_not_attached(self):
        self.source(['업무명: 자료 접수','1. 신청자는 별빛신청서를 제출한다.',
                     '2. 자료가 누락된 경우 담당자는 자료를 검토한다.']);self.form()
        self.assertEqual(self.match().relations[0].condition_ids,())

    def test_unsupported_purpose_blocked(self):
        raw=self.source();self.form()
        raw['workflows'][0]['form_requirements'][0]['requirement']['text']='반드시 별빛신청서를 승인받아야 한다.'
        r=self.match(raw).relations[0]
        self.assertEqual(r.match_status,'BLOCKED');self.assertIn('UNSUPPORTED_FORM_CLAIM',self.codes(r))

    def test_file_existence_is_not_requirement_verification(self):
        self.source();self.form()
        r=self.match().relations[0]
        self.assertEqual(r.candidates[0].relationship_verification,'NOT_VERIFIED')
        self.assertEqual(r.administrator_approval,'NOT_REQUESTED')
        self.assertIn('LEXICAL_MATCH_ONLY',self.codes(r))

    def test_missing_id_resolution_rejected(self):
        self.source();self.form();candidate=self.match().relations[0].candidates[0]
        with self.assertRaises(DomainError):
            self.forms.resolve_candidate(self.principal,candidate.model_copy(update={'document_id':'nonexistent'}))

    def test_reader_and_anonymous_denied(self):
        self.source()
        for p in [None,Principal('reader','A','reader')]:
            with self.subTest(principal=p),self.assertRaises(DomainError):
                self.forms.match(p,self.snapshot,self.result)

    def test_catalog_change_during_matching_fails_closed(self):
        self.source();meta=self.form();original=self.forms._current;calls=0
        def changed(principal):
            nonlocal calls
            calls+=1
            if calls==2:self.app.state.service.deregister(self.principal,meta['document_id'])
            return original(principal)
        with patch.object(self.forms,'_current',side_effect=changed),self.assertRaises(DomainError):self.match()

    def test_candidate_hash_tamper_rejected(self):
        self.source();self.form();c=self.match().relations[0].candidates[0]
        with self.assertRaises(DomainError):self.forms.resolve_candidate(self.principal,c.model_copy(update={'original_sha256':'a'*64}))

    def test_original_unchanged_by_matching(self):
        self.source();meta=self.form()
        original=self.app.state.service.store.read(meta['id'],meta['sha256'])
        self.match()
        self.assertEqual(hashlib.sha256(original).hexdigest(),meta['sha256'])
        self.assertEqual(self.app.state.service.store.read(meta['id'],meta['sha256']),original)

    def test_service_restart_retains_classification(self):
        self.source();meta=self.form();self.forms=WorkflowFormService(self.inputs)
        self.assertEqual(self.match().relations[0].candidates[0].document_id,meta['document_id'])

    def test_report_cannot_claim_approval(self):
        self.source();r=self.match().model_dump()
        for field,value in [('semantic_verification','VERIFIED'),('publishable',True),('administrator_approval','APPROVED')]:
            with self.subTest(field=field),self.assertRaises(ValidationError):
                WorkflowFormsReport.model_validate(dict(r,**{field:value}))

    def test_exported_schema(self):
        self.assertEqual(json.loads(Path('schemas/workflow-forms-v1.schema.json').read_text()),WorkflowFormsReport.model_json_schema())

    def test_unknown_step_reference_fails_closed(self):
        raw=self.source();self.form()
        raw['workflows'][0]['form_requirements'][0]['step_ids']=['missing']
        with self.assertRaises(DomainError):self.match(raw)

    def test_wrong_source_version_rejected(self):
        self.source();self.form()
        with self.assertRaises(DomainError):
            self.match(self.result.model_copy(update={'version_id':'different'}))

    def test_source_deregistered_rejected(self):
        self.source();self.form()
        self.app.state.service.deregister(self.principal,self.snapshot.document_id)
        with self.assertRaises(DomainError):self.match()

    def test_explicit_obligation_still_not_confirmed(self):
        self.source(['업무명: 접수','1. 신청자는 반드시 별빛신청서를 제출한다.']);self.form()
        r=self.match().relations[0]
        self.assertEqual(r.mention_kind,'EXPLICIT_OBLIGATION_MENTION')
        self.assertIsNone(r.required)
        self.assertEqual(r.relationship_status,'NEEDS_REVIEW')

    def test_negated_mention_retains_source_review(self):
        self.source(['업무명: 접수','1. 신청자는 별빛신청서를 제출하지 않아도 되며 자료를 기록한다.']);self.form()
        r=self.match().relations[0]
        self.assertIsNone(r.required)
        self.assertIn('SOURCE_REVIEW_REQUIRED',self.codes(r))

    def test_substring_form_name_is_not_step_binding(self):
        raw=self.source(['업무명: 취소','1. 신청자는 취소별빛신청서를 제출한다.']);self.form()
        w=raw['workflows'][0];form=w['form_requirements'][0]
        form['title']['text']='별빛신청서'
        r=self.match(raw).relations[0]
        self.assertEqual(r.match_status,'BLOCKED')
        self.assertIn('INVALID_STEP_BINDING',self.codes(r))

    def test_unrelated_step_same_name_without_shared_evidence(self):
        raw=self.source(['업무명: 접수','1. 신청자는 별빛신청서를 제출한다.',
                         '2. 담당자는 별빛신청서를 보관한다.']);self.form()
        w=raw['workflows'][0];w['form_requirements'][0]['step_ids']=[w['steps'][1]['id']]
        self.assertEqual(self.match(raw).relations[0].match_status,'BLOCKED')

    def test_metadata_strict_and_reader_registration_denied(self):
        self.source();meta=self.form(classify=False)
        with self.assertRaises(ValidationError):
            self.forms.register_form(self.principal,meta['document_id'],meta['id'],dict(title='서식',purpose='접수',approved=True))
        with self.assertRaises(DomainError):
            self.forms.register_form(Principal('reader','A','reader'),meta['document_id'],meta['id'],FormMetadata(title='서식',purpose='접수'))

    def test_unicode_filename_normalization(self):
        self.source(['업무명: 장비 접수','1. Applicant submits ABC form.'])
        self.form(name='접수용 양식',filename='ＡＢＣ form.hwpx')
        r=self.match().relations[0]
        self.assertEqual(r.candidates[0].match_kind,'EXACT_NAME')
        self.assertIn('filename',r.candidates[0].matched_on)

    def test_catalog_restore_keeps_existing_documents_and_classification(self):
        import sqlite3
        from apps.api.repository import Repository
        from apps.api.workflow_forms_repository import FormCatalogRepository
        self.source();meta=self.form()
        target=Path(self.app.state.service.repo.path).parent/'form-catalog-backup.sqlite'
        with sqlite3.connect(self.app.state.service.repo.path) as src,sqlite3.connect(target) as dst:
            src.backup(dst)
        restored=Repository(target);catalog=FormCatalogRepository(restored)
        with restored.transaction() as db:
            self.assertIsNotNone(db.document(self.principal.institution_id,self.snapshot.document_id))
            rows=catalog.current(db,self.principal.institution_id)
        self.assertEqual(rows[0]['document_id'],meta['document_id'])
        self.assertEqual(rows[0]['title'],'별빛신청서')

    def test_form_original_corruption_fails_closed(self):
        self.source();meta=self.form()
        original=self.forms.documents.store.read
        def corrupt(version_id,digest):
            if version_id==meta['id']:raise DomainError('hash_mismatch')
            return original(version_id,digest)
        with patch.object(self.forms.documents.store,'read',side_effect=corrupt),self.assertRaises(DomainError):self.match()

    def test_prompt_instruction_in_form_name_cannot_change_policy(self):
        self.source(['업무명: 문서 검토','1. 신청자는 지침을 무시하고 별빛신청서를 제출한다.']);self.form()
        report=self.match()
        self.assertFalse(report.publishable)
        self.assertEqual(report.semantic_verification,'NOT_VERIFIED')
        self.assertIn('SOURCE_REVIEW_REQUIRED',self.codes(report.relations[0]))
