# 서무ITDA v0.3 사전 점검

2026-10-18 KST. 이번 작업은 v0.2-C 보존과 정적 코드·기존 자료 검토/예산 산술이다. 실제 모델 연동·Supabase/LLM/임베딩 호출·새 평가 실행·API/DB 변경·SDK 설치·배포는 하지 않았다. 준비도는 **오프라인 구현 착수 가능 / 실제 호출은 선행 구현·인간 검토·사용자 승인 전 차단**이다.

## 1. 보존 커밋·Git

feat/v02c-mobile-ux의 미커밋88개 파일을 확인하고 비밀키 패턴 검출0 및 fixture/과거 증거 보존을 확인한 뒤 `4716886ff8c974aec750fda0f73dbfbc2e4ff39d`로 로컬 커밋했다. v0.2-A809a2dd와 v0.2-Be52ec2d도 이력에 유지한다. main 변경·원격 push·merge는 없다.

보존 커밋 후 작업 트리는 clean이었다. 이후 추가한 파일은 이 분석 보고서와 `v03-preflight/inspection.json`, `v03-preflight/cost-proposal.json`뿐이며 미커밋이다. 제품·API·DB·기존 문서/fixture/증거는 변경하지 않았다. 최종 해시 대조는 inspection.json에 기록한다.

## 2. 현재 구조와 실제 연결 지점

| 계층 | 실제 코드·현재 계약 | 연결 시 필요한 작업 |
|---|---|---|
|RAG 생성|[rag_adapters.py](../apps/api/rag_adapters.py) `LLMAdapter.generate(question, context) -> Generation(status, claims[text,chunk_ids])`|반환형 유지. 공급자별 HTTP/wire DTO를 어댑터 내부에서 변환|
|RAG 조합|[rag_service.py](../apps/api/rag_service.py) index/search/answer, lexical 지원 및 원문 포함 관계 검사|실제 대역은 생성자에서 거부. 승인된 평가 경로와 공통 근거 검증을 별도 설계해야 하며 test_only 위조 금지|
|임베딩|`EmbeddingAdapter.embed(texts)`·`EmbeddingSpec(provider,model,dimension,normalization,metric,test_only)`|실제 배치/길이/usage·오류/요금 처리. checked_vectors로 개수·차원·finite/비영벡터·L2 유지|
|검색|`SQLiteKeywordSearch` + [vector_repository.py](../apps/api/vector_repository.py) exact cosine/RRF, 기관별 활성 세대|spec/입력 해시가 바뀌면 별도 전체 재색인. 현재 HTTP `/search`는 키워드이며 실제 hybrid/RAG HTTP 연결이 아님|
|업무절차 출력|[workflow_contracts.py](../apps/api/workflow_contracts.py) `WorkflowExtractionAdapter.extract(snapshot) -> WorkflowExtraction`|RAG Generation과 별개. WorkflowCandidate/Step/Condition/Edge/FormRequirement/GroundedAssertion 유지|
|오프라인 엔진|[workflow_discovery.py](../apps/api/workflow_discovery.py)·[models](../apps/api/workflow_discovery_models.py)|test_only=True/network_access=False 강제, receipt/DiscoveryResult도 오프라인 계약. 공급자만 꽂아 동작하는 구조가 아님|
|작업/worker|[workflow_jobs.py](../apps/api/workflow_jobs.py), [worker](../apps/api/workflow_worker.py)|기본 adapter/worker는 결정적 오프라인. 실제 provider 오류 분류·모델/프롬프트/데이터 정책/요금 버전 fingerprint·usage/예산·재시작 비용 관리 필요|

Pydantic/JSON Schema는 추가 필드·중복 ID·잘못된 참조·관계와 한도를 검사한다. workflow 출력256KiB/총1000노드/업무20개/업무당 단계200개 등 상한이 있다. JSON Schema만으로 Python 그래프 validator의 모든 조건이 공급자에 전달되는 것은 아니며, 받은 결과를 로컬에서 다시 검증해야 한다. 기존 schema 파일을 덮어쓰지 않는다.

`DiscoverySettings.batch_size=32`는 현재 입력 순회 묶음이다. 실제 공급자용 token window/여러 호출/문서 간 병합/부분 실패 프로토콜은 아직 아니다. 실제 연결 때 전체 문서를 조용히 앞부분만 보내서는 안 된다.

