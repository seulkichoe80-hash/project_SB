# 배포 준비 4단계 — 오프라인 Supabase JWT·서버 멤버십

이번 범위는 **Fake password/JWKS 전송 + 실제 암호 서명 검증 + 기존 BFF 세션/DB 멤버십**이다. 실제 Supabase 계정·키·API·공개 배포와 운영 Auth 완료가 아니다. PRD FR-18/NFR-01·06·07, WEB-02/04/05 및 기존 [세션 계약](STAGE4B2_AUTH.md)·[사용자 조회 기반 공급자 계약](STAGE4B3A_SUPABASE_TRANSPORT.md)을 재사용한다. 기존 `/user` 검증 어댑터는 그대로 유지하고 새 명시 JWT 어댑터를 병행한다.

## 흐름과 경계

1. 서버 factory에 `SupabaseJWTProviderAdapter(FakeTokenTransport(...), SupabaseJWTVerifier(...))`를 명시 주입한다. 표준 앱·환경 변수는 이를 자동 구성하지 않으며 기존 deny-all 기본값을 유지한다. 새 transport는 정확한 Fake concrete type만 허용한다. HTTP/DNS/socket·임의 callback 구현이 없다.
2. 기존 `/auth/csrf`와 `/auth/login` password grant 계약을 사용한다. 브라우저 bearer JWT 로그인 경로나 새 AuthContext 응답을 추가하지 않는다. Fake password transport는 정적 합성 response와 고정 장애만 제공한다.
3. verifier는 서버가 고정한 issuer에 대응하는 `/auth/v1/.well-known/jwks.json`의 **새 bounded snapshot을 검증마다 한 번만** 읽는다. 키 추가/제거/교체를 즉시 반영하고 오류·중복 kid·모호한 키·unknown kid에 stale cache/fallback/무한 재시도를 하지 않는다. 실제 HTTP 캐시/timeout/프록시·TLS 구현은 이번에 연결하지 않았다.
4. 서명과 claim을 검증한 issuer/UUID subject/남은 수명만 기존 `VerifiedIdentity`로 전달한다. token response user.id도 verified subject와 같아야 하며 알려진 anonymous/banned/deleted 표시는 거부한다.
5. 서버 DB identity·organization·활성 단일 membership을 검증한 뒤 기존 난수 BFF 세션을 발급한다. JWT/user_metadata/app_metadata/email 도메인에서 기관·역할·관리자 여부를 가져오지 않는다. provider access/refresh token은 응답·세션 DB·로그에 저장하지 않는다.

`/auth/status`의 provider_available=true는 명시 Fake 구성에서 로그인 계약을 사용할 수 있다는 뜻이며 remote_enabled=false다. JWT 검증 코드는 기존 잠금파일 requirements-parsing-lock.txt의 **cryptography50.0.2**를 사용한다. 새 패키지/다운로드/기존 lock 변경은 없다. API-only lock만 설치한 미래 배포에는 이 암호 라이브러리가 추가로 필요하므로 운영 이미지 의존성 검증을 생략하면 안 된다.

## 제한된 JOSE 프로필

`apps/api/supabase_jwt.py`는 bounded JSON/base64url 프로필을 파싱하고 **cryptography의 검증 primitive**를 호출한다. 암호 연산을 직접 구현하거나 JWT를 단순 decode해 인증하지 않는다. 범용 JOSE 구현이나 모든 Supabase 구성 호환을 주장하지 않는다.

