# 배포 준비 3단계 — Private Storage·복구 계약

범위는 **Fake 전송으로 검증하는 비공개 원본 객체 어댑터와 application-schema 복구**다. Supabase 실제 HTTP 전송·bucket ACL·키 효력·운영 백업 성공을 주장하지 않는다. SQLite/LocalOriginalStore/deny-all 인증 기본값과 기존 HTTP 응답은 유지한다. FR-01/05/06/07/08/14/15/18, 원본 불변·기관 격리·EvidenceRef 및 worker fencing 계약에 연결한다.

## 구성과 시작 경계

- `apps/api/private_storage.py`: strict `PrivateStorageSettings`, `StorageTransport` 계약, `FakeStorageTransport`, `PrivateOriginalStore`, `StorageRegistry`.
- 설정은 HTTPS의 고정 Supabase project 형식, private=true, 서버 전용 SecretStr, real_calls_enabled=false다. 실제 키를 넣지 않는다. 현재 transport는 **정확히 FakeStorageTransport만** 허용하며 callback·임의 subclass·실 HTTP client를 거부한다. URL 설정 검사는 공급자 연결/공식 API 호환 실증이 아니다.
- `create_app(..., repository=repo, store=PrivateOriginalStore(...))`의 명시 로컬 주입만 지원한다. 환경 변수에서 원격 Storage로 자동 전환하지 않는다. 실제 API/독립 worker 운영 wiring은 미완료다. preflight는 `FAKE_ONLY_IMPLEMENTED_NOT_CONNECTED`와 `private_storage_production_transport_not_wired`를 보고하며 production은 계속 BLOCKED다.
- `migrations/storage/001_private_storage.sql`: 별도 checksum version table과 `private_storage_objects`, `private_storage_restores`를 추가한다. 명시 PrivateOriginalStore 생성 시 동일 DB transaction에서 적용한다. 기존 SQLite/PG baseline migration·테이블·데이터를 변경하지 않는다. 알 수 없는 기존 Storage schema/checksum은 거부한다.
- 기존 `DocumentService`는 로컬 저장소 시그니처를 보존하고, private 저장소에만 서버 Principal과 현재 UnitOfWork를 전달한다. 파싱·청킹·업무절차·서식·EvidenceRef 원본 재해결도 같은 경계를 사용한다. 이미 열린 domain transaction을 재사용하므로 PG 전역 guard/SQLite 쓰기 잠금을 중첩 획득하지 않는다.

## 객체 및 접근 계약

경로는 `institutions/<기관ID SHA256>/originals/<서버 UUID>`다. 파일명·원문·사용자 경로는 넣지 않는다. 이는 가명 경로이며 암호화나 접근 권한을 대신하지 않는다. API의 인증/서버 멤버십 검사 후 전달한 Principal을 사용해 DB의 기관·버전·등록 상태·활성 버전을 다시 확인한다. reader는 등록된 활성본만, worker는 등록된 문서만, manager의 과거 원본 조회는 기존 계약대로 유지한다. 등록 해제 자료를 현재 업무 후보로 사용하는 것은 기존 엔진에서 계속 거부한다. pending 업로드의 사전 조회는 해당 기관 manager만 허용한다.

서비스 키·장기 서명 URL·직접 객체 주소를 HTTP 응답에 반환하지 않는다. 브라우저는 기존 서버 원본 조회 경로만 사용한다. overwrite/upsert/delete/move/signed-URL 메서드가 없다. 업로드/조회 때 실제 bytes·길이·provider metadata·DB SHA256/크기를 모두 대조한다. 20MiB 한도, 경로·크기·해시가 어긋나면 실패한다. 정적 오류 코드만 사용하고 Fake 기록에는 작업 종류만 남긴다.

## DB와 객체 저장소의 일관성

단일 분산 transaction은 없다. 순서는 **DB pending upload_intent → DB 객체 planned/시도 기록 → put-if-absent → read-back 검증 → DB uploaded → 기존 문서 metadata commit**이다. 물리 객체 존재만으로 문서를 조회 가능하게 하지 않는다.

| 실패 | 안전 처리 |
|---|---|
| 객체 put 이전 실패/timeout | 원본 metadata는 게시하지 않음, unknown/실패 intent 기록 |
| put 성공 후 응답 유실 | 덮어쓰지 않음. 같은 pending intent/같은 bytes의 명시 재시도는 먼저 get 검증, 최대3시도 |
| 부분 업로드·SHA/크기 불일치 | quarantined, 조회/재사용 차단. 수정·삭제 없이 보존 |
| 객체 성공·DB metadata commit 실패 | DB rollback, 비공개 orphan으로 남음. 대사로 격리 |
| 동시 중복 등록 | 기존 문서 중복 계약 재확인. 경합으로 생긴 추가 원본은 orphan 대사 대상 |
| 기존 문서 객체 조회 실패 | metadata가 있어도 bytes/근거를 성공으로 반환하지 않음 |

`store.reconcile(manager)`는 해당 기관 prefix만 완전 페이지 순회한다(최대20,000개). 잘못된 경로/중복 listing은 실패한다. orphan은 **DB 상태만 quarantine**하며 이동/삭제/자동 문서 복원하지 않는다. missing/무결성 문제/pending은 구조화 코드로 표시한다. 비가역 quarantine을 자동 해제하지 않는다. 실패 intent의 객체를 새 요청에 임의 연결하지 않는다. 운영자가 보상·재처리 여부를 판단해야 한다. 실제 공급자의 listing 일관성·네트워크 재시도·보존 정책은 별도 실증 대상이다.

