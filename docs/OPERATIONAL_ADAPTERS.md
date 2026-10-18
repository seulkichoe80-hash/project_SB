# 운영 설정 mapping·승인 기반 HTTP 전송

FR-14/15/18·NFR-01/02/05/07·WEB-02/04/05 범위. 기존 local/test SQLite·deny-all, 서버 membership·원본 SHA/size·EvidenceRef·쿠키/CSRF/Origin 계약을 유지한다. 이번 구현은 외부 계정/실제 자격증명/공급자 요청 없이 검증한다. **production 시작 차단6개는 해제하지 않는다.**

## 해결한 코드 공백

1. RuntimeSettings에 DB application/budget schema, Storage gateway key, Auth audience/JWT lifetime, Supabase 전송 opt-in/승인 추적 참조를 mapping했다. model/secret 마스킹과 peer 비교를 재사용한다.
2. `operational_mapping_issues`는 schema 누락/관리 schema/같은 schema, gateway 누락·server key 혼용, opt-in인데 승인 참조 누락을 진단한다. preflight의 추가 필드와 startup SettingsRejected에 반영한다. 기존 `settings_status`는 일반 설정 호환 계약이며 이 추가 mapping 진단과 구별한다.
3. Factory의 `prepare_production_runtime` → `prepare_operational_adapters`가 실제 env→typed MigrationPlan/Storage/Auth/JWKS 어댑터를 준비한다. **연결/마이그레이션/프로세스 시작은 수행하지 않는다.** 실제 production 시작은 기존 build_runtime/main/worker guard가 계속 거부한다.
4. 기존 exact Mock-only StorageHTTPTransport는 그대로 지원한다. 새 SupabaseStorageHTTPTransport는 같은 immutable POST/인증 GET·probe-first·SHA/size 검증 코드를 재사용하면서 명시적 network policy 또는 MockTransport를 선택한다.
5. 새 SupabaseAuthHTTPTransport는 기존 공식 password/user HTTP 계약을 재사용한다. SupabaseJWKSTransport는 고정 issuer의 공개 JWKS endpoint만 조회한다. 기존 JWTVerifier/ProviderAdapter에 exact 허용 타입으로 연결해 ES256/RS256·issuer/aud/expiry·kid/서명 검증을 재사용한다. 기존 Fake 인터페이스/테스트는 변경하지 않는다.
6. local/test Factory와 RuntimeBinding은 실제 network-selected 어댑터를 거부한다. Mock으로 준비한 동일 HTTP 코드는 격리 PG/API/worker에 주입할 수 있다. API 부분 Mock 구성은 거부하여 password만 Mock이고 JWKS/Storage가 실제 경로인 혼용을 방지한다. worker mapping은 browser Auth provider를 생성하지 않는다.

## 새 환경 변수

| 이름 | 의미/검증 |
|---|---|
| DB_APPLICATION_SCHEMA | application schema. public/auth/storage/extensions/pg_* 금지 |
| DB_BUDGET_SCHEMA | 별도 budget schema. application과 같으면 거부 |
| STORAGE_GATEWAY_API_KEY | 서버에서 보내는 별도 gateway apikey, SecretStr. STORAGE_SERVER_KEY와 혼용 금지 |
| AUTH_AUDIENCE | 현재 authenticated만 지원 |
| AUTH_JWT_MAX_LIFETIME |60..3600초, 기본3600. BFF의 더 짧은 수명/idle은 유지 |
| SUPABASE_NETWORK_ENABLED | 기본false. true만으로 production 기동 허용 안 됨 |
| SUPABASE_APPROVAL_REF | 명시 operator 승인 범위의 추적 식별자. 비밀/인증토큰/승인 자체가 아님 |

기존 DATABASE_URL/STORAGE_*/SUPABASE_*/APP_ORIGIN/ROLE·보안·backup·AI false/비용0 설정도 그대로 필요하다. 새 cloud mapping을 local/test env에 넣어 활성화하는 우회는 거부한다. 실제 값을 Git/PR/채팅에 넣지 않는다. VITE_*에는 어떤 관리 비밀도 넣지 않는다.

## 네트워크·보안 경계

`ProviderNetworkPolicy`는 정확한20자 project-ref HTTPS Supabase URL·auth/storage 서비스·enabled·approval_ref를 가진 frozen strict 모델이다. transport는 설정을 매 요청 재검증하고 exact MockTransport만 받아 subclass/임의 객체를 거부한다.

