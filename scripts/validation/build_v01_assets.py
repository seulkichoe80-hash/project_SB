"""Create reviewed project-authored synthetic v0.1 demo inputs; never overwrite."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
from test_workflow_discovery import synthetic_hwpx, synthetic_pdf


def build(target):
    target = Path(target)
    if target.exists():
        raise ValueError('new_asset_directory_required')
    target.mkdir(parents=True)
    assets = {
        'v01-manual.hwpx': synthetic_hwpx([
            '업무명: 연구 자료 대여',
            '1. 신청자는 자료대여신청서를 제출한다.',
            '2. 담당자는 검토확인서를 작성한다.',
            '3. 자료가 누락된 경우 담당자는 보완하여 1단계로 돌아가 자료를 제출한다.',
            '4. 담당자는 결과보고서를 제출한다.',
        ]),
        'v01-manual.pdf': synthetic_pdf([
            'Workflow: Mineral loan',
            '1. Applicant submits the request form.',
            '2. Officer reviews the request.',
            '3. If incomplete, officer returns to step 1 and requests correction.',
        ]),
        'v01-manual-v2.pdf': synthetic_pdf(['Workflow: Mineral loan revised', '1. Applicant submits the revised request form.', '2. Officer reviews the request.']),
        'v01-request-form.hwpx': synthetic_hwpx(['합성 자료대여신청서', '입력란: 합성 자료']),
        'v01-report-a.hwpx': synthetic_hwpx(['합성 결과보고서 A', '입력란: 합성 자료']),
        'v01-report-b.hwpx': synthetic_hwpx(['합성 결과보고서 B', '입력란: 합성 자료']),
    }
    manifest = {'classification': 'synthetic', 'author': 'project-authored validation fixture',
                'privacy': 'no real people, institutions, credentials or records',
                'pdf_license_review': 'project-authored ASCII PDF; base Type1 Helvetica reference only; no embedded/distributed font',
                'files': {}}
    for name, data in assets.items():
        (target / name).write_bytes(data)
        manifest['files'][name] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    (target / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(); print(json.dumps(build(args.output_dir), ensure_ascii=False))
