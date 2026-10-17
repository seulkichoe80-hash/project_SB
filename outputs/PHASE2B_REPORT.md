# 서무ITDA Phase 2B 개발 결과

기준일: 2026-10-16 KST. 루트: `C:/Users/외부망/Documents/Codex/2026-10-16/15-2026-ai-2-itda-prd`.

**요청된 로컬 구조 추출·근거 추적·영속 파싱/복구 기능을 구현하고 검증했다.** 최종 전체 시험은 신규34+기존33=67 PASS다. HWPX 실제 한컴 화면 읽기 순서·페이지·독립 의미 정확성은 미검증이다. 전체 G1/G2·RAG·운영 배포 완료로 표현하지 않는다.

최신 증거: [최종 시험 V2](phase2b/VALIDATION_FINAL_V2.json), [원본 앵커 전체 재해결](phase2b/SAMPLE_EXTRACTION.json), [보존·변경·Git 검토](phase2b/PRESERVATION_AND_GIT.json). 이전 Phase 1/2A 보고·증거와 이번 중간 결과는 보존했다.

## 1. 구현 기능

- PDF/HWPX Parser Adapter를 분리하고 라이브러리 객체를 도메인/API로 노출하지 않는다.
- PDF 본문·기하학적 문단, 선 표·셀/병합, 물리 페이지·bbox를 추출한다.
- HWPX 문단·명시 제목 스타일·표/셀/병합, 이미지 asset 참조/해시·XML 포함 부모, manifest/spine 순서·원문 XML 앵커를 추출한다. 없는 페이지/이미지 좌표/캡션을 만들지 않는다.
- 문서/버전/블록 ID, 종류·원문 text, source_anchor·추출 방법/버전·순서·검증 상태와 부모/행/열/병합 관계를 저장한다.
- 원본 hash·문서/버전·canonical anchor·인용을 다시 확인하고 없는 앵커, 다른 버전, 가짜 블록/인용, 오래된 worker 시도를 거부한다. 구조 확인과 의미/시각 검증을 별도로 표시한다.
- 등록 트랜잭션에서 영속 작업을 생성한다. 별도 worker의 claim/lease/heartbeat·시도 fencing·실패/재시도·만료 복구·원자 게시를 구현했다.
- 처리 중/실패/등록 해제된 결과는 활성 조회에 노출하지 않는다. 새 버전 파싱 실패는 이전 활성본을 바꾸지 않는다. 물리 원본 삭제는 제공하지 않는다.
- 기관·역할은 서버 인증 주체를 따른다. 기본 실제 인증은 여전히 deny-all이고 테스트에서만 모의 주체를 명시 주입한다.

관련 범위: FR-02·05·14·15·18, NFR-02/03/04/05/06/07 및 WEB-02/03/05/06/07의 로컬 부분이다. FR-01~19·WEB-01~08·평가40/30/30·11/11 제출과 기존 전체 골드셋 목표를 삭제/축소하지 않았다.

## 2. 신규·수정 파일

| 구분 | 파일 |
|---|---|
| 신규 파서 | apps/api/parsers/__init__.py, contracts.py, pdf.py, hwpx.py |
| 신규 작업 계층 | apps/api/parsing_repository.py, parsing_service.py, worker.py |
| 수정 기존 API | apps/api/main.py, repository.py, service.py |
| 신규 시험·합성 생성기 | tests/test_parsing.py, tests/fixtures/synthetic/phase2b_pdf.py |
| 신규 검증 도구 | scripts/validation/run_phase2b_checks.py, build_phase2b_evidence.py, phase2b_claim_checkpoint.py, phase2b_http_server.py |
| 계약·의존성 | schemas/source-block.schema.json, requirements-parsing.txt, requirements-parsing-lock.txt |
| 신규 상세 설계 | docs/PHASE2B_PARSING.md |
| 수정 문서 | 루트 AGENTS/PRD/TASKS/ARCHITECTURE/TEST_PLAN/README.md, docs/G1_GATES.md, docs/GOLDSET.md |
| 보고·증거 | 이 보고서, outputs/phase2b/의 baseline·probe·최종JSON·sample·보존/Git 검토·변경 전 ZIP·diff·증거 ZIP |

