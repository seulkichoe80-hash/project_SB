# v0.3-C1 검색 진단·고정 문맥 평가

FR-05/06/19 및 NFR-02/03/04/05/06의 오프라인 진단 범위다. 제품 검색 SQL/전처리/API/DB·정답·기존 검토표를 변경하지 않는다. 실제 모델·임베딩·Supabase·지출·배포는 없다. [B 평가 계약](V03B_EVALUATION_FOUNDATION.md)을 유지한다.

## 실제 검색 진단

scripts/validation/retrieval_diagnostics.py는 현재 평가 DB를 읽는다. 기관/등록/활성 버전/현재 chunk job/완료/parse attempt 필터를 순서대로 집계하고, 실제 저장된 document/version/job/generation/chunk ID를 기록한다. 정답 근거의 eligible index 존재와 실제 원본 재해결을 독립 확인한다.

그 후 기존 ChunkQueries.search로 각 질문 window와 각 token의 LIKE 결과를 측정한다. 진단용 단일 token 조회는 원인을 확인하는 probe이며 제품 결과나 평가 문맥을 만드는 검색 개선으로 사용하지 않는다. 기존 service의 search_adapter를 일시적으로 기록 wrapper로 감싸 실제 실행 SQL/반환 순서/limit를 수집하고 finally에서 복구한다. 원문·키가 포함될 수 있는 운영 환경용 로거가 아니며 공개 합성 자료 전용 CLI다.

SQL은 casefold+공백 분리 token을 AND하는 literal LIKE이며 BM25 점수가 없다. 따라서 sql_score=null과 결정적 날짜/버전/청크 순서를 표시한다. window별50개 제한 이전/이후 후보·정답 ID, 최종 Top-K·RRF 점수·정확한 ID tuple 매칭을 분리한다. 8단어 split/200자 제한도 바꾸지 않는다.

분류는 다음 증거 우선순위다.

- DATA: 저장된 chunk index가 비어 있음.
- SCOPE: frozen corpus의 기관별 chunk 수와 현재 필터 통과 수가 달라짐.
- EVALUATION: 정답 근거가 잘못되거나 현재 범위와 불일치. 또는 원래 abstain인 문항을 positive retrieval miss로 표현한 경우. 실제 검색 성공 사례도 더 이상 검색 실패가 아님을 표시한다.
- TOKENIZATION: 모든 window에 eligible index 어느 곳에도 literal 일치하지 않는 token이 있어 AND 결과가 반드시 비게 됨.
- RETRIEVAL: token은 각각 있으나 한 청크에 공존하지 않음, 또는 정답이 최종 Top-K에서 사라짐.
- UNKNOWN: 제한/예외 등으로 진단을 완료하지 못했거나 증거가 충분하지 않음.

분류는 일반적인 한국어 형태소 원인의 증명이 아니다. 조사·구두점·어휘 차이·질문/본문의 표현 차이가 각각 얼마나 기여하는지는 별도 ablation 전 불확실하다. abstain4건의 EVALUATION은 기존 scorer의 recall 산식/ID 매칭 버그4건이라는 뜻이 아니다. 기대 근거가 없는 문항의 실패 집계 정의를 구분한다.

## 고정 문맥 경계

scripts/validation/fixed_context_evaluation.py의 FixedContextBuilder는 질문/정답 ID를 입력받지 않고 frozen generation의 해당 기관 전체 활성 문서·청크를 선택한다. A기관49청크/6문서, B기관8청크/1문서다. 정답 청크는 문맥 결정 후 별도 평가용으로만 확인한다. generation_id/snapshot_id·원본 SHA·parse/chunk job/세대/모든 청크와 context_id를 고정한다.

packet은 원문 청크·문서 범위·PROVISIONAL/NOT_VERIFIED/NOT_REQUESTED를 포함한다. build/validate는 현재 snapshot/기관/활성을 재확인한다. 청크나 문서를 뺀 후 hash를 다시 만들어도 canonical 전체 packet 대조에서 실패한다. 예측 근거는 packet의 정확한 EvidenceRef와 같아야 하고 원본을 재해결하며 주장 text는 primary quote에 포함돼야 한다. 원문 포함은 의미 정확성 인증이 아니다. 등록 해제·새 활성본·새 청킹 세대는 기존 packet을 거부한다.

