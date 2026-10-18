"""Additive durable workflow schema and transactional storage adapter."""
import json
import uuid
from .chunking import digest

SCHEMA = '''
CREATE TABLE IF NOT EXISTS workflow_jobs(
 id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,document_id TEXT NOT NULL REFERENCES documents(id),
 version_id TEXT NOT NULL REFERENCES versions(id),input_snapshot_id TEXT NOT NULL,snapshot TEXT NOT NULL,
 settings TEXT NOT NULL,catalog_hash TEXT NOT NULL,configuration TEXT NOT NULL,input_key TEXT NOT NULL,
 generation INTEGER NOT NULL,state TEXT NOT NULL CHECK(state IN ('queued','processing','completed','failed','cancelled')),
 attempt INTEGER NOT NULL DEFAULT 0 CHECK(attempt BETWEEN 0 AND 3),claim_hash TEXT,lease_until REAL,
 error_code TEXT,error_category TEXT,created_at REAL NOT NULL,
 UNIQUE(institution_id,version_id,input_key),UNIQUE(version_id,generation));
CREATE TABLE IF NOT EXISTS workflow_generations(
 id TEXT PRIMARY KEY,job_id TEXT NOT NULL UNIQUE REFERENCES workflow_jobs(id),
 payload TEXT NOT NULL,payload_hash TEXT NOT NULL,created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS workflow_candidates(
 generation_id TEXT NOT NULL REFERENCES workflow_generations(id),candidate_id TEXT NOT NULL,
 payload TEXT NOT NULL,PRIMARY KEY(generation_id,candidate_id));
CREATE TABLE IF NOT EXISTS workflow_review_issues(
 generation_id TEXT NOT NULL REFERENCES workflow_generations(id),ordinal INTEGER NOT NULL,
 payload TEXT NOT NULL,PRIMARY KEY(generation_id,ordinal));
CREATE TABLE IF NOT EXISTS workflow_form_links(
 generation_id TEXT NOT NULL REFERENCES workflow_generations(id),requirement_id TEXT NOT NULL,
 payload TEXT NOT NULL,PRIMARY KEY(generation_id,requirement_id));
CREATE TABLE IF NOT EXISTS workflow_job_events(
 id INTEGER PRIMARY KEY,job_id TEXT NOT NULL REFERENCES workflow_jobs(id),state TEXT NOT NULL,
 attempt INTEGER NOT NULL,error_code TEXT,error_category TEXT,created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS workflow_claim_queue ON workflow_jobs(institution_id,state,created_at);
CREATE TABLE IF NOT EXISTS schema_extensions(name TEXT PRIMARY KEY,version INTEGER NOT NULL);
INSERT OR IGNORE INTO schema_extensions VALUES ('workflow_jobs',1);
CREATE TRIGGER IF NOT EXISTS workflow_job_scope BEFORE INSERT ON workflow_jobs
WHEN NOT EXISTS(SELECT 1 FROM documents d JOIN versions v ON v.document_id=d.id
 WHERE d.id=NEW.document_id AND d.institution_id=NEW.institution_id AND v.id=NEW.version_id)
BEGIN SELECT RAISE(ABORT,'workflow_scope_mismatch'); END;
'''