기존 테스트 3개 파일과 Phase 2A 검증 스크립트·lockfile은 변경하지 않았다. Skill도 기존 반복 검증 절차를 적용하고 내용은 보존했다. 임시파일/venv/시험 DB/원본·렌더는 work/phase2b/에 분리했고 Git 제외다. 기존 소스/설계 변경 전 사본은 phase2b/BEFORE.zip, 차이는 DOCUMENT_CHANGES.diff와 PRESERVATION_AND_GIT.json에 남겼다.

## 3. DB 및 파서 구조

```text
HTTP 등록 → DocumentService → SQLite 등록+parse_jobs 원자 생성
                                  ↓ 별도 프로세스
worker claim/heartbeat → PDFParser | HWPXParser → Anchor/Block
    → 원본 재추출·범위/위치/내용 대조 → 전체 블록+작업/시도/버전 완료 원자 게시
    → 관리자 활성화 → 기관/권한 검사된 blocks·evidence/resolve 조회
```

기존4개 테이블 documents/versions/upload_intents/events를 보존하고 schema v2에 다음을 추가했다.

| 테이블 | 관계·기능 |
|---|---|
| parse_jobs | version_id UNIQUE FK, 상태, 시도 번호, claim_hash/lease, 고정 오류 코드, 파서 방법/시각 |
| parse_attempts | (job_id,attempt) PK, 시도별 상태·시작/종료·오류 |
| source_blocks | (job_id,attempt,block_id) PK, attempt 복합 FK·문서/버전 FK·순서 UNIQUE·Pydantic payload |

범위 trigger가 작업의 버전과 블록 버전/문서 불일치를 거부한다. SQL은 저장소 계층, 권한/정책은 서비스, 원본 접근은 기존 불변 저장 계층에 둔다. v1→v2는 추가 테이블 기반 마이그레이션이며 기존 원본/ID/활성 포인터를 보존하고 빠진 파싱 작업만 멱등 backfill한다. 알려지지 않은 미래 schema는 거부한다.

블록의 source_kind는 original_text/original_image/original_structure이고, `verification_status=structural_only`, `semantic_verification=NOT_VERIFIED`, `visual_order_verification=NOT_VERIFIED`다. block_id와 anchor는 원본 SHA-256·문서/버전·위치를 포함한다. HWPX 셀 집계 text와 자식 문단은 계층적으로 보존하므로 이후 청킹에서 중복 색인을 피해야 한다.

버전 경로 `/documents/{document_id}/versions/{version_id}` 아래 신규 API는 POST/GET `/parsing`, POST `/parsing/retry`, GET `/blocks`, POST `/evidence/resolve`다. manager는 작업/후보/이력, reader는 자기 기관 활성 버전만 조회한다. 등록 해제된 파생 데이터는 관리자도 조회하지 못하며 보존 원본의 관리자 접근은 기존 계약을 유지한다.

일반 서버 진입점 `apps.api.main:app`은 parsing_enabled=True다. factory 기본 False는 기존 Phase 2A-only 임베더/시험 호환용이다. **기존33개는 원래 모드의 회귀이고 신규34개는 파싱 활성 모드의 시험**이다. 일반 진입점은 파싱 작업이 있는 버전의 수동 transitions 우회와 미완료 활성화를 막으며 이 동작도 별도 시험했다. 두 모드 모두 실인증은 deny-all이다.

## 4. PDF/HWPX 지원 범위와 한계

