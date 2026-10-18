# 서무ITDA v0.3-A 완료 보고

Fake 전송 전용 안전장치 구현과 현재 소스의 전체 회귀를 완료했다. 실제 LLM·임베딩·Supabase 호출 0회, 외부 자료 전송·지출·push·merge·배포 0회다. 의미 정확성·공식 승인 상태는 변경하지 않았다.

## 1. 변경 파일과 구조

신규 구현은 apps/api/provider_safety.py(설정/전송 경계), provider_budget.py(별도 모의 비용 원장), provider_fake_adapters.py(분리된 workflow/RAG/embedding adapter)다. tests/test_provider_safety.py에 신규86개 검증을 추가했다. docs/V03A_PROVIDER_SAFETY.md 및 ARCHITECTURE.md·TEST_PLAN.md·TASKS.md에 계약/검증 범위를 기록했다. outputs/v03a에는 이번 실행 JSON·로그·Chromium 회귀 화면을 추가했다. 기존 제품 코드·UI/API/DB 계약·fixture·과거 증거는 수정하지 않았다.

## 2. 모의 전송

ProviderSettings → 공개/합성 입력 manifest/hash → ProviderSafetyGateway → FakeTransport → 엄격한 envelope/usage → adapter별 스키마·출처 검증이다. 기존 LLMAdapter.generate 반환형과 WorkflowExtractionAdapter를 유지한다. 고정 HTTPS endpoint descriptor만 제공하며 실제 HTTP 구현·키/SDK 로딩·활성화 스위치는 없다. real_calls_enabled는 False만 허용한다. 임의 URL·리다이렉트·Transport/서브클래스/실행 콜백을 거부한다. 429/503의 알려진 usage만 최대1회 재시도한다.

## 3. 비용·동시성

별도 SQLite schema v1의 6개 테이블에 기관/작업/요청/시도/사건을 기록한다. BEGIN IMMEDIATE로 예약·차감·해제를 원자 처리하고 요청 소유 claim과 fingerprint로 중복 전송/차감을 막는다. thread 및 별도 process 경쟁, 부분 실패 rollback, 재시작/lease 만료를 실제 검사했다. 전송 전 실패는 해제하고 알려진 usage는 사용분만 정산한다. timeout·불완전 응답·전송 중 취소는 불명확 사용분의 최대 예약을 보존하고 재전송하지 않는다. manager가 bounded receipt로 reconcile해야 해제 가능하다. 모든 금액은 SIMULATED_USD이며 actual_spent=0이다. USD3은 미승인 제안이다.

## 4. 보안

기관/역할·현재 문서/버전·스냅샷/세대·EvidenceRef·정확한 인용 범위를 검사한다. 위조/범위 밖 근거·근거 없는 기한·추가 승인 필드·잘못된 응답을 거부한다. 문서 내 명령을 실행하지 않는다. raw 키·원문·응답·예외를 원장/로그/repr에 노출하지 않는다. Python socket guard와 상속 subprocess guard는 loopback만 허용했고 외부 호출 시도0을 확인했다. UI 회귀도 외부 요청0이다. 강한 비밀키/개인키 패턴 검사 결과0건이다. 기존 문서·원본·fixture·과거 증거를 포함한 기준 파일619개 hash가 그대로이며 기존 문서3개는 승인된 새 절만 추가했다. 테스트 당시 제품 소스 hash와 최종 소스가 일치한다.

## 5. 이번에 실제 실행한 결과

| 검사 | 결과 | 시간 |
|---|---|---|
| 신규 백엔드 | 86 PASS | 5.318초 |
| 전체 백엔드 | 495 PASS / FAIL0 / SKIP0 / BLOCKED0 | 142.781초 |
| 기존 UI 전체 | 174 PASS(104+24+26+20) | suite별 JSON 참조 |
| 실제 loopback HTTP E2E | 13 PASS | 24.823초 |
| TypeScript 타입 검사 | PASS | 0.776초 |
| 프로덕션 빌드 | PASS | 1.147초 |

