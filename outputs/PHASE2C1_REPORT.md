# 서무ITDA Phase 2C-1 완료 보고

기준일2026-10-17 KST. 작업 루트 `C:/Users/외부망/Documents/Codex/2026-10-16/15-2026-ai-2-itda-prd`.

**로컬 구조 청킹·EvidenceRef·SQLite 키워드 검색을 구현하고 전체93개 시험을 통과했다.** 기존67개, 신규 기능25개, 자료 복구1개다. 실제 LLM·임베딩·OCR·Vision·UI·클라우드·실인증은 구현하지 않았다. 전체 G1/G2 및 FR-06 전체 완료로 판정하지 않는다.

## 1. 실제 구현 기능

- 기존 canonical source_blocks 기반 순수 결정론 청킹. 제목/문단·표의 셀/행/열/병합·이미지의 XML 부모를 보존한다.
- 원문 문자 범위로 긴 문단/셀을 분할하고 동일 입력·설정의 ID를 고정한다. 셀 집계와 자식 문단의 중복 본문 생성을 막는다. 첫 행 문맥을 실제 헤더라고 추론하지 않는다.
- organization_id/document_id/version_id/chunk_id/source_block_ids/source_anchor와 구조 검증 상태를 포함한 EvidenceRef. 원문 offset/quote/역할/source_kind도 보관한다.
- 원문 재파싱과 저장 청크 대조로 잘못된 근거/버전/인용을 거부한다. 기관 권한을 요청값으로 결정하지 않는다. 응답의 원문과 미검증 의미 상태를 구분한다.
- 영속 청킹 작업과 별도 worker, lease/시도 fencing, 중복 접수 방지, 원자 게시, 실패 재시도, 중단 복구, 세대 포인터.
- SQLite 어댑터로 파일명·명시 제목·본문/문맥 키워드 검색. 기관·현재 활성 버전·등록 상태·완료 세대만 반환한다. 검색 어댑터도 서비스 권한/활성/현재 데이터 검사를 우회하지 못한다.

대응 범위는 FR-05, FR-06 키워드 부분, FR-14/15/18 및 NFR-02/03/04/05/06/07이다. 제품 비전·FR-01~19·WEB-01~08·공모전 평가40/30/30·11/11 제출을 유지했다.

## 2. 재개 시 차이와 신규·수정 파일

재개 최초 기준은55 PASS/12 FAIL이었다. 기존 HWPX v1/v2 fixture 파일이 누락됐으며 누락 경위는 미검증이다. 정상 v2는 불변 저장본에서 기존 hash 그대로 복원했다. 과거 v1은 정확 복원하지 못해 기존 manifest/기록을 유지하고 별도 CRC 부정 fixture를 만들었다. 기존67개 중 부정 계약 시험1곳의 fixture 참조만 새 파일로 변경했다. 복구 후67개가 통과했다. **옛 v1 바이트의 재시험 또는 모든 fixture 무변경 회귀로 표현하지 않는다.** [복구 상세](RESUME_RECOVERY_20261017.md), [최초 실패](phase2c/BASELINE_67.json), [복구 후 기준](phase2c/BASELINE_RECOVERED_67.json)를 보존했다.

| 종류 | 파일 |
|---|---|
| 신규 도메인·저장·서비스·worker | apps/api/chunking.py, chunk_repository.py, chunk_service.py, chunk_worker.py |
| 수정 기존 코드 | apps/api/main.py, repository.py, service.py |
| 신규 시험·검증 | tests/test_chunking.py, scripts/validation/phase2c_claim_checkpoint.py, build_phase2c_evidence.py |
| 복구 | scripts/validation/restore_synthetic_fixtures.py, tests/fixtures/synthetic/hwpx-recovery.json, procedure-v2.hwpx, procedure-recovery-invalid.hwpx; test_validation_contracts.py 참조1곳 |
| 신규 계약·설계 | schemas/evidence-ref.schema.json, docs/PHASE2C1_CHUNK_SEARCH.md |
| 수정 기준 문서 | 루트 AGENTS/PRD/TASKS/ARCHITECTURE/TEST_PLAN/README, docs/G1_GATES.md, docs/GOLDSET.md |
| 산출물 | 이 보고서, 복구 보고, outputs/phase2c/의 테스트·합성 샘플·Git/보존 기록·증거 ZIP |

