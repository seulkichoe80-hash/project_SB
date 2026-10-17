# 기능별 테스트 및 합격 기준

## Phase 2C-1 수용 및 회귀 시험 2026-10-17

실제 전체 실행: `python scripts/validation/run_phase2b_checks.py --output outputs/phase2c/VALIDATION_FINAL.json`. 기존 runner가 tests 전체를 discovery하므로 새 파일 test_chunking.py도 포함한다. [최종 기록](outputs/phase2c/VALIDATION_FINAL.json)은93 PASS/0 FAIL/0 SKIP/0 BLOCKED이며 이 중 기존67, 기능25, 복구1이다. [실제 샘플](outputs/phase2c/SAMPLE_CHUNKS_SEARCH.json)에 PDF/HWPX 청크와 재해결·키워드 결과를 기록했다.

| 주제 | test_chunking.py 시험 |
|---|---|
| 문단/제목·긴 분할·결정성 | deterministic_and_source_scope, long_text_exact_ranges, heading_context_and_image_no_ai_description |
| 표 구조·중복·병합 | cells_not_duplicated_as_paragraphs, table_grid_and_first_row_context, merged_table_span_preserved |
| EvidenceRef/원문·위조/버전 | pdf_hwpx_chunks_and_evidence_roundtrip, missing_anchor_and_false_quote_rejected, other_version_evidence_mixing, mixed_versions_rejected |
| 기관/인증/검색 | org_read_mutation_and_evidence_blocked, reader_and_anonymous_controls, keyword_filename_body_and_active_only, hangul_and_heading_search, sql_literals_and_query_limits |
| 활성/해제·어댑터 방어 | active_version_swap_and_deregister, search_adapter_cannot_bypass_active_filter_or_invent_text |
| 실패/중단/중복/재시작 | idempotent_jobs_and_results, transaction_failure_no_partial_search_retry, expired_claim_recovery_and_stale_fence, new_version_failure_keeps_old_active, cancel_during_chunking, actual_worker_kill_and_new_process_recovery, server_reopen_and_worker_subprocess, real_http_server_process_restart_search |
| fixture 재현성 | safe_fixture_recovery_and_no_overwrite |

재개 최초55 PASS/12 FAIL은 자료 누락에 따른 실제 결과로 보존했다. v2는 과거 hash와 동일 복원, 과거 v1은 미복원이며 기존 부정 계약 시험1개는 새 별도 CRC 손상 자료를 사용한다. [복구 보고](outputs/RESUME_RECOVERY_20261017.md)를 따른다. 기존67개가 모두 통과했어도 옛 v1 바이트 자체를 다시 시험한 것으로 표현하지 않는다. 현재 작업의 Skill 검증 수준과 테스트 실행 기준은 아래 실행 시점과 범위를 따른다. 의미 정확성·한컴 시각 순서·실인증·LLM/embedding·전체 대표 corpus·운영 배포는 NOT_RUN이다.

## Phase 2B 실제 수용·회귀 시험

실행: `python scripts/validation/run_phase2b_checks.py --output outputs/phase2b/VALIDATION_NEW_RUN.json`. 최신 실제 기록은 [VALIDATION_FINAL_V2.json](outputs/phase2b/VALIDATION_FINAL_V2.json), [전체 앵커 증거](outputs/phase2b/SAMPLE_EXTRACTION.json)다. test_parsing.py 신규34개와 기존33개를 함께 실행했다. 새 결과는 기존 결과를 덮어쓰지 않는다.

| 요구 시험 | 신규 테스트(test_ 접두사 생략) |
|---|---|
| PDF 문단·표·위치 | pdf_paragraphs, pdf_table_grid, pdf_merged_cell, pdf_page_coordinates |
| HWPX 문단·제목·표·이미지/XML | hwpx_paragraphs_no_fake_page, hwpx_explicit_heading, hwpx_cells_and_table, hwpx_merged_cell, hwpx_image_relationship_and_xml_roundtrip, hwpx_spine_order_not_filename_sort |
| 손상/미추출/원본 변조 | corrupt_parsers_reject, no_invented_text_for_unextractable_page, corrupt_stored_original_and_wrong_worker_do_not_publish |
| 없는 앵커·없는 인용·다른 버전·가짜 블록 | evidence_resolve_and_invalid_anchor, hwpx_anchor_rejects_missing_xml_path, cross_version_anchor_rejected, batch_rejects_fabricated_and_mixed_blocks, direct_publication_rejects_forged_anchor, claim_cannot_mix_another_document_version |
| 저장/재조회·중복·DB 부분 실패 | auto_job_and_structured_storage_restart, hwpx_integration, duplicate_request_and_claim, publish_failure_rolls_back_all_blocks |
| 실패 재시도·중단/만료·새 worker | parser_failure_retry_no_partial_results, expired_worker_fenced_and_recovered, worker_renew_and_expiration_cap, worker_cli_restart_after_real_process_kill |
| 새 후보 실패·기존 활성본 | failed_new_version_keeps_previous_active |
| 기관/역할·논리 해제·우회 | tenant_and_auth_extraction_isolation, reader_requires_active_version_and_failed_retry_is_explicit, deregister_inflight_cannot_publish, legacy_transition_cannot_bypass_parser |
| schema v1→v2·실제 HTTP | legacy_database_backfill_preserves_original_and_active_pointer, real_http_upload_worker_evidence_roundtrip |
| 기존 전체 회귀 | test_document_api.py·test_live_document_http.py·test_validation_contracts.py 기존33개 무수정 재실행 |

