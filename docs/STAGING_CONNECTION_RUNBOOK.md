# 실제 스테이징 연결 준비표

사용자 요청 범위는 GitHub 보존과 실행 준비다. 실제 연결·마이그레이션·키 주입·유료 신청·공개 배포·production 차단 해제는 이번에 하지 않는다. 기존 PRD/AGENTS/TASKS/TEST_PLAN과 [공식 제약](DEPLOYMENT_STAGING_PREP.md), [HTTP 계약](DEPLOYMENT_STORAGE_HTTP.md)을 따른다. 추가 Fake 기능은 만들지 않는다.

## 현재 연결 가능 범위와 차단

| 구성 | 현재 근거 | 실제 스테이징 상태 |
|---|---|---|
| React | 기존 정적 빌드·합성 UI/HTTP 증거 | 설정/브라우저 경로 검증 준비 가능. 이번 배포 안 함 |
| PostgreSQL | psycopg 전용 DB/repository/auth/job/budget, 로컬 실DB 회귀 | 원격 DSN 검증 코드는 있으나 운영 factory/권한/연결/백업 미실증. 기동 BLOCKED |
| Storage | Local 기본, Fake 복구·정확 MockTransport HTTP | live network transport 없음. ACL·목록 API·원격 orphan 대사/복구 미확인. BLOCKED |
| Auth | 기존 사용자 조회 HTTP 계약, Fake JWT/JWKS·상태 재검증, DB membership | 운영 JWT/JWKS/password/status 경로·초기 등록 절차의 실증 미완료. BLOCKED |
| API/worker | 명시 Local/Fake wiring, loopback TLS/lease 회귀 | 독립 cloud worker의 DB/schema/object store 설정과 원격 ingress 미연결. BLOCKED |
| LLM/embedding | Fake와 예산 원장 | 실제 연결/지출 모두 미승인. false/0 유지 |

**계정과 키만 넣으면 배포되는 상태가 아니다.** 현재 `APP_ENV`는 local/test/production만 받으며 staging 값은 지원하지 않는다. 운영 성격의 스테이징은 production 계약을 만족해야 하고, test/local 또는 loopback 테스트 옵션으로 우회하지 않는다.

## 사용자 준비 체크리스트 — 생성/변경은 후속 승인 후

| 담당/서비스 | 준비할 항목 | 필요한 확인 |
|---|---|---|
| 사용자 / Supabase | 운영과 분리된 staging 프로젝트, region·요금제·리소스 한도, 프로젝트 소유자/MFA·복구 접근자 | 실제 계정 미조회. 유료 업그레이드/옵션 금지, 사용 조건·중단 정책·비용 상한 확인 |
| DB 관리자 | Dashboard의 DB host/port/database, migration 전용·runtime 최소권한 자격증명, TLS 검증에 필요한 신뢰 CA | migration과 API/worker 역할 분리. 비밀번호/DSN은 secret manager에서만 취급 |
| Storage 관리자 | private originals bucket, 최대 object/global 크기, PDF/HWPX 허용 정책, 실제 public=false·ACL | service key는 RLS를 우회하므로 서버 기관/역할 검사가 필수. 브라우저 anon/auth 직접 접근은 허용 목록 시험으로 확인 |
| Auth 관리자 | project issuer·JWKS·audience, 허용 알고리즘/rotation, 회원 초대/삭제·ban·상태 조회 정책 | 공개 signup의 필요 여부를 명시 결정. email 도메인/metadata로 관리자 자동 부여 금지 |
| 기관 운영자 | 합성 기관 A/B와 manager/reader 테스트 계정, 초기 관리자 subject UUID/issuer 대조 | 개인정보 없는 표시명. `bootstrap_initial_administrator`의 명시 확인 절차만 사용; 공개 bootstrap API/자동 생성 없음 |
| Render 운영자 | API 1개 + parse/chunk/workflow worker 각1개, region·상시 실행·최소 RAM/CPU·egress·healthcheck·timeout·plan | 현재 worker3종을 단일 프로세스에 임의 통합하지 않음. API/worker 로그에 키/원문 금지. 자동 배포 off |
| 프런트/DNS 운영자 | Vercel static 또는 승인된 대안, custom frontend/API domain·HTTPS·DNS, 브랜치 배포 연결 off | 같은 site 후보라도 same origin은 아님. 아래 A/B 경로를 실제 한도 확인 후 결정 |
| 백업 운영자 | DB+객체 bytes+manifest+Auth identity 관계의 보관/암호화·접근자·복구 대상·RPO/RTO | Supabase DB 백업에 Storage bytes가 포함된다고 가정하지 않음. 복구 리허설 필요 |

