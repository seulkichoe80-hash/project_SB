# Phase 2E-2A 완료 보고

기록: 2026-10-18T09:27:30.521141+09:00 · 범위는 관리자 UI 안정화/작업 복구 UX에 한정한다. setup/runtime 및 seomuitda-quality-check의 해당 게이트를 적용했다. 실제 공급자 연결·게시·다음 단계는 진행하지 않았다.

1. **구현**: 같은 입력의 명시적 POST 멱등 재요청 안내, RETRYABLE/입력 오류/횟수 초과/취소 구분, enqueue/retry/cancel latch, 변경 응답 유실 재조회, 늦은 status가 취소를 되돌리는 경합 차단. visible 직렬 polling·10초 deadline·지수 backoff·terminal 중단. 사용자/기관/역할/문서/버전/SHA/revision scope 폐기. 단계/다중 근거 선택 유지, 근거 미확인/실패/성공 구분, map node/edge memoization.

2. **복구 범위와 한계**: 새로고침 후 자동 작업 목록은 없다. 관리자가 '추출 작업 요청'을 선택해 현재 입력에 대응하는 기존 작업을 확인한다. 기존 작업이 없으면 새 작업을 생성하므로 읽기 전용 조회가 아니다. 취소 작업 재개는 지원하지 않는다. 입력 snapshot/settings/config/catalog가 달라지면 다른 작업일 수 있다. localStorage/sessionStorage에 ID·인증·원문·문서를 저장하지 않는다. terminal 유휴는 자동 갱신하지 않으므로 외부 변경의 실시간 감지는 지원하지 않는다. 명시 조회/focus/가시성 복귀 및 다음 서버 요청에서 현재성을 재검증한다. terminal 미확인 상태의 visible 문서 목록은 등록/활성 감지를 위해 5초 간격으로 유지하며, job status polling과 구별한다.

3. **요청량 실측**: 동일 Chromium/합성 API/fixture/측정 harness로 보존한 2E-1 production bundle과 최종 bundle을 비교했다. 완료 작업 안정화 후 가상20초의 자동 요청 **8→0회(100% 감소)**. 100노드의 메타데이터 갱신5.5초에서 node data 참조 교체 **100→0개**. 이는 Chromium 가상 시간 및 visibility 이벤트 주입 검증이다. 실기기 FPS·실제 OS 탭 스케줄링 인증으로 해석하지 않는다. 원시 before: work/phase2e2a/baseline-complete.json, after: work/phase2e2a/ui-complete.json.

4. **최종 실행**:

| 검사 | PASS / FAIL | 실행시간 |
| --- | --- | --- |
| 신규 UI |24 / 0|31.585초|
| 기존 Workflow UI |37 / 0|53.157초|
| 기존 나머지 UI |43 / 0|23.579초|
| 실제 loopback BFF/worker HTTP |6 / 0|11.937초|
| 전체 backend |409 / 0, SKIP0/BLOCKED0|130.872초|
| 타입 검사 / 프로덕션 빌드 |PASS / PASS|build 로그 Vite 0.408초(전체 tsc 포함 시간과 구별)|

최종 UI80=37+43은 과거 결과 대체가 아닌 새 실행이다. 실제 HTTP6은 모의 identity를 명시한 실제 BFF 세션/CSRF/영속 worker 경로이며 실제 Supabase가 아니다. backend409도 새로 실행했고 최종 backend Python/requirements 해시가 실행 입력과 동일하다. UI24는 hidden/logout/terminal, timeout/429/503/backoff, 명시 복구, retry 한도/중복, 늦은 취소 응답/응답 유실, 다중 근거 선택/focus, 실패 원문 미표시, 활성 변경/reader, 100노드와 캐시 비저장을 포함한다.

중간 실패 기록은 삭제하지 않았다. build-2의 지도 목록 ids 참조 누락을 수정했고 최종 typecheck/build가 통과했다. 중간37개 검증에서 발견한 EvidenceRef 목록 오류의 로딩 미종료를 수정했다. 가상 clock 시험의 횟수 경계는 요청 시작 시각으로 최소 backoff 간격을 확인하도록 정밀화했다. 최종 결과는 위 complete 파일만 사용한다.

5. **접근성/원문 상태**: 기존 keyboard 단계 목록·focus·mobile 탭·320~1440 반응형80회귀를 유지했다. 현재 generation 내 단계 왕복과 focus 재검증에서 근거 선택을 보존한다. 원문 인용·canonical EvidenceRef 검증 전/실패 원문은 숨기고 의미 NOT_VERIFIED/승인 NOT_REQUESTED를 유지한다. PDF 페이지는 힌트이며 HWPX XML/구조화 텍스트와 시각 페이지 한계를 안내한다. 스크린 리더와 한컴/native PDF 시각 이동은 미검증이다.

