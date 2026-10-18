# 배포 준비 6단계 — 스테이징 연결 준비·호스팅 제약 보고

확인일 **2026-10-18 KST**. **보존·후보 설계·연결 준비표 작성 완료, 호스팅 공식 검증은 일부 BLOCKED이며 아키텍처 최종 확정 불가.** [상세 설계·실행 준비](../docs/DEPLOYMENT_STAGING_PREP.md).

## 1. Git 보존

시작: `/workspace/project_SB`, feat/deployment-wiring, HEAD7451af863c7a81af140dc2c610033e430af526b3. 미커밋28파일의 manifest/실제 파일·1031 PASS 당시 source hash·TLS15 증거·강한 비밀키 패턴을 대조했다.

보존 커밋 **cbee283a9dc3e810573faad523a95c778ff87535** — Preserve local Fake runtime wiring and verified loopback TLS. 새 브랜치 **feat/deployment-staging-prep**. 이번 문서/근거는 미커밋, staged0. 원본·fixture·기존 테스트·과거 증거·인간 검토 변경/삭제0. main 수정/reset·push/merge/tag·서비스 배포 없음. [보존 JSON](deployment-staging-prep/PRESERVATION.json).

## 2. 공식 근거와 확인 범위

Vercel/Render/Supabase 공식 문서 사이트 GET은 inherited HTTPS proxy에서 ProxyError였다. 프록시/TLS를 우회하지 않았다. 공식 Supabase GitHub 소스를 허용된 경로로 읽었고 commit **7425d4930528931400fb3e656e860b1094cb224e**로 고정했다. 공식 소스24건과 문서 판단16건의 URL/줄/SHA/확인일을 [OFFICIAL_SOURCES](deployment-staging-prep/OFFICIAL_SOURCES.json)에 보존했다. raw cache는 ignored work/에만 있다.

공식 문서 소스로 확인한 내용:

- persistent IPv4-only backend는 shared session pooler5432, 지원 환경은 direct. migration/pg_dump는 direct 권장. transaction pooler6543는 prepared statement 미지원.
- private bucket 기본/RLS 적용, service key는 RLS 우회. Free 파일 상한50MB와 실제 global/bucket cap은 별개.6MB 초과 전송은 TUS 권장.
- JWKS edge10분 cache·client cache 가능. 사용자 삭제/ban만으로 기존 access JWT·세션이 즉시 철회되지 않음.
- Pro DB daily backup7일, Storage 객체 bytes는 DB 백업에 미포함.
- 공식 가격 소스 Free0·Pro From25 USD/월(one Micro project), Free1주 비활동 pause·active project2개. Compute credit/일부 spend cap은 총액 상한이 아님.

**미확인:** Vercel rewrite/static/Function 요청·응답20MiB/헤더·현재 요금·이용목적, Render web/worker의 지속 실행·현재 plan·outbound IPv4/IPv6·TLS/health·body/response/timeout. 계정·quota·invoice·실 endpoint는 모두 미조회다. 소스 확인을 실제 계정 또는 인터넷 E2E VERIFIED로 올리지 않았다. [접근 상태](deployment-staging-prep/ACCESS_STATUS.json).

## 3. 20MiB 권장 경로·아키텍처

**확정된20MiB 인터넷 경로는 없다.** A(Vercel /api proxy)는 공식 제한/실환경 증거가 없어 통과 판정하지 않는다. 과거의 Vercel 제한 숫자도 최신 검증값으로 재사용하지 않았다.

우선 검증 후보는 **B: 같은-site custom domain의 API 직통**이다. bytes가 Vercel proxy를 통과하지 않고 기존 서버 원본 검사·등록·다운로드를 재사용한다. 하지만 API Host/browser Origin 분리·정확 credentialed CORS/CSRF/Vary·Render 신뢰·20MiB 양방향 시험·domain 비용이 필요하므로 현재 기본 설계로 확정하지 않았다. 현재 SameSite=Lax를 vercel.app↔onrender.com cross-site에서 그대로 쓸 수 있다고 가정하지 않는다.

C(서버 승인 private Storage 직접 업로드/TUS)는 후속 후보다. server-fixed quarantine 경로·제한 capability·서버 read-back SHA/MIME/크기·finalize/취소/만료·orphan·기관 재검증이 새로 필요하다. provider JWT/서비스 키를 브라우저에 주지 않으며 native signed upload의 TTL/철회가 확인되지 않은 상태에서 짧은 일회성 권한을 보장하지 않는다. **C만으로 기존20MiB 원본 다운로드 제한까지 해결되지는 않는다.**

