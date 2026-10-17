"""Full regression runner. Writes a new evidence file; no external service calls."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import io
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))


class Result(unittest.TextTestResult):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.records = []
    def addSuccess(self,test):
        super().addSuccess(test)
        self.records.append({'test':test.id(),'status':'PASS'})
    def addFailure(self,test,error):
        super().addFailure(test,error)
        self.records.append({'test':test.id(),'status':'FAIL'})
    def addError(self,test,error):
        super().addError(test,error)
        self.records.append({'test':test.id(),'status':'FAIL'})
    def addSkip(self,test,reason):
        super().addSkip(test,reason)
        self.records.append({'test':test.id(),'status':'SKIP','reason':reason})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('choose a new output; existing evidence is immutable')
    (ROOT/'work/phase2a').mkdir(parents=True,exist_ok=True)
    (ROOT/'work/phase2b').mkdir(parents=True,exist_ok=True)
    log = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result = unittest.TextTestRunner(stream=log,verbosity=2,resultclass=Result).run(suite)
    paths = [p for folder in ('apps','tests','scripts/validation') for p in (ROOT/folder).rglob('*.py')]
    paths += list(ROOT.glob('requirements*.txt'))
    record = {'time_utc':datetime.now(timezone.utc).isoformat(),'command':' '.join(sys.argv),
        'platform':platform.platform(),'python':sys.version,
        'dependencies':{p:metadata.version(p) for p in ('fastapi','pydantic','uvicorn','pdfplumber','pdfminer.six','defusedxml')},
        'counts':{s:sum(t['status']==s for t in result.records) for s in ('PASS','FAIL','SKIP','BLOCKED')},
        'tests_run':result.testsRun,'tests':result.records,'log':log.getvalue(),
        'code_sha256':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        'scope':'synthetic/local; explicit mock principals; no LLM/embedding/cloud',
        'not_run':['Hancom visual order/page layout','real public document corpus','real auth/JWT',
                   'cloud deployment','actual LLM','embeddings','full representative goldset'],
        'external_api_calls':0}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    print(log.getvalue())
    print(json.dumps(record['counts']))
    raise SystemExit(0 if result.wasSuccessful() else 1)
