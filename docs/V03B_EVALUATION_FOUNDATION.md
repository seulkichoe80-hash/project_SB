# v0.3-B 오프라인 평가 기반

FR-05/06/19, NFR-02/03/04/05/06의 평가 자료 재현·측정 도구 범위다. 제품 검색/API/DB/LLM adapter·비용 원장 계약은 변경하지 않는다. 실제 공급자 호출·외부 자료 전송·공식 승인·배포 기능은 없다.

## 재현 및 세대

scripts/validation/evaluation_fixtures.py는 기존 build_phase2c2b_goldset.py를 독립 Python 프로세스에서 실행한다. 다른 시험의 전역 XML namespace 등록이 ZIP 원본 바이트를 바꾸지 않도록 격리하며 상속 네트워크 guard는 유지한다. 실제 DocumentService/ParsingService worker/ChunkService를 재사용한다. 원본 sources JSON·기존 GOLDSET_REVIEW.json의 40문항/정답/절·단계/보류 조건을 대조하고 다르면 실패한다. 기존 자료를 고치거나 과거 UUID를 활성 DB에 복사하지 않는다.

새 경로에 HWPX6·PDF1의 원본을 재생성하고 SHA-256, 기관, 신규 document/version, parse job/attempt, chunk job/generation/config 및 WorkflowInputSnapshot을 고정한다. corpus의 합성 파생 원본과 parsed-originals.json을 보존한다. 원본을 현재 새 버전 ID로 다시 파싱·청킹해 canonical 전체 equality를 검증한다. 과거 ID로도 순수 재파싱해 역사적 청크와 정확히 대조한다. 새 세대 ID 비교 시 UUID에 의존하는 block/chunk/table/cell ID만 제외한 내용·위치 비교도 별도 기록한다. 새 DB에서 세대 번호1인 것은 과거 작업과 같은 세대라는 뜻이 아니다.

EvidenceRef는 절→현재 청크를 고유 매핑하고 실제 원본에서 재해결한다. 정답 근거와 타기관 접근 금지 검증용 근거를 분리한다. 금지 근거의 구조 재현 성공은 질문 사용자에게 접근 권한을 부여하지 않는다. LiveEvidenceResolver는 매번 현재 활성 문서·기관·원본·snapshot을 검사하며 옛 버전·세대·등록 해제를 거부한다. 매핑/인용 불일치가 생기면 임의 보정하지 않고 실행을 중단하여 부분 증거를 보존한다. 생성 단계에서 미해결 근거를 승인 자료로 내보내지 않는다. scorer에서는 미해결 gold를 DATA_INVALID로 분리한다.

## 긴 질문 평가 어댑터

제품 제한은 RAGService.search의 200자/8단어와 ChunkService.search의 200자/8단어 AND 검색이다. 이번에는 제품 계약을 유지한다. EvaluationQueryAdapter는 원 질문을 유지하고 question-only 연속 window(8단어/200자)를 모두 검색한 후 RRF로 합친다. 전체128단어/2000자, 단어200자, 결과20개까지 제한한다. 검색 결과를 기존 권한 검사와 live resolver로 다시 검증한다. 중복/위조·타기관·옛 세대 결과는 전부 실패한다. 질문이나 문서 지시를 실행하지 않는다.

전체 질문 AND와 window 합집합은 서로 다른 검색 프로토콜이다. 접속어·조사·권한 우회 문구를 임의 제거하거나 정답에서 검색어를 얻지 않는다. 품질 향상을 보장하지 않는다. 전체 질문과 windows·protocol version·no_hits/retrieval_failed·지연을 기록한다. 검색 실패/미검색을 AI 추론 오류로 채점하지 않는다. 제품 장문 질의 지원은 추후 별도 요구와 회귀 후 판단한다.

## 평가 계약

scripts/validation/evaluation_metrics.py는 strict GoldCase/Prediction/Labels/Item/Relation/HumanReview를 사용한다. 새 필드·중복 객체/관계·없는 노드 참조·비유한 수/출처 없는 usage/불일치 비용을 거부한다. 정답은 미승인 sidecar로만 다루며 모델이 human_review/semantic_verification을 설정할 수 없다. scorer는 schema 오류를 INVALID_OUTPUT, 잘못된 정답/근거를 DATA_INVALID, 미제출을 NOT_RUN, 검색/생성 오류를 별도 집계한다. 잘못된 입력을 조용히 누락하지 않는다.

