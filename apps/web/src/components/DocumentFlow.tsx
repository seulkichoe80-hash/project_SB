import { useEffect, useRef, useState } from 'react';
import { ApiError, documentsClient as client, type Metadata, type Job } from '../api/documents';
import { requestDeadline } from '../api/requestDeadline';
import { Button, ErrorState, StatusBadge } from './UI';

/** State is scoped by the parent's document/version key. No persistent client cache. */
export function DocumentFlow({meta, parsing, canManage, rows, onRefresh, onInvalid}: {
  meta: Metadata; parsing: Job | null; canManage: boolean; rows: Metadata[];
  onRefresh: (meta: Metadata, rows?: Metadata[]) => void; onInvalid: (error: unknown) => void;
}) {
  const [parse, setParse] = useState<Job | null>(null), [chunk, setChunk] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [review, setReview] = useState(false), [notice, setNotice] = useState('');
  const scope = useRef(new AbortController()), latch = useRef(false), dialog = useRef<HTMLDialogElement>(null), cancel = useRef<HTMLButtonElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const parsed = parse ?? parsing;
  const active = rows.find(r => r.document_id === meta.document_id && r.active && r.registered);
  const groundedJobs = parsed?.version_id === meta.id && chunk?.version_id === meta.id && typeof parsed.attempt === 'number' && chunk.parse_job_id === parsed.id && chunk.parse_attempt === parsed.attempt;
  const eligible = groundedJobs && canManage && meta.registered && !meta.active && meta.state === 'completed' && parsed?.state === 'completed' && chunk?.state === 'completed';
  useEffect(() => { scope.current = new AbortController(); return () => scope.current.abort(); }, []);
  useEffect(() => { if(review) {dialog.current?.showModal();cancel.current?.focus();} }, [review]);
  const close = () => { dialog.current?.close(); setReview(false); trigger.current?.focus(); };
  function scoped(value: Metadata) {
    if(value.id !== meta.id || value.document_id !== meta.document_id || value.institution_id !== meta.institution_id || !value.registered) throw new ApiError(409);
    return value;
  }
  function jobInScope(job: Job, expectedId?: string) {
    if(!job || typeof job.id!=='string' || !job.id || job.version_id!==meta.id || (expectedId && job.id!==expectedId) || !['queued','processing','completed','failed','cancelled'].includes(job.state)) throw new ApiError(422);
    return job;
  }
  async function run(action: (signal: AbortSignal) => Promise<void>) {
    if(latch.current || scope.current.signal.aborted) return;
    latch.current = true; setBusy(true); setError('');setNotice('');
    try { await requestDeadline(scope.current.signal, action); }
    catch(e) { if(!scope.current.signal.aborted) {
      // An ambiguous failure never implies a submitted activation was rolled back.
      setError(e instanceof ApiError && e.status === 409 ? '문서·처리 상태가 변경되었거나 요청이 충돌했습니다.' : e instanceof ApiError ? e.message : '요청을 완료하지 못했습니다.');
      setChunk(null);close();
      if(e instanceof ApiError && [401,403,404].includes(e.status)) onInvalid(e);
    }} finally { latch.current = false; if(!scope.current.signal.aborted) setBusy(false); }
  }
  async function refresh(signal: AbortSignal) {
    const [fresh, job, list] = await Promise.all([client.detail(meta.document_id,meta.id,signal),client.parsing(meta.document_id,meta.id,signal),client.list(signal)]);
    if(signal.aborted) return;
    scoped(fresh);
    if(list.some(r=>r.institution_id!==meta.institution_id)) throw new ApiError(403);
    const next = chunk ? await client.chunkStatus(meta.document_id,meta.id,chunk.id,signal) : null;
    if(signal.aborted) return;
    setParse(jobInScope(job));setChunk(next && next.parse_job_id===job.id && next.parse_attempt===job.attempt ? jobInScope(next,chunk?.id) : null);onRefresh(fresh,list);
  }
  async function activate(signal: AbortSignal) {
    // Preserve the disclosure the administrator actually confirmed, then compare fresh state.
    const previousActive = active?.id ?? null;
    const [fresh, job, list, chunked] = await Promise.all([
      client.detail(meta.document_id,meta.id,signal), client.parsing(meta.document_id,meta.id,signal),client.list(signal),
      client.chunkStatus(meta.document_id,meta.id,chunk!.id,signal),
    ]);
    if(signal.aborted) return;
    scoped(fresh);
    if(list.some(r=>r.institution_id!==meta.institution_id)) throw new ApiError(403);
    jobInScope(job);jobInScope(chunked,chunk!.id);
    const currentActive=list.find(r=>r.document_id===meta.document_id&&r.active&&r.registered)?.id??null;
    if(fresh.active || currentActive!==previousActive || fresh.sha256!==meta.sha256 || fresh.revision!==meta.revision || fresh.state!=='completed' || job.state!=='completed' || chunked.state!=='completed' || typeof job.attempt!=='number' || chunked.parse_job_id!==job.id || chunked.parse_attempt!==job.attempt) {
      setParse(job);onRefresh(fresh,list);throw new ApiError(409);
    }
    await client.activate(meta.document_id,meta.id,signal);
    if(signal.aborted) return;
    // Never present the mutation response alone as the current server state.
    const [verified, latest] = await Promise.all([client.detail(meta.document_id,meta.id,signal),client.list(signal)]);
    if(signal.aborted) return;
    scoped(verified);
    if(latest.some(r=>r.institution_id!==meta.institution_id)) throw new ApiError(403);
    if(!verified.active || !latest.some(r=>r.id===meta.id&&r.document_id===meta.document_id&&r.active&&r.registered)) throw new ApiError(409);
    onRefresh(verified,latest);close();setNotice('활성화 후 서버 상태를 다시 확인했습니다. 업무절차 후보 검토로 이동할 수 있습니다.');
  }
  const status=(state?:string)=>({completed:'완료',queued:'처리 대기',processing:'처리 중',failed:'실패',cancelled:'취소됨'}[state??'']??'미확인');
  return <section className="document-flow" aria-labelledby="document-flow-title">
    <h3 id="document-flow-title">다음 작업</h3>
    <ol className="document-flow-steps">
      <li>문서 등록: {meta.registered?'등록됨':'등록 해제'}</li>
      <li>원문 처리: {status(meta.state)}</li>
      <li>파싱: {status(parsed?.state)} · 청킹: {status(chunk?.state)}</li>
      <li>활성 버전: {meta.active?`선택한 버전 ${meta.number} 사용 중`:active?`현재 버전 ${active.number} 사용 중`:'없음'}</li>
    </ol>
    {!canManage && <p>직원 계정은 문서 조회만 가능합니다. 처리·활성화는 자료관리자에게 문의해 주세요.</p>}
    {meta.active ? <><StatusBadge tone="info">현재 활성 버전</StatusBadge><p>이 문서 버전을 업무절차 후보 검토에 사용할 수 있습니다. 공식 절차 승인과는 다릅니다.</p>
      {canManage&&<a className="button button--primary" href={`#/workflows?document=${encodeURIComponent(meta.document_id)}&version=${encodeURIComponent(meta.id)}`}>업무절차 후보 검토</a>}</>
      : <><StatusBadge tone={eligible?'info':'warning'}>{eligible?'활성화 준비 완료':'활성화 전 확인 필요'}</StatusBadge>
      <p>{eligible?'선택한 문서와 현재 활성 버전을 확인한 뒤 직접 활성화해 주세요.':parsed?.state==='failed'?'원문을 읽지 못했습니다. 파싱 재시도 후 상태를 확인해 주세요.':parsed?.state!=='completed'?'원문 처리 중에는 활성화할 수 없습니다. 상태를 새로고침해 주세요.':!chunk?'청킹 작업 ID가 미확인입니다. 청킹 요청·상태 확인으로 기존 작업을 확인하거나 새 작업을 요청해 주세요.':chunk.state==='failed'?'청킹에 실패했습니다. 재시도 후 완료 상태를 확인해 주세요.':'청킹 완료 후 상태를 확인하면 활성화할 수 있습니다.'}</p></>}
    <p>파싱·청킹 완료는 AI 분석이나 내용 검증 완료를 뜻하지 않습니다.</p>
    {error&&<ErrorState message={`${error} 서버 상태를 새로 확인해 주세요. 활성화 결과는 재조회 전까지 확정하지 않습니다.`} onRetry={()=>void run(refresh)} />}
    {notice&&<p role="status">{notice}</p>}
    <div className="document-actions">
      <Button variant="secondary" disabled={busy} onClick={()=>void run(refresh)}>상태 새로고침</Button>
      {canManage&&parsed?.state==='failed'&&<Button disabled={busy} onClick={()=>void run(async signal=>{const job=await client.retryParsing(meta.document_id,meta.id,signal);if(!signal.aborted){setParse(jobInScope(job));setChunk(null);}})}>파싱 재시도</Button>}
      {canManage&&meta.registered&&!meta.active&&parsed?.state==='completed'&&!chunk&&<Button disabled={busy} onClick={()=>void run(async signal=>{const job=await client.enqueueChunks(meta.document_id,meta.id,signal);if(!signal.aborted)setChunk(jobInScope(job));})}>청킹 요청·상태 확인</Button>}
      {chunk&&<Button variant="secondary" disabled={busy} onClick={()=>void run(refresh)}>청킹 상태 새로고침</Button>}
      {canManage&&chunk?.state==='failed'&&<Button disabled={busy} onClick={()=>void run(async signal=>{const job=await client.retryChunks(meta.document_id,meta.id,chunk.id,signal);if(!signal.aborted)setChunk(jobInScope(job));})}>청킹 재시도</Button>}
      {eligible&&<button ref={trigger} className="button button--primary" disabled={busy} onClick={()=>setReview(true)}>이 버전 활성화</button>}
    </div>
    {review&&<dialog ref={dialog} className="deregister-dialog" aria-labelledby="activation-title" onCancel={e=>{e.preventDefault();if(!busy)close();}}>
      <h2 id="activation-title">이 문서 버전을 활성화할까요?</h2><p>{meta.original_name} · 버전 {meta.number}</p>
      <p>현재 활성 버전: {active?`${active.original_name} · 버전 ${active.number}`:'없음'}</p>
      <p>활성화하면 이 버전이 검색·업무절차 검토 기준이 됩니다. 이전 버전의 원본은 보존합니다. 업무절차의 공식 승인·게시가 아닙니다.</p>
      <div className="document-actions"><button ref={cancel} className="button button--secondary" disabled={busy} onClick={close}>취소</button><Button disabled={busy} onClick={()=>void run(activate)}>{busy?'활성화 확인 중…':'활성화 확인'}</Button></div>
    </dialog>}
  </section>;
}
