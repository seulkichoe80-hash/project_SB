# 서무ITDA v0.3-B 평가 기반 보고

기존 합성 평가자료를 새 문서·버전·파싱/청킹 작업으로 재현하고 현재 EvidenceRef에 연결했다. 제품 기능/API/DB/검색 제한/공급자 기본 차단은 유지했다. 실제 LLM·임베딩·Supabase 호출과 지출·외부 자료 전송·push·merge·배포는0회다. 실제 AI 정확도는 측정하지 않았으며 인간 검토40건이 대기 중이다.

## 1. 변경 파일

신규 scripts/validation/evaluation_fixtures.py는 독립 프로세스 자료 재현·원본/세대 고정·live EvidenceRef·평가 전용 장문 검색을 제공한다. evaluation_metrics.py는 strict label/prediction·분리 지표·인간 검토 계약이다. run_v03b_evaluation.py는 신규 자료/재현 결과/40문항 검토표를 생성하고 score_v03b_predictions.py는 오프라인 제출 결과만 채점한다. tests/test_evaluation_foundation.py에 신규59개 시험을 추가했다.

상세 계약은 docs/V03B_EVALUATION_FOUNDATION.md이며 ARCHITECTURE.md·TEST_PLAN.md·TASKS.md에는 해당 절/링크만 추가했다. 새 자료·시험·브라우저 증거는 outputs/v03b에 있다. 기존 제품 소스·테스트·원본·fixture·평가 정답·과거 보고서는 변경하지 않았다.

## 2. 재현 및57청크

현재 기준 결과는 [isolated-evaluation/summary.json](v03b/isolated-evaluation/summary.json)과 [고정 manifest](v03b/isolated-evaluation/generation.json)이다. HWPX6종과 PDF 형식 대조1종의 원본 SHA-256이 과거와 모두 일치했고 청크 수도57개로 일치했다. 과거 document/version ID로 실제 parser/chunker를 실행했을 때 청크 전체(내용·위치·ID·표 구조)가7문서 모두 정확히 일치했다.

새 DB에는 새 document/version·parse job/attempt·chunk job/generation을 만들고 WorkflowInputSnapshot·설정을 고정했다. 새 DB의 generation 번호1은 과거 세대와 동일하다는 뜻이 아니다. 새 ID로 다시 파싱·청킹한 canonical replay도57개 전체 일치했다. 원본은 corpus에 새 합성 파생 파일로 보존하고 전체 구조화 원문은 parsed-originals.json에 기록했다.

최초 비교에서는 새 UUID에서 파생한 PDF 표/셀 ID까지 내용 비교에 포함하여 차이로 보였다. 내용 비교에서 해당 ID를 구분하고 과거 ID의 exact replay를 추가해 실제 내용 차이가 없음을 확인했다. 기존 증거는 삭제하지 않았다. canonical 생성 소요시간은 별도 summary에 기록했다.

## 3. EvidenceRef

정답 근거48건과 타기관 접근 금지 확인용3건, 총51건을 현재 세대에 구조적으로 재연결했다. 구조 재연결 실패0/미해결0이며 의미 검증은51건 모두 NOT_VERIFIED다. 전체57청크도 실제 원본 재해결에 성공했다. 과거 UUID·위조 span·다른 기관·옛 청킹 세대·새 활성 버전·등록 해제는 거부한다. 금지 근거3건은 소유 기관에서 구조 재현을 확인한 것이며 질문 기관에서 접근할 수 있다는 뜻이 아니다.

원문/정답을 임의 수정해 연결을 맞추지 않았다. 연결 불일치 시 생성기는 임의 보정하지 않고 중단하며 부분 자료를 보존한다. scorer는 잘못된 gold/근거를 DATA_INVALID로 분리하고 AI 오류 분모에서 제외한다.

## 4. 검색 제한과 실제 결과

제품 제한은 RAGService.search와 ChunkService.search의200자/8단어 AND 검사에 있다. 초과7문항(travel-a-01, leave-a-01, purchase-a-01, meeting-a-01, form-a-01, travel-b-01, safety-04)의 질문/정답을 그대로 보존했다.

평가 전용 evaluation-window-rrf-v1은 질문 전체를 연속8단어/200자 window로 나눠 모두 검색하고 RRF로 합친다. 정답을 참조해 검색어를 만들거나 질문을 조용히 잘라내지 않는다. 원 질문·모든 window·실패/지연·프로토콜을 기록한다. 전체128단어/2000자·단어200자·최대20결과로 제한하고 현재 기관/세대/원본을 재검증한다. 제품 검색 계약은 변경하지 않았다.

실제40문항 검색은 retrieved0 / no_hits40 / retrieval_failed0이었다. 장문7건 모두 길이 제한 오류 없이2개 window로 처리했으나 검색 적중은 없었다. 길이 오류 해소와 검색 품질 향상은 별개다. 한국어 자연어/조사/문맥을 처리하지 못하는 엄격한 키워드 AND의 한계를 그대로 노출한다. [검색 증거](v03b/isolated-evaluation/retrieval.json). 제품 검색 개정 또는 고정 문맥 실험 프로토콜은 후속 별도 결정이 필요하다.

## 5. 평가 도구

자동 지표는 단계 precision/recall/F1, 순서/분기·반려·보완·반복 관계 PRF/exact-set accuracy, 기한/조건/서식 검출, 원문 재해결 인용 비율, 무근거 exact-quote 대리 지표를 분리한다. 항목/간선 ID 중복·없는 참조·추가 승인 필드·부정확 usage/비용·NaN을 거부한다. 분모0은null, 미주석은 NOT_ANNOTATED다. 시간/토큰은 NOT_MEASURED·FAKE_USAGE·PROVIDER_USAGE로 나누고 versioned rate의 정수 microUSD 추정만 허용한다. 실제 호출이 없으므로 현재 측정 토큰·실모델 예상 비용은null이며 실제 지출은0이다.

