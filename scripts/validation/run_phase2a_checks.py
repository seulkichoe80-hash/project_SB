"""Offline + local HTTP suite with immutable, machine-readable run evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Evidence already exists; choose a new output path')
    (ROOT / 'work/phase2a').mkdir(parents=True, exist_ok=True)
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(unittest.defaultTestLoader.discover(str(ROOT / 'tests')))
    hashes = {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
              for folder in ('apps', 'tests', 'scripts/validation') for path in (ROOT / folder).rglob('*.py')}
    record = {'time_utc': datetime.now(timezone.utc).isoformat(), 'python': sys.version,
        'platform': platform.platform(), 'command': ' '.join(sys.argv),
        'dependencies': {p: importlib.metadata.version(p) for p in ('fastapi', 'pydantic', 'uvicorn', 'httpx', 'starlette', 'defusedxml')},
        'counts': {'PASS': result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
                   'FAIL': len(result.failures)+len(result.errors), 'SKIP': len(result.skipped), 'BLOCKED': 0},
        'tests_run': result.testsRun, 'log': log.getvalue(), 'code_sha256': hashes,
        'external_api_calls': 0, 'public_deployment': 'NOT_RUN', 'real_auth': 'NOT_RUN'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(log.getvalue())
    print(json.dumps(record['counts']))
    sys.exit(0 if result.wasSuccessful() else 1)
