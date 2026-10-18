"""Fake-only private objects plus SQLite/real loopback PG application recovery."""
import copy
from contextlib import contextmanager
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import secrets
import socket
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi.testclient import TestClient
from apps.api.main import create_app,authenticated_principal
from apps.api.repository import Repository,DocumentUnitOfWork
from apps.api.models import Principal
from apps.api.errors import DomainError
from apps.api.private_storage import (PrivateStorageSettings,PrivateOriginalStore,FakeStorageTransport,StorageRegistry,
                                     ObjectData,StorageUnavailable,object_path,sha)
from apps.api.storage_backup import (StorageBackupService,BackupAuthority,BackupBundle,save_bundle,load_bundle,canonical)
from apps.api.service import now
import test_document_api as fixtures
import test_workflow_discovery as synthetic
from apps.api.chunking import ChunkConfig

A=Principal('synthetic-manager','A','manager');B=Principal('synthetic-other','B','manager')
R=Principal('synthetic-reader','A','reader');W=Principal('synthetic-worker','A','worker')
AUTHORITY=BackupAuthority(('A','B'))
DSN=os.environ.get('SB_PG_TEST_DSN')
MARKER='synthetic-server-private-MUST-NOT-PRINT'


def settings(**changes):
    return PrivateStorageSettings(project_url='https://'+'a'*20+'.supabase.co',bucket='private-originals',server_key=MARKER,**changes)


