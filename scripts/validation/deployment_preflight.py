"""Offline only; safe structured diagnostics, no raw validation errors or secret values."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from apps.api.runtime_settings import preflight, ENV_FIELDS


def read_config(path):
    p = Path(path)
    if p.is_symlink() or p.stat().st_size > 65536:
        raise ValueError('invalid_config_file')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError('duplicate_config_key')
            result[key] = value
        return result
    value = json.loads(p.read_text(), object_pairs_hook=unique)
    if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
        raise ValueError('invalid_config_file')
    if set(value) - set(ENV_FIELDS):
        raise ValueError('unknown_config_key')
    return value


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        print(json.dumps({'status': 'INVALID', 'startup_allowed': False, 'production_ready': False,
                          'connectivity': 'NOT_CHECKED', 'issues': ['invalid_command_arguments']}))
        raise SystemExit(1)


def main():
    p = SafeParser(description='Offline deployment contract check; never verifies cloud connectivity.')
    p.add_argument('--config-json', help='Environment-name/string mapping; omit to inspect current allowed environment keys')
    p.add_argument('--peer-config-json', help='Worker mapping; primary mapping must be API')
    p.add_argument('--role', choices=('api', 'parse_worker', 'chunk_worker', 'workflow_worker'))
    a = p.parse_args()
    try:
        result = preflight(read_config(a.config_json) if a.config_json else None,
                           expected_role=a.role, peer=read_config(a.peer_config_json) if a.peer_config_json else None)
    except (OSError, ValueError, RecursionError):
        result = {'settings_status': 'INVALID', 'status': 'INVALID', 'startup_allowed': False,
                  'production_ready': False, 'connectivity': 'NOT_CHECKED', 'issues': ['invalid_config_file']}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['startup_allowed'] else (2 if result['status'] == 'BLOCKED' else 1)


if __name__ == '__main__':
    raise SystemExit(main())
