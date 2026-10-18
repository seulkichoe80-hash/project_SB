"""Bounded JOSE parsing + cryptography signature checks. Only offline Fake transports are wired."""
import base64
import copy
from dataclasses import dataclass,field
import hashlib
import hmac
import json
import math
import re
import threading
import time
from typing import Literal,Protocol
from uuid import UUID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec,rsa,padding,utils
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .identity_provider import VerifiedIdentity,ProviderUnavailable


class JWTSettings(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='forbid',hide_input_in_errors=True)
    issuer: str=Field(pattern=r'^https://[a-z0-9]{20}\.supabase\.co/auth/v1$',repr=False)
    audience: Literal['authenticated']='authenticated'
    algorithms: tuple[Literal['ES256','RS256'],...]=('ES256','RS256')
    max_lifetime: int=Field(default=3600,ge=60,le=3600)
    @model_validator(mode='after')
    def validate_policy(self):
        if not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co/auth/v1',self.issuer) or not self.algorithms or len(set(self.algorithms))!=len(self.algorithms):raise ValueError('invalid_algorithm_policy')
        return self


def _json(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('duplicate_json_key')
            result[k]=v
        return result
    return json.loads(raw,object_pairs_hook=unique,parse_constant=lambda _:(_ for _ in ()).throw(ValueError('invalid_number')))


def _decode(value,limit):
    if type(value) is not str or not re.fullmatch('[A-Za-z0-9_-]+',value) or len(value)>limit*2:raise ValueError('invalid_base64url')
    raw=base64.urlsafe_b64decode(value+'='*((-len(value))%4))
    if len(raw)>limit or base64.urlsafe_b64encode(raw).rstrip(b'=').decode()!=value:raise ValueError('invalid_base64url')
    return raw


class JWKSTransport(Protocol):
    def request(self,issuer: str,path: str) -> tuple[int,bytes]: ...


class FakeJWKSTransport:
    """No callbacks, DNS, sockets, URLs from JWT headers or persisted public-key cache."""
    def __init__(self,issuer,payload,*,faults=()):
        self.issuer=issuer;self._lock=threading.RLock();self.calls=[]
        if any(type(f) is not str or f not in ('timeout','503','429','redirect','invalid_json','oversize') for f in faults):raise ValueError('invalid_fake_jwks_fault')
        self.faults=list(faults);self.replace(payload)
    def __repr__(self):return '<FakeJWKSTransport offline redacted>'
    def replace(self,payload):
        raw=payload if type(payload) is bytes else json.dumps(payload,allow_nan=False).encode()
        with self._lock:self._payload=raw
    def request(self,issuer,path):
        with self._lock:
            self.calls.append('jwks')
            if issuer!=self.issuer or path!='/auth/v1/.well-known/jwks.json':raise ProviderUnavailable()
            fault=self.faults.pop(0) if self.faults else None
            if fault=='timeout':raise ProviderUnavailable()
            if fault in ('503','429'):return int(fault),b'{}'
            if fault=='redirect':return 302,b'{}'
            if fault=='invalid_json':return 200,b'not-json'
            if fault=='oversize':return 200,b'x'*65537
            return 200,self._payload


@dataclass(frozen=True,repr=False)
class FakeCredential:
    email: str=field(repr=False)
    password: str=field(repr=False)
    payload: dict=field(repr=False)


class FakeTokenTransport:
    def __init__(self,records,*,faults=()):
        if type(records) not in (tuple,list) or any(type(r) is not FakeCredential for r in records):raise ValueError('invalid_fake_credentials')
        if any(type(f) is not str or f not in ('timeout','503','429','redirect') for f in faults):raise ValueError('invalid_fake_token_fault')
        self._records={r.email:(hashlib.sha256(r.password.encode()).digest(),copy.deepcopy(r.payload)) for r in records}
        if len(self._records)!=len(records):raise ValueError('duplicate_fake_credentials')
        self.faults=list(faults);self.calls=[];self._lock=threading.Lock()
    def __repr__(self):return '<FakeTokenTransport offline redacted>'
    def request(self,method,path,*,body):
        with self._lock:
            self.calls.append('password_grant')
            if method!='POST' or path!='/auth/v1/token?grant_type=password' or set(body)!={'email','password'}:raise ProviderUnavailable()
            fault=self.faults.pop(0) if self.faults else None
            if fault=='timeout':raise ProviderUnavailable()
            if fault:return (302 if fault=='redirect' else int(fault)),{}
            row=self._records.get(body['email'])
            if not row or not hmac.compare_digest(row[0],hashlib.sha256(body['password'].encode()).digest()):return 400,{}
            return 200,copy.deepcopy(row[1])


class SupabaseJWTVerifier:
    def __init__(self,settings,transport,*,clock=time.time):
        if type(settings) is not JWTSettings or type(transport) is not FakeJWKSTransport:raise ValueError('offline_jwks_transport_required')
        settings=JWTSettings.model_validate(settings.model_dump())
        if transport.issuer!=settings.issuer:raise ValueError('jwks_issuer_mismatch')
        self.settings,self.transport,self.clock=settings,transport,clock
    def __repr__(self):return '<SupabaseJWTVerifier offline redacted>'
    def _keys(self):
        if type(self.transport) is not FakeJWKSTransport:raise ProviderUnavailable()
        status,raw=self.transport.request(self.settings.issuer,'/auth/v1/.well-known/jwks.json')
        if type(status) is not int or status!=200 or type(raw) is not bytes or len(raw)>65536:raise ValueError('jwks_unavailable')
        payload=_json(raw)
        if type(payload) is not dict or set(payload)!={'keys'} or type(payload['keys']) is not list or not 1<=len(payload['keys'])<=8:raise ValueError('invalid_jwks')
        keys={}
        for key in payload['keys']:
            if type(key) is not dict or set(key)-{'kid','kty','alg','use','key_ops','crv','x','y','n','e'}:raise ValueError('invalid_jwk')
            kid=key.get('kid');alg=key.get('alg')
            if type(kid) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,80}',kid) or kid in keys:raise ValueError('invalid_kid')
            if alg not in self.settings.algorithms or key.get('use','sig')!='sig' or key.get('key_ops',['verify'])!=['verify']:raise ValueError('invalid_key_policy')
            if alg=='ES256':
                if key.get('kty')!='EC' or key.get('crv')!='P-256' or set(key)&{'n','e'}:raise ValueError('invalid_ec_key')
                x,y=_decode(key['x'],32),_decode(key['y'],32)
                if len(x)!=32 or len(y)!=32:raise ValueError('invalid_ec_key')
                public=ec.EllipticCurvePublicNumbers(int.from_bytes(x,'big'),int.from_bytes(y,'big'),ec.SECP256R1()).public_key()
            else:
                if key.get('kty')!='RSA' or set(key)&{'crv','x','y'}:raise ValueError('invalid_rsa_key')
                n,e=_decode(key['n'],512),_decode(key['e'],8)
                if n[0]==0 or e[0]==0 or int.from_bytes(e,'big')!=65537:raise ValueError('invalid_rsa_key')
                public=rsa.RSAPublicNumbers(int.from_bytes(e,'big'),int.from_bytes(n,'big')).public_key()
                if not 2048<=public.key_size<=4096:raise ValueError('invalid_rsa_size')
            keys[kid]=(alg,public)
        return keys
    def verify(self,token):
        try:
            if type(token) is not str or not 1<=len(token)<=8192:raise ValueError('invalid_token')
            parts=token.split('.')
            if len(parts)!=3:raise ValueError('invalid_token')
            header=_json(_decode(parts[0],1024));claims=_json(_decode(parts[1],6144));sig=_decode(parts[2],512)
            if type(header) is not dict or set(header)-{'alg','kid','typ'} or header.get('typ','JWT')!='JWT':raise ValueError('invalid_header')
            alg=header.get('alg');kid=header.get('kid')
            if type(kid) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,80}',kid) or alg not in self.settings.algorithms:raise ValueError('invalid_algorithm')
            # One fresh bounded key snapshot per verification. Removed keys are never served from stale cache.
            key_alg,key=self._keys()[kid]
            if key_alg!=alg:raise ValueError('algorithm_key_mismatch')
            signed=(parts[0]+'.'+parts[1]).encode('ascii')
            if alg=='ES256':
                if len(sig)!=64:raise ValueError('invalid_ec_signature')
                key.verify(utils.encode_dss_signature(int.from_bytes(sig[:32],'big'),int.from_bytes(sig[32:],'big')),signed,ec.ECDSA(hashes.SHA256()))
            else:key.verify(sig,signed,padding.PKCS1v15(),hashes.SHA256())
            if type(claims) is not dict or claims.get('iss')!=self.settings.issuer or claims.get('aud')!=self.settings.audience or claims.get('role')!='authenticated':raise ValueError('invalid_claims')
            subject=claims.get('sub')
            if type(subject) is not str or str(UUID(subject))!=subject or claims.get('is_anonymous',False) is not False:raise ValueError('invalid_subject')
            now=self.clock();exp=claims['exp'];iat=claims['iat'];nbf=claims.get('nbf',iat)
            if not math.isfinite(now) or any(type(v) is not int for v in (exp,iat,nbf)):raise ValueError('invalid_time')
            if not 0<=iat<=now<exp or not iat<=nbf<=now or not 0<exp-iat<=self.settings.max_lifetime:raise ValueError('invalid_lifetime')
            ttl=math.floor(exp-now)
            if ttl<=0:raise ValueError('expired_token')
            return VerifiedIdentity(self.settings.issuer,subject,ttl)
        except Exception:raise ProviderUnavailable() from None


