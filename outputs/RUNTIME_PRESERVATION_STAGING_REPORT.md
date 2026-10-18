# Runtime Factory 보존·실제 연결 준비 결과

## 보존·PR 반영 방식

실제 feat/deployment-runtime-factory / e091b7b clean 기준 위22개 미커밋 파일을 확인하고 manifest·최종 backend source136개/의존성 버전을 대조했다. 비밀키·신규 개인정보 후보0, 기존 원본/fixture/SQL/테스트/과거 증거와 실패·중단 기록을 보존했다. **39fe50a83015e6af977c651891f8a5a23d736511**이22파일 보존 커밋이다. 변경 전 사본/해시는 Git 제외 work/runtime-preservation-final에 보존한다.

PR#3은 현재 작업 브랜치가 아니라 feat/deployment-storage-http를 추적하며 시작 원격 HEAD는 e091b7b였다. 새 보존 커밋이 그 후손임을 확인했다. 현재 runtime-factory 브랜치도 GitHub에 보존하고 PR source branch를 같은 이력으로 **normal fast-forward**한다. force push·reset·다른 원격 이력 덮어쓰기·main merge를 사용하지 않는다. 최종 실제 원격 HEAD와 PR 상태는 GitHub metadata/최종 응답의 실행 후 확인값을 따른다. PR은 기존 Draft를 유지한다.

공개 저장소 후보를 재검사했다. 실제 .env/private key/원본 PDF/DB/raw upload는 새 보존 파일에 없으며 합성 테스트와 고정 진단 로그를 포함한다. 기존 main의 공개 제출 연락처 외 새 개인정보 후보는 없었다. 패턴/출처 검사는 모든 개인정보의 부재를 완전 자동 인증하지 않는다. [공개 검사](runtime-preservation-final/PUBLICATION_AUDIT.json).

## 검증 근거

**1,113 PASS / FAIL0 / SKIP0**는 직전 최종 backend-verified.json의 실제 실행 결과다. 이번에는 코드/fixture-support/잠금파일 SHA136개와 의존성 버전을 대조했다. 이번 보존·문서 작업에서 전체 테스트·UI·typecheck/build를 새로 실행하지 않았으며 과거 결과를 새 PASS로 표시하지 않는다. 기존190개 영향 시험, 실제 격리 PG stop/start와 원본/job/membership/UNKNOWN hold 복구 증거도 유지한다. production blocker 원문·런타임 코드·의존성은 이번에 변경하지 않았다.

## 사용자 작업·기술 차단 확정

[최종 게이트](../docs/STAGING_FINAL_GATES.md)에 상태 정의와 구성별 구현 완료/사용자 설정/코드·구조 변경/실제 연결 검증/BLOCKED를 구분했다. 이는 기존 [Runbook](../docs/STAGING_CONNECTION_RUNBOOK.md)과 [Factory 계약](../docs/RUNTIME_FACTORY_MIGRATIONS.md)을 보완한다.

사용자 준비는 승인된 staging 소유자/MFA·project/region/plan·DB 최소권한/TLS와 두 schema·private bucket/ACL·Auth issuer/JWKS/초대 및 명시 기관 관리자·Render API1/worker3·domain/HTTPS·안전한 secret 주입·backup/RPO/RTO다. 생성/등록/전송/배포는 이번에 하지 않았다.

필수 코드 작업은 **원격 factory/runner 승인 정책과 schema/env mapping**, live Storage/JWKS/password/현재 계정상태·철회·inventory/orphan/원격 backup, cloud worker 배치와 실제 ingress/클라이언트 연결이다. 현재 local/test seam이나 SB_PG_TEST_DSN을 cloud 우회로 사용할 수 없다. typed config나 키 입력만으로 production이 시작되지 않는다.

실행 순서는 코드 검토→범위/비용/데이터 승인→사용자 계정/secret/domain 준비→제한된 원격 사전 검사→승인된 Runner의 application/별도 budget/Storage migration verify→Auth bootstrap→소형 합성 E2E→20MiB 양방향·중단/복구·격리/철회→결과 검토 후 별도 공개 승인이다. 현재 runner는 원격 실행을 지원하지 않아 실제 명령을 제공했다고 주장하지 않는다.

현재 upload는 raw File body이며 multipart 기능이 아니다. 크기는 수KiB부터20MiB 경계까지 유효 합성 PDF/HWPX로 확대하고 upload/download·원본 SHA·기관/버전·Origin/CSRF/Secure/SameSite·메모리/시간·vendor quota를 분리 검증한다. A proxy의 실한도는 미확인, B same-site API 직통은 코드/신뢰 경계 변경과 검증이 필요한 후보다. C direct/TUS는 별도 구조 변경이며 자동 도입하지 않는다.

기존6개 production blocker·최신 실계정 요금/한도·private ACL·live Auth 철회·원격 복구·실제20MiB는 여전히 BLOCKED/미검증이다. 실제 LLM/embedding은 false/예산0이며 인간 판정/승인을 생성하지 않았다.

## 별도 사용자 승인

실제 계정 생성/설정·secret 등록·Supabase DB/Storage/Auth 요청에는 특정 project/region·계정/role·합성 입력/SHA/크기·읽기/쓰기/migration 범위·호출 횟수/기간·비용 상한·backup/복구 담당을 명시 승인해야 한다. 무료 서비스도 대상 외부 전송 승인을 대신하지 않는다. 유료 신청·공개 배포·main merge·실제 AI는 별도다. GitHub 보존 승인을 다른 서비스 승인으로 해석하지 않는다. 이번 작업은 보존과 계획 수립으로 종료한다.