| 영역 | 실제 구현/검증 | 보장하지 않는 범위 |
|---|---|---|
| PDF 본문 | 글자/줄에서 기하학 문단 추출, 표 문자는 본문에서 제외 | 저자 의미상 문단/복잡 다단의 완전한 읽기 순서 |
| PDF 표 | 선으로 구획한2×2 표와 병합 셀의 행/열/범위 | 테두리 없는 표·복잡 표 전체 |
| PDF 위치 | 물리1-based 페이지, 좌상단 points bbox, crop 텍스트 재확인 | 인쇄 쪽수와 동일성·전체 PDF 규격 지원 |
| PDF 입력 | 기존 classic-xref PDF-1.x 등록 검사, 최대100페이지 | 스캔/OCR·빈/미추출 페이지는 실패 처리, PDF2.0/암호화/첨부/일부 능동 기능 비지원 |
| HWPX 구조 | 정상 합성 v2의 문단·명시 제목·표/셀/병합·이미지 관계 | 임의 제목의 의미 추론·모든 복잡 문서 호환성 |
| HWPX 위치 | part+XML 자식 경로/tag+원본 hash, spine 순서 | **한컴 화면 순서/페이지·이미지 시각 위치 NOT_RUN** |
| 이미지 문맥 | XML 부모 포함 관계·asset hash | 임의 캡션/주변 문단 의미 연결·OCR/내용/픽셀 품질 |

PDF10개/HWPX17개 블록을 저장하고 전부 원본 앵커에 재해결했다. 기본 PDF는 새로 작성한 순수 Python 2페이지 합성 입력이고, HWPX는 기존 정상 v2 및 메모리 내 합성 변형이다. 기존 미배포 한국어 합성 PDF도 초기 구조 probe만 수행했다. 공개 실제 문서 corpus는 이번에 추가하지 않았다. 대표성·독립 검토자 골드셋·전체 정량 품질 지표는 미검증이다.

PDF2페이지를 Poppler로 렌더해 문단/표/페이지 배치를 육안 확인했다. 로컬 nameToUnicode/font 경고가 발생했지만 생성 PNG의 텍스트/표 배치는 정상으로 관찰했다. 이는 HWPX 한컴 렌더 확인이나 한국어 전체 폰트 호환성 증명이 아니다. 검증 원본/렌더는 work에 두고 증거 ZIP에 합성 자료만 포함한다.

