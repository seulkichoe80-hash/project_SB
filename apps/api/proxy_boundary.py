"""Single sanitized proxy hop contract + bounded offline /api edge simulator. Not a Vercel deployment."""
import asyncio
from collections import OrderedDict
import hashlib
import hmac
import ipaddress
import re
import time
from urllib.parse import urlsplit
from pydantic import BaseModel,ConfigDict,Field,SecretStr,model_validator
from .formats import MAX_BYTES

HOP={b'connection',b'keep-alive',b'proxy-authenticate',b'proxy-authorization',b'te',b'trailer',b'transfer-encoding',b'upgrade'}


class ProxyPolicy(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='forbid',hide_input_in_errors=True)
    origin: str=Field(repr=False)
    backend_host: str=Field(repr=False)
    trusted_peer_cidrs: tuple[str,...]
    shared_token: SecretStr=Field(repr=False)
    max_bytes: int=Field(default=MAX_BYTES,ge=1,le=MAX_BYTES)
    timeout_seconds: int=Field(default=60,ge=1,le=120)
    requests_per_minute: int=Field(default=30,ge=1,le=600)
    @model_validator(mode='after')
    def policy(self):
        p=urlsplit(self.origin)
        if (p.scheme!='https' or not p.hostname or p.username or p.password or p.path or p.query or p.fragment
            or p.netloc!=p.hostname+((':'+str(p.port)) if p.port else '') or not re.fullmatch(r'[a-z0-9.-]+',p.hostname)):
            raise ValueError('invalid_proxy_origin')
        if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?(?::[0-9]{1,5})?',self.backend_host) or '..' in self.backend_host:raise ValueError('invalid_backend_host')
        urlsplit('https://'+self.backend_host).port
        if not re.fullmatch(r'[\x21-\x7e]{32,256}',self.shared_token.get_secret_value()):raise ValueError('invalid_proxy_proof')
        if not self.trusted_peer_cidrs or len(self.trusted_peer_cidrs)>8:raise ValueError('explicit_trusted_peers_required')
        for cidr in self.trusted_peer_cidrs:
            n=ipaddress.ip_network(cidr,strict=True)
            if n.prefixlen<(24 if n.version==4 else 64) or n.is_multicast or n.is_unspecified:raise ValueError('unsafe_trusted_peer')
        return self


async def reject(send,status,code):
    import json
    body=json.dumps({'error':code}).encode()
    headers=[(b'content-type',b'application/json'),(b'cache-control',b'no-store')]
    if status==429:headers.append((b'retry-after',b'60'))
    await send({'type':'http.response.start','status':status,'headers':headers})
    await send({'type':'http.response.body','body':body})


def headers_of(scope):
    values={}
    for k,v in scope['headers']:
        key=k.lower()
        if key in values and key in (b'host',b'origin',b'cookie',b'content-length',b'transfer-encoding',b'forwarded',b'x-sb-proxy-token',b'x-csrf-token'):
            raise ValueError('duplicate_security_header')
        if key.startswith(b'x-forwarded-') and key in values:raise ValueError('duplicate_forwarded_header')
        values[key]=v
    return values


def framing(headers,limit):
    length=headers.get(b'content-length')
    if length is not None and (not re.fullmatch(b'[0-9]{1,10}',length) or (len(length)>1 and length.startswith(b'0'))):raise ValueError('invalid_request_framing')
    if b'transfer-encoding' in headers and (length is not None or headers[b'transfer-encoding'].lower()!=b'chunked'):raise ValueError('invalid_request_framing')
    if length is not None and int(length)>limit:raise OverflowError()
    return int(length) if length is not None else None


async def read_body(receive,limit,declared,timeout):
    async def collect():
        data=bytearray()
        while True:
            msg=await receive()
            if msg['type']!='http.request':raise ValueError('request_disconnected')
            chunk=msg.get('body',b'')
            if len(data)+len(chunk)>limit:raise OverflowError()
            data.extend(chunk)
            if not msg.get('more_body',False):break
        if declared is not None and declared!=len(data):raise ValueError('request_length_mismatch')
        return bytes(data)
    return await asyncio.wait_for(collect(),timeout)


def replay(body):
    used=False
    async def receive():
        nonlocal used
        if not used:used=True;return {'type':'http.request','body':body,'more_body':False}
        # Preserve a live HTTP connection while a downstream streaming response is sent.
        await asyncio.Future()
    return receive