기존 단계 출현48개는 미승인 정답 초안으로만 변환했다. 순서/분기 그래프·기한·조건·서식의 독립 정답 주석은 없으므로 현재40문항의 해당 지표는 NOT_ANNOTATED다. 정답 배열의 순서를 자동으로 검증된 업무 그래프로 만들지 않았다.

metric-calibration.json의 단계 F1=1은 정답 초안을 그대로 복사한 산식 검증 fixture다. AI 출력/일반화 성능이나 승인 점수가 아니다. [모델 미실행 채점](v03b/isolated-no-inference-score.json)은40문항 전부 NOT_RUN이며 자동/인간 정확도와 무근거 비율은 측정하지 않았다. 검색 실패·출력 오류·잘못된 gold·미실행은 별도 상태와 분모로 표시한다.

## 6. 인간 검토 대기40건

[검토 화면](v03b/isolated-evaluation/review.html), [검토 표 CSV](v03b/isolated-evaluation/review-sheet.csv), [기계 판독 행](v03b/isolated-evaluation/review-rows.json)을 제공한다. 원 질문·정답 초안·보류 기준·원문 발췌·전체 구조화 원문·원본 링크·기관/버전/hash/위치를 함께 확인할 수 있다.

정확/부분정확/오답/판정불가, 검토자·시간대 포함 날짜·이유는 모두 미기입이다. 승인된 골드셋0건이며 자동 인간 판정은 생성하지 않았다. 독립 담당자가40문항의 정답/보류·원문 의미·근거·단계 경계/행위자·순서/분기/반복·기한/조건/서식 및 독립 holdout을 검토해야 한다. HWPX 시각 순서·native 한컴 검증도 별도다. scorer는 입력된 인간 기록을 별도로 집계하지만 신원/독립성을 인증하거나 골드셋을 자동 승인하지 않는다.

## 7. 검증 결과

최종 전체 백엔드 **554 PASS / FAIL0 / SKIP0 / BLOCKED0**(기존495+신규59)를 새로 실행했다. 실행시간127.94초이며 비루프백 호출 시도0회다. [최종 집계](v03b/final-validation.json), [백엔드 상세](v03b/backend-final.json), [네트워크 guard](v03b/backend-final.network.json)를 보존했다. 신규59개 영향 시험은 PASS이며 XML 전역 namespace 변경을 포함한다. 기존 UI174(104+24+26+20)·실제 loopback HTTP13·타입 검사·프로덕션 빌드는 이번에 새로 실행하여 PASS했다. 타입1.258초·빌드1.616초·HTTP26.902초다. 과거 결과로 대체하지 않았다.

초기 영향 시험은 JSON에 저장된 strict tuple snapshot을 Python-list로 다시 검증해5 ERROR가 있었고 JSON 전용 round-trip으로 수정했다. 최초 전체 회귀는 앞선 시험의 전역 XML namespace 등록이 합성 ZIP 바이트를 바꾸어 신규 세대 class 준비에서1 ERROR(521 PASS)를 기록했다. 기존 생성기를 새 Python 프로세스에서 실행하도록 격리하고 재현 시험을 추가했다. 실패 로그/초기 전체 JSON은 보존했다. 제품 parser·chunker·기존 fixture를 수정하거나 시험을 생략하여 통과시키지 않았다.

## 8. 보존·보안·Git

v0.3-A 미커밋45파일을 검사 후 로컬 커밋 a3bfee3430ef69d042b3e543786ed13ea8ba1141로 보존했다. 현재 브랜치는 feat/v03b-evaluation-fixtures이며 HEAD는 이 보존 커밋이다. 이번 v0.3-B 구현/문서/새 증거는 미커밋 상태다. 원격 push·merge·배포는 하지 않았다.

기준 tracked664개 중 기존 문서3개에 관련 절을 추가했고 나머지661개는 변경하지 않았다. 새 corpus도 기존 원본을 수정하지 않은 별도 합성 사본이다. 강한 비밀키/개인키 패턴 검사0건, 새 키/계정/SDK/의존성/API/DB 변경0건이다. [보존 manifest](v03b/PRESERVATION.json), [보안 점검](v03b/SECURITY.json)을 따른다. Python 전체 회귀는 subprocess 상속 loopback-only guard로 실제 외부 호출 시도를 검사한다.

## 9. v0.3-C와 남은 조건

자료 재현·현재 근거·오프라인 채점 도구 기반은 마련됐다. 다만 실제 AI 정확도 평가를 시작하려면 독립 인간 검토, 그래프/기한/조건/서식 정답 주석, 검색 품질 또는 고정 문맥 프로토콜, 독립 holdout을 먼저 확정해야 한다. 실모델/임베딩/가격·토크나이저·공급자 데이터 조건·전송 범위·예산은 별도 승인 대상이다. 현재 결과를 실 AI 검증·승인/공식 게시/운영 배포 준비 완료로 해석할 수 없다. v0.3-C는 자동 시작하지 않았다.

## 10. 재현과 소요시간

[상세 실행 계약](../docs/V03B_EVALUATION_FOUNDATION.md)에 새 runtime/output 경로를 사용한 재현·빈 prediction 채점·신규 unittest 명령을 제공한다. canonical 자료는 isolated-evaluation이며 중간3세대/초기 실패는 GENERATION_INDEX.json으로 구분했다. 삭제하거나 덮어쓰지 않았다. 총 소요시간은 약15.5분이며 canonical 재현은5.578초, 신규59개 영향 시험은17.958초다. 최종 시험 집계와 시간은 final-validation.json을 따른다. 새 설치는 필요하지 않았다.
