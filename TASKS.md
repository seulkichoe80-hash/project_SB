# 단계별 개발 작업과 완료 기준

## 서무ITDA v0.1 오프라인 통합 기준

- 사용자 승인: 기존 기능 통합·검증·시연·기준 커밋·기존 브랜치 push/PR까지만. main 직접 변경/자동 merge/다음 개발은 하지 않는다.
- [x] 2E-2A 변경33개를 050349f에 보존하고 공개 가능한 합성 자료로 실제 HTTP 등록→worker→지도/근거→로그아웃 차단을 검증.
- [x] 전체 backend409·UI104·실제 HTTP13, 타입/빌드 PASS. 설치한 별도 Playwright에서도 HTTP13 재실행 PASS. 외부 공급자 호출0.
- [x] [현재 시연·재현·미검증 경계](docs/V01_DEMO.md), [v0.1 실행 보고](outputs/V01_REPORT.md), PC/모바일 캡처와 합성 fixture 준비.
- [ ] 운영 실제 인증/AI/공식 승인·게시/공개 배포·G1 C/D는 기존 미검증 상태 유지. 다음 개발은 별도 승인 후.

## Phase 2E-2A 업무지도 안정화·복구 UX

- 사용자 승인 범위: 2E-2A만. 2E-1 변경44개를 로컬1602564에 보존하고 원격 작업은 하지 않는다.
- [x] 명시적 동일 입력 POST 복구 안내·재시도 구분·중복/늦은 변경 응답 방지, visible 직렬 polling·deadline/backoff·terminal 중단, 근거 선택·실패 상태와 지도 참조 안정화.
- [x] 신규 UI24, 기존 UI80, loopback HTTP6, 전체 backend409 PASS. 타입/빌드 PASS. 외부 공급자 호출0.
- 현재 계약: [UI 수명](docs/PHASE2E2A_UI_STABILITY.md), [실행 보고](outputs/PHASE2E2A_REPORT.md).
- [ ] 2E-2B 이후는 별도 범위 승인 후. 승인·게시·실제 공급자 연결·배포 미진행.

## Phase 2E-1 관리자 후보 지도·원문 검토

- 사용자 승인 범위:2E-1만. 2D-6 변경17개는 로컬47dd389에 보존하고 원격 작업은 하지 않는다.
- [x] 기존 디자인/인증·9개 Workflow API 재사용, React Flow12.12.0 읽기 전용 지도/목록/모바일 탭, 단계·관계·검토·서식·canonical 원문 연동 구현.
- [x] 신규 모의 API 브라우저37, 실제 loopback BFF/worker 통합6, 기존 UI43, 전체 backend409 PASS. typecheck/build PASS, 실제 외부 공급자 호출0.
- 현재 계약: [관리자 검토](docs/PHASE2E1_WORKFLOW_REVIEW.md), [실행 보고](outputs/PHASE2E1_REPORT.md).
- [ ] 2E-2A는 상단의 별도 승인 범위에서 완료. 2E-2B 이후는 별도 요청 후. 의미/최종 승인·공식 게시·실제 모델/공급자·배포는 미진행.

## Phase 2D-6 영속 작업·관리자 조회

- 사용자 승인 범위: Phase 2D-6만. 2D-5 변경10개를 로컬 56b484d에 보존하고 원격 작업은 하지 않는다.
- [x] 오프라인 영속 작업·lease/fencing/최대3회·취소/재시도·오류 이력, 추가형 SQLite 세대/후보/검토/서식 원자 저장, manager 전용9개 경로와 strict schema 구현.
- [x] 신규49 + 기존360 = 전체409 PASS(FAIL/SKIP/BLOCKED0), 비루프백 가드 probe PASS·실제 외부 공급자 호출0.
- 계약: [영속 workflow](docs/PHASE2D6_WORKFLOW_JOBS.md), 실제 실행 결과: [보고](outputs/PHASE2D6_REPORT.md).
- [ ] UI/승인·공식 게시·실제 모델·배포는 별도 요청 후. 전체 Phase 2D 의미 정확성/운영 실증 완료로 승격하지 않는다.

## Phase 2D-5 업무절차·서식 관계

- 사용자 승인 범위: Phase 2D-5만. 2D-4 변경10개를 로컬 c2c9640으로 보존했고 원격 push/merge는 하지 않는다.
- [x] 기존 FormRequirement/근거/단계·조건 재검증, 같은 기관의 명시 등록·활성 서식만 미확정 어휘 후보로 검색. 별도 분류 카탈로그는 비파괴 추가 테이블이다.
- [x] 신규41 + 기존319 = 전체360 PASS(FAIL/SKIP/BLOCKED0), 비루프백 가드 probe PASS·실제 외부 공급자 호출0.
- 계약: [서식 관계](docs/PHASE2D5_FORM_RELATIONS.md). 실행 결과와 범위는 [보고](outputs/PHASE2D5_REPORT.md).
- [ ] Phase 2D-6는 별도 사용자 요청 후. 의미 검증·승인/게시·HWPX 자동 작성·UI·외부 API·배포는 진행하지 않는다.

