"""Local BFF sessions; provider tokens never enter browser responses or session storage."""
from dataclasses import dataclass
from urllib.parse import urlsplit
import secrets
import time
import hmac
import hashlib
import re
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal
from .auth_store import digest
from .identity_provider import UnconfiguredProvider, ProviderUnavailable
from .models import Principal


@dataclass(frozen=True)
class AuthSettings:
    origin: str = 'https://localhost'
    secure_cookie: bool = True
    ttl: int = 1800
    idle: int = 900

    def __post_init__(self):
        p = urlsplit(self.origin)
        if p.path or p.query or p.fragment or p.username or not p.hostname or self.ttl <= 0 or self.idle <= 0:
            raise ValueError('invalid_auth_settings')
        if not self.secure_cookie and (p.scheme != 'http' or p.hostname not in ('127.0.0.1', 'localhost')):
            raise ValueError('insecure_cookie_only_loopback_development')
        if self.secure_cookie and p.scheme != 'https':
            raise ValueError('https_required')

    @property
    def cookie(self):
        return '__Host-seomuitda' if self.secure_cookie else 'seomuitda-dev'


class Login(BaseModel):
    model_config = ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1, max_length=1024, repr=False)


class MembershipUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['reader', 'manager']
    active: bool
    institution_admin: bool = False


def csrf_for(sid):
    return hmac.new(sid.encode(), b'seomuitda-csrf-v1', hashlib.sha256).hexdigest()