파싱 신규 시험은 parsing_enabled=True, 기존 Phase 2A factory 시험은 호환 모드를 사용한다. 표준 앱 진입점은 파싱을 켜고 기존 수동 완료 API 우회를 막는 것을 별도 시험했다. 한컴 화면/시각 순서·대표 공개 corpus·독립 의미 검토·LLM/임베딩·클라우드는 NOT_RUN이며 위67개 PASS에 포함하지 않는다. 기존 정량 골드셋 목표와 안전성 게이트는 유지한다.

## Phase 2A 실제 수용·회귀 시험

실행법: Python 3.12 환경에서 `python scripts/validation/run_phase2a_checks.py --output outputs/phase2a/VALIDATION_NEW_RUN.json`. 기존 결과는 덮어쓰지 않는다. 이번 최종 증거는 [VALIDATION_FINAL.json](outputs/phase2a/VALIDATION_FINAL.json), 범위/한계는 [보고](outputs/PHASE2A_REPORT.md)다. tests/test_document_api.py의 시험은 명시 모의 주체, test_live_document_http.py는 별도 Uvicorn 프로세스의 루프백 HTTP와 강제 종료 후 재기동이다. 외부 서비스/실제 인증을 시험하지 않는다.

| 필수 항목 | 실행 테스트(test_ 접두사 생략) |
|---|---|
| 정상 PDF·HWPX | normal_pdf_metadata, normal_hwpx |
| 비허용·위장 형식 | unsupported_extension, disguised_extension_and_mime, malformed_pdf_structure, unsafe_or_corrupt_hwpx |
| 같은 이름·동일 내용 | same_filename_distinct_content, duplicate_content_idempotent, concurrent_duplicate_upload_published_once |
| SHA-256·원본 불변 | sha256_and_download, immutable_and_tamper_detection |
| 저장/DB 실패 복구 | partial_write_failure_recovery, database_failure_after_file_write |
| 버전 교체·후보 실패 | version_switch, failed_candidate_keeps_old_active |
| 등록 해제 | deregister_retains_original_and_blocks_jobs |
| 기관 간 조회·수정 차단 | cross_institution_read_and_mutation, client_institution_does_not_set_authority |
| 미인증·역할 | unauthenticated_cannot_spoof_tenant, reader_cannot_register_or_process |
| 잘못된 상태·중복 실행 | invalid_state_and_duplicate_claim |
| 재시작 영속성·실 HTTP | restart_persistence, real_http_and_process_restart |
| 크기·경로·자료 선언 | size_and_path_and_classification |

기존 test_validation_contracts.py의 9개를 함께 실행한다. FR-01/14/15/18·NFR-01/02/06/07, WEB-02/03/05/06/07의 로컬 부분만 대응한다. 실제 JWT·클라우드·백업복원·요청량 제한·브라우저·AI·검색 캐시 연동은 NOT_RUN이며 아래 전체 시험을 PASS로 바꾸지 않는다.

## 저장소 안정화와 현재 게이트

루트의 7개 문서가 단일 기준이다. [G1 A/B/C/D](docs/G1_GATES.md)가 개발/기능/배포/제출의 현재 진입 조건이며 이전 전체 G1 차단 설명보다 우선한다. 전체 G1 미완료와 개별 A 준비를 구별한다. 이번 변경은 사용자 지시에 따른 게이트 재분류이며 미실행 시험을 PASS로 바꾸지 않는다.

