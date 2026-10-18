"""Isolated, simulation-only cost ledger. Integer micro-USD, never real payment authority."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import re
import secrets
import sqlite3
import time
from .errors import DomainError
from .models import Principal


def integer(value, low=0, high=1_000_000_000):
    if type(value) is not int or not low <= value <= high:
        raise DomainError('invalid_simulation_budget', 422)
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}', value):
        raise DomainError('invalid_budget_identifier', 422)
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class Reservation:
    max_input_tokens: int
    max_output_tokens: int
    input_rate: int  # micro-USD per million tokens, not floats
    output_rate: int
    attempts: int = 2
    request_cap: int = 50_000

    def __post_init__(self):
        integer(self.max_input_tokens, 1, 100_000)
        integer(self.max_output_tokens, 0, 32_768)
        integer(self.input_rate, 1)
        integer(self.output_rate)
        integer(self.attempts, 1, 2)
        integer(self.request_cap, 1)
        if self.total > self.request_cap:
            raise DomainError('request_budget_exceeded', 402)

    def cost(self, inputs, outputs):
        integer(inputs, 0, self.max_input_tokens)
        integer(outputs, 0, self.max_output_tokens)
        return (inputs * self.input_rate + outputs * self.output_rate + 999_999) // 1_000_000

    @property
    def per_attempt(self):
        return self.cost(self.max_input_tokens, self.max_output_tokens)

    @property
    def total(self):
        return self.per_attempt * self.attempts


@dataclass(frozen=True)
class BudgetClaim:
    request_id: str
    token: str = field(repr=False)


SCHEMA = [
    'CREATE TABLE IF NOT EXISTS provider_budget_meta(version INTEGER NOT NULL)',
    '''CREATE TABLE IF NOT EXISTS provider_budget_accounts(
    institution TEXT PRIMARY KEY, cap INTEGER NOT NULL CHECK(cap>0),
    held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0), spent INTEGER NOT NULL DEFAULT 0 CHECK(spent>=0),
    CHECK(held+spent<=cap))''',
    '''CREATE TABLE IF NOT EXISTS provider_budget_jobs(
    institution TEXT NOT NULL REFERENCES provider_budget_accounts(institution), id TEXT NOT NULL,
    cap INTEGER NOT NULL CHECK(cap>0), held INTEGER NOT NULL DEFAULT 0 CHECK(held>=0),
    spent INTEGER NOT NULL DEFAULT 0 CHECK(spent>=0), cancelled INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(institution,id), CHECK(held+spent<=cap))''',
    '''CREATE TABLE IF NOT EXISTS provider_budget_requests(
    institution TEXT NOT NULL, id TEXT NOT NULL, job TEXT NOT NULL, fingerprint TEXT NOT NULL,
    owner_hash TEXT NOT NULL, state TEXT NOT NULL, held INTEGER NOT NULL CHECK(held>=0),
    spent INTEGER NOT NULL DEFAULT 0 CHECK(spent>=0), attempts INTEGER NOT NULL DEFAULT 0,
    max_input INTEGER NOT NULL, max_output INTEGER NOT NULL, input_rate INTEGER NOT NULL,
    output_rate INTEGER NOT NULL, attempt_limit INTEGER NOT NULL, request_cap INTEGER NOT NULL,
    per_attempt INTEGER NOT NULL, expires REAL NOT NULL,
    PRIMARY KEY(institution,id), FOREIGN KEY(institution,job) REFERENCES provider_budget_jobs(institution,id))''',
    '''CREATE TABLE IF NOT EXISTS provider_budget_attempts(
    institution TEXT NOT NULL, request TEXT NOT NULL, number INTEGER NOT NULL, state TEXT NOT NULL,
    inputs INTEGER, outputs INTEGER, charge INTEGER, receipt_hash TEXT,
    PRIMARY KEY(institution,request,number),
    FOREIGN KEY(institution,request) REFERENCES provider_budget_requests(institution,id))''',
    '''CREATE TABLE IF NOT EXISTS provider_budget_events(
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,institution TEXT NOT NULL,job TEXT NOT NULL,
    request TEXT NOT NULL,kind TEXT NOT NULL,delta_held INTEGER NOT NULL,delta_spent INTEGER NOT NULL,
    created REAL NOT NULL)''',
]


class SimulationBudgetLedger:
    """Not installed into the application DB; unknown charges retain a durable hold."""
    simulation_only = True

    def __init__(self, path, *, clock=time.time, ttl=120):
        self.path = Path(path)
        if self.path.is_symlink() or self.path.suffix != '.sqlite3':
            raise DomainError('invalid_budget_database', 422)
        if not isinstance(ttl, (int, float)) or isinstance(ttl, bool) or not 1 <= ttl <= 3600:
            raise DomainError('invalid_budget_ttl', 422)
        self.clock, self.ttl = clock, ttl
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if any(not t.startswith('provider_budget_') and t != 'sqlite_sequence' for t in tables):
                raise DomainError('budget_requires_isolated_database', 422)
            if 'provider_budget_meta' in tables:
                versions = [r[0] for r in db.execute('SELECT version FROM provider_budget_meta')]
                if versions != [1]:
                    raise DomainError('unsupported_budget_schema', 422)
            for statement in SCHEMA:
                db.execute(statement)
            if 'provider_budget_meta' not in tables:
                db.execute('INSERT INTO provider_budget_meta VALUES(1)')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def institution(principal, *, reconciliation=False):
        roles = ('manager',) if reconciliation else ('manager', 'worker')
        if not isinstance(principal, Principal) or principal.role not in roles:
            raise DomainError('budget_access_denied', 403)
        if not principal.institution_id or len(principal.institution_id) > 200:
            raise DomainError('budget_access_denied', 403)
        return principal.institution_id

    def provision(self, principal, cap):
        institution = self.institution(principal, reconciliation=True)
        integer(cap, 1)
        with self.transaction() as db:
            row = db.execute('SELECT cap FROM provider_budget_accounts WHERE institution=?', (institution,)).fetchone()
            if row and row['cap'] != cap:
                raise DomainError('budget_configuration_conflict')
            db.execute('INSERT OR IGNORE INTO provider_budget_accounts(institution,cap) VALUES(?,?)', (institution, cap))

    def open_job(self, principal, job, cap):
        institution = self.institution(principal)
        identifier(job); integer(cap, 1)
        with self.transaction() as db:
            row = db.execute('SELECT * FROM provider_budget_jobs WHERE institution=? AND id=?', (institution,job)).fetchone()
            if row and (row['cap'] != cap or row['cancelled']):
                raise DomainError('budget_job_conflict')
            account = db.execute('SELECT cap FROM provider_budget_accounts WHERE institution=?', (institution,)).fetchone()
            if not account or cap > account['cap']:
                raise DomainError('job_budget_exceeded', 402)
            db.execute('INSERT OR IGNORE INTO provider_budget_jobs(institution,id,cap) VALUES(?,?,?)', (institution,job,cap))

    def _row(self, db, institution, request):
        row = db.execute('SELECT * FROM provider_budget_requests WHERE institution=? AND id=?', (institution,request)).fetchone()
        if not row:
            raise DomainError('budget_request_not_found', 404)
        return row

    def _owned(self, db, institution, claim):
        row = self._row(db,institution,claim.request_id)
        if not secrets.compare_digest(row['owner_hash'],digest(claim.token)):
            raise DomainError('invalid_budget_claim', 403)
        return row

    def _move(self, db, row, held, spent, kind):
        db.execute('UPDATE provider_budget_accounts SET held=held+?,spent=spent+? WHERE institution=?',
                   (held,spent,row['institution']))
        db.execute('UPDATE provider_budget_jobs SET held=held+?,spent=spent+? WHERE institution=? AND id=?',
                   (held,spent,row['institution'],row['job']))
        db.execute('UPDATE provider_budget_requests SET held=held+?,spent=spent+? WHERE institution=? AND id=?',
                   (held,spent,row['institution'],row['id']))
        db.execute('INSERT INTO provider_budget_events(institution,job,request,kind,delta_held,delta_spent,created) VALUES(?,?,?,?,?,?,?)',
                   (row['institution'],row['job'],row['id'],kind,held,spent,self.clock()))

    def reserve(self, principal, job, request, fingerprint, reservation):
        institution = self.institution(principal)
        identifier(job); identifier(request)
        if type(reservation) is not Reservation or not re.fullmatch('[0-9a-f]{64}', fingerprint):
            raise DomainError('invalid_budget_reservation', 422)
        token = secrets.token_hex(32)
        with self.transaction() as db:
            old = db.execute('SELECT * FROM provider_budget_requests WHERE institution=? AND id=?', (institution,request)).fetchone()
            signature = (reservation.max_input_tokens,reservation.max_output_tokens,reservation.input_rate,
                         reservation.output_rate,reservation.attempts,reservation.request_cap)
            if old:
                previous = tuple(old[k] for k in ('max_input','max_output','input_rate','output_rate','attempt_limit','request_cap'))
                if old['job'] != job or old['fingerprint'] != fingerprint or previous != signature:
                    raise DomainError('budget_idempotency_conflict')
                return None  # No second owner, send, or charge; result replay belongs to the caller's result store.
            account = db.execute('SELECT * FROM provider_budget_accounts WHERE institution=?', (institution,)).fetchone()
            work = db.execute('SELECT * FROM provider_budget_jobs WHERE institution=? AND id=?', (institution,job)).fetchone()
            if not account or not work:
                raise DomainError('budget_job_not_found', 404)
            if work['cancelled']:
                raise DomainError('budget_job_cancelled')
            if any(r['held']+r['spent']+reservation.total > r['cap'] for r in (account,work)):
                raise DomainError('simulation_budget_exceeded', 402)
            db.execute('''INSERT INTO provider_budget_requests(institution,id,job,fingerprint,owner_hash,state,held,
                max_input,max_output,input_rate,output_rate,attempt_limit,request_cap,per_attempt,expires)
                VALUES(?,?,?,?,?,'reserved',0,?,?,?,?,?,?,?,?)''',
                (institution,request,job,fingerprint,digest(token),*signature,reservation.per_attempt,self.clock()+self.ttl))
            row = self._row(db,institution,request)
            self._move(db,row,reservation.total,0,'reserved')
        return BudgetClaim(request,token)

    def start(self, principal, claim):
        institution = self.institution(principal)
        with self.transaction() as db:
            row = self._owned(db,institution,claim)
            if row['state'] != 'reserved' or row['attempts'] >= row['attempt_limit'] or self.clock() >= row['expires']:
                raise DomainError('budget_attempt_not_allowed')
            n = row['attempts']+1
            db.execute("UPDATE provider_budget_requests SET state='in_flight',attempts=?,expires=? WHERE institution=? AND id=?",
                       (n,self.clock()+self.ttl,institution,row['id']))
            db.execute("INSERT INTO provider_budget_attempts(institution,request,number,state) VALUES(?,?,?,'in_flight')",
                       (institution,row['id'],n))
            self._move(db,row,0,0,'attempt_started')
            return n

    @staticmethod
    def _usage(row, inputs, outputs):
        integer(inputs,0,row['max_input']); integer(outputs,0,row['max_output'])
        return (inputs*row['input_rate']+outputs*row['output_rate']+999_999)//1_000_000

    def record(self, principal, claim, attempt, inputs, outputs, receipt_hash):
        institution = self.institution(principal)
        if not re.fullmatch('[0-9a-f]{64}',receipt_hash):
            raise DomainError('invalid_cost_receipt',422)
        with self.transaction() as db:
            row = self._owned(db,institution,claim)
            charge = self._usage(row,inputs,outputs)
            old = db.execute('SELECT * FROM provider_budget_attempts WHERE institution=? AND request=? AND number=?',
                             (institution,row['id'],attempt)).fetchone()
            if old and old['state'] == 'settled':
                if (old['inputs'],old['outputs'],old['receipt_hash']) != (inputs,outputs,receipt_hash):
                    raise DomainError('cost_receipt_conflict')
                return  # Idempotent settlement, including after a process restart.
            if (row['state'] != 'in_flight' or row['attempts'] != attempt or not old
                    or self.clock() >= row['expires']):
                raise DomainError('budget_settlement_not_allowed')
            self._move(db,row,-row['per_attempt'],charge,'usage_settled')
            db.execute("UPDATE provider_budget_attempts SET state='settled',inputs=?,outputs=?,charge=?,receipt_hash=? WHERE institution=? AND request=? AND number=?",
                       (inputs,outputs,charge,receipt_hash,institution,row['id'],attempt))
            db.execute("UPDATE provider_budget_requests SET state='reserved' WHERE institution=? AND id=?", (institution,row['id']))

    def finish(self, principal, claim, outcome):
        institution = self.institution(principal)
        if outcome not in ('completed','rejected','failed','cancelled'):
            raise DomainError('invalid_budget_outcome',422)
        with self.transaction() as db:
            row = self._owned(db,institution,claim)
            if row['state'] == outcome:
                return
            if row['state'] != 'reserved':
                raise DomainError('budget_finish_not_allowed')
            self._move(db,row,-row['held'],0,'reservation_released')
            db.execute('UPDATE provider_budget_requests SET state=? WHERE institution=? AND id=?', (outcome,institution,row['id']))

    def _unknown(self, db, row):
        if row['state'] == 'uncertain':
            return
        if row['state'] != 'in_flight':
            raise DomainError('budget_not_in_flight')
        self._move(db,row,-(row['held']-row['per_attempt']),0,'unused_retry_released')
        db.execute("UPDATE provider_budget_requests SET state='uncertain' WHERE institution=? AND id=?", (row['institution'],row['id']))
        db.execute("UPDATE provider_budget_attempts SET state='unknown' WHERE institution=? AND request=? AND number=?",
                   (row['institution'],row['id'],row['attempts']))

    def unknown(self, principal, claim):
        institution = self.institution(principal)
        with self.transaction() as db:
            self._unknown(db,self._owned(db,institution,claim))

    def _cancel(self, db, row):
        if row['state'] == 'in_flight':
            self._unknown(db,row)
        elif row['state'] == 'reserved':
            self._move(db,row,-row['held'],0,'cancelled')
            db.execute("UPDATE provider_budget_requests SET state='cancelled' WHERE institution=? AND id=?", (row['institution'],row['id']))

    def cancel(self, principal, request):
        institution = self.institution(principal)
        with self.transaction() as db:
            self._cancel(db,self._row(db,institution,request))

    def cancel_job(self, principal, job):
        institution = self.institution(principal)
        with self.transaction() as db:
            work = db.execute('SELECT * FROM provider_budget_jobs WHERE institution=? AND id=?',(institution,job)).fetchone()
            if not work:raise DomainError('budget_job_not_found',404)
            db.execute('UPDATE provider_budget_jobs SET cancelled=1 WHERE institution=? AND id=?',(institution,job))
            for row in db.execute('SELECT * FROM provider_budget_requests WHERE institution=? AND job=?',(institution,job)).fetchall():
                self._cancel(db,row)

    def recover(self, principal):
        institution = self.institution(principal)
        with self.transaction() as db:
            rows = db.execute("SELECT * FROM provider_budget_requests WHERE institution=? AND expires<=? AND state IN ('reserved','in_flight')",(institution,self.clock())).fetchall()
            for row in rows:self._cancel(db,row)
            return len(rows)

    def reconcile(self, principal, request, inputs, outputs, receipt_hash):
        institution = self.institution(principal,reconciliation=True)
        if not re.fullmatch('[0-9a-f]{64}',receipt_hash):raise DomainError('invalid_cost_receipt',422)
        with self.transaction() as db:
            row = self._row(db,institution,request)
            charge = self._usage(row,inputs,outputs)
            last = db.execute('SELECT * FROM provider_budget_attempts WHERE institution=? AND request=? AND number=?', (institution,request,row['attempts'])).fetchone()
            if row['state']=='reconciled' and last and (last['inputs'],last['outputs'],last['receipt_hash'])==(inputs,outputs,receipt_hash):return
            if row['state']!='uncertain' or not last or last['state']!='unknown':
                raise DomainError('budget_reconciliation_not_allowed')
            self._move(db,row,-row['held'],charge,'uncertain_reconciled')
            db.execute("UPDATE provider_budget_attempts SET state='reconciled',inputs=?,outputs=?,charge=?,receipt_hash=? WHERE institution=? AND request=? AND number=?",
                       (inputs,outputs,charge,receipt_hash,institution,request,row['attempts']))
            db.execute("UPDATE provider_budget_requests SET state='reconciled' WHERE institution=? AND id=?",(institution,request))

    def request(self, principal, request):
        institution = self.institution(principal)
        with self.transaction() as db:
            row = dict(self._row(db,institution,request));row.pop('owner_hash');return row

    def balance(self, principal):
        institution = self.institution(principal)
        with self.transaction() as db:
            row = db.execute('SELECT * FROM provider_budget_accounts WHERE institution=?',(institution,)).fetchone()
            if not row:raise DomainError('budget_account_not_found',404)
            return {**dict(row),'currency':'SIMULATED_USD','actual_spent':0}

    def events(self, principal):
        institution = self.institution(principal)
        with self.transaction() as db:
            return [dict(r) for r in db.execute('SELECT * FROM provider_budget_events WHERE institution=? ORDER BY sequence',(institution,))]
