"""Manager-only draft workflow endpoints; no worker capability or approval routes."""
from fastapi import Depends
from .models import Principal
from .workflow_jobs_models import (WorkflowJobRequest,WorkflowJobStatus,WorkflowCandidateResponse,
                                   WorkflowIssueResponse,WorkflowFormResponse,WorkflowEvidenceResponse)


def install_workflow_routes(app,service,principal_dependency):
    base='/documents/{document_id}/versions/{version_id}/workflow'

    @app.post(base+'/jobs',status_code=202,response_model=WorkflowJobStatus)
    def enqueue(document_id:str,version_id:str,body:WorkflowJobRequest,principal:Principal=Depends(principal_dependency)):
        return service.enqueue(principal,document_id,version_id,body)

    @app.get(base+'/jobs/{job_id}',response_model=WorkflowJobStatus)
    def status(document_id:str,version_id:str,job_id:str,principal:Principal=Depends(principal_dependency)):
        return service.status(principal,document_id,version_id,job_id)

    @app.post(base+'/jobs/{job_id}/retry',status_code=202,response_model=WorkflowJobStatus)
    def retry(document_id:str,version_id:str,job_id:str,principal:Principal=Depends(principal_dependency)):
        return service.retry(principal,document_id,version_id,job_id)

    @app.post(base+'/jobs/{job_id}/cancel',response_model=WorkflowJobStatus)
    def cancel(document_id:str,version_id:str,job_id:str,principal:Principal=Depends(principal_dependency)):
        return service.cancel(principal,document_id,version_id,job_id)

    @app.get(base+'/candidates',response_model=WorkflowCandidateResponse)
    def candidates(document_id:str,version_id:str,principal:Principal=Depends(principal_dependency)):
        return service.candidates(principal,document_id,version_id)

    @app.get(base+'/candidates/{candidate_id}',response_model=WorkflowCandidateResponse)
    def detail(document_id:str,version_id:str,candidate_id:str,principal:Principal=Depends(principal_dependency)):
        return service.candidates(principal,document_id,version_id,candidate_id)

    @app.get(base+'/review-issues',response_model=WorkflowIssueResponse)
    def issues(document_id:str,version_id:str,candidate_id:str|None=None,principal:Principal=Depends(principal_dependency)):
        return service.candidates(principal,document_id,version_id,candidate_id,'issues')

    @app.get(base+'/form-links',response_model=WorkflowFormResponse)
    def forms(document_id:str,version_id:str,candidate_id:str|None=None,principal:Principal=Depends(principal_dependency)):
        return service.candidates(principal,document_id,version_id,candidate_id,'forms')

    @app.get(base+'/candidates/{candidate_id}/evidence',response_model=WorkflowEvidenceResponse)
    def evidence(document_id:str,version_id:str,candidate_id:str,principal:Principal=Depends(principal_dependency)):
        return service.candidates(principal,document_id,version_id,candidate_id,'evidence')
