# 실제 스테이징 연결 전 최종 게이트

GitHub 보존·연결 준비 문서이며 계정 생성/설정 변경/자격증명 등록/외부 공급자 호출/유료 신청/배포/production 해제 승인이 아니다. [기존 실행 준비표](STAGING_CONNECTION_RUNBOOK.md), [Factory 계약](RUNTIME_FACTORY_MIGRATIONS.md), PRD/AGENTS/TEST_PLAN의 원본·기관 격리·검증 경계를 유지한다. 사용자 작업과 코드 작업을 아래와 같이 구분한다.

## 상태 정의와 구성별 판정

- **구현 완료:** 명시된 local/Mock 범위의 코드와 실행 증거가 있다. cloud 성공을 뜻하지 않는다.
- **사용자 설정 필요:** 승인된 소유 계정/프로젝트/도메인/권한/secret을 사용자가 준비해야 한다. 이 문서 작성 중 실제 설정은 하지 않는다.
- **실제 연결 검증 필요:** 설정 형식 확인과 별개로 승인된 실제 대상에서 TLS/권한/복구/E2E를 실행해야 한다.
- **구조 변경 필요:** 현재 생성/권한/입출력 경계의 코드가 해당 운영 경로를 아직 지원하지 않는다.
- **BLOCKED:** 앞 조건이 충족되지 않아 해당 단계의 시작/공개 전환을 허용하지 않는다. env flag나 빈 승인 체크로 해제하지 않는다.

한 구성에 여러 상태가 동시에 적용될 수 있다.

| 구성 | 구현 완료 범위 | 사용자 설정 필요 | 필수 코드/구조 변경 | 실제 연결 검증 필요 | 현재 |
|---|---|---|---|---|---|
| DB/Runner | 로컬 실PG repository·동시성·별도 schema·ordered apply/verify·checksum·재시작 복구 | staging project/DB role/endpoint/CA·application/budget schema | Runner의 승인된 원격 실행 정책·factory/env mapping·최소권한 migration/runtime 분리 | 실제 TLS/권한/pool/동시성·schema/데이터 보존 | BLOCKED |
| Storage | Local/Fake·exact Mock HTTP immutable upload/download·hash/size·부분 실패 | private bucket·한도·server/gateway key 종류·접근정책 | live transport 선택·공식 inventory/응답 계약·원격 orphan/backup·키 mapping | private ACL·익명/타기관 거부·원본 read-back·실제 장애 복구 | BLOCKED |
| Auth | Fake JWT/JWKS 검증·BFF·DB membership/bootstrap·세션 계약 | issuer/JWKS/audience/계정·초대·rotation·운영자 | live JWKS/password/계정상태/철회 선택·bootstrap 운영절차 | 실제 issuer/aud/expiry·rotation·비활성/탈퇴/로그아웃·DB 권한 | BLOCKED |
| API/worker | 공통 Factory·역할/peer 검증·독립 로컬 worker/lease | Render 서비스/region/plan·기관 범위·공통 저장소 | production factory와 cloud worker/secret/기관 배치·readiness/ingress 연결 | API/worker 동일 DB/schema/bucket·kill/restart/중복 완료 거부 | BLOCKED |
| 프런트/HTTPS | React 기존 MVP·상대 /api·로컬 proxy/쿠키/CSRF 증거 | domain/DNS·HTTPS·Origin/Host·프록시 선택 | B 선택 시 API Host/브라우저 Origin 분리·exact credentialed CORS·클라이언트 base URL, A면 검증된 ingress 연결 | 실제 Secure/HttpOnly/SameSite·Origin/CSRF·20MiB 양방향 | BLOCKED |
| 백업/복구 | Fake manifest/복원·로컬 실DB restart | 별도 암호화 보관/권한·RPO/RTO·복구 담당자 | 원격 DB+객체 bytes+manifest/Auth/원장 coordination | 새 대상 실제 복원·원본/권한/job/hold·실측 RPO/RTO | BLOCKED |
| AI/embedding | 기존 Fake·평가·비용 원장 | 실제 연결/예산 미승인 | 별도 공급자 설정/실전송/평가 단계 | 인간 의미 검토와 실제 모델 평가 | 이번 제외, false/예산0 |

