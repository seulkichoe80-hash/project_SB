"""Mock-only Supabase immutable object HTTP protocol; no production activation.

Only cached official upload/download contracts are implemented. Inventory and
remote ACL inspection deliberately fail closed until their contracts are verified.
Authorization is performed by PrivateOriginalStore, never by the server key.
"""
import hashlib
import hmac
import re
import time

import httpx
from pydantic import SecretStr

from .errors import DomainError
from .formats import MAX_BYTES
from .private_storage import (PrivateStorageSettings, ObjectData, ObjectMissing,
                              StorageUnavailable)


class StorageHTTPFailure(StorageUnavailable):
    """Fixed diagnostic codes only; never retains a response, request or cause."""
    def __init__(self, code, *, retryable=False, ambiguous=False, retry_after=None):
        super().__init__(code)
        self.code = code
        self.retryable = retryable
        self.ambiguous = ambiguous
        self.retry_after = retry_after


class StorageHTTPTransport:
    """Server-only protocol adapter, requiring an exact httpx.MockTransport.

    No automatic POST retries. A later intent retry must probe first (the store
    already enforces three attempts). HTTP status/body never establishes integrity.
    """
    __slots__ = ('_settings', '_gateway_key', '_mock')

    def __init__(self, settings, *, gateway_key, transport):
        self._settings = settings
        self._gateway_key = gateway_key
        self._mock = transport
        self._validate()

    def __repr__(self):
        return '<StorageHTTPTransport mock-only redacted>'

    @property
    def private(self):
        # Configuration assertion, NOT remote bucket ACL certification.
        return self._settings.private

    def _validate(self):
        if type(self) is not StorageHTTPTransport or type(self._mock) is not httpx.MockTransport:
            raise StorageHTTPFailure('real_storage_transport_disabled')
        self._validate_settings()

    def _validate_settings(self):
        try:
            if type(self._settings) is not PrivateStorageSettings or type(self._gateway_key) is not SecretStr:
                raise ValueError()
            s = PrivateStorageSettings.model_validate(self._settings.model_dump(warnings=False))
            if not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co', s.project_url.get_secret_value()):
                raise ValueError()
            for value in (s.server_key.get_secret_value(), self._gateway_key.get_secret_value()):
                if not re.fullmatch(r'[\x21-\x7e]{16,4096}', value):
                    raise ValueError()
            if s.server_key.get_secret_value().startswith(('sb_publishable_', 'sb_secret_')):
                # Cached docs establish a server bearer service key; modern
                # secret-key exchange semantics have not been verified here.
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise StorageHTTPFailure('invalid_storage_http_configuration') from None

    def matches(self, settings):
        self._validate()
        return (type(settings) is PrivateStorageSettings
                and self._settings == settings)

    def _scope(self, bucket, path):
        self._validate()
        if (type(bucket) is not str or bucket != self._settings.bucket or type(path) is not str
                or not re.fullmatch(r'institutions/[0-9a-f]{64}/originals/[0-9a-f]{32}', path)):
            raise StorageHTTPFailure('invalid_storage_http_scope')

    @staticmethod
    def _retry_after(value):
        # Dates/invalid headers are not interpreted as executable instructions.
        if value and re.fullmatch(r'[0-9]{1,5}', value):
            return min(int(value), 3600)
        return None

    def _before_request(self):
        self._validate()

    def _trust_env(self):
        return False

    def _request(self, method, bucket, path, body=None):
        self._scope(bucket, path)
        if method not in ('GET', 'POST'):
            raise StorageHTTPFailure('storage_http_method_forbidden')
        segment = 'object/' if method == 'POST' else 'object/authenticated/'
        url = self._settings.project_url.get_secret_value() + '/storage/v1/' + segment + bucket + '/' + path
        headers = {'Authorization': 'Bearer ' + self._settings.server_key.get_secret_value(),
                   'apikey': self._gateway_key.get_secret_value(), 'Accept-Encoding': 'identity'}
        if method == 'POST':
            headers.update({'Content-Type': 'application/octet-stream', 'x-upsert': 'false'})
        self._before_request()
        started = time.monotonic()
        timeout = self._settings.timeout_seconds
        result = None
        try:
            # New isolated client per operation: no cookie jar, proxy, credential
            # discovery, redirect, event hooks or real-network fallback.
            with httpx.Client(transport=self._mock, trust_env=self._trust_env(), follow_redirects=False,
                              timeout=httpx.Timeout(timeout)) as client:
                with client.stream(method, url, headers=headers, content=body) as response:
                    status = response.status_code
                    retry_after = self._retry_after(response.headers.get('retry-after'))
                    if time.monotonic() - started > timeout:
                        result = StorageHTTPFailure('storage_http_timeout', retryable=True, ambiguous=method == 'POST')
                    elif 300 <= status < 400:
                        result = StorageHTTPFailure('storage_redirect_blocked', ambiguous=method == 'POST')
                    elif method == 'GET' and status == 404:
                        result = ObjectMissing()
                    elif not 200 <= status < 300:
                        result = StorageHTTPFailure('storage_http_' + str(status),
                            retryable=status in (408, 429, 500, 502, 503, 504),
                            ambiguous=method == 'POST', retry_after=retry_after)
                    elif method == 'POST':
                        # Provider JSON is intentionally not parsed/assumed. The
                        # authenticated GET below is the only success criterion.
                        return None
                    elif status != 200 or response.headers.get('content-encoding', 'identity').lower() != 'identity':
                        result = StorageHTTPFailure('invalid_storage_download')
                    else:
                        length = response.headers.get('content-length')
                        if length is not None and (not re.fullmatch(r'[0-9]{1,10}', length) or not 0 < int(length) <= MAX_BYTES):
                            result = StorageHTTPFailure('invalid_storage_download_length')
                        else:
                            data = bytearray()
                            for part in response.iter_bytes(chunk_size=65536):
                                if time.monotonic() - started > timeout:
                                    result = StorageHTTPFailure('storage_http_timeout', retryable=True)
                                    break
                                if len(data) + len(part) > MAX_BYTES:
                                    result = StorageHTTPFailure('storage_download_size_limit')
                                    break
                                data.extend(part)
                            if result is None:
                                if not data or (length is not None and len(data) != int(length)):
                                    result = StorageHTTPFailure('invalid_storage_download_length')
                                else:
                                    value = bytes(data)
                                    return ObjectData(value, len(value), hashlib.sha256(value).hexdigest())
        except httpx.TimeoutException:
            result = StorageHTTPFailure('storage_http_timeout', retryable=True, ambiguous=method == 'POST')
        except httpx.TransportError:
            result = StorageHTTPFailure('storage_http_network_failure', retryable=True, ambiguous=method == 'POST')
        except Exception:
            result = StorageHTTPFailure('storage_http_invalid_response', ambiguous=method == 'POST')
        # Raised outside except: no secret-bearing HTTP exception context.
        raise result

    def get(self, bucket, path):
        return self._request('GET', bucket, path)

    @staticmethod
    def _verify(value, data):
        if value.size != len(data) or not hmac.compare_digest(value.sha256, hashlib.sha256(data).hexdigest()):
            raise DomainError('original_integrity_failure', 409)

    def put_if_absent(self, bucket, path, data):
        self._scope(bucket, path)
        if type(data) is not bytes or not 0 < len(data) <= MAX_BYTES:
            raise StorageHTTPFailure('storage_upload_size_limit')
        # Required even when used without the store: retry never blindly POSTs.
        try:
            previous = self.get(bucket, path)
        except ObjectMissing:
            pass
        else:
            self._verify(previous, data)
            return
        failure = None
        try:
            self._request('POST', bucket, path, data)
        except StorageHTTPFailure as error:
            failure = error
            if error.code in ('storage_redirect_blocked', 'storage_http_401', 'storage_http_403'):
                raise
        # Even timeout, duplicate 400, 429/5xx or malformed success must be
        # reconciled using immutable bytes, never provider JSON/error strings.
        try:
            self._verify(self.get(bucket, path), data)
        except StorageHTTPFailure as error:
            raise StorageHTTPFailure(error.code, retryable=error.retryable, ambiguous=True,
                                     retry_after=error.retry_after) from None
        except ObjectMissing:
            if failure is not None:
                raise failure from None
            raise StorageHTTPFailure('storage_upload_unconfirmed', retryable=True, ambiguous=True) from None

    def list_page(self, bucket, prefix, offset, limit):
        self._validate()
        raise StorageHTTPFailure('storage_inventory_contract_unverified')


