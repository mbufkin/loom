import type { ReactNode } from "react";
import type { Project, RunPreflight, RunStatus } from "../types";

interface Props {
  /** Title of the currently selected curriculum, which has no finished audit. */
  projectTitle: string;
  /** Curricula that *do* have a finished audit, so nobody ends up stranded. */
  reviewable: Project[];
  onPick: (id: string) => void;
  /** null while the capability check is still in flight. */
  preflight: RunPreflight | null;
  onRunAudit: () => void;
  running: boolean;
  runStatus: RunStatus | null;
}

/** "bash and python3", "bash, python3 and the run-audit script". */
function formatList(items: string[]): string {
  if (items.length <= 1) return items[0] ?? "";
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

// Shown in place of the review console when the selected curriculum has no
// finished audit. This is the screen a first-time user is most likely to meet,
// so it has to say what Loom does, why the page is empty, and give exactly one
// thing to do next — never a filename, a shell script, or a docs path.
export function FirstRun({
  projectTitle,
  reviewable,
  onPick,
  preflight,
  onRunAudit,
  running,
  runStatus,
}: Props) {
  const nothingAudited = reviewable.length === 0;

  // The action is gated on a real capability check rather than optimism:
  // starting an audit shells out to bash + python3, and offering a button that
  // dies on spawn is exactly the dead end this screen exists to remove.
  let action: ReactNode;
  if (!preflight) {
    action = <p className="muted-note">Checking what this computer can do…</p>;
  } else if (preflight.can_run) {
    action = (
      <>
        <button
          type="button"
          className="primary"
          onClick={onRunAudit}
          disabled={running}
        >
          {running ? "Audit running…" : "Run the audit now"}
        </button>
        <p className="muted-note">
          This reads the documents already sitting in the curriculum folder. It
          can take a while, and the progress appears below as it goes.
        </p>
      </>
    );
  } else {
    action = (
      <>
        <p className="fr-blocked">
          <strong>This computer can’t start an audit.</strong> It’s missing{" "}
          {formatList(preflight.missing)}.
        </p>
        <p className="muted-note">
          Run the audit on the workstation where Loom is set up, then copy the
          results folder over and reopen this window. Reading finished results
          works perfectly well here.
        </p>
      </>
    );
  }

  return (
    <div className="layout">
      <div className="main">
        <div className="panel">
          <div className="panel-head">
            {nothingAudited ? "Nothing audited yet" : "Not audited yet"}
          </div>
          <div className="panel-body fr-body">
            {nothingAudited ? (
              <>
                <h2 className="fr-title">No curriculum has been audited yet</h2>
                <p className="fr-lead">
                  Loom reads a folder of curriculum documents and tells you
                  what’s in it, what’s missing, and how good what’s there
                  actually is — quoting the source document for every
                  judgement. Nothing leaves this computer. As soon as an audit
                  finishes, its results open here.
                </p>
              </>
            ) : (
              <>
                <h2 className="fr-title">
                  {projectTitle} hasn’t been audited yet
                </h2>
                <p className="fr-lead">
                  There are no results to show for this one. Open a curriculum
                  that has been audited, or run the audit for this one.
                </p>
                <div className="fr-picks">
                  {reviewable.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => onPick(p.id)}
                    >
                      Open {p.title || p.id}
                    </button>
                  ))}
                </div>
              </>
            )}

            <div className="fr-action">{action}</div>
          </div>
        </div>

        {runStatus && (
          <div className="panel">
            <div className="panel-head">
              Audit progress{" "}
              <span className={`pill ${runStatus.status}`}>
                {runStatus.status}
              </span>
            </div>
            <div className="panel-body">
              <div className="runlog">{runStatus.log || "starting…"}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
