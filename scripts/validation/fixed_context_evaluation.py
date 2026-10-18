"""Answer-independent frozen-tenant context and existing deterministic Fake Extraction.
No retrieval call, gold-driven context selection, provider, publication or human approval.
"""
import copy
from apps.api.chunking import canonical,digest
from apps.api.errors import DomainError
from apps.api.models import Principal
from apps.api.workflow_snapshot import WorkflowInputService,WorkflowInputSnapshot
from apps.api.workflow_offline_adapter import DeterministicWorkflowAdapter
from apps.api.workflow_discovery import WorkflowDiscoveryEngine
from scripts.validation.evaluation_fixtures import LiveEvidenceResolver
from scripts.validation.evaluation_metrics import Prediction,normal,proposed_gold,evaluate_case,summarize


class FixedContextBuilder:
    policy='all-frozen-active-documents-for-tenant-v1'
    def __init__(self,chunks,generation):
        self.chunks=chunks;self.generation=copy.deepcopy(generation);self.inputs=WorkflowInputService(chunks)
        docs=self.generation['documents']
        if (not docs or len({d['version_id'] for d in docs})!=len(docs) or
            digest([d['snapshot']['snapshot_id'] for d in docs])!=generation['generation_id']):
            raise DomainError('invalid_fixed_generation',422)
        self.resolver=LiveEvidenceResolver(chunks,self.generation)
    def build(self,organization_id):
        selected=[d for d in self.generation['documents'] if d['organization_id']==organization_id]
        if not selected:raise DomainError('fixed_context_scope_missing',404)
        manager=Principal('fixed-context-manager',organization_id,'manager');scopes=[];items=[]
        for doc in selected:
            snap=WorkflowInputSnapshot.model_validate_json(canonical(doc['snapshot']))
            self.inputs.validate(manager,snap,require_active=True)
            if [c.model_dump(mode='json') for c in snap.chunks]!=doc['chunks']:raise DomainError('fixed_context_manifest_mismatch',422)
            scopes.append({'document_id':doc['document_id'],'version_id':doc['version_id'],
                'snapshot_id':snap.snapshot_id,'original_sha256':snap.original_sha256,
                'parse_attempt_id':snap.parse_attempt_id,'chunk_job_id':snap.chunk_job_id,'chunk_generation':snap.chunk_generation,
                'chunk_ids':list(snap.input_chunk_ids)})
            items.extend(c.model_dump(mode='json') for c in snap.chunks)
        body={'policy':self.policy,'generation_id':self.generation['generation_id'],
            'organization_id':organization_id,'document_scopes':scopes,'chunks':items,
            'goldset_status':'PROVISIONAL','semantic_verification':'NOT_VERIFIED','administrator_approval':'NOT_REQUESTED'}
        return {**body,'context_id':digest(body)}
    def validate(self,organization_id,packet):
        if packet!=self.build(organization_id):raise DomainError('fixed_context_incomplete_or_forged',422)
        return packet
    def validate_prediction(self,packet,prediction):
        self.validate(packet['organization_id'],packet)
        p=Prediction.model_validate(prediction)
        allowed={canonical(c['evidence']) for c in packet['chunks']}
        for item in p.claims+[x for f in ('steps','deadlines','conditions','forms') for x in getattr(p.labels,f) or []]:
            if not item.evidence_refs:raise DomainError('fixed_prediction_missing_evidence',422)
            if not any(normal(item.text) in normal(span['quote']) for ref in item.evidence_refs for span in ref.get('spans',[]) if span['role']=='primary'):
                raise DomainError('fixed_prediction_unquoted_claim',422)
            for ref in item.evidence_refs:
                if canonical(ref) not in allowed:raise DomainError('fixed_prediction_evidence_outside_context',422)
                self.resolver(packet['organization_id'],ref)
        return p


