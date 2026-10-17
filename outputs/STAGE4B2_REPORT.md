# Stage4B-2 로컬 인증·기관 권한 완료 보고

## 완료 범위

로컬 계약 Feature Gate 완료. IdentityProviderAdapter·SupabaseProviderAdapter(mock 전송 전용)·FastAPI BFF 세션·HttpOnly/Secure cookie·단회 login CSRF/Origin·session CSRF·login/logout/me·기관 관리자 멤버십 관리 구현. 실제 Supabase/유료자원/LLM/배포0. 기본 앱은 공급자 미설정으로 보호 API401/로그인503이며 모의 계정·권한을 자동 주입하지 않는다.

신규: apps/api/identity_provider.py, auth_store.py, auth.py; apps/web/src/auth/AuthContext.tsx; tests/test_auth.py; scripts/validation/check_stage4b2_ui.cjs; docs/STAGE4B2_AUTH.md.
수정: apps/api/main.py; apps/web/src/main.tsx, App.tsx, components/AppLayout.tsx, pages/DocumentsPage.tsx, api/documents.ts; 기존UI 검증3개; TASKS/ARCHITECTURE/TEST_PLAN 관련절. PRD/원본·파서·chunk/검색·EvidenceRef schema/기존 테스트 fixture는 변경하지 않았다.

## 데이터·API·UI

추가 DB: identities/organizations/memberships/sessions/auth_challenges/auth_audit_events/auth_login_limits. 기존 schema 파괴/삭제 없음. migration 이전 runtime/auth-backups에 SQLite 백업, 기존문서·버전·blocks/작업행과 원본hash 유지·별도파일복원 시험 PASS. 기존 개발 runtime의 metadata DB도 앱 import시 additive migration 대상이며 backup을 생성한다. 이 원칙을 사용자 원본 파일 변경과 구별한다.

API: GET /auth/status, POST /auth/csrf, POST /auth/login, GET /auth/me, POST /auth/logout, GET /auth/memberships, PATCH /auth/memberships/{user_id}. login body는 email/password 이외 필드를 거부한다. 모든 기존 보호 경로는 같은 session principal 검사와 기관 필터를 사용한다. reader mutation403, 다른기관 객체404, 계정·기관·멤버십 정지는 다음요청부터401. 기관관리자 capability와 reader/manager는 분리하고 worker는 브라우저로 발급하지 않는다.

React 로그인/상태확인/로그아웃/만료·기관/권한표시·reader 작업 비활성화를 구현했다. 로그인 전 보호 페이지와 자료요청 비노출. 개인정보/파일명 React escape 유지, 비밀번호·provider token의 local/sessionStorage 저장 없음. CSRF만 메모리에 보관한다. 401 수신 시 세션 메모리와 보호 화면을 제거한다. 인증상태 전환 시 제목 포커스 회귀도 수정했다.

## 실제 실행

| 시험/명령 | 결과 |
|---|---|
| python -B scripts/validation/run_phase2b_checks.py --output work/stage4b2/VALIDATION_FINAL.json | **153 PASS / 0 FAIL / 0 SKIP / 0 BLOCKED**, 64.227초 (기존123+신규30) |
| npm-cli.js run typecheck --prefix apps/web | PASS |
| npm-cli.js run build --prefix apps/web | PASS, 최종 bundling137ms |
| node scripts/validation/check_stage4b2_ui.cjs work/stage4b2/ui-final/RESULT.json | 신규6 PASS |
| 기존 check_stage2_ui / check_stage3_home / check_stage4a_ui | **36 PASS / 0 FAIL / 1 BLOCKED** |
| node work/stage4b2/live.cjs | 실제 Chrome→Vite→FastAPI 로컬BFF 시나리오 PASS, 3.168초 |

