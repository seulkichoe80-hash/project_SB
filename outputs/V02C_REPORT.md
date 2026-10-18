# 서무ITDA v0.2-C 모바일 사용성·지도 가독성

2026-10-18 KST. Feature Gate 완료. 신규 기능·API·DB·공식 승인·실제 공급자·배포로 범위를 확장하지 않았다.

## 보존·Git

시작 브랜치 feat/v02b-document-flow에서 v0.2-B 미커밋90개 파일을 확인했다. 비밀키 패턴 검출0 및 기존 보존 증거를 확인한 뒤 로컬 커밋 `e52ec2d`(feat(web): connect document activation and workflow review)로 보존했다. 해당 커밋에서 `feat/v02c-mobile-ux`를 생성했다. v0.2-A 커밋809a2dd와 기존 브랜치는 그대로다.

v0.2-C 변경은 검토용 미커밋 상태이며 추가 커밋·push·main 변경·merge·태그·공개 배포는 하지 않았다. [보존·보안 기록](v02c/preservation-security.json)은 기준 추적 파일539개 SHA-256 대조, 누락0, 기존 fixture/원본/과거 outputs 변경0, backend/API/DB/의존성/lockfile 변경0을 기록한다. 실제 비밀키 패턴 검출0이며 새 자료·화면은 합성이다. 자동 패턴 검사를 모든 민감정보 부재의 증명으로 간주하지 않는다.

## 구현 및 전후 비교

- 문서 목록: PC 표 유지.600px 이하에서는 동일 row DOM을 세로 카드로 배치하여 문서명·버전·활성·처리 상태·상세 버튼을 한 카드에서 확인한다. 복제 목록·추가 API 요청·새 캐시는 없다. 긴 이름을 줄바꿈하고 다중 버전을 구분한다.
- 계정 헤더: 긴 기관명은 독립적인 줄에서 감싸고 로그아웃·도움말은 단어 단위로 유지한다. 등록·활성화·업무절차 이동과 직원 권한 제한은 기존 동작을 그대로 사용한다.
- 모바일 업무절차:900px 이하 최초 진입은 단계 목록이 기본이다. 목록의 출처 상태를 숨기지 않으며 선택·키보드·원문 패널 포커스를 유지한다. 화면 크기 변경만으로 사용자의 지도/목록 선택을 덮어쓰지 않는다.
- 지도: 제목/상태 글자와 노드 세로 간격,44px 제어 버튼을 확대했다. ‘선택 단계 크게 보기’는 선택 노드를1배율로 중심 이동한다. 전체 맞춤으로 작아진 글씨는 목록/큰 보기로 보완한다. 좌표·배율은 탐색용이며 실제 순서·간선·분기·반려·보완 관계는 변경하지 않는다.
- 안내: 일반 경고의 중복 문장과 원문 확인 성공 설명을 줄였다. 복구 설명은 명시적인 ‘작업·복구 안내’로 접었다. 기한 null은 ‘미확인, 기한이 없다는 뜻은 아님’으로 표현한다. 기술 상태는 상세에 유지한다.
- ReviewIssue: 제거·필터링하지 않았다. ERROR 또는 auto_block이 있으면 전체 목록을 기본 펼침으로 제공한다. 출처 확인과 내용 검토 필요, NOT_VERIFIED/NOT_REQUESTED는 분리·유지한다.

## 읽기·터치·성능 실측

보관한 v0.2-B production bundle과 변경 후 bundle에 같은 합성 응답을 주입해 Chromium에서 비교했다. [측정 원본](v02c/before-after-measurements.json). 변경 전 기록은 관찰 측정이며 v0.2-C 수용 PASS로 계산하지 않았다.

| 측정 | 전 | 후 |
|---|---:|---:|
|320px 문서 목록 scroll/client 폭|600/278px|278/278px|
|375px 문서 목록 scroll/client 폭|600/333px|333/333px|
|430px 문서 목록 scroll/client 폭|600/388px|388/388px|
|320px 첫 상세 버튼 좌우 위치|517~605px(화면 밖)|38~282px(화면 안)|
|320px 상세 버튼 크기|88×68.2px|244×45.1px|
|로그아웃 크기·줄바꿈|50.9×114.4px / 여러 줄|89.5×45.1px / 단어 유지|
|도움말 크기|36.9×69.3px|62.6×44px|
|지도 확대 버튼|26×26px|44×44px|
|노드 제목/상태 글자 CSS 크기|15/11px|16/13px|
|모바일 최초 단계 목록|숨김|표시|
|선택 단계 크게 보기|없음|1배율, 제목16px|

수치는 CSS px이며 실제 기기 물리 픽셀과 구별한다. 측정한 지도 글자/상태/제어 버튼의 최소 명암 대비는6.43:1(일반 텍스트4.5:1 기준 이상)이었다. 상세 요약의 최소 높이는59.8px였다. 목록·지도 제어의44px 영역,3px 키보드 포커스·Enter 확대,320px/200% 본문 글자 확대 reflow를 검사했다. OS/native browser zoom 전체나 실제 모바일 하드웨어를 검증한 것은 아니다.

지도↔목록 전환은 추가 API 요청0이었다. 별도 기존 안정화 회귀에서 완료 후 virtual clock20초 추가 요청0,100노드 메타데이터5.5초 갱신의 node data 참조 교체0개를 새 실행으로 확인했다. 기존 memo/polling/기관·버전·취소 계약을 유지했다. 이 수치를 실사용 부하·전체 렌더링 시간·스크린 리더 성능으로 해석하지 않는다.

