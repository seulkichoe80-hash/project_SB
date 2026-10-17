# Stage 4B-3A Supabase Auth HTTP 계약

FR-01/14/15/18, WEB-02/03/06의 연결 계층이다. 기존 [BFF 세션 계약](STAGE4B2_AUTH.md)을 유지한다. 실제 Supabase·LLM·임베딩 호출/계정·키 등록·배포는 이번 범위 밖이다.

## 설정과 활성화 경계

`SupabaseSettings(project_url, api_key, timeout_seconds=5)`는 서버 전용 설정이다. `create_app(..., supabase_settings=settings)`를 명시 호출하거나 `SupabaseProviderAdapter(SupabaseHTTPTransport(settings), settings.issuer)`를 서버 factory에 주입한다. 두 설정 경로를 동시에 지정하면 거부한다. 생성/앱 시작 자체는 HTTP를 호출하지 않는다. 기본 `apps.api.main:app`은 설정을 읽거나 공급자를 자동 활성화하지 않으며 기존 deny-all이다. 환경변수·`.env`만 추가해서 원격 연결이 켜지지 않는다. 실제 server factory/secret 주입과 활성화는 별도 승인 후 Stage 4B-3B에서 한다.

- URL: `https://<20자리 소문자 영숫자 프로젝트 ref>.supabase.co`의 루트만 허용한다. 사용자정보·포트·query·fragment·하위경로·IP·custom/self-hosted 도메인을 거부한다. HTTPS/TLS 검증을 유지하고 플랫폼 proxy/CA 환경을 사용한다.
- gateway key: `sb_publishable_...` 또는 같은 ref의 legacy `anon` JWT 형식만 허용한다. `sb_secret_...`와 `service_role` 키는 거부한다. legacy 키의 role/ref 검사는 설정 형식 검사이며 JWT 서명 검증이나 키의 실제 유효성 검증이 아니다. 실제 gateway가 거부하면 로그인도 차단한다.
- 키는 dataclass repr에서 제외한다. 프런트/VITE 값·응답·DB에 넣지 않는다. 실제 키는 코드·채팅·증거에 저장하지 않는다. 자동 환경 스캔/파일 읽기/키 발급 기능은 없다.
- `/auth/status`는 가용성 및 `remote_enabled` boolean만 공개한다. HTTP transport를 모의 전송으로 시험해도 `remote_enabled=true`는 **구성 종류**를 의미하며 실제 네트워크 연결 성공을 의미하지 않는다.

## 신원 확인 순서

1. 기존 Origin·단회 로그인 challenge·CSRF·로컬 rate limit을 통과한다.
2. 고정 프로젝트에 `POST /auth/v1/token?grant_type=password`, JSON email/password와 서버 `apikey`를 보낸다.
3. 정상 bearer access token·정수 expires_in을 확인하고, 같은 고정 프로젝트의 `GET /auth/v1/user`에 apikey와 bearer를 보낸다.
4. **서버 사용자 조회 검증 방식**을 채택했다. 토큰의 로컬 decode/unsigned claims를 신원으로 사용하지 않는다. 토큰의 서명·만료·해당 프로젝트 검증은 TLS로 연결한 Supabase `/user`에 위임한다. `/user` 실패는 항상 차단한다. user UUID·aud=`authenticated`·비익명/비정지/비삭제 상태·token 응답 user.id 일치를 추가 검사한다. issuer는 서버 URL에서 고정하며 클라이언트나 user_metadata에서 받지 않는다. 로컬 JWKS 캐시/서명 검증은 이 방식에 추가하지 않는다.
5. expires_in은 60..86400 정수, 앱에 넘기는 TTL은 경과시간을 차감하고 최대3600초다. expires_at이 있으면 엄격한 정수·미래값인지 검사하고 더 짧은 수명을 택한다. BFF는 기존 최대1800초/idle900초 중 짧은 값을 사용한다.
6. 고정 issuer+검증 subject에 매칭되는 로컬 active identity/organization/membership이 정확히 하나일 때만 앱 세션을 만든다. user_metadata/app_metadata/email 도메인은 기관·역할 권한이 아니다. reader/manager·기관 간 자료/검색/EvidenceRef 검사는 기존 서버 서비스와 세션 dependency가 담당한다.

