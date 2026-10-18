"""Explicit trusted offline operator procedure. No public endpoint, email rules or startup provisioning."""
import re
import secrets
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .auth_store import AuthStore
from .errors import DomainError

CONFIRMATION='CREATE_INITIAL_INSTITUTION_ADMIN'


class InitialAdministrator(BaseModel):
    model_config=ConfigDict(strict=True,frozen=True,extra='forbid',hide_input_in_errors=True)
    issuer: str=Field(pattern=r'^https://[a-z0-9]{20}\.supabase\.co/auth/v1$',repr=False)
    subject: str=Field(repr=False)
    institution_id: str=Field(pattern=r'^[A-Za-z0-9_-]{1,100}$')
    institution_name: str=Field(min_length=1,max_length=200,repr=False)
    @model_validator(mode='after')
    def validate_subject(self):
        if str(UUID(self.subject))!=self.subject or not self.institution_name.strip() or not re.fullmatch(r'https://[a-z0-9]{20}\.supabase\.co/auth/v1',self.issuer) or not re.fullmatch('[A-Za-z0-9_-]{1,100}',self.institution_id):raise ValueError('invalid_initial_administrator')
        return self


def bootstrap_initial_administrator(store,request,*,confirmation):
    from .postgres import PostgresAuthStore
    if type(store) not in (AuthStore,PostgresAuthStore) or type(request) is not InitialAdministrator or confirmation!=CONFIRMATION:
        raise DomainError('explicit_offline_bootstrap_required',403)
    request=InitialAdministrator.model_validate(request.model_dump())
    with store.transaction() as db:
        if db.execute('SELECT 1 FROM organizations WHERE id=?',(request.institution_id,)).fetchone():raise DomainError('institution_already_exists',409)
        if db.execute('SELECT 1 FROM identities WHERE issuer=? AND subject=?',(request.issuer,request.subject)).fetchone():raise DomainError('identity_already_exists',409)
        user=secrets.token_hex(16)
        db.execute('INSERT INTO organizations(id,name,active) VALUES(?,?,1)',(request.institution_id,request.institution_name))
        db.execute('INSERT INTO identities(id,issuer,subject,active) VALUES(?,?,?,1)',(user,request.issuer,request.subject))
        db.execute("INSERT INTO memberships(user_id,institution_id,role,active,institution_admin) VALUES(?,?,'manager',1,1)",(user,request.institution_id))
        store.audit(db,'initial_admin_bootstrap',user,request.institution_id)
    return {'user_id':user,'institution_id':request.institution_id,'role':'manager','institution_admin':True}
