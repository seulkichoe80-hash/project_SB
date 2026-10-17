# Stage4A 문서 관리 UI·API Client 보고

## 판정

Stage4A 코드 구현과 로컬 모의 검증 완료. Feature Gate는 **조건부/잔여 검증 보류**다. 실제 브라우저 HTTP와 다운로드 파일 저장은 BLOCKED이며 통합 완료를 선언하지 않는다. Stage4B/4C는 구현하지 않았다.

관련 범위: FR-01/14/15/18, NFR-01/03/05/07, WEB-01/02/03/06/07의 프런트 부분. 원본 불변·기관/버전 권한·EvidenceRef·서버 검증 계약을 변경하지 않았다.

## 구현 기능

- PDF/HWPX 선택, 비어 있는 파일·20 MiB 초과·확장자·기본 PDF/ZIP 시그니처·파일명 사전 검사. HWPX ZIP/XML 전체 검사 및 PDF 진위/지원 기능은 서버가 최종 검사한다.
- 공개/합성 선택과 민감정보 없음 확인 후 raw body 등록. useRef 즉시 잠금+버튼 비활성화로 연속 제출 방지. 동일 내용 응답은 기존 버전 반환으로 안내.
- 서버 허용 버전별 목록, 문서·버전 상세/해시·형식·일시, 버전 전환 확인, 원본 다운로드 요청.
- 등록/파싱/청킹 상태 분리, 실패 파싱·청킹 재시도, 수동 상태 새로고침. AI 분석 완료로 표현하지 않으며 가짜 진행률 없음.
- loading/empty/401/403/404/409/422/500/503/network 안내. 401/403이면 표시 자료를 비우고 입력 차단. 원문 영구삭제와 다른 논리 해제 확인 dialog, 취소/Escape/초기 포커스/중복 요청 방지.
- 기존 토큰·AppLayout·Sidebar·Header·PageTitle·상태/버튼 재사용. 반응형 표는 지역 가로 스크롤이며 320px에서 페이지 가로 넘침 방지.

청킹 기존 작업 ID 열거 API가 없어 UI가 생성해 받은 ID만 추적한다. 재접속 후 기존 작업 상태를 추정하지 않는다. polling·검색·정렬·페이지네이션·새 버전 등록/활성화 UI·원문 렌더러는 없다. 목록의 active_only=false도 서버가 권한에 맞게 제한한다.

## 파일

신규 제품: apps/web/src/api/documents.ts, apps/web/src/pages/DocumentsPage.tsx, apps/web/src/styles/documents.css.
수정 제품: apps/web/src/App.tsx, src/components/AppLayout.tsx, src/pages/HomePage.tsx, vite.config.ts, README.md.
신규 시험: scripts/validation/check_stage4a_ui.cjs, check_stage4a_http.py, check_stage4a_live.cjs.
수정 시험: check_stage2_ui.cjs, check_stage3_home.cjs (문서 API401 동작으로 의도된 변경만 반영; 이전 증거 불변).
기준 문서: TASKS/ARCHITECTURE/TEST_PLAN 관련 절. PRD·AGENTS·Skill·백엔드·DB schema 변경 없음. 상세 파일/보존 목록은 [PRESERVATION](stage4a/PRESERVATION.json).

## 실제 연결 계약

| 용도 | method/path | 요청/응답 |
|---|---|---|
| 등록 | POST /documents?filename=... | raw File, Content-Type application/pdf 또는 application/hwp+zip, X-Data-Classification public/synthetic → document+duplicate |
| 목록 | GET /documents?active_only=false | 허용 버전 Metadata[] |
| 상세 | GET /documents/{document_id}/versions/{version_id} | Metadata, 경로와 응답 ID 재검사 |
| 원본 | GET 위 version/original | Blob → 안전 파일명으로 다운로드 |
| 파싱 | GET version/parsing, POST version/parsing/retry | Job |
| 청킹 | POST version/chunk-jobs (JSON {}), GET .../{job_id}, POST .../{job_id}/retry | Job |
| 등록 해제 | DELETE /documents/{document_id} | 논리 해제 결과 |

client는 새 버전 raw 업로드 메서드도 계약대로 지원하나 UI에는 노출하지 않는다. 토큰·관리자·기관 헤더를 생성하지 않는다. 기본 /api의 로컬 dev/preview proxy만 추가했으며 backend CORS는 변경하지 않았다. 공개 VITE_API_BASE_URL만 선택 설정 가능하고 배포 proxy는 미제공이다. redirect:error/no-store/same-origin credentials를 사용한다.

## 실제 실행과 결과