| 항목 | 허용/거부 |
|---|---|
| issuer | 정확 `https://<20자 project>.supabase.co/auth/v1`, 서버 설정으로 고정. trailing slash/newline·custom domain·임의 URL 거부 |
| audience | 문자열 `authenticated`만. 여러 audience/list는 현재 프로필 밖으로 거부 |
| alg | 명시 allowlist ES256/RS256. none/HS256/알고리즘 혼동/다른 alg 거부. legacy HS256 프로젝트 자동 fallback 없음 |
| JWK | ES256/P-256·32바이트 x/y, 또는 RS256/RSA2048–4096bit/e65537. public signature key만, private material/키 목적 혼동·중복 kid·미지원 필드 거부 |
| header | alg/kid/선택 typ=JWT만. jku/jwk/x5u/crit/b64 등 거부, 토큰 URL을 조회하지 않음 |
| claim | iss/aud/sub/role/iat/exp 필수. sub는 canonical UUID, role=authenticated, anonymous 거부. nbf가 있으면 확인 |
| 시간 | 정수 NumericDate만. iat≤now<exp, iat≤nbf≤now, 0<exp−iat≤설정 max_lifetime(최대3600초). 임의 clock leeway로 만료 연장 안 함. 남은 수명1초 미만 거부 |
| 한도 | JWT8192자, header1024B, claims6144B, signature512B, JWKS64KiB/키8개. 중복 JSON key·비정상 숫자·비정규 base64url 거부 |
| 실패 | 고정 ProviderUnavailable→기존 BFF503. 원 토큰/키/원문 오류를 반환·기록하지 않음. 429/503/redirect/timeout도 새 인증 거부 |