## 4. 요금·필요 서비스

확인된 수치는 공식 Supabase 가격 화면 소스의 **Free $0 / Pro 시작 $25월**이다. 실제 account quote/세금/초과·부가 옵션은 미확인이다. paid org $10 compute credit을 포함된 one Micro 비용과 중복 계산하지 않되 기존 project의 credit 사용량을 확인해야 한다.

Vercel/Render 최신 단가·상시 실행 plan은 BLOCKED여서 **월 합계 견적 미확정**이다. 기존 단계의 예상 단가를 현재 요금이라고 보고하지 않는다. 현행 구조는 frontend static1 + API1 + parse/chunk/workflow worker3 + Supabase project1 + domain/백업이다. worker를 하나의 service로 합치는 supervisor는 미구현이다.

예산식: Vercel + Render API + worker3개 + Supabase 실계정 청구 + domain/백업/egress/옵션·세금. 고정 금액·free 상시 운영·총액 spend cap을 보장하지 않는다. 신청/결제/계정 생성/사용자 invoice 조회0.

## 5. 남은 구현과 사용자 준비

[상세 체크리스트](../docs/DEPLOYMENT_STAGING_PREP.md)의 계정·권한·migration·운영 복구 순서를 따른다.

- 사용자 준비: 승인된 Vercel/Render/Supabase workspace/project·plan/region·budget, custom domain/DNS·staging 접근 대상, runtime/migration 최소권한 계정, private bucket·Auth signing/초기 기관 관리자 subject·보안 담당자, secret manager·암호화 백업 저장소. 비밀값은 console/secret store에만 입력한다.
- 구현 잔여: 실제 Storage/JWKS/상태 동기화 transport·운영 factory/worker wiring, DB/pool/CA·schema/권한 확인, 선택 ingress/CORS/Host·20MiB 양방향·health/증명/제한, 실제 coordinated 백업(객체·비용 원장·Auth mapping 포함)/복구. 실제 RLS와 direct SQL 서버 세션을 자동 Supabase auth.uid 문맥으로 가정하지 않는다.
- migration 계획: 승인·백업 → 새 app/budget schema001 → Storage001/권한·private 원본 → 실제 connection target·Auth/최초 관리자 확인 → 비공개 API/worker/ingress 합성 E2E → 복구검증 → 별도 공개 승인. managed auth/storage schema를 기존 앱 migration으로 덮어쓰거나 원본을 삭제하지 않는다.

## 6. 차단·승인·후속 최소 단위

production 시작 차단/G1-C/D 미완료 유지. 실제 Auth/Storage·권한/근거/원본/worker·backups·ingress/비밀 관리 검증 전 공개 금지, 합성 자료만 허용. 실제 계정 생성/유료 신청/Secret 주입/서비스 접속시험·DNS/배포 연결·push/공개 접근은 각각 명시 승인 후다.

공식 사이트 재확인에는 Codex 환경의 문서 host vercel.com/render.com/supabase.com 접근 허용 또는 provenance가 있는 공식 본문이 필요하다. 환경·network draft·Secret은 변경하지 않았다. 이는 서비스 접속/계정/예산 승인과 별개다.

다음 최소 구현 제안은 **실 Storage HTTP transport를 httpx.MockTransport로만 검증**하는 단위다(원본 hash/길이·upsert=false·기관/실패/고아 처리, 외부 호출0·production 차단 유지). 공식 호스팅 조건 확인을 병행하고, ingress B/C는 선택 근거가 확보된 뒤 별도 요청으로 구현한다. 이번에 후속 구현은 시작하지 않았다.

## 7. 검사·소요시간

문서-only 작업으로 TEST_PLAN의 예외에 따라 새 backend/TLS/UI·type/build·DB/worker를 실행하지 않았다. **1031 PASS/TLS15는 source hash가 같은 이전 단계 기록이며 이번 새 PASS가 아니다.** 이번 검사는 Git/hash 보존·로컬 문서 링크·공식 원문 SHA/줄 근거·강한 비밀키 패턴/코드 불변 대조다. 사람 판정/승인0, NOT_VERIFIED/NOT_REQUESTED 유지.

공식 자료 GET·공개 Git metadata 조회만 수행했다. 실제 Supabase Data/Auth/Storage·AI API0, 계정/요금제 조회0·결제/배포/push/merge0. 정확 종료 시각(KST)·보존 커밋 이후 소요시간·변경 수는 PRESERVATION.json에 기록한다. 스테이징 설계와 제약 조사에서 종료하며 미확인 항목을 완료로 올리지 않는다.