## 사용자 계정·설정 체크리스트

아래는 **후속 승인 후** 사용자가 콘솔에서 수행할 절차다. 실제 secret·원본·개인정보를 Git/PR/이 문서/채팅에 입력하지 않는다. 무료 plan이라도 프로젝트 생성/외부 전송 승인은 별도이며 유료 선택·옵션 활성화는 금지 상태다.

### Supabase 프로젝트

1. 소유자·복구 담당자와 MFA를 준비한다. 기존 운영 프로젝트와 구별되는 staging용 project/organization·region·plan을 선택하고 비용/자동 과금/중단 조건을 확인한다. 실제 최신 요금·quota는 아직 계정에서 확인하지 않았다.
2. 프로젝트 생성 승인 후에만 콘솔의 New project 절차로 생성하고 DB password를 안전한 secret manager에 저장한다. 예제 password나 실제 값을 코드에 넣지 않는다.
3. 생성 완료/가용 상태를 확인하고 project reference·DB host/port/database·issuer·JWKS·Storage URL을 Dashboard와 공식 자료에서 기록한다. 값은 placeholder를 실제 endpoint로 추측해 조합하지 않는다.
4. DB는 TLS verify-full/CA·IP 버전을 확인한다. direct 또는 검증된 session pooler를 우선 검토한다. transaction pooler6543의 prepared statement 호환을 통과했다고 가정하지 않는다.
5. application/budget용 별도 빈 private schema와 migration/runtime 최소권한 role을 계획한다. Supabase의 public/auth/storage/extensions 관리 schema를 변경하지 않는다. backup·복구 대상과 운영자 접근 경로도 준비한다.

### Storage private bucket·접근정책

- 전용 originals bucket을 **private**으로 만들고 public URL을 사용하지 않는다. 실제 global/bucket 파일 크기·허용 형식·경로 정책을 확인한다.
- 현행 흐름은 서버가 권한을 확인해 bytes를 전달한다. 브라우저용 anon/auth credential로 객체를 직접 읽고 쓰는 경로를 임의 허용하지 않는다. 필요한 정책만 별도 검토한다.
- service key는 RLS 우회 권한이 있으므로 private 설정만으로 기관 격리가 보장되지 않는다. 서버 membership·기관 hash 경로·version/active·SHA/size 검증은 그대로 필요하다. API와 worker 최소권한 credential의 실제 지원 범위도 확인한다.
- 브라우저에 server key/장기 signed URL/provider token을 노출하지 않는다. `sb_secret_` 같은 키 종류를 legacy bearer service key와 동일하게 취급하지 않는다. 현재 Mock adapter의 지원/거부와 실제 공급자 key 계약을 별도 확인한다.
- live inventory API와 orphan 격리·일관 backup/restore를 구현/검증하기 전 원격 업로드를 현재 후보로 게시하는 실험을 시작하지 않는다.

### Auth·기관·관리자

- 승인된 project의 issuer/JWKS/audience·허용 알고리즘·key rotation·공개 signup/초대·SMTP/plan 제한을 확인한다. JWT 유효성과 현재 계정 활성 상태는 별개다.
- 실제 Auth 테스트 계정은 초대 등 승인된 절차로 준비하며 실명/개인자료 대신 합성 표시명을 사용한다. 이메일 도메인·user metadata로 기관/manager를 생성하지 않는다.
- 확인한 issuer/subject UUID를 operator가 대조하고 `bootstrap_initial_administrator`의 명시 confirmation 절차로 최초 기관/manager membership을 만든다. 공개 bootstrap API/서버 시작 시 자동 생성은 없다.
- A/B 합성 기관, manager/reader, 비활성/탈퇴/권한변경 계정을 준비한다. JWT 삭제/ban만으로 기존 BFF 세션이 즉시 철회된다고 가정하지 않고 별도의 상태 재검증/서버 SID 철회 정책을 적용한다.

### Render·프런트·HTTPS

