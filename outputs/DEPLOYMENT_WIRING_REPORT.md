# 배포 준비 5단계 — 운영 Wiring·HTTPS·프록시 검증 보고

2026-10-18 UTC. **완료 범위는 명시 local/Fake API-worker wiring, 단일 정제 프록시 경계, 실제 loopback TLS 및 Fake 세션 재검증이다. Vercel/Render/Supabase 운영 연결 완료가 아니다.** [설계·명령·위험](../docs/DEPLOYMENT_WIRING.md).

## 1. 시작·보존·Git

실제 `/workspace/project_SB`, 브랜치 feat/deployment-auth, HEAD68a8a3513c1df7bc8290f5b3e091e2125733677c를 확인했다. 기존 미커밋20파일을 이전 CHANGE_MANIFEST와 대조하고 979 PASS 당시 source SHA의 일치를 확인했다. 강한 비밀키 패턴 검사 및 합성 자료/기존 증거 출처 확인 후 **7451af863c7a81af140dc2c610033e430af526b3**으로 로컬 보존했다. 메시지: Preserve offline JWT JWKS and server membership contracts.

이후 **feat/deployment-wiring** 분기. 이번 구현·문서·증거는 미커밋 검토 후보, staged0. 기존 원본·fixture·기존 테스트·과거 증거·인간 검토 자료 변경/삭제 없음. main 수정/reset/force push/remote push/merge/tag/공개 배포 없음. 보존 tar/파일 SHA는 work/deployment-wiring-preservation/에 있다. [보존 JSON](deployment-wiring/PRESERVATION.json), [전체 변경 SHA 목록](deployment-wiring/CHANGE_MANIFEST.json).

## 2. 변경 파일

신규:

- apps/api/runtime_wiring.py — 명시 RuntimeBinding·API/worker 저장소/역할/project·root 검증, Fake worker parent peer 확인, 공통 worker document factory.
- apps/api/proxy_boundary.py — strict ProxyPolicy·trusted peer+서버 증명·Host/forwarded/Origin 경계, bounded body/stream/rate/deadline, offline ASGI `/api` edge·cookie/redirect 전달.
- apps/api/session_revalidation.py — Fake provider 상태 조회와60..1800초 세션 상한 계약. 실제 상태 네트워크 전송 없음.
- scripts/validation/check_deployment_wiring_tls.py — private work의 시험용 CA/leaf 인증서로 실제 loopback TLS 입구 검증, Fake upstream/API만 사용.
- tests/test_deployment_wiring.py — 신규52개(공통 proxy14, SQLite wiring18, PG wiring20).
- docs/DEPLOYMENT_WIRING.md, 본 보고, outputs/deployment-wiring/* 새 증거.

수정:

- apps/api/main.py — 상호 배타적 binding 선택/검증, 선택적 proxy middleware/session guard. 기존 factory/응답/deny-all 기본 유지.
- apps/api/worker.py, chunk_worker.py, workflow_worker.py — 실제 main 경로가 공통 선택을 사용. 기존 CLI와 local/PG+Local 기본·lease/heartbeat/timeout/once 계약 유지.
- apps/api/auth.py — 선택적 provider 상태 재검사, 세션 상한, disabled/deleted SID 철회를 commit 후 거부. 기존 cookie/CSRF/멤버십 보존.
- apps/api/runtime_settings.py — API/worker의 timeout/rate/hops/LLM 상한 비교 보강, local/Fake 구현 상태와 vendor 미실증 blocker 표시.
- ARCHITECTURE.md, TASKS.md, TEST_PLAN.md — 관련 계약·실행 기준·완료 범위 추가.

DB schema/migration·기존 Storage/JWT 검증 모듈·UI·기존 테스트·lockfile은 그대로이며 새 설치/다운로드는 없다.

## 3. Wiring 상태·실제/미구현 구분

API는 `create_app(runtime_binding=...)`, worker는 실제 parse/chunk/workflow main 또는 파생 worker service 경로로 구성한다. provider/store/repository를 중복 별도 지정하면 거부한다. API·worker data_dir, DB backend/host/port/database/schema 또는 SQLite 경로, 로컬 원본 root 또는 private project/bucket/같은 Fake 인스턴스를 비교한다. Fake peer가 다르거나 API에서 파생되지 않은 worker는 claim 전에 거부한다. 브라우저 Auth/provider·proxy 증명은 worker에서 제거한다.

SQLite/Local 기본과 실제 로컬 PostgreSQL 선택은 동작한다. Private Storage·새 JWKS/password·provider 상태 전송은 **Fake-only**다. 기존 GET /user HTTP adapter 구현은 보존하지만 이번에 실제 연결하지 않았다. 원격 PG 구성은 이 binding에서 차단하며 production도 기동을 거부한다. Fake memory 객체는 별도 프로세스/재시작 사이에 공유되지 않는다. 독립 local/PG+Local CLI는 기존 동일 data-dir/schema/DSN 계약을 사용하며 실제 private Storage/cloud worker는 미완료다.

## 4. HTTPS·프록시 실제 검증

실제 검증: 자체 loopback listener의 **TLS1.3**, 시험용 CA chain/hostname 검증을 켠 httpx, `proxy_headers=False`, access log 비활성. 미신뢰 CA handshake 거부도 확인했다. TLS 이후 edge→API는 **in-process ASGI**이며 Vercel/Render 네트워크·인증·TLS가 아니다.

새 경계는 고정 HTTPS public Host와 `/api/` prefix, 허용 immediate peer CIDR+서버 전용 증명을 확인한다. client Forwarded/X-Forwarded-*/증명/hop-by-hop은 입구에서 제거하고 단일 정제 헤더를 생성한다. API는 체인/잘못된 Host·proto·Origin을 거부한 뒤에만 ASGI 값을 정규화하고 증명 헤더를 제거한다. 공개 CORS를 열지 않는다. 기존 Authorization/Cookie/CSRF 전달, 여러 Set-Cookie 유지, 같은 출처 redirect `/api` 재연결·외부 redirect 차단을 검사했다. backend API는 bearer 대신 기존 BFF 쿠키만 사용한다.

