# 배포 준비 6단계 — 스테이징 후보·공식 제약·실행 준비

확인일 **2026-10-18 KST**. 문서/설계 단계다. 운영 code/schema/설정·Secret·서비스는 변경하지 않는다. 기존 PRD FR-18/NFR-01·02·05·06·07·WEB-02/04/05 및 [G1-C/D](G1_GATES.md), [단계5 계약](DEPLOYMENT_WIRING.md)을 유지한다. **스테이징 아키텍처 최종 확정·공개 허용은 BLOCKED**다.

## 증거 등급과 접근 결과

- **공식 소스 확인:** 공급자 공식 저장소의 특정 commit 파일을 실제 HTTP200으로 읽고 SHA/줄 위치를 기록했다. 공식 웹사이트 현재 배포본/사용자 계정 설정·실제 연결 성공과는 다르다.
- **접근 BLOCKED:** vercel.com/render.com/supabase.com 문서 사이트 GET에서 inherited HTTPS proxy의 ProxyError를 관측했다. TLS 검증/프록시를 끄거나 우회하지 않았다. GitHub 공식 Supabase 저장소의 허용된 공개 경로를 사용했다.
- **계정 미확인/실행 미검증:** 요금제·region·quota·실 endpoint·20MiB 인터넷 E2E는 확인하지 않았다. 접근 불가 항목을 VERIFIED로 표시하지 않는다.

공식 Supabase source commit: `7425d4930528931400fb3e656e860b1094cb224e`. [소스24건·문서 판단16건](../outputs/deployment-staging-prep/OFFICIAL_SOURCES.json), [접근 상태](../outputs/deployment-staging-prep/ACCESS_STATUS.json). 원문 cache는 Git 제외 work/deployment-staging-preservation/에 보존하고 Git에는 URL/commit/SHA/짧은 요약만 기록한다. 문서의 예시 코드를 실행하지 않았다.

## 공식 근거로 확인한 제약

| 항목 | 확인한 공식 내용 | 이번 프로젝트 판단 |
|---|---|---|
| Supabase direct/session pooler | persistent IPv6/IPv4 add-on은 direct, IPv4-only는 shared session5432. migration/pg_dump는 direct 권장 [SB-DB] | Render outbound IP 버전 미확인. direct IPv6 또는 session pooler를 조건부 검증하고 Dashboard endpoint를 그대로 사용 |
| transaction pooler6543 | prepared statement 미지원 [SB-PREPARED] | 현재 psycopg 연결의 준비문 정책/복원 반복SQL을 검증하지 않아 기본 채택 금지. serverless pooler를 장기 worker에 자동 선택하지 않음 |
| private bucket/ACL | private 기본, 다운로드도 RLS, service key는 RLS 우회 [SB-PRIVATE/SERVICE-KEY] | private 선언만으로 기관 격리/WORM 보장 안 됨. 서버 membership/path/SHA 검증과 실제 권한 시험 필수 |
| 파일 크기 | Free 최대50MB, Pro이상 최대500GB; global/bucket 제한 별도 [SB-FILE] | 20MiB=20,971,520B는 문서상 Free 최대치보다 작지만 실제 계정/bucket 설정은 미확인. 앱20MiB 상한 유지 |
| 큰 파일 전송 | standard는6MB 이하에 적합, 큰 파일은TUS resumable 권장 [SB-LARGE] | 직접/서버 업로드 모두 복구·read-back 검증 필요. 업로드 방식의 기술상한과 plan/bucket/app 상한을 혼동하지 않음 |
| TUS URL | upload resource URL 최대24h [SB-TUS] | signed token TTL/권한 철회/짧은 일회용 capability를 보장하는 수치가 아님 |
| JWKS | edge10분 cache, client 추가 cache 가능 [SB-JWKS] | Fake에서 매번 fetch해도 실제 edge 캐시의 즉시 키 철회 보장은 못 함. 회전 overlap/cache bust/장애 기준 필요 |
| 사용자 삭제/ban | 삭제 후 기존 access JWT는 exp까지 유효할 수 있음. temporary ban도 기존 session 철회 대체 아님 [SB-DELETE/BAN] | JWKS 서명만으로 현재 계정 상태 확인 불가. 서버 membership·상태 신선도·BFF SID 철회 필요 |
| Auth 세션 제한 | provider time-box/idle/single-session 기능은 Pro이상, refresh 때 적용 [SB-SESSIONS] | 기존 앱 BFF TTL/idle·세션 철회를 provider 기능과 별개로 유지 |
| 백업 | Pro daily DB7일, Storage object bytes 미포함. custom role password는 별도 복구 필요 [SB-BACKUP/PRO-RETENTION] | DB+원본 객체+manifest+비용 schema+Auth identity 관계의 별도 일관 복구 필수 |
| 비용 | 공식 가격 화면 소스 Free0/Pro From25 USD/월, one Micro 포함. Free1주 비활동 중단/active project2개 제한 [SB-PRICE] | 계정 견적·세금·추가 project·초과/옵션은 별도. Free를 공모전 상시 안정성 보장으로 선택하지 않음 |
| Spend Cap | Pro 일부 usage만 제한, compute/IPv4/PITR 등 제외 [SB-CAP] | 총액 hard cap으로 간주 금지. 별도 예산 승인/알림/작업 cap 필요 |

