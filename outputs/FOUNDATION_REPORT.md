# 서무ITDA 저장소 안정화와 G1 검증 보고

작성일 2026-10-16 KST. 이번은 기존 프로젝트의 구조·문서·오프라인 검증 기반 정비다. 전체 앱·실제 LLM 호출·클라우드 자원 생성·원격 등록/push·배포는 수행하지 않았다. 기존 Phase 1 PASS와 미검증/차단 결과를 보존했다.

**현재 판정: A 공통 개발 기반은 준비됐고, 전체 G1은 미완료다. 다음 요청에서 B에 의존하지 않는 Phase 2 세부 기능부터 착수할 수 있다.** 실제 AI·검색·복잡 HWPX/원문 뷰·React Flow 기능은 해당 B 검증 후 진행한다. 배포 C와 제출 D도 아직 미완료다.

## 1 확정된 프로젝트 폴더 구조

현재 폴더 `C:/Users/외부망/Documents/Codex/2026-10-16/15-2026-ai-2-itda-prd`를 로컬 개발/Git 루트로 확정했다.

```text
프로젝트 루트/
  .git/                         로컬 저장소 main, 커밋 없음
  .gitignore  .gitattributes  .env.example
  AGENTS.md  PRD.md  TASKS.md  ARCHITECTURE.md
  TEST_PLAN.md  README.md         단일 기준 문서
  .agents/skills/seomuitda-quality-check/SKILL.md
  docs/                         G1 분류·API 설정·schema·골드셋·브라우저/검증 안내
  schemas/workflow.schema.json   구조화 절차/근거 계약
  scripts/validation/           생성/파싱·계약·평가·브라우저 스파이크 도구
  tests/                       외부 호출 없는 계약 시험
    fixtures/synthetic/         직접 만든 정상 HWPX·PDF·manifest·정답 부분표본
  outputs/                     사용자 보고·역사적 증거·연결 문서
    evidence/                   이번 검증 JSON, Git 제외
  work/                        이전 스파이크·venv·패키지·임시 로그, Git 제외
```

apps/web·apps/api는 다음 구현의 예정 위치로만 정했고 이번에는 생성하지 않았다. 이전 work 코드·설치물·원본을 삭제하지 않았다. 루트 6개 문서와 Skill이 현재 기준이며 outputs의 기존 6개 문서 경로는 루트 연결 문서로 바꿨다. Skill은 루트로 이동·수정해 활성 프로젝트 Skill을 하나만 남겼다. 수정 전 전체 outputs는 [REPOSITORY_BEFORE.zip](REPOSITORY_BEFORE.zip)에 해시와 함께 보존했다. 기존 PHASE1_REPORT/PHASE1_DOCUMENT_CHANGES/PHASE1_EVIDENCE는 바이트 불변이다.

현재 기준: [루트 README](../README.md), [AGENTS](../AGENTS.md), [PRD](../PRD.md), [TASKS](../TASKS.md), [ARCHITECTURE](../ARCHITECTURE.md), [TEST_PLAN](../TEST_PLAN.md), [Skill](../.agents/skills/seomuitda-quality-check/SKILL.md).

## 2 Git 초기화 결과와 초기 포함 검토

실행 전 git rev-parse/status는 not a git repository였다. `git init -b main`으로 현재 폴더에만 초기화했다. 원격 없음, index 비어 있음, HEAD commit 없음이다. 최초 커밋 전에 포함/제외를 보고하라는 요청에 따라 stage/add/commit은 하지 않았다.

sandbox가 저장소를 Administrators 소유로 판단해 일반 git status는 dubious ownership으로 거부됐다. 현재 루트를 확인한 후 `git -c safe.directory="현재 루트 절대경로" ...`로 상태·ignore·remote·index를 조회했다. 전역 safe.directory·소유권 변경이나 `safe.directory=*`는 사용하지 않았다. 사용자 환경에서 일반 Git도 동작하는지는 별도 확인 대상이다.

[초기 커밋 포함·제외 검토](INITIAL_COMMIT_REVIEW.md)에 실제 파일 목록·크기·SHA-256·보안 검사 한계·제외 이유를 기록했다. API 키·.env·가상환경·node_modules·work·DB/로그·사용자 자료 경로·압축 증거는 기본 제외한다. .env.example은 빈 값만 포함한다. 합성 HWPX만 명시 예외이며 합성 PDF는 폰트 재배포 검토 전 Git 제외로 보존한다. 민감 여부는 확장자/패턴만으로 완벽히 판정할 수 없어 최초 커밋 전 사람이 목록을 검토해야 한다.

## 3 AGENTS Skill 배치와 인식

루트 AGENTS.md와 `.agents/skills/seomuitda-quality-check/SKILL.md`를 배치했다. Skill 디렉터리에서 ../../..가 실제 루트이고 활성 프로젝트 Skill 파일은 1개다. 형식 검증 quick_validate.py는 `Skill is valid!`, 현재 문서 링크/FR-01~19 보존 검사는 PASS다. 현재 작업은 루트 지침을 직접 읽고 적용했다.

