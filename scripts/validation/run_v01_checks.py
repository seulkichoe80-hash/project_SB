"""Repeat the v0.1 baseline checks; immutable output paths, no provider/deployment calls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--capture-dir', type=Path, required=True)
    args = parser.parse_args(); output = args.output_dir.resolve(); captures = args.capture_dir.resolve()
    if output.exists() or captures.exists(): parser.error('new output and capture directories required')
    output.mkdir(parents=True); captures.mkdir(parents=True)
    started = time.monotonic()
    env = {**os.environ, 'PHASE2E_CAPTURE_DIR': os.path.relpath(captures / 'workflow-regression', ROOT),
           'V01_CAPTURE_DIR': os.path.relpath(captures / 'actual-http', ROOT)}
    def run(name, command, result=None):
        begin = time.monotonic()
        with (output / (name + '.log')).open('w') as log:
            process = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        record = {'name': name, 'command': command, 'exit_code': process.returncode,
                  'seconds': round(time.monotonic() - begin, 3)}
        if result and result.exists():
            data = json.loads(result.read_text()); record['counts'] = data.get('counts')
        return record
    preparation = [run('typecheck', ['npm', '--prefix', 'apps/web', 'run', 'typecheck'])]
    if preparation[0]['exit_code'] == 0:
        preparation.append(run('build', ['npm', '--prefix', 'apps/web', 'run', 'build']))
    if any(r['exit_code'] for r in preparation):
        (output / 'summary.json').write_text(json.dumps({'preparation': preparation, 'status': 'FAIL'}, indent=2)); return 1
    fixture = output / 'browser-fixture.json'
    preparation.append(run('generate-synthetic-api-fixture', [sys.executable, '-B', 'scripts/validation/build_phase2e1_fixture.py', '--output', str(fixture)]))
    if preparation[-1]['exit_code']: return 1
    def backend():
        result = output / 'backend.json'
        return [run('backend', [sys.executable, '-B', 'scripts/validation/run_stage4b3a_checks.py', '--output', str(result)], result)]
    def ui():
        checks = []
        for name in ['check_stage2_ui', 'check_stage3_home', 'check_stage4a_ui', 'check_stage4b2_ui', 'check_phase2e1_ui', 'check_phase2e2a_ui']:
            target = output / name; target.mkdir(); result = target / 'results.json'
            command = ['node', 'scripts/validation/' + name + '.cjs', str(result)]
            if 'phase2e' in name: command.append(str(fixture))
            checks.append(run(name, command, result))
        return checks
    def http():
        target = output / 'e2e'; target.mkdir(); result = target / 'results.json'
        return [run('actual-http-e2e', ['node', 'scripts/validation/check_v01_e2e.cjs', str(result)], result)]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(fn) for fn in [backend, ui, http]]
        suites = [item for future in futures for item in future.result()]
    paths = [p for folder in ['apps/api', 'apps/web/src', 'tests', 'scripts/validation'] for p in (ROOT / folder).rglob('*')
             if p.is_file() and 'node_modules' not in p.parts and '__pycache__' not in p.parts]
    paths += list(ROOT.glob('requirements*.txt')) + [ROOT / 'apps/web/package.json', ROOT / 'apps/web/package-lock.json']
    summary = {'scope': 'v0.1 baseline; all suites freshly executed; explicit synthetic/local mock identity only',
               'preparation': preparation, 'suites': suites, 'seconds': round(time.monotonic() - started, 3),
               'status': 'PASS' if all(r['exit_code'] == 0 and r.get('counts', {}).get('FAIL', 0) == 0 for r in suites) else 'FAIL',
               'input_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
               'external_provider_calls': 0, 'not_run': ['real Supabase', 'actual LLM/embedding', 'public deployment', 'native PDF/Hancom visual validation', 'screen reader']}
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'input_sha256'}, ensure_ascii=False, indent=2))
    return 0 if summary['status'] == 'PASS' else 1


if __name__ == '__main__': raise SystemExit(main())
