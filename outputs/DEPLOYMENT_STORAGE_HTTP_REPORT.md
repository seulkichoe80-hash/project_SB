# 배포 준비 7단계 — Storage HTTP 전송 결과

## Git 보존·범위

시작 `feat/deployment-staging-prep` / `cbee283a9dc3e810573faad523a95c778ff87535`, origin `github.com/seulkichoe80-hash/project_SB.git`를 확인했다. 기존 스테이징 문서 8개는 manifest SHA·민감정보 패턴을 확인하고 `work/deployment-storage-http-preservation/staging-eight.tar`와 로컬 커밋 **34c66e108a45442e164fa2230861a4a3f469f05c**에 보존했다. 이후 `feat/deployment-storage-http`에서 개발했다. 신규 단계 변경은 미커밋 검토 후보로 남긴다. 원격 작업·배포·서비스 계정/키 주입은 하지 않았다.

## 구현 파일

- `apps/api/storage_http.py`: exact httpx.MockTransport만 받는 서버 전용 전송. 공식 POST upload·GET authenticated download, immutable/probe-first, 상태 분류·비밀정보 비노출·바이트 크기/SHA 검증.
- `apps/api/private_storage.py`: 기존 인터페이스/권한/registry를 유지하고 정확한 새 transport 타입의 명시 주입을 허용. 설정 fingerprint 일치·매 요청 정책 재검증.
- `tests/test_storage_http.py`: 신규54개(프로토콜32, SQLite11, 격리 로컬PG11).
- `docs/DEPLOYMENT_STORAGE_HTTP.md`, `ARCHITECTURE.md`, `TEST_PLAN.md`, `TASKS.md`: 구현/미검증 계약과 실행 범위.
- 이번 보고 및 `outputs/deployment-storage-http/`의 새 evidence. 과거 증거는 덮어쓰지 않았다.

## 공식 API·보안·복구

이전 단계에서 확보한 Supabase 공식 소스 commit `7425d4930528931400fb3e656e860b1094cb224e`의 4자료 SHA를 재확인했다. [출처·판정](deployment-storage-http/CONTRACT_STATUS.json), [정확한 경로·헤더 및 운영 제약](../docs/DEPLOYMENT_STORAGE_HTTP.md)을 참조한다. 새 문서 조회 및 공급자 API 호출은0회다.

업로드 JSON 응답의 세부 필드, 원격 목록 API·bucket ACL 조회 계약은 확인되지 않아 구현했다고 표시하지 않는다. POST의 성공/오류 본문 대신 인증 GET 원본 바이트로 업로드 성공을 판정한다. private=True 구성과 authenticated 경로만 허용하지만 실제 private ACL 검증은 아직 BLOCKED다. modern sb_secret_ bearer 계약은 미확인으로 거부한다.

HTTPS 고정 호스트·canonical 기관 hash 경로·정확한 bucket·GET/POST만 허용한다. redirect·경로 탐색·환경 proxy·헤더 주입·cookie 재사용을 차단한다. 서버 DB의 기관/역할/현재성·원본 hash 검사를 우회하지 않는다. key/원문 로그 비노출·일반 예외 메시지 마스킹을 시험했다.

불명확한 POST·timeout·429/500/503 뒤 GET으로 실제 SHA/크기를 재검증한다. 인증 실패/redirect는 거부한다. 자동 POST 반복은 없으며 기존 intent 최대3회와 probe-first를 유지한다. retryable/ambiguous/Retry-After를 분리하되 운영 scheduler backoff 통합은 후속 조건이다. 부분 객체는 격리하고 DB 실패 시 미게시 상태와 객체를 보존한다.

기존 Fake 전체 orphan inventory·격리·backup/restore 회귀는 유지한다. **HTTP 전체 orphan 열거·대사 및 cloud backup은 공식 목록 계약이 없어 BLOCKED**다. HTTP store에 Fake 원자 backup을 잘못 적용하는 것도 차단한다. 운영 준비 전체 완료를 선언하지 않는다.

