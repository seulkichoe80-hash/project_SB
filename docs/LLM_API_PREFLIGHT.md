# 인터넷 LLM 연결 사전 검토 2026-10-17

실제 모델·임베딩 호출/키 조회/유료 자원/배포는 수행하지 않았다. 아래는 공식 문서상 지원과 설계 권고이며 계정·리전·할당량·한국어 품질·실제 모델 교체 검증이 아니다.

| 기존 후보 | API·계약 | 문서 확인과 위험 |
|---|---|---|
| OpenAI gpt-4.1-mini | Responses 또는 Chat Completions, JSON schema/Structured Outputs | 공식 모델 페이지에 Deprecated 표시. 계정의 실제 지원·종료일·대안 모델 승인 전 채택 완료로 볼 수 없음 |
| Google gemini-2.5-flash | generateContent, structured output(JSON schema 지원 범위 확인) | 후보 유지. 계정 접근·가용성·한국어·오류/요금 실증은 미실행 |

[OpenAI 모델/가격](https://developers.openai.com/api/docs/models/gpt-4.1-mini)은 입력 $0.40/출력 $1.60 per 1M tokens, [Gemini Standard 가격](https://ai.google.dev/gemini-api/docs/pricing)은 텍스트 입력 $0.30/출력(생각 토큰 포함) $2.50 per 1M tokens로 안내한다. 이는 확인 시점 문서 가격이며 실제 청구·가용성 보장이 아니다. 모델을 임의 교체하지 않는다. 대안은 별도 모델 선택·승인·동일 골드셋 검증 후 결정한다.

설계상 예산 산식은 요청수×(입력 상한×입력단가+출력/생각토큰 상한×출력단가)/1,000,000에 허용 재시도·안전 여유를 더한다. 예: 각 모델40질의×3회, 입력2000·출력2048 토큰 가정이면 각각 약 $0.489216/$0.6864, 합계 $1.175616다. 가정 계산이며 실행 비용은0이고 생각토큰/캐시/추가 도구·다른 모델 요금은 별도 확인한다. 이 계산은 비용 승인이나 $10 검증 예산 사용 허가가 아니다. 서버에서 호출 전 예약·동시성·요청/토큰 한도·재시도 비용을 강제해야 한다.

## 연결 전 체크리스트

- 승인할 provider/정확 model(snapshot)/공개·합성 corpus/질의셋/최대 USD·요청·토큰·재시도 횟수를 확정한다. 실제 내부/개인정보/비밀자료는 금지한다.
- OPENAI_API_KEY/GEMINI_API_KEY는 백엔드 환경변수 또는 시크릿으로만 주입한다. 예제는 변수명만 제공하고 키 존재·값을 이번 검토에서 수집하지 않는다. VITE_*·Git·일반 로그·오류 응답에는 비밀을 넣지 않는다.
- 공급자별 SDK/HTTP 타입은 adapter 내부로 제한한다. 공급자 host allowlist, HTTPS, timeout, 제한된429/5xx 재시도와 공통 unavailable/refusal/invalid_output 오류를 구현한다. 자동 외부 fallback·도구 실행·원격 문서 다운로드는 비활성으로 둔다.
- [OpenAI 데이터 통제](https://developers.openai.com/api/docs/guides/your-data): API 학습 사용과 abuse monitoring/application state 보관을 구분한다. 기본 abuse 로그 최대30일 및 endpoint별 보관 예외를 확인하고 store=false 등 전송 설정과 조직 정책을 점검한다. store=false를 무보관 보장으로 표현하지 않는다.
- [Gemini 약관](https://ai.google.dev/gemini-api/terms): 무료/유료의 데이터 사용 조건이 다르며 무료는 제품 개선·인간 검토 가능성을 명시한다. 무료라는 이유로 내부/민감자료를 전송하지 않는다.
- [OpenAI 구조화 출력](https://developers.openai.com/api/docs/guides/structured-outputs), [Gemini 구조화 출력](https://ai.google.dev/gemini-api/docs/structured-output): schema 지원은 사실·의미 정답 보장이 아니다. 공급자별 schema capability, 거부/timeout/401/429/invalid JSON을 같은 계약에서 검증한다.
- 명시적 문맥 EvidenceRef ID만 인용 가능하게 하고 source anchor·기관·현재 버전 재해결 뒤 의미 일치/근거없음·충돌 억제를 별도 평가한다. 악성 문서 지시/가짜 인용/기한 조작 골드셋을 포함한다.
- 2모델×동일 대표셋×3회, 임베딩 모델/차원/정규화/세대별 검색을 별도로 검증한다. 계정·모델 접근 및 비용·보안 조건이 충족되기 전 실제 호출은 BLOCKED/NOT_RUN으로 유지한다.
