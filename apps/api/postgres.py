"""Explicit PostgreSQL persistence. SQLite stays the default; no connections on import."""
from contextlib import contextmanager
import hashlib
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from .errors import DomainError
from .repository import DocumentUnitOfWork
from .auth_store import AuthStore
from .provider_budget import SimulationBudgetLedger

ROOT = Path(__file__).resolve().parents[2]


class PostgresFailure(RuntimeError):
    """Never expose DSNs, SQL parameter values, or raw server diagnostics."""


def compile_query(statement):
    """Compile shared qmark DML, preserving quoted question marks and percent literals.

    PostgreSQL-specific DDL lives in explicit migrations. No arbitrary SQLite DDL emulation.
    """
    sql = statement.strip()
    if re.match(r'INSERT\s+OR\s+REPLACE\s+INTO\s+auth_login_limits\b', sql, re.I):
        sql = 'INSERT INTO auth_login_limits(client_hash,"window",attempts) VALUES(?,?,?) ON CONFLICT(client_hash) DO UPDATE SET "window"=excluded."window",attempts=excluded.attempts'
    ignore = bool(re.match(r'INSERT\s+OR\s+IGNORE\b', sql, re.I))
    if ignore:
        sql = re.sub(r'^INSERT\s+OR\s+IGNORE\b', 'INSERT', sql, flags=re.I).rstrip(';') + ' ON CONFLICT DO NOTHING'
    out = []; state = None; index = 0
    while index < len(sql):
        c = sql[index]
        if state:
            out.append('%%' if c == '%' else c)
            if c == state:
                if index + 1 < len(sql) and sql[index + 1] == state:
                    out.append(state); index += 1
                else: state = None
        elif c in "'\"":
            state = c; out.append(c)
        elif c == '?': out.append('%s')
        elif c == '%': out.append('%%')
        elif c.isalpha() or c == '_':
            end = index + 1
            while end < len(sql) and (sql[end].isalnum() or sql[end] == '_'): end += 1
            word = sql[index:end]
            out.append('"window"' if word.lower() == 'window' else word)
            index = end - 1
        else: out.append(c)
        index += 1
    return ''.join(out)


class Row:
    """SQLite-compatible positional AND named access, including duplicate column labels."""
    def __init__(self, names, values): self.names, self.data = names, values
    def __getitem__(self, key):
        return self.data[key] if isinstance(key, int) else self.data[self.names.index(key)]
    def keys(self): return self.names
    def values(self): return self.data
    def __iter__(self): return iter(self.data)
    def __len__(self): return len(self.data)
    def __eq__(self, other):
        return dict(self) == dict(other) if hasattr(other, 'keys') else False


class Cursor:
    def __init__(self, cursor):
        self.cursor = cursor
        self.names = [c.name for c in cursor.description] if cursor.description else []
    @property
    def rowcount(self): return self.cursor.rowcount
    def fetchone(self):
        value = self.cursor.fetchone()
        return None if value is None else Row(self.names, value)
    def fetchall(self): return [Row(self.names, value) for value in self.cursor.fetchall()]
    def __iter__(self): return iter(self.fetchall())


class Connection:
    def __init__(self, raw): self.raw = raw
    def execute(self, sql, parameters=()):
        try:
            from psycopg.rows import tuple_row
            cursor = self.raw.cursor(row_factory=tuple_row)
            cursor.execute(compile_query(sql), parameters)
            return Cursor(cursor)
        except Exception:
            # Transaction owner rolls back; suppress unsafe server details.
            raise PostgresFailure('postgres_statement_failed') from None