## 검증

최종 전체 회귀 결과는 아래의 자동 기록 부록과 [backend.json](deployment-storage-http/backend.json), [network guard](deployment-storage-http/backend.network.json)를 따른다.

- 첫 영향 통합: 당시 신규49 + 기존 Storage/복구94 = **143 PASS**, 18.954초, SQLite/실제 격리 로컬 PostgreSQL 포함.
- 보강 후 신규 HTTP: **54 PASS**, 3.289초, SKIP0. 최종 전체 회귀에도 동일54개를 포함했다.
- 20MiB Mock 왕복·초과 거부·chunked 초과·부분 응답·hash 변조·중복/오류/DB 실패를 확인했다. 실제 클라우드 20MiB 전달 시험은 하지 않았다.
- UI/API 응답/DB schema·migration 변경 없음. UI·typecheck·프런트 build·별도 TLS 재실행은 NOT_RUN이며 과거 결과를 새 PASS로 대체하지 않는다.
- 실제 Supabase/Auth/LLM/embedding 호출·외부 자료 전송·유료 신청·push/merge/배포0회. loopback PostgreSQL과 Mock/ASGI 테스트만 실행했다.

## 운영 연결 전 남은 조건 및20MiB 계획

실제 연결은 별도 승인 후 진행한다. 키 종류/최소권한·private ACL·공식 목록/오류 응답·HTTP inventory와 원격 backup/restore·API/worker 공유 저장소 wiring·Auth·운영 DB/복구·프록시 제한을 먼저 확인해야 한다. production blocker는 변경하지 않았다.

20MiB-1/20MiB/20MiB+1 합성 자료, multipart overhead 포함 전체 body, upload/download hash, timeout·429·끊김·중복·동시요청을 승인된 실제 경로에서 검증한다. 스테이징 B(same-site API 직통)는 후보이며 확정하지 않는다. Vercel rewrite/Render ingress 요금제별 제한은 아직 미검증이다. 공식 문서는6MB 초과에 resumable을 권장하므로 이번 standard POST Mock 시험으로 실제20MiB 안정성을 보증하지 않는다. TUS·직접 업로드·public URL·서명 URL·삭제 API는 구현하지 않았다. 다음 단계는 자동 진행하지 않는다.

## 보존 검사 한계

추적 원본·fixture·기존 테스트·과거 증거는 기준 SHA로 대조한다. Git 후보의 강한 비밀키 패턴과 합성 출처를 검사하지만 모든 개인정보의 완전한 자동 인증은 아니다. 시험 중 생성된 work 임시물과 격리 DB 상태는 사용자 원본과 구별한다. 인간 검토 판정/승인 생성0건이다.

## 최종 자동 기록

- 전체 백엔드 **1,085 PASS / FAIL0 / SKIP0** (기존1,031 + 신규54), runner 347.524초. Python socket guard probe PASS, 차단된 외부 시도0, 실제 공급자 호출0. PostgreSQL은 격리 loopback 실DB다.
- 코드 SHA 132파일 대조 일치. 기준 976파일 불변, 의도한 추적 변경4파일, 예상 밖 변경/삭제0. 기존 스테이징8파일은 보존 커밋과 hash 일치.
- 새 단계 변경은 미커밋이며 HEAD는 `34c66e108a45442e164fa2230861a4a3f469f05c`, 브랜치는 `feat/deployment-storage-http`. production 차단 유지.
- 보존 검사 기준 소요 **12.16분**, 종료 2026-10-18T22:31:07.201140+09:00. [보존 검사](deployment-storage-http/PRESERVATION.json), [영향 시험](deployment-storage-http/TARGETED_RESULTS.json).
- 기존 Starlette/httpx TestClient deprecation 경고는 남아 있으나 이번 실행 오류는 없다. 의존성 잠금파일 변경 없음.
