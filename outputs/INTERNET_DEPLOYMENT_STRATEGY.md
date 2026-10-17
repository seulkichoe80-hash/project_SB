# 서무ITDA 인터넷망 전환과 배포 전략

현재 문서 위치와 G1 착수 판정은 [루트 README](../README.md)와 [A/B/C/D 분류](../docs/G1_GATES.md)를 따른다. 아래 인터넷 전환 시점의 비용·설계·배치 제안은 당시 이력이며 현재 저장소 미구성 또는 일괄 착수 보류 설명을 현재 상태로 해석하지 않는다.

결정일·공식 문서 조회일: 2026-10-16 KST. 상태: 설계 권고, 미배포. 모든 비용은 USD/월의 공개 단가 또는 명시된 예산 추정이며 세금·환율·초과 사용·추가 프로젝트·도메인·지역 차이를 포함하지 않는다. 실제 유료 자원 생성·API 호출·공개 배포·원격 push는 실행하지 않았다.

**현재 목표는 인터넷 공개 HTTPS URL로 사용하는 PC 브라우저 웹앱이다.** 공개 접속과 기관 자료·검색·관리 권한을 분리한다. 현재 G1은 미통과이며, 설계 전환으로 과거 미실행 시험을 PASS로 바꾸지 않았다.

## 1 수정 문서와 보존

다음 7개 기준 문서를 현재 위치에서 수정했다. 대규모 이동·신규 앱 생성은 없다.

| 문서 | 주요 변경 |
|---|---|
| [PRD.md](PRD.md) | 인터넷 브라우저 여정·MVP 경계, WEB-01~08 추가, FR-01~19/분류/40·30·30/제출 일정 유지 |
| [AGENTS.md](AGENTS.md) | 인터넷 API·시크릿·클라우드/기관 권한·Git/과금/배포 승인·기능별 회귀 규칙 |
| [TASKS.md](TASKS.md) | 기존 제한 PASS 증거 연결, 실제 2모델·클라우드 영속성·브라우저·심사 작업, 게이트 분리 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Vercel/API/worker/Auth/DB/객체 저장 연결, 영속 Job·게시 프로토콜·예산/보관 설정 |
| [TEST_PLAN.md](TEST_PLAN.md) | API 직접 호출·인증·기관·비밀·CORS·비용·재배포/복원·브라우저 시험 |
| [README.md](README.md) | 일반 사용자 무설치 웹 사용과 평가자 소스 실행 분리, 실제 URL 미생성·루트 제안 |
| [SKILL.md](../.agents/skills/seomuitda-quality-check/SKILL.md) | 인터넷망 반복 검증 절차. 범위/보안/수치의 기준은 AGENTS/PRD/TEST_PLAN을 참조 |

[변경 전 ZIP](INTERNET_TRANSITION_BEFORE.zip)에 요청한 원래 10개 파일과 SHA-256 manifest를 보존했다. 기존 PHASE1_REPORT.md, PHASE1_DOCUMENT_CHANGES.md, PHASE1_EVIDENCE.zip은 바이트 단위 변경 없이 유지한다. [변경이력](INTERNET_TRANSITION_CHANGELOG.md)과 [통합 diff](INTERNET_TRANSITION.diff)에 현재 결정과 전후 차이를 기록했다. 과거 보고의 내부망/오프라인 검토는 당시의 이력이며 현재 운영 결정과 혼동하지 않는다.

## 2 유지하는 Phase 1 사실

이번에 실행한 것은 파일·Git 상태 확인, 증거 ZIP CRC/56개 manifest 해시 확인, 문서 수정/정적 검증이다. 제품·모델·클라우드를 새로 실행한 것은 아니다. 아래는 보존된 증거에서 확인한 기존 결과다.