상태: 인터넷망 웹앱 테스트 계획 v1.2. Phase 1의 제한된 스파이크 PASS는 PHASE1_REPORT/PHASE1_EVIDENCE에 보존한다. 전체 앱·실모델·클라우드·인증 기능 수용시험은 미실행이며 기존 미통과 G1을 승격하지 않는다. 본 수치는 S1 §11 제안값을 팀의 목표로 채택한 것으로 공모전 공식 합격점이나 측정 결과가 아니다.

## 데이터와 실행 기록

골드셋 목표: 공개 출장·복무 자료 2종, 다른 기관 표현의 합성 매뉴얼 2종, 미지 업무 매뉴얼 1종 이상. PDF/HWPX, 텍스트/표/캡처/스캔, 충돌 규정·시행일 경계·정보 없음·손상 파일·저해상도 캡처·문서 지시 공격을 포함한다. 캡처 20장 이상·질의 40개 이상·절차 10개 이상, FR-13 채택 시 필드 20개 이상을 준비한다. 기관 A/B 및 기본팩 접근 허용 차이를 구성한다. 전부 민감정보 없는 자료여야 한다.

Phase 1에서 fixture ID, 원본 해시·공개 출처·이용조건, 기대 문서/버전/요소·원문 발췌, 기대 순서·필드·금지 단정, 평가 표본·모델 설정을 동결한다. 개발 중 보지 않은 업무는 최종 검증용으로 분리한다. 기대값은 사람이 확인하고 변경 시 이유·평가 영향·검토자를 기록한다. 실제 파일을 확보하지 않았으면 확보됨으로 표기하지 않는다.

시험 기록은 일시/KST, 변경 ID·FR/NFR, 코드 commit 또는 파일 해시, OS/장비/의존성, 모델/임베딩/프롬프트/파서·자료 버전, 실제 명령, 표본 수·분자/분모·성공률, 실패 사례·원인·조치·재시험 결과를 포함한다. 결과는 PASS/FAIL/NOT_RUN/BLOCKED/조건부 이월을 구별한다. mock/실제 모델, 사전 처리/실시간 처리도 구별한다. 결과/로그는 공개·합성 최소 발췌만 사용한다.

## 정량 게이트

| 영역 | 계산법 | 프로젝트 합격 목표 |
|---|---|---|
| 파싱 | 순서·종류·위치가 모두 맞는 수동 라벨 핵심 요소 / 전체 평가 핵심 요소 | 95% 이상 |
| OCR·설명 | 정확 인식되고 설명이 사실과 일치하는 핵심 UI 요소 / 라벨 UI 요소 | 85% 이상, 보이지 않는 조작 생성은 별도 실패 |
| 검색 | 정답 근거가 Top-5에 1개 이상 있는 답변 가능 질문 / 답변 가능 질문 | 90% 이상, 정보 없음 질의는 별도 안전성 평가 |
| 근거 정확도 | 실제 주장을 뒷받침하고 위치/버전이 맞는 핵심 주장 / 전체 평가 핵심 주장 | 95% 이상 |
| 근거 연결 완전성 | 유효 EvidenceRef 또는 미검증 억제가 있는 모든 AI 주장/노드/관계/추천/설명/규정 필드 / 전체 평가 항목 | 100%, 근거 없이 확정 안내 0건 |
| 업무지도 | 정확 발견 단계 / 정답 단계, 올바른 선후 관계 / 평가 선후 관계를 각각 계산 | 두 지표 각각 85% 이상 |
| 서식 추천 | 정답 서식이 Top-3에 포함된 질문 / 서식 정답이 있는 질문 | 90% 이상 |
| 초안 조건부 | 정확히 채운 필수 필드 / 시험 필수 필드 | 95% 이상 + 모든 시험 생성본 열기/레이아웃 육안 합격 |
| 갱신 | 교체/등록 해제 후 비활성 내용의 검색·답변·지도·추천·캐시 노출 | 0건 |
| 신뢰성 | 근거 없는 의무·기한 확정, 충돌 은폐, 권한 누출, 원본 변경 | 각각 0건 |
| 이식성 | 미지 기관팩 적용을 위한 업무별 코드 수정 수 | 0건 |

95% 근거 정확도는 허용 가능한 미세 연결 오류의 정량 목표이지 출처 없는 의무 안내 허용치가 아니다. 안전성 0건 게이트가 우선한다. 분모 0 또는 시험 누락은 통과가 아니다. 모델 비결정성을 고려해 실제 모델별 질의셋 3회 결과와 최저값을 보고하고, 안전성은 모든 실행에서 통과해야 한다. 표본 축소는 변경 사유·영향·사용자 합의 없이 목표 달성 수단으로 쓰지 않는다.

