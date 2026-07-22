import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { MarkdownViewer } from "../components/MarkdownViewer";
import { OutputNav } from "../components/OutputNav";
import { ReviewSlip } from "../components/ReviewSlip";
import { UnitDetail } from "../components/UnitDetail";
import { LessonDetail } from "../components/LessonDetail";
import { ArtifactDetail } from "../components/ArtifactDetail";
import { UnitOutputRow } from "../components/UnitOutputRow";
import type {
  ArtifactRung,
  Band,
  LessonFeedback,
  OutputsTree,
  Project,
  RunStatus,
  Stats,
  UnitRollup,
  UnitRung,
} from "../types";

const DEFAULT_PROJECT = "dallas-career-2026";
const UNITS_VIEW = "__units__";
const UNIT_DETAIL = "__unit_detail__";
const LESSON_DETAIL = "__lesson_detail__";
const ARTIFACT_DETAIL = "__artifact_detail__";

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
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<string>(DEFAULT_PROJECT);
  const [outputs, setOutputs] = useState<OutputsTree | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [unitRung, setUnitRung] = useState<UnitRung | null>(null);
  const [lessonFeedback, setLessonFeedback] = useState<LessonFeedback | null>(
    null
  );
  const [artifactRung, setArtifactRung] = useState<ArtifactRung | null>(null);

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

  // Load the project list once.
  useEffect(() => {
    api
      .projects()
      .then((ps) => {
        setProjects(ps);
        if (!ps.some((p) => p.id === DEFAULT_PROJECT) && ps[0]) {
          setProjectId(ps[0].id);
        }
      })
      .catch((e) => setError(String(e)));
  }, []);

  const loadDoc = useCallback(
    async (id: string, path: string, type = "md") => {
      setActivePath(path);
      setActiveType(type);
      if (type === "pdf") {
        setViewerText("");
        return;
      }
      try {
        const txt = await api.fileText(id, path);
        setViewerText(txt);
      } catch (e) {
        setViewerText(`Could not load \`${path}\`\n\n${String(e)}`);
      }
    },
    []
  );

  const loadProject = useCallback(
    async (id: string) => {
      setError("");
      setOutputs(null);
      setStats(null);
      setUnitRung(null);
      setLessonFeedback(null);
      setArtifactRung(null);
      try {
        const tree = await api.outputs(id);
        setOutputs(tree);
        // Default to the first available plate (Dashboard).
        const first = tree.plates[0] ?? tree.layers[0];
        if (first) await loadDoc(id, first.path, first.type);
        else {
          setActivePath(UNITS_VIEW);
          setActiveType("md");
        }
      } catch (e) {
        setError(`No outputs for ${id}: ${String(e)}`);
      }
      api.stats(id).then(setStats).catch(() => setStats(null));
      api.unitRung(id).then(setUnitRung);
      api.lessonFeedback(id).then(setLessonFeedback);
      api.artifactRung(id).then(setArtifactRung);
    },
    [loadDoc]
  );

  useEffect(() => {
    loadProject(projectId);
  }, [projectId, loadProject]);

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
            loadProject(projectId); // refresh outputs after the run completes
          }
        } catch {
          /* keep polling */
        }
      }, 1500);
    } catch (e) {
      setError(String(e));
    }
  }, [projectId, loadProject]);

  useEffect(() => stopPoll, []);

  const running = runStatus?.status === "running";

  const bandFor = useCallback(
    (u: UnitRollup): Band => {
      const real = unitRung?.units?.[u.unit_id]?.band;
      return real ?? deriveBand(u);
    },
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

  let panelTitle: string;
  if (showUnits) panelTitle = "Unit heatmap";
  else if (showUnitDetail)
    panelTitle = `Unit · ${selectedRecord?.title ?? selectedRollup?.title ?? selectedUnitId}`;
  else if (showLessonDetail) panelTitle = `Lesson · ${selectedLesson!.title}`;
  else if (showArtifactDetail)
    panelTitle = `Artifact · ${selectedArtifact!.title}`;
  else panelTitle = activePath ?? "Viewer";

  return (
    <div className="app">
      <div className="topbar">
        <h1>Loom Run Review</h1>
        <select
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id} — {p.tier}
            </option>
          ))}
        </select>
        <div className="spacer" />
        <span className="mono" style={{ color: "var(--muted)" }}>
          local review console
        </span>
      </div>

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
                (stats?.unit_rollup ?? []).length === 0 ? (
                  <div className="empty">No unit rollup in aggregate-stats.</div>
                ) : (
                  stats!.unit_rollup!.map((u) => (
                    <UnitOutputRow
                      key={u.unit_id}
                      rollup={u}
                      band={bandFor(u)}
                      onOpen={() => openUnitDetail(u.unit_id)}
                    />
                  ))
                )
              ) : showUnitDetail ? (
                <UnitDetail
                  unitId={selectedUnitId!}
                  record={selectedRecord}
                  rollup={selectedRollup}
                  files={selectedUnitFiles}
                  band={
                    selectedRecord?.band ??
                    (selectedRollup ? bandFor(selectedRollup) : "Unrated")
                  }
                  onOpenFile={(path, type) => loadDoc(projectId, path, type)}
                  lessons={selectedUnitLessons}
                  onSelectLesson={openLessonDetail}
                  artifacts={selectedUnitArtifacts}
                  onSelectArtifact={openArtifactDetail}
                />
              ) : showLessonDetail ? (
                <LessonDetail lesson={selectedLesson!} projectId={projectId} />
              ) : showArtifactDetail ? (
                <ArtifactDetail doc={selectedArtifact!} projectId={projectId} />
              ) : activeType === "pdf" && activePath ? (
                <div>
                  <p>
                    <a
                      href={api.fileUrl(projectId, activePath)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Open / download PDF ↗
                    </a>
                  </p>
                  <embed
                    src={api.fileUrl(projectId, activePath)}
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
                    loadDoc(projectId, rel, type);
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
              onSelect={(path, type) => {
                if (path === UNITS_VIEW) {
                  setActivePath(UNITS_VIEW);
                  setActiveType("md");
                } else {
                  loadDoc(projectId, path, type);
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
            onRefresh={() => loadProject(projectId)}
            onQuickLink={(path) => loadDoc(projectId, path, "md")}
          />
        </div>
      </div>
    </div>
  );
}
