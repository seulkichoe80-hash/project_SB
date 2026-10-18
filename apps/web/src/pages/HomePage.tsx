import { useAuth } from '../auth/AuthContext';
import { EmptyState, ErrorState, Icon, LoadingState, PageTitle, StatusBadge } from '../components/UI';
import '../styles/home.css';

// Presentation states only. No request, simulated delay, or fabricated document data.
export type RecentDocumentsStatus = 'disconnected' | 'loading' | 'empty' | 'error';
export function RecentDocumentsState({ status = 'disconnected' }: { status?: RecentDocumentsStatus }) {
  if (status === 'loading') return <LoadingState message="최근 문서를 불러오고 있습니다." />;
  if (status === 'error') return <ErrorState message="최근 문서를 조회하지 못했습니다. 문서가 없는 상태와는 다릅니다. 연결 상태를 확인해 주세요." />;
  if (status === 'empty') return <EmptyState title="등록된 문서가 없습니다" description="조회가 정상적으로 완료되었으나 표시할 문서가 없습니다." />;
  return <EmptyState title="최근 문서 조회가 연결되지 않았습니다" description="등록된 문서가 있는지는 아직 확인할 수 없습니다. 자료 조회 기능이 연결되면 이곳에서 확인할 수 있습니다." />;
}

export function HomePage() {
  const auth = useAuth();
  const manager = auth.user?.role === 'manager';
  const note = !auth.ready ? '로그인과 기관 권한을 확인하고 있습니다.' : !auth.user ? '문서 등록·조회 기능을 제공합니다. 로그인 후 기관 권한에 따라 이용할 수 있습니다.' : manager ? '공개·합성 PDF/HWPX를 등록하고 파싱·청킹 처리 상태를 확인할 수 있습니다.' : '소속 기관의 활성 문서와 원본을 조회할 수 있습니다. 문서 등록·작업 요청은 자료관리자에게 문의해 주세요.';
  const capability = !auth.ready ? '권한 확인 중' : !auth.user ? '로그인 필요' : manager ? '문서 등록·조회 가능' : '문서 조회 가능';
  return <div className="home-page">
    <PageTitle eyebrow="업무의 시작" title="업무 홈" description="문서를 모으고, 필요한 내용을 찾고, 원문을 확인하며 업무를 준비하는 공간입니다." />
    <section className="home-welcome" aria-labelledby="welcome-title">
      <span className="section-kicker">서무ITDA와 업무 시작하기</span>
      <h2 id="welcome-title">어디서 시작할지 막막할 때,<br />문서부터 살펴보세요.</h2>
      <p>기관의 매뉴얼·규정·서식을 바탕으로 업무를 안내합니다.<br />문서 기능은 로그인과 기관 권한에 따라 사용할 수 있습니다. 실제 AI 질문·답변은 연결되지 않았습니다.</p>
      <a className="button button--primary" href="#/documents">문서 관리로 이동 <Icon name="arrow" /></a>
    </section>

    <section className="start-section" aria-labelledby="home-actions-title">
      <div className="section-heading"><h2 id="home-actions-title">주요 작업</h2><span>할 수 있는 일과 준비 중인 일을 확인하세요</span></div>
      <div className="task-row"><span className="task-icon"><Icon name="document" /></span><div className="home-task-copy"><h3>문서 관리 <StatusBadge>{capability}</StatusBadge></h3><p id="home-upload-note">{note}</p></div><a className="button button--secondary" href="#/documents" aria-describedby="home-upload-note">{manager ? "문서 등록하러 가기" : auth.user ? "문서 조회로 이동" : "로그인 상태 확인"}</a></div>
      <div className="task-row task-row--pending"><span className="task-icon"><Icon name="spark" /></span><div><h3>AI 업무 지원 <StatusBadge>실제 AI 미연결</StatusBadge></h3><p>문서를 근거로 업무를 안내할 예정입니다. 현재 질문 전송과 답변 생성은 제공하지 않습니다.</p></div></div>
    </section>

    <section className="home-section home-recent" aria-labelledby="recent-title">
      <div className="section-heading"><h2 id="recent-title">최근 문서</h2><StatusBadge>조회 미연결</StatusBadge></div>
      <RecentDocumentsState />
    </section>

    <section className="home-section" aria-labelledby="processing-title">
      <div className="section-heading"><h2 id="processing-title">문서는 이렇게 처리해요</h2><StatusBadge>처리 현황 미연결</StatusBadge></div>
      <p className="home-section-note">아래는 단계별 설명입니다. 실제 처리 건수나 진행 상태가 아닙니다.</p>
      <dl className="home-processing">
        <div><dt>원문 추출</dt><dd>문서의 글과 표를 읽고, 원문에서 어디에 있는지 기록합니다. 업무 의미를 판단하는 단계는 아닙니다.</dd></div>
        <div><dt>검색용 나누기 <span>(청킹)</span></dt><dd>찾기 좋은 크기로 내용을 나누되 제목·표와 원문 연결을 유지합니다. AI가 답변을 만드는 단계와 다릅니다.</dd></div>
        <div><dt>업무절차 후보 <StatusBadge>관리자 검토</StatusBadge></dt><dd>자료관리자는 현재 활성 문서의 오프라인 자동 추출 후보와 원문을 비교할 수 있습니다. 실제 AI 모델의 의미 검증은 제공하지 않습니다.</dd></div>
      </dl>
    </section>

    <section className="home-section home-guide" aria-labelledby="guide-title">
      <h2 id="guide-title">처음이라면, 이 흐름을 기억하세요</h2>
      <p className="home-section-note">문서 관리와 업무절차 검토 화면에서 확인할 수 있는 흐름입니다. 권한과 문서 처리 상태에 따라 가능한 작업이 달라집니다.</p>
      <ol className="home-steps">
        <li><strong>문서 등록</strong><p>공개·합성 매뉴얼과 서식을 모읍니다. 자료관리자는 등록·처리 작업을 요청하고, 직원은 허용된 문서를 조회합니다.</p></li>
        <li><strong>원문 추출</strong><p>자료관리자는 문서 상세에서 파싱·청킹 처리 상태를 확인할 수 있습니다.</p></li>
        <li><strong>근거 검토</strong><p>자료관리자는 업무절차 검토에서 자동 추출 후보와 원문을 비교합니다. 출처 확인과 내용 검토는 별개입니다.</p></li>
      </ol>
      <p className="home-section-note">업무절차 검토에는 활성 문서가 필요합니다. 자료관리자는 문서 상세에서 파싱·청킹 완료를 확인한 뒤 버전을 활성화할 수 있습니다.</p>
      {manager && <a className="text-link" href="#/workflows">업무절차 후보 검토</a>}
      <a className="home-help-link" href="#/help"><Icon name="help" />사용 범위와 원문 보호 안내 <Icon name="arrow" /></a>
      <p className="privacy-note"><Icon name="shield" />실제 내부 행정자료·개인정보는 업로드하지 마세요. 개발·시연에는 공개·합성 자료만 사용합니다.</p>
    </section>
  </div>;
}