class PrivateStorageTests(unittest.TestCase):
    def setUp(self):
        Path('work/private-storage-tests').mkdir(parents=True,exist_ok=True)
        self.tmp=tempfile.TemporaryDirectory(dir='work/private-storage-tests');self.root=Path(self.tmp.name)
        self.app,self.store=self.make('source');self.repo=self.store.repo;self.docs=self.app.state.service
    def tearDown(self):self.tmp.cleanup()
    def make(self,name,transport=None,postgres=False):
        root=self.root/name
        if postgres:
            from apps.api.postgres import PostgresDatabase,PostgresRepository
            d=PostgresDatabase(DSN,'sb_storage_'+secrets.token_hex(8),local_test=True);d.migrate();repo=PostgresRepository(d)
        else:repo=Repository(root/'metadata.sqlite3')
        store=PrivateOriginalStore(repo,settings(),transport or FakeStorageTransport())
        app=create_app(root,repository=repo,store=store,parsing_enabled=True)
        return app,store
    def register(self,principal=A,data=None):
        return self.docs.register(principal,'synthetic.pdf','application/pdf',data or fixtures.pdf())[0]
    def pending(self):
        key=secrets.token_hex(16)
        with self.repo.transaction() as db:db.start_intent(key,A.institution_id,now())
        return key
    def count(self,table):
        assert table in ('documents','versions','private_storage_objects','private_storage_restores','workflow_generations')
        with self.repo.transaction() as db:return db.connection.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]
    def bundle(self):return StorageBackupService(self.repo,self.store).create(AUTHORITY)
    def test_upload_read_original_hash_and_size(self):
        meta=self.register();body,actual=self.docs.original(A,meta['document_id'],meta['id'])
        self.assertEqual(body,fixtures.pdf());self.assertEqual(sha(body),actual['sha256']);self.assertEqual(len(body),actual['size'])
        self.assertEqual(self.store.transport.calls.count('put'),1)
    def test_default_local_store_is_unchanged(self):
        with tempfile.TemporaryDirectory(dir='work/private-storage-tests') as path:
            app=create_app(Path(path),parsing_enabled=True)
            from apps.api.storage import LocalOriginalStore
            self.assertIs(type(app.state.service.store),LocalOriginalStore)
    def test_immutable_overwrite_forbidden(self):
        meta=self.register()
        with self.assertRaises(DomainError):self.store.write(A,meta['id'],b'changed')
        self.assertEqual(self.docs.original(A,meta['document_id'],meta['id'])[0],fixtures.pdf())
        self.assertFalse(hasattr(self.store,'delete'));self.assertFalse(hasattr(self.store,'signed_url'))
    def test_duplicate_upload_is_idempotent(self):
        first=self.register();second,duplicate=self.docs.register(A,'renamed.pdf','application/pdf',fixtures.pdf())
        self.assertTrue(duplicate);self.assertEqual(first['id'],second['id']);self.assertEqual(self.store.transport.calls.count('put'),1)
    def test_concurrent_duplicates_preserve_all_objects(self):
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:self.register(),range(2)))
        self.assertEqual(results[0]['id'],results[1]['id']);self.assertEqual(self.count('versions'),1)
        result=self.store.reconcile(A)
        self.assertTrue(all(i['code']=='ORPHAN_QUARANTINED' for i in result['issues']))
        self.assertEqual(result['deleted'],0)
    def test_paths_are_institution_separated(self):
        one=self.register();two=self.register(B)
        self.assertNotEqual(object_path('A',one['id']).split('/')[1],object_path('B',two['id']).split('/')[1])
        self.assertNotIn('synthetic.pdf',object_path('A',one['id']))
    def test_foreign_access_is_rejected_before_transport(self):
        meta=self.register(B);calls=len(self.store.transport.calls)
        with self.assertRaises(DomainError):self.store.read(A,meta['id'],meta['sha256'])
        self.assertEqual(len(self.store.transport.calls),calls)
    def test_reader_inactive_and_retired_denied(self):
        meta=self.register()
        with self.assertRaises(DomainError):self.store.read(R,meta['id'],meta['sha256'])
        self.docs.deregister(A,meta['document_id'])
        with self.assertRaises(DomainError):self.store.read(W,meta['id'],meta['sha256'])
        self.assertEqual(self.store.read(A,meta['id'],meta['sha256']),fixtures.pdf())
    def test_reader_cannot_upload(self):
        key=self.pending()
        with self.assertRaises(DomainError):self.store.write(R,key,fixtures.pdf())
        self.assertEqual(self.store.transport.calls,[])
    def test_traversal_rejected(self):
        for key in ('../secret','a/b','%2e%2e','a'*32+'/x'):
            with self.subTest(key=key),self.assertRaises(DomainError):self.store.read(A,key,'0'*64)
    def test_unknown_intent_rejected_before_put(self):
        with self.assertRaises(DomainError):self.store.write(A,'a'*32,fixtures.pdf())
        self.assertEqual(self.store.transport.calls,[])
    def test_policy_public_bucket_rejected(self):
        with self.assertRaises(DomainError):PrivateOriginalStore(self.repo,settings(),FakeStorageTransport(private=False))
        self.store.transport.private=False
        with self.assertRaises(DomainError):self.register()
    def test_real_or_subclass_transport_rejected(self):
        class Pretend(FakeStorageTransport):pass
        for transport in (object(),Pretend()):
            with self.assertRaises(DomainError):PrivateOriginalStore(self.repo,settings(),transport)
    def test_configuration_and_secret_repr(self):
        self.assertNotIn(MARKER,repr(settings()));self.assertNotIn(MARKER,settings().model_dump_json());self.assertNotIn(MARKER,repr(self.store))
        with self.assertRaises(ValueError):PrivateStorageSettings(project_url='x',bucket='public',server_key=MARKER,real_calls_enabled=True)
        for url in ('http://localhost','https://evil.example','https://'+'a'*20+'.supabase.co/path'):
            with self.assertRaises(DomainError):PrivateOriginalStore(self.repo,settings().model_copy(update={'project_url':__import__('pydantic').SecretStr(url)}),FakeStorageTransport())
    def test_fake_fault_configuration_no_callbacks(self):
        with self.assertRaises(ValueError):FakeStorageTransport(faults=[lambda:None])
    def test_upload_failure_has_intent_but_no_version(self):
        self.store.transport.faults=['put_timeout_before']
        with self.assertRaises(DomainError):self.register()
        self.assertEqual(self.count('versions'),0);self.assertEqual(len(self.store.transport._objects),0)
        with self.repo.transaction() as db:self.assertEqual(db.connection.execute('SELECT status FROM upload_intents').fetchone()[0],'failed')
    def test_lost_put_response_retained_not_published(self):
        self.store.transport.faults=['put_timeout_after']
        with self.assertRaises(DomainError):self.register()
        self.assertEqual(self.count('versions'),0);self.assertEqual(len(self.store.transport._objects),1)
        self.assertEqual(self.store.reconcile(A)['issues'][0]['code'],'ORPHAN_QUARANTINED')
    def test_pending_retry_verifies_existing_no_second_put(self):
        key=self.pending();self.store.transport.faults=['put_timeout_after']
        with self.assertRaises(DomainError):self.store.write(A,key,fixtures.pdf())
        self.store.write(A,key,fixtures.pdf())
        self.assertEqual(self.store.transport.calls.count('put'),1)
        self.assertEqual(self.store.read(A,key,sha(fixtures.pdf())),fixtures.pdf())
    def test_bounded_retry(self):
        key=self.pending();self.store.transport.faults=['put_timeout_before']*4
        for _ in range(3):
            with self.assertRaises(DomainError):self.store.write(A,key,fixtures.pdf())
        with self.assertRaises(DomainError) as e:self.store.write(A,key,fixtures.pdf())
        self.assertEqual(e.exception.code,'storage_retry_limit')
    def test_retry_payload_cannot_change(self):
        key=self.pending();self.store.transport.faults=['put_timeout_before']
        with self.assertRaises(DomainError):self.store.write(A,key,fixtures.pdf())
        with self.assertRaises(DomainError):self.store.write(A,key,b'other')
    def test_partial_upload_quarantined(self):
        self.store.transport.faults=['put_partial']
        with self.assertRaises(DomainError):self.register()
        self.assertEqual(self.count('versions'),0)
        with self.repo.transaction() as db:self.assertEqual(db.connection.execute('SELECT state FROM private_storage_objects').fetchone()[0],'quarantined')
    def test_object_success_db_failure_is_orphan(self):
        with patch.object(DocumentUnitOfWork,'insert_version',side_effect=RuntimeError(MARKER)):
            with self.assertRaises(RuntimeError):self.register()
        self.assertEqual(self.count('versions'),0);self.assertEqual(len(self.store.transport._objects),1)
        self.assertEqual(self.store.reconcile(A)['issues'][0]['code'],'ORPHAN_QUARANTINED')
    def test_corrupt_read_and_metadata_fail_closed(self):
        meta=self.register()
        for fault in ('get_corrupt','get_wrong_hash','get_wrong_size','get_timeout'):
            self.store.transport.faults=[fault]
            with self.subTest(fault=fault),self.assertRaises(DomainError):self.store.read(A,meta['id'],meta['sha256'])
    def test_forged_expected_hash_denied_before_get(self):
        meta=self.register();calls=len(self.store.transport.calls)
        with self.assertRaises(DomainError):self.store.read(A,meta['id'],'0'*64)
        self.assertEqual(len(self.store.transport.calls),calls)
    def test_unknown_orphan_and_foreign_inventory(self):
        key=secrets.token_hex(16);self.store.transport.put_if_absent(settings().bucket,object_path('A',key),b'synthetic-orphan')
        self.assertEqual(self.store.reconcile(A)['issues'][0]['code'],'ORPHAN_QUARANTINED')
        self.store.transport.faults=['list_foreign']
        with self.assertRaises(DomainError):self.store.reconcile(A)
    def test_missing_object_report(self):
        meta=self.register();self.store.transport._objects.clear() # Explicit provider-loss injection, not adapter deletion.
        self.assertEqual(self.store.reconcile(A)['issues'][0]['code'],'OBJECT_MISSING')
        with self.assertRaises(DomainError):self.store.read(A,meta['id'],meta['sha256'])
    def test_api_does_not_return_secrets_or_signed_urls(self):
        self.app.dependency_overrides[authenticated_principal]=lambda:A
        with TestClient(self.app) as c:
            response=c.post('/documents?filename=synthetic.pdf',content=fixtures.pdf(),headers={'Content-Type':'application/pdf','X-Data-Classification':'synthetic'})
            self.assertEqual(response.status_code,201);self.assertNotIn(MARKER,response.text);self.assertNotIn('signed',response.text)
    def test_pipeline_evidence_and_workflow_remain_unverified(self):
        raw=synthetic.synthetic_hwpx(['업무명: 합성 별 접수','1. 신청자는 별신청서를 제출한다.','2. 담당자는 자료를 검토한다.'])
        meta,_=self.docs.register(A,'synthetic.hwpx','application/hwp+zip',raw)
        p=self.app.state.parsing;self.assertEqual(p.execute(W,p.claim(W)),'completed')
        chunks=self.app.state.chunks;chunks.enqueue(A,meta['document_id'],meta['id'],ChunkConfig());self.assertEqual(chunks.execute(W,chunks.claim(W)),'completed')
        self.docs.activate(A,meta['document_id'],meta['id'])
        item=chunks.list(R,meta['document_id'],meta['id'])[0]
        from apps.api.chunking import EvidenceRef
        self.assertTrue(chunks.resolve(R,meta['document_id'],meta['id'],item['chunk_id'],EvidenceRef.model_validate(item['evidence']))['structural_valid'])
        jobs=self.app.state.workflows;jobs.enqueue(A,meta['document_id'],meta['id']);self.assertEqual(jobs.execute(W,jobs.claim(W)),'completed')
        self.assertFalse(jobs.current(A,meta['document_id'],meta['id'])['result'].forms.publishable)
    def test_all_operations_offline_no_raw_logs(self):
        stream=io.StringIO();handler=logging.StreamHandler(stream);logging.getLogger().addHandler(handler)
        try:
            with patch('socket.socket.connect',side_effect=AssertionError('network')),patch('socket.getaddrinfo',side_effect=AssertionError('DNS')),patch('httpx.Client',side_effect=AssertionError('HTTP client')):
                meta=self.register();self.store.read(A,meta['id'],meta['sha256']);self.store.reconcile(A);self.bundle()
        finally:logging.getLogger().removeHandler(handler)
        self.assertNotIn(MARKER,stream.getvalue());self.assertNotIn(fixtures.pdf().decode('latin1'),stream.getvalue())
    def test_backup_restore_and_duplicate_restore(self):
        meta=self.register();bundle=self.bundle();target,store=self.make('target');restore=StorageBackupService(store.repo,store)
        self.assertEqual(restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)['status'],'RESTORED')
        self.assertEqual(target.state.service.original(A,meta['document_id'],meta['id'])[0],fixtures.pdf())
        self.assertEqual(restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)['status'],'ALREADY_RESTORED')
    def test_inflight_parse_claim_fenced_and_recovered(self):
        meta=self.register();claim=self.app.state.parsing.claim(W)
        self.assertIsNotNone(claim)
        bundle=self.bundle();target,store=self.make('target')
        StorageBackupService(store.repo,store).restore(AUTHORITY,bundle,bundle.manifest_sha256)
        self.assertEqual(target.state.parsing.execute(W,claim),'stale')
        recovered=target.state.parsing.claim(W)
        self.assertIsNotNone(recovered);self.assertNotEqual(recovered['claim_hash'],claim['claim_hash'])
        self.assertEqual(target.state.parsing.execute(W,recovered),'completed')
        # Identity sequence must continue above restored event IDs on both databases.
        self.assertEqual(target.state.service.original(A,meta['document_id'],meta['id'])[0],fixtures.pdf())
    def test_orphan_blocks_backup_without_deleting_object(self):
        self.store.transport.faults=['put_timeout_after']
        with self.assertRaises(DomainError):self.register()
        self.store.reconcile(A)
        with self.assertRaises(DomainError):self.bundle()
        self.assertEqual(len(self.store.transport._objects),1)
    def test_extension_migration_idempotent_and_checksum_guard(self):
        self.assertFalse(self.store.registry.migrate())
        with self.repo.transaction() as db:db.connection.execute("UPDATE private_storage_schema SET checksum=?",('0'*64,))
        with self.assertRaises(DomainError):self.store.registry.migrate()
    def test_production_fake_adapter_stays_blocked(self):
        from apps.api.runtime_settings import PRODUCTION_BLOCKERS,preflight
        self.assertIn('private_storage_production_transport_not_wired',PRODUCTION_BLOCKERS)
        self.assertEqual(preflight({})['private_storage_adapter'],'FAKE_ONLY_IMPLEMENTED_NOT_CONNECTED')
    def test_backup_operator_not_browser_manager(self):
        self.register()
        with self.assertRaises(DomainError):StorageBackupService(self.repo,self.store).create(A)
    def test_backup_foreign_institution_scope(self):
        self.register(B)
        with self.assertRaises(DomainError):StorageBackupService(self.repo,self.store).create(BackupAuthority(('A',)))
    def test_backup_pending_or_orphan_is_not_complete(self):
        self.pending()
        with self.assertRaises(DomainError):self.bundle()
    def test_backup_changed_object_detected(self):
        self.register();self.store.transport.faults=['get_wrong_hash']
        with self.assertRaises(DomainError):self.bundle()
    def test_wrong_root_and_mixed_snapshot_rejected(self):
        self.register();bundle=self.bundle();target,store=self.make('target');restore=StorageBackupService(store.repo,store)
        with self.assertRaises(DomainError):restore.restore(AUTHORITY,bundle,'0'*64)
        m=json.loads(bundle.manifest_bytes);m['tables']['versions']['snapshot_id']='0'*32
        changed=BackupBundle(canonical(m),bundle.tables,bundle.objects)
        with self.assertRaises(DomainError):restore.restore(AUTHORITY,changed,changed.manifest_sha256)
    def test_tampered_table_or_object_rejected(self):
        self.register();bundle=self.bundle();target,store=self.make('target');restore=StorageBackupService(store.repo,store)
        tables=dict(bundle.tables);tables['versions']=b'[]'
        objects=dict(bundle.objects);objects[next(iter(objects))]=b'partial'
        for bad in (BackupBundle(bundle.manifest_bytes,tables,bundle.objects),BackupBundle(bundle.manifest_bytes,bundle.tables,objects)):
            with self.assertRaises(DomainError):restore.restore(AUTHORITY,bad,bundle.manifest_sha256)
    def test_restore_nonempty_target_refused(self):
        self.register();bundle=self.bundle()
        with self.assertRaises(DomainError):StorageBackupService(self.repo,self.store).restore(AUTHORITY,bundle,bundle.manifest_sha256)
    def test_restore_object_failure_no_db_visibility_retry_safe(self):
        self.register();bundle=self.bundle();target,store=self.make('target',FakeStorageTransport(faults=['put_timeout_after']))
        restore=StorageBackupService(store.repo,store)
        with self.assertRaises(DomainError):restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)
        self.assertEqual(target.state.service.list(A,False),[])
        self.assertEqual(restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)['status'],'RESTORED')
    def test_restore_database_failure_rolls_back_objects_retained(self):
        self.register();bundle=self.bundle();target,store=self.make('target');restore=StorageBackupService(store.repo,store)
        import sqlite3
        with store.repo.transaction() as db:db.connection.execute("CREATE TRIGGER injected_restore BEFORE INSERT ON versions BEGIN SELECT RAISE(ABORT,'synthetic'); END")
        with self.assertRaises(sqlite3.DatabaseError):restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)
        self.assertEqual(target.state.service.list(A,False),[]);self.assertEqual(len(store.transport._objects),1)
        with store.repo.transaction() as db:db.connection.execute('DROP TRIGGER injected_restore')
        self.assertEqual(restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)['status'],'RESTORED')
    def test_restore_retirement_tombstone_and_session_revocation(self):
        meta=self.register();self.docs.deregister(A,meta['document_id'])
        user=self.app.state.auth.store.provision('synthetic','subject','A','합성기관','manager')
        with self.repo.transaction() as db:db.connection.execute('INSERT INTO sessions VALUES(?,?,?,?,?,?,0)',('hash',user,'A','csrf',9999999999,1))
        bundle=self.bundle();target,store=self.make('target');StorageBackupService(store.repo,store).restore(AUTHORITY,bundle,bundle.manifest_sha256)
        self.assertEqual(target.state.service.list(R),[])
        with store.repo.transaction() as db:self.assertEqual(db.connection.execute('SELECT revoked FROM sessions').fetchone()[0],1)
    def test_restore_target_drift_does_not_overwrite(self):
        self.register();bundle=self.bundle();target,store=self.make('target');restore=StorageBackupService(store.repo,store)
        restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)
        with store.repo.transaction() as db:db.connection.execute("UPDATE documents SET registered=0,active_version_id=NULL")
        with self.assertRaises(DomainError):restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)
    def test_immutable_disk_backup_and_truncated_copy(self):
        self.register();bundle=self.bundle();path=self.root/'backup'
        expected=save_bundle(bundle,path);loaded=load_bundle(path,expected,AUTHORITY)
        self.assertEqual(loaded.manifest_sha256,bundle.manifest_sha256)
        with self.assertRaises(FileExistsError):save_bundle(bundle,path)
        (path/'COMPLETE').unlink() # Deliberate corruption of this test's new copy, not a user/prior backup.
        with self.assertRaises(DomainError):load_bundle(path,expected,AUTHORITY)
    def test_backup_loader_rejects_symlink(self):
        self.register();bundle=self.bundle();path=self.root/'backup';expected=save_bundle(bundle,path)
        alias=self.root/'alias';alias.symlink_to(path,target_is_directory=True)
        with self.assertRaises(DomainError):load_bundle(alias,expected,AUTHORITY)


@unittest.skipUnless(DSN,'BLOCKED: isolated loopback PostgreSQL not configured')
class PostgreSQLPrivateStorageTests(PrivateStorageTests):
    def make(self,name,transport=None,postgres=True):return super().make(name,transport,postgres)
    # The SQLite-only injected trigger is replaced by a PostgreSQL adapter failure seam.
    def test_restore_database_failure_rolls_back_objects_retained(self):
        self.register();bundle=self.bundle();target,store=self.make('target');restore=StorageBackupService(store.repo,store)
        from apps.api.postgres import Connection,PostgresFailure
        original=Connection.execute
        def fail(connection,sql,parameters=()):
            if sql.startswith('INSERT INTO versions('):raise PostgresFailure('synthetic_partial_restore')
            return original(connection,sql,parameters)
        with patch.object(Connection,'execute',fail),self.assertRaises(PostgresFailure):restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)
        self.assertEqual(target.state.service.list(A,False),[]);self.assertEqual(len(store.transport._objects),1)
        self.assertEqual(restore.restore(AUTHORITY,bundle,bundle.manifest_sha256)['status'],'RESTORED')
