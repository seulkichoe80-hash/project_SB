# 서무ITDA v0.2-B 완료 보고

2026-10-18 KST. Feature Gate: 문서 등록·처리·명시적 활성화·업무절차 후보 검토 동선을 구현했다. 다음 단계는 시작하지 않았다.

## Git·보존

시작 시 feat/v02a-ui-clarity의 HEAD는 `809a2dd3599bb9d0d1610f13a2d1bc439d30d9ef`이고 미커밋 변경은 없었다. 사용자의 앞선 저장 요청으로 이미 안전하게 커밋된 v0.2-A를 재커밋하지 않고 보존했다. 그 커밋에서 `feat/v02b-document-flow`를 생성했다. v0.2-B는 검토용 미커밋 변경 상태이며 신규 커밋·원격 push·merge·태그·배포는 하지 않았다. 로컬 main 브랜치는 없으며 origin/main 참조는 8986b912다. main 직접 변경은 하지 않았다.

[보존 검사](v02b/preservation-security.json): 기존 추적 파일459개를 시작 SHA-256과 비교했다. 누락0, 기존 fixture·원본·과거 outputs 변경0, backend/API/DB/의존성·lockfile 변경0이다. 수정/신규 텍스트의 실제 비밀키 패턴 검출0이며 새 화면·시험 데이터는 합성 자료다. 패턴 검사를 모든 비밀정보의 부재에 대한 증명으로 해석하지 않는다.

## 구현한 흐름

1. 공개·합성 PDF/HWPX 등록 후 반환 문서·버전을 상세 API로 다시 조회하고 바로 연다.
2. 문서 상세 맨 앞 ‘다음 작업’에서 등록·원문 처리·파싱·청킹·활성 버전을 확인한다. ID·해시 등은 접힌 ‘문서 상세 정보’로 옮겼다.
3. 미완료·실패·미확인 상태에서는 활성화 준비 완료로 표시하지 않는다. 원문 추출/청킹 실패는 해당 재시도, 진행 중은 명시적 새로고침을 제공한다.
4. 청킹 요청의 멱등 응답으로 작업 ID를 얻고 실제 완료와 parse job/attempt·버전 연결을 확인한다.
5. 관리자만 ‘이 버전 활성화’를 누를 수 있다. 확인창에 대상 문서·버전, 기존 활성 버전, 영향, 원본 보존 및 공식 승인과의 차이를 표시한다.
6. 확인 시 detail/parsing/chunk/list를 다시 조회하여 상태·해시·revision·활성 버전 변경을 비교한다. 실제 활성화 POST 뒤에도 detail/list를 다시 조회한다.
7. 현재 활성 버전에는 재활성화 버튼 대신 ‘업무절차 후보 검토’ 링크를 제공한다. 정확한 문서·버전을 서버 반환 목록에서 확인한 후 기존 Workflow 화면을 연다. 추출 작업은 별도로 명시적 요청해야 한다.

reader는 조회·원본 다운로드·상태 확인만 가능하며 처리·활성화·관리자 후보 검토 버튼이 없다. 서버도 reader의 활성화와 작업 생성을 403으로 거부한다. 기본 deny-all 및 기존 인증·쿠키·CSRF/Origin 계약은 유지했다.

## 실패·경합·재개

409는 문서·처리 상태 변경 또는 충돌로 안내하고 다시 확인하도록 한다. 403/404는 이전 상세를 제거하며, 네트워크/5xx/사후 조회 실패는 성공으로 표시하지 않는다. 응답을 잃은 경우 서버가 이미 활성화했을 수 있으므로 재조회 전 성공/롤백을 단정하지 않는다. 중복 확인은 latch와 비활성 버튼으로 차단한다. 문서/버전/사용자/기관/역할·페이지 전환에서는 이전 결과를 폐기하고 가능한 요청을 취소한다. 취소가 이미 실행된 서버 변경을 되돌리는 것은 아니다.

기존 활성화 API에는 expected-active-version/If-Match 비교 후 교환 기능이 없다. 사전 조회 이후 POST 사이에 다른 관리자가 활성화하는 경쟁까지 원자적으로 잠그지는 못한다. API 변경 없이 사전 비교와 사후 조회로 보완했고, 이 서버 계약의 한계는 남겨 두었다.

청킹 작업 목록 API도 없다. 상세 재방문 때 작업 ID가 없으면 ‘미확인’으로 표시한다. 비활성 버전의 ‘청킹 요청·상태 확인’은 기존 기본 설정 작업을 복구하거나, 없으면 실제 작업을 등록한다. 이미 활성화된 자료는 서버 활성 상태를 바탕으로 검토 화면 이동을 제공하고, Workflow API가 실제 현행 입력/세대 조건을 재검증한다. 민감정보·원문·인증정보를 browser storage에 저장하지 않는다.

## 실행 결과

| 검사 | 이번 최종 결과 |
|---|---|
| TypeScript | PASS |
| 프로덕션 빌드 | PASS |
| 신규 v0.2-B UI | 26 PASS / 0 FAIL |
| 기존 UI | 128 PASS / 0 FAIL (v0.1 104 + v0.2-A 24) |
| 전체 백엔드 | 409 PASS / 0 FAIL / 0 SKIP / 0 BLOCKED |
| 새 실제 HTTP 동선 | 14 PASS / 0 FAIL |
| 기존 v0.1 HTTP 회귀 | 13 PASS / 0 FAIL (새 동선과 겹치므로 합산하지 않음) |

