# v0.3-C2 한국어 검색 오프라인 비교

FR-06/19 및 NFR-02/03/04/05/06의 실험이다. 제품 ChunkService/RAGService/SQL/API/DB, 질문·정답·기관/문서/버전/청킹 세대, 인간 검토표는 변경하지 않는다. 실제 LLM·임베딩·Supabase·답변 생성·배포가 없다. 신규 의존성도 없다.

## 사전 고정 프로토콜

첫 실험 전 outputs/v03c2/PREREGISTRATION.json에 A~D, 정규화·분모·반복·tie break·선정 기준을 기록했다. source는 기존 B isolated-evaluation manifest+같은 ID의 runtime이다. 7문서57청크40문항 중 answerable36과 abstain4를 분리한다. 정답에서 질의를 만들거나 점수를 보고 규칙을 조정하지 않는다.

| 방법 | 질의/색인 처리 | 정렬 |
|---|---|---|
| A | 기존 casefold+공백 literal AND,8단어/200자 window당50건 | 기존 RRF60과 document/version/chunk key tie |
| B | NFKC+casefold, Unicode P 범주 구두점을 공백으로, 공백 축약; 동일 source search_text와 질의에 적용 | A와 같은 AND/window/RRF |
| C | B의 고유 token을 OR substring 검색 | 일치 고유 token 수 내림차순, 원본 행 순서 tie |
| D | B의 고유 token을 FTS5 unicode61 remove_diacritics0의 quoted OR로 검색 | SQLite BM25 오름차순, 원본 행 순서 tie |

조사/어미·stopword·동의어·도메인 업무명 규칙은 넣지 않는다. Unicode61은 한국어 형태소 분석기가 아니다. A는 C1에서 사용한 평가 window 경로이며 제품의 긴 질문 제한을 해제하는 변경이 아니다. B는 질의뿐 아니라 같은 filename/title/text/context 검색용 projection을 정규화한다. 원문/청크/EvidenceRef는 정규화하지 않는다. C는 부분 문자열, D는 token 일치라는 차이를 결과 해석에 포함한다.

## 실험 색인과 격리

scripts/validation/retrieval_ablation.py의 AblationSearch는 현재 FixedContextBuilder로 eligible corpus를 검증하고, 실제 제품 DB search_text를 새 메모리 SQLite로 복사한다. source DB/원본/제품 index에 FTS를 설치하거나 수정하지 않는다. source SQL의 날짜/버전/청크 순서를 ordinal로 고정한다. A의 결과는 기존 EvaluationQueryAdapter를40문항과 양성 keyword 시험에서 대조한다.

기관별 별도 connection/FTS index를 만들므로 문서뿐 아니라 BM25 문서빈도 통계도 섞지 않는다. 현재 A49/B8청크다. FTS 지원이 없으면 D=BLOCKED이며 다른 검색으로 몰래 대체하지 않는다. 이번 환경은 SQLite3.53.1/FTS5 지원을 실제 확인했다.

모든 질의는 기존 길이 envelope(2000자/128단어·단어200자)를 먼저 검사하고 normalized4000자/128token 한도를 적용한다. C의 SQL token/LIKE pattern과 D의 MATCH 문자열 모두 bound parameter다. D는 token 각각을 따옴표로 감싸 FTS operator도 literal로 취급한다. 임의 SQL/테이블명/정렬 코드는 입력받지 않는다. role은 trusted Principal의 reader/manager만 허용한다.

source 원본/parse/chunk generation·기관·활성 snapshot을 query 전후 재파싱/재구성해 확인한다. 결과 payload는 해당 packet과 정확히 대조하고 원본 재해결 proof를 사용한다. 등록 해제/버전/세대 변경 시 오래된 index는 실패한다. text/근거 위조, 타기관 결과를 반환하지 않는다. 실제 product factory·인증/CSRF 계약은 변경하지 않는다.

## 점수와 지연

각 positive 질의의 고유 (document_id,version_id,chunk_id)를 정답 집합으로 삼는다. Hit@5/10은 정답1개 이상 적중 여부, Recall@5/10은 필수 근거 중 적중 비율의36문항 macro 평균, MRR은 전체 반환 ranking(최대57)에서 첫 정답 역순위의 평균이다. MRR@10도 별도 기록한다. 잘못된 gold/중복 ranking은 실패하며 미적중을 조용히 제외하지 않는다.

abstain4는 positive 분모에서 제외하고 검색 후보 유무·forbidden refs/기관 누출·답변 미생성을 별도로 기록한다. 후보가 있다는 사실만으로 안전성 실패라 하지 않는다. 모든 질의에 대해 결과는 원문 candidate context이며 답변/주장 생성은 비활성이다. 이 정책을 의미적 보류 판별 능력으로 해석하지 않는다.

고정된 순서로3회 반복하되 method 순서를 ABCD/BCDA/CDAB로 회전한다. ranking/score fingerprint가 같아야 한다. query 순서는 원본 그대로다. latency는 positive108개·negative12개 sample을 각각 ranking SQL/RRF 시간과 source/근거 검증을 포함한 end-to-end로 구분한다. 평균·p50·nearest-rank p95·총합을 기록한다. index 생성/원본 proof priming은 제외하고 별도 보고한다.

최초 run에서는 repeat마다 공유 proof cache를 지워 첫 후보를 반환하는 방법이 validation 비용을 먼저 부담했다. 검색/점수 규칙을 바꾸지 않고 final run에서는 index 생성 시57개 proof를 모두 준비해 모든 방법에 같은 조건을 준다. query 전후의 fresh snapshot 재검증은 계속 수행한다. 초기 결과·LATENCY_CONTROL.json을 보존하며 final fingerprint가 initial과 같음을 검사한다. 최종 benchmark는 자체 전체 회귀/단위시험 종료 후 별도로 실행하여 겹치지 않는다. 그럼에도 작은 합성 메모리 corpus의 시간이며 운영/대규모/HTTP p95 보장이 아니다.

## 안전·의미 상태와 선택

PROVISIONAL, NOT_VERIFIED, human_review_pending40을 유지한다. 자동 lexical 점수는 의미 정확성·업무 승인·실 AI 성능이 아니다. 이번 source/gold는 독립 인간 검토 전 합성 개발 표본으로 holdout/공개 실제 corpus를 대체하지 않는다. 기존 정량 합격 목표는 낮추지 않는다.

연구 후보는 scope/근거 안전성이 통과한 방법 중 Recall@10, MRR, ranking 평균 지연 순으로 제안한다. 이 선정은 제품 교체 승인이나 통계적 일반화 입증이 아니다. 실패 문항·완전한 근거 누락·보류 안전성·검증 비용을 함께 보고한다. 형태소/의미 검색은 별도 후속 요청으로만 다룬다.

## 실행

```bash
.venv/bin/python -B scripts/validation/run_v03c2_ablation.py \
  --generation-dir outputs/v03b/isolated-evaluation \
  --output-dir outputs/v03c2/new-run
.venv/bin/python -B -m unittest discover -s tests -p 'test_retrieval_ablation.py'
```

current generation과 일치하는 runtime이 없으면 자동 빈 DB를 만들지 않는다. B 재현기로 새 manifest/runtime을 함께 생성하고 그 세대로 별도 실험해야 한다. 출력은 새 경로만 허용한다. [완료 보고](../outputs/V03C2_REPORT.md)에 이번 결과와 재현 hash를 기록한다. 실제 호출·유료 사용·제품 반영·push/merge/배포는 수행하지 않는다.