## Phase 2D-4 근거·그래프 검증

- 사용자 승인 범위: Phase 2D-4만. 기존 19개 변경은 로컬 보존 커밋 e57c657에 보존했고 원격 작업은 하지 않는다.
- [x] 별도 strict 검토 보고/JSON Schema, 현재 활성 원본·스냅샷·canonical EvidenceRef 재해결, 그래프 진단과 의미 검토 보조 구현.
- [x] 신규46 + 기존273 = 전체319 PASS(FAIL/SKIP/BLOCKED0), 비루프백 가드 아래 실제 외부 공급자 호출0.
- 실행 결과·한계: [계약](docs/PHASE2D4_VALIDATION.md), [실행 보고](outputs/PHASE2D4_REPORT.md).
- [ ] Phase 2D-5는 별도 사용자 요청 후. 의미 검증·승인/게시·UI·영속 worker·실제 API·배포는 미진행.

## Phase 2D-3 오프라인 업무절차 후보 추출

- [x] Phase 2D-1~2 미커밋12개 파일·증거의 archive/hash 보존 및 새 작업 브랜치로 유지.
- [x] 업무명 사전 없는 결정적 표식 기반 WorkflowExtractionAdapter, 다중/제목 없는 업무·단계/역할·조건/반려/반복·기한/의무/서식 언급 후보와 원문 연결.
- [x] 전체 snapshot 순회·strict 구조/근거·처리 범위/불완전 상태·adapter 변조/범위 검사, canonical EvidenceRef 보존, NOT_VERIFIED/미승인/게시 불가 유지.
- 현재 계약은 [오프라인 추출](docs/PHASE2D3_OFFLINE_DISCOVERY.md), 실제 실행 결과는 [보고](outputs/PHASE2D3_REPORT.md)를 따른다.
- [ ] Phase 2D-4 이후는 사용자 승인 전 미진행. 실제 의미 검토·LLM·임베딩·승인/자동 게시·업무지도·DB/클라우드 배포는 이번 범위 밖이다.

## Phase 2D-1~2 업무절차 계약·입력 스냅샷

- [x] 기존 RAG/구형 WORKFLOW_SCHEMA를 유지하고 strict WorkflowCandidate/Step/Condition/Edge/FormRequirement/ReviewIssue/GroundedAssertion·별도 WorkflowExtractionAdapter 및 버전 schema 추가.
- [x] ID/참조/한도/정확 원문 근거·모델 검증상태 위조 차단, 구형 tenant/element와 canonical EvidenceRef 사이 명시 왕복 bridge.
- [x] 단일 문서 버전 전체 snapshot·원본 재검증/청크 재구성·coverage·parse/chunk/활성 세대 변경/기관/해제 차단. DB/원본 무변경.
- 검증 결과는 [별도 실행 보고](outputs/PHASE2D12_REPORT.md), 현재 범위/한계는 [계약](docs/PHASE2D_INPUT_CONTRACT.md)을 따른다.
- [ ] Phase 2D-3 후보 추출 엔진은 별도 사용자 요청 후. 현재 실제 LLM·의미 정확성·관리자 승인·자동 게시·React Flow는 미구현/미검증이며 전체 Phase 2D 완료로 표시하지 않는다.

## 개발 지침 효율 개선 2026-10-17

- 현재 진척도·완료 상태는 이 문서에서 관리하고 단계별 상세 보고·증거는 outputs에 보존한다. PRD/ARCHITECTURE/TEST_PLAN은 각 요구사항/구조·계약/시험 기준이 변경될 때만 해당 절을 갱신한다. 기존 이력·문서 링크·요구사항 추적성은 유지한다.
- [x] AGENTS의 작업별 확인 범위·기술 재검증 조건·Git 보존 방식 명확화.
- [x] TEST_PLAN으로 실행 시점·영향 범위·결과 재사용 기준 통합, Skill을 Feature/Phase/Release/Read-only 수준으로 구분.
- 변경 검증 결과와 전후 사본·해시·diff는 work/instruction-optimization-20261017/에 기록한다. 앱·테스트 코드는 변경하지 않으며 이번 문서 검증을 기능 테스트 PASS로 계산하지 않는다.

## Phase 2C-1 구조 청킹·EvidenceRef·키워드 검색 2026-10-17

- [x] 누락 합성 v2 바이트 동일 복원, v1은 미복원 기록 유지·별도 PNG 손상 fixture, 재개 기준67개 회복.
- [x] 사용자 명시 승인·안전 파일 검토 후 초기 로컬 커밋 생성. 원격/push/배포 없음.
- [x] 결정론 청킹·문단/제목·표 행열/병합·긴 원문 분할·중복 본문 방지.
- [x] 기관/문서/버전/source_block/원문 anchor를 가진 EvidenceRef·원문 재해결.
- [x] 별도 영속 청킹 작업·원자 게시·실패 재시도·worker 중단/재시작·옛 활성본 유지.
- [x] SQLite 키워드 검색·문서명/제목/본문·기관/활성/등록 해제 필터·어댑터 경계.
- [x] 신규 기능25+자료 복구1+기존67=93개 시험 PASS. 증거 outputs/phase2c/VALIDATION_FINAL.json.
- [ ] Phase 2C-2 범위 확정: 실제 임베딩은 B-03 사전 검증·필요시 예산 승인 후, 기존 키워드 기준과 비교. 현재 실모델/임베딩은 NOT_RUN.

