# Phase 2D-3 오프라인 업무절차 후보 추출

FR-08·FR-05/07/11/14/15/18, NFR-02/03/04/05/06/07의 로컬 후보 처리 범위다. [2D-1~2 입력 계약](PHASE2D_INPUT_CONTRACT.md)과 기존 RAG/인증/EvidenceRef/원본 계약을 유지한다. 실제 LLM·임베딩·유료 서비스·자동 확정/게시·관리자 UI·React Flow·DB migration·새 HTTP API는 추가하지 않는다.

## 구성과 호출

```python
from apps.api.workflow_snapshot import WorkflowInputService
from apps.api.workflow_offline_adapter import DeterministicWorkflowAdapter
from apps.api.workflow_discovery import WorkflowDiscoveryEngine

inputs = WorkflowInputService(chunks_service)
snapshot = inputs.capture(server_manager_principal, document_id, version_id)
result = WorkflowDiscoveryEngine(inputs, DeterministicWorkflowAdapter()).run(
    server_manager_principal, snapshot)
```

Principal은 기존 서버 인증 경계에서 받아야 하며 공개 모의 로그인 경로를 만들지 않는다. 기본 앱의 deny-all은 그대로다. 이 서비스는 동기 로컬 하네스이며 요청 이후 영속 분석 job/worker를 제공하는 단계가 아니다. 원문 포함 결과를 공개 로그/Git에 무단 저장하지 않는다.

- `DeterministicWorkflowAdapter.extract(snapshot)->WorkflowExtraction`는 기존 Protocol을 구현한다. 기존 LLMAdapter.generate 반환형과 workflow-extraction-v1 스키마는 변경하지 않는다.
- 범위 처리를 위한 별도 확장 Protocol `OfflineWorkflowExtractionAdapter.extract_with_coverage(snapshot, chunk_ids)->OfflineExtractionReceipt`를 추가했다. receipt는 기존 extraction·처리 ID·미처리 사유·담당 역할 후보를 갖는다.
- `WorkflowDiscoveryEngine.run`은 전체 snapshot iterator를 완주하고 누락/순서 차이를 거부한 후 허용 범위를 어댑터에 전달한다. test_only=true/network_access=false만 받으며 구성/버전이 호출 중 바뀌거나 입력이 변조되면 거부한다. 이 flag는 신뢰된 로컬 Python 구현체의 구성 조건이지 비신뢰 코드를 sandbox하는 기능은 아니다.
- snapshot을 어댑터용으로 깊게 복제하고 결과를 strict 재검증한다. 인용은 허용·처리된 chunk ID에만 연결할 수 있다. 구조·원문 재해결·원문 문구 gate·fresh snapshot 검사를 수행한 뒤 결과를 반환한다. 역할 후보도 같은 근거 검사와 실제 step ID 검사를 받으며 인증 role/멤버십으로 사용하지 않는다.

## 결정적 규칙의 지원 범위

업무명/업무 유형 사전이나 시나리오별 응답표는 없다. 문서에서 `업무명:`, `업무:`, `절차명:`, `Workflow:`, `Procedure:` 표식 또는 파서가 명시 heading으로 추출한 문자열을 제목 후보로 사용한다. 제목이 없으면 첫 행위 원문 조각을 임시 제목으로 쓰고 검토 문제를 남긴다. 동일 제목이 반복돼도 원문 위치가 다르면 별도 후보 ID를 부여한다. 제목만 있고 행위 표식이 없으면 업무 후보를 만들지 않는다.

원본 block의 primary text span 전체가 허용 chunk 범위에 들어올 때만 블록을 분석한다. context 사본·표 셀 자식 문단은 중복 분석하지 않는다. 줄 단위로 번호/행위 어휘를 읽는다. 한국어는 제출/검토/작성/반려 등의 일반 행위 어휘와 명시 어미, 영어는 submit/review/return 등의 어휘 표식을 사용한다. 단계·업무명 자체를 코드에 고정하지 않는다. 줄마다 하나의 단계 후보를 만들며 한 줄 속 여러 행위의 의미적 분할은 하지 않는다.

단계 원문이 여러 청크에 걸치면 하나의 단계에 정확 인용 조각 actions를 보존한다. 결합 원문을 새 주장으로 꾸미지 않는다. title/label은 지원되는 첫 조각이며 분할 경계에 검토 문제를 남긴다. 기한은 명시 기간 구문 원문만 후보로 보관하며 날짜 계산은 하지 않는다. 의무 어휘는 전체 해당 구절이 한 청크에 있을 때만 기록하고, 분할된 구절의 의무는 임의 확정하지 않는다. 추출하지 못한 의미 관계는 검토 사항이며 빈 필드가 의무/기한 부재 증거는 아니다.

연속·유일한 단계 번호가 있고 양 단계 모두 조건/반려/보완/반복 어휘가 없을 때만 precedes 간선 후보를 만든다. 번호 누락/중복·무번호·조건 경계에서는 순서를 보충하지 않는다. 조건·보완·반려·반복 원문은 Condition/행위/ReviewIssue로 보존한다. `1단계로` 또는 `to step 1`처럼 명시된 목적지가 있고 참조 단계가 유일한 경우에만 conditional 간선을 만든다. 반려/보완을 정상 직선 흐름으로 바꾸지 않는다. 자기 단계 반복은 기존 스키마의 자기 간선 금지에 따라 원문/검토 사항으로 남긴다.

