# Phase 2E-1 관리자 업무절차 후보·원문 검토

## 제공 범위

`#/workflows`는 기존 AuthContext의 server membership manager만 접근한다. 직원에게 탐색 메뉴/관리 작업을 제공하지 않으며 직접 주소 접근 시 권한 안내만 표시한다. 미로그인 사용자는 기존 로그인 화면을 사용한다. 기관/사용자 변경 시 화면 인스턴스를 새로 만들고 모든 API는 기존 서버 인증·기관·버전 검사를 통과해야 한다. 기본 실제 앱의 인증 공급자 미설정 차단을 변경하지 않았다.

같은 기관의 등록 문서와 현재 활성 버전을 선택한다. 비활성 버전은 표시하되 선택할 수 없다. 아직 후보가 없으면 문서 준비 상태를 확인하고 오프라인 추출 작업을 요청할 수 있다. 동일 입력은 기존 job을 반환하는 서버 계약을 사용하며, 클라이언트도 중복 제출 latch를 적용한다. queued/processing/completed/failed/cancelled, 최대 횟수·오류 분류·재시도 가능 여부를 실제 job 응답으로 표시하고 상태를1.5초 간격으로 조회한다. retryable 실패만 재시도 버튼을 제공한다.

job 목록 API는 없다. 따라서 새로고침 후 기존 완료 후보는 다시 조회할 수 있지만 진행 중 job ID를 자동 발견한다고 주장하지 않는다. 같은 입력의 작업 요청으로 기존 job ID/상태를 다시 받을 수 있다. 취소 작업 재개·관리자 승인·공식 게시·저장되는 수정은 제공하지 않는다.

## 지도·접근성

과거 설치/빌드 검증에 사용한 @xyflow/react 12.12.0을 apps/web에 정확 버전으로 추가했다. 기존 React/Vite/TS 및 기타 잠금 버전·integrity는 유지한다. npm이 제거한 기존 libc 플랫폼 메타데이터도 보존했다. 기본 화면 번들과 별도 lazy chunk로 지도 라이브러리를 로드한다. 기존 디자인 토큰·Button/PageTitle/StatusBadge·AuthContext를 재사용한다.

단계는 읽기 전용 노드이며 저장된 간선만 표시한다. 배치는 탐색용2열 격자이며 단계 목록의 표시/배치가 의미상 순서를 결정하지 않는다. 선후/필요 관계와 조건 분기를 선 종류로 구분하고 원문 문구에 있는 반려/보완/복귀/반복을 후보 명칭으로 표시한다. 문구 분류가 실제 의미 검증은 아니다. 표시 가능한 노드/조건 참조가 없는 간선은 만들거나 보정하지 않고 별도 관계 목록에 남긴다. 각 관계의 설명·조건 원문과 출발 단계 탐색을 제공한다.

확대·축소·전체 보기·pan/축소판 탐색과 항상 이용 가능한 단계 목록이 있다. 노드/목록은 native button으로 키보드 Enter/Space와 focus outline을 지원한다. 좁은 화면에서는 지도/근거 탭으로 전환하며 좌우 화살표/Home/End와 roving tabIndex를 지원한다. 모바일에서 단계 선택 후 근거 제목으로 focus를 옮긴다. 화면 폭320/375/768/1440,100노드의 명시적 합성 구조 응답으로 탐색을 시험했다. 스크린 리더/실사용자 평가는 별도다.

## 근거·검토·서식

후보 상세/ReviewIssue/서식 응답의 generation_id·job_id가 같아야 함께 표시한다. 선택 단계의 주장·기한 null, 연결 조건과 관계, 단계/조건/간선/업무/서식 범위에 해당하는 ReviewIssue를 연동한다. 검토 이유는 한국어 설명으로 표시하고 원래 코드는 펼쳐볼 수 있다.

EvidenceRef 목록은 현재 후보 endpoint에서 받고 기관/문서/버전·구조/의미 상태를 확인한다. 선택된 citation의 canonical chunk를 기존 서버 resolve endpoint에 POST하여 재해결한다. canonical EvidenceRef 전체와 원문 블록 scope를 대조하고 codepoint 기준 인용 범위/원문을 비교한 뒤에만 출처 확인 표시를 보여준다. 구조·출처 확인은 의미 정확성 인증이 아니다. React text rendering만 사용하며 문서 텍스트를 HTML/명령으로 실행하지 않는다.

PDF는 실제 page/bbox를 표시하고 원본 파일을 세션으로 받아 blob 링크의 #page 힌트를 제공한다. 별도 페이지 렌더 API가 있는 것처럼 동작하지 않는다. 페이지 이동은 브라우저 PDF 뷰어 지원에 따르며 native viewer 렌더 결과는 미검증이다. HWPX는 source block/구조화 텍스트와 part/xml_path/tag만 표시하고 한컴 시각 페이지·읽기 순서 미검증을 안내한다. 가짜 HWPX 페이지 이동/미리보기는 없다.