class FakeFixedExtraction:
    test_only=True
    network_access=False
    model_id='deterministic-workflow-offline-fixed-context-v1'
    def __init__(self,builder):self.builder=builder;self.document_invocations=0
    def extract(self,packet):
        # No question, answer key, expected_refs or proposed gold is accepted by this interface.
        builder=self.builder;org=packet['organization_id'];builder.validate(org,packet)
        principal=Principal('fixed-context-manager',org,'manager');outputs=[];steps=[];seen={}
        for scope in packet['document_scopes']:
            doc=next(d for d in builder.generation['documents'] if d['version_id']==scope['version_id'])
            snapshot=WorkflowInputSnapshot.model_validate_json(canonical(doc['snapshot']))
            result=WorkflowDiscoveryEngine(builder.inputs,DeterministicWorkflowAdapter()).run(principal,snapshot)
            self.document_invocations+=1;outputs.append(result.model_dump(mode='json'))
            by_id={c.chunk_id:c.evidence.model_dump(mode='json') for c in snapshot.chunks}
            for w in result.extraction.workflows:
                for s in w.steps:
                    text=s.label.text;key=normal(text)
                    refs=[by_id[c.chunk_id] for c in s.label.evidence]
                    if key in seen:
                        target=steps[seen[key]]
                        for ref in refs:
                            if ref not in target['evidence_refs']:target['evidence_refs'].append(ref)
                    else:
                        seen[key]=len(steps);steps.append({'id':'fixed-'+digest([key])[:40],'text':text,'evidence_refs':refs})
        builder.validate(org,packet)
        return {'labels':{'steps':steps,'relations':None,'deadlines':None,'conditions':None,'forms':None},
            'document_outputs':outputs,'context_id':packet['context_id'],'goldset_status':'PROVISIONAL',
            'semantic_verification':'NOT_VERIFIED','administrator_approval':'NOT_REQUESTED','publishable':False,
            'limitation':'Rule-based document extraction, not a question-answering or semantic model; repeated tenant context reused.'}


def run_fixed_context(chunks,generation):
    import time
    builder=FixedContextBuilder(chunks,generation);fake=FakeFixedExtraction(builder);packets={};extracted={};records=[];predictions=[];cases=[];case_inputs=[]
    # Build context before accessing query answers; one tenant corpus independent of expected IDs.
    for org in sorted({d['organization_id'] for d in generation['documents']}):
        packet=builder.build(org);packets[org]=packet;started=time.perf_counter()
        value=fake.extract(packet);value['fake_document_extraction_seconds']=time.perf_counter()-started;extracted[org]=value
    for q in generation['queries']:
        org=q['organization_id'];packet=packets[org];value=extracted[org]
        case_inputs.append({'question_id':q['id'],'question':q['question'],'organization_id':org,
            'context_id':packet['context_id'],'instruction_version':'fixed-question-extraction-v1'})
        p={'id':q['id'],'status':'generated','labels':copy.deepcopy(value['labels']),'claims':[],
            'elapsed_seconds':0.0,'run_kind':'fake_model','token_basis':'NOT_MEASURED'}
        # Per-question scoring duration is separate from reused document extraction time.
        started=time.perf_counter();prediction=builder.validate_prediction(packet,p)
        records.append(evaluate_case(proposed_gold(q),prediction,builder.resolver));predictions.append(p)
        context_keys={c['chunk_id'] for c in packet['chunks']};expected={r['chunk_id'] for r in q['expected_evidence_refs']}
        if expected-context_keys:raise DomainError('fixed_context_missing_expected_evidence',422)
        cases.append({'id':q['id'],'organization_id':org,'context_id':packet['context_id'],
            'context_chunk_count':len(context_keys),'expected_chunk_count':len(expected),
            'expected_chunks_in_context':sorted(expected&context_keys),'missing_expected_chunks':sorted(expected-context_keys),
            'context_selected_from_gold':False,'retrieval_executed':False,'goldset_status':'PROVISIONAL',
            'scoring_seconds':time.perf_counter()-started,'semantic_accuracy':None})
    for org,p in packets.items():builder.validate(org,p)
    return {'context_packets':packets,'fake_extractions':extracted,'predictions':predictions,'cases':cases,
        'case_inputs':case_inputs,'metrics':summarize(records),'fake_document_invocations':fake.document_invocations,
        'question_count':len(cases),'actual_provider_calls':0,'actual_spend_usd':0,
        'scope':'offline fixed-context plumbing and provisional exact-label metric smoke; NOT LLM accuracy',
        'semantic_accuracy_pass':False,'goldset_status':'PROVISIONAL','administrator_approval':'NOT_REQUESTED','publishable':False}
