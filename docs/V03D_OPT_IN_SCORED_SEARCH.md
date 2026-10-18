# v0.3-D 선택적 C 검색 통합

FR-06/19 및 NFR-02/03/04/05/06의 제한적 제품 API 통합이다. 실제 모델·임베딩·Supabase·답변 생성·승인/게시·배포는 없다. [C2 비교](V03C2_RETRIEVAL_ABLATION.md)의 C 규칙을 유지하며 정답/질문/원본/청크 세대는 바꾸지 않는다.

## 통합 방안과 기본값

전체 search_adapter를 C로 바꾸거나 flag만 켜면 모든 기존 요청이 C가 되는 방식은 사용하지 않는다. 기존 RAGService의 lexical gate/기존 UI가 자동으로 넓어진 후보를 소비할 수 있기 때문이다. 서버 허용과 요청 의도를 둘 다 확인하는 방식을 선택했다.

- 기본 환경 `SB_ENABLE_SCORED_OR_SEARCH=0` 또는 미설정: 기존 literal만 가능.
- 서버 설정을 정확히 `1`로 지정하고 재시작한 경우에도 기존 요청은 literal 그대로다.
- C를 사용하려면 `/search?q=...&strategy=scored_or&limit=10`을 명시해야 한다.
- `/search?q=...` 또는 strategy=literal은 이전 method와 결과 구조/한도를 유지한다.
- C 미허용은503 scored_or_search_not_enabled, 알 수 없는 strategy는422다. 자동 fallback은 없다.
- client query/header로 서버 flag를 켤 수 없다. 요청자 기관/역할도 client flag/metadata가 아닌 기존 BFF session과 서버 멤버십을 따른다.

환경값은0/1만 허용하며 'true' 등 잘못된 값은 startup에서 실패한다. 서버 코드에서 SearchSettings(scored_or_enabled=True)를 명시 주입할 수도 있다. 설정은 strict/frozen 재검증으로 model_copy 우회를 거부하고 직렬화 warning에 raw 설정값이 노출되지 않게 한다. 실제 환경 설정이나 공개 서비스의 flag를 이번 작업에서 켜지 않았다.

## API 계약

기존 GET /search와 method/results 구조를 재사용한다. literal은 method=sqlite_keyword_substring_v1, C는 sqlite_scored_or_v1이다. results의 Chunk/EvidenceRef 구조는 같고 점수·답변·claims·승인 필드를 새로 넣지 않는다. UI 수정/승인 버튼/새 인증/DB schema는 없다. 같은 shape의 candidate 결과이지 확정 답변이 아니다.

literal은 기존200자/8단어/limit1~50을 유지한다. opt-in C에만2000자/원 질의128단어·단어200자, normalized4000자/128token 한도를 적용한다. 기호만 남아 normalized token이 없으면 빈 결과다. NFKC/casefold·Unicode P 구두점 공백화·공백 축약 후 고유 token을 사용하며 조사/동의어/정답 기반 rewrite는 없다.

ChunkService.search에 optional strategy를 추가했으며 기존 positional 인자와 기본 호출은 그대로다. RAGService는 여전히 strategy를 지정하지 않으므로 literal을 사용한다. C의 넓은 후보가 기존 RAG 답변 경로에 자동 유입되지 않는다. 기존 HttpOnly/Secure/CSRF/Origin/no-store 계약과 기본 deny-all 인증도 바꾸지 않는다. GET 검색에는 기존 read-only cookie 계약을, POST evidence resolve에는 기존 CSRF/Origin을 적용한다.

## 검색·자원·근거 경계

apps/api/scored_search.py의 ScoredORSearch는 현재 기관·registered·활성 version·current chunk job·완료 parse attempt를 SQL에서 제한한다. 해당 source search_text에만 C2와 같은 정규화를 적용하여 일치 고유 token 수로 정렬한다. tie는 기존 문서 생성시각/버전/청크 순서다. bound institution SQL만 사용하고 질의 token은 Python의 문자열 비교에만 사용하므로 SQL/FTS operator를 실행하지 않는다.