[최종 실행 인덱스](v02b/verification.json)에 원본 결과 경로·소스 해시·명령·시간을 기록했다. 기존 설치 환경(Python3.12.14/Node24.19.0/npm11.9.0/Chromium154)을 재사용했으며 설치 스크립트·환경 설정·패키지 변경은 없었다. 타입·빌드와 기존 전체 runner를 새 실행했고, 신규 UI/실제 HTTP도 별도로 새 실행했다. 전체 runner는121.645초, backend는117.422초였다(병렬이므로 합산하지 않는다). 총 작업시간 약10분.

실제 HTTP 시험은 route mock 없이 Chromium→실제 FastAPI BFF→SQLite→독립 parse/chunk/workflow worker를 사용했다. PDF/HWPX 등록, 파싱/청킹, 확인창 활성화, 사후 조회, 정확한 문서·버전 이동, 지도·EvidenceRef·서식·ReviewIssue·원본 해시, CSRF/허용되지 않은 Origin/기관/reader 차단을 검증했다. 원문 worker를 잠시 정지한 미완료 버전의 직접 활성화409 및 UI 차단, 기존 v1을 명시한 v2 교체 확인창, 기존 원본 해시 보존도 실제 HTTP로 검증했다. 지연·5xx·응답 유실·잘못된 주소·버전/세대 불일치 조합은 별도 모의 HTTP UI 시험으로 구별한다.

최초 실제 HTTP 시험은 새 Workflow 이동 뒤 문서 목록 화면으로 돌아오지 않은 시험 동선 때문에 4 PASS/1 FAIL이었다. 시험 내 명시적 화면 이동 후 재실행했다. 최초 기존 문서 UI는 모의 로그인 기관A와 자료 응답test-org의 불일치가 새 기관 검사에 차단돼 9 PASS/8 FAIL이었다. 모의 응답을 같은 기관으로 맞추고 parse linkage를 실제 계약에 맞춰 명시했다. 접힌 상세를 펼치는 시험 동작 및 내용 검증 안내 기대값도 갱신했으며, fixture 파일은 수정하지 않았다. 해당17개는 최종 소스에서 재실행하여 전부 PASS다. [최초 전체 결과](v02b/initial-full-summary.json)와 [최초 HTTP 실패](v02b/initial-http-results.json)를 보존했다. 후반 상세 배치·안내 문구 변경 뒤에는 영향받는 문서17개와 실제 HTTP14개를 다시 실행했다. 백엔드 및 나머지 UI 기능은 그 사이 변경되지 않았다.

## Chromium 화면

실제 HTTP·합성 로컬 인증:

- [PC 활성화 완료와 검토 이동](v02b/http-current/activated-hwpx-desktop.png)
- [PC 문서 상세](v02b/http-current/documents-desktop.png) / [모바일 문서 상세](v02b/http-current/documents-mobile.png)
- [기존 활성 v1을 보여주는 v2 확인창](v02b/http-current/replace-version-confirmation.png)
- [PC 업무지도](v02b/http-current/workflow-desktop.png) / [모바일 근거](v02b/http-current/workflow-mobile-evidence.png)

모의 HTTP 상태·오류 시험의 실제 Chromium:

- [모바일 활성화 확인창](v02b/ui-verified/activation-mobile.png)

320/375/768에서 핵심 버튼·확인창의 가로 넘침과 키보드 취소·포커스를 확인했다. 문서 목록은 기존 가로 스크롤 표를 유지하며, 상세의 핵심 행동은 가로 스크롤 없이 사용한다. 스크린 리더·실제 모바일 기기·전체 WCAG 적합성은 검증하지 않았다.

## 변경 파일

제품7개:

- `apps/web/src/App.tsx`: 쿼리 포함 hash 라우트 처리, URL/역할 전환 시 화면 scope 격리.
- `apps/web/src/api/documents.ts`: 기존 activate 요청과 취소 signal, job 연결 필드 타입.
- `apps/web/src/components/DocumentFlow.tsx`: 상태 기반 다음 행동·확인창·사전/사후 조회·오류·중복/늦은 응답 처리(신규).
- `apps/web/src/pages/DocumentsPage.tsx`: 등록 후 상세 연결·기관 검사·flow 배치·기술 상세 접기.
- `apps/web/src/pages/HomePage.tsx`: 활성화 미제공 안내를 실제 동선으로 갱신.
- `apps/web/src/pages/WorkflowPage.tsx`: 전달 문서/버전의 서버 현재성 확인과 잘못된 주소 차단.
- `apps/web/src/styles/documents.css`: 다음 작업·모바일 버튼 배치.

시험: 신규 `check_v02b_ui.cjs`, `check_v02b_http.cjs`; 기존 `check_stage4a_ui.cjs`의 올바른 기관·연결 메타데이터/상세 펼침/문구 기대값, `check_v01_e2e.cjs`의 과거 전용 안내 문장 정정. 모두 `scripts/validation/` 아래다.

문서·증거: `TASKS.md`, `TEST_PLAN.md`, `docs/V02B_DOCUMENT_FLOW.md`, 본 보고서, `outputs/v02b/` 신규 JSON·캡처. 과거 보고서와 fixture는 그대로다.

## 남은 위험·권고

- 서버 비교 후 교환 부재에 따른 동시 관리자 경합은 위 한계를 유지한다. 개선은 후속 API 계약 변경 범위로 별도 승인해야 한다.
- 작업 상태는 명시적 새로고침이며, worker가 실행되지 않으면 실제 queued 상태를 완료로 바꾸지 않는다.
- 새 버전 업로드 UI·서식 카탈로그 등록·공식 승인/게시·실제 Supabase/LLM/임베딩·공개 배포는 추가하지 않았다. 실제 외부 공급자 호출0회다.
- 다음 개발 후보는 여러 관리자의 버전 교체 정책·현재 버전 충돌 안내 보강과 사용성 점검이다. 이번 변경 검토·저장 후 별도 요청으로 결정하며 자동 진행하지 않는다.
