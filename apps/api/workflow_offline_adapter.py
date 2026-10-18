"""Deterministic lexical mock. No business-name registry, SDK, network or semantic model."""
import re
from .chunking import digest
from .workflow_contracts import (EvidenceCitation, GroundedAssertion, ReviewIssue,
                                 WorkflowExtraction, parse_extraction)
from .workflow_discovery_models import (ChunkOmission, OfflineExtractionReceipt, StepRoleCandidate)

# Syntax/lexical markers only: task labels always come from the supplied document.
TITLE = re.compile(r'^(?:업무(?:명)?|절차명|Workflow|Procedure)\s*[:：]\s*(\S.*)$', re.I)
NUMBER = re.compile(r'^\s*(\d{1,3})[.)]\s+')
ACTION = re.compile(r'(?:작성|제출|검토|확인|승인|반려|보완|첨부|기록|보관|통지|접수|요청|처리|전달|신청|보고|반환|재제출|완료|등록|점검|실시|지급|수정|예약|준비)'
                    r'(?:한다|합니다|하여야|해야|할 것|하십시오|하세요)(?:[.!?]|$)|'
                    r'\b(?:prepare|submit|attach|review|check|approve|reject|return|resubmit|record|send|complete|keep)(?:s|es)?\b', re.I)
CONDITION = re.compile(r'경우|때에는|이라면|이면|한다면|필요\s*시|발생\s*시|\b(?:if|unless|otherwise|when)\b', re.I)
BRANCH = re.compile(r'보완|반려|반복|되돌|돌아|다시|\b(?:reject|return|repeat|resubmit|otherwise)\b', re.I)
TARGET = re.compile(r'(\d{1,3})\s*단계(?:로|부터)|\b(?:to|from)\s+step\s+(\d{1,3})\b', re.I)
DEADLINE = re.compile(r'\d+\s*(?:영업일|일|개월|월|년|시간|분)\s*(?:이내|전|후|까지)|'
                      r'\bwithin\s+\d+\s+(?:business\s+)?(?:days?|hours?|minutes?)\b', re.I)
OBLIGATION = re.compile(r'반드시|하여야|해야|\b(?:must|shall)\b', re.I)
FORM = re.compile(r'[가-힣A-Za-z0-9_-]{0,40}(?:신청서|보고서|확인서|동의서|서식)|'
                  r'\b[A-Za-z0-9_-]+\s+(?:form|template)\b', re.I)
# A grammatical subject alone (e.g. "자료가") is not a responsible-role mention.
# These generic role/organization suffixes are lexical hints, not an authority registry.
ROLE_KO = re.compile(r'^(.{0,36}?(?:자|장|원|관|사|팀|부서|기관|위원회|센터|실|담당))(?:은|는|이|가)\s+')
ROLE_EN = re.compile(r'^(.{1,60}?)\s+(?:(?:must|shall)\s+)?'
                     r'(?:prepare|submit|attach|review|check|approve|reject|return|resubmit|record|send|complete)(?:s|es)?\b', re.I)


