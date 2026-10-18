"""Fake-only provider status revalidation; no JWT storage or external account API."""
from dataclasses import dataclass
import threading
from .identity_provider import ProviderUnavailable


class FakeIdentityStatusTransport:
    def __init__(self,states):
        self._lock=threading.RLock();self._states=dict(states);self.unavailable=False;self.calls=[]
    def __repr__(self):return '<FakeIdentityStatusTransport offline redacted>'
    def set(self,issuer,subject,state):
        if state not in ('active','disabled','deleted'):raise ValueError('invalid_fake_identity_state')
        with self._lock:self._states[issuer,subject]=state
    def status(self,issuer,subject):
        with self._lock:
            self.calls.append('status')
            if self.unavailable:raise ProviderUnavailable()
            state=self._states.get((issuer,subject))
            if state not in ('active','disabled','deleted'):raise ProviderUnavailable()
            return state


@dataclass(frozen=True,repr=False)
class SessionRevalidation:
    transport: FakeIdentityStatusTransport
    max_seconds: int=1800
    def __post_init__(self):
        if type(self.transport) is not FakeIdentityStatusTransport or type(self.max_seconds) is not int or not 60<=self.max_seconds<=1800:
            raise ValueError('offline_session_revalidation_required')
    def status(self,issuer,subject):
        if type(self.transport) is not FakeIdentityStatusTransport:raise ProviderUnavailable()
        return self.transport.status(issuer,subject)
