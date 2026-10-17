"""Real HTTP serialization with MockTransport only; inherited BFF security regressions."""
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import NAMESPACE_URL, uuid5

import httpx
import test_auth

from apps.api.identity_provider import ProviderUnavailable, SupabaseProviderAdapter
from apps.api.main import create_app
from apps.api.supabase_transport import SupabaseHTTPTransport, SupabaseSettings

URL = 'https://abcdefghijklmnopqrst.supabase.co'
KEY = 'sb_publishable_' + 'synthetic_test_only_123456'
SUBJECT = '11111111-1111-4111-8111-111111111111'


def token(**extra):
    return {'access_token': 'synthetic-access-only', 'token_type': 'bearer',
            'expires_in': 600, 'expires_at': 1600, 'user': {'id': SUBJECT},
            'refresh_token': 'synthetic-refresh-only', **extra}


def user(**extra):
    return {'id': SUBJECT, 'aud': 'authenticated', 'is_anonymous': False,
            'user_metadata': {'role': 'manager', 'institution_id': 'foreign'}, **extra}


class TransportTests(unittest.TestCase):
    def provider(self, handler):
        settings = SupabaseSettings(URL, KEY)
        return SupabaseProviderAdapter(SupabaseHTTPTransport(settings, mock_transport=httpx.MockTransport(handler)),
                                       settings.issuer, clock=lambda: 1000)

    def responses(self, first=None, second=None):
        return self.provider(lambda r: httpx.Response(200, json=(token() if first is None else first)
                             if r.method == 'POST' else (user() if second is None else second)))

    def test_valid_request_serialization_and_verified_user(self):
        calls = []
        def handler(request):
            calls.append(request)
            self.assertEqual(request.headers['apikey'], KEY)
            self.assertEqual(request.url.host, 'abcdefghijklmnopqrst.supabase.co')
            self.assertEqual(request.extensions['timeout'], dict(connect=5., read=5., write=5., pool=5.))
            if request.method == 'POST':
                self.assertEqual(str(request.url), URL + '/auth/v1/token?grant_type=password')
                self.assertEqual(json.loads(request.content), {'email': 'synthetic@test', 'password': 'test-only'})
                self.assertNotIn('authorization', request.headers)
                return httpx.Response(200, json=token(), headers={'Set-Cookie': 'untrusted=provider-cookie'})
            self.assertEqual(request.url.path, '/auth/v1/user')
            self.assertEqual(request.headers['authorization'], 'Bearer synthetic-access-only')
            self.assertNotIn('cookie', request.headers)
            return httpx.Response(200, json=user())
        identity = self.provider(handler).authenticate('synthetic@test', 'test-only')
        self.assertEqual((identity.issuer, identity.subject), (URL + '/auth/v1', SUBJECT))
        self.assertTrue(1 <= identity.ttl <= 600)
        self.assertEqual(len(calls), 2)
        self.assertNotIn('synthetic-access-only', repr(identity))

    def test_invalid_urls(self):
        for url in ['http://abcdefghijklmnopqrst.supabase.co', URL + ':443', URL + '/auth/v1',
                    URL + '?x=1', URL + '#x', URL.replace('https://', 'https://u:p@'),
                    'https://127.0.0.1', 'https://localhost', 'https://metadata.google.internal',
                    URL + '.attacker.test', URL.upper(), URL + '/%2e%2e', URL + '\\@evil.test']:
            with self.subTest(url=url), self.assertRaisesRegex(ValueError, '^invalid_supabase_settings$'):
                SupabaseSettings(url, KEY)

    def test_invalid_keys_and_timeouts(self):
        for key in ['', None, 'sb_secret_test', 'service_role', KEY + '\r\nInjected: bad', 'x' * 5000]:
            with self.subTest(key_type=type(key).__name__), self.assertRaises(ValueError):
                SupabaseSettings(URL, key)
        for timeout in [0, -.1, 11, True, float('nan'), float('inf'), '5']:
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                SupabaseSettings(URL, KEY, timeout)
        self.assertNotIn(KEY, repr(SupabaseSettings(URL, KEY)))

    def test_legacy_anon_gateway_key_only(self):
        def key(claims):
            encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
            return 'eyJhbGciOiJIUzI1NiJ9.' + encoded + '.synthetic_signature'
        self.assertIsInstance(SupabaseSettings(URL, key({'role': 'anon', 'ref': 'abcdefghijklmnopqrst'})), SupabaseSettings)
        for claims in [{'role': 'service_role', 'ref': 'abcdefghijklmnopqrst'},
                       {'role': 'anon', 'ref': 'foreign'}, {}, []]:
            with self.subTest(claims=claims), self.assertRaises(ValueError):
                SupabaseSettings(URL, key(claims))

    def test_fixed_endpoints_and_headers_only(self):
        calls = []
        transport = self.provider(lambda r: calls.append(r)).transport
        for method, path, headers in [('GET', 'https://evil.test', {}), ('GET', '//evil.test', {}),
                                      ('POST', '/auth/v1/admin/users', {}),
                                      ('GET', '/auth/v1/user', {'Authorization': 'Bearer x\r\nBad: x'}),
                                      ('GET', '/auth/v1/user', {'Authorization': 'Bearer x', 'apikey': 'override'})]:
            with self.subTest(path=path), self.assertRaises(ProviderUnavailable):
                transport.request(method, path, headers=headers)
        self.assertEqual(calls, [])

    def test_transport_type_and_issuer_binding(self):
        settings = SupabaseSettings(URL, KEY)
        with self.assertRaises(ValueError):
            SupabaseHTTPTransport(settings, mock_transport=httpx.HTTPTransport())
        with self.assertRaises(ValueError):
            SupabaseProviderAdapter(SupabaseHTTPTransport(settings), 'https://foreign.test/auth/v1')

    def test_bad_status_no_retry_or_redirect_at_both_endpoints(self):
        for endpoint in ['POST', 'GET']:
            for status in [301, 302, 307, 308, 400, 401, 403, 404, 422, 429, 500, 503]:
                calls = []
                def handler(request):
                    calls.append(request)
                    if request.method == endpoint:
                        return httpx.Response(status, text='sensitive-provider-body', headers={'Location': 'https://evil.test'})
                    return httpx.Response(200, json=token())
                with self.subTest(endpoint=endpoint, status=status), self.assertRaises(ProviderUnavailable) as e:
                    self.provider(handler).authenticate('synthetic@test', 'test-only')
                self.assertEqual(str(e.exception), '')
                self.assertEqual(len(calls), 1 if endpoint == 'POST' else 2)

    def test_network_failures_are_sanitized(self):
        for error in [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.WriteTimeout,
                      httpx.PoolTimeout, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError]:
            for endpoint in ['POST', 'GET']:
                def handler(request):
                    if request.method == endpoint:
                        raise error('password token api-key sensitive', request=request)
                    return httpx.Response(200, json=token())
                with self.subTest(error=error.__name__, endpoint=endpoint), self.assertRaises(ProviderUnavailable) as e:
                    self.provider(handler).authenticate('synthetic@test', 'test-only')
                self.assertEqual(str(e.exception), '')
                self.assertTrue(e.exception.__suppress_context__)

    def test_response_shape_content_type_and_size(self):
        bad = [httpx.Response(200, text='not json'), httpx.Response(200, json=[]),
               httpx.Response(200, content=b'{', headers={'Content-Type': 'application/json'}),
               httpx.Response(200, json={'padding': 'x' * 65536})]
        for response in bad:
            with self.subTest(response_type=response.headers.get('content-type')), self.assertRaises(ProviderUnavailable):
                self.provider(lambda r: response).authenticate('synthetic@test', 'test-only')

    def test_no_decompression_or_unbounded_streaming(self):
        class LargeBody(httpx.SyncByteStream):
            def __init__(self):
                self.reads, self.closed = 0, False
            def __iter__(self):
                for _ in range(100):
                    self.reads += 1
                    yield b'x' * 4096
            def close(self):
                self.closed = True
        stream = LargeBody()
        with self.assertRaises(ProviderUnavailable):
            self.provider(lambda r: httpx.Response(200, stream=stream,
                          headers={'Content-Type': 'application/json'})).authenticate('synthetic@test', 'test-only')
        self.assertLess(stream.reads, 100)
        self.assertTrue(stream.closed)
        with self.assertRaises(ProviderUnavailable):
            self.provider(lambda r: httpx.Response(200, stream=LargeBody(),
                          headers={'Content-Type': 'application/json', 'Content-Encoding': 'gzip'})).authenticate('synthetic@test', 'test-only')

    def test_authentication_elapsed_time_cannot_extend_token_lifetime(self):
        with patch('apps.api.identity_provider.time.monotonic', side_effect=[0, 0, 0, 0, 0, 601]):
            with self.assertRaises(ProviderUnavailable):
                self.responses().authenticate('synthetic@test', 'test-only')

    def test_invalid_token_responses_never_verify_user(self):
        for first in [token(access_token=''), token(access_token='bad\nheader'), token(access_token=None),
                      token(access_token='x' * 8193), token(token_type='mac'), token(expires_in=True),
                      token(expires_in=0), token(expires_in=90000), token(expires_in='600')]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(200, json=first)
            with self.subTest(fields=list(first)), self.assertRaises(ProviderUnavailable):
                self.provider(handler).authenticate('synthetic@test', 'test-only')
            self.assertEqual(len(calls), 1)

    def test_verified_user_and_token_identity_must_match(self):
        for second in [user(id='forged'), user(id='22222222-2222-4222-8222-222222222222'),
                       user(aud='anon'), user(is_anonymous=True), user(banned_until='future'),
                       user(deleted_at='past'), {}, []]:
            with self.subTest(user=second), self.assertRaises(ProviderUnavailable):
                self.responses(second=second).authenticate('synthetic@test', 'test-only')
        for first in [token(user={}), token(user=None)]:
            with self.assertRaises(ProviderUnavailable):
                self.responses(first=first).authenticate('synthetic@test', 'test-only')

    def test_expired_identity_and_ttl_bounds(self):
        for expiry in [1000, 999, True, '1600']:
            with self.subTest(expiry=expiry), self.assertRaises(ProviderUnavailable):
                self.responses(first=token(expires_at=expiry)).authenticate('synthetic@test', 'test-only')
        identity = self.responses(first=token(expires_in=86400, expires_at=90000)).authenticate('synthetic@test', 'test-only')
        self.assertEqual(identity.ttl, 3600)
        identity = self.responses(first=token(expires_at=1005)).authenticate('synthetic@test', 'test-only')
        self.assertTrue(1 <= identity.ttl <= 5)

    def test_provider_rejection_of_forged_or_expired_bearer(self):
        for response in [401, 403]:
            def handler(request):
                return httpx.Response(200, json=token()) if request.method == 'POST' else httpx.Response(response)
            with self.subTest(status=response), self.assertRaises(ProviderUnavailable):
                self.provider(handler).authenticate('synthetic@test', 'test-only')

    def test_tls_and_proxy_defaults_no_construction_requests(self):
        with patch('httpx.Client', wraps=httpx.Client) as client:
            p = self.responses()
            client.assert_not_called()
            p.authenticate('synthetic@test', 'test-only')
            self.assertEqual(client.call_count, 2)
            for call in client.call_args_list:
                self.assertIs(call.kwargs['verify'], True)
                self.assertIs(call.kwargs['trust_env'], True)
                self.assertIs(call.kwargs['follow_redirects'], False)

    def test_app_configuration_is_explicit_and_default_is_closed(self):
        with tempfile.TemporaryDirectory() as root, patch('httpx.Client') as client:
            app = create_app(Path(root) / 'default')
            self.assertFalse(app.state.auth.provider.available)
            app = create_app(Path(root) / 'configured', supabase_settings=SupabaseSettings(URL, KEY))
            self.assertTrue(app.state.auth.provider.remote_enabled)
            client.assert_not_called()
            with self.assertRaises(ValueError):
                create_app(Path(root) / 'ambiguous', identity_provider=app.state.auth.provider,
                           supabase_settings=SupabaseSettings(URL, KEY))


