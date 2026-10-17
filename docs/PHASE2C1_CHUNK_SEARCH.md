# Phase 2C-1 구조 청킹·EvidenceRef·SQLite 키워드 검색

기준일2026-10-17. FR-05 구조 청킹, FR-06의 키워드 부분, FR-14/15/18 및 NFR-02/03/04/05/06/07의 로컬 범위다. 기존 전체 FR/WEB·G1/G2 목표는 유지한다. LLM·임베딩·OCR·Vision·UI·클라우드·실인증은 구현하지 않는다.

## 실행과 요청 흐름

Python3.12와 기존 requirements-parsing-lock.txt 환경을 유지한다. 새 라이브러리를 추가하지 않았다. 프로젝트 루트에서 실행한다.

```powershell
python scripts/validation/restore_synthetic_fixtures.py --restore-missing
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000 --no-access-log
python -m apps.api.worker --data-dir work/phase2a/runtime --institution-id A
# 별도 터미널에서 청킹 큐 처리. 단일 작업은 --once 추가
python -m apps.api.chunk_worker --data-dir work/phase2a/runtime --institution-id A
```

표준 앱 진입점은 parsing_enabled=True이며 새 경로도 이 모드에서만 등록한다. factory의 Phase2A-only 호환 모드는 유지한다. 실제 인증은 deny-all이다. 테스트는 모의 인증 주체를 명시 주입하며 실제 로그인 방법으로 배포하지 않는다. CLI institution-id는 신뢰하는 로컬 운영자 설정이지 인터넷 요청자의 권한 근거가 아니다.

등록→기존 파싱 worker 완료→관리자의 POST chunk-jobs→청킹 worker 완료→명시적 activate→검색 순서다. 청킹 요청을 만든 새 버전은 완료된 청킹 세대가 없으면 활성화를 거부한다. 이미 정상인 이전 문서 버전/청킹 세대는 후보 실패로 교체하지 않는다. 파싱 완료 직후 자동 청킹은 이번 범위가 아니며 명시 요청이 필요하다.

## 순수 청킹과 출처

apps/api/chunking.py는 SDK·저장소와 독립된 결정론 코드다. 같은 source_blocks·organization_id·설정에서 같은 청크와 ID를 생성한다. ID는 알고리즘 structural-v1·설정·기관·원문 anchor/범위·종류의 canonical JSON hash다. Python Unicode 문자 수로 나누며 token 수를 뜻하지 않는다.

- 문단/명시 제목은 원문 순서대로 보존하고 max_chars(기본800,64~4000)로 나눈다. 원문 offset/quote를 유지하며 문장을 새로 요약하거나 정규화하지 않는다. 긴 문단의 언어학적 문장 경계는 보장하지 않는다.
- 셀 집계 text를 한 번만 본문으로 사용하고 같은 셀의 자식 paragraph는 본문 청크로 재생성하지 않는다. 표는 셀/셀 조각 단위의 table_row 청크로 표현한다. table_block_id/table_shape/row/column/row_span/column_span을 보관해 행·열과 병합을 재구성한다. 하나의 청크가 행 전체를 항상 포함한다는 뜻은 아니다.
- 표 컨테이너와 첫 행 셀을 별도 context 근거로 제공한다. 첫 행을 의미상 헤더라고 확정하지 않는다. 본문 중복과 의도적인 문맥 참조 반복을 구별한다.
- 최근 명시 제목은 title_context로 참조한다. 이미지에는 XML상 실제 포함 부모만 연결하고 임의의 앞뒤 문단/캡션을 생성하지 않는다. 이미지 text는 빈 문자열이고 이미지 출처임을 보존한다.
- 문맥은 context_chars(기본400,0~2000) 안에서 원문 prefix로 제한하며 잘리면 context_truncated를 표시한다. 문서당 청크20,000개 한도를 초과하면 실패한다.

EvidenceRef는 organization_id/document_id/version_id/chunk_id/source_block_ids/source_anchor/verification_status를 갖는다. 여러 원문 요소를 가리킬 수 있어 source_anchor는 ID 목록과 같은 순서의 배열이다. spans에는 block_id·원문 anchor·원문 start/end·quote·역할·source_kind를 보존한다. 기본 검증 상태는 structural_only, 의미는 NOT_VERIFIED다. AI 생성 설명은 넣지 않는다. 계약은 schemas/evidence-ref.schema.json이다.

근거 조회는 저장된 EvidenceRef와 요청값 전체를 대조하고 원본을 다시 파싱해 source_blocks·anchor·quote를 검증한다. 임의 anchor/기관/문서/버전/인용을 받아 원문처럼 보이게 하지 않는다. 보존 원본은 수정하지 않으며 기본 다운로드와 원문 블록 재조회 경로를 유지한다. 기존 bootstrap workflow.schema.json은 다른 모델이므로 이후 AI 연결 시 명시 변환/활성 검증이 필요하다. 이번 기능을 AI 주장 의미 검증이라고 표현하지 않는다.

## DB·영속 작업

