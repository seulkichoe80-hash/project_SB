"""Offline schema/evidence contract. Does not call models or prove semantic entailment."""
from pydantic import BaseModel,ConfigDict,Field
from typing import Literal
from pathlib import Path
import json,re,unicodedata

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)

class Evidence(StrictModel):
    tenant_id:str
    document_id:str
    version_id:str
    element_id:str
    quote:str=Field(min_length=1)

class Assertion(StrictModel):
    text:str=Field(min_length=1)
    evidence:list[Evidence]=Field(min_length=1)

class Step(StrictModel):
    id:str=Field(min_length=1)
    label:Assertion
    actions:list[Assertion]=Field(min_length=1)
    deadline:Assertion|None
    required_documents:list[Assertion]

class Edge(StrictModel):
    id:str
    source:str
    target:str
    relation:Literal['precedes','conditional','requires']
    explanation:Assertion

class Workflow(StrictModel):
    workflow_id:str
    title:Assertion
    steps:list[Step]=Field(min_length=1)
    edges:list[Edge]
    unresolved_issues:list[str]

def normalize(s):return ' '.join(unicodedata.normalize('NFC',s).split())

def verify(payload,registry,tenant_id,active_versions):
    model=Workflow.model_validate(payload)
    ids=[s.id for s in model.steps]
    if len(ids)!=len(set(ids)):raise ValueError('duplicate step id')
    if len({e.id for e in model.edges})!=len(model.edges):raise ValueError('duplicate edge id')
    for e in model.edges:
        if e.source not in ids or e.target not in ids or e.source==e.target:raise ValueError('invalid graph endpoint')
    claims=[model.title]
    for s in model.steps:
        claims.extend([s.label,*s.actions,*s.required_documents])
        if s.deadline is not None:claims.append(s.deadline)
    claims.extend(e.explanation for e in model.edges)
    resolved=[]
    for claim in claims:
        references=[]
        for e in claim.evidence:
            key=(e.document_id,e.version_id,e.element_id)
            source=registry.get(key)
            if not source or e.tenant_id!=tenant_id or source['tenant_id']!=tenant_id:raise ValueError('unknown or foreign evidence')
            if key[:2] not in active_versions:raise ValueError('inactive evidence')
            if source.get('source_kind')!='original_text':raise ValueError('this bootstrap validator requires original text; OCR/image paths need separate validation')
            if normalize(e.quote) not in normalize(source['text']):raise ValueError('quote does not resolve')
            if not source.get('location'):raise ValueError('missing source location')
            references.append({'document_id':e.document_id,'version_id':e.version_id,'element_id':e.element_id,'location':source['location'],'quote':e.quote})
        resolved.append({'text':claim.text,'evidence':references,'status':'candidate','semantic_review_required':True})
    for step in model.steps:
        if step.deadline:
            # An additional conservative lexical gate, never a semantic proof.
            atoms=re.findall(r'\d+\s*(?:일|월|년|시간|분)',step.deadline.text)
            quotes=' '.join(e.quote for e in step.deadline.evidence)
            if any(normalize(x) not in normalize(quotes) for x in atoms):raise ValueError('unsupported numeric deadline')
    return {'status':'candidate','claims':resolved,'semantic_validation':'NOT_RUN','model_extraction':'NOT_RUN'}

if __name__=='__main__':
    root=Path(__file__).resolve().parents[2]
    (root/'schemas/workflow.schema.json').write_text(json.dumps(Workflow.model_json_schema(),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Exported local JSON Schema; no API called.')
