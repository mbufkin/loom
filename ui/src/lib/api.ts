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
  DocumentList,
  E2ERunsResponse,
  GapItem,
  GapsResponse,
  GraphOverview,
  GraphRunsResponse,
  GraphUnitDetail,
  KeyStatus,
  LessonFeedback,
  ModelDiscovery,
  ModelProvider,
  OutputsTree,
  PacketType,
  PathsSummary,
  Project,
  ProposedUnits,
  RemoteModels,
  RunPreflight,
  RunStatus,
  Stats,
  StorageInfo,
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

/** An API failure carrying both what to tell the reviewer and what we saw.
 *
 * The reviewer is a curriculum director, not an engineer: showing them
 * "500 Internal Server Error for /api/projects/x/create/matrix" tells them
 * nothing they can act on. `message` is the sentence to display; `detail`
 * keeps the status, URL and server text for the Details disclosure and logs.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  readonly detail: string;

  constructor(opts: {
    message: string;
    status: number;
    url: string;
    detail: string;
  }) {
    super(opts.message);
    this.name = "ApiError";
    this.status = opts.status;
    this.url = opts.url;
    this.detail = opts.detail;
  }
}

/** Split any thrown value into a sentence to show and the raw text to hide.
 *
 * Use this at every catch site that renders something: it keeps the technical
 * string available for a Details disclosure without ever putting a status code
 * or a URL in front of the reviewer.
 */
export function describeError(e: unknown): { message: string; detail: string } {
  if (e instanceof ApiError) return { message: e.message, detail: e.detail };
  return {
    message: "Something went wrong. The details below may help.",
    detail: String(e),
  };
}

/** Plain-language cause for an HTTP status, matching what this API means by it. */
function humanReason(status: number): string {
  switch (status) {
    case 501:
      return "That part of Loom isn’t installed on this machine.";
    case 404:
      return "That isn’t part of this audit.";
    case 403:
      return "That file sits outside the curriculum folder, so it wasn’t opened.";
    case 400:
      return "Loom couldn’t read that request.";
    default:
      return status >= 500
        ? "Something went wrong reading this audit."
        : "That request didn’t go through.";
  }
}

async function getJSON<T>(url: string): Promise<T> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch (e) {
    // Fetch only rejects on a transport failure: the API process is down or
    // the window outlived its server.
    throw new ApiError({
      message:
        "Lost contact with the local Loom service. Close the window and start it again.",
      status: 0,
      url,
      detail: `network error for ${url}: ${String(e)}`,
    });
  }
  if (!res.ok) {
    // The API reports its own failures as {"error": "..."} — prefer that text
    // as the detail, since it is far more specific than the status line.
    const serverText = await res
      .json()
      .then((b) => (b && typeof b.error === "string" ? b.error : ""))
      .catch(() => "");
    throw new ApiError({
      message: humanReason(res.status),
      status: res.status,
      url,
      detail: `${res.status} ${res.statusText} for ${url}${
        serverText ? ` — ${serverText}` : ""
      }`,
    });
  }
  const ctype = res.headers.get("content-type") || "";
  // Vite SPA fallback returns HTML when /api proxy is down or misconfigured —
  // fail loudly instead of a cryptic JSON parse error.
  if (ctype.includes("text/html")) {
    throw new ApiError({
      message:
        "The Loom service answered with a web page instead of data, so it is probably not running.",
      status: res.status,
      url,
      detail: `API returned HTML for ${url} (is ui/server.py on :8770 and Vite proxying /api?)`,
    });
  }
  return (await res.json()) as T;
}

/** POST, preferring the server's own sentence as the thing to show.
 *
 * getJSON deliberately replaces the server's text with a generic reason,
 * because most GET failures are plumbing ("the service isn't running") and the
 * server's wording would not help. The setup endpoints are the opposite: their
 * errors are written for the person reading them — "Use lowercase letters,
 * numbers and hyphens", "Loom cannot read .tiff" — and the whole point is to
 * say which of those went wrong. Dropping that in favour of "Loom couldn't
 * read that request" would leave someone with a rejected name and no idea why.
 */
