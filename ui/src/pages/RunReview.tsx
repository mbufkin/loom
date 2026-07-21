import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import { MarkdownViewer } from "../components/MarkdownViewer";
import { OutputNav } from "../components/OutputNav";
import { ReviewSlip } from "../components/ReviewSlip";
import { UnitOutputRow } from "../components/UnitOutputRow";
import type {
  Band,
  OutputsTree,
  Project,
  RunStatus,
  Stats,
  UnitRollup,
  UnitRung,
} from "../types";

const DEFAULT_PROJECT = "dallas-career-2026";
const UNITS_VIEW = "__units__";

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

  const [activePath, setActivePath] = useState<string | null>(null);
  const [activeType, setActiveType] = useState<string>("md");
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

  const openUnitReport = useCallback(
    (unitId: string) => {
      const unit = outputs?.units.find((x) => x.unit_id === unitId);
      const report =
        unit?.files.find((f) => f.label === "Report") ?? unit?.files[0];
      if (report) loadDoc(projectId, report.path, report.type);
    },
    [outputs, projectId, loadDoc]
  );

  const quickLinks = useMemo(
    () => (outputs ? outputs.plates.slice(0, 4) : []),
    [outputs]
  );

  const showUnits = activePath === UNITS_VIEW;

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
              {showUnits ? "Unit heatmap" : activePath ?? "Viewer"}
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
                      onOpen={() => openUnitReport(u.unit_id)}
                    />
                  ))
                )
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
