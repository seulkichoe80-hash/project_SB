# 선택적 C 검색 통합 완료 보고

기존 AND를 기본값으로 유지하고, 서버 feature flag와 명시적 strategy가 모두 있는 요청에만 점수 기반 OR(C)을 제공했다. 기존 제품 검색을 즉시 교체하지 않았다. 실제 LLM·임베딩·Supabase·유료 API·외부 자료 전송·공개 배포·main 병합은 없다.

## 1. 보존·통합 판단

v0.3-C2 미커밋 변경23파일을 원본/fixture/기존 정답·증거·비밀정보 검사 후 **e2bb7f769cb425edbe06b375595eaf839440f004** 로컬 커밋으로 보존했다. 새 브랜치는 **feat/v03d-opt-in-scored-search**다. main·원격은 변경하지 않았다.

검색 adapter를 전역 C로 바꾸거나 flag만으로 기존 모든 요청을 전환하면 기존 UI/RAG의 lexical gate까지 영향을 줄 수 있어 채택하지 않았다. 기존 GET /search에 optional strategy를 추가하되 server allow+request opt-in을 동시에 요구한다. UI/DB migration/새 인증/새 LLM 경로는 추가하지 않는다.

## 2. 사용 계약

- flag 미설정 또는 SB_ENABLE_SCORED_OR_SEARCH=0: 기존 literal만 허용.
- 서버 flag=1로 재시작해도 `/search?q=...`는 기존 AND다.
- C는 flag=1 AND `/search?q=...&strategy=scored_or&limit=10`에서만 동작한다.
- flag off C 요청은503, 알 수 없는 strategy는422이며 자동 fallback은 없다.
- query/header의 feature_flag=1로 서버 허용을 우회할 수 없다.

기존 method/results 구조·Chunk/EvidenceRef shape를 유지한다. 기본 method는 sqlite_keyword_substring_v1, opt-in C는 sqlite_scored_or_v1이다. 점수/답변/claims/승인 상태를 기존 응답에 섞지 않는다. C는 검색 후보이지 검증된 업무 답변이 아니다.

literal의200자/8단어/limit1~50은 그대로다. C에만2000자/128단어·단어200자, normalized4000자/128token 한도를 제공한다. C2의 NFKC/casefold/구두점·공백 정규화와 고유 token 일치 수/동일 tie break를 유지한다. 조사/정답 기반 rewrite는 없다. RAGService가 호출하는 기본 search도 여전히 literal이며 C가 기존 답변 경로로 자동 유입되지 않는다.

## 3. 변경 파일

apps/api/search_settings.py는 strict/frozen server flag·자원 한도·정규화 계약, apps/api/scored_search.py는 bounded 기관별 C scorer다. apps/api/chunk_service.py에 명시적 C 분기와 원문/세대 전후 검증을, apps/api/main.py에 optional factory 설정/strategy를 추가했다.

tests/test_opt_in_search.py에 신규24개 시험을 추가했고 scripts/validation/check_opt_in_search_http.py는 실제 TCP/BFF 인증·성능/보안 검증 도구다. docs/V03D_OPT_IN_SCORED_SEARCH.md, ARCHITECTURE.md·TEST_PLAN.md·TASKS.md 관련 절과 outputs/v03d 새 실행 증거를 추가했다. 기존 테스트/fixture/골드셋/과거 증거는 수정하지 않았다. 전체 목록/hash는 CHANGE_MANIFEST.json에 기록한다.

## 4. 격리·근거·보류 안전성

SQL에서 기관·registered·현재 활성 version/current chunk job·완료 parsing attempt를 제한한다. 질의는 SQL 문자열에 넣지 않고 C의 Python 문자열 비교에서만 사용한다. 선형 스캔은 기본20,000 eligible chunk·32MiB(raw+normalized 합산)를 넘으면413으로 전체 차단하며 limit 크기의 heap만 유지한다. 제품 FTS/새 DB schema/SDK는 없다.

선택 결과의 기관/활성·source batch digest·parse/chunk job/세대·canonical payload를 확인하고 기존 EvidenceRef resolve로 원본 SHA/재파싱/span을 검증한다. 마지막 transaction에서 상태 fingerprint를 다시 비교한다. 위조/중복/타기관·처리 중 활성본/세대 변경·등록 해제·원본 무결성 오류 시 부분 결과를 반환하지 않는다.

reader/manager 읽기는 허용하고 worker/미인증은 차단한다. 실제 HTTP에서 HttpOnly session 기반 회원 권한·default deny·Origin/CSRF·로그아웃·옛 cookie 재사용 차단·원문 근거 정상/위조/타기관을 확인했다. 개발 하네스의 MockSupabaseTransport는 명시적 loopback 실행에서만 쓰며 production 기본 deny-all과 Secure cookie 설정은 변경하지 않았다.

4개 보류 문항에서도 own-tenant 후보는 반환할 수 있지만 타기관/forbidden 근거와 생성 답변은0건이다. semantic_verification=NOT_VERIFIED인 원문 candidate를 반환할 뿐 기한·금액·의무를 생성/승인하지 않는다. 이 결과를 실제 모델의 의미적 보류 판별 능력으로 해석하지 않는다.

## 5. 실제 제품 API 비교