6. **보존·보안**: 작업 시작 시 44개 보존 사본은 모두 보존 커밋의 byte/hash와 일치한다. 이후 승인된 기존 소스·기준 문서 변경은 별도 Git diff로 추적한다. /tmp/sb-phase2e2a-preservation/prior-work.tar.gz·manifest.json도 보유한다. 기존 원본/fixture/과거 증거 삭제0, backend/API/DB/파서 변경0, 의존성/lock 변경0. 고신뢰 비밀키 패턴 발견0, 화면·HTTP 자료는 합성이다. 패턴 검사는 모든 개인정보 검출을 보장하지 않는다. Python DNS/TCP guard probe PASS, 차단된 외부 시도0, 브라우저 예상 밖 목적지0. 실제 Supabase/LLM/임베딩 호출0. 배포·push·merge0.

7. **Git**: feat/phase2d-offline-extraction. 2E-1 보존 HEAD `16025642d24c0aaa67a3071734d0fb9682226901`. 2E-2A 변경은 미커밋·미스테이징이며 main에 반영하지 않았다. 원격 작업은 수행하지 않았다.

8. **미해결 문제**: 작업 목록/자동 재개/취소 재개는 기존 API 밖이다. terminal 상태의 외부 변경은 다음 focus/명시 조회까지 알 수 없다. native 탭 동작·실기기 장기 성능·스크린 리더·실제 공급자·의미 검증·운영 배포는 미검증으로 유지한다. 100노드 참조 안정성을 전체 성능 인증으로 확대하지 않는다.

9. **다음 단계**: 이번 범위의 기능 게이트는 충족하여 2E-2B 요구사항 검토를 시작할 수 있다. 구현은 사용자 범위 승인 후에만 진행한다. 최종 승인/게시 API와 실제 공급자 연결은 구현하지 않았다.

10. **소요시간**: 보존 시작부터 보고서 생성까지 652초(약 10.9분). 초기 지침/저장소 확인 시간은 이 측정에 포함하지 않는다. Linux Python3.12.14/Node24.19.0/npm11.9.0/Chromium 기존 환경을 사용했고 설치·환경 설정 변경은 필요하지 않았다.

실행 명령·정책: [UI 계약](../docs/PHASE2E2A_UI_STABILITY.md). 원시 결과/소스·dist 해시/상세 계수: [검증 요약](phase2e2a/validation-summary.json). 실제 HTTP의 확인 완료 화면: [데스크톱](phase2e2a/live-complete/workflow-desktop.png), [모바일](phase2e2a/live-complete/workflow-mobile.png). live capture harness는 기존 check_phase2e1_live.cjs 사본에 원문 인용 로딩 완료 대기만 추가한 work/phase2e2a/check_live_verified.cjs이며 기능/검증 assertion을 제거하지 않았다.

## 변경 파일

- `ARCHITECTURE.md`
- `TASKS.md`
- `TEST_PLAN.md`
- `apps/web/src/api/documents.ts`
- `apps/web/src/api/requestDeadline.ts`
- `apps/web/src/api/workflows.ts`
- `apps/web/src/hooks/useVisiblePolling.ts`
- `apps/web/src/pages/WorkflowPage.tsx`
- `docs/PHASE2E2A_UI_STABILITY.md`
- `outputs/PHASE2E2A_REPORT.md`
- `outputs/phase2e2a/complete/workflow-desktop.png`
- `outputs/phase2e2a/complete/workflow-mobile-evidence.png`
- `outputs/phase2e2a/complete/workflow-mobile-map.png`
- `outputs/phase2e2a/delivery/workflow-desktop.png`
- `outputs/phase2e2a/delivery/workflow-mobile-evidence.png`
- `outputs/phase2e2a/delivery/workflow-mobile-map.png`
- `outputs/phase2e2a/final/workflow-desktop.png`
- `outputs/phase2e2a/final/workflow-mobile-evidence.png`
- `outputs/phase2e2a/final/workflow-mobile-map.png`
- `outputs/phase2e2a/live-complete/workflow-desktop.png`
- `outputs/phase2e2a/live-complete/workflow-mobile.png`
- `outputs/phase2e2a/live-final/workflow-desktop.png`
- `outputs/phase2e2a/live-final/workflow-mobile.png`
- `outputs/phase2e2a/live-release/workflow-desktop.png`
- `outputs/phase2e2a/live-release/workflow-mobile.png`
- `outputs/phase2e2a/regression-1/workflow-desktop.png`
- `outputs/phase2e2a/regression-1/workflow-mobile-evidence.png`
- `outputs/phase2e2a/regression-1/workflow-mobile-map.png`
- `outputs/phase2e2a/regression-2/workflow-desktop.png`
- `outputs/phase2e2a/regression-2/workflow-mobile-evidence.png`
- `outputs/phase2e2a/regression-2/workflow-mobile-map.png`
- `outputs/phase2e2a/validation-summary.json`
- `scripts/validation/check_phase2e2a_ui.cjs`

중간 캡처도 삭제하지 않았으며 최종 검증은 complete/live-complete 경로를 참조한다.