기존 parsing schema user_version=2는 보존하고 독립 schema_extensions의 chunks/version1로 추가 구조를 기록한다. 원본/기존 테이블/증거를 삭제하지 않는다.

| 테이블 | 계약 |
|---|---|
| schema_extensions | 모듈별 추가 schema 버전 |
| chunk_jobs | 버전/파싱 작업·시도/설정 유일, 입력hash, generation, queued/processing/completed/failed/cancelled, attempt·capability/lease·오류 |
| chunk_items | job+chunk PK, job+순서 UNIQUE, 청크/EvidenceRef JSON과 SQLite 검색 문자열 |
| chunk_current | 버전별 게시된 청킹 세대 포인터 |

chunk_jobs는 parse_attempts 복합 FK를 갖고 trigger가 다른 버전의 파싱 작업 혼용을 막는다. BEGIN IMMEDIATE에서 claim을 직렬화하고 완전한 입력 batch hash와 파싱 세대를 게시 직전에 재검사한다. config/기관/문서/원본hash/파싱시도/generation/시도번호/capability/lease를 함께 검사해 오래된 worker의 게시를 거부한다.

청킹은 별도 worker 프로세스다. 기본 lease120초, 만료 시 새 claim이 queued로 복구하고3회 만료 후 failed다. failed만 관리자 retry가 가능하다. 이번 청킹 worker에는 heartbeat/자동 supervisor가 없으므로120초 초과 작업은 게시하지 않고 복구/실패한다. 큰 문서에서 실제 작업 예산과 heartbeat가 필요한지는 후속 검증이다.

결과 전체 insert·완료 상태·current 포인터를 한 트랜잭션으로 커밋한다. 중간 실패/프로세스 종료 전에는 부분 결과를 조회하지 않는다. 재시도 시 불변 원본/source_blocks로 재계산한다. 서로 다른 설정의 generation이 역순으로 완료돼도 이전 generation이 새 current를 덮지 않는다. 등록 해제는 작업 cancelled와 모든 조회의 등록 상태 검사로 차단한다. 완료된 세대는 감사/원본 보호를 위해 물리 삭제하지 않는다.

## API

버전 경로는 `/documents/{document_id}/versions/{version_id}`다. 기관 ID를 요청에서 권한으로 받지 않는다.

| 경로 | 역할·기능 |
|---|---|
| POST version/chunk-jobs | manager, `{max_chars?,context_chars?}`, 멱등 접수202 |
| GET version/chunk-jobs/{job_id} | 기관/버전 권한 범위 상태, capability 비공개 |
| POST version/chunk-jobs/{job_id}/retry | manager, failed만202 |
| GET version/chunks | manager 후보/과거 등록 버전, reader 현재 활성 버전만 |
| POST version/chunks/{chunk_id}/evidence/resolve | EvidenceRef 본문, 원문 블록·구조 유효성·원문/AI 구분 반환 |
| GET /search?q=…&limit=20 | 인증된 자기 기관·현재 활성 문서/버전만, 청크와 EvidenceRef 반환 |

미인증401, 다른 기관404, 역할403, 준비 미완료/상태 오류409, 위조 근거422다. 등록 해제 자료는404이며 검색에서는 제외한다. 관리자 검색도 비활성 후보를 노출하지 않는다.

## 키워드 검색과 교체 경계

SQLiteKeywordSearch 어댑터가 SQL의 parameterized LIKE/ESCAPE로 파일명·확인된 제목 text·본문/문맥을 검색한다. casefold를 저장/질의 모두에 적용해 한글/영문을 다룬다. 공백으로 나눈 최대8개 검색어를 AND로 적용하고 %/_/역슬래시는 리터럴 처리한다. 질의200자 이하, 결과1~50개. 결과 정렬은 문서 생성시각/버전ID/청크 순서로 결정적이며 BM25/의미 유사도 순위가 아니다.

SQL은 소유 기관·registered·활성 버전·완료 청킹 세대·동일 파싱시도를 JOIN 검사한다. 서비스는 어댑터 결과도 다시 검사해 기관/활성/원본hash/현재 청크 내용이 다르면 반환하지 않는다. 앞으로 벡터 어댑터를 추가하더라도 이 권한/활성 검사를 우회할 수 없다. 현재는 LIKE 전체 문자열 탐색이라 큰 corpus의 성능/FTS 도입·검색 품질 지표는 미검증이다. 실제 embedding을 실행하지 않았다.

## 검증과 남은 게이트

실제 명령/결과는 [보고](../outputs/PHASE2C1_REPORT.md), 기존 합성 자료 누락 및 복구는 [복구 이력](../outputs/RESUME_RECOVERY_20261017.md)이다. 신규25개 기능 시험+복구1개+기존67개=93개를 실행했다. 실제 HTTP 서버 재시작·chunk worker 강제 종료/새 프로세스 복구와 SQLite 부분 insert 롤백도 시험했다. 실제 HWPX 한컴 시각 순서·독립 의미 검토·전체 대표 corpus·실인증/운영 배포·실제 모델은 미검증이다. 전체 G1/G2 및 FR-06 전체(벡터/자동 임베딩)를 PASS로 바꾸지 않는다.
