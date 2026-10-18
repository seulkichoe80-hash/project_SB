# 운영 설정·시작 계약과 오프라인 사전 검사

범위: 배포 준비 1단계. FR-15/18·NFR 보안/영속성 및 TEST_PLAN WEB-02/04/05/06/07에 연결한다. **실제 DB/Auth/Storage 연결·백업 복원·배포 준비 완료를 판정하지 않는다.** G1-C/D는 미완료다. 기존 LLM·임베딩 실제 호출 차단과 인간 검토 PROVISIONAL/NOT_VERIFIED를 유지한다.

## 명령과 판정

```bash
# 현재 프로세스의 허용된 설정 키만 검사. .env를 자동으로 읽지 않는다.
.venv/bin/python -B scripts/validation/deployment_preflight.py --role api

# 별도 설정 파일은 환경 변수 이름 → 문자열 값의 JSON 객체다.
# 실제 키를 커밋하지 않는다. 아래 경로의 파일은 운영자가 별도 준비한다.
.venv/bin/python -B scripts/validation/deployment_preflight.py --config-json /secure/config/api.json --peer-config-json /secure/config/worker.json --role api
```

첫 명령은 클라우드 설정이 없는 현재 local 환경에서 exit 0/LOCAL_CONTRACT_VALID다. 두 번째 명령은 파일이 실제 준비되어야 실행 가능하며 예시 경로를 생성하지 않았다. JSON의 중복/미등록 키·비문자열 값·64KiB 초과·symlink·읽기/파싱 오류를 안전한 오류로 거부한다. 시스템 환경 전체의 무관한 변수는 무시한다. 환경 변수 값이나 파일 내용·경로를 진단에 출력하지 않는다. API-worker 비교는 --peer-config-json을 제공한 때에만 수행하며, 실제 두 배포가 같은 설정을 사용하는지 확인한 것은 아니다.

| exit | 상태 | 뜻 |
|---|---|---|
| 0 | LOCAL_CONTRACT_VALID | local/test 계약상 시작 가능. 실제 DB/공급자 연결은 NOT_CHECKED, 공개 배포 가능 아님 |
| 1 | INVALID | 필수 키/형식/정책/역할/peer 불일치 또는 설정 파일 오류 |
| 2 | BLOCKED | production 설정 형식은 VALID이나 코드가 보유한 미구현/미검증 항목으로 시작 차단 |

모든 결과는 production_ready=false, connectivity=NOT_CHECKED다. operator가 `adapter_ready=true` 같은 값을 넣어 통과시킬 수 없다. JSON unknown key는 거부하며 환경에서도 준비 상태를 바꾸는 flag는 구현하지 않았다. production은 이번 코드에서 절대 startup_allowed=true가 되지 않는다. 설정 오류와 미구현 adapter는 구분하며 실제 실증이 있어야 향후 readiness 구현을 변경한다.

## 설정 구조

apps/api/runtime_settings.py의 strict/frozen Pydantic RuntimeSettings가 단일 계약이다. 기존 AuthSettings의 origin/cookie 규칙, SupabaseSettings의 고정 HTTPS project/key 검사, formats.MAX_BYTES의20MiB를 재사용한다. URL/secret은 SecretStr·repr 제외, ValidationError는 입력을 제외한 정적 키/코드만 변환한다. raw 설정/유효성 오류를 로깅하지 않는다. SupabaseSettings 생성은 형식 검사만 수행하며 HTTP transport를 생성하거나 요청하지 않는다.

| 환경 변수 | 기본/요건 |
|---|---|
| APP_ENV | local/test/production. 미설정 local, 과거 development는 local alias. 그 외·빈 값 거부 |
| APP_ROLE | api/parse_worker/chunk_worker/workflow_worker. production 필수. local/test 미설정은 해당 실행 경로의 역할 |
| DATABASE_BACKEND | local/test sqlite, production postgresql 필수 |
| DATABASE_URL | production 필수 SecretStr. postgresql://, user/password, 공개 형태 host, DB name, 포트5432/6543 또는생략, 정확 sslmode=verify-full. 로컬/private IP·localhost/internal·중복 query·다른 query 거부 |
| STORAGE_BACKEND | local/test local, production supabase 필수 |
| STORAGE_PROJECT_URL, STORAGE_BUCKET, STORAGE_SERVER_KEY | production 필수. Auth와 같은 project URL, 제한 bucket명, 별도 서버키(16–4096 printable ASCII, publishable key 금지). 실제 키 효력·권한은 미확인 |
| STORAGE_PRIVATE | true, production 명시 필수. 선언일 뿐 실제 bucket ACL 확인 아님 |
| AUTH_PROVIDER | local/test deny_all 또는mock, production supabase. 기본 deny_all |
| SUPABASE_PROJECT_URL, SUPABASE_AUTH_API_KEY | production 필수. 기존 20문자 project.supabase.co HTTPS·publishable/legacy anon 형식 재사용. legacy JWT payload는 gateway 설정 확인용이며 신원 인증 아님 |
| APP_ORIGIN | 기본 https://localhost. production은 공개 형태 HTTPS host, 기본443 또는 명시443만. 경로/쿼리/fragment/userinfo 금지 |
| SECURE_COOKIE, CSRF_ENABLED, SAME_ORIGIN_PROXY | 기본true. production에서 명시true 필수. secure=false는 local/test의 http loopback만 |
| TRUSTED_PROXY_HOPS | 기본0, production 명시1–2. 실제 proxy header middleware는 미구현/미검증이므로 production 차단 |
| MEMBERSHIP_POLICY | server_active_single만. production 명시 필수. metadata/클라이언트 role 금지 |
| MAX_UPLOAD_BYTES | 기본20MiB, 1..20MiB |
| REQUESTS_PER_MINUTE | 기본30, 1..600 |
| REQUEST_TIMEOUT_SECONDS | 기본60, 1..120 |
| REAL_LLM_ENABLED, REAL_EMBEDDING_ENABLED, PAID_CALLS_APPROVED | 기본false, production 명시false 필수. true는 모든 환경에서 거부 |
| LLM_BUDGET_MICRO_USD, LLM_REQUEST_CAP_MICRO_USD | 기본0, 현재 0만 허용. 예산이 제안돼도 지출 승인 아님 |
| LLM_MAX_INPUT_TOKENS, LLM_MAX_OUTPUT_TOKENS, LLM_MAX_RETRIES | 기본16000/2048/1. 범위1..100000/1..32768/0..1 |
| BACKUP_STRATEGY | local/test unconfigured 가능. production coordinated_private_db_objects 명시 필수 |
| RESTORE_RPO_HOURS, RESTORE_RTO_HOURS | production 명시1..24. 목표값이며 복구 시험 결과 아님 |

