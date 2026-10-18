import type { ReactNode } from 'react';
import { useAuth } from '../auth/AuthContext';
import { Icon, StatusBadge, type IconName } from './UI';

export type Page = 'home' | 'documents' | 'workflows' | 'ai' | 'help';
export const pages: { id: Page; label: string; icon: IconName; pending?: boolean }[] = [
  { id: 'home', label: '업무 홈', icon: 'home' },
  { id: 'documents', label: '문서 관리', icon: 'document' },
  { id: 'workflows', label: '업무절차 검토', icon: 'document' },
  { id: 'ai', label: 'AI 업무 지원', icon: 'spark', pending: true },
  { id: 'help', label: '도움말', icon: 'help' },
];

export function Sidebar({ page }: { page: Page | null }) {
  const auth=useAuth();
  return <aside className="sidebar" aria-label="서비스 탐색">
    <a className="brand" href="#/home" aria-label="서무ITDA 업무 홈"><span className="brand-mark" aria-hidden="true">잇</span><span className="brand-name">서무<span>ITDA</span><small>행정업무 AI 워크스페이스</small></span></a>
    <p className="nav-caption">워크스페이스</p>
    <nav aria-label="주 메뉴">{pages.filter(item=>item.id!=='workflows'||auth.user?.role==='manager').map(item => <a key={item.id} href={`#/${item.id}`} className={`nav-item ${page === item.id ? 'is-active' : ''}`} aria-current={page === item.id ? 'page' : undefined}><Icon name={item.icon} /><span>{item.label}</span>{item.pending && <span className="nav-pending">준비 중</span>}</a>)}</nav>
    <div className="sidebar-note"><Icon name="shield" /><p>행정업무의 시작과 끝에<br /><strong>확인할 수 있는 근거</strong></p></div>
    <p className="sidebar-footer">서무ITDA <span>화면 기반</span></p>
  </aside>;
}

export function Header({ title }: { title: string }) {
  const auth = useAuth();
  return <header className="header"><p className="breadcrumb">워크스페이스 <span aria-hidden="true">/</span> <strong>{title}</strong></p><div className="header-tools"><span className="auth-status">{auth.user ? `${auth.user.institution_name} · ${auth.user.role === 'manager' ? '자료관리자' : '직원'}${auth.user.institution_admin ? ' · 기관관리' : ''}` : '인증·기관 미연결'}</span>{auth.user ? <button className="button button--secondary" onClick={()=>void auth.logout()}>로그아웃</button> : <a className="help-link" href="#/documents">로그인</a>}<a href="#/help" className="help-link"><Icon name="help" /><span>도움말</span></a></div></header>;
}

export function AppLayout({ page, children }: { page: Page | null; children: ReactNode }) {
  const auth=useAuth();
  const title = pages.find(p => p.id === page)?.label ?? '화면을 찾을 수 없음';
  return <><a href="#main-content" className="skip-link" onClick={event => { event.preventDefault(); document.getElementById('main-content')?.focus(); }}>본문으로 바로가기</a><div className="app-layout"><Sidebar page={page} /><div className="workspace"><Header title={title} /><div className="connection-notice"><StatusBadge tone="info">{page === 'workflows' && auth.user?.role === 'manager' ? '관리자 검토 전용' : '데이터 미연결'}</StatusBadge><p>{page === 'workflows' && auth.user?.role === 'manager' ? '로그인한 기관의 현재 문서 버전만 조회합니다. 오프라인 후보이며 의미 검증·공식 게시가 완료되지 않았습니다.' : '문서 자료는 로그인과 기관 권한이 필요합니다. 실제 공급자는 아직 미연결이며 실제 AI 기능도 연결되지 않았습니다.'}</p></div><main id="main-content" tabIndex={-1}>{children}</main><footer className="workspace-footer"><span>원문은 그대로, 판단은 근거와 함께.</span><span>공개·합성 자료만 사용해 주세요.</span></footer></div></div></>;
}
