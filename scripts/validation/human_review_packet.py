"""Offline synthetic-only priority review packet. Never approves gold or edits inputs."""
import argparse
import csv
import html
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts.validation.evaluation_fixtures import sha_file, verify_frozen, services, LiveEvidenceResolver
from scripts.validation.run_v03c1_diagnostics import PRIORITY
from scripts.validation.evaluation_metrics import HumanReview

FIELDS = ['query_id', 'reviewer', 'reviewed_at', 'verdict', 'reason']


def load(path):
    return json.loads(Path(path).read_text())


def build(generation_dir, output_dir):
    source, out = Path(generation_dir).resolve(), Path(output_dir)
    if out.exists():
        raise ValueError('new_output_path_required')
    g = load(source / 'generation.json')
    verify_frozen(g, source)
    resolve = LiveEvidenceResolver(services(g['data_dir']), g)
    questions = {q['id']: q for q in g['queries']}
    rows = []
    for order, (qid, reason) in enumerate(PRIORITY, 1):
        q = questions[qid]
        evidence = []
        for ref in q['expected_evidence_refs']:
            result = resolve(q['organization_id'], ref)
            if not result['structural_valid']:
                raise ValueError('unresolved_review_evidence')
            evidence.append({'reference': ref, 'quotes': [s['quote'] for s in ref['spans']]})
        # Only the question tenant's full context; never dereference forbidden refs for display.
        docs = [d for d in g['documents'] if d['organization_id'] == q['organization_id']]
        context = [{'document_id': d['document_id'], 'version_id': d['version_id'],
                    'title': d.get('source', {}).get('title', d['logical_id']), 'sha256': d['sha256'],
                    'blocks': [{'text': b['text'], 'location': b['source_anchor']['selector']}
                               for b in d['snapshot']['source_blocks']]} for d in docs]
        rows.append({'order': order, 'query_id': qid, 'organization_id': q['organization_id'],
                     'selection_reason': reason, 'question': q['question'],
                     'proposed_answer': q['expected_answer'], 'evidence': evidence,
                     'context': context, 'reviewer': None, 'reviewed_at': None,
                     'verdict': None, 'reason': None})
    packet = {'schema_version': 'priority-review-v1', 'generation_id': g['generation_id'],
              'generation_sha256': sha_file(source / 'generation.json'),
              'goldset_status': 'PROVISIONAL', 'semantic_verification': 'NOT_VERIFIED',
              'human_identity_verified': False, 'actual_provider_calls': 0, 'rows': rows}
    out.mkdir(parents=True)
    (out / 'packet.json').write_text(json.dumps(packet, ensure_ascii=False, indent=2) + '\n')
    with (out / 'judgments.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows({'query_id': row['query_id']} for row in rows)
    esc = lambda value: html.escape(str(value), quote=True)
    body = []
    for row in rows:
        refs = ''.join('<li>' + esc(' / '.join(e['quotes'])) + '</li>' for e in row['evidence'])
        contexts = ''.join('<details><summary>' + esc(d['title']) + '</summary><p>버전 ' + esc(d['version_id']) + '</p>' + ''.join('<p><small>' + esc(b['location']) + '</small><br>' + esc(b['text']) + '</p>' for b in d['blocks']) + '</details>' for d in row['context'])
        body.append('<article id="' + esc(row['query_id']) + '"><h2>' + esc(str(row['order']) + '. ' + row['query_id']) + '</h2><p>기관 ' + esc(row['organization_id']) + ' · ' + esc(row['selection_reason']) + '</p><h3>질문</h3><p>' + esc(row['question']) + '</p><h3>검토 대상 정답 초안</h3><p>' + esc(row['proposed_answer']) + '</p><h3>구조 확인된 근거 · 내용 검토 필요</h3><ul>' + refs + '</ul>' + ('' if refs else '<p>연결된 정답 근거 없음. 아래 기관 내 전체 문맥에서 근거 부족·응답 보류를 검토하세요.</p>') + contexts + '</article>')
    page = '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><title>우선 10문항 독립 검토</title><style>body{font:18px/1.7 sans-serif;max-width:960px;margin:auto;padding:16px;color:#17212b}article{border-top:2px solid #526475;margin:32px 0;overflow-wrap:anywhere}summary{cursor:pointer;padding:12px}a:focus,summary:focus{outline:3px solid #005fcc}small{color:#465362}</style><h1>우선 10문항 독립 검토</h1><p>공개 합성 평가자료 · 공식 행정 규정 아님 · 정답 미승인 · 실제 AI 평가 아님</p><p>판정: 정확 / 부분정확 / 오답 / 판정불가. 단계·순서·조건·기한·서식과 원문을 각각 대조하세요. HWPX XML 위치는 시각적 페이지를 보증하지 않습니다.</p><p>judgments.csv에 검토자 식별명(실명 불필요), 시간대 포함 검토일, 판정, 이유를 직접 기록하세요. 브라우저 입력·자동 저장·외부 전송은 없습니다. 수정 제안은 이유에 적으며 기존 정답을 덮어쓰지 않습니다.</p><nav>' + ' '.join('<a href="#' + esc(r['query_id']) + '">' + str(r['order']) + '</a>' for r in rows) + '</nav>' + ''.join(body) + '</html>'
    (out / 'review.html').write_text(page)
    return packet


def check(packet_path, csv_path):
    packet = load(packet_path)
    expected = {r['query_id'] for r in packet['rows']}
    with Path(csv_path).open(newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDS:
            raise ValueError('review_columns_mismatch')
        rows = list(reader)
    ids = [r['query_id'] for r in rows]
    if len(ids) != len(expected) or len(set(ids)) != len(ids) or set(ids) != expected:
        raise ValueError('review_question_coverage_mismatch')
    completed, pending = [], []
    for row in rows:
        if not any(row[k] for k in FIELDS[1:]):
            pending.append(row['query_id'])
        else:
            completed.append(HumanReview.model_validate(row).model_dump(mode='json'))
    return {'completed': len(completed), 'total': len(rows), 'pending_ids': pending,
            'submitted_reviews': completed, 'human_identity_verified': False,
            'goldset_status': 'PROVISIONAL', 'semantic_verification': 'NOT_VERIFIED',
            'semantic_accuracy_pass': False}


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest='command', required=True)
    b = sub.add_parser('build'); b.add_argument('--generation-dir', required=True); b.add_argument('--output-dir', required=True)
    c = sub.add_parser('check'); c.add_argument('--packet', required=True); c.add_argument('--judgments', required=True)
    a = p.parse_args()
    if a.command == 'build':
        result = build(a.generation_dir, a.output_dir)
        print(json.dumps({'questions': len(result['rows']), 'status': 'PROVISIONAL'}))
    else:
        print(json.dumps(check(a.packet, a.judgments), ensure_ascii=False, indent=2))
