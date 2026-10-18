# 배포 준비 2단계 PostgreSQL 이식 보고

작성일: 2026-10-18 KST. **범위 내 완료: SQLite 기본값을 유지하는 PG 어댑터·명시 migration·격리 로컬 실제 검증.** production/G1-C/D 또는 실제 Supabase 연결 완료는 아니다.

## 1. 보존과 Git

시작 브랜치 feat/deployment-preflight, HEAD3453eecd3f35f78ece116cb53399ba014f1151c9. 이전 preflight manifest의25개 hash를 모두 대조했고 manifest 자신까지26파일을 검사·보존했다. 대상 강한 비밀키/개인키 패턴0건, 합성 증거·설정 코드·사용자 승인 문서 출처를 확인했다. 완전한 개인정보 인증은 아니며 실제 secret 파일/운영 값을 읽거나 주입하지 않았다.

기존 결과 보존 로컬 커밋: **8abe7fc5b5cc0ce66c2febd979ef699fad5f1895**. 이후 **feat/deployment-postgres** 분기. 새 PG 구현은 미커밋 검토 후보다. 원격 push·main 변경·merge·tag·공개 배포 없음. work/deployment-postgres-preservation/baseline.tar.gz와 SHA 목록도 보존했다.

기존 추적885파일은 내용 동일이며 의도한12개 source/기준 문서만 수정했다. 기존 원본·fixture·과거 증거·인간 검토 자료는 그대로다. [해시 기록](deployment-postgres/PRESERVATION.json). 인간 판정 생성/승인0건.

## 2. 변경 파일과 구조

신규:

