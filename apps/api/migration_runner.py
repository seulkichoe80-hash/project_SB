"""Ordered additive migration coordinator. Remote execution remains explicitly blocked."""
from pathlib import Path
import hashlib
import time
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from typing import Literal
from .postgres import PostgresDatabase, PostgresRepository
from .private_storage import StorageRegistry

ROOT = Path(__file__).resolve().parents[2]


class MigrationPlan(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra='forbid', hide_input_in_errors=True)
    database_url: SecretStr = Field(repr=False)
    application_schema: str = Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    budget_schema: str = Field(pattern=r'^[a-z][a-z0-9_]{0,62}$')
    target: Literal['isolated_local', 'production'] = 'isolated_local'

    @model_validator(mode='after')
    def schemas(self):
        if (self.application_schema == self.budget_schema or any(
                s in ('public','auth','storage','extensions') or s.startswith('pg_') for s in (self.application_schema, self.budget_schema))):
            raise ValueError('separate_private_schemas_required')
        return self


class MigrationBlocked(RuntimeError):
    def __init__(self, stage, code):
        self.stage, self.code = stage, code
        super().__init__('migration_blocked:' + stage + ':' + code)


def verify_storage(repository):
    digest = hashlib.sha256((ROOT/'migrations/storage/001_private_storage.sql').read_bytes()).hexdigest()
    with repository.transaction() as db:
        rows = db.connection.execute('SELECT version,checksum FROM private_storage_schema').fetchall()
        if len(rows) != 1 or rows[0][0] != 1 or rows[0][1] != digest:
            raise ValueError('storage_migration_checksum_mismatch')
        db.connection.execute('SELECT object_id,institution_id,bucket,object_path,sha256,size,state,attempts,error_code,created_at FROM private_storage_objects WHERE 1=0')
        db.connection.execute('SELECT backup_id,manifest_sha256,result_digest,state FROM private_storage_restores WHERE 1=0')


class MigrationRunner:
    """Per-step transactions, resumable after failure; no destructive rollback.

    Session locks cover BOTH schema names in global order. Existing per-schema
    migration transaction locks/checksums and application transaction_guard remain.
    API/worker startup should use verify; apply is an explicit operator operation.
    """
    def __init__(self, plan):
        if type(plan) is not MigrationPlan:
            raise MigrationBlocked('configuration', 'invalid_plan')
        try:
            self.plan = MigrationPlan.model_validate(plan.model_dump(warnings=False))
        except ValueError:
            raise MigrationBlocked('configuration', 'invalid_plan') from None
        if self.plan.target != 'isolated_local':
            raise MigrationBlocked('configuration', 'remote_execution_not_approved')
        try:
            self.application = PostgresDatabase(self.plan.database_url.get_secret_value(), self.plan.application_schema, local_test=True)
            self.budget = PostgresDatabase(self.plan.database_url.get_secret_value(), self.plan.budget_schema, local_test=True)
        except ValueError:
            raise MigrationBlocked('configuration', 'isolated_loopback_database_required') from None

    def __repr__(self):
        return '<MigrationRunner redacted local-execution-only>'

    def run(self, *, mode='verify'):
        if mode not in ('apply', 'verify'):
            raise MigrationBlocked('configuration', 'invalid_mode')
        stage = 'lock'; completed = []
        try:
            with self.application._connect() as guard:
                keys = sorted(int(hashlib.sha256(('runtime-migration:'+s).encode()).hexdigest()[:15], 16)
                              for s in (self.plan.application_schema, self.plan.budget_schema))
                deadline = time.monotonic()+10
                for key in keys:
                    while not guard.execute('SELECT pg_try_advisory_lock(%s) AS locked', (key,)).fetchone()['locked']:
                        if time.monotonic() >= deadline:
                            raise MigrationBlocked('lock', 'migration_lock_timeout')
                        time.sleep(.05)
                stage = 'application'
                applied = self.application.migrate('application') if mode == 'apply' else False
                self.application.verify('application')
                completed.append({'stage': stage, 'applied': applied})
                stage = 'budget'
                applied = self.budget.migrate('budget') if mode == 'apply' else False
                self.budget.verify('budget')
                completed.append({'stage': stage, 'applied': applied})
                stage = 'storage'
                repository = PostgresRepository(self.application)
                applied = StorageRegistry(repository).migrate() if mode == 'apply' else False
                verify_storage(repository)
                completed.append({'stage': stage, 'applied': applied})
            return {'status': 'READY', 'mode': mode, 'target': 'ISOLATED_LOCAL', 'steps': completed,
                    'production_ready': False, 'recovery': 'preserve_data_fix_cause_then_rerun_apply_or_verify'}
        except MigrationBlocked as blocked:
            error = MigrationBlocked(blocked.stage, blocked.code)
        except Exception as failure:
            # Preserve only allowlisted static diagnoses; never arbitrary text.
            allowed={'postgres_migration_version_mismatch','postgres_schema_not_empty',
                     'postgres_extension_version_mismatch','postgres_transaction_guard_missing',
                     'postgres_migration_required','postgres_connection_failed','postgres_migration_failed',
                     'postgres_transaction_failed','unsupported_private_storage_schema',
                     'unknown_private_storage_schema','storage_migration_checksum_mismatch'}
            code=getattr(failure,'code',None)
            if code is None and len(failure.args)==1 and type(failure.args[0]) is str:code=failure.args[0]
            if type(code) is not str or code not in allowed:code='migration_lock_failed' if stage=='lock' else 'verify_or_apply_failed'
            error = MigrationBlocked(stage, code)
        raise error
