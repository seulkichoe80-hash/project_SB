# 서무ITDA v0.1 — 오프라인 통합 기준본

작성 2026-10-18T09:43:25.527123+09:00. 이번 완료는 기존 오프라인 기능을 통합·보존한 검토 기준본 확보다. 신규 제품 기능·UI 전면 개편·운영용 인증·DB 변경은 없다. G1 C/D 또는 실제 AI·공개 서비스의 완료를 뜻하지 않는다. 다음 개발은 자동 시작하지 않는다.

## 통합 기능과 실제 E2E

합성 관리자 로그인 → 업무 홈 → PDF/HWPX **브라우저 업로드** → 독립 parse worker → UI 청킹 요청/독립 chunk worker → 기존 HTTP activate → 후보 추출 요청 → 독립 workflow worker → React Flow → 단계 선택 → canonical EvidenceRef 재해결 → ReviewIssue/단일·미등록·동명 서식 → 로그아웃 후 원본·후보 HTTP401을 실제 HTTP로 확인했다. 네트워크 응답 가로채기나 auth dependency override를 쓰지 않았다.

별도 실제 HTTP 음성 시험으로 표준 앱 deny-all401·미설정 공급자 상태, CSRF403, 타기관404, reader 작업403, 완료 작업 retry409, 위조 인용 거부, 새 비활성 버전/구버전의 후보 조회 거부와 원본 SHA 보존을 확인했다. workflow worker를 정지한 상태의 queued 작업을 새로고침/멱등 재요청하고 새 독립 프로세스로 완료했다. processing lease 만료·실패 재시도·롤백·서버 재시작은 전체 backend의 별도 회귀로 구분한다.

활성화 UI와 서식 카탈로그 등록 UI/API는 없다. 활성화는 **기존 HTTP API**, 서식 세 개는 **검증 전용 Python 사전 준비**를 썼다. 작업 ID 재확인은 기존 멱등 POST를 사용하므로 작업이 없으면 새 작업이 생길 수 있다. 작업 목록을 만들거나 취소 재개 기능을 추가하지 않았다. mock 신원은 명시적 loopback 하네스에서만 제공하며 표준 앱 인증 기본값은 바꾸지 않았다.

## 이번에 새로 실행한 검증

| 검사 | 결과 | 범위 |
| --- | --- | --- |
| 전체 backend |409 PASS / FAIL0 / SKIP0 / BLOCKED0|기존 unittest 전체 discover·비루프백 DNS/TCP guard|
| 전체 UI |104 PASS / FAIL0|14+6+17+6+37+24; production Chromium·합성 응답/SSR|
| 실제 HTTP E2E |13 PASS / FAIL0|기본 차단·인증/업로드부터 worker·지도/근거·권한·로그아웃|
| 새로 설치한 Playwright의 E2E |13 PASS / FAIL0|같은13개 재실행; 중복 합산하지 않음|
| 타입 검사·프로덕션 빌드 |PASS / PASS|frozen npm ci 이후 tsc/Vite|
| Python 설치 명령·pip check |PASS|기존 venv에서 만족 확인; 새 OS 설치 실증으로 확대하지 않음|

최종 runner 전체 118.762초, backend 114.441초, 실제 HTTP 18.568초. 명령·suite 종료 코드·입력 SHA는 [summary](v01/validation/summary.json), 전체 test ID와 로그는 [backend](v01/validation/backend.json), [UI](v01/validation/ui.json), 실제 HTTP 요청 상태/원본 해시는 [E2E](v01/validation/e2e-http.json)를 따른다. [핵심 안전성 시험 인덱스](v01/validation/safety-test-index.json)를 함께 보존했다. 모든 최종 suite 종료 코드0이며 과거 PASS로 대체하지 않았다.

초기 통합 하네스 실패도 work/v01/e2e-attempt1~3와 attempt 캡처에 보존했다. Chromium의 response body inspector cache 유실은 기존 GET/멱등 POST 재확인으로 관찰하고, 탭 locator를 실제 이름에 맞추고, 새 버전 PDF의 EOF 뒤 주석으로 인한 정당한415 거부는 별도의 유효 합성 PDF로 고쳤다. 제품 코드는 수정하지 않았다. 최종 판정은 full/ 및 e2e-reproduced/ 결과만 사용한다.