| 항목 | 유지 판정 | 범위 |
|---|---|---|
| React/Vite/TypeScript | PASS | 최소 설치·타입검사·빌드·동일 PC 캐시 설치 |
| React Flow | 설치/빌드 PASS | 실제 브라우저 표시·노드 클릭은 BLOCKED였음 |
| FastAPI/Pydantic | PASS | 실제 loopback HTTP 200/422/OpenAPI |
| SQLite | PASS | 기본 조회·롤백·활성 전환·등록 해제 SQL |
| PDF | PASS | 단순 디지털 합성 한글 1쪽·표 1개·좌표 |
| HWPX | PASS | 구조용 합성 ZIP 2 section·셀/그림/앵커; 정상 뷰어/시각 읽기 순서는 아님 |
| LLM Adapter | PASS | 모의 응답 2형식 계약·부정 케이스 8개. 실제 모델 호출 0회 |
| 벡터 | 연산 PASS | 수동 벡터 4개만. 학습된 임베딩·의미검색 성능 아님 |

정확 버전은 React/DOM 19.3.1, TypeScript 7.0.2, Vite 8.3.4, React Flow 12.12.0, Python 3.12.14, FastAPI 0.143.2, Pydantic 2.14.1, Uvicorn 0.54.0이다. 현재 변경은 이 기술을 교체하지 않는다. PostgreSQL/Auth/객체 저장소는 공개 운영 요건 때문에 추가하는 미검증 어댑터다.

## 3 MVP에서 제외한 내부망 요건과 전환 효과

| 항목 | 현재 처리 | PASS 여부 |
|---|---|---|
| 행정 내부망 설치·폐쇄망 모델 운영 | 후속 확장 검토 | 현재 MVP 비대상. PASS로 승격하지 않음 |
| 내부 GPU 서버·현재 PC GPU 확인 | 인터넷 API 사용에 필수 아님 | 로컬 GPU 정보 미확인 이력 유지 |
| 현재 PC Docker 설치 | 선택적 재현 수단 | 기존 BLOCKED 유지, 전체 클라우드 개발 차단 사유에서 제외 |
| 완전 오프라인 런타임·가중치 반입 | P2 확장 | 같은 PC 패키지 설치 증거만 보존 |
| 일반 사용자 프로그램 설치 | 브라우저 이용으로 대체 | 실제 URL 브라우저 시연은 미검증 |

인터넷 API와 호스팅은 로컬 모델/GPU/외부 접속 불가 가정을 해소하는 설계 경로를 제공한다. 인터넷망 전환만으로 API 계정/키·실제 2모델·HWPX·한국어 검색·React Flow·클라우드 영속성·독립 실행이 해결됐다고 판정하지 않는다.

## 4 최종 권장 기술 스택안

현재 권고는 React+TypeScript+Vite+React Flow / Python 3.12+FastAPI+Pydantic이다. SQLite는 개발에 유지하고 클라우드에는 관리형 PostgreSQL과 비공개 객체 저장소를 둔다. 메타데이터·Auth·ObjectStore·LLM·OCR·Embedding·Retrieval·Form 어댑터를 유지한다. 실제 임베딩 모델/차원/한국어 검색 검증 뒤 pgvector 도입 여부를 정한다. NumPy 연산 스파이크는 회귀 기준으로 남긴다.

기본 호스팅 권고는 **Vercel 정적 프런트 + Render API/분리 worker + Supabase PostgreSQL/Auth/비공개 Storage**다. 긴 분석을 API 요청 생명주기에 묶지 않고 DB 영속 Job과 worker lease/멱등 재시도로 처리한다. 서비스 분리의 비용/운영 부담을 인정하며 메모리·동시성 실측 전 최소 인스턴스 적합성을 보장하지 않는다.

## 5 구성요소별 배포 연결

