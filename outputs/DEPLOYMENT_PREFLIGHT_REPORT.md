# 배포 준비 1단계 완료 보고

작성일: 2026-10-18 KST. 범위: 운영 설정·시작 계약·오프라인 사전 검사. 저장소 품질검증 스킬에 따라 시작 경로 영향 회귀 및 전체 backend를 실행했다. G1-C 배포 준비 완료/실제 연결 성공은 선언하지 않는다.

## 1. 기존 변경 보존

시작 브랜치 feat/v03e-human-review-support, HEAD e2bb7f769cb425edbe06b375595eaf839440f004. 이전 보존 manifest 68파일을 대조했고, 그 후 추가된 배포 계획·검사 기록2파일과 TASKS의 계획 절 추가를 확인했다. 따라서 이번 보존 커밋은70파일이며 미확인 파일을 임의 포함하지 않았다. 내용 출처는 D 선택검색·회귀 증거, E 합성 인간검토 자료와 도구, 사용자 승인한 배포 계획이다. 대상 키 패턴 검사0건이며 완전한 개인정보 인증으로 표현하지 않는다. 실제 운영 자격증명은 주입/검사하지 않았다.

**보존 커밋: 3453eecd3f35f78ece116cb53399ba014f1151c9**. 이 커밋은 기존 브랜치에 로컬로 생성했고 feat/deployment-preflight를 분기했다. ignored 빈 judgments.csv는 Git 규칙을 유지하며 별도 local archive에 함께 보존했다. archive·SHA 목록: work/deployment-preflight-preservation/baseline.tar.gz, baseline-files.json. 기존 snapshot도 보존했다. 변경된 검토 결과·인간 승인 없음.

## 2. 변경 파일

신규:

