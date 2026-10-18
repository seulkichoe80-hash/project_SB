"""Fresh synthetic contract examples, generated through real offline Workflow APIs."""
import base64
import argparse
import json
from pathlib import Path
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'tests'))
from test_workflow_jobs import WorkflowJobTests
from test_workflow_discovery import synthetic_hwpx,synthetic_pdf
from apps.api.workflow_forms_models import FormMetadata


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():parser.error('new output required')
    test=WorkflowJobTests('test_normal_complete_atomic_components');test.setUp()
    try:
        test.source(['업무명: 연구 자료 대여','1. 신청자는 자료대여신청서를 제출한다.',
            '2. 담당자는 검토확인서를 작성한다.','3. 자료가 누락된 경우 담당자는 보완하여 1단계로 돌아가 자료를 제출한다.',
            '4. 담당자는 결과보고서를 제출한다.'])
        test.form(name='자료대여신청서',filename='자료대여신청서.hwpx')
        test.form(name='결과보고서',filename='결과보고서-A.hwpx',text='합성 서식 A')
        test.form(name='결과보고서',filename='결과보고서-B.hwpx',text='합성 서식 B')
        app=test.app;service=app.state.workflows
        job=service.enqueue(test.principal,test.snapshot.document_id,test.snapshot.version_id)
        assert service.execute(test.worker,service.claim(test.worker))=='completed'
        docs=app.state.service.list(test.principal,False)
        datasets=[]
        # Also generate an independent PDF scope for real page/bbox anchor examples.
        pdf,_,_=test.prepare(synthetic_pdf(['Workflow: Mineral request','1. Applicant submits the request.']), '광물-접수.pdf')
        app.state.service.activate(test.principal,pdf['document_id'],pdf['id'])
        service.enqueue(test.principal,pdf['document_id'],pdf['id']);assert service.execute(test.worker,service.claim(test.worker))=='completed'
        for doc,ver in [(test.snapshot.document_id,test.snapshot.version_id),(pdf['document_id'],pdf['id'])]:
            base=f'/documents/{doc}/versions/{ver}/workflow'
            current=service.current(test.principal,doc,ver)
            listing=test.client.get(base+'/candidates').json();candidate=listing['candidates'][0]['id']
            responses={suffix:test.client.get(base+suffix).json() for suffix in ['/candidates','/candidates/'+candidate,'/review-issues?candidate_id='+candidate,'/form-links?candidate_id='+candidate,'/candidates/'+candidate+'/evidence']}
            refs=responses['/candidates/'+candidate+'/evidence']['evidence_refs']
            resolved={r['chunk_id']:test.client.post(f'/documents/{doc}/versions/{ver}/chunks/'+r['chunk_id']+'/evidence/resolve',json=r).json() for r in refs}
            datasets.append({'document':app.state.service.get(test.principal,doc,ver),'responses':responses,'resolved':resolved,'job':current['job'],'original_pdf_base64':base64.b64encode(app.state.service.original(test.principal,doc,ver)[0]).decode() if doc==pdf['document_id'] else None})
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps({'source':'real local API; synthetic-only; no provider','documents':app.state.service.list(test.principal,False),'datasets':datasets},ensure_ascii=False,indent=2))
    finally:test.tearDown()


if __name__=='__main__':main()
