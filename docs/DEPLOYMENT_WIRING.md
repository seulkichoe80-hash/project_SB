# 배포 준비 5단계 — Local/Fake Wiring·HTTPS 경계

범위는 기존 API/worker 진입점에 **명시 local/Fake 조합**을 연결하고, 단일 정제 프록시 홉과 BFF 세션 정책을 로컬에서 검증하는 것이다. Vercel/Render 배포·실 Supabase·원격 DB/Auth/Storage 호출은 없다. FR-18/NFR-01·02·05·06·07, WEB-02/04/05 및 [설정](DEPLOYMENT_PREFLIGHT.md)·[PG](DEPLOYMENT_POSTGRES.md)·[Storage](DEPLOYMENT_PRIVATE_STORAGE.md)·[Auth](DEPLOYMENT_AUTH.md) 계약을 재사용한다.

## API·worker 선택 경로

`apps/api/runtime_wiring.py`의 RuntimeBinding은 data_dir/repository/store/role과 API 전용 provider/AuthSettings/ProxyPolicy/SessionRevalidation을 명시 결합한다. 임의 env flag로 Fake/원격 provider를 생성하지 않는다.

- API `create_app(runtime_binding=binding, parsing_enabled=True)`는 기존 별도 store/repository/provider 설정과 혼합을 거부한다. 역할 api·data_dir·private store 소유 repo·Auth와 Storage project·proxy origin/cookie 정합을 검증한다. 기존 factory 호출·표준 deny-all/SQLite/Local 저장소 기본은 유지한다.
- `binding.worker('parse_worker'|'chunk_worker'|'workflow_worker')`는 repo/store를 공유하고 브라우저 Auth/provider/프록시 증명/상태 transport를 제거한 별도 역할을 만든다. cookie/Origin 값은 비교용 정책일 뿐 worker가 브라우저 로그인이나 관리자 역할을 발급하지 않는다.
- parse/chunk/workflow 실제 main 진입점은 공통 `worker_documents`를 사용한다. 기존 CLI 인수/PG loopback 선택/lease·heartbeat·timeout·once 계약은 유지한다. 명시 `runtime_binding=` Python 인자로 Fake 조합을 주입할 수 있으나 직렬화된 임의 binding/환경 변수로 활성화하지 않는다.
- Fake worker는 API에서 파생한 peer가 필수다. 시작/claim 전에 DB(backend/host/port/database/**schema**, SQLite 경로), 원본 저장소(로컬 root 또는 project/bucket/**같은 Fake 인스턴스**), data_dir/AuthSettings가 같은지 검사한다. 설정만 같은 별도 메모리 객체를 공유 저장소로 인정하지 않는다.
- 독립 프로세스의 기존 local/PG+Local CLI는 같은 --data-dir/--postgres-schema/loopback DSN을 사용해야 한다. **Fake 객체 저장소는 독립 프로세스나 재시작 간 영속성을 제공하지 않는다.** 실제 private Storage transport/cloud worker wiring은 여전히 미완료다.
- `peer_issues`는 기존 RuntimeSettings의 DB target/공통 정책 외에 proxy hops·request timeout/rate·LLM 상한도 비교한다. DB 자격증명은 최소권한 user별로 달라도 되며 실제 data target을 비교한다. typed ProxyPolicy는 명시 binding에서 사용하며 선언된 env 설정만으로 원격 adapter/프록시 신뢰를 활성화하지 않는다.

| 구성 | 실제 검증 범위 | 운영 미완료 |
|---|---|---|
| SQLite/Local | 기존 API/독립 worker 기본값·영속 파일 | 컨테이너 로컬 디스크를 운영 원본 저장소로 사용 금지 |
| PostgreSQL | 실제 격리 loopback PG, API/worker 공유 schema·기존 회귀 | production runtime/계정/권한/실 DB·pool 실증 |
| Private Storage | 불변 Fake 객체·같은 인스턴스 공유 | 실 Supabase 전송/ACL/다중 프로세스 |
| Auth | 기존 BFF + Fake JWKS/password 서명 검증 | 새 JWT/JWKS 실 전송/계정·프로젝트 호환/초기화 |
| 이전 GET /user HTTP adapter | 기존 구현·모의 회귀 보존 | 이번 단계 미호출, 운영 wiring/실 연결 미검증 |
| Proxy | 실제 로컬 TLS 입구 + ASGI edge/API 경계 | Vercel/Render 실제 proxy/제한/신뢰 증명 |
| Provider session status | 정확한 Fake transport만 | 실 provider 이벤트/상태 동기화·신선도/장애 정책 실증 |

## 단일 정제 홉·HTTPS

`apps/api/proxy_boundary.py`의 ProxyPolicy와 ProxyBoundary는 opt-in이다. 기존 Vite/local API 개발 흐름을 바꾸지 않는다. 운영까지 검증된 공급자 gateway가 아니다.

1. 외부 입구는 정확한 HTTPS origin/Host와 `/api/` 경로만 받는다. `/apievil`·HTTP·잘못된 Host/중복 보안 헤더/명백한 경로 조작을 거부한다. `/api` prefix 한 번을 제거해 backend 경로로 보낸다.
2. 입구는 클라이언트의 Forwarded/X-Forwarded-*/프록시 증명/hop-by-hop 헤더를 제거한다. 즉시 연결의 실제 client IP에서 새 단일 X-Forwarded-For를 만들고 고정 public Host/https 및 **서버 전용 증명**을 설정한다. Origin/CSRF/Cookie/Authorization은 전달하되 BFF는 bearer를 권한으로 사용하지 않는다. 서비스 키를 Authorization에 자동 삽입하지 않는다.
3. API 경계는 **허용 immediate peer CIDR + constant-time 공유 증명**을 모두 검사한다. `/0`이나 넓은 범위는 거부하고 IPv4 /24 이상·IPv6 /64 이상만 허용한다. 고정 backend Host, 정확 public X-Forwarded-Host/proto=https, 쉼표 없는 단일 IP를 확인하며 다른 forwarded/header 체인은 거부한다. 검증 후에만 ASGI scheme/server/client를 정규화하고 증명/forwarded 헤더를 앱에서 제거한다.
4. origin은 worker/browser 입력이 아닌 서버 정책이다. unsafe 요청은 정확한 Origin 필수, 다른 Origin/cross-site는 거부한다. 기존 Auth의 CSRF도 별도로 검사한다. 공개 CORS/와일드카드는 추가하지 않는다.
5. 쿠키는 기존 __Host·Secure·HttpOnly·SameSite=Lax·Path=/를 유지하고 여러 Set-Cookie를 합치지 않는다. 응답 redirect는 따라가지 않는다. 허용된 같은 origin/상대 경로만 `/api`로 다시 연결하며 외부/HTTP redirect는 거부한다.
6. 선언 Content-Length와 실제 bytes/unknown-length stream을 모두 확인한다. 기본20MiB(최대20MiB), 초과413. CL/TE 혼용·잘못된 framing 거부. bounded request/response buffer, body deadline, upstream deadline, 고정 오류를 사용한다. 진행 중 DB/worker가 proxy timeout만으로 취소/rollback됐다는 보장은 없으며 기존 idempotency/상태 조회·claim fencing을 사용해야 한다.
7. API 경계의 요청 제한은 IP hash별 process-local/최대1000 key, 기본30회/분, 429/Retry-After다. 분산 영속 rate limit/DoS 보호나 vendor 제한 실증은 아니다.

**필수 시작 조건:** trusted forwarding을 먼저 처리하는 다른 미들웨어를 넣지 않는다. Uvicorn은 `proxy_headers=False` 또는 `--no-proxy-headers`로 실행해야 하며 `--forwarded-allow-ips='*'`를 사용하지 않는다. 즉시 peer를 이미 바꿔버린 서버 설정에서는 경계 검증을 보장할 수 없다. 로컬 TLS harness는 이 설정을 실제 사용한다. 실제 Render/Vercel 앞단의 헤더 동작과 origin 방화벽/인증된 gateway는 미검증이라 production blocker를 유지한다.

OfflineSameOriginProxy는 **네트워크 client가 없는 ASGI 시험용 edge**다. 이를 Vercel deployment adapter로 표시하지 않는다. 로컬 TLS 입구 이후 backend는 in-process ASGI이며 Render의 TLS·네트워크·서비스 인증을 시험하지 않았다.

## Vercel /api → Render 이전 조건

- 프런트는 기존 `/api` 상대 경로를 유지한다. 별도 browser→Render 공개 CORS를 열지 않는다. 실제 domain·exact origin/backend Host·고정 upstream HTTPS·secret-manager 증명·edge egress identity를 승인된 배포에서 구성해야 한다.
- 정적 rewrite와 Vercel Function proxy는 다르다. Function 경로는 알려진 약4.5MB body 제한 등 플랫폼 제약이 있을 수 있다. **이번20MiB 로컬 성공은 Vercel20MiB 통과를 뜻하지 않는다.** 사용 plan/경로/스트리밍/Render 상한을 실증하고 부족하면 승인된 별도 same-origin gateway/업로드 설계를 정해야 한다. 제한을 우회해 공개 bucket·장기 signed URL/서비스 키 노출로 해결하지 않는다.
- 비밀 헤더를 공개 vercel.json/프런트 번들에 넣지 않는다. Render 직접 접근은 고정 Host만으로 보호하지 못하므로 실제 신뢰 peer+증명/검증된 origin gateway·health probe 경로를 설계해야 한다. 증명 회전/유출 대응·provider IP 변경도 운영 절차다.
- actual edge의 timeout/redirect/Authorization·Cookie/Set-Cookie 전달·no-store·TLS·secure cookie·20MiB 경계·request limit·로그/APM 마스킹을 별도 승인 후 확인한다. 이번에는 계정/Secret/env/리소스/배포 설정을 변경하지 않았다.

## 세션 재검증·철회

`SessionRevalidation(FakeIdentityStatusTransport(...), max_seconds=...)`는 opt-in Fake 계약이다. 새 JWT RuntimeBinding은 이를 필수로 요구한다. 기존 직접 주입/deny-all 개발 경로는 호환 유지한다.

- 새 BFF 수명은 AuthSettings/provider JWT 남은 수명/정책 상한(60..1800초) 중 최소다. idle 상한도 유지하고 성공 요청으로 절대 만료를 연장하지 않는다. 합성 wiring 검사는300초 상한을 사용한다.
- 매 protected 요청마다 서버 identity issuer/subject로 Fake provider 상태를 재확인한다. JWT·password를 세션 DB에 저장하거나 브라우저에서 재전송하지 않는다. unknown/장애는503으로 거부하고 touched/유효기간을 연장하지 않는다.
- disabled/deleted는 기존 SID를 DB에서 revoked로 **커밋한 뒤**401을 반환한다. provider를 다시 active로 바꿔도 옛 SID는 살아나지 않으며 명시 새 로그인이 필요하다. 신규 로그인도 active 확인 실패 시 거부한다.
- 서버 identity/org/membership 비활성은 기존 즉시 거부다. 로컬 membership이 이미 무효이면 provider 장애가 있어도 인증하지 않는다. worker에는 browser provider/session transport를 전달하지 않는다.
- provider 장애만으로 모든 SID를 영구 철회하지는 않는다. 장애 중 요청은503, 복구 후 아직 만료/철회되지 않은 세션만 다시 검증해 사용할 수 있다.

**실제 운영 구현 아님:** 실제 provider 상태를 어디서 받는지(승인된 이벤트/webhook·신뢰된 동기화/상태 freshness·필요한 계정조회)는 미구현이다. Fake 상태 조회는 DB transaction 안의 짧은 메모리 작업이며 여기에 네트워크 호출을 그대로 끼워 넣어 장시간 DB lock을 만들면 안 된다. 실 운용에서는 freshness 상한/누락·재처리/장애 시 fail-closed/로그·재인증 요구와 철회 영속성을 별도 설계·검증해야 한다. 기존 guard 없는 local BFF를 운영 철회가 구현된 것으로 간주하지 않는다.

## 재현 명령·증거 경계

기존 가상환경·잠금파일 사용, 새 설치/환경 설정 변경은 없다. PG fixture 시작은 이전 PG 계약을 따른다. 명령은 새 출력/작업 경로를 사용해 과거 증거를 덮어쓰지 않는다.

```bash
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test .venv/bin/python -B -m unittest discover -s tests -p test_deployment_wiring.py
.venv/bin/python -B scripts/validation/check_deployment_wiring_tls.py --data-dir work/my-new-loopback-tls
SB_PG_TEST_DSN=postgresql://postgres@127.0.0.1:55432/sb_test .venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output outputs/my-new-wiring-backend.json
.venv/bin/python -B scripts/validation/deployment_preflight.py
```

TLS harness는 새 Git 제외 private work 디렉터리(0700)에 시험용 leaf key/cert/CA cert(0600)를 생성한다. 실제 계정·운영 키가 아니며 leaf key를 Git/일반 보고에 넣지 않는다. 자체 loopback listener만 시작/중지하고 CA/hostname 검증을 켠 httpx로 접속한다(verify=False 사용 안 함). 미신뢰 CA 실패도 확인한다. provider/Storage는 Fake, upstream은 ASGI다. 실제 브라우저/실 Vercel·Render·운영 Auth 성공을 주장하지 않는다.

전체 backend는 Phase Gate로 새 실행하며 Python 비루프백 guard + PG local_test 강제를 병행한다(C libpq는 Python guard 범위 밖). UI/API 응답/DB schema·원본·fixture·기존 assertion은 변경하지 않는다. 인간 판정·의미 검증/승인을 생성하지 않는다. production은 아직 미실증 PG/Storage/Auth/proxy/cloud-worker/통합 복구 조건으로 계속 차단된다.