현재 계약은 [청킹/검색](docs/PHASE2C1_CHUNK_SEARCH.md), 결과는 [보고](outputs/PHASE2C1_REPORT.md)다. 기존 Phase 이력과 전체 G1/G2 미완료는 유지한다.

## 저장소 안정화와 현재 게이트

루트의 7개 문서가 단일 기준이다. [G1 A/B/C/D](docs/G1_GATES.md)가 개발/기능/배포/제출의 현재 진입 조건이며 이전 전체 G1 차단 설명보다 우선한다. 전체 G1 미완료와 개별 A 준비를 구별한다. 이번 변경은 사용자 지시에 따른 게이트 재분류이며 미실행 시험을 PASS로 바꾸지 않는다.

## 인터넷망 전환 상태 2026-10-16

현재 기준은 PRD와 docs/G1_GATES.md다. [Phase 1 보고](outputs/PHASE1_REPORT.md)의 과거 판정은 불변 보존한다. 내부망/GPU/폐쇄망/Docker 필수 제외는 MVP 비대상 처리이며 시험 PASS가 아니다. 전체 G1은 미완료, A 준비와 작업별 B가 Phase 2 세부 착수 기준이다. 2026-10-16 후속 사용자 요청으로 Phase 2A 로컬 자료 관리만 구현했다. 유료 호출/공개 배포는 실행하지 않았다.

계획 기준은 2026-10-16, 모든 날짜는 KST다. 11/11 제출 시각·최신 변경 공지는 미검증이다. 담당자는 아직 지정되지 않았다. 각 Phase 시작 시 담당/검토자를 기록한다. 아래 Phase 전체 계획은 유지하고 Phase 2A의 제한된 완료만 별도 구분한다.

## Phase 2A 로컬 수직 기능 10/16 후속 승인

- [x] FastAPI/Pydantic/SQLite 메타데이터·원본 UUID 저장과 해시·중복 정책.
- [x] 등록/조회/다운로드·버전 후보/활성화·등록 해제·명시 상태 전이.
- [x] 신뢰 주체 주입 경계, 기본 401, 기관/역할/과거 버전 차단 시험.
- [x] 파일/DB 실패 주입, 재시도·고아 대사, 동시 중복·원본 불변·새 프로세스 재조회.
- [x] 필수 자료 관리 시험과 기존 계약 회귀. 증거: outputs/phase2a/VALIDATION_FINAL.json.
- [x] Phase 2B: 아래 제한된 논리 구조 파서·SourceBlock·영속 worker 수직 기능을 후속 사용자 요청으로 구현·시험. B-01 시각 순서/대표 corpus와 실인증은 별도 미완료다.
- [ ] 기존 G2 전체(파싱/표·그림/순서/실인증 등), C 배포, D 제출. 현재 완료로 처리하지 않는다.

상세 실행·상태 의미는 [Phase 2A 계약](docs/PHASE2A_BACKEND.md), 판정은 [보고](outputs/PHASE2A_REPORT.md)를 따른다. 기존 Phase 2 전체 체크박스는 부분 구현만으로 선택하지 않는다.

## Phase 2B 원문 추적·영속 파싱 10/16 후속 승인

- [x] PDF 기하학 문단·선 기반 표/병합·물리 page/bbox, HWPX 논리 spine/XML 문단·명시 제목·표/병합·이미지 참조 추출.
- [x] Anchor/SourceBlock 구조·schema v2 저장·버전/해시 범위·근거 재해결. 구조/의미/시각 상태 분리.
- [x] 등록과 작업 생성 동일 트랜잭션, 독립 worker·claim/heartbeat/lease·시도 fencing·재시도·중단 복구·원자 게시.
- [x] 신규34개 및 기존33개 전체67개 시험 PASS. 최신 증거: outputs/phase2b/VALIDATION_FINAL_V2.json.
- [x] 합성 PDF10/HWPX17개 블록 저장·모든 앵커 재해결, 실제 HTTP/worker·강제 종료 후 새 worker 복구.
- [ ] B-01 한컴 시각 순서/페이지·복잡 레이아웃/대표 공개 corpus·독립 골드셋 검증. 전체 G2 미완료.
- [ ] Phase 2C 후보: 결정론적 구조 청킹·EvidenceRef 연결부터. 실제 임베딩/LLM/지도는 B-02/03/04 선행 시험과 사용자 요청 필요.

현재 상세 기준은 [Phase 2B 계약](docs/PHASE2B_PARSING.md)이며 Phase 2A 보고/증거는 당시 범위로 보존한다. 제출11/11·동결11/09·후보11/10은 유지한다.

