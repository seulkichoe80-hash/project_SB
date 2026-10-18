CREATE TABLE private_storage_objects(
 object_id TEXT PRIMARY KEY,institution_id TEXT NOT NULL,bucket TEXT NOT NULL,object_path TEXT NOT NULL UNIQUE,
 sha256 TEXT NOT NULL,size INTEGER NOT NULL CHECK(size>=0),
 state TEXT NOT NULL CHECK(state IN ('planned','uploaded','unknown','quarantined')),
 attempts INTEGER NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 3),error_code TEXT,created_at TEXT NOT NULL);
CREATE TABLE private_storage_restores(
 backup_id TEXT PRIMARY KEY,manifest_sha256 TEXT NOT NULL,result_digest TEXT NOT NULL,state TEXT NOT NULL CHECK(state='completed'));
