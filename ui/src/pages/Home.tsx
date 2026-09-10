import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, describeError } from "../lib/api";
import type { Project, StorageInfo } from "../types";

/** "Audited 10 Sep 2026", or an honest statement that it has not been. */
function auditedLabel(p: Project): string {
  if (!p.last_audit) {
    return p.has_manifest
      ? "Set up, not audited yet"
      : "Documents not organised yet";
  }
  const when = new Date(p.last_audit * 1000).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return `Audited ${when}`;
}

/**
 * The landing screen: a list of the curricula on this machine.
 *
 * Deliberately not a menu of features. A menu is how a developer pictures an
 * application; somebody responsible for curriculum thinks in terms of "the
 * curricula I am working on", the same way a text editor opens on your recent
 * folders rather than on a list of its own capabilities. So the list is the
 * screen, and everything else is reachable from a row in it or from the nav.
 */
export function Home() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [error, setError] = useState<{ message: string; detail: string } | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      // Storage is best-effort: an older API build without /api/storage should
      // still render the list rather than failing the whole screen.
      const [ps, st] = await Promise.all([
        api.projects(),
        api.storage().catch(() => null),
      ]);
      setProjects(ps);
      setStorage(st);
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

  // Lab forks are engineering scratch space, never a district's work.
  const curricula = projects.filter((p) => p.kind !== "lab");
  const reviewable = curricula.filter((p) => p.has_review_run);

  if (error) {
    return (
      <div className="home">
        <div className="panel">
          <div className="panel-head">Can’t reach Loom</div>
          <div className="panel-body">
            <p className="err-message">
              Loom’s local service isn’t responding, so this list can’t be
              loaded. Nothing has been lost — this is a connection problem
              between the two halves of the app on this machine.
            </p>
            <button type="button" onClick={() => void load()}>
              Try again
            </button>
            <details className="err-details">
              <summary>Technical details</summary>
              <pre>{error.detail}</pre>
            </details>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="home">
      <div className="home-head">
        <h2>Your curricula</h2>
        <Link className="btn-primary" to="/curricula/new">
          Add a curriculum
        </Link>
      </div>

      {!loaded ? (
        <div className="panel">
          <div className="panel-body empty">Loading…</div>
        </div>
      ) : curricula.length === 0 ? (
        <div className="panel">
          <div className="panel-head">Nothing here yet</div>
          <div className="panel-body">
            <p>
              No curriculum has been added on this computer. Loom reads the
              documents a district already has — pacing guides, lesson plans,
              assessments — and reports what is present, what is missing, and
              what needs a decision.
            </p>
            <Link className="btn-primary" to="/curricula/new">
              Add your first curriculum
            </Link>
          </div>
        </div>
      ) : (
        <ul className="curr-list">
          {curricula.map((p) => (
            <li key={p.id} className="curr-row">
              <div className="curr-main">
                <div className="curr-title">{p.title || p.id}</div>
                <div className="curr-meta">{auditedLabel(p)}</div>
              </div>
              {/* The console only renders a finished audit, so a curriculum
                  without one goes to its setup page instead of to a screen
                  that would have nothing on it. */}
              {p.has_review_run ? (
                <Link className="btn-primary" to={`/review?project=${p.id}`}>
                  Open
                </Link>
              ) : (
                <Link className="btn" to={`/curricula/${p.id}`}>
                  Set up
                </Link>
              )}
            </li>
          ))}
        </ul>
      )}

      {loaded && curricula.length > 0 && reviewable.length === 0 && (
        <p className="home-note">
          None of these have been audited yet. Opening one will show you what it
          still needs before Loom can report on it.
        </p>
      )}

      {storage && (
        <p className="home-note home-storage">
          Curricula, settings and reports are stored on this computer at{" "}
          <code>{storage.data_root}</code>. Nothing is uploaded anywhere.
        </p>
      )}
    </div>
  );
}
