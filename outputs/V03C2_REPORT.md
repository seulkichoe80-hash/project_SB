# 서무ITDA v0.3-C2 한국어 검색 오프라인 비교

같은7문서·57청크·40문항에서 A literal AND/B정규화 AND/C점수 OR/D FTS5 BM25를 비교했다. 질문·정답·기관·문서 버전·청킹 세대·기존 제품 검색/API/DB는 바꾸지 않았다. 결과는 미승인 합성 골드셋의 lexical retrieval 실험이며 실제 AI 정확도/공식 절차 검증이 아니다. 실제 LLM·임베딩·Supabase·유료 API 지출·외부 자료 전송·배포는0회다.

## 1. Git 보존과 변경 파일

C1 미커밋 변경을 원본/fixture/정답/증거·비밀정보 검사 후 로컬 커밋 **137177b43c60d194da41678a550ad8b2b0ed62ad**로 보존했다. 현재 **feat/v03c2-retrieval-ablation**, HEAD는 이 보존 커밋이고 C2는 미커밋 상태다. main 수정·원격 push·merge·배포는 하지 않았다.

신규 scripts/validation/retrieval_ablation.py는 기관별 메모리 색인·4검색·격리·metric/latency 산식을, run_v03c2_ablation.py는3회 비교·재현성·결과/후보 선정을 제공한다. tests/test_retrieval_ablation.py에27개 시험, docs/V03C2_RETRIEVAL_ABLATION.md에 계약을 추가했다. ARCHITECTURE.md·TEST_PLAN.md·TASKS.md에 관련 절을 추가했고 새 증거는 outputs/v03c2다. 상세 파일/hash는 CHANGE_MANIFEST.json에 기록한다.

## 2. 입력·규칙과 통제

B isolated-evaluation의 원본 SHA·실제 parser/chunker57청크 replay를 확인했다. 문서·버전·기관·parse/chunk 세대와 현재 등록/활성 snapshot은 그대로다. 새 검색용 projection만 기관별 메모리 SQLite에 생성했으며 A49/B8청크다. 실제 원본/청크/제품 DB/FTS 설정은 수정하지 않았다.

첫 결과 확인 전 [PREREGISTRATION.json](v03c2/PREREGISTRATION.json)에 규칙을 고정했다. B/C/D의 정규화는 NFKC+casefold, Unicode P 구두점을 공백으로, 공백 축약이다. 조사/어미/stopword/동의어/업무명 규칙은 사용하지 않았다. 정답에서 질의를 만들지 않는다.

A는 기존 평가 window literal AND/RRF이며 실제 기존 adapter와40문항 및 양성 keyword에서 동등성을 확인했다. B는 같은 원문 검색 projection과 질의를 정규화하고 AND를 유지한다. C는 고유 token OR substring+일치 token 수 정렬, D는 quoted OR token+FTS5 BM25다. SQLite3.53.1에서 FTS5 지원을 실제 확인했다. D의 unicode61은 한국어 형태소 분석이 아니다.

3회 반복의 순서는 ABCD/BCDA/CDAB이며 순위·score fingerprint를 대조한다. MRR은 전체 반환 ranking(최대57) 기준이며 MRR@10도 별도 기록한다. Hit/Recall은36positive의 macro 평균이고4abstain을 섞지 않는다. 지연은 ranking과 원본/근거 검증 포함 end-to-end를 분리하며 index 생성 시간을 별도로 기록한다.

초기 run의 repeat별 공유 proof cache 초기화는 첫 후보를 찾은 방법에 validation 비용을 먼저 부담시켰다. 최종 run은 모든57개 proof를 index 생성 시 똑같이 준비하며, 매 질의 전후 fresh snapshot 재검증은 유지한다. 검색/score 규칙은 바꾸지 않았다. [LATENCY_CONTROL.json](v03c2/LATENCY_CONTROL.json)과 초기 결과를 보존하고 final fingerprint의 동일성을 검증한다. 최종 run은 자체 단위/전체 회귀가 끝난 뒤 단독 실행한다.

