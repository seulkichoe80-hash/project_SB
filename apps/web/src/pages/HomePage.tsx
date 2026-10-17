import { Button, EmptyState, ErrorState, Icon, LoadingState, PageTitle, StatusBadge } from '../components/UI';
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
  return <div className="home-page">
    <PageTitle eyebrow="업무의 시작" title="업무 홈" description="문서를 모으고, 필요한 내용을 찾고, 원문을 확인하며 업무를 준비하는 공간입니다." />
    <section className="home-welcome" aria-labelledby="welcome-title">
      <span className="section-kicker">서무ITDA와 업무 시작하기</span>
      <h2 id="welcome-title">어디서 시작할지 막막할 때,<br />문서부터 살펴보세요.</h2>
      <p>기관의 매뉴얼·규정·서식을 바탕으로 업무를 안내합니다.<br />현재는 문서 관리 화면을 살펴볼 수 있으며, 자료 연결과 AI 기능은 준비 중입니다.</p>
      <a className="button button--primary" href="#/documents">문서 관리로 이동 <Icon name="arrow" /></a>
    </section>

    <section className="start-section" aria-labelledby="home-actions-title">
      <div className="section-heading"><h2 id="home-actions-title">주요 작업</h2><span>할 수 있는 일과 준비 중인 일을 확인하세요</span></div>
      <div className="task-row"><span className="task-icon"><Icon name="document" /></span><div className="home-task-copy"><h3>문서 등록 <StatusBadge>준비 중</StatusBadge></h3><p id="home-upload-note">문서 관리에서 등록 화면을 확인할 수 있습니다. 실제 전송에는 인증이 필요합니다.</p></div><Button variant="secondary" disabled aria-describedby="home-upload-note">문서 등록 · 준비 중</Button></div>
      <div className="task-row task-row--pending"><span className="task-icon"><Icon name="spark" /></span><div><h3>AI 업무 지원 <StatusBadge>준비 중</StatusBadge></h3><p>문서를 근거로 업무를 안내할 예정입니다. 현재 질문 전송과 답변 생성은 제공하지 않습니다.</p></div></div>
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
        <div><dt>AI 분석 <StatusBadge>준비 중</StatusBadge></dt><dd>확인된 근거를 바탕으로 업무 안내 후보를 만듭니다. 실제 AI는 미연결이며, 결과는 원문과 비교해 검토해야 합니다.</dd></div>
      </dl>
    </section>

    <section className="home-section home-guide" aria-labelledby="guide-title">
      <h2 id="guide-title">처음이라면, 이 흐름을 기억하세요</h2>
      <p className="home-section-note">자료 연결 후 제공할 흐름입니다. 아래 단계는 아직 이 화면에서 실행할 수 없습니다.</p>
      <ol className="home-steps">
        <li><strong>문서 등록</strong><p>공개·합성 매뉴얼과 서식을 모읍니다. 문서 관리에서 등록 UI를 제공하며 실제 인증 연결은 준비 중입니다.</p></li>
        <li><strong>원문 추출</strong><p>문단·표와 출처를 확인합니다. 처리 결과 화면은 준비 중입니다.</p></li>
        <li><strong>근거 검토</strong><p>안내 내용과 원문을 비교합니다. 원문 검토 화면은 준비 중입니다.</p></li>
      </ol>
      <a className="home-help-link" href="#/help"><Icon name="help" />사용 범위와 원문 보호 안내 <Icon name="arrow" /></a>
      <p className="privacy-note"><Icon name="shield" />실제 내부 행정자료·개인정보는 업로드하지 마세요. 개발·시연에는 공개·합성 자료만 사용합니다.</p>
    </section>
  </div>;
}