SB-ID의 pinned URL·줄 번호는 OFFICIAL_SOURCES.json을 따른다. 문서 소스의 plan 정보가 실제 사용자의 현재 결제 조건임을 확인한 것은 아니다.

## 아직 공식 확인이 막힌 항목

| 대상 | 필요한 공식 페이지 | 상태/해제 조건 |
|---|---|---|
| Vercel static hosting·external rewrite | https://vercel.com/docs/rewrites | BLOCKED_DOCUMENT_ACCESS. /api external rewrite의 요청/응답/body/timeouts·헤더 전달/비밀 주입·plan 적용 확인 필요 |
| Vercel Function | https://vercel.com/docs/functions/limitations | BLOCKED. 과거 단계의 약4.5MB는 이번 확인한 최신 수치가 아니다. 20MiB 요청·응답 통과 판정 금지 |
| Vercel plan/이용목적/좌석·usage | https://vercel.com/pricing /docs/plans | 현재 가격·Hobby의 기관/이용목적 적합성·Pro 좌석 과금 미확인. 기존 예산 가정을 최신 견적으로 재사용하지 않음 |
| Render web/worker·free/paid 상시 실행 | https://render.com/docs/web-services /docs/background-workers /docs/free | sleep/시간·worker 사용 가능 plan·재시작·CPU/RAM/ephemeral disk 조건 미확인. Free 상시 실행을 보장하지 않음 |
| Render outbound/TLS/health | https://render.com/docs/outbound-ip-addresses /docs/health-checks | IPv4/IPv6·고정 egress·TLS termination·forwarded peer·health probe 조건 미확인 |
| Render request/response·limits/요금 | https://render.com/pricing | API20MiB 요청/다운로드·timeout/traffic·plan 단가 모두 미확인 |
| Supabase 실제 project/plan | https://supabase.com/pricing 및 승인 후 사용자 Dashboard | 공개 source는 확보. 실제 project의 bucket cap/DB연결 수/region/현재 invoice/SMTP 제한 등은 미확인 |

직접 문서 사이트 접근 재검증에는 환경 설정의 문서 host `vercel.com`, `render.com`, `supabase.com` 허용 상태 확인이 필요하다. 현재 network/Secret draft나 실제 환경 설정은 바꾸지 않았다. 다른 환경에서 공식 본문/확인일을 제공받아도 source provenance를 기록해야 한다. 서비스 계정 접근 승인은 문서 GET 허용과 별개다.

## A/B/C 비교와20MiB 경로

| 대안 | 장점 | 필요한 변경·보안/운영 위험 | 비용·채택 상태 |
|---|---|---|---|
| A Vercel /api → Render | 기존 상대 `/api`/same-origin BFF·쿠키/CSRF 재사용 | static external rewrite와 Function proxy를 구분.20MiB 업로드 **및 원본 다운로드**, proof 주입/직접 origin 차단·forwarded 신뢰·deadline을 검증해야 함 | Vercel/Render 단가·usage/상한 미확인. **기본 설계 확정 보류** |
| B 별도 API domain | 업로드/다운로드 bytes가 Vercel proxy를 통과하지 않음. 기존 서버 검증/불변 등록·원본 반환 계약 재사용 | `app.example`/`api.example`처럼 HTTPS **같은 site의 custom domain** 우선. 정확 credentialed CORS/Host와 browser Origin 분리/CSRF/Vary·proxy 신뢰 계약 추가 필요. 현재 코드에 이 ingress가 구현된 것은 아님 | domain+Render 서비스+Supabase. 가격/Render20MiB 통과 미확인. **20MiB 우선 검증 후보** |
| C 서버 승인 private Storage 직접 업로드 | Vercel 요청 본문 병목 제거. 공식 문서상20MiB 수용 후보, TUS 복구 가능 | 새 intent/제한 capability/서버 read-back·SHA·MIME/zip 검증·finalize·orphan 격리·멤버십 재확인 필요. browser에 provider JWT/서비스 키 금지. capability TTL/회수/재사용 실제 계약 미확인 | 대역폭/Storage·추가 API 구현 비용. **후속 후보, 현재 기능/기본값 아님** |

