import json
import uuid

SCHEMA = '''
CREATE TABLE IF NOT EXISTS schema_extensions(name TEXT PRIMARY KEY,version INTEGER NOT NULL);
INSERT OR IGNORE INTO schema_extensions VALUES ('chunks',1);
CREATE TABLE IF NOT EXISTS chunk_jobs(
 id TEXT PRIMARY KEY,version_id TEXT NOT NULL REFERENCES versions(id),
 parse_job_id TEXT NOT NULL,parse_attempt INTEGER NOT NULL,config TEXT NOT NULL,input_hash TEXT NOT NULL,
 generation INTEGER NOT NULL,state TEXT NOT NULL,attempt INTEGER NOT NULL DEFAULT 0,
 claim_hash TEXT,lease_until REAL,error_code TEXT,created_at REAL NOT NULL,
 UNIQUE(version_id,generation),UNIQUE(version_id,parse_job_id,parse_attempt,config),
 FOREIGN KEY(parse_job_id,parse_attempt) REFERENCES parse_attempts(job_id,attempt));
CREATE TABLE IF NOT EXISTS chunk_items(
 job_id TEXT NOT NULL REFERENCES chunk_jobs(id),chunk_id TEXT NOT NULL,order_index INTEGER NOT NULL,
 payload TEXT NOT NULL,search_text TEXT NOT NULL,PRIMARY KEY(job_id,chunk_id),UNIQUE(job_id,order_index));
CREATE TABLE IF NOT EXISTS chunk_current(version_id TEXT PRIMARY KEY REFERENCES versions(id),job_id TEXT NOT NULL REFERENCES chunk_jobs(id));
CREATE TRIGGER IF NOT EXISTS chunk_job_scope BEFORE INSERT ON chunk_jobs
WHEN NEW.version_id != (SELECT version_id FROM parse_jobs WHERE id=NEW.parse_job_id)
BEGIN SELECT RAISE(ABORT,'chunk_source_version_mismatch'); END;
'''


