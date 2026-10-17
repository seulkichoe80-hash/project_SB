# Phase 2D-5 업무절차·서식 관계 검증

## 경계와 사용 계약

기존 WorkflowCandidate, FormRequirement, EvidenceRef와 추출/RAG 계약은 수정하지 않는다. WorkflowFormService(inputs)는 Phase 2D-4 검증 엔진을 선행 호출하고 현재 활성 원본의 근거와 snapshot을 재검증한다. 모든 진입점은 서버 manager 주체만 허용한다. HTTP API, 관리자 승인·게시 API, UI, HWPX 자동 작성, 실제 모델·임베딩 호출은 추가하지 않았다.

현재 문서 모델에는 서식 분류 메타데이터가 없다. 따라서 파일명만으로 임의 문서를 서식으로 취급하지 않고, 관리자가 기존 등록 문서의 현재 활성·completed 버전을 명시적으로 분류하는 내부 서비스 register_form(principal, document_id, version_id, FormMetadata(title,purpose))를 추가했다. 이는 서식 자료 분류이며 업무절차/사용 필요성 승인이 아니다. 실제 관리 화면/등록 HTTP 경로는 이 단계 범위 밖이다.

카탈로그는 같은 SQLite에 별도 workflow_form_catalog 테이블만 추가한다. 기존 문서·버전·원본 테이블이나 user_version은 변경하지 않는다. SQL은 새 SQLite adapter에만 둔다. 분류는 기관/문서/특정 활성 버전과 메타데이터 revision에 고정한다. 서비스 객체 재생성과 SQLite 백업 복원 뒤에도 유지된다. 기본 앱 부팅은 이 서비스를 자동 활성화하거나 실제 저장소를 변경하지 않는다.

## 매칭 흐름

1. 원본 스냅샷·현재 활성 버전·기관·원본 SHA256·파싱/청킹 세대를 Phase 2D-4 검증으로 확인한다. 형식/근거 실패는 연결하지 않는다. strict extraction 그래프를 다시 파싱하여 잘못된 참조를 수락하지 않는다.
2. 서식명·사용 목적은 기존 form.title과 form.requirement의 GroundedAssertion을 그대로 보존한다. 새 목적을 생성하지 않는다. 수동 서식 메타데이터의 purpose는 검색 힌트이며 업무 필요성의 원문 증거로 사용하지 않는다.
3. 지정된 모든 단계에 해당 서식명 언급과 원문 span 겹침이 있어야 한다. 같은 이름이어도 다른 원문 단계에 임의로 연결하면 BLOCKED다. 더 긴 서식명 안에 포함된 짧은 이름도 단순 부분문자열로 단계 연결을 통과시키지 않는다.
4. 조건은 해당 단계와 원문 근거가 겹치는 기존 Condition만 연결한다. requirement 자체의 조건 문구도 조건부 언급으로 표시한다. 다른 단계의 조건은 연결하지 않는다. required는 항상 null이다. 조건/필수 표현이 있더라도 적용 필요성을 확정하지 않는다.
5. 같은 기관의 등록 상태·현재 활성·completed 파일이면서 명시적으로 서식 분류된 자료만 조회한다. 현재 활성 버전이 바뀌면 기존 분류를 자동 승계하지 않으며 새 버전 재분류 전까지 제외한다. 더 최신 비활성 버전이 있어도 기존 활성 버전은 유지한다.
6. 원본 파일명(확장자 제외), 카탈로그 title/purpose를 NFKC/casefold/구분기호 정규화한 어휘 후보 검색에 사용한다. EXACT_NAME/PARTIAL_NAME은 매칭 경로 설명일 뿐 신뢰 점수나 최종 선택이 아니다. 파일 원본을 SHA256으로 읽어 존재·무결성을 확인한다.
7. 후보0은 UNLINKED와 NO_REGISTERED_MATCH, 후보1은 CANDIDATES, 복수 후보는 AMBIGUOUS다. 표시 후보는50개 한도이며 초과는 CANDIDATE_LIMIT 이슈를 남긴다. 모든 후보는 미선택이다. 종료 시 카탈로그와 원본 snapshot을 다시 읽어 변경을 검출한다.

미등록은 '같은 기관의 현재 접근 가능한 활성 등록 서식 중 일치 후보가 없음'이라는 뜻이다. 다른 기관·사용자 PC·미등록 파일까지 존재하지 않는다고 주장하지 않는다. 원문 언급은 보존하고 등록 파일과의 연결은 비워 둔다.

## 출력·재사용·안전성

별도 workflow-forms-v1 Pydantic/JSON Schema는 기존 계약과 병행한다. 보고서는 input_snapshot_id/기관/문서/버전과 원래 source_review, 단계·조건·서식명·목적·canonical 원문 EvidenceRef, 후보 파일의 문서/버전/해시/원본명/분류 revision과 검색 경로를 기록한다. 이슈는 대상·코드·심각도·근거·사유·자동 차단 여부를 가진다.

파일 existence=CURRENT_REGISTERED_FILE은 조회 시점의 사실이다. relationship_verification=NOT_VERIFIED, relationship_status=NEEDS_REVIEW 또는 BLOCKED, selected_form_id=null, required=null이다. 원본 검토에 차단 이슈가 있으면 SOURCE_REVIEW_REQUIRED도 남긴다. semantic_verification=NOT_VERIFIED, administrator_approval=NOT_REQUESTED, publishable=false는 모든 결과에서 고정한다.

resolve_candidate(principal,candidate)는 이후 재사용 시 기관·현재 등록/활성·버전·원본 SHA256·분류 revision/메타데이터를 다시 확인한다. 임의의 ID만으로 연결하지 않는다. 이는 파일 현재성 검증이며 업무 관계를 확정하는 API가 아니다. 후속 화면/영속 승인 기능은 반드시 다시 매칭·검증해야 한다. 검증 종료 후 변경까지 막는 영속 승인 트랜잭션은 아직 없다.

## 한계와 검증

어휘 검색은 동의어·별칭·띄어쓰기 중의성·기관별 서식 의미를 이해하지 않는다. purpose의 어휘 일치도 약한 후보일 뿐이다. 조건·목적·필수 여부의 의미 정확성은 사람 검토 대상이다. 선택/확정/실모델 성능을 주장하지 않는다. 대형 기관 카탈로그의 전체 조회·반복 원본 해시 비용은 성능 검증 전이다.

신규 시험은 tests/test_workflow_forms.py이며 실제 기존 문서·파싱·청킹 서비스를 새 합성 HWPX 원본과 임시 SQLite에서 사용한다. 원본/기존 fixture는 수정하지 않는다. 정상·미등록·동명·이름 변경·filename/metadata 검색·타기관·reader·등록 해제·활성 교체·위조 근거/해시·단계/조건 오연결·무서식·부정/필수/문서 지시·재시작/복원·검사 중 변경을 확인한다. 실행 기록은 outputs/PHASE2D5_REPORT.md와 work/phase2d5에 새로 보존한다.

서식 프리뷰·필드 매핑·작성·파일 저장/재열기는 미구현이며 실행했다고 보고하지 않는다. 기존 UI는 변경하지 않았다. Phase 2D-6는 별도 사용자 요청 전 시작하지 않는다.