현재 최신 Render/Vercel 요금·실계정 quota는 미확인이다. 비용 총액을 확정하지 않는다. 무료 프로젝트의 sleep/pause·worker 제공 조건을 장기 시연 보장으로 취급하지 않는다. 향후 승인에는 project/region/plan과 월 상한·비용 알림 수신자를 포함한다.

## 환경 변수·비밀 주입 계약

아래는 **현재 `apps/api/runtime_settings.py:ENV_FIELDS`에 등록된 이름**이다. 실제 값을 이 문서·Git·PR·채팅에 넣지 않는다. secret manager/서비스 secret UI에서만 승인된 접근자가 주입한다. 명령행 인자나 CI 출력으로 비밀을 전달하지 않는다.

| 현재 키 | 준비 계약 |
|---|---|
| `APP_ENV`, `APP_ROLE` | 운영 스테이징은 production; role은 api/parse_worker/chunk_worker/workflow_worker. 이번에 주입/시작하지 않음 |
| `DATABASE_BACKEND`, `DATABASE_URL` | postgresql, Dashboard에서 확인한 대상. TLS `sslmode=verify-full`. 현재 URL validator는 이 query 하나만 허용하므로 임의 query를 추가하지 않음 |
| `STORAGE_BACKEND`, `STORAGE_PROJECT_URL`, `STORAGE_BUCKET`, `STORAGE_SERVER_KEY`, `STORAGE_PRIVATE` | supabase, 고정 project URL/bucket, 서버 전용 key, true. 실제 HTTP 전송 활성화와 키 종류 계약은 미구현/미확인 |
| `AUTH_PROVIDER`, `SUPABASE_PROJECT_URL`, `SUPABASE_AUTH_API_KEY` | supabase와 Storage의 동일 project. Auth 공개 API key와 Storage 서버 key는 구분. provider 토큰은 browser 응답에 전달 금지 |
| `APP_ORIGIN`, `SECURE_COOKIE`, `CSRF_ENABLED`, `SAME_ORIGIN_PROXY`, `TRUSTED_PROXY_HOPS` | 정확한 HTTPS origin, Secure/CSRF true, 검증된 ingress와 홉 수. 현행은 same-origin 프록시 계약이며 B 경로를 설정만으로 지원하지 않음 |
| `MEMBERSHIP_POLICY`, `MAX_UPLOAD_BYTES` | server_active_single, 최대20,971,520 bytes. HTTP multipart body/프록시 한도는 별도 검증 |
| `REQUESTS_PER_MINUTE`, `REQUEST_TIMEOUT_SECONDS` | 현재 기본30/60초와 plan 한도 대조. worker lease/job timeout과 혼동 금지 |
| `REAL_LLM_ENABLED`, `REAL_EMBEDDING_ENABLED`, `PAID_CALLS_APPROVED` | 모두 false |
| `LLM_BUDGET_MICRO_USD`, `LLM_REQUEST_CAP_MICRO_USD` | 모두0. 공급자/공개 합성 입력/비용 승인은 별도 |
| `LLM_MAX_INPUT_TOKENS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_MAX_RETRIES` | 기본16000/2048/1은 오프라인 계약이며 과금 승인이 아님 |
| `BACKUP_STRATEGY`, `RESTORE_RPO_HOURS`, `RESTORE_RTO_HOURS` | coordinated_private_db_objects와 승인된 목표. 값 입력은 복구 검증 완료를 뜻하지 않음 |

