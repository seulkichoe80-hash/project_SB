"""SQLite-only parsing persistence and fencing operations."""
import json
import uuid

SCHEMA = '''
CREATE TABLE IF NOT EXISTS parse_jobs (
 id TEXT PRIMARY KEY, version_id TEXT NOT NULL UNIQUE REFERENCES versions(id),
 state TEXT NOT NULL CHECK(state IN ('queued','processing','completed','failed','cancelled')),
 attempt INTEGER NOT NULL DEFAULT 0, claim_hash TEXT, lease_until REAL,
 error_code TEXT, parser_method TEXT, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS parse_attempts (
 job_id TEXT NOT NULL REFERENCES parse_jobs(id), attempt INTEGER NOT NULL,
 state TEXT NOT NULL, started_at REAL NOT NULL, finished_at REAL, error_code TEXT,
 PRIMARY KEY(job_id,attempt));
CREATE TABLE IF NOT EXISTS source_blocks (
 job_id TEXT NOT NULL, attempt INTEGER NOT NULL, block_id TEXT NOT NULL,
 document_id TEXT NOT NULL REFERENCES documents(id), version_id TEXT NOT NULL REFERENCES versions(id),
 order_index INTEGER NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(job_id,attempt,block_id), UNIQUE(job_id,attempt,order_index),
 FOREIGN KEY(job_id,attempt) REFERENCES parse_attempts(job_id,attempt));
CREATE INDEX IF NOT EXISTS parse_queue ON parse_jobs(state,created_at);
CREATE INDEX IF NOT EXISTS source_versions ON source_blocks(version_id,order_index);
CREATE TRIGGER IF NOT EXISTS source_block_scope BEFORE INSERT ON source_blocks
WHEN NEW.version_id != (SELECT version_id FROM parse_jobs WHERE id=NEW.job_id)
 OR NEW.document_id != (SELECT document_id FROM versions WHERE id=NEW.version_id)
BEGIN SELECT RAISE(ABORT,'source_block_scope_mismatch'); END;
PRAGMA user_version=2;
'''


