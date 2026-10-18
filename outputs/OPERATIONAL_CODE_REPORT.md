# 실제 스테이징 전 운영 코드 보완 결과

## 기준·구현

1f32b3de0b949551fa4d2d0a65e769ee8941573a/feat/deployment-runtime-factory의 clean 기준을 확인하고 feat/deployment-live-adapters에서 개발했다. 기존 원본/fixture/SQL/테스트/검증 증거·인간 검토 자료를 보존한다. 이번 commit/push는 새 개발 브랜치만 대상으로 하며 main이나 PR#3 source branch를 자동 갱신하지 않는다.

- apps/api/runtime_settings.py: schema/gateway/audience/JWT lifetime/network opt-in/ref env mapping·peer 비교·추가 operational_mapping_issues/startup 진단.
- apps/api/operational_mapping.py, runtime_factory.py: 생산 설정→typed MigrationPlan/Storage/password/JWKS 준비, worker browser auth 제외, 부분 Mock 혼용 거부, 기존 Factory DI 연결.
- apps/api/provider_http.py: 명시 project/service/opt-in/ref 정책과 gated password/user·고정 JWKS HTTP. 설정 준비만으로 네트워크 요청하지 않는다.
- apps/api/storage_http.py: 기존 검증 프로토콜을 재사용한 gated SupabaseStorageHTTPTransport. default Mock-only class는 보존.
- apps/api/supabase_jwt.py: 기존 JWT 서명·issuer/aud/expiry·identity에 새 exact HTTP 타입 연결. role/기관은 서버 membership만 신뢰한다.
- apps/api/private_storage.py, runtime_wiring.py: 새 exact 타입/설정 검증·local/test live 선택 차단. DB 원본/근거 보호는 유지.
- tests/test_operational_adapters.py: 신규23개(HTTP/config20 + 실제 격리 PostgreSQL3).
- docs/OPERATIONAL_ADAPTERS.md와 ARCHITECTURE/TASKS/TEST_PLAN/STAGING_FINAL_GATES의 해당 절, 새 outputs evidence.

추가 Fake 시나리오 기능이 아니라 기존 Fake/Mock 주입으로 실제 HTTP 직렬화·검증·설정 경로를 시험했다. actual HTTP를 지원하는 코드가 있어도 production 프로세스를 시작할 권한/실증이 생긴 것은 아니다.

## 해결한 차단 원인과 경계

schema/gateway key mapping·잘못된 조합/누락·peer 진단, 명시적인 HTTP 준비 경로, password/JWKS/Storage live 선택 코드 공백을 보완했다. [상세 계약](../docs/OPERATIONAL_ADAPTERS.md)을 따른다. opt-in과 승인 추적 참조는 operator 설정이며 승인 자체를 생성하는 토큰이 아니다. 실제 연결은 사용자 별도 승인 전 수행하지 않는다. Mock은 API의 세 전송 모두 명시하거나 모두 생략하며 부분적으로 실제 경로와 섞을 수 없다.

공식 계약은 [CONTRACTS.json](operational-code/CONTRACTS.json)의 기존 확보본 SHA5건·기존 Auth OpenAPI 확인 기록에 한정한다. 이번에 실제 계정/키/API 또는 새 공식 문서 네트워크 요청은 하지 않았다. upstream문서와 실제 project 버전/ACL/가용성은 별개다.

## 테스트 실행 기록

- 최초 기존 영향182개 실행은 PG DSN 미설정으로41 SKIP이 있었고 PASS로 대체하지 않았다.
- 격리 PG를 켠 뒤 신규22+기존210 = **232 PASS/FAIL0/SKIP0**,31.663초.
- 부분 Mock 방지 보강 후 신규 **23 PASS/FAIL0/SKIP0**,1.441초.
- 최초 전체 backend는 **1,096 PASS/40 FAIL/SKIP0**,368.236초. 로컬 Docker PostgreSQL의 동적 공유 메모리32MiB 확장 실패로 서버가 복구 모드에 진입했다. 실패 증거 backend.json/backend.network.json과 RETRY_REASON.json을 보존했다.
- 두 번째 전체 실행은 DSN query options가 기존 local_test allowlist에서 거부되어 **903 PASS/233 FAIL/SKIP0**,239.539초. 잘못된 테스트 실행 설정을 원복했으며 backend-final.json/network.json을 실패 증거로 보존한다.
- 원래 DSN과 libpq PGOPTIONS 환경 변수로만 병렬 query/maintenance를 제한한 신규23개 재확인은 **23 PASS/FAIL0/SKIP0**,1.706초. 직접 module 호출의 import 오류는 discover로 바로잡았으며 실행하지 못한 호출을 PASS로 세지 않았다.
- 코드/테스트/기존 DB 자료는 삭제·변경하지 않았다. 최종 전체 실행은 backend-verified.json/network.json을 따른다. 이전1,113개 기록을 이번 PASS로 복사하지 않는다.

