# 서무ITDA v0.2-A 결과

2026-10-18 KST. P0-1·P0-3 구현 완료. P0-2·다음 단계는 시작하지 않았다.

## 기준 및 Git

origin/main을 갱신하고 PR #2 병합 SHA `8986b912083876ccfd6dabb207a92cc33d00d1e5`가 최신 main에 포함됨을 확인했다. 이 SHA에서 `feat/v02a-ui-clarity`를 생성했다. 이전 `feat/phase2d-offline-extraction`의 v0.1 SHA `1565d84d6b96088caf3a08cf0fb2d7a67df33c46`를 보존했다. 시작 작업 트리는 clean이었다. 신규 커밋·push·merge·태그·배포는 없다. 변경은 검토할 수 있는 미커밋 상태다.

## 화면 변경

| 위치 | 이전 | 현재 |
|---|---|---|
| 홈 문서 관리 | 문서 등록 준비 중 | 관리자: 문서 등록·조회 가능 / 직원: 문서 조회 가능 / 익명: 로그인 필요 |
| 공통 안내 | 데이터 미연결 | 문서 이용 권한을 표시하고 실제 AI·원격 인증 연결 상태를 별도 설명 |
| 홈 AI | 준비 중 | 실제 AI 미연결, 질문 전송·답변 생성 미제공 |
| 지도 노드 | 근거 미확인 또는 검토 개수 | 근거 확인 필요 / 출처 확인, 내용 검토 필요는 별도 유지 |
| 원문 패널 | EvidenceRef 구조·출처 확인, NOT_VERIFIED | 출처 확인 + 내용 검토 필요. 기술 상태는 접힌 상세 정보 |
| 원문 누락 | 일반 요청 오류 | 원문 근거를 찾을 수 없음, 문서 등록 상태·버전 확인 안내 |

문서 등록·조회 링크는 기존 화면을 사용한다. 최근 문서와 실제 처리 건수는 미연결이며 가짜 데이터를 생성하지 않았다. `remote_enabled`는 기존 상태 API에서 읽으며 설정 감지를 실제 인증 성공으로 표현하지 않는다. 실제 공급자에는 연결하지 않았다.

노드의 출처 확인은 현재 선택한 단계의 중복 제거된 모든 인용이 원문 재해결·범위·인용 대조를 통과한 경우에만 표시한다. 단일 인용 통과로 복수 근거 전체를 확인했다고 표시하지 않는다. 단계·문서·후보·세대 전환 시 상태를 구분하고 재확인한다. 실패/재요청 중에는 확인 상태를 제거한다. 의미 상태 NOT_VERIFIED와 승인 NOT_REQUESTED는 유지한다.

## 변경 파일

- 제품 4개: `apps/web/src/auth/AuthContext.tsx`, `apps/web/src/components/AppLayout.tsx`, `apps/web/src/pages/HomePage.tsx`, `apps/web/src/pages/WorkflowPage.tsx`.
- 신규 시험: `scripts/validation/check_v02a_ui.cjs`.
- 기존 시험의 문구·상세 펼침 기대값 갱신: `check_stage2_ui.cjs`, `check_stage3_home.cjs`, `check_phase2e1_ui.cjs`, `check_phase2e2a_ui.cjs`, `check_phase2e1_live.cjs`, `check_v01_e2e.cjs` (모두 scripts/validation/).
- 문서: `TASKS.md`, `TEST_PLAN.md`, `docs/V02A_UI_CLARITY.md`, 이 보고서.
- 새 증거: `outputs/v02a/`의 JSON·PNG. 기존 증거는 수정하지 않았다.

## 이번 실행 결과

| 범위 | 최종 결과 |
|---|---|
| TypeScript 검사 | PASS |
| 프로덕션 빌드 | PASS |
| 신규 v0.2-A UI | 24 PASS / 0 FAIL |
| 기존 UI | 104 PASS / 0 FAIL (14+6+17+6+37+24) |
| 전체 백엔드 | 409 PASS / 0 FAIL / 0 BLOCKED |
| 실제 loopback HTTP 통합 | 13 PASS / 0 FAIL |

