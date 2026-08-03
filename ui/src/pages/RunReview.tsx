import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { MarkdownViewer } from "../components/MarkdownViewer";
import { OutputNav, VIEW_GRAPH, VIEW_UNITS } from "../components/OutputNav";
import { ReviewSlip } from "../components/ReviewSlip";
import { UnitDetail } from "../components/UnitDetail";
import { LessonDetail } from "../components/LessonDetail";
import { ArtifactDetail } from "../components/ArtifactDetail";
import { UnitOutputRow } from "../components/UnitOutputRow";
import { PacketTypeBar } from "../components/PacketTypeBar";
import { Overview } from "../components/Overview";
import { NextSteps } from "../components/NextSteps";
import { GraphBelongingPanel } from "../components/GraphBelongingPanel";
import type {
  ArtifactRung,
  Band,
  CurriculumReview,
  E2ERunInfo,
  GraphOverview,
  GraphRunInfo,
  GraphUnitDetail,
  LessonFeedback,
  OutputsTree,
  Project,
  RunStatus,
  Stats,
  UnitRollup,
  UnitRung,
} from "../types";

const DEFAULT_PROJECT = "dallas-career-2026";
const UNITS_VIEW = VIEW_UNITS;
const GRAPH_VIEW = VIEW_GRAPH;
const UNIT_DETAIL = "__unit_detail__";
const LESSON_DETAIL = "__lesson_detail__";
const ARTIFACT_DETAIL = "__artifact_detail__";

/** Short label for the model picker (run_id when model is a local path). */
function graphRunLabel(r: GraphRunInfo): string {
  const m = (r.model || "").trim();
  if (!m) return r.run_id;
  if (m.includes("/") || m.endsWith(".gguf")) return r.run_id;
  return m;
}

/** Curriculum option text: prefer manifest title, keep tier for STATUS rows. */
function curriculumOptionLabel(p: Project): string {
  const title = (p.title || p.id).trim();
  if (p.kind === "lab") return title;
  if (p.tier && p.tier !== "Unknown") return `${title} — ${p.tier}`;
  return title;
}

function projectSortKey(p: Project): [number, string, string] {
  return [p.sort_tier ?? 9, (p.title || p.id).toLowerCase(), p.id];
}

// Prefer the real unit-rung band; otherwise derive a heat band from Layer 1 role
// fulfillment so the heatmap still renders for projects without a unit rung.
function deriveBand(r: UnitRollup): Band {
  const total = r.fulfilled + r.missing;
  if (total === 0) return "Unrated";
  const pct = r.fulfilled / total;
  if (r.mismatch > 0 || pct < 0.34) return "Weak";
  if (pct >= 0.67) return "Strong";
  return "Developing";
}