한국어 역할명 후보는 역할·조직 명사 어미와 주격/보조사 표식, 영어는 주어+행위 표식을 사용한다. `자료가` 같은 조건 주어를 담당자로 간주하지 않도록 어미를 제한했다. 이는 인사 정보/역할의 의미 검증이 아니다. 서식은 신청서/보고서/서식/form/template 등의 원문 언급 후보이며 실제 파일·필요 관계를 확정하지 않는다. 각 FormRequirement에 form_unresolved 검토 문제를 남긴다.

## 결과와 처리 범위

새 결과 모델/JSON Schema는 `WorkflowDiscoveryResult` / schemas/workflow-discovery-v1.schema.json이다. 기존 extraction 내부 형식은 유지하고 역할·범위·생성 정보를 별도 envelope에 둔다. 사용된 chunk별 canonical EvidenceRef 전체를 evidence_refs에 한 번씩 보존한다. original hash·기관/문서/버전·다중 block/span/anchor와 NOT_VERIFIED는 그대로다.

result는 model_id/rule_version, 입력 설정·prompt 계약 버전, engine contract/settings, snapshot ID·문서/기관/parse attempt/chunk generation을 기록한다. candidate_state는 DRAFT 또는 NEEDS_REVIEW, test_only=true이고 서버 validation은 semantic_verification=NOT_VERIFIED / administrator_approval=NOT_REQUESTED / publishable=false다. 정규 어댑터는 의미 검토 문제를 남기므로 NEEDS_REVIEW를 반환한다. 모델이 승인/게시 상태를 설정할 필드는 없다.

scope는 전체 input ID, 실제 순회 ID, 요청한 분석 ID, adapter 처리 ID와 모든 미처리 ID·사유를 분리한다. 기본 max_chunks=20000, batch_size=32이며 별도 DiscoverySettings로 제한할 수 있다. `scope_limit`, `partial_block`, `unsupported_content`, `adapter_omitted`를 구분한다. 이미지/비텍스트를 처리 완료로 허위 보고하는 receipt를 거부한다. 처리·누락 ID 중복/혼용·범위 밖 인용도 거부한다. adapter가 누락을 숨겨도 엔진은 전체 입력과 대조해 incomplete와 partial_input 문제를 생성한다.

전체 순회는 분석 완료와 다르다. 모든 지원 text를 살펴봤어도 의미적 업무를 모두 발견했다는 뜻은 아니다. 결과가 없으면 빈 workflows와 no_workflow_found 검토 항목을 반환한다. 이것을 실제 업무 부재 판정으로 쓰지 않는다. unsupported 이미지/OCR·일부만 제공된 블록 등은 pending으로 남는다. 기존 출력262144byte/1000 ID 등의 한도를 유지하며 최종 envelope는8MiB를 넘으면 전체 실패한다. 한도 실패를 complete로 꾸미거나 부분 결과를 게시하지 않는다.

## 검증·보존·후속

tests/test_workflow_discovery.py는 기존 fixture를 덮어쓰지 않고 테스트 내에서 새로운 HWPX와 ASCII PDF bytes를 생성한다. 실제 parser/chunker/snapshot 서비스에 넣고 새 업무명·다중/제목 없음/비절차 자료·청크 경계·조건/반려/반복·서식/역할/기한·어댑터 공격·누락·기관/문서/버전/세대 변경·원본/DB 무변경을 시험한다. 기존 전체 회귀와 비루프백 Python DNS/TCP 차단 runner를 사용한다. 실제 의미 품질 지표나 실모델의 미지 업무 일반화 시험이 아니다.

2D-1~2의 미커밋12개 파일/추적 diff/검증 근거를 checkout 밖 검증된 archive와 hash manifest로 보존한 후 새 feature branch로 그대로 옮겼다. 구형 코드·스키마·테스트·fixture·과거 증거는 유지한다. 결과는 로컬 반환 DTO일 뿐 영속 저장/검토/승인/게시 서비스가 아니다. 후속 Phase 2D-4의 범위는 별도 사용자 승인 후 진행하며 이번 구현은 그 단계에 진입하지 않는다.

명시 표식·행위 어휘가 없는 문서, 복합 문장, 부정/인용/설명문과 지시문 구별, 시각 순서, 표의 암묵적 역할·서식 관계는 놓치거나 위양성을 낼 수 있다. 제목/라벨 조각·문법 기반 역할·번호 기반 순서도 의미를 증명하지 않는다. 과거 snapshot과 동일 상태로 돌아온 사건 이력 탐지·대규모 반복 재파싱 성능·영속 작업/저장·독립 의미 골드셋·실제 모델·UI는 미검증/미구현이다. 원문 내 명령/링크는 데이터로만 다루고 도구/외부 fetch/권한을 부여하지 않는다.