| 명령/시험 | 현재 결과 |
|---|---|
| node work/phase1/npm-tool/package/bin/npm-cli.js run typecheck --prefix apps/web | PASS |
| 위 npm-cli.js run build --prefix apps/web | PASS, 최종 Vite120ms |
| node scripts/validation/check_stage4a_ui.cjs outputs/stage4a/VALIDATION_FINAL.json | 신규16 PASS / 0 FAIL / 1 BLOCKED, 3.529초 |
| node scripts/validation/check_stage2_ui.cjs outputs/stage4a/stage2-final/RESULT.json | 14 PASS / 0 FAIL, 2.509초 |
| node scripts/validation/check_stage3_home.cjs outputs/stage4a/stage3-final/RESULT.json | 6 PASS / 0 FAIL, 2.673초 |
| work/phase2b/venv/Scripts/python.exe -B scripts/validation/check_stage4a_http.py outputs/stage4a/FASTAPI_HTTP_V2.json | 실제 FastAPI TCP HTTP6경로401、6 PASS, 1.669초 |
| node scripts/validation/check_stage4a_live.cjs outputs/stage4a/LIVE_BROWSER.json | 실제 Chrome→Vite4175 접속 ERR_CONNECTION_TIMED_OUT, BLOCKED |

최종 필수 실행 집계 **44 PASS / 0 FAIL / 0 SKIP / 2 BLOCKED** (타입·빌드2, 신규16, UI회귀20, 실제 HTTP6). 추가 ASGI TestClient 진단은 중단하여 판정 집계에서 제외하며 미완료로 별도 기록했다. 과거123개 백엔드 결과는 역사적 기록이며 재실행·합산하지 않았다.

모의 브라우저 시험은 static response interception과 합성 메타데이터/파일만 사용한다. API raw body·헤더·경로/메서드·오류·버전 ID·파일명 HTML escape·중복 제출/해제·파싱/청킹 재시도를 확인했다. JS/예상 외 콘솔 오류·예상 외 외부 요청0. 의도된 401 등 오류 응답에 따른 브라우저 resource 메시지는 오류 상황 시험으로 구분한다.

Chrome download 이벤트와 파일명은 확인됐지만 파일 저장이 canceled여서 원본 다운로드 최종 저장/해시 검증은 **BLOCKED**다. actual TCP HTTP는 격리 work DB의 원래 deny-all 의존성으로 실행했고 override를 쓰지 않았다. 실제 브라우저 HTTP가 통과했다고 주장하지 않는다. 로컬 검증 서버2개는 종료했다.

## 접근성·화면

데스크톱/모바일 캡처를 확인했다. 키보드 포커스3px·44px 주요 조작·native modal Escape/취소 focus 복원·320/375/768/1440px·한국어 라벨·table header·상태 텍스트를 검사했다. Stage2/3 영향 회귀에 명암/글자200%도 포함한다. 전체 WCAG AA·스크린리더·native zoom 및 새 문서 페이지의200% 확대 별도 정밀 감사는 미검증이다. 캡처의 자료는 시험 합성 메타데이터이며 제품 기본 데이터가 아니다.

## 보존·Git

시작 175개 파일 hash 대조. 기존 backend/fixture/schema/이전 outputs 증거 변경·삭제0. 기존 미커밋 변경은 보존하며 이번 변경과 목록을 분리했다. 사본·해시·Git diff는 work/stage4a/before, 전후 diff는 work/stage4a/CHANGES.diff. Git main HEAD `f9a01d8c5b6b2b2311f4d8d8461b0f5b55b7a182` 유지. 새 commit/merge/push/배포 없음. work/node_modules/dist는 Git 제외 확인. 비밀·API키·토큰을 코드/증거에 저장하지 않았다.

## 시간·실패 기록·다음 단계

시작 UTC04:59:59, 보고까지 **17.11분**. 최종 UI 검사합계 8.710초, 실제 HTTP 1.669초, live browser 시도 2.221초. 완료 JSON으로 남은 여러 UI 실행 합계 42.765초이며 초기 crash/ASGI 중단·명령 준비·모델 추론 등은 완전 분리 측정하지 않아 전체 테스트 시간으로 주장하지 않는다. 최종 타입/빌드 개별 시간은 미측정, Vite bundling120ms. [측정](stage4a/METRICS.json)·[재시도 진단](stage4a/DIAGNOSTIC_NOTES.json).

이전 시험의 selector 오류·download wait 미처리와320px overflow를 보존하고 수정·재실행했다. 초기 제한망 HTTP 실패는 권한 후 실제 HTTP6 PASS로 대체된 현재 결과와 구분한다. 다운로드 취소/브라우저 loopback 실패는 원인을 확정하지 않고 환경 제약으로 남긴다.

**Stage4B 자동 착수 없음.** UI·계약 기반은 준비됐으나 Gate 잔여인 다운로드 저장/브라우저 실HTTP 확인을 권고한다. 실제 인증·기관 주체·CORS/배포 검증 전 공개 운영 불가. 별도 승인 후 다음 범위를 정하고 기존 원문/권한/버전 안전성을 유지해야 한다.

[신규 검사](stage4a/VALIDATION_FINAL.json) · [Stage2](stage4a/stage2-final/RESULT.json) · [Stage3](stage4a/stage3-final/RESULT.json) · [실HTTP](stage4a/FASTAPI_HTTP_V2.json) · [실브라우저](stage4a/LIVE_BROWSER.json) · [desktop](stage4a/documents-desktop.png) · [mobile](stage4a/documents-mobile.png) · [Git](stage4a/GIT_STATUS.txt)