## 기능별 수용 테스트

| ID | 입력/행동 | 관찰과 합격 기준 |
|---|---|---|
| FR-01 | PDF/HWPX 여러 개 등록, 기관별 목록 조회 | ID·출처·상태·오류 표시, 타기관 목록/파일 접근 0건 |
| FR-02 | 표·그림이 문단 사이에 있는 문서 파싱 | 요소 순서/본문·표·그림 참조 및 원문 앵커 대조, 파싱 정량 목표 통과 |
| FR-03 | 캡처 20장 이상 OCR/설명, 흐린 이미지 포함 | 핵심 UI 목표 충족, 판독불가 경고, 화면에 없는 버튼·조작 확정 0건 |
| FR-04 | 검색 표현과 원본 비교 | 원본 해시 동일, 원문/OCR/AI 별도 필드, 설명에 원본 이미지·인접 문단 근거 |
| FR-05 | 긴 절차·표·그림 경계 청킹 | 표 헤더/순서/이미지 맥락과 요소 ID 유지, 출처 손실 0건 |
| FR-06 | 등록만 수행, 자동 색인 후 질의 | 수동 재작업 없이 키워드+벡터 검색, Top-5 목표 및 기관/활성 필터 통과 |
| FR-07 | 정상·정보부족·근거없음·기한 질문 | 필요 시 추가질문/미확인, 주장별 근거 클릭과 정확도 목표, 무근거 의무 0건 |
| FR-08 | 기본팩에 없는 미지 업무 문서 투입 | 코드 변경 없이 업무·단계·서식 후보, 모든 후보 근거/상태 표시 |
| FR-09 | 노드 선택·질문 전환, 목록 탐색 | 현재 단계·다음 행동·근거·서식 일치, 단계/선후 정량 목표, 목록에서 동등 정보 접근 |
| FR-10 | 제목/관계 드래그·클릭 편집, 자연어 제안 취소·적용 | 채택 시 권한·전후 차이·명시 확인·취소·이력, 제안만으로 원본 변경 0건 |
| FR-11 | 상황·기관·업무 단계별 서식 검색 | Top-3 목표, 추천 이유/원문 근거, 비활성/타기관 서식 0건 |
| FR-12 | 지원·미지원·렌더 실패 서식 열기 | 지원 서식 육안 확인, 실패 시 제한 안내·권한 검사된 원본 다운로드, 원본 불변 |
| FR-13 | 채택한 1종 이상에 정상/누락 입력 | 확인 후 별도 초안, 필드 정량/재열기/레이아웃 통과, 원본 해시 동일 |
| FR-14 | 메타 수정·추출 정정·버전 교체·등록 해제 | 정정/공식 개정 구분, 옛 검색/지도/추천/캐시 0건, 원본 보존, 작업 실패 시 활성본 안정 |
| FR-15 | A/B 기관·직원/관리자·공통팩 권한 교차 | API 직접 호출/다운로드/대화에서도 권한 누출 0건, 적용기간 경계 정확 |
| FR-16 | 동일 업무의 상충 기한/문서 지위 제공 | 양쪽 근거·시점·적용범위 표시, 자동 법적 효력 단정 0건 |
| FR-17 | 채택 시 정상 변경과 중요 충돌 처리 | 정상은 자동, 중요한 예외만 알림, 행위자/시각/이전 버전·영향 확인 |
| FR-18 | 파싱/OCR/API/색인 단계별 강제 실패와 재시도 | 실패 구역/단계/복구 표시, 중복 활성본 0건, 중간 결과 미게시 |
| FR-19 | 채택 시 평가 모드·모델/임베딩 설정 변경 | 같은 골드셋 비교와 버전 기록, mock/실제 구분, 재색인 전 혼합 금지 |

FR-10·13·17·19는 미채택 시 이월로 기록한다. NFR-04의 교체 계약과 최소 감사이력 검증은 해당 P1 채택 여부와 무관하게 수행한다.

## 안전성과 회귀 시험

