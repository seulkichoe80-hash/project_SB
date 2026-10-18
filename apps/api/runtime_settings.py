"""Offline deployment contract. No DNS, clients, database or filesystem access."""
import ipaddress
import os
import re
from urllib.parse import parse_qsl, unquote, urlsplit
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError
from typing import Literal
from .formats import MAX_BYTES
from .auth import AuthSettings
from .supabase_transport import SupabaseSettings


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True, hide_input_in_errors=True)
    environment: Literal['local', 'test', 'production'] = 'local'
    role: Literal['api', 'parse_worker', 'chunk_worker', 'workflow_worker'] = 'api'
    database_backend: Literal['sqlite', 'postgresql'] = 'sqlite'
    database_url: SecretStr | None = Field(default=None, repr=False)
    storage_backend: Literal['local', 'supabase'] = 'local'
    storage_project_url: SecretStr | None = Field(default=None, repr=False)
    storage_bucket: SecretStr | None = Field(default=None, repr=False)
    storage_server_key: SecretStr | None = Field(default=None, repr=False)
    storage_private: bool = True
    auth_provider: Literal['deny_all', 'mock', 'supabase'] = 'deny_all'
    supabase_project_url: SecretStr | None = Field(default=None, repr=False)
    supabase_auth_api_key: SecretStr | None = Field(default=None, repr=False)
    origin: SecretStr = Field(default=SecretStr('https://localhost'), repr=False)
    secure_cookie: bool = True
    csrf_enabled: bool = True
    same_origin_proxy: bool = True
    trusted_proxy_hops: int = Field(default=0, ge=0, le=2)
    membership_policy: Literal['server_active_single'] = 'server_active_single'
    max_upload_bytes: int = Field(default=MAX_BYTES, ge=1, le=MAX_BYTES)
    requests_per_minute: int = Field(default=30, ge=1, le=600)
    request_timeout_seconds: int = Field(default=60, ge=1, le=120)
    real_llm_enabled: bool = False
    real_embedding_enabled: bool = False
    paid_calls_approved: bool = False
    llm_budget_micro_usd: int = Field(default=0, ge=0, le=100_000_000)
    llm_request_cap_micro_usd: int = Field(default=0, ge=0, le=1_000_000)
    llm_max_input_tokens: int = Field(default=16000, ge=1, le=100000)
    llm_max_output_tokens: int = Field(default=2048, ge=1, le=32768)
    llm_max_retries: int = Field(default=1, ge=0, le=1)
    backup_strategy: Literal['unconfigured', 'coordinated_private_db_objects'] = 'unconfigured'
    restore_rpo_hours: int | None = Field(default=None, ge=1, le=24)
    restore_rto_hours: int | None = Field(default=None, ge=1, le=24)


# Explicit allowlist: no arbitrary environment-to-model interpolation or secret dumps.
ENV_FIELDS = {
    'APP_ENV': 'environment', 'APP_ROLE': 'role', 'DATABASE_BACKEND': 'database_backend',
    'DATABASE_URL': 'database_url', 'STORAGE_BACKEND': 'storage_backend',
    'STORAGE_PROJECT_URL': 'storage_project_url', 'STORAGE_BUCKET': 'storage_bucket',
    'STORAGE_SERVER_KEY': 'storage_server_key', 'STORAGE_PRIVATE': 'storage_private',
    'AUTH_PROVIDER': 'auth_provider', 'SUPABASE_PROJECT_URL': 'supabase_project_url',
    'SUPABASE_AUTH_API_KEY': 'supabase_auth_api_key', 'APP_ORIGIN': 'origin',
    'SECURE_COOKIE': 'secure_cookie', 'CSRF_ENABLED': 'csrf_enabled',
    'SAME_ORIGIN_PROXY': 'same_origin_proxy', 'TRUSTED_PROXY_HOPS': 'trusted_proxy_hops',
    'MEMBERSHIP_POLICY': 'membership_policy', 'MAX_UPLOAD_BYTES': 'max_upload_bytes',
    'REQUESTS_PER_MINUTE': 'requests_per_minute', 'REQUEST_TIMEOUT_SECONDS': 'request_timeout_seconds',
    'REAL_LLM_ENABLED': 'real_llm_enabled', 'REAL_EMBEDDING_ENABLED': 'real_embedding_enabled',
    'PAID_CALLS_APPROVED': 'paid_calls_approved', 'LLM_BUDGET_MICRO_USD': 'llm_budget_micro_usd',
    'LLM_REQUEST_CAP_MICRO_USD': 'llm_request_cap_micro_usd',
    'LLM_MAX_INPUT_TOKENS': 'llm_max_input_tokens', 'LLM_MAX_OUTPUT_TOKENS': 'llm_max_output_tokens',
    'LLM_MAX_RETRIES': 'llm_max_retries', 'BACKUP_STRATEGY': 'backup_strategy',
    'RESTORE_RPO_HOURS': 'restore_rpo_hours', 'RESTORE_RTO_HOURS': 'restore_rto_hours',
}
BOOL_FIELDS = {name for name, field in RuntimeSettings.model_fields.items() if field.annotation is bool}
INT_FIELDS = {'trusted_proxy_hops', 'max_upload_bytes', 'requests_per_minute', 'request_timeout_seconds',
              'llm_budget_micro_usd', 'llm_request_cap_micro_usd', 'llm_max_input_tokens',
              'llm_max_output_tokens', 'llm_max_retries', 'restore_rpo_hours', 'restore_rto_hours'}


