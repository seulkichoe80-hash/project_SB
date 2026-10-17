# Phase 2A 로컬 자료 관리 백엔드

2026-10-16. 사용자 승인 범위는 로컬 첫 수직 기능이다. 전체 웹앱, 파싱/AI 분석, 실인증, 배포 완료를 뜻하지 않는다. 전체 G1 및 G2는 미완료다.

## 코드와 실행

`apps/api/main.py`는 HTTP/인증 경계, `models.py`는 인증 주체·Pydantic 상태 요청, `service.py`는 권한·중복·버전·상태 정책, `repository.py`는 SQLite SQL/트랜잭션, `storage.py`는 원본 저장 어댑터, `formats.py`는 제한된 형식 수용 검사다. `create_app(data_dir, store, repository)`로 저장소를 주입한다. PostgreSQL/객체 저장소 어댑터는 미구현이며 같은 동기 작업/트랜잭션 계약을 구현해야 한다.

Python 3.12에서 저장소 루트를 작업 디렉터리로 사용한다. 새 PC의 온라인 설치 명령은 안내이며 이번 실증은 기존 로컬 wheelhouse를 사용한 새 venv 설치다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-api-lock.txt
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
.\.venv\Scripts\python.exe scripts/validation/run_phase2a_checks.py --output outputs/phase2a/VALIDATION_NEW_RUN.json
```

실제 현재 PC 검증 인터프리터는 `work/phase2a/venv/Scripts/python.exe`다. `work/phase2a/runtime/metadata.sqlite3`와 `originals/`가 기본 데이터 경로이며 Git 제외다. 운영 URL이 없고 기본 자료 API는 모두 401이다. `/health`만 비인증이며 `local_only`, `authentication=deny_all`, `public_deployment_ready=false`를 알린다. API 문서 UI도 열지 않는다. 테스트 하네스의 모의 인증은 실제 로그인 방법으로 사용하지 않는다.

`requirements-api.txt`는 직접 런타임 의존성, `requirements-api-test.txt`는 전체 회귀용 추가 의존성, `requirements-api-lock.txt`는 이번 Windows/Python 3.12 시험 환경의 전이 의존성까지 고정한 목록이다. 다른 OS/심사자 클린 실행과 취약점 점검은 별도다. Starlette가 기존 httpx TestClient에 deprecation 경고를 내지만 이번 계약은 통과했다. 새 라이브러리를 추가해 경고만 숨기지 않았다.

## HTTP 계약

모든 자료 경로에 신뢰 가능한 서버 인증 주체가 필요하다. 기관 ID는 URL·query·헤더·요청 본문에서 권한으로 받지 않는다. 테스트는 FastAPI `dependency_overrides[authenticated_principal]`로 직접 생성한 `Principal(subject, institution_id, role)`을 주입한다. 실제 JWT/기관 멤버십 검증은 다음 보안 작업이다. 관리자(manager)는 등록/이력/활성화/등록 해제, worker는 처리 상태 전이, reader는 현재 활성 자료 조회만 가능하다. 관리자는 자기 기관의 등록 해제된 이력·원본에 접근할 수 있다. 타기관은 404, 역할 부족은 403, 미인증은 401이다.

| 메서드·경로 | 역할과 동작 |
|---|---|
| GET /health | 로컬 상태만 공개 |
| POST /documents?filename=sample.pdf | manager, 원본 raw bytes 등록. 신규 201, 동일 내용 200 |
| POST /documents/{document_id}/versions?filename=sample.pdf | manager, 기존 논리 문서의 새 버전 |
| GET /documents?active_only=true | 자기 기관 활성 버전. manager만 false로 후보/과거 등록 버전 조회 가능 |
| GET /documents/{document_id}/versions/{version_id} | 권한 범위 메타데이터 |
| GET /documents/{document_id}/versions/{version_id}/original | 권한/해시 검사 후 attachment, no-store/nosniff |
| POST /documents/{document_id}/versions/{version_id}/transitions | target/revision/claim_token 요청, 낙관적 버전 검사 |
| POST /documents/{document_id}/versions/{version_id}/activate | manager, 완료/해시 정상인 버전만 원자적 활성화 |
| DELETE /documents/{document_id} | manager, 논리 등록 해제. 원본 물리 삭제 없음 |

등록은 multipart가 아니라 단일 파일 raw body다. `Content-Type: application/pdf`, `application/hwp+zip` 또는 `application/octet-stream`, `X-Data-Classification: synthetic` 또는 `public`이 필요하다. 이 선언은 민감정보 자동 탐지가 아니다. 허용 데이터에 대한 관리자의 확인이 필요하며 실제 행정자료 사용은 금지한다. 기관 ID를 클라이언트가 주입해도 인증 주체의 기관만 사용한다.

오류 응답은 `{error: code}`이며 인증/요청 스키마 오류는 FastAPI의 표준 detail 형식이다. 크기 413, 형식 415, 파일명/자료 선언 400, 상태·해시 409, 저장/DB 예외 503이다. 예외 문자열·파일 바이트·외부 경로는 오류 본문에 넣지 않는다. 운영 실행 시 access log를 끄고 상위 프록시에서도 query/원문/토큰 기록 정책을 별도 검증한다.

## 데이터 모델과 정책

| 테이블 | 필드·관계 |
|---|---|
| documents | id PK, institution_id, registered, active_version_id FK versions.id, created_at |
| versions | id PK(원본 저장 키), document_id FK, number, original_name, size, mime, format, sha256, created_at, actor, state, revision, claim_hash |
| upload_intents | id PK(저장 시도 키), institution_id, pending/committed/failed/retained_duplicate, version_id 참조 식별자, created_at |
| events | id PK, version_id FK, action, actor, created_at |

documents 1:N versions, versions 1:N events. upload_intents는 실패 시 버전이 없어도 남는 독립 대사 기록이므로 version_id에 FK를 강제하지 않는다. institution_id는 documents와 intent에 보관하고 모든 버전 접근은 소유 문서의 기관을 재검사한다. 원본명은 표시 메타데이터일 뿐 저장 경로가 아니다. 상태/활성은 별개이며 활성 상태는 registered와 단일 active_version_id로 계산한다. 한 논리 문서의 (문서, 버전번호), (문서, 해시)는 유일하다. 기관 삭제·회원 관리·원본 폐기 API는 없다.

동일 이름/다른 내용은 별개 문서다. 동일 기관·활성 등록 문서들에 같은 내용을 신규 등록하면 기존 버전을 반환하고 이름/상태를 수정하지 않는다. 같은 논리 문서의 동일 내용도 기존 버전 반환이다. 다른 기관은 해시가 같아도 별도 자료와 파일을 갖는다. 등록 해제된 문서는 자동 재활성화하지 않으며 이후 새 등록은 새 문서가 된다. 동시 중복은 최종 DB 트랜잭션에서 재검사한다. 경합으로 이미 쓰인 중복 원본은 retained_duplicate 의도로 보존하며 삭제하지 않는다.

## 원본·DB 일관성과 복구

1. 형식/크기/역할/기관 검사 후 pending intent를 먼저 커밋한다.
2. UUID hex 키로만 `xb` 배타 생성·flush/fsync·읽기전용 속성을 적용하고 SHA-256을 다시 확인한다. 파일명 충돌/경로 조작/재덮어쓰기 API가 없다.
3. `BEGIN IMMEDIATE` SQLite 트랜잭션에서 문서·버전·event·intent committed를 게시한다. 실패 시 DB 롤백, 정상 조회에 부분 파일을 게시하지 않는다.
4. 저장 실패는 intent failed를 남긴다. 실패 기록도 불가능한 DB 장애/강제 종료면 pending이 남는다. `service.reconcile()`는 pending/failed/retained_duplicate 식별자를 로컬 운영자에게 제공한다. 자동 원본 삭제나 미검증 파일의 자동 게시를 하지 않는다. 장애 원인 해결 후 새 등록으로 재시도한다.

부분/고아 파일은 비공개 저장 디렉터리에 남는다. 이것은 원본 보호를 위한 의도적 보존이며 용량 누적·운영자 대사·별도 승인 폐기 정책이 필요하다. 전원 장애 내구성과 스토리지 ACL/WORM, 클라우드 원자성/백업 복원은 별도 C 검증이다. 읽기전용 속성은 OS 관리자를 막는 보안 경계가 아니므로 다운로드·처리 완료·활성화·중복 반환에서 해시를 재검증한다. 디렉터리는 웹 정적 경로로 제공하지 않는다.

## 처리 상태

`registered → queued → processing → completed | failed`, `failed → queued`만 허용한다. queued까지 manager/worker, processing 이후는 worker만 변경한다. 요청 revision과 DB revision을 트랜잭션 안에서 비교하고 변경마다 증가시켜 중복 claim과 오래된 요청을 거부한다. processing 진입 시 임의 claim token을 1회 응답하고 DB에는 해시만 보관한다. 완료/실패에는 이 토큰도 필요하다. 등록 해제 후 모든 전이를 거부한다. 처리 중 프로세스가 강제 종료되어 토큰을 잃으면 자동 재실행하지 않는다. 다음 worker 단계에서 lease/운영자 복구 규칙을 추가해야 한다.

이번 completed는 **자료 관리 단계의 처리 완료와 원본 무결성 확인**이다. 실제 문단/표 파싱·AI 분석 완료를 뜻하지 않는다. 자동 파싱 worker/스케줄러는 없다. 새 버전은 등록만으로 활성본을 바꾸지 않으며 완료 후 명시적 activate에서만 단일 포인터를 변경한다. 후보 실패·잘못된 전이·해시 변조는 기존 정상 활성본을 유지한다. 등록 해제는 포인터를 비우고 논리 플래그를 내리며 파일을 보존한다. 미래 색인/캐시의 폐기 이벤트 소비는 Phase 2B 이후 별도 구현한다.

## 형식 지원 한계와 다음 게이트

파일은 최대 20MiB, PDF는 `%PDF-1.x`, EOF/catalog/pages와 classic xref/객체 offset을 검사하고 JavaScript/Launch/EmbeddedFile/Encrypt 표식을 보수적으로 거부한다. 압축 xref/PDF 2.0·암호화·첨부파일은 이번 수용 범위 밖이다. 전체 PDF 렌더/파싱/백신 검증으로 표현하지 않는다. HWPX는 ZIP mimetype/필수 content.hpf·header·section/XML 안전 파싱/ZIP CRC를 검사한다. ZIP 경로 탈출/중복 이름/암호화/1,000개 초과/총 해제 200MiB 초과/압축비 100 초과를 거부한다. XML 순서·시각 읽기 순서·그림 픽셀 품질은 B-01 파싱 검증으로 남는다.

FR-01·14·15·18의 로컬 부분과 NFR-01/02/06/07을 검증했다. WEB-02/03/05/06/07은 모의 주체·로컬 저장/논리 해제 범위만 검증했다. WEB-01 브라우저, WEB-04 실제 시크릿/배포, WEB-08 AI, C 운영 보안·백업/제한·실인증·클라우드·D 심사 독립 실행은 NOT_RUN이다. 전체 FR/WEB 요구사항 완료로 승격하지 않는다.

Phase 2B는 B-01 지원 범위 검증을 먼저 보완하는 파서/SourceElement 수직 기능 또는 실인증 경계 개발부터 착수할 수 있다. 실제 AI·검색·지도는 해당 B-02/03/04 선행 검증 후 진행한다.