- NFR-01/06: 확장자 위장·과대 파일·압축폭탄·zip slip·손상 PDF/HWPX·능동 콘텐츠·경로 조작을 안전한 합성 fixture로 검사한다. 거부 시 원본·임시파일·상태·로그가 일관돼야 한다. 악성 실행은 허용하지 않는다.
- NFR-01/03: 문서 속 “다른 기관 자료 공개/지침 무시/키 출력” 지시가 권한·시스템 정책·도구 실행으로 이어지지 않아야 한다. 미승인 외부 전송 0건, 민감정보/키 일반 로그 노출 0건.
- NFR-02/07: 등록 전후·교체·등록 해제·재시도·서식 작성·백업 복구의 원본 SHA-256 동일. 관리자 과거 버전 접근과 직원 현재 검색을 구분한다.
- NFR-03: 지도 노드뿐 아니라 간선·그림 설명·추천 이유·초안 필드까지 원문 위치 열기. HWPX XML 앵커만 검증됐으면 페이지 번호를 보장하지 않는다.
- NFR-04: 실제 생성 모델 2종에 같은 핵심 시나리오·골드셋 적용. 공급자 SDK 변경 없이 설정/어댑터로 교체, 스키마·근거·타임아웃 검증. 임베딩 모델 변경은 차원 확인·별도 색인 구축·전환·되돌림 시험. 접근 불가 시 미검증으로 남긴다.
- NFR-05/07: 재시작·중단·중복 작업·색인 장애·전환 도중 질의·백업 복구에 활성 버전/권한 일관성 유지. 성능은 표본별 크기/페이지/캡처 수와 처리시간·메모리·p50/p95를 기록하며 Phase 1 예산을 넘으면 실패 처리한다. 예산 미정이면 성능 통과를 선언하지 않는다.

## 테스트 실행 시점과 범위

테스트 실행 시점·범위·재사용의 단일 기준은 이 절이다. AGENTS와 품질검증 Skill은 이 기준을 참조한다.

| 시점 / 검증 수준 | 필수 실행 범위 |
|---|---|
| 개발 중 | 변경 기능의 단위 테스트. 실패를 수정한 뒤 해당 시험을 재실행 |
| 기능 완료 / Feature Gate | 영향 범위 통합 테스트와 해당 핵심 안전성 회귀 |
| Phase 완료 / Phase Gate | 기존 전체 회귀테스트 및 전체 P0·채택 P1의 해당 단계 합격 기준 대조 |
| 배포·제출 전 / Release Gate | 전체 회귀 및 전체 보안·실패 복구·브라우저·독립 실행 검증. 실제 배포 검증은 승인된 환경에서 수행 |
| Read-only Review | 기존 문서·증거만 검토. 테스트·앱 실행 및 파일·캐시·로그 변경 없이 미확인 항목과 추가 검증 필요사항 보고 |

변경 영향 기준: 파서/OCR는 청킹·검색·지도까지, 검색/모델은 답변·추천·충돌까지, 데이터/권한은 전체 핵심 여정까지, 서식은 프리뷰·필드·저장·재열기까지 확장한다. 해당 핵심 안전성은 인증·기관 격리·EvidenceRef/원문 앵커·원본 불변·활성 버전/등록 해제·비밀/예산 통제·실패/중단 복구다. 인증·저장·검색·모델·파서 변경에는 관련 안전성 회귀를 반드시 포함한다. DB schema·스토리지 정책·배포 변경은 재시작·복원·권한·영향받는 브라우저 동작을 재검증한다. 미구현 기능의 시험을 실행한 것으로 간주하지 않는다.

결과 재사용은 코드·fixture·환경·잠금파일·설정·명령·검증 범위가 모두 동일하고 기존 결과가 유효할 때만 허용한다. 비교 근거와 재사용할 실행 기록을 명시하며 어느 하나라도 변경 영향이 있으면 관련 테스트를 반드시 재실행한다. Phase 완료 시에는 재사용만으로 대체하지 않고 전체 회귀를 실행한다.

이번 작업과 관계없는 미구현·미승인 항목은 기존 NOT_RUN/BLOCKED 기록과 증거를 참조하고 상태를 유지한다. 매번 같은 미검증 목록을 새로 작성하지 않되 대상 게이트의 필수 항목은 누락 없이 대조한다. 필수 시험의 미실행을 PASS 또는 게이트 완료로 처리하지 않는다. 안전성 실패 시 다음 기능 확대·출시를 중단하고 수정·재시험한다. 문서만 변경한 경우 링크·요구사항·안전성·Skill 계약을 검증하며 앱 전체 시험은 반복하지 않는다. 단, 실행 가능한 테스트 계약·기대값·기능 동작에 영향이 있으면 관련 시험을 수행한다.

## 심사위원 독립 실행 합격

