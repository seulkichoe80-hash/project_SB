# Stage3 업무 홈 Feature Gate

업무 시작 안내, 문서 관리 이동, 문서 등록·AI 준비 중, 최근 문서 조회 미연결, 원문 추출/검색용 나누기/AI 분석 설명, 향후 등록→추출→근거 검토 흐름과 도움말 구현. 가짜 문서·날짜·건수·진행률 없음. FR-01/07/18·NFR-01/05/07·WEB-01/03/06의 화면 부분이며 전체 요구사항 합격이 아니다.

## 파일·재사용

수정: apps/web/src/App.tsx, TASKS.md, TEST_PLAN.md.
신규: apps/web/src/pages/HomePage.tsx, apps/web/src/styles/home.css, scripts/validation/check_stage3_home.cjs 및 이 보고서/outputs/stage3 증거.
AppLayout·Sidebar·Header·해시 라우팅·PageTitle·Button·StatusBadge·Icon·LoadingState·EmptyState·ErrorState·기존 토큰 재사용. 다른 페이지/공통 컴포넌트/토큰/잠금파일 동일. 기본 recent 상태 disconnected 고정. 대체 상태는 SSR 표시 시험만 수행하며 실제 API 상태 전이가 아니다.

## 실행·결과

- `node work/phase1/npm-tool/package/bin/npm-cli.js run typecheck --prefix apps/web`: PASS.
- `node work/phase1/npm-tool/package/bin/npm-cli.js run build --prefix apps/web`: PASS, Vite184ms.
- `node scripts/validation/check_stage3_home.cjs outputs/stage3/home/RESULT.json`: 6 PASS / 0 FAIL, 2.621초.
- `node scripts/validation/check_stage2_ui.cjs outputs/stage3/stage2-regression/RESULT.json`: 14 PASS / 0 FAIL, 3.121초.

총22 PASS(타입/빌드 포함), FAIL0, SKIP0. 실제 HTTP 브라우저 접속은 이전 loopback 제한으로 BLOCKED 유지, 이번 재시도 없음. Chrome 정적 응답 interception은 실HTTP 검증이 아니다. 콘솔/JS 오류0·API/외부요청0. 백엔드123개는 영향 밖으로 재실행하지 않았으며 합산하지 않았다.

키보드/3px 포커스·44px 주요 버튼·시맨틱 구조·색+텍스트 상태·명암6쌍4.5:1 이상·320/375/768/1440px·글자200% reflow PASS. 데스크톱/모바일 캡처 직접 확인. 스크린리더·native toolbar zoom·전체 WCAG2.2AA·사용자5초/3회 목표는 미검증. 실제 API 로딩/오류 전이도 미검증.

## 보존·Git·시간

시작 시점162개 파일 해시 대조, 기존 소스는 App.tsx만 변경. 이후 TASKS/TEST_PLAN에 현 범위 추가. App.tsx Documents 이후 동일. 백엔드·fixture·사용자 원본·이전 증거 보존. 변경 전 사본/해시/diff: work/stage3/before. 기존 미커밋 변경 유지. HEAD `f9a01d8c5b6b2b2311f4d8d8461b0f5b55b7a182`. commit/push/배포·AI호출·의존성 추가 없음.

UTC04:41:55 시작, 보고까지232.7초. 타입/빌드 포함 명령5.823초(파일생성 포함, 개별 분리 미측정), 브라우저 합계5.742초. 보존 검사 경로 구분자/인코딩 오류2회 수정 재시도, 기능검사 실패 없음. 모델 추론시간 추정 없음.

Stage3 로컬 화면 범위 완료. Stage4는 별도 사용자 승인 후 착수 가능, 이번 미구현. 기본 인증401·실HTTP·업로드/권한·실API 상태 전이는 후속 검증 필요.

[홈 결과](stage3/home/RESULT.json) · [회귀](stage3/stage2-regression/RESULT.json) · [데스크톱](stage3/home/home-desktop.png) · [모바일](stage3/home/home-mobile.png) · [Git](stage3/GIT_STATUS.txt) · [보존/측정](stage3/PRESERVATION_METRICS.json)
