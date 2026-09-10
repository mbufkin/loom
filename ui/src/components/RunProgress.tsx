import type { RunProgressInfo } from "../types";

/** "4m 12s" — a duration a person can read at a glance. */
function humanDuration(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return rem ? `${m}m ${rem}s` : `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

const MARK: Record<string, string> = {
  done: "✓",
  running: "●",
  pending: "",
  failed: "✕",
};

/**
 * What the pipeline is doing, while it does it.
 *
 * An audit is a long job made of model calls, and a single call against a
 * hosted reasoning model can run for minutes with nothing written to the log.
 * A plain log tail therefore looks identical whether the run is working or
 * wedged, which is the one distinction someone watching actually needs. So
 * this leads with the current stage and how long the current step has been
 * outstanding, and keeps the raw log available underneath for when something
 * has genuinely gone wrong.
 */
export function RunProgress({
  progress,
  status,
}: {
  progress?: RunProgressInfo;
  status: string;
}) {
  if (!progress || !progress.stages || progress.stages.length === 0) return null;

  const running = status === "running";
  const { docsDone, docsTotal, detail, elapsed, modelCalls } = progress;
  const showDocs = docsTotal > 0 && progress.current === "layer0";
  const pct = showDocs ? Math.round((docsDone / docsTotal) * 100) : 0;

  return (
    <div className="run-progress">
      <div className="run-progress-head">
        <span className={`run-dot ${running ? "live" : status}`} />
        <strong>
          {status === "done"
            ? "Audit finished"
            : status === "error"
              ? "Audit stopped"
              : "Audit running"}
        </strong>
        <span className="setup-detail">{humanDuration(elapsed)} elapsed</span>
      </div>

      <ol className="run-stages">
        {progress.stages.map((s) => (
          <li key={s.id} className={`run-stage ${s.state}`}>
            <span className="run-stage-mark">{MARK[s.state] ?? ""}</span>
            <span className="run-stage-label">{s.label}</span>
            {s.state === "running" && detail && (
              <span className="run-stage-detail mono">{detail}</span>
            )}
          </li>
        ))}
      </ol>

      {showDocs && (
        <div className="run-bar-wrap">
          <div className="run-bar">
            <div className="run-bar-fill" style={{ width: `${pct}%` }} />
          </div>
          <span className="setup-detail">
            {docsDone} of {docsTotal} documents read
          </span>
        </div>
      )}

      {/* The liveness line. `waitingSeconds` is time since the last model
          reply landed, so a growing number during a stage means the model is
          still thinking rather than that the run has died. */}
      {running && (
        <p className="run-liveness">
          {modelCalls > 0
            ? `${modelCalls} model ${modelCalls === 1 ? "reply" : "replies"} so far`
            : "Waiting on the first model reply"}
          {progress.waitingSeconds > 0 &&
            ` · nothing back for ${humanDuration(progress.waitingSeconds)}`}
          {progress.lastCallSeconds > 0 &&
            ` · last reply took ${humanDuration(progress.lastCallSeconds)}`}
        </p>
      )}

      {running && progress.waitingSeconds > 180 && (
        <p className="setup-hint">
          A slow reply is normal for a reasoning model on a hosted service, and
          the run retries by itself if the service times out. The log below
          shows any warnings.
        </p>
      )}
    </div>
  );
}
