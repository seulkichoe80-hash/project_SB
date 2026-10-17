"""Restore only whitelisted, hash-pinned synthetic fixtures; never overwrite files."""
import argparse
import base64
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAMES = ('procedure-v2.hwpx', 'procedure-recovery-invalid.hwpx')


def restore(destination=None, write=False):
    destination = destination or ROOT/'tests/fixtures/synthetic'
    bundle = json.loads((ROOT/'tests/fixtures/synthetic/hwpx-recovery.json').read_text(encoding='utf-8'))
    expected_normal = json.loads((ROOT/'tests/fixtures/synthetic/hwpx-manifest-v2.json').read_text(encoding='utf-8'))['sha256']
    if bundle[NAMES[0]]['sha256'] != expected_normal:
        raise ValueError('normal fixture must match the historical manifest')
    result = []
    # Validate every payload before writing any file.
    decoded = {}
    for name in NAMES:
        data = base64.b64decode(bundle[name]['base64'], validate=True)
        digest = hashlib.sha256(data).hexdigest()
        if digest != bundle[name]['sha256']:
            raise ValueError('fixture payload hash mismatch')
        path = destination/name
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('existing fixture differs; refusing overwrite')
        decoded[name] = (data,digest)
    for name,(data,digest) in decoded.items():
        path = destination/name
        state = 'present' if path.exists() else 'missing'
        if write and state == 'missing':
            destination.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream:
                stream.write(data)
            state = 'restored'
        result.append({'file':name,'sha256':digest,'status':state})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--restore-missing',action='store_true')
    args = parser.parse_args()
    print(json.dumps(restore(write=args.restore_missing),ensure_ascii=False,indent=2))