- apps/api/postgres.py: PostgresDatabase/Repository/AuthStore/BudgetLedger, PG parameter·cursor/row adapter, explicit migration/checksum·트랜잭션.
- apps/api/postgres_worker.py: 기존 worker CLI의 명시 loopback PG test 선택 seam.
- migrations/postgresql/001_application.sql, 001_budget.sql: 추가형 baseline·FK/check/unique·scope trigger·별도 비용 schema.
- requirements-postgres-lock.txt: optional psycopg/psycopg-binary3.2.10. 기존 lockfiles 불변.
- scripts/validation/postgres_migrate.py, inventory_persistence.py, check_postgres_recovery.py.
- tests/test_postgres.py: 신규110개(실제PG106개·dialect/설정4개), 기존 assertion 함수 재사용.
- docs/DEPLOYMENT_POSTGRES.md, 본 보고와 outputs/deployment-postgres/* 새 증거.

수정:

- main.py: PG repository 주입 시 같은 PG AuthStore 사용.
- worker.py/chunk_worker.py/workflow_worker.py: 선택 flag/helper, 기본 SQLite 그대로.
- workflow_jobs_repository.py/workflow_forms_repository.py/vector_repository.py: PG에서 SQLite constructor DDL 생략, 명시 migration 사용.
- provider_safety.py: 정확한 PostgresBudgetLedger concrete type만 추가 허용. FakeTransport/실외부 차단 유지.
- runtime_settings.py: PG 구현과 production runtime 미연결을 구분. 실제 연결 NOT_CHECKED/production BLOCKED 유지.
- ARCHITECTURE/TASKS/TEST_PLAN: 현재 계약 절만 추가.

직접 SQLite SQL/연결 경계는 초기 rg206행과 [AST 전수 목록](deployment-postgres/sql-inventory.json)에 기록했다. auth·문서·parse/chunk·workflow/ReviewIssue/forms·vector/search·cost의 SQL과 main.repo.path/worker 연결 의존까지 포함했다. AST는 동적 SQL 호출도 위치를 남기며 비SQL execute 메서드 false positive도 포함한다. 검증 스크립트의 고정 SQLite 평가 corpus는 앱 운영 DB와 별도여서 보존했다.

## 3. SQLite 호환성·API

기본 앱/worker는 계속 SQLite/로컬 원본/deny-all이다. PG는 explicit repository 주입 또는 loopback 전용 --postgres-local-test로만 사용한다. API의 응답/role/CSRF/Origin/쿠키·기관/버전/current·EvidenceRef·원본 SHA·lease 계약과 기존 검색 기본값은 유지한다. 검색 method 문자열의 sqlite_* prefix는 기존 API algorithm identifier로 보존하며 실제 backend 식별용이라고 주장하지 않는다.

domain SQL을 다시 복제하지 않고 PG adapter 안에서 bound parameter·OR IGNORE/정해진 auth upsert·row positional/named 접근을 처리한다. native PG 문법은 migration/adapter 내부에만 둔다. vector는 기존 exact-cosine baseline이며 pgvector·실임베딩 연결이 아니다.

## 4. PostgreSQL 실제 실행 범위·migration

로컬 Docker PostgreSQL17.6(공식 이미지 digest f3bd19c606e442c3d7bdfa8002e03fe260a1023351e0ea4598032022b68dd6e3), psycopg3.2.10을 사용했다. 호스트 포트는 정확127.0.0.1:55432만 공개했다. trust 인증은 이 격리 합성 fixture 전용으로 운영 사용 금지다. 이미지/드라이버는 설정된 proxy/TLS로 설치했으며 실제 Supabase·Auth·Storage·LLM API 호출은 하지 않았다.

새 application/budget schema에 version1 migration을 적용했다. 동일 checksum 재실행은 no-op, 알려지지 않은 기존 schema·미지원 새 version·다른 kind·checksum 변조는 거부했다. 알려지지 않은 user_owned 테이블을 삭제하지 않는 것도 확인했다. source/parse/chunk/workflow/active-version 범위 trigger와 FK/check/unique를 실제 DB에서 검사했다.

DDL·version/checksum·bootstrap은 advisory transaction lock과 한 트랜잭션으로 적용한다. constructor는 자동 migration 없이 verify한다. SQLite 데이터/원본을 이동·삭제하거나 cloud에 import하지 않았다. 실제 data cutover·운영 SSL/connection pool·DB 최소권한/RLS는 미검증이다.

실행 예와 operator 단계/rollback 전략은 [PG 계약](../docs/DEPLOYMENT_POSTGRES.md)을 따른다. SQLite→PG 실제 자료 이전은 별도 승인/읽기 전용 snapshot·건수/해시/권한·원본 위치 검증이 필요하다. commit된 DB schema를 DROP으로 롤백하지 않는다.

## 5. 동시성·비용·무결성

PG schema의 transaction_guard **단일 행 FOR UPDATE + READ COMMITTED**로 기존 BEGIN IMMEDIATE의 직렬화 의미를 보존한다. API/Auth/workers가 같은 행을 잡으며 budget은 별도 schema로 격리한다. thread와 독립 process의 claim/중복 완료/예산 경쟁을 실제 PG에서 검사했다. 범용 SKIP LOCKED·기관별 높은 병렬 처리량을 구현한 것으로 표현하지 않는다. 이 방식은 같은 schema의 읽기·다른 기관도 직렬화하므로 처리량 최적화가 남는다. guard를 무시하는 임의 raw writer는 서비스 상태 전이 계약 밖이다.

테스트 범위: 문서 CRUD/버전·동시 활성화·기관 접근 차단, auth 세션/active membership·CSRF/Origin·로그아웃, parse/chunk/workflow claim·lease/attempt·중복/취소·현재 세대 변경, 원본 변조·위조 근거 거부, candidate/ReviewIssue/form link 부분 쓰기 rollback, vector현재 세대/검색·기한 무근거 응답 차단, 비용 원장 duplicate receipt/예약 경쟁·thread/process·unknown 사용량 보류·수동 합성 정산·Fake gateway 통합.

## 6. 재시작·영속성

새 합성 HWPX를 실제 parser/chunker로 처리·활성화하고 workflow를 processing, 비용을 in_flight 상태로 남겼다. 테스트 전체 종료 후 **이 작업에서 만든 컨테이너만 정상 stop/start**했다. 데이터 volume은 유지했다. 이는 정상 DB 재시작 검증이며 강제 전원 장애·PITR·운영 백업 복원 시험이 아니다.

재시작 후 새 Python 프로세스가 확인한 결과:

- 원본 SHA·활성 버전 유지.
- 만료 workflow를 attempt2로 재claim하고 completed1회, 중복 완료는 stale 거부.
- in-flight 비용을 uncertain으로 복구해20 micro-USD 모의 hold 유지.
- 합성 사용량 재정산 후 held0/spent6 micro-USD. 실제 과금0.

[seed](deployment-postgres/recovery-seed.json), [재시작 후 결과](deployment-postgres/recovery-after-restart.json). 작업 종료 시 fixture를 정상 중지했고 named volume·모든 합성 원본을 보존했다.

## 7. 실제 테스트 결과

| 실행 | 결과 | 시간 |
|---|---|---:|
| 최초 PG56개 |22 FAIL/1 ERROR |22.460초 |
| 중복 column label의 행 변환 수정 후56개 |56 PASS |22.872초 |
| auth/RAG 확대102개 |102 PASS |57.904초 |
| schema/process 확대109개 |109 PASS |64.462초 |
| 최종PG110개 |110 PASS |63.366초 |
| 전체backend(기존687+신규110) |**797 PASS / FAIL0 / SKIP0 / BLOCKED0** |283.265초 |
| guarded runner |exit0, Python 비루프백 시도0 |284.731초 |
| DB 실제 재시작 후 recovery |PASS |별도 harness |

최초 실패는 같은 label의 두 SQL 결과 열을 dict로 합치며 한 값이 소실된 PG row adapter 문제였다. 원본 테스트/fixture는 바꾸지 않고 위치·이름 접근을 모두 보존하도록 수정했다. 초기 증거도 [보존](deployment-postgres/targeted-initial.txt)했다. Fake gateway 통합 테스트 초기 입력이 기존 byte/token 상한보다 커서 거부된 사례도 있었고, 상한을 내리지 않고 합성 입력만 그 안으로 줄여 최종 통과했다.

최종 tested code hash mismatch0. migration 파일 checksum도 별도 기록했다. 기존 Starlette/httpx deprecation warning은 남으며 임의 dependency 교체하지 않았다.

Python socket guard는 libpq C socket을 가로채지 않는다. 모든 PG test constructor가 정확127.0.0.1을 강제했고 runtime actual provider 호출0이다. PG 서버/DSN이 없을 때 skip되는 테스트를 PASS로 보고하지 않는다. 이번 실행은 server가 실제 있었으며 skip0이다.

프런트·기존 API/파서 lock·UI source는 변경하지 않아 UI/타입/build는 새 실행하지 않았다. 이전 UI174 등의 증거는 이전 실행으로 보존하며 새 PASS로 집계하지 않는다.

## 8. preflight·BLOCKED·환경 재현

PG adapter 구현은 보고하지만 운영 자동 wiring은 아직 없다. preflight는 POSTGRESQL_OPT_IN_IMPLEMENTED_NOT_CONNECTED, connectivity=NOT_CHECKED, production_ready=false이며 production 시작은 계속 BLOCKED다. Storage/운영 Auth bootstrap·proxy·cloud worker runtime·공동 백업복원 blocker도 그대로다.

클라우드 setup skill을 따라 **start_skill 초안**에 optional driver 설치·기존 local/API 작업 지침·loopback PG fixture 시작/readiness/migration/test·원본/로컬 커밋 보존을 저장했다. 실제 환경 적용/게시 없음(requires_publish=true), 네트워크 allowlist/secret 요구사항 변경 없음. 사용자가 환경 설정에서 검토·저장·게시하기 전 활성 설정이라고 주장하지 않는다. 새 Cloud 작업의 로컬-only commit/Docker volume/ignored corpus 복원은 실제 미검증이며 원격 보존도 하지 않았다.

## 9. 다음 Storage 이식 준비도

시작 가능: PG 저장·원자 transaction·intent/current 상태를 기준으로 private 객체 adapter를 주입할 수 있다. 먼저 Fake/local-compatible object store로 immutable conditional create/read SHA·partial upload/orphan 대사·기관/버전·DB rollback·DB+객체 manifest/restore를 검증해야 한다. 운영 최소권한·connection pool·기관 worker dispatch·Auth 설정/초기 identity bootstrap·실Supabase 연결·TLS·RLS·운영 백업/PITR는 이후 별도 작업/승인 사항이다. 단계 종료 후 자동 진행하지 않는다.

## 10. 소요시간

기존 결과 보존 커밋 이후18.5분 실측(초기 조사·보안검사 제외). 전체 약20여분. 실제 검증 실행시간은 위 표로 분리했다. Supabase/LLM/embedding 실제 호출0·유료 서비스 신청/결제0·공개 배포0·원격 push/merge0이다.

추가 미검증 범위: 선택적 C 검색의 동일40문항 실API 성능 benchmark를 PostgreSQL에서 다시 실행하지 않았다. 현재 PG 검색 검증은 별도 합성 자료의 literal/vector/hybrid 및 원문·기관/세대 회귀다. 기존 C 평가 점수를 PG 실측으로 재사용하지 않는다.