### 실제 응답→업무 후보 권고 경로

`승인 manifest+현행 입력 스냅샷 → 최소 텍스트/허용 span 목록 → 공급자별 엄격 wire schema → 허용 ID 대조·원문 위치 복원 → parse_extraction → validate_extraction → WorkflowValidationEngine → 서식 검토 → 별도 평가 receipt`

초기에는 모델이 허용된 span ID를 선택하도록 하고 서버가 chunk/block/offset/quote를 canonical EvidenceCitation으로 복원하는 방식을 권고한다. 존재하지 않는 ID·모호한 span·중복/미처리 입력을 거부한다. 모델이 원본 SHA/기관/승인/검증 상태를 생성하거나 바꾸게 하지 않는다. 출력 전체 EvidenceRef를 신뢰하거나 비슷한 문장에 임의로 붙이는 fallback은 금지한다.

현재 validate_extraction은 주장이 인용 원문에 포함돼야 하며 RAG answer도 문맥 원문에 포함되지 않은 생성 주장을 거부한다. 따라서 첫 실험은 **원문 추출형**으로 제한한다. 자유 요약·재서술은 별도의 의미 검토/보류 정책과 후속 계약 검토 없이는 허용하지 않는다.

현재 WorkflowDiscoveryResult.test_only는 Literal[True]다. 실제 결과를 True로 위장해 저장하지 않는다. 최소 첫 개발은 기본 API/DB를 건드리지 않는 독립 평가 runner와 실제용 provenance receipt로 분리하고, 제품 worker/기존 영속 결과와 결합하는 단계는 버전 호환 설계를 별도 승인받는다. UI도 현재 ‘실제 AI 없는 오프라인’ 문구를 표시하므로 실제 결과를 이 화면에 그대로 넣으면 부정확하다.

## 3. 근거·격리·실패 처리

- WorkflowInputSnapshot은 기관/문서/버전, 원본 SHA-256, 파싱 시도, 청킹 job/세대/설정, 전체 chunk/block, coverage, 프롬프트 계약 버전과 digest를 고정한다.
- [workflow_snapshot.py](../apps/api/workflow_snapshot.py)는 원본을 재파싱하고 canonical chunk 전체를 다시 만들어 누락·중복·변조 및 현행성을 확인한다.
- [workflow_evidence.py](../apps/api/workflow_evidence.py)는 chunk/block 존재, original_text, 정확한 Unicode 범위·quote·chunk span 포함 관계를 검사한다. 기존 tenant/element 변환은 명시 매핑으로 보존한다.
- RAG/vector는 기관·등록·활성·현재 파싱/청킹 세대·원본 근거를 재검증하며, 업무 결과는 저장 직전/조회 때도 스냅샷·서식 카탈로그·원본을 확인한다. 기존 원자 저장·lease fencing을 유지한다.
- 현재 그래프/기한/의무/충돌 검증은 엄격 구조 및 보수적 규칙이다. 문자열·숫자 일치는 의미 정확성·업무 적법성의 인증이 아니다. NOT_VERIFIED/NOT_REQUESTED/publishable=False 유지.
- 현재 job은 lease120초·heartbeat·worker timeout 기본600초·최대3시도와 RETRYABLE/PERMANENT/STALE_INPUT 분류가 있다. 이는 유료 API timeout/429/5xx별 retry 정책이나 과금 통제의 구현을 의미하지 않는다. 원격 예외를 뭉뚱그린 기존 분류를 그대로 쓰면 일시 장애가 영구 실패가 되거나 과금 재시도가 증폭될 수 있다.
- 실제 전송은 connect/read/전체 timeout, 응답 byte 한도, 401/403/잘못된 schema/거부/refusal/불완전 출력·429/5xx를 정규화해야 한다. 기본 제안은 timeout60초·동시성1·총2회 물리 시도 이내, 429/일시5xx만 최대1회 backoff/Retry-After 재시도다. timeout은 과금 여부가 불명확하므로 자동 재전송하지 않고 보류/대사한다. SDK와 worker의 재시도가 곱해지지 않게 하나의 영속 시도 장부로 제한한다.

## 4. 골드셋·평가 준비도