canonical B 세대의 SQLite backup과 원본 사본을 새 work 경로에 만들고, 실제 create_app을127.0.0.1 uvicorn에 띄웠다. httpx의 실제 TCP와 BFF login/cookie·CSRF를 사용했다. ASGI TestClient/dependency override로 성능을 측정하지 않았으며 proxy/실제 provider도 사용하지 않았다. canonical 원본/runtime은 보존했다.

원 질문40개를 유지하고 각 방식3회 반복했다. C는 원 질문1요청, 기존 literal은 C1/C2와 동일한 window별 요청/RRF를 사용하므로3회 HTTP 요청 수는 literal141/C120이다. 길이 초과7문항의 literal 원 질문400도 따로 확인했다. 이것을 AI 오류/검색 품질 실패 분모에 조용히 섞지 않았다.

아래는 [최종 실제 HTTP 결과](v03d/http-final/results.json)다. 초기/최종 및3회 순위가 동일했고 C2 C Top10과40문항 모두 일치했다. [품질·시간 표](v03d/HTTP_COMPARISON.md)를 보존했다.

| 방식 | Hit@5 | Hit@10 | Recall@5 | Recall@10 | MRR@10 |
|---|---:|---:|---:|---:|---:|
| 기존 literal(window API) | 0% | 0% | 0% | 0% | 0 |
| opt-in C(raw question API) | 83.33% | 91.67% | 78.70% | 87.04% | 0.5787 |

C의40문항 Top10은 C2의 같은 세대/기관 순위와 전부 일치했다.3회 API 결과도 동일했다. 36positive 분모와4abstain은 분리했다. C는 여전히3문항 Top10 미적중·7문항 완전 근거 누락이 있어 기존 품질 목표를 낮추거나 제품/의미 정확성 합격으로 선언하지 않는다.

최종 API 전체 질의 지연 mean/p50/p95와 요청 수는 HTTP_COMPARISON.md에 기록한다. TCP·인증·DB·EvidenceRef 재해결을 포함하므로 C2의 메모리 SQL 시간과 직접 비교하지 않는다. 기존 장문은2요청인 경우가 있고 C는1요청이므로 단일 요청 수를 같게 둔 latency 비교도 아니다. 작은 합성 corpus의 single-client 실측이며 대규모/동시 부하/운영 p95 보장은 아니다.

## 6. 테스트

신규24개 영향 시험 PASS. 초기21개에 원본 오류·config 우회·활성본/등록 해제 경쟁을 추가했고, 잘못된 config의 직렬화 warning에 값이 나오지 않게 수정한 뒤24개를 다시 실행했다. 최종 영향 시험은14.905초다. 기존 warning/중간 실행도 보존했다.

전체 **backend642 PASS / FAIL0 / SKIP0 / BLOCKED0**, **UI174 PASS**, 타입 검사·빌드·기존 실제 HTTP13 PASS를 이번에 새로 확인했다. 전체 runner 253.978초, backend 247.608초, 타입0.801초·빌드1.152초다. [최종 집계](v03d/final-validation.json), [전체 실행](v03d/full-summary.json), [backend](v03d/backend.json), [network guard](v03d/backend.network.json)에 기록했다. 새 API HTTP 도구는11개 통합 검증 묶음과40문항×3회×2방식 성능을 별도로 확인한다. 최종 실제 HTTP 측정은 자체 전체 회귀/UI 종료 후 비루프백 guard 안에서 단독 실행한다. 새 API HTTP11묶음도 최종 PASS이고 [HTTP guard](v03d/http.network.json)에서 외부 시도0회를 확인했다. 이전 PASS로 대체하지 않는다.

## 7. Git·데이터 보존

현재 브랜치 feat/v03d-opt-in-scored-search, HEAD는 C2 보존 커밋이며 이번 통합은 미커밋 상태다. 승인 없는 추가 push/merge/배포는 하지 않았다. 기존 product main.py/chunk_service.py와 문서3개에 승인된 범위만 변경했고, 원본/fixture/정답/기존 시험·과거 보고/증거는 보존했다. 새 메모리 검색이나 새 API 하네스는 canonical DB를 변경하지 않는다. 보존/hash·보안 점검은 outputs/v03d에 기록한다.

## 8. 남은 위험·종료

C는 기본 off이며 실제 환경 flag를 이번 작업에서 켜지 않았다. 승인된 pilot에서만 서버 flag와 명시적 요청을 함께 사용하고 문제가 있으면 flag0+재시작으로 되돌릴 수 있다. schema migration이 없어 데이터 rollback은 필요하지 않다. UI 토글은 구현하지 않았으며 기존 UI는 변하지 않았다.

선형 스캔·원본 검증 비용·큰 기관 corpus/동시성·미검토 합성 골드셋/holdout·한국어 표현 차이가 남는다. 실제 AI/인증/배포와 인간 의미 검토40건은 여전히 미검증이다. 실제 호출·자료 반출·모델·예산 승인과 독립 검토 전에는 진행하지 않는다. 이번 작업에서 후속 단계/제품 기본값 교체/실모델 시험을 자동 시작하지 않는다.

상세 실행/허용/rollback 계약은 [V03D_OPT_IN_SCORED_SEARCH.md](../docs/V03D_OPT_IN_SCORED_SEARCH.md)를 따른다. 총 작업시간 약15.2분, 최종 실제 API 비교 22.755초다. 최종 시간은 final-validation.json에 기록했다.