요청은 선언/실제 크기·unknown stream/framing과 bounded buffer를 검사한다. 정확20MiB 합성 PDF는 실제 TLS/인증/DB/Storage 등록201 및 원본 SHA 일치, +1byte는413이었다. body/upstream deadline·429/Retry-After도 검사했다. rate limit은 process-local/IP hash별·최대1000 key이므로 분산/운영 DoS 제어 완료가 아니다. proxy timeout은 이미 진행 중인 DB 작업/worker를 자동 rollback하지 않으므로 기존 idempotency/claim/상태 조회가 필요하다.

**운영 중요 조건:** Uvicorn/상위 계층이 먼저 forwarded 헤더를 믿어 peer를 바꾸면 이 검증을 보장할 수 없다. 실제 서버는 --no-proxy-headers와 검증된 정제 gateway를 사용해야 한다. Vercel Function의 알려진 약4.5MB 제한 등과 static rewrite는 다르므로 **로컬20MiB PASS를 클라우드20MiB PASS로 주장하지 않는다**. 실제 선택 경로/plan/상한/스트리밍·비밀 헤더 주입·Render 직접 접근/health probe 차단·증명 회전은 미검증이다. 공개 설정파일/프런트 번들에 shared secret을 넣거나 공개 bucket으로 대체하지 않았다.

## 5. 세션 철회 정책

새 JWT RuntimeBinding에는 정확한 Fake SessionRevalidation을 요구한다. BFF 절대 수명은 기존 AuthSettings/provider JWT/정책 상한60..1800초의 최소값(합성 시험300초), idle 유지·활동으로 절대 만료 연장 없음.

보호 요청마다 DB identity issuer/subject의 Fake provider 상태를 확인한다. disabled/deleted는 SID revoke를 **커밋한 후**401, 재활성화해도 옛 SID 거부·명시 새 로그인 필요. unknown/장애는503으로 요청 거부하고 touched/수명을 연장하지 않는다. 장애 복구 후 아직 만료/철회되지 않은 SID만 재검증 가능하다. 서버 identity/org/membership 비활성은 provider 장애와 관계없이 기존 즉시 거부를 유지한다. provider 토큰/비밀번호를 세션에 저장하지 않는다.

남은 위험: 실제 Supabase 이벤트/신뢰된 상태 동기화·freshness/누락/재처리/권한·운영 장애 정책은 미구현이다. Fake 상태는 DB transaction 안의 짧은 메모리 작업이며 네트워크 조회를 그대로 넣어 DB lock을 늘리면 안 된다. 기존 guard 없는 local/direct-injection BFF를 실제 provider 철회 연동 완료로 간주하지 않는다.

## 6. 실행 결과