export function RunReview() {
  // Top-level view switch. "review" is the untouched console; "overview" /
  // "next" are presentation decks. Kept as a tiny local flag (no router) so the
  // existing page and all its state are undisturbed when a deck is showing.
  const [topView, setTopView] = useState<"review" | "overview" | "next">(
    "review"
  );
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>(DEFAULT_PROJECT);
  // Lab forks (lab-*) stay out of Curriculum until the reviewer opts in.
  const [showLabForks, setShowLabForks] = useState(false);
  const [outputs, setOutputs] = useState<OutputsTree | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [unitRung, setUnitRung] = useState<UnitRung | null>(null);
  const [lessonFeedback, setLessonFeedback] = useState<LessonFeedback | null>(
    null
  );
  const [artifactRung, setArtifactRung] = useState<ArtifactRung | null>(null);
  const [lessonReview, setLessonReview] = useState<CurriculumReview | null>(
    null
  );
  // Full-pipeline snapshots (e2e/runs/*). Empty e2eRunId = live project root.
  const [e2eRuns, setE2eRuns] = useState<E2ERunInfo[]>([]);
  const [e2eRunId, setE2eRunId] = useState<string>("");
  // Model graph A/B: curriculum picker + model picker drive the belonging panel.
  // When an E2E workspace is selected, graph runs are nested under that tree.
  const [graphRuns, setGraphRuns] = useState<GraphRunInfo[]>([]);
  const [graphRunId, setGraphRunId] = useState<string>("");
  const [graphOverview, setGraphOverview] = useState<GraphOverview | null>(null);
  const [graphUnitDetail, setGraphUnitDetail] =
    useState<GraphUnitDetail | null>(null);
  const [graphLoading, setGraphLoading] = useState(false);

  const [activePath, setActivePath] = useState<string | null>(null);
  const [activeType, setActiveType] = useState<string>("md");
  const [selectedUnitId, setSelectedUnitId] = useState<string | null>(null);
  const [selectedLessonId, setSelectedLessonId] = useState<string | null>(null);
  const [selectedArtifactId, setSelectedArtifactId] = useState<string | null>(
    null
  );
  const [viewerText, setViewerText] = useState<string>("");
  const [error, setError] = useState<string>("");

  const [runStatus, setRunStatus] = useState<RunStatus | null>(null);
  const pollRef = useRef<number | null>(null);

  const project = projects.find((p) => p.id === projectId) ?? {
    id: projectId,
    tier: "Unknown",
    has_output: false,
    has_stats: false,
    has_unit_rung: false,
  };

  // Curricula = STATUS.md rows. If STATUS is empty, fall back to non-lab dirs.
  const curriculumProjects = useMemo(() => {
    const fromStatus = projects.filter((p) => p.kind === "curriculum");
    const list =
      fromStatus.length > 0
        ? fromStatus
        : projects.filter((p) => p.kind !== "lab" && !p.id.startsWith("lab-"));
    return [...list].sort((a, b) => {
      const ka = projectSortKey(a);
      const kb = projectSortKey(b);
      return ka[0] - kb[0] || ka[1].localeCompare(kb[1]) || ka[2].localeCompare(kb[2]);
    });
  }, [projects]);

  const labProjects = useMemo(() => {
    return projects
      .filter((p) => p.kind === "lab" || p.id.startsWith("lab-"))
      .sort((a, b) =>
        (a.title || a.id).localeCompare(b.title || b.id, undefined, {
          sensitivity: "base",
        })
      );
  }, [projects]);

  // Model runs A–Z by display label (stable secondary key = run_id).
  const sortedGraphRuns = useMemo(() => {
    return [...graphRuns].sort((a, b) => {
      const la = graphRunLabel(a).toLowerCase();
      const lb = graphRunLabel(b).toLowerCase();
      return la.localeCompare(lb) || a.run_id.localeCompare(b.run_id);
    });
  }, [graphRuns]);

  // Load the project list once; default to Dallas when it is a real curriculum.
  useEffect(() => {
    api
      .projects()
      .then((ps) => {
        setProjects(ps);
        const curricula = ps.filter((p) => p.kind === "curriculum");
        const fallback =
          curricula.length > 0
            ? curricula
            : ps.filter((p) => p.kind !== "lab" && !p.id.startsWith("lab-"));
        if (fallback.some((p) => p.id === DEFAULT_PROJECT)) {
          setProjectId(DEFAULT_PROJECT);
        } else if (fallback[0]) {
          setProjectId(fallback[0].id);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  const loadDoc = useCallback(
    async (id: string, path: string, type = "md", e2eRun?: string) => {
      setActivePath(path);
      setActiveType(type);
      if (type === "pdf") {
        setViewerText("");
        return;
      }
      try {
        const txt = await api.fileText(id, path, e2eRun);
        setViewerText(txt);
      } catch (e) {
        setViewerText(`Could not load \`${path}\`\n\n${String(e)}`);
      }
    },
    []
  );

  // Load plates / stats / graph for the current review workspace
  // (live project root, or e2e/runs/<id>/ when an E2E snapshot is selected).
  const loadWorkspace = useCallback(
    async (id: string, e2eRun: string) => {
      const e2e = e2eRun || undefined;
      setError("");
      setOutputs(null);
      setStats(null);
      setUnitRung(null);
      setGraphRuns([]);
      setGraphRunId("");
      setGraphOverview(null);
      setGraphUnitDetail(null);
      setLessonFeedback(null);
      setArtifactRung(null);
      setLessonReview(null);
      try {
        const tree = await api.outputs(id, e2e);
        setOutputs(tree);
        // Default to the first available plate (Dashboard).
        const first = tree.plates[0] ?? tree.layers[0];
        if (first) await loadDoc(id, first.path, first.type, e2e);
        else {
          setActivePath(UNITS_VIEW);
          setActiveType("md");
        }
      } catch (e) {
        // Still offer View → Curriculum graph when plates are not ready yet.
        setOutputs({ plates: [], layers: [], pdfs: [], units: [], e2e_run: e2e ?? null });
        setActivePath(GRAPH_VIEW);
        setActiveType("md");
        setError(
          e2e
            ? `No E2E output plates for ${id}/${e2e} yet (graph/runs may still load).`
            : `No outputs for ${id}: ${String(e)}`
        );
      }
      api.stats(id, e2e).then(setStats).catch(() => setStats(null));
      api.unitRung(id, e2e).then(setUnitRung);
      api.artifactRung(id, e2e).then(setArtifactRung);
      // Graph A/B (or nested graph under the E2E mirror).
      setGraphLoading(true);
      api
        .graphRuns(id, e2e)
        .then((res) => {
          setGraphRuns(res.runs);
          // Prefer active pointer on live root; under E2E prefer matching run id.
          const preferred =
            e2e && res.runs.some((r) => r.run_id === e2e)
              ? e2e
              : res.active && res.runs.some((r) => r.run_id === res.active)
                ? res.active
                : res.runs[0]?.run_id ?? "";
          setGraphRunId(preferred);
        })
        .catch(() => {
          setGraphRuns([]);
          setGraphRunId("");
        })
        .finally(() => setGraphLoading(false));
    },
    [loadDoc]
  );

  // Curriculum change: list E2E snapshots and default into the best one.
  // Best practice: E2E is canonical — only fall back to live root when none exist.
  useEffect(() => {
    let cancelled = false;
    setE2eRuns([]);
    setE2eRunId("");
    api
      .e2eRuns(projectId)
      .then((res) => {
        if (cancelled) return;
        setE2eRuns(res.runs);
        // Prefer a run with quality plates, else dashboard, else first id.
        const preferred =
          res.runs.find((r) => r.has_quality)?.run_id ??
          res.runs.find((r) => r.has_dashboard)?.run_id ??
          res.runs[0]?.run_id ??
          "";
        setE2eRunId(preferred);
      })
      .catch(() => {
        if (cancelled) return;
        setE2eRuns([]);
        setE2eRunId("");
      });
    return () => {
      cancelled = true;
    };
  }, [projectId]);

  // Workspace reload whenever curriculum or E2E selection settles.
  useEffect(() => {
    loadWorkspace(projectId, e2eRunId);
  }, [projectId, e2eRunId, loadWorkspace]);

  // Selected model run → belonging overview (drives the panel under the heatmap).
  useEffect(() => {
    if (!projectId || !graphRunId) {
      setGraphOverview(null);
      return;
    }
    let cancelled = false;
    const e2e = e2eRunId || undefined;
    setGraphLoading(true);
    api
      .graphOverview(projectId, graphRunId, e2e)
      .then((ov) => {
        if (!cancelled) setGraphOverview(ov);
      })
      .catch(() => {
        if (!cancelled) setGraphOverview(null);
      })
      .finally(() => {
        if (!cancelled) setGraphLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, graphRunId, e2eRunId]);

  // Model / E2E picker also swaps the quality heatmap + curriculum review plates.
  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    const rid = graphRunId || undefined;
    const e2e = e2eRunId || undefined;
    Promise.all([
      api.lessonFeedback(projectId, rid, e2e),
      api.lessonReview(projectId, rid, e2e),
    ])
      .then(([fb, rev]) => {
        if (cancelled) return;
        setLessonFeedback(fb);
        setLessonReview(rev);
      })
      .catch(() => {
        if (cancelled) return;
        setLessonFeedback(null);
        setLessonReview(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, graphRunId, e2eRunId]);

  // Open unit + selected model → materials / lessons / assessments (HAS-PART).
  // Load on unit drill-down *and* Curriculum graph view so the SVG can draw
  // below-unit nodes (previously GRAPH_VIEW cleared detail and stayed unit-only).
  useEffect(() => {
    if (!projectId || !graphRunId || !selectedUnitId) {
      setGraphUnitDetail(null);
      return;
    }
    if (activePath !== UNIT_DETAIL && activePath !== GRAPH_VIEW) {
      setGraphUnitDetail(null);
      return;
    }
    let cancelled = false;
    const e2e = e2eRunId || undefined;
    api
      .graphUnit(projectId, graphRunId, selectedUnitId, e2e)
      .then((d) => {
        if (!cancelled) setGraphUnitDetail(d);
      })
      .catch(() => {
        if (!cancelled) setGraphUnitDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, graphRunId, e2eRunId, selectedUnitId, activePath]);

  // --- run + poll ---------------------------------------------------------
  const stopPoll = () => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const startRun = useCallback(async () => {
    try {
      stopPoll();
      const id = await api.startRun(projectId, []);
      setRunStatus({ runId: id, status: "running", exitCode: null, log: "" });
      pollRef.current = window.setInterval(async () => {
        try {
          const s = await api.runStatus(id);
          setRunStatus(s);
          if (s.status !== "running") {
            stopPoll();
            // Live audit writes to project root — refresh that workspace.
            loadWorkspace(projectId, e2eRunId);
          }
        } catch {
          /* keep polling */
        }
      }, 1500);
    } catch (e) {
      setError(String(e));
    }
  }, [projectId, e2eRunId, loadWorkspace]);

  useEffect(() => stopPoll, []);

  const running = runStatus?.status === "running";

  const bandFor = useCallback(
    (u: UnitRollup): Band => {
      const real = unitRung?.units?.[u.unit_id]?.band;
      return real ?? deriveBand(u);
    },
    [unitRung]
  );

  // Completeness (Chip 1) comes straight from the unit rung; undefined when the
  // rung predates the packet-type work, so the chip degrades to "unknown".
  const completenessFor = useCallback(
    (u: UnitRollup) => unitRung?.units?.[u.unit_id]?.completeness ?? null,
    [unitRung]
  );

  // Drill-down now opens the rich unit-rung detail panel (rendered from the
  // already-loaded UNIT-RUNG.json) instead of the thin per-unit stub. The stub
  // and other artifacts remain reachable as links inside the panel.
  const openUnitDetail = useCallback((unitId: string) => {
    setSelectedUnitId(unitId);
    setSelectedLessonId(null);
    setSelectedArtifactId(null);
    setActivePath(UNIT_DETAIL);
    setActiveType("md");
  }, []);

  const openLessonDetail = useCallback((lessonId: string) => {
    setSelectedLessonId(lessonId);
    setActivePath(LESSON_DETAIL);
    setActiveType("md");
  }, []);

  const openArtifactDetail = useCallback((docId: string) => {
    setSelectedArtifactId(docId);
    setActivePath(ARTIFACT_DETAIL);
    setActiveType("md");
  }, []);

  // Lessons for the currently-selected unit (from LESSON-QUALITY-FEEDBACK.json).
  const selectedUnitLessons = useMemo(() => {
    if (!selectedUnitId || !lessonFeedback) return [];
    return lessonFeedback.units[selectedUnitId] ?? [];
  }, [selectedUnitId, lessonFeedback]);

  const selectedLesson = useMemo(() => {
    if (!selectedLessonId || !lessonFeedback) return undefined;
    for (const ls of Object.values(lessonFeedback.units)) {
      const hit = ls.find((l) => l.lesson_id === selectedLessonId);
      if (hit) return hit;
    }
    return undefined;
  }, [selectedLessonId, lessonFeedback]);

  // The grounded curriculum review for the selected lesson (if one has been
  // generated). Matched by lesson_id across units, same as the quality feedback.
  const selectedLessonReview = useMemo(() => {
    if (!selectedLessonId || !lessonReview) return undefined;
    for (const ls of Object.values(lessonReview.units)) {
      const hit = ls.find((l) => l.lesson_id === selectedLessonId);
      if (hit) return hit;
    }
    return undefined;
  }, [selectedLessonId, lessonReview]);

  // The artifact rung's per-unit block for the selected unit, and the single doc
  // record for the artifact drill-down.
  const selectedUnitArtifacts = useMemo(() => {
    if (!selectedUnitId || !artifactRung) return undefined;
    return artifactRung.units[selectedUnitId];
  }, [selectedUnitId, artifactRung]);

  const selectedArtifact = useMemo(() => {
    if (!selectedArtifactId || !artifactRung) return undefined;
    for (const u of Object.values(artifactRung.units)) {
      const hit = u.documents.find((d) => d.doc_id === selectedArtifactId);
      if (hit) return hit;
    }
    return undefined;
  }, [selectedArtifactId, artifactRung]);

  // Per-unit artifact files, minus the thin stub "Report" when richer files
  // exist, so the detail panel links to the useful reports first.
  const selectedUnitFiles = useMemo(() => {
    if (!selectedUnitId) return [];
    const unit = outputs?.units.find((x) => x.unit_id === selectedUnitId);
    const files = unit?.files ?? [];
    const rich = files.filter((f) => f.label !== "Report");
    return rich.length > 0 ? rich : files;
  }, [outputs, selectedUnitId]);

  const quickLinks = useMemo(
    () => (outputs ? outputs.plates.slice(0, 4) : []),
    [outputs]
  );

  const showUnits = activePath === UNITS_VIEW;
  const showUnitDetail = activePath === UNIT_DETAIL && !!selectedUnitId;
  const showLessonDetail = activePath === LESSON_DETAIL && !!selectedLesson;
  const showArtifactDetail =
    activePath === ARTIFACT_DETAIL && !!selectedArtifact;
  const selectedRollup = selectedUnitId
    ? stats?.unit_rollup?.find((u) => u.unit_id === selectedUnitId)
    : undefined;
  const selectedRecord = selectedUnitId
    ? unitRung?.units?.[selectedUnitId]
    : undefined;

  const showGraph = activePath === GRAPH_VIEW;
  const hasGraph = !!graphOverview || sortedGraphRuns.length > 0;

  let panelTitle: string;
  if (showUnits) panelTitle = "Unit heatmap";
  else if (showGraph) panelTitle = "Curriculum graph";
  else if (showUnitDetail)
    panelTitle = `Unit · ${selectedRecord?.title ?? selectedRollup?.title ?? selectedUnitId}`;
  else if (showLessonDetail) panelTitle = `Lesson · ${selectedLesson!.title}`;
  else if (showArtifactDetail)
    panelTitle = `Artifact · ${selectedArtifact!.title}`;
  else panelTitle = activePath ?? "Viewer";

  return (
    <div className="app">
      <div className="topbar">
        <h1>Run Review</h1>
        {/* Top-level page switch: review console vs presentation decks. */}
        <div className="topnav" role="group" aria-label="page">
          <button
            type="button"
            aria-pressed={topView === "review"}
            onClick={() => setTopView("review")}
          >
            Review
          </button>
          <button
            type="button"
            aria-pressed={topView === "overview"}
            onClick={() => setTopView("overview")}
          >
            Overview
          </button>
          <button
            type="button"
            aria-pressed={topView === "next"}
            onClick={() => setTopView("next")}
          >
            Next Steps
          </button>
        </div>
        {(topView === "review" || topView === "next") && (
          <>
            <select
              value={projectId}
              onChange={(e) => {
                // Clear E2E with the curriculum change so we never request
                // projects/<new>/e2e/runs/<old-id> for one paint cycle.
                setE2eRunId("");
                setProjectId(e.target.value);
              }}
              aria-label="Curriculum"
              title="Curriculum"
            >
              <optgroup label="Curriculum">
                {curriculumProjects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {curriculumOptionLabel(p)}
                  </option>
                ))}
              </optgroup>
              {showLabForks && labProjects.length > 0 && (
                <optgroup label="Lab forks">
                  {labProjects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {curriculumOptionLabel(p)}
                    </option>
                  ))}
                </optgroup>
              )}
              {/* Keep a selected lab visible if the toggle was just turned off. */}
              {!showLabForks &&
                labProjects.some((p) => p.id === projectId) && (
                  <optgroup label="Lab forks">
                    {labProjects
                      .filter((p) => p.id === projectId)
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {curriculumOptionLabel(p)}
                        </option>
                      ))}
                  </optgroup>
                )}
            </select>
            <label className="topbar-lab-toggle" title="Show lab-* experiment forks">
              <input
                type="checkbox"
                checked={showLabForks}
                onChange={(e) => {
                  const on = e.target.checked;
                  setShowLabForks(on);
                  // Leaving labs: snap back to a real curriculum so the list stays clean.
                  if (!on && labProjects.some((p) => p.id === projectId)) {
                    const next =
                      curriculumProjects.find((p) => p.id === DEFAULT_PROJECT) ??
                      curriculumProjects[0];
                    if (next) setProjectId(next.id);
                  }
                }}
              />
              <span>Lab forks</span>
            </label>
            {topView === "review" && (
              <>
                <select
                  value={e2eRunId}
                  onChange={(e) => setE2eRunId(e.target.value)}
                  aria-label="E2E run"
                  title="Canonical full-pipeline snapshot (e2e/runs/). Live root is legacy/golden only."
                >
                  <option value="">
                    {e2eRuns.length
                      ? "Legacy · live project root"
                      : "No E2E runs (live root)"}
                  </option>
                  {e2eRuns.map((r) => (
                    <option key={r.run_id} value={r.run_id}>
                      E2E · {r.run_id}
                      {r.n_output_units ? ` · ${r.n_output_units}u` : ""}
                    </option>
                  ))}
                </select>
                <select
                  value={graphRunId}
                  onChange={(e) => setGraphRunId(e.target.value)}
                  disabled={!sortedGraphRuns.length}
                  aria-label="Model run"
                  title={
                    e2eRunId
                      ? `Graph nested under e2e/runs/${e2eRunId}/graph/runs/`
                      : "Legacy bare graph/runs/ (prefer an E2E snapshot)"
                  }
                >
                  {!sortedGraphRuns.length ? (
                    <option value="">No model runs</option>
                  ) : (
                    sortedGraphRuns.map((r) => (
                      <option key={r.run_id} value={r.run_id}>
                        {graphRunLabel(r)}
                        {r.active ? " · active" : ""}
                        {r.n_haspart ? ` · ${r.n_haspart}u` : ""}
                      </option>
                    ))
                  )}
                </select>
              </>
            )}
          </>
        )}
        <div className="spacer" />
        {topView === "overview" && (
          <span className="mono" style={{ color: "var(--muted)" }}>
            how it works
          </span>
        )}
        {topView === "review" && (
          <span className="mono" style={{ color: "var(--muted)" }}>
            {e2eRunId
              ? `E2E · ${e2eRunId}`
              : "local review console"}
          </span>
        )}
        {topView === "next" && (
          <span className="mono" style={{ color: "var(--muted)" }}>
            create-after-audit
          </span>
        )}
      </div>

      {topView === "overview" ? (
        <Overview />
      ) : topView === "next" ? (
        <NextSteps projectId={projectId} />
      ) : (
      <div className="layout">
        <div className="main">
          {error && (
            <div className="panel">
              <div className="panel-body" style={{ color: "var(--accent)" }}>
                {error}
              </div>
            </div>
          )}

          {runStatus && (
            <div className="panel">
              <div className="panel-head">
                Run log{" "}
                <span className={`pill ${runStatus.status}`}>
                  {runStatus.status}
                </span>
              </div>
              <div className="panel-body">
                <div className="runlog">
                  {runStatus.log || "starting…"}
                </div>
              </div>
            </div>
          )}

          <div className="panel">
            <div className="panel-head">
              {showUnitDetail && (
                <button
                  className="back-link"
                  onClick={() => {
                    setActivePath(UNITS_VIEW);
                    setActiveType("md");
                  }}
                >
                  ← heatmap
                </button>
              )}
              {(showLessonDetail || showArtifactDetail) && (
                <button
                  className="back-link"
                  onClick={() => {
                    setActivePath(UNIT_DETAIL);
                    setActiveType("md");
                  }}
                >
                  ← {selectedRecord?.title ?? selectedRollup?.title ?? "unit"}
                </button>
              )}
              {panelTitle}
            </div>
            <div className="panel-body">
              {showUnits ? (
                <>
                  {(stats?.unit_rollup ?? []).length === 0 ? (
                    <div className="empty">
                      No unit rollup in aggregate-stats. Pick an E2E run with
                      finished output, or open Curriculum graph from View.
                    </div>
                  ) : (
                    <>
                      <PacketTypeBar
                        projectId={projectId}
                        packet={unitRung?.packet_type}
                        onChanged={() => loadWorkspace(projectId, e2eRunId)}
                      />
                      <div className="heat-colhead">
                        <span />
                        <span>Unit</span>
                        <span className="hc-pkt">
                          Packet &amp; completeness
                        </span>
                        <span className="hc-qual">Quality</span>
                      </div>
                      {stats!.unit_rollup!.map((u) => (
                        <UnitOutputRow
                          key={u.unit_id}
                          rollup={u}
                          band={bandFor(u)}
                          completeness={completenessFor(u)}
                          onOpen={() => openUnitDetail(u.unit_id)}
                        />
                      ))}
                    </>
                  )}
                </>
              ) : showGraph ? (
                <GraphBelongingPanel
                  overview={graphOverview}
                  unitDetail={graphUnitDetail}
                  selectedUnitId={selectedUnitId}
                  loading={graphLoading}
                  onOpenUnit={(unitId) => {
                    // Stay on Curriculum graph view; empty id = back to map.
                    if (!unitId) {
                      setSelectedUnitId(null);
                      setGraphUnitDetail(null);
                      return;
                    }
                    setSelectedUnitId(unitId);
                    setSelectedLessonId(null);
                    setSelectedArtifactId(null);
                    setActivePath(GRAPH_VIEW);
                    setActiveType("md");
                  }}
                />
              ) : showUnitDetail ? (
                <>
                  <UnitDetail
                    unitId={selectedUnitId!}
                    record={selectedRecord}
                    rollup={selectedRollup}
                    files={selectedUnitFiles}
                    band={
                      selectedRecord?.band ??
                      (selectedRollup ? bandFor(selectedRollup) : "Unrated")
                    }
                    onOpenFile={(path, type) =>
                      loadDoc(projectId, path, type, e2eRunId || undefined)
                    }
                    lessons={selectedUnitLessons}
                    onSelectLesson={openLessonDetail}
                    artifacts={selectedUnitArtifacts}
                    onSelectArtifact={openArtifactDetail}
                  />
                  <GraphBelongingPanel
                    overview={graphOverview}
                    unitDetail={graphUnitDetail}
                    selectedUnitId={selectedUnitId}
                    loading={graphLoading}
                    onOpenUnit={openUnitDetail}
                  />
                </>
              ) : showLessonDetail ? (
                <LessonDetail
                  lesson={selectedLesson!}
                  review={selectedLessonReview}
                  projectId={projectId}
                />
              ) : showArtifactDetail ? (
                <ArtifactDetail doc={selectedArtifact!} projectId={projectId} />
              ) : activeType === "pdf" && activePath ? (
                <div>
                  <p>
                    <a
                      href={api.fileUrl(
                        projectId,
                        activePath,
                        e2eRunId || undefined
                      )}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open / download PDF ↗
                    </a>
                  </p>
                  <embed
                    src={api.fileUrl(
                      projectId,
                      activePath,
                      e2eRunId || undefined
                    )}
                    type="application/pdf"
                    width="100%"
                    height="720px"
                    style={{ border: "2px solid var(--line)" }}
                  />
                </div>
              ) : viewerText ? (
                <MarkdownViewer
                  text={viewerText}
                  onNavigate={(rel) => {
                    const type = /\.pdf$/i.test(rel) ? "pdf" : "md";
                    loadDoc(projectId, rel, type, e2eRunId || undefined);
                  }}
                />
              ) : (
                <div className="empty">Select an output to review.</div>
              )}
            </div>
          </div>
        </div>

        <div>
          {outputs && (
            <OutputNav
              outputs={outputs}
              activePath={activePath}
              hasGraph={hasGraph}
              graphLabel={
                graphRunId
                  ? `Curriculum graph · ${graphRunLabel(
                      sortedGraphRuns.find((r) => r.run_id === graphRunId) ?? {
                        run_id: graphRunId,
                        model: graphRunId,
                        n_units: 0,
                        n_haspart: 0,
                      }
                    )}`
                  : "Curriculum graph"
              }
              onSelect={(path, type) => {
                if (path === UNITS_VIEW || path === GRAPH_VIEW) {
                  setSelectedUnitId(null);
                  setSelectedLessonId(null);
                  setSelectedArtifactId(null);
                  setActivePath(path);
                  setActiveType("md");
                  setViewerText("");
                } else {
                  loadDoc(projectId, path, type, e2eRunId || undefined);
                }
              }}
            />
          )}
          <ReviewSlip
            project={project}
            stats={stats}
            quickLinks={quickLinks}
            running={running}
            runStatus={runStatus}
            onRun={startRun}
            onRefresh={() => loadWorkspace(projectId, e2eRunId)}
            onQuickLink={(path) =>
              loadDoc(projectId, path, "md", e2eRunId || undefined)
            }
          />
        </div>
      </div>
      )}
    </div>
  );
}
