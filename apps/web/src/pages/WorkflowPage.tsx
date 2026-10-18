import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  ControlButton,
  useReactFlow,
  MiniMap,
  Handle,
  Position,
  MarkerType,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useAuth, LoginPanel } from "../auth/AuthContext";
import { ApiError, documentsClient, type Metadata } from "../api/documents";
import {
  createWorkflowClient,
  type Candidate,
  type Step,
  type Issue,
  type FormLink,
  type Job,
  type EvidenceRef,
  type Resolved,
  type Citation,
  type Edge,
} from "../api/workflows";
import {
  Button,
  PageTitle,
  StatusBadge,
  ErrorState,
  LoadingState,
  EmptyState,
} from "../components/UI";
import "../styles/workflow.css";
const jobLabels: Record<Job["state"], string> = {
  queued: "대기 중",
  processing: "분석 중",
  completed: "처리 완료 · 검토 필요",
  failed: "처리 실패",
  cancelled: "취소됨",
};
const formLabels: Record<FormLink["match_status"], string> = {
  CANDIDATES: "연결 후보",
  UNLINKED: "미등록 · 미연결",
  AMBIGUOUS: "동명·유사 후보 · 선택 필요",
  BLOCKED: "연결 차단",
};
function message(e: unknown) {
  return e instanceof Error ? e.message : "요청을 처리하지 못했습니다.";
}
function relationLabel(e: Edge) {
  const t = e.explanation.text;
  return /반려|reject/i.test(t)
    ? "반려 관계 후보"
    : /보완|resubmit/i.test(t)
      ? "보완 관계 후보"
      : /반복|돌아|repeat|return/i.test(t)
        ? "반복·복귀 후보"
        : e.relation === "conditional"
          ? "조건 분기 후보"
          : e.relation === "requires"
            ? "필요 관계 후보"
            : "선후 관계 후보";
}
function targets(i: Issue) {
  return i.target_ids ?? (i.target_id ? [i.target_id] : []);
}
type MapData = {
  step: Step;
  selected: boolean;
  count: number;
  select: (id: string) => void;
};
function StepNode({ data }: NodeProps<Node<MapData>>) {
  return (
    <>
      <Handle type="target" position={Position.Top} isConnectable={false} />
      <button
        className="wf-map-node"
        aria-pressed={data.selected}
        onClick={() => data.select(data.step.id)}
      >
        <span className="wf-node-caption">
          단계 후보{" "}
          <span>{data.count ? `검토 ${data.count}` : "원문 연결"}</span>
        </span>
        <strong>{data.step.label.text}</strong>
        <small>선택하여 근거 확인 →</small>
      </button>
      <Handle type="source" position={Position.Bottom} isConnectable={false} />
    </>
  );
}
const nodeTypes = { step: StepNode };
function MapControls() {
  const flow = useReactFlow();
  return (
    <Controls
      showZoom={false}
      showFitView={false}
      showInteractive={false}
      aria-label="지도 탐색"
    >
      <ControlButton
        aria-label="지도 확대"
        title="지도 확대"
        onClick={() => void flow.zoomIn()}
      >
        ＋
      </ControlButton>
      <ControlButton
        aria-label="지도 축소"
        title="지도 축소"
        onClick={() => void flow.zoomOut()}
      >
        −
      </ControlButton>
      <ControlButton
        aria-label="전체 지도 보기"
        title="전체 지도 보기"
        onClick={() => void flow.fitView()}
      >
        ⌂
      </ControlButton>
    </Controls>
  );
}
export function WorkflowPage() {
  const auth = useAuth(),
    [docs, setDocs] = useState<Metadata[]>([]),
    [documentId, setDocumentId] = useState(""),
    [versionId, setVersionId] = useState(""),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true);
  const refresh = useCallback(
    async (signal: AbortSignal) => {
      if (auth.user?.role !== "manager") return;
      try {
        const data = await documentsClient.list(signal);
        if (signal.aborted) return;
        if (data.some((d) => d.institution_id !== auth.user?.institution_id))
          throw new ApiError(403);
        setDocs(data.filter((d) => d.registered));
        setError("");
      } catch (e) {
        if (!signal.aborted) {
          setDocs([]);
          setError(message(e));
        }
      } finally {
        if (!signal.aborted) setLoading(false);
      }
    },
    [auth.user?.institution_id, auth.user?.role],
  );
  useEffect(() => {
    const c = new AbortController();
    if (auth.user?.role === "manager") {
      void refresh(c.signal);
      const timer = setInterval(() => void refresh(c.signal), 5000);
      const focus = () => void refresh(c.signal);
      window.addEventListener("focus", focus);
      return () => {
        c.abort();
        clearInterval(timer);
        window.removeEventListener("focus", focus);
      };
    }
    setLoading(false);
    return () => c.abort();
  }, [refresh, auth.user?.role]);
  useEffect(() => {
    setDocumentId((current) =>
      docs.some((d) => d.document_id === current && d.active)
        ? current
        : (docs.find((d) => d.active)?.document_id ?? ""),
    );
  }, [docs]);
  const versions = docs.filter((d) => d.document_id === documentId);
  useEffect(() => {
    if (!versions.some((v) => v.id === versionId && v.active))
      setVersionId(versions.find((v) => v.active)?.id ?? "");
  }, [docs, documentId, versionId]);
  if (!auth.ready || !auth.user) return <LoginPanel />;
  if (auth.user.role !== "manager")
    return (
      <>
        <PageTitle
          eyebrow="관리자 전용"
          title="업무절차 검토"
          description="자동 추출 후보와 원문 근거를 관리자가 검토하는 화면입니다."
        />
        <EmptyState
          title="관리자 권한이 필요합니다"
          description="직원 계정에는 업무절차 후보 조회·관리 기능을 제공하지 않습니다."
        />
      </>
    );
  const selected = versions.find((v) => v.id === versionId && v.active);
  return (
    <div className="workflow-page">
      <PageTitle
        eyebrow="원문 기반 · 관리자 워크스페이스"
        title="업무절차 검토"
        description="자동 추출 후보를 탐색하고, 단계마다 원문 근거와 검토 항목을 확인하세요."
      />
      <div className="wf-trust">
        <StatusBadge tone="warning">담당자 검토 필요</StatusBadge>
        <span>의미 검증 NOT_VERIFIED · 승인 NOT_REQUESTED</span>
        <strong>공식 업무절차가 아닌 자동 추출 후보입니다.</strong>
      </div>
      <section className="wf-source-select" aria-label="분석 대상 선택">
        <label>
          문서
          <select
            id="workflow-document"
            aria-label="문서"
            value={documentId}
            onChange={(e) => {
              setDocumentId(e.target.value);
              setVersionId("");
            }}
          >
            <option value="">문서 선택</option>
            {[
              ...new Set(
                docs.filter((d) => d.active).map((d) => d.document_id),
              ),
            ].map((id) => (
              <option key={id} value={id}>
                {
                  docs.find((d) => d.document_id === id && d.active)
                    ?.original_name
                }
              </option>
            ))}
          </select>
        </label>
        <label>
          문서 버전
          <select
            id="workflow-version"
            aria-label="문서 버전"
            value={versionId}
            onChange={(e) => setVersionId(e.target.value)}
          >
            <option value="">버전 선택</option>
            {versions.map((v) => (
              <option key={v.id} value={v.id} disabled={!v.active}>
                v{v.number} · {v.active ? "현재 활성" : "비활성 · 조회 불가"}
              </option>
            ))}
          </select>
        </label>
        <span className="wf-scope-note">
          {auth.user.institution_name}
          <br />
          현재 활성 버전만 검토합니다.
        </span>
      </section>
      {error && (
        <ErrorState
          message={error}
          onRetry={() => {
            const c = new AbortController();
            void refresh(c.signal);
          }}
        />
      )}
      {loading ? (
        <LoadingState message="접근 가능한 문서를 확인하고 있습니다." />
      ) : selected ? (
        <Workspace
          key={
            auth.user.user_id +
            auth.user.institution_id +
            selected.document_id +
            selected.id
          }
          meta={selected}
          institution={auth.user.institution_id}
        />
      ) : (
        !error && (
          <EmptyState
            title="검토할 활성 문서가 없습니다"
            description="등록·파싱·청킹 및 활성 버전 설정이 완료된 문서가 필요합니다. 문서 처리 상태를 확인해 주세요."
          />
        )
      )}
    </div>
  );
}
function Workspace({
  meta,
  institution,
}: {
  meta: Metadata;
  institution: string;
}) {
  const client = useMemo(
    () => createWorkflowClient(institution, meta.document_id, meta.id),
    [institution, meta.document_id, meta.id],
  );
  const [candidates, setCandidates] = useState<Candidate[]>([]),
    [generation, setGeneration] = useState(""),
    [chosen, setChosen] = useState(""),
    [candidate, setCandidate] = useState<Candidate | null>(null),
    [issues, setIssues] = useState<Issue[]>([]),
    [forms, setForms] = useState<FormLink[]>([]),
    [stepId, setStepId] = useState(""),
    [job, setJob] = useState<Job | null>(null),
    [busy, setBusy] = useState(false),
    [loading, setLoading] = useState(true),
    [error, setError] = useState(""),
    [empty, setEmpty] = useState(false),
    [pane, setPane] = useState<"map" | "evidence">("map"),
    [mode, setMode] = useState<"map" | "list">("map");
  const alive = useRef(true),
    scope = useRef(new AbortController()),
    mutation = useRef(false),
    loadId = useRef(0),
    selectedDetail = useRef<HTMLHeadingElement>(null);
  const clear = () => {
    setCandidates([]);
    setCandidate(null);
    setIssues([]);
    setForms([]);
    setStepId("");
    setChosen("");
    setGeneration("");
  };
  async function current() {
    const d = await documentsClient.detail(meta.document_id, meta.id);
    if (
      d.institution_id !== institution ||
      !d.active ||
      !d.registered ||
      d.sha256 !== meta.sha256 ||
      d.revision !== meta.revision
    )
      throw new ApiError(409);
  }
  async function load() {
    const ticket = ++loadId.current;
    let scopeChecked = false;
    setLoading(true);
    setError("");
    clear();
    try {
      await current();
      scopeChecked = true;
      const v = await client.candidates(scope.current.signal);
      if (!alive.current || ticket !== loadId.current) return;
      setCandidates(v.candidates);
      setGeneration(v.generation_id);
      setChosen(v.candidates[0]?.id ?? "");
      setEmpty(v.candidates.length === 0);
    } catch (e) {
      if (alive.current && ticket === loadId.current) {
        clear();
        if (e instanceof ApiError && e.status === 404 && scopeChecked) {
          setEmpty(true);
          setError("");
        } else setError(message(e));
      }
    } finally {
      if (alive.current && ticket === loadId.current) setLoading(false);
    }
  }
  useEffect(() => {
    alive.current = true;
    scope.current = new AbortController();
    void load();
    const timer = setInterval(() => {
      void current().catch((e) => {
        if (alive.current) {
          ++loadId.current;
          clear();
          setJob(null);
          setError(message(e));
        }
      });
    }, 5000);
    return () => {
      alive.current = false;
      ++loadId.current;
      scope.current.abort();
      clearInterval(timer);
    };
  }, [client]);
  useEffect(() => {
    if (!chosen || !generation) return;
    const c = new AbortController();
    setCandidate(null);
    setIssues([]);
    setForms([]);
    setStepId("");
    setError("");
    void (async () => {
      try {
        const [detail, review, links] = await Promise.all([
          client.detail(chosen, c.signal),
          client.issues(chosen, c.signal),
          client.forms(chosen, c.signal),
        ]);
        if (c.signal.aborted) return;
        if (
          [detail, review, links].some(
            (v) => v.generation_id !== generation || v.job_id !== detail.job_id,
          )
        )
          throw new ApiError(409);
        if (
          links.form_links.some(
            (f) =>
              f.workflow_id !== chosen ||
              f.step_ids.some(
                (id) => !detail.candidates[0].steps.some((s) => s.id === id),
              ),
          )
        )
          throw new ApiError(409);
        setCandidate(detail.candidates[0]);
        setIssues(review.issues);
        setForms(links.form_links);
        setStepId(detail.candidates[0].steps[0]?.id ?? "");
      } catch (e) {
        if (!c.signal.aborted) {
          clear();
          setError(message(e));
        }
      }
    })();
    return () => c.abort();
  }, [chosen, generation, client]);
  useEffect(() => {
    if (!job || !["queued", "processing"].includes(job.state)) return;
    let closed = false;
    const c = new AbortController();
    const timer = setTimeout(() => {
      void (async () => {
        try {
          await current();
          const v = await client.status(job.id, c.signal);
          if (closed) return;
          setJob(v);
          if (v.state === "completed") void load();
        } catch (e) {
          if (!closed) {
            clear();
            setJob(null);
            setError(message(e));
          }
        }
      })();
    }, 1500);
    return () => {
      closed = true;
      c.abort();
      clearTimeout(timer);
    };
  }, [job, client]);
  async function action(kind: "enqueue" | "retry" | "cancel") {
    if (mutation.current) return;
    mutation.current = true;
    setBusy(true);
    setError("");
    try {
      await current();
      const v =
        kind === "enqueue"
          ? await client.enqueue(scope.current.signal)
          : kind === "retry"
            ? await client.retry(job!.id, scope.current.signal)
            : await client.cancel(job!.id, scope.current.signal);
      if (!alive.current) return;
      setJob(v);
      if (v.state === "completed") void load();
      else clear();
    } catch (e) {
      if (alive.current) {
        clear();
        setError(message(e));
      }
    } finally {
      mutation.current = false;
      if (alive.current) setBusy(false);
    }
  }
  const step = candidate?.steps.find((s) => s.id === stepId);
  const selectStep = (id: string) => {
    setStepId(id);
    if (matchMedia("(max-width: 900px)").matches) {
      setPane("evidence");
      setTimeout(() => selectedDetail.current?.focus(), 0);
    }
  };
  const relatedIds = new Set(
    step
      ? [
          step.id,
          candidate!.id,
          ...candidate!.conditions
            .filter((c) => c.step_ids.includes(step.id))
            .map((c) => c.id),
          ...candidate!.edges
            .filter((e) => e.source === step.id || e.target === step.id)
            .map((e) => e.id),
          ...forms
            .filter((f) => f.step_ids.includes(step.id))
            .map((f) => f.requirement_id),
        ]
      : [],
  );
  const related = step
    ? issues.filter(
        (i) =>
          !targets(i).length || targets(i).some((id) => relatedIds.has(id)),
      )
    : [];
  const ids = new Set(candidate?.steps.map((s) => s.id));
  const conditionIds = new Set(candidate?.conditions.map((c) => c.id));
  const drawn =
    candidate?.edges.filter(
      (e) =>
        ids.has(e.source) &&
        ids.has(e.target) &&
        e.source !== e.target &&
        e.condition_ids.every((id) => conditionIds.has(id)),
    ) ?? [];
  const nodes: Node<MapData>[] =
    candidate?.steps.map((s, index) => ({
      id: s.id,
      type: "step",
      position: { x: (index % 2) * 340, y: Math.floor(index / 2) * 205 },
      data: {
        step: s,
        selected: s.id === stepId,
        count: issues.filter((i) => targets(i).includes(s.id)).length,
        select: selectStep,
      },
    })) ?? [];
  const edges = drawn.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: relationLabel(e),
    type: "smoothstep",
    markerEnd: { type: MarkerType.ArrowClosed },
    style: {
      stroke: e.relation === "conditional" ? "#a16207" : "#1d4ed8",
      strokeWidth: 2,
      strokeDasharray: e.relation === "conditional" ? "6 4" : undefined,
    },
    labelStyle: { fontSize: 12, fill: "#172b4d" },
  }));
  return (
    <>
      <section className="wf-run">
        <div>
          <h2>자동 추출 후보</h2>
          <p>
            실제 AI 모델 호출 없이 오프라인 추출합니다. 이 화면에서 요청한
            작업의 상태를 확인할 수 있습니다.
          </p>
        </div>
        <div className="wf-actions">
          <Button
            variant="secondary"
            onClick={() => void load()}
            disabled={busy}
          >
            후보 새로고침
          </Button>
          <Button
            onClick={() => void action("enqueue")}
            disabled={
              busy || (!!job && ["queued", "processing"].includes(job.state))
            }
          >
            추출 작업 요청
          </Button>
        </div>
      </section>
      {job && (
        <section className="wf-job" aria-live="polite">
          <strong>{jobLabels[job.state]}</strong>
          <span>
            시도 {job.attempt}/{job.max_attempts}
          </span>
          {job.error_code && (
            <p>
              사유: {job.error_code} · {job.error_category ?? "취소"}
            </p>
          )}
          {job.state === "failed" &&
            (job.error_category === "RETRYABLE" &&
            job.attempt < job.max_attempts ? (
              <Button onClick={() => void action("retry")} disabled={busy}>
                실패 작업 재시도
              </Button>
            ) : (
              <p>
                입력·처리 상태를 확인해야 합니다. 이 작업은 재시도할 수
                없습니다.
              </p>
            ))}
          {["queued", "processing"].includes(job.state) && (
            <Button
              variant="secondary"
              onClick={() => void action("cancel")}
              disabled={busy}
            >
              작업 취소
            </Button>
          )}
        </section>
      )}
      {error && <ErrorState message={error} onRetry={() => void load()} />}{" "}
      {loading ? (
        <LoadingState message="현재 버전의 후보를 확인하고 있습니다." />
      ) : !error && empty && !candidates.length ? (
        <EmptyState
          title="조회 가능한 업무 후보가 없습니다"
          description="아직 완료된 세대가 없거나 추출 결과가 비어 있습니다. 작업 요청으로 기존 작업 상태를 확인하거나 새 추출을 요청할 수 있습니다."
        />
      ) : null}
      {candidates.length > 0 && (
        <>
          <section className="wf-candidate-bar">
            <label>
              업무 후보
              <select
                aria-label="업무 후보"
                value={chosen}
                onChange={(e) => setChosen(e.target.value)}
              >
                {candidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title.text}
                  </option>
                ))}
              </select>
            </label>
            <span>
              <strong>{candidate?.steps.length ?? 0}</strong> 단계 후보
            </span>
            <span>
              <strong>{issues.length}</strong> 검토 항목
            </span>
            <StatusBadge tone="warning">의미 검토 미완료</StatusBadge>
          </section>
          {!candidate ? (
            <LoadingState message="후보 상세와 검토 항목을 불러오고 있습니다." />
          ) : (
            <>
              <div
                className="wf-mobile-tabs"
                role="tablist"
                aria-label="검토 화면"
                onKeyDown={(e) => {
                  if (
                    ["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)
                  ) {
                    e.preventDefault();
                    const value =
                      e.key === "Home"
                        ? "map"
                        : e.key === "End"
                          ? "evidence"
                          : pane === "map"
                            ? "evidence"
                            : "map";
                    setPane(value);
                    document.getElementById("wf-tab-" + value)?.focus();
                  }
                }}
              >
                <button
                  id="wf-tab-map"
                  role="tab"
                  tabIndex={pane === "map" ? 0 : -1}
                  aria-selected={pane === "map"}
                  aria-controls="wf-map-pane"
                  onClick={() => setPane("map")}
                >
                  지도·단계
                </button>
                <button
                  id="wf-tab-evidence"
                  role="tab"
                  tabIndex={pane === "evidence" ? 0 : -1}
                  aria-selected={pane === "evidence"}
                  aria-controls="wf-evidence-pane"
                  onClick={() => setPane("evidence")}
                >
                  원문 근거
                </button>
              </div>
              <div className="wf-review-grid" data-pane={pane}>
                <section
                  id="wf-map-pane"
                  className="wf-map-pane"
                  aria-label="업무지도와 단계 목록"
                >
                  <div className="wf-panel-heading">
                    <div>
                      <h2>{candidate.title.text}</h2>
                      <p>
                        배치는 탐색용입니다. 실제 업무 순서를 결정하지 않습니다.
                      </p>
                    </div>
                    <div className="wf-view-switch">
                      <Button
                        variant="secondary"
                        aria-pressed={mode === "map"}
                        onClick={() => setMode("map")}
                      >
                        지도
                      </Button>
                      <Button
                        variant="secondary"
                        aria-pressed={mode === "list"}
                        onClick={() => setMode("list")}
                      >
                        단계 목록
                      </Button>
                    </div>
                  </div>
                  {mode === "map" && (
                    <div className="wf-canvas" aria-label="단계 후보 지도">
                      <ReactFlow
                        key={candidate.id}
                        nodes={nodes}
                        edges={edges}
                        nodeTypes={nodeTypes}
                        nodesDraggable={false}
                        nodesConnectable={false}
                        nodesFocusable={false}
                        edgesFocusable={false}
                        fitView
                        minZoom={0.15}
                        maxZoom={2}
                      >
                        <Background />
                        <MapControls />
                        <MiniMap
                          style={{ width: 110, height: 65 }}
                          nodeColor="#dbeafe"
                          nodeStrokeColor="#64748b"
                          maskColor="#172b4d15"
                          pannable
                          zoomable
                          ariaLabel="지도 탐색 축소판"
                        />
                      </ReactFlow>
                    </div>
                  )}
                  <p className="wf-legend">
                    실선: 선후·필요 관계 후보 · 점선: 조건 분기·복귀 후보
                  </p>
                  <details open={mode === "list"}>
                    <summary>
                      키보드로 탐색하는 단계 목록 ({candidate.steps.length})
                    </summary>
                    <ul className="wf-step-list">
                      {candidate.steps.map((s) => (
                        <li key={s.id}>
                          <button
                            aria-pressed={stepId === s.id}
                            onClick={() => selectStep(s.id)}
                          >
                            {s.label.text}
                            <span>근거 확인 →</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </details>
                  <details className="wf-relationships">
                    <summary>
                      조건·분기·반복 및 관계 목록 ({candidate.edges.length})
                    </summary>
                    {candidate.edges.length === 0 ? (
                      <p>
                        명시적으로 연결된 관계가 없습니다. 순서를 임의로
                        연결하지 않았습니다.
                      </p>
                    ) : (
                      candidate.edges.map((e) => (
                        <article key={e.id}>
                          <strong>{relationLabel(e)}</strong>
                          {!drawn.includes(e) && (
                            <StatusBadge tone="warning">
                              지도 미표시 관계
                            </StatusBadge>
                          )}
                          <p>
                            {candidate.steps.find((s) => s.id === e.source)
                              ?.label.text ?? e.source}{" "}
                            →{" "}
                            {candidate.steps.find((s) => s.id === e.target)
                              ?.label.text ?? e.target}
                          </p>
                          <blockquote>{e.explanation.text}</blockquote>
                          {e.condition_ids.map((id) => (
                            <p key={id}>
                              조건:{" "}
                              {candidate.conditions.find((c) => c.id === id)
                                ?.statement.text ?? "연결된 조건 확인 필요"}
                            </p>
                          ))}
                          <Button
                            variant="secondary"
                            onClick={() => selectStep(e.source)}
                            disabled={!ids.has(e.source)}
                          >
                            출발 단계 근거
                          </Button>
                        </article>
                      ))
                    )}
                  </details>
                  <details>
                    <summary>전체 검토 항목 ({issues.length})</summary>
                    <IssueList issues={issues} />
                  </details>
                </section>
                <section
                  id="wf-evidence-pane"
                  className="wf-evidence-pane"
                  aria-label="원문 근거 검토"
                >
                  <h2 ref={selectedDetail} tabIndex={-1}>
                    원문 근거 확인
                  </h2>
                  {step && (
                    <EvidencePanel
                      key={candidate.id + step.id}
                      meta={meta}
                      client={client}
                      generation={generation}
                      candidate={candidate}
                      step={step}
                      issues={related}
                      forms={forms.filter((f) => f.step_ids.includes(step.id))}
                      onInvalid={(e) => {
                        clear();
                        setError(message(e));
                      }}
                    />
                  )}
                </section>
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
const issueLabels: Record<string, string> = {
  EXTRACTION_REVIEW: "추출 내용 검토",
  ORPHAN_NODE: "단계 연결 확인",
  UNCLEAR_ORDER: "순서 근거 확인",
  UNSUPPORTED_CYCLE: "반복 관계 근거 확인",
  INVALID_REFERENCE: "연결 참조 확인",
  LEXICAL_MATCH_ONLY: "서식 사용 관계 미확정",
  NO_REGISTERED_MATCH: "등록 서식 없음",
  AMBIGUOUS_FORM: "서식 후보 중복",
  SOURCE_REVIEW_REQUIRED: "원문 검토 필요",
  MENTION_NOT_OBLIGATION: "필수 여부 검토",
  CONDITIONAL_MENTION: "적용 조건 검토",
  POSSIBLE_CONFLICT: "상충 가능성 검토",
  POSSIBLE_CONTEXT_MISMATCH: "인용 문맥 검토",
  DOCUMENT_INSTRUCTION: "문서 내 지시문 검토",
  PARTIAL_INPUT: "일부 입력 미처리",
};
function IssueList({ issues }: { issues: Issue[] }) {
  return issues.length ? (
    <ul className="wf-issue-list">
      {issues.map((i, n) => (
        <li key={n}>
          <StatusBadge
            tone={
              i.severity === "ERROR"
                ? "error"
                : i.severity === "WARNING"
                  ? "warning"
                  : "info"
            }
          >
            {i.auto_block ? "자동 사용 차단" : "검토 안내"}
          </StatusBadge>
          <strong>{issueLabels[i.code] ?? "추출·근거 검토"}</strong>
          <p>{i.reason}</p>
          <details className="wf-issue-code">
            <summary>참조 코드</summary>
            <code>{i.code}</code>
          </details>
        </li>
      ))}
    </ul>
  ) : (
    <p className="wf-muted">
      이 대상에 연결된 검토 이슈가 없습니다. 의미 검증 완료를 뜻하지 않습니다.
    </p>
  );
}
function EvidencePanel({
  meta,
  client,
  generation,
  candidate,
  step,
  issues,
  forms,
  onInvalid,
}: {
  meta: Metadata;
  client: ReturnType<typeof createWorkflowClient>;
  generation: string;
  candidate: Candidate;
  step: Step;
  issues: Issue[];
  forms: FormLink[];
  onInvalid: (e: unknown) => void;
}) {
  const [refs, setRefs] = useState<EvidenceRef[]>([]),
    [resolved, setResolved] = useState<Resolved | null>(null),
    [index, setIndex] = useState(0),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [pdf, setPdf] = useState(""),
    [pdfBusy, setPdfBusy] = useState(false);
  const panelAlive = useRef(true),
    pdfRequest = useRef(false);
  useEffect(() => {
    panelAlive.current = true;
    return () => {
      panelAlive.current = false;
    };
  }, []);
  const claims = [
    step.label,
    ...step.actions,
    ...step.obligations,
    ...(step.deadline ? [step.deadline] : []),
  ];
  const citations: Citation[] = [
    ...new Map(
      claims
        .flatMap((a) => a.evidence)
        .map((c) => [`${c.chunk_id}:${c.block_id}:${c.start}:${c.end}`, c]),
    ).values(),
  ];
  useEffect(() => {
    const c = new AbortController();
    setLoading(true);
    void client
      .evidence(candidate.id, c.signal)
      .then((v) => {
        if (c.signal.aborted) return;
        if (v.generation_id !== generation) throw new ApiError(409);
        if (
          citations.some(
            (x) => !v.evidence_refs.some((r) => r.chunk_id === x.chunk_id),
          )
        )
          throw new ApiError(422);
        setRefs(v.evidence_refs);
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setError(message(e));
          onInvalid(e);
        }
      });
    return () => c.abort();
  }, [client, candidate.id, generation]);
  const citation = citations[index];
  const ref = refs.find((r) => r.chunk_id === citation?.chunk_id);
  useEffect(() => {
    if (!ref) return;
    const c = new AbortController();
    setLoading(true);
    setResolved(null);
    setError("");
    void client
      .resolve(ref, c.signal)
      .then((v) => {
        if (c.signal.aborted) return;
        const block = v.source_blocks.find(
          (b) => b.block_id === citation.block_id,
        );
        if (
          !block ||
          Array.from(block.text)
            .slice(citation.start, citation.end)
            .join("") !== citation.quote
        )
          throw new ApiError(422);
        setResolved(v);
      })
      .catch((e) => {
        if (!c.signal.aborted) {
          setError(message(e));
          onInvalid(e);
        }
      })
      .finally(() => {
        if (!c.signal.aborted) setLoading(false);
      });
    return () => c.abort();
  }, [client, ref, index]);
  useEffect(
    () => () => {
      if (pdf) URL.revokeObjectURL(pdf);
    },
    [pdf],
  );
  const block = resolved?.source_blocks.find(
    (b) => b.block_id === citation?.block_id,
  );
  const anchor = block?.source_anchor;
  async function original() {
    if (pdfRequest.current) return;
    pdfRequest.current = true;
    setPdfBusy(true);
    try {
      const blob = await documentsClient.original(meta.document_id, meta.id);
      if (panelAlive.current) setPdf(URL.createObjectURL(blob));
    } catch (e) {
      if (panelAlive.current) setError(message(e));
    } finally {
      pdfRequest.current = false;
      if (panelAlive.current) setPdfBusy(false);
    }
  }
  return (
    <>
      <div className="wf-evidence-meta">
        <StatusBadge tone="info">
          원문 · {meta.format.toUpperCase()}
        </StatusBadge>
        <strong>{meta.original_name}</strong>
        <span>v{meta.number} · 현재 활성 문서</span>
      </div>
      <h3>추출 주장</h3>
      <ul className="wf-claims">
        {[...new Set(claims.map((a) => a.text))].map((t, i) => (
          <li key={i}>{t}</li>
        ))}
      </ul>
      {step.deadline === null && (
        <p className="wf-muted">
          기한은 미확정(null)입니다. 기한이 없다는 뜻이 아닙니다.
        </p>
      )}
      <div className="wf-evidence-picker">
        {citations.map((c, i) => (
          <button
            key={i}
            aria-pressed={index === i}
            onClick={() => {
              setIndex(i);
              setPdf("");
            }}
          >
            원문 근거 {i + 1}
            <span className="sr-only"> {c.block_id}</span>
          </button>
        ))}
      </div>
      {loading ? (
        <LoadingState message="EvidenceRef를 원본에서 다시 확인하고 있습니다." />
      ) : error ? (
        <ErrorState message={error} />
      ) : (
        resolved && (
          <>
            <StatusBadge tone="info">EvidenceRef 구조·출처 확인</StatusBadge>
            <p className="wf-muted">의미 정확성은 NOT_VERIFIED입니다.</p>
            <h3>근거 원문 텍스트</h3>
            <blockquote className="wf-original-quote">
              {citation.quote}
            </blockquote>
            <details>
              <summary>인용 주변 구조화 원문</summary>
              <p className="wf-context">{block?.text}</p>
            </details>
            {anchor && (
              <dl className="wf-anchor">
                <dt>출처 유형</dt>
                <dd>
                  {block?.block_type} · {citation.block_id}
                </dd>
                {anchor.kind === "pdf" ? (
                  <>
                    <dt>PDF 위치</dt>
                    <dd>
                      페이지 {anchor.page} · 영역 {anchor.bbox?.join(", ")}
                    </dd>
                  </>
                ) : (
                  <>
                    <dt>HWPX 구조 위치</dt>
                    <dd>
                      {anchor.part}
                      <br />
                      XML 경로 [{anchor.xml_path?.join(", ")}]<br />
                      {anchor.tag}
                    </dd>
                  </>
                )}
              </dl>
            )}
            {anchor?.kind === "hwpx" ? (
              <p className="wf-limitation">
                HWPX 시각적 페이지와 한컴 읽기 순서는 검증되지 않았습니다.
                구조화 텍스트와 XML 앵커만 표시합니다.
              </p>
            ) : (
              <>
                <Button
                  variant="secondary"
                  onClick={() => void original()}
                  disabled={pdfBusy}
                >
                  {pdfBusy ? "PDF 원본 준비 중…" : "PDF 원본 준비"}
                </Button>
                {pdf && (
                  <a
                    className="text-link"
                    href={pdf + `#page=${anchor?.page ?? 1}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    PDF 원본 열기 · {anchor?.page}페이지 힌트
                  </a>
                )}
                <p className="wf-muted">
                  원본 파일을 브라우저 PDF 뷰어로 엽니다. 페이지 이동은 뷰어
                  지원에 따릅니다.
                </p>
              </>
            )}
          </>
        )
      )}
      <section className="wf-subsection">
        <h3>연결된 조건</h3>
        {candidate.conditions
          .filter((c) => c.step_ids.includes(step.id))
          .map((c) => (
            <p key={c.id}>{c.statement.text}</p>
          ))}
        {!candidate.conditions.some((c) => c.step_ids.includes(step.id)) && (
          <p className="wf-muted">연결된 명시 조건이 없습니다.</p>
        )}
      </section>
      <section className="wf-subsection">
        <h3>검토 항목 ({issues.length})</h3>
        <IssueList issues={issues} />
      </section>
      <section className="wf-subsection">
        <h3>서식 관계 후보 ({forms.length})</h3>
        {forms.length ? (
          forms.map((f) => (
            <article className="wf-form" key={f.requirement_id}>
              <strong>{f.form_name.text}</strong>
              <StatusBadge tone="warning">
                {formLabels[f.match_status]}
              </StatusBadge>
              <p>사용 목적 원문: {f.purpose.text}</p>
              <ul>
                {f.candidates.map((c) => (
                  <li key={c.document_id + c.version_id}>
                    {c.metadata.title} · {c.original_name}
                    <small>파일 존재 확인 · 업무 사용 필요성 미검증</small>
                  </li>
                ))}
              </ul>
              <p className="wf-muted">
                선택·필수 여부 미확정 · 관리자 승인 요청 없음
              </p>
            </article>
          ))
        ) : (
          <p className="wf-muted">이 단계에 연결된 서식 언급이 없습니다.</p>
        )}
      </section>
    </>
  );
}