새23개에는 미승인 client 생성 차단·프로젝트/service/path·정책 교체/부분 Mock·JWT 서명/만료/issuer/audience·새 JWKS key 회전/오류·token/JWKS429/503/redirect/timeout/size·로그 마스킹·immutable Storage 복구·실제 PG cookie/CSRF/logout·기관/role 변경/비활성·worker parsing을 포함한다. 기존 전체 회귀가 EvidenceRef/버전/원본/lease/비용/격리 안전성을 함께 확인한다.

UI/API 응답/DB schema 변경 없음. UI/typecheck/build·별도 실제 TLS 재실행은 NOT_RUN이다. 기존 증거를 새 실행 PASS로 바꾸지 않는다.

## 여전히 BLOCKED

기존 code-owned6개 blocker는 하나도 제거하지 않았다. 특히 남은 것은 단순한 사용자 설정만이 아니다.

1. 승인된 remote migration runner 실행 정책·공통 cloud factory/role·TLS/CA/pool·실DB 검증.
2. 실제 Storage private ACL·공식 목록/응답·orphan inventory/원격 backup·20MiB 실전송. list_page는 계속 명시 차단.
3. Auth live 현재 계정 상태/세션 철회·operator bootstrap 실증. SessionRevalidation은 아직 Fake-only이며 서명 검증으로 활성 계정을 자동 인증하지 않는다.
4. Vercel/Render의 실제 ingress 신뢰·Origin/CSRF/cookie·upload/download 한도와 same-site API 구조 변경.
5. cloud worker 기관 범위·공통 remote stores·lease/restart·최소권한.
6. 원격 DB+객체 bytes+manifest/Auth/원장 coordinated 복원과 RPO/RTO.

SUPABASE_NETWORK_ENABLED=true/승인 참조를 넣어도 main/worker/build_runtime의 production 시작은 막힌다. local/test로 cloud 설정을 우회하거나 code-owned blocker를 삭제하지 않았다. 전체 운영 연결 준비 완료라고 선언하지 않는다.

## 사용자 설정과 다음 승인

staging 소유자/region/plan·DB TLS DSN/두 schema/최소권한·private bucket·서버/gateway key·Auth issuer/audience/초대/명시 기관 manager·HTTPS Origin/Host·secret manager·backup 목표가 필요하다. 새 변수는 상세 계약 표를 따른다. VITE에 비밀을 넣지 않으며 실제 값을 Git/PR/채팅에 등록하지 않는다. 실제 연결에는 특정 project·합성 입력/SHA/크기·read/write/migration 범위·횟수/기간·비용·복구 담당을 별도 승인해야 한다.

실제 Supabase/Render/Vercel/LLM/embedding 연결·계정/자격증명/결제·공개 배포·main merge·인간 판정 생성0회다. GitHub 개발 브랜치 보존은 이번 사용자 승인 범위이며 실제 서비스 승인이 아니다. 이후 단계는 자동 진행하지 않는다.

## 최종 실행·보존 검사

최종 전체 backend **1,136 PASS / FAIL0 / SKIP0 / BLOCKED0**, **354.938초**. [최종 결과](operational-code/backend-verified.json), [네트워크 가드](operational-code/backend-verified.network.json). 가드 자체 probe PASS, blocked external attempts0, actual provider calls0. 격리 PostgreSQL 실DB 시험을 포함한다. 최종 소스 SHA256 전체 일치. 첫 두 실패 실행은 별도 파일로 보존했다.

기준1,015개 파일 중 허용한 구현/문서 외 기존 원본·fixture·SQL·테스트·과거 증거·인간 검토 자료는 변경/삭제하지 않았다. [보존·패턴 검사](operational-code/PRESERVATION.json), [실행 명령](operational-code/TEST_COMMANDS.json). 강한 secret/새 개인정보 패턴 후보0. 기존 main에 공개된 TASKS 연락처1건은 기존 내용으로 대조했으며 값을 재출력하지 않았다. 패턴 검사만으로 모든 개인정보 부재를 증명한다고 주장하지 않는다.

현재 새 브랜치의 일반 commit/push로 보존한다. 정확한 최종 commit SHA/remote 일치 여부는 작업 완료 응답의 실제 Git 확인 결과를 따른다. 기존 Draft PR#3 source와 main은 변경하지 않는다.

작업 시작부터 최종 검증 보고 작성까지 약 22.9분(커밋/push 확인 시간 별도).