[최종 실행 인덱스](v02a/verification.json)에서 명령·해시·결과 경로를 확인한다. 기존 전체 runner는 128.263초, 백엔드는 123.926초, 실제 HTTP는 20.853초였다(병렬 실행으로 단순 합산하지 않는다). 개발·보존·검증은 약 9분이었다. 기존 환경·설치 지침을 재사용했고 의존성 재설치나 설정·lockfile 변경은 없었다.

전체 runner 첫 실행은 2개 문구 기대값 때문에 FAIL이었다. 관리자 모의 세션을 익명 문구로 기대한 Stage2와 HTTP500을 검증 실패로 기대한 안정화 시험을 수정하고 해당 suite만 재실행하여 14/14·24/24 PASS를 확인했다. 신규 모바일 시험도 단계 목록 모드에서 존재하지 않는 지도 노드를 기다리던 조건을 보완해 최종24/24 PASS를 확인했다. 중간 실패와 캡처는 work/v02a 및 outputs/v02a에 보존했다. [최초 전체 판정](v02a/initial-full-summary.json)을 성공으로 덮어쓰지 않았다. 제품 코드는 전체 회귀 시작 후 변경하지 않았다.

실제 HTTP는 명시적 로컬 모의 인증·실제 FastAPI·독립 worker·합성 PDF/HWPX를 사용한다. 신규 UI의 오류/지연/권한 조합은 실제 Chromium에 모의 HTTP 응답을 주입했다. 두 범위를 혼동하지 않는다. 관리자/직원/익명, 로딩/출처 확인/실패/미확인, 복수 근거, 늦은 응답, 의미 상태 위조 거부, 키보드·320/375/768/1440 화면을 검사했다.

## 화면

실제 HTTP 화면:

- [PC 홈](v02a/final-regression/actual-http/home-desktop.png) / [모바일 홈](v02a/final-regression/actual-http/home-mobile.png)
- [PC 업무지도](v02a/final-regression/actual-http/workflow-desktop.png)
- [모바일 지도](v02a/final-regression/actual-http/workflow-mobile-map.png) / [모바일 근거](v02a/final-regression/actual-http/workflow-mobile-evidence.png)

권한·상태 모의 HTTP 화면:

- [직원 모바일 홈](v02a/accepted-ui/home-reader-mobile.png)
- [키보드 선택 후 모바일 지도](v02a/accepted-ui/workflow-mobile-map.png) / [근거 패널](v02a/accepted-ui/workflow-mobile-evidence.png)

## 보존·보안·남은 범위

[보존·보안 검사](v02a/preservation-security.json): 기존 추적 파일405개 대조, 삭제0, 기존 fixture·원본·outputs 해시 보존, 백엔드/API/DB/잠금파일 변경 없음. 신규/수정 텍스트에 실제 키·토큰 패턴이 발견되지 않았으며 자료와 표시 이름은 합성이다. 자동 패턴 검사만으로 모든 민감정보의 부재를 증명한다고 주장하지 않는다. 외부 공급자 호출0회, 배포0회다.

실제 Supabase·LLM·임베딩, 의미 정확성, 운영 HTTPS, 스크린 리더, 한컴 시각 페이지 검증은 미실행이다. 모바일의 기존 헤더 버튼 줄바꿈과 작은 그래프 글씨 등 시각 개선은 이번 범위 밖이다. 출처 확인 상태는 서버의 새 영속 검증 상태가 아니라 현재 화면의 원문 재해결 결과이며 재방문하면 재확인한다. 원격 인증 설정 여부는 실제 연결 성공을 보장하지 않는다.

P0-2 문서 활성화 동선은 후속 개발 준비가 가능하다. 현재 활성화 UI가 없음을 정확히 안내했으며, 다음 단계에서는 기존 활성 버전 API·manager 권한·CSRF·버전 충돌 계약을 먼저 확인하고 별도 사용자 승인 범위로 구현해야 한다. 이번에는 활성화·승인·게시 UI를 추가하지 않았다.
