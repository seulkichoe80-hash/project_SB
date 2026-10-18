"""Offline HTTP contract tests. Synthetic data only, no real HTTP transport."""
import hashlib
import os
from pathlib import Path
import secrets
import socket
import tempfile
import unittest
from unittest.mock import patch

import httpx
from pydantic import SecretStr

from apps.api.errors import DomainError
from apps.api.formats import MAX_BYTES
from apps.api.main import create_app
from apps.api.private_storage import (PrivateOriginalStore, ObjectMissing, object_path, sha)
from apps.api.repository import Repository, DocumentUnitOfWork
from apps.api.storage_http import StorageHTTPTransport, StorageHTTPFailure
from apps.api.storage_backup import StorageBackupService
from apps.api.service import now
import test_private_storage as old
import test_document_api as fixtures

PATH = object_path('A', 'a' * 32)
GATEWAY = SecretStr('synthetic-gateway-not-a-real-key')
DSN = os.environ.get('SB_PG_TEST_DSN')


class ObjectServer:
    """Mock HTTP peer, not an assertion of undocumented provider JSON shapes."""
    def __init__(self):
        self.objects = {}
        self.methods = []
        self.post_status = 200
        self.store_on_error = False
        self.timeout_after = False
        self.partial = False
        self.json_body = b'{}'
        self.get_status = None
    def __call__(self, request):
        self.methods.append(request.method)
        # Canonical object suffix, fixed methods; no actual hostname resolution.
        path = request.url.path.split('/institutions/', 1)[1]
        if request.method == 'GET':
            if self.get_status is not None:
                return httpx.Response(self.get_status)
            if path not in self.objects:
                return httpx.Response(404)
            return httpx.Response(200, content=self.objects[path])
        assert request.method == 'POST'
        if path in self.objects:
            return httpx.Response(400)  # Documented duplicate status, no body assumptions.
        if self.post_status < 300 or self.store_on_error:
            self.objects[path] = request.content[:len(request.content)//2] if self.partial else request.content
        if self.timeout_after:
            raise httpx.ReadTimeout('synthetic hidden upstream message')
        return httpx.Response(self.post_status, content=self.json_body, headers={'retry-after': '7'})


def transport(peer=None, settings=None, **kwargs):
    return StorageHTTPTransport(settings or old.settings(), gateway_key=GATEWAY,
                                transport=httpx.MockTransport(peer or ObjectServer()), **kwargs)


class StorageHTTPTests(unittest.TestCase):
    def test_upload_download_and_idempotent_duplicate(self):
        peer = ObjectServer(); t = transport(peer); data = b'synthetic original'
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')), patch('socket.getaddrinfo', side_effect=AssertionError('DNS forbidden')):
            t.put_if_absent(old.settings().bucket, PATH, data)
            t.put_if_absent(old.settings().bucket, PATH, data)
            value = t.get(old.settings().bucket, PATH)
        self.assertEqual((value.data, value.size, value.sha256), (data, len(data), sha(data)))
        self.assertEqual(peer.methods.count('POST'), 1)

    def test_official_paths_headers_and_no_upsert(self):
        peer = ObjectServer(); seen = []
        def handler(r):
            seen.append((r.method, r.url.path, r.headers.get('authorization'), r.headers.get('apikey'), r.headers.get('x-upsert')))
            return peer(r)
        t = transport(handler); t.put_if_absent(old.settings().bucket, PATH, b'original')
        for method, path, auth, key, upsert in seen:
            self.assertEqual(auth, 'Bearer ' + old.MARKER); self.assertEqual(key, GATEWAY.get_secret_value())
            if method == 'POST':
                self.assertEqual(path, '/storage/v1/object/' + old.settings().bucket + '/' + PATH)
                self.assertEqual(upsert, 'false')
            else:
                self.assertEqual(path, '/storage/v1/object/authenticated/' + old.settings().bucket + '/' + PATH)

    def test_no_real_transport_or_subclasses(self):
        class Subclass(httpx.MockTransport): pass
        for mock in (None, object(), Subclass(lambda _: httpx.Response(200))):
            with self.subTest(kind=type(mock).__name__), self.assertRaises(StorageHTTPFailure):
                StorageHTTPTransport(old.settings(), gateway_key=GATEWAY, transport=mock)
        class Unsafe(StorageHTTPTransport): pass
        with self.assertRaises(StorageHTTPFailure):
            Unsafe(old.settings(), gateway_key=GATEWAY, transport=httpx.MockTransport(ObjectServer()))

    def test_tampered_transport_rechecked_before_request(self):
        t = transport(); t._mock = None
        with self.assertRaises(StorageHTTPFailure): t.get(old.settings().bucket, PATH)

    def test_https_exact_host_and_no_url_injection(self):
        for url in ('http://'+'a'*20+'.supabase.co', 'https://localhost', 'https://127.0.0.1',
                    'https://'+'a'*20+'.supabase.co.evil.test', 'https://user@'+'a'*20+'.supabase.co',
                    'https://'+'a'*20+'.supabase.co/path', 'https://'+'a'*20+'.supabase.co?x=1',
                    'https://'+'a'*20+'.supabase.co:443'):
            with self.subTest(url=url), self.assertRaises(StorageHTTPFailure):
                transport(settings=old.settings().model_copy(update={'project_url': SecretStr(url)}))

    def test_key_and_private_configuration(self):
        for key in ('x', 'x'*20+'\r\nX: injected', 'sb_publishable_'+'x'*20, 'sb_secret_'+'x'*20):
            with self.subTest(key_kind=key[:3]), self.assertRaises(StorageHTTPFailure):
                transport(settings=old.settings().model_copy(update={'server_key': SecretStr(key)}))
        for update in ({'private': False}, {'real_calls_enabled': True}, {'timeout_seconds': 100}):
            with self.subTest(update=update), self.assertRaises(StorageHTTPFailure):
                transport(settings=old.settings().model_copy(update=update))
        with self.assertRaises(StorageHTTPFailure):
            StorageHTTPTransport(old.settings(), gateway_key=SecretStr('a\nb'), transport=httpx.MockTransport(ObjectServer()))

    def test_path_traversal_and_wrong_bucket(self):
        peer = ObjectServer(); t = transport(peer)
        for path in ('../x', PATH+'/..', PATH.replace('institutions/', 'institutions/%2e%2e/'), PATH+'?x=1', '/'+PATH, PATH+'#x', PATH+'\\x'):
            with self.subTest(path=path), self.assertRaises(StorageHTTPFailure): t.get(old.settings().bucket, path)
        with self.assertRaises(StorageHTTPFailure): t.get('other-private', PATH)
        self.assertEqual(peer.methods, [])

    def test_redirect_not_followed_and_key_not_forwarded(self):
        requests = []
        def handler(r):
            requests.append(r)
            return httpx.Response(307, headers={'location': 'https://evil.test/steal'})
        with self.assertRaises(StorageHTTPFailure) as error:
            transport(handler).get(old.settings().bucket, PATH)
        self.assertEqual(error.exception.code, 'storage_redirect_blocked'); self.assertEqual(len(requests), 1)

    def test_429_500_503_classified_without_sleep_or_auto_retry(self):
        for status in (429, 500, 503):
            peer = ObjectServer(); peer.get_status = status
            with self.subTest(status=status), self.assertRaises(StorageHTTPFailure) as error:
                transport(peer).get(old.settings().bucket, PATH)
            self.assertTrue(error.exception.retryable); self.assertEqual(peer.methods, ['GET'])

    def test_retry_after_bounded_and_untrusted_values(self):
        for header, expected in (('99999', 3600), ('12', 12), ('invalid', None)):
            with self.subTest(header=header), self.assertRaises(StorageHTTPFailure) as error:
                transport(lambda _: httpx.Response(429, headers={'retry-after': header})).get(old.settings().bucket, PATH)
            self.assertEqual(error.exception.retry_after, expected)

    def test_nonretryable_statuses(self):
        for status in (400, 401, 403, 422):
            with self.subTest(status=status), self.assertRaises(StorageHTTPFailure) as error:
                transport(lambda _: httpx.Response(status)).get(old.settings().bucket, PATH)
            self.assertFalse(error.exception.retryable)

    def test_missing(self):
        with self.assertRaises(ObjectMissing): transport().get(old.settings().bucket, PATH)

    def test_duplicate_400_after_race_verified_by_bytes(self):
        peer = ObjectServer()
        def handler(r):
            if r.method == 'POST':
                peer.objects[r.url.path.split('/institutions/', 1)[1]] = r.content
            return peer(r)
        t = transport(handler); t.put_if_absent(old.settings().bucket, PATH, b'original')
        self.assertEqual(peer.methods.count('POST'), 1)

    def test_lost_upload_response_is_resolved_without_second_post(self):
        peer = ObjectServer(); peer.timeout_after = True
        t = transport(peer); t.put_if_absent(old.settings().bucket, PATH, b'original')
        t.put_if_absent(old.settings().bucket, PATH, b'original')
        self.assertEqual(peer.methods.count('POST'), 1)

    def test_error_after_stored_object_resolved_using_original(self):
        for status in (429, 500, 503):
            peer = ObjectServer(); peer.post_status = status; peer.store_on_error = True
            with self.subTest(status=status): transport(peer).put_if_absent(old.settings().bucket, PATH, b'original')
            self.assertEqual(peer.methods.count('POST'), 1)

    def test_failed_post_no_blind_retry(self):
        for status in (429, 500, 503, 400):
            peer = ObjectServer(); peer.post_status = status
            with self.subTest(status=status), self.assertRaises(StorageHTTPFailure) as error:
                transport(peer).put_if_absent(old.settings().bucket, PATH, b'original')
            self.assertTrue(error.exception.ambiguous); self.assertEqual(peer.methods, ['GET', 'POST', 'GET'])
            self.assertEqual(error.exception.retry_after, 7)

    def test_malformed_success_body_does_not_establish_success(self):
        peer = ObjectServer(); peer.json_body = b'{malformed provider body'
        transport(peer).put_if_absent(old.settings().bucket, PATH, b'original')
        self.assertEqual(peer.methods, ['GET', 'POST', 'GET'])
        # 2xx without an object must never be published.
        seen = []
        def handler(r):
            seen.append(r.method)
            return httpx.Response(200 if r.method == 'POST' else 404, content=b'{}')
        with self.assertRaises(StorageHTTPFailure) as error: transport(handler).put_if_absent(old.settings().bucket, PATH, b'original')
        self.assertEqual(error.exception.code, 'storage_upload_unconfirmed'); self.assertEqual(seen.count('POST'), 1)

    def test_existing_different_hash_cannot_be_overwritten(self):
        peer = ObjectServer(); t = transport(peer); t.put_if_absent(old.settings().bucket, PATH, b'original')
        with self.assertRaises(DomainError): t.put_if_absent(old.settings().bucket, PATH, b'different')
        self.assertEqual(peer.methods.count('POST'), 1)

    def test_partial_upload_rejected(self):
        peer = ObjectServer(); peer.partial = True
        with self.assertRaises(DomainError): transport(peer).put_if_absent(old.settings().bucket, PATH, b'original')

    def test_body_bounds_and_response_headers(self):
        for data in (b'', b'x'*(MAX_BYTES+1)):
            with self.subTest(length=len(data)), self.assertRaises(StorageHTTPFailure): transport().put_if_absent(old.settings().bucket, PATH, data)
        for headers, data in (({'content-length': '3'}, b'x'), ({'content-length': '-1'}, b'x'),
                              ({'content-length': str(MAX_BYTES+1)}, b'x'), ({'content-encoding': 'gzip'}, b'x'), ({}, b'')):
            with self.subTest(headers=headers), self.assertRaises(StorageHTTPFailure):
                transport(lambda _: httpx.Response(200, content=data, headers=headers)).get(old.settings().bucket, PATH)

    def test_20mib_local_protocol_only(self):
        peer = ObjectServer(); data = b'x'*MAX_BYTES; t = transport(peer)
        t.put_if_absent(old.settings().bucket, PATH, data)
        self.assertEqual(t.get(old.settings().bucket, PATH).sha256, sha(data))

    def test_get_timeout_and_exception_redaction(self):
        marker = old.MARKER
        def handler(_): raise httpx.ReadTimeout(marker)
        with self.assertRaises(StorageHTTPFailure) as error:
            transport(handler).get(old.settings().bucket, PATH)
        self.assertEqual(error.exception.code, 'storage_http_timeout')
        self.assertNotIn(marker, str(error.exception)); self.assertIsNone(error.exception.__context__)
        self.assertNotIn(marker, repr(transport())); self.assertNotIn(marker, repr(old.settings()))

    def test_response_deadline(self):
        with patch('apps.api.storage_http.time.monotonic', side_effect=[0, 100]):
            with self.assertRaises(StorageHTTPFailure) as error:
                transport(lambda _: httpx.Response(200, content=b'original')).get(old.settings().bucket, PATH)
        self.assertEqual(error.exception.code, 'storage_http_timeout')

    def test_no_cookie_reuse(self):
        seen = []
        def handler(r):
            seen.append(r.headers.get('cookie'))
            return httpx.Response(200, content=b'original', headers={'set-cookie': 'private=hidden'})
        t = transport(handler); t.get(old.settings().bucket, PATH); t.get(old.settings().bucket, PATH)
        self.assertEqual(seen, [None, None])

    def test_http_logs_do_not_include_keys_or_original(self):
        peer = ObjectServer(); t = transport(peer)
        with self.assertLogs('httpx', level='INFO') as captured:
            t.put_if_absent(old.settings().bucket, PATH, b'synthetic-sensitive-original-marker')
        log = '\n'.join(captured.output)
        for marker in (old.MARKER, GATEWAY.get_secret_value(), 'synthetic-sensitive-original-marker'):
            self.assertNotIn(marker, log)

    def test_chunked_body_exceeding_limit_is_rejected(self):
        class Stream(httpx.SyncByteStream):
            def __iter__(self):
                for _ in range(MAX_BYTES//65536+1): yield b'x'*65536
        with self.assertRaises(StorageHTTPFailure) as error:
            transport(lambda _: httpx.Response(200, stream=Stream())).get(old.settings().bucket, PATH)
        self.assertEqual(error.exception.code, 'storage_download_size_limit')

    def test_response_partial_content_is_not_a_full_original(self):
        with self.assertRaises(StorageHTTPFailure):
            transport(lambda _: httpx.Response(206, content=b'partial')).get(old.settings().bucket, PATH)

    def test_delete_and_update_methods_forbidden(self):
        peer = ObjectServer(); t = transport(peer)
        for method in ('DELETE', 'PUT', 'PATCH', 'HEAD'):
            with self.subTest(method=method), self.assertRaises(StorageHTTPFailure):
                t._request(method, old.settings().bucket, PATH)
        self.assertEqual(peer.methods, [])

    def test_timeout_before_upload_leaves_ambiguous_retryable_state(self):
        seen = []
        def handler(r):
            seen.append(r.method)
            if r.method == 'POST': raise httpx.WriteTimeout(old.MARKER)
            return httpx.Response(404)
        with self.assertRaises(StorageHTTPFailure) as error:
            transport(handler).put_if_absent(old.settings().bucket, PATH, b'original')
        self.assertTrue(error.exception.ambiguous); self.assertTrue(error.exception.retryable)
        self.assertEqual(seen, ['GET', 'POST', 'GET'])

    def test_auth_failure_never_becomes_success(self):
        for status in (401, 403, 307):
            seen = []
            def handler(r):
                seen.append(r.method)
                return httpx.Response(status if r.method == 'POST' else 404)
            with self.subTest(status=status), self.assertRaises(StorageHTTPFailure):
                transport(handler).put_if_absent(old.settings().bucket, PATH, b'original')
            self.assertEqual(seen, ['GET', 'POST'])

    def test_unknown_handler_exception_does_not_leak_body_or_key(self):
        def handler(_): raise RuntimeError(old.MARKER)
        with self.assertRaises(StorageHTTPFailure) as error:
            transport(handler).get(old.settings().bucket, PATH)
        self.assertEqual(str(error.exception), 'storage_http_invalid_response')
        self.assertIsNone(error.exception.__context__)

    def test_unverified_inventory_blocks_without_network(self):
        peer = ObjectServer()
        with self.assertRaises(StorageHTTPFailure) as error: transport(peer).list_page(old.settings().bucket, '', 0, 100)
        self.assertEqual(error.exception.code, 'storage_inventory_contract_unverified'); self.assertEqual(peer.methods, [])


class HTTPStoreTests(unittest.TestCase):
    postgres = False
    def setUp(self):
        Path('work/storage-http-tests').mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir='work/storage-http-tests')
        root = Path(self.tmp.name)
        if self.postgres:
            from apps.api.postgres import PostgresDatabase, PostgresRepository
            database = PostgresDatabase(DSN, 'sb_http_'+secrets.token_hex(8), local_test=True)
            database.migrate(); self.repo = PostgresRepository(database)
        else: self.repo = Repository(root/'metadata.sqlite3')
        self.peer = ObjectServer(); self.http = transport(self.peer)
        self.store = PrivateOriginalStore(self.repo, old.settings(), self.http)
        self.app = create_app(root, repository=self.repo, store=self.store, parsing_enabled=True)
        self.docs = self.app.state.service
    def tearDown(self): self.tmp.cleanup()
    def register(self): return self.docs.register(old.A, 'synthetic.pdf', 'application/pdf', fixtures.pdf())[0]
    def test_registration_original_integrity_and_duplicate(self):
        meta = self.register(); duplicate, exists = self.docs.register(old.A, 'copy.pdf', 'application/pdf', fixtures.pdf())
        self.assertTrue(exists); self.assertEqual(meta['id'], duplicate['id'])
        body, _ = self.docs.original(old.A, meta['document_id'], meta['id'])
        self.assertEqual(sha(body), meta['sha256']); self.assertEqual(self.peer.methods.count('POST'), 1)
    def test_cross_institution_and_reader_denied_before_transport(self):
        meta = self.register(); count = len(self.peer.methods)
        for principal in (old.B, old.R):
            with self.subTest(role=principal.role), self.assertRaises(DomainError): self.store.read(principal, meta['id'], meta['sha256'])
        self.assertEqual(len(self.peer.methods), count)
    def test_wrong_expected_hash_rejected_before_download(self):
        meta = self.register(); count = len(self.peer.methods)
        with self.assertRaises(DomainError): self.store.read(old.A, meta['id'], '0'*64)
        self.assertEqual(len(self.peer.methods), count)
    def test_unregistered_document_worker_denied(self):
        meta = self.register(); self.docs.deregister(old.A, meta['document_id']); count = len(self.peer.methods)
        with self.assertRaises(DomainError): self.store.read(old.W, meta['id'], meta['sha256'])
        self.assertEqual(len(self.peer.methods), count)
    def test_partial_object_quarantined_no_version(self):
        self.peer.partial = True
        with self.assertRaises(DomainError): self.register()
        with self.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0], 0)
            self.assertEqual(db.connection.execute('SELECT state FROM private_storage_objects').fetchone()[0], 'quarantined')
    def test_object_stored_db_failure_preserves_unpublished_original(self):
        with patch.object(DocumentUnitOfWork, 'insert_version', side_effect=RuntimeError('synthetic db failure')):
            with self.assertRaises(RuntimeError): self.register()
        self.assertEqual(len(self.peer.objects), 1)
        with self.repo.transaction() as db:
            self.assertEqual(db.connection.execute('SELECT COUNT(*) FROM versions').fetchone()[0], 0)
            self.assertEqual(db.connection.execute('SELECT status FROM upload_intents').fetchone()[0], 'failed')
        # No guessed inventory API: full orphan scan is explicitly blocked.
        with self.assertRaises(DomainError): self.store.reconcile(old.A)
        self.assertEqual(len(self.peer.objects), 1)
    def test_intent_retry_after_timeout_probes_before_post(self):
        key = secrets.token_hex(16)
        with self.repo.transaction() as db: db.start_intent(key, old.A.institution_id, now())
        self.peer.post_status = 503
        with self.assertRaises(DomainError): self.store.write(old.A, key, fixtures.pdf())
        self.peer.post_status = 200
        self.store.write(old.A, key, fixtures.pdf())
        self.assertEqual(self.peer.methods.count('POST'), 2)
        self.assertEqual(self.store.read(old.A, key, sha(fixtures.pdf())), fixtures.pdf())
    def test_retry_limit_and_unknown_state(self):
        key = secrets.token_hex(16)
        with self.repo.transaction() as db: db.start_intent(key, old.A.institution_id, now())
        self.peer.post_status = 503
        for _ in range(3):
            with self.assertRaises(DomainError): self.store.write(old.A, key, fixtures.pdf())
        count = len(self.peer.methods)
        with self.assertRaises(DomainError) as error: self.store.write(old.A, key, fixtures.pdf())
        self.assertEqual(error.exception.code, 'storage_retry_limit'); self.assertEqual(len(self.peer.methods), count)
    def test_original_changed_after_registration_is_rejected(self):
        meta = self.register()
        # URL suffix key in ObjectServer excludes the initial institutions/.
        key = object_path('A', meta['id'])[len('institutions/'):]
        self.peer.objects[key] = b'tampered original'
        with self.assertRaises(DomainError) as error: self.store.read(old.A, meta['id'], meta['sha256'])
        self.assertEqual(error.exception.code, 'original_integrity_failure')

    def test_settings_mismatch_rejected(self):
        with self.assertRaises(DomainError):
            PrivateOriginalStore(self.repo, old.settings().model_copy(update={'bucket':'different-bucket'}), self.http)
    def test_http_backup_not_misrepresented_as_fake_atomic_backup(self):
        with self.assertRaises(DomainError): StorageBackupService(self.repo, self.store)


@unittest.skipUnless(DSN, 'BLOCKED: isolated loopback PostgreSQL not configured')
class PostgreSQLHTTPStoreTests(HTTPStoreTests):
    postgres = True