class ChunkQueries:
    def __init__(self,db):
        self.db = db

    def job(self,job_id):
        return self.db.execute('SELECT * FROM chunk_jobs WHERE id=?',(job_id,)).fetchone()

    def enqueue(self,version_id,parsed,config,input_hash,clock):
        old = self.db.execute('SELECT * FROM chunk_jobs WHERE version_id=? AND parse_job_id=? AND parse_attempt=? AND config=?',
            (version_id,parsed['id'],parsed['attempt'],config)).fetchone()
        if old:
            if old['input_hash'] != input_hash:
                raise ValueError('source batch changed')
            return old
        generation = self.db.execute('SELECT COALESCE(MAX(generation),0)+1 FROM chunk_jobs WHERE version_id=?',(version_id,)).fetchone()[0]
        key = uuid.uuid4().hex
        self.db.execute('''INSERT INTO chunk_jobs(id,version_id,parse_job_id,parse_attempt,config,input_hash,generation,state,created_at)
            VALUES (?,?,?,?,?,?,?,'queued',?)''',(key,version_id,parsed['id'],parsed['attempt'],config,input_hash,generation,clock))
        return self.job(key)

    def recover(self,organization,clock):
        expired = self.db.execute('''SELECT j.* FROM chunk_jobs j JOIN versions v ON v.id=j.version_id
            JOIN documents d ON d.id=v.document_id WHERE d.institution_id=? AND d.registered=1
            AND j.state='processing' AND j.lease_until<=?''',(organization,clock)).fetchall()
        for j in expired:
            state = 'queued' if j['attempt'] < 3 else 'failed'
            self.db.execute("UPDATE chunk_jobs SET state=?,claim_hash=NULL,lease_until=NULL,error_code='lease_expired' WHERE id=?",(state,j['id']))

    def claim(self,organization,capability,clock,lease):
        self.recover(organization,clock)
        row = self.db.execute('''SELECT j.*,v.document_id,v.sha256,d.institution_id FROM chunk_jobs j
            JOIN versions v ON v.id=j.version_id JOIN documents d ON d.id=v.document_id
            WHERE d.institution_id=? AND d.registered=1 AND j.state='queued' ORDER BY j.created_at,j.id LIMIT 1''',(organization,)).fetchone()
        if not row:
            return None
        self.db.execute("UPDATE chunk_jobs SET state='processing',attempt=attempt+1,claim_hash=?,lease_until=?,error_code=NULL WHERE id=?",
                        (capability,clock+lease,row['id']))
        return {**dict(row),'attempt':row['attempt']+1,'claim_hash':capability}

    def owned(self,claim,clock):
        return self.db.execute('''SELECT j.id FROM chunk_jobs j JOIN versions v ON v.id=j.version_id
            JOIN documents d ON d.id=v.document_id WHERE j.id=? AND j.attempt=? AND j.claim_hash=?
            AND j.state='processing' AND j.lease_until>? AND j.version_id=? AND v.document_id=?
            AND d.registered=1 AND d.institution_id=? AND v.sha256=?
            AND j.config=? AND j.input_hash=? AND j.parse_job_id=? AND j.parse_attempt=? AND j.generation=?''',
            (claim['id'],claim['attempt'],claim['claim_hash'],clock,claim['version_id'],claim['document_id'],
             claim['institution_id'],claim['sha256'],claim['config'],claim['input_hash'],
             claim['parse_job_id'],claim['parse_attempt'],claim['generation'])).fetchone() is not None

    def retry(self,job_id):
        self.db.execute("UPDATE chunk_jobs SET state='queued',claim_hash=NULL,lease_until=NULL,error_code=NULL WHERE id=?",(job_id,))

    def finish(self,claim,chunks,filename,titles=''):
        for c in chunks:
            context = '\n'.join(s.quote for s in c.evidence.spans if s.role != 'primary')
            search = (filename+'\n'+titles+'\n'+c.text+'\n'+context).casefold()
            self.db.execute('INSERT INTO chunk_items VALUES (?,?,?,?,?)',(claim['id'],c.chunk_id,c.order_index,c.model_dump_json(),search))
        self.db.execute("UPDATE chunk_jobs SET state='completed',claim_hash=NULL,lease_until=NULL WHERE id=?",(claim['id'],))
        current = self.db.execute('SELECT j.generation FROM chunk_current c JOIN chunk_jobs j ON j.id=c.job_id WHERE c.version_id=?',(claim['version_id'],)).fetchone()
        if current is None or current['generation'] <= claim['generation']:
            self.db.execute('INSERT INTO chunk_current VALUES (?,?) ON CONFLICT(version_id) DO UPDATE SET job_id=excluded.job_id',
                            (claim['version_id'],claim['id']))

    def fail(self,claim,code):
        self.db.execute("UPDATE chunk_jobs SET state='failed',error_code=?,claim_hash=NULL,lease_until=NULL WHERE id=?",(code,claim['id']))

    def current(self,version_id):
        return self.db.execute('SELECT j.* FROM chunk_current c JOIN chunk_jobs j ON j.id=c.job_id WHERE c.version_id=?',(version_id,)).fetchone()

    def items(self,job_id):
        return [json.loads(r['payload']) for r in self.db.execute('SELECT payload FROM chunk_items WHERE job_id=? ORDER BY order_index',(job_id,))]

    def requested(self,version_id):
        return self.db.execute('SELECT 1 FROM chunk_jobs WHERE version_id=? LIMIT 1',(version_id,)).fetchone() is not None

    def cancel(self,document_id):
        self.db.execute("UPDATE chunk_jobs SET state='cancelled',claim_hash=NULL,lease_until=NULL WHERE version_id IN (SELECT id FROM versions WHERE document_id=?)",(document_id,))

    def search(self,organization,terms,limit):
        conditions = ' AND '.join("i.search_text LIKE ? ESCAPE '\\'" for _ in terms)
        escaped = ['%'+t.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%' for t in terms]
        return [json.loads(r['payload']) for r in self.db.execute('''SELECT i.payload FROM chunk_items i
            JOIN chunk_current c ON c.job_id=i.job_id JOIN chunk_jobs j ON j.id=c.job_id
            JOIN versions v ON v.id=c.version_id JOIN documents d ON d.id=v.document_id
            JOIN parse_jobs p ON p.id=j.parse_job_id AND p.attempt=j.parse_attempt
            WHERE d.institution_id=? AND d.registered=1 AND d.active_version_id=v.id
            AND j.state='completed' AND p.state='completed' AND '''+conditions+
            ' ORDER BY d.created_at,v.id,i.order_index LIMIT ?',(organization,*escaped,limit))]
