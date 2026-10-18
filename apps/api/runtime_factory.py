"""Single API/worker composition boundary, with code-owned production blocking."""
from pathlib import Path
from .runtime_settings import RuntimeSettings, load_settings, preflight, SettingsRejected
from .runtime_wiring import RuntimeBinding, ROLES
from .repository import Repository
from .storage import LocalOriginalStore
from .identity_provider import UnconfiguredProvider
from .auth import AuthSettings


def build_runtime(data_dir, *, role='api', settings=None, postgres_plan=None, migration_mode='verify',
                  private_settings=None, storage_transport=None, identity_provider=None,
                  auth_settings=None, session_guard=None, proxy_policy=None, api_peer=None, repository_factory=None):
    """Explicit DI works without real credentials. No environment flag grants live I/O.

    postgres_plan is an isolated-loopback test/operator seam, not a production
    DATABASE_URL override. Supabase settings stay blocked by preflight capability.
    """
    if role not in ROLES:
        raise ValueError('invalid_factory_role')
    if settings is None:
        settings = load_settings(default_role=role)
    if type(settings) is not RuntimeSettings:
        raise ValueError('invalid_factory_settings')
    try:
        settings = RuntimeSettings.model_validate(settings.model_dump(warnings=False))
    except ValueError:
        raise ValueError('invalid_factory_settings') from None
    from .runtime_settings import ENV_FIELDS
    # Preserve secret values only inside typed validation; never report this map.
    env = {}
    for key, field in ENV_FIELDS.items():
        value = getattr(settings, field)
        if value is None:
            continue
        if hasattr(value, 'get_secret_value'): value = value.get_secret_value()
        env[key] = str(value).lower() if type(value) is bool else str(value)
    result = preflight(env, expected_role=role)
    if not result['startup_allowed']:
        raise SettingsRejected(result['issues'] + result.get('implementation_blockers', []) + result.get('operational_mapping_issues', []))
    if migration_mode not in ('apply', 'verify') or (postgres_plan is None and migration_mode != 'verify'):
        raise ValueError('invalid_factory_migration_policy')
    from .private_storage import PrivateStorageSettings, FakeStorageTransport, PrivateOriginalStore
    from .storage_http import StorageHTTPTransport,SupabaseStorageHTTPTransport
    from .supabase_jwt import SupabaseJWTProviderAdapter
    from .session_revalidation import SessionRevalidation
    from .proxy_boundary import ProxyPolicy
    provider = identity_provider if identity_provider is not None else UnconfiguredProvider()
    if type(provider) not in (UnconfiguredProvider, SupabaseJWTProviderAdapter):
        raise ValueError('factory_provider_not_implemented')
    if auth_settings is not None and type(auth_settings) is not AuthSettings:
        raise ValueError('invalid_auth_binding')
    if role != 'api' and (type(provider) is not UnconfiguredProvider or session_guard is not None or proxy_policy is not None):
        raise ValueError('worker_browser_auth_forbidden')
    if type(provider) is SupabaseJWTProviderAdapter and type(session_guard) is not SessionRevalidation:
        raise ValueError('fake_auth_revalidation_required')
    if proxy_policy is not None and (type(proxy_policy) is not ProxyPolicy or auth_settings is None
            or proxy_policy.origin != auth_settings.origin or not auth_settings.secure_cookie):
        raise ValueError('proxy_auth_binding_mismatch')
    if (private_settings is None) != (storage_transport is None):
        raise ValueError('storage_settings_transport_pair_required')
    if private_settings is not None:
        if type(private_settings) is not PrivateStorageSettings or type(storage_transport) not in (FakeStorageTransport, StorageHTTPTransport, SupabaseStorageHTTPTransport):
            raise ValueError('factory_storage_transport_not_implemented')
        try:
            private_settings = PrivateStorageSettings.model_validate(private_settings.model_dump(warnings=False))
            # Reuse private-store URL/key validation before any DB side effects.
            import re
            if (not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co', private_settings.project_url.get_secret_value())
                    or not re.fullmatch(r'[\x21-\x7e]{16,4096}', private_settings.server_key.get_secret_value())
                    or private_settings.server_key.get_secret_value().startswith('sb_publishable_')):
                raise ValueError()
        except ValueError:
            raise ValueError('invalid_factory_private_settings') from None
        if storage_transport.private is not True:
            raise ValueError('private_storage_required')
        if type(storage_transport) in (StorageHTTPTransport,SupabaseStorageHTTPTransport) and not storage_transport.matches(private_settings):
            raise ValueError('storage_http_configuration_mismatch')
        if type(provider) is SupabaseJWTProviderAdapter and provider.issuer != private_settings.project_url.get_secret_value()+'/auth/v1':
            raise ValueError('storage_auth_project_mismatch')
    if repository_factory is not None and (not callable(repository_factory) or postgres_plan is not None):
        raise ValueError('choose_one_repository_configuration')
    if (getattr(storage_transport,'network_selected',False) or getattr(provider,'remote_enabled',False)
            or getattr(getattr(getattr(provider,'verifier',None),'transport',None),'network_selected',False)):
        raise ValueError('local_live_transports_forbidden')
    root = Path(data_dir).resolve()
    if api_peer is not None:
        if type(api_peer) is not RuntimeBinding or api_peer.role != 'api' or role == 'api':
            raise ValueError('api_worker_role_mismatch')
        api_peer.validate()
        if root != api_peer.data_dir:
            raise ValueError('api_worker_data_root_mismatch')
        from urllib.parse import urlsplit
        expected = getattr(api_peer, 'migration_plan', None)
        def plan_target(plan):
            if plan is None: return None
            from .migration_runner import MigrationRunner
            runner = MigrationRunner(plan)  # Validates loopback; no connection.
            p = urlsplit(runner.application._dsn)
            return p.hostname, p.port, p.path, plan.application_schema, plan.budget_schema
        if plan_target(expected) != plan_target(postgres_plan):
            raise ValueError('api_worker_database_or_budget_mismatch')
        if private_settings is not None:
            if (type(api_peer.store) is not PrivateOriginalStore or api_peer.store.settings != private_settings
                    or api_peer.store.transport is not storage_transport):
                raise ValueError('api_worker_private_storage_mismatch')
        elif type(api_peer.store) is not LocalOriginalStore:
            raise ValueError('api_worker_storage_kind_mismatch')
        effective_auth = auth_settings or AuthSettings(origin=settings.origin.get_secret_value(), secure_cookie=settings.secure_cookie)
        if api_peer.auth_settings != effective_auth:
            raise ValueError('api_worker_session_policy_mismatch')
    budget = None
    if postgres_plan is not None:
        from .migration_runner import MigrationRunner
        from .postgres import PostgresRepository, PostgresBudgetLedger
        runner = MigrationRunner(postgres_plan)
        runner.run(mode=migration_mode)
        repo = PostgresRepository(runner.application)
        budget = PostgresBudgetLedger(runner.budget)
    else:
        repo = (repository_factory or Repository)(root/'metadata.sqlite3')
        from .postgres import PostgresRepository
        if type(repo) not in (Repository,PostgresRepository) or (type(repo) is PostgresRepository and not repo.database.local_test):
            raise ValueError('repository_injection_not_implemented')
    store = (PrivateOriginalStore(repo, private_settings, storage_transport) if private_settings is not None
             else LocalOriginalStore(root/'originals'))
    binding = RuntimeBinding(root, repo, store, role=role, provider=provider,
                             auth_settings=auth_settings or AuthSettings(origin=settings.origin.get_secret_value(), secure_cookie=settings.secure_cookie),
                             proxy_policy=proxy_policy, session_guard=session_guard)
    binding.budget_ledger = budget
    binding.migration_plan = postgres_plan
    if api_peer is not None:
        binding._api_peer = api_peer
        from .runtime_wiring import compare_bindings
        if compare_bindings(api_peer,binding): raise ValueError('api_worker_binding_mismatch')
    return binding


def build_legacy_local_postgres(args, role):
    """Preserve older CLI's application-only verify seam, never migrate or go remote."""
    from .runtime_settings import ensure_start_environment
    ensure_start_environment(role)
    from .postgres_worker import worker_repository
    return RuntimeBinding(args.data_dir, worker_repository(args),
                          LocalOriginalStore(args.data_dir/'originals'), role=role)


def build_application(data_dir, **configuration):
    """Factory entry usable by an ASGI launcher; guarded before app/DB creation."""
    if configuration.get('role', 'api') != 'api':
        raise ValueError('api_factory_role_required')
    binding = build_runtime(data_dir, **configuration)
    from .main import create_app
    return create_app(runtime_binding=binding, parsing_enabled=True)


def prepare_production_runtime(settings, **transports):
    """Prepare mapped adapters only; cannot start processes or release blockers."""
    from .operational_mapping import prepare_operational_adapters
    return prepare_operational_adapters(settings, **transports)
