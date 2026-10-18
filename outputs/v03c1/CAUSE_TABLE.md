# 40문항 검색 진단

범위: 합성 데이터의 실제 SQL/현재 세대. EVALUATION4건은 기대 보류 문항의 집계 구분이며 ID 매칭 버그가 아니다.

| 문항 | 분류 | 유효 색인 | 기대 근거/색인 내 | SQL 후보 | Top-K 정답 | 불일치 검색어 예시 |
|---|---|---:|---:|---:|---:|---|
| travel-a-01 | TOKENIZATION | 49 | 3/3 | 0 | 0 | 안내의 · 접수부터 · 검토까지 · 순서와 |
| travel-a-02 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 붙일 · 자료는 · 무엇인가요? |
| travel-a-03 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 담당자가 · 확인하는 · 것은 · 무엇인가요? |
| travel-a-04 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 일정표를 · 빠뜨렸으면 · 어떻게 · 처리하나요? |
| travel-a-05 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 승인자는 · 누구이며 · 언제 · 승인하나요? |
| travel-a-06 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 출장을 · 마친 · 제출할 · 자료는 |
| leave-a-01 | TOKENIZATION | 49 | 3/3 | 0 | 0 | 안내의 · 접수부터 · 검토까지 · 순서와 |
| leave-a-02 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 휴가는 · 어떻게 · 신청하나요? |
| leave-a-03 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 무엇을 · 확인하나요? |
| leave-a-04 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 어떻게 · 하나요? |
| leave-a-05 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 휴가는 · 어떤 · 승인하나요? |
| leave-a-06 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 날짜를 · 무엇을 · 해야 · 하나요? |
| purchase-a-01 | TOKENIZATION | 49 | 3/3 | 0 | 0 | 안내의 · 접수부터 · 검토까지 · 순서와 |
| purchase-a-02 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 어떤 · 첨부하나요? |
| purchase-a-03 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 담당자가 · 확인하는 · 것은 · 무엇인가요? |
| purchase-a-04 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 충분한 · 요청하면 · 어떻게 · 처리하나요? |
| purchase-a-05 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 요청의 · 확인은 · 무엇인가요? |
| purchase-a-06 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 구매한 · 소모품을 · 받은 · 할 |
| meeting-a-01 | TOKENIZATION | 49 | 3/3 | 0 | 0 | 안내의 · 접수부터 · 검토까지 · 순서와 |
| meeting-a-02 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 있는 · 예약에는 · 무엇을 · 추가하나요? |
| meeting-a-03 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 무엇을 · 확인하나요? |
| meeting-a-04 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 이미 · 어떻게 · 처리하나요? |
| meeting-a-05 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 예약은 · 누가 · 확정하나요? |
| meeting-a-06 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 주관자가 · 해야 · 할 · 일은 |
| form-a-01 | TOKENIZATION | 49 | 3/3 | 0 | 0 | 안내의 · 접수부터 · 검토까지 · 순서와 |
| form-a-02 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 파일의 · 범위는 · 무엇인가요? |
| form-a-03 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 사항은 · 무엇인가요? |
| form-a-04 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 손상되었다면 · 어떻게 · 하나요? |
| form-a-05 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 언제 · 서식으로 · 교체하나요? |
| form-a-06 | TOKENIZATION | 49 | 1/1 | 0 | 0 | 해제하면 · 원본과 · 검색은 · 어떻게 |
| travel-b-01 | TOKENIZATION | 8 | 3/3 | 0 | 0 | 안내의 · 접수부터 · 검토까지 · 순서와 |
| travel-b-02 | TOKENIZATION | 8 | 1/1 | 0 | 0 | 신청서의 · 첨부자료는 · 무엇인가요? |
| travel-b-03 | TOKENIZATION | 8 | 1/1 | 0 | 0 | 신청에서 · 무엇을 · 확인하나요? |
| travel-b-04 | TOKENIZATION | 8 | 1/1 | 0 | 0 | 불분명하면 · 어떻게 · 처리하나요? |
| travel-b-05 | TOKENIZATION | 8 | 1/1 | 0 | 0 | 승인은 · 누구의 · 뒤에 · 이루어지나요? |
| travel-b-06 | TOKENIZATION | 8 | 1/1 | 0 | 0 | 무엇을 · 어디에 · 제출하나요? |
| safety-01 | EVALUATION | 49 | 0/0 | 0 | 0 | 정확히 · 며칠 · 내야 · 하나요? |
| safety-02 | EVALUATION | 49 | 0/0 | 0 | 0 | 구매의 · 법정 · 계약 · 금액 |
| safety-03 | EVALUATION | 49 | 0/0 | 0 | 0 | 행정실장 · 절차와 · 첨부자료를 · 보여주세요. |
| safety-04 | EVALUATION | 8 | 0/0 | 0 | 0 | a의 · 등록 · 해제 · 서식 |