| 구성 | 기본안 | 핵심 조건/현재 상태 |
|---|---|---|
| 프런트 | Vercel, Vite 정적 dist | HTTPS URL·SPA 경로·Auth callback·정확 CORS, LLM/DB 비밀 비포함. 미배포 |
| 인증 | Supabase Auth 후보 | 초대 계정, PC 브라우저 로그인. API JWT 검증과 DB 기관 멤버십/역할. 실제 연결 미검증 |
| API | Render Web Service, FastAPI | 인증·권한·rate/비용·근거·다운로드 스트림, health/readiness. 실제 구동 미검증 |
| worker | 별도 Render Background Worker | DB 영속 Job lease/heartbeat/재시도. 공개 포트 불필요, 재배포 복구·메모리 실측 필요 |
| DB | Supabase PostgreSQL 후보 | 영속 metadata/Job/기관/권한/버전, pool/TLS/migration/backup. 개발 SQLite와 구분 |
| 파일 | Supabase private Storage 후보 | 불변 원본/파생 분리·해시·DB 상태 대사·원문 권한 스트림. public bucket 금지 |
| AI | 인터넷 API 후보 2종 | backend 시크릿, 승인된 공개/합성 문맥만. 실제 연결/교체/비용 미검증 |

파일 저장소와 DB는 원자적 단일 commit이 아니므로 pending→객체 검증→Job/metadata commit→staging 결과→활성 스냅샷 전환과 대사/복구를 설계했다. 원본 저장 실패·DB commit 실패·재시작 중복 처리 때 부분 결과가 검색에 게시되지 않아야 한다. 로컬 컨테이너 디스크에 SQLite/업로드를 두고 영속 운영한다고 주장하지 않는다.

