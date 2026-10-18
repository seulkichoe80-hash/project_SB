"""Deployment checks are offline contracts, never live cloud readiness claims."""
import contextlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from apps.api.runtime_settings import (RuntimeSettings, SettingsRejected, load_settings, preflight,
                                       ensure_start_environment, PRODUCTION_BLOCKERS)
from scripts.validation.deployment_preflight import read_config

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / 'scripts/validation/deployment_preflight.py'
MARKER = 'synthetic-private-value-MUST-NOT-APPEAR'


def production(role='api'):
    project = 'https://' + 'a' * 20 + '.supabase.co'
    return {'APP_ENV': 'production', 'APP_ROLE': role, 'DATABASE_BACKEND': 'postgresql',
            'DATABASE_URL': 'postgresql://synthetic:synthetic-only@db.synthetic.example:5432/app?sslmode=verify-full',
            'STORAGE_BACKEND': 'supabase', 'STORAGE_PROJECT_URL': project, 'STORAGE_BUCKET': 'synthetic-originals',
            'STORAGE_SERVER_KEY': 'synthetic-storage-key-not-real', 'STORAGE_PRIVATE': 'true',
            'AUTH_PROVIDER': 'supabase', 'SUPABASE_PROJECT_URL': project,
            'SUPABASE_AUTH_API_KEY': 'sb_publishable_synthetic_not_real_key_123456',
            'APP_ORIGIN': 'https://app.synthetic.example', 'SECURE_COOKIE': 'true',
            'CSRF_ENABLED': 'true', 'SAME_ORIGIN_PROXY': 'true', 'TRUSTED_PROXY_HOPS': '1',
            'MEMBERSHIP_POLICY': 'server_active_single', 'REAL_LLM_ENABLED': 'false',
            'REAL_EMBEDDING_ENABLED': 'false', 'PAID_CALLS_APPROVED': 'false',
            'BACKUP_STRATEGY': 'coordinated_private_db_objects', 'RESTORE_RPO_HOURS': '24', 'RESTORE_RTO_HOURS': '4'}