FakeFixedExtraction은 기존 DeterministicWorkflowAdapter와 WorkflowDiscoveryEngine을 재사용한다. retrieval·정답·기대 refs 없이 기관별 전체 문서 후보를 추출한다. 이 Fake는 질문 답변 모델이 아니며 질문별 업무 선택·추론/일반화를 하지 않는다. 기관별 후보를 재사용하므로40문항 평가 경로는7문서 Fake 실행이며40번의 LLM 호출이 아니다. case_inputs에는 question_id/question/organization_id/context_id/instruction_version만 넣어 후속 질문+고정 문맥 입력과 평가 정답을 분리한다. 현재 Fake는 이 질문에 응답하는 구현이 아니다.

예측은 existing Prediction 스키마로 채점하되 검색 지표와 분리한다. labels는 rule-based 원문 후보이므로 기존 짧은 정답 label과 exact-match가0이어도 실제 모델 의미 정확도0%로 해석하지 않는다. 인용 비율은 반복된 인용 출현 기준이며 unique 근거나 인간 검토 수로 부풀리지 않는다. 미주석 관계/기한/조건/서식은 NOT_ANNOTATED, 의미 정확도는 null, semantic_accuracy_pass=false, publishable=false다. 실제 호출·토큰·비용 성능은 측정하지 않는다.

## 사람 검토

기존 B의 review.html/JSON/CSV는 읽기 전용으로 유지한다. run_v03c1_diagnostics.py는 형식상 유효한 reviewer/date/verdict/reason이 있는 기록만 진행률에 반영한다. 불완전/잘못된 기록은 대기하며 도구가 인간 신원·독립성·검토 진실성을 인증하지 않는다. 인간 판정은 생성하지 않는다.

우선10문항은6개 매뉴얼의 다중 단계/기관 대조, 조건·보완, 무근거 기한, 타기관 접근/프롬프트 지시를 고루 확인하도록 선정한다. 점수가 낮은 문항만 골라 정답을 바꾸는 절차가 아니다. 상세 순서·위치는 human-review-plan.json에 기록한다. 금액/법령 보류 safety-02와 나머지30문항, 완전 그래프/기한/서식 정답 주석은 다음 검토 묶음으로 남긴다.

## 실행과 최소 후속 제안

현재 generation과 같은 ID의 metadata.sqlite3 및 불변 원본이 필요하다. DB가 없으면 자동 빈 DB를 만들지 않고 실패한다. 다른 환경에서 B 생성기를 실행했다면 새 manifest+DB를 함께 선택한다. 출력은 새 경로만 허용한다.

```bash
.venv/bin/python -B scripts/validation/run_v03c1_diagnostics.py \
  --generation-dir outputs/v03b/isolated-evaluation \
  --output-dir outputs/v03c1/new-run
.venv/bin/python -B -m unittest discover -s tests -p 'test_retrieval_diagnostics.py'
```

색인 누락이나 ID 매칭 오류가 확인되지 않았으므로 자료/정답/제품 코드를 고칠 이유는 없다. 다음 승인 범위에서는 질문만을 이용한 구두점/한국어 token 처리와 lexical OR/BM25 등의 작은 offline ablation을 개별 프로토콜로 비교할 수 있다. 조사 무차별 제거·정답 기반 질의 rewrite는 금지한다. 여러 단계의 근거가 여러 청크에 있는 경우 AND/청크 단위 결합의 한계도 구분해야 한다. 임베딩이 필요하다는 결론은 아직 증명하지 못했으며 실제 임베딩은 별도 비용/보안/자료 승인 후다.

실모델 시험 전 독립 정답/의미 검토, 완전 주석과 holdout, 고정 문맥의 길이/실 tokenizer·모델/context 정책·프롬프트 동결·데이터 처리조건·실비 예약/사용량·명시적 예산 승인이 필요하다. [이번 실행 결과](../outputs/V03C1_REPORT.md)를 따른다.