async function postJSON<T>(url: string, body?: unknown): Promise<T> {
  let res: Response;
  const init: RequestInit = { method: "POST" };
  if (body !== undefined) {
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(body);
  }
  try {
    res = await fetch(url, init);
  } catch (e) {
    throw new ApiError({
      message:
        "Lost contact with the local Loom service. Close the window and start it again.",
      status: 0,
      url,
      detail: `network error for ${url}: ${String(e)}`,
    });
  }
  const payload = await res.json().catch(() => null);
  if (!res.ok) {
    const serverText =
      payload && typeof payload.error === "string" ? payload.error : "";
    throw new ApiError({
      message: serverText || humanReason(res.status),
      status: res.status,
      url,
      detail: `${res.status} ${res.statusText} for ${url}${
        serverText ? ` — ${serverText}` : ""
      }`,
    });
  }
  return payload as T;
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

  /** A–H review lenses: routing, findings status, and per-step presence rollups. */
  paths: (id: string, e2eRun?: string) =>
    getJSON<PathsSummary>(withE2e(`/api/projects/${id}/paths`, e2eRun)),

  config: () => getJSON<ConfigSummary>("/api/config"),

  /** Which build of the interface this server is serving. See useFreshBundle. */
  version: () => getJSON<{ bundle: string | null }>("/api/version"),

  /** Can this machine start an audit? Asked before offering the button. */
  canRun: () => getJSON<RunPreflight>("/api/can-run"),

  /** Where curricula, settings and logs are kept on this machine. */
  storage: () => getJSON<StorageInfo>("/api/storage"),

  /**
   * Look for model servers running on this computer.
   *
   * Loopback only — see the server-side note. Takes a second or two, since it
   * has to wait out the ports where nothing is listening.
   */
  discoverModels: () => getJSON<ModelDiscovery>("/api/models/discover"),

  /** Hosted services and whether each already has a key stored. */
  providers: () =>
    getJSON<{ providers: ModelProvider[] }>("/api/models/providers"),

  /** List a hosted service's models, using the key held server-side. */
  remoteModels: (provider: string) =>
    getJSON<RemoteModels>(
      `/api/models/remote?provider=${encodeURIComponent(provider)}`,
    ),

  /** The same listing, for an endpoint Loom does not ship a provider entry for. */
  remoteModelsByUrl: (url: string) =>
    getJSON<RemoteModels>(`/api/models/remote?url=${encodeURIComponent(url)}`),

  /** Whether a key is stored for an endpoint. Presence only, never the key. */
  keyStatus: (url: string) =>
    getJSON<KeyStatus>(`/api/models/key?url=${encodeURIComponent(url)}`),

  /**
   * Save or clear an API key for an endpoint.
   *
   * The key travels to the local server once and is written to the OS
   * credential store. It is never read back — responses report only whether
   * a key is present, so it cannot end up in the page, in devtools, or in a
   * screenshot.
   */
  async saveKey(
    url: string,
    key: string | null,
  ): Promise<KeyStatus & { ok: boolean; message?: string; error?: string }> {
    const res = await fetch("/api/models/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(key === null ? { url, clear: true } : { url, key }),
    });
    if (!res.ok) throw new Error(`key save failed: ${res.status}`);
    return res.json();
  },

  /** Point config.yaml at a model. Returns {ok} or {ok:false, error}. */
  async selectModel(
    url: string,
    model: string,
  ): Promise<{ ok: boolean; error?: string }> {
    const res = await fetch("/api/models/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, model }),
    });
    if (!res.ok) throw new Error(`select model failed: ${res.status}`);
    return res.json();
  },

  /**
   * Install the Python dependencies on this machine.
   *
   * Takes no arguments by design — the server runs a fixed
   * `pip install -r requirements.txt` and accepts no package name from the
   * client. Can take a couple of minutes on a cold cache, so callers should
   * show progress rather than assume it returns quickly.
   */
  async installDeps(): Promise<{ ok: boolean; output: string }> {
    const res = await fetch("/api/install-deps", { method: "POST" });
    if (!res.ok) throw new Error(`install failed: ${res.status}`);
    return res.json();
  },

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

  // --- Setting up a curriculum: create, add documents, organise ------------

  /** Make a new curriculum folder with its sources/ subfolder. */
  createProject: (id: string, title = "") =>
    postJSON<{ ok: boolean; id: string; title: string; path: string }>(
      "/api/projects",
      { id, title }
    ),

  /** What is in this curriculum's sources folder, and whether organise is stale. */
  documents: (id: string) =>
    getJSON<DocumentList>(`/api/projects/${id}/documents`),

  /**
   * Upload one document into sources/.
   *
   * One request per file with the bytes as the raw body and the name in the
   * query string. Not a multipart form: the server side of that is a parser
   * with a security boundary in front of it, and the stdlib's own (`cgi`) is
   * gone in Python 3.13. This shape also gives per-file progress and per-file
   * errors, which matters when someone drops twenty files and two are the
   * wrong type — those two get named, the other eighteen still land.
   */
  async addDocument(
    id: string,
    file: File
  ): Promise<{ name: string; bytes: number; renamed: boolean }> {
    const url = `/api/projects/${id}/documents?name=${encodeURIComponent(
      file.name
    )}`;
    let res: Response;
    try {
      res = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: file,
      });
    } catch (e) {
      throw new ApiError({
        message: `${file.name} could not be sent to Loom.`,
        status: 0,
        url,
        detail: `network error for ${url}: ${String(e)}`,
      });
    }
    const payload = await res.json().catch(() => null);
    if (!res.ok) {
      const serverText =
        payload && typeof payload.error === "string" ? payload.error : "";
      throw new ApiError({
        message: serverText || `${file.name} was not accepted.`,
        status: res.status,
        url,
        detail: `${res.status} ${res.statusText} for ${url}${
          serverText ? ` — ${serverText}` : ""
        }`,
      });
    }
    return payload;
  },

  removeDocument: (id: string, name: string) =>
    postJSON<{ ok: boolean; removed: string }>(
      `/api/projects/${id}/documents/delete`,
      { name }
    ),

  /** Read every document and group them into units. Returns a runId to poll. */
  async organise(id: string): Promise<string> {
    const out = await postJSON<{ runId: string }>(
      `/api/projects/${id}/organise`,
      {}
    );
    return out.runId;
  },

  /** The units organise proposed, for review before committing to an audit. */
  units: (id: string) => getJSON<ProposedUnits>(`/api/projects/${id}/units`),

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
