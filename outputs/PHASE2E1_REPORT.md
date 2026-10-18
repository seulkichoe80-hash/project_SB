# Phase 2E-1 관리자 업무지도·원문 근거 검토 완료 보고

작성: 2026-10-18 09:12:29 KST. 요청 범위인 관리자 후보 탐색/근거 검토까지만 구현했다.2E-2·실제 모델·승인·공식 게시·배포는 시작하지 않았다.

## 1. 구현 화면·UX

#/workflows 관리자 전용 화면을 추가했다. 기존 디자인 토큰·공통 컴포넌트·AuthContext를 재사용하고, 실제 React Flow12.12.0을 정확 버전으로 설치해 lazy chunk로 로드한다. 문서/현재 활성 버전·작업 요청/상태/재시도/취소, 후보 업무명/단계, 조건·분기·보완/반려/반복 후보, 검토 개수·상세, 서식 후보와 원문을 연결했다.

저장된 간선만 표시하며 배치는 탐색용이다. 관계를 자동 보정/직선화하지 않는다. 표시 불가능한 관계도 별도 목록에 보존한다. 확대/축소/전체보기/pan/작은 minimap, native button 기반 키보드 목록과 모바일 지도/근거 탭을 제공한다.100노드 명시적 합성 구조로 탐색을 검증했다. 단계 선택 후 모바일 근거 제목에 focus를 보낸다. 검토 이유는 한국어로 표시하고 참조 코드는 펼쳐볼 수 있다.

의미 NOT_VERIFIED·승인 NOT_REQUESTED·자동 추출 후보/담당자 검토 필요를 명시했다. 승인·공식 게시·저장되는 수정 버튼은 없다. 실제 자료를 조회하는 관리자 검토 화면에는 미연결이라는 잘못된 안내 대신 검토 전용 상태를 표시한다.

## 2. 변경 파일

텍스트/코드16개(수정7·신규9):

- apps/web/package.json
- apps/web/package-lock.json
- apps/web/src/App.tsx
- apps/web/src/components/AppLayout.tsx
- apps/web/src/api/workflows.ts
- apps/web/src/pages/WorkflowPage.tsx
- apps/web/src/styles/workflow.css
- scripts/validation/build_phase2e1_fixture.py
- scripts/validation/check_phase2e1_ui.cjs
- scripts/validation/check_phase2e1_live.cjs
- scripts/validation/phase2e1_live_server.py
- docs/PHASE2E1_WORKFLOW_REVIEW.md
- outputs/PHASE2E1_REPORT.md
- ARCHITECTURE.md
- TASKS.md
- TEST_PLAN.md


실제 Chromium PNG 캡처 28개도 신규 상태다. 최종 전달 대상은 아래 release-live2개와 release3개이며, 나머지는 이번 검증 과정의 과거 캡처를 삭제하지 않고 보존한 것이다. 전체 변경 경로는 work/phase2e1/changed-files.json에 기록한다. 기존 원본·fixture·과거 보고는 수정하지 않았다.

## 3. 연결 API

기존 prefix `/documents/{document_id}/versions/{version_id}/workflow`의9개 경로를 모두 재사용했다:

| Method | suffix | UI |
|---|---|---|
| POST | /jobs | 작업 요청, 중복 제출 방지 |
| GET | /jobs/{job_id} | 상태 polling |
| POST | /jobs/{job_id}/retry | retryable 실패 재시도 |
| POST | /jobs/{job_id}/cancel | 처리 전/중 취소 |
| GET | /candidates | 후보 목록 |
| GET | /candidates/{candidate_id} | 상세 |
| GET | /review-issues | 선택 후보의 검토 항목 |
| GET | /form-links | 선택 후보의 서식 관계 |
| GET | /candidates/{candidate_id}/evidence | canonical 근거 목록 |

기존 documents list/detail/original 및 chunk EvidenceRef resolve를 추가 재사용한다. backend 경로·스키마·DB 변경0이다. TS DTO/guard는 실제 Pydantic/JSON Schema 및 실제 API에서 생성한 합성 JSON을 기준으로 구성했다. 세션 cookie/same-origin/no-store와 기존 CSRF를 준수한다. query generation/job ID 일치 및 ref 기관/문서/버전을 확인한다.401은 세션 해제,403/404/409/500/네트워크·잘못된 상태/응답은 초기화·안내한다.

job 목록 API가 없으므로 새로고침 후 진행 중 작업을 자동 발견하는 기능을 가장하지 않는다. 같은 입력 작업 요청으로 기존 job을 다시 받을 수 있고 완료 후보는 바로 조회한다. 구버전 옵션은 비활성 처리한다.

