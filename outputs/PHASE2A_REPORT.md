# 서무ITDA Phase 2A 개발 완료 보고

기준일: 2026-10-16 KST. 작업 루트: `C:/Users/외부망/Documents/Codex/2026-10-16/15-2026-ai-2-itda-prd`. **로컬 자료 관리 Phase 2A 완료**. 전체 Phase 2·G1/G2·운영 배포 완료는 아니다. 외부 API 호출·클라우드 생성·배포·Git stage/commit/push는 수행하지 않았다.

## 1. 실제 구현한 기능

- FastAPI API, Pydantic 상태 요청, SQLite 메타데이터·트랜잭션과 불변 로컬 원본 저장.
- 문서/기관 ID, 원본명, 바이트 크기, canonical MIME·실제 형식, SHA-256, UTC 생성 시각, 버전 번호, 활성/등록 상태. 행위자·revision·이벤트도 기록한다.
- 합성 PDF/HWPX 단일 원본 등록, 20MiB 제한, 확장자/MIME/실제 구조 검사, 경로 조작·ZIP 탈출/폭탄·안전하지 않은 XML·일부 능동 PDF 기능 거부.
- 같은 이름/다른 내용의 별도 저장, 같은 기관/내용의 멱등 반환, UUID 키 배타 쓰기, 원본 덮어쓰기·물리 삭제 API 없음. 중복 반환에도 원본 해시 확인.
- 영속 upload intent→파일 fsync·해시 검증→DB 원자적 게시. 실패 시 미완성 파일 미게시, DB 롤백, failed/pending/중복 보존 의도 대사. 기존 정상 활성본과 과거 원본 유지.
- `registered→queued→processing→completed|failed`, `failed→queued` 상태 머신. revision 및 worker claim token으로 오래된 요청·중복 실행·잘못된 전이 차단. token은 DB에 해시만 저장한다.
- 후보 버전 완료 전 활성화 차단, 완료·해시 정상 시 명시적인 단일 활성 버전 전환, 등록 해제는 논리 플래그/포인터만 변경.
- 서버가 제공하는 인증 주체의 기관·역할로만 접근. 타기관 조회/다운로드/수정/버전 등록/전이 404, reader의 관리·과거 버전 접근 차단, 기본 미인증 401. 테스트에서만 명시적인 모의 주체를 주입한다.

이번 completed는 자료 관리 단계의 무결성 확인 완료다. PDF/HWPX 내용 분석·AI 처리 완료가 아니다. 자동 파싱 worker와 실제 사용자 로그인은 구현하지 않았다.

FR-01·14·15·18, NFR-01/02/06/07 및 WEB-02/03/05/06/07의 로컬 부분에 연결된다. FR-01~19·WEB-01~08의 기존 전체 요구사항은 유지하며 해당 요구사항 전체를 PASS로 처리하지 않았다.

## 2. 신규·수정 파일과 폴더

```text
apps/
  __init__.py
  api/
    __init__.py
    main.py          HTTP·기본 deny-all 인증·앱 구성
    models.py        신뢰 인증 주체·Pydantic 상태 전이 요청
    errors.py        공개 가능한 오류 코드
    formats.py       제한된 PDF/HWPX 수용 검사
    service.py       기관/역할·등록·중복·상태·활성화 정책
    repository.py    SQLite Unit of Work·SQL·트랜잭션
    storage.py       UUID 불변 원본·해시 검사
docs/PHASE2A_BACKEND.md
requirements-api.txt
requirements-api-test.txt
requirements-api-lock.txt
tests/test_document_api.py
tests/test_live_document_http.py
scripts/validation/phase2a_http_server.py
scripts/validation/run_phase2a_checks.py
outputs/PHASE2A_REPORT.md
outputs/phase2a/
  DOCUMENTS_BEFORE.zip
  DOCUMENT_CHANGES.diff
  VALIDATION_RUN_1.json
  VALIDATION_FINAL.json
  PRESERVATION_AND_GIT.json
```

수정: 루트 PRD.md·AGENTS.md·TASKS.md·ARCHITECTURE.md·TEST_PLAN.md·README.md에 제한된 구현 상태/계약/시험 추적과 실행 안내를 반영했다. 이전 ‘앱 미착수’ 설명은 현재 Phase 2A 범위와 구분했다. 제품 요구사항·공모전 기준·일정은 유지했다. Skill은 기존 절차를 명시 적용했으며 내용 변경 없이 보존했다.

