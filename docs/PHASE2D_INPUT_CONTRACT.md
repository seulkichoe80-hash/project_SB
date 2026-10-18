# Phase 2D-1~2 업무절차 계약·입력 스냅샷

FR-08의 후보 구조·FR-05/14/15/18 및 NFR-02/03/04/05/06/07 기반 범위다. 실제 LLM/임베딩·업무 자동 발견 알고리즘·자동 확정/게시·관리자 승인 API·React Flow는 구현하지 않는다. 기존 RAG `LLMAdapter.generate()->Generation`과 구형 업무절차 스키마는 변경하지 않는다.

## 출력 계약

`apps.api.workflow_contracts`의 WorkflowCandidate/Step/Condition/Edge/FormRequirement/ReviewIssue/GroundedAssertion은 strict Pydantic 모델이다. 별도 `WorkflowExtractionAdapter.extract(snapshot)->WorkflowExtraction` Protocol은 model_id/test_only를 갖되 구현체나 네트워크 호출은 없다. 기존 RAG와 같은 명시 주입 패턴을 재사용하며 반환형은 분리한다.

새 JSON Schema는 schemas/workflow-extraction-v1.schema.json, workflow-input-snapshot-v1.schema.json, workflow-validation-v1.schema.json이다. 구형 schemas/workflow.schema.json·관련 verifier·테스트를 보존한다. 입력 schema_version으로 계약을 구분한다. `parse_extraction`을 출력 검증 진입점으로 사용한다. JSON Schema만으로 ID 참조·원문 지지·전체 byte 한도를 검증했다고 간주하지 않는다.

- 추가/누락 필드, 잘못된 scalar type, 공백 주장, 중복 JSON key/비유한 JSON 상수를 거부한다.
- 최대 UTF-8 출력262144byte, 업무20개, 전체 ID 대상1000개, 업무당 단계200/조건200/간선400/서식200개, 검토항목200개다. 각 주장은4000자·근거20개 이하이며 추가 배열 한도는 schema를 따른다. 초기 방어 한도이며 성능 실측 결과가 아니다.
- workflow/step/condition/edge/form/issue ID는 출력 전체에서 유일하다. 단계/조건 참조는 같은 업무 안에서만 가능하고 검토 대상은 실제 객체여야 한다.
- 간선 relation은 precedes/conditional/requires다. conditional에만 조건 ID가 필요하고 조건이 대상 단계에 적용돼야 한다. 자기 간선·중복 참조를 거부한다. 서로 다른 단계의 순환은 구조상 보존할 수 있지만 의미 검토 완료가 아니다.
- deadline은 필수 nullable 필드다. null은 미확인이며 기한 없음으로 단정하지 않는다. 의무는 근거 있는 주장 배열이다. 서식은 제목·필요 관계·대상 단계 후보이며 실제 FormTemplate 파일 연결이나 추천은 아직 하지 않는다.
- 결과 없음은 빈 workflows와 명시 ReviewIssue로 표현한다. 공백 결과를 성공 발견으로 표시하지 않는다.

## 근거 및 구형 변환

각 EvidenceCitation은 chunk_id/block_id/start/end/quote를 갖고 GroundedAssertion에 최소1개 필요하다. 모델은 기관·원본 hash/anchor·검증 상태를 생성하지 않는다. `validate_extraction(inputs, principal, snapshot, payload)`는 현재 snapshot을 재검사하고 각 인용을 canonical 원본 text span에 연결한다. 현재 단계의 모든 주장 문구는 지원 quote 안에 정확히 존재해야 한다. 임의 요약/의역은 허용하지 않는다. 이 보수적인 문자열 gate도 조건 누락·문맥 왜곡·법적 의미의 정확성을 증명하지 않는다. issues.message는 검토용 비신뢰 텍스트이며 사실 안내가 아니다.

`LegacyEvidenceAdapter`는 tenant_id/document_id/version_id/element_id/quote를 받는다. 호출자는 명시적으로 chunk_id/block_id/start를 제공해야 하며 element_id를 임의 rename하거나 첫 번째 검색 결과에 연결하지 않는다. 범위/quote/원문 span을 검사하고 EvidenceBridge에 **구형 필드 전체 + 정확 인용 범위 + 기존 canonical EvidenceRef 전체**를 보관한다. 역변환은 fresh snapshot으로 bridge를 재검증한 뒤 원래 LegacyEvidence를 반환한다. full anchor·다중 source_block·span·원본 hash·NOT_VERIFIED 상태를 제거하지 않는다. 이는 명시 mapping의 구조/인용 검증이며 구형 element와 새 block의 의미 동일성을 자동 증명하지 않는다.

구조/근거 연결 PASS는 별도 WorkflowValidation 서버 결과다. semantic_verification=NOT_VERIFIED, semantic_review_required=true, administrator_approval=NOT_REQUESTED, publishable=false만 가능하다. 모델 출력 스키마에 이 상태 필드는 없으며 삽입하면 거부한다. 모델 객체의 mutable 중첩 배열도 검증 경계에서 다시 직렬화/검증한다. 관리자 승인이나 자동 게시 경로는 없다.

