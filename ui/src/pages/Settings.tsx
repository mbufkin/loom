import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ModelPicker } from "../components/ModelPicker";
import { api, describeError } from "../lib/api";
import { readiness, usePreflight } from "../lib/usePreflight";
import type { StorageInfo } from "../types";

/**
 * Settings: what this copy of Loom is currently doing, and where.
 *
 * Answers the questions people actually get stuck on: which model is being
 * used, does it run on this computer, where did my work go, and can this
 * machine run an audit at all.
 *
 * The model is the one setting that can be changed here, and ModelPicker
 * owns that story end to end — what is in use, where it runs, whether
 * documents leave the machine, and what else is available. This screen used
 * to describe the current model itself as well, which meant two components
 * rendering one fact from two sources.
 */
export function Settings() {
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [error, setError] = useState<{ message: string; detail: string } | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);
  // Shared with Setup rather than fetched separately. When each screen kept
  // its own copy they could answer the same question differently depending on
  // when they happened to ask, which is how "finish setup" ended up linking
  // to a screen that said setup was already finished.
  const { preflight, refresh: refreshPreflight } = usePreflight();

  const load = useCallback(async () => {
    try {
      // Independently optional — a missing endpoint on an older build should
      // grey out one card, not blank the whole screen.
      const st = await api.storage().catch(() => null);
      await refreshPreflight();
      setStorage(st);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoaded(true);
    }
  }, [refreshPreflight]);

  useEffect(() => {
    void load();
  }, [load]);

  // A response with no `checks` came from a server started before the program
  // was updated — the usual cause is a desktop window left open across an
  // upgrade, which keeps its original server process alive indefinitely.
  const staleServer = !!preflight && (preflight.checks ?? []).length === 0;
  // Prefer the detailed checks; fall back to the flat list an older server
  // sends, since naming something beats naming nothing.
  const missingNames = (preflight?.checks ?? [])
    .filter((c) => !c.ok && c.severity !== "optional")
    .map((c) => c.label);
  const shown = missingNames.length > 0 ? missingNames : (preflight?.missing ?? []);
  const missingLabel =
    shown.length === 0
      ? ""
      : shown.length === 1
        ? `${shown[0]} is missing`
        : `${shown.slice(0, -1).join(", ")} and ${shown[shown.length - 1]} are missing`;

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

      {/* The picker now owns the whole model story — what is in use, where it
          runs, whether documents leave the machine, and what else is
          available. There used to be a separate "Where the reading happens"
          panel above it, but two panels describing one setting is how they
          drift apart, and the answer was split across both. */}
      <ModelPicker onConnected={() => void load()} />

      {preflight && (
        <div className="panel">
          <div className="panel-head">Can this computer run an audit?</div>
          <div className="panel-body">
            {/* Same helper Setup uses, so the two screens cannot reach
                different conclusions from the same reply. */}
            {readiness(preflight).ready ? (
              <p>Yes — everything an audit needs is installed.</p>
            ) : (
              <>
                {/* Name what is missing rather than saying "something".
                    "Something is missing" sends the reader to another screen
                    just to learn the noun, and it hides the case that matters
                    most here: a stale answer. Seeing "bash, python3" on a
                    Windows box is immediately recognisable as wrong, where
                    "something" looks like a normal setup step. */}
                <p className="err-message">
                  {readiness(preflight).pdfOnly
                    ? "Almost. Loom can run here but cannot open PDF files yet."
                    : missingLabel
                      ? `Not yet — ${missingLabel}.`
                      : "Not yet — something an audit needs is missing."}
                </p>
                {staleServer && (
                  <p className="err-message">
                    That list looks out of date. This window is still talking
                    to a copy of Loom that was started before the program was
                    updated. Close Loom and open it again.
                  </p>
                )}
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
        The model can be changed here. Everything else on this screen is still
        read-only, and API keys for hosted services are not managed in the app
        yet.
      </p>
    </div>
  );
}