## Phase 0 문서 기반 수립 10/16

- [x] 현재 폴더·Git 상태·실행 도구 및 두 원문 확인.
- [x] FR-01~19 보존, 공모전 기준과 팀 선택 구분, 원본 보호 충돌 해소.
- [x] 기준 문서 7종 작성 및 로컬 일관성 확인.
- [ ] 담당자가 10/16 기관 수요조사 처리 여부와 참가 자격·기관 내 제출 절차 확인.

완료: 문서 기반은 준비됨. 행정 절차 완료는 미검증이며 문서 작성 완료와 구별한다.

## Phase 1 실행환경과 기술검증 10/16~10/19

의존: Phase 0 문서. 아직 앱 전체 구현 금지, 격리된 최소 스파이크만 다음 개발 요청 후 수행한다.

- [ ] PC 브라우저·Node/패키지 매니저·Python 3.12 가상환경·포트·인터넷 API 경로를 확인. 메모리·실행 한도는 개발/클라우드 작업자 실측으로 확인한다. 로컬 GPU·폐쇄망·Docker는 현재 필수 게이트에서 제외하고 후속/선택 검증으로 기록.
- [x] React+Vite+TypeScript·React Flow 설치/빌드와 FastAPI 최소 HTTP는 Phase 1의 제한된 PASS 증거를 재사용. 브라우저 동작/전체 앱 PASS는 아님. 정확 버전은 PHASE1_EVIDENCE의 lock/메타데이터에 보존.
- [ ] 공개/합성 PDF/HWPX 각 1종에서 표·이미지·앵커 추출과 재현 프리뷰 시험. HWPX 지원 범위·페이지 대응 한계 명시.
- [ ] 인터넷 LLM 후보 2종·OCR/Vision·임베딩의 실제 연결, 키 주입·자료 정책·예산·오류를 검증. 유료 호출은 범위/금액 승인 후만 수행. 후보는 GPT-4.1 mini와 Gemini 2.5 Flash이며 계정 접근·모델 수명·한국어 성능은 호출 시 다시 확인. mock 계약 PASS와 분리.
- [ ] rhwp의 최신 공식 기능·라이선스·필드 API·저장/재열기 시험. 불가하면 FR-13 보류, FR-12 폴백은 유지.
- [ ] SQLite+벡터 어댑터와 PostgreSQL+pgvector 후보의 필터·한글 키워드 품질·설치 난도 비교. 전용 그래프DB는 필수 아님.
- [ ] 검증 결과/명령/버전/라이선스/실패/대안과 결정 이유를 ARCHITECTURE에 기록. 재현 가능한 lockfile·환경 예제의 작성 계획 확정.
- [ ] 골드셋 표본·기대 근거·기관 경계·성능 예산·파일 한도를 TEST_PLAN에 확정.

G1의 현재 분류와 착수 조건은 docs/G1_GATES.md의 A/B/C/D가 단일 기준이다. A는 공통 개발 기반 진입, B는 해당 기능 전, C는 운영 배포 전, D는 제출 전 검사다. 전체 G1은 미완료이며 A 통과가 B/C/D 통과를 뜻하지 않는다. 과거 G1-A/B/C 표는 이전 결정 이력으로 아래에 보존한다.

## Phase 2 수집·원본·권한·버전 10/20~10/23

의존: G1 A 범주 및 작업별 B 범주. FR-01·02·14·15·18, NFR-01·02·06·07.

- [ ] G1 A 판정·작업별 B 확인·다음 개발 요청 후 React/Vite+FastAPI 골격, 초대 인증·기관 권한·개발 SQLite/클라우드 PostgreSQL 어댑터·비공개 객체 저장 경계를 구현.
- [ ] 업로드 검증/공개성 확인, 불변 원본·SourceElement, 영속 Job/worker·재시도·DB/파일 staging→검증→게시/대사를 구현. API는 접수 ID/202를 반환하고 긴 분석을 요청 메모리에만 두지 않는다.
- [ ] 메타 수정·원문 교체·추출 정정·등록 해제, 버전 이벤트 구현.
- [ ] TEST_PLAN 해당 기능·원본 해시·타기관 접근·악성 업로드·복구 회귀 실행.

G2 완료: 정상 PDF/HWPX의 표·그림 순서/위치 확인, 실패 시 부분 결과 공개 금지, 원본 불변·기관 격리·등록 해제 테스트 통과.

## Phase 3 멀티모달 지식DB와 근거 답변 10/24~10/28

의존 G2. FR-03~07·15·16·18, NFR-03·04.

- [ ] 인접 문단↔캡처 OCR↔Vision 설명, source_kind 분리.
- [ ] 구조 청킹, 자동 임베딩, 기관/버전 필터 후 하이브리드 검색과 재정렬.
- [ ] 주장별 근거 연결, 부족 정보 질문, 충돌/미확인·모델 장애 표시.
- [ ] TEST_PLAN 이미지·검색·답변·프롬프트 인젝션 및 G2 회귀.

