interface Props {
  error: { message: string; detail?: string };
  onRetry: () => void;
}

// Shown when the local API cannot be reached at all. This has to be its own
// screen rather than an empty state: if the service is down, "no audits yet"
// and "nothing missing" are both indistinguishable from the truth, and a
// reviewer would reasonably conclude their curriculum is fine. Say what broke.
export function ServiceDown({ error, onRetry }: Props) {
  return (
    <div className="layout">
      <div className="main">
        <div className="panel">
          <div className="panel-head">Not connected</div>
          <div className="panel-body fr-body">
            <h2 className="fr-title">Loom isn’t responding</h2>
            {/* Deliberately not `error.message`: in development the Vite proxy
                turns a refused connection into a plain 500, so the mapped
                sentence would say "something went wrong reading this audit"
                when the real problem is that nothing is listening at all.
                Reaching this screen already means the project list failed. */}
            <p className="fr-lead">
              This window can’t reach the Loom service on this computer, so no
              results can be loaded.
            </p>
            <p className="fr-lead">
              Nothing is shown below because the results can’t be read right
              now — not because the curriculum is empty.
            </p>
            <div className="fr-action">
              <button type="button" className="primary" onClick={onRetry}>
                Try again
              </button>
              <p className="muted-note">
                If this keeps happening, close the window and open Loom again.
              </p>
              <details className="err-details">
                <summary>Technical details</summary>
                <code>
                  {error.message}
                  {error.detail ? ` — ${error.detail}` : ""}
                </code>
              </details>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
