# 운영 Factory·Migration Runner 통합 계약

관련 FR-14/15/18, NFR-01/02/05/07, WEB-02/04/05. [스테이징 준비표](STAGING_CONNECTION_RUNBOOK.md)의 factory/migration 공백 중 **공통 생성 경로·명시적 계획·격리 로컬 실행**을 구현한다. live 공급자 어댑터·승인된 원격 기동은 구현/검증 완료로 승격하지 않는다. 추가 Fake 응답 시나리오나 실제 외부 호출은 추가하지 않는다.

## 공통 Factory와 시작 경로

`apps/api/runtime_factory.py`의 `build_runtime`은 role별 RuntimeBinding을 만든다. `build_application`은 이를 FastAPI에 주입한다. 기존 표준 `create_app`의 기본 DB/store 선택과 독립 parse/chunk/workflow worker의 기본 선택도 이 모듈로 모은다. 명시적 기존 repo/store 주입과 Repository constructor DI도 하위호환을 유지한다. constructor DI는 Python 내부의 신뢰된 local/test 조합 지점이며 env/HTTP 입력에서 호출자를 받지 않고 production 검사 이전에 실행하지 않는다. 기존 loopback PostgreSQL worker CLI는 같은 모듈의 `build_legacy_local_postgres`에서 application-only verify 계약을 유지한다.

- RuntimeSettings를 엄격히 재검증하고 preflight/role 검사 후에만 DB·파일을 만든다. local/test는 SQLite/Local·deny-all 기본이며 기존 Fake binding은 명시 주입한다.
- `MigrationPlan`을 명시하면 **isolated loopback PostgreSQL**과 application/budget의 별도 schema를 사용한다. 이는 local/test의 테스트 seam이며 `DATABASE_URL` 운영 경로를 활성화하는 우회가 아니다.
- PostgreSQL 기본 시작 정책은 `migration_mode='verify'`다. 미적용 DB는 거부한다. `apply`는 명시적인 operator 작업 또는 격리 로컬 초기화에서만 선택한다.
- 기존 PrivateStorageSettings+정확 FakeStorageTransport/정확 Mock HTTP, Fake JWT/JWKS provider+SessionRevalidation, AuthSettings/ProxyPolicy를 명시 DI할 수 있다. 실제 키 없이 계약/권한을 시험하며 위험한 pair·project/role/Origin은 연결 전에 거부한다.
- child worker는 API의 repo/store/auth policy/budget ledger를 보존한다. 독립 factory 생성 시 `api_peer`를 전달하면 root·DB/schema·budget schema·storage·cookie policy를 연결 전에 대조하고 생성 후 다시 검증한다. peer 없이 독립 생성한 binding이 실제 API와 일치하는지는 자동으로 알 수 없으므로 운영자가 검증된 공통 설정을 배포해야 한다. 공유 메모리 Fake/Mock object worker는 기존처럼 API peer 없는 사용을 거부한다.
- app.state.runtime_binding과 app.state.budget_ledger에 조합 결과를 보관한다. provider budget은 기존 Simulation/PostgreSQL 원장이며 실제 과금/외부 호출은 활성화하지 않는다.

예시(파이썬 주입, 비밀은 예제에 넣지 않음):

```python
# plan은 승인된 격리 로컬 DSN과 별도 schema를 담은 MigrationPlan
api_binding = build_runtime(root, postgres_plan=plan, migration_mode='verify')
worker_binding = build_runtime(root, role='parse_worker', postgres_plan=plan, api_peer=api_binding)
app = build_application(root, postgres_plan=plan)
# 기존 worker main(args, runtime_binding=worker_binding)으로 독립 실행 루프 재사용
```

## Migration Runner

`apps/api/migration_runner.py`:

1. plan/type/schema를 재검증한다. application/budget은 달라야 하고 public/auth/storage/extensions/pg_*는 금지한다. DSN은 local_test 기준의 127.0.0.1 명시 port만 허용한다. target=production은 연결 전에 거부한다.
2. schema별 이름으로 유도한 session advisory lock 2개를 정렬 순서로 획득한다. 같은 schema를 공유하는 Runner가 서로 직렬화되며 잠금 대기는10초 상한이다. 세션이 닫히거나 죽으면 잠금이 풀린다.
3. application `001_application.sql` → 별도 budget `001_budget.sql` → application Storage registry `001_private_storage.sql` 순서로 apply/verify한다. 각 단계의 기존 트랜잭션 잠금·transaction_guard·version/checksum을 재사용한다.
4. verify 모드는 migration DDL을 실행하지 않는다. schema가 없거나 checksum이 다르면 해당 stage에서 거부한다. Storage version/hash와 필요한 객체/복구 열도 확인한다.
5. apply 중 application·budget·Storage의 각 단계는 별도 transaction이다. **세 단계 전체가 한 원자 transaction인 것은 아니다.** 실패한 단계만 롤백하며 앞서 완료된 단계는 보존한다. 전체 READY가 나오기 전에 API/worker를 시작하지 않는다.
6. stage/code만 출력한다. DSN·비밀번호·SQL/원래 예외를 로그에 포함하지 않는다. 성공 결과는 각 stage의 applied 여부와 `production_ready=false`를 반환한다.