제품 DB에 normalized column/FTS/index table을 만들지 않는다. row를 순회하며 크기 limit의 heap만 유지한다. 기본 최대20,000 eligible chunk·32MiB(raw+normalized UTF-8 합산) 스캔을 넘으면413 scored_or_corpus_limit으로 전체 요청을 차단한다. 작은 corpus pilot용 선형 스캔이며 대규모/동시 부하 성능은 검증하지 않았다. 서버 설정에서 더 낮은 cap을 줄 수 있다.

결과의 기관·활성·현재 parse/chunk 세대·source batch digest·canonical payload를 먼저 대조한다. transaction을 해제한 뒤 기존 resolve로 원본 hash/재파싱/anchor/span을 다시 확인하고, 최종 transaction에서 상태 fingerprint를 대조한다. 부분 결과를 먼저 반환하지 않는다. 타기관·구버전·미완료·위조/중복 결과, 처리 중 세대/활성본 변경·등록 해제·원본 무결성 오류는 실패한다. 기관/문서/version 권한은 서버에서 검사한다.

구조적 출처가 유효해도 의미가 맞다는 뜻은 아니다. 원문 없는 기한/의무·금액을 생성하는 API나 LLM 연결은 추가하지 않는다. 보류 질의에 own-tenant candidate가 나오는 것은 허용하되 답변으로 승격하지 않는다. 실제 의미적 보류 판정은 여전히 미검증이다.

## 실제 HTTP 비교

scripts/validation/check_opt_in_search_http.py는 명시적 --synthetic-loopback-test에서만 동작한다. canonical 평가 DB를 SQLite backup하고 원본을 새 work 경로에 복사한다. 실제 product create_app을127.0.0.1 uvicorn에 올리고 httpx TCP로 BFF login/session/CSRF와 search를 호출한다. source DB/원본은 수정하지 않는다. MockSupabaseTransport만 사용하며 provider user_metadata의 가짜 역할/기관은 실제 권한에 사용하지 않는다. dependency override/in-process ASGI transport는 사용하지 않는다.

원 질문40개를 유지한다. C는 원 질문을 한 요청으로 호출한다. literal은 C1/C2 window 프로토콜을 API 요청으로 수행해 RRF를 합친다. 따라서3회 요청 수는 literal141/C120이며 같은 수의 단일 HTTP 요청 시간으로 해석하면 안 된다. 원 장문7건의 literal400도 따로 기록해 계약을 바꾸지 않았음을 확인한다. C의 Top10은 C2 원본 세대의 순위와40건 모두 일치해야 한다.

36positive의 Hit/Recall@5/10·MRR@10과 HTTP 질의 전체 지연을3회 측정한다. 4abstain은 분모에서 제외하고 타기관/forbidden ref·답변 필드 부재를 별도로 검사한다. flag off503/default200, reader/manager·anonymous401, Origin/CSRF403, 올바른 근거/위조422/타기관404, logout/옛 cookie401을 확인한다. session cookie·비밀번호·provider token은 결과 파일에 저장하지 않는다. 값은 합성 전용이고 일반 운영 인증으로 배포할 수 없다.

## 실행과 복구

server flag는 기본0이며 설정 변경은 재시작 시 적용한다. 문제가 생기면 flag를0으로 되돌리고 재시작한다. query의 strategy를 생략하면 literal로 돌아간다. schema/data migration이 없으므로 원본/청크/후보를 되돌리는 작업은 없다. 운영 환경의 flag 변경·배포는 별도 승인 대상이다.

검증은 프로젝트 루트 기존 .venv에서 새 출력 경로로 실행한다.

```bash
.venv/bin/python -B -m unittest discover -s tests -p 'test_opt_in_search.py'
.venv/bin/python -B scripts/validation/check_opt_in_search_http.py \
  --synthetic-loopback-test --generation-dir outputs/v03b/isolated-evaluation \
  --output-dir outputs/v03d/new-http-run
```

현재 manifest와 같은 ID의 runtime/원본이 필요하다. 다른 환경에서 재생성한 새 세대를 사용할 때는 C2 비교도 같은 세대로 다시 수행해 순위 대조 자료를 맞춰야 한다. 실제 key/계정·외부 provider·환경 install/start 설정 변경은 없다. [완료 보고](../outputs/V03D_REPORT.md)에 실행 범위/한계·시간을 기록한다.
