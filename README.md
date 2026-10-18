# 서무ITDA

현재 기준은 **서무ITDA v0.1 오프라인 통합 검토본**이다. PDF/HWPX 등록·파싱·청킹·영속 업무 후보 추출/검증·서식 관계·관리자 React Flow 지도/원문 검토를 제공한다. 실제 AI·Supabase 원격 로그인·공식 승인/게시·공개 배포는 미검증이다. [시연·설치·실행 안내](docs/V01_DEMO.md)와 [v0.1 검증 보고](outputs/V01_REPORT.md)를 따른다. 표준 앱은 인증 미설정 시 기본 차단한다.

인터넷 HTTPS URL에서 PC 브라우저로 사용하는 근거 기반 AI 서무 노트북이다. 공개 접속과 기관 자료/관리 권한은 분리하며 공개·합성 데이터만 사용한다. 2026 공공 AI 대전환 챌린지 세션2 서무비서: 활용성40·완성도30·확산용이성30, 제출11/11·기능동결11/09·후보11/10을 유지한다.

## 저장소와 기준 위치

현재 폴더가 로컬 Git 루트다. 루트의 [PRD](PRD.md), [AGENTS](AGENTS.md), [TASKS](TASKS.md), [ARCHITECTURE](ARCHITECTURE.md), [TEST_PLAN](TEST_PLAN.md)와 [.agents Skill](.agents/skills/seomuitda-quality-check/SKILL.md)이 기준이다. outputs의 옛 문서 위치는 연결 문서다. 수정 전 사본은 outputs/REPOSITORY_BEFORE.zip, Phase 1 보고·증거도 outputs에 보존한다.

- docs/: [G1 분류](docs/G1_GATES.md), [LLM 설정](docs/LLM_CONFIGURATION.md), [골드셋](docs/GOLDSET.md), [브라우저 검증](docs/BROWSER_TEST.md).
- schemas/: 업무절차/근거 JSON 계약. scripts/validation/: 외부 호출 없는 검증 도구.
- tests/fixtures/synthetic/: 직접 생성한 비민감 샘플과 정답. 원본·허용범위·hash를 manifest에 기록.
- outputs/: 사용자 보고와 증거. ZIP 원문/로그는 기본 Git 제외, 정제된 문서만 초기 포함 후보.
- work/: 이전 스파이크·venv·node_modules·다운로드/임시 로그를 보존하되 Git 제외.
- apps/api/: 자료 관리·파싱/청킹·업무 후보 영속 worker/API. apps/web/: React 관리자 지도·근거 검토 및 문서/인증 화면. 실제 공급자 연결은 별도 승인 범위다.

## 기술과 게이트

React+Vite+TypeScript+React Flow, Python3.12+FastAPI+Pydantic, 개발 SQLite를 유지한다. 클라우드 영속 DB/객체 저장소는 C 범주 배포 검증에서 확정한다. 인터넷 LLM은 서버 시크릿과 교체형 Adapter를 사용한다. 내부 GPU/폐쇄망/Docker는 현재 핵심 개발 필수가 아니다.

기존 설치/빌드·HTTP·단순 파싱/모의 계약 PASS는 outputs/PHASE1_EVIDENCE.zip의 제한된 실증이다. 전체 G1은 미완료다. A 공통 기반이 준비되면 A를 전제로 하는 Phase 2 세부 작업부터 착수 가능하며, 실제 HWPX/AI/검색/브라우저 등의 B 검사는 해당 기능에 앞서 통과해야 한다. C 배포·D 제출 미검증을 A 차단으로 혼동하거나 PASS로 승격하지 않는다. v0.1은 아래 과거 Phase 기록과 구별한 로컬 통합 검토 기준이며 G1 C/D 운영·배포·제출 미검증을 완료로 바꾸지 않는다.

## 실행과 비밀

현재 공개 운영 URL은 없다. v0.1 로컬 검토 화면의 재현·시연은 [현재 실행 안내](docs/V01_DEMO.md)를 따른다. 이전 API/worker 실행·원문 추적·인증 차단은 [Phase 2B 파싱 계약](docs/PHASE2B_PARSING.md)을 따른다. [Phase 2A 백엔드](docs/PHASE2A_BACKEND.md)는 자료 관리의 이전 계약으로 보존한다. 일반 사용자는 향후 브라우저만, 소스를 독립 실행하는 평가자는 Python/Node와 환경설정이 필요하다.

Phase 2A는 FastAPI/Pydantic/SQLite의 문서 등록·원본 보관·상태·버전·기관 경계만 구현했다. 기본 API는 deny-all 인증이며 외부 공개용이 아니다. 실행 결과는 [Phase 2A 보고](outputs/PHASE2A_REPORT.md)에서 확인한다. 기존 Phase 1/G1 증거와 FR-01~19·WEB-01~08은 유지한다.

Phase 2B에서 PDF/HWPX 구조 블록·원문 앵커·영속 파싱 작업/중단 복구를 추가했다. 실제 시험 결과는 [Phase 2B 보고](outputs/PHASE2B_REPORT.md)다. 파싱 완료는 AI 분석/업무 의미·한컴 화면 순서 검증을 뜻하지 않는다. 인증 없이 자료 API를 사용할 수 없으며 공개 배포는 계속 차단한다.

.env.example은 빈 서버 설정 계약이다. 실제 .env·API 키·토큰·DB 자격증명·원본 문서는 Git 제외한다. 키를 채팅/클라이언트 VITE_*에 넣지 않는다. 유료 API·클라우드 자원·공개 배포·원격 push는 별도 승인 전 실행하지 않는다. 현재 GitHub origin은 seulkichoe80-hash/project_SB이다. 사용자 승인에 따라 feat/phase2d-offline-extraction 브랜치에 v0.1 기준을 보존하고 main은 PR 검토 대상으로 유지한다. 원격 보존 결과는 v0.1 완료 보고를 따른다.