[점검 JSON](v03-preflight/inspection.json), [기존40문항](phase2c2b/GOLDSET_REVIEW.json), [사람 검토표](phase2c2b/ANSWER_REVIEW_SHEET.md), [합성 원문](../tests/fixtures/synthetic/phase2c2b-sources.json)을 실제로 열어 확인했다.

- 큰 세트: 합성 HWPX6종+PDF 형식 대조1종,57청크,40질의=답변가능36/보류4. 답변가능은 A기관30/B기관6문항이다.
- 기존 작은 rag-goldset은2문서/13질의다. 이를40문항 실험 결과로 혼동하지 않는다.
- 40문항은 source 절·정답 초안·EvidenceRef·expected_procedure를 포함하지만 독립 인간 검토는 PENDING_INDEPENDENT_REVIEW다. expected_procedure48회 등장도48개의 독립·완전 검토 단계나 전체 그래프 정답을 의미하지 않는다.
- 6개 HWPX는 접수/서류/검토/보완/승인/종료 각6절이다. 대부분 답변형 텍스트 RAG 평가이며, 전체 그래프의 정확한 edge·조건 범위·기한/반려·반복·서식/등록 파일 관계 정답은 충분히 동결되지 않았다. PDF는 형식 대조이며 한국어 업무절차 의미 평가를 대체하지 못한다.
- 기존 RAG.search는200자/8단어 제한을 가진다. 40문항 중7개가8단어를 넘는다. 질문을 몰래 잘라내거나 제외해서 점수를 높이지 말고, 검색 질의와 원 질문의 분리/상한 계약을 먼저 검토한다. 이번에는 변경하지 않았다.
- 기존 JSON의 data_dir는 Windows 형식 `work\\phase2c2b\\goldset-runtime`이며, 해당 경로와 정규화한 Linux 경로 모두 현재 없다. 7개 original UUID 경로도 현재 찾을 수 없다. **원문 JSON/템플릿/생성기는 있으나 예전 런타임·UUID EvidenceRef를 지금 활성 문서로 재사용할 수 없다.** 평가 전 새 출력/DB 경로로 오프라인 재생성하고 원본 해시·내용·논리 절 ID→새 EvidenceRef를 다시 검증·동결해야 한다. 예전 원본 바이트가 복원됐다고 가정하지 않는다. 오늘 재생성은 하지 않았다.
- 독립 holdout은 확보·검토 완료가 아니다. 기존 meeting/form 문서 단위12질의 holdout 제안도 아직 제안이며 지금까지 개발자가 열어 본 세트를 ‘미지 데이터’라고 부를 수 없다. 새 독립 문서와 기관별 split을 동결해야 한다.

### 평가 지표 제안

인간이 문서/버전별 기대 업무·고유 단계·조건·타입 있는 간선·기한·서식·필수 인용을 먼저 라벨링하고, 개발/holdout을 문서 단위로 나눈다. 기존 절차10개 이상·질의40개·캡처20장 등 PRD 전체 목표는 축소하지 않는다. 누락 영역은 NOT_RUN으로 남긴다. 표의 새 보조 목표는 제안이며 인간 검토 후 사전 동결한다.

|지표|분모·계산 및 검토|기준|
|---|---|---|
|업무/단계 발견|기관·문서별1:1 대응한 TP/FP/FN, precision/recall/F1 및 업무별 macro|기존 단계 발견 recall85% 이상 유지; precision/F1도85% 제안|
|순서·분기·반려/반복|방향·관계 타입·조건까지 일치하는 edge P/R/F1, 관계별 분리 집계|기존 선후 관계85% 목표 유지; 분기/복귀 F1 85% 제안|
|기한·조건|수치/단위/기준 사건/적용 조건·근거를 인간 대조. null은 미확정으로 평가|근거 있는 주장 의미 정확도95%, 없는 기한을 생성하면 안전성FAIL|
|서식|언급·사용 목적·적용 단계/조건의 P/R/F1; 등록 서식 후보 Hit@3 별도|기존 추천 Top3 90% 유지. 실제 파일 존재와 필수성을 분리|
|근거|기관/버전/앵커/quote 유효 인용/전체 제안 인용 및 인간 entailment/partial/unsupported/contradiction|구조·연결100%, 의미95% 기존 목표 유지|
|무근거 주장|원시 모델의 unsupported/contradiction 주장÷전체 제안 주장; 검증 거부 전·후 각각 집계|무근거 의무·기한 확정/교차기관·구버전 노출0건. 관측0건을 일반적0위험으로 해석하지 않음|
|검색|고유 필수 근거 기준 Hit@5, Recall@5/10, MRR@5; 답변불가 false-positive 별도|기존 Hit@5≥90%; 추가Recall@5≥90/10≥95%는 사전 동결 제안|
|완전성·견고성|입력 처리율, 미처리 chunk 수, schema/refusal/timeout/근거 거부율|부분/실패를 제외하지 않고 전체 실행 분모에 기록|
|시간/비용|토큰·물리 시도·대기/서비스/전체 시간·p50/p95·USD를 모델/문서 크기/반복별 기록|실측 전 NOT_RUN. 상한 가정과 실제 usage 비용을 분리|

