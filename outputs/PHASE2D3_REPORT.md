# Phase 2D-3 오프라인 후보 추출 구현·검증 보고

2026-10-17 KST. 구현 범위는 합성 PDF/HWPX를 읽는 결정적 오프라인 후보 엔진과 출력/근거/처리 범위 검증이다. 실제 LLM·임베딩·Supabase·유료 서비스 호출, 자동 확정/게시, 관리자 UI, React Flow, 파괴적 DB 변경/배포는 하지 않았다. 측정 경과는 약14분이다.

## Git·기존 작업 보존

시작 브랜치는 feat/phase2d-contract-snapshot, HEAD는 main 기준 `40badd6d3553b9d46ff01edb144d02cdb76b22ce`였다. Phase 2D-1~2의 미커밋 변경12개를 확인했다. checkout 밖 `/workspace/sb-phase2d12-preservation-6awwrpld/`에 전체12개와 work/phase2d 검증 근거의 archive, SHA256 manifest, 추적 diff를 저장하고 압축 안의 파일 hash까지 검증했다. 그 뒤 `feat/phase2d-offline-extraction` 브랜치를 만들고12개 hash가 모두 유지됨을 확인했다. stash/drop/reset/merge를 사용하지 않았다.

완료 시 이전12개 중 구현·schema·기존 시험·계약 문서·과거 보고9개는 byte-identical이다. 나머지 ARCHITECTURE/TASKS/TEST_PLAN3개에는 현재 단계 내용만 추가했다. 기존 RAG/인증/파서/원본/fixture/잠금파일·과거 증거도 유지했다. HEAD는 그대로이며 Phase2D-1~2와2D-3 변경은 모두 미커밋이다. commit/push/merge/배포는 하지 않았다. 이전 미커밋 작업이 새 브랜치에 자동 커밋된 것은 아니며 archive는 추가 보존본이다.

## 구현·파일

이번 단계 신규 파일:

- apps/api/workflow_offline_adapter.py: 문서 표식·구조·행위 어휘 기반 DeterministicWorkflowAdapter.
- apps/api/workflow_discovery.py: 관리자용 WorkflowDiscoveryEngine, 전체 순회·scope·안전성 검증.
- apps/api/workflow_discovery_models.py: receipt/역할/scope/settings/서버 후보 envelope와 확장 Protocol.
- schemas/workflow-discovery-v1.schema.json: 별도 결과 Schema. 기존 extraction Schema는 변경하지 않았다.
- tests/test_workflow_discovery.py: 신규34개 시험과 테스트 내 새로운 합성 PDF/HWPX 생성 helper.
- docs/PHASE2D3_OFFLINE_DISCOVERY.md: 규칙·계약·한도·사용법·한계.
- 본 outputs/PHASE2D3_REPORT.md.

기존 기준 문서3개를 보완했으며 Phase2D-1~2의 미커밋 파일12개도 현재 작업 트리에 포함된다. AGENTS/PRD·관련 FR/NFR·TEST_PLAN 실행 기준과 seomuitda-quality-check의 Feature Gate를 적용하고 전체 backend 회귀를 새로 수행했다.

## Adapter·처리 구조

기존 `WorkflowExtractionAdapter.extract(snapshot)->WorkflowExtraction`를 그대로 구현한다. 구조화된 처리 범위를 위해 별도 확장 `extract_with_coverage(snapshot, chunk_ids)->OfflineExtractionReceipt`를 둔다. 기존 LLMAdapter.generate/Generation을 변경하지 않았다. model_id는 offline-lexical-workflow-v1, rule_version은 explicit-markers-v1이며 test_only=true/network_access=false다.

엔진은 fresh snapshot 검증→전체 청크 순회→명시 분석 범위 지정→깊은 복제 입력으로 adapter 호출→strict Schema·ID/참조·scope 검사→canonical 근거/정확 원문 검증→역할/원본세대 재검사→결과 DTO 반환 순서다. 허용되지 않은 scope/기관/문서/버전 근거, duplicate/unknown ID·잘못된 receipt·호출 중 설정/입력 변조·stale snapshot을 차단한다. 모델/설정/계약·입력 세대 정보를 결과에 기록한다.

