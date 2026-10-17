# Phase 2C-2B 실제 AI 시험 승인 계획

상태: 사전검증/실행계획. **외부 모델 호출·SDK 설치·자원 생성·배포는 실행하지 않았다.** 기존 설정·기술 채택은 변경하지 않았다. 기존123 PASS는 과거 실행이며 이번 결과가 아니다. 이번 문서·새 합성 자료의 구조 검증은 Feature Gate 범위이며 전체 Phase/B-02/B-03 완료 선언이 아니다.

## 모델 제안과 공식 근거 (2026-10-17 확인)

| 역할 | 제안 | 선정 근거·제약 |
|---|---|---|
| LLM 1 | gpt-6-luna | 고빈도 작업용 저비용 모델, Structured Outputs 지원. 한국어 행정 정확성·계정 접근은 미검증 |
| LLM 2 | gemini-3.1-flash-lite | 공식 개별 모델 문서의 Stable 모델, 구조화 출력·저비용·다른 공급자 비교. 종합 가이드의 preview 문구와 차이가 있어 개별 모델 카드·deprecations를 우선 확인하고 실행 직전 재확인 |
| 기본 임베딩 후보 | text-embedding-3-small,1536차원,L2/cosine | 다국어 검색 실험의 저비용 기준. 한국어 성능이 입증됐다는 뜻은 아님 |
| 임베딩 비교 후보 | gemini-embedding-2,768차원,L2/cosine | 100개 이상 언어의 멀티모달 공간. 이번은 텍스트만 사용. 모델별 전체 재색인·별도 세대·query/document 입력 지시 고정 |
| 후속 로컬 후보 | BAAI/bge-m3 | 공식 모델 카드의 100개 이상 언어·긴 입력 지원. 다운로드·설치·한국어 품질·자원 실측은 미실행. 이번 유료 호출 예산에는 포함하지 않음 |

Deprecated인 gpt-4.1-mini는 기본 추천에서 제외한다. 기존 docs/LLM_API_PREFLIGHT.md 및 과거 ARCHITECTURE의 후보 기록·런타임 기본 설정은 수정하지 않는다. gemini-embedding-001은 공식 종료 예정/교체 권고를 확인했으므로 새 기본 추천은 embedding-2다. 원 공급자 실패 시 자동 외부 fallback을 하지 않는다.

