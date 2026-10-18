# 서무ITDA v0.3-C1 검색 실패 진단 및 고정 문맥 평가

검색 알고리즘·제품 API/DB·정답·기존40문항 인간 검토표를 변경하지 않고 검색 실패 원인과 고정 문맥 평가 경로를 분리했다. 실제 LLM·임베딩·Supabase 호출, 유료 API 지출, 외부 자료 전송·push·merge·배포는0회다. 의미 정확도·골드셋 승인 상태는 미검증이다.

## 1. v0.3-B 보존 및 변경 파일

기존 미커밋 변경을 원본/fixture/과거 증거·비밀정보 검사 후 로컬 커밋 **a3b8a35d2ed412497b85a6c2f61746b0f41af5a8**로 보존했다. 현재 feat/v03c1-retrieval-diagnostics를 생성했으며 HEAD는 이 보존 커밋이다. 이번 C1 변경은 미커밋 상태다.

신규 scripts/validation/retrieval_diagnostics.py(SQL/필터/토큰/Top-K), fixed_context_evaluation.py(정답 독립 문맥/Fake 경로), run_v03c1_diagnostics.py(CLI/검토 계획), tests/test_retrieval_diagnostics.py(신규37시험), docs/V03C1_RETRIEVAL_DIAGNOSTICS.md를 추가했다. ARCHITECTURE.md·TEST_PLAN.md·TASKS.md에는 관련 절만 추가했다. 실행 증거는 outputs/v03c1의 새 파일이다.

## 2. 40문항 원인 집계

| 주 분류 | 문항 수 | 실제 확인한 내용 |
|---|---:|---|
| DATA | 0 | 실제 저장 색인57행이 존재함 |
| SCOPE | 0 | A기관49/B기관8청크, 기관·등록·활성 버전·현재 job/세대·완료 parse attempt 필터가 정상 |
| TOKENIZATION | 36 | 답변 가능 문항의 모든 window에 eligible index 어디에도 literal 일치하지 않는 token이 존재해 AND 결과가0 |
| RETRIEVAL | 0 | 현재 positive 문항의 별도 Top-K/후단 손실은 확인되지 않음 |
| EVALUATION | 4 | 원래 abstain인 safety-01~04를 positive 검색 실패로 집계해서는 안 됨 |
| UNKNOWN | 0 | 40건 모두 진단 절차를 완료함 |

[40문항 표](v03c1/CAUSE_TABLE.md), [문항별 전체 SQL·token·필터·후보·ID·점수](v03c1/final-run/diagnostics.json)에 근거를 기록했다. 주 분류와 별도로 각 문항의 absent token·색인/범위 여부·expected refs·raw SQL 결과·Top-K 영향을 기록했다.

## 3. 확인 사실과 불확실성

기존7문서·57청크의 원본 SHA/파서/청커 replay를 확인한 현재 B 세대를 그대로 사용했다. 정답 근거48건은 현재 기관별 eligible index에 모두 존재하고 실제 원본에서 재해결됐다. 접근 금지3건을 다른 기관의 정답 후보로 편입하지 않았다. 색인 누락/세대 필터/정답 ID 매칭이 positive36건의0 hit를 만든 증거는 없다.

질의는 casefold 후 공백 분리한다. 예를 들어 travel-a-01에는 '안내의', '접수부터', '검토까지', '순서와', '준비자료를', '알려주세요.'가 해당 기관 색인 어디에도 그대로 일치하지 않는다. 각 window에 이런 token이 하나 이상 있으므로 AND SQL은 반드시0행이다. 날짜/버전/청크 순서 정렬이며 lexical relevance 점수는 없으므로 sql_score=null이다. window별50개 제한 전에도0행이라 최종 Top-K10이나 RRF가 원인은 아니다.

짧은 keyword '일정표'로 같은 색인에서 정답 근거가 실제 검색되고 RRF=1/61임을 별도 시험했다. token은 각각 있지만 동일 청크에 함께 없을 때 RETRIEVAL로 분류하는 진단도 시험했다. 잘못된 ref/ID는 EVALUATION으로 구분한다.