class DeploymentPreflightTests(unittest.TestCase):
    def test_default_local(self):
        r = preflight({})
        self.assertTrue(r['startup_allowed']); self.assertEqual(r['connectivity'], 'NOT_CHECKED')
        self.assertFalse(r['production_ready'])
    def test_test_environment(self):
        self.assertTrue(preflight({'APP_ENV': 'test', 'AUTH_PROVIDER': 'mock'})['startup_allowed'])
    def test_historical_development_alias(self):
        self.assertEqual(load_settings({'APP_ENV': 'development'}).environment, 'local')
    def test_unknown_environment_fails_closed(self):
        for value in ('', 'prod', 'Production', MARKER):
            with self.subTest(value=value):
                r = preflight({'APP_ENV': value}); self.assertFalse(r['startup_allowed'])
                self.assertNotIn(MARKER, json.dumps(r))
    def test_production_missing_keys(self):
        r = preflight({'APP_ENV': 'production'})
        self.assertEqual(r['settings_status'], 'INVALID')
        self.assertIn('missing_DATABASE_URL', r['issues'])
    def test_each_required_key(self):
        for key in production():
            if key == 'APP_ENV': continue
            env = production(); del env[key]
            with self.subTest(key=key):
                self.assertIn('missing_' + key, preflight(env)['issues'])
    def test_valid_production_is_blocked_not_connected(self):
        r = preflight(production())
        self.assertEqual(r['settings_status'], 'VALID'); self.assertEqual(r['status'], 'BLOCKED')
        self.assertFalse(r['startup_allowed']); self.assertEqual(r['connectivity'], 'NOT_CHECKED')
        self.assertEqual(r['implementation_blockers'], list(PRODUCTION_BLOCKERS))
    def test_production_sqlite(self):
        r = preflight(production() | {'DATABASE_BACKEND': 'sqlite'})
        self.assertIn('production_postgresql_required', r['issues'])
    def test_production_local_storage(self):
        self.assertIn('production_private_storage_required', preflight(production() | {'STORAGE_BACKEND': 'local'})['issues'])
    def test_production_mock_and_deny_all(self):
        for provider in ('mock', 'deny_all'):
            self.assertIn('production_supabase_auth_required', preflight(production() | {'AUTH_PROVIDER': provider})['issues'])
    def test_database_tls_and_url_safety(self):
        values = ['sqlite:///data', 'postgresql://u:p@localhost/app?sslmode=verify-full',
                  'postgresql://u:p@127.0.0.1/app?sslmode=verify-full',
                  'postgresql://u:p@db.synthetic.example/app?sslmode=require',
                  'postgresql://u:p@db.synthetic.example/app?sslmode=verify-full&sslmode=disable',
                  'postgresql://u:p@db.synthetic.example:80/app?sslmode=verify-full', MARKER]
        for value in values:
            with self.subTest(value=value):
                self.assertIn('invalid_DATABASE_URL', preflight(production() | {'DATABASE_URL': value})['issues'])
    def test_origin_safety(self):
        for value in ('http://app.synthetic.example', 'https://localhost', 'https://app.synthetic.example/path',
                      'https://user:password@app.synthetic.example', 'https://app.synthetic.example:bad', 'https://app.synthetic.example:8443', 'https://app.synthetic.example?secret='+MARKER, 'https://['):
            with self.subTest(value=value):
                r = preflight(production() | {'APP_ORIGIN': value})
                self.assertFalse(r['startup_allowed']); self.assertNotIn(MARKER, json.dumps(r))
    def test_cookie_csrf_proxy_safety(self):
        for key, value in [('SECURE_COOKIE', 'false'), ('CSRF_ENABLED', 'false'),
                           ('SAME_ORIGIN_PROXY', 'false'), ('TRUSTED_PROXY_HOPS', '0'), ('TRUSTED_PROXY_HOPS', '3')]:
            with self.subTest(key=key): self.assertEqual(preflight(production() | {key:value})['settings_status'], 'INVALID')
    def test_http_cookie_only_local_loopback(self):
        self.assertTrue(preflight({'APP_ORIGIN':'http://127.0.0.1', 'SECURE_COOKIE':'false'})['startup_allowed'])
        self.assertFalse(preflight({'APP_ORIGIN':'http://app.synthetic.example', 'SECURE_COOKIE':'false'})['startup_allowed'])
    def test_bucket_and_private(self):
        for key, value in [('STORAGE_BUCKET','../public'), ('STORAGE_PRIVATE','false')]:
            self.assertEqual(preflight(production() | {key:value})['settings_status'], 'INVALID')
    def test_auth_https_project_key_validation(self):
        for key, value in [('SUPABASE_PROJECT_URL','http://localhost'), ('SUPABASE_AUTH_API_KEY',MARKER)]:
            self.assertIn('invalid_supabase_auth_settings', preflight(production() | {key:value})['issues'])
    def test_storage_project_and_key_separation(self):
        self.assertIn('storage_auth_project_mismatch', preflight(production() | {'STORAGE_PROJECT_URL':'https://'+'b'*20+'.supabase.co'})['issues'])
        self.assertIn('storage_auth_keys_must_differ', preflight(production() | {'STORAGE_SERVER_KEY':production()['SUPABASE_AUTH_API_KEY']})['issues'])
    def test_membership_metadata_not_accepted(self):
        r = preflight(production() | {'MEMBERSHIP_POLICY':'user_metadata'})
        self.assertFalse(r['startup_allowed'])
    def test_provider_approval_or_spend_cannot_be_enabled(self):
        for key, value in [('REAL_LLM_ENABLED','true'), ('REAL_EMBEDDING_ENABLED','true'), ('PAID_CALLS_APPROVED','true'),
                           ('LLM_BUDGET_MICRO_USD','3000000'), ('LLM_REQUEST_CAP_MICRO_USD','10000')]:
            with self.subTest(key=key):
                self.assertIn('real_provider_budget_not_supported', preflight(production() | {key:value})['issues'])
    def test_upload_request_token_limits(self):
        for key, value in [('MAX_UPLOAD_BYTES','20971521'), ('REQUESTS_PER_MINUTE','0'),
                           ('REQUEST_TIMEOUT_SECONDS','121'), ('LLM_MAX_RETRIES','2'),
                           ('LLM_MAX_OUTPUT_TOKENS','0'), ('LLM_MAX_INPUT_TOKENS','100001')]:
            with self.subTest(key=key): self.assertFalse(preflight({key:value})['startup_allowed'])
    def test_strict_environment_types(self):
        for key, value in [('CSRF_ENABLED','1'), ('SECURE_COOKIE','yes'), ('MAX_UPLOAD_BYTES','NaN'), ('APP_ENV',42)]:
            with self.subTest(key=key): self.assertEqual(preflight({key:value})['settings_status'], 'INVALID')
    def test_local_cloud_settings_do_not_silently_fallback(self):
        for change in [{'DATABASE_BACKEND':'postgresql'}, {'STORAGE_BACKEND':'supabase'},
                       {'AUTH_PROVIDER':'supabase'}, {'DATABASE_URL':MARKER}]:
            self.assertFalse(preflight(change)['startup_allowed'])
    def test_backups_are_declarations_only(self):
        r = preflight(production())
        self.assertEqual(r['backup_restore_verification'], 'NOT_VERIFIED')
        self.assertIn('coordinated_backup_restore_not_verified', r['implementation_blockers'])
        self.assertIn('backup_restore_plan_required', preflight(production() | {'BACKUP_STRATEGY':'unconfigured'})['issues'])
    def test_expected_role(self):
        self.assertIn('runtime_role_mismatch', preflight({'APP_ROLE':'workflow_worker'}, expected_role='api')['issues'])
    def test_valid_api_worker_pair_remains_blocked(self):
        r = preflight(production(), peer=production('workflow_worker'))
        self.assertEqual(r['settings_status'], 'VALID'); self.assertEqual(r['status'], 'BLOCKED')
    def test_invalid_pair_roles(self):
        self.assertIn('api_worker_role_mismatch', preflight(production(), peer=production())['issues'])
    def test_pair_database_scope(self):
        env = production('chunk_worker'); env['DATABASE_URL'] = env['DATABASE_URL'].replace('/app?', '/other?')
        self.assertIn('api_worker_database_target_mismatch', preflight(production(), peer=env)['issues'])
    def test_pair_distinct_db_credentials_allowed(self):
        env = production('chunk_worker'); env['DATABASE_URL'] = env['DATABASE_URL'].replace('synthetic:synthetic-only', 'worker:worker-only')
        self.assertEqual(preflight(production(), peer=env)['settings_status'], 'VALID')
    def test_pair_origin_storage_isolation(self):
        for key, value in [('STORAGE_BUCKET','other-originals'), ('APP_ORIGIN','https://other.synthetic.example'), ('APP_ENV','test')]:
            self.assertIn('api_worker_contract_mismatch', preflight(production(), peer=production('parse_worker') | {key:value})['issues'])
    def test_no_sockets_or_client_construction(self):
        with patch.object(socket.socket,'connect',side_effect=AssertionError('network forbidden')), \
             patch.object(socket,'getaddrinfo',side_effect=AssertionError('DNS forbidden')), \
             patch('httpx.Client',side_effect=AssertionError('client forbidden')):
            self.assertEqual(preflight(production())['status'], 'BLOCKED')
    def test_secret_redaction_on_valid_and_invalid(self):
        env = production() | {'DATABASE_URL':MARKER,'STORAGE_SERVER_KEY':MARKER,'SUPABASE_AUTH_API_KEY':MARKER}
        s = load_settings(env)
        self.assertNotIn(MARKER, repr(s)); self.assertNotIn(MARKER, s.model_dump_json())
        self.assertNotIn(MARKER, json.dumps(preflight(env)))
        with patch.dict(os.environ, env, clear=True):
            try: ensure_start_environment('api')
            except SettingsRejected as error: self.assertNotIn(MARKER,str(error))
            else: self.fail('unsafe startup')
    def test_api_factory_blocks_before_repository_creation(self):
        from apps.api.main import create_app
        with patch.dict(os.environ, production(), clear=True), patch('apps.api.main.Repository') as repo:
            with self.assertRaises(SettingsRejected): create_app()
            repo.assert_not_called()
    def test_startup_role_guard_for_all_workers(self):
        for role in ('parse_worker', 'chunk_worker', 'workflow_worker'):
            with patch.dict(os.environ, {'APP_ENV':'test','APP_ROLE':'api'}, clear=True):
                with self.assertRaises(SettingsRejected): ensure_start_environment(role)
    def test_cli_exit_codes_and_no_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp)/'config.json'
            for env, code in [({'APP_ENV':'test'},0), (production(),2), (production()|{'DATABASE_URL':MARKER},1)]:
                cfg.write_text(json.dumps(env))
                p = subprocess.run([sys.executable,'-B',str(CLI),'--config-json',str(cfg)],capture_output=True,text=True)
                self.assertEqual(p.returncode,code,p.stderr); self.assertNotIn(MARKER,p.stdout+p.stderr)
                self.assertEqual(json.loads(p.stdout)['connectivity'],'NOT_CHECKED')
    def test_unknown_duplicate_and_nonstring_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp)/'config.json'
            for text in ('{"APP_ENV":"test","APP_ENV":"local"}', '{"APP_EN":"production"}', '{"APP_ENV":42}'):
                cfg.write_text(text)
                with self.assertRaises(ValueError): read_config(cfg)
    def test_frozen_strict_settings(self):
        with self.assertRaises(ValueError): RuntimeSettings.model_validate({'secure_cookie':'false'})
        with self.assertRaises(ValueError): RuntimeSettings.model_validate({'pretend_adapter_ready':True})

    def test_cli_argument_error_is_redacted(self):
        p = subprocess.run([sys.executable, '-B', str(CLI), '--role', MARKER], capture_output=True, text=True)
        self.assertEqual(p.returncode, 1)
        self.assertNotIn(MARKER, p.stdout + p.stderr)
    def test_bad_json_does_not_echo_input_or_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / (MARKER + '.json'); cfg.write_text('{"SECRET": "' + MARKER)
            p = subprocess.run([sys.executable, '-B', str(CLI), '--config-json', str(cfg)], capture_output=True, text=True)
            self.assertEqual(p.returncode, 1); self.assertNotIn(MARKER, p.stdout + p.stderr)
    def test_guard_worker_commands_before_io(self):
        for module in ('worker', 'chunk_worker', 'workflow_worker'):
            with tempfile.TemporaryDirectory() as tmp:
                target = Path(tmp) / 'must-not-be-created'
                env = dict(os.environ, APP_ENV='production')
                p = subprocess.run([sys.executable, '-B', '-m', 'apps.api.' + module,
                                    '--data-dir', str(target), '--institution-id', 'synthetic', '--once'],
                                   capture_output=True, text=True, cwd=ROOT, env=env)
                self.assertNotEqual(p.returncode, 0)
                self.assertIn('runtime_start_blocked', p.stderr)
                self.assertFalse(target.exists())
    def test_standard_api_import_blocks_before_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, APP_ENV='production')
            env['PYTHONPATH'] = str(ROOT) + os.pathsep + env.get('PYTHONPATH', '')
            p = subprocess.run([sys.executable, '-B', '-c', 'import apps.api.main'],
                               capture_output=True, text=True, cwd=tmp, env=env)
            self.assertNotEqual(p.returncode, 0)
            self.assertIn('runtime_start_blocked', p.stderr)
            self.assertFalse((Path(tmp) / 'work').exists())
