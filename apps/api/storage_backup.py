"""Privileged offline application-schema + Fake object backups. No cloud control plane."""
import copy
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import uuid
from .errors import DomainError
from .private_storage import PrivateOriginalStore, FakeStorageTransport, ObjectData, ObjectExists, ObjectMissing, StorageUnavailable, sha, object_path

TABLES = (
 'organizations','identities','memberships','sessions','auth_challenges','auth_audit_events','auth_login_limits',
 'documents','versions','upload_intents','events','parse_jobs','parse_attempts','source_blocks',
 'chunk_jobs','chunk_items','chunk_current','workflow_form_catalog','vector_generations','vector_items','vector_current',
 'workflow_jobs','workflow_generations','workflow_candidates','workflow_review_issues','workflow_form_links','workflow_job_events',
 'private_storage_objects')
INFRA = {'migrations','transaction_guard','schema_extensions','private_storage_schema','private_storage_restores'}
LIMIT = 64 * 1024 * 1024


def canonical(value): return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()


def parse(data):
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('duplicate_json_key')
            result[k]=v
        return result
    return json.loads(data,object_pairs_hook=unique,parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))


@dataclass(frozen=True)
class BackupAuthority:
    """Trusted offline operator scope, NOT a browser role, public API or human approval."""
    institutions: tuple[str,...]


@dataclass(frozen=True,repr=False)
class BackupBundle:
    manifest_bytes: bytes = field(repr=False)
    tables: dict[str,bytes] = field(repr=False)
    objects: dict[str,bytes] = field(repr=False)
    @property
    def manifest_sha256(self):return sha(self.manifest_bytes)


def _authority(operator):
    if type(operator) is not BackupAuthority or not operator.institutions or any(type(x) is not str or not 1<=len(x)<=200 for x in operator.institutions):
        raise DomainError('offline_backup_operator_required',403)