class WorkflowJobRepository:
    def __init__(self, repository):
        self.repository = repository
        if getattr(repository, 'dialect', None) == 'postgresql':
            return  # Versioned migrations own PostgreSQL DDL.
        with repository.transaction() as db:
            version = db.connection.execute("SELECT version FROM schema_extensions WHERE name='workflow_jobs'").fetchone()
            if version and version[0] != 1:
                raise RuntimeError('unsupported_workflow_schema')
            import sqlite3
            pending = ''
            for line in SCHEMA.splitlines(keepends=True):
                pending += line
                if sqlite3.complete_statement(pending):
                    db.connection.execute(pending); pending = ''

    @staticmethod
    def job(db, key):
        row = db.connection.execute('SELECT * FROM workflow_jobs WHERE id=?',(key,)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def enqueue(db, principal, snapshot, settings, catalog_hash, configuration, clock):
        key = digest([snapshot.snapshot_id,settings.model_dump(mode='json'),catalog_hash,configuration])
        old = db.connection.execute('SELECT * FROM workflow_jobs WHERE institution_id=? AND version_id=? AND input_key=?',
                                    (principal.institution_id,snapshot.version_id,key)).fetchone()
        if old:return dict(old)
        generation = db.connection.execute('SELECT COALESCE(MAX(generation),0)+1 FROM workflow_jobs WHERE version_id=?',(snapshot.version_id,)).fetchone()[0]
        job_id = uuid.uuid4().hex
        db.connection.execute('''INSERT INTO workflow_jobs(id,institution_id,document_id,version_id,input_snapshot_id,
            snapshot,settings,catalog_hash,configuration,input_key,generation,state,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,'queued',?)''', (job_id,principal.institution_id,snapshot.document_id,snapshot.version_id,
            snapshot.snapshot_id,snapshot.model_dump_json(),settings.model_dump_json(),catalog_hash,configuration,key,generation,clock))
        WorkflowJobRepository.event(db,job_id,clock)
        return WorkflowJobRepository.job(db,job_id)

    @staticmethod
    def recover(db, institution, clock):
        expired=db.connection.execute("SELECT id FROM workflow_jobs WHERE institution_id=? AND state='processing' AND lease_until<=?",(institution,clock)).fetchall()
        for row in expired:
            db.connection.execute("""UPDATE workflow_jobs SET state=CASE WHEN attempt<3 THEN 'queued' ELSE 'failed' END,
                error_code='lease_expired',error_category='RETRYABLE',claim_hash=NULL,lease_until=NULL WHERE id=?""",(row['id'],))
            WorkflowJobRepository.event(db,row['id'],clock)

    @staticmethod
    def claim(db, institution, capability_hash, clock, lease):
        WorkflowJobRepository.recover(db,institution,clock)
        row = db.connection.execute("SELECT id FROM workflow_jobs WHERE institution_id=? AND state='queued' AND attempt<3 ORDER BY created_at,id LIMIT 1",(institution,)).fetchone()
        if not row:return None
        db.connection.execute("UPDATE workflow_jobs SET state='processing',attempt=attempt+1,claim_hash=?,lease_until=?,error_code=NULL,error_category=NULL WHERE id=?",(capability_hash,clock+lease,row['id']))
        WorkflowJobRepository.event(db,row['id'],clock)
        return WorkflowJobRepository.job(db,row['id'])

    @staticmethod
    def owned(db, claim, capability_hash, clock):
        row = WorkflowJobRepository.job(db,claim['id'])
        if (not row or row['institution_id']!=claim['institution_id'] or row['attempt']!=claim['attempt']
            or row['state']!='processing' or row['claim_hash']!=capability_hash or row['lease_until']<=clock):return None
        return row

    @staticmethod
    def finish(db, row, result, clock):
        key = uuid.uuid4().hex
        payload = result.model_dump_json()
        db.connection.execute('INSERT INTO workflow_generations VALUES(?,?,?,?,?)',(key,row['id'],payload,digest(payload),clock))
        for candidate in result.discovery.extraction.workflows:
            db.connection.execute('INSERT INTO workflow_candidates VALUES(?,?,?)',(key,candidate.id,candidate.model_dump_json()))
        for index,issue in enumerate(result.forms.source_review.issues):
            db.connection.execute('INSERT INTO workflow_review_issues VALUES(?,?,?)',(key,index,issue.model_dump_json()))
        # Form-specific review issues are also discoverable in the review endpoint.
        offset = len(result.forms.source_review.issues)
        for relation in result.forms.relations:
            db.connection.execute('INSERT INTO workflow_form_links VALUES(?,?,?)',(key,relation.requirement_id,relation.model_dump_json()))
            for issue in relation.issues:
                db.connection.execute('INSERT INTO workflow_review_issues VALUES(?,?,?)',(key,offset,issue.model_dump_json()));offset+=1
        db.connection.execute("UPDATE workflow_jobs SET state='completed',claim_hash=NULL,lease_until=NULL,error_code=NULL,error_category=NULL WHERE id=?",(row['id'],))
        WorkflowJobRepository.event(db,row['id'],clock)

    @staticmethod
    def current(db,institution,document,version):
        row = db.connection.execute('''SELECT g.*,j.id AS source_job_id FROM workflow_generations g
            JOIN workflow_jobs j ON j.id=g.job_id WHERE j.institution_id=? AND j.document_id=? AND j.version_id=?
            AND j.state='completed' ORDER BY j.generation DESC LIMIT 1''',(institution,document,version)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def components(db,generation):
        return {
            'candidates':[json.loads(r[0]) for r in db.connection.execute('SELECT payload FROM workflow_candidates WHERE generation_id=? ORDER BY candidate_id',(generation,))],
            'issues':[json.loads(r[0]) for r in db.connection.execute('SELECT payload FROM workflow_review_issues WHERE generation_id=? ORDER BY ordinal',(generation,))],
            'forms':[json.loads(r[0]) for r in db.connection.execute('SELECT payload FROM workflow_form_links WHERE generation_id=? ORDER BY requirement_id',(generation,))]}


    @staticmethod
    def event(db,key,clock):
        db.connection.execute("""INSERT INTO workflow_job_events(job_id,state,attempt,error_code,error_category,created_at)
            SELECT id,state,attempt,error_code,error_category,? FROM workflow_jobs WHERE id=?""",(clock,key))

    @staticmethod
    def events(db,key):
        return [dict(r) for r in db.connection.execute('SELECT state,attempt,error_code,error_category,created_at FROM workflow_job_events WHERE job_id=? ORDER BY id',(key,))]

    @staticmethod
    def cancel(db,key,clock):
        db.connection.execute("UPDATE workflow_jobs SET state='cancelled',claim_hash=NULL,lease_until=NULL,error_code='cancelled_by_manager',error_category=NULL WHERE id=?",(key,))
        WorkflowJobRepository.event(db,key,clock)

    @staticmethod
    def retry(db,key,clock):
        db.connection.execute("UPDATE workflow_jobs SET state='queued',error_code=NULL,error_category=NULL WHERE id=?",(key,))
        WorkflowJobRepository.event(db,key,clock)

    @staticmethod
    def renew(db,key,until):
        db.connection.execute('UPDATE workflow_jobs SET lease_until=? WHERE id=?',(until,key))

    @staticmethod
    def fail(db,key,code,category,clock):
        db.connection.execute("UPDATE workflow_jobs SET state='failed',error_code=?,error_category=?,claim_hash=NULL,lease_until=NULL WHERE id=?",(code,category,key))
        WorkflowJobRepository.event(db,key,clock)