복구 관련 파일과 이전 기준 소스/문서는 초기 커밋에 포함했다. 초기 커밋 이후 Phase 2C-1 새 기능·문서·증거는 미커밋 검토 후보로 남겼다. 기존 Phase 1/2A/2B 보고·증거는 덮어쓰지 않았다. 새 의존성/비밀값/실제 행정자료를 추가하지 않았다.

## 3. DB·스키마·API

기존 SQLite parsing user_version2를 보존하고 schema_extensions(chunks,1)로 독립 확장을 기록한다.

| 테이블 | 역할 |
|---|---|
| schema_extensions | 모듈별 추가 schema 버전 |
| chunk_jobs | 버전/파싱 시도/설정 유일, 입력hash, generation, 상태·시도·lease·오류 |
| chunk_items | 청크/EvidenceRef JSON·검색 문자열, job+chunk PK/순서 UNIQUE |
| chunk_current | 버전별 완전 게시된 청킹 세대 |

FK와 trigger가 다른 버전의 파싱 근거 혼용을 거부한다. 한 트랜잭션으로 모든 청크·완료 상태·게시 포인터를 갱신한다. 등록 해제·후보 실패는 이전 활성본을 자동 교체하지 않는다. 원본/source_blocks를 수정하거나 물리 삭제하지 않는다.

버전 경로 `/documents/{document_id}/versions/{version_id}` 아래에 다음을 추가했다.

- POST `/chunk-jobs` — manager, `{max_chars?,context_chars?}`, 멱등202.
- GET `/chunk-jobs/{job_id}`, POST `/chunk-jobs/{job_id}/retry` — 상태/실패 재시도.
- GET `/chunks` — manager 후보/이력, reader 현재 활성 버전만.
- POST `/chunks/{chunk_id}/evidence/resolve` — EvidenceRef 대조·원문 블록/원문 구분/구조 검증 반환.
- GET `/search?q=…&limit=20` — 자기 기관 활성 자료만 청크/EvidenceRef로 반환.

기본 인증은 deny-all이고 실제 사용자 로그인은 미구현이다. mock은 시험에서만 주입했다. 일반 공개 서비스 실행용으로 배포하지 않는다. CLI는 신뢰하는 로컬 운영자 도구다.

## 4. 실제 실행 명령과 결과

기존 Python3.12/FastAPI/Pydantic/SQLite·pdfplumber 환경을 재사용했다. 프로젝트 루트에서 실제 실행했다.

```powershell
# 최초 기준:55 PASS/12 FAIL — 누락 파일 확인
& './work/phase2b/venv/Scripts/python.exe' scripts/validation/run_phase2b_checks.py --output outputs/phase2c/BASELINE_67.json

# hash 검증된 합성 자료 복구 후:67 PASS
& './work/phase2b/venv/Scripts/python.exe' scripts/validation/restore_synthetic_fixtures.py --restore-missing
& './work/phase2b/venv/Scripts/python.exe' scripts/validation/run_phase2b_checks.py --output outputs/phase2c/BASELINE_RECOVERED_67.json

# 신규 기능 초기 시험22개 PASS, 확대 전체92개 PASS도 별도 기록
& './work/phase2b/venv/Scripts/python.exe' -m unittest discover -s tests -p test_chunking.py -v

# 최종 전체93개 PASS
& './work/phase2b/venv/Scripts/python.exe' scripts/validation/run_phase2b_checks.py --output outputs/phase2c/VALIDATION_FINAL.json
& './work/phase2b/venv/Scripts/python.exe' -m pip check

# 합성 샘플 저장·원문 재해결·키워드 검색
& './work/phase2b/venv/Scripts/python.exe' scripts/validation/build_phase2c_evidence.py --data-dir work/phase2c/evidence-runtime --output outputs/phase2c/SAMPLE_CHUNKS_SEARCH.json
```

