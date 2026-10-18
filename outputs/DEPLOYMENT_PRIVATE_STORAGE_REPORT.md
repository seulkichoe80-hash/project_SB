# 배포 준비 3단계 — Private Storage·복구 구현 보고

2026-10-18 UTC. **범위 내 완료: Fake-only 비공개 객체 어댑터와 application-schema 복구 계약. 실제 Supabase/운영 연결 완료가 아니다.** [설계·실행법](../docs/DEPLOYMENT_PRIVATE_STORAGE.md).

## 1. 기존 변경 보존·Git

시작 브랜치 feat/deployment-postgres, 시작 HEAD8abe7fc5b5cc0ce66c2febd979ef699fad5f1895. 기존 PostgreSQL 변경38파일(이전 manifest37항목과 manifest 자신)을 대조·비밀정보 검사 후 **acc09eb6beb1ba6fed5a9d0194bb112c3c394cbe**로 로컬 커밋했다. 메시지: Preserve PostgreSQL adapters, migrations and local recovery evidence.

새 브랜치 **feat/deployment-private-storage**. 이번 Storage 구현은 미커밋 검토 후보로 남긴다. staged 변경 없음. 원격 push·main 변경·merge·tag·배포 없음. 기존 변경 원문은 work/deployment-storage-preservation/baseline.tar.gz와 파일별 SHA로도 보존했다. [보존 검사](deployment-private-storage/PRESERVATION.json).

## 2. 변경 파일

신규 구현:

- apps/api/private_storage.py — 설정/전송 계약, 정확한 Fake-only 허용, registry migration, 권한·기관 경로·SHA/크기 검증, immutable 업로드·제한 재시도·대사/quarantine.
- apps/api/storage_backup.py — 운영자 scope·manifest·private disk bundle·새 대상 원자 DB 복구/receipt·세션 철회·worker fencing.
- migrations/storage/001_private_storage.sql — 객체 원장과 복구 receipt. 독립 checksum 버전으로 기존 SQLite/PG baseline 보존.
- scripts/validation/check_private_storage_recovery.py — 합성 HWPX의 parse/chunk/workflow/backup→새 DB+새 Fake→EvidenceRef/worker 복구 실행 도구.
- tests/test_private_storage.py — 47개 시나리오를 SQLite/실제 로컬PG 각각 실행(94개).

수정 구현:

- apps/api/service.py — 기존 Local 호출을 보존하면서 Private 경로에만 Principal/UnitOfWork 전달.
- apps/api/parsing_service.py, chunk_service.py, workflow_snapshot.py, workflow_jobs.py, workflow_forms.py — 원본 재해결을 같은 권한·해시 경계로 통일. 열린 DB transaction 재사용.
- apps/api/runtime_settings.py — Fake 구현 상태를 표시하고 실제 transport 미연결 production blocker 유지.