**이번 권고:** A로20MiB를 확정하지 말고, 기존 원본 검증을 재사용하는 **B의 같은-site API 직통 경로를 먼저 검증**한다. Render의 body/response/timeout/plan·same-site domain·정확 CORS 및 신뢰 경계를 확인하기 전 배포 구성으로 채택하지 않는다. C는 더 큰 파일/불안정 전송 대응의 후속 대안으로 별도 설계한다. 세 대안 중 전체 E2E가 검증된 것은 없다.

B에서 주의할 점:

- Vercel 기본 domain과 onrender.com은 서로 다른 site다. 현행 SameSite=Lax가 cross-site fetch를 해결하지 않으며 SameSite=None만 바꾸는 것도 third-party cookie 차단을 해결하지 못한다. user-controlled custom domain/DNS·exact API host·frontend Origin을 별도 검증한다.
- __Host cookie는 API host-only/Domain 없음·Secure·HttpOnly 유지. fetch credentials 포함, Allow-Origin exact(와일드카드 금지)·Allow-Credentials·Vary Origin,Cookie·CSRF를 함께 설계한다. CORS는 권한/기관 검사를 대신하지 않는다.
- 현재 ProxyPolicy는 public Host/Origin이 같은 단일 정제 홉이다. B에는 API Host와 browser Origin의 분리, 실제 Render ingress peer/TLS 처리, 전용 테스트가 필요하다. 단순 VITE_API_BASE_URL 변경으로 완료되지 않는다.
- React 정적 파일을 API와 같은 origin에서 제공하는 별도 fallback도 검토 가능하나 static mount/캐시/라우팅·Render 조건·비용을 새로 검증해야 한다. 자동 전환하지 않는다.

C에서 주의할 점:

- 작은 서버 승인 요청은 현재 BFF+CSRF+기관 manager 기준. object 경로/UUID·bucket·크기/format은 서버가 고정하고 최소권한 업로드 capability만 허용한다. token은 저장/로그/referrer에 남기지 않는다. 실제 signed upload TTL을 확인하기 전 임의로60초·즉시 회수가 가능하다고 약속하지 않는다.
- TUS URL 수명24h와 signed token 권한 수명은 다르다. 로그아웃/관리자 취소 뒤 native upload가 계속 가능할 수 있으므로 **미게시 quarantine 경로**에만 기록하고 expired/cancelled intent는 finalize하지 않는다. 최종 원본에는 임의 overwrite/upsert/delete를 허용하지 않는다.
- 브라우저 SHA/size/MIME만 믿지 않는다. 서버가 bytes를 다시 읽어 기존 inspect_file/SHA/크기·기관·버전 검증을 수행한 뒤 기존 문서/작업/EvidenceRef 계약에 게시한다. DB 실패/응답 유실/orphan은 이전 보상 계약을 따른다. 이는 새 구현 범위다.
- C는 업로드만 해결한다. **기존20MiB 원본/PDF 조회의 다운로드 경로가 A에 남으면 response 제한도 해결해야 한다.** 장기 다운로드 signed URL·public bucket으로 우회하지 않는다. 단기 다운로드 URL도 세션 철회와 별도 bearer 권한이라 별도 정책/승인 대상이다.

## 서비스 구성·비용

현행 실행기를 그대로 분리하면 React static1, Render API1, parse/chunk/workflow background **3개**, Supabase staging project1(DB/Auth/private Storage)과 별도 암호화 백업 저장소·domain/DNS가 필요하다. worker3개를 하나로 합치는 supervisor/스케줄러는 미구현이며 parse/workflow의 os._exit timeout을 한 프로세스에 단순 합치면 전체 worker를 종료시킬 수 있다.

| 항목 | 이번 확인한 값 | 예산 사용 방식 |
|---|---|---|
| Supabase Free | 공식 source $0, DB500MB/file Storage1GB, 비활동1주 pause/active project2 | 초기 합성 테스트 후보. 지속 시연 안정성/자체 백업·프로젝트 설정 별도 |
| Supabase Pro | 공식 source From$25/월, one Micro·100GB Storage·daily DB7일 | 전용 org/단일 project 예시의 출발점. 실제 견적·세금·usage/추가 project 별도 |
| Compute | 문서 $10 org credit, Micro $0.01344/h 약$10/월 | Pro$25에 포함된 compute를 무조건 중복 합산하지 않음. 기존 org의 project/credit 사용량 미확인 |
| Vercel | 최신 가격·이용목적/좌석/usage 미확인 | V(미정). 과거 단계의 단가를 최신 값으로 재사용 금지 |
| Render API/worker | 최신 plan 단가·계속 실행 조건 미확인 | R_api+R_parse+R_chunk+R_workflow(각 미정) |
| domain/backup/egress/PITR 등 | 실제 구성·견적 미확인 | D+B+E+옵션+세금(미정). Supabase Spend Cap이 compute/PITR/IPv4 등 전체를 막지 않음 |

