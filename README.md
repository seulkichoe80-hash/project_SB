# 서무ITDA

인터넷 HTTPS URL에서 PC 브라우저로 사용하는 근거 기반 AI 서무 노트북이다. 공개 접속과 기관 자료/관리 권한은 분리하며 공개·합성 데이터만 사용한다. 2026 공공 AI 대전환 챌린지 세션2 서무비서: 활용성40·완성도30·확산용이성30, 제출11/11·기능동결11/09·후보11/10을 유지한다.

## 저장소와 기준 위치

현재 폴더가 로컬 Git 루트다. 루트의 [PRD](PRD.md), [AGENTS](AGENTS.md), [TASKS](TASKS.md), [ARCHITECTURE](ARCHITECTURE.md), [TEST_PLAN](TEST_PLAN.md)와 [.agents Skill](.agents/skills/seomuitda-quality-check/SKILL.md)이 기준이다. outputs의 옛 문서 위치는 연결 문서다. 수정 전 사본은 outputs/REPOSITORY_BEFORE.zip, Phase 1 보고·증거도 outputs에 보존한다.

- docs/: [G1 분류](docs/G1_GATES.md), [LLM 설정](docs/LLM_CONFIGURATION.md), [골드셋](docs/GOLDSET.md), [브라우저 검증](docs/BROWSER_TEST.md).
- schemas/: 업무절차/근거 JSON 계약. scripts/validation/: 외부 호출 없는 검증 도구.
- tests/fixtures/synthetic/: 직접 생성한 비민감 샘플과 정답. 원본·허용범위·hash를 manifest에 기록.
- outputs/: 사용자 보고와 증거. ZIP 원문/로그는 기본 Git 제외, 정제된 문서만 초기 포함 후보.
- work/: 이전 스파이크·venv·node_modules·다운로드/임시 로그를 보존하되 Git 제외.
- apps/api/: Phase 2A 자료 관리 + Phase 2B 원문 추적 파서·독립 worker. apps/web는 아직 구현하지 않았다.

## 기술과 게이트

React+Vite+TypeScript+React Flow, Python3.12+FastAPI+Pydantic, 개발 SQLite를 유지한다. 클라우드 영속 DB/객체 저장소는 C 범주 배포 검증에서 확정한다. 인터넷 LLM은 서버 시크릿과 교체형 Adapter를 사용한다. 내부 GPU/폐쇄망/Docker는 현재 핵심 개발 필수가 아니다.

기존 설치/빌드·HTTP·단순 파싱/모의 계약 PASS는 outputs/PHASE1_EVIDENCE.zip의 제한된 실증이다. 전체 G1은 미완료다. A 공통 기반이 준비되면 A를 전제로 하는 Phase 2 세부 작업부터 착수 가능하며, 실제 HWPX/AI/검색/브라우저 등의 B 검사는 해당 기능에 앞서 통과해야 한다. C 배포·D 제출 미검증을 A 차단으로 혼동하거나 PASS로 승격하지 않는다. 이번에는 전체 웹앱을 구현하지 않는다.

## 실행과 비밀

현재 운영 URL·완성 웹앱은 없다. 현재 API/worker 실행·원문 추적·인증 차단은 [Phase 2B 파싱 계약](docs/PHASE2B_PARSING.md)을 따른다. [Phase 2A 백엔드](docs/PHASE2A_BACKEND.md)는 자료 관리의 이전 계약으로 보존한다. 일반 사용자는 향후 브라우저만, 소스를 독립 실행하는 평가자는 Python/Node와 환경설정이 필요하다.

Phase 2A는 FastAPI/Pydantic/SQLite의 문서 등록·원본 보관·상태·버전·기관 경계만 구현했다. 기본 API는 deny-all 인증이며 외부 공개용이 아니다. 실행 결과는 [Phase 2A 보고](outputs/PHASE2A_REPORT.md)에서 확인한다. 기존 Phase 1/G1 증거와 FR-01~19·WEB-01~08은 유지한다.

Phase 2B에서 PDF/HWPX 구조 블록·원문 앵커·영속 파싱 작업/중단 복구를 추가했다. 실제 시험 결과는 [Phase 2B 보고](outputs/PHASE2B_REPORT.md)다. 파싱 완료는 AI 분석/업무 의미·한컴 화면 순서 검증을 뜻하지 않는다. 인증 없이 자료 API를 사용할 수 없으며 공개 배포는 계속 차단한다.

.env.example은 빈 서버 설정 계약이다. 실제 .env·API 키·토큰·DB 자격증명·원본 문서는 Git 제외한다. 키를 채팅/클라이언트 VITE_*에 넣지 않는다. 유료 API·클라우드 자원·공개 배포·원격 push는 별도 승인 전 실행하지 않는다. 현재 로컬 Git만 초기화하며 초기 커밋은 포함/제외 목록 보고 전 만들지 않는다.
