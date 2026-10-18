"""Explicit local/Fake API-worker composition. No production capability override or implicit remote fallback."""
from pathlib import Path
from urllib.parse import urlsplit
from .repository import Repository
from .storage import LocalOriginalStore
from .service import DocumentService
from .auth import AuthSettings
from .identity_provider import UnconfiguredProvider

ROLES=('api','parse_worker','chunk_worker','workflow_worker')


class RuntimeBinding:
    def __init__(self,data_dir,repository,store,*,role='api',provider=None,auth_settings=None,proxy_policy=None,session_guard=None):
        self.data_dir=Path(data_dir).resolve();self.repo=repository;self.store=store;self.role=role
        self.provider=provider or UnconfiguredProvider();self.auth_settings=auth_settings or AuthSettings()
        self.proxy_policy,self.session_guard=proxy_policy,session_guard
        self.validate()
    def __repr__(self):return '<RuntimeBinding local-or-fake redacted>'
    def validate(self):
        from .postgres import PostgresRepository
        from .private_storage import PrivateOriginalStore,FakeStorageTransport
        from .supabase_jwt import SupabaseJWTProviderAdapter
        from .session_revalidation import SessionRevalidation
        from .proxy_boundary import ProxyPolicy
        if self.role not in ROLES or type(self.repo) not in (Repository,PostgresRepository):raise ValueError('invalid_runtime_binding')
        if type(self.repo) is PostgresRepository and not self.repo.database.local_test:raise ValueError('remote_database_wiring_blocked')
        if type(self.store) is PrivateOriginalStore:
            if self.store.repo is not self.repo or type(self.store.transport) is not FakeStorageTransport:raise ValueError('private_storage_binding_mismatch')
            self.store._policy()
        elif type(self.store) is not LocalOriginalStore:raise ValueError('storage_binding_not_implemented')
        if type(self.auth_settings) is not AuthSettings:raise ValueError('invalid_auth_binding')
        if self.role!='api':
            if type(self.provider) is not UnconfiguredProvider or self.session_guard is not None or self.proxy_policy is not None:raise ValueError('worker_browser_auth_forbidden')
        elif type(self.provider) is not UnconfiguredProvider:
            if type(self.provider) is not SupabaseJWTProviderAdapter or type(self.session_guard) is not SessionRevalidation:raise ValueError('fake_auth_revalidation_required')
            if type(self.store) is PrivateOriginalStore and self.provider.issuer!=self.store.settings.project_url.get_secret_value()+'/auth/v1':raise ValueError('storage_auth_project_mismatch')
        if self.proxy_policy is not None:
            if type(self.proxy_policy) is not ProxyPolicy or self.proxy_policy.origin!=self.auth_settings.origin or not self.auth_settings.secure_cookie:raise ValueError('proxy_auth_binding_mismatch')
        return self
    def worker(self,role):
        if role not in ROLES[1:]:raise ValueError('invalid_worker_role')
        child=RuntimeBinding(self.data_dir,self.repo,self.store,role=role,auth_settings=self.auth_settings)
        child._api_peer=self
        return child
    def documents(self):
        self.validate()
        if self.role!='api':
            from .private_storage import PrivateOriginalStore
            peer=getattr(self,'_api_peer',None)
            if peer is not None and compare_bindings(peer,self):raise ValueError('api_worker_binding_mismatch')
            if type(self.store) is PrivateOriginalStore and peer is None:raise ValueError('fake_worker_requires_shared_api_binding')
        return DocumentService(self.repo,self.store,True)
    def worker_service(self):
        self.validate()
        from .parsing_service import ParsingService
        from .chunk_service import ChunkService
        from .workflow_jobs import WorkflowJobService
        parsing=ParsingService(self.documents())
        if self.role=='parse_worker':return parsing
        chunks=ChunkService(parsing)
        if self.role=='chunk_worker':return chunks
        if self.role=='workflow_worker':return WorkflowJobService(chunks)
        raise ValueError('worker_role_required')


def compare_bindings(api,worker):
    api.validate();worker.validate()
    errors=[]
    if api.data_dir!=worker.data_dir:errors.append('api_worker_data_root_mismatch')
    if api.role!='api' or worker.role not in ROLES[1:]:errors.append('api_worker_role_mismatch')
    def target(binding):
        if getattr(binding.repo,'dialect',None)=='postgresql':
            db=binding.repo.database;p=urlsplit(db._dsn)
            return ('postgresql',p.hostname,p.port or 5432,p.path,db.schema)
        return ('sqlite',str(binding.repo.path.resolve()))
    if target(api)!=target(worker):errors.append('api_worker_database_target_mismatch')
    from .private_storage import PrivateOriginalStore
    if type(api.store)!=type(worker.store):errors.append('api_worker_storage_kind_mismatch')
    elif type(api.store) is PrivateOriginalStore:
        if (api.store.settings.project_url,api.store.settings.bucket)!=(worker.store.settings.project_url,worker.store.settings.bucket):errors.append('api_worker_storage_target_mismatch')
        if api.store.transport is not worker.store.transport:errors.append('fake_storage_not_shared')
    elif api.store.root!=worker.store.root:errors.append('api_worker_local_storage_mismatch')
    if api.auth_settings!=worker.auth_settings:errors.append('api_worker_session_policy_mismatch')
    return sorted(set(errors))


def worker_documents(args,role,binding=None):
    from .runtime_settings import ensure_start_environment
    ensure_start_environment(role)
    if binding is not None:
        if type(binding) is not RuntimeBinding or binding.role!=role or binding.data_dir!=args.data_dir.resolve():raise ValueError('worker_binding_mismatch')
        if args.postgres_local_test:raise ValueError('choose_one_worker_binding')
        return binding.documents()
    from .postgres_worker import worker_repository
    return RuntimeBinding(args.data_dir,worker_repository(args),LocalOriginalStore(args.data_dir/'originals'),role=role).documents()
