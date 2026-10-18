# 배포 준비 2단계 — PostgreSQL 영속 저장

범위: **기존 SQLite 기본값을 유지하는 명시적 PostgreSQL 어댑터와 격리 로컬 검증**. Supabase 원격 DB/Auth/Storage·LLM·임베딩 호출이나 공개 배포를 수행하지 않는다. production 시작은 계속 차단하며 G1-C/D 완료로 승격하지 않는다. FR-01/05/06/07/08/14/15/18·NFR 데이터 무결성·WEB-02/04/05/06/07의 저장 계약을 재사용한다.

## 저장 경로 분석과 재사용

초기 rg 전수 조사206행과 AST 호출 목록을 별도 기록한다. 재생성 명령:

```bash
.venv/bin/python -B scripts/validation/inventory_persistence.py
```

목록은 apps/api 전체의 execute/executemany/executescript/connect/transaction/backup 호출을 포함하며, 동적 SQL도 위치를 남긴다. execute라는 비SQL 서비스 메서드도 포함하므로 호출 수를 SQL statement 개수로 오해하지 않는다. 평가/검증 스크립트의 독립 SQLite corpus는 기존 평가 재현 계약이므로 이식 대상 앱 DB와 구분해 유지한다.

| 저장·조회 경계 | 기존 직접 SQL·초기화 위치 | PostgreSQL 처리 |
|---|---|---|
| 문서/버전/업로드 intent/events | repository.py, service.py의 UnitOfWork 사용 | 공유 domain UnitOfWork + PG transaction/parameter adapter |
| 파싱/원문 blocks/attempt | parsing_repository.py | 공유 parameter SQL·fencing, PG scope trigger |
| chunks/current/search | chunk_repository.py, chunk_service.py, scored_search.py | 기존 LIKE/점수OR·현재 세대/근거 확인 유지 |
| 업무 jobs/generation/candidate/issue/form links/events | workflow_jobs_repository.py, workflow_jobs.py | 공유 SQL·원자 finish, 명시 migration 소유 |
| 기관 서식 분류 | workflow_forms_repository.py | 공유 metadata query/upsert, PG에서 constructor DDL 생략 |
| vector generation/items/current | vector_repository.py, rag_service.py | 기존 exact-cosine·원자 포인터·세대 필터 재사용. pgvector/실임베딩 추가 아님 |
| identity/org/membership/session/challenge/rate/audit | auth_store.py, auth.py, main.py의 repo.path 의존 | PostgresAuthStore와 동일 schema transaction, 기존 BFF 계약 |
| 비용 계정/job/request/attempt/event | provider_budget.py | 별도 PG schema PostgresBudgetLedger, 모의 원장 의미 유지 |
| CLI 로컬 DB 선택 | worker.py/chunk_worker.py/workflow_worker.py | 명시 loopback PostgreSQL test seam, 기본 SQLite 유지 |

schema 정의/SQLite connect/PRAGMA/backup/complete_statement는 기존 SQLite 경로에만 남는다. PG에서는 명시 migration이 소유하며 기존 constructor의 SQLite schema 실행을 호출하지 않는다. AuthService의 INSERT OR REPLACE와 repository의 OR IGNORE도 PG adapter 내부에서 명시 ON CONFLICT로 처리한다. PostgreSQL 문법을 SQLite SQL에 넣지 않는다.

## 어댑터 구조

apps/api/postgres.py:

- PostgresDatabase: redacted DSN, strict schema identifier, 로컬 test URI 검증 또는 향후 production verify-full URI 검증. import/생성 자체에는 연결이 없으며 migrate/verify/transaction이 명시 연결한다.
- PostgresRepository: 기존 DocumentUnitOfWork와 ParsingQueries/ChunkQueries를 재사용한다.
- PostgresAuthStore: 기존 검증된 AuthStore domain 메서드와 AuthService SQL을 재사용한다. API factory가 PG repository를 받으면 공유 PG AuthStore를 사용한다.
- PostgresBudgetLedger: 기존 SimulationBudgetLedger의 정수 비용·예약·불확실 보류·재정산을 재사용한다. simulation_only와 actual_spent=0 유지. 공급자 gateway는 **정확한 concrete type**으로 이 클래스만 추가 허용하며 임의 subclass/real transport는 계속 차단한다.
- PG Connection/Cursor/Row: qmark를 psycopg bind로 컴파일한다. 문자열의 ?/percent·중복 label의 위치 접근/이름 접근을 보존한다. 기존 SQL의 제한된 portable subset용이며 범용 SQLite SQL 엔진 에뮬레이터가 아니다. DDL·trigger는 전용 SQL migration이다.

