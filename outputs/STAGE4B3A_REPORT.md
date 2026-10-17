# Stage 4B-3A 구현·Feature Gate 보고

2026-10-17, Linux x86_64/Python3.12.14/Node24.19.0/npm11.9.0. 사용자 승인 범위는 원격 전송 계층 구현과 모의 HTTP 시험이며, 실제 공급자 호출은 제외했다. 공식 계약 확인·구현·검증·보고 측정 경과는 약8분이다.

## 구현

`IdentityProviderAdapter`와 `SupabaseProviderAdapter`를 유지하고 `SupabaseHTTPTransport` 및 서버 전용 `SupabaseSettings`를 추가했다. 고정 HTTPS 프로젝트/두 endpoint만 사용하며 apikey는 서버 request header에만 들어간다. client TLS/proxy/CA 검증 유지, redirect/retry 없음, timeout·64KiB JSON·압축응답 거부·오류본문 비노출·연결/cookie 폐기를 적용했다. runtime 요구사항에 기존 lock과 같은 httpx0.28.1을 명시했다.

검증 방식은 password token 교환 후 같은 프로젝트의 GET /auth/v1/user다. 로컬 JWT decode를 신원으로 사용하지 않는다. 사용자 UUID/aud/token 응답 subject 일치/만료/익명·정지·삭제 상태를 검사하고 권한은 기존 local active identity·organization·membership으로 결정한다. BFF HttpOnly/Secure cookie·CSRF/Origin·로그아웃 revoke를 유지하며 provider token/비밀번호를 브라우저나 DB에 저장하지 않는다. 실패는 고정 ProviderUnavailable/BFF503으로 차단한다.

`create_app(..., supabase_settings=...)`의 명시 설정 경로와 기존 provider 주입 경로를 지원하며 동시 설정은 거부한다. 구성·시작만으로 호출하지 않는다. 기본 `apps.api.main:app`은 환경변수로 자동 활성화되지 않으며 기존 deny-all을 유지한다. `/auth/status`의 remote_enabled는 HTTP 계층 구성 여부이며 네트워크 성공 판정이 아니다.

공식 Supabase Auth OpenAPI의 고정 commit·파일 hash·호환 범위와 구현 한계는 [계약](../docs/STAGE4B3A_SUPABASE_TRANSPORT.md)에 기록했다. 공식 공개 소스 열람과 Git read는 수행했지만 실제 Supabase 프로젝트/API에는 접속하지 않았다.

## 이번 실행 결과

| 검증 | 결과 |
|---|---|
| 전체 backend: `.venv/bin/python scripts/validation/run_stage4b3a_checks.py --output work/stage4b3a/backend-final.json` | **205 PASS /0 FAIL /0 SKIP /0 BLOCKED**, runner31.664초/시험30.818초; 기존153 + 신규52(기존 BFF30개를 새 HTTP mock 경로로 재사용 포함) |
| 네트워크 가드 | DNS/TCP 비루프백 차단 probe PASS; 본 시험 외부 연결 시도0, 실제 공급자 호출0 |
| `npm run typecheck`, apps/web | PASS, 1.060초 |
| `npm run build`, apps/web | PASS, 1.243초 |
| check_stage2_ui / check_stage3_home / check_stage4a_ui / check_stage4b2_ui | 각각14/6/17/6 PASS, 합계 **43 PASS /0 FAIL /0 BLOCKED** |
| 프런트 typecheck/build + 브라우저 전체 실행 경과 | 15.196초 |
| `.venv/bin/python -m pip check`, `git diff --check` | PASS |