- API1 + parse/chunk/workflow worker 각1의 독립 프로세스 구성을 우선 준비한다. 현행 institution-id 범위와 다기관 배치 정책을 명시하고 한 worker가 자동으로 모든 기관을 처리한다고 가정하지 않는다.
- 상시 worker 제공 plan·sleep·리소스/ephemeral disk·egress·TLS termination·health/readiness·요청/응답 한도를 확인한다. 계정/서비스를 생성하거나 자동 배포를 연결하지 않았다.
- API/worker에는 같은 DB 대상·application schema·budget schema·bucket/project·계약 버전을 배포한다. migration 권한과 runtime 권한, browser auth/초기 등록 권한을 분리한다.
- 프런트는 기존 apps/web 정적 빌드를 재사용한다. VITE_*는 공개 값이며 비밀을 넣지 않는다. URL/secret mapping이 미구현인 이름을 현재 지원한다고 만들지 않는다.
- A `/api` 동일 출처 proxy의 실제 업로드/다운로드 한도는 미검증이다. B는 같은 site의 app/API custom domain 직통을 우선 검증할 후보이나 현재 exact Host/Origin 분리·CORS/base URL 코드는 없다. Vercel 기본 domain과 onrender.com의 서로 다른 site를 SameSite=Lax로 해결할 수 있다고 안내하지 않는다.
- Secure·HttpOnly·host-only·SameSite 쿠키, 정확 Origin/Host·credentialed 요청·CSRF·trusted ingress를 함께 검증한다. wildcard CORS/모든 X-Forwarded-* 신뢰/SameSite=None만 변경하는 우회는 금지한다.

## secret·환경 변수 주입

실제 주입은 승인 후 secret UI/manager에서만 수행한다. commit/PR body·명령행·화면 캡처·CI 출력에 실제 값을 넣지 않는다.

