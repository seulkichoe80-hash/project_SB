# Phase 2D-6 완료 보고

최종 실행: 2026-10-17T11:10:04.977006+00:00. 합성/오프라인 영속 작업·관리자 조회 범위를 완료했다. 의미 검증·관리자 승인·직원용 공식 게시·실제 모델·UI·배포 완료를 뜻하지 않는다.

## 1. 구현 기능·변경 파일

오프라인 후보 추출 → 근거·그래프 검증 → 서식 관계를 영속 workflow job/독립 worker/API로 연결했다. 스냅샷/원본 SHA/parse attempt/chunk generation/카탈로그/설정 고정, 중복 방지·lease fencing·갱신/만료/최대3회·취소/분류된 오류·재시도 이력을 구현했다. 원자 게시=검토용 세대의 원자 조회 가능 전환이며 의미 승인과 다르다.

이번 변경17개(신규12/수정5):

신규:
- apps/api/workflow_jobs.py
- apps/api/workflow_jobs_models.py
- apps/api/workflow_jobs_repository.py
- apps/api/workflow_routes.py
- apps/api/workflow_worker.py
- schemas/workflow-job-request-v1.schema.json
- schemas/workflow-job-status-v1.schema.json
- schemas/workflow-job-result-v1.schema.json
- schemas/workflow-query-v1.schema.json
- tests/test_workflow_jobs.py
- docs/PHASE2D6_WORKFLOW_JOBS.md
- outputs/PHASE2D6_REPORT.md

수정:
- apps/api/main.py: 파싱 활성 factory에 서비스/경로 연결. 기존 인증·응답 경로 유지.
- apps/api/workflow_snapshot.py: 기존 _read 본문을 같은 _read_in으로 재사용하여 저장 트랜잭션 안에서 검사. 기존 모델·계약은 변경하지 않음.
- ARCHITECTURE.md, TASKS.md, TEST_PLAN.md: 이번 단계 절만 추가.

## 2. DB 추가·마이그레이션

필수 workflow_jobs/workflow_generations/workflow_candidates/workflow_review_issues/workflow_form_links의5개 테이블과, 재시도 이후 오류/취소 사유 보존용 workflow_job_events를 비파괴 추가했다. 기존 Phase 2D-5의 workflow_form_catalog를 재사용/없으면 초기화한다. 원본/기존 documents·versions·source_blocks·chunks·EvidenceRef 구조는 변경하지 않는다. 기존 user_version=2를 유지하고 schema_extensions.workflow_jobs=1을 기록한다.

6개 workflow 작업/결과 테이블은 SQLite complete_statement를 이용해 단일 transaction으로 생성하며 미래 확장 버전은 차단한다. 서비스 반복 초기화·실제 서버 재시작·SQLite 백업 복원이 PASS다. 새 합성 DB PRAGMA integrity_check=ok, foreign_key_check=[]를 확인했다. 기존 자료를 삭제/교체하는 마이그레이션은 없다.

저장 직전 전체 원본 재파싱/스냅샷 검증 뒤 동일 SQLite transaction에서 원본 bytes SHA, 현재 활성/등록/기관/parse/chunk/source_blocks/chunks/카탈로그 및 lease를 다시 확인한다. 세대·후보·검토 이슈·서식 관계·완료 상태·이력을 한 번에 commit한다. form_links INSERT를 강제로 실패시켜 전체 결과4개 테이블이0행으로 롤백되고 작업 실패/재시도 후 정상 복구됨을 검증했다.

## 3. Workflow API

모두 `/documents/{document_id}/versions/{version_id}/workflow` 아래다. 요청·응답 strict Pydantic 및4개 JSON Schema를 추가했다.

| Method | 경로 suffix | 기능 |
|---|---|---|
| POST | /jobs | 현재 스냅샷 고정·오프라인 작업 등록,202 |
| GET | /jobs/{job_id} | 상태·오류 분류·이벤트 이력 |
| POST | /jobs/{job_id}/retry | retryable 실패 재시도,202 |
| POST | /jobs/{job_id}/cancel | queued/processing 취소 |
| GET | /candidates | 현재 검토 후보 목록 |
| GET | /candidates/{candidate_id} | 후보 상세(1개 목록 envelope) |
| GET | /review-issues | 검토 이슈, 선택 candidate_id query |
| GET | /form-links | 서식 후보 관계, 선택 candidate_id query |
| GET | /candidates/{candidate_id}/evidence | 원본 재해결한 canonical EvidenceRef |