작업 중간 파일·가상환경·시험용 DB/원본·환경 장애 로그는 `work/phase2a/`이며 Git 제외다. 이전 Phase 1/기반 코드·fixture·보고·증거 46개 파일을 사전 해시와 비교해 변경 없음. 기존 PHASE1_EVIDENCE.zip 57개 항목과 FOUNDATION_EVIDENCE_V2.zip 22개 항목의 ZIP CRC도 정상이다. 원본 사용자 DOCX/HWPX는 이번 처리 입력으로 사용하거나 변경하지 않았다.

## 3. 주요 API

| 메서드 | 경로 | 동작 |
|---|---|---|
| GET | /health | 로컬 상태와 공개 배포 불가 표시 |
| POST | /documents?filename=… | raw body 등록: 신규201, 중복200 |
| POST | /documents/{document_id}/versions?filename=… | 같은 논리 문서의 후보 버전 등록 |
| GET | /documents?active_only=true | 기관별 활성 목록, 관리자만 false로 후보/이력 조회 |
| GET | /documents/{document_id}/versions/{version_id} | 권한 범위 메타데이터 |
| GET | /documents/{document_id}/versions/{version_id}/original | 해시 확인된 원본 attachment 다운로드 |
| POST | /documents/{document_id}/versions/{version_id}/transitions | target/revision/claim_token 상태 전이 |
| POST | /documents/{document_id}/versions/{version_id}/activate | 완료 버전 활성화 |
| DELETE | /documents/{document_id} | 원본 보존·논리 등록 해제 |

등록에 `X-Data-Classification: synthetic|public`과 적합한 Content-Type이 필요하다. 이 선언은 민감정보 탐지를 대신하지 않는다. 요청 기관 ID는 권한 근거가 아니다. 실제 인증이 없으므로 기본 자료 API는 전부 401이며 브라우저 사용이 가능한 완성 웹앱으로 제공하지 않는다. 테스트 모의 주체를 운영 인증으로 사용하면 안 된다.

## 4. DB 테이블과 관계

| 테이블 | 핵심 관계/역할 |
|---|---|
| documents | 문서 PK, 기관, 논리 등록, 단일 active_version_id FK |
| versions | 문서 FK, 버전번호/원본 메타/해시, 영속 작업 상태/revision/claim_hash |
| upload_intents | 게시 이전 저장 의도와 실패/중단/중복 보존 대사. 실패는 버전 없이도 남음 |
| events | 버전 FK, 등록/전이/활성화/등록 해제 행위자·시각 |

documents 1:N versions, versions 1:N events. 버전번호/해시는 문서 내 유일하다. 모든 변경은 BEGIN IMMEDIATE 트랜잭션으로 직렬화하고 실패 시 롤백한다. 원본 파일과 DB는 하나의 트랜잭션이 될 수 없으므로 intent 게시 프로토콜로 부분 자료 노출을 막는다. PostgreSQL/객체 저장소는 주입 가능한 어댑터 경계만 준비했고 실증하지 않았다.

## 5. 실제 실행 명령과 환경

Windows 11 / Python 3.12.14 / FastAPI 0.143.2 / Pydantic 2.14.1 / Uvicorn 0.54.0 / Starlette 1.8.0 / httpx 0.28.1. 상세 버전·코드 SHA는 [최종 실행 기록](phase2a/VALIDATION_FINAL.json)에 있다.

작업 디렉터리는 프로젝트 루트다. 다음은 실제 실행한 명령이다.

