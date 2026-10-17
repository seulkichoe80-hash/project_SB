# Phase 2D-5 완료 보고

실행 시점: 2026-10-17T10:50:41.391762+00:00. 범위는 오프라인 업무절차·서식 관계 후보 검증까지이며 Phase 2D-6는 시작하지 않았다.

## 1. 구현 기능

기존 WorkflowCandidate·FormRequirement·EvidenceRef·RAG 계약을 그대로 유지했다. WorkflowFormService는 Phase 2D-4의 현재 원본/기관/버전/해시/파싱·청킹 세대·EvidenceRef 재해결을 선행하고, 서식명·사용 목적·지정 단계·조건의 원문 연결을 확인한다. 원문에 없는 목적/필수성을 생성하지 않는다. title과 requirement 원문 주장을 보존하고 조건은 기존 근거가 연결된 Condition만 사용한다.

기관의 실제 등록 파일과 문서상의 서식 언급을 구별한다. 기존 문서 모델에 서식 분류가 없으므로 내부 register_form(manager, document_id, version_id, metadata)로 현재 활성·completed 버전을 명시 분류한다. 이 분류는 업무 관계 승인과 다르다. 기존 DB에는 별도 workflow_form_catalog 테이블만 비파괴 추가하며 원본/기존 테이블/스키마 버전을 바꾸지 않는다. 기본 앱 시작 시 자동 적용하지 않는다. 이번 실제 분류/쓰기 시험은 임시 합성 DB에서만 실행했다.

HTTP 경로·UI·관리자 승인·자동 게시·HWPX 자동 작성은 추가하지 않았다. 서비스와 versioned JSON Schema를 후속 기능이 사용할 수 있는 상태다.

## 2. 변경 파일 (이번 단계 10개)

신규7:
- apps/api/workflow_forms.py — 서식 분류·원문 관계 검증·어휘 후보 검색·후보 현재성 재검증
- apps/api/workflow_forms_models.py — strict workflow-forms-v1 계약
- apps/api/workflow_forms_repository.py — 별도 SQLite 분류 adapter
- schemas/workflow-forms-v1.schema.json
- tests/test_workflow_forms.py
- docs/PHASE2D5_FORM_RELATIONS.md
- outputs/PHASE2D5_REPORT.md

수정3: ARCHITECTURE.md, TASKS.md, TEST_PLAN.md의 이번 단계 절 추가.

## 3. 매칭 구조

같은 기관의 등록 상태·활성 버전·completed 상태·명시적 서식 분류를 모두 만족한 파일만 후보로 조회한다. 파일명(확장자 제외), title/purpose 메타데이터의 NFKC/casefold/구분기호 정규화 일치를 EXACT_NAME/PARTIAL_NAME으로 설명한다. 모든 후보는 원본 SHA256을 읽어 존재/무결성을 확인한다. 문서 ID·버전·해시·원본명·카탈로그 revision/메타데이터·매칭 필드를 기록한다.

최신 비활성 버전을 추천하지 않는다. 활성 교체 후 새 버전을 재분류하기 전까지 이전 분류를 자동 승계하지 않는다. 동일/유사 후보가 여럿이면 AMBIGUOUS이며 임의 선택하지 않는다. 표시 한도50개 초과는 별도 검토 이슈다. 매칭 종료 시 카탈로그와 원본 snapshot을 재검사한다. resolve_candidate는 이후 재사용 시 기관·활성·버전·해시·분류 revision을 재확인하지만 업무 관계를 확정하지 않는다.

## 4. 실제 사례

새 합성 '별빛 접수' 문서의 '별빛신청서' 언급을 동일 입력으로 실행했다:

| 사례 | match_status | 후보 수 | 최종 선택/필수 여부 |
|---|---|---:|---|
| 활성 등록 서식 없음 | UNLINKED | 0 | 모두 null |
| 같은 기관 활성 등록 파일 1개 | CANDIDATES | 1 | 모두 null |
| 서로 다른 파일에 동명 분류 2개 | AMBIGUOUS | 2 | 모두 null |

전체 실제 결과/원문 EvidenceRef/파일 식별자는 work/phase2d5/matching-examples.json에 보존했다. UNLINKED는 해당 기관의 현재 등록·접근 가능한 서식 후보가 없다는 뜻이며 외부/미등록 파일 전체의 부존재를 주장하지 않는다.

## 5. 안전성

타기관·reader·익명 접근, 타기관 분류/후보 재사용, 해제·비활성·옛 버전, 위조 근거/해시/문서 ID를 차단한다. 같은 이름이 있어도 지정 단계의 실제 원문 span이 다르면 BLOCKED이며 후보를 반환하지 않는다. 서식명의 단순 부분문자열로 다른 이름의 서식에 단계 연결하지 않는다. 원본 검토 차단 이슈는 SOURCE_REVIEW_REQUIRED로 남긴다.

