# 업무절차 JSON과 근거 계약

schemas/workflow.schema.json은 scripts/validation/workflow_contract.py의 Pydantic 모델에서 생성했다. 제목·각 단계의 label/actions/deadline/required_documents·간선 explanation은 각각 evidence를 가진다. 자료에 없는 deadline은 null, 필수서류가 없으면 빈 배열로 반환한다. evidence는 tenant/document/version/element/quote를 참조하며 위치 좌표는 모델이 생성하지 않고 서버의 원문 registry에서 재해결한다. 노드/간선 ID·허용 관계형·대상 존재·추가 필드 금지를 검사한다.

검증 계층을 분리한다.

1. JSON/스키마: 필수 필드·타입·null·빈 근거·추가 필드·중복 ID·끊어진 관계를 거부한다.
2. 근거 참조: 기관/현재 활성 문서버전·존재 element·원문 인용·위치·원본 hash 체인을 확인한다. 현재 bootstrap verifier는 original_text만 지원하고 AI 설명을 원문으로 승인하지 않는다. OCR/원본이미지는 B 단계 별도 계약으로 추가하며 제품 요구사항에서 삭제하지 않는다.
3. 의미: 인용이 존재해도 주장을 뒷받침하는지, 기한/조건/예외/순서가 맞는지 사람이 검토한 골드셋으로 평가한다. 숫자 기한의 어휘 대조는 보조 방어이며 법적 의미 판정이 아니다.

현재 verifier는 참조가 맞아도 candidate/semantic_review_required로만 반환한다. 모델이 스스로 verified 상태를 지정할 필드는 없다. unresolved_issues는 미확인 문제 목록이며 사실 안내의 근거로 사용하지 않는다. 무관한 원문 인용이 붙은 주장을 자동으로 의미 정확성 PASS 처리하지 않는 시험을 포함한다.

이것은 오프라인 계약/검증기이며 실제 AI 추출 기능·출시용 파서·권한 서비스가 아니다. 실제 모델 응답과 이미지/서식/충돌 등 전체 기능 검증은 G1-B에 남아 있다.