class ProxyBoundary:
    def __init__(self,app,policy,clock=time.monotonic):
        self.app=app;self.policy=ProxyPolicy.model_validate(policy.model_dump());self.clock=clock;self._limits=OrderedDict()
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        try:
            h=headers_of(scope);p=self.policy;peer=ipaddress.ip_address(scope['client'][0])
            trusted=any(peer in ipaddress.ip_network(n) for n in p.trusted_peer_cidrs)
            if not trusted or not hmac.compare_digest(h.get(b'x-sb-proxy-token',b''),p.shared_token.get_secret_value().encode()):return await reject(send,403,'untrusted_proxy')
            public=urlsplit(p.origin)
            if h.get(b'host')!=p.backend_host.encode() or h.get(b'x-forwarded-host')!=public.netloc.encode() or h.get(b'x-forwarded-proto')!=b'https':return await reject(send,400,'proxy_host_or_https_rejected')
            if b'forwarded' in h or any(k in h for k in HOP-{b'transfer-encoding'}) or any(k.startswith(b'x-forwarded-') and k not in (b'x-forwarded-for',b'x-forwarded-host',b'x-forwarded-proto') for k in h):raise ValueError('unsupported_forwarded_header')
            client=ipaddress.ip_address(h.get(b'x-forwarded-for',b'').decode())
            if h.get(b'origin') not in (None,p.origin.encode()) or h.get(b'sec-fetch-site')==b'cross-site':return await reject(send,403,'origin_rejected')
            if scope['method'] not in ('GET','HEAD','OPTIONS') and h.get(b'origin')!=p.origin.encode():return await reject(send,403,'origin_rejected')
            key=hashlib.sha256(client.packed).digest();now=self.clock();window,count=self._limits.get(key,(now,0))
            if now-window>=60:window,count=now,0
            if count>=p.requests_per_minute:return await reject(send,429,'proxy_request_limit')
            self._limits[key]=(window,count+1);self._limits.move_to_end(key)
            while len(self._limits)>1000:self._limits.popitem(last=False)
            body=await read_body(receive,p.max_bytes,framing(h,p.max_bytes),p.timeout_seconds)
            clean={**scope,'scheme':'https','server':(public.hostname,public.port or 443),'client':(str(client),0)}
            clean['headers']=[(k,v) for k,v in scope['headers'] if not k.lower().startswith(b'x-forwarded-') and k.lower() not in (b'forwarded',b'x-sb-proxy-token',b'host',b'transfer-encoding')]+[(b'host',public.netloc.encode())]
        except OverflowError:return await reject(send,413,'file_size_limit')
        except TimeoutError:return await reject(send,408,'proxy_body_timeout')
        except (ValueError,TypeError,KeyError,UnicodeError):return await reject(send,400,'invalid_proxy_request')
        await self.app(clean,replay(body),send)


class OfflineSameOriginProxy:
    """In-process /api edge simulation. For local validation only; never contacts Render or Vercel."""
    def __init__(self,backend,policy,*,peer='127.0.0.1'):
        self.backend=backend;self.policy=ProxyPolicy.model_validate(policy.model_dump());self.peer=peer
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.backend(scope,receive,send)
        p=self.policy;public=urlsplit(p.origin);path=scope['path']
        try:
            h=headers_of(scope)
            if scope.get('scheme')!='https' or h.get(b'host')!=public.netloc.encode():return await reject(send,400,'edge_https_host_rejected')
            if not path.startswith('/api/') or '//' in path or '\\' in path or '..' in path.split('/'):return await reject(send,404,'proxy_route_not_found')
            body=await read_body(receive,p.max_bytes,framing(h,p.max_bytes),p.timeout_seconds)
            upstream={**scope,'scheme':'http','path':path[4:],'raw_path':path[4:].encode(),'root_path':'','client':(self.peer,0),'server':(p.backend_host,80)}
            upstream['headers']=[(k,v) for k,v in scope['headers'] if not k.lower().startswith(b'x-forwarded-') and k.lower() not in HOP|{b'host',b'forwarded',b'x-sb-proxy-token',b'content-length'}]+[(b'content-length',str(len(body)).encode()),(b'host',p.backend_host.encode()),(b'x-forwarded-host',public.netloc.encode()),(b'x-forwarded-proto',b'https'),(b'x-forwarded-for',scope['client'][0].encode()),(b'x-sb-proxy-token',p.shared_token.get_secret_value().encode())]
            messages=[];total=0
            async def capture(message):
                nonlocal total
                if message['type']=='http.response.body':
                    total+=len(message.get('body',b''))
                    if total>MAX_BYTES+65536:raise ValueError('response_too_large')
                messages.append(message)
            await asyncio.wait_for(self.backend(upstream,replay(body),capture),p.timeout_seconds)
            if sum(m['type']=='http.response.start' for m in messages)!=1 or not messages or messages[-1]['type']!='http.response.body' or messages[-1].get('more_body',False):raise ValueError('incomplete_upstream_response')
            for message in messages:
                if message['type']=='http.response.start':
                    result=[]
                    for key,value in message.get('headers',[]):
                        if key.lower() in HOP:continue
                        if key.lower()==b'location':
                            location=urlsplit(value.decode())
                            if location.netloc and location.netloc not in (public.netloc,p.backend_host):raise ValueError('external_redirect_blocked')
                            if location.scheme and location.scheme!='https':raise ValueError('insecure_redirect_blocked')
                            if not location.path.startswith('/') or location.path.startswith('//') or '\\' in location.path:raise ValueError('invalid_redirect')
                            target=location.path if location.path.startswith('/api/') else '/api'+location.path
                            value=(target+('?' + location.query if location.query else '')).encode()
                        if key.lower() in (b'access-control-allow-origin',b'access-control-allow-credentials'):raise ValueError('unexpected_cors')
                        result.append((key,value))
                    message={**message,'headers':result}
        except OverflowError:return await reject(send,413,'file_size_limit')
        except TimeoutError:return await reject(send,504,'proxy_upstream_timeout')
        except Exception:return await reject(send,502,'proxy_request_failed')
        for message in messages:
            if message['type']=='http.response.start':message={**message,'headers':result}
            await send(message)