DSN·원문·파라미터·raw server error는 공개 오류에 넣지 않는다. 연결 실패·constraint/statement 실패는 정적 PostgresFailure 코드로 변환한다. 운영 DB 서버의 statement/error/parameter 로그 보관·마스킹은 별도 운영 정책으로 검증해야 한다. 이번에는 합성 데이터만 사용한다.

## 동시성·무결성

각 PostgreSQL 트랜잭션은 READ COMMITTED를 명시하고, schema의 transaction_guard 단일 행을 FOR UPDATE로 잠근 뒤 domain 읽기/쓰기를 수행한다. 이 잠금은 API/Auth/parse/chunk/workflow 프로세스 모두 공유한다. transaction owner가 commit/rollback/연결 종료하면 잠금이 해제된다. guard 행이 없으면 실패한다. budget은 application과 **별도 schema**에 동일한 방식으로 격리한다.

이것은 기존 SQLite BEGIN IMMEDIATE 의미를 보수적으로 보존하는 첫 이식이다. 동일 schema의 읽기까지 직렬화되며 기관별 병렬 처리량을 보장하지 않는다. SKIP LOCKED 기반 세부 job/account 잠금은 이번에 구현했다고 주장하지 않는다. 다른 tenant/job도 같은 schema에서는 기다릴 수 있다. 향후 축소하려면 모든 document activation/retirement·generation·auth·budget 갱신 경계를 함께 재검증해야 한다. raw 외부 writer가 guard를 무시하면 서비스의 상태 fencing을 보장할 수 없으므로 운영 역할에 임의 SQL 쓰기를 허용하지 않는다.

schema FK/unique/check와 PG source_block/chunk/workflow/active-version scope trigger가 잘못된 parent 관계도 거부한다. source payload와 EvidenceRef는 TEXT canonical JSON으로 그대로 보존한다. SHA·원본 재파싱·기관/등록/활성버전/parse attempt/chunk generation 검증은 기존 서비스가 최종 transaction에서 재실행한다. '원자 게시'는 후보 세대 조회 전환이며 공식 승인/게시가 아니다. NOT_VERIFIED/NOT_REQUESTED를 유지한다.

lease/claim attempt·capability hash·동일 job unique·부분 generation 전체 rollback·비용 예약 경쟁/중복 receipt/unknown 사용량 보류는 기존 계약과 동일하다. PostgreSQL REAL 대신 DOUBLE PRECISION을 써 epoch/lease 정밀도를 보존하며 이벤트 identity는 BIGINT다.

## 설치·로컬 fixture

검증 버전: PostgreSQL17.6, psycopg/psycopg-binary3.2.10. 테스트 이미지 digest는 아래와 같다. 최신 production 보안 패치/Supabase 실제 버전 적합성 판정은 별도다.

```bash
.venv/bin/python -m pip install -r requirements-postgres-lock.txt
```

기존 API/파싱 lockfile은 그대로다. Docker 로컬 소켓 사용, registry/proxy/CA는 클라우드 runtime skill 지침을 따른다. **이 프로젝트 전용 합성 fixture에 한해** 다음을 사용한다. 포트/이름이 이미 사용 중이면 기존 리소스를 삭제하지 말고 상태를 확인한다.

```bash
env -u DOCKER_HOST -u DOCKER_CONTEXT -u DOCKER_TLS -u DOCKER_TLS_VERIFY -u DOCKER_CERT_PATH \
  docker --host=unix:///var/run/docker.sock run -d --name sb-postgres-isolated \
  -p 127.0.0.1:55432:5432 -e POSTGRES_HOST_AUTH_METHOD=trust -e POSTGRES_DB=sb_test \
  --mount type=volume,source=sb-postgres-isolated-data,destination=/var/lib/postgresql/data \
  postgres@sha256:f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3 \
  -c listen_addresses='*'
```

trust 인증은 이 합성 loopback fixture만의 설정이며 운영 사용 금지다. 호스트 공개 바인딩/host networking을 사용하지 않는다. named volume은 재시작 이후 남는다. cloud filesystem snapshot이 Docker image/volume을 보존한다고 가정하지 않으며 필요 시 이미지 재pull/새 합성 schema 생성부터 재현한다. 실제 자격증명은 필요하지 않다. 네트워크에 대한 Python guard는 libpq C 소켓을 가로채지 않으므로 테스트 database helper가 정확127.0.0.1과 포트를 강제한다.

## migration 순서·실행

```bash
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test \
  .venv/bin/python -B scripts/validation/postgres_migrate.py --schema sb_application
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test \
  .venv/bin/python -B scripts/validation/postgres_migrate.py --schema sb_budget --kind budget
```