## 3. 36문항 품질 비교

아래는 [최종3회 실측 결과](v03c2/experiment-final/results.json)다. 3회 fingerprint와 초기 실험의 순위/점수가 모두 일치했고 입력/프로토콜 hash도 같았다. [비교·시간 표](v03c2/COMPARISON.md), [실패 사례 CSV](v03c2/FAILURES.csv)를 보존했다.

| 방법 | Hit@5 | Hit@10 | Recall@5 | Recall@10 | MRR | 무결과 |
|---|---:|---:|---:|---:|---:|---:|
| A 기존 AND | 0% | 0% | 0% | 0% | 0 | 36/36 |
| B 정규화 AND | 0% | 0% | 0% | 0% | 0 | 36/36 |
| C 점수 OR | 83.33% | 91.67% | 78.70% | 87.04% | 0.5787 | 0/36 |
| D FTS5/BM25 | 77.78% | 88.89% | 75.00% | 84.26% | 0.5809 | 0/36 |

C는 Top10에서33/36문항, D는32/36문항의 정답 근거를 하나 이상 찾았다. B의 구두점/공백 정규화만으로는 본문의 표현과 질의 사이의 literal AND 불일치를 해소하지 못했다. C/D의 후보가 있다는 사실은 답변이 맞다는 뜻이 아니다. 현재 C도 기존 Hit@5>=90% 및 제안 Recall@10>=95% 목표에 미달한다. 목표를 낮추거나 제품 합격으로 선언하지 않는다.

## 4. 실패 사례

C의 Top10 정답 미적중은 travel-a-04 / purchase-a-06 / meeting-a-05다. D는 이3건에 meeting-a-06이 추가된다. C의 완전 근거 Recall@10<1 문항은 travel-a-01, travel-a-04, purchase-a-01, purchase-a-06, meeting-a-01, meeting-a-05, form-a-01의7개다. D는 meeting-a-06을 포함한8개다. 정답/근거를 수정해 점수를 맞추지 않았다.

예를 들어 '출장 일정표를 빠뜨렸으면 어떻게 처리하나요?'의 정답 절은 '첨부자료가 빠진 경우 신청자에게 보완을 요청하고 검토를 보류한다.'다. '구매한 소모품을 받은 뒤 할 일'은 원문에서 '물품을 받으면 요청자가 수량과 상태를 확인하고 인수 내역을 기록한다.'로 표현된다. OR/BM25도 이런 어휘·표현 차이를 일반적으로 해결하지 못한다. meeting-a-06의 '회의'와 원문 '회의가'처럼 C substring과 D token 일치의 차이도 있다. 이는 새로운 규칙으로 즉석 보정하지 않고 후속 과제로 기록했다.

## 5. 보류4문항과 안전성

A/B는4건 모두 후보0, C/D는4건 모두 후보가 있었다. C의 후보 수는 safety-01~04 순서로5/1/19/7, D는4/1/2/7이었다. 다른 기관·forbidden evidence 적중은 모든 방법에서0건이다. FTS는 기관별 별도 색인이어서 BM25 빈도 통계도 섞이지 않는다.

모든40질의에서 답변 생성을 꺼 두었다. 후보가 있으면 CANDIDATE_CONTEXT_ONLY_NO_ANSWER, 없으면 INSUFFICIENT_RETRIEVAL_NO_ANSWER이며 NOT_VERIFIED/PROVISIONAL을 유지한다. 따라서 부족한 근거에서 기한·금액·의무 답변을 생성하지 않았다. 이것은 실모델의 의미적 보류 판별 능력을 검증한 결과가 아니다. 실제 모델이 후보 문맥을 과잉 해석하지 않는지는 별도 승인·인간 평가가 필요하다.

SQL 값은 binding하고 FTS MATCH token도 각각 quote한다. SQL/FTS operator injection·길이 제한·기관/role·위조 payload·등록 해제/세대 변경을 검사했다. 원본 재해결 proof와 매 query 전후 원문 재파싱/현재 snapshot 검증을 적용한다. 실제 외부 요청이나 임베딩은 없다.