기존 runner 이름은 phase2b지만 tests 전체 discovery라 새 test_chunking.py도 포함한다. 최종 결과와 코드 hash는 [VALIDATION_FINAL.json](phase2c/VALIDATION_FINAL.json)에 있다. pip check는 No broken requirements found였다.

## 5. PASS / FAIL / SKIP / BLOCKED

| 최종 실행 범위 | PASS | FAIL | SKIP | BLOCKED |
|---|---:|---:|---:|---:|
| Phase 2C-1 신규 기능 |25|0|0|0|
| 합성 fixture 복구 안전성 |1|0|0|0|
| 기존 Phase 2A/2B·계약 |67|0|0|0|
| 합계 |**93**|**0**|**0**|**0**|

최종 테스트 메서드 수이며 중간 실행을 합산하지 않았다. 최초12개 오류는 결과 파일에 남겨두었다. 별도 샘플 재해결/키워드 검색/pip check를 위93개에 더하지 않는다. 실모델/임베딩·한컴 시각 순서·실인증·클라우드·전체 대표 corpus·독립 심사 실행은 NOT_RUN이고 PASS 개수에 포함하지 않는다.

## 6. EvidenceRef 무결성

[실제 저장 샘플](phase2c/SAMPLE_CHUNKS_SEARCH.json): PDF9개/HWPX9개 청크의 모든 EvidenceRef를 원본에 재해결했다. 원본 hash는 변하지 않았다. 검색 표본은 Prepare 1개, 신청 4개, manual.pdf 9개가 반환됐다. 이는 대표 검색 품질/의미 정확도 지표가 아닌 작은 합성 확인이다.

존재하지 않는 청크/앵커·다른 버전·다른 기관·가짜 quote를 거부했다. 표 좌표/병합·문자 범위·셀 자식 문단 중복 방지·제목 문맥·이미지 원문/AI 구분을 시험했다. 근거는 구조적으로 유효하지만 semantic_verification은 NOT_VERIFIED다. `source_anchor`는 다중 출처를 표현하는 배열이며 source_block_ids와 대응한다. 과거 workflow bootstrap 모델과 직접 동일하지 않으므로 향후 AI 연결 시 명시 변환이 필요하다.

## 7. 기관·버전 격리

타기관 자료 조회/청킹 요청/근거 해결과 worker claim을 차단했다. 검색은 관리자도 자기 기관의 현재 활성 버전만 대상으로 한다. 후보/과거 버전은 관리자 명시 조회만 가능하고 reader는 활성본만 읽는다. 미인증401, 역할403, 타기관404를 확인했다.

버전 교체 직후 옛 버전 검색 제외, 등록 해제 후 검색·파생 조회 제외를 확인했다. 검색 어댑터가 비활성/가짜 텍스트를 반환하도록 주입해도 서비스가 거부했다. SQL 인젝션 모사·%/_ 리터럴·질의/결과 한도도 시험했다.

## 8. 실패 복구와 회귀

- 두 번째 chunk insert에 DB 강제 실패: 모든 부분 행 롤백0개, 실패 상태/미노출, 명시 retry 후 정상 완료.
- claim 후 worker 강제 종료, 실제 짧은 lease 만료 뒤 새 chunk_worker 프로세스가 자동 복구해 attempt2 완료. 체크포인트는 claim 직후이며 모든 CPU 실행 위치에서 중단을 실증한 것은 아니다.
- 가짜 시간 기반 만료/새 claim, 이전 worker의 늦은 결과 거부, 처리 중 등록 해제/취소를 확인했다.
- 새 문서 버전의 청킹 실패 시 활성화 거부와 이전 정상 버전 검색 유지.
- 실제 HTTP 서버를 별도 프로세스로 두 번 실행해 검색 결과와 근거 해결이 재시작 후 유지됨을 확인했다. 별도 chunk_worker CLI 및 앱/DB 재열기도 시험했다.
- 기존67개 모두 통과했다. 단, 누락된 과거 v1의 부정 시험은 새 합성 대체 자료를 사용했다는 복구 이력을 유지한다. Phase 2B 원문 파서·앵커·worker 복구·Phase 2A 원본/기관/버전 계약에서 관찰된 회귀 없음.