CLI는 loopback test DSN만 허용한다. 실제 운영 DSN을 인자로 넣지 않는다. schema는 identifier 검증 후 안전 quote하며 application/budget 각각 migration kind/version/SHA-256을 기록한다. advisory transaction lock 아래 신규/빈 schema에만 적용하고 DDL/data/trigger를 한 트랜잭션으로 commit한다. 기존 unknown schema를 임의 adopt하지 않는다. 이미 동일 checksum/version이면 no-op이며 checksum 변조·다른 kind·미지원 새 version/extension은 거부한다. repository constructor는 migration을 자동 실행하지 않고 버전을 확인한다.

SQLite 기존 DB·원본을 이동/복사/삭제하거나 cloud로 이전하는 data import는 이번에 하지 않았다. 실제 cutover에는 별도 읽기 전용 SQLite snapshot·건수/SHA/current pointer/FK 검증·객체 key 보존·권한/세션 폐기 검토가 필요하다. migration rollback은 commit 전 자동 rollback, commit 후에는 쓰기 중지/검증된 백업을 **새 격리 DB**로 복원하거나 forward fix한다. DROP/down migration으로 원본/기존 schema를 파괴하지 않는다.

## API·worker 연결

기존 factory의 repository/store 주입 seam을 사용한다. 합성 검증에서는 explicit PostgresRepository와 LocalOriginalStore를 주입한다. 기본 앱/CLI는 계속 SQLite다. 표준 production entrypoint의 자동 PG/Auth/Storage wiring은 아직 없다.

```bash
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test \
  .venv/bin/python -B -m apps.api.worker --data-dir work/pg-synthetic-files \
  --institution-id A --once --postgres-local-test --postgres-schema sb_application
```

먼저 해당 schema에 합성 작업/원본을 만들어야 하며 이 명령은 이미 존재하는 파일을 처리한다. chunk_worker/workflow_worker에도 같은 옵션이 있다. --data-dir는 이 단계에서 로컬 원본 위치이며 DB 경로로 쓰지 않는다. 원본 Storage 미이식을 운영 가능으로 혼동하지 않는다. APP_ROLE이 설정됐다면 각 시작 역할과 일치해야 하며 기존 production guard를 우회하지 않는다. API와 독립 worker가 같은 PG schema/DB를 사용해 완료 결과를 조회하는 실제 테스트를 수행한다.

## 검증

```bash
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test \
  .venv/bin/python -B -m unittest discover -s tests -p test_postgres.py
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test \
  .venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output <새_증거경로.json>
```

DSN이 없으면 실제 PostgreSQL tests는 명시 BLOCKED 사유로 skip된다. 그 실행을 PG 통과로 보고하지 않는다. 이번 검증은 실제 loopback DB를 사용하며 기존 SQLite687개 회귀도 함께 실행한다. 기존 workflow/auth/RAG/budget 수용 테스트를 원본 변경 없이 새 PG class에 재사용한다. thread와 process의 claim/예산 경쟁, 잘못된 scope, 부분 rollback, source/current 세대 변화, unknown hold/receipt 재정산을 포함한다. 실제 외부 AI/Auth API 사용 없음.

DB 재시작 검증 harness는 check_postgres_recovery.py seed/check다. 새 work 경로에 합성 원본과 처리 중 workflow·in-flight budget을 만들고, **이 작업에서 만든 fixture만** 명시적으로 중지/재시작한 뒤 check한다. 기존 서비스나 알 수 없는 컨테이너를 종료하지 않는다. 원본 SHA/활성버전, lease attempt 증가·중복 완료 거부, 불확실 사용량 hold와 재정산을 확인한다. 운영 backup restore/PITR/다중리전은 검증하지 않는다.

## preflight·잔여 범위

preflight는 PG adapter 구현 사실을 POSTGRESQL_OPT_IN_IMPLEMENTED_NOT_CONNECTED로 보고한다. 'PG adapter 없음' blocker를 'production runtime 미연결'로 갱신했지만 connectivity=NOT_CHECKED/production_ready=false와 production BLOCKED는 유지한다. private Storage·운영 Auth bootstrap·proxy/worker wiring·백업복구 등 나머지 blocker는 그대로다.

다음 순서는 private 객체 adapter(immutable write/read hash/intent 대사)와 DB-객체 백업복구다. 이후 운영 설정 wiring·최소권한 PG roles/RLS 보강·기관별 worker dispatch·TLS/connection pool/서버 로그 정책·실Auth 승인 시험이 필요하다. 이 단계의 앱 tenant filter는 기존 서버 계약이며 PostgreSQL RLS를 구현했다고 주장하지 않는다. 운영자가 RLS를 추가해도 bypass role의 app 검사를 대체하지 않는다. PostgreSQL Supabase 원격·실제 Auth·Storage·LLM·임베딩·공개 배포는 이번에 하지 않는다.