## 시연 자료

[설치·실행·약4분 시연·개선 순위](../docs/V01_DEMO.md). 합성 파일6개와 manifest는 [대표 자료](../tests/fixtures/synthetic/v01)에 있다. PDF2개는 프로젝트 자체 ASCII 생성물이며 폰트 파일이 포함되지 않은 것을 검토하여 명시적으로 Git 보존한다. 기존 사용자 원본이 아니다. HWPX 재생성 시 package timestamp 때문에 byte 고정을 약속하지 않으며 저장된 파일은 manifest 해시로 확인한다.

아래 화면은 **실제 HTTP** 최종 실행의 PC/모바일 캡처다.

- [업무 홈 PC](v01/final/actual-http/home-desktop.png) / [모바일](v01/final/actual-http/home-mobile.png)
- [문서 관리 PC](v01/final/actual-http/documents-desktop.png) / [모바일](v01/final/actual-http/documents-mobile.png)
- [업무지도 PC](v01/final/actual-http/workflow-desktop.png)
- [모바일 지도](v01/final/actual-http/workflow-mobile-map.png) / [모바일 원문](v01/final/actual-http/workflow-mobile-evidence.png)

## 보존·보안·Git

2E-2A 변경33개는 로컬 `050349febe300a3563819d9e2309ce4d42c743b4`에 보존했다. 시작 시 추적 파일318개와 별도2E-2A 사본의 SHA를 검사하고 기존 원본·fixture·과거 증거 삭제0을 확인했다. README/TASKS/TEST_PLAN의 승인된 기준 문서 갱신은 diff로 구분한다. 새로운 demo fixture는 synthetic6개뿐이다. 앱·백엔드·기존 테스트·기존 lockfile은 이 기준점 이후 변경하지 않았다.

2E-2A 보존 시점에 origin/main `40badd6d3553b9d46ff01edb144d02cdb76b22ce` 이후 공개 예정 이력 blob150개의 고신뢰 비밀키 패턴 탐지0을 확인했다. v0.1 신규/변경 파일은 커밋 전, 최종 이력은 push 전에 다시 검사한다. 새 파일/합성 HWPX XML·메타데이터·PDF도 별도 검사한다. 검사 결과는 [보존·보안 기록](v01/validation/security-preservation.json)에 있다. 패턴 검사는 모든 개인정보 검출을 보장하지 않는다. 실제 자료/키/계정은 등록하지 않았다.

Python guard probe PASS, backend 차단된 외부 시도0, 실제 HTTP 서버/worker 차단된 외부 시도0, 브라우저 예상 밖 외부 목적지0·JS exception0, 실제 Supabase/LLM/임베딩 호출0이다. npm/Python 검증 도구 설치의 registry 접근은 공급자 호출과 구별한다.

기준 브랜치는 feat/phase2d-offline-extraction이다. 이 보고와 검증물·시연 자료를 v0.1 기준 커밋으로 보존한 뒤 해당 브랜치만 일반 push하고 main 대상 PR을 시도한다. 보고는 커밋 직전 작성되므로 최종 커밋 SHA/원격 ref/PR URL은 완료 응답과 GitHub PR 메타데이터가 기준이다. main 직접 변경·force push·자동 merge·배포는 하지 않는다.

## 미검증 경계와 내일 우선순위

실제 Supabase 원격 로그인·실제 AI/임베딩·사람의 의미 검토·최종 승인/게시·HWPX 자동 작성·클라우드 배포는 미구현/미검증이다. Windows/새 Cloud·완전 고정된 OS/브라우저 독립 재현, native PDF/한컴 시각 페이지·스크린 리더·실기기 장기 성능도 미검증이다. React 지도 배치는 실제 업무 순서의 의미 인증이 아니다. semantic_verification=NOT_VERIFIED/승인 NOT_REQUESTED를 유지한다.