class DeterministicWorkflowAdapter:
    model_id = 'offline-lexical-workflow-v1'
    test_only = True
    network_access = False
    rule_version = 'explicit-markers-v1'

    @staticmethod
    def _id(kind, *parts):
        return kind + '_' + digest(parts)[:32]

    def extract(self, snapshot):
        # Preserve the Phase 2D-1 WorkflowExtractionAdapter return contract.
        return self.extract_with_coverage(snapshot, snapshot.input_chunk_ids).extraction

    def extract_with_coverage(self, snapshot, chunk_ids):
        allowed = set(chunk_ids)
        if len(allowed) != len(chunk_ids) or not allowed <= set(snapshot.input_chunk_ids):
            raise ValueError('invalid_offline_input_scope')
        spans = {}
        for chunk in snapshot.chunks:
            if chunk.chunk_id not in allowed:
                continue
            for span in chunk.evidence.spans:
                if span.role == 'primary' and span.source_kind == 'original_text' and span.quote:
                    spans.setdefault(span.block_id, []).append((span.start, span.end, chunk.chunk_id))

        # Analyze a source block only when ALL its text is present in the supplied
        # primary spans. Context copies and child cell paragraphs are not duplicated.
        complete, partial = set(), set()
        for block in snapshot.source_blocks:
            ranges = sorted(spans.get(block.block_id, []))
            if not ranges:
                continue
            cursor = 0
            for start, end, _ in ranges:
                if start != cursor:
                    break
                cursor = end
            if cursor == len(block.text):
                complete.add(block.block_id)
            else:
                partial.add(block.block_id)

        def pieces(block, start, end):
            result = []
            for left, right, chunk_id in sorted(spans.get(block.block_id, [])):
                a, b = max(left, start), min(right, end)
                if a < b and block.text[a:b].strip():
                    quote = block.text[a:b]
                    result.append(GroundedAssertion(text=quote, evidence=[EvidenceCitation(
                        chunk_id=chunk_id, block_id=block.block_id, start=a, end=b, quote=quote)]))
            return result

        issues, roles, workflows = [], [], []
        pending_title, group = None, None

        def issue(code, message, targets=(), key=()):
            issues.append(ReviewIssue(id=self._id('issue', code, targets, key), target_ids=list(targets),
                                      code=code, message=message))

        def finish():
            nonlocal group
            if group is None:
                return
            numbered = {}
            relations = group.pop('_relations')
            for step, number, hazard, targets, claims in relations:
                if number is not None:
                    numbered.setdefault(number, []).append(step)
            previous = None
            for step, number, hazard, targets, claims in relations:
                if (previous and number is not None and previous[1] is not None
                        and number == previous[1] + 1 and not hazard and not previous[2]
                        and len(numbered[number]) == len(numbered[previous[1]]) == 1):
                    group['edges'].append({'id': self._id('edge', previous[0]['id'], step['id']),
                        'source': previous[0]['id'], 'target': step['id'], 'relation': 'precedes',
                        'condition_ids': [], 'explanation': claims[0]})
                if hazard:
                    condition = next((c for c in group['conditions'] if step['id'] in c['step_ids']), None)
                    for target, explanation in targets:
                        destination = numbered.get(target, [])
                        if condition and len(destination) == 1 and destination[0]['id'] != step['id']:
                            target_id = destination[0]['id']
                            if target_id not in condition['step_ids']:
                                condition['step_ids'].append(target_id)
                            group['edges'].append({'id': self._id('branch', step['id'], target_id),
                                'source': step['id'], 'target': target_id, 'relation': 'conditional',
                                'condition_ids': [condition['id']], 'explanation': explanation})
                elif previous and (number is None or previous[1] is None or number != previous[1] + 1
                                   or len(numbered.get(number, [])) != 1):
                    issue('unclear_order', '단계 번호의 누락·중복 또는 명시 순서 부재로 선후 관계를 추가하지 않았습니다.',
                          (step['id'],), ('numbering', step['id']))
                previous = (step, number, hazard)
            issue('semantic_review_required', '결정적 원문 후보이며 업무 의미·효력·필요 관계를 확인하지 않았습니다.',
                  (group['id'],))
            workflows.append(group)
            group = None

        for block in snapshot.source_blocks:
            if block.block_id not in complete:
                continue
            offset = 0
            for line in block.text.splitlines(keepends=True):
                trimmed = line.strip()
                begin = offset + len(line) - len(line.lstrip())
                end = begin + len(trimmed)
                offset += len(line)
                if not trimmed:
                    continue
                title = TITLE.match(trimmed)
                if title or (block.block_type == 'heading' and not ACTION.search(trimmed)):
                    finish()
                    start = begin + (title.start(1) if title else 0)
                    title_claims = pieces(block, start, end)
                    pending_title = (title_claims[0], block.block_id, start) if title_claims else None
                    continue
                if not ACTION.search(trimmed):
                    continue
                claims = pieces(block, begin, end)
                if not claims:
                    continue
                if group is None:
                    if pending_title:
                        label, title_block, title_start = pending_title
                        group_id = self._id('workflow', snapshot.snapshot_id, title_block, title_start)
                    else:
                        label = claims[0]
                        group_id = self._id('workflow', snapshot.snapshot_id, block.block_id, begin)
                        issue('semantic_review_required', '명시 제목이 없어 첫 행위 원문을 업무명 후보로 사용했습니다.',
                              (group_id,), (block.block_id, begin))
                    group = {'id': group_id, 'title': label, 'steps': [], 'conditions': [], 'edges': [],
                             'form_requirements': [], '_relations': []}
                step_id = self._id('step', group['id'], block.block_id, begin, end)
                marker = NUMBER.match(trimmed)
                number = int(marker.group(1)) if marker else None
                hazard = bool(CONDITION.search(trimmed) or BRANCH.search(trimmed))
                targets = []
                for match in TARGET.finditer(trimmed):
                    target = int(match.group(1) or match.group(2))
                    explanation = next((c for c in claims if match.group() in c.text), None)
                    if explanation and target not in [n for n, _ in targets]:
                        targets.append((target, explanation))
                deadlines = DEADLINE.search(trimmed)
                deadline_parts = pieces(block, begin + deadlines.start(), begin + deadlines.end()) if deadlines else []
                step = {'id': step_id, 'label': claims[0], 'actions': claims,
                        'deadline': deadline_parts[0] if len(deadline_parts) == 1 else None,
                        'obligations': claims if OBLIGATION.search(trimmed) and len(claims) == 1 else []}
                group['steps'].append(step)
                relationship = (step, number, hazard, targets, claims)
                group['_relations'].append(relationship)
                if hazard:
                    group['conditions'].append({'id': self._id('condition', step_id),
                        'statement': next((c for c in claims if CONDITION.search(c.text) or BRANCH.search(c.text)), claims[0]),
                        'step_ids': [step_id]})
                    issue('unclear_order', '조건·보완·반려·반복 원문을 보존했습니다. 명시 목적지 외의 분기는 미확정입니다.',
                          (step_id,), (block.block_id, begin))
                elif number is None:
                    issue('unclear_order', '번호나 명시적 연결이 없어 이 단계의 선후 간선을 만들지 않았습니다.',
                          (step_id,), (block.block_id, begin))
                if len(claims) > 1:
                    issue('semantic_review_required', '청크 경계로 행위 문구를 원문 조각으로 분리했습니다. 연결 문맥 검토가 필요합니다.',
                          (step_id,), ('boundary', block.block_id, begin))
                content_start = begin + (marker.end() if marker else 0)
                body = block.text[content_start:end]
                role = ROLE_KO.match(body) or ROLE_EN.match(body)
                if role and not re.match(r'^(if|unless|otherwise)\b', body, re.I):
                    role_parts = pieces(block, content_start + role.start(1), content_start + role.end(1))
                    if len(role_parts) == 1:
                        roles.append(StepRoleCandidate(step_id=step_id, role=role_parts[0]))
                for match in FORM.finditer(trimmed):
                    names = pieces(block, begin + match.start(), begin + match.end())
                    if len(names) == 1:
                        form_id = self._id('form', step_id, match.start())
                        group['form_requirements'].append({'id': form_id, 'title': names[0],
                            'requirement': next((c for c in claims if names[0].text in c.text), claims[0]),
                            'step_ids': [step_id]})
                        issue('form_unresolved', '서식 이름의 원문 언급 후보입니다. 필요 관계와 실제 파일 연결은 미확정입니다.',
                              (form_id,))
        finish()

        processed, omissions = [], []
        for chunk in snapshot.chunks:
            if chunk.chunk_id not in allowed:
                continue
            primary = [s for s in chunk.evidence.spans if s.role == 'primary']
            if primary and all(s.block_id in complete for s in primary):
                processed.append(chunk.chunk_id)
            else:
                reason = 'partial_block' if any(s.block_id in partial for s in primary) else 'unsupported_content'
                omissions.append(ChunkOmission(chunk_id=chunk.chunk_id, reason=reason))
        if omissions:
            issue('partial_input', '지원하지 못한 원문 또는 일부만 제공된 블록이 있습니다.')
        if not workflows:
            issue('no_workflow_found', '허용 입력에서 지원하는 행위 표식을 찾지 못했습니다. 업무 부재의 의미 판정은 아닙니다.')
        extraction = parse_extraction({'schema_version': 'workflow-extraction-v1',
                                        'workflows': workflows, 'issues': issues})
        return OfflineExtractionReceipt(extraction=extraction, processed_chunk_ids=tuple(processed),
                                         omissions=tuple(omissions), roles=tuple(roles))
