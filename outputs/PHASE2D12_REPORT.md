# Phase 2D-1~2 구현·검증 보고

2026-10-17 KST, 사용자 승인 범위인 업무절차 구조화 계약과 입력 스냅샷만 구현했다. 실제 LLM·임베딩 호출, 유료 서비스, 업무 자동 발견/확정/게시, 관리자 승인 API, React Flow, DB migration은 추가하지 않았다. 작업 측정 경과는 약10분이며 아래 실행시간은 별도 기록이다.

## 기준과 Git

GitHub origin seulkichoe80-hash/project_SB의 main은 `40badd6d3553b9d46ff01edb144d02cdb76b22ce`(PR #1 병합)였다. 시작 작업 트리는 clean, 기존 feature branch HEAD는 `acde13587e7f39aabe50377fdab6e5a01af11233`이며 main과 파일 tree가 같았다. main에서 `feat/phase2d-contract-snapshot` 새 브랜치를 생성했다. HEAD는 main 기준 SHA 그대로이며 변경은 미커밋이다. commit/push/merge/배포는 하지 않았다.

PRD/AGENTS/TASKS, G1 A/B/C/D, 기존 WORKFLOW_SCHEMA/청킹/EvidenceRef/RAG 계약과 TEST_PLAN의 영향 범위 기준을 적용했다. 현재 로컬 계약 구현은 실제 LLM의 G1 B-02 통과나 전체 Phase 2D 완료가 아니다.

## 구현·파일

- apps/api/workflow_contracts.py: WorkflowCandidate, Step, Condition, Edge, FormRequirement, ReviewIssue, GroundedAssertion, EvidenceCitation, 별도 WorkflowExtractionAdapter Protocol, parse_extraction, 서버 WorkflowValidation.
- apps/api/workflow_snapshot.py: SnapshotSettings, WorkflowInputSnapshot, 입력/진척 계약, WorkflowInputService의 capture/validate/iter_chunks/mark_processed.
- apps/api/workflow_evidence.py: canonical 근거 범위 해석, LegacyEvidenceAdapter/EvidenceBridge, fail-closed validate_extraction.
- schemas/workflow-extraction-v1.schema.json, workflow-input-snapshot-v1.schema.json, workflow-validation-v1.schema.json: 새 버전 JSON Schema.
- tests/test_workflow_inputs.py: 신규34개 시험.
- docs/PHASE2D_INPUT_CONTRACT.md: 현재 계약·사용 경계·한도·한계.
- ARCHITECTURE.md, TEST_PLAN.md, TASKS.md: 관련 구조·검증·진척만 추가.
- 본 보고: outputs/PHASE2D12_REPORT.md.

기존 LLMAdapter.generate()/Generation, RAG·인증·파서·청크 서비스 코드와 구형 schemas/workflow.schema.json, 기존 테스트/fixture/잠금파일/과거 보고·증거는 변경하지 않았다. 작업 시작 추적 파일239개 중 변경된 것은 위 기준 문서3개이며 나머지236개는 SHA256이 동일하다.

## 계약·스냅샷·근거

출력 모델은 strict type·추가 필드 금지·필수 nullable deadline·전역 ID 유일성·동일 업무 내 단계/조건 참조·허용 간선/조건 관계·출력 byte/노드/배열 한도를 검사한다. raw JSON 중복 key·비유한 상수도 거부한다. deadline=null은 미확인이며 기한 부재 확정이 아니다. 기존 어댑터 반환형은 그대로 두고 WorkflowExtractionAdapter는 분리했다. 실제 추출 구현체는 아직 없다.

스냅샷은 단일 선택 문서 버전 전체에 대해 institution/document/version, 원본 SHA256, 당시 활성 포인터·version revision, parse job/attempt/복합 attempt ID, parser method, chunk job/세대/config, 전체 chunk ID·payload와 source_blocks 관계, 설정/프롬프트 계약 버전, input_scope, 처리/미처리 목록을 기록한다. canonical 입력 digest와 처리 진척을 분리한다. DTO는 JSON 직렬화 가능하지만 이번에 DB/파일 영속 snapshot 서비스는 추가하지 않았다. 사용 전 fresh validate가 필요하다.

원본 hash 검증·재파싱·전체 블록 대조·전체 청크 재구성/JSON 대조·마지막 metadata 재조회로 누락·중복·변조·진행 중 변경을 검사한다. 저장된 청크 개수만으로 완전성을 판단하지 않는다. 설정 한도 초과는 전체 실패이며 조용한 truncation은 없다. 현재 기관/등록 상태·활성 포인터·parse/chunk 세대가 바뀌면 stale 입력을 차단한다. 관리자 후보 분석과 require_active=True의 현재 활성 입력 검사를 분리한다. 기존 한글 기관 ID도 지원한다.

구형 근거는 원래 tenant/document/version/element/quote 전체를 보존하고 명시 block/chunk/start mapping을 검사한다. bridge는 선택 citation과 전체 canonical EvidenceRef의 anchor·hash·다중 block/span·NOT_VERIFIED 상태를 유지한다. 역변환은 fresh snapshot과 전체 bridge를 재검증해 원래 값을 복원한다. element ID 이름을 추측하거나 임의의 첫 청크를 선택하지 않는다. 명시 mapping의 의미적 동일성은 여전히 사람 검토 사항이다.

구조·근거 연결 검증을 통과해도 semantic_verification=NOT_VERIFIED, semantic_review_required=true, administrator_approval=NOT_REQUESTED, publishable=false다. 모델 출력에 검증/승인 상태를 넣으면 거부한다. 지금은 인용된 원문에 그대로 존재하는 주장만 받지만 정확 인용도 조건·법적 효력·업무 순서의 의미적 타당성을 증명하지 않는다. 근거 없는 기한/의무 문구는 검증 단계에서 거부한다.

## 실제 실행

| 명령/범위 | 결과 |
|---|---|
| `.venv/bin/python -B -m unittest discover -s tests -p test_workflow_inputs.py -v` | **34 PASS /0 FAIL**, 3.899초 |
| `.venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output work/phase2d/backend-confirmed.json` | **239 PASS /0 FAIL /0 SKIP /0 BLOCKED** = 기존205 + 신규34 |
| 최종 전체 regression 실행시간 | 시험44.081초, guard runner45.326초 |
| network guard | probe PASS, 본 시험 비루프백 연결 시도0, 실제 공급자 호출0 |
| `.venv/bin/python -m pip check`, `git diff --check` | PASS |
| 기존 원본/코드/테스트/fixture/증거 hash 확인 | 기존 추적 파일236개 동일, 관련 문서3개만 변경 |

최종 전체 실행 시각은 결과 파일의 UTC `2026-10-17T10:13:37.224378+00:00`(KST 19:13:37)이다. 결과에 기록한 Python source/requirements 해시와 최종 구현 파일은 일치한다. UI/프런트 코드는 변경하지 않았으며 UI43개·typecheck/build는 이번에 재실행하지 않았고 신규 PASS로 보고하지 않는다.

시험은 정상/비정상 JSON·각 계층 extra/missing·중복 ID/인용·잘못된 참조/관계·크기/노드 제한·상태 위조, nullable deadline, unsupported 기한/의무, 구형 bridge 왕복과 scope/quote/정보손실 거부, 전체 순회/부분/중복/누락 처리, inactive 후보/current 구분, 버전/청킹 세대·capture/순회 중 변경, parse attempt/기관 변경, 타기관/reader/worker/미인증, 등록 해제, 실제 테스트 임시 원본 손상·SHA256·DB dump 무변경을 포함했다. 기존 RAG·인증·파싱 전체 회귀도 재실행했다.

초기 표 grid의 Python tuple/JSON list 표현 차이를 canonical JSON 비교로 수정했고, 신규 시험의 UnitOfWork SQL 호출 경로를 수정했다. 중간 focused 로그와238 PASS 전체 결과도 덮어쓰지 않고 work/phase2d에 보존했다. 한글 기관 ID 호환성 시험을 추가한 뒤 최종34/239개를 다시 실행했다. 테스트 자체에서 만든 임시 원본만 손상 시험에 사용했으며 기존 fixture는 건드리지 않았다.

## 위험·후속

전체 문서·batch마다 재파싱/재구성하므로 대규모 성능은 미측정이다. snapshot은 인증된 서버 Principal을 받는 로컬 서비스이며 새 공개 API가 아니다. batch 사이 변경은 다음 경계에서 탐지한다. 조기 순회 중단 시 명시 validate/진척 보고가 필요하며 미래 결과 저장/게시 직전에도 재검사해야 한다. coverage complete는 호출자의 처리 진척 기록으로, 추출 성공·의미 검토·승인 증거가 아니다. 설정/프롬프트 버전은 입력에 고정하며 전역 현재 프롬프트 설정 registry는 아직 없다. immutable DTO hash도 서명이 아니며 서비스의 current 검사 없이 신뢰하지 않는다.

실제 모델 추출·독립 의미 검토·미지 업무 발견 품질·OCR/Vision·서식 실물 연결·승인/게시·업무지도는 미구현/미검증이다. 기존 Starlette TestClient/httpx deprecation 경고가 남으며 이번에 의존성을 변경하지 않았다. 실제 Supabase/LLM/임베딩 API 호출·유료 서비스·배포는 모두0이다.

**Phase 2D-1~2의 로컬 계약/입력 기반은 검증됐다. Phase 2D-3의 오프라인 모의 어댑터 기반 후보 추출 구현에 착수 가능한 상태지만 이번에는 진행하지 않는다.** 실제 LLM 연결·품질 검증은 자료/모델/예산 승인과 별도 B-02 검증이 필요하고 자동 게시 권한은 포함하지 않는다.
