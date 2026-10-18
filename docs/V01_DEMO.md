# 서무ITDA v0.1 — 로컬 검토·시연 기준본

v0.1은 합성 자료를 대상으로 문서 등록·PDF/HWPX 구조 파싱·청킹·오프라인 업무 후보 추출·검증·서식 관계·영속 worker·관리자 지도/원문 검토를 통합한 기준본이다. 의미 정확성을 검증하거나 공식 절차를 승인한 제품이 아니다. 실제 AI 모델과 Supabase 로그인은 연결하지 않는다. 표준 앱의 인증 기본값은 deny-all을 유지한다.

## 재현 환경과 설치

이번 검증 환경은 Linux/Python 3.12.14, Node 24.19.0/npm 11.9.0, Playwright 1.57.0, 시스템 Chromium 154.0.8037.57이다. 로컬 실행에는 Python 3.12와 Node 24, Chromium 실행파일이 필요하다. 다음은 저장소 루트에서 실행한다. 시스템 경로의 Python/Chromium 설치와 운영용 외부 계정 설정은 이 스크립트가 수행하지 않는다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-parsing-lock.txt -r requirements-validation.txt
.venv/bin/python -m pip check
npm --prefix apps/web ci
npm --prefix apps/web run typecheck
npm --prefix apps/web run build
# 검증용 브라우저 라이브러리는 앱 의존성과 분리한다.
npm install --prefix work/v01-browser --no-save --package-lock=false playwright@1.57.0
export PLAYWRIGHT_MODULE_DIR="$PWD/work/v01-browser/node_modules"
export BROWSER_EXECUTABLE=/usr/bin/chromium
```

현재 환경에서는 기존 Python venv의 위 설치 명령·pip check와 frozen npm ci를 실제 실행했다. 별도 work 경로의 Playwright 설치와 해당 라이브러리로 E2E도 확인한다. 완전히 새로운 OS/Cloud 작업·Windows·다른 Chromium 버전의 독립 재현을 PASS로 주장하지 않는다. pip 전이 의존성과 브라우저 OS 패키지의 완전 고정은 향후 보완 항목이다. TLS/integrity 검증을 끄지 않는다.

## 전체 검증 재실행

아래 출력·캡처 경로는 존재하지 않는 새 이름을 사용한다. 기존 증거를 덮어쓰지 않는다. runner는 typecheck/build 후 backend409, UI104, 실제 HTTP E2E를 실행하고 새 summary.json에 명령·종료 코드·결과·소스 해시를 남긴다. 새 합성 API 응답 fixture도 매번 생성한다. pytest 대신 저장소의 unittest 기반 전체 runner를 사용한다.

```bash
.venv/bin/python -B scripts/validation/run_v01_checks.py \
  --output-dir work/v01-recheck-NEW \
  --capture-dir outputs/v01-recheck-NEW
```

backend와 demo 서버/worker는 비루프백 DNS/TCP 차단 가드 아래 실행한다. Chromium 모의 UI 검증과 실제 HTTP E2E는 별도 결과다. 실제 API 공급자 호출·배포를 하지 않는다. 모의 UI 시간 검증은 Chromium 가상 clock/visibility 이벤트를 사용한다.

## 대화형 로컬 시연 실행

```bash
# 새 ready-file 이름을 사용한다. 이미 실행한 서버를 임의로 종료하지 않는다.
.venv/bin/python -B scripts/validation/v01_demo_server.py \
  --synthetic-loopback-test --ready-file work/v01-demo-NEW/ready.json
