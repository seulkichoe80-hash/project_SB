# Phase 2D-4 완료 보고

실행일: 2026-10-17T10:42:17.521418+00:00. 범위는 오프라인 근거·그래프 검증이며 Phase 2D-5는 시작하지 않았다.

## 구현과 계약

- 기존 후보/근거/RAG 계약을 보존하고 WorkflowValidationEngine, 그래프 진단, workflow-review-v1 strict Pydantic/JSON Schema를 추가했다.
- 형식: 필수/추가 필드·타입·허용 관계·중복 JSON 키·전역 ID·출력 크기/객체 한도 검증. 참조/간선 오류는 원 후보를 보존한 검토 이슈로 진단한다.
- 출처: 관리자·기관·현재 활성 버전·등록 상태 확인, 스냅샷 원본 SHA256/재파싱/청킹 세대 대조, 실제 span과 canonical EvidenceRef 원본 서비스 재해결, 위조 근거 목록 거부. 검사 종료 시 현재성 재검사.
- 그래프: 정상 선형·조건 분기, 보완/반려/반복의 명시 목적지·조건 근거, 잘못된 순환·중복 간선·참조 누락·고아/미사용 조건 진단. 순환 후속 노드와 실제 순환 구성요소를 구별한다. 순서/간선을 임의로 보정하지 않는다.
- 의미 보조: 무근거 기한·금액·의무, 숫자 부분문자열 오인, 부정/면제 문맥, 가능한 규정 충돌·문서 지시 문자열 검토. 단순 일치로 의미를 인증하지 않는다.
- 모든 결과는 semantic_verification=NOT_VERIFIED, administrator_approval=NOT_REQUESTED, publishable=false다. PASS는 기계적 검사만 의미한다.

## 변경 파일 (이번 단계 10개)

신규:
- apps/api/workflow_validation.py
- apps/api/workflow_graph.py
- apps/api/workflow_review.py
- schemas/workflow-review-v1.schema.json
- tests/test_workflow_validation.py
- docs/PHASE2D4_VALIDATION.md
- outputs/PHASE2D4_REPORT.md

수정: ARCHITECTURE.md, TASKS.md, TEST_PLAN.md의 관련 절만 추가/갱신.

## 실제 ReviewIssue 예시

새 합성 원본에 없는 `3일 이내` 기한 주장을 주입한 실행 결과:

```json
{
  "status": "NEEDS_REVIEW",
  "target_ids": [
    "step_0285921a2559c260c8360d9ae391b053"
  ],
  "code": "UNSUPPORTED_DEADLINE",
  "severity": "ERROR",
  "auto_block": true,
  "canonical_reference_count": 1,
  "semantic_verification": "NOT_VERIFIED"
}
```

실제 EvidenceRef 전체는 work/phase2d4/review-example.json에 별도로 보존했다. raw extraction의 미완료 snapshot coverage에 대해서는 별도 PARTIAL_INPUT도 함께 기록됐다. 오류 그래프는 후보/간선을 보존하지만 자동 사용/승인하지 않는다.

## 실제 검증

- 영향 시험: `.venv/bin/python -B -m unittest discover -s tests -p test_workflow_validation.py -v` → 신규 46 PASS, 13.326초. 증거 work/phase2d4/focused-4.log.
- 전체: `.venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output work/phase2d4/backend-final.json` → 기존273 + 신규46 = **319 PASS / FAIL0 / SKIP0 / BLOCKED0**. 기존273개 test ID의 포함을 대조했다. 전체 runner 59.575초.
- 비루프백 DNS/TCP 가드 probe PASS, 차단된 외부 시도0, 실제 공급자 호출0. 가드 범위는 Python 및 상속 Python 하위 프로세스이며 loopback은 허용한다.
- 근거: work/phase2d4/backend-final.json, backend-final.log, backend-final.network.json. 모든 기록 code_sha256이 최종 Python 코드와 일치한다.
- 선형/분기/명시 반복·반려와 근거 없는 순환, 중복/누락 참조, 위조 인용/근거 목록, 타기관·reader·구버전·새 청킹 세대·해제·검사 중 변경·원본 변조, 부정·충돌·문서 지시·처리 누락 모두 신규 시험에 포함된다.
- 초기 집중 시험에서 발견한 연결/시험 구성 오류를 수정했고 실패 로그도 삭제하지 않았다. 현재 최종 실행은 위 수치다.
- UI/typecheck/build·실제 공급자·공개 문서 의미 goldset·한컴 시각 검증은 이번 미실행이며 과거 결과를 새 PASS로 사용하지 않는다. 기존 Starlette/httpx deprecation warning은 남아 있다.

## 보존·보안·Git

시작 브랜치/HEAD: feat/phase2d-offline-extraction / 40badd6d3553b9d46ff01edb144d02cdb76b22ce.

기존 19개 변경을 비밀키/자격증명 패턴 검사 및 archive/hash 보존 뒤 사용자 승인에 따라 로컬 커밋 **e57c657a9b0adff50e254b26e6655be1179895e1**으로 보존했다. 보존 사본 /tmp/sb-phase2d4-preservation/prior-work.tar.gz와 manifest.json. 기존 구현·스키마·테스트·보고서16개 해시 일치, 과거 work/phase2d 및 work/phase2d3 증거22개 원본 일치. 기존 원본·fixture 변경/삭제 없음. 패턴 검사 발견0이며 이는 전용 개인정보 분류기의 완전성 보장은 아니다. 합성 문서만 새로 생성했다.

현재도 feat/phase2d-offline-extraction, HEAD는 위 보존 커밋이다. 이번 2D-4의 10개 파일은 미커밋(추적 문서3, 신규7)이며 staging하지 않았다. main 직접 변경·push·merge·배포·실제 계정/키 등록·LLM/임베딩/Supabase 호출은 없다.

## 미검증 범위·후속 조건·시간

어휘 기반 보조는 동음/의역·복합 조건·규정 우선순위·교묘한 인젝션·복잡한 금액/기한을 완전 판별하지 못한다. 보수적 오탐도 가능하다. 의미 검토와 관리자 승인은 미완료다. 현재성 검사는 검증 경계 시점 기준이며, 이후 영속화/승인/게시가 생기면 그 시점의 원자적 현재성 재검사가 필요하다. 원본 재파싱과 근거 재해결을 반복하므로 대형 문서 성능은 미검증이다.

Phase 2D-4의 합성·오프라인 기계적 검증 범위는 완료했다. Phase 2D-5는 이 계약/NOT_VERIFIED 경계·최종 회귀 결과를 유지하고 사용자에게 후속 범위를 승인받은 후 착수할 수 있다. 이번에는 착수하지 않았다.

보존 준비부터 최종 검증/보고 작성까지 약 420초 (7.0분), 사전 문서/환경 점검 시간은 별도다. 신규 패키지 설치·환경 설정 변경은 없었다.