서식은 실제 CANDIDATES/UNLINKED/AMBIGUOUS/BLOCKED, 원문 목적·조건·현재 등록 파일 메타데이터를 표시한다. 파일 존재와 사용 필요성을 구별한다. required/selected_form_id=null, 의미 NOT_VERIFIED, 승인 NOT_REQUESTED를 유지하고 승인/공식 게시 버튼은 없다.

## API·경합 처리

기존9개 Workflow 경로를 모두 연결한다. prefix는 `/documents/{document_id}/versions/{version_id}/workflow`:

- POST /jobs, GET /jobs/{job_id}, POST /jobs/{job_id}/retry, POST /jobs/{job_id}/cancel
- GET /candidates, GET /candidates/{candidate_id}
- GET /review-issues?candidate_id=..., GET /form-links?candidate_id=...
- GET /candidates/{candidate_id}/evidence

기존 문서 list/detail/original 및 POST `/documents/{d}/versions/{v}/chunks/{chunk}/evidence/resolve`를 추가로 재사용한다. 백엔드 경로/응답/DB는 바꾸지 않았다. TypeScript DTO/런타임 guard는 실제 Pydantic/JSON Schema와 서버 생성 합성 응답에 맞춘다. 모의 시험 응답은 실제 API를 실행해 새로 생성하고 잘못된 상태/기관/세대 변형은 부정 시험에만 명시 주입한다.

same-origin session cookie, no-store, redirect:error 및 기존 authMemory CSRF를 사용한다. POST의 Origin은 브라우저가 전달하고 서버가 검사한다.401은 기존 세션 만료 이벤트로 보호 화면을 해제한다.403/404/409/500/503/네트워크·잘못된 응답은 후보를 초기화하고 구별해 안내한다. 정상404(완료 세대 없음)/빈 후보와 문서 권한/현재성 실패를 구별한다.

문서/버전/사용자 변경 시 controller·unmount·요청 순번으로 늦은 후보/상세/작업 응답을 폐기한다. PDF 원본의 늦은 응답도 unmount 이후 URL을 만들지 않으며 object URL은 revoke한다. 문서 목록/활성·원본 metadata는5초 주기 및 window focus에서 재확인하므로 변경 감지는 polling 지연이 있을 수 있다. 서버는 각 요청에서 별도로 현재성을 검사한다. Push 구독·job 목록·pagination API를 가정하지 않는다.

## 실제 검증과 재현

- npm ci --cache /tmp/sb-phase2e-npm-cache; npm run typecheck; npm run build (apps/web)
- `build_phase2e1_fixture.py --output <new.json>`: 실제 로컬 서비스/Workflow API에서 새 합성 HWPX/PDF·서식 응답 생성, 기존 원본/fixture 변경 없음.
- `check_phase2e1_ui.cjs <new-report.json> <fixture.json>`: 프로덕션 번들 Chromium, 로컬 API 응답 가로채기 기반 정상/경합/보안/레이아웃 시험. 실제 모델 의미 품질 시험은 아님.
- 기존 check_stage2_ui / check_stage3_home / check_stage4a_ui / check_stage4b2_ui: 총43개 기존 UI 회귀.
- `check_phase2e1_live.cjs <new-report.json>`: 응답 가로채기 없이 loopback FastAPI와 실제 BFF session·CSRF·독립 worker를 사용한 통합. 명시적 MockSupabaseTransport와 합성 로컬 멤버십이며 실제 Supabase가 아니다. 테스트만 기존 secure_cookie=False loopback 옵션을 사용한다. 운영 기본 Secure 쿠키는 변경하지 않았다. harness는 `--synthetic-loopback-test` 명시와 임의 loopback 포트만 사용하고 종료 시 자신이 시작한 worker/server를 정리한다. 운영/공개 배포용 경로가 아니다.
- Phase Gate: 기존 비루프백 DNS/TCP guard runner의 전체409개 backend를 새 실행했다.

Playwright 모듈/Chromium 경로는 검증 환경의 PLAYWRIGHT_MODULE_DIR/BROWSER_EXECUTABLE을 사용한다. 모든 증거는 새 파일명으로 생성하며 기존 파일이 있으면 중단한다. 상세 결과·스크린샷·실행 시간은 outputs/PHASE2E1_REPORT.md에 기록한다.

## 남은 범위

실제 Supabase/모델/유료 API, 관리자 수정/승인·게시, HWPX 작성·한컴 시각 위치, native PDF renderer, 스크린 리더/사용자 평가·운영 HTTPS·대규모 실문서/대량 Edge 레이아웃은 미검증이다.100노드 시험은 UI 탐색만 검증한 합성 구조이며 업무 발견 일반화를 증명하지 않는다. 서버의 재파싱 비용과 client 전체 목록 수신 때문에 더 큰 corpus에는 pagination/성능 계약이 필요하다.2E-2는 별도 사용자 승인 후 근거 검토 UX/접근성·성능 보강 범위를 정해야 하며 이번에는 착수하지 않는다.