새 HTTP 시험은 유효 요청 serialization·서버 apikey/토큰 header·설정/URL/키 거부·redirect/400/401/403/404/422/429/5xx·timeout/연결/프로토콜 오류·JSON/응답형식/크기/압축·위조/만료 신원·TTL·credential 로그/응답/DB 비노출을 확인했다. 기존 BFF30개를 새 HTTP MockTransport 경로로 모두 재사용하여 CSRF/Origin·reader/manager·inactive 계정/기관/멤버십·기관 간 문서/검색/EvidenceRef·세션 revoke/logout/replay 등을 재검증했다. 추가로 로그인 전 비활성 상태·CSRF 실패 시 provider 무호출을 확인했다.

모든 새 provider 요청은 httpx.MockTransport를 사용했다. 전체 backend는 subprocess에 상속되는 loopback-only socket guard 아래 실행했다. probe는 외부 DNS를 수행하기 전에 차단하며 시험 시도 계수와 분리된다. UI는 기존 Chromium 응답 interception/모의 API 검사를 실행한 결과이며 실제 Supabase 로그인 UI 통합 성공이 아니다. Stage4A original download binary도 이번 Linux에서 PASS였지만 과거 Windows 보고의 BLOCKED를 덮어쓰지 않았다.

새 원시 근거는 `work/stage4b3a/backend-final.json`, `.network.json`, `backend-final.log`, `work/stage4b3a/ui-1/*.json`/로그다. work는 기존 Git 제외 경로다. 중간 backend203 PASS 기록도 `backend-1.*`로 보존했다. 이후 성공 로그인 민감값 비저장·로그인 전 비활성 계정 시험2개를 추가해 최종205개를 다시 실행했다. 과거153/43 PASS를 이번 결과로 대체하지 않고 모두 새 실행했다.

## Git·보존 범위

GitHub origin은 seulkichoe80-hash/project_SB이며 원격 main과 작업 시작 HEAD가 `dbecf6e7bac72895b8564322e0a25bf924b7e7e2`로 일치했다. 시작 브랜치 work에서 `feat/stage4b3a-supabase-transport`를 생성했다. HEAD는 그대로이고 변경은 검토 가능한 미커밋 상태다. main ref·commit/push/merge·배포는 변경하지 않았다. 기존 tests/fixtures·회귀 테스트 파일·웹 소스·잠금파일·과거 보고/증거는 보존했다.

변경 파일: apps/api/supabase_transport.py(신규), identity_provider.py, main.py, auth.py(설명), requirements-api.txt; tests/test_supabase_transport.py(신규); scripts/validation/run_stage4b3a_checks.py(신규); docs/STAGE4B3A_SUPABASE_TRANSPORT.md(신규), docs/STAGE4B2_AUTH.md, ARCHITECTURE.md, TEST_PLAN.md, TASKS.md, 본 보고(신규).

## 남은 위험과 Stage 4B-3B 조건

Stage 4B-3A Feature Gate는 모의 전송/로컬 권한 범위에서 통과했다. 실제 계정/키·프로젝트 버전·인증 정책·TLS handshake·gateway/원격 가용성은 **NOT_RUN**이다. 실제 Supabase/LLM/임베딩 서비스 호출 **각0회**, 실제 키 등록·클라우드 배포·공개 변경도0이다.

Stage4B-3B 착수에는 프로젝트/리전·테스트 계정·서버 키 보관/주입·허용 HTTPS origin·접속/비용 범위를 별도 승인해야 한다. 그 후 명시 server factory 구성·실제 TLS/gateway·만료/위조 토큰·공급자 장애/제한·세션 수명·로그를 실증한다. 공급자 ban/logout은 기존 앱 세션에 즉시 동기화되지 않으며 로컬 취소/만료에 의존한다. refresh/MFA/CAPTCHA/초대·복구·custom domain/self-hosted 지원은 미구현이다. 전체 로그인 절대 deadline은 없고 각 요청 timeout 및 응답 읽기 예산으로 제한한다. 현재 Starlette TestClient의 httpx deprecation 경고는 남지만 모든 시험은 통과했으며 호환성 검토 없는 의존성 교체는 하지 않았다. 운영 인증/공개 배포 준비 완료로 판정하지 않는다.
