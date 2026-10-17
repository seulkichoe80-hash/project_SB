# Phase 2D-6 영속 Workflow 작업·관리자 조회

## 범위

기존 오프라인 추출 → 근거/그래프 검증 → 서식 관계를 SQLite 작업과 별도 worker로 연결한다. 의미 검증·관리자 승인·공식 절차 확정·직원용 게시·UI·실제 외부 API는 추가하지 않는다. 모든 결과는 NOT_VERIFIED / NOT_REQUESTED / publishable=false다. 원자 게시라는 용어는 관리자용 후보 세대가 원자적으로 조회 가능해지는 것만 뜻한다.

## 마이그레이션과 데이터

파싱 활성 create_app과 trusted worker의 WorkflowJobService 초기화 시 SQLite adapter가 한 트랜잭션으로 CREATE IF NOT EXISTS를 실행한다. 기존 documents/versions/source_blocks/chunks/원본/EvidenceRef 계약과 PRAGMA user_version=2를 바꾸지 않는다. schema_extensions의 workflow_jobs=1을 기록하며 알 수 없는 확장 버전은 차단한다. executescript의 암묵 커밋을 피하고 complete_statement로 개별 SQL을 실행한다. 재시작/백업 복원/반복 초기화·FK/integrity_check를 시험한다.

필수 추가 테이블:
- workflow_jobs: 기관/문서/버전, 전체 immutable snapshot JSON과 digest, 설정·오프라인 모델/규칙/검증 계약, 카탈로그 digest, idempotency key, generation 순서, state/attempt/claim_hash/lease/오류.
- workflow_generations: completed job의 검증 결과 envelope와 digest. 조회 가능한 세대 선택은 같은 기관·문서·버전의 completed 세대 중 최대 generation이다.
- workflow_candidates: 세대별 후보 JSON.
- workflow_review_issues: 원본 검증 및 서식 검토 이슈. 기존 이슈 계약은 그대로 보존한다.
- workflow_form_links: 세대별 서식 관계 후보 JSON.

실패/취소 사유를 재시도 이후에도 보존하도록 workflow_job_events를 추가한다. queued/processing/failed/retry/cancelled/completed/lease 만료 이력이 상태 조회 events에 포함된다. 원문·예외 메시지·claim 토큰은 이력에 넣지 않는다. 이전 세대나 이력 삭제/자동 정리는 없다.

## 작업과 소유권

POST jobs는 관리자/기관과 현재 활성 원본을 확인하고 전체 문서 스냅샷을 고정한다. 같은 snapshot·설정·pipeline configuration·서식 카탈로그 digest는 동일 작업을 반환한다. 다른 카탈로그나 입력/설정은 새 generation이다. 처리 중 중복 claim은 BEGIN IMMEDIATE로 직렬화한다.

queued → processing → completed/failed, queued/processing → cancelled만 허용한다. failed는 RETRYABLE이면서 attempt<3이고 원본이 여전히 같은 경우에만 명시 retry로 queued가 된다. 취소와 완료는 terminal이며 같은 입력 재요청은 해당 기존 작업을 반환한다. 취소 작업 재개 API는 이번 범위 밖이다. 최대3번의 claim 횟수는 실패/lease 복구 후에도 초기화하지 않는다.

claim은 worker 역할과 기관에 제한하고 랜덤 토큰을 worker 내부로만 전달한다. DB에는 해시만 저장한다. id/기관/attempt/해시/state/미만료 lease를 함께 검사하고 갱신한다. lease 만료는 같은 기관의 다음 claim에서 queued(3회 미만) 또는 failed로 복구한다. heartbeat는 기존 worker.run_once 패턴을 재사용한다. stale worker, 취소된 worker, 중복 execute는 저장할 수 없다.

오류는 RETRYABLE(내부/DB 임시 실패), PERMANENT(검증/무결성 실패), STALE_INPUT(버전/세대/등록·카탈로그·설정 변경)으로 고정 분류하고 안전한 오류 코드만 기록한다. 실제 예외 텍스트는 공개하지 않는다. 임시 실패는 관리자 retry가 필요하고 lease 만료만 worker가 자동 회수한다.

worker는 로컬 trusted operator 프로세스다. 웹 사용자에게 worker 역할/claim endpoint를 제공하지 않는다. 내부 추출 호출에만 동일 기관의 manager 문맥을 구성한다. 실제 운영 membership을 우회하는 로그인 경로로 사용하지 않는다.

```sh
.venv/bin/python -B -m apps.api.workflow_worker --data-dir <private-data-directory> --institution-id <institution> --once
```

--lease-seconds 기본120(1..300), --job-timeout-seconds 기본600(1..3600). --once 생략 시 반복 실행한다. timeout은 프로세스를 종료하여 lease가 만료되게 하며 영원히 갱신하지 않는다. stdout은 고정 상태만 출력한다. worker는 API 프로세스의 BackgroundTasks와 독립이다.

