# Stage4B-2 로컬 인증 계약

현재 연결 계층은 [Stage 4B-3A 계약](STAGE4B3A_SUPABASE_TRANSPORT.md)을 함께 따른다. 아래 원격 transport 미구현 설명은 Stage4B-2 시점의 범위이며, 새 HTTP 계층은 명시 서버 설정으로만 활성화된다. 실제 공급자 연결은 여전히 미검증이다.

FR-01/14/15/18·WEB-02/03/06의 로컬 접근 주체 경계다. 실제 공급자/클라우드는 미연결이다. 제품 앱의 기본 provider는 UnconfiguredProvider이며 기존 세션이 남아 있어도401로 차단한다. 환경변수만으로 mock 계정/권한을 활성화하는 기능은 없다.

## Provider와 세션

IdentityProviderAdapter → SupabaseProviderAdapter(MockSupabaseTransport 명시 주입만 허용) → mock POST /auth/v1/token?grant_type=password → mock GET /auth/v1/user로 신원 확인 계약을 검증한다. 실제 HTTP client/SDK/원격 transport는 구현하지 않았다. user metadata/role/email domain은 권한 자료가 아니다. provider issuer+subject와 로컬 active identity·organization·membership을 매 요청 검사해 기존 Principal을 생성한다. worker는 provision에서 거부하고 browser role에는 reader/manager만 허용한다.

세션 ID는32바이트 난수, DB에는 SHA-256만 저장한다. cookie는 기본 __Host-seomuitda, HttpOnly/Secure/SameSite=Lax/Path=/·Domain 없음. 성공 로그인 시 기존 세션 회전, 만료/유휴/정지/취소/멤버십 해제 시401. provider가 준 유효기간과 로컬1800초 중 짧은 값을 만료로 사용하고 idle900초다. provider 토큰/비밀번호/refresh token은 DB나 브라우저 저장소에 저장하지 않는다. refresh는 현재 미구현이며 만료 시 재로그인이 필요하다. provider token을 직접 브라우저 API 인증으로 받는 경로도 없다.

HttpOnly pre-login nonce cookie+CSRF token challenge는5분 단회다. 세션 mutation에도 CSRF+정확 Origin 검사를 적용한다. 세션 CSRF는 난수 session ID를 키로 한 domain-separated HMAC에서 도출하며 DB에는 그 hash만 저장한다. CSRF token은 UI 메모리에만 둔다. login IP당5분10회 제한은 로컬 계약이며 trusted proxy/운영 rate limit은 후속 검증한다. credential을 포함할 수 있는422 입력 상세는 반환하지 않는다. 모든 API 응답 no-store/Vary Cookie.

기본 origin=https://localhost·Secure=true다. insecure cookie는 명시적 AuthSettings에서 http://127.0.0.1 또는 localhost에만 허용하며 외부 origin에서는 설정 자체를 거부한다. 테스트 harness의 local HTTP 설정을 운영 실행법으로 사용하지 않는다. HTTPS/TLS 운영 실증은 미검증이다.

## API

| 경로 | 계약 |
|---|---|
| GET /auth/status | provider_available/remote_enabled(false), 비밀값 없음 |
| POST /auth/csrf | Origin 필요, pre-login HttpOnly nonce와 JSON csrf_token |
| POST /auth/login | email/password만 허용, cookie+CSRF+Origin, 공급자 미설정503/신원·기관미승인403 |
| GET /auth/me | 유효 세션만 사용자ID/기관명/기관ID/role/admin/CSRF 반환 |
| POST /auth/logout | 유효 세션+CSRF+Origin, 로컬 revoke/cookie삭제 |
| GET /auth/memberships | 서버 세션 기관의 institution_admin만 조회 |
| PATCH /auth/memberships/{user_id} | 소속기관 기존 멤버만 role/active/admin 수정, CSRF/Origin 필요, 자기 변경/마지막 관리자 제거 금지, 대상세션 revoke |

한 사용자에게 active membership이 정확히1개일 때만 로그인한다. 0개/복수는403이며 client 기관 ID를 임의 선택해 사용하지 않는다. multi-organization 전환 UI/초대/가입/복구 UI는 후속 계약이다. 기관관리 capability는 reader/manager와 별개이며 운영자에 타기관 자료 권한을 자동 부여하지 않는다. bootstrap은 신뢰된 로컬 provision seam만 있고 공개 HTTP bootstrap은 없다.

## DB·백업

기존 metadata.sqlite3에 identities·organizations·memberships·sessions·auth_challenges·auth_audit_events·auth_login_limits를 추가한다. 기존 documents/versions/source_blocks/원본/EvidenceRef schema는 변경하지 않는다. 최초 auth migration 전 SQLite backup API로 같은 runtime의 auth-backups/pre-auth-<random>.sqlite3를 만들고 추가 DDL을 트랜잭션으로 실행한다. 기존 user_version과 데이터는 유지한다. SQLite connection은 context 종료 시 명시적으로 close한다.

검증에서는 기존 문서·버전·source_blocks·parse_jobs/attempts의 행과 backup을 대조하고 원본 SHA-256을 확인했다. 복원은 별도 DB 파일에서 검증했으며 운영 DB를 자동 덮어쓰지 않는다. 실배포 백업은 비공개/암호화/수명정책/파일과 DB 동기복원이 별도 필요하다. audit에는 시간/action/내부 user/org ID/outcome만 저장하며 credential/token/원문을 넣지 않는다.

## React

AuthProvider가 /status와 /me를 확인하고, 준비 전/로그인 전 DocumentsPage를 mount하지 않는다. 로그인 화면은 공급자 미설정 시 submit 비활성화이며 성공을 꾸미지 않는다. 로그인·logout·만료 시 user/CSRF 메모리를 정리한다. Header 기관·reader/manager/admin 표시는 서버 응답만 사용한다. reader mutation UI를 비활성화하고 서버는 별도로403 처리한다. 보호 자료401 이벤트 시 화면·선택을 제거하고 재로그인 안내를 표시한다. localStorage/sessionStorage에 비밀번호·provider token을 쓰지 않는다.

## 다음 연결 전 필수사항

실제 Supabase 계정/리전/테스트 사용자·허용 origin과 예산 승인 후 remote transport, gateway apikey/시크릿 주입·TLS/timeout/rate limit·응답 검증을 구현해야 한다. 현재 mock은 원격 가용성/JWT 서명/issuer/audience/JWKS 회전 검증이나 공급자 logout/ban 동기화 성공이 아니다. 승인된 flow의 검증 라이브러리/SDK와 getUser/JWKS 정책을 결정하고 공개·비밀 키 구분, provider 장애, 복구/MFA/초대, 세션 refresh 여부를 검증한다. 공급자 정지와 앱 identity 정지의 동기화도 미구현이다. 실제 인증/공개 배포 준비 완료로 판정하지 않는다.

[공식 로그인 계약](https://supabase.com/docs/reference/python/auth-signinwithpassword) · [사용자 확인](https://supabase.com/docs/reference/python/auth-getuser) · [이번 실행 보고](../outputs/STAGE4B2_REPORT.md)