숫자는 부호/소수 없는 최대10자리 decimal, boolean은 정확 true/false다. 값 양끝 공백을 조용히 보정하지 않는다. 공개 hostname 형식 검사는 DNS·인증서·공급자 실소유를 검증하지 않는다. 향후 전송 구현에서 고정 endpoint/SSRF/CA trust 검증을 추가로 유지해야 한다.

local/test에서 cloud DB/Storage/Auth 설정이나 미사용 cloud 자격증명이 들어오면 조용히 SQLite/deny-all로 fallback하지 않고 거부한다. 기존 local 테스트의 명시 factory MockProvider/AuthSettings 주입은 유지된다. AUTH_PROVIDER=mock만 입력해 모의 사용자가 생성되거나 로그인 가능해지는 기능은 없다. 실제 cloud 자격증명을 local .env로 넣어 시험하지 않는다.

MAX_UPLOAD_BYTES/요청 제한/토큰·백업 목표는 **배포 계약 검증**이다. 이번에는 기존 업로드·rate-limit·worker 동작에 동적으로 적용하지 않는다. 기존 실제20MiB·로그인 제한 등은 그대로다. proxy의 더 낮은 upload cap, API rate-limit 미들웨어, 복구 목표 준수는 별도 구현/실측 대상이며 production blocker를 유지한다.

## 시작 경로

- API: 기존 `apps.api.main:create_app()` 첫 단계에서 api 역할 확인. 표준 `apps.api.main:app`도 같은 guard를 통과해야 한다. production을 환경 변수로 명시하면 Repository·원본 파일 생성 및 공급자 transport 구성 전에 차단된다.
- 파싱/청킹/업무 worker: 기존 CLI의 인수 파싱 직후, Repository·원본 생성 전에 각 역할을 검사한다. --help는 설정 검사 없이 도움말만 제공하며 실행하지 않는다.
- APP_ROLE이 실행 경로와 다르면 local/test도 차단한다. API와 worker를 같은 APP_ROLE로 시작하지 않는다. local/test에서 역할 미설정이면 기존 CLI를 그대로 사용할 수 있다.
- 설정 형식이 맞아도 현재 production의 PostgreSQL repository/auth/jobs/budget, private object adapter, auth bootstrap, proxy/limit/header 실증, cloud worker runtime, DB+객체 복구 실증이 없으므로 차단한다. 입력된 Supabase 설정을 실제 transport로 주입하는 운영 wiring을 이번에 추가하지 않는다.

API/worker 쌍은 환경·backend·bucket/project·origin·cookie/CSRF·membership·upload·실모델/예산·백업 목표와 DB target을 비교한다. 최소권한을 위해 DB user/password가 달라도 host/port/database가 같으면 허용한다. pooler와 direct endpoint가 다른 경우에는 자동 동등 판정하지 않고 현재는 mismatch다. 실제 동일 DB identity를 검증하는 확장은 별도다. 쌍 비교 통과도 임의 기관 접근이나 실권한 검증 완료가 아니다.

## 안전성과 검증 범위

직접 production 자격증명 주입·서비스 가입·외부 접속은 하지 않는다. 테스트 설정은 합성 placeholder만 사용한다. socket/DNS 및 httpx.Client 생성을 차단한 단위 검사, 입력값 marker의 repr/JSON/예외/CLI stderr 누출 검사, 잘못된 역할/API module import/worker CLI의 DB 파일 생성 전 차단을 확인한다. 기존 인증/세대/EvidenceRef·lease/재시도·원본 회귀는 전체 backend 실행으로 확인한다. UI·DB schema·lockfile은 변경하지 않는다.

다음 구현은 PostgreSQL adapter/auth·job·budget 트랜잭션 → private Storage와 대사/백업 → 운영 Auth provisioning/wiring 및 proxy/worker 실제 시작 계약 순서다. 실제 Auth API 호출·리소스·비용·공개 전환은 각 승인 후만 가능하다. 이번 작업 종료 뒤 자동 진행하지 않는다.
