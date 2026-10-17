# 서무ITDA 프런트엔드 기반

Stage2·3 기반에 Stage4A 문서 등록·목록·상세·버전·원본 다운로드·처리 상태·논리적 등록 해제 UI와 API Client를 제공한다. 실제 로그인과 AI는 미구현이다. 기본 백엔드는 401로 접근을 차단하며 운영 인증 우회는 없다.

## 실행

일반 Node/npm 환경에서는 이 디렉터리에서 npm ci --ignore-scripts, npm run typecheck, npm run build, npm run dev -- --host 127.0.0.1을 사용한다. 검증 환경은 Node24.19.0/npm12.2.0/Windows다. 현재 PC의 npm은 PATH에 없어 저장소 루트에서 아래 명령으로 실제 검증했다.

```powershell
node work/phase1/npm-tool/package/bin/npm-cli.js ci --prefix apps/web --offline --cache work/phase1/npm-cache --ignore-scripts --no-audit --no-fund
node work/phase1/npm-tool/package/bin/npm-cli.js run typecheck --prefix apps/web
node work/phase1/npm-tool/package/bin/npm-cli.js run build --prefix apps/web
cd apps/web
node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 4173 --strictPort
```

오프라인 cache/npm-tool은 이 PC의 기존 산출물이므로 심사자 PC에 있다고 가정하지 않는다. 문서 API를 사용하려면 별도 backend 실행이 필요하며, UI만 열어도 정상 자료 조회를 보장하지 않는다. 공개 배포나 인증을 제공하는 명령이 아니다.

경로는 #/home, #/documents, #/ai, #/help다. 새 라우터 패키지 없이 뒤로가기/새로고침·알 수 없는 경로 안내를 제공한다. src/components는 레이아웃·프리미티브, src/styles는 토큰·반응형 스타일이다. 자격증명·기관 ID를 저장하지 않는다. 문서 관리 화면에서 API 요청을 보낸다.

검증 스크립트는 scripts/validation/check_stage2_ui.cjs다. 별도 Playwright 설치/번들 경로와 설치된 브라우저를 PLAYWRIGHT_MODULE_DIR/BROWSER_EXECUTABLE로 지정할 수 있다. 제품 의존성에는 추가하지 않았다. 새 JSON 출력 경로를 인자로 전달한다. 본 PC는 브라우저 localhost socket 제한으로 프로덕션 응답 interception으로 렌더했다. 실제 HTTP 연동·실인증·스크린리더·전체 WCAG 준수는 별도 검증이다.

## Stage4A 연결 설정

기본 API 접두사는 `/api`다. Vite dev/preview는 이 경로를 로컬 `http://127.0.0.1:8000`으로 전달하고 `/api`를 제거한다. backend 경로는 `/documents`로 시작한다. 이 proxy는 인증·권한을 우회하지 않으며 401을 그대로 전달한다. 배포 서버의 rewrite 설정은 이번에 제공하지 않는다.

다른 API 주소는 공개 설정 `VITE_API_BASE_URL`로 빌드 시 지정한다. 비밀·토큰·기관 ID를 이 값에 넣지 않는다. 교차 출처 연결에는 서버의 정확한 CORS·인증 설계가 별도로 필요하다. client는 `credentials: same-origin`, no-store, redirect:error를 사용하며 bearer token이나 모의 관리자 헤더를 만들지 않는다.

업로드는 raw File body와 filename query, canonical Content-Type, X-Data-Classification: public/synthetic을 보낸다. 브라우저 검증은 확장자/크기/기본 시그니처이며 전체 PDF·HWPX ZIP/XML 검증은 서버가 맡는다. 목록은 서버가 허용한 버전별 행이다. 서버 검색·정렬·페이지네이션·버전 활성 전환 UI는 없다. 청킹은 UI 요청으로 받은 job ID만 추적하며 재접속 후 기존 job ID 자동 발견은 지원하지 않는다. 등록 해제는 원본 영구 삭제가 아니다.
