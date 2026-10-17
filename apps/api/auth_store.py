"""Additive authentication schema with SQLite pre-migration backup."""
from pathlib import Path
import sqlite3, secrets, hashlib, time
from contextlib import contextmanager, closing

SCHEMA = [
 "CREATE TABLE IF NOT EXISTS identities(id TEXT PRIMARY KEY, issuer TEXT NOT NULL, subject TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, UNIQUE(issuer,subject))",
 "CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY, name TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1)",
 "CREATE TABLE IF NOT EXISTS memberships(user_id TEXT NOT NULL REFERENCES identities(id), institution_id TEXT NOT NULL REFERENCES organizations(id), role TEXT NOT NULL CHECK(role IN ('reader','manager')), active INTEGER NOT NULL DEFAULT 1, institution_admin INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user_id,institution_id))",
 "CREATE TABLE IF NOT EXISTS sessions(sid_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES identities(id), institution_id TEXT NOT NULL, csrf_hash TEXT NOT NULL, expires REAL NOT NULL, touched REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0)",
 "CREATE TABLE IF NOT EXISTS auth_challenges(nonce_hash TEXT PRIMARY KEY, csrf_hash TEXT NOT NULL, expires REAL NOT NULL)",
 "CREATE TABLE IF NOT EXISTS auth_audit_events(id INTEGER PRIMARY KEY, at REAL NOT NULL, action TEXT NOT NULL, user_id TEXT, institution_id TEXT, outcome TEXT NOT NULL)",
 "CREATE TABLE IF NOT EXISTS auth_login_limits(client_hash TEXT PRIMARY KEY, window REAL NOT NULL, attempts INTEGER NOT NULL)"
]
def digest(value): return hashlib.sha256(value.encode()).hexdigest()

class AuthStore:
    def __init__(self,path:Path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True); self.backup=None
        with closing(sqlite3.connect(self.path)) as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE name='identities'").fetchone()
            if not exists:
                directory=self.path.parent/'auth-backups';directory.mkdir(exist_ok=True)
                self.backup=directory/('pre-auth-'+secrets.token_hex(12)+'.sqlite3')
                with closing(sqlite3.connect(self.backup)) as target: db.backup(target)
            db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
            try:
                for statement in SCHEMA: db.execute(statement)
                db.commit()
            except BaseException: db.rollback();raise
    @contextmanager
    def transaction(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row;db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        try: yield db;db.commit()
        except BaseException:db.rollback();raise
        finally:db.close()
    def audit(self,db,action,user=None,org=None,outcome='ok',at=None):
        db.execute('INSERT INTO auth_audit_events(at,action,user_id,institution_id,outcome) VALUES(?,?,?,?,?)',(time.time() if at is None else at,action,user,org,outcome))
    # Provisioning is a trusted local administration seam, never a public bootstrap API.
    def provision(self,issuer,subject,org,name,role='reader',institution_admin=False):
        if role not in ('reader','manager'):raise ValueError('invalid_browser_role')
        with self.transaction() as db:
            row=db.execute('SELECT id FROM identities WHERE issuer=? AND subject=?',(issuer,subject)).fetchone()
            user=row['id'] if row else secrets.token_hex(16)
            db.execute('INSERT OR IGNORE INTO identities(id,issuer,subject) VALUES(?,?,?)',(user,issuer,subject))
            db.execute('INSERT OR IGNORE INTO organizations(id,name) VALUES(?,?)',(org,name))
            db.execute('INSERT INTO memberships(user_id,institution_id,role,institution_admin) VALUES(?,?,?,?) ON CONFLICT(user_id,institution_id) DO UPDATE SET role=excluded.role,institution_admin=excluded.institution_admin',(user,org,role,int(institution_admin)))
            return user