provider access/refresh token은 로그인 호출 중 지역 변수로만 사용한다. 브라우저에는 기존 난수 BFF 세션만 전달하고 DB에는 세션 해시만 저장한다. 기존 HttpOnly·Secure·SameSite=Lax·Path=/·CSRF/Origin·세션회전·로그아웃 revoke를 유지한다.

## 오류와 자원 제한

두 method/path 조합만 허용하고 임의 URL/헤더를 전달하지 않는다. redirect/자동 재시도/공급자 fallback/refresh는 없다. 각 요청 connect/read/write/pool timeout은 기본5초(설정0.1..10초)이며, 응답 반복 읽기에서도 경과시간을 검사한다. 이는 네트워크 각 단계 timeout과 읽기 예산이며 전체 로그인 요청의 절대 deadline은 아니다. 로그인은 최대 두 HTTP 요청이다.

응답은 JSON object·최대64KiB만 허용하며 identity encoding을 요청하고 압축 응답을 거부한다. 새 client를 요청마다 닫아 연결과 provider cookie를 보관하지 않는다. 3xx/400/401/403/404/422/429/5xx, TLS/연결/timeout/프로토콜/JSON/형식 오류는 모두 `ProviderUnavailable` → 기존 BFF503으로 수렴한다. 공급자 오류본문·비밀번호·키·토큰·원 예외를 로깅/반환하지 않는 방식으로 마스킹한다. 기존 audit는 고정 outcome만 남긴다. 잘못된 서버 설정은 값 없는 고정 `ValueError`로 실패한다.

## 공식 계약·호환성 근거

2026-10-17에 [Supabase Auth 공식 OpenAPI](https://github.com/supabase/auth/blob/ce9a8eee0cc042be8c7a42981a7ddae631e41d91/openapi.yaml)를 확인했다. upstream commit은 `ce9a8eee0cc042be8c7a42981a7ddae631e41d91`, OpenAPI3.0.3/info.version=`latest`, 파일 SHA256은 `2e2206095d3614640f3b395f403b6d132e750c84c1e8a37a5888a3cd140ac788`이다. `/token` password grant, `/user` APIKeyAuth+UserAuth, bearer/expires_in/expires_at/user 응답 계약과 429·비JSON 5xx 안내를 근거로 구현했다. SDK 대신 기존 잠금파일의 httpx0.28.1을 사용하고 runtime requirements에도 같은 버전을 명시했다. 실제 프로젝트에 배포된 Auth 버전·설정과 호환되는지는 Stage 4B-3B에서 승인 후 확인해야 한다.

## 검증과 다음 단계

`python scripts/validation/run_stage4b3a_checks.py --output work/stage4b3a/<새이름>.json`은 기존 전체 regression runner를 재사용한다. sitecustomize로 Python DNS/TCP 연결을 loopback으로 제한하고 하위 Python worker/HTTP subprocess에도 상속한다. 가드 자체는 외부 DNS를 수행하기 전에 차단하는 probe로 확인한다. probe와 시험의 차단 로그를 분리하며, 시험 중 외부 연결 시도가 한 번이라도 있으면 runner를 실패시킨다. 새 HTTP 시험은 httpx.MockTransport만 사용한다. TLS 실제 handshake/실공급자 가용성은 검증하지 않는다.

Stage 4B-3B 전에는 실제 접속 범위·프로젝트/리전·테스트 계정·키 관리·동일 출처 TLS/origin·비용을 승인하고, 명시적 서버 factory 활성화·gateway/TLS·잘못된 키/토큰·Supabase user 검증·세션 수명/장애·로그를 실제 조건에서 검증해야 한다. custom domain/self-hosted 지원, MFA/CAPTCHA/초대/복구/refresh, 공급자 ban/logout의 기존 앱 세션 즉시 취소 동기화는 미구현이다. 로컬 비활성화는 즉시 검사하지만 공급자만 정지하면 기존 앱 세션은 로컬 만료까지 남을 수 있다. 이번 완료는 원격 계층의 모의 검증이며 운영 인증/공개 배포 완료가 아니다.