## 9. 로컬 Git 기준점과 작업 트리

초기 로컬 커밋 SHA:

`f9a01d8c5b6b2b2311f4d8d8461b0f5b55b7a182`

사용자의 오늘 명시 승인에 따라 main에 생성했다. 이름/이메일 설정이 없어 커밋 명령에만 합성 로컬 작성자 `SeomuITDA Local Development <seomuitda@localhost>`를 지정했고 전역 설정은 변경하지 않았다. 검토된 소스/문서/합성 자료만 포함하고 .env·키·원본 행정문서·DB·venv·node_modules·work·ZIP/log/diff는 제외했다. 검토 목록은 [INITIAL_COMMIT_REVIEW.json](phase2c/INITIAL_COMMIT_REVIEW.json)이다. 샌드박스 .git 쓰기 권한 거부 후 필요한 디렉터리 권한을 허용받아 실행했다.

초기 기준점 이후 이번 기능 변경은 추가 commit/stage하지 않고 검토 후보로 남겼다. 변경 목록·보존 hash·현재 Git 상태는 [최종 Git/보존 기록](phase2c/FINAL_REVIEW.json)을 따른다. 원격 등록·push·배포는 수행하지 않았다.

## 10. 남은 문제와 한계

1. 키워드 검색은 SQLite LIKE 기반 AND 부분문자열 검색이다. 형태소/어간/오타/동의어·BM25·의미 검색이나 대규모 성능을 검증하지 않았다. 파일명·명시 제목은 문서 수준으로 각 청크의 검색 문자열에 포함된다.
2. 청크는 문자 수 기반이고 표는 셀/셀 조각 단위다. 문장/행 전체가 항상 한 청크에 들어가지 않는다. 행·열/병합 메타데이터로 재구성한다. 첫 행 문맥은 확정 헤더가 아니다.
3. 청킹 worker lease는120초이며 heartbeat/자동 supervisor가 없다. 초과 작업은 늦은 게시를 거부하고 만료 복구한다. 큰 문서의 시간/메모리 예산·heartbeat·강한 프로세스 격리는 후속 작업이다.
4. 실제 인증/JWT·rate limit·CORS/HTTPS·클라우드/백업·실제 LLM/임베딩·한컴 시각 순서·독립 의미/대표 corpus는 미검증이다. 기본 deny-all을 해제해 공개하지 않는다.
5. 과거 v1 원본은 미복원이다. 새 복구 패키지는 정상 v2 바이트와 별도 부정 자료의 재현성을 제공하며 과거 v1 증거를 대체했다고 주장하지 않는다.
6. 완료된 청킹 작업의 알고리즘 업그레이드는 schema_extensions/설정·세대 정책을 명시 변경해야 한다. 기존 완료 작업을 몰래 재생성하지 않는다.

## 11. Phase 2C-2 착수 판단

**사전 기술검증부터 조건부 착수 가능하다.** 근거 연결된 키워드 검색을 비교 기준으로 사용할 수 있고, 새 검색 어댑터도 기관/활성/현재 근거 검사를 통과해야 한다. 실제 임베딩·벡터 검색 구현 전 B-03의 모델/차원/정규화/한글 골드셋·Hit@5·필터·재색인/전환을 검증해야 한다. 유료 외부 모델/API가 필요하면 모델·공개/합성 corpus·예산을 먼저 승인받는다. 로컬/무료 후보도 설치·품질이 확인되지 않았으므로 이미 준비됐다고 표현하지 않는다.

이번 작업에서는 실제 모델/API 호출·OCR/Vision·React Flow·클라우드를 시작하지 않았다. 전체 G1/G2 통과나 인터넷 공개 가능을 선언하지 않는다.
