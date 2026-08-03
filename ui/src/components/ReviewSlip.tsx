import type { OutputFile, Project, RunStatus, Stats } from "../types";

interface Props {
  project: Project;
  stats: Stats | null;
  quickLinks: OutputFile[];
  running: boolean;
  runStatus: RunStatus | null;
  onRun: () => void;
  onRefresh: () => void;
  onQuickLink: (path: string) => void;
}

// Sticky right-rail slip — the Loom analogue of Fairway's DraftSlip. Shows the
// tier badge, headline counts, run controls, and quick links to top plates.
export function ReviewSlip({
  project,
  stats,
  quickLinks,
  running,
  runStatus,
  onRun,
  onRefresh,
  onQuickLink,
}: Props) {
  const findings = stats?.finding_status_counts ?? {};
  const missing = findings["MISSING"] ?? 0;
  const fulfilled = findings["FULFILLED"] ?? 0;
  const pending = stats?.review_queue_pending_pairs ?? 0;

  return (
    <aside className="panel slip">
      <div className="panel-head">Review slip</div>
      <div className="panel-body">
        <span className="tier-badge">{project.tier}</span>{" "}
        <span className="mono">{project.id}</span>

        <div className="stat-grid">
          <div className="stat">
            <div className="n">{stats?.documents_judged ?? "—"}</div>
            <div className="l">Docs judged</div>
          </div>
          <div className="stat">
            <div className="n">{stats?.elements_judged ?? "—"}</div>
            <div className="l">Elements</div>
          </div>
          <div className="stat">
            <div className="n">{fulfilled}</div>
            <div className="l">Fulfilled</div>
          </div>
          <div className="stat">
            <div className="n">{missing}</div>
            <div className="l">Missing</div>
          </div>
          <div className="stat">
            <div className="n">{pending}</div>
            <div className="l">Review pairs</div>
          </div>
          <div className="stat">
            <div className="n">{stats?.unit_rollup?.length ?? "—"}</div>
            <div className="l">Units</div>
          </div>
        </div>

        <div className="actions">
          <button className="primary" onClick={onRun} disabled={running}>
            {running ? "Running…" : "Run"}
          </button>
          <button onClick={onRefresh}>Refresh</button>
        </div>

        {runStatus && (
          <div style={{ marginBottom: 12 }}>
            <span className={`pill ${runStatus.status}`}>
              {runStatus.status}
              {runStatus.exitCode !== null ? ` (${runStatus.exitCode})` : ""}
            </span>
          </div>
        )}

        {quickLinks.length > 0 && (
          <div className="quick-links">
            <h3
              style={{
                fontSize: 11,
                textTransform: "uppercase",
                color: "var(--muted)",
              }}
            >
              Quick links
            </h3>
            {quickLinks.map((q) => (
              <a
                key={q.path}
                href="#"
                onClick={(e) => {
                  e.preventDefault();
                  onQuickLink(q.path);
                }}
              >
                {q.label}
              </a>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
