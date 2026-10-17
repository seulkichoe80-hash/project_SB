# Stage2 프런트엔드 계약

FR-01/07/09/12/15/18의 향후 화면 경계, NFR-01/03/05/06/07 및 WEB-01/02/03/04/06의 프런트엔드 기반 부분이다. 요구사항 전체 통과를 뜻하지 않는다. 기존 API·DB·EvidenceRef·백엔드·fixture는 변경하지 않았다.

Phase1 잠금 해석 버전을 재사용해 React/react-dom19.3.1,TypeScript7.0.2,Vite8.3.4,plugin-react6.1.2,types19.3.0을 정확 고정했다. 복사한 잠금 graph를 npm offline으로 갱신해 이번에 사용하지 않는 ReactFlow 의존성을 제거했다. 기존 지도 기술 선택은 유지하며 추가 UI 라이브러리·라우터·웹폰트는 없다.

색상/간격/타이포그래피/44px 조작 영역/반경/포커스/224px 사이드바 토큰을 사용한다. AppLayout·Sidebar·Header,PageTitle·Button·StatusBadge·LoadingState·EmptyState·ErrorState를 분리했다. table·reduced motion·forced colors·800px 이하 상단2열 메뉴를 제공한다. 우측 검토 패널은 아직 없고 main 슬롯으로 확장할 수 있다.

4화면은 해시 경로/제목/aria-current/이동 후 h1 포커스/본문 바로가기/history/unknown 경로 안내를 제공한다. AI 메뉴는 준비 안내로만 이동한다. 실제 통계·최근 작업·업로드·검색·정렬·AI 입력·원문 뷰어·사용자 수정/확정은 없다. 미연결과 빈 결과·조회 실패를 구분하며 가짜 사용자·기관·건수·진행률은 표시하지 않는다.

Stage2는 Feature Gate다. 브라우저 검사는 정적 프로덕션 응답 interception이며 live HTTP 검증이 아니다. 확대는720px reflow+글자200%다. screen reader 수동 검토·native toolbar zoom·전체 WCAG2.2AA 감사는 별도이며 backend123개 회귀를 수행한 것으로 표시하지 않는다. 상세 명령·실측·제약은 outputs/STAGE2_REPORT.md, JSON·스크린샷은 outputs/stage2에 보존한다. Stage3는 별도 승인 전 구현하지 않는다.
