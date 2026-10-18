"""Fake-only provider boundary. No HTTP client, key lookup, DNS, SDK or real enable switch."""
from dataclasses import dataclass, field
import hashlib
import json
import re
import threading
import time
from typing import Callable, Literal, Protocol, TypeVar
from pydantic import BaseModel, ConfigDict, Field
from .errors import DomainError
from .provider_budget import Reservation, SimulationBudgetLedger


class SafetyModel(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True,frozen=True)


class ProviderSettings(SafetyModel):
    provider: Literal['openai','google']
    model: str = Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9][A-Za-z0-9._-]*$')
    real_calls_enabled: Literal[False] = False
    max_input_tokens: int = Field(default=16_000,ge=1,le=100_000)
    max_output_tokens: int = Field(default=4096,ge=0,le=32768)
    input_rate_micro: int = Field(default=100_000,ge=1,le=1_000_000_000)
    output_rate_micro: int = Field(default=500_000,ge=0,le=1_000_000_000)
    request_cap_micro: int = Field(default=50_000,ge=1,le=1_000_000_000)
    max_retries: int = Field(default=1,ge=0,le=1)
    timeout_seconds: float = Field(default=1.0,ge=.001,le=60)
    retry_delay_seconds: float = Field(default=.01,ge=0,le=.1)
    rate_version: str = Field(default='simulation-rates-v1',min_length=1,max_length=100)

    def endpoint(self, task):
        if task not in ('rag','workflow','embedding'):raise DomainError('invalid_provider_task',422)
        if self.provider=='openai':
            return 'https://api.openai.com'+('/v1/embeddings' if task=='embedding' else '/v1/responses')
        action = 'embedContent' if task=='embedding' else 'generateContent'
        return f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:{action}'

    def reservation(self):
        return Reservation(self.max_input_tokens,self.max_output_tokens,self.input_rate_micro,
                           self.output_rate_micro,self.max_retries+1,self.request_cap_micro)


class Usage(SafetyModel):
    input_tokens: int = Field(ge=0,le=100_000)
    output_tokens: int = Field(ge=0,le=32768)


class CompleteOutput(SafetyModel):
    status: Literal['complete']
    model: str
    output: dict | list
    usage: Usage


class ErrorUsage(SafetyModel):
    usage: Usage


class ApprovedSimulationInput(SafetyModel):
    institution_id: str = Field(min_length=1,max_length=200)
    payload_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    classification: Literal['synthetic','public']
    manifest_version: str = Field(min_length=1,max_length=100)


def encoded(value):
    return json.dumps(value,ensure_ascii=False,allow_nan=False,sort_keys=True,separators=(',',':')).encode()


def approved_simulation_input(principal, payload, *, classification='synthetic', manifest_version='synthetic-test-v1'):
    """Trusted test setup helper, not an upload declaration or real external-transfer approval."""
    return ApprovedSimulationInput(institution_id=principal.institution_id,
        payload_sha256=hashlib.sha256(encoded(payload)).hexdigest(),classification=classification,manifest_version=manifest_version)


def bounded_json(body):
    if type(body) is not bytes or len(body)>262_144:
        raise DomainError('provider_response_limit',422)
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate_key')
            result[key]=value
        return result
    def invalid(_):raise ValueError('nonfinite')
    try:return json.loads(body,object_pairs_hook=unique,parse_constant=invalid)
    except (ValueError,UnicodeError,RecursionError):raise DomainError('provider_invalid_json',422) from None


@dataclass(frozen=True)
class SimulationRequest:
    endpoint: str
    fingerprint: str
    payload: bytes = field(repr=False)
    follow_redirects: bool = False
    test_only: bool = True


class FakeResponse(SafetyModel):
    status: int = Field(default=200,ge=100,le=599)
    body: bytes = Field(default=b'',repr=False)
    delay_seconds: float = Field(default=0.0,ge=0,le=1)
    failure: Literal['none','connect','timeout'] = 'none'
    retry_after_seconds: float = Field(default=0.0,ge=0,le=.1)


class SimulationTransportError(Exception):
    def __init__(self, sent):
        self.sent=sent
        super().__init__('simulated_transport_failure')


class ProviderTransport(Protocol):
    def send(self, request: SimulationRequest, timeout: float) -> FakeResponse: ...


class BlockedTransport:
    def send(self, request, timeout):
        raise DomainError('real_provider_calls_disabled',503)


class FakeTransport:
    """In-memory scripted data only. No callbacks, redirects, sockets or arbitrary transports."""
    __slots__=('_responses','_index','_lock')
    def __init__(self, responses):
        values=tuple(responses)
        if not values or any(type(v) is not FakeResponse for v in values):
            raise DomainError('invalid_fake_transport',422)
        try:values=tuple(FakeResponse.model_validate(v.model_dump(warnings=False)) for v in values)
        except Exception:raise DomainError('invalid_fake_transport',422) from None
        self._responses,self._index,self._lock=values,0,threading.Lock()

    @property
    def calls(self):
        with self._lock:return self._index

    def send(self, request, timeout):
        with self._lock:
            if self._index>=len(self._responses):raise SimulationTransportError(False)
            result=self._responses[self._index];self._index+=1
        if result.failure=='connect':raise SimulationTransportError(False)
        wait=min(result.delay_seconds,timeout)
        if wait:threading.Event().wait(wait)
        if result.failure=='timeout' or result.delay_seconds>timeout:raise SimulationTransportError(True)
        return result