자동 인식은 별도다. 모델 호출 없이 로컬 `codex app-server`의 initialize→skills/list를 시도했지만 기본 Codex home의 상태 SQLite 쓰기 실패로 차단됐다. 상태/로그를 work에 지정한 프로세스 단위 재시도도 Access denied로 종료돼 동적 목록 결과를 받지 못했다. **자동 Skill 발견/명시 호출과 다음 세션 AGENTS 프롬프트 주입은 미검증/BLOCKED다.** 파일 위치·형식 PASS를 실제 인식 PASS로 바꾸지 않는다. 글로벌 설정·계정/키·기존 앱 상태는 변경하지 않았다.

필요 조치는 정상 사용자 권한의 프로젝트 세션에서 루트로 열고 지침/Skill 목록을 확인하는 것이다. API/모델 호출 없는 discovery 단계만 우선 확인한다. 공식 문서상 AGENTS의 프로젝트 루트→CWD, Skill의 CWD→루트 탐색 위치와 일치하게 배치했다. [AGENTS 공식 안내](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Skill 공식 안내](https://learn.chatgpt.com/docs/build-skills), [skills/list 공식 안내](https://learn.chatgpt.com/docs/app-server).

## 4 G1 재분류 결과

[G1_GATES.md](../docs/G1_GATES.md)를 현재 진입 조건의 단일 기준으로 작성했다. 과거 보고의 전체 일괄 보류는 당시 판단으로 보존한다. 이번 재분류는 사용자의 지시에 따른 적용 시점 변경이다.

| 범주 | 의미 | 현재 판단 |
|---|---|---|
| A | Git/단일 문서/지침·선택 스택 최소 실행·자료/근거 계약·비밀/시험 경계 | 정적·계약 기반 준비. 자동 Codex runtime 인식의 환경 한계는 별도 공개 |
| B | 실제 HWPX/뷰·LLM2종·임베딩·React Flow·OCR/서식 등 해당 기능 전 | 구조/계약 일부 PASS, 실모델/검색/시각/UI 미검증·BLOCKED 유지 |
| C | HTTPS/Auth/CORS/secret/rate·예산·클라우드 DB/파일 영속성·복구·플랜 | 운영 배포 전 미검증. 승인 없는 생성·배포 없음 |
| D | 전체 회귀·동결 대표셋·모델/근거 품질·독립 실행·GitLab·제출 규격 | 제출 전 미완료 |

Docker·내부 GPU·폐쇄망은 현재 A를 막지 않는다. 개발 SQLite를 유지하고 클라우드 DB/저장소는 C에서 확정한다. 세션2 활용성40·완성도30·확산용이성30, FR-01~19/P0·P1·P2와 11/11 제출을 보존했다.

## 5 실제 기술검증 결과

요청 순서대로 ①HWPX ②API 설정 검토 ③JSON/근거 계약 ④골드셋 설계 ⑤임베딩 평가 방법 ⑥브라우저 준비·시험을 진행했다.

| 항목 | 결과 | 실제 범위/한계 |
|---|---|---|
| 정상 합성 HWPX | PASS | python-hwpx6.8.0의 완전 문서 생성·저장/재열기 validate issues=0, 수정된 v2 문단8텍스트/표4셀/그림1/원문 앵커9 재해결·PNG CRC·해시 불변. 직접 조립한 최소 ZIP을 정상 파일로 둔갑시키지 않음 |
| HWPX 화면·시각 순서 | 미검증 | 한컴/독립 renderer, 다단/병합/각주·페이지 대응은 NOT_RUN. 구조용1픽셀은 OCR 표본 아님 |
| 실제 LLM 설정 | 검토 완료 / 실제 BLOCKED | 빈 서버 .env.example·모델/예산/자료·키 주입/오류 계약. 실제 키를 읽거나 모델 호출하지 않음 |
| JSON/근거 검증기 | PASS | unittest9개, 정상 후보·근거 누락·기관/버전/요소·추가필드·중복/간선·허위 숫자기한·AI설명·의미 미검증 상태·검색계수/누출 검사 |
| 실제 AI의 의미 정확성 | 미검증 | 원문 인용 존재와 의미 일치는 별개. 결과는 candidate/semantic_review_required로만 반환 |
| 골드셋 | 설계/부분표본 준비 | 정상 합성 PDF/HWPX와 bootstrap 질의4개. 전체 문서/캡처/질의40개·절차10개 목표와 대표성은 미달/미검증 |
| 임베딩 검색 | 평가기 계약 PASS / 실모델 미검증 | Hit@5/Recall@5/MRR@5·권한/활성 누출·중복 방어 설계/단위시험. 실제 벡터 생성·검색은 없음 |
| React Flow | 준비 완료 / 실행 BLOCKED | 보존 Vite build의 localhost preview가 준비된 뒤 Edge가 실행 중 종료. 노드 클릭/화면 확인 미실행. 새 로그로 보존 |
| Git·문서·보존 | PASS 지정 범위 | root/main/원격·stage·commit 없음, 제외 규칙·링크·원본/역사 증거 해시 검사 |

현재 HWPX 도구는 검증 전용이며 기존 제품 파서 후보/스택을 교체한 것이 아니다. 설치물과 별도 venv는 work에 보존/Git 제외했다. [python-hwpx 프로젝트](https://github.com/airmang/python-hwpx).

실행 명령은 현재 명시 Python3.12 경로로 venv·python-hwpx/Pydantic/defusedxml 설치, `generate_hwpx_fixture.py`, `probe_hwpx.py`, `workflow_contract.py`, `python -m unittest discover -s tests -v`, 로컬 `browser_smoke.mjs`, quick_validate와 Git read-only 검사다. 재현 명령과 환경 한계는 [VALIDATION_SETUP.md](../docs/VALIDATION_SETUP.md)에 기록했다. [새 검증 JSON](FOUNDATION_VALIDATION.json)은 앱 품질 PASS가 아니라 문서/보존/계약 검사 결과다.

## 6 추가 입력자료와 API 설정

- 정상 공개/합성 HWPX의 기준 렌더 또는 한컴 열기 결과: 표/그림/다단/페이지를 대조할 수 있어야 한다. 이번 파일은 구조 검증됐지만 독립 시각 oracle은 없다.
- 실제 모델 2종의 승인된 계정·정확 모델/버전·quota·데이터 처리 조건과 호출 데이터/금액 상한. 키는 사용자 본인이 로컬 .env 또는 시크릿에 입력하며 채팅/Git에는 주지 않는다.
- 실제 임베딩 공급자/모델/차원/색인세대와 대표 공개 corpus·정답 검토자·holdout. [설정 안내](../docs/LLM_CONFIGURATION.md), [골드셋/평가 방법](../docs/GOLDSET.md).
- 정상 권한으로 실행되는 PC browser/Playwright와 Codex 프로젝트 세션. 현재 sandbox 정책을 전역 완화하거나 개인 브라우저 프로필을 사용하지 않는다.
- C 단계에서 hosting/리전·비용·보관기간·영속 DB/파일·Auth·백업 선택. 지금 계정을 만들 필요는 없다.

## 7 다음 바로 구현 가능한 기능

다음 사용자 개발 요청에서는 Phase 2의 **로컬 메타데이터 모델/SQLite repository, 불변 원본 저장·해시·상태/재시도·등록 해제, 서버 권한/기관 경계의 테스트 가능한 기반**부터 진행할 수 있다. 실제 외부 모델 없이도 계약과 부정 테스트로 구현 가능한 범위다. 각 기능 직후 단위/통합 및 기관·원본·버전 회귀를 실행한다.

실제 의미검색/AI 절차 생성은 B-02/B-03, 지도 UI는 B-04, 일반 HWPX 뷰와 시각 위치는 B-01 통과 전 완료 기능으로 구현·시연하지 않는다. 모의 데이터를 실제 AI 결과로 표시하지 않는다. 유료 API나 클라우드 승인이 없다는 이유만으로 독립적인 로컬 기반 작업 전체를 막지 않는다.

## 8 Phase 2 착수 판정

**제한적 착수 가능: A 준비 + 해당 작업의 B 조건을 만족하는 세부 기능만.** 전체 G1 PASS·전체 웹앱 착수·운영 배포 가능을 선언하지 않는다. 이번에는 실제 제품 API/화면을 구현하지 않았다. 다음 작업은 로컬 자료·권한·버전 저장 기반을 한 기능 단위로 지정하는 것이 적합하다.

초기 커밋은 [포함/제외 검토](INITIAL_COMMIT_REVIEW.md)를 확인한 뒤 별도 결정한다. 원격 저장소 등록/push·유료 서비스·공개 배포는 현재 승인 범위가 아니다. 보존 증거는 [FOUNDATION_EVIDENCE_V2.zip](FOUNDATION_EVIDENCE_V2.zip)과 변경 전 ZIP에 남겼다.

## 추가 발견과 회귀 보존

첫 v1 HWPX는 라이브러리 구조 검사와 이미지 참조는 통과했으나 추가 검사에서 내장 PNG IDAT CRC가 실패했다. 이를 정상 이미지 검증 PASS로 인정하지 않고 원본 v1/로그를 negative regression fixture로 보존했다. PNG를 표준 chunk/CRC로 생성한 새 v2에서 저장/재열기·문단/표/이미지·앵커·이미지 CRC를 재검증해 통과했다. 초기 증거 ZIP도 보존하고 최신 결과는 V2 증거 묶음으로 분리했다. 한컴 렌더와 시각 순서는 두 버전 모두 미실행이다.
