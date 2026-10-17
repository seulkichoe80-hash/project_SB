from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from starlette.concurrency import run_in_threadpool
from .errors import DomainError
from .formats import MAX_BYTES
from .models import Principal, Transition
from .repository import Repository
from .service import DocumentService
from .storage import LocalOriginalStore


def authenticated_principal() -> Principal:
    # Fail closed. Real JWT validation/membership is deliberately not implemented in Phase 2A.
    # Tests explicitly override this dependency with server-created Principal objects.
    raise HTTPException(401, 'authentication_not_configured')


def create_app(data_dir: Path | None = None, store=None, repository=None, parsing_enabled=False) -> FastAPI:
    root = data_dir or Path('work/phase2a/runtime')
    service = DocumentService(repository or Repository(root / 'metadata.sqlite3'), store or LocalOriginalStore(root / 'originals'), parsing_enabled)
    app = FastAPI(title='서무ITDA local Phase 2B' if parsing_enabled else '서무ITDA local Phase 2A',
                  docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = service
    if parsing_enabled:
        import time
        from .parsing_service import ParsingService, EvidenceRequest
        parsing = ParsingService(service)
        app.state.parsing = parsing
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
        return {'status': 'local_only', 'authentication': 'deny_all', 'public_deployment_ready': False,
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