| 자동 지표 | 계산/제한 |
|---|---|
| 단계·기한·조건·서식 | NFKC+공백 정규화 exact-label 집합의 TP/FP/FN, precision/recall/F1 |
| 순서·분기/반려/보완/반복 | 노드 label+방향+관계형 집합의 PRF와 exact-set accuracy |
| EvidenceRef | 실제 원문 재해결 유효 인용/전체 제출 인용, 인용 없는 항목 수 별도 |
| 무근거 주장 대리 지표 | 유효한 primary 원문 quote에 exact 포함되지 않은 주장/전체 주장; 의미 entailment 아님 |
| 시간·토큰·비용 | 개별 elapsed, NOT_MEASURED/FAKE_USAGE/PROVIDER_USAGE 출처 분리, versioned rate의 정수 microUSD 추정 |

일치 텍스트가 의미적으로 올바르다는 보장은 없다. 분모가0이면 null이며 정답 주석이 없으면 NOT_ANNOTATED다. micro 집계와 주석/제외 문항 수를 함께 출력한다. 부분정확을 정확으로 계산하지 않는다. 실제 billing이 아닌 비용 추정은 `ceil((input_tokens*input_rate_micro + output_tokens*output_rate_micro)/1,000,000)`이며 rate는 백만 token당 microUSD다. 토큰을 측정하지 않았으면 비용도 만들지 않는다.

현재 골드셋은 미승인 expected_procedure의 단계 출현48개만 초안 label로 전환한다. 기존 절차 배열을 참조 정보로 보여주되 완전한 순서·분기 그래프/기한/조건/서식 정답은 독립 주석 전 NOT_ANNOTATED다. 현재 도구로 해당 지표를 계산할 수 있지만 실제40문항의 해당 정확도는 미측정이다. metric-calibration.json은 정답 초안을 복사해 산식을 검사한 fixture이며 모델 응답/AI 점수가 아니다. no-inference-score.json은40개 모두 NOT_RUN이다.

## 독립 인간 검토

review.html, review-rows.json, review-sheet.csv는40문항을 원 질문·기존 정답·보류 기준·원문 발췌·전체 구조화 원문/합성 원본·버전/hash/위치와 함께 제공한다. 정확/부분정확/오답/판정불가, reviewer/reviewed_at/reason을 별도 사본에 작성한다. 초기 값은 모두 비어 있으며 자동 판정/승인은 없다. 시간대와 이유가 없는 검토 기록은 거부한다.

scorer는 제출된 인간 검토만 별도 human 집계한다. 식별자의 실제 소유자·독립성·검토 진실성은 도구가 인증하지 않는다. review 입력으로도 goldset_approved를 자동 true로 만들지 않는다. 예상답의 검토와 실제 모델 응답의 의미 검토를 별도 파일/버전으로 운영해야 한다. 개인정보 대신 기관에서 승인한 검토자 식별자를 사용한다.

## 실행

프로젝트 루트의 기존 .venv에서 실행하며 설치 변경은 없다. 출력·DB는 반드시 새 경로다.

```bash
.venv/bin/python -B scripts/validation/run_v03b_evaluation.py \
  --data-dir work/v03b/new-runtime --output-dir outputs/v03b/new-generation
.venv/bin/python -B scripts/validation/score_v03b_predictions.py \
  --generation-dir outputs/v03b/new-generation \
  --predictions outputs/v03b/new-generation/predictions-empty.json \
  --output outputs/v03b/new-score.json
.venv/bin/python -B -m unittest discover -s tests -p 'test_evaluation_foundation.py'
```

scorer는 prediction JSON 배열과 선택적 --labels(40개 GoldCase 배열), --human-reviews(HumanReview 배열), --data-dir(해당 generation과 같은 고정 ID의 DB)를 받는다. 중복 JSON 키·NaN·64MiB 초과를 거부한다. 새 DB로 자료를 재생성하면 새 generation/근거를 함께 사용해야 하며 옛 manifest에 DB경로만 바꿔 쓰지 않는다. 정답/검토 파일은 모델 입력이 아니다. inference 실행기는 포함하지 않는다. [이번 결과](../outputs/V03B_REPORT.md)를 따른다.

인간 검토를 scorer에 전달할 때는 검토표 전체를 모델 출력으로 넣지 않고 완료된 기록만 별도 배열로 추린다. 각 항목은 query_id, reviewer, reviewed_at(ISO8601+시간대), verdict(정확/부분정확/오답/판정불가), reason과 선택적 supported_claims/unsupported_claims다. 미완료 행은 제출하지 않는다. 이 제출 자체가 독립성 인증이나 골드셋 승인은 아니다.