추가 연결 지점: `PostgresDatabase.schema`(application/budget 별도), `StorageHTTPTransport.gateway_key`, 실제 JWKS/상태 전송 설정, API/worker live factory는 현재 ENV_FIELDS만으로 연결되지 않는다. 가상의 새 env 이름을 현재 지원한다고 안내하지 않는다. 이 mapping/secret 최소권한 설계가 다음 구현 대상이다. `VITE_*`는 전부 공개 빌드 값으로 비밀을 넣지 않는다. API worker에는 Auth admin/초기 등록 권한을 배포하지 않으며 Storage 읽기 자격증명의 최소권한 실증이 추가로 필요하다.

## DB migration 실행 순서 — 이번 실행 금지

1. 승인된 staging 대상/소유자/region과 TLS를 확인한다. direct IPv6 또는 검증된 session pooler5432를 선택한다. transaction pooler6543의 prepared statement 호환은 미검증이다. endpoint를 추정하지 않는다.
2. 읽기 전용 대상 확인 후 DB+객체+manifest backup을 별도 보존한다. 빈 새 schema와 최소권한 migration role을 준비한다. Supabase 관리 `auth/storage/public` schema를 덮어쓰지 않는다.
3. 예시 `sb_application_staging` schema에서 `PostgresDatabase.migrate('application')` → `migrations/postgresql/001_application.sql` 적용/verify. auth/doc/version/parse/chunk/workflow/검색 테이블과 transaction guard 포함. checksum을 기록한다.
4. 별도 예시 `sb_budget_staging` schema에서 `migrate('budget')` → `001_budget.sql` 적용/verify. **application과 budget은 같은 version1을 사용하므로 같은 schema에 혼합하지 않는다.**
5. application repository의 `StorageRegistry.migrate()`로 `migrations/storage/001_private_storage.sql`을 추가 적용/verify한다. 기존 table·version/checksum 충돌은 중단하며 임의 adopt/drop/reset하지 않는다.
6. 승인된 operator가 확인된 issuer/subject로 최초 합성 기관/관리자를 명시 bootstrap한다. A/B manager/reader 멤버십·비활성 전이를 대조한다. email/metadata에서 역할을 생성하지 않는다.
7. API/worker가 동일 database·application schema·bucket/project와 동일 계약 버전을 참조하고 budget schema도 동일 대상인지 검사한다. 서로 다른 DB 사용자 사용은 가능하지만 권한/격리 시험이 선행한다.
8. 승인된 합성 데이터를 새 ID로 등록한다. 기존 SQLite/원본/fixture를 자동 import 또는 덮어쓰지 않는다. 복구 시 새 대상에 restore→SHA/기관/버전/manifest→세션 철회→검토 후 전환한다. destructive down migration은 하지 않는다.

현재 `scripts/validation/postgres_migrate.py`는 **loopback local_test=True 전용**이다. 이를 cloud DSN으로 실행하거나 코드의 local_test 제한을 완화하지 않는다. 운영 migration runner/권한 분리/verify·복구 계획은 아직 구현해야 하므로 위 순서는 실행 설계이며 사용 가능한 cloud CLI라고 주장하지 않는다.

## Render·프런트 실행 경로

현재 개발 명령은 확인된 기존 entry point다. **운영 실행 레시피로 승인된 것은 아니다.**

