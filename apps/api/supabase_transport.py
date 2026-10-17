"""Bounded server-only Supabase Auth HTTP transport; no calls during construction."""
import base64
import json
import math
import re
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

import httpx

from .identity_provider import ProviderUnavailable


@dataclass(frozen=True)
class SupabaseSettings:
    project_url: str
    api_key: str = field(repr=False)
    timeout_seconds: float = 5.0

    def __post_init__(self):
        try:
            url = urlsplit(self.project_url)
            if (url.scheme != 'https' or url.username is not None or url.password is not None
                    or url.netloc != url.hostname or url.path not in ('', '/')
                    or url.query or url.fragment
                    or not re.fullmatch(r'[a-z0-9]{20}\.supabase\.co', url.hostname or '')
                    or self.project_url != 'https://' + url.hostname + url.path):
                raise ValueError()
            if (isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (int, float))
                    or not math.isfinite(self.timeout_seconds) or not .1 <= self.timeout_seconds <= 10):
                raise ValueError()
            key = self.api_key
            if not isinstance(key, str) or not 1 <= len(key) <= 4096:
                raise ValueError()
            if not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]{16,256}', key):
                # A legacy anon JWT is a gateway key, NOT a locally verified identity.
                if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', key):
                    raise ValueError()
                encoded = key.split('.')[1]
                claims = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
                if claims.get('role') != 'anon' or claims.get('ref') != url.hostname.split('.')[0]:
                    raise ValueError()
            object.__setattr__(self, 'project_url', self.project_url.rstrip('/'))
        except Exception:
            raise ValueError('invalid_supabase_settings') from None

    @property
    def issuer(self):
        return self.project_url + '/auth/v1'


class SupabaseHTTPTransport:
    """Only two fixed endpoints. No redirects, retries, cookies, body logs or token storage.

    Optional MockTransport injection exercises the same HTTP client without sockets.
    Real connections keep TLS verification and the environment's proxy/CA trust.
    """
    max_response_bytes = 65536

    def __init__(self, settings: SupabaseSettings, *, mock_transport: httpx.MockTransport | None = None):
        if not isinstance(settings, SupabaseSettings):
            raise ValueError('invalid_supabase_settings')
        if mock_transport is not None and not isinstance(mock_transport, httpx.MockTransport):
            raise ValueError('mock_http_transport_required')
        self.settings = settings
        self._mock_transport = mock_transport

    def request(self, method, path, *, headers=None, body=None):
        try:
            supplied = headers or {}
            if (method, path) == ('POST', '/auth/v1/token?grant_type=password'):
                if supplied or not isinstance(body, dict) or set(body) != {'email', 'password'}:
                    raise ProviderUnavailable()
                if (not isinstance(body['email'], str) or not 3 <= len(body['email']) <= 254
                        or not isinstance(body['password'], str) or not 1 <= len(body['password']) <= 1024):
                    raise ProviderUnavailable()
            elif (method, path) == ('GET', '/auth/v1/user'):
                if body is not None or set(supplied) != {'Authorization'}:
                    raise ProviderUnavailable()
                if not re.fullmatch(r'Bearer [\x21-\x7e]{1,8192}', supplied['Authorization']):
                    raise ProviderUnavailable()
            else:
                raise ProviderUnavailable()
            request_headers = {'apikey': self.settings.api_key, 'Accept': 'application/json',
                               'Accept-Encoding': 'identity', **supplied}
            # A fresh client discards provider Set-Cookie and closes every connection.
            with httpx.Client(verify=True, trust_env=True, follow_redirects=False,
                              timeout=httpx.Timeout(self.settings.timeout_seconds),
                              transport=self._mock_transport) as client:
                started = time.monotonic()
                with client.stream(method, self.settings.project_url + path,
                                   headers=request_headers, json=body) as response:
                    if response.status_code != 200:
                        return response.status_code, {}  # Never expose provider error bodies.
                    if response.headers.get('content-type', '').split(';')[0].strip().lower() != 'application/json':
                        raise ProviderUnavailable()
                    if response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        raise ProviderUnavailable()
                    data = bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        data.extend(chunk)
                        if len(data) > self.max_response_bytes or time.monotonic() - started > self.settings.timeout_seconds:
                            raise ProviderUnavailable()
                    payload = json.loads(data)
                    if not isinstance(payload, dict):
                        raise ProviderUnavailable()
                    return 200, payload
        except Exception:
            # Fixed error only: never propagate a URL, credential, response or exception repr.
            raise ProviderUnavailable() from None
