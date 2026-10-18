"""SQLite exact-cosine baseline. Publication and current pointer share a transaction."""
import json
from .chunking import canonical, digest
from .errors import DomainError

SCHEMA = '''
CREATE TABLE IF NOT EXISTS vector_generations(
 id TEXT PRIMARY KEY,organization_id TEXT NOT NULL,spec TEXT NOT NULL,input_hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS vector_items(
 generation_id TEXT NOT NULL REFERENCES vector_generations(id),job_id TEXT NOT NULL,
 chunk_id TEXT NOT NULL,payload_hash TEXT NOT NULL,vector TEXT NOT NULL,
 PRIMARY KEY(generation_id,job_id,chunk_id),
 FOREIGN KEY(job_id,chunk_id) REFERENCES chunk_items(job_id,chunk_id));
CREATE TABLE IF NOT EXISTS vector_current(
 organization_id TEXT PRIMARY KEY,generation_id TEXT NOT NULL REFERENCES vector_generations(id));
'''


class SQLiteVectorStore:
    def __init__(self, repository):
        self.repo = repository
        if getattr(repository, 'dialect', None) == 'postgresql':
            return  # Versioned migrations own PostgreSQL DDL.
        with repository.transaction() as db:
            for statement in SCHEMA.split(';'):
                if statement.strip():
                    db.connection.execute(statement)

    @staticmethod
    def eligible(db, organization):
        rows = db.connection.execute('''SELECT i.job_id,i.chunk_id,i.payload FROM chunk_items i
            JOIN chunk_current c ON c.job_id=i.job_id JOIN chunk_jobs j ON j.id=c.job_id
            JOIN versions v ON v.id=c.version_id JOIN documents d ON d.id=v.document_id
            JOIN parse_jobs p ON p.id=j.parse_job_id AND p.attempt=j.parse_attempt
            WHERE d.institution_id=? AND d.registered=1 AND d.active_version_id=v.id
            AND j.state='completed' AND p.state='completed'
            ORDER BY i.job_id,i.chunk_id''',(organization,)).fetchall()
        return [{'job_id':r['job_id'],'chunk':json.loads(r['payload'])} for r in rows]

    def publish(self, organization, spec, snapshot, vectors):
        signature = digest(snapshot)
        key = digest([organization,spec,signature])
        with self.repo.transaction() as db:
            if digest(self.eligible(db,organization)) != signature:
                raise DomainError('index_source_changed')
            old = db.connection.execute('SELECT * FROM vector_generations WHERE id=?',(key,)).fetchone()
            if not old:
                db.connection.execute('INSERT INTO vector_generations VALUES (?,?,?,?)',(key,organization,canonical(spec),signature))
                for item,vector in zip(snapshot,vectors,strict=True):
                    c=item['chunk']
                    db.connection.execute('INSERT INTO vector_items VALUES (?,?,?,?,?)',
                        (key,item['job_id'],c['chunk_id'],digest(c),canonical(vector)))
            db.connection.execute('INSERT INTO vector_current VALUES (?,?) ON CONFLICT(organization_id) DO UPDATE SET generation_id=excluded.generation_id',(organization,key))
        return key

    def candidates(self, organization, spec, query_vector, limit):
        with self.repo.transaction() as db:
            current = db.connection.execute('''SELECT g.* FROM vector_current c JOIN vector_generations g ON g.id=c.generation_id
                WHERE c.organization_id=? AND g.organization_id=?''',(organization,organization)).fetchone()
            if not current:
                return []
            if current['spec'] != canonical(spec):
                raise DomainError('embedding_generation_mismatch')
            allowed={(x['job_id'],x['chunk']['chunk_id']):x['chunk'] for x in self.eligible(db,organization)}
            scores=[]
            for row in db.connection.execute('SELECT * FROM vector_items WHERE generation_id=?',(current['id'],)):
                chunk=allowed.get((row['job_id'],row['chunk_id']))
                if chunk is None:
                    continue
                if row['payload_hash'] != digest(chunk):
                    raise DomainError('vector_source_mismatch')
                from .rag_adapters import checked_vectors
                vector=checked_vectors([json.loads(row['vector'])],1,len(query_vector))[0]
                score=sum(a*b for a,b in zip(vector,query_vector,strict=True))
                scores.append((score,chunk))
            scores.sort(key=lambda x:(-x[0],x[1]['chunk_id']))
            return [c for _,c in scores[:limit]]
