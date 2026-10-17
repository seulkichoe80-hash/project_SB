# Phase 2D-4 근거·그래프 검증 계약

`WorkflowValidationEngine(inputs).validate(principal, snapshot, payload)`는 서버에서 관리자로 확인된 주체와 현재 활성 문서 버전의 스냅샷만 받는다. payload는 기존 WorkflowDiscoveryResult 또는 workflow-extraction-v1 JSON이다. 원격 공급자나 HTTP 연결 없이 동작하며 HTTP API·영속 저장·승인·게시를 추가하지 않는다.

## 입력과 호환성

기존 WorkflowExtraction/ReviewIssue, LLMAdapter, RAG, WORKFLOW_SCHEMA는 변경하지 않는다. 기존 parse_extraction의 강한 그래프 검증도 유지한다. 별도 DiagnosticInput은 개별 객체의 동일한 strict 모델과 크기/개수 한도를 적용하되 교차 참조 오류를 진단할 수 있도록 한다. 타입·필수 필드·추가 필드·알 수 없는 관계·중복 JSON 키·전역 ID 중복·한도 위반은 REJECTED다. deadline=null은 그대로 보존한다.

DiscoveryResult의 스냅샷·기관·문서·버전·파싱 시도·청킹 작업/세대를 서버 스냅샷과 대조한다. 입력·요청·순회·처리 청크 및 누락 상태도 검사한다. raw extraction만 전달할 때는 완전 처리된 snapshot coverage가 없으면 PARTIAL_INPUT으로 차단한다. 모델이 보고하는 coverage는 실제 의미 이해의 증거가 아니다.

## 근거와 상태

WorkflowInputService.validate(require_active=True)를 시작과 종료에 실행한다. 원본 SHA256, 원본 재파싱, source_blocks/청크 재구성과 현재 등록·기관·버전·세대가 기존 서비스에서 확인된다. 각 인용은 실제 block 부분 문자열과 canonical chunk span에 포함되어야 한다. 사용된 canonical EvidenceRef를 ChunkService.resolve에서 다시 원본 앵커에 해결한다. 공급된 근거 목록은 사용된 canonical 참조 집합과 정확히 일치해야 한다. 외부/위조 참조와 인용은 결과에 반사하지 않는다.

권한·오래된 스냅샷·활성 변경 실패는 기존 DomainError로 중단하며 후보 내용을 반환하지 않는다. 형식/근거 실패 보고는 candidates가 비어 있다. 그래프 오류는 원래 후보와 간선을 보존한 NEEDS_REVIEW이며 보정하지 않는다. 보고서는 서버에서 확인한 input_snapshot_id와 문서·기관·세대를 기록한다. 영속 승인 시점의 동시성/재검증 계약은 이후 별도 구현 대상이다.

`workflow-review-v1`은 기존 ReviewIssue와 충돌하지 않는 별도 계약이다. 각 WorkflowReviewIssue는 target_ids, code, severity, evidence_refs, reason, auto_block을 가진다. 보고 상태 PASS는 기계적 검사에서 차단 이슈가 없다는 뜻이다. 모든 상태에서 semantic_verification=NOT_VERIFIED, semantic_review_required=true, administrator_approval=NOT_REQUESTED, publishable=false다. 의미 검증·승인 상태를 모델 출력으로 설정할 수 없다.

## 그래프 진단

단계·조건·서식 참조, 조건과 간선 대상 결합, 자기 간선·중복 참조·중복 간선·고아 단계·미사용 조건을 검사한다. 명시 번호와 순서 근거가 없는 선후 관계는 UNCLEAR_ORDER다. 조건 문맥이 불일치하거나 requires 관계의 의미를 확정할 수 없으면 검토한다. 불명확한 순서에 간선을 추가하지 않는다.

반복은 조건, 보완/반려/복귀 표현, 명시적 목적 단계 번호와 그 조건 근거가 함께 있는 경우에만 반복 근거로 분류한다. 반복 간선을 제거한 뒤에도 순환이 남으면 UNSUPPORTED_CYCLE이다. 반복으로 해소된 순환은 EVIDENCED_REPEAT INFO로 표시하며 의미 정확성을 보증하지 않는다. 반복이라는 단어만 있거나 목적지가 없으면 순환을 허용하지 않는다. 순환 노드는 반복 DFS 기반 강연결요소로 찾고 단순 후속 노드와 구별한다.

## 의미 검토 보조의 한계

추출적 원문 일치, 기한/금액의 토큰 경계, 의무 표현을 검사하고 원문에 없는 주장은 차단 이슈로 남긴다. 인용 주변 부정/면제/금지, 같은 단계의 서로 다른 기한·상반 의무, 문서 내 규칙 변경 지시 문자열은 보수적으로 경고한다. 예: UNSUPPORTED_DEADLINE(ERROR, auto_block=true), POSSIBLE_CONTEXT_MISMATCH(WARNING), POSSIBLE_CONFLICT(WARNING).

이는 제한된 한국어/영어 어휘 규칙이다. 상이한 기한이 적용 조건별로 모두 유효할 수 있으며, 반대로 어휘가 같은 오류·규정 충돌·교묘한 프롬프트 인젝션을 놓칠 수 있다. 문자열·숫자 일치로 의미 정확성이나 법적 효력을 인증하지 않는다. 의역, 복잡한 시점/금액 계산, 규정 우선순위, 표/시각 순서, 실제 문서 goldset은 미검증이다. 문서는 데이터로만 처리하며 명령 실행·외부 호출 권한이 없다.

## 검증 범위

tests/test_workflow_validation.py는 새 합성 HWPX와 기존 파싱/청킹 서비스를 사용한다. 원본/fixture를 수정하지 않는다. 영향 시험과 비루프백 DNS/TCP 차단 전체 백엔드 회귀의 실제 결과는 outputs/PHASE2D4_REPORT.md에 기록한다. 프런트엔드·실모델·공개 문서 의미 검증·한컴 시각 검증은 이 단계 범위 밖이다. Phase 2D-5는 별도 사용자 요청 전 진행하지 않는다.