def _tables(repo,db):
    if getattr(repo,'dialect',None)=='postgresql':
        names={r[0] for r in db.connection.execute("SELECT table_name FROM information_schema.tables WHERE table_schema=? AND table_type='BASE TABLE'",(repo.database.schema,))}
    else:names={r[0] for r in db.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if names-set(TABLES)-INFRA:raise DomainError('backup_unknown_schema',409)
    return [name for name in TABLES if name in names]


def _columns(db,table):
    c=db.connection.execute('SELECT * FROM '+table+' LIMIT 0')
    return c.names if hasattr(c,'names') else [r[0] for r in c.description]


def _rows(db,tables):
    return {table:sorted([dict(r) for r in db.connection.execute('SELECT * FROM '+table)],key=canonical) for table in tables}


def _normalize(rows,stamp):
    rows=copy.deepcopy(rows)
    for r in rows.get('sessions',[]):r['revoked']=1
    if 'auth_challenges' in rows:rows['auth_challenges']=[]
    for r in rows.get('parse_attempts',[]):
        if r['state']=='processing':r.update(state='expired',finished_at=stamp,error_code='restore_recovered')
    parse_states={}
    for table in ('parse_jobs','chunk_jobs','workflow_jobs'):
        for r in rows.get(table,[]):
            if r['state']=='processing':
                r.update(state='queued' if r['attempt']<3 else 'failed',claim_hash=None,lease_until=None,error_code='restore_recovered')
                if table=='workflow_jobs':r['error_category']='RETRYABLE'
                if table=='parse_jobs':parse_states[r['version_id']]=r['state']
    for r in rows.get('versions',[]):
        if r['id'] in parse_states:r.update(state=parse_states[r['id']],claim_hash=None,revision=r['revision']+1)
    return {table:sorted(values,key=canonical) for table,values in rows.items()}


class StorageBackupService:
    def __init__(self,repo,store):
        if type(store) is not PrivateOriginalStore or type(store.transport) is not FakeStorageTransport or store.repo is not repo:
            raise DomainError('offline_private_backup_required',503)
        self.repo,self.store=repo,store
    def create(self,operator):
        _authority(operator);self.store._policy()
        with self.repo.transaction() as db, self.store.transport.frozen():
            tables=_tables(self.repo,db);rows=_rows(db,tables)
            scope={r['institution_id'] for r in rows.get('documents',[])} | {r['id'] for r in rows.get('organizations',[])}
            scope |= {r['institution_id'] for r in rows.get('private_storage_objects',[])}
            if not scope<=set(operator.institutions):raise DomainError('backup_institution_scope',403)
            if any(r['status']=='pending' for r in rows.get('upload_intents',[])):raise DomainError('backup_upload_in_progress',409)
            catalog={r['object_id']:r for r in rows.get('private_storage_objects',[])}
            versions={r['id']:r for r in rows.get('versions',[])}
            docs={r['id']:r for r in rows.get('documents',[])}
            if set(catalog)!=set(versions) or any(r['state']!='uploaded' for r in catalog.values()):raise DomainError('backup_unresolved_objects',409)
            objects={};descriptors={};snap=uuid.uuid4().hex
            for key,r in catalog.items():
                v=versions[key];institution=docs[v['document_id']]['institution_id']
                if (r['institution_id']!=institution or r['sha256']!=v['sha256'] or r['size']!=v['size']
                    or r['object_path']!=object_path(institution,key) or r['bucket']!=self.store.settings.bucket):raise DomainError('backup_object_scope_mismatch',409)
                try:body=self.store._verified(r)
                except (ObjectMissing,StorageUnavailable):raise DomainError('backup_object_unavailable',503) from None
                objects[key]=body;descriptors[key]={'institution_id':institution,'sha256':sha(body),'size':len(body),'snapshot_id':snap}
            actual={p for (bucket,p) in self.store.transport._objects if bucket==self.store.settings.bucket}
            if actual!={r['object_path'] for r in catalog.values()}:raise DomainError('backup_inventory_mismatch',409)
            table_bytes={table:canonical(values) for table,values in rows.items()}
            manifest={'schema_version':'private-backup-v1','backup_id':snap,'created_at':datetime.now(timezone.utc).isoformat(),
                      'bucket':self.store.settings.bucket,'institutions':sorted(scope),'source_backend':getattr(self.repo,'dialect','sqlite'),
                      'schema_contract':'seomuitda-application-v1','excluded_components':['provider_budget_separate_schema'],
                      'tables':{t:{'sha256':sha(data),'rows':len(rows[t]),'columns':_columns(db,t),'snapshot_id':snap} for t,data in table_bytes.items()},
                      'objects':descriptors}
            bundle=BackupBundle(canonical(manifest),table_bytes,objects)
            validate_bundle(bundle,bundle.manifest_sha256,operator)
            return bundle
    def restore(self,operator,bundle,expected_manifest_sha256):
        _authority(operator);self.store._policy()
        manifest,source=validate_bundle(bundle,expected_manifest_sha256,operator)
        if manifest['bucket']!=self.store.settings.bucket:raise DomainError('restore_bucket_mismatch',409)
        stamp=datetime.fromisoformat(manifest['created_at']).timestamp(); normalized=_normalize(source,stamp)
        # Objects precede DB visibility; failure leaves private, unreferenced objects, never deletion/overwrite.
        with self.repo.transaction() as db, self.store.transport.frozen():
            tables=_tables(self.repo,db)
            if not set(source)<=set(tables):raise DomainError('restore_schema_mismatch',409)
            for table,desc in manifest['tables'].items():
                if _columns(db,table)!=desc['columns']:raise DomainError('restore_schema_mismatch',409)
            previous=db.connection.execute('SELECT * FROM private_storage_restores WHERE backup_id=?',(manifest['backup_id'],)).fetchone()
            if previous:
                if previous['manifest_sha256']!=expected_manifest_sha256 or previous['result_digest']!=sha(canonical(_rows(db,list(source)))):
                    raise DomainError('restore_target_changed',409)
                self._restore_objects(manifest,bundle,copy_missing=False)
                return {'status':'ALREADY_RESTORED','backup_id':manifest['backup_id'],'published_workflows':0}
            if any(db.connection.execute('SELECT 1 FROM '+t+' LIMIT 1').fetchone() for t in tables):raise DomainError('restore_target_not_empty',409)
            self._restore_objects(manifest,bundle,copy_missing=True)
            active={r['id']:r['active_version_id'] for r in normalized.get('documents',[])}
            for table in TABLES:
                for row in normalized.get(table,[]):
                    value=dict(row)
                    if table=='documents':value['active_version_id']=None
                    columns=manifest['tables'][table]['columns']
                    if any(not re.fullmatch(r'[a-z][a-z0-9_]*',c) for c in columns):raise DomainError('restore_schema_mismatch',409)
                    db.connection.execute('INSERT INTO '+table+'('+','.join('"'+c+'"' for c in columns)+') VALUES('+','.join('?' for _ in columns)+')',tuple(value[c] for c in columns))
            for key,version in active.items():db.connection.execute('UPDATE documents SET active_version_id=? WHERE id=?',(version,key))
            if getattr(self.repo,'dialect',None)=='postgresql':
                for table in ('events','auth_audit_events','workflow_job_events'):
                    if table in normalized:
                        maximum=max((r['id'] for r in normalized[table]),default=0)
                        db.connection.execute('SELECT setval(pg_get_serial_sequence(?,?),?,?)',(table,'id',max(maximum,1),maximum>0))
            actual=_rows(db,list(source))
            if actual!=normalized:raise DomainError('restore_database_mismatch',409)
            db.connection.execute("INSERT INTO private_storage_restores VALUES(?,?,?,'completed')",(manifest['backup_id'],expected_manifest_sha256,sha(canonical(actual))))
        return {'status':'RESTORED','backup_id':manifest['backup_id'],'objects':len(bundle.objects),'sessions_revoked':True,
                'worker_claims_fenced':True,'semantic_verification':'NOT_VERIFIED','published_workflows':0}
    def _restore_objects(self,manifest,bundle,*,copy_missing):
        expected={object_path(d['institution_id'],key) for key,d in manifest['objects'].items()}
        actual={path for bucket,path in self.store.transport._objects if bucket==self.store.settings.bucket}
        if actual-expected:raise DomainError('restore_unexpected_objects',409)
        try:
            for key,data in bundle.objects.items():
                desc=manifest['objects'][key];path=object_path(desc['institution_id'],key)
                try:value=self.store.transport.get(self.store.settings.bucket,path)
                except ObjectMissing:
                    if not copy_missing:raise DomainError('restore_object_missing',409)
                    try:self.store.transport.put_if_absent(self.store.settings.bucket,path,data)
                    except ObjectExists:pass
                    value=self.store.transport.get(self.store.settings.bucket,path)
                if type(value) is not ObjectData or value.size!=desc['size'] or len(value.data)!=desc['size'] or value.sha256!=desc['sha256'] or sha(value.data)!=desc['sha256']:
                    raise DomainError('restore_object_integrity',409)
        except StorageUnavailable:raise DomainError('restore_storage_unavailable',503) from None


def validate_bundle(bundle,expected,operator):
    _authority(operator)
    try:
        if type(bundle) is not BackupBundle or not re.fullmatch(r'[0-9a-f]{64}',expected or '') or bundle.manifest_sha256!=expected:raise ValueError()
        if len(bundle.manifest_bytes)>1024*1024 or sum(map(len,bundle.tables.values()))+sum(map(len,bundle.objects.values()))>LIMIT:raise ValueError()
        m=parse(bundle.manifest_bytes)
        if set(m)!={'schema_version','backup_id','created_at','bucket','institutions','source_backend','schema_contract','excluded_components','tables','objects'}:raise ValueError()
        if m['schema_version']!='private-backup-v1' or m['schema_contract']!='seomuitda-application-v1' or m['source_backend'] not in ('sqlite','postgresql'):raise ValueError()
        if m['excluded_components']!=['provider_budget_separate_schema'] or not re.fullmatch('[0-9a-f]{32}',m['backup_id']):raise ValueError()
        if datetime.fromisoformat(m['created_at']).tzinfo is None or not set(m['institutions'])<=set(operator.institutions):raise ValueError()
        if not set(m['tables'])<=set(TABLES) or not {'documents','versions','private_storage_objects'}<=set(m['tables']):raise ValueError()
        if set(m['tables'])!=set(bundle.tables) or set(m['objects'])!=set(bundle.objects):raise ValueError()
        rows={}
        for table,data in bundle.tables.items():
            desc=m['tables'][table]
            if set(desc)!={'sha256','rows','columns','snapshot_id'} or desc['snapshot_id']!=m['backup_id'] or sha(data)!=desc['sha256']:raise ValueError()
            values=parse(data)
            if not isinstance(values,list) or len(values)!=desc['rows'] or len(values)>100000 or len(desc['columns'])!=len(set(desc['columns'])):raise ValueError()
            if any(not isinstance(row,dict) or set(row)!=set(desc['columns']) for row in values):raise ValueError()
            rows[table]=sorted(values,key=canonical)
        docs={r['id']:r for r in rows['documents']};versions={r['id']:r for r in rows['versions']}
        catalog={r['object_id']:r for r in rows['private_storage_objects']}
        if len(docs)!=len(rows['documents']) or len(versions)!=len(rows['versions']) or len(catalog)!=len(rows['private_storage_objects']):raise ValueError()
        if set(versions)!=set(catalog) or set(versions)!=set(m['objects']):raise ValueError()
        if not {r['institution_id'] for r in docs.values()}<=set(m['institutions']):raise ValueError()
        for d in docs.values():
            if d['active_version_id'] is not None and (d['active_version_id'] not in versions or versions[d['active_version_id']]['document_id']!=d['id']):raise ValueError()
            if not d['registered'] and d['active_version_id'] is not None:raise ValueError()
        for key,data in bundle.objects.items():
            desc=m['objects'][key];v=versions[key];r=catalog[key];institution=docs[v['document_id']]['institution_id']
            if set(desc)!={'institution_id','sha256','size','snapshot_id'} or desc['snapshot_id']!=m['backup_id']:raise ValueError()
            if not re.fullmatch('[0-9a-f]{32}',key) or desc['institution_id']!=institution or r['institution_id']!=institution:raise ValueError()
            if not 0<len(data)<=20*1024*1024 or len(data)!=desc['size'] or sha(data)!=desc['sha256']:raise ValueError()
            if (v['sha256'],v['size'])!=(desc['sha256'],desc['size']) or (r['sha256'],r['size'])!=(desc['sha256'],desc['size']):raise ValueError()
            if r['state']!='uploaded' or r['bucket']!=m['bucket'] or r['object_path']!=object_path(institution,key):raise ValueError()
        return m,rows
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):raise DomainError('invalid_backup_bundle',422) from None