class SupabaseJWTProviderAdapter:
    """Explicit Fake password grant -> verified JWT -> existing BFF identity contract, never bearer API auth."""
    available=True
    remote_enabled=False
    def __init__(self,transport,verifier):
        if type(transport) is not FakeTokenTransport or type(verifier) is not SupabaseJWTVerifier:raise ValueError('offline_jwt_provider_required')
        self.transport,self.verifier,self.issuer=transport,verifier,verifier.settings.issuer
    def __repr__(self):return '<SupabaseJWTProviderAdapter offline redacted>'
    def authenticate(self,email,password):
        try:
            if type(self.transport) is not FakeTokenTransport or type(self.verifier) is not SupabaseJWTVerifier:raise ProviderUnavailable()
            status,payload=self.transport.request('POST','/auth/v1/token?grant_type=password',body={'email':email,'password':password})
            if type(status) is not int or status!=200 or type(payload) is not dict or payload.get('token_type')!='bearer':raise ValueError('invalid_token_response')
            ttl=payload['expires_in']
            if type(ttl) is not int or not 1<=ttl<=86400:raise ValueError('invalid_token_response')
            identity=self.verifier.verify(payload['access_token'])
            if type(payload.get('user')) is not dict or payload['user'].get('id')!=identity.subject or any(payload['user'].get(k) for k in ('is_anonymous','banned_until','deleted_at')):raise ValueError('token_user_mismatch')
            return VerifiedIdentity(identity.issuer,identity.subject,min(identity.ttl,ttl))
        except Exception:raise ProviderUnavailable() from None