전체 통합 runner는147.544초이며 일부 suite는 병렬 실행했다. 추가 UI24/26/20은 각각 별도 runner로 실행했다. 최초 신규 테스트의 빈 SUM NULL/0 비교 helper에서2 FAIL이 있었고 helper 수정 후 전체 재실행했다. 최초 실패 로그도 보존했다. 과거 결과로 대체한 PASS는 없다.

증거: [전체 실행](v03a/full-summary.json), [백엔드](v03a/backend.json), [네트워크 차단](v03a/backend.network.json), [HTTP](v03a/http-results.json), [보존·보안](v03a/PRESERVATION_SECURITY.json). UI 기본104개 결과/실행 명령은 전체 실행 JSON에, 추가24/26/20은 v03a/v02a-regression.json·v02b-regression.json·v02c-regression.json에 있다. Chromium 캡처는 v03a/ui-regression·v02a-regression·v02b-regression·v02c-regression에 있다. 플랫폼은 Linux Python3.12.14/Node24.19.0/npm11.9.0/Chromium154다. 의존성 신규 설치는 없다.

## 6. 평가 자료와 인간 검토

7문서(6HWPX+1PDF 형식 대조)·57청크·40문항(응답36/보류4)을 재확인했다. 과거 runtime 경로는 현재 Linux에 없으며 현재 청크 세대와 EvidenceRef 재해결은 NOT_VERIFIED다. 48개의 procedure 출현을48개 독립 검증 그래프로 해석하지 않는다. 자료/정답은 변경하지 않았다.

8단어 제한 초과7문항은 travel-a-01, leave-a-01, purchase-a-01, meeting-a-01, form-a-01, travel-b-01, safety-04다. 원 질문은 보존하고 질문만으로 만든 별도 retrieval_query를 독립 검토하거나 검색 계약을 명시적으로 개정해야 한다. 조용한 잘라내기·제외·정답에서 검색어 만들기는 금지한다. 현재 검색 제한은 유지했다.

인간 검토 대상은40문항 정답/보류, 원문과 현재 EvidenceRef, 단계/행위자, 순서·분기·반려·반복, 기한/의무/조건/서식, 독립 holdout·무근거 주장 판정이다. [평가 준비 JSON](v03a/EVALUATION_READINESS.json)을 따른다. 현재 Fake 결과나 정답 자료를 AI 성능으로 보고하지 않는다.

## 7. Git

기준 v0.2-C 4716886ff8c974aec750fda0f73dbfbc2e4ff39d를 보존했다. 기존 분석3개를 로컬 커밋193e54d67c1cd85352ee779bc195ef3fac5668f7로 보존하고 feat/v03a-provider-safety를 생성했다. 현재 HEAD는 이 보존 커밋이며 이번 구현·문서·시험 증거는 미커밋 상태다. 원격 push/merge는 하지 않았다.

## 8. 남은 위험과 v0.3-B

후속 mock 기반 개발에 착수할 기반은 마련됐으나 실제 호출 준비 완료는 아니다. 실제 serializer/API 버전 호환성·고정 모델/가격·production tokenizer·키 관리·데이터 외부전송 독립 승인·실비 예산·불확실 청구 정산·worker/job 비용 통합은 별도 설계/승인이 필요하다. 현재 byte counter는 실제 토큰 수 추정이 아니며 SQLite 검증을 다중 호스트 보장으로 확대할 수 없다. 원장은 결과 replay를 저장하지 않고 중복을 차단한다. 의미 정확성·스크린 리더/native OS·실제 AI/인증/배포는 미검증이다. v0.3-B는 자동 시작하지 않는다.

## 9. 시간과 재현

현재 작업 약20분. 전체 suite·신규 suite 실행시간은 위 표 및 JSON에 기록했다. 설치 변경은0이다. [상세 계약](../docs/V03A_PROVIDER_SAFETY.md)의 신규 unittest와 기존 run_v01_checks.py, check_v02a_ui.cjs·check_v02b_ui.cjs·check_v02c_ui.cjs 실행으로 재현한다. 공개/합성 데이터와 명시적 로컬 모의 인증만 사용한다.