- Mock을 명시하면 실제 HTTP 직렬화/응답 처리를 socket 없이 시험한다. Mock 호출을 live 접속 성공이나 사용자 승인으로 보고하지 않는다.
- Mock이 없으면 **enabled=true AND 승인 추적 참조 AND 일치하는 project/service**가 모두 필요하다. 기본false 또는 참조만 있는 경우 Client 생성 전 실패한다. opt-in은 신뢰된 operator 구성에만 허용하며 HTTP 요청/user metadata에서 만들지 않는다. 참조 문자열은 사용자 승인 대체물이 아니다.
- 실제 경로의 httpx는 TLS verify·환경 proxy/CA 신뢰를 유지하고 redirect=false다. 기존 Mock-only 경로의 보안/검증은 유지한다. timeout·고정 URL/헤더·응답 크기·상태/인코딩을 제한한다.
- JWKS는 GET `/auth/v1/.well-known/jwks.json` 한 경로,64KiB 상한, 매번 새 snapshot이다. JWT의 jku/x5u/임의 URL은 사용하지 않는다. JWKS에 bearer/cookie를 보내지 않는다. 키 회전/삭제 시 stale cache fallback 없이 실패한다.
- password grant는 POST `/auth/v1/token?grant_type=password`, apikey/JSON. 기존 GET `/auth/v1/user`도 같은 gated HTTP 전송에서 지원한다. 이번 새 JWT profile은 서명 검증을 사용하며 원격 계정의 현재 활성 상태를 signature만으로 인증하지 않는다.
- 사용자 metadata는 권한으로 사용하지 않는다. 검증 issuer/subject를 서버 active identity/기관/membership에 매칭한다. provider access/refresh token은 브라우저·세션 DB·로그에 저장하지 않는다.
- Storage는 정해진 bucket/기관 hash 경로만 허용하고 x-upsert=false, 인증 GET bytes로 SHA/size를 확인한다. 오류/timeout 뒤 무조건 POST를 반복하지 않는다. delete/upsert/public URL/signed URL은 없다.
- Auth/JWKS의 비200·잘못된 JSON/서명·timeout/429/503은 fail-closed, 자동 재시도/실패한 공급자 fallback이 없다. Storage는 기존 retryable/ambiguous/Retry-After와 intent 재시도 한도를 재사용한다.
- 고정 진단만 노출하며 request/response·key·JWT·원문/비밀번호를 로그하지 않는다. 일반 httpx INFO 로그도 합성 marker 비노출로 검증한다.

## 공식 계약 확인 범위

[CONTRACTS.json](../outputs/operational-code/CONTRACTS.json)에 기존 확보본과 SHA/버전을 기록한다. 새로운 공급자 API 요청/자격증명 조회는 하지 않았다.

- Storage 공식 supabase/supabase commit7425d493…의 standard-uploads/authenticated downloads/access-control: POST object, GET authenticated object, bearer/apikey, immutable/서버 key RLS 우회 계약.
- 같은 공식 commit의 auth/jwts 및 signing-keys: 고정 JWKS endpoint와 비대칭 공개 key set. ES256/RS256은 기존 검증 정책 범위이며 HS256/custom domain 등으로 임의 확대하지 않는다.
- password/user는 기존 Stage4B-3A의 공식 Auth OpenAPI commitce9a8eee…/SHA2e220609… 확인 기록을 재사용한다. 이번에 최신 서버 버전과 실제 계정 호환을 재확인한 것은 아니다.
- 목록/실제 bucket ACL 조회·admin 계정 상태 동기화·원격 backup/restore의 계약을 추정 구현하지 않는다. Storage list_page는 여전히 명시 BLOCKED다.

## 유지되는 BLOCKED와 실제 연결 전 조건

| 코드/조건 | 이번 해결 | 남은 차단 |
|---|---|---|
| PostgreSQL production runtime | schema/env→typed plan 준비·peer/startup 진단 | Runner는 여전히 local_test/target guard. 승인된 remote runner/최소권한/TLS/pool 실증 필요 |
| private Storage production transport | live 선택 가능한 HTTP 코드와 config 연결, Mock/해시 검증 | 실제 private ACL·inventory/orphan·키 종류·가용성·20MiB·복구 미확인 |
| production Auth/provisioning | password/JWKS HTTP→기존 서명/identity 계약 연결 | live 현재 계정 상태/철회·bootstrap 실증 미완료. SessionRevalidation은 여전히 Fake-only |
| edge trust/HTTPS | 기존 쿠키/CSRF/Origin 유지 | Vercel/Render 신뢰 경계·body/response·same-site API 대안 미검증 |
| cloud worker runtime | 기존 role/peer·Mock 주입 worker 경로 유지 | 실제 프로세스/기관 범위·공통 remote stores·권한·lease/restart 검증 필요 |
| coordinated backup | 기존 Fake/로컬 복구 보존 | 원격 DB+객체+manifest/Auth/원장 일관 복원 미완료 |

따라서 SUPABASE_NETWORK_ENABLED=true를 넣어도 build_runtime/main/worker의 production 시작은 거부된다. 이 flag/승인 참조를 production guard 해제 방식으로 쓰지 않는다. 이번에 live 요청을 실행하지 않았고 실제 모델/embedding/Supabase/Render/Vercel 연결·결제·공개 배포를 승인받지 않았다.

사용자 설정: 승인된 staging project/region/plan, DB TLS role/endpoint·두 schema, private bucket·서버/gateway key, Auth issuer/audience·초대 계정/명시 초기 manager, 정확 HTTPS Origin/Host·secret manager·backup 목표. 이후 실제 연결에는 합성 입력/SHA/용량·읽기/쓰기/migration 범위·횟수/기간·비용·복구 담당을 별도 승인해야 한다. 현재 code-owned6개 blocker를 없애서 접속하지 않는다.

## 검증과 Git 보존

신규 tests/test_operational_adapters.py는 mapping/미승인 차단·부분 Mock 혼용·URL/헤더/redirect·JWT 위조/만료/키 회전·오류/로그·Mock immutable Storage·실제 격리PG 세션/CSRF/멤버십/기관/worker를 다룬다. 전체 회귀와 소요시간은 이번 새 보고/evidence를 따른다. 기존 테스트/fixture/원본/SQL·과거 증거는 변경하지 않는다. UI/API 응답·DB schema 변경 없음, 프런트 typecheck/build는 이번 범위에서 실행하지 않는다. 결과를 검토한 뒤 이번 feature branch만 normal push로 보존하고 main은 병합하지 않는다.
