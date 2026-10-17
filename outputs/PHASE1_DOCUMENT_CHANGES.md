# Phase 1 결과에 따른 기준 문서 수정안

상태: 적용 전 제안 / 2026-10-16. 기존 문서 7종은 변경하지 않았다. FR-01~19와 제품 비전·필수/조건부/후속 범위 및 11/11 제출 일정을 유지한다. 스파이크 버전·시험 성공을 제품 구현 완료로 해석하지 않는다.

## PRD.md

FR-02 수용 기준에 HWPX package spine 순서, 문단/run/표 셀/그림 참조 보존과 논리/시각 순서 차이 경고를 추가한다. 검증되지 않은 페이지 번호를 만들지 않는다. 복잡한 레이아웃을 임의로 요구사항에서 삭제하지 않고 시험 범위와 실패를 공개한다.

FR-07·08과 NFR-03에 JSON 문법/스키마 적합성, 근거 ID·위치 재해결, 주장과 근거의 의미 일치를 별도로 검증한다고 명시한다. 형식 PASS만으로 사실 안내를 확정하지 않는다. 노드뿐 아니라 간선·추천 이유·그림 설명·초안 규정 필드까지 연결을 유지한다.

NFR-04·05에 실제 2종 생성 모델과 mock 계약 시험, 실제 임베딩과 수동 벡터 연산, 동일 호스트 재설치와 독립 PC 검증을 구분한다. 기존 정량 목표·안전성 0건 게이트는 변경하지 않는다.

## ARCHITECTURE.md

환경 표를 이번 실증으로 갱신한다. PowerShell python 별칭 실패/번들 성공, 모듈 pip 성공, 작업 TEMP 필요, 일반 npm 부재/workspace npm-cli 성공, pnpm symlink 실패를 구분한다. Docker는 선택적 추가 검증 경로로 둔다.

React+Vite+TypeScript·React Flow·FastAPI/Pydantic·SQLite 우선안을 제시하되 브라우저·독립 실행·동시성 한계를 함께 기록한다. 정확 버전·lockfile을 연결하고 실제 개발에서는 latest를 제거한다. 의미 검색은 RetrievalAdapter와 NumPy 기준 연산부터 시작하되 실제 embedding·한국어 검색·규모 실측 후 물리 벡터 저장소를 결정한다.

HWPX 계약에 manifest/spine·상대 리소스 경로 정규화·중첩 텍스트 중복 방지·셀 주소/병합·이미지 resource ID·읽기 이벤트·XML 앵커를 추가한다. ZIP 경로/압축 한도와 XML 공격 방어를 구현 완료와 구별해 명시한다. 정상 렌더러/뷰어 검증은 구조 추출과 별도다.

LLM 공급자 capability matrix에는 structured output dialect, refusal, reasoning, 이미지, stream, timeout/retry와 오류 변환을 둔다. fixture URL은 실제 endpoint가 아니며 실모델 성능 증거가 아니다. 자동 외부 fallback 기본 차단을 유지한다.

폐쇄망 계획에는 API docs CDN·웹 폰트·뷰어·모델 자동 다운로드 의존성을 제거/자가 호스팅하고 OS/CPU별 패키지·가중치·언어팩·허용 폰트·해시·라이선스를 사전 반입하도록 추가한다.

## TASKS.md

실제 설치·기동 세부 항목에만 완료 증거를 연결할 수 있다. Phase 1 전체/G1은 미완료로 둔다. 메모리/GPU·망/모델 정책·정상 HWPX 프리뷰·실제 모델/embedding·OCR/Vision·rhwp 저장·골드셋·성능 예산·파일 한도는 남은 작업이다.

10/19 보완 작업은 PHASE1_REPORT §7에 연결한다. 설치용 timeout/다운로드 옵션을 운영 SLO로 전용하지 않는다. Phase 2 전 루트·지침 배치를 확정한다.

## TEST_PLAN.md

| 추가 시험 | 최소 확인 |
|---|---|
| 정상 HWPX | 완전한 패키지·실제 renderer 비교, 다중 section·중첩/병합표·떠 있는 그림·다단·페이지 분할 |
| JSON 계약 | 잘못된 형식·필수 근거 누락·중복 ID·끊어진 관계·지원하지 않는 필드 거부 |
| 근거 의미 | 존재하는 인용으로 무관한 기한을 주장하는 경우 억제, 조건/적용범위와 주장 대조 |
| 실제 모델 교체 | 2종 동일 골드셋, schema/refusal/timeout/stream 차이 확인 |
| 검색 | 학습된 한글 임베딩, 기관/시점/활성 필터, 차원/세대 재색인, Top-5·키워드 품질 |
| 독립·제한망 | 다른 사용자/PC, 패키지·모델·언어팩 반입, outbound deny에서 설치·질의·재시작 |

기존 합격 기준은 유지한다. 스파이크 PASS를 FR 수용 PASS로 승격하지 않는다. 합성 구조 ZIP은 정상 HWPX 호환성 표본으로 계산하지 않는다.

## README.md와 최종 배치

Git 미구성·완성 앱 미존재를 유지하며 Phase 1 결과를 연결한다. npm-cli와 번들 Python은 현 환경의 우회법이며 심사 PC의 필수 경로가 아니다. 실제 실행 스크립트가 생기기 전 가짜 앱 명령을 적지 않는다.

현재 workspace를 향후 Git 루트로 삼는 안을 권고한다. 루트 AGENTS.md·`.agents/skills/seomuitda-quality-check/SKILL.md`와 나머지 문서의 단일 기준 위치·상대 링크를 함께 확정한다. 기존 outputs를 보존하고 이동/중복 제거는 범위 확정 후 수행한다. 같은 Skill 이름이 중복 탐색되지 않게 한다.

## AGENTS.md와 Skill

AGENTS에는 확정된 루트·실행환경·실제 테스트 명령의 기준 위치를 연결한다. 제품 수치·세부 검사 절차는 중복하지 않는다. Skill은 기존 반복 절차를 유지하고 JSON 형식/근거 재해결/의미 일치, mock/실제, 논리/시각 순서, 동일 호스트/독립 PC 차이를 TEST_PLAN에서 읽어 검사한다.

quick_validate는 UTF-8/PyYAML 조건에서 통과했다. 자동 발견·명시 `$` 호출·실제 게이트 충족은 별도 확인 대상이다. 이번에 자동 호출 성공으로 표기하지 않는다.