전체 예산은 `V + R_api + R_parse + R_chunk + R_workflow + Supabase실계정청구 + D + B + E + 옵션/세금`이다. **확정 총액 없음.** 예산 승인 전 가입/upgrade/add-on·auto-scaling·유료 호출을 실행하지 않는다. LLM/embedding은 기존 false/예산0을 유지한다.

## 계정·설정·권한 준비표

사용자가 실제 연결 승인 전에 안전한 provider console/secret manager에서 준비할 항목이다. 채팅/Git/문서에 값 입력 금지.

1. GitHub의 승인된 staging branch/배포 대상·owner, Render workspace 및 API/worker 역할, Vercel project/이용목적·좌석/과금 동의. Git 연결이 auto-deploy를 활성화하면 공개 변경이므로 승인 전 켜지 않는다.
2. 실제 plan·region·API/worker 개수/CPU·RAM/egress/월 예상청구·무료 pause/보관 제약 확인. domain 소유/DNS 변경 승인과 staging 접근제한/테스트 담당자 지정. 공식 조건·account screenshot에는 key/개인정보를 제거한다.
3. Supabase 전용 staging project·region, DB runtime/migration 계정 분리. API/worker 최소권한·application/budget schema 지정, direct/pooler endpoint는 Dashboard에서 복사한다. IPv6/IPv4/CA·sslmode=verify-full 연결을 승인 후 검사한다.
4. private original/quarantine bucket·global/bucket20MiB cap·허용 MIME·버전/기관 prefix·access 정책. service key가 RLS를 우회하므로 app 검사/역할/credentials의 범위를 실제 검증한다. public bucket/upsert/delete 금지. 원본 보존·orphan/백업 운영자 별도 지정.
5. Auth asymmetric ES256/RS256/JWKS 실제 응답·issuer/audience·key rotation/cache·사용자 상태 동기화·초대/SMTP 제한·JWT/BFF TTL 확인. 가입/이메일 도메인으로 기관·관리자 자동 부여 금지. 최초 계정 subject를 검증한 뒤 기존 명시 bootstrap 절차로 기관/manager를 별도 등록한다.
6. 현재 loader 이름: APP_ENV/APP_ROLE, DATABASE_BACKEND/DATABASE_URL, STORAGE_BACKEND/STORAGE_PROJECT_URL/STORAGE_BUCKET/STORAGE_SERVER_KEY/STORAGE_PRIVATE, AUTH_PROVIDER/SUPABASE_PROJECT_URL/SUPABASE_AUTH_API_KEY, APP_ORIGIN/SECURE_COOKIE/CSRF_ENABLED/SAME_ORIGIN_PROXY/TRUSTED_PROXY_HOPS, MAX_UPLOAD_BYTES/REQUESTS_PER_MINUTE/REQUEST_TIMEOUT_SECONDS, BACKUP_STRATEGY/RESTORE_RPO_HOURS/RESTORE_RTO_HOURS, REAL_* false/예산0. [정확 변수명](DEPLOYMENT_PREFLIGHT.md). **설정 존재와 원격 wiring 동작은 다르며 production은 계속 차단한다.**
7. 향후 별도 구현할 후보: migration 전용 URL·app/budget schema 설정, API public Host와 browser Origin 분리, 실제 proxy 증명/peer source, 상태 freshness/복구 bootstrap. 이 이름들을 현행 env loader가 이미 지원한다고 표시하지 않는다. PGSSLROOTCERT 같은 libpq CA 경로도 배포 mount/설정 실증 필요. 현재 DSN validator가 허용하지 않는 추가 query를 임의로 붙이지 않는다.
8. worker에는 browser session/JWT·Auth bootstrap/proxy 증명을 주지 않는다. 원본 조회/작업 처리에 필요한 최소 credential만 제공하고 APP_ROLE/기관 범위/DB target/bucket을 일치시킨다. 실제 최소권한이 가능한지 검증 전 service key를 read-only로 간주하지 않는다.

## Migration·배포·복구 순서(실행 안 함)