## 6. 지연과 재현

최종 평균/p95 ranking, end-to-end, 방법별 누적 처리시간, index 생성 및 총 실행시간은 final-run 결과와 COMPARISON.md에 기록한다. 각 방법의 positive108개/negative12개 sample(질의×3회)을 모두 포함하며 빠른 run만 골라내지 않는다. 초기/최종 latency 조건은 구분한다.

메모리57청크라는 작은 corpus와 현재 Linux 워크스페이스의 시간이다. 원본 재파싱/검증이 ranking보다 큰 비중을 차지하므로 raw SQL 시간만으로 운영 응답성/확장성을 주장하지 않는다. 최종 실행은 자체 회귀 시험과 겹치지 않으며 그래도 운영/HTTP/실사용 p95 보장은 아니다.

## 7. 최적 후보와 제품 반영

사전 기준 Recall@10→MRR→ranking 지연 및 scope 안전성에 따라 **C를 다음 연구/시범 후보로 제안**한다. D는 MRR이 근소하게 높아 비교군으로 유지할 가치가 있다. 이 차이는36개 미검토 합성 질의의 결과이며 통계적 일반화·실제 업무 성능의 입증이 아니다. C도7건의 완전 근거 누락과 보류 질의의 과잉 후보가 남아 있다.

제품 검색을 자동 교체하지 않았다. 후속에는 독립 인간 검토·holdout과 더 큰 corpus에서 후보 다양성/잡음/검증 비용/질의 정규화를 비교해야 한다. 실제 임베딩/LLM이 필요한지와 효과는 이번 실험에서 입증하지 않았다.

## 8. 테스트·보존

신규27개 영향 시험은 PASS(38.949초). 전체 백엔드 **618 PASS / FAIL0 / SKIP0 / BLOCKED0**(기존591+신규27)를 새 실행했다. 183.790초가 걸렸으며 [전체 증거](v03c2/backend-final.json), [네트워크 guard](v03c2/backend-final.network.json), [최종 집계](v03c2/final-validation.json)를 보존했다. 기존 UI174·타입/빌드는 제품/UI/의존성/설정이 동일함을 hash로 대조해 이전 증거를 재사용했으며 이번 새 실행 PASS가 아니다. 새로 테스트하지 않은 실제 AI/실인증/배포·실기기/전체 접근성은 미검증이다.

원본·fixture·기존 정답/검토표·과거 증거는 보존했다. 기준 tracked793개 중 기존 문서3개에 새 절만 추가했고 나머지790개는 변경하지 않았다. [보존 hash](v03c2/PRESERVATION.json), UI_REUSE.json, 네트워크 guard/보안 점검을 별도 기록한다. 새 SDK/키/계정/의존성/제품 DB schema 변경은 없다.

## 9. 실제 모델 시험 준비도

자료/현재 근거·검색 비교·고정 문맥/지표 도구는 준비됐다. 다만 인간 검토40건은 여전히 대기하며, 실제 AI 정확도는 미측정이다. 독립 정답·의미 검토/관계·조건·기한·서식 주석·holdout, 모델/프롬프트/실 tokenizer·문맥 길이 동결, 데이터 처리조건·반출·실비 예산/정산·명시적 호출 승인이 필요하다. 검색 실험 점수로 이를 대체하지 않는다.

## 10. 재현·시간

[상세 계약과 명령](../docs/V03C2_RETRIEVAL_ABLATION.md)에 새 output 경로 실행법을 제공한다. 같은 manifest/DB/세대·질문·사전 규칙·SQLite tokenizer를 사용한다. 최종 검증은 전체 회귀 후 별도 socket/DNS guard에서 실행한다. 초기 결과도 보존한다. 총 작업시간 약11.8분, 최종3회 비교 64.900초, index/proof 준비 1.328초다. 상세 시간은 final-validation.json/COMPARISON.md를 따른다. C2에서 종료하며 후속 개발을 자동 시작하지 않는다.
