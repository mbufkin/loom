import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, describeError } from "../lib/api";
import type { ConfigSummary, RunPreflight, StorageInfo } from "../types";

/** Is this endpoint on this machine, or somewhere on the network? */
function isLocalEndpoint(url: string | null | undefined): boolean {
  if (!url) return false;
  return /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(url);
}

/**
 * Settings: what this copy of Loom is currently doing, and where.
 *
 * Read-only for now, and it says so rather than presenting inputs that
 * silently fail to save. That is deliberate: `config.yaml` has never had a
 * write path — the API only ever exposed a curated read — so shipping an
 * editor here would mean building the write side, and doing that carelessly is
 * how you corrupt the file that every pipeline stage depends on.
 *
 * What it *can* do honestly today is answer the questions people actually get
 * stuck on: which model is being used, is it running on this computer, where
 * did my work go, and can this machine run an audit at all.
 */
export function Settings() {
  const [config, setConfig] = useState<ConfigSummary | null>(null);
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [preflight, setPreflight] = useState<RunPreflight | null>(null);
  const [error, setError] = useState<{ message: string; detail: string } | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      // Each is independently optional — a missing endpoint on an older build
      // should grey out one card, not blank the whole screen.
      const [cfg, st, pf] = await Promise.all([
        api.config().catch(() => null),
        api.storage().catch(() => null),
        api.canRun().catch(() => null),
      ]);
      if (!cfg && !st && !pf) throw new Error("no settings endpoints responded");
      setConfig(cfg);
      setStorage(st);
      setPreflight(pf);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const models = config?.models ?? {};
  const analystUrl = models.analyst_url ?? null;
  const local = isLocalEndpoint(analystUrl);

  if (!loaded) {
    return (
      <div className="home">
        <div className="panel">
          <div className="panel-body empty">Loading…</div>
        </div>
      </div>
    );
  }

  return (
    <div className="home">
      <div className="home-head">
        <h2>Settings</h2>
      </div>

      {error && (
        <div className="panel">
          <div className="panel-head">Can’t reach Loom</div>
          <div className="panel-body">
            <p className="err-message">{error.message}</p>
            <button type="button" onClick={() => void load()}>
              Try again
            </button>
            <details className="err-details">
              <summary>Technical details</summary>
              <pre>{error.detail}</pre>
            </details>
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-head">Where the reading happens</div>
        <div className="panel-body">
          {analystUrl ? (
            <>
              <p>
                {local ? (
                  <>
                    Loom is reading your documents with a model running{" "}
                    <strong>on this computer</strong>. No curriculum text
                    leaves the building.
                  </>
                ) : (
                  <>
                    Loom is reading your documents with a model at{" "}
                    <strong>an address outside this computer</strong>. Curriculum
                    text is sent there, so this should only be an endpoint your
                    district approves.
                  </>
                )}
              </p>
              <dl className="set-grid">
                <dt>Model</dt>
                <dd>{models.analyst_model || "not set"}</dd>
                <dt>Address</dt>
                <dd className="mono">{analystUrl}</dd>
                {models.verifier_url && models.verifier_url !== analystUrl && (
                  <>
                    <dt>Second opinion</dt>
                    <dd className="mono">{models.verifier_url}</dd>
                  </>
                )}
              </dl>
            </>
          ) : (
            <p className="err-message">
              No model is configured, so an audit cannot read anything yet.
            </p>
          )}
        </div>
      </div>

      {preflight && (
        <div className="panel">
          <div className="panel-head">Can this computer run an audit?</div>
          <div className="panel-body">
            {preflight.can_run && preflight.can_read_pdf !== false ? (
              <p>Yes — everything an audit needs is installed.</p>
            ) : (
              <>
                <p className="err-message">
                  {preflight.can_run
                    ? "Almost. Loom can run here but cannot open PDF files yet."
                    : "Not yet — something an audit needs is missing."}
                </p>
                {/* Point at the fix rather than restating the problem. Setup
                    lists each requirement separately with the command for this
                    platform, which is the part a reviewer can actually act on. */}
                <p>
                  <Link className="btn btn-primary" to="/setup">
                    Finish setup
                  </Link>
                </p>
                <p className="home-note">
                  Reviewing audits that were run elsewhere works either way.
                </p>
              </>
            )}
          </div>
        </div>
      )}

      {storage && (
        <div className="panel">
          <div className="panel-head">Where your work is kept</div>
          <div className="panel-body">
            <dl className="set-grid">
              <dt>Your curricula</dt>
              <dd className="mono">{storage.projects_root}</dd>
              <dt>The program</dt>
              <dd className="mono">{storage.install_root}</dd>
            </dl>
            {storage.legacy_in_repo ? (
              <p className="home-note">
                Your work is currently stored inside the program’s own folder.
                That is a developer setup — on an installed copy the two are
                kept apart so updating Loom can never touch your curricula.
              </p>
            ) : (
              <p className="home-note">
                Kept separate from the program, so updating Loom never touches
                your curricula.
              </p>
            )}
            {storage.pinned_by_env && (
              <p className="home-note">
                This location was set explicitly with <code>LOOM_HOME</code>.
              </p>
            )}
          </div>
        </div>
      )}

      <p className="home-note">
        These settings are read-only in the app for now. Changing the model or
        adding an API key still means editing <code>config.yaml</code> by hand.
      </p>
    </div>
  );
}