class RemoteHTTPAuthTests(test_auth.AuthTests):
    """Reuse all 30 existing BFF permission tests with the real transport + mock HTTP."""
    def setUp(self):
        super().setUp()
        settings = SupabaseSettings(URL, KEY)
        def subject(email):
            return str(uuid5(NAMESPACE_URL, 'synthetic:' + email))
        with self.store.transaction() as db:
            for email in ['manager@test', 'reader@test', 'foreign@test']:
                db.execute('UPDATE identities SET issuer=?,subject=? WHERE subject=?',
                           (settings.issuer, subject(email), email))
        def handler(request):
            self.calls.append((request.method, request.url.raw_path.decode()))
            self.assertEqual(request.headers['apikey'], KEY)
            if request.method == 'POST':
                email = json.loads(request.content)['email']
                return httpx.Response(200, json=token(access_token=email, expires_at=int(self.now[0]) + 600,
                                                     user={'id': subject(email)}))
            email = request.headers['Authorization'].split(' ', 1)[1]
            return httpx.Response(200, json=user(id=subject(email)))
        self.provider = SupabaseProviderAdapter(SupabaseHTTPTransport(settings, mock_transport=httpx.MockTransport(handler)),
                                                settings.issuer, clock=lambda: self.now[0])
        self.app.state.auth.provider = self.provider

    def test_remote_status_exposes_only_availability(self):
        self.assertEqual(self.client.get('/auth/status').json(), {'provider_available': True, 'remote_enabled': True})

    def test_bad_origin_and_csrf_do_not_call_provider(self):
        self.assertEqual(self.client.post('/auth/login', headers={'Origin': 'https://evil.test'},
                         json={'email': 'synthetic@test', 'password': 'test-only'}).status_code, 403)
        self.client.post('/auth/csrf', headers={'Origin': 'https://local.test'})
        self.assertEqual(self.client.post('/auth/login', headers={'Origin': 'https://local.test', 'X-CSRF-Token': 'forged'},
                         json={'email': 'synthetic@test', 'password': 'test-only'}).status_code, 403)
        self.assertEqual(self.calls, [])

    def test_remote_error_no_session_or_secret_leak(self):
        self.provider.transport = SupabaseHTTPTransport(SupabaseSettings(URL, KEY), mock_transport=httpx.MockTransport(
            lambda r: httpx.Response(401, json={'message': 'test-only synthetic-access-only ' + KEY})))
        with self.assertLogs('httpx', level='INFO') as captured:
            response = self.login()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('__Host-seomuitda=', response.headers.get('set-cookie', ''))
        for sensitive in [KEY, 'synthetic-access-only', 'synthetic-test-only']:
            self.assertNotIn(sensitive, response.text + '\n'.join(captured.output))
        with self.store.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_success_does_not_persist_or_log_provider_credentials(self):
        with self.assertLogs('httpx', level='INFO') as captured:
            response = self.login()
        self.assertEqual(response.status_code, 200)
        with self.store.transaction() as db:
            dump = '\n'.join(db.iterdump())
        output = dump + response.text + str(response.headers) + '\n'.join(captured.output)
        for sensitive in [KEY, 'synthetic-test-only', 'synthetic-refresh-only', 'manager@test']:
            self.assertNotIn(sensitive, output)

    def test_inactive_account_org_or_membership_cannot_login(self):
        for table, where in [('identities', 'id'), ('organizations', 'id'), ('memberships', 'user_id')]:
            target = 'A' if table == 'organizations' else self.a
            with self.subTest(table=table):
                with self.store.transaction() as db:
                    db.execute(f'UPDATE {table} SET active=0 WHERE {where}=?', (target,))
                self.assertEqual(self.login().status_code, 403)
                with self.store.transaction() as db:
                    self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)
                    db.execute(f'UPDATE {table} SET active=1 WHERE {where}=?', (target,))
