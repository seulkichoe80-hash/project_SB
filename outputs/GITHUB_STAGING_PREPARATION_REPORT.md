# GitHub 보존·실제 스테이징 연결 준비

## 보존·공개 전 검사

시작 브랜치 `feat/deployment-storage-http`, HEAD `34c66e108a45442e164fa2230861a4a3f469f05c`. 기존14파일은 이전 manifest와 전체 backend 코드 SHA를 대조한 뒤 `7feaeb162c099c50091692f72fcaaba15cbf3700`으로 로컬 보존했다. 기존 브랜치/commit을 삭제·재작성하지 않았다. 변경 전 사본/해시는 Git 제외 `work/github-staging-preservation/`에 보관한다.

GitHub origin은 공개 `seulkichoe80-hash/project_SB`, 원격 main은 `8986b912083876ccfd6dabb207a92cc33d00d1e5`였다. 신규14파일뿐 아니라 그 이전15커밋의 main 미반영 이력도 push/PR에 포함된다. 이를 Storage HTTP만 변경하는 작은 PR로 오해하면 안 된다. 보존 PR은 검토용 draft로 만들며 main을 자동 병합하지 않는다. 실제 push/PR URL·최종 SHA는 최종 응답 및 GitHub PR metadata로 확인한다.

공개 전 신규 이력520개 blob(약45.2MB)을 검사했다. private key/GitHub/AWS/Supabase secret/JWT 강한 패턴 발견0,100MiB 초과 blob0. 신규 .env/원본 PDF/DB/private key/archive/raw upload 파일 없음. 개인정보 후보14건은 TASKS의 **기존 main에 이미 공개된 동일 제출 연락처** 반복으로 확인됐다. 원문 연락처를 새 보고서에 복제하지 않았다. 합성 generation 스크립트/manifest와 대표 문서관리·인간검토 화면을 대조했다. 자동 패턴 검사는 모든 개인정보의 부재를 완전 인증하지 않는다.

[공개 검사](github-staging-preservation/PUBLICATION_AUDIT.json), [사전 검사](github-staging-preservation/PREPARATION_CHECKS.json). 알려진 GitHub Actions workflow0·GitHub deployment 기록0이나 webhook 목록은 integration 권한403으로 확인하지 못했다. 이는 push/PR 권한 실패와 다르다. 외부 호스팅 연동 목록을 확인 완료로 표시하지 않는다. 이번에 workflow/서비스/자동 배포를 만들거나 활성화하지 않았다.

## 테스트 증거

기존 `outputs/deployment-storage-http/backend.json`의 **1,085 PASS / FAIL0 / SKIP0**는 직전 실행 증거다. 이번에132개 Python/fixture-support/잠금파일 source hash와 dependency version 일치를 확인했다. 런타임/테스트/DB schema/의존성은 변경하지 않았다. 새 기능 개발·전체 회귀·UI/typecheck/build 재실행은 하지 않았고 과거 결과를 이번 실행 PASS로 바꾸지 않는다. 새 offline preflight에서 local 기본 계약 허용과 production 필수 설정 누락 시 기동 거부를 확인했다. 실제 클라우드 연결은 NOT_CHECKED다.

## 실제 연결 준비와 남은 차단

[상세 실행 준비표](../docs/STAGING_CONNECTION_RUNBOOK.md)에 다음을 정리했다.

- 사용자 소유 staging project/region/plan/예산, DB 최소권한과 TLS, Storage private bucket/ACL·용량, Auth issuer/JWKS와 명시적 기관 관리자 bootstrap.
- application→별도 budget schema→application Storage registry 순의 additive migration과 checksum 검증. 현재 migration CLI는 loopback 전용이므로 cloud 실행 준비 완료가 아니다.
- 현재 지원 env 이름과 secret 주입 방법, 아직 env mapping이 없는 schema/gateway/live factory 지점. VITE에는 비밀 금지.
- API1+parse/chunk/workflow worker3의 공통 DB/schema/bucket·기관 범위, 프런트/API A/B/C 대안과 same-site/CSRF/Origin·cookie·20MiB 한도.
- 작은 합성 PDF/HWPX부터20MiB까지 양방향 검증, 부분 실패/orphan·lease·기관 격리·서버 재시작·DB+객체 manifest 복구 계획.
- code-owned production blocker6개의 해제에 필요한 구현/실증. 키를 주입하거나 APP_ENV를 바꿔 차단을 우회하지 않는다.

## 승인과 다음 최소 단위

현재 실제 Supabase/Auth/Storage/AI/embedding 연결·외부 자료 전송·유료 사용·공개 배포·main merge·production guard 해제0회다. GitHub 쓰기는 사용자가 이번에 명시 승인한 보존 범위다. 인간 판정/승인 생성0건, 기존 원본/fixture/증거 보존.

다음 최소 단위는 production 전용 factory/migration 및 빠진 설정 mapping의 구현 범위 확정이다. 추가 Fake 기능이 아니라 실제 연결 전 필요한 entry point를 준비하되 외부 호출·차단 해제는 별도 승인이다. 최초 실제 연결에는 **특정 project/region·합성 입력/SHA·호출/쓰기/migration 범위·횟수·기간·예산·비밀 주입/백업 담당**이 필요하다. 유료 호스팅·공개 전환·실제 AI는 각각 별도 승인한다. 이번 작업 이후 자동 진행하지 않는다.