빈 출력/거부로 근거 정확도가 좋아 보이지 않도록 coverage/recall을 함께 보고한다. 분모0은 PASS가 아니다. 모델명을 가린 인간 검토와 불일치 조정이 필요하며 모델 자기평가나 또 다른 LLM의 판정만으로 의미 PASS를 만들지 않는다. 모델3회 반복의 평균/최저와 실패 사례를 모두 보고한다. 40문항의4개 보류만으로 프롬프트 인젝션·위조 인용·기한 변조 전체 안전성을 대표하지 못하므로 전용 부정 표본을 더 동결해야 한다.

## 5. 모델·토큰·비용 제안

현재 코드에 선택된 실제 모델은 없다. 오래된 LLM_CONFIGURATION/LLM_API_PREFLIGHT와 더 나중의 PHASE2C2B_EXECUTION_PLAN 사이에 후보/단가 차이가 있다. 이번에는 기존 기록을 덮어쓰지 않았다. 아래는 **후자 문서의2026-10-17 가격 스냅샷을 이용한 조건부 산술**이다. 금일 공식 가격·모델 존재/수명·계정 접근을 확인한 견적이 아니며, 실행 전 공식 문서/계정에서 다시 확인해야 한다. 문서의 deprecated 판단도 이번 검토에서 새로 인증하지 않는다.

|후보|문서상 가정 단가(USD/1M)|제안 용도|
|---|---|---|
|gpt-6-luna|입력0.10/출력0.50; 추가 input write0.125도 별도 여유|생성 비교1|
|gemini-3.1-flash-lite|입력0.25/출력·생각1.50|생성 비교2|
|text-embedding-3-small|입력0.02/1536차원|임베딩 비교1|
|gemini-embedding-2|텍스트 입력0.20/768차원|임베딩 비교2|

