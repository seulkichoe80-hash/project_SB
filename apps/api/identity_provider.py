"""Offline identity contracts. This module deliberately has no HTTP client."""
from dataclasses import dataclass
from typing import Protocol, Callable

class ProviderUnavailable(Exception):
    pass

@dataclass(frozen=True)
class VerifiedIdentity:
    issuer: str
    subject: str
    ttl: int

class IdentityProviderAdapter(Protocol):
    available: bool
    def authenticate(self, email: str, password: str) -> VerifiedIdentity: ...

class UnconfiguredProvider:
    available = False
    def authenticate(self, email, password):
        raise ProviderUnavailable()

@dataclass
class MockSupabaseTransport:
    """Explicit test-only seam, never auto-created from environment values."""
    handler: Callable
    def request(self, method, path, *, headers=None, body=None):
        return self.handler(method, path, headers or {}, body)

class SupabaseProviderAdapter:
    available = True
    def __init__(self, transport: MockSupabaseTransport, issuer: str):
        if not isinstance(transport, MockSupabaseTransport) or not issuer.startswith('https://'):
            raise ValueError('offline_mock_transport_required')
        self.transport, self.issuer = transport, issuer.rstrip('/')

    def authenticate(self, email, password):
        try:
            status, payload = self.transport.request('POST', '/auth/v1/token?grant_type=password',
                body={'email': email, 'password': password})
            if status != 200 or not isinstance(payload.get('access_token'), str):
                raise ProviderUnavailable()
            # Identity is obtained from the provider's user verification endpoint,
            # never from client metadata, email domain, or a locally decoded JWT.
            status, user = self.transport.request('GET', '/auth/v1/user',
                headers={'Authorization': 'Bearer ' + payload['access_token']})
            subject, ttl = user.get('id'), payload.get('expires_in')
            if status != 200 or not isinstance(subject,str) or not 1 <= len(subject) <= 200:
                raise ProviderUnavailable()
            if isinstance(ttl,bool) or not isinstance(ttl,int) or not 60 <= ttl <= 3600:
                raise ProviderUnavailable()
            if user.get('is_anonymous') or user.get('banned_until'):
                raise ProviderUnavailable()
            return VerifiedIdentity(self.issuer, subject, ttl)
        except Exception:
            raise ProviderUnavailable() from None
