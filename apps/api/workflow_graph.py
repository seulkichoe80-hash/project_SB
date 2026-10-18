"""Conservative graph diagnostics. No inferred edges, repairs or legal conclusions."""
import re

NUMBER = re.compile(r'^\s*(\d{1,3})[.)]\s+')
BRANCH = re.compile(r'보완|반려|반복|되돌|돌아|다시|reject|return|repeat|resubmit', re.I)
CONDITIONAL = re.compile(r'경우|때에는|이라면|이면|한다면|필요시|발생시|\bif\b|\bunless\b|\bwhen\b', re.I)
TARGET = re.compile(r'(\d{1,3})\s*단계(?:로|부터)|(?:to|from)\s+step\s+(\d{1,3})', re.I)


def cyclic_nodes(nodes, edges):
    """Iterative strongly connected components; descendants are not cycles."""
    outgoing, reverse = {n: [] for n in nodes}, {n: [] for n in nodes}
    for e in edges:
        outgoing[e.source].append(e.target)
        reverse[e.target].append(e.source)
    seen, order = set(), []
    for start in nodes:
        stack = [(start, False)]
        while stack:
            node, finished = stack.pop()
            if finished:
                order.append(node)
            elif node not in seen:
                seen.add(node)
                stack.append((node, True))
                stack.extend((n, False) for n in outgoing[node] if n not in seen)
    assigned, cyclic = set(), set()
    for start in reversed(order):
        if start in assigned:
            continue
        component, stack = set(), [start]
        while stack:
            node = stack.pop()
            if node not in assigned:
                assigned.add(node); component.add(node)
                stack.extend(reverse[node])
        if len(component) > 1 or start in outgoing[start]:
            cyclic.update(component)
    return cyclic



def graph_review(workflow, emit):
    steps = {s.id: s for s in workflow.steps}
    conditions = {c.id: c for c in workflow.conditions}
    ids = set(steps)
    edges, used, seen, connected, returns = [], set(), set(), set(), []
    numbers = {}
    for step in workflow.steps:
        matches = {int(m.group(1)) for a in [step.label, *step.actions]
                   if (m := NUMBER.match(a.text))}
        if len(matches) == 1:
            numbers[step.id] = matches.pop()
    for obj in [*workflow.conditions, *workflow.form_requirements]:
        if len(obj.step_ids) != len(set(obj.step_ids)) or not set(obj.step_ids) <= ids:
            emit('INVALID_REFERENCE', (obj.id,), 'ERROR', '단계 참조가 중복되거나 존재하지 않습니다.', True)
    for edge in workflow.edges:
        valid = (edge.source in ids and edge.target in ids and edge.source != edge.target
                 and len(edge.condition_ids) == len(set(edge.condition_ids))
                 and set(edge.condition_ids) <= conditions.keys()
                 and bool(edge.condition_ids) == (edge.relation == 'conditional'))
        if valid:
            valid = all(edge.target in conditions[c].step_ids for c in edge.condition_ids)
        if not valid:
            emit('INVALID_REFERENCE', (edge.id,), 'ERROR', '간선의 단계·조건 참조 또는 관계가 유효하지 않습니다.', True)
            continue
        key = (edge.source, edge.target, edge.relation, tuple(sorted(edge.condition_ids)))
        if key in seen:
            emit('DUPLICATE_EDGE', (edge.id,), 'WARNING', '동일한 관계가 중복되었습니다.', True)
        seen.add(key); edges.append(edge); used.update(edge.condition_ids)
        connected.update((edge.source, edge.target))
        # Edge evidence has already been resolved. Matching is a conservative hint,
        # never semantic approval. Require explicit target AND branch AND condition.
        text = edge.explanation.text
        targets = {int(a or b) for a, b in TARGET.findall(text)}
        repeat = (edge.relation == 'conditional' and BRANCH.search(text)
                  and CONDITIONAL.search(text) and numbers.get(edge.target) in targets
                  and all(BRANCH.search(conditions[c].statement.text)
                          and CONDITIONAL.search(conditions[c].statement.text)
                          and numbers.get(edge.target) in {int(a or b) for a,b in TARGET.findall(conditions[c].statement.text)}
                          for c in edge.condition_ids))
        if repeat:
            returns.append(edge)
        elif edge.relation == 'precedes':
            src, dst = numbers.get(edge.source), numbers.get(edge.target)
            supported = (src is not None and dst == src + 1
                         and list(numbers.values()).count(src) == 1
                         and list(numbers.values()).count(dst) == 1
                         and any(NUMBER.match(c.quote) and int(NUMBER.match(c.quote).group(1)) == dst
                                 for c in edge.explanation.evidence))
            if not supported:
                emit('UNCLEAR_ORDER', (edge.id,), 'WARNING', '선후 순서를 명시한 근거가 불충분합니다. 순서를 보정하지 않았습니다.', True)
        elif edge.relation == 'requires' or (edge.relation == 'conditional' and (not CONDITIONAL.search(text) or any(conditions[c].statement.text not in text for c in edge.condition_ids))):
            emit('UNCLEAR_ORDER', (edge.id,), 'WARNING', '조건 분기를 명시한 문맥을 검토해야 합니다.', True)
    if len(steps) > 1:
        for node in ids - connected:
            emit('ORPHAN_NODE', (node,), 'WARNING', '다른 단계와 연결되지 않았습니다.', True)
    for node in conditions.keys() - used:
        emit('UNUSED_CONDITION', (node,), 'WARNING', '간선에서 참조하지 않는 조건입니다.', True)
    cyclic = cyclic_nodes(ids, edges)
    if cyclic:
        remaining = cyclic_nodes(ids, [e for e in edges if e not in returns])
        if remaining:
            emit('UNSUPPORTED_CYCLE', tuple(sorted(cyclic)), 'WARNING', '명시적 보완·반려·반복 근거로 해소되지 않는 순환입니다.', True)
        else:
            emit('EVIDENCED_REPEAT', tuple(e.id for e in returns), 'INFO', '명시적 복귀 단계와 조건을 가진 반복 관계입니다. 의미 검토는 별도입니다.', False)