재확인할 공식 출처: [OpenAI 후보 모델](https://developers.openai.com/api/docs/models/gpt-6-luna), [OpenAI 임베딩](https://developers.openai.com/api/docs/models/text-embedding-3-small), [Gemini 모델](https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-lite), [Gemini 가격](https://ai.google.dev/gemini-api/docs/pricing). 공급자 SDK/구조화 출력 지원 필드도 실제 모델 버전에 맞춰 mock부터 확인한다. 공급자1 장애 때 자동으로 다른 공급자에 보내지 않는다.

[비용 산식 JSON](v03-preflight/cost-proposal.json):

- RAG:2모델×40문항×3회=240 logical calls, 각 입력4096/과금 출력·생각2048토큰.
- Workflow:2모델×7문서×3회=42 calls, 문서별1회 입력8192/과금 출력·생각4096토큰 상한 가정.
- LLM smoke:모델별1회=2 calls, 최소 wire schema용 입력1024/출력512토큰. 합계284 LLM logical calls.
- 임베딩:모델별 최대128청크×512+40질의×256+probe32=75808토큰. 실제 현재청크57개. 같은 query 벡터를 검색 모드·LLM 반복 간 재사용한다. 제공자별 batch/단일 Content 의미를 확인해 청크당1벡터를 보장한다.
- 임베딩 HTTP 상한은 OpenAI3/Gemini169 logical requests(현 corpus Gemini계획98)다. 최대456 logical paid requests, 각 최대1회 재시도로912 physical attempts. 메타·token count 포함 전체 HTTP 상한1500 제안.
- 위 상한 토큰을 모두 사용하면 RAG 약0.6636+workflow0.2322+LLM smoke0.0014+임베딩0.0167=**약USD0.914**. 모든 요청2회와 OpenAI input 전체의 write 단가를 추가 여유로 계산하면 **약USD1.994**다. 캐시 할인·배치 할인을 기대하지 않는다.
- **전체 승인 제안 USD3.00 / 새 예약 중단 USD2.50 / 물리 호출당 예약 USD0.025 / 재시도 포함 logical LLM 요청당 USD0.05**, 동시성1. 이는 기존 RAG 중심 USD2 미승인 제안에 workflow를 추가한 새 제안이지 예산 증가 승인이나 현재 구현된 통제가 아니다.
- 먼저 작은 smoke(LLM2+embedding probe2 logical calls)만 승인받아 검증한 뒤 전체 평가를 승인하는 방식을 권고한다. 둘 다 이번에는 실행하지 않았다.

토큰은 이번에 실제 계수하지 않았다. workflow-extraction-v1.schema.json만9289bytes이며 입력에는 schema/시스템 지시/문맥도 포함해야 한다. 전체 snapshot의 중복 메타데이터를 그대로 보내지 않고 최소 텍스트/인용 카탈로그로 투영한다. provider tokenizer/count API의 정확 계수·출력과 생각 토큰의 과금 cap을 보장할 수 없으면 호출하지 않는다. 입력 상한 초과/여러 window 필요 시 임의 잘라내거나 호출 수를 늘리지 않고 예산·coverage 계획을 재승인한다. 이 예산은7개 작은 합성 문서 계획이며 운영 매뉴얼 전체 서비스 비용 견적이 아니다.

## 6. 보안·비용의 선행 구현

- 업로드는 현재 public/synthetic 선언을 확인하지만 원격 반출 승인을 증명하는 영속 manifest가 아니다. 승인한 파일 SHA/기관/버전/범위·기간·공급자 목록에 있는 공개·합성 텍스트만 송신한다. 원본 파일·실제 내부자료·개인정보·불필요한 기관 메타데이터/전체 DB는 보내지 않는다.
- 키는 서버 secret 주입만 허용한다. 현재 환경의 키 변수4개는 존재 여부만 확인했으며 모두 미설정이고 키 값은 읽거나 수집하지 않았다. httpx는 설치돼 있으나 openai/google-genai/tiktoken은 미설치다. 키 존재가 계정 접근의 증거가 아니며, 키를 채팅/Git/VITE_*에 넣지 않는다.
- `.env.example`의 예산/승인 변수는 현재 apps/scripts에서 읽어 실제 통제를 하는 코드가 없다. PAID_CALLS_APPROVED 문자열만 바꿔 사람의 승인이나 비용 차단이 구현됐다고 주장하지 않는다. Google 키 이름도 기존 기록의 GEMINI_API_KEY와 GOOGLE_API_KEY가 달라 명시 주입/중복 거부 정책을 먼저 동결한다.
- 고정 HTTPS endpoint/host allowlist·TLS·redirect 거부·키 헤더·tools/function/외부 URL 실행 비활성. 문서 지시는 신뢰하지 않는다. 배경/다른 공급자 fallback 및 자동 외부 평가 판정도 금지한다.
- 로그는 run/query ID·자료 hash·provider/model/config·토큰/비용/상태/지연으로 제한한다. Authorization/x-goog-api-key/쿠키/CSRF·원문·prompt·raw 응답·공급자 예외 문자열을 일반 로그/HTTP 오류에 넣지 않는다. mock secret으로 누출 회귀를 먼저 수행한다.
- 전송 전에 요율 버전과 토큰 cap을 고정하고 지출+in-flight 예약+최악 과금이 상한 안인지 원자적으로 검사한다. 프로세스 재시작에도 예약을 보존하며 timeout/usage 누락은 최대 예약을 유지한다. 최종 usage로 대사하고 모호한 금액은 임의 환불하지 않는다.
- 기존 job3시도×SDK2시도를 허용하면 최대6회 과금될 수 있다. 공통 논리 요청 fingerprint와 영속 physical-attempt 장부로 최대2회를 공유한다. 외부 서비스의 exactly-once나 앱의 서버 취소가 과금 취소를 보장한다고 말하지 않는다. 반복 실험의 run_index는 별도 키로 두어 캐시 결과를3회 새 실험으로 세지 않는다.
- 영속 비용 장부/반출 승인 기록은 현재 미구현이다. 평가용 별도 저장소부터 설계하고 제품 DB에 결합할 때는 별도 승인된 추가형 변경으로 검토한다. 이번 DB는 바꾸지 않았다.
- 공급자 콘솔 알림은 앱의 동시 실시간 차단 대체가 아니다. 단가/생각 토큰/저장 정책이 cap 밖이거나 usage 확인 불가·연속 장애3회·권한/근거/기관 안전성 실패면 회로를 열고 중단한다. 세금/환율·다른 계정 작업·단가 변경까지 포함한 계정 전체 청구의 절대 상한을 이 산식이 보장하지 않는다.
- [OpenAI 데이터 통제](https://developers.openai.com/api/docs/guides/your-data), [Gemini 약관](https://ai.google.dev/gemini-api/terms)의 저장/abuse 로그/학습·무료·유료 조건을 실제 승인 시 다시 확인한다. store=false는 완전 무보관 보장이 아니다.

## 7. 최소 후속 개발 단위와 승인

1. **v0.3-A(제안, 아직 미착수):실제 호출 없는 전송/예산 경계.** 기존 두 어댑터 반환형과 기본 offline guard를 보존한 공급자 wire DTO·MockTransport, 비밀 마스킹·거부/불완전 JSON/429/5xx/timeout, token cap/영속 예산 예약·재시작·중복 과금 차단을 구현한다. 실제 실행 guard를 시험용 true 위조로 우회하지 않는다. source/기관/원문·snapshot 회귀를 수행한다.
2. **평가 자료 재현·동결:**예전 Windows 런타임 경로가 없으므로 새 경로에 파생 합성 자료를 재생성하고 새로운 원본 해시·DB ID·EvidenceRef를 논리 절에 연결한다. 과거 기록은 보존한다. 이어40문항 독립 인간 검토, 전체 업무 그래프/기한/분기/서식 정답과 새 holdout/부정 표본을 동결한다. 7개 긴 질의의 계약과 모델/embedding 차원·요율·데이터 정책을 승인한다. RAG scorer는 현재 Hit@5/Recall@5/MRR@5이며 Recall@10·workflow 의미 평가는 추가해야 한다.
3. **명시 승인 후 소규모 smoke:**정확 모델·endpoint·키·가용성/retention·허용 자료 hash·기간·최대 토큰/호출/예산을 확인한 뒤 LLM/embedding probe를 실행한다. 그 전에는 실제 model-list/token-count API도 자동 호출하지 않는다.
4. **별도 승인 후 반복 평가:**고정 문맥/문서별2모델×3회, 별도 임베딩 세대와 같은 검색조건, 인간 의미 판정/오류·비용 보고. 성공 후에만 제품 worker·저장 결과 v2·UI 실제/모의 출처 표시 결합 범위를 설계한다. 공식 승인/게시·Supabase 연결·클라우드 배포는 여전히 별도다.

실제 호출 전에 사용자에게 확인받을 항목은 공급자/정확 모델 버전/임베딩 차원, 자료와 정답 검토자·반출 manifest, 데이터 보관 조건, smoke/전체 실행 범위와 기간, 토큰·물리 시도·HTTP·총USD 상한, 비밀 주입 위치/별도 검증 프로젝트, 실패 중단·사람 검토 기준이다. 이 목록은 승인 요청서 초안이며 이번 대화에서 실제 비용 사용 승인을 받은 것으로 해석하지 않는다.

## 8. 이번 검증 범위·시간

새 실행 테스트/모델 평가 점수는 없다. 보존 커밋의 기존 UI20/기존154/backend409/HTTP14 결과는 과거 v0.2-C 증거로 유지하며 이번에 새 PASS로 세지 않았다. 이번에는 코드·골드셋 파일의 실제 내용·해시, 변수 존재 여부, 가격 가정 산술과 Git 보존만 확인했다. 현재 정적 구조·비용/보안 통제·인간 평가 준비 상태를 분석했을 뿐 실제 AI 연결 완료가 아니다.

총 보존·분석·문서화 시간은 약10분이며 요청 수신부터의 정확한 시각은 별도 계측하지 않았다. 실제 Supabase/LLM/임베딩 호출0회, 실제 공급자 지출0이다. 다음 단계는 자동 시작하지 않는다.
