# 운영 Factory·Migration Runner 통합 결과

## 시작 기준·보존

실제 `feat/deployment-storage-http`/`e091b7b494c2fff5dc10dcd27d45ad5e963e3ef9` clean 작업 트리와 Draft PR#3의 동일 원격 HEAD/OPEN 상태를 확인했다. 새 `feat/deployment-runtime-factory`에서 작업했다. 기존 원본·fixture·보안 설정·migration SQL·과거 증거는 기준 SHA로 보존한다. 이번 새 변경은 미커밋 검토 후보이며 push·main merge·PR 갱신은 하지 않는다.

## 구현 파일과 생성 경로

- `apps/api/runtime_factory.py`: build_runtime/build_application, role/preflight·typed config·DI·DB/store/provider 생성, peer의 DB/budget/schema/storage/session 대조, 기존 loopback worker CLI 호환 경로.
- `apps/api/migration_runner.py`: 별도 application/budget MigrationPlan, sorted session locks, application→budget→Storage 순서 apply/verify, stage/code 마스킹·실패 재개.
- `apps/api/main.py`, `apps/api/runtime_wiring.py`: API 기본 생성과 worker 경로 연결, runtime/budget state, Mock HTTP 주입·budget peer 검증.
- `scripts/validation/runtime_migrate.py`: 명시 schema와 SB_PG_TEST_DSN을 사용하는 로컬 CLI; 기본 verify, 원격 실행 거부.
- `tests/test_runtime_factory.py`: 신규28개, 기존 테스트/fixture 변경 없음.
- `docs/RUNTIME_FACTORY_MIGRATIONS.md`, `docs/STAGING_CONNECTION_RUNBOOK.md`, ARCHITECTURE/TASKS/TEST_PLAN 해당 절, 이번 새 outputs 증거.

일반 시작은 검증만 하며 migration apply는 명시적 operator 선택이다. local/test SQLite·Local·deny-all 기본과 기존 명시적 API DI를 보존했다. 새 factory는 실제 키 없는 Fake JWT/Mock Storage 주입을 지원하지만 추가 Fake 추출/응답 시나리오를 개발하지 않는다.

## Migration 안전성

세 단계는 각각 원자 transaction이며 전체가 한 transaction은 아니다. 앞 단계 성공 뒤 다음 단계가 실패하면 성공 데이터/schema를 보존한다. 실패 단계만 롤백하고 같은 plan으로 apply→verify 재실행한다. version/checksum 충돌 시 overwrite/adopt/drop/reset하지 않는다. 정렬한 schema session lock과 기존 DDL transaction lock·transaction_guard로 동시 초기화를 직렬화한다. DB 연결 또는 잠금 실패와 stage별 적용 오류를 고정 코드로 보고한다. 실제 Supabase 원격 실행 정책은 계속 BLOCKED다.

## 검증 기록

- 초기 신규 단위 실행에서 다른 기관의 비용 계정 부재를 0잔액으로 기대한 신규 테스트1건이 실패했다. 기존 ledger의404 차단 계약에 맞게 신규 assertion을 수정했으며 기존 제품 계약을 바꾸지 않았다.
- 초기 영향 통합78개(당시 신규26+기존 Wiring52), 13.991초 PASS/FAIL0/SKIP0.
- peer pre-connect 검증과 비용 hold 보강 당시 신규26개, 5.228초 PASS/FAIL0/SKIP0.
- 신규 시험은 실제 격리 PostgreSQL15개와 안전성13개다. apply/reapply/verify-only, 동시 초기화, checksum 오류, budget/Storage 부분 실패 롤백·재개, 기관/멤버십/예산 hold/원본, 실제 worker pipeline, CLI/원격 차단을 포함한다.
- 최종 점검에서 기본 API의 Factory Origin→AuthService 전달 누락을 재현하는 시험이 실패했다. 전달과 기본 binding 연결을 수정하고 올바른 Origin 허용/다른 Origin 거부 시험을 추가했다. 진행 중이던 전체 회귀는 중단해 PASS로 집계하지 않고 최종 코드를 재실행했다. 중단 기록은 backend.network.json(backend_exit=-15)이며 최종 결과와 구분한다.
- 전체 회귀1회에서1,106 PASS/6 FAIL이 발생했다. 공통 Factory가 기존 API Repository constructor DI를 전달하지 않아 PostgreSQL workflow fixture가 SQLite를 선택한 것이 원인이었다. 기존 테스트는 바꾸지 않고 constructor를 공통 Factory에 전달하도록 수정하고 저장소 identity 회귀를 추가했다. 실패 기록 backend-final.json은 보존하고 최종 backend-verified.json과 구분한다.
- constructor DI 복원 후 신규28+기존 PostgreSQL110+기존 Wiring52 = **190 PASS**,81.454초/FAIL0/SKIP0. 이후 최종 전체 회귀를 실행했다.
- 최종 전체 회귀·서버 재시작 결과와 시간은 아래 최종 evidence 부록을 따른다. 기존1,085개를 이번 실행 결과 없이 PASS로 복사하지 않는다.

