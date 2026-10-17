"""Run full backend regression with a subprocess-inherited non-loopback socket guard."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]

GUARD = '''
import ipaddress, os, socket
from pathlib import Path
def allowed(host):
    if isinstance(host, bytes): host = host.decode('ascii')
    if host == 'localhost': return True
    try: return ipaddress.ip_address(host).is_loopback
    except ValueError: return False
def reject():
    with open(os.environ['SB_NETWORK_GUARD_LOG'], 'a') as f: f.write('blocked\\n')
    raise OSError('external_network_disabled_for_stage4b3a_tests')
connect, connect_ex, resolve = socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo
def guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not allowed(address[0]): reject()
    return connect(self, address)
def guarded_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not allowed(address[0]): reject()
    return connect_ex(self, address)
def guarded_resolve(host, *args, **kwargs):
    if host is not None and not allowed(host): reject()
    return resolve(host, *args, **kwargs)
socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = guarded_connect, guarded_connect_ex, guarded_resolve
os.environ['SB_NETWORK_GUARD_ACTIVE'] = '1'
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() or output.with_suffix('.network.json').exists():
        parser.error('new output path required')
    output.parent.mkdir(parents=True, exist_ok=True)
    for name in ['phase2a', 'phase2b', 'phase2c', 'stage4b2']:
        (ROOT / 'work' / name).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='sb-offline-guard-') as directory:
        guard = Path(directory)
        (guard / 'sitecustomize.py').write_text(GUARD)
        blocked = guard / 'blocked.log'
        env = os.environ.copy()
        env['PYTHONPATH'] = str(guard) + os.pathsep + env.get('PYTHONPATH', '')
        env['SB_NETWORK_GUARD_LOG'] = str(blocked)
        # Check enforcement without contacting any destination, in a separate log.
        probe_env = {**env, 'SB_NETWORK_GUARD_LOG': str(guard / 'probe.log')}
        probe = subprocess.run([sys.executable, '-c',
            "import socket,os; assert os.environ['SB_NETWORK_GUARD_ACTIVE']=='1'; "
            "socket.getaddrinfo('forbidden.invalid',443)"], env=probe_env, capture_output=True, text=True)
        if probe.returncode == 0 or not (guard / 'probe.log').exists():
            raise RuntimeError('network_guard_not_enforced')
        started = time.monotonic()
        run = subprocess.run([sys.executable, 'scripts/validation/run_phase2b_checks.py', '--output', str(output)],
                             cwd=ROOT, env=env)
        attempts = len(blocked.read_text().splitlines()) if blocked.exists() else 0
        report = {'backend_exit': run.returncode, 'seconds': round(time.monotonic() - started, 3),
                  'socket_guard_probe': 'PASS', 'blocked_external_attempts': attempts,
                  'actual_external_provider_calls': 0, 'guard_scope': 'Python tests and inherited Python subprocesses; loopback only'}
        output.with_suffix('.network.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report))
        return run.returncode or int(attempts != 0)


if __name__ == '__main__':
    raise SystemExit(main())