TOKENIZATION은 literal token/AND 경로에서 탈락한 사실을 뜻한다. 조사·구두점·본문/질문 어휘·의역이 각각 얼마나 기여하는지는 분리 실험 전 확정하지 않는다. UNKNOWN0은 이 세부 기여도까지 모두 설명했다는 뜻이 아니다. EVALUATION4건 역시 기존 scorer의 recall 산식/ID 매칭 버그4건이라는 뜻이 아니다. 기존 scorer는 expected가 없는 문항의 recall을null로 다뤘으며 '40문항 모두 검색 실패'라는 해석을36개 positive miss와4개 expected abstention으로 구분해야 한다.

## 4. 최소 검색 개선 제안

자료 준비/원본/정답/기관 필터 수정은 필요하지 않다. 이번 작업에서 제품 알고리즘이나 평가 질문도 수정하지 않았다. 다음 작은 개발 단위에서는 질문만으로 구두점 정규화·한국어 token 처리, lexical OR/BM25 등의 offline ablation을 각각 별도 프로토콜로 비교하도록 제안한다. 조사 무차별 삭제나 정답에서 검색어 만들기는 허용하지 않는다. 여러 단계의 근거가 여러 청크에 있는 경우 AND/단일 청크 단위 검색의 한계도 분리해야 한다.

임베딩이 필수라는 결론은 아직 입증하지 못했다. 실제 임베딩 비교는 모델·자료 반출·비용·토크나이저·평가 조건을 별도 검토/승인한 뒤 진행해야 한다.

## 5. 고정 문맥 Fake 실행

[전체 실행](v03c1/final-run/fixed-context.json), [요약](v03c1/final-run/summary.json)을 제공한다. 문맥은 정답 ID나 기대 refs를 보기 전에 frozen corpus의 기관별 전체 활성 문서로 선택한다. A기관6문서49청크/B기관1문서8청크이며 문서·원본 hash·snapshot·parse attempt·chunk job/세대·모든 청크를 context_id로 고정했다. question+context_id 입력과 gold refs/labels는 별도 구조다.

기존 DeterministicWorkflowAdapter·WorkflowDiscoveryEngine으로7문서를 Fake 추출하고40문항에 기관별 결과를 재사용했다. 검색 호출 없이 수행했고7문서 scope는 모두 complete다. 문맥 누락·hash 재계산 위조·타기관/위조 span·없는 근거·무근거 주장·옛 세대·새 활성본·등록 해제를 거부했다. 기존 기관·원문 무결성 검증을 우회하지 않았다.

Fake 후보는 A기관21단계/B기관6단계다. 같은 기관 문서 후보를 반복 평가하여 인용 출현735/735가 구조적으로 유효했다. 이는735개 고유 근거나735건 의미 검증을 뜻하지 않는다. 단계 exact-label 비교는 TP0/FP735/FN48, F1=0이었다. Fake가 질문에 맞는 업무/단계를 선택하는 모델이 아니고, 원문 전체 문장 label과 기존 짧은 정답 label을 엄격히 대조했기 때문이다. 이 점수를 실제 LLM 정확도0%나 골드셋 오류로 해석하지 않는다. 정답을 고쳐 점수를 맞추지도 않았다.

현재 경로는 문맥/추출/채점 연결의 오프라인 smoke다. 관계·기한·조건·서식 정답은 미주석 상태를 유지한다. 의미 정확도는null, semantic_accuracy_pass=false, goldset_status=PROVISIONAL, semantic_verification=NOT_VERIFIED, administrator_approval=NOT_REQUESTED, publishable=false다. 토큰/실모델 비용 성능은 측정하지 않았다.

## 6. 인간 검토 우선10문항

현재 진행률은 **0/40(0%)**, 미검토40건이다. 기존 검토표는 변경하지 않았고 도구가 인간 판정/검토자/검토일/이유를 만들지 않았다. [기존 검토표](v03b/isolated-evaluation/review.html), [진행률·미검토 목록·위치·우선순위](v03c1/final-run/human-review-plan.json)를 제공한다.

| 순서 | 문항 | 선정 이유 |
|---|---|---|
| 1 | travel-a-01 | 기본 다중 단계/다중 근거 |
| 2 | travel-b-01 | 같은 업무명의 기관별 차이·권한 |
| 3 | leave-a-01 | 다른 업무의 단계·역할 |
| 4 | purchase-a-01 | 구매 단계/서류 관계 |
| 5 | meeting-a-01 | 문서 단위 holdout 후보 검토 |
| 6 | form-a-01 | 서식명/목적/단계 관계 |
| 7 | travel-a-04 | 조건·보완·보류 |
| 8 | safety-01 | 무근거 기한 단정 금지 |
| 9 | safety-03 | 타기관 접근 차단 |
| 10 | safety-04 | 타기관/옛 자료 공개 지시 거부 |