- API 표준 진입점: `apps.api.main:app`(uvicorn). 승인 후 Render PORT/0.0.0.0·readiness·trusted ingress 적용이 필요하며 현재 production guard가 먼저 차단한다.
- 독립 worker: `python -m apps.api.worker`, `python -m apps.api.chunk_worker`, `python -m apps.api.workflow_worker`. 기존 CLI는 data-dir/institution-id가 필요하고 PostgreSQL 옵션은 loopback seam이다. CLI에 key/DB URL을 넣지 않는다. 다기관 worker 배치/스케줄은 별도 설계하며 한 institution-id가 모든 기관을 처리한다고 가정하지 않는다.
- 프런트: apps/web에서 잠금파일 기반 `npm ci`, `npm run typecheck`, `npm run build`; 출력 dist. 현재 상대 `/api` 호출과 CSRF/session 계약을 유지한다. 이번 빌드/배포는 실행하지 않는다.
- health/readiness는 비밀·기관/문서 정보를 반환하지 않고 DB/원격 준비 상태를 구분해야 한다. 실제 vendor healthcheck/ingress 신뢰 설정이 검증되기 전 일반 forwarded 헤더 전체 신뢰 금지.

A(same-origin rewrite)는 기존 BFF를 재사용하기 쉽지만 Vercel 요청/응답 제한이 미확인이다. B(동일 site custom frontend/API domain 직통)는 대용량 우선 검증 후보이지만 현재 exact Host/Origin/CORS 분리 구현이 없다. Vercel 기본 domain과 onrender.com은 서로 다른 site이므로 SameSite=Lax로 cross-site fetch가 된다고 가정하지 않는다. SameSite=None만 변경하는 우회도 금지한다. C(Storage 직접 upload)는 새 승인 intent/finalize·capability·orphan 계약이 필요하여 이번 범위가 아니다. 실제 경로는 한도·쿠키·비용 검증 후 사용자와 확정한다.

## 단계별 검증 계획 — 승인된 isolated staging에서만

| 순서 | 입력/실행 | 통과 증거 / 중단 조건 |
|---|---|---|
| 0 offline | 정확한 commit/의존성, production/API-worker peer preflight | 형식 VALID와 실제 연결 VERIFIED 구분. 현재 code-owned BLOCKED는 유지 |
| 1 연결 | 선택한 project의 TLS DB 단발 확인, Auth JWKS 공개 key, private bucket 권한 | 대상/리전/인증서·허용 key·최소권한 확인. provider data/secret은 로그 금지 |
| 2 작은 원본 | 합성 PDF/HWPX 수KiB~100KiB, API 등록→원격 read-back | 원본 SHA/크기·기관/버전·private 익명 접근 거부·DB 게시 일치 |
| 3 크기 | 1MiB→5MiB→10MiB→20MiB-1→정확20MiB→20MiB+1 | 각 크기 upload와 download 양방향 측정. multipart 전체 body overhead/메모리/응답·timeout·plan 제한 포함. 초과는 거부, 부분 성공으로 게시 금지 |
| 4 복구 | 중단/응답 유실/429/503·동일 원본 재시도·DB 저장 실패 | probe-first·hash/size·최대 재시도·backoff/Retry-After·unknown 보류·orphan 격리. 무조건 POST 반복 금지 |
| 5 세션 | manager/reader/A/B·expired/위조 JWT·membership 해제·logout | HttpOnly/Secure/SameSite·host-only cookie, fetch credentials, 정확 Origin/Host·CSRF. wildcard CORS/타기관/구버전/세션 철회 우회0 |
| 6 E2E | 합성 PDF/HWPX→parse worker→chunk worker→활성화→workflow worker→지도/근거/서식/ReviewIssue | 원본 불변·EvidenceRef 재해결·기관/버전/세대 일치, NOT_VERIFIED/NOT_REQUESTED 유지, 실제 AI 없이 오프라인 후보임을 표시 |
| 7 재시작 | API/worker 재시작·lease 만료/재claim·DB 재연결 | 같은 데이터·job/generation·중복 완료 방지·새 세션 정책 보존. API 재시작을 데이터 영속성 증거와 혼동 금지 |
| 8 복구 리허설 | DB+객체+manifest를 새 isolated 대상으로 복원 | checksum/버전/기관/원본 SHA·lease/예산 hold·세션 철회, 실측 RPO/RTO. 실패 시 공개 전환 중단 |