1. 담당자·예산·source artifact SHA/lockfiles·승인된 합성 자료/원본 hash·private staging 접근 정책을 동결한다. 기존 DB/객체/manifest/비용 원장·Auth mapping 백업을 확보한다.
2. **새 격리 staging schema**에 migration role로 application001, budget001을 각각 명시 적용하고 체크섬·schema_extensions를 검증한다. Supabase managed auth/storage schema를 앱 baseline으로 덮어쓰지 않는다.
3. Storage001 독립 버전/체크섬을 준비한 뒤 private bucket/transport/read-back·기관 path·실 권한을 검증한다. runtime user가 startup에서 DDL을 수행하지 않도록 migration/verify 경로를 분리 검증한다. 기존 SQLite/원본은 이관 후에도 보존하고 운영 덮어쓰기 migration/rollback을 금지한다.
4. API/worker runtime connection target과 schema·bucket의 같은 실제 project를 확인한다. direct migration endpoint와 pooled runtime host가 다르다는 사실을 단순 문자열 동일성으로 해결하지 않는다. psycopg prepare/SSL/CA·connection budget을 API replicas+3worker+operator 합계로 제한한다. 현재 전역 transaction_guard 잠금의 처리량 한계도 확인한다.
5. Auth 실제 전송·상태 동기화/신선도·최초 승인 기관/계정·서버 membership을 준비한다. 일반 manager/reader·외부 issuer·disabled/deleted·cross-tenant·CSRF/Origin/session revoke를 비공개 staging에서 확인한다. provider JWT 서명 통과만으로 publish/운영관리자를 생성하지 않는다.
6. 선택한 ingress의 HTTPS/Host/Origin/프록시 신뢰·health probe·body/response20MiB·cancel/deadline/429·Cookie/redirect/CORS·secret log·캐시를 실제 환경에서 시험한다. 설정/실 연결/인터넷 E2E를 별도 기록하고 모든 필수 게이트 전 공개하지 않는다.
7. API·parse/chunk/workflow worker를 순서대로 올려 합성 등록→근거/미승인 workflow까지 검증한다. readiness는 DB/객체/Auth·worker heartbeat/lease/retry/connection limit을 포함해야 한다. 현재 Fake boundary는 이 운영 readiness를 대체하지 않는다.
8. 복구 시 신규 작업 중지→worker drain/fence→대상 schema/객체 inventory/manifest 시점 대조→새 대상 restore→hash/기관/버전·generation 검증→세션 전부 철회/비용 uncertain hold 정산→재개를 따른다. managed DB 백업은 객체 bytes를 복원하지 않으므로 별도 encrypted copy/보관/키복구가 필수다. 실제 PITR/객체/RPO·RTO는 미검증이다.

## 배포 승인 게이트와 최소 후속 단위

현재 production blocker를 하나도 해제하지 않는다. 다음이 모두 필요하다:

- 공식 Vercel/Render 문서·현재 선택 plan·두 방향20MiB 경로/조건 확인.
- 실제 HTTP Storage/JWKS/provider 상태/계정·runtime wiring, API/worker schema/권한·private bucket/RLS·원본/근거 검증.
- 새로운 ingress의 Cookie/CSRF/Origin/Host/CORS·TLS/forwarded/proxy 증명과 취소/timeout·로그/예산·health 검증.
- 비용 schema/Auth mapping 포함 coordinated backup/restore·immutable originals·tenant/세대/worker fencing·합성 E2E·담당자 확인.
- 계정 생성/유료 신청/credential 주입/서비스 연결 테스트·DNS·자동배포 연결·staging 노출·push는 각각 범위/예산/데이터/담당자 승인을 받고 실행. 비밀값은 secure console만 사용.

**다음 최소 구현 제안:** 기존 문서 등록 계약을 보존하는 실제 Storage HTTP transport를 먼저 httpx.MockTransport만으로 검증(실제 호출0, 원본 hash/길이/upsert=false/timeout·응답 유실/orphan·최소권한·기관 경계, production 차단 유지). 병행 선행조건은 공식 host 접근/계정 plan 검토다. ingress B/C 구현과 공개 staging은 호스팅 제약 확인 및 별도 요청 후에 진행한다. 이번에는 어느 후속 구현도 시작하지 않는다.

이번 산출물은 문서·근거뿐이다. TEST_PLAN의 문서-only 기준으로 링크/source SHA·요구사항/안전성·Git 보존을 검사하며 전체 backend/TLS/브라우저를 새 실행하지 않는다. 이전1,031 PASS/TLS15는 source hash가 같은 **과거 증거**로만 참조한다. 문서 접근 BLOCKED를 환경 또는 기능 PASS로 바꾸지 않는다.