G3 완료: 캡처 관련 질문에 실제 원문 이미지 이동, 텍스트·OCR·AI 구분, 삭제/교체 직후 옛 결과 차단, 근거 안전성 테스트 통과.

## Phase 4 업무지도·서식·변경 동기화 10/29~11/02

의존 G3. FR-08·09·11·12·14·16.

- [ ] 새 업무 자동 발견, 지식 관계모델·지도·목록·대화 동기화.
- [ ] 추천 근거·서식 프리뷰·미지원 다운로드 구현.
- [ ] 활성 버전 일괄 전환, 등록 해제/교체의 지도·서식·캐시 영향 처리.
- [ ] TEST_PLAN 미지 업무·순서·추천·접근성·버전 전환 회귀.

G4 완료: 기본팩과 미지 기관 매뉴얼로 코드 수정 없이 A/B/C 시나리오, 전체 P0 기능 회귀 통과. 정량 골드셋 미달은 원인·수정 작업으로 남긴다.

## Phase 5 조건부 기능·품질 강화 11/03~11/06

의존 G4. FR-10·13·17·19. 11/04 최종 채택 판단.

- [ ] P1별 채택/이월·증거·이유를 PRD/README 상태에 반영.
- [ ] 채택 시 자연어 지도 편집 확인/취소, 1종 초안 저장/재열기, 예외 비교 UI, 평가 모드 구현.
- [ ] G1에서 최소 연결/교체를 확인한 실제 모델 2종을 전체 동결 골드셋으로 재평가. 생성 모델과 임베딩 교체는 별개 시험이며 실패/비용/근거 의미 일치도 기록.
- [ ] 임베딩 교체 시 재색인·차원 검증·비활성 인덱스 전환 회귀.
- [ ] 정량 목표, 권한·근거·원본 보호 안전성 게이트, 실패 복구·자원/시간 측정.

G5 완료: P0 목표 통과, 채택 P1 기준 통과, 이월 사실 공개. 모델 2종 입증 불가 시 모델 비종속 계약 자체는 유지하고 실증 한계를 기록한다. 기준 미달을 완료로 표기하지 않는다.

## Phase 6 독립 실행과 제출 후보 11/07~11/10

의존 G5. 11/09 기능 동결, 11/10 후보 완성.

- [ ] 깨끗한 검증 환경에서 Git 복제에 해당하는 로컬 소스 복사/설치부터 초기화·샘플 투입·핵심 흐름·재시작·중지·모델 교체 재현.
- [ ] 승인된 공개 URL의 HTTPS·인증·CORS·rate limit·키 비노출·절전/재시작·DB/파일 영속성·복원을 확인. 사용자 브라우저 사용법과 심사자 독립 소스 실행법/환경변수를 README에 분리한다. Docker는 선택이며 네이티브 경로를 필수 제공.
- [ ] 신청서 PDF·A4 3~5쪽 구동안내서 PDF·약 5분 이내 MP4·비민감 데이터·소스와 lockfile·라이선스/출처 목록 준비. 이 문서 작업에서 해당 파일 제작까지 완료한 것은 아님.
- [ ] 공공 GitLab 비공개 프로젝트/세션2 Topics/심사위원 권한/신청서 링크 계획 점검. 계정·권한·등록은 미검증. 승인 전 원격 변경 없음.
- [ ] 구동안내서에 환경·설치·모델 연결·키 입력/교체·샘플·사용 순서·제약·재배포 제한·1쪽 이내 개발 경위 포함.
- [ ] 제출 후보 해시/commit·테스트 보고·미해결 항목 고정, 시연 실제 화면과 기능표 일치.

G6 완료: 개발자 개입 없이 문서만으로 독립 실행 합격, 제출 규격·민감정보/비밀 검사 통과. 부족하면 신규 기능 대신 재현성 수정을 우선한다.

## Phase 7 승인 후 제출 11/11

- [ ] 담당자가 최신 공지·정확한 마감 시각·기관별 신청목록·수요조사 이행 확인.
- [ ] 검토 가능한 최종 후보에 대한 사용자 원격 push/제출 승인 확보.
- [ ] 승인 범위에서 공공 GitLab 등록, 비공개·세션2 Topics·심사위원 접근 검증, 신청서 링크 확인.
- [ ] 이메일 수신처·제목·첨부 규격 확인 후 승인된 발송, 도착 접수 증빙 확보. S2 기준 수신처 databus@nia.or.kr, 제목 `[공공 AI 대전환 챌린지 제출]_세션2_기관명_팀명`.
- [ ] 제출 해시/시각/접수 증빙 기록, 마감 이후 등록 산출물 업데이트 금지.

G7 완료: 등록과 접수 확인 증거가 있어야 제출 완료다. 로컬 준비만으로 제출 완료를 주장하지 않는다.

## 이전 인터넷망 검증 작업과 일정 이력

