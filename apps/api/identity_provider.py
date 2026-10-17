"""Provider identity contracts; application permissions always come from local membership."""
from dataclasses import dataclass
from typing import Protocol, Callable
import math
import re
import time
from uuid import UUID

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
    def __init__(self, transport, issuer: str, *, clock=time.time):
        from .supabase_transport import SupabaseHTTPTransport
        if not isinstance(transport, (MockSupabaseTransport, SupabaseHTTPTransport)) or not issuer.startswith('https://'):
            raise ValueError('invalid_identity_transport')
        self.remote_enabled = isinstance(transport, SupabaseHTTPTransport)
        if self.remote_enabled and issuer != transport.settings.issuer:
            raise ValueError('identity_issuer_mismatch')
        self.clock = clock
        self.transport, self.issuer = transport, issuer.rstrip('/')

    def authenticate(self, email, password):
        try:
            started = time.monotonic()
            status, payload = self.transport.request('POST', '/auth/v1/token?grant_type=password',
                body={'email': email, 'password': password})
            if (status != 200 or not isinstance(payload, dict)
                    or not isinstance(payload.get('access_token'), str)
                    or not re.fullmatch(r'[\x21-\x7e]{1,8192}', payload['access_token'])):
                raise ProviderUnavailable()
            ttl = payload.get('expires_in')
            if isinstance(ttl, bool) or not isinstance(ttl, int) or not 60 <= ttl <= (86400 if self.remote_enabled else 3600):
                raise ProviderUnavailable()
            if self.remote_enabled and payload.get('token_type') != 'bearer':
                raise ProviderUnavailable()
            # Identity is obtained from the provider's user verification endpoint,
            # never from client metadata, email domain, or a locally decoded JWT.
            status, user = self.transport.request('GET', '/auth/v1/user',
                headers={'Authorization': 'Bearer ' + payload['access_token']})
            if status != 200 or not isinstance(user, dict):
                raise ProviderUnavailable()
            subject = user.get('id')
            if not isinstance(subject, str) or not 1 <= len(subject) <= 200:
                raise ProviderUnavailable()
            if user.get('is_anonymous') or user.get('banned_until') or user.get('deleted_at'):
                raise ProviderUnavailable()
            if self.remote_enabled:
                # GET /user verifies signature/expiry/project at Supabase. Never decode the
                # bearer token into an identity or accept token-response metadata as authority.
                if str(UUID(subject)) != subject or user.get('aud') != 'authenticated':
                    raise ProviderUnavailable()
                token_user = payload.get('user')
                if not isinstance(token_user, dict) or token_user.get('id') != subject:
                    raise ProviderUnavailable()
                ttl = min(ttl - math.ceil(time.monotonic() - started), 3600)
                if 'expires_at' in payload:
                    expires = payload['expires_at']
                    if isinstance(expires, bool) or not isinstance(expires, int):
                        raise ProviderUnavailable()
                    ttl = min(ttl, math.floor(expires - self.clock()))
                if ttl <= 0:
                    raise ProviderUnavailable()
            return VerifiedIdentity(self.issuer, subject, ttl)
        except Exception:
            raise ProviderUnavailable() from None
