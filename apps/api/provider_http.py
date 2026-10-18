"""Server-only provider network capability. Construction never contacts providers."""
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from typing import Literal
import httpx
import re
import time
from .identity_provider import ProviderUnavailable
from .supabase_transport import SupabaseHTTPTransport, SupabaseSettings


class ProviderNetworkPolicy(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='forbid',hide_input_in_errors=True)
    project_url: SecretStr=Field(repr=False)
    service: Literal['auth','storage']
    enabled: bool=False
    approval_ref: str | None=Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,80}$',repr=False)

    def validate_for(self,project,service,mock):
        if type(self) is not ProviderNetworkPolicy:raise ProviderUnavailable()
        try:
            p=ProviderNetworkPolicy.model_validate(self.model_dump(warnings=False))
            if (p.project_url.get_secret_value()!=project or p.service!=service
                    or not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co',project)
                    or (mock is not None and type(mock) is not httpx.MockTransport)):
                raise ValueError()
        except (ValueError,TypeError,AttributeError):raise ProviderUnavailable() from None
        return p

    def authorize(self,project,service,mock):
        p=self.validate_for(project,service,mock)
        if mock is None and (not p.enabled or not p.approval_ref):raise ProviderUnavailable()


def validated_policy(policy,project,service,mock):
    if type(policy) is not ProviderNetworkPolicy:raise ProviderUnavailable()
    return policy.validate_for(project,service,mock)


class SupabaseAuthHTTPTransport(SupabaseHTTPTransport):
    """Existing official password/user API, with a separate opt-in network policy."""
    def __init__(self,settings,*,policy,mock_transport=None):
        if type(self) is not SupabaseAuthHTTPTransport or type(settings) is not SupabaseSettings:
            raise ProviderUnavailable()
        super().__init__(settings,mock_transport=mock_transport)
        self.policy=validated_policy(policy,settings.project_url,'auth',mock_transport)
    @property
    def network_selected(self):
        validated_policy(self.policy,self.settings.project_url,'auth',self._mock_transport)
        return self._mock_transport is None and self.policy.enabled and bool(self.policy.approval_ref)
    @property
    def can_request(self):
        return type(self._mock_transport) is httpx.MockTransport or self.network_selected
    def request(self,method,path,*,headers=None,body=None):
        if type(self) is not SupabaseAuthHTTPTransport:raise ProviderUnavailable()
        SupabaseSettings(self.settings.project_url,self.settings.api_key,self.settings.timeout_seconds)
        validated_policy(self.policy,self.settings.project_url,'auth',self._mock_transport).authorize(self.settings.project_url,'auth',self._mock_transport)
        return super().request(method,path,headers=headers,body=body)
    def __repr__(self):return '<SupabaseAuthHTTPTransport redacted gated>'


class SupabaseJWKSTransport:
    """Fixed issuer JWKS route, bounded fresh snapshot, no token-selected URL/cache."""
    def __init__(self,settings,*,policy,mock_transport=None):
        if type(self) is not SupabaseJWKSTransport or type(settings) is not SupabaseSettings:raise ProviderUnavailable()
        self.settings=settings;self.issuer=settings.issuer;self._mock=mock_transport
        self.policy=validated_policy(policy,settings.project_url,'auth',mock_transport)
    def __repr__(self):return '<SupabaseJWKSTransport redacted gated>'
    @property
    def network_selected(self):
        validated_policy(self.policy,self.settings.project_url,'auth',self._mock)
        return self._mock is None and self.policy.enabled and bool(self.policy.approval_ref)
    def request(self,issuer,path):
        failed=False
        try:
            if type(self) is not SupabaseJWKSTransport or issuer!=self.issuer or path!='/auth/v1/.well-known/jwks.json':raise ValueError()
            SupabaseSettings(self.settings.project_url,self.settings.api_key,self.settings.timeout_seconds)
            validated_policy(self.policy,self.settings.project_url,'auth',self._mock).authorize(self.settings.project_url,'auth',self._mock)
            started=time.monotonic()
            with httpx.Client(transport=self._mock,trust_env=True,verify=True,follow_redirects=False,
                              timeout=httpx.Timeout(self.settings.timeout_seconds)) as client:
                with client.stream('GET',self.settings.project_url+path,headers={'Accept':'application/json','Accept-Encoding':'identity'}) as response:
                    if response.status_code!=200:return response.status_code,b''
                    if (response.headers.get('content-type','').split(';')[0].strip().lower()!='application/json'
                            or response.headers.get('content-encoding','identity').lower()!='identity'):raise ValueError()
                    raw=bytearray()
                    for chunk in response.iter_bytes(chunk_size=4096):
                        if len(raw)+len(chunk)>65536 or time.monotonic()-started>self.settings.timeout_seconds:raise ValueError()
                        raw.extend(chunk)
                    if not raw or time.monotonic()-started>self.settings.timeout_seconds:raise ValueError()
                    return 200,bytes(raw)
        except Exception:failed=True
        if failed:raise ProviderUnavailable()