## 입력 스냅샷과 사용

`WorkflowInputService(chunks).capture(manager, document_id, version_id, settings=None)`는 관리자에게 허용된 **하나의 등록 문서 버전 전체**를 읽는다. 별도 HTTP API·DB table·migration·앱 자동 실행은 추가하지 않았다. 반환 DTO는 `model_dump_json()`으로 보관 가능하며 저장소에 원문 포함 JSON을 무단 커밋/로깅하지 않는다. 역직렬화한 객체는 사용 전 반드시 서비스 `validate`를 호출한다. 현재는 스냅샷 영속 저장/복구 서비스가 아니며 2D-3 이후 작업 저장소와 연결한다.

스냅샷에는 institution/document/version, 원본 SHA256, 당시 active_version_id, version revision, parse_job_id+attempt 및 복합 parse_attempt_id, parser method, chunk_job_id+generation/config, 순서 있는 전체 input_chunk_ids/chunks/source_blocks, 설정/프롬프트 계약 버전, input_scope와 처리 coverage를 포함한다. chunk.evidence에 각 chunk와 모든 source_block·span·anchor 관계가 유지된다. snapshot_id는 이 입력 전체의 canonical JSON SHA256이며 처리 진척은 입력 identity에 포함하지 않는다. hash는 서명이 아니므로 자체 digest 검사를 인증/최신성 검사 대신 사용하지 않는다.

capture는 현재 완료된 parse_attempt·chunk generation을 읽고 원본 hash 검증→재파싱→전체 source_blocks 대조→같은 config로 전체 chunks 재구성→canonical JSON 대조를 수행한다. 저장 목록이 누락/중복/변조됐으면 실패한다. 마지막 DB 재조회로 capture 도중 변경도 검사한다. 기본32MiB(최대64MiB) snapshot byte 제한과 기존20000 block/chunk 한도를 적용하며 초과 시413으로 전체 실패한다. 입력을 몰래 잘라 complete로 만들지 않는다.

`iter_chunks(manager, snapshot, batch_size=32)`는 검색 Top-K를 쓰지 않고 전체 청크를 순서대로 제공한다. 시작·각 batch 전·완전 순회 종료에 fresh capture로 재검사한다. 중간 변경은 다음 경계에서 실패한다. batch 크기는1..200이다. 조기 중단한 소비자는 종료 재검사가 실행되지 않을 수 있으므로 mark_processed/validate를 명시 호출해야 한다. batch 중 받은 입력만으로 게시하거나 현재 문서라고 단정하는 경로는 없다.

`mark_processed`는 중복/알 수 없는/기처리 ID를 거부하고 처리/미처리 항목을 전체 ID와 정확히 분할한다. 누락 항목이 있으면 incomplete다. complete는 **호출자가 보고한 청크 처리 진척**만 의미하며 추출 성공·의미 검증·승인을 뜻하지 않는다. 순회만 해도 자동 complete로 바꾸지 않는다. 기존 DTO를 덮어쓰지 않고 새 DTO를 반환한다.

manager만 capture/validate/진척 보고가 가능하다. 다른 기관/reader/worker/미인증은 차단한다. 비활성 후보 버전은 관리자 분석용으로만 허용한다. 현재 활성 문서로 사용하려면 `validate(..., require_active=True)`를 호출해야 한다. 활성 포인터·버전 revision·parse attempt·chunk 세대/본문·기관·등록 상태가 바뀌거나 원본이 손상되면 실패한다. 다른 버전이 단지 등록됐지만 활성 전환되지 않았다면 기존 불변 버전 snapshot을 자동 무효화하지 않는다.

## 검증과 한계

tests/test_workflow_inputs.py는 strict JSON/ID/참조/한도/상태, 구형 bridge 왕복·누락/조작, 전체 순회·부분 진척·duplicate/누락 chunk·세대/버전/parse attempt/기관/해제·실제 임시 원본 손상·DB 무변경을 시험한다. 실제 데이터 원본/기존 fixture는 변경하지 않는다. 기존 offline network guard와 전체 regression runner를 재사용한다. backend 전체 회귀에서 기존 RAG 시험도 새로 실행한다.

새 검증기는 snapshot당 원본 재파싱·청킹 재구성을 반복하므로 대규모 문서 성능은 미측정이다. 배치 사이의 변경은 다음 검사 시 탐지하며 미래 저장/게시 시점에도 재검사가 필수다. parse attempt 재검사와 current pointer 비교는 현재 관측 상태 기준으로, 과거에 바뀌었다가 완전히 동일하게 복구된 상태의 사건 이력까지 증명하지 않는다. 실제 모델의 의미 품질·미지 업무 발견률·기관 공통팩 통합·관리자 승인·자동 게시·UI는 NOT_RUN/미구현이다. 단계/간선의 인용이 정확해도 의미 확정은 불가능하며 G1 B-02/B-03이나 전체 Phase2D 완료로 승격하지 않는다.