선정 기준은6매뉴얼 대표·기관 대조·조건·근거 부족·안전성의 다양성이며 모델 점수에 따른 선별이 아니다. safety-02 금액/법령 보류, 나머지30문항, 완전 그래프/기한/조건/서식 정답 주석과 PDF 시각 검토는 다음 묶음이다. 검토 완료가 곧 실모델 의미 정확도 합격이라는 뜻도 아니다.

## 7. 테스트 및 회귀

신규37개 영향 시험 PASS(17.667초). 최종 전체 백엔드 **591 PASS / FAIL0 / SKIP0 / BLOCKED0**(기존554+신규37)를 새로 실행했다. 소요시간은143.515초다. [최종 집계](v03c1/final-validation.json), [백엔드](v03c1/backend-final.json), [네트워크 guard](v03c1/backend-final.network.json)를 보존했다. 별도 CLI도 비루프백 socket/DNS guard 안에서 실행하여 외부 시도0회·exit0을 확인했다. 초기/확장/최종 영향 시험은 각각33/35/37 PASS였으며 시험 생략/정답 수정은 없다.

이번 변경은 오프라인 scripts/tests/docs에 한정되어 제품/API/UI/DB/의존성/환경은 같다. UI174·타입/빌드는 B에서 실제 실행한 증거와 현재 소스 hash 일치를 확인해 재사용했다. 이번에 새 UI/빌드를 실행한 PASS로 보고하지 않는다. [재사용 근거](v03c1/UI_EVIDENCE_REUSE.json)를 따른다. 전체 WCAG/실기기·실인증/실모델·클라우드 배포는 이번 범위 밖이다.

## 8. Git·보존·보안

현재 feat/v03c1-retrieval-diagnostics / HEAD a3b8a35d2ed412497b85a6c2f61746b0f41af5a8이며 C1은 미커밋이다. main 수정/push/merge/배포는 없다. B 커밋은 기존 추적 정책에 맞는105파일을 보존했다. 기존 비추적 원본/runtime/corpus는 작업 공간에 유지하며 Git에 원본을 넣지 않는 정책도 바꾸지 않았다. 고정 원본·runtime이 없는 새 환경은 B 생성기로 새 manifest와DB를 함께 생성한 뒤 C1을 실행해야 하며 옛 UUID manifest에 새 DB만 붙여 사용하지 않는다.

기준 tracked766개 중 기존 문서3개에 새 절만 추가했고 나머지763개는 변하지 않았다. 원본·fixture·정답·검토표·과거 증거는 모두 보존했다. 원장/실공급자 설정/키/SDK/의존성 추가0건이다. [보존 hash](v03c1/PRESERVATION.json), [CLI 네트워크 guard](v03c1/cli.network.json)를 기록했다.

## 9. 실제 모델 시험 착수 조건

검색과 독립된 입력/출력/근거 검증 경로는 준비됐다. 실제 시험은 독립 인간 정답·의미 검토, 관계/기한/서식 주석·holdout, question+문맥/프롬프트·모델/context 길이·실 tokenizer 동결, 공급자 데이터 조건·자료 반출 범위·가격/예약/사용량 정산·명시적 호출/예산 승인 이후다. 고정 문맥 실험과 end-to-end 검색+추출 실험은 별도로 보고해야 한다. 이번 결과는 실모델 사용 승인이 아니다.

## 10. 실행·시간

실행 명령과 경계는 [계약](../docs/V03C1_RETRIEVAL_DIAGNOSTICS.md)에 기록했다. 최신 진단/고정 문맥/검토 계획은 final-run이며 최초 diagnostic-run도 보존했다. 신규 설치는 없다. 총 작업시간 약11.8분, 최종 진단/Fake CLI 42.862초다. 최종 시간/회귀 결과는 final-validation.json을 따른다. 이번 작업은 C1에서 종료하며 검색 개선·실모델 시험·다음 단계를 자동 시작하지 않았다.
