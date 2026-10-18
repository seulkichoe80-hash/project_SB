# Phase 2E-2A — 관리자 업무지도 안정화

적용 요구사항: FR-09/14/18, NFR-01/02/03/04/05, WEB-02/04/05/08. 기존 Workflow 9개 경로·DTO·백엔드·DB·파서는 변경하지 않는다.

## 작업 복구

작업 목록 API와 임의의 작업 목록은 없다. 새로고침 후 작업 ID를 브라우저 저장소에서 복원하지 않는다. 관리자가 **추출 작업 요청**을 명시적으로 선택하면 POST /workflow/jobs의 동일 snapshot/settings/config/catalog 입력 멱등성으로 기존 작업을 반환받는다. 해당 입력의 작업이 없으면 새 작업이 생성되므로 읽기 전용 조회로 표현하지 않는다. 입력이 달라졌으면 다른 작업일 수 있다. 완료·취소 작업은 terminal이다. 취소 작업의 재개 API는 없으며 동일 입력 재요청도 취소 작업을 반환한다.

RETRYABLE failed + attempt < max_attempts만 명시적으로 재시도한다. PERMANENT/STALE_INPUT/횟수 초과는 입력·처리 상태 확인을 안내한다. 동기 ref latch와 busy 상태가 enqueue/retry/cancel 중복 제출을 차단한다. 변경 요청 동안 status 요청을 중단하고 늦은 조회가 취소 결과를 덮지 못하게 한다. retry/cancel 응답 유실 시 마지막 상태를 미확인으로 표시하고 기존 작업 ID를 재조회한다. enqueue 응답 유실로 ID를 알 수 없으면 명시적 멱등 재요청으로 복구하며 기존 ID를 현재 입력의 작업이라고 추측하지 않는다.

## 조회 수명

- 작업 상태: queued/processing 또는 변경 응답 유실로 상태가 미확인인 기존 작업 ID만 1.5초 후 직렬 조회. 성공 후 1.5초, 일시 오류·429·5xx·10초 timeout 시 3/6/12/24/30초로 증가하고 성공 시 초기화한다. 상태 오류 중에는 이전 상태를 현재로 표시하지 않고 작업 ID만 보유하여 '현재 상태 미확인'을 표시한다. 권한/출처 오류 또는 잘못된 응답은 차단·초기화한다.
- 문서 목록/메타데이터: 상태 조회와 분리한다. 눈에 보이는 화면에서 terminal 상태가 아직 확인되지 않았을 때 5초마다 등록/활성 변경을 확인한다. 실패 시 10/20/30초로 backoff한다. 중복 Workspace 5초 detail timer와 매 status 요청의 detail GET은 제거했다. 동일 목록이면 state 객체를 보존한다.
- 확인된 completed/failed/cancelled에서는 모든 반복 timer를 중단한다. 명시적 후보 새로고침, 창 focus/가시성 복귀에서는 현재 metadata·후보를 서버에서 다시 확인한다. terminal 유휴 중 외부 변경을 실시간 push로 통지받는 기능은 없다. 다음 서버 조회가 권한·활성·세대를 재검증하며, 상시 실시간 동기화를 보장하지 않는다.
- hidden/unmount/logout에서는 timer와 polling 요청을 abort한다. 사용자·기관·역할·문서·버전·SHA/revision 변경 시 scope를 분리한다. 작업·후보·근거 늦은 응답은 abort/ticket/generation 검사로 폐기한다.
- workflow fetch와 JSON body, 문서 목록/detail, PDF blob은 10초 deadline을 적용한다. 문서 client는 기존 호출과 호환되는 선택적 AbortSignal 인자만 추가한다.

## 지도와 근거

지도 노드/간선·선택 callback을 memoize하고 동일 문서 목록으로 인한 전체 재생성을 막는다. 100노드 검증은 DOM 수·목록/확대 조작·메타데이터 refresh 후 node data 참조 교체 수를 측정한다. FPS·실사용자 기기 성능 인증은 아니다.

선택 단계와 여러 EvidenceRef 인덱스는 현재 화면의 메모리에만 보존한다. 동일 immutable generation에서 단계 왕복/focus 재검증 시 선택을 유지하고 새 generation 또는 scope에서는 폐기한다. 인증정보·원문·문서는 localStorage/sessionStorage에 저장하지 않는다.

초기 노드는 '근거 미확인', pending은 재해결 중, 출처/인용 불일치는 '검증 실패', 통신 오류는 '미확인'으로 표시한다. 검증 전·실패 원문은 표시하지 않는다. canonical ref/구조·원문 span 검증에 성공한 경우만 'EvidenceRef 구조·출처 확인'을 표시한다. semantic_verification=NOT_VERIFIED·승인 NOT_REQUESTED를 유지한다. PDF 페이지는 힌트이며 HWPX XML 앵커/구조화 텍스트와 시각 페이지 한계를 유지한다. 지도 관계는 자동 보정하지 않는다. 기존 키보드 목록/모바일 탭/포커스 대안을 유지한다.

## 검증 명령

기존 합성 fixture를 그대로 사용한다. 과거 증거 경로를 덮어쓰지 말고 아래 NEW 경로를 매번 바꾼다. 실제 API 공급자는 사용하지 않는다.

```
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
PLAYWRIGHT_MODULE_DIR=/opt/codex/cua_node/lib/node_modules BROWSER_EXECUTABLE=/usr/bin/chromium node scripts/validation/check_phase2e2a_ui.cjs work/NEW-ui.json work/phase2e1/browser-fixture-v2.json
PLAYWRIGHT_MODULE_DIR=/opt/codex/cua_node/lib/node_modules BROWSER_EXECUTABLE=/usr/bin/chromium PHASE2E_CAPTURE_DIR=outputs/NEW-captures node scripts/validation/check_phase2e1_ui.cjs work/NEW-regression.json work/phase2e1/browser-fixture-v2.json
.venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output work/NEW-backend.json
```

신규 browser harness는 Chromium virtual clock의 500ms tick 사이에 mock HTTP를 완료시키고 visibility API 이벤트를 주입한다. 실제 OS 탭 스케줄러·스크린 리더·실기기 장기 부하·운영 HTTPS·실제 Supabase/LLM·의미 정확성은 미검증이다. 실제 loopback BFF/worker 6개와 모의 API browser 검증은 별도로 보고한다.