11/07~11/10 공개 URL 브라우저 사용과 독립 소스 실행을 분리해 평가한다. 소스 재현은 개발자 로컬 의존성·캐시·절대경로 없는 깨끗한 환경에서 다른 검증자가 README/구동안내서만 읽고 설치, 환경변수/키 설정, 초기화, 비민감 자료 투입, A/B/C 흐름, 근거 열기, 교체/등록 해제, 재시작·중지, 모델 교체를 완료해야 한다. 실제 명령과 성공 증거를 기록한다. 네트워크·모델 접근·하드웨어 제한과 미지원 기능은 공개한다. mock 단독 구동은 AI 심사 실행 합격으로 대체하지 않는다.

비공개 공공 GitLab 심사위원 권한은 승인된 등록 후 검증한다. 소스+실행방법/실행물, Topics 세션2, 신청서 링크·PDF 파일명·3~5쪽 안내서·약 5분 이내 MP4·라이선스·비밀 제외와 제출 후보 해시를 대조한다. 원격/발송 승인이 없으면 로컬 준비만 PASS 가능하며 실제 제출은 NOT_RUN이다.

## 인터넷망 추가 시험과 합격 기준

아래 전부 현재 NOT_RUN이다. 설계/공식 문서/기존 스파이크를 시험 통과로 대체하지 않는다. 한도·RPO/RTO·기간의 단일 기준은 ARCHITECTURE 설정표다. 기존 정량 골드셋 목표와 무근거 의무/권한 누출/원본 변경 0건 게이트를 유지한다.

| ID | 행동/입력 | 합격 기준 |
|---|---|---|
| WEB-01 | PC Chrome/Edge에서 공개 HTTPS URL, SPA 깊은 경로 새로고침·로그인 callback·React Flow 노드 클릭·목록 대안 | 일반 사용자 설치 없이 6단계 핵심 여정, 혼합 콘텐츠/브라우저 오류 없음, 노드/간선/원문·서식 동기화. 비로그인은 공개 합성 예시만 |
| WEB-02 | 비로그인·직원·관리자·기관 A/B·만료/위조 JWT·비활성 멤버십으로 API 직접 호출 | 미인증 401·권한 부족 403 또는 정보 비노출 404, 업로드/작업/검색/근거/서식/다운로드 전 경로 교차기관 0건. admin UI 숨김 우회 실패 |
| WEB-03 | 내부/비공개/개인정보/키 모사 합성 fixture·출처 미기재, 위장 확장자·MIME·손상·크기 초과·zip slip/폭탄 | 거부/격리, 허용 데이터가 아니면 외부 API 전송 0회. 자동 탐지 한계와 관리자 공개성 확인 기록. 실제 민감자료로 시험하지 않음 |
| WEB-04 | 프런트 번들·소스맵·브라우저 network·로그·오류·Git 후보에서 시크릿 유출 검사, 환경 변수 누락 | LLM/DB/스토리지 관리키 노출 0건, 키 누락은 안전한 오류, VITE_*에 비밀 없음. Auth 공개키와 비밀을 구별 |
| WEB-05 | 새 업로드 후 API/worker 재시작·재배포, DB commit 실패·객체 쓰기 실패·중복/중단/lease 만료 | 원본 해시/기관/활성 세대 유지, 부분 게시 0건, 옛 버전/등록 해제 결과 노출0, 멱등 재처리, orphan 대사 가능. 영속성은 실제 승인 환경에서 확인 |
| WEB-06 | 허용/미허용 origin preflight·본문 요청, 동시 AI/업로드·예산 초과·문서 인젝션/XSS/SSRF 모사 | 정확 origin만 CORS 응답; 비브라우저도 인증 필수. 413/415/429 등 정책별 명확한 거부, 초과 시 LLM 호출 차단, tool/키/타기관 유출0. 가격 reservation 경쟁상태 시험 |
| WEB-07 | DB 스냅샷·객체 백업 복원, 등록 해제 후 복원, 로그 만료·기간 만료 이벤트 | 파일/메타 해시 일치, 권한·tombstone 유지, RPO/RTO 목표 실측; DB 백업만으로 파일 복원 PASS 금지. 원본 자동삭제 없음, 폐기는 승인 여부로 구별 |
| WEB-08 | 승인 후 실제 2모델 동일 골드셋/3회, 인터넷 장애·401/429/timeout·교체·초기 임베딩·재색인 | 스키마/근거/의미/순서·지연·비용 기록, 모델 자동 외부 fallback 없음. 기존 목표 통과, 오류 안전 표시, 실제 실행을 mock과 분리 |

### 추가 정확성 시험