업무명 사전/특정 업무별 시나리오 분기는 없다. 문서의 업무명/Workflow 표식·명시 heading과 일반 행위 어휘를 사용한다. 제목 없이 행위가 시작되면 첫 원문을 임시 업무명 후보로 쓰고 검토 문제를 남긴다. 다중 제목을 별도 업무로 묶고 반복 제목도 위치별 ID로 구분한다. 실제 업무명/단계명을 코드에 삽입하지 않는다.

단계는 행위가 있는 줄 단위 후보다. 여러 청크에 걸친 원문은 한 단계의 복수 인용 actions로 보존한다. 명시 기한 구문·의무 어휘·역할/서식 언급을 원문 그대로 연결한다. 무번호/번호 중복·누락/조건 경계에는 순서를 만들지 않고, 유일한 연속 번호에만 precedes 후보를 만든다. 조건·반려·보완·반복 원문을 유지하고 명시한 목적지에만 conditional 관계를 연결한다. 알 수 없는 분기를 정상 직선 흐름으로 바꾸지 않는다.

## 실제 합성 출력 예시

새 HWPX 입력:

> 업무명: 별빛 표본 접수
>
> 1. 접수 담당자는 반드시 별빛신청서를 3일 이내 제출한다.
>
> 2. 자료가 누락된 경우 1단계로 돌아가 보완을 요청하고 반려한다.

실제 실행에서 업무명 후보1개, 단계2개, 역할 후보 `접수 담당자`, 원문 기한 `3일 이내`, 원문 의무 문구, 서식 언급 `별빛신청서`, 2→1 conditional 후보를 얻었다. 1→2의 무조건 직선 간선은 만들지 않았다. 조건 주어 `자료`는 역할 후보에서 제외했다. 입력 scope는 complete이지만 후보는 NEEDS_REVIEW·semantic_verification=NOT_VERIFIED·administrator_approval=NOT_REQUESTED·publishable=false다.

첫 행위는 원문 block의 start0/end33 quote에 연결됐다. 실제 chunk ID는 `d56c5ca61b9d2e081ceee41f13af83cd33862d4e87881b525bada30306627794`, block ID는 `7871603f079feb67c3c280a419a487f1bb587303df01a7545494722d83a729c2`다. 결과에는 사용된 canonical EvidenceRef3개 전체(anchor·SHA256·문서/버전·spans·NOT_VERIFIED)를 보존했다. 전체 합성 예시는 로컬 `work/phase2d3/example-result-confirmed.json`에 새로 저장했다. 이 수동 예시 실행을 추가 unittest 건수로 계산하지 않았다.

## 범위·누락·불확실성

input/traversed/requested/processed ID와 omissions를 따로 기록한다. 모든 원문 text가 허용된 primary spans로 제공된 블록만 분석한다. scope 제한/부분 블록/미지원 비텍스트/adapter 누락은 각각 scope_limit/partial_block/unsupported_content/adapter_omitted로 남긴다. 누락을 receipt에서 숨겨도 엔진이 incomplete와 partial_input을 생성한다. 비텍스트를 처리 완료로 허위 보고하면 거부한다. context 사본·표 셀 자식 문단을 중복 추출하지 않는다.

처리 완료는 규칙 스캔 범위의 완료이지 모든 업무의 의미적 발견 완료가 아니다. 비절차 자료는 빈 workflows+no_workflow_found 검토 항목이다. 실제로 업무가 없다는 의미 판정을 하지 않는다. 제목/단계/조건/간선/서식·역할 모두 후보이며 의미 검토가 필요하다. 실제 서식 파일과 필요 관계는 form_unresolved다. 자동 승인/게시 경로는 없다.