## 이번 실행 결과

| 검사 | 최종 결과 |
|---|---|
|TypeScript·production build|PASS|
|신규 v0.2-C UI|20 PASS / 0 FAIL|
|기존 UI154|154 PASS / 0 FAIL (104+24+26)|
|전체 backend|409 PASS / 0 FAIL / 0 SKIP / 0 BLOCKED|
|실제 v0.2-B HTTP 동선|14 PASS / 0 FAIL|
|기존 v0.1 HTTP 회귀|13 PASS / 0 FAIL (위 시험과 겹치므로 합산하지 않음)|

[실행 인덱스](v02c/verification.json)에 명령·건수·원본 경로·생산 소스 해시·시간을 기록했다. 현재 환경/의존성을 재사용했고 설치·환경 설정·패키지 변경은 없다. 전체 runner131.687초/backend127.188초(병렬 실행)였으며 개발·보존·검증은 약9분이다.

최초 전체 runner는 안정화23 PASS/1 FAIL이었다. 기존 시험이 접힌 복구 설명을 innerText로 바로 찾았기 때문이다. ‘작업·복구 안내’를 명시적으로 펼친 뒤 기존 주장을 그대로 확인하도록 수정하고 해당24개만 재실행해24 PASS를 확인했다. [최초 판정](v02c/initial-full-summary.json)을 성공으로 덮어쓰지 않았다. 제품은 전체 회귀 시작 이후 변경하지 않았으며, 과거 시험 결과를 이번 PASS로 대체하지 않았다.

실제 HTTP는 명시적 로컬 모의 인증과 합성 PDF/HWPX, 실제 FastAPI/독립 worker/SQLite/세션·CSRF·Origin·기관/버전·reader 차단을 사용했다. 브라우저 크기/문구/지연/대비 조합은 별도 mock HTTP 시험으로 구분한다. 실제 Supabase/LLM/임베딩 호출0회다.

## 실제 Chromium 캡처

동일 합성 자료의 좁은 화면 비교:

- [변경 전 모바일 지도](v02c/detail-before/initial-workflow-375.png) → [변경 후 기본 단계 목록](v02c/detail-after/initial-workflow-375.png)
- [변경 전 문서 행](v02c/detail-before/document-card-375.png) → [변경 후 문서 카드](v02c/detail-after/document-card-375.png)
- [긴 이름 변경 전 전체](v02c/before/documents-mobile.png) → [긴 이름 변경 후 전체](v02c/verified/documents-mobile.png)
- [모바일 지도 크게 보기](v02c/verified/map-mobile.png) / [목록 선택 후 원문 근거](v02c/verified/evidence-mobile.png)
- [모바일 활성화 확인창](v02c/verified/activation-mobile.png) / [직원 화면](v02c/verified/reader-mobile.png)
- PC 문서 목록: [전](v02c/before/documents-desktop.png) → [후](v02c/verified/documents-desktop.png)
- PC 업무지도: [전](v02c/before/workflow-desktop.png) → [후](v02c/verified/workflow-desktop.png)

실제 HTTP 연결 화면: [모바일 문서 관리](v02c/http/documents-mobile.png), [PC 활성화 완료](v02c/http/activated-hwpx-desktop.png), [모바일 근거](v02c/http/workflow-mobile-evidence.png). 좁은 viewport의 실제 Chromium 캡처이며 실제 휴대폰 촬영은 아니다.

## 변경 파일

제품5개:

- `apps/web/src/pages/DocumentsPage.tsx`: 단일 문서 row에 모바일 항목명 및 정확한 목록 접근성 이름.
- `apps/web/src/pages/WorkflowPage.tsx`: 모바일 최초 목록·선택 크게 보기·노드 간격·일반 안내 간소화·심각 이슈 기본 펼침.
- `apps/web/src/styles/documents.css`: 모바일 카드/긴 문서명/상세 버튼.
- `apps/web/src/styles/app.css`: 긴 기관명·계정 동작 줄바꿈.
- `apps/web/src/styles/workflow.css`: 노드 글자/44px 제어·목록 상태·모바일 읽기.

시험: 신규 `scripts/validation/check_v02c_ui.cjs`, 기존 `scripts/validation/check_phase2e2a_ui.cjs`의 설명 펼침 동작.

문서: `docs/V02C_MOBILE_UX.md`, `TEST_PLAN.md`, `TASKS.md`, 이 보고서 및 `outputs/v02c/` 신규 측정/JSON/PNG. 원본 fixture와 과거 증거는 수정하지 않았다.

## 남은 접근성 위험·준비도

스크린 리더(NVDA/VoiceOver 등), 실제 iOS/Android 터치·native zoom, 모든 조합의 WCAG2.2 AA 적합성은 미검증이다. 카드형 table은 Chromium에서 기존 row/버전/버튼 접근을 확인했지만 보조기술별 표 읽기 확인은 남아 있다. 전체 지도 맞춤은 큰 문서에서 글씨가 작아지므로 목록/선택 크게 보기를 병행한다. 심각 이슈가 많으면 펼친 목록이 길어질 수 있으며, 임의 숨김·삭제보다 정보 보존을 우선했다.

로컬 오프라인 기능의 회귀는 통과했다. 실제 AI 의미 정확성·원격 Supabase 로그인·공개 HTTPS·클라우드 영속성/운영 보안·배포 준비는 이번 UI 결과로 완료 판정하지 않는다. 기존 API의 동시 활성화 비교 후 교환 부재도 v0.2-B의 한계 그대로다. 다음 개발을 자동 시작하지 않는다.