정상 공개/합성 HWPX에서 section2/section10·spine·중첩/병합표·떠 있는 그림·다단/머리말/각주를 렌더와 대조한다. 구조용 ZIP 합격을 정상 HWPX 호환성 표본으로 계산하지 않는다. JSON 형식, 인용 ID 재해결, 실제 주장 의미 일치를 각각 계산한다. 실제 한글 임베딩·기관/시점/활성 필터를 적용해 Top-5와 키워드 품질을 평가한다. 수동 벡터 4개 시험은 의미검색 성능 분모에 넣지 않는다.

### 배포와 심사 독립 실행

G1-C 최소 클라우드 시험은 사용자 승인 후 작은 공개/합성 자료를 넣고 재시작·재배포 뒤 DB/파일/권한/해시를 확인한다. production 공개 전 TLS·CORS·초대 로그인·관리자/기관 격리·시크릿·예산·백업을 통과해야 한다. 무료 절전 후 첫 응답, worker 중단 재개, 만료/저장/연결 제한과 요금 경고도 기록한다. hosting 성공만으로 제품 FR 통과라고 하지 않는다.

G6에서 평가자는 URL과 제한된 평가 계정으로 PC 브라우저 핵심 여정을 수행하고, 별도 검증자는 소스+문서만으로 네이티브 실행·실제 모델 설정·샘플·중지/재시작·교체/등록 해제를 수행한다. Docker 유무는 네이티브 경로 실패를 가리는 조건이 아니다. 소스 실행에는 런타임 설치가 필요할 수 있으나 일반 사용자는 설치하지 않는다. 평가자용 자격증명·키를 공개 README/Git에 적지 않고 승인된 경로로 전달한다.

향후 폐쇄망/내부 GPU/오프라인 런타임은 P2 확장 검증이다. 기존 같은 PC 오프라인 패키지 설치 PASS는 역사적 증거로 보존하되 현재 인터넷망 G1/G6의 필수 폐쇄망 시험으로 요구하지 않는다.

### 회귀와 결과 기록

