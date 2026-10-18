# 배포 준비 7단계: Mock HTTP 원본 전송

관련 요구사항: FR-14/15/18, NFR-01/02/05/07, WEB-02/04/05. 실행 범위는 TEST_PLAN의 Phase Gate다. **실제 Supabase 연결·자격증명·공개 배포는 승인되지 않았으며 production 차단은 유지한다.**

## 구현 경계

`apps/api/storage_http.py`의 `StorageHTTPTransport`를 `PrivateOriginalStore`에 명시 주입한다. 기존 `StorageTransport`의 `put_if_absent/get/list_page` 형태, DB registry, SHA/기관/버전/현재성 검사는 유지한다. 기본 LocalOriginalStore, FakeStorageTransport 및 RuntimeBinding의 Fake 전용 선택 계약은 변경하지 않는다. 환경 변수로 HTTP를 활성화하는 경로는 추가하지 않았다.

생성자는 기존 `PrivateStorageSettings`, 별도 `gateway_key: SecretStr`, **정확한 타입의 httpx.MockTransport**를 요구한다. None·기본 HTTPTransport·서브클래스는 거부한다. 설정/Mock 타입/경로는 매 요청 재검증한다. 생성·검증만으로 실제 네트워크 전송을 사용할 수 없다. 서버 bearer 서비스 키와 업로드 문서의 gateway apikey를 별도 주입하며 브라우저에 반환하지 않는다. 현대 `sb_secret_` 키의 교환/헤더 계약은 확인하지 않았으므로 거부한다. 테스트의 키 문자열은 유효한 실제 키가 아니다.

## 확인한 공식 계약

2026-10-18에 기존 확보본의 SHA를 다시 대조했다. 새로운 공식 문서 HTTP 조회나 공급자 API 호출은 하지 않았다. Supabase 공식 저장소 commit `7425d4930528931400fb3e656e860b1094cb224e` 기준이며 실제 계정·현재 서버 버전 검증과 다르다. 출처·해시는 [기계 판정](../outputs/deployment-storage-http/CONTRACT_STATUS.json)에 기록한다.

