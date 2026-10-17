import sqlite3
from contextlib import contextmanager
from pathlib import Path


class DocumentUnitOfWork:
    """SQL is confined to the SQLite adapter; service code uses domain operations."""
    def __init__(self, connection):
        self.connection = connection
        from .parsing_repository import ParsingQueries
        self.parsing = ParsingQueries(connection)
        from .chunk_repository import ChunkQueries
        self.chunks = ChunkQueries(connection)

    def document(self, institution, document_id):
        return self.connection.execute('SELECT * FROM documents WHERE id=? AND institution_id=?',
                                       (document_id, institution)).fetchone()

    def version(self, document_id, version_id):
        return self.connection.execute('SELECT * FROM versions WHERE id=? AND document_id=?',
                                       (version_id, document_id)).fetchone()

    def duplicate(self, institution, digest, document_id=None):
        if document_id:
            return self.connection.execute('SELECT * FROM versions WHERE document_id=? AND sha256=?',
                                           (document_id, digest)).fetchone()
        return self.connection.execute('''SELECT v.* FROM versions v JOIN documents d ON d.id=v.document_id
            WHERE d.institution_id=? AND d.registered=1 AND v.sha256=? ORDER BY v.created_at LIMIT 1''',
                                       (institution, digest)).fetchone()

    def start_intent(self, intent, institution, timestamp):
        self.connection.execute('INSERT INTO upload_intents VALUES (?,?,?,?,?)',
                                (intent, institution, 'pending', None, timestamp))

    def finish_intent(self, intent, status, version_id=None):
        self.connection.execute('UPDATE upload_intents SET status=?,version_id=? WHERE id=? AND status=\'pending\'',
                                (status, version_id, intent))

    def create_document(self, document_id, institution, timestamp):
        self.connection.execute('INSERT INTO documents VALUES (?,?,1,NULL,?)', (document_id, institution, timestamp))

    def insert_version(self, version_id, document_id, filename, size, mime, fmt, digest, timestamp, actor):
        number = self.connection.execute('SELECT COALESCE(MAX(number),0)+1 FROM versions WHERE document_id=?',
                                         (document_id,)).fetchone()[0]
        self.connection.execute('''INSERT INTO versions
            (id,document_id,number,original_name,size,mime,format,sha256,created_at,actor,state)
            VALUES (?,?,?,?,?,?,?,?,?,?, 'registered')''',
            (version_id, document_id, number, filename, size, mime, fmt, digest, timestamp, actor))

    def event(self, version_id, action, actor, timestamp):
        self.connection.execute('INSERT INTO events(version_id,action,actor,created_at) VALUES (?,?,?,?)',
                                (version_id, action, actor, timestamp))

    def documents(self, institution):
        return self.connection.execute('SELECT * FROM documents WHERE institution_id=? AND registered=1',
                                       (institution,)).fetchall()

    def versions(self, document_id):
        return self.connection.execute('SELECT * FROM versions WHERE document_id=? ORDER BY number',
                                       (document_id,)).fetchall()

    def transition(self, version_id, target, claim_hash):
        self.connection.execute('UPDATE versions SET state=?,revision=revision+1,claim_hash=? WHERE id=?',
                                (target, claim_hash, version_id))

    def activate(self, document_id, version_id):
        self.connection.execute('UPDATE documents SET active_version_id=? WHERE id=?', (version_id, document_id))

    def deregister(self, document_id, actor, timestamp):
        self.connection.execute('UPDATE documents SET registered=0,active_version_id=NULL WHERE id=?', (document_id,))
        self.connection.execute('''INSERT INTO events(version_id,action,actor,created_at)
            SELECT id,'deregistered',?,? FROM versions WHERE document_id=?''', (actor, timestamp, document_id))

    def unfinished_intents(self):
        return [dict(r) for r in self.connection.execute("SELECT id,status FROM upload_intents WHERE status!='committed'")]


class Repository:
    """SQLite adapter. Each operation owns its connection and transaction."""
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as session:
            db = session.connection
            if db.execute('PRAGMA user_version').fetchone()[0] > 2:
                raise RuntimeError('unsupported_database_schema')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS documents (
              id TEXT PRIMARY KEY, institution_id TEXT NOT NULL,
              registered INTEGER NOT NULL DEFAULT 1, active_version_id TEXT,
              created_at TEXT NOT NULL,
              FOREIGN KEY(active_version_id) REFERENCES versions(id));
            CREATE TABLE IF NOT EXISTS versions (
              id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id),
              number INTEGER NOT NULL, original_name TEXT NOT NULL,
              size INTEGER NOT NULL, mime TEXT NOT NULL, format TEXT NOT NULL,
              sha256 TEXT NOT NULL, created_at TEXT NOT NULL, actor TEXT NOT NULL,
              state TEXT NOT NULL CHECK(state IN ('registered','queued','processing','completed','failed')),
              revision INTEGER NOT NULL DEFAULT 0, claim_hash TEXT,
              UNIQUE(document_id, number), UNIQUE(document_id,sha256));
            CREATE TABLE IF NOT EXISTS upload_intents (
              id TEXT PRIMARY KEY, institution_id TEXT NOT NULL, status TEXT NOT NULL,
              version_id TEXT, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, version_id TEXT NOT NULL REFERENCES versions(id),
              action TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL);
            ''')
            from .parsing_repository import SCHEMA
            db.executescript(SCHEMA)
            from .chunk_repository import SCHEMA as CHUNK_SCHEMA
            db.executescript(CHUNK_SCHEMA)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA busy_timeout=10000')
        try:
            db.execute('BEGIN IMMEDIATE')
            yield DocumentUnitOfWork(db)
            if db.in_transaction:
                db.commit()
        except BaseException:
            if db.in_transaction:
                db.rollback()
            raise
        finally:
            db.close()