class SupabaseStorageHTTPTransport(StorageHTTPTransport):
    """Same immutable verified protocol; optional live I/O requires explicit policy.

    Production factory remains blocked. Mock injection exercises identical HTTP
    bytes without network approval. Inventory/ACL/backup are still unimplemented.
    """
    __slots__=('policy',)
    def __init__(self,settings,*,gateway_key,policy,mock_transport=None):
        from .provider_http import validated_policy
        self.policy=validated_policy(policy,settings.project_url.get_secret_value(),'storage',mock_transport)
        super().__init__(settings,gateway_key=gateway_key,transport=mock_transport)
    def _validate(self):
        from .provider_http import validated_policy
        if type(self) is not SupabaseStorageHTTPTransport:raise StorageHTTPFailure('invalid_storage_http_transport')
        self._validate_settings()
        try:validated_policy(self.policy,self._settings.project_url.get_secret_value(),'storage',self._mock)
        except Exception:raise StorageHTTPFailure('invalid_storage_network_policy') from None
    @property
    def network_selected(self):
        self._validate()
        return self._mock is None and self.policy.enabled and bool(self.policy.approval_ref)
    def _before_request(self):
        self._validate()
        try:self.policy.authorize(self._settings.project_url.get_secret_value(),'storage',self._mock)
        except Exception:raise StorageHTTPFailure('external_storage_calls_not_approved') from None
    def _trust_env(self):return True
    def __repr__(self):return '<SupabaseStorageHTTPTransport redacted gated>'
