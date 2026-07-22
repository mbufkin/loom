// Thin fetch wrappers around the local API. Everything is same-origin in dev via
// the Vite proxy (/api -> :8770), so no base URL juggling.
import type {
  ArtifactRung,
  ConfigSummary,
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

async function getJSON<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return (await res.json()) as T;
}

export const api = {
  projects: () => getJSON<Project[]>("/api/projects"),

  outputs: (id: string) =>
    getJSON<OutputsTree>(`/api/projects/${id}/outputs`),

  stats: (id: string) => getJSON<Stats>(`/api/projects/${id}/stats`),

  config: () => getJSON<ConfigSummary>("/api/config"),

  // Absolute URL so <a href> / <embed src> for PDFs work directly.
  fileUrl: (id: string, path: string) =>
    `/api/projects/${id}/file?path=${encodeURIComponent(path)}`,

  async fileText(id: string, path: string): Promise<string> {
    const res = await fetch(api.fileUrl(id, path));
    if (!res.ok) throw new Error(`${res.status} for ${path}`);
    return res.text();
  },

  // Best-effort: UNIT-RUNG.json may not exist for every project.
  async unitRung(id: string): Promise<UnitRung | null> {
    try {
      const txt = await api.fileText(id, "layer_unit/UNIT-RUNG.json");
      return JSON.parse(txt) as UnitRung;
    } catch {
      return null;
    }
  },

  // Best-effort: LESSON-QUALITY-FEEDBACK.json only exists once the feedback
  // report has been generated for a project.
  async lessonFeedback(id: string): Promise<LessonFeedback | null> {
    try {
      const txt = await api.fileText(id, "output/LESSON-QUALITY-FEEDBACK.json");
      return JSON.parse(txt) as LessonFeedback;
    } catch {
      return null;
    }
  },

  // Best-effort: ARTIFACT-RUNG.json only exists once the artifact rung (Paths B/C)
  // has run for a project.
  async artifactRung(id: string): Promise<ArtifactRung | null> {
    try {
      const txt = await api.fileText(id, "layer_artifact/ARTIFACT-RUNG.json");
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
};