표준 upload 공식 자료는6MB 초과에 resumable을 권장한다. Mock20MiB PASS는 실제 standard POST의 안정성 보장이 아니다. 실패 원인부터 분석하고 A/B 경로·상한 또는 별도 TUS 단계로 결정한다. 실제 bytes가 외부로 나가는 단계는 합성 입력 목록·SHA·용량·호출 횟수·비용 상한 승인을 먼저 받는다.

## production preflight BLOCKED 해제의 필요조건

현재 code-owned 여섯 blocker는 환경 변수나 관리자 체크박스로 해제할 수 없다. 이번에 변경하지 않는다.

| 현재 blocker | 해제 전 필요한 구현/증거 |
|---|---|
| postgresql_production_runtime_not_wired | 운영 factory·schema/role·migration/verify·TLS DB·API-worker 대상 일치·동시성/재시작 |
| private_storage_production_transport_not_wired | live HTTP allowlist/timeout·private ACL·공식 inventory·원격 orphan/복구·실제 원본 hash |
| production_auth_runtime_and_operator_provisioning_not_verified | live JWKS/상태 조회·key rotation·issuer/aud/expiry·명시 bootstrap·membership·철회/장애 거부 |
| vercel_render_edge_trust_limits_and_https_not_verified | 선택 경로의 호스팅 제약·정제 ingress·Host/Origin/CSRF/cookie·20MiB 양방향 |
| worker_cloud_runtime_not_implemented | 독립 cloud worker 설정·공유 DB/Storage·기관 범위·claim/lease/retry·kill/restart |
| coordinated_backup_restore_not_verified | DB+bytes+manifest·Auth identity·원장·새 대상 복구·RPO/RTO |

위 항목의 구현과 오프라인/로컬 회귀만으로 실제 cloud 실증 완료가 되지 않는다. 승인된 비공개 검증을 위한 제한된 실행 방식도 별도 설계해야 하며 public production guard를 단순 제거해 시험하지 않는다. 공개 전환은 결과를 검토한 뒤 별도 승인을 받는다.

## 사용자 승인 묶음과 다음 최소 실행 단위

1. **다음 준비 단위:** 운영 전용 migration/factory와 현재 설정의 누락 mapping을 코드로 연결하는 범위를 확정한다. 추가 Fake 시나리오가 아니라 실제 전송이 들어갈 경로를 준비하되 외부 호출·guard 해제 없이 검토 가능한 변경으로 만든다. 이번에는 실행하지 않는다.
2. **최초 실제 연결 승인:** 사용자 소유의 특정 staging project/region·합성 입력 목록/SHA·조회/쓰기/migration 범위·호출 횟수·시간·예산 상한·cleanup/backup 담당자를 지정한다. secret은 안전한 설정 화면에만 입력한다. Auth/Storage/DB는 각 대상/권한 범위를 명시한다.
3. **호스팅/비용 승인:** 서비스/요금제·API/worker 개수·domain과 upload 경로·월 상한을 확정한다. 자동 배포는 계속 off로 둔다.
4. **제한적 E2E와 공개 승인:** 검증 결과·복구·격리·secret 검사를 확인한 후 별도 공개 승인을 받는다. GitHub push/PR 승인은 Supabase 연결·지출·배포 승인과 다르다.

LLM/embedding은 이 승인 묶음에도 자동 포함하지 않는다. 사용자에게서 실제 모델·데이터 범위·예산 승인을 별도로 받기 전 false/0이다. 인간 검토 결과를 생성하거나 승인하지 않는다.

## 후속 구현 상태: 공통 Factory·로컬 Runner

[Factory·Runner 통합](RUNTIME_FACTORY_MIGRATIONS.md)이 공통 API/worker 생성 경로와 별도 schema MigrationPlan, ordered apply/verify, 동시 잠금/실패 재개를 추가한다. 새 CLI는 runtime_migrate.py이며 기존 postgres_migrate.py와 함께 **격리 loopback 실행만 허용**한다. 위의 운영 migration/factory·실계정 전송·설정 주입 준비 항목이 전부 해제된 것은 아니다. 실공급자/production6개 blocker와 사용자 승인 조건은 그대로 유지한다.
