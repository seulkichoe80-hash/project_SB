"""Private original contract: local fake or explicit mock HTTP; no live transport."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
import threading
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, SecretStr
from .errors import DomainError
from .formats import MAX_BYTES
from .models import Principal

ROOT = Path(__file__).resolve().parents[2]


class PrivateStorageSettings(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra='forbid', hide_input_in_errors=True)
    project_url: SecretStr = Field(repr=False)
    bucket: str = Field(pattern=r'^[a-z0-9][a-z0-9_-]{2,62}$')
    server_key: SecretStr = Field(repr=False)
    private: Literal[True] = True
    real_calls_enabled: Literal[False] = False
    timeout_seconds: int = Field(default=5, ge=1, le=10)


def sha(data): return hashlib.sha256(data).hexdigest()


def object_path(institution, key):
    if not isinstance(institution, str) or not 1 <= len(institution) <= 200 or not re.fullmatch(r'[0-9a-f]{32}', key or ''):
        raise DomainError('invalid_storage_scope',400)
    return 'institutions/' + sha(institution.encode()) + '/originals/' + key


@dataclass(frozen=True)
class ObjectData:
    data: bytes = field(repr=False)
    size: int
    sha256: str


class StorageUnavailable(Exception): pass
class ObjectMissing(Exception): pass
class ObjectExists(Exception): pass


class StorageTransport(Protocol):
    def put_if_absent(self, bucket: str, path: str, data: bytes): ...
    def get(self, bucket: str, path: str) -> ObjectData: ...
    def list_page(self, bucket: str, prefix: str, offset: int, limit: int) -> list[str]: ...


class FakeStorageTransport:
    """Thread-safe immutable synthetic objects, deterministic fault injection, no callbacks/sockets."""
    def __init__(self, *, private=True, faults=()):
        allowed={'put_timeout_before','put_timeout_after','put_partial','get_timeout','get_corrupt','get_wrong_hash','get_wrong_size','list_timeout','list_foreign'}
        if type(private) is not bool or type(faults) not in (tuple,list) or any(type(f) is not str or f not in allowed for f in faults):
            raise ValueError('invalid_fake_storage_configuration')
        self.private = private
        self._objects = {}; self._lock = threading.RLock(); self.faults = list(faults)
        self.calls = []  # Operation names only: never keys, bodies, server keys or URLs.
    def _fault(self, operation):
        if self.faults and self.faults[0].startswith(operation + '_'):
            return self.faults.pop(0)
        return None
    def put_if_absent(self, bucket, path, data):
        with self._lock:
            self.calls.append('put'); fault = self._fault('put')
            if fault == 'put_timeout_before': raise StorageUnavailable()
            if (bucket,path) in self._objects: raise ObjectExists()
            body = data[:max(0,len(data)//2)] if fault == 'put_partial' else data
            self._objects[bucket,path] = ObjectData(body,len(data),sha(data))
            if fault == 'put_timeout_after': raise StorageUnavailable()
    def get(self, bucket, path):
        with self._lock:
            self.calls.append('get'); fault = self._fault('get')
            if fault == 'get_timeout': raise StorageUnavailable()
            value = self._objects.get((bucket,path))
            if value is None: raise ObjectMissing()
            if fault == 'get_corrupt': return ObjectData(value.data+b'x',value.size,value.sha256)
            if fault == 'get_wrong_hash': return ObjectData(value.data,value.size,'0'*64)
            if fault == 'get_wrong_size': return ObjectData(value.data,value.size+1,value.sha256)
            return value
    def list_page(self,bucket,prefix,offset,limit):
        with self._lock:
            self.calls.append('list'); fault = self._fault('list')
            if fault == 'list_timeout': raise StorageUnavailable()
            keys = sorted(path for b,path in self._objects if b == bucket and path.startswith(prefix))
            if fault == 'list_foreign': keys = ['institutions/foreign/originals/'+'a'*32]
            return keys[offset:offset+limit]
    @contextmanager
    def frozen(self):
        with self._lock: yield


class StorageRegistry:
    def __init__(self, repository): self.repo = repository
    def migrate(self):
        data=(ROOT/'migrations/storage/001_private_storage.sql').read_text(); checksum=sha(data.encode())
        with self.repo.transaction() as db:
            c=db.connection
            if getattr(self.repo,'dialect',None)=='postgresql':
                existing={r[0] for r in c.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=?', (self.repo.database.schema,))}
            else: existing={r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'private_storage_schema' in existing:
                rows=c.execute('SELECT version,checksum FROM private_storage_schema').fetchall()
                if len(rows)!=1 or rows[0][0]!=1 or rows[0][1]!=checksum: raise DomainError('unsupported_private_storage_schema')
                return False
            if existing & {'private_storage_objects','private_storage_restores'}: raise DomainError('unknown_private_storage_schema')
            c.execute('CREATE TABLE private_storage_schema(version INTEGER PRIMARY KEY,checksum TEXT NOT NULL)')
            for statement in data.split(';'):
                if statement.strip(): c.execute(statement)
            c.execute('INSERT INTO private_storage_schema VALUES(1,?)',(checksum,))
            return True
    @contextmanager
    def use(self, db=None):
        if db is not None: yield db
        else:
            with self.repo.transaction() as current: yield current


class PrivateOriginalStore:
    """Server-authorized original access; database publication and object upload stay separate."""
    def __init__(self, repository, settings, transport):
        from .storage_http import StorageHTTPTransport,SupabaseStorageHTTPTransport
        if type(settings) is not PrivateStorageSettings or type(transport) not in (FakeStorageTransport, StorageHTTPTransport, SupabaseStorageHTTPTransport):
            raise DomainError('real_storage_transport_disabled',503)
        try:
            settings=PrivateStorageSettings.model_validate(settings.model_dump(warnings=False))
            if (not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co',settings.project_url.get_secret_value())
                or not re.fullmatch(r'[\x21-\x7e]{16,4096}',settings.server_key.get_secret_value())
                or settings.server_key.get_secret_value().startswith('sb_publishable_')): raise ValueError()
        except ValueError: raise DomainError('invalid_private_storage_settings',422) from None
        self.repo,self.settings,self.transport=repository,settings,transport
        self._policy(); self.registry=StorageRegistry(repository); self.registry.migrate()
    def __repr__(self): return '<PrivateOriginalStore offline-only redacted>'
    def _policy(self):
        from .storage_http import StorageHTTPTransport,SupabaseStorageHTTPTransport
        if type(self.transport) in (StorageHTTPTransport,SupabaseStorageHTTPTransport):
            if not self.transport.matches(self.settings):
                raise DomainError('storage_http_configuration_mismatch',503)
        elif type(self.transport) is not FakeStorageTransport:
            raise DomainError('private_storage_required',503)
        if self.transport.private is not True:
            raise DomainError('private_storage_required',503)
    @staticmethod
    def _principal(principal, write=False):
        if not isinstance(principal,Principal) or principal.role not in (('manager',) if write else ('reader','manager','worker')):
            raise DomainError('private_storage_access_denied',403)
    def _record(self,db,principal,key):
        row=db.connection.execute('SELECT * FROM private_storage_objects WHERE object_id=? AND institution_id=?',(key,principal.institution_id)).fetchone()
        if not row: raise DomainError('original_unavailable',409)
        if row['object_path']!=object_path(principal.institution_id,key) or row['bucket']!=self.settings.bucket:
            raise DomainError('storage_scope_integrity',409)
        return row
    def _scope(self,db,principal,key):
        object_path(principal.institution_id,key)
        version=db.connection.execute('SELECT v.*,d.institution_id,d.registered,d.active_version_id FROM versions v JOIN documents d ON d.id=v.document_id WHERE v.id=? AND d.institution_id=?',(key,principal.institution_id)).fetchone()
        if version:
            if principal.role=='reader' and (not version['registered'] or version['active_version_id']!=key): raise DomainError('private_storage_access_denied',404)
            if principal.role=='worker' and not version['registered']: raise DomainError('private_storage_access_denied',404)
            return version
        intent=db.connection.execute("SELECT * FROM upload_intents WHERE id=? AND institution_id=? AND status='pending'",(key,principal.institution_id)).fetchone()
        if not intent or principal.role!='manager': raise DomainError('private_storage_access_denied',404)
        return None
    def _verified(self,row):
        value=self.transport.get(self.settings.bucket,row['object_path'])
        if (type(value) is not ObjectData or type(value.data) is not bytes or not 0<len(value.data)<=MAX_BYTES
            or value.size!=row['size'] or len(value.data)!=row['size'] or value.sha256!=row['sha256'] or sha(value.data)!=row['sha256']):
            raise DomainError('original_integrity_failure',409)
        return value.data
    def write(self,principal,key,data):
        self._principal(principal,True); self._policy(); path=object_path(principal.institution_id,key)
        if type(data) is not bytes or not 0<len(data)<=MAX_BYTES: raise DomainError('file_size_limit',413)
        digest=sha(data)
        with self.repo.transaction() as db:
            if self._scope(db,principal,key) is not None: raise DomainError('original_overwrite_forbidden',409)
            old=db.connection.execute('SELECT * FROM private_storage_objects WHERE object_id=?',(key,)).fetchone()
            if old and (old['institution_id']!=principal.institution_id or old['sha256']!=digest or old['size']!=len(data) or old['state']=='quarantined'):
                raise DomainError('original_overwrite_forbidden',409)
            if not old:
                from .service import now
                db.connection.execute("INSERT INTO private_storage_objects VALUES(?,?,?,?,?,?,'planned',0,NULL,?)",(key,principal.institution_id,self.settings.bucket,path,digest,len(data),now()))
            row=self._record(db,principal,key)
            if row['attempts']>=3: raise DomainError('storage_retry_limit',409)
            db.connection.execute('UPDATE private_storage_objects SET attempts=attempts+1 WHERE object_id=?',(key,))
        state,error='uploaded',None
        try:
            # Probe first: an upload whose response was lost is never overwritten.
            try: self._verified(row)
            except ObjectMissing:
                try: self.transport.put_if_absent(self.settings.bucket,path,data)
                except ObjectExists: pass
                self._verified(row)
        except DomainError:
            state,error='quarantined','original_integrity_failure'
        except (StorageUnavailable,ObjectMissing): state,error='unknown','storage_unavailable'
        except Exception: state,error='unknown','storage_invalid_response'
        with self.repo.transaction() as db:
            current=self._record(db,principal,key)
            if current['state']=='quarantined':state,error='quarantined','original_integrity_failure'
            db.connection.execute('UPDATE private_storage_objects SET state=?,error_code=? WHERE object_id=?',(state,error,key))
        if error: raise DomainError(error,503 if state=='unknown' else 409)
    def read(self,principal,key,expected_hash,*,db=None):
        self._principal(principal); self._policy()
        with self.registry.use(db) as current:
            version=self._scope(current,principal,key);row=self._record(current,principal,key)
            if row['state']!='uploaded' or row['sha256']!=expected_hash:
                raise DomainError('original_integrity_failure',409)
            if version and (version['sha256']!=row['sha256'] or version['size']!=row['size']): raise DomainError('original_integrity_failure',409)
            try: return self._verified(row)
            except (StorageUnavailable,ObjectMissing): raise DomainError('original_unavailable',503) from None
            except DomainError: raise
            except Exception: raise DomainError('storage_invalid_response',503) from None
    def reconcile(self,principal):
        self._principal(principal,True);self._policy()
        prefix=object_path(principal.institution_id,'0'*32)[:-32];keys=[];offset=0
        try:
            while True:
                page=self.transport.list_page(self.settings.bucket,prefix,offset,100)
                if not isinstance(page,list) or len(page)>100 or any(not isinstance(k,str) or not k.startswith(prefix) or not re.fullmatch(r'[0-9a-f]{32}',k[len(prefix):]) for k in page):
                    raise DomainError('invalid_storage_inventory',409)
                keys.extend(page);offset+=len(page)
                if len(keys)>20000 or len(set(keys))!=len(keys):raise DomainError('storage_inventory_limit',413)
                if len(page)<100:break
        except StorageUnavailable:raise DomainError('storage_inventory_unavailable',503) from None
        issues=[]
        with self.repo.transaction() as db:
            known={r['object_path']:r for r in db.connection.execute('SELECT * FROM private_storage_objects WHERE institution_id=?',(principal.institution_id,))}
            for path in keys:
                key=path[len(prefix):];row=known.get(path)
                version=db.connection.execute('SELECT v.id FROM versions v JOIN documents d ON d.id=v.document_id WHERE v.id=? AND d.institution_id=?',(key,principal.institution_id)).fetchone()
                intent=db.connection.execute('SELECT status FROM upload_intents WHERE id=? AND institution_id=?',(key,principal.institution_id)).fetchone()
                if version and row:
                    try:self._verified(row)
                    except (DomainError,StorageUnavailable,ObjectMissing):
                        db.connection.execute("UPDATE private_storage_objects SET state='quarantined',error_code='original_integrity_failure' WHERE object_id=?",(key,));issues.append({'object_id':key,'code':'INTEGRITY_QUARANTINED'})
                elif intent and intent['status']=='pending':issues.append({'object_id':key,'code':'UPLOAD_PENDING'})
                else:
                    if row:db.connection.execute("UPDATE private_storage_objects SET state='quarantined',error_code='orphan_object' WHERE object_id=?",(key,))
                    else:
                        try:value=self.transport.get(self.settings.bucket,path)
                        except (StorageUnavailable,ObjectMissing):raise DomainError('storage_inventory_unavailable',503) from None
                        if type(value) is not ObjectData or len(value.data)>MAX_BYTES:raise DomainError('invalid_storage_inventory',409)
                        from .service import now
                        db.connection.execute("INSERT INTO private_storage_objects VALUES(?,?,?,?,?,?,'quarantined',0,'orphan_object',?)",(key,principal.institution_id,self.settings.bucket,path,sha(value.data),len(value.data),now()))
                    issues.append({'object_id':key,'code':'ORPHAN_QUARANTINED'})
            for path,row in known.items():
                if path not in keys:issues.append({'object_id':row['object_id'],'code':'OBJECT_MISSING'})
        return {'issues':issues,'objects_seen':len(keys),'deleted':0,'moved':0,'published':0}