현재 외부용 연결 경로/원격 migration 승인은 제공하지 않는다. Runner를 설정했다고 실제 Supabase DB migration이 가능해지는 것이 아니다. raw `PostgresDatabase`는 TLS URL validation 코드가 있지만 통합 Runner/Factory의 실제 원격 사용은 계속 차단한다.

## 실행 명령 — 이번 검증은 loopback만

기존 `scripts/validation/postgres_migrate.py`는 유지한다. 새 `scripts/validation/runtime_migrate.py`는 비밀을 인자로 받지 않고 `SB_PG_TEST_DSN`을 사용한다. 예시 schema는 실제 운영 schema를 생성하라는 지시가 아니다.

```bash
# 격리 로컬 PostgreSQL만: DSN은 안전한 실행 환경에서 별도 주입
.venv/bin/python -B scripts/validation/runtime_migrate.py \
  --application-schema sb_application_check --budget-schema sb_budget_check --mode apply
.venv/bin/python -B scripts/validation/runtime_migrate.py \
  --application-schema sb_application_check --budget-schema sb_budget_check --mode verify
```

verify가 기본이며 config/schema 누락·원격 DSN·잘못된 mode는 고정 진단과 nonzero exit로 중단한다. 이미 적용된 단계는 재실행 시 applied=false이며 데이터를 초기화하지 않는다.

## 실패·복구 절차

1. API/worker 시작을 멈추고 stage/code를 확인한다. 로그/명령행에 DSN·토큰을 붙이지 않는다.
2. 기존 DB/원본/backup/manifest를 보존하고 checksum/lock/권한/DB 상태를 확인한다. checksum을 현재 값으로 임의 덮어쓰거나 schema를 drop/reset하지 않는다.
3. 원인을 수정한다. transaction 실패라면 해당 단계의 partial DDL은 롤백된다. 앞 단계 완료 자체는 오류가 아니며 다음 apply에서 건너뛴다.
4. 동일 계획으로 apply 후 verify를 다시 실행한다. 데이터·멤버십·비용 hold·원본 SHA와 job 상태를 확인한다. READY 이후에만 검증된 프로세스 구성으로 재시작한다.
5. schema/설계 자체를 되돌려야 하면 destructive down이 아니라 검증된 backup을 새 대상에 복원하고 검토 후 전환한다. 원격 coordinated backup/restore는 여전히 미검증이다.

## production BLOCKED와 최소 설정

기존 PRODUCTION_BLOCKERS 6개는 유지한다. PostgreSQL의 **로컬 통합 경로**가 추가돼도 아래 cloud 실증을 대체하지 않는다.

| blocker | 남은 실제 조건 |
|---|---|
| postgresql_production_runtime_not_wired | 승인된 원격 factory/runner 정책·schema/최소권한·TLS/CA·connection pool·연결/실DB 실증 |
| private_storage_production_transport_not_wired | live HTTP 선택·서버/gateway key 종류·private ACL·공식 목록·orphan 대사/복구 |
| production_auth_runtime_and_operator_provisioning_not_verified | live JWT/JWKS/password/현재 계정 상태·철회·명시 초기 관리자 실증 |
| vercel_render_edge_trust_limits_and_https_not_verified | 실제 ingress 신뢰·Origin/CSRF/cookie·20MiB 양방향·정확 호스팅 요금제 |
| worker_cloud_runtime_not_implemented | cloud 프로세스/기관 범위·공통 DB/schema/Storage·lease/중단 복구·권한 분리 |
| coordinated_backup_restore_not_verified | DB+객체 bytes+manifest/Auth identity/비용 원장의 실제 복구·RPO/RTO |

현재 운영 최소 준비 항목은 기존 RuntimeSettings의 PostgreSQL TLS DSN/role, Storage project/bucket/server key/private, Auth project/API key, HTTPS Origin/쿠키/CSRF/proxy, membership, backup 목표다. 여기에 이번 `MigrationPlan.application_schema/budget_schema`와 명시 migration 정책을 맞춰야 한다. 계획은 typed DI/로컬 CLI로 연결되며 운영 env mapping·승인 정책은 아직 없다. Storage HTTP gateway key와 live JWKS/status 어댑터의 안전한 secret binding도 남아 있다. **실제 값을 주입해도 현재 production 시작은 안 된다.**

## 검증과 보존

`tests/test_runtime_factory.py`: 신규28개(안전성13, 실제 격리 PostgreSQL15). 새 DB/재실행/verify-only·동시 apply/초기화·checksum·부분 실패/재개·기관/멤버십/예산 hold·API worker mismatch·실제 worker pipeline·CLI·원격 차단을 검증한다. 전체 회귀와 실제 PostgreSQL fixture stop/start 결과는 [완료 보고](../outputs/RUNTIME_FACTORY_REPORT.md)의 새 evidence를 따른다. UI/API 응답/DB migration 원문/원본/fixture/과거 증거는 바꾸지 않는다. production 해제·실공급자·push/PR 갱신은 하지 않는다.
