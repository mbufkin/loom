import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, describeError } from "../lib/api";
import { IS_HOSTED } from "../lib/hosted";
import type { Project, StorageInfo } from "../types";

/**
 * Confirming a curriculum delete.
 *
 * A native <dialog> opened with showModal(), styled as one of the app's
 * panels: the browser supplies the focus trap, Escape to cancel, and an inert
 * page behind it, which a hand-rolled overlay would have to re-implement.
 *
 * The guard is typing the curriculum's folder name, not a second "are you
 * sure". The setup screen already shows that name in mono as the folder is
 * created, so it is a name the operator has seen; and a second click is the
 * same reflex as the first, where typing is not. Cancel takes focus, so Enter
 * on arrival does nothing destructive.
 */
function DeleteDialog({
  project,
  onCancel,
  onDeleted,
}: {
  project: Project;
  onCancel: () => void;
  onDeleted: (title: string, keepDays: number) => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const title = project.title || project.id;
  const matches = typed.trim().toLowerCase() === project.id.toLowerCase();

  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal();
  }, []);

  const confirm = async () => {
    if (!matches || deleting) return;
    setDeleting(true);
    setError(null);
    try {
      const res = await api.deleteProject(project.id);
      onDeleted(title, res.keep_days);
    } catch (e) {
      // 409 (a run started meanwhile) arrives here in the server's words.
      setError(describeError(e).message);
      setDeleting(false);
    }
  };

  return (
    <dialog
      ref={ref}
      className="panel confirm-dialog"
      aria-labelledby="delete-title"
      // Escape fires "cancel"; route it through the same path as the button
      // so the parent's state and the dialog never disagree.
      onCancel={(e) => {
        e.preventDefault();
        if (!deleting) onCancel();
      }}
    >
      <div className="panel-head" id="delete-title">
        Delete this curriculum?
      </div>
      <div className="panel-body">
        <p>
          <strong>{title}</strong> will be removed from Loom: its documents,
          the units Loom organised, and its audit results.
        </p>
        <p className="home-note">
          {IS_HOSTED
            ? "It is kept for 7 days in case this was a mistake; the operator can restore it in that time."
            : "It is kept for 7 days in the .trash folder beside your curricula, in case this was a mistake."}
        </p>
        <label className="confirm-type">
          Type <code>{project.id}</code> to confirm
          <input
            type="text"
            value={typed}
            autoComplete="off"
            spellCheck={false}
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void confirm();
            }}
          />
        </label>
        {error && <p className="err-message">{error}</p>}
        <div className="confirm-actions">
          <button type="button" autoFocus disabled={deleting} onClick={onCancel}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-danger"
            disabled={!matches || deleting}
            onClick={() => void confirm()}
          >
            {deleting ? "Deleting…" : "Delete curriculum"}
          </button>
        </div>
      </div>
    </dialog>
  );
}

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
  const [toDelete, setToDelete] = useState<Project | null>(null);
  const [deletedNote, setDeletedNote] = useState<string | null>(null);

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
                <div className="curr-meta" id={`meta-${p.id}`}>
                  {auditedLabel(p)}
                  {p.run_in_progress &&
                    " · Organising or auditing now — it can be deleted when that finishes"}
                </div>
              </div>
              {/* Quiet on purpose: the row's job is Open, and a destructive
                  action should not compete with it for attention. The
                  confirmation is where it becomes explicit. */}
              <button
                type="button"
                className="curr-delete"
                disabled={p.run_in_progress}
                aria-label={`Delete ${p.title || p.id}`}
                aria-describedby={p.run_in_progress ? `meta-${p.id}` : undefined}
                onClick={() => {
                  setDeletedNote(null);
                  setToDelete(p);
                }}
              >
                Delete
              </button>
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

      {deletedNote && (
        <p className="home-note" role="status">
          {deletedNote}
        </p>
      )}

      {toDelete && (
        <DeleteDialog
          project={toDelete}
          onCancel={() => setToDelete(null)}
          onDeleted={(title, keepDays) => {
            setToDelete(null);
            setDeletedNote(
              `Deleted “${title}”. It can be recovered for ${keepDays} days.`,
            );
            void load();
          }}
        />
      )}

      {loaded && curricula.length > 0 && reviewable.length === 0 && (
        <p className="home-note">
          None of these have been audited yet. Opening one will show you what it
          still needs before Loom can report on it.
        </p>
      )}

      {/* The desktop promise ("nothing is uploaded") is false when hosted, and
          a privacy claim is the one sentence that must never be wrong. */}
      {storage && IS_HOSTED && (
        <p className="home-note home-storage">
          Curricula and reports are kept on the Loom service the operator runs.
          To read them, Loom sends document text to the operator’s hosted model.
        </p>
      )}
      {storage && !IS_HOSTED && (
        <p className="home-note home-storage">
          Curricula, settings and reports are stored on this computer at{" "}
          <code>{storage.data_root}</code>. Nothing is uploaded anywhere.
        </p>
      )}
    </div>
  );
}