class SettingsRejected(RuntimeError):
    """Static codes only; never retain ValidationError inputs or configuration values."""
    def __init__(self, codes):
        self.codes = tuple(sorted(set(codes)))
        super().__init__('runtime_start_blocked:' + ','.join(self.codes))


def load_settings(environ=None, *, default_role='api'):
    env = os.environ if environ is None else environ
    values = {'role': default_role}
    errors = []
    for key, name in ENV_FIELDS.items():
        if key not in env:
            continue
        value = env[key]
        if not isinstance(value, str) or len(value) > 8192:
            errors.append('invalid_' + key)
            continue
        if key == 'APP_ENV' and value == 'development':
            value = 'local'  # Preserve historical .env.example alias, never defaults unknown envs.
        if name in BOOL_FIELDS:
            if value not in ('true', 'false'):
                errors.append('invalid_' + key); continue
            value = value == 'true'
        elif name in INT_FIELDS:
            if not re.fullmatch(r'[0-9]{1,10}', value):
                errors.append('invalid_' + key); continue
            value = int(value)
        values[name] = value
    if values.get('environment') == 'production':
        required = ('APP_ROLE', 'DATABASE_BACKEND', 'DATABASE_URL', 'STORAGE_BACKEND',
                    'STORAGE_PROJECT_URL', 'STORAGE_BUCKET', 'STORAGE_SERVER_KEY', 'STORAGE_PRIVATE',
                    'AUTH_PROVIDER', 'SUPABASE_PROJECT_URL', 'SUPABASE_AUTH_API_KEY', 'APP_ORIGIN',
                    'SECURE_COOKIE', 'CSRF_ENABLED', 'SAME_ORIGIN_PROXY', 'TRUSTED_PROXY_HOPS',
                    'MEMBERSHIP_POLICY', 'REAL_LLM_ENABLED', 'REAL_EMBEDDING_ENABLED', 'PAID_CALLS_APPROVED',
                    'BACKUP_STRATEGY', 'RESTORE_RPO_HOURS', 'RESTORE_RTO_HOURS')
        errors.extend('missing_' + key for key in required if not isinstance(env.get(key), str) or not env[key].strip())
    if errors:
        raise SettingsRejected(errors)
    try:
        return RuntimeSettings.model_validate(values)
    except ValidationError as error:
        fields = {name: key for key, name in ENV_FIELDS.items()}
        codes = ['invalid_' + fields.get(e['loc'][0], 'settings')
                 for e in error.errors(include_input=False, include_context=False, include_url=False)]
        raise SettingsRejected(codes) from None


def secret(value):
    return value.get_secret_value() if value else ''


def public_hostname(host):
    if not host or host != host.lower() or host.endswith('.'):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return bool(re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', host)) and '.' in host and not any(
            host == suffix or host.endswith('.' + suffix) for suffix in ('localhost', 'local', 'internal', 'test', 'invalid'))


def valid_database_url(raw):
    try:
        p = urlsplit(raw)
        params = parse_qsl(p.query, strict_parsing=True)
        return (not any(c.isspace() or ord(c) < 32 for c in raw)
                and p.scheme == 'postgresql' and public_hostname(p.hostname)
                and bool(p.username) and bool(p.password) and not p.fragment
                and bool(re.fullmatch(r'/[A-Za-z0-9_-]+', p.path))
                and (p.port is None or p.port in (5432, 6543))
                and params == [('sslmode', 'verify-full')]
                and not any(ord(c) < 32 for c in unquote(p.username + p.password)))
    except (ValueError, TypeError):
        return False


