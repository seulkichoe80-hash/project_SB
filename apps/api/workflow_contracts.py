"""Versioned extraction contracts, independent of RAG Generation and provider SDKs."""
import json
from typing import Annotated, Literal, Protocol, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

if TYPE_CHECKING:
    from .workflow_snapshot import WorkflowInputSnapshot

MAX_OUTPUT_BYTES = 262144
MAX_NODES = 1000
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]*$')]
Text = Annotated[str, StringConstraints(min_length=1, max_length=4000, pattern=r'\S')]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)


class EvidenceCitation(StrictModel):
    chunk_id: Identifier
    block_id: Identifier
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    quote: Text

    @model_validator(mode='after')
    def bounds(self):
        if self.end <= self.start or self.end - self.start != len(self.quote):
            raise ValueError('invalid_citation_range')
        return self


class GroundedAssertion(StrictModel):
    text: Text
    evidence: list[EvidenceCitation] = Field(min_length=1, max_length=20)

    @model_validator(mode='after')
    def unique_citations(self):
        keys = [e.model_dump_json() for e in self.evidence]
        if len(keys) != len(set(keys)):
            raise ValueError('duplicate_citation')
        return self


class Step(StrictModel):
    id: Identifier
    label: GroundedAssertion
    actions: list[GroundedAssertion] = Field(min_length=1, max_length=50)
    deadline: GroundedAssertion | None  # Required null means unconfirmed, not no deadline.
    obligations: list[GroundedAssertion] = Field(max_length=50)


class Condition(StrictModel):
    id: Identifier
    statement: GroundedAssertion
    step_ids: list[Identifier] = Field(min_length=1, max_length=200)


class Edge(StrictModel):
    id: Identifier
    source: Identifier
    target: Identifier
    relation: Literal['precedes', 'conditional', 'requires']
    condition_ids: list[Identifier] = Field(max_length=50)
    explanation: GroundedAssertion


class FormRequirement(StrictModel):
    id: Identifier
    title: GroundedAssertion
    requirement: GroundedAssertion
    step_ids: list[Identifier] = Field(min_length=1, max_length=200)


class ReviewIssue(StrictModel):
    id: Identifier
    target_ids: list[Identifier] = Field(max_length=200)
    code: Literal['insufficient_evidence', 'unclear_order', 'conflict', 'form_unresolved',
                  'partial_input', 'semantic_review_required', 'no_workflow_found']
    message: Text


class WorkflowCandidate(StrictModel):
    id: Identifier
    title: GroundedAssertion
    steps: list[Step] = Field(min_length=1, max_length=200)
    conditions: list[Condition] = Field(max_length=200)
    edges: list[Edge] = Field(max_length=400)
    form_requirements: list[FormRequirement] = Field(max_length=200)


def assertions(workflow):
    yield workflow.title
    for step in workflow.steps:
        yield step.label
        yield from step.actions
        yield from step.obligations
        if step.deadline is not None:
            yield step.deadline
    for condition in workflow.conditions:
        yield condition.statement
    for edge in workflow.edges:
        yield edge.explanation
    for form in workflow.form_requirements:
        yield form.title
        yield form.requirement


class WorkflowExtraction(StrictModel):
    schema_version: Literal['workflow-extraction-v1']
    workflows: list[WorkflowCandidate] = Field(max_length=20)
    issues: list[ReviewIssue] = Field(max_length=200)

    @model_validator(mode='after')
    def graph(self):
        all_ids = [node.id for w in self.workflows for node in
                   [w, *w.steps, *w.conditions, *w.edges, *w.form_requirements]]
        targets = set(all_ids)
        all_ids.extend(i.id for i in self.issues)
        if len(all_ids) != len(set(all_ids)):
            raise ValueError('duplicate_workflow_id')
        if len(all_ids) > MAX_NODES:
            raise ValueError('workflow_node_limit')
        for workflow in self.workflows:
            steps = {s.id for s in workflow.steps}
            conditions = {c.id: c for c in workflow.conditions}
            for item in [*workflow.conditions, *workflow.form_requirements]:
                if len(item.step_ids) != len(set(item.step_ids)) or not set(item.step_ids) <= steps:
                    raise ValueError('invalid_step_reference')
            for edge in workflow.edges:
                if edge.source not in steps or edge.target not in steps or edge.source == edge.target:
                    raise ValueError('invalid_edge_endpoint')
                if len(edge.condition_ids) != len(set(edge.condition_ids)) or not set(edge.condition_ids) <= conditions.keys():
                    raise ValueError('invalid_condition_reference')
                if bool(edge.condition_ids) != (edge.relation == 'conditional'):
                    raise ValueError('invalid_conditional_edge')
                if any(edge.target not in conditions[c].step_ids for c in edge.condition_ids):
                    raise ValueError('condition_target_mismatch')
        for issue in self.issues:
            if len(issue.target_ids) != len(set(issue.target_ids)) or not set(issue.target_ids) <= targets:
                raise ValueError('invalid_issue_target')
        if not self.workflows and not self.issues:
            raise ValueError('empty_extraction_requires_issue')
        if len(self.model_dump_json().encode('utf-8')) > MAX_OUTPUT_BYTES:
            raise ValueError('workflow_output_limit')
        return self


def parse_extraction(payload: str | bytes | dict | WorkflowExtraction) -> WorkflowExtraction:
    """Bound raw UTF-8 before JSON parsing; reject duplicate keys and non-finite JSON."""
    if isinstance(payload, WorkflowExtraction):
        payload = payload.model_dump_json()
    if isinstance(payload, (str, bytes)):
        raw = payload.encode('utf-8') if isinstance(payload, str) else payload
        if len(raw) > MAX_OUTPUT_BYTES:
            raise ValueError('workflow_output_limit')
        def unique(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError('duplicate_json_key')
                result[key] = value
            return result
        def invalid_constant(value):
            raise ValueError('non_finite_json')
        payload = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid_constant)
    return WorkflowExtraction.model_validate(payload)


class WorkflowExtractionAdapter(Protocol):
    model_id: str
    test_only: bool
    def extract(self, snapshot: 'WorkflowInputSnapshot') -> WorkflowExtraction: ...


class WorkflowValidation(StrictModel):
    structural_validation: Literal['PASS'] = 'PASS'
    evidence_link_validation: Literal['PASS'] = 'PASS'
    semantic_verification: Literal['NOT_VERIFIED'] = 'NOT_VERIFIED'
    semantic_review_required: Literal[True] = True
    administrator_approval: Literal['NOT_REQUESTED'] = 'NOT_REQUESTED'
    publishable: Literal[False] = False
