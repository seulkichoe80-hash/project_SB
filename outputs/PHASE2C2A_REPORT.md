# Phase 2C-2A 로컬 RAG 계약 완료 보고

범위: 결정적 임베딩/LLM 테스트 대역과 벡터·HybridSearch·근거 응답 계약. 실제 모델·의미검색 품질/전체 G1/G2·공개 운영 완료가 아니다. 최적화된 Skill의 Feature Gate 및 이 세부 Phase의 Phase Gate를 적용했다.

## 구현과 파일

신규 apps/api/rag_adapters.py, vector_repository.py, rag_service.py: EmbeddingSpec/Adapter, 결정적 L2 벡터·검증, SQLite 세대/원자 게시/재색인/롤백, keyword/vector/RRF, 현재 원문 EvidenceRef 재검사, LLMAdapter/Claim/Generation·추출식 candidate/근거부족 억제. API는 로컬 Python 서비스 메서드이며 기존 HTTP 경로·앱 인증은 변경하지 않았다. 외부 공급자는 코드에서 비활성이다.

신규 tests/test_rag_contracts.py, tests/fixtures/synthetic/rag-goldset.json, scripts/validation/evaluate_phase2c2a.py 및 docs/PHASE2C2A_RAG.md, docs/LLM_API_PREFLIGHT.md. 기존 수정은 TASKS/ARCHITECTURE/TEST_PLAN의 해당 절 추가뿐이다. 앱/fixture/이전 테스트·증거는 시작 snapshot 해시와 일치한다. PRD/AGENTS/Skill/README는 이번에 수정하지 않았다. 이전 미커밋 목록과 이번 구분은 [PRESERVATION](phase2c2a/PRESERVATION.json)에 보존했다.

## 실제 검증

- 기존93개 기록의 코드 hash·설치 의존성은 시작 시 일치했다. 기존 기록을 신규 PASS로 계산하지 않았다.
- `work/phase2b/venv/Scripts/python.exe -B -m unittest discover -s tests -p test_rag_contracts.py -v`: 첫 실행은 네트워크 제한의 TestClient 대기 후 중단. 루프백 권한 확보 후 재실행25 PASS/13.618초. 이후 추가 시험은 전체 실행에 포함했다.
- `work/phase2b/venv/Scripts/python.exe -B scripts/validation/run_phase2b_checks.py --output outputs/phase2c2a/VALIDATION_FINAL.json`: **123 PASS /0 FAIL/0 SKIP/0 BLOCKED**, 기존93+신규30, **63.559초**. 기존 runner는 전체 discovery이며 not_run의 embeddings는 실제 모델을 의미한다. 테스트 대역의 벡터 계산과 구별한다.
- 평가 스크립트의 초기/최종 결과는 별도 파일로 보존했다. 최종 `--output outputs/phase2c2a/GOLDSET_EVALUATION_FINAL.json`.
- 기관/버전/현재 청킹 세대·등록 해제 필터, 가짜 text/anchor/중복 후보, 원본 hash·응답 직전 해제, 잘못된 LLM 인용/무근거 생성 거부, 임베딩 실패·중단/게시 rollback·재시도·별도 Python 프로세스 재시작 PASS.
- 문서 링크·요구사항·기존 파일 hash·검증 후 코드 hash·Git diff check 모두 통과. 전체 기능 이외 미검증을 승격하지 않았다.

## 평가와 위험

합성2문서/13질의(답변가능11, 정보없음/기관차단2)의 개발 부분표본. keyword/vector/hybrid 모두 Hit@5=11/11이나 실제 임베딩 품질이 아니다. vector/hybrid는 정답 없음 후보1건, keyword0건으로 기록했다. 테스트 응답은 키워드 지지가 없는 문맥을 배제해 답변을 보류한다. 독립 인간 검토·holdout·대표 한국어/공개 corpus 및 전체5문서/40질의/20캡처/10절차는 미완료다.

실제 어댑터·의미 검증·관련성 보정·영속 indexing job/lease·대규모 성능·실인증/보안 운영·클라우드는 미완료다. 오프라인 동기 index를 실제 HTTP 장시간 처리로 사용하지 않는다. hash-character-v1은 의미 모델이 아니며 문자열/앵커 검증은 semantic entailment가 아니다. 기존 Starlette/httpx deprecation 경고는 남았다.

API·비용·보안 검토는 [사전 검토](../docs/LLM_API_PREFLIGHT.md)를 따른다. 기존 gpt-4.1-mini의 공식 Deprecated 표시를 확인했고 자동 교체하지 않았다. Gemini 후보 계정/수명/자료정책과 실제2모델 교체는 별도 검증이 필요하다. 키를 조회·저장하지 않았고 유료 API/자원·React Flow·push·배포는0회다.

## 시간·Git·다음 단계

첫 UTC 계측부터 증거 작성 시점까지 **477.062초**. 최초 읽기 이전 및 최종 응답 생성은 미측정이므로 요청 전체 정확 시간은 측정 불가다. 완료된 테스트 실행 합계77.177초(13.618+63.559), 중단 실행 시간은 미측정이다. 모델 추론시간은 미측정이며 추정하지 않는다. 도구23 wrapper 요청/43 nested 호출, 테스트 실행3회 중 재시작1회. 세부 정의는 [METRICS](phase2c2a/METRICS.json)를 따른다.

main/HEAD f9a01d8c5b6b2b2311f4d8d8461b0f5b55b7a182 유지, staged 변경·추가 커밋/push/배포 없음. 시작 전 변경사항은 PRESERVATION의 preexisting_git_changes, 이번 추가 파일과 문서 변경은 별도 목록이다.

**제한된 Phase 2C-2A 계약 범위는 완료.** 다음은 B-03 실제 임베딩 후보/한국어 골드셋/관련성 억제·세대 전환 검증, B-02 실제 모델의 계정 가용성·대안·자료·예산 승인과 의미 검증부터 조건부 착수 가능하다. 사용자 승인 없이 유료 호출하지 않는다.
