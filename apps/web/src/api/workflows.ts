import { authMemory } from "../auth/AuthContext";
import { ApiError } from "./documents";
export type Citation = {
  chunk_id: string;
  block_id: string;
  start: number;
  end: number;
  quote: string;
};
export type Assertion = { text: string; evidence: Citation[] };
export type Step = {
  id: string;
  label: Assertion;
  actions: Assertion[];
  deadline: Assertion | null;
  obligations: Assertion[];
};
export type Condition = {
  id: string;
  statement: Assertion;
  step_ids: string[];
};
export type Edge = {
  id: string;
  source: string;
  target: string;
  relation: "precedes" | "conditional" | "requires";
  condition_ids: string[];
  explanation: Assertion;
};
export type Candidate = {
  id: string;
  title: Assertion;
  steps: Step[];
  conditions: Condition[];
  edges: Edge[];
  form_requirements: {
    id: string;
    title: Assertion;
    requirement: Assertion;
    step_ids: string[];
  }[];
};
export type Issue = {
  target_ids?: string[];
  target_id?: string;
  code: string;
  severity: "ERROR" | "WARNING" | "INFO";
  reason: string;
  auto_block: boolean;
  evidence_refs: EvidenceRef[];
};
export type Anchor = {
  kind: "pdf" | "hwpx";
  page: number | null;
  bbox: number[] | null;
  part: string | null;
  xml_path: number[] | null;
  tag: string | null;
};
export type EvidenceRef = {
  organization_id: string;
  document_id: string;
  version_id: string;
  chunk_id: string;
  source_block_ids: string[];
  source_anchor: Anchor[];
  spans: {
    block_id: string;
    source_anchor: Anchor;
    start: number;
    end: number;
    quote: string;
    role: string;
    source_kind: string;
  }[];
  verification_status: "structural_only";
  semantic_verification: "NOT_VERIFIED";
};
export type FormLink = {
  workflow_id: string;
  requirement_id: string;
  step_ids: string[];
  form_name: Assertion;
  purpose: Assertion;
  condition_ids: string[];
  mention_kind: string;
  match_status: "UNLINKED" | "CANDIDATES" | "AMBIGUOUS" | "BLOCKED";
  required: null;
  selected_form_id: null;
  relationship_status: "NEEDS_REVIEW" | "BLOCKED";
  candidates: {
    institution_id: string;
    document_id: string;
    version_id: string;
    original_name: string;
    metadata: { title: string; purpose: string };
    existence: "CURRENT_REGISTERED_FILE";
    relationship_verification: "NOT_VERIFIED";
  }[];
  issues: Issue[];
  administrator_approval: "NOT_REQUESTED";
};
export type Job = {
  id: string;
  document_id: string;
  version_id: string;
  input_snapshot_id: string;
  generation: number;
  state: "queued" | "processing" | "completed" | "failed" | "cancelled";
  attempt: number;
  max_attempts: 3;
  error_category: "RETRYABLE" | "PERMANENT" | "STALE_INPUT" | null;
  error_code: string | null;
  lease_until: number | null;
  events: {
    state: string;
    attempt: number;
    error_code: string | null;
    error_category: string | null;
    created_at: number;
  }[];
  semantic_verification: "NOT_VERIFIED";
  administrator_approval: "NOT_REQUESTED";
  publishable: false;
};
export type Envelope = {
  schema_version: "workflow-query-v1";
  generation_id: string;
  job_id: string;
  semantic_verification: "NOT_VERIFIED";
  administrator_approval: "NOT_REQUESTED";
  publishable: false;
};
export type Resolved = {
  structural_valid: true;
  semantic_verification: "NOT_VERIFIED";
  content_origin: "original";
  evidence: EvidenceRef;
  source_blocks: {
    block_id: string;
    text: string;
    block_type: string;
    source_anchor: Anchor;
  }[];
};
type Obj = Record<string, unknown>;
const obj = (v: unknown): v is Obj =>
  !!v && typeof v === "object" && !Array.isArray(v);
