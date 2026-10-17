# Phase 2B 원문 추적 파싱 계약

2026-10-16. FR-02·05·14·15·18 및 NFR-02/03/04/05/06/07의 로컬 파싱 부분이다. 전체 G1/G2, 실제 한컴 시각 순서, 의미 정확성, RAG 품질 통과가 아니다. 기존 요구사항·11/11 제출 일정과 공모전 평가 40/30/30은 유지한다.

## 실행과 호환 경계

```powershell
# Python 3.12, 프로젝트 루트에서 실행
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-parsing-lock.txt
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
# 별도 터미널. institution-id는 신뢰하는 로컬 운영자 설정이다.
.\.venv\Scripts\python.exe -m apps.api.worker --data-dir work/phase2a/runtime --institution-id A
# 단일 작업만 처리: --once
.\.venv\Scripts\python.exe scripts/validation/run_phase2b_checks.py --output outputs/phase2b/VALIDATION_NEW_RUN.json
```

위 새 PC 설치 안내와 이번 PC의 실제 실행 증거는 구분한다. 이번 실행은 `work/phase2b/venv/Scripts/python.exe`를 사용했다. 새 venv에 Phase 2A의 기존 wheel과 공식 PyPI의 PDF 의존성을 설치했고 pip check를 통과했다. 다른 PC/OS의 독립 실행은 미검증이다.

**일반 실행 진입점 `apps.api.main:app`은 parsing_enabled=True**다. 등록 트랜잭션에서 영속 파싱 작업을 생성하고 실제 파싱은 별도 worker가 수행한다. HTTP 요청 안의 FastAPI BackgroundTasks에 의존하지 않는다. 기본 인증은 그대로 deny-all이고 `/health` 외의 자료 API는 401이다. 모의 인증 하네스는 검증용이며 운영 로그인 방법으로 제공하지 않는다. CLI는 파일시스템 권한을 가진 로컬 운영자 도구이지 최종 사용자의 인증 수단이 아니다.

`create_app(..., parsing_enabled=False)`가 factory 기본값으로 남은 것은 Phase 2A-only 임베더/기존 33개 계약을 보존하기 위한 호환 경계다. 운영용 진입점과 이번 신규 34개 파싱 시험은 True다. `uvicorn --factory apps.api.main:create_app`를 파싱 서비스 실행법으로 사용하지 않는다. 어느 모드에서도 실제 인증을 우회하지 않는다. 작업이 생성된 버전은 Phase 2A 수동 transitions로 완료 처리할 수 없고 파싱 완료 전 활성화할 수 없다.

## 파서 및 구조화 블록

`apps/api/parsers/contracts.py`의 ParserAdapter·Anchor·Block이 공통 계약이다. PDFParser와 HWPXParser를 분리하고 서비스에서 SDK/라이브러리 객체를 반환하지 않는다. JSON Schema는 schemas/source-block.schema.json이다. 파서 방법에는 패키지/알고리즘 버전을 기록한다. 현재 버전은 PDF pdfplumber-0.11.9/phase2b-v1, HWPX hwpx-defusedxml/phase2b-v1이다.

각 블록은 document_id, version_id, block_id, block_type, text, source_anchor, extraction_method, order_index, verification_status를 갖는다. block_id는 문서/버전/원본 hash/위치 selector를 포함한 canonical anchor의 SHA-256이므로 다른 버전과 혼용하지 않는다. source_kind는 original_text/original_image/original_structure다. OCR/AI 내용은 생성하지 않는다.

table 블록은 table_shape를, cell은 parent_block_id/row/column/row_span/column_span을 갖는다. 인덱스는 0부터 시작한다. HWPX cell 안의 paragraph는 별도 자식이며 cell.text는 해당 셀의 문단을 모은 원문 표현이다. 향후 청킹은 부모 집계와 자식 텍스트를 중복 색인하지 않도록 선택해야 한다. 빈 원문 요소/실제 빈 셀은 빈 text로 보존하며 없는 셀을 생성하지 않는다. 표 grid는 테이블당 행/열 각 1,000 이하·면적 20,000 이하, HWPX 전체 점유 grid 20,000 이하, 문서 블록 20,000 이하로 제한한다.

모든 결과는 `verification_status=structural_only`, `semantic_verification=NOT_VERIFIED`, `visual_order_verification=NOT_VERIFIED`다. 구조적 재현과 실제 업무 의미·시각 배치의 정확성을 구분한다.

### PDF