POST jobs body는 기본 {} 또는 settings/snapshot_settings다. snapshot/기관/provider/승인 상태를 클라이언트가 주입할 수 없다. 모든 경로는 서버 membership manager만 허용한다. reader/worker403, 타기관/잘못된 ID404, 익명401, Origin/CSRF 실패403, 잘못된 body422, stale/state 충돌409다. no-store/Vary:Cookie를 유지한다. claim 토큰/해시·전체 원본 snapshot은 API로 노출하지 않는다.

## 4. 영속성·worker 복구

별도 `python -B -m apps.api.workflow_worker --data-dir ... --institution-id ... --once`를 실제 프로세스로 실행하여 completed를 확인했다. worker claim 후 프로세스를 강제 종료하고 새 service에서 lease 만료/attempt2로 회수·완료했다. 서버 재시작과 DB 백업 복원 뒤 후보·서식 관계가 유지됐다. 만료/취소/중복/틀린 token·기관의 claim은 저장할 수 없다. heartbeat와 프로세스 timeout을 사용하며 무한 갱신하지 않는다.

queued/processing/completed/failed/cancelled 전이, retryable/permanent/stale 분류, 최대3회 소진을 검증했다. 재시도 후 완료돼도 이전 실패 이벤트가 남는다. 같은 고정 입력은 작업1개를 반환한다. completed/cancelled는 terminal이고 동일 입력 재요청은 기존 작업을 반환하며 취소 재개 API는 없다. 새 입력·설정·카탈로그는 새 세대다. 늦게 완료된 옛 세대는 더 최신 completed 세대를 덮어쓰지 않는다.

## 5. 기관 격리·EvidenceRef

worker는 trusted local operator이며 기관별로 claim한다. 내부 manager 문맥은 서버 소유 offline pipeline 호출에만 사용하며 웹 사용자에게 worker 권한/endpoint를 제공하지 않는다. 실제 쿠키 로그인 경로에서 upload→parse/chunk→activate→workflow enqueue→complete→GET을 통합 검증했고 Origin/CSRF/reader/로그아웃 회귀도 확인했다. 인증 공급자는 MockSupabaseTransport이며 실제 원격 호출은 없다.

활성 버전·등록 해제·청킹 세대·원본 해시·서식 카탈로그 변경 중 처리한 결과는 저장하지 않는다. 이미 저장된 결과도 조회마다 현재 snapshot/원문 근거를 재해결한다. payload digest·분리 저장 행·현재 서식 관계를 대조하여 위조 span/저장 행·구버전/타기관 근거를 차단했다. source review issue 순서는 프로세스별 집합 순서 차이로 stale 오판하지 않도록 정규화해 비교한다.

모든 결과는 semantic_verification=NOT_VERIFIED, administrator_approval=NOT_REQUESTED, publishable=false다. 서식 최종 선택/필수 여부도 미확정이다.

## 6. 실제 테스트

