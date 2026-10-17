# 서무ITDA Stage2 프런트엔드 기반 완료 보고

**Stage2 Feature Gate 범위 완료. Stage3·전체 Phase·실제 데이터/API·공개 운영 완료가 아니다.** 사용자 승인 범위 안의 프런트엔드 기반만 구현했다.

## 생성·수정

apps/web의 package/lock·tsconfig·vite config·index.html·src/main.tsx·App.tsx·components/AppLayout.tsx·UI.tsx·styles/tokens.css·app.css·README.md를 생성했다. scripts/validation/check_stage2_ui.cjs와 docs/STAGE2_FRONTEND.md를 추가했다. 기존 수정은 TASKS/ARCHITECTURE/TEST_PLAN 해당 절 추가뿐이며 [보존 결과](stage2/PRESERVATION.json)에 시작 전 변경과 이번 변경을 구분했다.

검증 버전을 정확 고정하고 기존 잠금파일의 해석 graph를 재사용했다. React19.3.1·TypeScript7.0.2·Vite8.3.4이며 현재 사용하지 않는 지도 의존성만 새 패키지에서 제외했다. 기존 스파이크/지도 선택은 유지한다. 제품에 새 UI/라우팅 라이브러리·웹폰트를 추가하지 않았다.

## 화면·컴포넌트

AppLayout/Sidebar/Header/PageTitle/Button/StatusBadge/LoadingState/EmptyState/ErrorState와4화면 해시 전환을 구현했다. 밝은 배경·네이비/블루·16px 본문·44px 주요 조작영역·4~32px 간격·8px 반경·224px 사이드바·명시적 포커스를 토큰화했다.

업무 홈은 안내/진입 구조만, 문서 관리는 미연결 목록·비활성 등록 버튼, AI는 준비 안내, 도움말은 사용 범위/원문 보호 설명이다. 통계·업로드·검색/정렬·원문 뷰어·AI 질문·검토 확정·실제 사용자/기관은 없다. 우측 패널은 main 슬롯을 통해 확장 가능하다. API 및 외부 요청은 없다.

## 실제 실행

저장소 루트:
- node work/phase1/npm-tool/package/bin/npm-cli.js install --prefix apps/web --package-lock-only --offline --cache work/phase1/npm-cache --ignore-scripts --no-audit --no-fund : 잠금 갱신 PASS.
- node work/phase1/npm-tool/package/bin/npm-cli.js ci --prefix apps/web --offline --cache work/phase1/npm-cache --ignore-scripts --no-audit --no-fund :24 packages 설치 PASS.
- 같은 npm-cli의 run typecheck --prefix apps/web : PASS.
- 같은 npm-cli의 run build --prefix apps/web : PASS. tsc 이후 Vite19 modules, JS233.23kB(gzip72.98), CSS12.62kB(gzip3.18), Vite 보고143ms.
- apps/web에서 node node_modules/vite/bin/vite.js preview --host127.0.0.1 --port4173 --strictPort(실제 명령에서는 옵션과 값 사이 공백 사용): 로컬 서버 시작 성공, 검증 후 중단. 브라우저 직접 접속은 타임아웃이었다.
- PLAYWRIGHT_MODULE_DIR를 번들 node_modules, BROWSER_EXECUTABLE을 설치된 Chrome 경로로 지정한 node scripts/validation/check_stage2_ui.cjs outputs/stage2/BROWSER_FINAL.json : **14 PASS/0 FAIL/0 SKIP/0 BLOCKED(선언한 정적 브라우저 검사 범위)**.

초기 브라우저 실행12 PASS/2 FAIL은 검사 코드의 화면 전환 대기 누락과 TypeScript7에서 제공하지 않는 transpile API 사용이었다. 명시적인 h1 대기·기존 Vite SSR 로딩으로 검사 코드를 수정했고 앱 동작을 낮추지 않았다. 초기 JSON은 보존했다. 기본 브라우저 부재·Edge sandbox crash·localhost 타임아웃은 환경 제약으로 기록했다. 설치된 Chrome155를 사용해 모든 정적 파일 응답을 로컬에서 가로채서 제공했으며 실제 HTTP 배포/E2E 합격으로 표현하지 않는다.

## 접근성·시각 검토

자동: lang/landmark/h1/table/caption·aria-current,skip link·Tab/Enter·포커스 이동,4화면 history/새로고침/unknown 경로,320/375/768px 가로 넘침 없음,720px reflow+글자200%,공통 상태 SSR,콘솔/JS 오류0·외부/API 요청0 확인.

자동 명암6쌍 최소5.69:1(본문14.10:1, 보조7.12:1, 주요 버튼6.70:1, 정보5.69:1, 경고6.50:1, 오류5.98:1). 이 결과는 지정 토큰쌍이며 전체 화면 WCAG 감사를 대신하지 않는다.

수동: home-desktop.png/home-mobile.png를 실제 열어 배치·줄바꿈·가림을 시각 확인했다. 키보드 검사는 자동 브라우저 조작이며 독립 사람/스크린리더 검토를 수행한 것으로 표기하지 않는다. 실제 툴바 확대·실제 모바일 기기·실인증·서버 통합은 미검증/차단이다. 전체 WCAG2.2AA 준수를 선언하지 않는다.

[데스크톱](stage2/home-desktop.png) / [모바일](stage2/home-mobile.png) / [문서 화면](stage2/documents-desktop.png) / [검사 JSON](stage2/BROWSER_FINAL.json)

## 보존·Git·시간

기존 backend·DB schema·source_blocks/EvidenceRef·fixture·증거·Phase1 프런트엔드는 변경 전 byte hash와 같다. 백엔드123개는 이번 실행하지 않았고 현재 PASS로 바꾸지 않았다. main/HEAD f9a01d8c5b6b2b2311f4d8d8461b0f5b55b7a182 유지. 기존 미커밋 변경을 보존했으며 add/commit/push/deploy는 하지 않았다.

최초 UTC 계측~최종 증거 작성 556.950초. 브라우저 최종 검사 2.624초, 초기 포함 검사 구간 합계 5.022초. npm/타입검사/빌드 전체의 독립 구간은 미측정이며 Vite 자체 보고0.143초와 구분한다. 모델 추론시간·최종 응답 생성은 미측정이다. 상세 [시간 기록](stage2/METRICS.json).

Stage3의 화면 작업은 별도 승인 후 착수 가능하다. 실제 최근 자료/오류·업무 통계 연동은 인증/API 계약 준비가 필요하다. 추가 라우터·UI 도구·PDF 뷰어·기관 인증·백엔드 변경을 이번 승인으로 확대하지 않는다.