CURRENT_REGISTERED_FILE은 조회 시점 파일 존재만 의미한다. 모든 관계는 NEEDS_REVIEW 또는 BLOCKED, required=null, selected_form_id=null, relationship_verification=NOT_VERIFIED, administrator_approval=NOT_REQUESTED, publishable=false다. 명시 필수 표현·조건부 언급도 실제 의무로 자동 확정하지 않는다. 문서의 규칙 변경 문자열은 자료로만 취급한다.

## 6~7. 실제 시험·회귀

- 영향 시험: `.venv/bin/python -B -m unittest discover -s tests -p test_workflow_forms.py -v` → **신규41 PASS**, 17.286초, work/phase2d5/focused-2.log. 먼저 실행한29 PASS 기록도 focused-1.log로 보존했다.
- Phase Gate: `.venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output work/phase2d5/backend-final.json` → **전체360 PASS / FAIL0 / SKIP0 / BLOCKED0**, runner 71.56초.
- 기존319개 test ID가 최종 실행에 모두 포함됨을 대조했다. 기존 Phase 2D-1~4, RAG, 파싱/청킹, 문서/기관/인증 회귀가 포함된다. 최종 결과 code_sha256과 현재 Python 파일이 모두 일치한다.
- 정상·미등록·동명·이름 변경·파일명/메타데이터/Unicode, 해제/타기관/비활성/새 활성/위조 ID·해시, 원문 EvidenceRef/단계·조건 오류, 무서식·부정·필수·문서 지시, 원본 불변·서비스 재시작·SQLite 백업 복원·검사 중 변경을 검증했다.
- 비루프백 DNS/TCP 가드 probe PASS, 차단된 외부 시도0, 실제 외부 공급자 호출0. 범위는 Python 및 상속 Python 하위 프로세스이며 loopback은 허용한다.
- 증거: work/phase2d5/backend-final.json, backend-final.log, backend-final.network.json.
- UI/typecheck/build, 서식 프리뷰/필드/작성/파일 저장·재열기, 실제 모델/유료 서비스, 실제 공개 문서 의미 goldset은 이번 미실행이다. 기존 UI 과거 수치를 새 PASS로 대체하지 않는다. 기존 Starlette/httpx deprecation warning이 남아 있다.

## 8. Git·보존

브랜치: feat/phase2d-offline-extraction.

시작 HEAD: c2c9640의 부모 e57c657a9b0adff50e254b26e6655be1179895e1. 기존 2D-4 미커밋10개를 archive/hash 및 비밀키 패턴 점검 후 사용자 승인에 따라 로컬 보존 커밋 **c2c96408c783c1ce61792ff162c325525b032b3a**으로 만들었다. 현재 HEAD도 동일하다.

보존 위치 /tmp/sb-phase2d5-preservation/phase2d4.tar.gz, manifest.json. 기존2D-4 구현·스키마·테스트·계약 문서·보고서7개는 hash 일치, 과거 raw 실행 증거8개는 바이트 일치다. 기존 원본·fixture·과거 보고를 수정/삭제하지 않았다. 이번 변경은 신규7/수정3의 미커밋 상태이며 stage하지 않았다. 기존 추적 소스/테스트/원본/fixture 변경은 없다. 비밀키/자격증명 패턴 검사 발견0; 시험 자료는 새 합성 문서만 사용했다.

원격 push·merge·배포·실제 키/계정 등록은 하지 않았다. Supabase/LLM/임베딩 API 호출0.

## 9~11. 위험·후속·시간

어휘 기반 매칭은 동의어·별칭·실제 서식 의미·규정 효력을 이해하지 못한다. 카탈로그 purpose는 관리자 메타데이터 검색 힌트이지 절차 필요성의 근거가 아니다. 원문 목적은 전체 원문 주장으로 보존하므로 정교한 목적 분류를 제공하지 않는다. 조건·부정·의무의 의미 검토는 미완료다. 분류/매칭은 내부 Python 서비스이며 실제 등록 화면/HTTP 연결은 후속 범위다. 큰 기관 카탈로그 전체 조회 및 원본 해시 비용은 성능 미검증이다. 검사 종료 이후의 변경을 막는 승인/영속 트랜잭션은 없다. 후속 사용 시 다시 매칭/현재성 검사해야 한다.

Phase 2D-5의 합성·오프라인 범위는 완료했다. Phase 2D-6는 별도 사용자 범위 승인과 NOT_VERIFIED/미선택 경계를 유지하는 조건으로 개발 착수 가능하며 이번에는 진행하지 않았다.

보존 준비부터 최종 검증/보고 작성까지 약 398초(6.6분), 사전 점검은 별도다. 신규 패키지 설치·환경 설정 변경은 없었다.