class PostgresDatabase:
    def __init__(self, dsn, schema, *, local_test=False):
        if not isinstance(dsn, str) or not re.fullmatch(r'[a-z][a-z0-9_]{0,62}', schema or '') or schema == 'public' or schema.startswith('pg_'):
            raise ValueError('invalid_postgres_configuration')
        try:
            p = urlsplit(dsn)
            if local_test:
                valid = (p.scheme == 'postgresql' and p.hostname == '127.0.0.1' and p.port is not None
                         and p.username is not None and bool(p.path) and not p.query and not p.fragment)
            else:
                from .runtime_settings import valid_database_url
                valid = valid_database_url(dsn)
            if not valid: raise ValueError()
        except ValueError:
            raise ValueError('invalid_postgres_configuration') from None
        self._dsn, self.schema, self.local_test = dsn, schema, local_test
    def __repr__(self): return '<PostgresDatabase redacted>'
    def _connect(self):
        try:
            import psycopg
            from psycopg.rows import dict_row
            from psycopg import IsolationLevel
            connection = psycopg.connect(self._dsn, connect_timeout=5, row_factory=dict_row)
            connection.isolation_level = IsolationLevel.READ_COMMITTED
            return connection
        except Exception:
            raise PostgresFailure('postgres_connection_failed') from None
    def _path(self, db):
        from psycopg import sql
        db.execute(sql.SQL('SET LOCAL search_path TO {}, pg_catalog').format(sql.Identifier(self.schema)))
        db.execute("SET LOCAL lock_timeout='10s'")
        db.execute("SET LOCAL statement_timeout='30s'")
    def migrate(self, kind='application'):
        if kind not in ('application', 'budget'): raise ValueError('invalid_migration_kind')
        migration = ROOT / 'migrations/postgresql' / ('001_' + kind + '.sql')
        data = migration.read_text(); checksum = hashlib.sha256(data.encode()).hexdigest()
        from psycopg import sql
        try:
            with self._connect() as db:
                db.execute('SELECT pg_advisory_xact_lock(%s)', (int(hashlib.sha256(self.schema.encode()).hexdigest()[:15],16),))
                db.execute(sql.SQL('CREATE SCHEMA IF NOT EXISTS {}').format(sql.Identifier(self.schema)))
                self._path(db)
                db.execute('CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY, kind TEXT NOT NULL, checksum TEXT NOT NULL)')
                rows = db.execute('SELECT * FROM migrations ORDER BY version').fetchall()
                if rows:
                    if len(rows) != 1 or rows[0]['version'] != 1 or rows[0]['kind'] != kind or rows[0]['checksum'] != checksum:
                        raise PostgresFailure('postgres_migration_version_mismatch')
                    return False
                # Never adopt an existing unknown schema with IF NOT EXISTS tables.
                tables = db.execute('SELECT table_name FROM information_schema.tables WHERE table_schema=%s', (self.schema,)).fetchall()
                if {r['table_name'] for r in tables} != {'migrations'}: raise PostgresFailure('postgres_schema_not_empty')
                db.execute(data, prepare=False)
                db.execute('CREATE TABLE transaction_guard(id INTEGER PRIMARY KEY CHECK(id=1))')
                db.execute('INSERT INTO transaction_guard VALUES(1)')
                db.execute('INSERT INTO migrations VALUES(1,%s,%s)', (kind, checksum))
                return True
        except PostgresFailure: raise
        except Exception: raise PostgresFailure('postgres_migration_failed') from None
    def verify(self, kind):
        checksum = hashlib.sha256((ROOT / 'migrations/postgresql' / ('001_' + kind + '.sql')).read_bytes()).hexdigest()
        try:
            with self._connect() as db:
                self._path(db)
                rows = db.execute('SELECT * FROM migrations ORDER BY version').fetchall()
                if len(rows) != 1 or rows[0]['version'] != 1 or rows[0]['kind'] != kind or rows[0]['checksum'] != checksum:
                    raise PostgresFailure('postgres_migration_version_mismatch')
                if kind == 'application':
                    extensions = db.execute('SELECT name,version FROM schema_extensions').fetchall()
                    if {r['name']:r['version'] for r in extensions} != {'chunks':1,'workflow_jobs':1}:
                        raise PostgresFailure('postgres_extension_version_mismatch')
        except PostgresFailure: raise
        except Exception: raise PostgresFailure('postgres_migration_required') from None
    @contextmanager
    def transaction(self):
        try:
            with self._connect() as raw:
                self._path(raw)
                # Conservatively preserve SQLite BEGIN IMMEDIATE semantics across processes.
                # API/auth/workers using this schema acquire the SAME row before any reads.
                if raw.execute('SELECT id FROM transaction_guard WHERE id=1 FOR UPDATE').fetchone() is None:
                    raise PostgresFailure('postgres_transaction_guard_missing')
                yield Connection(raw)
        except PostgresFailure: raise
        except Exception as error:
            import psycopg
            if isinstance(error, psycopg.Error): raise PostgresFailure('postgres_transaction_failed') from None
            raise


class PostgresRepository:
    dialect = 'postgresql'
    def __init__(self, database):
        self.database = database
        database.verify('application')
    @contextmanager
    def transaction(self):
        with self.database.transaction() as connection:
            yield DocumentUnitOfWork(connection)
    def auth_store(self): return PostgresAuthStore(self.database)


class PostgresAuthStore(AuthStore):
    def __init__(self, database):
        self.database, self.backup = database, None
        database.verify('application')
    def transaction(self): return self.database.transaction()


class PostgresBudgetLedger(SimulationBudgetLedger):
    def __init__(self, database, *, clock=time.time, ttl=120):
        if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not 1 <= ttl <= 3600:
            raise DomainError('invalid_budget_ttl',422)
        self.database, self.clock, self.ttl = database, clock, ttl
        database.verify('budget')
    def transaction(self): return self.database.transaction()