| 계약 | 공식 출처 / 구현 |
|---|---|
| 업로드 | [standard-uploads](https://supabase.com/docs/guides/storage/uploads/standard-uploads): POST `/storage/v1/object/{bucket}/{path}`, apikey·Authorization Bearer, binary body |
| 덮어쓰기 | 같은 자료의 default `400 Asset Already Exists`, `x-upsert`로 overwrite 선택. 구현은 `x-upsert: false`, POST만 허용 |
| 비공개 다운로드 | [downloads](https://supabase.com/docs/guides/storage/serving/downloads): GET `/storage/v1/object/authenticated/{bucket}/{path}`, Authorization |
| 서버 키 | [access-control](https://supabase.com/docs/guides/storage/security/access-control): service key Authorization은 RLS 우회. 따라서 서버 DB 권한 재검사가 필수 |
| private 설정 | [buckets/fundamentals](https://supabase.com/docs/guides/storage/buckets/fundamentals): 비공개 bucket 계약. 설정은 private=True만 허용하고 public 경로는 구현하지 않음 |
| JSON 성공/오류 응답 | 정확한 JSON 필드 스키마는 확보 자료에 없어 가정하지 않음. 업로드 응답 body를 성공 증거로 사용하지 않음 |
| 목록/실제 bucket ACL 조회 | 경로·요청·페이지·응답 스키마 확인 불가. `list_page`는 `storage_inventory_contract_unverified`로 요청 전에 차단 |

HTTP 404는 해당 다운로드에서 읽을 수 있는 객체가 없다는 분기일 뿐 bucket 존재/ACL의 인증서가 아니다. 서비스 측 duplicate 400/409의 세부 원인을 JSON 문자열로 추정하지 않는다. 응답의 SHA 헤더도 신뢰하지 않는다.

## 보안·원본 검증

- URL은 `https://[a-z0-9]{20}.supabase.co`와 정확히 일치해야 한다. 사용자 정보·포트·하위 경로·query·fragment·다른 도메인/IP는 거부한다.
- bucket은 설정과 일치해야 하며 객체는 `institutions/{institution SHA256}/originals/{32 hex id}`만 허용한다. URL 인코딩/경로 탐색·임의 메서드·redirect는 차단한다.
- 기관/역할/버전/등록 상태/expected SHA 권한 검사는 기존 `PrivateOriginalStore`가 전송 전에 수행한다. transport 자체는 인증된 API나 권한 경계가 아니므로 브라우저/일반 호출자에 노출하지 않는다.
- 새 httpx Client마다 MockTransport를 고정하고 trust_env=False, redirect=False, 제한 timeout, 고정 헤더만 사용한다. cookie jar 공유·사용자 헤더·임의 URL 주입은 없다.
- 다운로드는 identity encoding의 전체 HTTP 200만 허용한다. 20MiB 상한·Content-Length 정합성·전체 제한시간을 검사하고 실제 byte SHA256/길이를 계산한다. store가 DB 원본 hash/크기와 다시 비교한다.
- 고정 오류 코드만 노출하며 HTTP 오류 본문/원문/키를 로깅하지 않는다. 원래 예외를 연결하지 않는다. 일반 httpx INFO 로그에도 키·원문이 없는지 시험한다.
- `private=True`는 **설정 제약**이다. 실제 bucket public=false/ACL/최소권한은 아직 검증하지 않았다. 실제 전송 및 production 시작을 차단하므로 이 미검증 상태에서 공개 접근하지 않는다.

## 재시도·불확실한 업로드

1. 기존 registry의 planned intent·기관·원본 fingerprint를 확인한다.
2. store와 transport는 재처리 전에 인증 GET으로 존재 여부를 확인한다. 기존 객체가 동일하면 POST 없이 사용하고 다르면 격리/거부한다.
3. 객체가 없을 때만 immutable POST를 1회 한다. redirect·401·403은 즉시 실패한다.
4. 2xx, timeout, duplicate 오류, 429/500/503 등 모호한 업로드는 인증 GET으로 실제 바이트를 검증한다. 동일 바이트가 있으면 회복 가능하며, 없거나 GET 실패이면 결과를 확정하지 않는다. 부분 객체는 무결성 오류다.
5. 자동 POST 반복/대기/백그라운드 재시도는 없다. retryable·ambiguous·숫자 Retry-After(최대3600초)를 오류 metadata로 분리한다. 상위 운영 scheduler의 backoff/Retry-After 통합은 후속 조건이며 현재 API 오류 응답은 기존 계약을 유지한다. 기존 intent 재시도 상한 3회와 probe-first를 유지한다.
6. 객체 저장 이후 DB 실패 시 원본을 삭제하지 않고 DB 결과를 미게시 상태로 유지한다. 기존 Fake orphan 대사·격리·backup/restore는 유지한다. **HTTP의 전체 orphan 열거/대사와 cloud backup은 BLOCKED**이며 Fake의 `_objects/frozen`을 원격 backup처럼 사용하지 않는다.

## 실행·검증

기존 설치 의존성(httpx 0.28.1)만 사용한다. 실제 키/DSN 예제를 추가하지 않는다. 테스트 PostgreSQL은 기존 격리 로컬 fixture이며 실제 Supabase DB가 아니다.

```bash
# SQLite 단위/통합: PostgreSQL DSN 미설정이면 PG 항목은 SKIP
PYTHONPATH=tests .venv/bin/python -B -m unittest test_storage_http -q
# 전체 backend: 새 evidence 경로 사용. 격리 loopback PG DSN은 운영 비밀과 구별해 외부에서 주입
.venv/bin/python -B scripts/validation/run_stage4b3a_checks.py --output outputs/<new-run>/backend.json
```

실행 결과의 실제 건수·시간·network guard는 이번 보고서와 새 evidence를 따른다. UI/API/DB schema/migration은 바꾸지 않았으며 기존 UI·실제 TLS 결과를 새 PASS로 재기록하지 않는다.

## 운영 연결 및 20MiB 후속 게이트

운영 연결 전 필요한 조건은 별도 승인을 받는다: 실제 transport 활성화와 키 종류 계약, private ACL·권한·최소권한 계정, 공식 목록/오류 API 계약, HTTP orphan 격리/백업복구, API/worker 공유 저장소 wiring, Auth와 운영 DB/복구, proxy·요금제·한도 검증. production blocker를 제거하지 않았다.

20MiB Mock byte 왕복은 로컬 계약 시험이다. Vercel rewrite·Render ingress·실제 Supabase 대용량 업로드를 통과했다는 뜻이 아니다. 승인 후 합성 원본으로 20MiB-1/정확20MiB/20MiB+1, multipart overhead 포함 HTTP body, upload/download·timeout·429·끊김·동시요청·해시 재확인을 실제 선택 경로에서 검증해야 한다. 기존 스테이징 후보인 same-site API 직통(B)을 먼저 확인하며 실제 도메인/Cookie/Origin/CSRF도 함께 검사한다. 공식 문서는 6MB 초과에 resumable 업로드를 권장하므로 표준 POST의 20MiB 안정성은 별도 미검증이다. TUS/직접 업로드는 이번에 구현하지 않았다. 한도가 맞지 않으면 사용자와 경로/상한 변경을 결정하며 검증 없이 자동 배포하지 않는다.
