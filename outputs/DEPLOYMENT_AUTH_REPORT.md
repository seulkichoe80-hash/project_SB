# 서무ITDA 배포 준비 4단계 — 오프라인 Auth 완료 보고

2026-10-18 UTC. **완료 범위: Fake JWT/JWKS 전송에 실제 서명 검증을 연결하고 기존 BFF·서버 멤버십·명시 최초 관리자 계약을 검증했다. 운영 Supabase 연결/production 준비 완료는 아니다.** [계약·재현 명령](../docs/DEPLOYMENT_AUTH.md).

## 1. 실제 시작 상태와 보존

- 실제 디렉터리 `/workspace/project_SB`, 저장소 seulkichoe80-hash/project_SB.
- 시작 브랜치 `feat/deployment-private-storage`, HEAD `acc09eb6beb1ba6fed5a9d0194bb112c3c394cbe`로 사용자 기준과 일치했다. 새 clone/reset/복구 가정 없이 기존 작업을 확인했다.
- Private Storage 미커밋 **27파일**을 이전 CHANGE_MANIFEST26항목+manifest 자신과 대조했다. 기존891 PASS 증거와 실행 대상 source SHA가 현재 파일에 일치하는지 검증한 뒤 보존했다. 당시 결과를 새 테스트 PASS로 계상하지 않았다.
- 이전 변경 보존 로컬 커밋: **68a8a3513c1df7bc8290f5b3e091e2125733677c**, 메시지 `Preserve Fake private storage and application recovery contracts`.
- 이후 **feat/deployment-auth** 분기. 새 Auth 구현·문서·증거20파일은 미커밋 검토 후보이며 staged 파일0. push·main 수정·reset·force push·merge·tag·공개 배포 없음.
- 보존 사본: `work/deployment-auth-preservation/baseline.tar.gz`, 파일별 SHA. [보존·보안 결과](deployment-auth/PRESERVATION.json).

## 2. 변경 파일과 구현 범위

신규:

- `apps/api/supabase_jwt.py`: strict JWTSettings/JWKSTransport 계약, Fake JWKS/password 전송, SupabaseJWTVerifier, SupabaseJWTProviderAdapter.
- `apps/api/auth_bootstrap.py`: strict InitialAdministrator와 명시 확인이 필요한 신뢰된 오프라인 bootstrap transaction. 공개 API 없음.
- `tests/test_deployment_auth.py`: 암호/JOSE28개, SQLite 세션/기관/Storage/초기화30개, 동일 real-loopback PG30개로 신규88개.
- `docs/DEPLOYMENT_AUTH.md`, 본 보고, `outputs/deployment-auth/*` 새 증거와 CHANGE_MANIFEST.

수정:

- `apps/api/auth.py`: 세션의 provider issuer 바인딩과 활성 단일 멤버십 재검사. 관리자 조회/변경 transaction 안에서 세션·계정·기관·멤버십·관리자 권한 재검사.
- `apps/api/runtime_settings.py`: Fake JWT 구현 상태와 운영 Auth runtime/provisioning 미실증 blocker 표시. production 허용 없음.
- `ARCHITECTURE.md`, `TASKS.md`, `TEST_PLAN.md`: 해당 단계 계약/진척/검증 절만 추가.

기존 LLM·RAG·DB schema·SQL migration·Private Storage·worker·EvidenceRef·UI·원본·fixture·기존 테스트·잠금파일은 수정하지 않았다. 추가 설치/다운로드 없이 기존 cryptography50.0.2/requirements-parsing-lock.txt를 사용했다. 향후 API-only 운영 이미지에는 이 의존성이 포함되는지 별도 확인해야 한다.

## 3. JWT/JWKS 및 기관·역할

새 경로는 **Fake password grant → 서명/claim 검증 → VerifiedIdentity → 기존 서버 identity/organization/membership → 난수 BFF 세션**이다. 기존 SupabaseProviderAdapter의 검증된 사용자 조회 방식은 변경하지 않고 병행한다. 표준 앱은 계속 deny-all, 명시 factory 주입만 Fake 로그인을 구성한다. 새 HTTP endpoint 또는 브라우저 bearer 인증을 추가하지 않았다.