- 현재 등록 env 이름은 [기존 Runbook의 환경 변수 표](STAGING_CONNECTION_RUNBOOK.md#환경-변수비밀-주입-계약)를 따른다: APP_ENV/APP_ROLE, DATABASE_*, STORAGE_*, AUTH_PROVIDER/SUPABASE_*, APP_ORIGIN/쿠키/CSRF/proxy, MEMBERSHIP_POLICY, 제한·backup 값.
- APP_ENV에 staging 값은 없다. 운영 성격 staging은 production 계약을 통과해야 한다. local/test·`--postgres-local-test`·SB_PG_TEST_DSN을 원격 연결 우회로 쓰지 않는다.
- MigrationPlan의 application_schema/budget_schema와 Storage gateway key, live JWKS/status 전송의 production env/secret mapping은 아직 코드 작업이 필요하다. 새 변수 이름을 설정하면 동작한다고 약속하지 않는다.
- API/worker peer 검증에 실제 공통 설정을 제공해야 한다. 독립 프로세스가 설정만 없이 서로의 상태를 자동으로 발견하지 않는다.
- REAL_LLM_ENABLED/REAL_EMBEDDING_ENABLED/PAID_CALLS_APPROVED=false, 비용 cap=0 유지. 기존 비용 원장은 모의 원장이며 실제 과금 통제가 cloud 공급자에서 검증됐다는 뜻이 아니다.

## 실행 순서·승인 경계

1. **이번 완료 범위:** 기존22파일 보존/보안·해시 확인/commit/normal push/PR HEAD 확인, 문서 게이트 확정. 실제 서비스 변경 없음.
2. **필수 코드 작업:** 명시적으로 승인된 원격 factory/runner 정책과 schema/env mapping → live Storage/JWKS/상태 전송·실패 안전 처리 → inventory/backup → 선택한 ingress/클라이언트·worker 연결을 구현한다. 승인되지 않은 실제 호출은 없이 검토 가능한 변경을 만든다. 이번에 자동 시작하지 않는다.
3. **사용자 연결 승인:** 특정 project/region·plan/비용 상한·합성 입력/SHA/크기·DB/Storage/Auth별 읽기/쓰기/migration 범위·호출 횟수/기간·담당/복구 정책을 승인받는다. 계정 생성·secret 주입·실제 공급자 요청은 이 승인 전 실행하지 않는다.
4. **계정/설정 준비:** 위 콘솔 절차·최소권한·backup·domain/DNS를 수행한다. 자동 배포는 off 유지한다. 서비스 연결 승인과 유료/공개 승인을 분리한다.
5. **원격 사전 검사:** 승인된 비공개 검증 경로에서 exact endpoint/TLS/CA/role·project·bucket ACL·issuer/audience·quota를 확인한다. production guard를 제거하거나 test/local로 우회해 검사하지 않는다. 제한된 remote 검사 entry point부터 검토/승인이 필요하다.
6. **migration:** 승인된 원격 Runner가 준비된 뒤 application→별도 budget→application Storage registry apply/verify. 현재 runtime_migrate.py는 loopback 전용이므로 이 단계에서 사용 가능한 cloud 명령이 아니다. checksum 불일치는 중단하고 drop/reset/임의 overwrite하지 않는다.
7. **Auth bootstrap·소형 E2E:** 명시 기관/관리자 등록, 작은 합성 PDF/HWPX 등록→parse/chunk→활성화→workflow→지도/근거/서식/ReviewIssue→logout 차단을 확인한다. 모델은 오프라인 후보이며 NOT_VERIFIED/NOT_REQUESTED 유지한다.
8. **크기·복구 확대:** 아래20MiB 검증과 API/worker 재시작·lease/동시 claim·DB+객체 복원·세션 철회·비용 hold 보존을 검증한다. 실패 시 원인/범위를 분리하고 공개 전환을 중단한다.
9. **공개 전환:** 실제 결과·복구·기관 격리·비밀정보 검사·운영 gate를 사용자가 검토한 뒤 별도 승인한다. GitHub PR 보존이나 연결 승인은 main merge/공개 배포 승인이 아니다.

## 20MiB 업로드·다운로드 경로

현재 `main.upload`는 request.stream으로 **파일 raw body**를 받고 프런트도 File body를 전송한다. 현재 제품 API는 multipart 업로드가 아니다. 기존 계획의 multipart overhead 검토는 이후 그 방식을 채택할 때의 추가 시험이며 현재 지원처럼 표시하지 않는다.

- 작은 유효 합성 PDF/HWPX 수KiB→100KiB→1MiB→5MiB→10MiB→20MiB-1/정확20MiB/20MiB+1. bytes 상한은20,971,520이며 확장자만 바꾼 임의 padding 파일은 유효 parser 자료로 보고하지 않는다.
- upload와 원본/PDF download를 **양방향**으로 확인한다. raw body/응답 byte·SHA·메모리/시간·browser deadline·프록시/body/response/plan quota를 각각 기록한다. 가능한 content-length/streaming 경계도 확인한다.
- A는 실제 external rewrite인지 Function proxy인지 구분하고 공식 문서/실환경 증거 없이20MiB PASS로 처리하지 않는다. B는 Vercel 본문 병목을 피할 후보이나 Render 한도와 브라우저 보안 경계 검증이 선행한다.
- timeout/끊김/429/503·중복/동시 요청·업로드 후 DB 실패를 시험하고 probe-first·hash/size·unknown 보류·backoff/Retry-After·orphan 격리를 확인한다.
- 표준 Storage POST의 공식 자료는6MB 초과에 resumable을 권장한다. Mock20MiB 통과는 실제 cloud 안정성 증거가 아니다. TUS/직접 upload(C)는 새 capability/intent/finalize·다운로드 정책이 필요한 별도 구조 변경이며 이번에 구현하지 않는다.

## 변경하지 않은 production 게이트

`postgresql_production_runtime_not_wired`, `private_storage_production_transport_not_wired`, `production_auth_runtime_and_operator_provisioning_not_verified`, `vercel_render_edge_trust_limits_and_https_not_verified`, `worker_cloud_runtime_not_implemented`, `coordinated_backup_restore_not_verified` 여섯 blocker를 유지한다. settings 형식 VALID와 실제 연결 VERIFIED를 구분하며 실제6개 조건이 해소되기 전 어떤 flag/체크리스트도 기동을 허용하지 않는다.

실계정 plan·최근 가격·20MiB ingress·외부 자동배포 연동·실제 backup/복구는 아직 미검증이다. 기존 공식 source의 확인일/범위를 최신 계정의 실증으로 대체하지 않는다. 인간 검토 판정/승인도 자동 생성하지 않는다.