@dataclass(frozen=True)
class SimulationReceipt:
    request_id: str
    simulated_spent_micro: int
    attempts: int
    test_only: bool = True
    actual_spent_micro: int = 0
    semantic_verification: str = 'NOT_VERIFIED'
    administrator_approval: str = 'NOT_REQUESTED'
    publishable: bool = False


T=TypeVar('T')


class ProviderSafetyGateway:
    def __init__(self, settings, ledger, transport=None):
        # Runtime allowlist is by exact concrete implementation, not a spoofable attribute.
        from .postgres import PostgresBudgetLedger
        if type(settings) is not ProviderSettings or type(ledger) not in (SimulationBudgetLedger, PostgresBudgetLedger):
            raise DomainError('invalid_provider_safety_configuration',422)
        try:settings=ProviderSettings.model_validate(settings.model_dump(warnings=False))
        except Exception:raise DomainError('invalid_provider_safety_configuration',422) from None
        if type(transport) is not FakeTransport:
            raise DomainError('real_provider_calls_disabled',503)
        if settings.timeout_seconds>=ledger.ttl:
            raise DomainError('provider_timeout_exceeds_budget_lease',422)
        self.settings,self.ledger,self.transport=settings,ledger,transport

    def invoke(self, principal, job, request_id, task, payload, approval, validate:Callable[[object],T]):
        if type(self.transport) is not FakeTransport or type(self.settings) is not ProviderSettings:
            raise DomainError('real_provider_calls_disabled',503)
        try:settings=ProviderSettings.model_validate(self.settings.model_dump(warnings=False))
        except Exception:raise DomainError('invalid_provider_safety_configuration',422) from None
        if settings.timeout_seconds>=self.ledger.ttl:
            raise DomainError('provider_timeout_exceeds_budget_lease',422)
        transport=self.transport
        self.ledger.institution(principal)
        if type(approval) is not ApprovedSimulationInput or approval.institution_id!=principal.institution_id:
            raise DomainError('provider_input_scope_denied',403)
        try:approval=ApprovedSimulationInput.model_validate(approval.model_dump(warnings=False))
        except Exception:raise DomainError('invalid_provider_input_approval',422) from None
        try:raw=encoded(payload)
        except (TypeError,ValueError,RecursionError):raise DomainError('invalid_provider_input',422) from None
        if hashlib.sha256(raw).hexdigest()!=approval.payload_sha256:
            raise DomainError('provider_input_manifest_mismatch',422)
        # Conservative UTF-8 byte counter for this fake-only harness, NOT a production tokenizer.
        if len(raw)>settings.max_input_tokens:
            raise DomainError('provider_input_token_limit',413)
        endpoint=settings.endpoint(task)
        reservation=settings.reservation()
        fingerprint=hashlib.sha256(encoded({'task':task,'payload_hash':approval.payload_sha256,
            'manifest':approval.model_dump(),'settings':settings.model_dump()})).hexdigest()
        claim=self.ledger.reserve(principal,job,request_id,fingerprint,reservation)
        if claim is None:raise DomainError('provider_request_already_handled',409)
        wire=SimulationRequest(endpoint,fingerprint,raw)
        for index in range(settings.max_retries+1):
            attempt=self.ledger.start(principal,claim)
            try:response=transport.send(wire,settings.timeout_seconds)
            except SimulationTransportError as e:
                if e.sent:self.ledger.unknown(principal,claim)
                else:
                    self.ledger.record(principal,claim,attempt,0,0,hashlib.sha256(b'local-connect-failure').hexdigest())
                    self.ledger.finish(principal,claim,'failed')
                raise DomainError('provider_timeout_unknown_charge' if e.sent else 'provider_not_sent',503) from None
            # No raw response/error text is surfaced. Unknown usage is held, never assumed free.
            try:
                data=bounded_json(response.body)
                if response.status==200:
                    envelope=CompleteOutput.model_validate(data)
                    if envelope.model!=settings.model:raise ValueError('model_mismatch')
                    usage=envelope.usage
                else:usage=ErrorUsage.model_validate(data).usage
                if usage.input_tokens>settings.max_input_tokens or usage.output_tokens>settings.max_output_tokens:
                    raise ValueError('usage_limit')
            except Exception:
                self.ledger.unknown(principal,claim)
                raise DomainError('provider_invalid_response_unknown_charge',422) from None
            try:self.ledger.record(principal,claim,attempt,usage.input_tokens,usage.output_tokens,hashlib.sha256(response.body).hexdigest())
            except DomainError:
                self.ledger.unknown(principal,claim)
                raise DomainError('provider_budget_settlement_blocked',409) from None
            if response.status!=200:
                if response.status in (429,503) and index<settings.max_retries:
                    delay=max(settings.retry_delay_seconds,response.retry_after_seconds)
                    if delay:threading.Event().wait(delay)
                    continue
                self.ledger.finish(principal,claim,'failed')
                raise DomainError('provider_redirect_blocked' if 300<=response.status<400 else 'provider_http_failure',503)
            try:value=validate(envelope.output)
            except Exception:
                self.ledger.finish(principal,claim,'rejected')
                raise DomainError('provider_output_rejected',422) from None
            self.ledger.finish(principal,claim,'completed')
            row=self.ledger.request(principal,request_id)
            return value,SimulationReceipt(request_id,row['spent'],row['attempts'])
        raise DomainError('provider_attempt_limit',503)  # Exhaustive loop, no implicit fallback.
