# v0.3-A 공급자 안전 경계

현재 구현은 Fake 전송 전용이다. 실제 HTTP client/SDK/키 조회·외부 요청·자동 활성화 설정은 없다. 기본 앱, RAGService, workflow worker, API 및 기존 DB에 연결하지 않는다. 환경변수나 키를 추가해도 실제 호출을 열 수 없다. USD 3은 미승인 제안이며 지출 권한이 아니다.

## 계약과 경로

`provider_safety.py`의 ProviderSettings → ApprovedSimulationInput → ProviderSafetyGateway → 정확한 FakeTransport → 엄격한 CompleteOutput → 서버 domain validator → SimulationReceipt 순서다. 임의 Transport/서브클래스/콜백을 거부한다. 요청 본문 hash·기관·공개/합성 manifest를 대조한다. 임의 URL·키 설정을 거부하고 고정 HTTPS endpoint descriptor만 제공한다. 리다이렉트는 금지한다. descriptor는 실제 공급자 serializer 또는 API 호환성 인증이 아니다.

`provider_fake_adapters.py`는 기존 LLMAdapter.generate, WorkflowExtractionAdapter, EmbeddingAdapter를 각각 유지한다. workflow는 활성 snapshot·원본 hash·세대·허용 chunk·EvidenceRef와 정확한 인용을 검증하고 기존 validation을 적용한다. RAG는 활성 canonical chunk·기관·원문 span 내 주장과 사용 근거를 검증한다. embedding은 명시적으로 허용된 공개/합성 text hash와 유한 vector·차원·정규화를 검증한다. embedding의 현재 문서/버전 확인은 기존 서비스의 index 전후 검사 책임이다. 문자열 일치는 의미 정확성 증명이 아니다.

JSON은 256KiB 한도, 중복 키/NaN/추가 필드/미완료 응답/잘못된 model·usage를 거부한다. 도구 실행·문서 지시 해석·승인 상태 승격은 없다. test_only, NOT_VERIFIED, NOT_REQUESTED, publishable=false를 유지한다. 로그에 본문·원문·키·raw 오류를 기록하지 않으며 요청/응답 repr에서 본문을 숨긴다. 이 경계는 sandbox 내부의 악의적 Python 코드 실행을 막는 보안 경계는 아니다.

## 비용 원장

`provider_budget.py`의 SimulationBudgetLedger는 별도 `.sqlite3` 경로에서만 사용한다. 기존 앱 테이블이 있거나 symlink인 파일을 거부한다. schema version 1에 meta/accounts/jobs/requests/attempts/events 6개 테이블을 생성한다. 기존 앱 DB 마이그레이션은 없다. 신뢰된 Principal의 기관·manager/worker 역할을 사용하며 reader를 거부한다. 원문 대신 hash와 정산 정보만 저장한다.

통화는 SIMULATED_USD, 금액은 정수 micro-USD(1 USD=1,000,000)다. rate는 백만 token당 micro-USD다. 시도 비용은 `ceil((input_tokens*input_rate_micro + output_tokens*output_rate_micro)/1,000,000)`이다. 실가격·실청구가 아니다. UTF-8 byte 기반 입력 counter는 테스트용이며 실제 tokenizer를 대체하지 않는다.

BEGIN IMMEDIATE 트랜잭션 안에서 기관/작업/요청 한도와 worst-case 최대 2회 시도분을 예약한다. 요청 fingerprint·정책·claim 소유권을 확인하고 attempt와 event·잔액을 함께 기록한다. 같은 요청은 재전송·중복 차감 대신 차단한다. 결과 replay 저장소는 아니다.

| 사건 | 정산 |
|---|---|
| 전송 전 실패·취소 | 미사용 예약 해제 |
| 알려진 usage + 정상/형식·근거 거부 | 사용분만 차감, 남은 예약 해제 |
| 429/503 + 알려진 usage | 시도별 정산 후 최대 1회 bounded retry |
| timeout·미완료·usage 누락·전송 중 취소/lease 만료 | uncertain, 전송한 1회 최대분 유지·미전송 retry분 해제 |
| 재시작 | lease 만료 미전송 해제, 전송 중 요청 unknown hold 유지 |
| manager reconcile | 검증된 bounded usage와 receipt hash로 1회 정산; 결과 재게시 없음 |

불명확한 사용량을 무조건 환불하지 않는다. 실제 공급자 usage가 설정 한도를 초과하거나 청구가 지연되는 경우의 실비 보장은 아직 없다. 단일 SQLite 파일의 여러 프로세스 경쟁까지 검증하며 다중 호스트 분산 예산/고가용성은 범위 밖이다. 원장 정산은 실제 workflow_jobs 재시도 정책과 아직 통합하지 않는다.

## 재현과 후속 조건

신규 검증: `.venv/bin/python -B -m unittest discover -s tests -p 'test_provider_safety.py'`.
전체 검증은 TEST_PLAN 및 outputs/V03A_REPORT.md의 실행 증거를 따른다. 네트워크 guard는 loopback만 허용하며 외부 socket/DNS 호출 부재를 별도로 검사한다.

실제 연동 전 별도 승인이 필요한 항목은 공급자·고정 모델/API serializer·실가격/토크나이저·키 저장/회전·공개/합성 입력 manifest의 독립 검토·요청/작업/총 예산·청구 불확실성 대응·인간 평가다. 현재는 원격 전송 구현이나 실 AI 성능/과금·운영 준비 완료로 해석할 수 없다.