공식 기술 참고는 [pdfplumber 문서](https://github.com/jsvine/pdfplumber), [pdfminer 레이아웃 설명](https://pdfminersix.readthedocs.io/en/latest/topic/converting_pdf_to_text.html)이다. 공식 기능 설명과 실제 로컬 corpus 검증은 구별했다.

## 5. 실제 실행한 명령과 결과

환경: Windows11, Python3.12.14, FastAPI0.143.2, Pydantic2.14.1, Uvicorn0.54.0, pdfplumber0.11.9, pdfminer.six20251230, defusedxml0.7.1. 기존 API 스택은 교체하지 않고 PDF 런타임 의존성만 추가했다. 정확한 전이 버전은 requirements-parsing-lock.txt다.

프로젝트 루트에서 실행했다.

```powershell
# 변경 전33개
& './work/phase2a/venv/Scripts/python.exe' scripts/validation/run_phase2a_checks.py --output outputs/phase2b/BASELINE_33.json

# 새 격리환경: 기존 API wheel + 공식 PyPI PDF 의존성
$env:TEMP=(Resolve-Path work/phase2b/tmp).Path
$env:TMP=$env:TEMP
& './work/phase2a/venv/Scripts/python.exe' -m venv work/phase2b/venv
& './work/phase2b/venv/Scripts/python.exe' -m pip install --no-index --find-links work/phase1/wheelhouse -r requirements-api-lock.txt
& './work/phase2b/venv/Scripts/python.exe' -m pip install pdfplumber==0.11.9

# 단계별 신규 시험과 전체 회귀
& './work/phase2b/venv/Scripts/python.exe' -m unittest discover -s tests -p test_parsing.py -v
& './work/phase2b/venv/Scripts/python.exe' -m unittest discover -s tests -v

# 최종 독립 HTTP 서버 재시작까지 포함한 전체 시험
& './work/phase2b/venv/Scripts/python.exe' scripts/validation/run_phase2b_checks.py --output outputs/phase2b/VALIDATION_FINAL_V2.json
& './work/phase2b/venv/Scripts/python.exe' -m pip check

# 실제 저장된 샘플의 전체 앵커 재해결
& './work/phase2b/venv/Scripts/python.exe' scripts/validation/build_phase2b_evidence.py --data-dir work/phase2b/evidence-runtime --output outputs/phase2b/SAMPLE_EXTRACTION.json

# 합성 PDF 시각 점검
pdftoppm -scale-to 1000 -png work/phase2b/goldset.pdf work/phase2b/goldset
```

| 최종 실행 범위 | PASS | FAIL | SKIP | BLOCKED |
|---|---:|---:|---:|---:|
| 신규 파서/영속 작업/근거/실 HTTP·worker 시험 | 34 | 0 | 0 | 0 |
| 기존 자료 관리·HTTP 시험 | 24 | 0 | 0 | 0 |
| 기존 근거/검색 평가 계약 | 9 | 0 | 0 | 0 |
| **전체** | **67** | **0** | **0** | **0** |

분모는 최종 테스트 메서드67개다. 앞선 성공 실행을 합산하지 않았다. 별도 sample의27개 앵커 재해결/visual 검사/pip check도 unittest 개수에 더하지 않았다. pip check는 No broken requirements found다.

실제 한컴·대표 공개 corpus·실인증/배포·LLM/임베딩은 **NOT_RUN**이며 위 PASS 개수에 포함하지 않는다. 외부 LLM/유료 API 호출·유료 자원·배포는0회다. 라이브러리 설치를 위한 공식 패키지 다운로드와 공식 문서 조회는 수행했다.

초기 제한 환경의 asyncio loopback 대기로 첫 기준 시험을 중단했고 네트워크 권한 허용 후33개 기준 시험을 완료했다. 첫 신규25개 실행은 테스트 작성 중 `defusedxml.ElementTree.SubElement` 오용으로24 PASS/1 ERROR였으며 표준 라이브러리 생성 함수로 수정했다. 이후25/32/66/67개로 범위를 확장해 재검증했다. 이 초기 오류/중단을 PASS로 숨기지 않고 로그와 증거 ZIP에 보존했다. Starlette/httpx deprecation 경고는 남아 있으며 시험 실패는 아니었다.

## 6. 원문 근거 추적 결과

- 새 합성 PDF:10/10 블록 앵커 저장·재조회·원본 재해결. 물리 페이지2와 bbox crop의 원문 text 일치,2×2 셀/병합 변형 기대값 통과.
- 정상 합성 HWPX v2:17/17 블록 앵커 저장·재조회·원본 재해결. XML 경로/tag,4개 셀·표, 이미지 참조/asset hash·XML 부모 관계 통과.
- 없는 PDF page/bbox/selector, 없는 HWPX XML path, 다른 문서 버전/hash·가짜text·인용 불일치와 claim의 문서/버전 혼용 차단 시험 통과.
- 원본 hash는 샘플 전후 동일. privileged 원본 변조 모사 시 게시/조회 거부. 원본 바이트를 수정해 파싱하는 단계가 없다.
- 모든 응답은 구조 유효성만 확인하고 의미/시각은 NOT_VERIFIED다. 같은 파서의 재추출은 독립적인 업무 의미 평가가 아니다.

## 7. 중단·재시작 복구 결과

- 실제 worker checkpoint 프로세스가 작업을 claim해 processing으로 남긴 뒤 강제 종료했다. 실제1초 lease 만료를 기다린 후 새 `python -m apps.api.worker --once`가 자동 복구해 attempt2로 완료했다. 체크포인트는 durable claim 직후이며 PDF 엔진 실행 중 강제 종료를 모든 단계에서 실증한 것은 아니다.
- 가짜 시간 기반 시험에서 heartbeat 연장, 총3회 만료 후 failed, 이전 시도의 renew/늦은 결과 거부를 확인했다. 새 worker의 완료가 stale 실패 보고로 덮이지 않는다.
- source_blocks 세 번째 insert에 DB 강제 실패를 넣어 앞서 insert된 블록도 전부 롤백(0개)됨을 확인했다. failed 상태·409 조회 차단 후 retry 성공을 확인했다.
- 원본 파서 예외, 원본 변조, 처리 중 등록 해제, 새 후보 실패를 시험했다. 등록 해제 후 게시 차단, 다른 기관 worker 접근 차단, 이전 활성본 유지가 통과했다.
- 실제 HTTP 업로드→별도 worker→blocks/evidence 성공 후 **API 서버 프로세스를 종료하고 새 프로세스로 재시작**해 동일 블록과 attempt1이 유지되는 것을 확인했다. app/DB 재열기 및 v1→v2 backfill도 별도 시험했다.

## 8. Phase 2A 회귀·보존·Git

구현 전 기존33/33 PASS, 최종 기존33/33 PASS로 관찰된 회귀 없음. 기존 테스트 파일은 변경하지 않았다. Phase 2A-only factory 계약과 새 파싱 활성 모드의 의도적인 강화(수동 완료 우회 차단)를 구분해 검증했다.

Git은 main, 아직 초기 커밋 없음. staged 파일·원격 없음. 로컬 commit/add/push/deploy를 실행하지 않았다. 저장소 전체가 untracked라 Git diff만으로 전후를 판단하지 않고 사전 SHA-256·BEFORE.zip 사본과 비교했다. 기존 원본/fixture·Phase 1/2A 증거는 보존하고 필요한 코드/기준 문서만 변경했다. 전체 신규/수정 후보와 변경 전후 hash·기존 최종 시험 코드 hash 일치는 PRESERVATION_AND_GIT.json에 기록한다.

.env·비밀키·venv·node_modules·work/DB·ZIP·diff·로그는 기존 .gitignore로 제외한다. 제한된 비밀 패턴/후보 검사와 문서 링크를 확인했다. 이는 운영 보안 감사나 완전한 비밀 탐지를 뜻하지 않는다. 커밋 후보는 위 신규/수정 코드·계약·문서·정제 JSON이며 원본 DB/venv/임시 자료·증거 ZIP은 제외다.

## 9. 미해결 사항과 한계

1. 한컴 시각 순서·페이지/부유 그림·복잡 다단/각주·대표 공개/한국어 PDF corpus·독립 의미 평가와 전체 골드셋은 미검증이다. 논리 구조 지원을 B-01 전체 PASS로 바꾸지 않았다.
2. PDF 문단/선 표는 휴리스틱이다. 빈/스캔 페이지는 보수적으로 실패하고 OCR로 복구하지 않는다. HWPX 이미지 내용·픽셀/OCR를 검증하지 않는다.
3. 파일/페이지/ZIP/블록/grid 한도와 worker 실행 timeout은 있지만 강제 메모리 격리·일반 근거 조회 CPU timeout·요청 제한은 운영 수준으로 검증하지 않았다. 실인증/권한 공급자가 없으므로 공개 배포는 차단한다.
4. worker 자동 supervisor, 분산 clock skew, 전원 장애·스토리지 내구성/백업 복원·PostgreSQL/객체 저장소는 미구현/미검증이다. CLI는 신뢰하는 로컬 운영자 권한이다.
5. 파서 버전 변경 후 같은 버전의 새 추출 세대/색인 전환은 다음 설계 과제다. 현재 completed 작업은 멱등 반환하며 자동 재파싱하지 않는다. 고정 버전 재해결 실패를 임의의 다른 앵커로 대체하지 않는다.
6. 다른 PC/OS·심사위원 독립 실행·의존성 취약점/최종 라이선스 감사는 별도다. 기존 API 스택과 잠금파일을 특별한 이유 없이 교체하지 않았다.

## 10. Phase 2C 착수 판단

**결정론적 구조 청킹·SourceBlock→EvidenceRef 연결의 제한된 Phase 2C는 착수 가능하다.** 문단/표/이미지의 계층과 원문 버전/위치, 영속 작업·실패 복구 기반이 실제 시험으로 확보됐다. 다음 요청에서는 집계 셀/문단 중복 방지, 표 헤더 맥락·이미지 XML 부모 보존, 기관/활성 버전 필터, 등록 해제·버전 전환 회귀를 먼저 구현하는 것이 적절하다.

실제 임베딩/벡터 검색은 G1-B-03, 실제 LLM·업무절차 생성은 B-02, React Flow는 B-04 검증을 먼저 통과해야 한다. 유료 호출/클라우드·공개 배포는 승인 전 진행하지 않는다. 전체 G1/G2 또는 Phase 2 전체 완료로 판정하지 않았다.