## 백업·복구

`StorageBackupService`는 공개 API나 기관 관리자 버튼이 아닌 **신뢰된 오프라인 운영자**용이다. 명시 `BackupAuthority`가 전체 application 기관을 포함해야 한다. 이 객체를 브라우저 입력으로 구성하지 않는다.

1. DB transaction과 Fake 객체 lock을 함께 획득한다. 등록 해제 원본도 보존한다. pending 업로드·orphan·quarantine·missing·알 수 없는 schema가 있으면 완전한 백업 생성을 거부한다.
2. application 테이블과 원본 bytes를 복사하고 snapshot ID·원본 hash/크기·기관·버전·table hash/행수/열·schema 계약·UTC 시점을 manifest에 고정한다. 물리 객체 전체 inventory와 DB version/registry의 일치를 검증한다.
3. `save_bundle`은 새 디렉터리에만 기록한다(디렉터리0700/파일0600, exclusive create/fsync, COMPLETE marker 마지막). 기존 복원 가능한 백업을 덮어쓰지 않는다. 원본/인증 데이터가 포함되므로 `work/` 같은 Git 제외 private 위치에만 둔다. 별도 안전 경로에 manifest SHA를 보관한다.
4. `load_bundle`/restore에는 **별도 신뢰 경로의 manifest SHA**가 필수다. 자체 hash만으로 작성자 진위를 보장하지 않는다. 혼합 snapshot, 변조/누락/잘못된 기관·버전·경로, symlink, 크기 초과를 거부한다.
5. 새 격리 DB/schema와 비어 있는 같은 bucket namespace의 Fake 대상에만 복원한다. 기존 운영 DB에 덮어쓰거나 자동 cutover하지 않는다. 객체를 먼저 immutable copy/read-back한 뒤 모든 application 행과 활성 포인터·완료 receipt를 단일 DB transaction으로 복원한다. PG 이벤트 sequence도 복구한다.
6. 중간 실패 시 DB 전체 rollback. 먼저 복사된 객체는 private/unreferenced로 보존하며 같은 manifest의 명시 재시도에서 hash 일치 객체만 재사용한다. 부분/다른 객체는 수정 없이 거부한다. 완료 후 같은 manifest/대상 digest이면 ALREADY_RESTORED, 대상이 바뀌었으면 복구를 거부한다.
7. 세션은 전부 revoked, 인증 challenge 제거, 진행 중 parse/chunk/workflow claim/lease는 fence하고 queued 또는 재시도 한도 초과 failed로 전환한다. worker는 새 claim을 받아야 한다. NOT_VERIFIED/NOT_REQUESTED 및 미승인 후보 상태는 승격하지 않는다.

**제약:** 최대64MiB/테이블10만행의 오프라인 검증용 application snapshot이다. 별도 schema의 공급자 비용 원장은 `excluded_components`로 명시하며 이 bundle의 복구 범위가 아니다. 전체 클러스터 backup/PITR·Storage 실물 복제·암호화/키복구·별도 원장과 동일 시점 fencing·보존기간/RPO/RTO·원격 재난복구는 BLOCKED다. 실제 운영에서는 쓰기/worker 중지 또는 검증된 snapshot/barrier와 immutable 객체 inventory, pg_dump/PITR 및 비용 원장 별도 복구를 조정해야 한다. 운영 재시작 전 세션 철회·불확실 비용 hold·권한·원본/EvidenceRef 재검증이 필요하다.

## 실행과 검증

기존 가상환경/lockfile을 사용하며 새 의존성은 없다. PostgreSQL fixture 시작/선택은 [이전 단계](DEPLOYMENT_POSTGRES.md)의 격리 loopback 계약을 따른다. 실제 cloud DSN이나 키는 넣지 않는다.

```bash
# 신규 Storage 검사: DSN 없으면 PG 부분은 SKIP/BLOCKED이며 PG PASS가 아니다.
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test .venv/bin/python -B -m unittest discover -s tests -p test_private_storage.py

# 새 경로를 사용할 것. 객체 원문/DB 사본은 private work 안에만 기록한다.
.venv/bin/python -B scripts/validation/check_private_storage_recovery.py --backend sqlite --data-dir work/my-new-storage-drill-sqlite
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test .venv/bin/python -B scripts/validation/check_private_storage_recovery.py --backend postgresql --data-dir work/my-new-storage-drill-pg

# Phase Gate 전체 backend: 기존 증거를 덮어쓰지 않도록 새 output 지정
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test .venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output outputs/my-new-storage-backend.json

.venv/bin/python -B scripts/validation/deployment_preflight.py
```

검사는 Fake 성공/장애·동시 중복·기관/권한·부분 저장/rollback·orphan·immutable disk bundle·checksum·세션 철회·stale claim·EvidenceRef 재해결과 실제 로컬 PG를 포함한다. Python socket guard는 C libpq를 가로채지 않으므로 PG의 `local_test=True` DSN loopback 강제를 함께 사용한다. 외부 연결 성공/운영 Auth 완료 또는 사람의 의미 검토 PASS로 해석하지 않는다. 다음 Auth 단계는 별도 사용자 요청 후에만 수행한다.