| 작업 | 기간 | 완료 증거/현재 상태 |
|---|---|---|
| G1-A 기존 스파이크 증거 보존 | 10/16 | ZIP CRC·56개 해시 확인. 기술별 제한된 PASS 유지 |
| G1-B HWPX·실제 AI·의미검색·브라우저·루트 확인 | 10/16~10/19 | 기존 미검증을 유지. 공개/합성 정상 자료, 실제 2모델·임베딩 시험, 키/예산 승인, 그래프 클릭/원문 대조 필요 |
| G1-C 클라우드 최소 환경·영속성 검증 | 10/19 목표 | 플랫폼/리전·비용 승인 후 최소 검증. 재시작·재배포 뒤 DB/파일/권한·해시 확인. 미승인/미실행은 BLOCKED/NOT_RUN |
| 배포 구조·비밀/환경·마이그레이션 계획 | 10/16~10/19 | 문서 작성 완료와 실제 DB 접속/리소스 생성은 구분. 계정/리전/용량은 미검증 |
| 기능별 보안/영속성 회귀 | Phase 2~5 | TEST_PLAN WEB-01~08. 단계마다 실행/실패/미실행 기록 |
| 심사 운영 준비 | 11/03~11/06 | 승인된 유료/적합 플랜 결정, 절전/메모리 시험, 별도 worker와 백업/복원. 무료 만료 직전 의존 금지 |
| 공개 후보·독립 실행·영상 | 11/07~11/10 | 11/09 기능 동결·11/10 후보. 평가자 브라우저 계정, 설치 가능한 소스·샘플·실제 모델 설정, URL/제약 확인 |
| 승인된 제출 | 11/11 | 비공개 공공 GitLab·심사 권한·URL·접수 증빙, 마감 후 산출물 업데이트 금지 |

G1-C가 승인 대기이면 클라우드 실증을 PASS 처리하거나 자동으로 무료 배포하지 않는다. 일정에 영향이 생기면 완료한 증거와 남은 조건을 보고한다. 현재 Phase 2의 단계별 착수는 docs/G1_GATES.md의 A/B 조건으로 판단하며 전체 앱 구현은 이번 범위에 없다. 등록 해제·원본 불변·모델 독립·공모전 제출 규격은 종전 기준을 유지한다.

## Phase 2C-2A 로컬 RAG 계약 2026-10-17

- [x] Embedding/LLM/HybridSearch 인터페이스와 명시 주입형 결정적 테스트 대역. 실제 모델은 미연결.
- [x] SQLite 벡터 세대·원자 게시·멱등 재색인/전환·RRF·EvidenceRef/기관/현재 활성 버전 재검사.
- [x] 합성 PDF/HWPX 2문서·13질의 개발 평가셋과 keyword/vector/hybrid 비교. 전체 대표 골드셋·실제 의미검색은 미검증.
- [x] Feature Gate 및 Phase Gate 전체 회귀123개(기존93+신규30) PASS. [실행 결과](outputs/phase2c2a/VALIDATION_FINAL.json).
- 계약은 [로컬 RAG](docs/PHASE2C2A_RAG.md), 실제 모델 연결 전 조건은 [API 사전 검토](docs/LLM_API_PREFLIGHT.md)를 따른다. 기존 미검증·G1/G2와 공개 배포 차단은 유지한다.

## Phase 2C-2B 실제 AI 연결 사전검증

- [x] 공식 모델/API/단가·Deprecated 상태 조사와 승인용 [실행계획](docs/PHASE2C2B_EXECUTION_PLAN.md) 작성. 기존 설정 변경 없음.
- [x] 합성7문서·40질의 원문/EvidenceRef·정답·절차·보류 검토자료 준비 및 구조 확인.
- [ ] 독립 정답 검토/동결, 키·계정·모델 가용성 확인, 실제 adapter/예산 통제/검색 질의·절차 출력 계약 선행 구현·회귀.
- [ ] 자료·2LLM/2embedding·API사용료 최대USD2 승인 후에만 실제 시험. 현재 실제 호출0, 기존123 PASS는 역사적 기록이며 전체 Phase/B-02/B-03 완료가 아니다.

## Stage2 디자인 시스템·공통 레이아웃

- [x] apps/web 검증 버전 고정·잠금파일·CSS 토큰·공통 컴포넌트·4화면 해시 전환·키보드/반응형 기반.
- [x] 오프라인 npm ci·타입검사·프로덕션 빌드, Chrome 정적 번들14개 검사 PASS. [보고](outputs/STAGE2_REPORT.md)·[계약](docs/STAGE2_FRONTEND.md).
- [ ] Stage3는 별도 승인 후. API/인증/실제 AI·업로드/검색·원문 검토·실제 업무 수치는 이번 범위 밖이다.

## Stage3 업무 홈

- [x] 승인된 업무 홈 구현 및 Feature Gate 타입/빌드·홈6개·Stage2 회귀14개 PASS. [현재 보고](outputs/STAGE3_REPORT.md).
- [ ] Stage4 별도 승인 필요. 실제 HTTP·사용자 목표 검증 미검증 유지.

## Stage4A 문서 관리 UI·API Client