def save_bundle(bundle,directory):
    path=Path(directory)
    path.mkdir(mode=0o700,parents=False,exist_ok=False)
    def write(name,data):
        with name.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        name.chmod(0o600)
    (path/'tables').mkdir(mode=0o700);(path/'objects').mkdir(mode=0o700)
    for name,data in bundle.tables.items():
        if name not in TABLES:raise DomainError('invalid_backup_bundle',422)
        write(path/'tables'/(name+'.json'),data)
    for key,data in bundle.objects.items():
        if not re.fullmatch('[0-9a-f]{32}',key):raise DomainError('invalid_backup_bundle',422)
        write(path/'objects'/key,data)
    write(path/'manifest.json',bundle.manifest_bytes)
    write(path/'COMPLETE',bundle.manifest_sha256.encode())
    return bundle.manifest_sha256


def load_bundle(directory,expected_manifest_sha256,operator):
    path=Path(directory)
    try:
        if path.is_symlink() or any(p.is_symlink() for p in path.rglob('*')):raise ValueError()
        if (path/'COMPLETE').read_text()!=expected_manifest_sha256:raise ValueError()
        if (path/'manifest.json').stat().st_size>1024*1024:raise ValueError()
        manifest=(path/'manifest.json').read_bytes()
        if sha(manifest)!=expected_manifest_sha256:raise ValueError()
        m=parse(manifest);tables={};objects={};total=0
        for names,dest,folder,ext in ((m['tables'],tables,'tables','.json'),(m['objects'],objects,'objects','')):
            for name in names:
                if (folder=='tables' and name not in TABLES) or (folder=='objects' and not re.fullmatch('[0-9a-f]{32}',name)):raise ValueError()
                file=path/folder/(name+ext);total+=file.stat().st_size
                if total>LIMIT:raise ValueError()
                dest[name]=file.read_bytes()
        bundle=BackupBundle(manifest,tables,objects);validate_bundle(bundle,expected_manifest_sha256,operator)
        return bundle
    except (OSError,ValueError,TypeError,KeyError,RecursionError):raise DomainError('invalid_backup_bundle',422) from None