- pdfplumber로 문자·줄/표를 추출한다. 표 안 문자는 일반 문단에서 제외하고, 가까운 줄을 보수적으로 묶는다. 문단 경계와 top/left 정렬 순서는 기하학적 휴리스틱이지 원래 저자의 의미 순서가 아니다.
- 선으로 구획된 표의 셀 bbox/행·열/병합 범위를 보존한다. 실제 감지되지 않은 셀은 만들지 않는다. 테두리 없는 표·복잡한 다단·회전·한국어 폰트 전체 호환성은 대표 corpus 검증이 필요하다.
- 페이지는 1부터 시작하는 물리 페이지다. bbox는 pdfplumber 페이지 좌표, 좌상단 기준 points의 `(x0, top, x1, bottom)`이며 소수점4자리로 저장한다. 인쇄된 쪽수와 동일하다고 단정하지 않는다.
- 최대 100페이지. 텍스트/표를 추출할 수 없는 페이지가 하나라도 있으면 실패시켜 불완전 문서를 정상으로 게시하지 않는다. 빈 페이지·스캔/OCR 문서는 이번 보수적 지원 범위 밖이다. OCR은 실행하지 않았다.
- Phase 2A의 등록 수용 검사(classic xref PDF-1.x, 비암호화·비첨부/일부 능동 콘텐츠 거부)를 유지한다. 파서 자체의 처리 가능성과 API의 보수적 수용 범위가 다를 수 있다.

### HWPX

- 기존 ZIP/XML 안전 한도를 먼저 적용하고 content.hpf의 manifest/spine을 따른다. section10/section2의 파일명 정렬을 읽기 순서로 대신하지 않는다.
- 문단, 명시적인 제목 스타일 이름, 표·셀 좌표/병합, 이미지 binaryItemIDRef→패키지 asset과 SHA-256을 추적한다. 제목 스타일이 확인되지 않으면 문단으로 보존한다.
- source_anchor에는 part, root부터의 정수 자식 인덱스 xml_path, tag를 저장한다. `part#/0/1/...` selector와 원본 hash가 함께 고정된다. 이 경로는 원본 XML에 재해결 가능하지만 한컴 페이지 번호/화면 좌표가 아니다.
- 이미지의 확인된 관계는 XML상 포함 부모와 asset 참조뿐이다. 인접 문단을 임의의 캡션·설명·절차 관계로 연결하지 않는다. 이미지 text는 빈 문자열이다. 이미지 내용/OCR/픽셀 품질은 이번 파서가 보장하지 않는다.
- order_basis는 xml_spine_preorder다. **실제 한컴 화면의 다단/부유 그림/머리말·각주/병합표 읽기 순서와 페이지 대응은 NOT_RUN**이다. 따라서 HWPX에는 page/bbox를 생성하지 않는다.

## 영속 작업과 SQLite schema v2

기존 documents/versions/upload_intents/events는 보존한다. repository 초기화는 아래 테이블/인덱스/범위 trigger를 추가하는 schema v2다. 알려지지 않은 미래 schema는 실패시킨다. 등록 해제되지 않은 기존 v1 문서에는 빠진 작업을 멱등 backfill한다. 기존 문서 ID/원본/활성 포인터를 재생성하지 않는다. 기존 completed는 자료 관리의 해시 확인이었으므로 backfill된 버전은 파싱 단계 queued부터 처리한다. 운영 DB 업그레이드 전 DB/파일 백업은 별도 운영 절차다.

| 테이블 | 의미 |
|---|---|
| parse_jobs | 버전당 UNIQUE 작업, queued/processing/completed/failed/cancelled, attempt, claim_hash, lease_until, 고정 error_code, parser_method, 시각 |
| parse_attempts | (job_id,attempt) PK, 시도별 processing/completed/failed/expired/cancelled와 시작·종료·오류 |
| source_blocks | (job_id,attempt,block_id) PK, 문서/버전 FK, 순서, Pydantic JSON. 같은 시도의 순서는 UNIQUE |

source_blocks는 parse_attempts에 복합 FK를 갖고 trigger가 job→version→document 범위 불일치를 거부한다. 기관 정보는 소유 documents를 통해 검사한다. API·비즈니스·SQL·원본 저장 계층을 분리했다.

작업 생성→queued, worker claim→processing, 전부 성공→completed 또는 예외→failed다. failed만 명시적인 retry가 가능하며 queued/processing/completed의 중복 요청은 기존 작업을 돌려준다. 등록 해제는 cancelled로 바꾸고 결과 조회/게시를 차단한다. 완료 후 재추출/파서 교체 세대는 이번 API에 포함하지 않는다.

claim은 BEGIN IMMEDIATE 안에서 직렬화한다. capability hash·시도 번호·버전/문서/hash/format과 lease를 함께 검사한다. lease 기본30초, heartbeat는 약 lease/3마다 연장한다. 만료된 시도는 expired로 남기고 새 worker가 자동 queued 복구한다. 연속 만료는 총3회 시도 후 failed가 되며 관리자 retry가 필요하다. lease 시간은 동일 호스트의 wall clock을 기준으로 하므로 시스템 시각 급변·분산 노드 clock skew는 운영 검증 대상이다.