class ParsingQueries:
    def __init__(self, connection):
        self.db = connection

    def job(self, version_id):
        return self.db.execute('SELECT * FROM parse_jobs WHERE version_id=?', (version_id,)).fetchone()

    def enqueue(self, version_id, clock):
        inserted = self.db.execute('''INSERT OR IGNORE INTO parse_jobs(id,version_id,state,created_at,updated_at)
            VALUES (?,?,'queued',?,?)''', (uuid.uuid4().hex, version_id, clock, clock))
        if inserted.rowcount == 1:
            self.set_version_state(version_id, 'queued')
        return self.job(version_id)

    def backfill(self, clock):
        for row in self.db.execute('''SELECT v.id FROM versions v JOIN documents d ON d.id=v.document_id
            WHERE d.registered=1 AND NOT EXISTS(SELECT 1 FROM parse_jobs j WHERE j.version_id=v.id)''').fetchall():
            self.enqueue(row['id'], clock)

    def event(self, version_id, action, actor, timestamp):
        self.db.execute('INSERT INTO events(version_id,action,actor,created_at) VALUES (?,?,?,?)',
                        (version_id, action, actor, timestamp))

    def set_version_state(self, version_id, state, claim_hash=None):
        self.db.execute('UPDATE versions SET state=?,revision=revision+1,claim_hash=? WHERE id=?',
                        (state, claim_hash, version_id))

    def retry(self, job, clock):
        self.db.execute("UPDATE parse_jobs SET state='queued',claim_hash=NULL,lease_until=NULL,error_code=NULL,updated_at=? WHERE id=?",
                        (clock, job['id']))
        self.set_version_state(job['version_id'], 'queued')

    def recover(self, institution_id, clock, max_attempts):
        jobs = self.db.execute('''SELECT j.* FROM parse_jobs j JOIN versions v ON v.id=j.version_id
            JOIN documents d ON d.id=v.document_id WHERE d.institution_id=? AND d.registered=1
            AND j.state='processing' AND j.lease_until<=?''', (institution_id, clock)).fetchall()
        for job in jobs:
            state = 'queued' if job['attempt'] < max_attempts else 'failed'
            self.db.execute("UPDATE parse_attempts SET state='expired',finished_at=?,error_code='lease_expired' WHERE job_id=? AND attempt=?",
                            (clock, job['id'], job['attempt']))
            self.db.execute('''UPDATE parse_jobs SET state=?,claim_hash=NULL,lease_until=NULL,
                error_code='lease_expired',updated_at=? WHERE id=?''', (state, clock, job['id']))
            self.set_version_state(job['version_id'], state)
        return [dict(j) for j in jobs]

    def claim(self, institution_id, digest, clock, lease_seconds):
        row = self.db.execute('''SELECT j.*,v.document_id,v.sha256,v.format FROM parse_jobs j
            JOIN versions v ON v.id=j.version_id JOIN documents d ON d.id=v.document_id
            WHERE d.institution_id=? AND d.registered=1 AND j.state='queued'
            ORDER BY j.created_at,j.id LIMIT 1''', (institution_id,)).fetchone()
        if not row:
            return None
        attempt = row['attempt'] + 1
        self.db.execute('''UPDATE parse_jobs SET state='processing',attempt=?,claim_hash=?,lease_until=?,
            error_code=NULL,updated_at=? WHERE id=?''', (attempt, digest, clock+lease_seconds, clock, row['id']))
        self.db.execute("INSERT INTO parse_attempts VALUES (?,?,'processing',?,NULL,NULL)", (row['id'], attempt, clock))
        self.set_version_state(row['version_id'], 'processing', digest)
        return {**dict(row), 'attempt': attempt, 'claim_hash': digest, 'state': 'processing', 'lease_until': clock+lease_seconds}

    def owned(self, claim, clock):
        row = self.db.execute('''SELECT j.* FROM parse_jobs j JOIN versions v ON v.id=j.version_id
            JOIN documents d ON d.id=v.document_id WHERE j.id=? AND j.attempt=? AND j.claim_hash=?
            AND j.state='processing' AND j.lease_until>? AND d.registered=1
            AND j.version_id=? AND v.document_id=? AND v.sha256=? AND v.format=?''',
            (claim['id'], claim['attempt'], claim['claim_hash'], clock, claim['version_id'],
             claim['document_id'], claim['sha256'], claim['format'])).fetchone()
        return row is not None

    def renew(self, claim, clock, lease_seconds):
        if not self.owned(claim, clock):
            return False
        self.db.execute('UPDATE parse_jobs SET lease_until=?,updated_at=? WHERE id=?',
                        (clock+lease_seconds, clock, claim['id']))
        return True

    def publish(self, claim, blocks, method, clock):
        for block in blocks:
            self.db.execute('INSERT INTO source_blocks VALUES (?,?,?,?,?,?,?)',
                (claim['id'], claim['attempt'], block.block_id, block.document_id, block.version_id,
                 block.order_index, block.model_dump_json()))
        self.db.execute("UPDATE parse_attempts SET state='completed',finished_at=? WHERE job_id=? AND attempt=?",
                        (clock, claim['id'], claim['attempt']))
        self.db.execute("""UPDATE parse_jobs SET state='completed',parser_method=?,claim_hash=NULL,
            lease_until=NULL,error_code=NULL,updated_at=? WHERE id=?""", (method, clock, claim['id']))
        self.set_version_state(claim['version_id'], 'completed')

    def fail(self, claim, error_code, clock):
        self.db.execute("UPDATE parse_attempts SET state='failed',finished_at=?,error_code=? WHERE job_id=? AND attempt=?",
                        (clock, error_code, claim['id'], claim['attempt']))
        self.db.execute("""UPDATE parse_jobs SET state='failed',error_code=?,claim_hash=NULL,
            lease_until=NULL,updated_at=? WHERE id=?""", (error_code, clock, claim['id']))
        self.set_version_state(claim['version_id'], 'failed')

    def cancel_document(self, document_id, clock):
        self.db.execute("""UPDATE parse_attempts SET state='cancelled',finished_at=?
            WHERE state='processing' AND job_id IN (SELECT j.id FROM parse_jobs j
            JOIN versions v ON v.id=j.version_id WHERE v.document_id=?)""", (clock, document_id))
        self.db.execute("""UPDATE parse_jobs SET state='cancelled',claim_hash=NULL,lease_until=NULL,updated_at=?
            WHERE version_id IN (SELECT id FROM versions WHERE document_id=?)""", (clock, document_id))

    def blocks(self, version_id):
        return [json.loads(row['payload']) for row in self.db.execute('''SELECT b.payload FROM source_blocks b
            JOIN parse_jobs j ON j.id=b.job_id AND j.attempt=b.attempt
            WHERE j.version_id=? AND j.state='completed' ORDER BY b.order_index''', (version_id,))]