UI/API 응답/DB migration 원문 변경 없음. UI/typecheck/build·실제 브라우저 재실행은 NOT_RUN이다. 기존 UI·TLS 결과를 새 PASS로 표시하지 않는다. 별도 과거 증거를 덮어쓰지 않는다.

## 운영 상태·최소 설정

production BLOCKED6개는 그대로다. 로컬 factory/runner 통합 완료는 원격 권한/전송 구현/호스팅/복구 완료가 아니다. 여전히 필요한 것은 원격 DB factory/runner 승인 정책·TLS/권한·schema, live Storage/ACL/inventory, live Auth/JWKS/계정상태/철회·초기 관리자, 실제 HTTPS ingress/CSRF/cookie/20MiB, cloud worker, coordinated backup이다.

운영 최소 준비 설정은 [상세 계약](../docs/RUNTIME_FACTORY_MIGRATIONS.md#production-blocked와-최소-설정) 및 [실행 준비표](../docs/STAGING_CONNECTION_RUNBOOK.md)를 따른다. MigrationPlan의 명시 application/budget schema·정책을 같은 API/worker에 제공해야 한다. 현행 runtime env 값만 주입하면 활성화되는 live factory/원격 runner는 없다. 실제 값을 Git/보고서/채팅에 넣지 않는다.

실제 Supabase·Render·Vercel·LLM·embedding 연결, 서비스 계정/비밀 주입·결제·공개 배포·기동 차단 해제·인간 판정 생성은 수행하지 않았다. GitHub PR 원격 확인은 승인된 read-only metadata 조회다. 다음 단계는 자동 진행하지 않는다.

## 실행 환경

기존 .venv/Python3.12.14·잠금 의존성과 격리 loopback PostgreSQL fixture를 재사용했다. 보조 준비 검사에서 시스템 Python을 사용한1회는 defusedxml 미설치로 실패해 .venv로 재실행했고 정상 완료했다. 패키지 설치/잠금파일·네트워크/Secret 설정은 바꾸지 않았다. 기존 Starlette/httpx TestClient deprecation 경고는 이번 기능의 실패와 구별한다.

## 최종 실행 결과

- **전체 backend1,113 PASS / FAIL0 / SKIP0** (기존1,085 + 신규28),358.877초. 최종 근거는 [backend-verified.json](runtime-factory/backend-verified.json)이며 이전 실패/중단 기록과 구분한다.
- [네트워크 가드](runtime-factory/backend-verified.network.json) probe PASS, blocked external attempts0. 실제 공급자 호출0. loopback DB 사용을 외부 공급자 연결로 표시하지 않는다.
- 실제 격리 PG container stop/start 뒤 새 Python process에서 Runner verify·원본 SHA·queued parse job·활성 manager membership·UNKNOWN 비용 hold20의 보존을 확인했다. [복구 결과](runtime-factory/recovery.json). 재시작 직후1회는 DB 준비 전 접속을 안전하게 거부했고 pg_isready 이후 재검증 PASS다. PG fixture는 최종 중지했고 기존 volume을 보존했다.
- 최종 source hash 136파일 일치, 기존989파일 불변·의도한 기존6파일 변경·예상 밖 변경/삭제0. [보존 검사](runtime-factory/PRESERVATION.json), [영향 시험](runtime-factory/TARGETED_RESULTS.json).
- 작업 브랜치 `feat/deployment-runtime-factory`, HEAD `e091b7b494c2fff5dc10dcd27d45ad5e963e3ef9`. 새 변경은 미커밋이며 PR#3은 기존 e091b7b/Draft OPEN 그대로다. 원격 갱신/배포/production 해제 없음.
- 보존 검사부터 **37.3분**, 종료 2026-10-19T08:24:15.450386+09:00. 다음 단계 자동 진행 없음.