브라우저 신규6+기존36=42 PASS. 타입/빌드2 및 별도 실제HTTP 시나리오1을 포함한 실행 단위 집계198 PASS /0 FAIL /0 SKIP /1 BLOCKED. 단위 분모가 다르므로 backend153과 UI42를 별도로 해석한다. BLOCKED는 이전부터의 Chrome 다운로드 저장권한이다. 이번 auth 기능의 실패가 아니며 다운로드 저장을 PASS로 바꾸지 않았다.

local HTTP 시험은 **명시 mock Supabase transport**를 주입한 독립 work DB, loopback 한정 secure_cookie=False 개발용 설정이다. 실제 cookie HttpOnly/JS비노출·CSRF/Origin·기관표시·웹저장소 미사용·reload 유지·logout 후실제401을 확인했다. 생산용 default Secure=true는 TestClient HTTPS scheme에서 헤더/정책을 확인했으며 실제TLS 배포 검증이 아니다. 기존 mock principal override 테스트와 새 session 검증을 구별한다. 문서/원본/작업/검색/유효 EvidenceRef의 타기관 차단, 활성 B기관 corpus가 A기관 검색에 나오지 않음, 원본hash 일치도 새 session 시험으로 확인했다.

## 재시도·제약

초기 변경 전 baseline 명령은 네트워크 권한 전60초 timeout으로 완료하지 못했다. 이후 기존123개를 다시 실행해 PASS 기록을 남겼다. migration backup 연결 미종료에 따른 Windows 임시파일 잠김2건은 close 수정 후 해소했다. UI 제목포커스1건은 auth전환 useLayoutEffect로 고치고 재실행했다. 초기 실패/중간 기록은 work/stage4b2에 보존했다. 최종153 입력 source hash와 시험기록은 BACKEND_FINAL.json이다.

실제 원격 transport·gateway apikey·JWT 서명/JWKS/issuer/audience 회전·provider logout/ban sync·초대/복구/MFA·refresh는 미구현/미검증이다. 토큰을 보관하지 않아 로컬 세션 만료 후 재로그인이 필요하다. 현재 active membership이 정확히1개여야 하며 복수는403으로 fail closed, 기관전환 UI 없음. 단순 mock이 실제 Supabase 사용자 검증·네트워크 가용성 통과를 뜻하지 않는다. 외부 DB/시크릿·감사보존·TLS/CORS 운영 검증 전 공개 운영 불가.

## 보존·다음 단계

시작222개 파일 중 변경은 위 승인범위만이고 기존 output/fixture/schema/사용자 원본은 hash 동일·삭제0. 변경전 사본/hash/Git diff: work/stage4b2/before 및 CHANGES.diff. 기존 미커밋 변경을 초기화하지 않았다. HEAD `f9a01d8c5b6b2b2311f4d8d8461b0f5b55b7a182` 유지. commit/push/merge/배포 없음. API key/실토큰/실비밀번호를 기록하지 않았다. 테스트의 synthetic credential은 실제 계정과 무관하다. local 검증 자식 서버는 종료했다.

Stage4B-3의 **로컬 기반은 준비**됐다. 다음 승인에서 공급자 프로젝트/리전/테스트 계정/키설정·remote transport·선택flow JWT 검증·세션 lifecycle·한도/사용량 범위를 확정해야 한다. 키만 넣으면 바로 연결되는 완성된 원격 adapter라고 보고하지 않는다. 실제 외부 인증은 이번에 진행하지 않았다.

경과시간 보고기록까지 14.66분. 최종 backend64.227초, UI합계11.048초, 실제BFF3.168초. 모든 재시도/추론/도구시간의 완전 분리는 미측정이며 절감률을 제시하지 않는다.

[계약](../docs/STAGE4B2_AUTH.md) · [backend](stage4b2/BACKEND_FINAL.json) · [기존123](stage4b2/EXISTING_123.json) · [auth UI](stage4b2/AUTH_UI.json) · [실제 local BFF](stage4b2/LIVE_BFF.json) · [보존·시간](stage4b2/METRICS_PRESERVATION.json) · [Git](stage4b2/GIT_STATUS.txt) · [로그인 캡처](stage4b2/login.png)