```

ready.json의 url에서 로컬 브라우저로 접속한다. 포트는 사용 가능한 loopback 포트를 자동 선택한다. 이 검증 전용 서버는 127.0.0.1에만 bind하며, 임시 합성 DB/스토리지와 parse·chunk·workflow 독립 worker를 시작한다. 종료는 실행 터미널의 Ctrl+C이며 합성 임시 DB는 종료 시 제거한다. 원본 시연 fixture와 기존 사용자 자료는 건드리지 않는다. 공개 배포하거나 표준 앱 factory 대신 운영 진입점으로 사용하지 않는다.

명시적 로컬 mock 계정:

- 관리자: `v01-manager@example.test`
- 직원: `v01-reader@example.test`
- 위 두 합성 계정의 mock 입력: `synthetic-local-only` (실제 서비스 비밀번호가 아니며 다른 서비스에 사용하지 않는다.)

실제 HTTP 자동 시연은 새 출력 경로로 실행한다.

```bash
V01_CAPTURE_DIR=outputs/v01-http-NEW \
node scripts/validation/check_v01_e2e.cjs work/v01-http-NEW/results.json
```

두 매뉴얼은 브라우저 UI로 실제 업로드한다. 파싱은 등록 시 자동 등록된 영속 작업을 독립 worker가 처리하고 청킹은 기존 UI 버튼으로 요청한다. 작업 ID는 기존 멱등 POST 재확인으로 얻는다. **버전 활성화 UI는 없으므로 자동 하네스가 기존 activate HTTP API를 호출한다.** 수동 시연도 검증된 하네스로 자료를 준비하거나 해당 기존 API를 운영자 도구로 실행해야 한다. 이를 존재하는 UI인 것처럼 설명하지 않는다. **서식 분류/카탈로그 등록 UI·API는 없으며** 검증 전용 Python 사전 준비로 합성 서식 세 개를 등록한다. 준비된 서식의 실제 관계·근거·미연결·동명 후보 조회는 기존 API/UI를 사용한다.

## 대표 자료

[tests/fixtures/synthetic/v01](../tests/fixtures/synthetic/v01)의 공개 가능한 프로젝트 자체 합성 자료만 사용한다. manifest.json에 실제 SHA-256과 크기를 기록했다.

- v01-manual.hwpx: 연구 자료 대여 4단계, 보완 복귀 조건, 자료대여신청서/검토확인서/결과보고서 언급.
- v01-manual.pdf: Mineral loan 3단계, 원문 페이지 힌트·영문 조건 언급.
- v01-manual-v2.pdf: 새 버전/비활성·활성 전환 격리 검증용.
- v01-request-form.hwpx, v01-report-a.hwpx, v01-report-b.hwpx: 단일/동명 서식 후보 검증용. 실제 기관 양식이나 의무 서식이 아니다.

PDF는 프로젝트가 작성한 ASCII PDF이며 Type1 Helvetica 이름 참조만 있고 폰트 파일은 포함하지 않는다. 기존 사용자 원본이 아니며 개인정보·기관 내부자료가 없다. 생성기는 기존 위치 덮어쓰기를 거부한다. 재생성 시 다른 디렉터리를 사용한다. HWPX 패키지 시간 정보 때문에 재생성 파일 전체 바이트가 고정된다고 주장하지 않는다. 저장된 시연 파일은 manifest의 해시로 확인한다.

```bash
.venv/bin/python -B scripts/validation/build_v01_assets.py --output-dir work/v01-assets-NEW
```

## 약 4분 시연 순서

| 시간 | 보여줄 화면/행동 | 설명 |
| --- | --- | --- |
| 0:00–0:30 | 합성 관리자 로그인 → 업무 홈 | 실제 원격 인증이 아닌 로컬 mock. 홈의 '준비 중' 설명 일부는 이전 단계 문구이며 최근 문서 영역은 실제 조회가 연결되지 않음 |
| 0:30–1:20 | 문서 관리 → PDF/HWPX 합성 등록 | 등록과 파싱·청킹·AI 분석을 구별. 서버가 확인한 작업 상태와 원본 SHA 표시 |
| 1:20–2:00 | 청킹 완료 확인 → 기존 API의 활성 준비 → 업무절차 검토 | 활성화 UI/서식 등록 UI가 없음을 명시. 관리자만 요청 가능 |
| 2:00–2:50 | 추출 요청 → 독립 worker → 지도·단계 목록 | '자동 추출 후보', 의미 NOT_VERIFIED/승인 NOT_REQUESTED. 배치가 실제 순서를 확정하지 않음 |
| 2:50–3:35 | 단계 선택 → 원문·XML/페이지 힌트 → 서식/ReviewIssue | 출처 구조 확인과 의미 정확성은 다름. 단일·미등록·동명 서식 상태 구분 |
| 3:35–4:00 | 직원 접근 제한 → 관리자 로그아웃 | 보호 후보/원본 HTTP401. 실제 AI·원격 인증·공개 배포 미검증으로 마무리 |

신규 작업을 준비하는 데 실제 worker 시간이 더 걸리면 준비된 합성 세대로 시연하고 사전 준비임을 말한다. 새로고침 시 문서와 버전을 다시 선택한 후 '추출 작업 요청'으로 같은 입력의 기존 작업을 확인한다. 작업 목록이나 취소 재개 기능은 없다.

## 검증 기능과 미구현 경계

검증: 합성 PDF/HWPX 업로드·독립 파싱/청킹·worker 재시작 후 queued 작업 복구·오프라인 후보·지도/목록·단계/조건/보완·canonical EvidenceRef/원본 해시·ReviewIssue·서식 후보·기관/버전/reader·CSRF·로그아웃 차단. 처리 중 lease 만료/실패 재시도·트랜잭션 롤백은 전체 backend 회귀의 별도 시험이며 queued E2E와 혼동하지 않는다.

미구현/미검증: 실제 Supabase·LLM·임베딩, 의미 검토 완료·관리자 승인/공식 게시, HWPX 자동 작성, 홈의 최근 문서 실조회, 활성화/서식 등록 UI, 작업 목록/취소 재개, native PDF viewer/한컴 시각 페이지, 스크린 리더·실기기 장기 성능, 운영 HTTPS/클라우드 배포. 실제 서비스가 완료되었다고 주장하지 않는다.

## 내일부터 검토할 우선순위 (이번에 개발하지 않음)

1. P0: 사용자에게 v0.1 시연을 보여주고 동선/용어/실패 안내의 수정 요청을 수집한다. 실제 내부 문서 대신 익명화 요구사항/합성 예시를 받는다.
2. P1: 홈의 이전 단계 안내 문구와 현재 검토 화면을 맞추고, 활성화·서식 등록·작업 찾기 등 없는 UI의 운영 흐름을 합의한다. 새 API/기능은 별도 승인한다.
3. P1: 실제 공개 행정자료 골드셋과 사람의 의미 검토 기준을 마련한다. 결정적 mock의 문법 단서 추출을 의미 일반화로 해석하지 않는다.
4. P1: Windows/새 Linux 환경·고정 브라우저/스크린 리더·긴 문서/100노드 이상 실기기 성능을 검증한다.
5. 별도 승인: Supabase/실제 AI의 데이터·키·예산·보안 조건을 확정한 뒤 연결 검증한다. 배포는 별도 게이트다.
