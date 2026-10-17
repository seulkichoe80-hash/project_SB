# 인터넷망 전환 변경이력

변경일 2026-10-16 KST. 근거는 사용자의 인터넷망 웹앱 운영·설계 전환 요청이다. 새 프로젝트를 생성하지 않았으며 현재 폴더/기술 스파이크/역사적 증거를 유지했다.

## 승인 범위와 실제 작업

이번 승인 범위는 기준 문서 7개 수정, 공식 배포/가격 자료 조사, 변경 전 사본·diff·일관성 검증이다. 전체 웹앱 구현·클라우드 자원 생성·LLM API 호출·공개 배포·원격 push는 수행하지 않았다. 현재 URL·실제 운영계정/리전·키는 미생성/미검증이다.

## 전후 결정

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| 운영 대상 | 내부망/폐쇄망 이식과 로컬 환경 가능성 검토 포함 | 공개 HTTPS URL·PC 브라우저 무설치, 인증된 기관 자료/관리 |
| 폐쇄망·GPU | G1 검토 항목에 포함 | 현재 MVP 비대상, 후속 확장. 과거 FAIL/BLOCKED를 PASS로 바꾸지 않음 |
| Docker | 실행환경 미구성 | 선택적 독립 심사 수단, 클라우드 전체 개발 중단 사유 아님 |
| 검증 스택 | React/Vite/TS·Flow·FastAPI·SQLite 등 제한 PASS | 그대로 유지, cloud PostgreSQL/Auth/비공개 ObjectStore 추가 검증 |
| LLM | 모의 계약 PASS·실모델 미검증 | 인터넷 API 후보2종·서버 시크릿·호출 예산/데이터 승인 후 실검증 |
| 파일/DB | 로컬 저장 경계 논리 설계 | DB+객체 게시 프로토콜·영속 Job/worker·대사·재배포/백업/권한 검증 |
| 민감자료 | 공개/합성 원칙과 마스킹/격리 표현 | 실제 내부/비공개/개인정보·키 금지, 마스킹만으로 허용하지 않음 |
| G1 | 실제 파서/AI/근거/환경 미통과 | G1-A 기존 증거/G1-B 기술/G1-C 승인된 최소 클라우드 실증으로 구분, 전체 미통과 |
| 보안/운영 | 기본 격리·원본/근거·오류 복구 | WEB-01~08 HTTPS·Auth·CORS·사용/비용·영속성·기간·비밀/로그 시험 추가 |
| 사용자와 평가자 | 재현 설치 위주 설명 | 직원은 브라우저만, 독립 소스 실행 평가자는 런타임 설치/별도 모델 설정 |
| 저장소/지침 | outputs를 문서 루트라고 표현 | 실제 CWD와 구분, workspace 루트 배치 제안. 이동/자동 발견/호출 검증은 미수행 |
| 범위/일정 | FR-01~19·P0/P1/P2·40/30/30·11/11 | 보존. 11/09 동결·11/10 후보 유지, 최신 공지/정확 마감 미검증 |

기존 PRD 기능 행과 TEST_PLAN의 19개 기능 행은 문구까지 동일하게 유지했다. NFR·운영 설명은 사용자 지시에 맞춰 수정하고 WEB 기준을 추가했다. 기존 골드셋 목표·안전성 0건·조건부 초안과 이월 기준은 유지한다.

## 보존과 확인 경계

[변경 전 ZIP](INTERNET_TRANSITION_BEFORE.zip)은 원래 10개 파일과 해시를 포함한다. 원래 Phase 1 보고/수정 제안/증거 ZIP 3개는 현재 위치에서도 불변이다. 첨부 DOCX/HWPX 원본의 해시도 종전 값과 동일하다. [통합 diff](INTERNET_TRANSITION.diff)는 7개 문서 전후 차이다. [배포 전략](INTERNET_DEPLOYMENT_STRATEGY.md)은 현재 판단과 공식 출처·비용 가정을 담는다.

이번 문서 검증 PASS는 제품/브라우저/클라우드/모델 시험 PASS가 아니다. Skill 형식 검증도 자동 발견이나 실제 G1 통과와 다르다. 기존 PHASE1_DOCUMENT_CHANGES의 적용 전 제안은 역사적 이력으로 남겼고 일부를 이번 문서에 반영했으나 실제 구현은 미수행이다.

## 파일별 전후 SHA-256

| 파일 | 변경 전 | 변경 후 |
|---|---|---|
| PRD.md | `1a61205ebf98a778fb61a3903dd8313dbd7dc72ade6965fa4833c7c67a793650` | `7fa422d6ceb976d003c2f3d2e938ca34023f380fb0baa7c6d24ca690f5651bc7` |
| AGENTS.md | `974656d20841fe2df590d539d0432bcfab2559399f6a7097cd52dc2e08f8a867` | `c2c9a715ab342f8d9ee08205028a0812dcd92aecec681c510472a0d2ddf14f81` |
| TASKS.md | `e576b1197c7111a4edb98cc8155ae29bab1a144294f1a2ce3057894a33d13590` | `8b362f0741f40f4d85e17159c30a9e045b777d7d292d4d4c39a9ae5917bb04d1` |
| ARCHITECTURE.md | `09a1b468dce39609d521f88644a90d1183f6e02a49f5edf5231ca4c7f6c7c23f` | `a42b4987d34ca59edfaa2b93ec1633ee3f0065344f2d7cdeb6d05cc8c5fad69c` |
| TEST_PLAN.md | `39b6a2ac1daf0737950114ef817cd5e91819b86c0dfb363b8fc57289f436c567` | `14856d684f670160edc8de82e05821f5a41c9e278087dbcea7d88337d96e91f8` |
| README.md | `ea894a53be53e816f2928aa0ae7bf35ef17f4a5b4887924173eaaad410721108` | `bc2370901f24f2fb3cda692fb70104b478c36157d4544c6ae731cde166138591` |
| .agents/skills/seomuitda-quality-check/SKILL.md | `b18334bebdf74cb68539487f4694e697fe8823d3b64513ddd33a55219d696c82` | `f3c99b51c5ede8a7a5b032e4982a7a330d5231be364c7e54c81eb8e1c4cc2338` |

## 정적 검증 기록

- PASS: baseline_snapshot_10_files
- PASS: seven_documents_changed
- PASS: phase1_three_files_unchanged
- PASS: prd_19_requirement_rows_exactly_preserved
- PASS: test_19_rows_preserved
- PASS: P0_P1_P2_preserved
- PASS: web_8_requirements_have_test_rows
- PASS: current_G1_not_passed
- PASS: no_masked_private_data_exception
- PASS: skill_document_root_correct
- PASS: workspace_root_not_moved
- PASS: source_unchanged_.docx
- PASS: source_unchanged_.hwpx
- PASS: skill_static_validation

원문 링크와 스냅샷/diff 무결성은 별도 검증 JSON에 기록한다. 초기 정적 비교의 CRLF/LF 처리 오류를 수정해 행 내용으로 재비교했고, PRD에도 G1 미통과를 명시해 문서 정합성을 보완했다. 배포 비용은 공식 문서 조회와 계획 추정만 수행했고 실제 청구·속도·메모리·가용성은 미검증이다.