내일 우선순위: (1) 사용자 시연 후 수정 요청 수집, (2) 홈의 이전 단계 안내 문구·활성화/서식 등록/작업 찾기 동선 합의, (3) 공개 자료 골드셋·담당자 의미 검토 기준, (4) 새 환경·접근성·긴 문서 성능. 실제 공급자 연결/배포는 별도 데이터·예산·보안 승인 후 검토한다. 이번 작업에서는 착수하지 않았다.

보고 생성까지 보존 시작 기준 약 11.5분. 최종 Git 보존·PR 확인 시간은 완료 응답에 별도 반영한다.

## v0.1 추가 변경 파일

- `README.md`
- `TASKS.md`
- `TEST_PLAN.md`
- `docs/V01_DEMO.md`
- `outputs/V01_REPORT.md`
- `outputs/v01/attempt1/home-desktop.png`
- `outputs/v01/attempt1/home-mobile.png`
- `outputs/v01/attempt2/documents-desktop.png`
- `outputs/v01/attempt2/documents-mobile.png`
- `outputs/v01/attempt2/home-desktop.png`
- `outputs/v01/attempt2/home-mobile.png`
- `outputs/v01/attempt2/workflow-desktop.png`
- `outputs/v01/attempt2/workflow-mobile-evidence.png`
- `outputs/v01/attempt3/documents-desktop.png`
- `outputs/v01/attempt3/documents-mobile.png`
- `outputs/v01/attempt3/home-desktop.png`
- `outputs/v01/attempt3/home-mobile.png`
- `outputs/v01/attempt3/workflow-desktop.png`
- `outputs/v01/attempt3/workflow-mobile-evidence.png`
- `outputs/v01/attempt3/workflow-mobile-map.png`
- `outputs/v01/attempt4/documents-desktop.png`
- `outputs/v01/attempt4/documents-mobile.png`
- `outputs/v01/attempt4/home-desktop.png`
- `outputs/v01/attempt4/home-mobile.png`
- `outputs/v01/attempt4/workflow-desktop.png`
- `outputs/v01/attempt4/workflow-mobile-evidence.png`
- `outputs/v01/attempt4/workflow-mobile-map.png`
- `outputs/v01/final/actual-http/documents-desktop.png`
- `outputs/v01/final/actual-http/documents-mobile.png`
- `outputs/v01/final/actual-http/home-desktop.png`
- `outputs/v01/final/actual-http/home-mobile.png`
- `outputs/v01/final/actual-http/workflow-desktop.png`
- `outputs/v01/final/actual-http/workflow-mobile-evidence.png`
- `outputs/v01/final/actual-http/workflow-mobile-map.png`
- `outputs/v01/final/workflow-regression/workflow-desktop.png`
- `outputs/v01/final/workflow-regression/workflow-mobile-evidence.png`
- `outputs/v01/final/workflow-regression/workflow-mobile-map.png`
- `outputs/v01/reproduced/documents-desktop.png`
- `outputs/v01/reproduced/documents-mobile.png`
- `outputs/v01/reproduced/home-desktop.png`
- `outputs/v01/reproduced/home-mobile.png`
- `outputs/v01/reproduced/workflow-desktop.png`
- `outputs/v01/reproduced/workflow-mobile-evidence.png`
- `outputs/v01/reproduced/workflow-mobile-map.png`
- `outputs/v01/validation/backend.json`
- `outputs/v01/validation/backend.network.json`
- `outputs/v01/validation/e2e-http.json`
- `outputs/v01/validation/e2e-installed-tools.json`
- `outputs/v01/validation/safety-test-index.json`
- `outputs/v01/validation/security-preservation.json`
- `outputs/v01/validation/summary.json`
- `outputs/v01/validation/ui.json`
- `scripts/validation/build_v01_assets.py`
- `scripts/validation/check_v01_e2e.cjs`
- `scripts/validation/run_v01_checks.py`
- `scripts/validation/v01_demo_server.py`
- `tests/fixtures/synthetic/v01/manifest.json`
- `tests/fixtures/synthetic/v01/v01-manual-v2.pdf`
- `tests/fixtures/synthetic/v01/v01-manual.pdf`

기존 2E-2A 보존33개는 050349f 커밋의 파일 목록을 따른다. 중간 캡처도 삭제하지 않았으며 최종 final/actual-http를 사용한다.