- 영향 시험: `.venv/bin/python -B -m unittest discover -s tests -p test_workflow_jobs.py -v` → **49 PASS**,22.143초. 증거 work/phase2d6/focused-final.log.
- Phase Gate: `.venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output work/phase2d6/backend-final.json` → **전체409 PASS / FAIL0 / SKIP0 / BLOCKED0**, 113.299초.
- 기존360개 test ID가 최종 실행에 모두 포함됨을 대조했다. Phase2A~2D-5 문서/원본/파싱/청킹/검색/RAG/인증/계약 회귀와 신규49개가 모두 실행됐다. 최종 Python code_sha256이 현재 코드와 일치한다.
- 네트워크 가드 probe PASS, blocked_external_attempts=0, actual_external_provider_calls=0. Python/상속 Python 하위 프로세스에 비루프백 DNS/TCP를 차단하며 loopback은 허용한다. 실제 Supabase·LLM·임베딩 호출0.
- 신규 범위는 작업/전이/중복/동시 claim/lease/최대재시도/이력·취소, worker CLI/kill·복원/서버 재시작, 원자 롤백·late generation, 현재성/근거 위조/원본해시/기관·reader·쿠키/CSRF/Origin/토큰 비노출, 빈 후보·schema/migration/FK 검증을 포함한다.
- 응답 모델 도입 중 strict tuple/JSON 배열 변환 오류를 발견해 모델 객체 반환으로 수정했다. 수정 전 실패 기록(focused-3.log 포함)을 삭제하지 않았다. 위 최종 실행은 모두 통과다.
- UI/typecheck/build·실제 모델/공개 의미 goldset·HWPX 시각/자동 작성·운영 클라우드는 이번 미실행이다. 과거 UI 수치를 새 PASS로 사용하지 않는다. 기존 Starlette/httpx deprecation warning은 남아 있다.

실제 API/DB 사례는 work/phase2d6/api-example.json에 보존했다. queued→completed와6개 GET(작업/목록/상세/검토/서식/근거)이 모두200이며 원본 예시/버전 식별자는 합성이다. 전체 raw 증거는 backend-final.json/log/network.json, preservation-check.json에 새로 남겼다.

## 7~8. 보존·Git

브랜치 feat/phase2d-offline-extraction. 시작 HEAD c2c96408c783c1ce61792ff162c325525b032b3a, Phase2D-5 변경10개를 비밀키 패턴·archive/hash 검사 후 승인된 로컬 보존 커밋 **56b484d2042c1ce548f9a35f8986a62a0d446222**으로 저장했다. 현재 HEAD도 동일하다.

보존 사본 /tmp/sb-phase2d6-preservation/phase2d5.tar.gz와 manifest.json. 기존2D-5 구현·스키마·테스트·계약·보고7개 해시, 과거 raw증거6개 바이트가 일치한다. 기존 원본·fixture·과거 보고를 변경/삭제하지 않았다. 새로운 기록은 별도 경로다. 비밀키/자격증명 패턴 검사 발견0이며 새 시험 자료는 합성 데이터다. 패턴 검사로 개인정보 완전 검출을 주장하지 않는다.

이번17개 파일은 미커밋(신규12/수정5), staging0이다. 기존 테스트/fixture 수정0. main 직접 변경·원격 push/merge·배포·실제 계정/키 등록은 하지 않았다.

## 9~11. 남은 위험·UI 착수·시간

SQLite 단일 저장소/로컬 worker 검증이며 다중 호스트·공유 원본 저장소·클라우드 DB·대규모 부하/장애 운영은 미검증이다. 조회마다 재파싱·근거/서식 재검증하고 전체 snapshot을 저장하므로 큰 문서/카탈로그의 처리 시간·잠금 경합·보관 용량은 추가 검증이 필요하다. 취소된 동일 입력의 재개 API와 자동 retry 스케줄러는 없다. 검증 트랜잭션 이후의 변경까지 영구 고정하는 공식 승인/게시 계약은 미구현이다.

오프라인 어휘 후보·규정/조건/필수성은 의미 검증 미완료다. 이 단계는 Phase2D의 합성 오프라인 백엔드 연결 범위 완료이며 실제 의미/운영/제품 전체 완료가 아니다.

React 업무지도·원문 검토 UI는 별도 사용자 승인 후 이 manager API를 기반으로 개발 착수 가능하다. 세대/기관/버전·NOT_VERIFIED·검토 이슈·서식 미선택과 원문 EvidenceRef를 유지하고 공식 절차/직원 게시로 표시하지 않아야 한다. 실제 로그인 공급자/배포는 별도 승인·실증 조건이다. 이번에는 UI나 이후 단계를 시작하지 않았다.

보존 준비부터 최종 검증/보고 작성까지 약 831초(13.8분), 사전 문서 점검은 별도다. 신규 패키지 설치·환경 설정 변경은 없었다.