def settings_issues(s):
    issues = []
    def require(condition, code):
        if not condition: issues.append(code)
    try:
        AuthSettings(origin=secret(s.origin), secure_cookie=s.secure_cookie)
    except ValueError:
        issues.append('invalid_https_origin_cookie')
    require(s.csrf_enabled, 'csrf_required')
    require(not (s.real_llm_enabled or s.real_embedding_enabled or s.paid_calls_approved
                 or s.llm_budget_micro_usd or s.llm_request_cap_micro_usd), 'real_provider_budget_not_supported')
    if s.environment != 'production':
        require(s.database_backend == 'sqlite' and s.storage_backend == 'local', 'cloud_adapters_not_implemented')
        require(s.auth_provider in ('deny_all', 'mock'), 'local_remote_auth_not_wired')
        require(not any((s.database_url, s.storage_project_url, s.storage_server_key,
                         s.supabase_project_url, s.supabase_auth_api_key, s.storage_bucket)), 'unused_cloud_settings')
        return issues
    require(s.database_backend == 'postgresql', 'production_postgresql_required')
    require(valid_database_url(secret(s.database_url)), 'invalid_DATABASE_URL')
    require(s.storage_backend == 'supabase' and s.storage_private, 'production_private_storage_required')
    require(bool(re.fullmatch(r'[a-z0-9][a-z0-9_-]{2,62}', secret(s.storage_bucket))), 'invalid_STORAGE_BUCKET')
    require(bool(re.fullmatch(r'[\x21-\x7e]{16,4096}', secret(s.storage_server_key)))
            and not secret(s.storage_server_key).startswith('sb_publishable_'), 'invalid_STORAGE_SERVER_KEY')
    require(s.auth_provider == 'supabase', 'production_supabase_auth_required')
    try:
        SupabaseSettings(secret(s.supabase_project_url), secret(s.supabase_auth_api_key))
    except ValueError:
        issues.append('invalid_supabase_auth_settings')
    require(bool(s.storage_project_url) and secret(s.storage_project_url) == secret(s.supabase_project_url),
            'storage_auth_project_mismatch')
    require(bool(s.storage_server_key) and secret(s.storage_server_key) != secret(s.supabase_auth_api_key),
            'storage_auth_keys_must_differ')
    try:
        p = urlsplit(secret(s.origin))
        public_origin = (p.scheme == 'https' and public_hostname(p.hostname)
                         and p.netloc in (p.hostname, p.hostname + ':443') and p.port in (None, 443))
    except ValueError:
        public_origin = False
    require(public_origin, 'production_public_https_origin_required')
    require(s.secure_cookie and s.same_origin_proxy, 'production_secure_same_origin_required')
    require(1 <= s.trusted_proxy_hops <= 2, 'production_trusted_proxy_hops_required')
    require(s.backup_strategy == 'coordinated_private_db_objects' and s.restore_rpo_hours is not None
            and s.restore_rto_hours is not None, 'backup_restore_plan_required')
    return issues


def peer_issues(api, worker):
    if api.role != 'api' or worker.role not in ('parse_worker', 'chunk_worker', 'workflow_worker'):
        return ['api_worker_role_mismatch']
    common = ('environment', 'database_backend', 'storage_backend', 'storage_project_url', 'storage_bucket',
              'supabase_project_url', 'auth_provider', 'origin', 'secure_cookie', 'csrf_enabled',
              'same_origin_proxy', 'membership_policy', 'max_upload_bytes', 'real_llm_enabled',
              'real_embedding_enabled', 'llm_budget_micro_usd', 'backup_strategy', 'restore_rpo_hours', 'restore_rto_hours')
    issues = ['api_worker_contract_mismatch'] if any(getattr(api, k) != getattr(worker, k) for k in common) else []
    # Distinct least-privilege DB users are allowed; compare the database target, not credentials.
    def target(s):
        p = urlsplit(secret(s.database_url))
        return p.hostname, p.port or 5432, p.path
    if target(api) != target(worker): issues.append('api_worker_database_target_mismatch')
    return issues


# Code-owned capabilities; operator flags cannot turn these into an implementation or verified deployment.
PRODUCTION_BLOCKERS = (
    'postgresql_repository_auth_jobs_budget_not_implemented',
    'private_object_storage_adapter_not_implemented',
    'production_auth_membership_bootstrap_not_implemented',
    'proxy_limits_and_headers_not_verified',
    'worker_cloud_runtime_not_implemented',
    'coordinated_backup_restore_not_verified',
)


def preflight(environ=None, *, expected_role=None, peer=None):
    try:
        s = load_settings(environ, default_role=expected_role or 'api')
        issues = settings_issues(s)
        if expected_role is not None and s.role != expected_role:
            issues.append('runtime_role_mismatch')
        if peer is not None:
            other = load_settings(peer)
            issues.extend(settings_issues(other))
            issues.extend(peer_issues(s, other))
    except SettingsRejected as error:
        return {'settings_status': 'INVALID', 'status': 'INVALID', 'startup_allowed': False,
                'production_ready': False, 'connectivity': 'NOT_CHECKED', 'issues': list(error.codes)}
    blockers = list(PRODUCTION_BLOCKERS) if s.environment == 'production' else []
    return {'environment': s.environment, 'role': s.role,
            'settings_status': 'INVALID' if issues else 'VALID',
            'status': 'INVALID' if issues else ('BLOCKED' if blockers else 'LOCAL_CONTRACT_VALID'),
            'startup_allowed': not issues and not blockers, 'production_ready': False,
            'connectivity': 'NOT_CHECKED', 'membership_verification': 'SERVER_ACTIVE_SINGLE_CONTRACT_ONLY',
            'backup_restore_verification': 'NOT_VERIFIED',
            'issues': sorted(set(issues)), 'implementation_blockers': blockers}


def ensure_start_environment(role):
    result = preflight(expected_role=role)
    if not result['startup_allowed']:
        raise SettingsRejected(result['issues'] + result.get('implementation_blockers', []))