- [x] raw body 등록·검증·중복 제출 방지·목록/상세/버전·원본 다운로드 요청·상태/재시도·논리 해제 확인 UI.
- [x] 타입/빌드·모의 신규16개/기존 UI20개·실제 FastAPI HTTP401 차단6개 PASS. [현재 실행 보고](outputs/STAGE4A_REPORT.md).
- [ ] Feature Gate 잔여: 실제 브라우저 HTTP와 다운로드 파일 저장 BLOCKED. 인증된 통합·전체 접근성 미검증.
- [ ] Stage4B/4C는 별도 승인 후. 백엔드·DB·원문/EvidenceRef·실인증 변경 없음.

## Stage4B-2 로컬 인증·기관 권한

- [x] 기본 deny-all 유지, provider mock 전송 계약·BFF 세션·CSRF/Origin·기관 멤버십·React 로그인 상태 구현.
- [x] 기존123+신규30=153 backend 회귀 및 auth/UI 영향 검증. [보고](outputs/STAGE4B2_REPORT.md), [계약](docs/STAGE4B2_AUTH.md).
- [ ] Stage4B-3 실제 계정/키/remote transport/JWT·세션 lifecycle·TLS 실증은 별도 승인 후. 다운로드 파일저장 BLOCKED는 기존 상태 유지.

## Stage 4B-3A Supabase 원격 전송 계층

- [x] 기존 IdentityProviderAdapter/SupabaseProviderAdapter 유지, 고정 HTTPS HTTP transport·서버 설정·사용자 조회 검증·오류/민감정보 차단 구현. 기본 앱은 deny-all 유지.
- [x] 기존153+새 HTTP/BFF52=205 backend PASS, UI Chromium43 PASS, typecheck/build PASS. 비루프백 DNS/TCP 차단 가드 아래 실제 공급자 호출0. [계약](docs/STAGE4B3A_SUPABASE_TRANSPORT.md)·[실행 보고](outputs/STAGE4B3A_REPORT.md).
- [ ] Stage 4B-3B는 실제 프로젝트/계정/키·허용 origin/TLS·접속/비용 범위의 별도 승인 후 server factory 활성화와 실제 공급자 검증. 이번에는 실제 Supabase/LLM/임베딩 호출·키 등록·배포·commit/push/merge를 하지 않았다.

## v0.2-A 화면 안내 정합성

- [x] PR #2가 포함된 최신 main에서 feat/v02a-ui-clarity 분기. 권한별 홈·공통 기능 안내와 근거/내용 검토 상태 분리. [계약](docs/V02A_UI_CLARITY.md).
- [ ] P0-2 활성화 동선은 별도 승인 후. API/DB/엔진·실제 공급자·승인/게시·배포는 이번 범위 밖이다.
- [x] 타입·빌드, 신규 UI24·기존 UI104·실제 HTTP13·backend409 최종 PASS. 중간 실패 기록과 재실행을 구분한 [완료 보고](outputs/V02A_REPORT.md). 승인/게시·P0-2는 미구현 유지.

## v0.2-B 문서 처리·활성화 동선

- [x] v0.2-A 커밋809a2dd 보존 후 별도 feat/v02b-document-flow 분기. 등록→상세·처리 상태→관리자 확인 활성화→현재 문서·버전 후보 검토 연결. [계약](docs/V02B_DOCUMENT_FLOW.md).
- [ ] 후속 개발은 별도 사용자 요청 후. 실제 공급자·공식 승인/게시·서식 등록·DB 변경·배포는 이번 범위 밖이다.
- [x] Feature Gate 타입·빌드, 신규 UI26·기존 UI128·실제 HTTP14(기존 별도13)·backend409 최종 PASS. [완료 보고](outputs/V02B_REPORT.md). 최초 실패와 영향 범위 재실행 증거는 보존했다.

## v0.2-C 모바일 사용성

- [x] v0.2-B 변경을 로컬 커밋 e52ec2d로 보존하고 feat/v02c-mobile-ux 분기. 단일 문서 DOM 카드 배치·모바일 단계 목록 기본·지도 글자/44px 제어·선택 크게 보기·일반 안내 간소화 및 심각 이슈 보존. [계약](docs/V02C_MOBILE_UX.md).
- [ ] 이후 기능·실제 공급자·배포는 별도 사용자 요청 후. API/DB/승인·게시 계약 변경 없음.
- [x] 신규 UI20·기존 UI154·실제 HTTP14(기존 별도13)·backend409 및 타입/빌드 최종 PASS. 실측·중간 실패·후속 접근성 미검증을 구분한 [완료 보고](outputs/V02C_REPORT.md).

## v0.3-A 실제 연결 전 안전장치

- [x] 분석 3파일을 193e54d 로컬 커밋으로 보존하고 feat/v03a-provider-safety 분기. Fake-only transport/strict 출력·근거 검증과 별도 SQLite 모의 비용 원장 구현. [계약](docs/V03A_PROVIDER_SAFETY.md).
- [x] 신규86·전체 backend495·UI174·실제 HTTP13·타입/빌드 PASS. [보고](outputs/V03A_REPORT.md).
- [ ] 실제 공급자·실비 예산 승인·평가 정답 독립 검토·v0.3-B는 후속 사용자 요청 후. push/merge/배포 없음.

