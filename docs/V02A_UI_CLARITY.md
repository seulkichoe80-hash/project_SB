# v0.2-A 화면 상태·문구 정합성

범위: P0-1 기능 상태 안내, P0-3 근거 상태 표현. 기반 main은 PR #2 병합 커밋 `8986b912083876ccfd6dabb207a92cc33d00d1e5`다. API·DB·인증 정책·업무절차 엔진은 변경하지 않는다.

## 기능 안내

- 관리자: 문서 등록·조회 가능, 기존 등록 화면으로 이동.
- 직원(reader): 문서 조회 가능, 등록·작업 요청은 자료관리자에게 문의.
- 미로그인: 로그인 필요. 권한 확인 중에는 관리자 기능을 사용할 수 있다고 표시하지 않는다.
- 공통 안내는 문서 이용 권한, 실제 AI 미연결, 기존 `/auth/status`의 원격 인증 설정 여부를 구분한다. `remote_enabled=true`도 실제 원격 연결 성공의 증거로 표현하지 않는다.
- 최근 문서·처리 건수는 미연결을 유지한다. 임의 데이터나 신규 API 요청을 추가하지 않는다.

## 근거 상태

- `근거 보기`: 원문 확인 동작.
- `근거 확인 필요`: 아직 재해결하지 않았거나 실패한 근거.
- `출처 확인`: 기존 API와 클라이언트 범위·원문 인용 대조를 통과한 근거. 현재 선택 단계의 중복을 제거한 모든 인용을 확인해야 지도 노드에도 표시한다.
- `내용 검토 필요`: 출처 확인 여부와 독립적인 의미 검토 상태. 의미 검증과 관리자 승인을 승격하지 않는다.

확인 상태는 메모리에만 보관한다. 단계·후보·세대·문서 전환 시 재확인하며, 다른 단계에 이전 상태를 적용하지 않는다. 재요청 중에는 현재 근거의 확인 상태를 제거한다. 원문 누락·검증 실패·네트워크 오류를 구분하고, 기존 권한/버전 오류 초기화 계약을 유지한다.

`EvidenceRef`, `NOT_VERIFIED`, `NOT_REQUESTED`, XML 경로 등은 접힌 상세 정보에서 확인한다. HWPX 페이지·읽기 순서 미검증 안내는 유지한다. 공개·합성 자료만 사용하며 실제 공급자 호출·자동 승인·게시를 제공하지 않는다.

## 검증 및 재현

기존 설치 환경과 `docs/V01_DEMO.md`의 로컬 실행 방법을 재사용한다. 설치 설정·잠금파일 변경은 없다.

```bash
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
PLAYWRIGHT_MODULE_DIR="$PWD/work/v01-browser/node_modules" \
BROWSER_EXECUTABLE=/usr/bin/chromium \
.venv/bin/python -B scripts/validation/run_v01_checks.py \
  --output-dir work/v02a/NEW-regression --capture-dir outputs/v02a/NEW-regression
PLAYWRIGHT_MODULE_DIR="$PWD/work/v01-browser/node_modules" \
BROWSER_EXECUTABLE=/usr/bin/chromium V02A_CAPTURE_DIR=outputs/v02a/NEW-ui \
node scripts/validation/check_v02a_ui.cjs work/v02a/NEW-ui.json \
  work/v02a/NEW-regression/browser-fixture.json
```

출력은 매번 새로운 경로를 지정하여 과거 증거를 보존한다.