문서: docs/DEPLOYMENT_PRIVATE_STORAGE.md, ARCHITECTURE.md, TEST_PLAN.md, TASKS.md, 본 보고와 새 outputs/deployment-private-storage/* 증거. 전체 파일별 SHA는 [CHANGE_MANIFEST](deployment-private-storage/CHANGE_MANIFEST.json)에 기록한다.

## 3. Storage·DB 일관성

로컬 저장소/SQLite/deny-all 기본과 기존 API 응답은 유지했다. private store는 명시 factory 주입만 가능하다. HTTPS project 형식·private=true·서버 SecretStr·real_calls_enabled=false를 검증하며 정확한 FakeTransport만 허용한다. 실제 HTTP 요청 코드는 없다. 서비스 키·객체 URL·장기 서명 URL은 브라우저에 전달하지 않는다.

기관 hash prefix/서버 UUID 경로와 DB 기관·버전·등록/활성본을 재확인한다. reader는 등록 활성본만, worker는 등록 문서만, manager의 과거 원본 조회는 기존 권한 의미를 유지한다. parse/chunk/workflow/form/evidence도 원본 SHA와 크기를 검증한다. 구조적 EvidenceRef 확인을 의미 정확성으로 승격하지 않는다.

단일 DB+객체 transaction은 없으므로 pending intent/객체 planned→put-if-absent→read-back→uploaded→기존 metadata commit 순서다. 객체 실패는 metadata 게시를 막고 DB 실패 후 객체는 private orphan으로 보존한다. 응답 유실 재시도는 같은 pending intent/같은 bytes에 한해 먼저 get 검증하며 최대3회다. 부분 업로드·다른 SHA/크기는 quarantine, overwrite/delete/move 없음. 명시 대사는 orphan을 DB 상태로 격리하며 문서를 임의 복원하지 않는다. 실패 intent를 새 요청에 연결하거나 자동 quarantine 해제하지 않는다.

## 4. 백업·복구 결과

application DB transaction+Fake 객체 lock에서 원본·버전·기관·registry/전체 물리 inventory를 맞춘 후 공통 snapshot ID·table/객체 hash·행수·열·시점 manifest를 생성한다. pending/orphan/quarantine/missing/미지 schema는 완전 백업으로 인정하지 않는다.

private disk bundle은 새 경로/디렉터리0700/파일0600/exclusive create/fsync/COMPLETE-last로 기록한다. 복구는 별도 신뢰 경로의 manifest SHA가 필수이고 새 빈 DB/schema+Fake 대상으로만 가능하다. 객체 먼저 검증·복사 후 application 행/활성 포인터/receipt를 단일 DB transaction으로 저장한다. 부분 실패는 DB rollback, 먼저 복사된 private 객체는 보존·검증 재사용한다. 같은 복구의 재실행은 대상 digest까지 같을 때만 ALREADY_RESTORED이며 대상 변경 시 거부한다.

세션 전부 revoked/challenge 제거, processing claim/lease는 무효화하고 queued 또는 한도 초과 failed로 전환한다. 이전 worker claim stale 차단 후 새 claim으로 재개했다. 기존 승인/의미 상태는 승격하지 않았다.

| 새 실제 실행 | 결과 | 시간 |
|---|---|---:|
| SQLite disk bundle→새 DB/Fake→원본·EvidenceRef·workflow 재개 | PASS | 0.582초 |
| 격리 로컬 PostgreSQL 동일 복구 | PASS | 2.412초 |
| 신규 Storage/복구94개(SQLite47+PG47) | PASS | 15.742초 |
| 전체 backend891개(기존797+신규94) | PASS, FAIL0/SKIP0/BLOCKED0 | 295.000초 |

[SQLite 복구](deployment-private-storage/recovery-sqlite.json) · [PG 복구](deployment-private-storage/recovery-postgresql.json) · [전체 테스트](deployment-private-storage/backend.json) · [네트워크 검사](deployment-private-storage/backend.network.json).

범위 제한: 이 bundle은 최대64MiB/테이블10만행의 application-schema+Fake 객체 복구다. **별도 공급자 비용 schema는 manifest excluded_components로 명시**하며 통합 백업으로 주장하지 않는다. 전체 클러스터/PITR·실물 객체·암호화/키복구·원격 재난복구·운영 RPO/RTO는 BLOCKED다. DB 서버 stop/start 복구를 이번에 새로 수행하지 않았으며 이전 단계 증거로만 남긴다.

## 5. 보안·회귀·보존

기관 외 경로/타기관 원본, reader 쓰기/비활성 접근, traversal, public bucket, real/subclass transport, 임의 callback, 위조 hash/크기, 부분 객체, timeout 전후, 동시 중복, DB 부분 실패/rollback, orphan, 혼합 시점/변조 manifest, 비어 있지 않은 복구 대상, symlink, 중복/변경 대상 복구, 세션·claim fencing을 실제 테스트했다. 새 pipeline에서 구조적 EvidenceRef와 미승인 workflow 상태를 확인했다.

Python socket/DNS guard 자체 probe PASS, 본 전체 회귀의 차단 외부 시도0·실제 Supabase/LLM/임베딩 호출0·실제 지출0. 새 Fake 검사는 HTTP client/socket/DNS 생성도 막는다. guard는 C libpq를 가로채지 않으므로 PG local_test의127.0.0.1 DSN 강제를 함께 사용했다. 로컬PG만 실제 접속했고 원격 서비스/자격증명을 주입하지 않았다.

강한 private-key/AWS/provider-key 패턴 검사0건, 합성 placeholder의 출처를 확인했다. 이는 모든 개인정보 부재의 포괄 인증은 아니다. backup 원문/DB는 Git 제외 work/에만 저장하며 보고에는 객체 원문/서비스 키를 넣지 않았다. 기존 원본·fixture·과거 outputs·인간 검토 자료 삭제/변경0, 인간 판정/승인 생성0. 기존 Local storage.py·PG baseline migration·UI·lockfile 불변을 대조했다.

UI/타입/build는 프론트 변경 없음으로 이번 미실행이며 과거174 PASS를 새 실행 결과로 계상하지 않는다. FastAPI TestClient의 기존 Starlette/httpx deprecation 경고는 있었으나 실패는 없다.

## 6. preflight·남은 조건·Auth 준비도

[local preflight](deployment-private-storage/preflight-local.json)는 LOCAL_CONTRACT_VALID. [production 합성 API/worker 설정](deployment-private-storage/preflight-production.json)은 settings VALID라도 **BLOCKED/startup_allowed=false/connectivity=NOT_CHECKED**다. private_storage_adapter=FAKE_ONLY_IMPLEMENTED_NOT_CONNECTED이며 실제 transport, PG runtime, Auth bootstrap, proxy/limits, cloud worker, coordinated 운영 복구 blocker를 유지했다.

운영 연결 전 별도 구현/실증이 필요하다: 고정 Supabase HTTP 전송·리다이렉트/SSRF/timeout/오류 계약, 실제 private bucket ACL/최소권한·기관별 정책, API/worker 동일 DB·bucket wiring, secret manager, 실제 백업 암호화/보존/비용 원장 포함 시점 정합·PITR·RPO/RTO 복구훈련, 연결/비용/데이터 범위 사용자 승인.

Auth 이식 설계에 착수할 저장·권한 경계는 준비됐지만 실제 Auth·서버 멤버십 초기화/운영 세션·프록시 검증은 미완료다. 이번 종료 후 자동 진행하지 않는다. NOT_VERIFIED/NOT_REQUESTED, 인간 검토0/10·0/40, production/G1-C/D 미완료 유지.

작업시간은 아래 최종 검증 메타데이터에 기록한다. 이전 결과 보존 commit08:09 UTC 이후 약24분(사전 확인 제외), 전체 회귀295초·새 복구 drill 합계2.994초. 로컬 PG 전용 컨테이너는 검증 후 중지하고 기존 named volume을 보존한다.
