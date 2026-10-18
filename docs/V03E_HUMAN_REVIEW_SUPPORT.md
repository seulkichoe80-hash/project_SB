# 우선 10문항 인간 검토 지원

FR-07/08/15와 TEST_PLAN의 원문 불변·기관 격리·평가 분리를 위한 오프라인 Feature Gate다. 제품 UI/API/DB, 검색 기본값과 기존 정답·검토표를 바꾸지 않는다.

## 실행

```bash
.venv/bin/python -B scripts/validation/human_review_packet.py build --generation-dir outputs/v03b/isolated-evaluation --output-dir outputs/v03e/priority10
.venv/bin/python -B scripts/validation/human_review_packet.py check --packet outputs/v03e/priority10/packet.json --judgments outputs/v03e/priority10/judgments.csv
```

build는 기존 출력 경로를 거부한다. 새 검토 묶음에는 새 경로를 지정한다. 원본 corpus와 해당 generation의 runtime이 필요하며, 해시·실제 파서/청커 재현과 live EvidenceRef/스냅샷을 검증한 뒤 생성한다. 신규 환경에서 다른 UUID 세대를 과거 manifest에 덮어씌우지 않는다.

## 검토 순서

기존 C1의 선정 기준과 순서를 유지한다: travel-a-01, travel-b-01, leave-a-01, purchase-a-01, meeting-a-01, form-a-01, travel-a-04, safety-01, safety-03, safety-04.

review.html을 오프라인 브라우저에서 열어 질문·정답 초안·인용·전체 문맥을 비교한다. 관리 정책이 file URL을 차단하면 기관이 허용한 로컬 정적 뷰어를 사용한다. 자동 서버나 공개 배포를 제공하지 않는다. 기관 A/B 자료가 한 합성 검토 묶음에 포함되므로 제품 사용자용 파일이 아니며 독립 평가자 전용이다. 문항별 문맥은 해당 기관으로 한정하고 forbidden refs는 펼쳐 보이지 않는다. 안전 문항에서 연결 근거가 없다는 사실만으로 전체 문서에 근거가 없다고 인증하지 않는다.

CSV의 빈 필드를 직접 채운다. 정확/부분정확/오답/판정불가, 검토자 식별명(실명 불필요), 시간대 포함 ISO 검토일, 판정 이유가 필요하다. 순서·분기·기한·조건·서식·인용 적합성을 각각 검토하고 개선 제안은 이유에 적는다. HWPX XML 구조는 시각적 페이지 검증이 아니다. 기존 정답이나 원본을 직접 수정하지 않는다.

check는 누락·중복·알 수 없는 문항·부분 입력·잘못된 판정·시간대를 거부하며 빈 행은 미검토로 집계한다. 결과는 제출 형식 검증일 뿐 인간 신원·독립성·진실성 인증이 아니다. 모든 제출 후에도 PROVISIONAL/NOT_VERIFIED/semantic_accuracy_pass=false를 유지한다. 골드셋 승인·제품 승인·실제 모델 평가와 자동 연동하지 않는다. CSV에는 민감정보를 적지 않으며 제출 결과를 Git에 넣기 전에 검토한다.

HTML에는 실행 스크립트·외부 자원·브라우저 저장소·전송 기능이 없고 모든 자료를 HTML escape한다. 기존 40문항 검토표는 그대로 유지하며 우선 10문항 이후 나머지 30문항과 독립 관계/기한/조건/서식 주석 검토가 필요하다.