## 실제 테스트 결과

환경: Linux Python3.12.14, 기존 의존성 유지. 모든 fixture는 기존 것을 읽기 전용으로 사용하거나 시험 내 새 합성 파일/bytes로 생성했다. 기존 fixture 파일을 덮어쓰지 않았다.

| 명령/범위 | 실제 결과 |
|---|---|
| `.venv/bin/python -B -m unittest discover -s tests -p test_workflow_discovery.py -v` | **34 PASS /0 FAIL**, 9.257초; work/phase2d3/focused-confirmed.log |
| `.venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output work/phase2d3/backend-confirmed.json` | **273 PASS /0 FAIL /0 SKIP /0 BLOCKED** = 기존239 + 신규34 |
| 전체 실행시간 | 시험43.166초, guard runner44.218초 |
| Python DNS/TCP 비루프백 guard | probe PASS, 본 시험 외부 연결 시도0, 실제 공급자 호출0 |
| 원본·DB dump 무변경, Schema 일치, source hash 비교 | PASS |
| UI/typecheck/build | 이번에는 미실행. 프런트 변경이 없으며 과거43 PASS를 신규 결과로 보고하지 않음 |

최종 전체 실행 기록 시각은 UTC2026-10-17T10:30:30.661464+00:00(KST19:30:30)이다. 결과의 Python source/requirements hash와 최종 소스가 모두 일치한다. raw 근거는 work/phase2d3/backend-confirmed.json/.network.json/.log이며 기존 raw 파일을 덮어쓰지 않았다. 이전271 PASS 기록도 중간 실행으로 보존했다. 예시 검토에서 조건 주어를 역할로 추출한 위양성을 발견해 일반 역할 어미 필터·회귀시험을 추가했고, canonical EvidenceRef catalog 보존을 보강한 최종 코드로34/273개를 다시 실행했다.

신규 시험은 새로운 합성 업무명·실제 PDF/HWPX 경로·다중/반복 제목·제목 없음·비절차·청크 경계·기한/의무/역할/서식·조건/반려/반복/번호 누락, 어댑터 ID 중복/범위 밖 근거/무근거 주장/잘못된 역할·receipt·예외·입력/설정 변조, scope 누락/미지원 이미지·stale 세대/등록 해제·기관/문서/동일 문서 다른 버전 혼용, 원본/DB 무변경을 포함한다. 기존 Phase2D-1~2/RAG/인증/파싱 전체도 새로 실행했다.

## 한계·다음 단계

규칙 기반 결정적 테스트 대역이다. 임의 매뉴얼의 의미 이해·새 업무 일반화·절차/관계 정확도 목표 달성을 주장하지 않는다. 일반 행위 어휘/명시 표식 밖 문서, 부정/인용/설명문 구별, 복합 문장의 단계 분리, 임의 담당 역할, 표/그림의 암묵적 의미는 누락·위양성이 가능하다. 번호·정확 인용도 선후·의무의 의미적 타당성을 증명하지 않는다. 역할 후보는 인증 권한이 아니다.

기존 snapshot의 반복 재파싱·재구성 비용과 대규모 지연/메모리는 미측정이다. 결과는 로컬 DTO이며 영속 작업/재개·DB 저장·수정/승인 UI·자동 게시가 없다. 비신뢰 Python adapter를 sandbox하는 제품이 아니며 개발자가 명시 주입한 로컬 대역만 사용한다. 실제 LLM·embedding·독립 의미 holdout·HWPX 시각 순서는 NOT_RUN이며 기존 Starlette/httpx deprecation 경고도 남는다.

**Phase 2D-3의 오프라인 후보 처리 범위는 검증됐다. 후속 Phase 2D-4는 범위와 사용자 승인을 받은 뒤 착수할 수 있으나 이번 작업에서는 진행하지 않았다.** 실제 공급자/유료 호출·자동 확정/게시·배포 권한을 의미하지 않는다.