const str = (v: unknown): v is string => typeof v === "string";
const list = (v: unknown): v is unknown[] => Array.isArray(v);
const strings = (v: unknown): v is string[] => list(v) && v.every(str);
const safe = (v: Obj) =>
  v.semantic_verification === "NOT_VERIFIED" &&
  v.administrator_approval === "NOT_REQUESTED" &&
  v.publishable === false;
const citation = (v: unknown): boolean =>
  obj(v) &&
  str(v.chunk_id) &&
  str(v.block_id) &&
  str(v.quote) &&
  Number.isInteger(v.start) &&
  Number.isInteger(v.end) &&
  Number(v.start) >= 0 &&
  Number(v.end) > Number(v.start) &&
  Number(v.end) - Number(v.start) === Array.from(v.quote).length;
const assertion = (v: unknown): boolean =>
  obj(v) &&
  str(v.text) &&
  list(v.evidence) &&
  v.evidence.length > 0 &&
  v.evidence.every(citation);
function candidate(v: unknown): boolean {
  if (
    obj(v) &&
    list(v.steps) &&
    new Set(v.steps.map((s) => (obj(s) ? s.id : null))).size !== v.steps.length
  )
    return false;
  return (
    obj(v) &&
    str(v.id) &&
    assertion(v.title) &&
    list(v.steps) &&
    v.steps.length > 0 &&
    v.steps.length <= 200 &&
    v.steps.every(
      (s) =>
        obj(s) &&
        str(s.id) &&
        assertion(s.label) &&
        list(s.actions) &&
        s.actions.length > 0 &&
        s.actions.every(assertion) &&
        "deadline" in s &&
        (s.deadline === null || assertion(s.deadline)) &&
        list(s.obligations) &&
        s.obligations.every(assertion),
    ) &&
    list(v.conditions) &&
    v.conditions.every(
      (c) =>
        obj(c) && str(c.id) && assertion(c.statement) && strings(c.step_ids),
    ) &&
    list(v.edges) &&
    v.edges.every(
      (e) =>
        obj(e) &&
        str(e.id) &&
        str(e.source) &&
        str(e.target) &&
        ["precedes", "conditional", "requires"].includes(String(e.relation)) &&
        strings(e.condition_ids) &&
        assertion(e.explanation),
    ) &&
    list(v.form_requirements) &&
    v.form_requirements.every(
      (f) =>
        obj(f) &&
        str(f.id) &&
        assertion(f.title) &&
        assertion(f.requirement) &&
        strings(f.step_ids),
    )
  );
}
function anchor(v: unknown): boolean {
  return (
    obj(v) &&
    (v.kind === "pdf"
      ? Number.isInteger(v.page) &&
        Number(v.page) > 0 &&
        list(v.bbox) &&
        v.bbox.length === 4 &&
        v.bbox.every((n) => typeof n === "number")
      : v.kind === "hwpx" &&
        str(v.part) &&
        list(v.xml_path) &&
        v.xml_path.every((n) => Number.isInteger(n) && Number(n) >= 0) &&
        str(v.tag))
  );
}
function canonical(v: unknown): string {
  return JSON.stringify(v, (_key, value) =>
    obj(value)
      ? Object.fromEntries(
          Object.entries(value).sort(([a], [b]) => a.localeCompare(b)),
        )
      : value,
  );
}
function evidence(v: unknown, i: string, d: string, ver: string): boolean {
  return (
    obj(v) &&
    v.organization_id === i &&
    v.document_id === d &&
    v.version_id === ver &&
    str(v.chunk_id) &&
    strings(v.source_block_ids) &&
    list(v.source_anchor) &&
    v.source_anchor.every(anchor) &&
    v.verification_status === "structural_only" &&
    v.semantic_verification === "NOT_VERIFIED" &&
    list(v.spans) &&
    v.spans.every(
      (s) =>
        obj(s) &&
        str(s.block_id) &&
        anchor(s.source_anchor) &&
        str(s.quote) &&
        Number.isInteger(s.start) &&
        Number.isInteger(s.end) &&
        str(s.source_kind) &&
        str(s.role),
    )
  );
}
function issue(v: unknown, i: string, d: string, ver: string): boolean {
  return (
    obj(v) &&
    str(v.code) &&
    str(v.reason) &&
    ["ERROR", "WARNING", "INFO"].includes(String(v.severity)) &&
    typeof v.auto_block === "boolean" &&
    (strings(v.target_ids) || str(v.target_id)) &&
    list(v.evidence_refs) &&
    v.evidence_refs.every((r) => evidence(r, i, d, ver))
  );
}
export function createWorkflowClient(
  institution: string,
  document: string,
  version: string,
  transport: typeof fetch = fetch,
) {
  const root = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");
  const path = `/documents/${encodeURIComponent(document)}/versions/${encodeURIComponent(version)}`;
  async function request(
    url: string,
    signal: AbortSignal,
    method = "GET",
    body?: unknown,
  ): Promise<unknown> {
    let res: Response;
    try {
      res = await transport(root + url, {
        signal,
        method,
        credentials: "same-origin",
        cache: "no-store",
        redirect: "error",
        ...(method !== "GET"
          ? {
              headers: {
                "Content-Type": "application/json",
                "X-CSRF-Token": authMemory.csrf,
              },
              body: JSON.stringify(body ?? {}),
            }
          : {}),
      });
    } catch (e) {
      if (signal.aborted) throw e;
      throw new ApiError(0);
    }
    if (!res.ok) {
      if (res.status === 401)
        window.dispatchEvent(new Event("seomuitda-session-expired"));
      throw new ApiError(res.status);
    }
    try {
      return await res.json();
    } catch {
      throw new ApiError(500, "invalid_response");
    }
  }
  function checkJob(v: unknown, expectedId?: string): Job {
    if (
      !obj(v) ||
      !safe(v) ||
      !str(v.id) ||
      (expectedId !== undefined && v.id !== expectedId) ||
      v.document_id !== document ||
      v.version_id !== version ||
      !str(v.input_snapshot_id) ||
      !Number.isInteger(v.generation) ||
      !["queued", "processing", "completed", "failed", "cancelled"].includes(
        String(v.state),
      ) ||
      !Number.isInteger(v.attempt) ||
      Number(v.attempt) < 0 ||
      Number(v.attempt) > 3 ||
      v.max_attempts !== 3 ||
      !list(v.events) ||
      !v.events.every(
        (e) =>
          obj(e) &&
          str(e.state) &&
          Number.isInteger(e.attempt) &&
          typeof e.created_at === "number",
      ) ||
      ![null, "RETRYABLE", "PERMANENT", "STALE_INPUT"].includes(
        v.error_category as string | null,
      ) ||
      !(v.error_code === null || str(v.error_code))
    )
      throw new ApiError(500, "invalid_response");
    return v as Job;
  }
  async function query<
    K extends "candidates" | "issues" | "form_links" | "evidence_refs",
  >(
    suffix: string,
    key: K,
    signal: AbortSignal,
  ): Promise<Envelope & Record<K, unknown[]>> {
    const v = await request(path + "/workflow" + suffix, signal);
    if (
      !obj(v) ||
      !safe(v) ||
      v.schema_version !== "workflow-query-v1" ||
      !str(v.generation_id) ||
      !str(v.job_id) ||
      !list(v[key])
    )
      throw new ApiError(500, "invalid_response");
    const items = v[key] as unknown[];
    const valid =
      key === "candidates"
        ? items.length <= 20 && items.every(candidate)
        : key === "issues"
          ? items.every((x) => issue(x, institution, document, version))
          : key === "evidence_refs"
            ? items.every((x) => evidence(x, institution, document, version))
            : items.every(
                (f) =>
                  obj(f) &&
                  str(f.workflow_id) &&
                  str(f.requirement_id) &&
                  strings(f.step_ids) &&
                  assertion(f.form_name) &&
                  assertion(f.purpose) &&
                  strings(f.condition_ids) &&
                  ["UNLINKED", "CANDIDATES", "AMBIGUOUS", "BLOCKED"].includes(
                    String(f.match_status),
                  ) &&
                  f.required === null &&
                  f.selected_form_id === null &&
                  f.administrator_approval === "NOT_REQUESTED" &&
                  list(f.candidates) &&
                  f.candidates.every(
                    (c) =>
                      obj(c) &&
                      c.institution_id === institution &&
                      str(c.document_id) &&
                      str(c.version_id) &&
                      str(c.original_name) &&
                      obj(c.metadata) &&
                      str(c.metadata.title) &&
                      c.relationship_verification === "NOT_VERIFIED" &&
                      c.existence === "CURRENT_REGISTERED_FILE",
                  ) &&
                  list(f.issues) &&
                  f.issues.every((x) =>
                    issue(x, institution, document, version),
                  ),
              );
    if (!valid) throw new ApiError(500, "invalid_response");
    return v as Envelope & Record<K, unknown[]>;
  }
  return {
    enqueue: async (s: AbortSignal) =>
      checkJob(await request(path + "/workflow/jobs", s, "POST", {})),
    status: async (j: string, s: AbortSignal) =>
      checkJob(
        await request(path + "/workflow/jobs/" + encodeURIComponent(j), s),
        j,
      ),
    retry: async (j: string, s: AbortSignal) =>
      checkJob(
        await request(
          path + "/workflow/jobs/" + encodeURIComponent(j) + "/retry",
          s,
          "POST",
        ),
        j,
      ),
    cancel: async (j: string, s: AbortSignal) =>
      checkJob(
        await request(
          path + "/workflow/jobs/" + encodeURIComponent(j) + "/cancel",
          s,
          "POST",
        ),
        j,
      ),
    candidates: async (s: AbortSignal) =>
      (await query("/candidates", "candidates", s)) as Envelope & {
        candidates: Candidate[];
      },
    detail: async (id: string, s: AbortSignal) => {
      const v = (await query(
        "/candidates/" + encodeURIComponent(id),
        "candidates",
        s,
      )) as Envelope & { candidates: Candidate[] };
      if (v.candidates.length !== 1 || v.candidates[0].id !== id)
        throw new ApiError(500, "invalid_response");
      return v;
    },
    issues: async (id: string, s: AbortSignal) =>
      (await query(
        "/review-issues?candidate_id=" + encodeURIComponent(id),
        "issues",
        s,
      )) as Envelope & { issues: Issue[] },
    forms: async (id: string, s: AbortSignal) =>
      (await query(
        "/form-links?candidate_id=" + encodeURIComponent(id),
        "form_links",
        s,
      )) as Envelope & { form_links: FormLink[] },
    evidence: async (id: string, s: AbortSignal) =>
      (await query(
        "/candidates/" + encodeURIComponent(id) + "/evidence",
        "evidence_refs",
        s,
      )) as Envelope & { evidence_refs: EvidenceRef[] },
    resolve: async (ref: EvidenceRef, s: AbortSignal): Promise<Resolved> => {
      if (!evidence(ref, institution, document, version))
        throw new ApiError(403);
      const v = await request(
        path +
          "/chunks/" +
          encodeURIComponent(ref.chunk_id) +
          "/evidence/resolve",
        s,
        "POST",
        ref,
      );
      if (
        !obj(v) ||
        v.structural_valid !== true ||
        v.semantic_verification !== "NOT_VERIFIED" ||
        v.content_origin !== "original" ||
        !evidence(v.evidence, institution, document, version) ||
        canonical(v.evidence) !== canonical(ref) ||
        !list(v.source_blocks) ||
        !v.source_blocks.every(
          (b) =>
            obj(b) &&
            str(b.block_id) &&
            str(b.text) &&
            b.document_id === document &&
            b.version_id === version &&
            anchor(b.source_anchor),
        )
      )
        throw new ApiError(500, "invalid_evidence");
      return v as Resolved;
    },
  };
}
