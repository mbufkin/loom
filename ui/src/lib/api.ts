// Thin fetch wrappers around the local API. Everything is same-origin in dev via
// the Vite proxy (/api -> :8770), so no base URL juggling.
import type {
  ArtifactRung,
  ConfigSummary,
  CreateMatrixResponse,
  CreateRoleTreeResponse,
  CreateStatus,
  CreateTreeResponse,
  CreateUnitTreeResponse,
  CreateUnitsResponse,
  CurriculumReview,
  E2ERunsResponse,
  GapItem,
  GapsResponse,
  GraphOverview,
  GraphRunsResponse,
  GraphUnitDetail,
  LessonFeedback,
  OutputsTree,
  PacketType,
  Project,
  RunStatus,
  Stats,
  UnitRung,
} from "../types";

export interface PacketTypeRegistry {
  default: string | null;
  types: PacketType[];
  error?: string;
}

/** Append ?e2e_run= when reviewing a full-pipeline snapshot workspace. */
function withE2e(url: string, e2eRun?: string): string {
  if (!e2eRun) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}e2e_run=${encodeURIComponent(e2eRun)}`;
}

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  const ctype = res.headers.get("content-type") || "";
  // Vite SPA fallback returns HTML when /api proxy is down or misconfigured —
  // fail loudly instead of a cryptic JSON parse error.
  if (ctype.includes("text/html")) {
    throw new Error(
      `API returned HTML for ${url} (is ui/server.py on :8770 and Vite proxying /api?)`
    );
  }
  return (await res.json()) as T;
}

export const api = {
  projects: () => getJSON<Project[]>("/api/projects"),

  /** Full-pipeline snapshots under e2e/runs/* (Dashboard, layers, teachers…). */
  e2eRuns: (id: string) =>
    getJSON<E2ERunsResponse>(`/api/projects/${id}/e2e/runs`),

  outputs: (id: string, e2eRun?: string) =>
    getJSON<OutputsTree>(withE2e(`/api/projects/${id}/outputs`, e2eRun)),

  stats: (id: string, e2eRun?: string) =>
    getJSON<Stats>(withE2e(`/api/projects/${id}/stats`, e2eRun)),

  config: () => getJSON<ConfigSummary>("/api/config"),

  // Absolute URL so <a href> / <embed src> for PDFs work directly.
  fileUrl: (id: string, path: string, e2eRun?: string) =>
    withE2e(
      `/api/projects/${id}/file?path=${encodeURIComponent(path)}`,
      e2eRun
    ),

  async fileText(
    id: string,
    path: string,
    e2eRun?: string
  ): Promise<string> {
    const res = await fetch(api.fileUrl(id, path, e2eRun));
    if (!res.ok) throw new Error(`${res.status} for ${path}`);
    return res.text();
  },

  // Best-effort: UNIT-RUNG.json may not exist for every project.
  async unitRung(id: string, e2eRun?: string): Promise<UnitRung | null> {
    try {
      const txt = await api.fileText(
        id,
        "layer_unit/UNIT-RUNG.json",
        e2eRun
      );
      return JSON.parse(txt) as UnitRung;
    } catch {
      return null;
    }
  },

  // Best-effort quality / curriculum-review plates.
  // When an E2E workspace is selected, read plates from that tree.
  // Otherwise prefer e2e/runs/<graphRunId>/… so graph A/B still tracks quality,
  // then fall back to the curriculum-root plate.
  async lessonFeedback(
    id: string,
    graphRunId?: string,
    e2eRun?: string
  ): Promise<LessonFeedback | null> {
    const paths = e2eRun
      ? ["output/LESSON-QUALITY-FEEDBACK.json"]
      : [
          ...(graphRunId
            ? [`e2e/runs/${graphRunId}/output/LESSON-QUALITY-FEEDBACK.json`]
            : []),
          "output/LESSON-QUALITY-FEEDBACK.json",
        ];
    for (const path of paths) {
      try {
        const txt = await api.fileText(id, path, e2eRun);
        return JSON.parse(txt) as LessonFeedback;
      } catch {
        /* try next */
      }
    }
    return null;
  },

  async lessonReview(
    id: string,
    graphRunId?: string,
    e2eRun?: string
  ): Promise<CurriculumReview | null> {
    const paths = e2eRun
      ? ["output/LESSON-CURRICULUM-REVIEW.json"]
      : [
          ...(graphRunId
            ? [`e2e/runs/${graphRunId}/output/LESSON-CURRICULUM-REVIEW.json`]
            : []),
          "output/LESSON-CURRICULUM-REVIEW.json",
        ];
    for (const path of paths) {
      try {
        const txt = await api.fileText(id, path, e2eRun);
        return JSON.parse(txt) as CurriculumReview;
      } catch {
        /* try next */
      }
    }
    return null;
  },

  // Best-effort: ARTIFACT-RUNG.json only exists once the artifact rung (Paths B/C)
  // has run for a project.
  async artifactRung(
    id: string,
    e2eRun?: string
  ): Promise<ArtifactRung | null> {
    try {
      const txt = await api.fileText(
        id,
        "layer_artifact/ARTIFACT-RUNG.json",
        e2eRun
      );
      return JSON.parse(txt) as ArtifactRung;
    } catch {
      return null;
    }
  },

  async startRun(id: string, flags: string[] = []): Promise<string> {
    const res = await fetch(`/api/projects/${id}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ flags }),
    });
    if (!res.ok) throw new Error(`run failed: ${res.status}`);
    return (await res.json()).runId as string;
  },

  runStatus: (runId: string) => getJSON<RunStatus>(`/api/runs/${runId}`),

  // Declarable packet-type registry (drives the start-point selector).
  packetTypes: () => getJSON<PacketTypeRegistry>("/api/packet-types"),

  // DECLARE a project's packet type. Persists to the manifest and regenerates the
  // unit rung server-side; caller should reload the project to pick up new bands.
  async setPacketType(
    id: string,
    packet_type: string
  ): Promise<{ packet_type: string; regenerated: boolean; detail: string }> {
    const res = await fetch(`/api/projects/${id}/packet-type`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ packet_type }),
    });
    if (!res.ok) throw new Error(`set packet type failed: ${res.status}`);
    return res.json();
  },

  createStatus: () => getJSON<CreateStatus>("/api/create/status"),

  createMatrix: (id: string) =>
    getJSON<CreateMatrixResponse>(`/api/projects/${id}/create/matrix`),

  createTree: (id: string) =>
    getJSON<CreateTreeResponse>(`/api/projects/${id}/create/tree`),

  createRoleTree: (id: string, role: string) =>
    getJSON<CreateRoleTreeResponse>(
      `/api/projects/${id}/create/tree/${encodeURIComponent(role)}`
    ),

  createUnits: (id: string) =>
    getJSON<CreateUnitsResponse>(`/api/projects/${id}/create/units`),

  createUnitTree: (id: string, unitId: string) =>
    getJSON<CreateUnitTreeResponse>(
      `/api/projects/${id}/create/units/${encodeURIComponent(unitId)}`
    ),

  gaps: (id: string) => getJSON<GapsResponse>(`/api/projects/${id}/gaps`),

  async setGapDecision(
    id: string,
    gapId: string,
    decision: GapItem["decision"],
    note = ""
  ): Promise<{ gap_id: string; decision: GapItem["decision"]; note: string; updated_at: string }> {
    const res = await fetch(`/api/projects/${id}/gaps/${gapId}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision, note }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `decision failed: ${res.status}`);
    }
    return res.json();
  },

  async makeBrief(
    id: string,
    gapId: string
  ): Promise<{ gap_id: string; path: string; text: string }> {
    const res = await fetch(`/api/projects/${id}/gaps/${gapId}/brief`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ generate: true }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `brief failed: ${res.status}`);
    }
    return res.json();
  },

  async getBrief(id: string, gapId: string): Promise<{ text: string }> {
    return getJSON(`/api/projects/${id}/gaps/${gapId}/brief`);
  },

  async makeDraft(
    id: string,
    gapId: string,
    context = ""
  ): Promise<{
    gap_id: string;
    path: string;
    model: string;
    run_id: string | null;
    text: string;
    key_source: string;
    chars: number;
  }> {
    const res = await fetch(`/api/projects/${id}/gaps/${gapId}/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ context, generate: true }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `draft failed: ${res.status}`);
    }
    return res.json();
  },

  async getDraft(id: string, gapId: string): Promise<{ text: string }> {
    return getJSON(`/api/projects/${id}/gaps/${gapId}/draft`);
  },

  async saveBrief(id: string, gapId: string, text: string): Promise<void> {
    const res = await fetch(`/api/projects/${id}/gaps/${gapId}/brief`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `save brief failed: ${res.status}`);
    }
  },

  async saveDraft(id: string, gapId: string, text: string): Promise<void> {
    const res = await fetch(`/api/projects/${id}/gaps/${gapId}/draft`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `save draft failed: ${res.status}`);
    }
  },

  /** Model graph runs for a curriculum (A/B trees under graph/runs/). */
  graphRuns: (id: string, e2eRun?: string) =>
    getJSON<GraphRunsResponse>(
      withE2e(`/api/projects/${id}/graph/runs`, e2eRun)
    ),

  graphOverview: (id: string, runId: string, e2eRun?: string) =>
    getJSON<GraphOverview>(
      withE2e(
        `/api/projects/${id}/graph/runs/${encodeURIComponent(runId)}/overview`,
        e2eRun
      )
    ),

  graphUnit: (
    id: string,
    runId: string,
    unitId: string,
    e2eRun?: string
  ) =>
    getJSON<GraphUnitDetail>(
      withE2e(
        `/api/projects/${id}/graph/runs/${encodeURIComponent(runId)}/units/${encodeURIComponent(unitId)}`,
        e2eRun
      )
    ),
};