설계 참고: [Supabase JWT](https://supabase.com/docs/guides/auth/jwts), [signing keys](https://supabase.com/docs/guides/auth/signing-keys), RFC7515/7517/7519. 이번에는 공식 사이트/실제 provider에 새 요청을 하지 않았다. 실제 프로젝트 signing algorithm/claims·JWKS 응답 필드·배포 Auth 버전과의 호환성은 승인 후 별도 확인해야 한다.

## 기관·역할·세션

- 기존 `AuthService.resolve()`의 identity/org/membership active 검사를 유지하고, 설정된 provider issuer와 DB identity issuer 일치 및 활성 membership이 정확히 하나인지 매 요청 확인한다. 공급자/기관 전환이나 새 모호한 membership을 기존 세션으로 우회하지 않는다.
- reader/manager는 DB 역할만 사용한다. 별도 institution_admin도 DB 기준이며 일반 manager에게 계정 관리 권한을 자동 부여하지 않는다. 브라우저에서 worker 역할을 만들 수 없다. worker는 기존 별도 서버 역할/claim 경계로 실행한다.
- 멤버십 변경 API는 기존 CSRF/Origin·본인 변경 금지·마지막 관리자 보호·기관 범위·세션 철회를 유지한다. 관리자 목록/변경의 실제 DB transaction 안에서도 현재 세션·계정·기관·관리자 플래그·단일 멤버십을 다시 검사하여 앞선 resolve 이후 권한 철회 경합을 차단한다.
- HttpOnly/Secure/SameSite=Lax/__Host/Path=/, Origin/CSRF/교차사이트 검사, SID 회전·로그아웃·DB hash 저장·만료/idle 계약과 HTTP 응답은 그대로다. JWT는 브라우저 쿠키가 아니며 Authorization bearer만으로 기존 API에 접근할 수 없다.
- BFF 수명은 기존 최대1800초/idle900초와 provider JWT 남은 수명 중 짧은 값이다. 로그인 이후 매 요청 Supabase에 접속하지 않는다. **provider-only ban/logout·키 제거가 이미 발급된 BFF 세션을 즉시 철회하는 동기화는 미구현**이며 로컬 DB 철회/비활성은 즉시 검사한다. 운영 전 provider revocation 정책·TTL·필요한 이벤트/관리 절차를 정해야 한다.

## 최초 기관·관리자 등록

`apps/api/auth_bootstrap.py`의 `bootstrap_initial_administrator(store, request, confirmation=...)`는 **신뢰된 오프라인 운영자 절차**이며 공개 API/자동 startup hook/임의 email-domain 가입이 아니다.

- `InitialAdministrator`는 고정 issuer/canonical subject UUID/기관 ID/표시 이름만 받는다. email/domain/역할 입력은 계약에 없다. 호출 전 운영자가 허용된 프로젝트의 검증된 사용자 subject와 승인된 기관·최초 담당자를 별도 확인해야 한다. UUID 형식만으로 실제 계정 존재를 증명하지 않는다.
- 정확한 AuthStore/PostgresAuthStore와 명시 확인 문자열 `CREATE_INITIAL_INSTITUTION_ADMIN`이 필수다. 승인/사용자 확인을 코드가 대신하지 않는다. production에서 이 절차가 완료됐다는 flag를 자동 기록하거나 readiness를 해제하지 않는다.
- 기존 기관 또는 기존 issuer/subject가 있으면 거부한다. 기존 관리자/비활성 조직을 덮어쓰거나 이메일로 연계하지 않는다. 새 identity/org/manager+institution_admin membership/감사 event를 한 transaction으로 기록한다. 동시 호출은 하나만 성공, 부분 실패는 전체 rollback이다.
- 기존 테스트용 `AuthStore.provision` seam은 보존하되 운영 onboarding API로 노출하지 않는다. 실제 서버 DB·운영자 권한·명시 승인과 최초 사용자 확인이 운영 이식 전 조건이다. 이번 실행에서는 새 테스트 DB의 합성 사용자만 사용했다.

## 실행·검증

기존 가상환경과 격리 PostgreSQL fixture의 [이전 시작 계약](DEPLOYMENT_POSTGRES.md)을 사용한다. 서비스 계정·실제 키를 주입하지 않는다.

```bash
# PG DSN 없으면 해당 부분은 skip/BLOCKED이며 PG PASS가 아니다.
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test .venv/bin/python -B -m unittest discover -s tests -p test_deployment_auth.py

# Phase Gate 전체 backend. 항상 새 output 이름 지정.
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test .venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output outputs/my-new-auth-backend.json

.venv/bin/python -B scripts/validation/deployment_preflight.py
```

신규 검사: ephemeral EC/RSA 실제 서명·위조·시간/issuer/aud·알고리즘/키 정책·JWKS rotation/error, Fake grant→실제 BFF session→DB 멤버십/기관 경계, 쿠키/CSRF/logout·권한 변경/경합, 명시 bootstrap 동시성/rollback, Private Storage→parse/chunk/workflow→reader 원본/EvidenceRef·앱 재구성 후 세션 유지. 기존 fixture·테스트·과거 증거는 수정하지 않는다. 전송은 Fake이며 TestClient의 ASGI 요청을 실제 원격 HTTP/Auth 성공으로 보고하지 않는다.

전체 runner의 Python 비루프백 guard와 PG local_test loopback 강제를 병행한다(C libpq는 Python guard 범위 밖). 실제 Supabase/AI 호출·지출은0이며 인간 의미 판정은 생성하지 않는다. UI/타입/build는 웹 계약/코드/의존성 변경이 없어 이번 범위 밖으로 구분한다.

## 운영 시작 차단과 다음 조건

preflight는 `jwt_verification=FAKE_JWKS_IMPLEMENTED_NOT_CONNECTED`를 표시한다. production은 Auth runtime/운영자 provisioning 미실증 blocker 및 기존 PG/Storage/proxy/cloud-worker/운영 backup blocker로 계속 차단한다. 형식 검증 VALID와 연결 성공은 다르다.

다음 사용자 요청의 후보는 운영 wiring/동일 출처 HTTPS·proxy 및 제한 계약 구현이다. 실제 연결 전에는 별도 승인된 프로젝트·계정/키, asym signing/JWKS 호환, CA/SSRF/redirect/timeout·cache 정책, 서버 membership 최초 확인/초대·회수, provider 정지/세션 철회 정책, secret manager와 최소권한·RLS, DB/Storage 일관 백업/비용 원장/복구·운영 worker 검증이 필요하다. 현재 production 또는 G1-C/D 완료로 승격하지 않으며 다음 단계는 자동 실행하지 않는다.
