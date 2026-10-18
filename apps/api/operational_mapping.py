"""Pure mapping/preparation: no migrations, connections, secret logs or guard release."""
from dataclasses import dataclass
from .runtime_settings import RuntimeSettings,settings_issues,operational_mapping_issues,secret,SettingsRejected,PRODUCTION_BLOCKERS
from .provider_http import ProviderNetworkPolicy,SupabaseAuthHTTPTransport,SupabaseJWKSTransport
from .private_storage import PrivateStorageSettings
from .storage_http import SupabaseStorageHTTPTransport
from .supabase_transport import SupabaseSettings
from .supabase_jwt import JWTSettings,SupabaseJWTVerifier,SupabaseJWTProviderAdapter
from .migration_runner import MigrationPlan
from .identity_provider import UnconfiguredProvider


@dataclass(frozen=True,repr=False)
class OperationalAdapters:
    migration_plan: MigrationPlan
    storage_settings: PrivateStorageSettings
    storage: SupabaseStorageHTTPTransport
    identity: SupabaseJWTProviderAdapter | UnconfiguredProvider
    def __repr__(self):return '<OperationalAdapters prepared redacted production-blocked>'
    def diagnostics(self):
        return {'mapping':'PREPARED','production_ready':False,'startup_allowed':False,
                'blockers':list(PRODUCTION_BLOCKERS),'storage_network_selected':self.storage.network_selected,
                'auth_network_selected':getattr(self.identity,'remote_enabled',False),'migration_target':self.migration_plan.target,
                'actual_connectivity':'NOT_CHECKED'}


def prepare_operational_adapters(settings,*,storage_mock=None,auth_mock=None,jwks_mock=None):
    if type(settings) is not RuntimeSettings:raise SettingsRejected(['invalid_operational_settings'])
    try:settings=RuntimeSettings.model_validate(settings.model_dump(warnings=False))
    except ValueError:raise SettingsRejected(['invalid_operational_settings']) from None
    issues=settings_issues(settings)+operational_mapping_issues(settings)
    if settings.environment!='production':issues.append('production_mapping_required')
    mocks=(storage_mock,auth_mock,jwks_mock)
    if settings.role=='api' and any(m is not None for m in mocks) and not all(m is not None for m in mocks):
        issues.append('partial_mock_transports_forbidden')
    if issues:raise SettingsRejected(issues)
    project=secret(settings.supabase_project_url)
    def policy(service):
        return ProviderNetworkPolicy(project_url=project,service=service,enabled=settings.provider_network_enabled,
                                     approval_ref=settings.provider_approval_ref)
    try:
        migration=MigrationPlan(database_url=settings.database_url,application_schema=settings.application_schema,
                                budget_schema=settings.budget_schema,target='production')
        storage_settings=PrivateStorageSettings(project_url=settings.storage_project_url,bucket=secret(settings.storage_bucket),
                                                server_key=settings.storage_server_key)
        storage=SupabaseStorageHTTPTransport(storage_settings,gateway_key=settings.storage_gateway_key,
                                             policy=policy('storage'),mock_transport=storage_mock)
        if settings.role!='api':
            if auth_mock is not None or jwks_mock is not None:raise ValueError('worker_browser_auth_forbidden')
            return OperationalAdapters(migration,storage_settings,storage,UnconfiguredProvider())
        auth_settings=SupabaseSettings(project,secret(settings.supabase_auth_api_key))
        token=SupabaseAuthHTTPTransport(auth_settings,policy=policy('auth'),mock_transport=auth_mock)
        keys=SupabaseJWKSTransport(auth_settings,policy=policy('auth'),mock_transport=jwks_mock)
        verifier=SupabaseJWTVerifier(JWTSettings(issuer=auth_settings.issuer,audience=settings.auth_audience,
                                                max_lifetime=settings.jwt_max_lifetime),keys)
        return OperationalAdapters(migration,storage_settings,storage,SupabaseJWTProviderAdapter(token,verifier))
    except Exception:
        error=SettingsRejected(['operational_adapter_preparation_failed'])
    raise error