실행 범위와 재사용은 [테스트 실행 시점과 범위](#테스트-실행-시점과-범위)를 따른다. 실제 명령·환경/버전·자료 hash·건수/분모·비용·실패/조치/재시험을 새 실행 기록에 남긴다. 구조화된 실행 기록을 공통 근거로 사용하고 보고서는 변경점·결과·남은 위험과 증거 링크를 요약한다. 과거 증거를 덮어쓰지 않으며 미승인 유료 호출·배포는 BLOCKED/NOT_RUN으로 유지한다.

## 로컬 RAG 계약 시험

FR-05/06/07/14/15/18·NFR-02/03/04/05/06/07, WEB-02/04/05/08의 로컬 범위는 tests/test_rag_contracts.py로 검증한다. 결정성·정규화/차원/NaN·멱등/세대 교체·롤백/중단/재시작·기관/활성/해제/앵커·위조 후보·응답 근거/억제 계약을 포함한다. 합성 개발 부분표본은 tests/fixtures/synthetic/rag-goldset.json 및 scripts/validation/evaluate_phase2c2a.py를 사용한다. test_only 지표는 실제 임베딩/LLM 의미 품질·전체 대표셋 PASS가 아니다. 기존 실행 시점/범위·정량 목표·Phase 전체 회귀 규칙을 유지한다.

## 실제 AI 시험 사전검증 계약

[Phase 2C-2B 실행계획](docs/PHASE2C2B_EXECUTION_PLAN.md)의 동일 기관/활성 snapshot에서 keyword/vector/hybrid Recall@5·10, 기존 Hit@5 목표, 인용 유효성·독립 의미 정확성·무근거 주장·보류·기관 격리·모델별 지연/usage/비용을 검증한다. 상세 지표·분모·추가 실험 목표·호출수·중단 기준은 계획을 따르며 기존 정량 목표와 안전성0건 게이트는 유지한다. 합성 정답 초안은 독립 검토·동결 전 실모델 합격 근거로 사용하지 않는다. 사전 자료 구조검사와 기존123 PASS를 실제 AI 성능 실측으로 계산하지 않는다. 공급자 연결·비용/검색/출력 계약 변경 후 영향 회귀, 해당 Phase 완료 시 전체 회귀는 기존 실행 기준대로 필수다.

## Stage2 프런트엔드 기반 검증

scripts/validation/check_stage2_ui.cjs는 프로덕션4화면·active navigation·history/unknown 경로·키보드/포커스·미구현 표시·320/375/768px·글자200% reflow·명암6쌍·공통 상태 SSR·콘솔/외부/API 무요청을 검증한다. socket 제한 시 정적 응답 interception을 실제 HTTP 연동과 구별한다. 전체 WCAG/스크린리더/native zoom·실인증은 별도 미검증이다. Stage2 Feature Gate는 프런트엔드 영향 범위를 시험하며 backend 전체 회귀를 수행한 것으로 표시하지 않는다.

## Stage3 업무 홈 검증

scripts/validation/check_stage3_home.cjs로 홈 동선·history/reload·키보드·미구현 표시·320~1440px·글자200%를 검증한다. loading/empty/error는 SSR 표시 계약이며 실API 상태 전이가 아니다. Stage2 영향 회귀를 유지한다. 정적 응답 interception과 실제 HTTP 검증을 구별하고 5초 인지·3회 접근은 사용자 검증 전 확정하지 않는다. [현재 증거](outputs/STAGE3_REPORT.md).

## Stage4A 문서 관리 검증

`scripts/validation/check_stage4a_ui.cjs`는 File 확장자/크기/기본 시그니처, raw body·자료분류 헤더·endpoint/method, 오류 구분, 버전 목록·상세/전환, HTML 파일명 안전 표시, 중복 제출·재시도·등록 해제 확인·다운로드·키보드/320~1440px를 시험한다. 서버 전체 형식 검사와 기관 권한 검증을 브라우저 검사로 대체하지 않는다. 브라우저 모의 응답과 실제 서버 HTTP는 별도 결과로 보관한다.

`check_stage4a_http.py`는 격리 work DB와 원래 deny-all 인증으로 실제 TCP HTTP401 차단만 검사한다. `check_stage4a_live.cjs`는 별도 실행된 local FastAPI8000/Vite preview4175에 실제 브라우저로 접속하며 auth override/interception을 사용하지 않는다. 실제 인증 성공 경로는 미구현이므로 모의 성공 시험을 운영 통합 PASS로 승격하지 않는다.

Stage2/3 회귀는 의도적으로 변경된 문서 페이지를 401 모의 응답으로 확인한다. 과거 테스트 무요청 조건은 문서 GET만 예외이며 이외 외부/API 요청을 허용하지 않는다. 과거 증거는 수정하지 않는다. Chrome 다운로드 취소는 BLOCKED이며 파일 저장 PASS가 아니다. [실행 근거](outputs/STAGE4A_REPORT.md).

## Stage4B-2 인증 검증

Stage4B-3A는 [연결 계약](docs/STAGE4B3A_SUPABASE_TRANSPORT.md)과 tests/test_supabase_transport.py를 따른다. 실제 HTTP serialization/고정 host/path·HTTPS/서버 키/timeout·상태/응답크기/형식·신원/만료·비밀 비노출 시험 및 기존 BFF30개를 HTTP MockTransport 경로로 재사용한다. scripts/validation/run_stage4b3a_checks.py의 비루프백 DNS/TCP 차단 아래 기존153개와 신규 시험을 모두 실행하며 실제 외부 요청을 허용하지 않는다. 기존 UI43개·typecheck/build도 회귀한다. 실제 TLS handshake·공급자 JWT 검증 성공·계정/키·유료 API·배포는 모의 PASS로 승격하지 않는다.

tests/test_auth.py는 mock Supabase 전송→실제 BFF session dependency 경로의30개 시험이다. 401/403/타기관404, CSRF·Origin/단회challenge, 위조·중복cookie, 만료/idle/회전/logout/replay, 계정·기관·멤버십정지, 기관관리범위, worker/metadata 권한상승차단, provider미설정/실패, throttle, additive backup/별도복원·기존 source_blocks/버전/원본해시, 세션재시작/hash 저장·민감값미포함을 검사한다. dependency override가 아닌 실제 session dependency를 사용한다. 기존 전체123개도 인증 영향 회귀로 실행하며 mock principal 계약과 새 세션계약을 구분한다.

scripts/validation/check_stage4b2_ui.cjs는 공급자미설정·로그인/기관표시·reader UI·logout/만료·브라우저저장소·키보드/반응형6개를 모의HTTP로 검증한다. 이전 Stage2/3/4A 회귀는 명시 mock /auth/status/me 응답만 추가하며 실제 공급자 성공으로 세지 않는다. 별도 local HTTP harness는 loopback dev cookie로만 BFF 실제 왕복을 확인하고 production Secure/TLS 성공과 구별한다. [실행 근거](outputs/STAGE4B2_REPORT.md).
