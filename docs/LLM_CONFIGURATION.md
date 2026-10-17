# 실제 인터넷 LLM 연결 준비

상태: 설정 계약/공식 문서 검토, 실제 호출 미실행. 후보는 기존 GPT-4.1 mini와 Gemini 2.5 Flash를 유지한다. 계정·할당량·API 권한·모델 수명/버전은 실제 호출 직전에 확인한다. 문서에 모델이 있어도 현재 계정에서 사용 가능하다는 뜻은 아니다.

루트 .env.example을 로컬 .env로 복사하고 서버 프로세스에서만 읽는다. 키는 사용자 본인이 로컬 또는 승인된 시크릿 저장소에 입력한다. 채팅·Git·프런트 VITE_*·브라우저에 넣지 않는다. 후보별 설정은 OPENAI_API_KEY/OPENAI_MODEL, GOOGLE_API_KEY/GOOGLE_MODEL이며 generic provider가 해당 어댑터를 선택한다. EMBEDDING_*는 생성 모델과 분리한다. DATABASE_URL 등의 실제 자격증명도 Git 제외다.

## 호출 전 확인

1. 호출할 공급자·정확 모델/버전·기능(text/vision/schema)·공식 endpoint를 지정한다. 임의 사용자 URL을 endpoint로 허용하지 않는다.
2. 공개/합성 fixture·질의 수·최대 입력/출력·재시도·기간·최대 비용을 사용자에게 구체적으로 제시하고 승인 범위를 기록한다. PAID_CALLS_APPROVED 값을 바꾸는 것만으로 사람의 승인이 생기지 않는다.
3. 서버 설정에서 값 존재/범위만 검사하고 실제 키·질문·원문을 출력하지 않는다. 미설정·예산 미승인 시 네트워크를 호출하지 않고 BLOCKED로 기록한다. 로그에는 공급자/모델 ID·설정 버전·자료 hash·token 수·비용·오류 종류만 남긴다.
4. 승인 후 최소 1개 합성 질문부터 시험하고 같은 schema·자료·기대값으로 2종을 교체한다. schema 유효성·근거 재해결·의미 정확성·timeout/401/429·비용을 각각 기록한다. 자동 다른 공급자 전송은 금지한다.

예산 요청 초안은 합성 corpus·2종 모델·총 $10 이내지만 현재 승인/호출은 없다. 무료 호출도 실증 기록이 없는 한 PASS로 표시하지 않는다. 실제 키를 읽는 도구나 클라우드 계정 생성은 이번 단계에서 실행하지 않았다.

## 공급자별 차이

OpenAI는 JSON Schema 기반 structured output을 제공하나 지원 schema/모델 조건을 확인해야 한다. Gemini도 schema의 지원 범위를 가진다. 공통 Pydantic/JSON schema를 공급자 요청에 맞게 변환한 뒤 반환값을 다시 로컬 검증한다. JSON 형식 보장이 사실의 정확성·근거 의미 일치 보장은 아니다. [OpenAI 공식 문서](https://developers.openai.com/api/docs/guides/structured-outputs), [Gemini 공식 문서](https://ai.google.dev/gemini-api/docs/structured-output)

공통 오류는 unavailable/unauthorized/rate_limit/timeout/invalid_schema/invalid_evidence로 정규화한다. 공급자 SDK 객체는 공통 도메인에 노출하지 않는다. 응답 streaming·refusal·reasoning 토큰·이미지 지원/비용은 capability matrix로 분리한다. Embedding은 provider/model/version/dimension/정규화/metric/세대가 바뀌면 별도 인덱스로 재구축한다.

현재 단계에서 가능한 것은 모의 transport 계약 검증뿐이다. 실제 모델 2종·임베딩 정확도는 각각 G1-B의 해당 기능 전 게이트로 남는다.
