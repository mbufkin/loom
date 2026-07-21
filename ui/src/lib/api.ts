// Thin fetch wrappers around the local API. Everything is same-origin in dev via
// the Vite proxy (/api -> :8770), so no base URL juggling.
import type {
  ConfigSummary,
  LessonFeedback,
  OutputsTree,
  Project,
  RunStatus,
  Stats,
  UnitRung,
} from "../types";

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
};