- ES256/P-256와 RS256/RSA2048–4096/e65537만 허용. 실제 암호 검증은 cryptography primitive를 사용한다. none/HS256·key/alg 혼동·private JWK·악성 jku/jwk/x5u/crit·중복 kid/JSON·비정규 base64url·한도 초과를 거부한다.
- 고정 HTTPS project issuer, 정확 audience=authenticated, canonical UUID subject, role=authenticated, iat/exp 및 선택 nbf의 타입·기간·만료를 검증한다. TTL은 JWT/response 수명과 BFF 최대1800초/idle900초로 제한한다.
- 검증마다 bounded Fake JWKS snapshot을 한 번 읽는다. 추가/교체 키는 반영하고 제거 키·unknown kid·오류에 stale cache/fallback/무한 retry를 사용하지 않는다. Fake 429/503/timeout/redirect 및 잘못된 응답은 새 인증을 거부한다.
- user_metadata/app_metadata/email 도메인은 기관·역할·관리자 근거가 아니다. 서버 DB active identity/org와 단일 active membership만 사용한다. 기존 세션에서도 비활성·권한 변경·기관/issuer 전환·새 모호한 membership을 재검사한다.
- 브라우저는 reader/manager만 사용하고 worker는 별도 서버 실행/claim 경계를 유지한다. 일반 manager에게 institution_admin 권한을 자동 부여하지 않는다.
- 최초 등록은 기존 기관/identity를 덮어쓰지 않는 명시 오프라인 운영자 함수이며 identity/org/manager+institution_admin/audit를 원자 저장한다. 동시 호출 하나만 성공, 부분 실패 전체 rollback. 실제 provider 사용자의 존재/기관 승인은 운영자가 별도 확인해야 하며 코드가 인간 승인을 생성하지 않는다.

## 4. 테스트 실제 결과

| 실행 | 결과 | 시간 |
|---|---|---:|
| 신규 JWT/JWKS·SQLite30·로컬PG30 및 암호28 | **88 PASS**, FAIL0/SKIP0 | 13.585초 |
| 전체 백엔드(기존891+신규88) | **979 PASS**, FAIL0/SKIP0/BLOCKED0 | tests288.590초, 전체 명령290.226초 |
| local offline preflight | LOCAL_CONTRACT_VALID, connectivity NOT_CHECKED | 연결 없음 |
| production 합성 API/worker preflight | 설정 VALID, **BLOCKED/startup_allowed=false** | 연결 없음 |

[신규 최종 검사](deployment-auth/targeted-complete.txt) · [전체 회귀](deployment-auth/backend.json) · [네트워크 가드](deployment-auth/backend.network.json) · [local](deployment-auth/preflight-local.json) · [production](deployment-auth/preflight-production.json).

전체 회귀는 단 한 번 최종 코드에서 실행했다. 최초 영향 검사에서는 PG `? IS NULL` 파라미터의 타입 미확정 오류 및 새 테스트가 기존 응답 `{document: ...}` 래퍼를 누락한 오류가 있었다. 공통 SQL을 `i.issuer=COALESCE(?,i.issuer)`로 고치고 새 테스트를 실제 계약에 맞춘 뒤 재검사했다. 초기82/12 errors 및 두 번째84/2 errors 기록을 삭제/덮어쓰지 않고 남겼다. 이어84 PASS 후 통합2시나리오×DB2를 추가하여 최종88 PASS, 전체979 PASS를 확인했다. 기존 테스트 assertion을 완화하거나 정답을 변경하지 않았다.

검증한 핵심 흐름: JWT 로그인/쿠키 → 관리자의 Private Storage 업로드 → worker parse/chunk → 관리자 명시 활성화 → 미승인 workflow → reader 원본·구조적 EvidenceRef 재해결. 다른 기관 문서/검색/근거 접근 거부, reader 관리 mutation 차단, CSRF/Origin/cross-site, 로그아웃·재사용·만료, 권한 강등/정지·resolve 이후 관리자 철회 경합, bootstrap 중복/경합/rollback, 앱 재생성 뒤 해시 기반 세션 유지도 양 DB에서 검증했다. 서비스 프로세스 재구성과 PostgreSQL 서버 재시작은 다르며 후자를 이번에 새 실행했다고 주장하지 않는다.

