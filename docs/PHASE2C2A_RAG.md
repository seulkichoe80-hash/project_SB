# Phase 2C-2A 로컬 RAG 계약

범위: FR-05/06/07/14/15/18·NFR-02/03/04/05/06/07, WEB-02/04/05/08의 로컬 계약 부분. 실제 의미검색·실제 모델 품질 및 전체 G1/G2 완료가 아니다.

## 구성과 사용

`apps.api.rag_adapters`에 EmbeddingAdapter/LLMAdapter/HybridSearch Protocol, EmbeddingSpec, Generation/Claim Pydantic 계약과 결정적 hash-character-v1·extractive 테스트 대역을 추가했다. SDK·네트워크 호출·새 의존성은 없다. `RAGService(chunks, DeterministicEmbedding(), ExtractiveTestLLM())`를 신뢰하는 로컬 하네스에서 명시 주입한다. Principal은 기존 서버 인증 경계에서만 생성한다. 테스트 대역은 운영 인증/실제 AI 연결 경로가 아니다.

서비스 메서드는 `index(principal)`(manager), `search(principal, query, limit=5, mode='keyword'|'vector'|'hybrid')`(reader/manager), `answer(principal,question)`다. 기존 HTTP 경로와 앱 진입점은 변경하지 않았다. 신규 공개 API·자동 인덱싱·장시간 HTTP background task는 제공하지 않는다. 실인증은 여전히 deny-all이다.

## 벡터와 세대

SQLite exact cosine을 로컬 비교 기준으로 사용한다. 별도 vector_generations/vector_items/vector_current 테이블을 RAG 서비스 생성 시 추가하며 기존 parsing/chunks schema를 변경하지 않는다. 인덱스 키는 기관·전체 EmbeddingSpec·정렬된 현재 청크 snapshot hash다. model/provider/dimension/normalization/metric/test_only를 기록하고 다른 spec 조회를 거부한다. 벡터 개수·차원·유한값·0 norm을 검증하고 L2 정규화한다.

기관의 현재 활성·등록 자료, 완료된 현재 파싱·청킹 세대만 snapshot에 포함한다. 임베딩 계산은 트랜잭션 밖에서 수행하고 원본·근거를 전후 재검사한다. 게시 직전 snapshot 재대조 후 항목과 현재 포인터를 한 SQLite 트랜잭션으로 기록한다. 실패/중단 시 부분 결과는 게시되지 않으며 재호출은 멱등이다. 이전 정상 세대는 보존한다. 새 model/spec으로 명시 재색인 후 전환하며 이전 spec으로 재색인하면 기존 세대를 재활성화할 수 있다.

이 단계는 최대20,000 청크의 오프라인 계약 기준이다. 영속 indexing Job/lease·대규모 배치·취소·자동 supervisor·원격 공급자 오류/예산 reservation 구현은 후속 범위다. 실모델 인덱싱을 HTTP 요청에서 실행하도록 확대하지 않는다. 벡터 조회는 O(N×dimension)이며 성능 합격을 주장하지 않는다.

## 검색과 응답 안전성

keyword는 기존 SQLite substring 검색, vector는 cosine 순위, hybrid는 동일 후보의 reciprocal rank fusion(k=60)이다. 한국어 형태소/BM25 의미검색과 동일하지 않다. 원본 EvidenceRef를 반환하고 기관·활성 버전·현재 세대·canonical payload·원본 hash·원문 앵커/quote를 서비스에서 다시 확인한다. 악성 검색 어댑터의 조작 text·다른 기관/버전·중복 후보는 거부한다.

LLM 응답은 candidate 또는 insufficient_evidence다. 모든 claim은 검색 문맥 안의 실제 chunk ID를 참조해야 하며 원문에 없는 생성 문장은 거부한다. 테스트 대역에는 보정된 의미 관련성 점수가 없으므로 응답 문맥은 키워드 지지가 있는 후보로 제한한다. 참조는 응답 직전 다시 검증한다. 결과는 generated_candidate/test_only/NOT_VERIFIED/not_official_guidance로 표시한다. 형식·앵커·문자열 포함 확인은 의미적 정답 검증이 아니다. 원문 내 지시를 실행하지 않으며 모델에 도구·파일·명령 실행 권한을 주지 않는다.

## 재현과 평가

```powershell
python -B -m unittest discover -s tests -p test_rag_contracts.py -v
python -B scripts/validation/run_phase2b_checks.py --output outputs/phase2c2a/VALIDATION_NEW_RUN.json
python -B scripts/validation/evaluate_phase2c2a.py --output outputs/phase2c2a/EVALUATION_NEW_RUN.json
```

기존 결과 파일은 덮어쓰지 않는다. 실제 명령은 outputs/PHASE2C2A_REPORT.md를 따른다. 골드셋 tests/fixtures/synthetic/rag-goldset.json은 합성2문서/13질의 개발 부분표본이며 원문 SHA·ID·기대 quote→chunk 연결은 평가 결과에 저장한다. 인간 독립 검토/holdout/대표 공개 corpus는 미완료다. 전체5문서·40질의·20캡처·10절차 목표를 축소하지 않는다. keyword/vector/hybrid의 Hit@5·Recall@5·MRR·기관 누출·정답 없음 후보를 같은 조건으로 비교한다. metric_fixture 결과를 실제 임베딩 평가로 사용하지 않는다.

기존 G1 B-02/03은 실제 모델·임베딩에 대해 미완료다. 후속 연결은 [사전 검토](LLM_API_PREFLIGHT.md)의 자료·모델·예산 승인과 별도 검증을 따른다.