| 새 실행 | 결과 | 시간 |
|---|---|---:|
| 신규 proxy/wiring/세션·SQLite/실제 로컬PG | **52 PASS**, FAIL0/SKIP0 | 7.080초 |
| 검증된 실제 loopback TLS15개 | **15 PASS**, 미신뢰 CA/20MiB 등 포함 | 1.527초 |
| 전체 backend(기존979+신규52), 최종1회 | **1031 PASS**, FAIL0/SKIP0/BLOCKED0 | tests323.831초, 전체325.453초 |
| local preflight | LOCAL_CONTRACT_VALID | 연결 확인 아님 |
| production 합성 API/worker preflight | settings VALID, **BLOCKED/startup_allowed=false** | connectivity NOT_CHECKED |

[신규](deployment-wiring/targeted-final.txt) · [TLS](deployment-wiring/tls-verified.json) · [TLS guard](deployment-wiring/tls-network.json) · [전체 회귀](deployment-wiring/backend.json) · [전체 guard](deployment-wiring/backend.network.json) · [production preflight](deployment-wiring/preflight-production.json).

초기 관련48개도 PASS였고 이후 시작 전 peer 분기 차단4개를 추가해52 PASS로 검증했다. 기존 Auth30개 영향 검사도 PASS였다. 실패 증거를 지우거나 기존 assertion을 바꾸지 않았다. TLS는 최초 성공 후 최종 binding에서 네트워크 guard를 적용해 새 경로에 재실행했다. 최종 전체 회귀는1회만 실시했다.

Python loopback guard 자체 probe PASS, 본 TLS/전체 회귀의 차단 외부 시도0, 실제 Supabase/LLM/임베딩 호출0·실제 지출0. C libpq는 Python guard 범위 밖이므로 정확127.0.0.1 local_test DSN 강제를 함께 사용했다. PostgreSQL 서버 stop/start 복구를 이번에 새 검증했다고 보고하지 않는다. 검증 후 소유 로컬 컨테이너만 중지하고 named volume을 보존한다.

UI/타입/build/실제 Chromium은 프런트·응답 계약·의존성 미변경으로 이번 미실행이며 과거 UI174 PASS를 새 결과로 계상하지 않는다. Starlette/httpx의 기존 deprecation 경고는 남지만 실패는 없다.

## 7. 보안·기존 자료·운영 조건

기존 tracked 파일을 HEAD와 대조해 의도한 source/문서 외 변경·삭제0, 이전 Auth20파일의 보존 커밋 SHA 일치 확인. 원본·fixture·기존 테스트·과거 증거·인간 검토 불변, 판정/승인 생성0. NOT_VERIFIED/NOT_REQUESTED 유지.

Git 후보의 강한 private-key/AWS/provider-key 패턴0건, 합성 marker만 사용. 이는 포괄 PII 인증은 아니다. 로컬 TLS leaf key는 시험용으로만 Git 제외 work/0700 디렉터리·0600 파일에 생성했고 CA trust/서비스 Secret/env는 변경하지 않았다. 실제 계정/키·JWT·원문·세션·자격증명을 일반 로그/보고에 기록하지 않았다. 운영 edge/Render/APM 로그 정책은 별도 실증 대상이다.

production 차단 사유는 원격 PG runtime, 실제 Storage 전송, 운영 Auth·provisioning/상태 동기화, **Vercel/Render edge 신뢰·limits·HTTPS 미실증**, cloud worker, 통합 백업·복구 미실증이다. 설정 flag로 해제할 수 없다. provider·서비스 가입/Secret 설정·자원·공개 전환은 이번에 수행하지 않았다.

운영 연결 전 승인된 Vercel/Render/Supabase 프로젝트·도메인/정확 Origin·서버 전용 비밀 관리·최소권한 DB/Storage/auth 계정·private bucket/RLS·worker 역할·provider subject와 최초 기관 관리자 확인, 검증된 gateway와 ingress/health probe 경로, 실제 body/timeout/rate/cookie/header 전달, 상태 동기화/재검증·백업/복구/RPO/RTO가 필요하다.

다음 권고는 **실제 원격 전송 구현 및 staging 연결 전 체크리스트/대상 경로 확정**이다. 특히20MiB 업로드와 서버 전용 edge 증명을 만족하는 proxy 선택이 먼저다. 실제 외부 호출/서비스 신청/배포는 별도 승인 후에만 가능하며 이번 종료 후 자동 진행하지 않는다.

보존 커밋09:06:19 UTC 이후 약23분(사전 검사 제외). 정확 종료 시각/분·변경 수·source hash·소유 PG 종료 상태는 PRESERVATION.json에 기록한다. 새 wiring 변경은 미커밋 검토 후보로 남기고 배포 준비5단계에서 종료한다.