- apps/api/runtime_settings.py: strict/frozen RuntimeSettings, 허용 환경키 로더, 비밀 마스킹, 정책/쌍 검사, code-owned blockers, 시작 guard.
- scripts/validation/deployment_preflight.py: offline CLI, 안전 JSON 입력/정적 오류, exit0/1/2.
- tests/test_deployment_preflight.py: 신규40테스트, 다수 부정 하위사례.
- docs/DEPLOYMENT_PREFLIGHT.md: 전체 변수·시작/정책·제한·명령 계약.
- outputs/DEPLOYMENT_PREFLIGHT_REPORT.md 및 outputs/deployment-preflight/*: 새 검사 증거.

수정:

- apps/api/main.py: create_app의 저장소/transport 초기화 전 api guard2줄.
- apps/api/worker.py, chunk_worker.py, workflow_worker.py: 각 CLI의 저장소 생성 전 역할 guard2줄씩.
- ARCHITECTURE.md, TASKS.md, TEST_PLAN.md: 해당 계약/진척/검증 절 추가.

기존 API 응답·DB schema·파서·원본·EvidenceRef·검색 기본값·worker claim/lease 구현·프런트·의존성은 변경하지 않았다.

## 3. 운영 설정·실행 결과

[상세 계약](../docs/DEPLOYMENT_PREFLIGHT.md). APP_ENV local/test/production, APP_ROLE api/parse_worker/chunk_worker/workflow_worker. 과거 development는 local alias이며 빈 값/다른 환경은 거부한다. cloud DB/Auth/Storage는 SecretStr이며 기존 AuthSettings/SupabaseSettings/20MiB를 재사용한다. production은 정확 HTTPS/Origin/Secure/CSRF/same-origin proxy, PG verify-full URL, private bucket/서버키 분리, 서버 single-active membership, 백업 목표를 요구한다. local/test에서 cloud 자격증명·backend를 넣어 silent fallback하는 것도 차단한다.

명령:

```bash
.venv/bin/python -B scripts/validation/deployment_preflight.py --role api
```

현재 local 결과: exit0, LOCAL_CONTRACT_VALID, startup_allowed=true, production_ready=false, connectivity=NOT_CHECKED.

6개 실제 CLI 실행을 합성 placeholder 설정과 socket guard에서 확인했다:

| 사례 | exit | 결과 |
|---|---:|---|
| local | 0 | LOCAL_CONTRACT_VALID |
| test mock 계약 | 0 | LOCAL_CONTRACT_VALID; 모의 사용자/로그인 자동 구성 아님 |
| test workflow_worker | 0 | LOCAL_CONTRACT_VALID |
| production 필수키 누락 | 1 | INVALID |
| 역할 불일치 | 1 | INVALID |
| 완전한 production API+worker 설정 | 2 | settings VALID, 시작 BLOCKED |

production 형식 정상은 실제 DNS/TLS/DB/키/ACL/권한/백업 복구가 성공했다는 뜻이 아니다. 쌍 비교는 옵션 제공 때만 수행한다. URL target 비교는 설정상 host/port/DB명 비교이며 공유 pooler 등에서 실제 같은 DB identity라고 인증하지 않는다. 서버/worker 최소권한 DB credential 차이는 허용한다.

## 4. production 시작 차단 조건

필수키/형식 오류, SQLite/local Storage/mock/deny-all 운영 사용, private bucket 미선언/키 혼용, HTTPS/Origin/Secure Cookie/CSRF/proxy 오류, 역할/peer 불일치, real LLM/embedding/유료 승인 또는 양수 예산 설정, 백업 계획 누락을 차단한다.

설정이 완전해도 code-owned6개 blocker를 유지한다: PostgreSQL repository/auth/jobs/budget, private object adapter, production Auth membership bootstrap, proxy/limit/header 실증, cloud worker runtime, coordinated backup/restore 실증. 환경 변수나 readiness flag로 우회할 수 없다. 표준 API import/factory와 세 worker CLI가 영속 저장소를 생성하기 전에 production 실행을 거부하는 것을 검사했다.

이번 request/upload/token/backup 제한은 배포 설정 계약이다. 기존 동작에 새 미들웨어/timeout/rate limiter/원격 transport를 적용하지 않았다. 현재 API의20MiB와 기존 로그인·권한 정책은 그대로다. production wiring 이전에 실제 한도 집행과 플랫폼proxy 검증이 필요하다.

## 5. 검증 결과

- 신규40개 PASS,3.531초. 초기36개1.155초도 개발 중 실행했으며 이후4개를 추가해 최종40개 실행했다.
- 전체 backend **687 PASS / FAIL0 / SKIP0 / BLOCKED0**, 테스트214.300초·guarded runner215.706초. 기존647개와 신규40개다. backend.json/network.json 참조.
- 6개 CLI 사례 기대 exit 일치, 외부 접속0.
- 실제 socket/DNS/httpx client 금지 검사 및 subprocess 상속 비루프백 차단 하네스. 최종 외부 시도0, 실제 Supabase/LLM/embedding 호출0, 비용0.
- secrets의 repr/JSON/error/CLI marker 누출 차단, malformed JSON·인수 오류 redaction 검사. raw ValidationError 입력을 출력하지 않는다.
- 표준 API import·factory 및 worker CLI의 production 차단을 실프로세스/생성자 mock로 확인했다. 관련 기존 auth/기관/원본/EvidenceRef/worker복구·재시도 회귀는 전체 backend 포함.
- tested source hash mismatch0, git diff --check PASS. 이전 commit과 비교한 나머지 추적871파일 동일. 기존 fixture/과거 증거/인간 검토 원문 유지.
- UI/타입/build는 frontend·lock·의존성 파일이 동일하여 이번 재실행하지 않았다. D의 기존 UI174/타입/build 증거는 이전 실행이며 새로운 PASS로 집계하지 않는다.
- 기존 Starlette/httpx deprecation warning을 관찰했으나 dependency를 임의 교체하지 않았다. 테스트 실패는 없다.

## 6. Git·잔여 위험·다음 순서

브랜치 feat/deployment-preflight, HEAD 위3453eec. 이번 신규 구현은 미커밋 검토 후보이며 원격 push·main merge·tag·배포 없음. 실제 연결·영속성·DNS/HTTPS·proxy·기관 권한·backup restore는 현재 환경의 검사로 증명하지 않았다.

다음 우선순위는 PostgreSQL repository/auth/job/budget 이식 및 명시 migration/락·lease·예산 동등성 → private Storage 불변/intent 대사·백업복구 → 운영 Supabase Auth provisioning/설정 wiring과 shared membership/세션이다. 기존 Auth transport 형식/모의 HTTP 계약은 재사용한다. 실제 Auth 시험은 별도 계정/자료/호출 승인 후만 가능하다. 실제 내부 자료 외부 전송, 사용자 인간판정 자동 생성, 공식 업무절차 승인/게시를 추가하지 않았다.

소요시간: 전체 약10분, 보존 커밋 이후8.4분 실측(초기 검사 제외). 전체 backend 검증 시간은 위 별도 실측이다. 다음 단계는 자동 시작하지 않는다.