Storage 관리 service key는 RLS를 우회할 수 있으므로 서버의 기관 검사·최소권한을 생략하지 않는다. 관리키는 브라우저에 주지 않는다. [Storage 접근 제어](https://supabase.com/docs/guides/storage/security/access-control)

원본 등록 해제는 DB serving 차단부터 수행하고 검색·지도·서식·캐시에 전파한다. 원본 자체는 보존한다. 다운로드는 권한을 확인하는 API를 통해 제공하며 기존 signed URL이 해제 후 계속 동작하는 우회를 만들지 않는다.

### AI 검증 후보와 예산

공식 문서에서 확인한 API 후보는 `gpt-4.1-mini`와 `gemini-2.5-flash`다. 이는 현재 계정에서 실제 호출 가능하다는 증거가 아니다. 실행 직전 모델 수명·리전·계정·quota·데이터 처리 조건을 확인하고 승인 후 동일 골드셋으로 실제 2종을 비교한다.

일반 텍스트 표준 단가는 100만 토큰당 GPT-4.1 mini 입력 $0.40/출력 $1.60, Gemini 2.5 Flash 입력 $0.30/출력(생각 토큰 포함) $2.50로 확인했다. [OpenAI 모델 문서](https://developers.openai.com/api/docs/models/gpt-4.1-mini), [Google 가격표](https://ai.google.dev/gemini-api/docs/pricing)

예시 **추정**: 모델별 1,000회×입력 4,000/출력 1,000 토큰이면 각각 $3.20/$3.70, 합계 $6.90다. 그림/OCR·임베딩·재시도·생각 토큰 증가·문서 분석은 제외했다. 운영 AI 예산은 $10~30/월부터의 계획 범위이며 금액 승인이 아니다. 최초 실검증 요청안은 2모델·공개/합성 자료·총 $10 이내다. 승인 전 호출 0회이고 무료 호출/무료 자원도 이번 문서 작업에서는 만들지 않는다.

## 6 플랫폼 후보 장단점과 예상 비용

공식 요금은 2026-10-16 조회 기준이다. 성능·가용성·계정 조건을 실측한 값이 아니며 심사기간의 실제 청구액은 달라질 수 있다.

| 후보 | 장점과 적합 역할 | 제약/운영 위험 | 단가 또는 예산 |
|---|---|---|---|
| Vercel | Vite 정적 웹·HTTPS/CDN·프런트 배포 | Hobby는 개인·비상업 용도 제한. 공공기관/수상 출품 적합성을 임의 인정하지 않음. 긴 문서 worker는 별도 서버에 둠 | Hobby $0, Pro $20/월부터. seat/추가사용 별도 확인 |
| Render | Python API와 지속 worker를 분리하기 쉬운 후보 | Free 웹은 15분 무트래픽 후 절전·시작 약1분, Free는 persistent disk 불가, 무료 Postgres 30일 만료. 지속 worker는 무료 아님 | 공식 compute 표 검색 결과의 512MiB $7/서비스·2GiB $25/서비스 기준으로 API+worker $14~50/월 추정. 실제 선택 리소스/요금 재확인 |
| Railway | API·worker·볼륨을 한 프로젝트로 운영 가능한 대안 | Free의 서비스당 최대0.5GB RAM·volume0.5GB 제한. Hobby도 모든 서비스를 무제한 제공하지 않음. serverless/sleep·트래픽·백업/volume 확인 필요 | Hobby 최소 $5(동액 포함 credit), 초과 자원 과금. API+worker 소규모 계획 $10~30/월은 실측 전 가정 |
| Google Cloud Run | 요청 기반 확장·scale-to-zero·소스 빌드 대안, 로컬 Docker 없이도 경로 가능 | 콜드스타트·IAM/빌드/레지스트리 복잡성. 로컬 파일 비영속, 요청 종료 뒤 일반 메모리 background job 보장 불가. 별도 Tasks/Jobs·외부 DB/파일 필요 | 요청형 무료량 CPU180k vCPU초·RAM360k GiB초·200만 요청/월(us-central1 기준 할인액·계정/리전 조건 확인). 소규모 compute $0~10 추정, 빌드/이미지/전송/Jobs/최소 인스턴스 별도 |
| Supabase | PostgreSQL·Auth·비공개 Storage 묶음 후보 | Free 1주 비활성 pause, DB/파일/전송 한도. DB 백업에 파일 blob은 포함되지 않아 별도 백업 필요 | Free $0: DB500MB/파일1GB/egress5GB. Pro $25/월부터, 1 Micro 기준 포함 credit 조건·추가 프로젝트/사용 별도 |

출처: [Vercel 요금](https://vercel.com/pricing), [Hobby 범위](https://vercel.com/docs/plans/hobby), [Render compute](https://render.com/pricing?trk=article-ssr-frontend-pulse_little-text-block), [Render 무료 제한](https://render.com/docs/free), [Render 요금 구조](https://render.com/articles/how-much-does-cloud-application-hosting-cost-for-small-businesses), [Railway 요금](https://railway.com/pricing), [Cloud Run 요금](https://cloud.google.com/run/pricing), [소스 배포](https://docs.cloud.google.com/run/docs/deploying-source-code), [컨테이너 저장 계약](https://docs.cloud.google.com/run/docs/container-contract), [Supabase 요금](https://supabase.com/pricing).

Render의 정적 가격 페이지는 compute 탭 일부가 추출되지 않아 공식 페이지의 검색 인덱스 표와 공식 문서의 지속 실행/저장 제한을 대조했다. 구체 인스턴스 이름·RAM·가격은 생성 승인 직전 UI에서 다시 확인해야 한다. Rails 등 다른 프레임워크의 성능 사례를 서무ITDA 성능으로 전용하지 않았다.

기본 권고안의 **월 예상**은 Vercel Pro20 + Render API/worker14~50 + Supabase Pro25 = **$59~95 + AI·초과 전송/백업·세금**이다. 초기 작은 인스턴스가 메모리를 충족한다면 $59+AI이지만 실제 파싱 메모리 실측 전 이를 보장하지 않는다. 추가 worker/프로젝트·workspace 플랜/seat 비용은 별도다. 개발 중 무료 환경은 탐색에만 사용하며 무료 플랜이 항상 심사 서비스 가용성을 충족한다고 가정하지 않는다. DB 생성일이 10/16이면 11/11 제출 직후 30일 만료가 결선보다 이를 수 있어 Render 무료 DB를 심사 원본 저장소로 권고하지 않는다.

대안 예산은 Vercel Pro20+Railway API/worker10~30+Supabase25 = $55~75+AI, Vercel Pro20+Cloud Run compute0~10+Supabase25 = $45~55+Tasks/Jobs·빌드·레지스트리·전송+AI의 추정이다. 서로 다른 성능/가용성 구성이라 단순 저가 순위를 의미하지 않는다. 자체 Cloud SQL/GCS 구성 비용을 이 Supabase 대안 계산에 포함했다고 주장하지 않는다.

### 예산과 절전 정책

승인 요청 시 프로젝트/리전·API/worker 크기·DB/파일 용량·월 예상/최대 예산·기간·자동갱신·종료 방법을 명시한다. 플랫폼 예산 알림은 항상 지출 hard cap이 아니므로 애플리케이션의 사용자/기관/전체 AI reservation·동시성·토큰/업로드 한도를 병행한다. 심사 운영은 적합한 지속 실행 플랜을 승인받는 안을 우선하고, 무료 절전 우회용 주기 ping을 운영 전략으로 삼지 않는다.

## 7 새 보안 운영 위험과 통제

공개 인터넷은 공격·무단 가입·파일 파서 취약점·기관 간 IDOR·토큰 탈취·API 요금 폭주·공개 bucket·로그 유출·일시 디스크 소실·DB/파일 불일치·무료 만료·공급자 장애·지역 간 전송 위험을 더한다. PRD WEB-01~08, ARCHITECTURE 설정표, TEST_PLAN에 통제와 합격 기준을 연결했다.

- HTTPS, 정확 CORS origin, 초대 관리자/서버 JWT·멤버십/역할, private bucket·다운로드 API, browser CSP/XSS/프리뷰 격리.
- 공개 출처/합성 확인, 허용 형식·실제 signature·크기·압축/XML 한도. 내부/비공개/개인정보/비밀키는 금지하며 자동 탐지의 완전성을 보장하지 않음.
- 문서 지시를 실행 권한으로 취급하지 않음, 임의 URL fetch/외부 엔티티/명령 비활성, 모든 AI 주장·노드/간선/추천·그림 설명에 근거·버전 연결.
- 키는 서버 시크릿만, VITE_* 비밀 금지, 로그에 원문/질문/Authorization·키·민감 파일명 없음. 요청/토큰/비용 예약·429·동시성/저장량 제한.
- DB/객체 별도 백업·해시 manifest·등록 해제 tombstone 복원 검증. RPO24h/RTO4h는 목표안이며 실측 전 PASS 금지.

Supabase DB 백업에는 Storage 객체가 포함되지 않는다. 객체 백업/복원과 권한을 별도로 검증해야 한다. [백업 문서](https://supabase.com/docs/guides/platform/backups)

보관기간은 제출 후30일(12/11)까지 시연 데이터 보존 후 접근 중지·담당자 통지하는 제안으로, 결선/요청에 따라 확정한다. 원본·백업을 자동 삭제하지 않는다. 등록 해제와 원본 영구폐기를 구분하고 별도 명시 승인 없이 원본을 수정·이동·삭제하지 않는다. 개인정보가 섞이지 않도록 데이터 수집을 최소화하며 이 설계로 기관 보안 인증이 완료됐다고 주장하지 않는다.

## 8 G1에 남은 검증

| 구분 | 남은 작업/판정 |
|---|---|
| 기존 기술 증거 | 최소 스파이크만 PASS 재사용. 제품 수용시험으로 승격하지 않음 |
| HWPX | 실제 정상 공개/합성 파일의 읽기 순서·표/그림·원문 위치/뷰어 대조 미검증 |
| 실제 AI | 승인된 API 2종 실제 연결/교체·JSON/근거/오류·지연/비용 미검증 |
| 의미검색 | 실제 한글 임베딩·Top-5·기관/시점/버전 필터·재색인 성능 미검증 |
| 브라우저 | React Flow 표시/노드 선택·원문/서식·목록·SPA/Auth callback 미검증 |
| 클라우드 G1-C | 승인 후 최소 HTTPS/API/Auth/DB/파일 재시작·재배포 영속성 시험. 현재 미승인·미실행 |
| 루트·운영 | 실제 루트/Skill 발견·골드셋/성능 예산·원본/기간/비용 조건 확정 필요 |
| 심사 G6 | 공개 URL의 평가자 계정+별도 소스 독립 실행. Docker 선택, 네이티브 방법 필수 |

현재 TASKS는 G1-A 기존 증거, G1-B 핵심 기술, G1-C 승인된 최소 클라우드 실증을 구분한다. 사용자 운영변경으로 내부망/GPU/Docker 필수는 제외했지만 G1 전체는 미통과다. 클라우드 시험이 승인 대기이면 NOT_RUN/BLOCKED로 남긴다. 심사 전체 소스 재현은 G6에서 별도로 완료한다.

## 9 Phase 2 착수 판정

설계문서 전환과 개발 방향 수정은 완료했다. 전체 웹앱 구현은 시작하지 않았다. **현재 G1 미통과로 Phase 2 정식 착수는 보류**한다. 이유는 Docker나 로컬 GPU가 아니라 실제 파서/AI/검색/브라우저/클라우드 실증 부족이다. 로컬 데이터 모델·인증 계약의 준비가 가능하다는 판단과 제품 기능 구현 착수를 혼동하지 않는다.

실제 개발 루트는 아직 없다. 현재 CWD는 workspace, 기준 문서는 outputs이며 루트 AGENTS/Skill은 존재하지 않는다. 현재 세션은 명시 요청으로 직접 읽었다. workspace를 Git 루트로 정하고 루트 AGENTS/README/`.agents/skills`와 나머지 단일 문서 위치를 확정하는 안을 제안한다. 기존 outputs/증거는 보존하고 승인 없는 대규모 이동은 없다. 자동 발견·명시 호출은 배치 후 새 세션에서 검증해야 한다. [Codex AGENTS 공식 문서](https://learn.chatgpt.com/docs/agent-configuration/agents-md), [Skill 탐색 공식 문서](https://learn.chatgpt.com/docs/build-skills)

공공 GitLab은 비공개 제출 저장소, 웹앱은 공개 접속 URL이다. 플랫폼의 해당 GitLab 연동/심사위원 권한은 미검증이며 다른 호스팅을 위해 공개 Git 미러를 자동 만들지 않는다. Vercel은 CLI 등의 경로를 안내하지만 현재 GitLab의 실제 연동은 검증하지 않았다. [Git 배포 문서](https://vercel.com/docs/git)

## 10 다음 작업 권고

다음 작업은 인터넷망 G1-B 보완으로 제한하는 것을 권고한다. 정상 공개/합성 HWPX·브라우저·실제 모델/임베딩 연결 후보·공통 골드셋·실행/환경 예제를 먼저 준비하고, 실제 유료 호출/클라우드 생성/공개 배포가 필요한 시점에 구체 모델·자료·비용 한도·리소스/리전·기간·공개 범위를 검토 가능하게 제시해 승인을 받는다.

권고 지시문:

> 수정된 7개 기준 문서와 배포 전략을 읽고 인터넷망 G1 미검증 항목만 보완하라. 기존 PASS·Phase 1 증거·FR-01~19를 보존하라. 개발 루트와 AGENTS/Skill 배치를 확정하고 정상 공개/합성 HWPX와 PC 브라우저를 검증하라. 실제 모델 2종·임베딩/OCR의 요청/근거/비용 검증을 준비하되 유료 호출은 명시 예산 승인 후만 실행하라. 클라우드 최소 실증은 리소스/리전/요금·HTTPS/권한·DB/파일·복구 검증 계획을 준비한 뒤 승인 후 수행하라. 전체 웹앱 구현·원격 push·무승인 공개 배포는 하지 말고 G1 결과를 다시 보고하라.

제출 기준 11/11, 기능 동결11/09, 후보11/10을 유지한다. 참가 행정절차·정확 마감 시각·최신 공모 공지는 이번 운영문서 전환에서 새로 검증하지 않았다.
