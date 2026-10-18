# 우선 10문항 인간 검토 지원

## 결과

별도 브랜치 feat/v03e-human-review-support에서 오프라인 검토 묶음 생성기와 CSV 제출 형식 검증기를 추가했다. 기존 D 제품 변경은 그대로 유지했으며 신규 제품 UI/API/DB 변경은 없다. 기존 D 증거 manifest의 56파일은 최초 확인 시 모두 일치했고, TASKS/TEST_PLAN 후속 절 추가 외 기존 manifest 내용 변경이 없다. 기존 tracked 파일 삭제 0. 기존 patch와 manifest 대상 사본은 /tmp에 추가 보존했다. 새 커밋/push/merge/배포 없음. HEAD e2bb7f769cb425edbe06b375595eaf839440f004, D/E 변경 모두 미커밋이다.

## 신규 파일

- scripts/validation/human_review_packet.py
- tests/test_human_review_packet.py
- docs/V03E_HUMAN_REVIEW_SUPPORT.md
- outputs/v03e/priority10/{packet.json,review.html,judgments.csv}
- outputs/v03e/{progress.json,browser-check.json,review-1280.png,review-375.png,targeted-guarded.txt}

TASKS/TEST_PLAN에는 해당 기능·검증 절만 추가했다. 사용법은 docs/V03E_HUMAN_REVIEW_SUPPORT.md를 따른다.

## 검토 방식과 한계

C1 우선순위 10문항의 질문·정답 초안·구조 확인 근거와 기관 내 전체 문맥을 제공한다. 원본 해시/파서/청커 replay 및 live 스냅샷/EvidenceRef를 재검증한다. 타기관 forbidden ref 원문은 문항에 표시하지 않는다. 독립 평가자용 묶음에는 A/B 합성 자료가 함께 들어 있어 제품 사용자에게 제공하는 파일이 아니다.

판정 CSV는 빈 상태다. 판정/식별명/시간대 포함 일시/이유를 검토자가 직접 기록한다. 미완성/중복/미등록 문항/잘못된 판정을 거부하며 제출 형식이 유효해도 신원·독립성·진실성을 인증하지 않는다. PROVISIONAL/NOT_VERIFIED 유지, semantic_accuracy_pass=false. 인간 검토 현재 0/10, 전체 0/40. 골드셋 승인·자동 정답 수정·모델 평가·제품 승인 연동 없음.

## 검증

Feature Gate: 신규 5개 테스트(잘못된 제출 6개 하위 사례 포함)와 기존 B/C1 관련 96개 회귀를 실행한다. 첫 pytest 명령은 의존성 미설치로 실패했으며 저장소의 unittest 방식으로 전환했다. 초기 build는 source 필드가 없는 문서에서 실패하여 logical_id 대체 표시를 적용했다. 이전 출력은 덮어쓰지 않았다.

Chromium PC1280/mobile375에서10문항·가로 넘침 없음·Tab 링크 진입 PASS. 관리 정책으로 file URL이 차단되어 동일 HTML을 setContent로 렌더링했다. 제품 E2E나 file URL 성공으로 보고하지 않는다. 실제 사용자 스크린리더·한컴 시각 검토는 미실행이다.

제품 소스는 D와 동일하다. 이전 D 전체 backend642/UI174/HTTP13+11묶음/타입·빌드 결과는 이전 증거이며 이번 새 실행으로 집계하지 않는다. 이번 지원 도구는 외부 SDK·전송·자동 서버·브라우저 저장 기능을 사용하지 않는다. 실제 공급자/유료 API 호출과 비용 0. 본 작업 이후 단계는 진행하지 않는다.

최종 네트워크 차단 환경 재실행: 관련 101개 PASS, 실패 0, 외부 네트워크 시도 차단 로그 0건. 결과는 outputs/v03e/targeted-guarded.txt에 보존한다. git diff --check PASS.