```powershell
# 구현 전 기존 계약 시험: 9/9
& './work/repository-foundation/venv/Scripts/python.exe' -m unittest discover -s tests -v

# 초기 기능 시험: 20 + 기존9 = 29/29
& './work/phase1/venv-clean-check/Scripts/python.exe' -m unittest discover -s tests -v

# 추가 보안/실제 HTTP 시험 반영: 33/33, 중간 증거 보존
& './work/phase1/venv-clean-check/Scripts/python.exe' scripts/validation/run_phase2a_checks.py --output outputs/phase2a/VALIDATION_RUN_1.json

# 독립된 새 가상환경에 기존 로컬 wheel만 설치: 외부 다운로드 없음
$env:TEMP=(Resolve-Path work/phase2a/tmp).Path
$env:TMP=$env:TEMP
& 'C:/Users/외부망/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe' -m venv work/phase2a/venv
& './work/phase2a/venv/Scripts/python.exe' -m pip install --no-index --find-links work/phase1/wheelhouse -r requirements-api-lock.txt
& './work/phase2a/venv/Scripts/python.exe' -m pip check

# SQL 계층 분리/권한 보완 후 최종 전체 회귀: 33/33
& './work/phase2a/venv/Scripts/python.exe' scripts/validation/run_phase2a_checks.py --output outputs/phase2a/VALIDATION_FINAL.json
```

`pip check`: No broken requirements found. HTTP 시험은 tests/test_live_document_http.py가 validation 전용 모의 주체를 명시적으로 주입한 Uvicorn을 127.0.0.1 임의 포트에 별도 프로세스로 두 번 실행했다. 실제 HTTP PDF 등록/원본 일치, 프로세스 종료와 재실행 후 메타데이터/파일 유지까지 검사했다. 시험 서버는 종료했다. 공개 배포나 실제 사용자 인증 시험이 아니다.

초기 네트워크 제한 상태에서 TestClient의 Windows asyncio socketpair 초기화가 대기해 해당 실행을 중단했다. 별도 15초 faulthandler 진단도 socket.accept 대기를 확인했다. 사용자 네트워크 권한 허용 후 같은 방식의 시험이 정상 실행됐다. 이 미완료 시도는 PASS로 계산하지 않았다. CIM 프로세스 조회는 환경 권한으로 거부되어 실행 세션의 Ctrl-C로 기존 대기 시험을 종료했다. 실제 외부 API 호출은 없었다.

## 6. 최종 결과 개수

| 범위 | PASS | FAIL | SKIP | BLOCKED |
|---|---:|---:|---:|---:|
| 신규 자료 관리 시험 | 23 | 0 | 0 | 0 |
| 실제 HTTP·프로세스 재시작 | 1 | 0 | 0 | 0 |
| 기존 계약 회귀 | 9 | 0 | 0 | 0 |
| 최종 전체 | **33** | **0** | **0** | **0** |

필수 16개 시험 주제 모두 실제 실행됐으며 크기/경로/형식/역할/동시중복/DB 실패 등으로 추가 세분화했다. 상세 주제-테스트 매핑은 TEST_PLAN.md, 개별 결과는 VALIDATION_FINAL.json에 있다. 결과 수는 최종 실행 한 번의 테스트 메서드 수이며 중간 29/33회 실행을 합산하지 않는다. 초기 환경 대기 이력과 향후 미실행 항목도 위 합계에 섞지 않는다.

실인증/JWT·HTTPS·CORS 정책·요청량 제한·클라우드 DB/객체 저장/백업 복원·프런트 브라우저·실제 LLM·임베딩·심사 독립 실행은 **NOT_RUN**이다. 유료 호출/공개 배포는 승인 전 실행 제한을 유지한다. 전체 G1을 PASS로 변경하지 않았다.

## 7. 기존 기능 회귀와 보존

구현 전 기존 계약9 PASS, 구현 후 같은 계약9 PASS로 관찰된 회귀 없음. AI 근거·외부기관·비활성 자료 계약, 합성 HWPX v1 부정 fixture와 v2 앵커 검증을 그대로 보존했다. 이전 결과 파일은 덮어쓰지 않았고 새 실행 기록을 추가했다. 루트 문서의 수정 전 사본은 DOCUMENTS_BEFORE.zip, 전후 diff는 DOCUMENT_CHANGES.diff다. 문서 상호 링크 검사에서 누락 링크 없음. 이는 미구현 전체 제품의 회귀 통과를 뜻하지 않는다.

## 8. 미해결 문제와 보안 위험