## 4. 노드·분기·원문 연결

실제 합성 HWPX에서4개 단계와 저장된2개 간선(선후·보완 복귀)을 표시했다. 없는 간선을 추가하지 않았다. 노드/목록 선택은 실제 단계 주장·연결 조건·업무/단계/간선/조건/서식 검토 항목·서식 CANDIDATES/UNLINKED/AMBIGUOUS와 동기화된다.

근거 목록을 다시 조회하고 서버 resolve에 canonical ref를 POST한 뒤, 전체 ref와 block scope 및 Unicode codepoint 인용 범위를 대조한다. 확인 전에는 구조·출처 확인 표시를 하지 않는다. 근거 존재와 의미 정확성을 구별한다. HWPX는 part/xml_path/tag·구조화 텍스트 및 시각 페이지/읽기 순서 미검증 안내를 표시한다. PDF는 실제 page/bbox와 세션으로 받은 원본 blob의 #page 힌트만 제공한다. native viewer 실제 페이지 렌더는 미검증이다.

문서/버전/사용자 변경 시 abort·unmount·요청 순번으로 오래된 목록/상세/작업 응답을 폐기한다. 늦은 PDF 응답도 unmount 후 URL을 만들지 않고 기존 URL은 revoke한다. 초기 자동 문서 선택이 사용자의 새 선택을 덮지 않도록 함수형 state 갱신으로 보호했다. 등록/활성/metadata는5초 주기와 window focus에서 확인하고 변경 시 후보를 비운다. 서버는 요청마다 별도로 현재성을 검증한다. 변경 감지는 polling 지연이 있다.

## 5. 권한·기관 격리

직원·익명은 관리 UI/API 호출을 제공하지 않는다. 잘못된 기관의 문서 목록/EvidenceRef, 다른 세대 응답, 위조 확인 상태/resolve 응답을 표시 전에 거부했다. 실제 BFF HTTP 통합에서 정상 세션·서버 CSRF403·잘못된 문서404·로그아웃 후 보호 화면 제거를 확인했다. backend409개에는 기존 기관/버전/reader/CSRF/Origin/위조 근거 회귀가 포함된다.

실제 공급자는 연결하지 않았다. live harness는 명시적 MockSupabaseTransport·합성 로컬 멤버십과 기존 loopback 개발용 cookie 옵션을 사용한다. 운영 기본 Secure cookie나 인증 경계를 변경하지 않았다. 공개 서비스/운영 HTTPS/TLS 실증은 아니다.

## 6. 실제 타입·빌드·회귀

| 실행 | 현재 최종 결과 | 시간 |
|---|---|---:|
| npm ci (frozen lock) | PASS | npm 로그 기준 약2초 |
| npm run typecheck | PASS | typecheck-release-confirmed.log |
| npm run build | PASS | build-release-confirmed.log |
| 신규 production Chromium·합성 API |37 PASS / FAIL0 | 41.527초 |
| 실제 loopback BFF+독립 worker HTTP |6 PASS / FAIL0 | 5.650초 |
| 기존 UI4 suites |43 PASS / FAIL0 / SKIP0 / BLOCKED0 | 11.605초 |
| 전체 backend |409 PASS / FAIL0 / SKIP0 / BLOCKED0 | 138.472초 |

신규37개는 상태·분기/원문/서식/검토·keyboard/focus/반응형/100노드·기관/세대/상태 위조·401/403/404/409/500/네트워크·빈 상태·중복/재시도/취소·늦은 문서/작업/PDF 응답 폐기를 포함한다. 실제 HTTP6개는 응답 가로채기/인증 dependency override 없이 브라우저→FastAPI BFF→영속 job→독립 worker→후보/원문 조회를 확인했다. 기존 UI43=14+6+17+6을 새로 실행했다. backend409도 과거 기록으로 대체하지 않고 새로 실행했고409개 test ID·현재 Python hash를 대조했다.

최종 증거:
- work/phase2e1/ui-release.json / ui-release.log
- work/phase2e1/live-release/results.json / run.log
- work/phase2e1/regression-release/summary.json 및 suite별 results/log
- work/phase2e1/backend-final.json / log / network.json
- work/phase2e1/install-release.log / typecheck-release-confirmed.log / build-release-confirmed.log
- work/phase2e1/dist-release-sha256.json / web-final-sha256.json / preservation-final.json