class AuthService:
    def __init__(self, store, provider=None, settings=None, clock=time.time, session_guard=None):
        self.store = store
        self.provider = provider or UnconfiguredProvider()
        self.settings = settings or AuthSettings()
        self.clock = clock
        from .session_revalidation import SessionRevalidation
        if session_guard is not None and type(session_guard) is not SessionRevalidation:raise ValueError('invalid_session_guard')
        self.session_guard=session_guard

    def origin(self, request):
        if request.headers.get('origin') != self.settings.origin or request.headers.get('sec-fetch-site') == 'cross-site':
            raise HTTPException(403, 'origin_rejected')

    def cookie(self, request, name):
        matches = [p for p in request.headers.get('cookie', '').split(';') if p.strip().split('=', 1)[0] == name]
        value = request.cookies.get(name, '')
        if len(matches) != 1 or not re.fullmatch('[A-Za-z0-9_-]{43}', value):
            raise HTTPException(401, 'invalid_session')
        return value

    def set_cookie(self, response, name, value, max_age):
        response.set_cookie(name, value, max_age=max_age, secure=self.settings.secure_cookie,
                            httponly=True, samesite='lax', path='/')
        response.headers['Cache-Control'] = 'no-store'

    def challenge(self, request, response):
        self.origin(request)
        nonce, csrf, now = secrets.token_urlsafe(32), secrets.token_urlsafe(32), self.clock()
        with self.store.transaction() as db:
            db.execute('DELETE FROM auth_challenges WHERE expires<?', (now,))
            db.execute('INSERT INTO auth_challenges VALUES(?,?,?)', (digest(nonce), digest(csrf), now + 300))
        self.set_cookie(response, self.settings.cookie + '-login', nonce, 300)
        return {'csrf_token': csrf}

    def login(self, request, response, body):
        self.origin(request)
        nonce = self.cookie(request, self.settings.cookie + '-login')
        csrf, now = request.headers.get('x-csrf-token', ''), self.clock()
        with self.store.transaction() as db:
            row = db.execute('SELECT * FROM auth_challenges WHERE nonce_hash=?', (digest(nonce),)).fetchone()
            if not row or row['expires'] <= now or not hmac.compare_digest(row['csrf_hash'], digest(csrf)):
                raise HTTPException(403, 'csrf_rejected')
            db.execute('DELETE FROM auth_challenges WHERE nonce_hash=?', (digest(nonce),))
            key = digest(request.client.host if request.client else 'unknown')
            limit = db.execute('SELECT * FROM auth_login_limits WHERE client_hash=?', (key,)).fetchone()
            if limit and limit['window'] > now - 300 and limit['attempts'] >= 10:
                raise HTTPException(429, 'login_rate_limit')
            count = limit['attempts'] + 1 if limit and limit['window'] > now - 300 else 1
            window = limit['window'] if count > 1 else now
            db.execute('INSERT OR REPLACE INTO auth_login_limits VALUES(?,?,?)', (key, window, count))
        try:
            identity = self.provider.authenticate(body.email, body.password)
            if self.session_guard is not None and self.session_guard.status(identity.issuer,identity.subject)!='active':raise ProviderUnavailable()
        except ProviderUnavailable:
            with self.store.transaction() as db:
                self.store.audit(db, 'login', outcome='provider_unavailable', at=now)
            raise HTTPException(503, 'identity_provider_unavailable') from None
        with self.store.transaction() as db:
            user = db.execute('SELECT * FROM identities WHERE issuer=? AND subject=? AND active=1',
                              (identity.issuer, identity.subject)).fetchone()
            members = [] if not user else db.execute('''SELECT m.*,o.name FROM memberships m
              JOIN organizations o ON o.id=m.institution_id WHERE user_id=? AND m.active=1
              AND o.active=1 ORDER BY m.institution_id''', (user['id'],)).fetchall()
            if len(members) != 1:
                raise HTTPException(403, 'active_single_membership_required')
            member, sid = members[0], secrets.token_urlsafe(32)
            expires = now + min(self.settings.ttl, identity.ttl, self.session_guard.max_seconds if self.session_guard else self.settings.ttl)
            db.execute('INSERT INTO sessions(sid_hash,user_id,institution_id,csrf_hash,expires,touched) VALUES(?,?,?,?,?,?)',
                       (digest(sid), user['id'], member['institution_id'], digest(csrf_for(sid)), expires, now))
            old = request.cookies.get(self.settings.cookie)
            if old:
                db.execute('UPDATE sessions SET revoked=1 WHERE sid_hash=?', (digest(old),))
            self.store.audit(db, 'login', user['id'], member['institution_id'], at=now)
        self.set_cookie(response, self.settings.cookie, sid, max(1, int(expires - now)))
        response.delete_cookie(self.settings.cookie + '-login', path='/', secure=self.settings.secure_cookie,
                               httponly=True, samesite='lax')
        return self.public(user['id'], member, csrf_for(sid))

    @staticmethod
    def public(user, member, csrf):
        return {'user_id': user, 'institution_id': member['institution_id'], 'institution_name': member['name'],
                'role': member['role'], 'institution_admin': bool(member['institution_admin']), 'csrf_token': csrf}

    def _revalidate_provider(self,sid,at):
        revoked=False
        try:
            with self.store.transaction() as db:
                row=db.execute('''SELECT i.issuer,i.subject FROM sessions s
                  JOIN identities i ON i.id=s.user_id AND i.active=1
                  JOIN memberships m ON m.user_id=s.user_id AND m.institution_id=s.institution_id AND m.active=1
                  JOIN organizations o ON o.id=s.institution_id AND o.active=1
                  WHERE s.sid_hash=? AND s.revoked=0 AND s.expires>? AND s.touched>?''',
                  (digest(sid),at,at-self.settings.idle)).fetchone()
                if row and self.session_guard.status(row['issuer'],row['subject'])!='active':
                    db.execute('UPDATE sessions SET revoked=1 WHERE sid_hash=?',(digest(sid),));revoked=True
        except ProviderUnavailable:raise HTTPException(503,'identity_revalidation_unavailable') from None
        # Raise after commit: an account reactivation must not revive this revoked session.
        if revoked:raise HTTPException(401,'session_expired_or_revoked')

    def resolve(self, request, mutation=None):
        if not self.provider.available:
            raise HTTPException(401, 'authentication_not_configured')
        sid, now = self.cookie(request, self.settings.cookie), self.clock()
        if self.session_guard is not None:self._revalidate_provider(sid,now)
        with self.store.transaction() as db:
            row = db.execute('''SELECT s.*,m.role,m.institution_admin,o.name FROM sessions s
              JOIN identities i ON i.id=s.user_id AND i.active=1
              JOIN memberships m ON m.user_id=s.user_id AND m.institution_id=s.institution_id AND m.active=1
              JOIN organizations o ON o.id=s.institution_id AND o.active=1
              WHERE s.sid_hash=? AND s.revoked=0 AND i.issuer=COALESCE(?,i.issuer)''',
                (digest(sid),getattr(self.provider,'issuer',None))).fetchone()
            if not row or row['expires'] <= now or row['touched'] <= now - self.settings.idle:
                raise HTTPException(401, 'session_expired_or_revoked')
            memberships=db.execute('''SELECT COUNT(*) FROM memberships m JOIN organizations o ON o.id=m.institution_id
              WHERE m.user_id=? AND m.active=1 AND o.active=1''',(row['user_id'],)).fetchone()[0]
            if memberships!=1:
                raise HTTPException(401, 'active_single_membership_required')
            unsafe = mutation if mutation is not None else request.method not in ('GET', 'HEAD', 'OPTIONS')
            if unsafe:
                self.origin(request)
                if not hmac.compare_digest(row['csrf_hash'], digest(request.headers.get('x-csrf-token', ''))):
                    raise HTTPException(403, 'csrf_rejected')
            db.execute('UPDATE sessions SET touched=? WHERE sid_hash=?', (now, digest(sid)))
        request.state.auth = dict(row)
        return Principal(row['user_id'], row['institution_id'], row['role'])

    def me(self, request, response):
        p = self.resolve(request)
        response.headers['Cache-Control'] = 'no-store'
        return self.public(p.subject, request.state.auth, csrf_for(self.cookie(request, self.settings.cookie)))

    def logout(self, request, response):
        p = self.resolve(request, True)
        with self.store.transaction() as db:
            db.execute('UPDATE sessions SET revoked=1 WHERE sid_hash=?', (request.state.auth['sid_hash'],))
            self.store.audit(db, 'logout', p.subject, p.institution_id, at=self.clock())
        response.delete_cookie(self.settings.cookie, path='/', secure=self.settings.secure_cookie,
                               httponly=True, samesite='lax')
        response.headers['Cache-Control'] = 'no-store'
        return {'logged_out': True}

    def _admin_in(self, db, request):
        # Recheck inside the mutation/read transaction; resolve() may precede a concurrent revocation.
        at=self.clock()
        row=db.execute('''SELECT s.user_id FROM sessions s
          JOIN identities i ON i.id=s.user_id AND i.active=1
          JOIN memberships m ON m.user_id=s.user_id AND m.institution_id=s.institution_id AND m.active=1
          JOIN organizations o ON o.id=s.institution_id AND o.active=1
          WHERE s.sid_hash=? AND s.revoked=0 AND s.expires>? AND s.touched>?
          AND m.institution_admin=1 AND i.issuer=COALESCE(?,i.issuer)
          AND (SELECT COUNT(*) FROM memberships other JOIN organizations org ON org.id=other.institution_id
               WHERE other.user_id=s.user_id AND other.active=1 AND org.active=1)=1''',
          (request.state.auth['sid_hash'],at,at-self.settings.idle,getattr(self.provider,'issuer',None))).fetchone()
        if not row:raise HTTPException(403,'institution_admin_required')

    def members(self, request):
        self.resolve(request)
        if not request.state.auth['institution_admin']:
            raise HTTPException(403, 'institution_admin_required')
        with self.store.transaction() as db:
            self._admin_in(db,request)
            return [dict(r) for r in db.execute('SELECT user_id,role,active,institution_admin FROM memberships WHERE institution_id=?',
                                               (request.state.auth['institution_id'],))]

    def update_member(self, request, user_id, body):
        p = self.resolve(request, True)
        if not request.state.auth['institution_admin']:
            raise HTTPException(403, 'institution_admin_required')
        if p.subject == user_id:
            raise HTTPException(409, 'self_membership_change_forbidden')
        with self.store.transaction() as db:
            self._admin_in(db,request)
            row = db.execute('SELECT * FROM memberships WHERE user_id=? AND institution_id=?', (user_id, p.institution_id)).fetchone()
            if not row:
                raise HTTPException(404, 'membership_not_found')
            admins = db.execute('SELECT COUNT(*) FROM memberships WHERE institution_id=? AND active=1 AND institution_admin=1',
                                (p.institution_id,)).fetchone()[0]
            if row['active'] and row['institution_admin'] and admins <= 1 and (not body.active or not body.institution_admin):
                raise HTTPException(409, 'last_admin_required')
            db.execute('UPDATE memberships SET role=?,active=?,institution_admin=? WHERE user_id=? AND institution_id=?',
                       (body.role, int(body.active), int(body.institution_admin), user_id, p.institution_id))
            db.execute('UPDATE sessions SET revoked=1 WHERE user_id=? AND institution_id=?', (user_id, p.institution_id))
            self.store.audit(db, 'membership_change', p.subject, p.institution_id, at=self.clock())
        return {'updated': True}