worker CLI의 작업 제한 기본120초를 넘으면 프로세스가 124로 종료되고 마지막 lease가 만료된 후 재시작 worker가 복구한다. 자동 서비스 재시작 supervisor는 구현하지 않았다. 완료와 실패 직전에도 소유권을 확인하므로 이전 worker의 늦은 게시/실패 보고가 새 시도를 덮어쓰지 못한다.

파서 결과는 요청 프로세스가 아닌 worker 메모리에서 생성하고 원본 재추출과 대조한다. DB에는 블록 전체·시도 완료·작업 완료·버전 완료·이벤트를 **한 트랜잭션**으로 게시한다. 중간 insert 실패는 전부 롤백한다. failed/processing 결과는 조회되지 않고 새 버전 실패도 기존 활성 포인터를 바꾸지 않는다. 완료 후 관리자 activate가 있어야 직원에게 노출된다. 원본 물리 삭제는 없다.

## API와 근거 검증

기존 버전 경로 `/documents/{document_id}/versions/{version_id}` 아래에 다음을 추가했다.

| 경로 | 동작 |
|---|---|
| POST /parsing | 관리자, 멱등 작업 생성/조회, 202 |
| POST /parsing/retry | 관리자, failed만 재시도, 202 |
| GET /parsing | 자기 기관·권한 범위 상태, claim_hash 비공개 |
| GET /blocks | 파싱 완료본만 조회. 관리자 후보/이력, 직원 현재 활성 버전만 |
| POST /evidence/resolve | `{source_anchor, quote?}`, 원본에 재해결 및 인용 일치 검사 |

모든 자료 API는 기존 신뢰 주체를 사용한다. 타기관 404, 미인증401, 역할 부족403, 준비되지 않은 파싱/잘못된 재시도409, 없는 앵커/다른 버전/원본 hash/인용 불일치422다. 잘못된 Anchor 형식도 Pydantic422다. 등록 해제 후 파생 데이터 조회는 관리자 포함404이고, 보존 원본의 관리자 이력 접근은 Phase 2A 계약을 유지한다.

게시할 때 원본을 다시 파싱한 canonical 블록과 위치·text·관계·순서를 모두 대조한다. 조회/근거 해결은 권한과 원본 hash를 다시 확인하고, 근거 해결은 canonical anchor와 인용 substring을 검사한다. 구조적 존재 확인이 의미적 뒷받침을 증명하지 않으므로 응답은 `structural_valid=true`, `semantic_accuracy=NOT_VERIFIED`, `visual_order=NOT_VERIFIED`를 별도로 반환한다. 같은 파서의 재추출은 독립적인 의미 검증이 아니다.

## 검증 자료와 남은 일

독립 PDF 입력은 tests/fixtures/synthetic/phase2b_pdf.py의 순수 Python 2페이지 합성 생성기다. 텍스트·표 좌표가 명시되어 있고 폰트 파일을 재배포하지 않는다. HWPX는 기존 procedure-v2.hwpx와 메모리 내 합성 변형(제목/병합/spine)을 썼다. 변형은 기존 원본을 덮어쓰지 않는다. 기대값은 테스트에 명시되어 있으나 독립 검토자가 동결한 대표 골드셋은 아니다.

PDF 10개/HWPX 17개 블록의 저장·재조회·모든 앵커 재해결 증거는 outputs/phase2b/SAMPLE_EXTRACTION.json에 있다. PDF 합성2페이지는 Poppler 렌더를 육안 확인했으며 글자/표 배치가 정상이다. Poppler의 로컬 폰트/data 경고는 남겼고 HWPX 렌더로 대체하지 않았다. 기존 로컬 한국어 합성 PDF도 추가 구조 probe만 수행했으며 해당 미배포 폰트 fixture를 새 필수 시험 의존성으로 넣지 않았다. 실제 공개 문서 corpus 추가 검증은 미실행이다.

근거/기관/버전·실패/중단·실 HTTP 시험과 기존33 회귀를 실행했다. 결과와 알려진 제약은 [Phase 2B 보고](../outputs/PHASE2B_REPORT.md)다. 실인증·요청 제한·PDF/ZIP의 강한 자원 격리·API 근거 재해결의 비용/시간 제한·클라우드·백업 복원·대표 골드셋과 실제 한컴 시각 검증은 별도다. 현재 공개 배포를 허용하지 않는다.

공식 참고: [pdfplumber 문서](https://github.com/jsvine/pdfplumber), [pdfminer 레이아웃 설명](https://pdfminersix.readthedocs.io/en/latest/topic/converting_pdf_to_text.html). 공식 지원 설명은 로컬 corpus 품질 실증으로 대신하지 않았다.