공식 출처:
- [GPT-6 Luna 지원·가격](https://developers.openai.com/api/docs/models/gpt-6-luna): 입력 $0.10/출력 $0.50 per 1M, cache write $0.125. 공식 모델명 그대로 사용하고 응답 model 필드를 기록한다.
- [Gemini 개별 모델](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite), [가격](https://ai.google.dev/gemini-api/docs/pricing), [종료 일정](https://ai.google.dev/gemini-api/docs/deprecations): 텍스트 입력 $0.25/출력(생각토큰 포함) $1.50 per 1M. 종료일 미발표를 영구 지원으로 해석하지 않는다.
- [OpenAI 임베딩](https://developers.openai.com/api/docs/guides/embeddings), [모델·단가](https://developers.openai.com/api/docs/models/text-embedding-3-small): 기본1536차원, $0.02 per 1M 입력.
- [Gemini 임베딩](https://ai.google.dev/gemini-api/docs/embeddings), [단가](https://ai.google.dev/gemini-api/docs/pricing): embedding-2 텍스트 $0.20 per 1M. 같은 요청의 여러 입력이 합쳐질 수 있어 개별 Content/개별 embedContent로 청크별 벡터를 보장한다.
- [BGE-M3 제작자 카드](https://huggingface.co/BAAI/bge-m3). 벤치마크 설명을 이 프로젝트의 한국어 실측으로 사용하지 않는다.

## API 명세·보안 설정

OpenAI: HTTPS api.openai.com/v1/responses, Authorization Bearer를 서버에서만 주입한다. input, model, text.format의 strict JSON schema, max_output_tokens, store=false를 사용하며 tools는 비활성이다. [구조화 출력 가이드](https://developers.openai.com/api/docs/guides/structured-outputs)의 refusal/incomplete/출력 한도 처리도 구현해야 한다. 두 API-reference URL은 이번 도구에서 Internal Error여서 가이드와 모델 카드로 교차 확인했으며 필드별 실제 호환은 smoke 전 미검증이다. 임베딩은 /v1/embeddings의 input/model/dimensions/encoding_format을 사용한다.

Gemini: HTTPS generativelanguage.googleapis.com/v1beta/models/{model}:generateContent, x-goog-api-key 헤더, contents·generationConfig·maxOutputTokens를 사용한다. [REST 명세](https://ai.google.dev/api/generate-content)와 [현재 구조화 출력 가이드](https://ai.google.dev/gemini-api/docs/structured-output)는 schema 필드 전환을 포함하므로 responseFormat/responseJsonSchema/기존 responseSchema 중 승인 모델이 지원하는 경로를 SDK 버전 고정·mock 요청으로 먼저 검증한다. Deprecated 필드를 새 기본으로 고정하지 않는다. 임베딩은 :embedContent, 청크별 content·768차원, query/document 지시를 명시한다. 001의 task_type 설정을 embedding-2에 그대로 전송하지 않는다.

두 공급자 모두 schema 준수는 사실·원문 의미 일치의 보장이 아니다. 공급자 SDK/HTTP 응답 타입은 adapter 내부로 제한한다. timeout60초·동시성1·최대1회 재시도(429/일시5xx만), 401/403/404·잘못된 schema·단가/지원 변경·안전성 실패는 즉시 중단한다. 질문/원문/키를 일반 로그에 남기지 않고 query_id·model·지연·usage·USD·오류 코드만 기록한다. 원문/정답 비교 자료는 접근 제한된 합성 평가 증거로 분리한다.

[OpenAI 데이터 정책](https://developers.openai.com/api/docs/guides/your-data)과 [Gemini 약관](https://ai.google.dev/gemini-api/terms)의 학습 사용/보관/무료·유료 차이를 담당자가 승인한다. store=false가 모든 보관을 없앤다고 주장하지 않는다. 실제 내부 문서·개인정보·비밀자료는 모든 플랜에서 이번 자료 범위 밖이다.

## 골드셋과 검토

합성 행정 HWPX6종(A기관 출장·휴가·구매·회의실·서식, B기관 출장)+합성 PDF 형식 대조1종=7문서. 40질의(답변가능36·보류/기관차단4), 절차/정답/필수 인용·보류 조건을 원문 절 ID에 매핑한다. 최초6개 질문은 각 업무의 접수→서류→검토 다중 근거/순서를 요구한다. [정답·EvidenceRef](../outputs/phase2c2b/GOLDSET_REVIEW.json), [사람 검토표](../outputs/phase2c2b/ANSWER_REVIEW_SHEET.md), [합성 원문](../tests/fixtures/synthetic/phase2c2b-sources.json)을 함께 검토한다.

원문과 정답 초안은 Codex가 합성 작성했다. 시험 대상 외부 모델의 응답을 정답으로 복사하지 않았다. 자동 원문 재해결은 통과했지만 독립 인간의 의미 검토는 PENDING이다. 검토자·일시·수정 이유를 추가한 새 버전을 만든 후 source/문서 hash·EvidenceRef·질문·기대 단계·모델·설정을 동결한다. HWPX 한컴 시각 순서는 미검증이고 이 표본은 텍스트 RAG용이다. 공개 실제 행정자료는 이번에 추가하지 않았다. 독립 공개 corpus·20캡처·10개 완전 절차는 미완료이며 PRD 목표를 축소하지 않는다.

검토 전 제안 split: meeting-a/form-a를 문서 단위 holdout(12질의), 나머지를 개발/검토용으로 분리하고 같은 문서·버전·청크의 양쪽 누출을 금지한다. 아직 독립 holdout 확보/검토 완료로 표현하지 않는다. 모델에는 질문·허용된 원문 문맥만 전송하고 expected_answer/정답 EvidenceRef 목록은 보내지 않는다.

## 평가 기준

- 동일 기관·활성·등록/현재 세대·query snapshot에서 keyword/vector/hybrid를 비교한다. 기본 임베딩과 비교 임베딩의 색인을 따로 구축하고 차원/세대를 혼합하지 않는다. 모델별 query embedding은 캐시해 검색 방식 간 재사용한다.
- Recall@k = 질의별 검색된 고유 정답 근거/전체 필수 정답 근거의 평균(k=5,10). 다중 정답을 모두 세며 chunk→근거 절/원문 요소로 중복을 제거한다. 답변불가 질의는 분모에서 제외해 별도 집계한다. 기존 Hit@5>=90%는 유지한다. 추가 제안 목표 Recall@5>=90%, Recall@10>=95%는 사전 동결하고 실제 점수는 미측정이다.
- 인용 유효성 = 실제 기관/문서/버전/앵커/quote를 재해결한 인용/전체 인용, 목표100%. 다른 기관·비활성·가짜 근거1건이면 안전성 FAIL.
- 의미 정확성 = 원문이 실제 주장·조건·기한·순서를 뒷받침하는 인용 주장/전체 인용 주장. 기존95% 목표 유지. 독립 검토자가 모델명 비공개 상태로 entailment/partial/unsupported/contradiction을 라벨링하며 불일치는 별도 검토자가 조정한다. 부분 일치는 합격 분자에서 제외한다. 스키마/문자열 포함만으로 의미 PASS 금지.
- 근거 없는 주장 비율 = 지지 근거가 없는 사실 주장/전체 사실 주장. 목표0%, 특히 의무·기한·기관 누출은 한 건도 허용하지 않는다. 전체 보류는 coverage와 답변가능 질의의 과잉 보류로 따로 보고해 점수 회피를 막는다.
- 보류 적절성 = 보류해야 할4질의 중 근거 없음/권한 부족을 표시하고 내용 노출 없이 보류한 수/4. 목표4/4. 답변가능36개 중 불필요 보류 비율·정확 응답 coverage도 별도 기록한다.
- 모델별 3회 결과/최저 정확도와 모든 안전성 결과, 시작~완료 wall latency p50/p95·실패/재시도율·입출력/생각/캐시 토큰·실청구 기준 USD를 기록한다. 공급자 usage를 얻지 못하면 비용0이 아니라 UNKNOWN으로 중단한다.

## 호출수·예산 (실행하지 않은 상한 계산)

[예산 JSON](../outputs/phase2c2b/BUDGET_PROPOSAL.json)이 기계 판독 기준이다. 기본 RAG는 primary embedding의 고정 hybrid 문맥을 사용해 2 LLM×40질의×3회=240회, 공급자별 smoke1회씩 총242회다. 검색3방식 비교는 검색 단계에서 수행하고 LLM 호출을3배 늘리지 않는다. 3방식별 생성 전체 매트릭스가 필요하면 별도 범위/예산 승인을 받는다.

main 요청별 입력4096토큰(질문+system+schema+문맥 전체), 과금 출력/생각 합계2048토큰 이내. smoke 입력/출력128씩. 문서 임베딩은 최대128청크×512토큰, 질의40×256토큰, smoke32토큰/모델. OpenAI는 문서/질의 batch+smoke 최대3요청, Gemini는 합쳐진 벡터를 피하려고 개별 최대169요청(실제는 청크수+41)이다. 가격·token cap이 지원되는지 확인 불가하면 전송하지 않는다.

정상 상한 가정은 약 $0.68, 일시 오류를 요청당1회 재시도하고 OpenAI input/cache-write 차이를 보수적으로 더해도 약 $1.39다. **제안 승인 상한은 총 $2.00**, 신규 예약+확정 지출이$1.80을 넘으면 요청을 멈춘다. 공급자 콘솔의 월 예산은 정확한 실시간 차단으로 신뢰하지 않는다. 앱 측 사전 예약·원자적 차감·unknown/timeout 비용의 보수적 유지가 필요하다. 생각 토큰이 cap 외 추가 과금되거나 SDK 기본 재시도가 통제되지 않으면 계획을 중단·수정 승인한다. tax/환율·사용자 다른 작업의 계정 과금은 별도다.

## 환경과 승인 후 실행 순서

현재 Python3.12·기존 FastAPI/Pydantic/httpx 환경은 있다. OpenAI/google-genai/tiktoken은 미설치이고 이 프로세스의 API 키3개 변수는 미설정이다(값을 수집/기록하지 않음). 계정 권한·키 유효성·모델 접근·망 실제 호출은 NOT_VERIFIED다.

1. 검토자가 정답표·자료 반출 조건·모델 ID·총$2 예산·호출수/재시도 상한을 승인한다. 승인은 키를 채팅에 붙여넣으라는 뜻이 아니다.
2. 실제 adapter·공급자별 token counter/schema 매핑·승인/비용 reservation을 별도 변경으로 구현하고 lockfile·mock 오류/예산·기관/근거 회귀를 먼저 실행한다. 현재 RAGService는 real provider를 명시 거부한다. 이를 몰래 해제하지 않는다. 7개 자연어 질문은 기존8단어 검색 제한을 넘으므로 검색 질의 계약을 검토·회귀하고 조용히 질문을 잘라내지 않는다. 업무절차 출력 schema도 별도로 검증한다.
3. 키는 공급자 콘솔에서 별도 검증 프로젝트/최소권한 키로 만들고 백엔드 시크릿 또는 로컬 비추적 세션 환경으로 설정한다. Windows에서는 환경변수 UI/비공개 시크릿 주입을 사용하고 명령행·셸 history·Git·VITE_*에 실제 값을 적지 않는다. [Gemini 키 문서](https://ai.google.dev/gemini-api/docs/api-key)의 GOOGLE_API_KEY 우선순위에 유의해 중복 변수를 제거하거나 명시 주입한다. OpenAI ChatGPT 구독과 API 과금/프로젝트 권한을 혼동하지 않는다.
4. 승인 이후에만 계정 모델 목록/정확 모델 접근을 확인하고 schema smoke를 공급자별1회 실행한다. 키·원문을 로그에 남기지 않고 모델 접근 실패를 자동 대체 호출로 처리하지 않는다.
5. 2 임베딩의 corpus/query를 각각 생성·캐시하고 세대 전환/기관 필터/Recall@5·10을 평가한다. 한국어 품질이 낮으면 결과를 FAIL로 기록하고 holdout 정답을 튜닝용으로 누출하지 않는다.
6. 고정 문맥·프롬프트·질문 순서로 각 LLM3회 시험한다. timeout/429/invalid schema/refusal·근거 부족·충돌·교차기관 지시를 별도로 확인한다. 자동 tool 호출은 없다.
7. 독립 의미 검토 및 영향 안전성 회귀, 이 세부 Phase 완료를 선언할 경우 전체 회귀 후 보고한다. 실모델 합격을 이전123 PASS로 대신하지 않는다.

중단: 승인 없음, 키/모델 접근 실패, 원문/기관/활성 범위 누출, 위조 인용·무근거 의무/기한, 입력 초과, 지출 예약/usage 확인 불가, 연속3회 transient 오류, 총 HTTP1500회 또는 유료 시도828회 상한 초과, 자료 hash 변경, 의미 검토 미완료. 안전성 실패 시 확장·배포를 진행하지 않는다.