## 원자 저장과 조회 안전성

추출/서식 검증과 원본 SHA·재파싱을 수행한 뒤 저장 직전에 snapshot을 다시 검증한다. 같은 DB 트랜잭션 안에서는 기존 _read_in으로 원본 메타데이터/활성 상태/parse attempt/chunk current/items/source_blocks를 읽어 고정 snapshot 전체와 비교하고, 원본 bytes 해시·서식 카탈로그 digest·lease 소유권을 재확인한다. 이후 generation/candidates/issues/forms/job completion/event를 한 트랜잭션으로 저장한다. 중간 INSERT 실패는 전부 롤백하며 별도 트랜잭션에서 안전한 실패 상태/이력만 기록한다. 늦게 끝난 구 generation은 더 큰 completed generation을 덮어쓰지 못한다.

조회는 현재 활성·등록·기관과 snapshot을 재검사한다. 저장 envelope digest와 분리된 후보/이슈/서식 행을 대조하고 canonical 근거를 원본에 재해결한다. 현재 서식 관계와 저장된 결과가 다르면 stale로 차단한다. 종료 시 최신 generation·snapshot·카탈로그를 다시 확인한다. 재파싱/청킹·활성 변경·서식 해제 후 과거 후보를 현재 절차로 반환하지 않는다. 이력 job status는 등록 문서의 같은 버전에 한해 관리자에게 조회 가능하지만 전체 snapshot/원문/claim 정보는 반환하지 않는다.

## API

공통 prefix: `/documents/{document_id}/versions/{version_id}/workflow`.

| Method | suffix | 의미 |
|---|---|---|
| POST | /jobs | body={} 또는 settings/snapshot_settings, 202·중복 요청은 기존 작업 |
| GET | /jobs/{job_id} | 상태·안전한 오류·이벤트 이력 |
| POST | /jobs/{job_id}/retry | retryable 실패 재시도, 202 |
| POST | /jobs/{job_id}/cancel | queued/processing 취소 |
| GET | /candidates | 현재 검토용 후보 목록 |
| GET | /candidates/{candidate_id} | 후보1개의 목록 envelope |
| GET | /review-issues | 원본/서식 ReviewIssue, candidate_id 선택 query |
| GET | /form-links | 서식 연결 후보, candidate_id 선택 query |
| GET | /candidates/{candidate_id}/evidence | 원본 재해결한 canonical EvidenceRef |

모두 서버 membership 기반 manager만 접근한다. reader/worker의 관리자 API는403, 타기관/존재하지 않는 ID는404다. 익명401, Origin/CSRF 실패403, 잘못된 body422, stale/state 충돌409다. 무결성 오류는422 또는 저장/DB 실패503으로 차단한다. 기존 인증 dependency가 모든 POST의 Origin·CSRF를 검사한다. no-store/Vary:Cookie를 유지한다. 기존 경로/응답은 바꾸지 않는다.

strict Pydantic request/status/result/query 응답과 JSON Schema는 workflow-job-request-v1 / workflow-job-status-v1 / workflow-job-result-v1 / workflow-query-v1.schema.json이다. 조회는 generation_id/job_id와 안전 상태를 포함하며 후보/이슈/서식/근거 payload를 구분한다. 요청으로 snapshot·기관·provider 토큰·승인 상태를 주입할 수 없다.

## 검증과 한계

신규 tests/test_workflow_jobs.py는 중복/상태/lease/최대 재시도·작업 이력·취소·별도 CLI·프로세스 kill/재시작·서버 재시작/SQLite 복원·FK/무결성·부분 저장 트리거 롤백·원본/버전/세대/등록/카탈로그 변경·위조 근거/저장 행·기관/reader/실제 쿠키/CSRF/Origin을 시험한다. 새 합성 원본만 사용하며 기존 fixture는 수정하지 않는다. 실제 결과는 outputs/PHASE2D6_REPORT.md와 work/phase2d6에 기록한다.

SQLite 단일 저장소와 로컬 worker 검증이다. 다중 호스트/공유 객체 저장소/클라우드 DB·대규모 부하·스케줄러 운영은 미검증이다. 조회마다 현재성·근거를 재해결하므로 큰 문서/카탈로그에서 비용이 크다. 전체 snapshot/결과 저장 공간도 커질 수 있다. 읽기의 현재성은 검증 트랜잭션 시점 기준이며 이후 공식 승인/게시에는 별도 원자 재검증이 필요하다. 오프라인 어휘 추출과 의미 검토 보조는 여전히 실제 의미/규정 효력을 인증하지 않는다. React 업무지도·원문 검토 UI는 이 API의 검토 상태·기관/세대·근거 경계를 유지하는 별도 승인 작업이다.
