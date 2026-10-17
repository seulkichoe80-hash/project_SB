import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useAuth, LoginPanel } from './auth/AuthContext';
import { DocumentsPage } from './pages/DocumentsPage';
import { HomePage } from './pages/HomePage';
import { AppLayout, pages, type Page } from './components/AppLayout';
import { EmptyState, Icon, PageTitle } from './components/UI';

function currentPage(): Page | null {
  const value = window.location.hash.replace(/^#\/?/, '') || 'home';
  return pages.some(p => p.id === value) ? value as Page : null;
}

export function App() {
  const auth = useAuth();
  const [page, setPage] = useState<Page | null>(currentPage);
  const previousPage = useRef<Page | null>(page);
  const authKey = auth.ready ? (auth.user?.user_id ?? 'guest') + (auth.user?.institution_id ?? '') : 'pending';
  const previousAuth = useRef(authKey);
  useEffect(() => {
    const change = () => setPage(currentPage());
    window.addEventListener('hashchange', change);
    return () => window.removeEventListener('hashchange', change);
  }, []);
  useLayoutEffect(() => {
    document.title = `${pages.find(p => p.id === page)?.label ?? '화면을 찾을 수 없음'} · 서무ITDA`;
    if (previousPage.current !== page || (page === 'documents' && authKey !== previousAuth.current)) document.getElementById('page-heading')?.focus();
    previousAuth.current = authKey;
    previousPage.current = page;
  }, [page, authKey]);
  return <AppLayout page={page}>{page === 'home' ? <HomePage /> : page === 'documents' ? (auth.ready && auth.user ? <DocumentsPage key={auth.user.user_id+auth.user.institution_id} /> : <LoginPanel />) : page === 'ai' ? <AI /> : page === 'help' ? <Help /> : <NotFound />}</AppLayout>;
}

function AI() {
  return <><PageTitle eyebrow="원문 기반 업무 안내" title="AI 업무 지원" description="질문에 필요한 원문 근거와 업무 절차를 함께 살펴보는 기능을 준비하고 있습니다." /><section className="plain-panel"><EmptyState icon="spark" title="AI 업무 지원을 준비하고 있습니다" description="현재 실제 AI 모델은 연결되지 않았으며, 질문 전송이나 답변 생성은 실행되지 않습니다." /><div className="principle-list"><p><Icon name="check" />답변의 근거를 원문에서 확인</p><p><Icon name="check" />근거가 부족하면 안내 보류</p><p><Icon name="check" />다른 기관 자료에 대한 접근 제한</p></div><a href="#/help" className="text-link">사용 범위와 제한 보기 <Icon name="arrow" /></a></section></>;
}

function Help() {
  return <><PageTitle eyebrow="이용 안내" title="도움말" description="현재 사용할 수 있는 화면과 안전한 자료 이용 원칙을 안내합니다." /><section className="help-section" aria-labelledby="help-title"><h2 id="help-title">현재 제공 범위</h2><p>업무 홈, 문서 관리의 기본 구성과 AI 업무 지원 준비 안내를 볼 수 있습니다. 문서 API와 로컬 세션 UI를 제공하지만 실제 인증 공급자는 미연결이므로 기본 서버는 401로 차단합니다. AI 질문은 연결되지 않았습니다.</p><details open><summary>문서가 없다는 표시와 미연결 표시는 어떻게 다른가요?</summary><p>‘등록된 문서 없음’은 정상 조회 결과가 비어 있을 때 사용합니다. 현재의 ‘조회 미연결’은 자료 조회 자체가 준비되지 않았다는 뜻입니다. ‘조회 실패’는 연결 후 요청이 실패한 경우에만 표시합니다.</p></details><details><summary>어떤 자료를 사용할 수 있나요?</summary><p>문서 등록 시 공개·합성 자료만 사용해야 합니다. 내부·비공개 행정자료, 개인정보, 비밀키가 포함된 자료는 사용하지 않습니다.</p></details><details><summary>AI 결과를 바로 업무 기준으로 사용할 수 있나요?</summary><p>AI 후보와 원문은 구분해야 합니다. 원문 근거·적용 기관·버전을 확인하고 사람이 검토해야 하며, 근거가 없는 기한·금액·절차는 확정할 수 없습니다.</p></details><details><summary>원문과 HWPX는 어떻게 확인하나요?</summary><p>원문 검토 화면은 후속 단계에서 제공할 예정입니다. HWPX의 XML 구조와 실제 한컴 화면의 읽기 순서는 다를 수 있으며, 검증되지 않은 페이지 번호를 표시하지 않습니다.</p></details></section></>;
}

function NotFound() {
  return <><PageTitle eyebrow="화면 안내" title="화면을 찾을 수 없습니다" description="주소를 확인하거나 업무 홈으로 이동해 주세요." /><a className="button button--primary" href="#/home">업무 홈으로 이동</a></>;
}