기존 잠금 package 버전/resolved/integrity를 모두 유지했고 libc 플랫폼 메타데이터10개를 보존했다. frozen lock 재설치 후 다시 빌드한 production 자산은 시험한 산출물과 byte-for-byte 동일하다. 지도 chunk는 약206KB(gzip 약67KB), 기본 JS는 약258KB(gzip 약80KB)다.

초기 브라우저 harness의 동일 URL 이동이 페이지를 재설정하지 않는 문제, 선택 상자 접근성 label, 상태 안내 수정의 타입 오류와 초기 선택 경합을 수정했다. 수정 전 실패·중간 캡처를 삭제하지 않았다. 최종 통과 판정은 위 release 기록만 사용한다. 기존 Starlette/httpx warning은 남아 있다. 실제 모델 의미·native PDF/Hancom·screen reader·실사용자 평가는 PASS로 보고하지 않는다.

외부 Supabase/LLM/임베딩 호출0. backend 비루프백 guard probe PASS·차단된 외부 시도0이고, 브라우저 예상 밖 외부 목적지0·JS exception0이다. worker도 Python 비루프백 guard 아래 실행했다. npm 의존성 설치는 공급자 호출과 별개이며 정상 registry/TLS/integrity 경로를 사용했다.

## 7. 실제 브라우저 캡처

최종 실제 HTTP 합성 환경:
- [데스크톱](phase2e1/release-live/workflow-desktop.png)
- [모바일 근거 검토](phase2e1/release-live/workflow-mobile.png)

최종 모의 API의 production 번들 검증:
- [지도+근거](phase2e1/release/workflow-desktop.png)
- [모바일 지도](phase2e1/release/workflow-mobile-map.png)
- [모바일 근거](phase2e1/release/workflow-mobile-evidence.png)

브라우저 screenshot 원본이며 그림 생성·화면 합성·사후 이미지 수정으로 대체하지 않았다. 전체 페이지를 캡처하고 캡처 직전 scroll을 문서 상단으로 이동했다. 임시 crop은 내부 확인용 work에만 있고 전달 캡처는 변경하지 않았다.

## 8~9. 보존·Git

시작 브랜치 feat/phase2d-offline-extraction / HEAD56b484d2042c1ce548f9a35f8986a62a0d446222. 기존 Phase2D-6 변경17개를 비밀정보 패턴 검사·tar/hash 사본으로 보존한 뒤 사용자 승인된 로컬 커밋 **47dd3899147c97c3db0603f7796643f44b59fd60**으로 저장했다. 현재 HEAD도 동일하다.

/tmp/sb-phase2e1-preservation/phase2d6.tar.gz와 manifest.json을 보존했다. 기존2D-6 source/schema/tests/계약/보고14개 hash와 과거 raw 증거10개 byte가 일치한다. 기존 원본·fixture·backend 기능·DB 계약 변경/삭제0이다. 관련 root 문서3개만 현재 진척을 추가했다. 개인/비밀정보는 새로 넣지 않았고 패턴 검사 발견0이며 화면 자료는 모두 새 합성 자료다. 패턴 검사는 개인정보 완전 검출 보장은 아니다.

이번 UI·검증·보고·캡처 변경은 미커밋·staging0이다. main 직접 변경·원격 push/merge·배포·실제 계정/키 등록은 하지 않았다. 설치/환경 설정은 기존 npm ci 경로로 재현하며 새 cloud draft/서버 공개 설정을 추가하지 않았다.

## 10~11. 위험·2E-2 권고·시간

UI는 관리자 읽기 전용 첫 수직 기능이다. 자동 추출·근거 연결이 업무 의미·규정 효력을 검증했다는 뜻이 아니다. native PDF 페이지 렌더/한컴 시각 위치, screen reader/실사용자 평가, 운영 TLS·실제 공급자, 큰 실제 corpus/복잡한 다수 간선은 미검증이다.100노드 시험은 탐색 성능/목록만 증명한다. 전체 목록/반복 원문 재검증·5초 polling에는 큰 문서/기관의 성능·요청 비용이 있다. 승인/수정 API, job 목록/페이지네이션·push 구독이 없어 해당 기능은 제공하지 않는다.

2E-2는 별도 승인 후 접근성 실평가, 원문 검토 탐색/성능·API pagination/job 복구 UX를 우선 권고한다. 현재 NOT_VERIFIED/미승인·기관/세대·근거 경계를 유지해야 한다. 이번에는 이후 단계로 진행하지 않았다.

보존 준비부터 최종 보고 작성까지 약 1677초(27.9분), 사전 점검 시간은 별도다. 작업 중 UI만 개발했고 실제 모델/유료 API/공개 배포는 실행하지 않았다.