## v0.3-B 오프라인 평가 기반

- [x] v0.3-A를 a3bfee3으로 로컬 보존하고 feat/v03b-evaluation-fixtures 분기. 실제 parser/chunker의 신규 평가 세대·EvidenceRef 재연결·question-only window 검색·분리 metric scorer·40문항 인간 검토표 구현. [계약](docs/V03B_EVALUATION_FOUNDATION.md).
- [ ] 독립 인간 정답/관계/기한/조건/서식 주석 검토 및 실제 AI 성능은 미완료다. v0.3-C와 외부 호출·push·배포는 자동 진행하지 않는다.

- [x] 최종 신규59·전체 backend554·UI174·실제 loopback HTTP13·타입/빌드 PASS. 7원본 hash/57청크/51구조 근거 재연결 일치. 검색 no_hits40·인간 검토 대기40·AI NOT_RUN과 초기 namespace 오류를 구분한 [보고](outputs/V03B_REPORT.md).

## v0.3-C1 검색 실패 진단·고정 문맥

- [x] v0.3-B를 a3b8a35로 보존하고 feat/v03c1-retrieval-diagnostics 분기. 실제 SQL/색인/권한/token/Top-K와40문항 분류, 정답 독립 고정 문맥 Fake, 우선10문항 인간 검토 계획 구현. [계약](docs/V03C1_RETRIEVAL_DIAGNOSTICS.md).
- [ ] 실모델·임베딩·검색 개선 실험·인간 의미 검토는 별도 승인/작업 후. 현재 PROVISIONAL/NOT_VERIFIED/NOT_REQUESTED 유지.

- [x] 신규37·전체 backend591 PASS, 별도 CLI guard 외부 시도0. 36literal/AND 탈락과4expected abstention 구분, 고정 문맥40문항/7문서 Fake 완료. 인간 검토0/40·의미 합격false 유지. [보고](outputs/V03C1_REPORT.md). UI174/타입·빌드는 소스 동일성에 따른 이전 증거 재사용이며 새 실행 아님.

## v0.3-C2 오프라인 검색 비교

- [x] C1을137177b로 로컬 보존하고 feat/v03c2-retrieval-ablation 분기. 사전 고정 규칙으로 A literal AND/B정규화/C점수 OR/D기관별 FTS5 BM25를 비교하는 독립 평가 도구 구현. [계약](docs/V03C2_RETRIEVAL_ABLATION.md).
- [ ] 제품 교체·실제 모델/임베딩·독립 인간 검토·후속 실험은 별도 승인/요청 후.

- [x] 신규27·전체 backend618 PASS. 3회 반복/초기-최종 순위·점수 동일, FTS5 지원 확인, 외부 시도/지출0. C를 연구 후보로 제안하고 제품 교체 없음. [최종 보고](outputs/V03C2_REPORT.md). 인간 검토40·실 AI 성능 미검증 유지.

## v0.3-D 서버 flag와 명시적 C API

- [x] C2를 e2bb7f7로 로컬 보존하고 feat/v03d-opt-in-scored-search 분기. literal 기본 유지·서버 허용+명시 strategy의 C 검색·bounded scan·원본/세대 재검증·실제 TCP API 비교 도구 구현. [계약](docs/V03D_OPT_IN_SCORED_SEARCH.md).
- [ ] 실제 환경 flag활성화/배포·실모델/임베딩·인간 의미 검토·후속 UI/검색 확장은 별도 사용자 승인/요청 후.

- [x] 신규24·전체 backend642·UI174·타입/빌드·기존 HTTP13·새 API HTTP11묶음 최종 PASS. 실제 API C2 Top10 40문항 동등, 서버 flag기본off/literal 기본 유지, 외부 호출/지출0. [보고](outputs/V03D_REPORT.md).

## v0.3-E 우선 10문항 인간 검토 지원

- [x] C1 선정 순서를 유지하는 별도 오프라인 검토 HTML/JSON·빈 판정 CSV와 제출 형식 검증 CLI. 원문 replay/live 근거 검증, 기관별 문맥, 원본/정답 불변. [사용법](docs/V03E_HUMAN_REVIEW_SUPPORT.md).
- [ ] 실제 인간 검토 0/10(전체 0/40), 독립 판정·골드 승인·실제 모델 평가 미실행. 기존 PROVISIONAL/NOT_VERIFIED 유지.

## 인터넷 배포 준비 계획 — 2026-10-18

- [x] 사용자 요청 범위의 배포 구성·비용 가정·인증/DB/객체/worker 차이·백업·설정·실행 순서 검토. [실행 계획](docs/INTERNET_DEPLOYMENT_PLAN_20261018.md). 실제 리소스/외부 호출/배포 없음.
- [ ] 다음 구현 제안: strict 운영 설정·시작 계약/오프라인 사전 검사. PG·객체 저장·실Auth/staging·G1-C는 별도 구현/승인 후. 인간 판정은 별도 진행, 자동 생성/승인 안 함.