UI/타입/build는 프런트 코드·응답 계약·의존성 변경이 없어 이번 미실행이다. 과거 UI174 PASS를 새 결과로 계상하지 않는다. TestClient 요청은 ASGI 통합이며 실제 Supabase/TLS/TCP 운영 인증 성공이 아니다. 기존 Starlette/httpx deprecation 경고는 남았으나 실패는 없다.

## 5. 보안 결과와 기존 데이터 영향

HttpOnly·Secure·SameSite=Lax·__Host/Path=/, 기존 Origin/CSRF·SID 회전·세션 hash·로그아웃 revoke를 유지했다. provider access/refresh token·password·JWT를 응답·세션 DB·일반 로그에 노출하지 않는 검사를 통과했다. 키는 시험 시 메모리에서만 생성했고 PEM/private key를 파일이나 Git에 쓰지 않았다. 최초 계정/기관을 startup에서 만들거나 이메일로 자동 권한 부여하지 않는다.

Python socket/DNS guard 자체 probe PASS, 본 전체 회귀의 외부 연결 시도0·실제 Supabase/LLM/임베딩 호출0·실제 지출0. C libpq는 Python guard 범위 밖이므로 local_test의127.0.0.1 DSN 강제를 함께 사용했다. 실제 DB 접속은 기존 격리 로컬PG뿐이다. 실제 자격증명·계정·Secret/environment 변경·유료 서비스·배포는 없다.

새/변경 파일의 강한 private-key/AWS/provider-key 패턴0건, 합성 fixture 출처/파일 hash를 대조했다. 이는 포괄 개인정보 부재 인증은 아니다. 기존 원본·fixture·테스트·과거 증거·인간 검토 파일을 변경/삭제하지 않았다. 판정 생성/승인0, 기존 인간 검토0/10·0/40과 NOT_VERIFIED/NOT_REQUESTED를 유지한다. source hash 최종 일치·개별 파일 목록은 보존 JSON과 CHANGE_MANIFEST로 확인한다.

## 6. 운영 연결의 미완료 조건

이번 결과는 production/G1-C/D 완료가 아니다. preflight의 `jwt_verification=FAKE_JWKS_IMPLEMENTED_NOT_CONNECTED`, Auth runtime/운영 provisioning 미실증 및 기존 PG/Storage/proxy/cloud worker/운영 backup blocker를 유지한다.

실제 Supabase 연결 전에 별도 사용자 승인과 다음 확인이 필요하다:

1. 승인된 프로젝트/계정·asymmetric signing algorithm·JWT/JWKS claim/field·키 교체 호환. 현재 HS256/custom-domain/다중 audience 프로필은 지원하지 않으며 자동 fallback하지 않는다.
2. 실 JWKS/password 전송의 고정 endpoint·CA/TLS·SSRF/redirect·timeout/429·bounded cache/회전·실패 정책과 factory/runtime wiring. 이번에는 정확한 Fake만 허용한다.
3. 운영자 권한·허용된 provider subject·최초 기관/관리자 승인·초대/회수 절차, server membership DB 최소권한/RLS·감사·secret manager.
4. **provider-only ban/logout/키 제거를 이미 발급된 BFF 세션에 즉시 반영하는 동기화는 미구현**이다. 기존 BFF는 로컬 만료까지 유지될 수 있고 로컬 DB 비활성/철회는 즉시 검사한다. 운영 전 TTL/이벤트/관리 철회 정책을 정해야 한다.
5. 동일 출처 HTTPS/프록시·쿠키/CSRF·업로드/요청 제한, API/worker 동일 DB/bucket, 별도 비용 원장 포함 통합백업/PITR·암호화·복구 목표 실증.

다음 구현 제안은 **운영 wiring·동일 출처 HTTPS/proxy/요청 제한의 오프라인 계약**이다. 실제 자원 생성/외부 연결·배포나 후속 구현을 이번 종료 후 자동 수행하지 않는다.

## 7. 시간·종료 상태

08:47:49 UTC의 Storage 보존 커밋 이후 약16분(사전 프로젝트·보존 검사 제외), 전체 회귀 명령290.226초. 정확 종료 시각/분과 Git·PG fixture 상태는 PRESERVATION.json에 남긴다. 로컬 PostgreSQL 검증 컨테이너만 종료하고 기존 named volume·DB/백업 사본·과거 증거를 보존한다. 새 Auth 작업은 미커밋 검토 후보이며 다음 단계로 진행하지 않는다.
