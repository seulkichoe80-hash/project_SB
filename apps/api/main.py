from pathlib import Path
from typing import Literal
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from .errors import DomainError
from .formats import MAX_BYTES
from .models import Principal, Transition
from .repository import Repository
from .service import DocumentService
from .storage import LocalOriginalStore


def authenticated_principal(request: Request) -> Principal:
    return request.app.state.auth.resolve(request)


def create_app(data_dir: Path | None = None, store=None, repository=None, parsing_enabled=False, identity_provider=None, auth_settings=None, auth_clock=None, supabase_settings=None, search_settings=None) -> FastAPI:
    from .runtime_settings import ensure_start_environment
    ensure_start_environment('api')
    if supabase_settings is not None:
        if identity_provider is not None:
            raise ValueError('choose_one_identity_configuration')
        from .identity_provider import SupabaseProviderAdapter
        from .supabase_transport import SupabaseHTTPTransport
        identity_provider = SupabaseProviderAdapter(SupabaseHTTPTransport(supabase_settings), supabase_settings.issuer)
    root = data_dir or Path('work/phase2a/runtime')
    service = DocumentService(repository or Repository(root / 'metadata.sqlite3'), store or LocalOriginalStore(root / 'originals'), parsing_enabled)
    app = FastAPI(title='서무ITDA local Phase 2B' if parsing_enabled else '서무ITDA local Phase 2A',
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    from .auth import AuthService, Login, MembershipUpdate
    from .auth_store import AuthStore
    import time as auth_time
    auth = AuthService((service.repo.auth_store() if getattr(service.repo, 'dialect', None) == 'postgresql' else AuthStore(service.repo.path)), identity_provider, auth_settings, auth_clock or auth_time.time)
    app.state.auth = auth

    @app.middleware('http')
    async def private_response(request: Request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Vary'] = 'Cookie'
        return response
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_request, _error):
        # Validation inputs may contain credentials: never echo them.
        return JSONResponse({'error': 'invalid_request'}, status_code=422)


    @app.get('/auth/status')
    def auth_status(response: Response):
        response.headers['Cache-Control'] = 'no-store'
        return {'provider_available': auth.provider.available, 'remote_enabled': getattr(auth.provider, 'remote_enabled', False)}

    @app.post('/auth/csrf')
    def csrf(request: Request, response: Response):
        return auth.challenge(request, response)

    @app.post('/auth/login')
    def login(body: Login, request: Request, response: Response):
        return auth.login(request, response, body)

    @app.get('/auth/me')
    def current_user(request: Request, response: Response):
        return auth.me(request, response)

    @app.post('/auth/logout')
    def logout(request: Request, response: Response):
        return auth.logout(request, response)

    @app.get('/auth/memberships')
    def memberships(request: Request):
        return auth.members(request)

    @app.patch('/auth/memberships/{user_id}')
    def update_membership(user_id: str, body: MembershipUpdate, request: Request):
        return auth.update_member(request, user_id, body)

    if parsing_enabled:
        import time
        from .parsing_service import ParsingService, EvidenceRequest
        parsing = ParsingService(service)
        app.state.parsing = parsing
        from .chunk_service import ChunkService
        from .chunking import ChunkConfig, EvidenceRef
        from .search_settings import SearchSettings
        search_settings=SearchSettings.from_environment() if search_settings is None else SearchSettings.model_validate(search_settings.model_dump(warnings=False))
        chunks = ChunkService(parsing,search_settings=search_settings)
        app.state.chunks = chunks
        from .workflow_jobs import WorkflowJobService
        from .workflow_routes import install_workflow_routes
        workflows = WorkflowJobService(chunks)
        app.state.workflows = workflows
        install_workflow_routes(app, workflows, authenticated_principal)

        @app.post('/documents/{document_id}/versions/{version_id}/chunk-jobs',status_code=202)
        def enqueue_chunks(document_id: str,version_id: str,body: ChunkConfig,principal: Principal=Depends(authenticated_principal)):
            return chunks.enqueue(principal,document_id,version_id,body)

        @app.get('/documents/{document_id}/versions/{version_id}/chunk-jobs/{job_id}')
        def chunk_status(document_id: str,version_id: str,job_id: str,principal: Principal=Depends(authenticated_principal)):
            return chunks.status(principal,document_id,version_id,job_id)

        @app.post('/documents/{document_id}/versions/{version_id}/chunk-jobs/{job_id}/retry',status_code=202)
        def retry_chunks(document_id: str,version_id: str,job_id: str,principal: Principal=Depends(authenticated_principal)):
            return chunks.retry(principal,document_id,version_id,job_id)

        @app.get('/documents/{document_id}/versions/{version_id}/chunks')
        def list_chunks(document_id: str,version_id: str,principal: Principal=Depends(authenticated_principal)):
            return chunks.list(principal,document_id,version_id)

        @app.post('/documents/{document_id}/versions/{version_id}/chunks/{chunk_id}/evidence/resolve')
        def chunk_evidence(document_id: str,version_id: str,chunk_id: str,body: EvidenceRef,principal: Principal=Depends(authenticated_principal)):
            return chunks.resolve(principal,document_id,version_id,chunk_id,body)

        @app.get('/search')
        def search(q: str,limit: int=20,strategy: Literal['literal','scored_or']='literal',principal: Principal=Depends(authenticated_principal)):
            method='sqlite_scored_or_v1' if strategy=='scored_or' else 'sqlite_keyword_substring_v1'
            return {'method':method,'results':chunks.search(principal,q,limit,strategy)}
        with service.repo.transaction() as db:
            db.parsing.backfill(time.time())

        @app.post('/documents/{document_id}/versions/{version_id}/parsing', status_code=202)
        def enqueue_parsing(document_id: str, version_id: str, principal: Principal = Depends(authenticated_principal)):
            return parsing.enqueue(principal, document_id, version_id)

        @app.post('/documents/{document_id}/versions/{version_id}/parsing/retry', status_code=202)
        def retry_parsing(document_id: str, version_id: str, principal: Principal = Depends(authenticated_principal)):
            return parsing.enqueue(principal, document_id, version_id, retry=True)

        @app.get('/documents/{document_id}/versions/{version_id}/parsing')
        def parsing_status(document_id: str, version_id: str, principal: Principal = Depends(authenticated_principal)):
            return parsing.status(principal, document_id, version_id)

        @app.get('/documents/{document_id}/versions/{version_id}/blocks')
        def source_blocks(document_id: str, version_id: str, principal: Principal = Depends(authenticated_principal)):
            return parsing.blocks(principal, document_id, version_id)

        @app.post('/documents/{document_id}/versions/{version_id}/evidence/resolve')
        def resolve_evidence(document_id: str, version_id: str, body: EvidenceRequest,
                             principal: Principal = Depends(authenticated_principal)):
            return parsing.resolve(principal, document_id, version_id, body)

    @app.exception_handler(DomainError)
    async def domain_error(_request, error):
        return JSONResponse({'error': error.code}, status_code=error.status)

    @app.exception_handler(Exception)
    async def internal_error(_request, _error):
        return JSONResponse({'error': 'storage_or_database_failure'}, status_code=503)

    @app.get('/health')
    def health():
        return {'status': 'local_only', 'authentication': 'server_membership_sessions' if auth.provider.available else 'deny_all', 'public_deployment_ready': False,
                'persistent_parsing': parsing_enabled}

    async def upload(request, principal, filename, document_id=None):
        service.role(principal, 'manager')
        if request.headers.get('x-data-classification') not in ('synthetic', 'public'):
            raise DomainError('public_or_synthetic_ack_required', 400)
        # A declaration is not sensitive-data detection. Real administrative material remains prohibited.
        chunks, size = [], 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > MAX_BYTES:
                raise DomainError('file_size_limit', 413)
            chunks.append(chunk)
        meta, duplicate = await run_in_threadpool(service.register, principal, filename,
            request.headers.get('content-type', ''), b''.join(chunks), document_id)
        return JSONResponse({'document': meta, 'duplicate': duplicate}, status_code=200 if duplicate else 201)

    @app.post('/documents')
    async def register(request: Request, filename: str, principal: Principal = Depends(authenticated_principal)):
        return await upload(request, principal, filename)

    @app.post('/documents/{document_id}/versions')
    async def new_version(document_id: str, request: Request, filename: str,
                          principal: Principal = Depends(authenticated_principal)):
        return await upload(request, principal, filename, document_id)

    @app.get('/documents')
    def listing(active_only: bool = True, principal: Principal = Depends(authenticated_principal)):
        return service.list(principal, active_only)

    @app.get('/documents/{document_id}/versions/{version_id}')
    def metadata(document_id: str, version_id: str, principal: Principal = Depends(authenticated_principal)):
        return service.get(principal, document_id, version_id)

    @app.get('/documents/{document_id}/versions/{version_id}/original')
    def original(document_id: str, version_id: str, principal: Principal = Depends(authenticated_principal)):
        data, meta = service.original(principal, document_id, version_id)
        return Response(data, media_type=meta['mime'], headers={'Content-Disposition': 'attachment',
                        'X-Content-Type-Options': 'nosniff', 'Cache-Control': 'no-store'})

    @app.post('/documents/{document_id}/versions/{version_id}/transitions')
    def transition(document_id: str, version_id: str, body: Transition,
                   principal: Principal = Depends(authenticated_principal)):
        return service.transition(principal, document_id, version_id, **body.model_dump())

    @app.post('/documents/{document_id}/versions/{version_id}/activate')
    def activate(document_id: str, version_id: str, principal: Principal = Depends(authenticated_principal)):
        return service.activate(principal, document_id, version_id)

    @app.delete('/documents/{document_id}')
    def deregister(document_id: str, principal: Principal = Depends(authenticated_principal)):
        return service.deregister(principal, document_id)

    return app


# Production module entry always enables persistent parsing. Factory default retains
# Phase 2A-only embedders/tests; real authentication is deny-all in BOTH modes.
app = create_app(parsing_enabled=True)
