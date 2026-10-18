"""Durable offline workflow orchestration with fenced, atomic candidate generations."""
import hashlib
import secrets
import time
from .errors import DomainError
from .models import Principal
from .chunking import canonical,digest
from .workflow_snapshot import WorkflowInputService,WorkflowInputSnapshot,SnapshotContent
from .workflow_discovery import WorkflowDiscoveryEngine
from .workflow_offline_adapter import DeterministicWorkflowAdapter
from .workflow_forms import WorkflowFormService
from .workflow_jobs_models import WorkflowJobRequest,WorkflowJobStatus,WorkflowStoredResult
from .workflow_jobs_repository import WorkflowJobRepository


def capability(value):
    return hashlib.sha256(value.encode()).hexdigest()


class WorkflowJobService:
    def __init__(self,chunks,clock=time.time,lease_seconds=120,adapter=None):
        if not 1 <= lease_seconds <= 300:raise ValueError('invalid_workflow_lease')
        self.inputs=WorkflowInputService(chunks)
        self.forms=WorkflowFormService(self.inputs)
        self.repository=WorkflowJobRepository(chunks.repo)
        self.repo=chunks.repo
        self.clock,self.lease_seconds=clock,lease_seconds
        self.engine=WorkflowDiscoveryEngine(self.inputs,adapter or DeterministicWorkflowAdapter())

    def configuration(self):
        return canonical({'engine':'workflow-jobs-v1','model':self.engine.adapter.model_id,
                          'rule':self.engine.adapter.rule_version,'review':'workflow-review-v1','forms':'workflow-forms-v1'})

    def _catalog(self,db,institution):
        return digest(self.forms.catalog.current(db,institution))

    def _fresh(self,db,principal,snapshot,catalog_hash):
        content=self.inputs._read_in(db,principal,snapshot.document_id,snapshot.version_id,snapshot.settings)
        expected=SnapshotContent.model_validate({k:getattr(snapshot,k) for k in SnapshotContent.model_fields})
        if content != expected or content.selected_active_version_id != content.version_id:
            raise DomainError('workflow_input_changed')
        self.inputs.documents.store.read(snapshot.version_id,snapshot.original_sha256)
        if self._catalog(db,principal.institution_id)!=catalog_hash:
            raise DomainError('workflow_form_catalog_changed')

    @staticmethod
    def _snapshot(row):
        snapshot=WorkflowInputSnapshot.model_validate_json(row['snapshot'])
        if (snapshot.institution_id,snapshot.document_id,snapshot.version_id,snapshot.snapshot_id)!=(
            row['institution_id'],row['document_id'],row['version_id'],row['input_snapshot_id']):
            raise DomainError('workflow_snapshot_scope_mismatch',422)
        from .workflow_discovery_models import DiscoverySettings
        settings=DiscoverySettings.model_validate_json(row['settings'])
        if digest([snapshot.snapshot_id,settings.model_dump(mode='json'),row['catalog_hash'],row['configuration']])!=row['input_key']:
            raise DomainError('workflow_job_integrity',422)
        return snapshot

    @staticmethod
    def public(row,events=()):
        return WorkflowJobStatus(events=list(events),**{k:row[k] for k in ('id','document_id','version_id','input_snapshot_id','generation',
            'state','attempt','lease_until','error_code','error_category')}).model_dump(mode='json')

    def _job(self,db,principal,document,version,key):
        self.inputs._manager(principal)
        self.inputs.documents.version(db,principal,document,version)
        row=self.repository.job(db,key)
        if not row or (row['institution_id'],row['document_id'],row['version_id'])!=(principal.institution_id,document,version):
            raise DomainError('workflow_job_not_found',404)
        return row

    def enqueue(self,principal,document,version,request=None):
        self.inputs._manager(principal)
        request=WorkflowJobRequest.model_validate_json((request or WorkflowJobRequest()).model_dump_json())
        snapshot=self.inputs.capture(principal,document,version,request.snapshot_settings)
        self.inputs.validate(principal,snapshot,require_active=True)
        with self.repo.transaction() as db:
            catalog_hash=self._catalog(db,principal.institution_id)
            self._fresh(db,principal,snapshot,catalog_hash)
            row=self.repository.enqueue(db,principal,snapshot,request.settings,catalog_hash,self.configuration(),self.clock())
            return self.public(row,self.repository.events(db,row['id']))

    def status(self,principal,document,version,key):
        with self.repo.transaction() as db:
            row=self._job(db,principal,document,version,key)
            return self.public(row,self.repository.events(db,key))

    def cancel(self,principal,document,version,key):
        with self.repo.transaction() as db:
            row=self._job(db,principal,document,version,key)
            if row['state'] not in ('queued','processing'):raise DomainError('workflow_job_not_cancellable')
            self.repository.cancel(db,key,self.clock())
            return self.public(self.repository.job(db,key),self.repository.events(db,key))

    def retry(self,principal,document,version,key):
        with self.repo.transaction() as db:
            row=self._job(db,principal,document,version,key)
        if row['state']!='failed' or row['error_category']!='RETRYABLE' or row['attempt']>=3:
            raise DomainError('workflow_job_not_retryable')
        snapshot=self._snapshot(row)
        self.inputs.validate(principal,snapshot,require_active=True)
        with self.repo.transaction() as db:
            current=self._job(db,principal,document,version,key)
            if current!=row:raise DomainError('workflow_job_changed')
            self._fresh(db,principal,snapshot,row['catalog_hash'])
            self.repository.retry(db,key,self.clock())
            return self.public(self.repository.job(db,key),self.repository.events(db,key))

    def claim(self,principal):
        if principal is None or principal.role!='worker':raise DomainError('workflow_worker_required',403)
        token=secrets.token_hex(32)
        with self.repo.transaction() as db:
            row=self.repository.claim(db,principal.institution_id,capability(token),self.clock(),self.lease_seconds)
            return None if row is None else {'id':row['id'],'institution_id':row['institution_id'],
                                             'attempt':row['attempt'],'claim_token':token}

    def _owned(self,db,claim):
        return self.repository.owned(db,claim,capability(claim['claim_token']),self.clock())

    def renew(self,claim):
        with self.repo.transaction() as db:
            if not self._owned(db,claim):return False
            self.repository.renew(db,claim['id'],self.clock()+self.lease_seconds)
            return True

    def execute(self,principal,claim):
        if principal is None or principal.role!='worker' or principal.institution_id!=claim['institution_id']:
            raise DomainError('workflow_worker_required',403)
        manager=Principal(principal.subject,principal.institution_id,'manager') # trusted local worker context only
        try:
            with self.repo.transaction() as db:
                row=self._owned(db,claim)
                if not row:return 'stale'
            snapshot=self._snapshot(row)
            if self.configuration()!=row['configuration']:raise DomainError('workflow_configuration_changed')
            self.inputs.validate(manager,snapshot,require_active=True)
            with self.repo.transaction() as db:self._fresh(db,manager,snapshot,row['catalog_hash'])
            from .workflow_discovery_models import DiscoverySettings
            discovery=self.engine.run(manager,snapshot,DiscoverySettings.model_validate_json(row['settings']))
            forms=self.forms.match(manager,snapshot,discovery)
            result=WorkflowStoredResult(discovery=discovery,forms=forms)
            if len(result.model_dump_json().encode())>16777216:raise DomainError('workflow_result_limit')
            # Full original reparse immediately before transaction; transaction-bound
            # metadata/blocks/chunks/catalog comparison closes the publication race.
            self.inputs.validate(manager,snapshot,require_active=True)
            with self.repo.transaction() as db:
                current=self._owned(db,claim)
                if not current:return 'stale'
                self._fresh(db,manager,snapshot,row['catalog_hash'])
                self.repository.finish(db,current,result,self.clock())
            return 'completed'
        except Exception as error:
            if isinstance(error,DomainError):
                stale=any(t in error.code for t in ('stale','changed','inactive','not_found','not_ready'))
                category='STALE_INPUT' if stale else 'PERMANENT'
                code='workflow_input_changed' if stale else 'workflow_validation_failed'
            elif isinstance(error,ValueError):
                category,code='PERMANENT','workflow_invalid_stored_input'
            else:
                category,code='RETRYABLE','workflow_internal_failure'
            with self.repo.transaction() as db:
                if not self._owned(db,claim):return 'stale'
                self.repository.fail(db,claim['id'],code,category,self.clock())
            return 'failed'

    def current(self,principal,document,version):
        self.inputs._manager(principal)
        with self.repo.transaction() as db:
            self.inputs.documents.version(db,principal,document,version)
            generation=self.repository.current(db,principal.institution_id,document,version)
            if not generation:raise DomainError('workflow_generation_not_found',404)
            row=self.repository.job(db,generation['job_id'])
            components=self.repository.components(db,generation['id'])
        if digest(generation['payload'])!=generation['payload_hash']:raise DomainError('workflow_result_integrity',422)
        result=WorkflowStoredResult.model_validate_json(generation['payload'])
        snapshot=self._snapshot(row)
        expected={
            'candidates':sorted([c.model_dump(mode='json') for c in result.discovery.extraction.workflows],key=lambda c:c['id']),
            'issues':[i.model_dump(mode='json') for i in result.forms.source_review.issues]+[i.model_dump(mode='json') for r in result.forms.relations for i in r.issues],
            'forms':sorted([r.model_dump(mode='json') for r in result.forms.relations],key=lambda r:r['requirement_id'])}
        if components!=expected:raise DomainError('workflow_result_integrity',422)
        self.inputs.validate(principal,snapshot,require_active=True)
        fresh_forms=self.forms.match(principal,snapshot,result.discovery)
        def signature(forms):
            value=forms.model_dump(mode='json')
            value['source_review']['issues'].sort(key=canonical)
            for relation in value['relations']:relation['issues'].sort(key=canonical)
            return canonical(value)
        if signature(fresh_forms)!=signature(result.forms):raise DomainError('workflow_result_stale',409)
        with self.repo.transaction() as db:
            self._fresh(db,principal,snapshot,row['catalog_hash'])
            latest=self.repository.current(db,principal.institution_id,document,version)
            if latest!=generation:raise DomainError('workflow_generation_changed')
            events=self.repository.events(db,row['id'])
        return {'generation_id':generation['id'],'job':self.public(row,events),'result':result}

    def candidates(self,principal,document,version,candidate_id=None,part=None):
        current=self.current(principal,document,version)
        result=current['result']
        candidates=result.discovery.extraction.workflows
        if candidate_id is not None:
            candidates=[c for c in candidates if c.id==candidate_id]
            if not candidates:raise DomainError('workflow_candidate_not_found',404)
        ids={c.id for c in candidates}
        node_ids={n.id for c in candidates for n in [c,*c.steps,*c.conditions,*c.edges,*c.form_requirements]}
        if part=='issues':
            issues=[i for i in result.forms.source_review.issues if candidate_id is None or not i.target_ids or set(i.target_ids)&node_ids]
            issues += [i for r in result.forms.relations if r.workflow_id in ids for i in r.issues]
            payload={'issues':issues}
        elif part=='forms':payload={'form_links':[r for r in result.forms.relations if r.workflow_id in ids]}
        elif part=='evidence':
            from .workflow_contracts import assertions
            chunks={e.chunk_id for c in candidates for a in assertions(c) for e in a.evidence}
            refs=[r for r in result.discovery.evidence_refs if r.chunk_id in chunks]
            for ref in refs:self.inputs.chunks.resolve(principal,document,version,ref.chunk_id,ref)
            payload={'evidence_refs':refs}
        else:payload={'candidates':candidates}
        return {'schema_version':'workflow-query-v1','generation_id':current['generation_id'],
                'job_id':current['job']['id'],'semantic_verification':'NOT_VERIFIED',
                'administrator_approval':'NOT_REQUESTED','publishable':False,**payload}
