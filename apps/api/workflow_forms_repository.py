"""Additive SQLite form classification, isolated from original document tables."""


class FormCatalogRepository:
    def __init__(self, repository):
        self.repository = repository
        if getattr(repository, 'dialect', None) == 'postgresql':
            return  # Versioned migrations own PostgreSQL DDL.
        with repository.transaction() as db:
            db.connection.execute('''CREATE TABLE IF NOT EXISTS workflow_form_catalog (
                institution_id TEXT NOT NULL,
                document_id TEXT NOT NULL REFERENCES documents(id),
                version_id TEXT NOT NULL REFERENCES versions(id),
                title TEXT NOT NULL, purpose TEXT NOT NULL,
                revision INTEGER NOT NULL CHECK(revision>0),
                PRIMARY KEY(institution_id,document_id))''')

    @staticmethod
    def upsert(db, institution, document, version, title, purpose):
        db.connection.execute('''INSERT INTO workflow_form_catalog VALUES (?,?,?,?,?,1)
            ON CONFLICT(institution_id,document_id) DO UPDATE SET
            version_id=excluded.version_id,title=excluded.title,purpose=excluded.purpose,
            revision=workflow_form_catalog.revision+1''', (institution,document,version,title,purpose))

    @staticmethod
    def current(db, institution):
        return [dict(r) for r in db.connection.execute('''
            SELECT c.*,v.original_name,v.sha256,v.state FROM workflow_form_catalog c
            JOIN documents d ON d.id=c.document_id AND d.institution_id=c.institution_id
            JOIN versions v ON v.document_id=d.id AND v.id=c.version_id
            WHERE c.institution_id=? AND d.registered=1
              AND d.active_version_id=c.version_id AND v.state='completed'
            ORDER BY c.document_id''', (institution,))]