1. **공개 배포 차단**: 실제 로그인/JWT/기관 멤버십·인증 주체 공급자가 없다. 테스트 하네스는 모의 주체 전용이다. 실제 인증/기관 권한·요청 제한·CORS/HTTPS·시크릿·로그 검증 후에만 공개 운영을 검토한다.
2. **원본 보호 한계**: API는 원본 덮어쓰기/삭제를 제공하지 않고 해시 변조 시 실패한다. 로컬 OS 관리자의 파일/DB 직접 조작이나 전원 장애까지 방지하는 WORM/ACL·백업 내구성은 검증하지 않았다.
3. **실패 원본 보존 용량**: 실패/중단/동시 중복 파일은 비공개 상태로 보존한다. 대사 결과를 운영자가 검토해야 하며 자동 삭제하지 않는다. 승인된 보존·폐기 정책과 용량 관리가 필요하다.
4. **worker 강제 중단**: 상태는 DB에 남지만 processing의 claim token을 잃었을 때 자동 lease 회수/재처리하는 worker는 없다. 다음 worker 구현 시 안전한 만료·운영자 복구·중복 실행 정책을 추가한다.
5. **형식 검사의 제한**: PDF classic-xref와 기본 HWPX 구조를 보수적으로 수용한다. 전체 PDF 규격/백신·HWPX 읽기 순서·픽셀·렌더 검증이 아니다. 공개/합성 선언만으로 민감정보가 자동 탐지되는 것도 아니다. 지원 범위는 docs/PHASE2A_BACKEND.md에 명시했다.
6. **이후 연동**: 실제 파서/색인/캐시/지도는 없으므로 등록 해제·버전 전환에 따른 downstream 무효화는 향후 구현·회귀 대상이다. 현재 SQLite schema v1 초기 생성만 있고 운영 마이그레이션/클라우드 어댑터는 미구현이다.
7. **의존성/재현**: 고정 환경에서 신규 venv 검증은 통과했다. 다른 OS·다른 검증자의 소스 실행·취약점/라이선스 최종 감사는 별도다. TestClient/httpx deprecation 경고는 남아 있고 시험 실패는 아니었다.

## 9. Git 상태와 커밋 후보

로컬 브랜치 main, 아직 커밋 없음. 원격 없음, staged 파일 없음. 초기 저장소 전체가 untracked이므로 `git diff`만으로 이번 변경 목록을 판단하지 않고 사전 파일 해시와 문서 ZIP을 사용했다. 기존 .gitignore를 유지했고 .env·하위 .env·venv·node_modules·work/DB·ZIP의 제외를 실제 git check-ignore로 확인했다. .gitignore 추가 수정이 필요하지 않았다.

커밋 후보는 신규 apps/api/와 패키지 init, requirements-api*.txt, 신규 테스트2개·검증 스크립트2개, docs/PHASE2A_BACKEND.md, 수정 루트 문서6개, 이 보고서와 정제된 phase2a JSON 증거다. 이전 미커밋 문서/fixture/계약 코드도 저장소 전체 후보에 함께 보인다. 전체 목록은 [PRESERVATION_AND_GIT.json](phase2a/PRESERVATION_AND_GIT.json)에 기록했다. 원본·venv·DB·ZIP·diff·임시 로그는 후보에서 제외된다. 제한된 비밀 패턴 검사에 검출 없음이며 완전한 비밀 감사로 표현하지 않는다.

**git add/로컬 commit/remote 등록/push/배포 모두 수행하지 않았다.**

## 10. Phase 2B 착수 판단과 권고

**제한된 Phase 2B 착수는 가능하다.** 로컬 자료 관리의 사용자 완료 조건(실 HTTP/DB 재조회/원본 해시/기관 격리/버전 및 실패 복구/필수 시험/기존 회귀)을 모두 충족했다. 전체 G1은 미완료이며 Phase 2B에서 실제 파서 기능을 확대하기 전에 B-01의 지원 범위·읽기 순서·원문 앵커 검증을 먼저 보완해야 한다. AI·검색·지도는 각각 B-02/03/04 검증을 건너뛰지 않는다.

다음 Codex 작업 권고: “Phase 2B에서 기존 Phase 2A 계약과 증거를 읽고, 공개·합성 정상 PDF/HWPX의 지원 범위/원문 앵커를 먼저 검증하라. 검증된 범위에 한해 읽기 전용 ParserAdapter·SourceElement 저장과 영속 worker 복구/lease를 작은 수직 기능으로 구현하고, 원본·기관·버전·등록 해제·실패 복구 전체 회귀를 수행하라. 실인증은 별도 명시 작업으로 진행하고 LLM/OCR/벡터/React Flow·배포·commit/push는 포함하지 마라.”
