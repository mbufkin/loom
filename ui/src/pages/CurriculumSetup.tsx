import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, describeError } from "../lib/api";
import type { Project, RunPreflight, StorageInfo } from "../types";

/**
 * Setting up a curriculum: adding a new one, or finishing an existing one.
 *
 * One screen for both because they are the same checklist at different points.
 * The steps are not cosmetic — they reflect a real constraint in the pipeline:
 * `run-audit` prepares its run directory *before* ingest, and that preparation
 * needs `manifest.yaml` and `units/` to already exist, which ingest is what
 * creates. So a brand-new curriculum genuinely cannot go straight from
 * "documents dropped in" to "audited"; the organise step has to happen first.
 *
 * Rather than hide that, the checklist names it. It is also the step worth
 * pausing on: organising is model-driven and can mis-group files, and an audit
 * is long, so confirming the units first is both cheaper and more trustworthy.
 */
export function CurriculumSetup() {
  const { projectId } = useParams<{ projectId: string }>();
  const isNew = !projectId;

  const [project, setProject] = useState<Project | null>(null);
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [preflight, setPreflight] = useState<RunPreflight | null>(null);
  const [error, setError] = useState<{ message: string; detail: string } | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);

  const load = useCallback(async () => {
    try {
      const [ps, st, pf] = await Promise.all([
        api.projects(),
        api.storage().catch(() => null),
        api.canRun().catch(() => null),
      ]);
      setProject(ps.find((p) => p.id === projectId) ?? null);
      setStorage(st);
      setPreflight(pf);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoaded(true);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  const folder = storage
    ? `${storage.projects_root}\\${projectId ?? "<curriculum-name>"}`
    : null;

  if (!loaded) {
    return (
      <div className="home">
        <div className="panel">
          <div className="panel-body empty">Loading…</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="home">
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
      </div>
    );
  }

  const title = isNew ? "Add a curriculum" : project?.title || projectId;

  return (
    <div className="home">
      <div className="home-head">
        <h2>{title}</h2>
        <Link className="btn" to="/">
          Back to curricula
        </Link>
      </div>

      {!isNew && !project && (
        <div className="panel">
          <div className="panel-head">Not found</div>
          <div className="panel-body">
            <p>
              There is no curriculum called <code>{projectId}</code> on this
              computer.
            </p>
          </div>
        </div>
      )}

      <ol className="setup-steps">
        <li className={project ? "done" : ""}>
          <div className="setup-step-head">Make a folder for it</div>
          <p>
            Each curriculum is one folder. Create it inside{" "}
            {storage ? (
              <code>{storage.projects_root}</code>
            ) : (
              "your Loom data folder"
            )}
            , named in lowercase with hyphens — for example{" "}
            <code>my-district-2026</code>.
          </p>
        </li>

        <li className={project?.has_manifest ? "done" : ""}>
          <div className="setup-step-head">Put the documents in</div>
          <p>
            Inside that folder, create a <code>sources</code> folder and copy in
            the curriculum documents — pacing guides, lesson plans,
            assessments, teacher editions. PDF, Word, PowerPoint, Excel, HTML
            and plain text all work.
          </p>
          {folder && (
            <p className="mono setup-path">{folder}\sources</p>
          )}
        </li>

        <li className={project?.has_manifest ? "done" : ""}>
          <div className="setup-step-head">Let Loom organise them</div>
          <p>
            Loom reads every document and groups them into units, working out
            what each one is. This has to happen before a full audit can start.
          </p>
          {project?.has_manifest && (
            <p className="setup-ok">
              Done — this curriculum’s documents have been organised into units.
            </p>
          )}
        </li>

        <li className={project?.has_review_run ? "done" : ""}>
          <div className="setup-step-head">Run the audit</div>
          <p>
            Loom checks every unit against what a complete unit needs, and
            reports what is present, what is missing, and what needs your
            decision.
          </p>
          {preflight && !preflight.can_run && (
            <>
              <p className="err-message">
                This computer isn’t ready to run an audit yet.
              </p>
              {/* A link to the fix, not a restatement of the problem: Setup
                  names each requirement and gives the command for this OS. */}
              <p>
                <Link className="btn" to="/setup">
                  Finish setup
                </Link>
              </p>
            </>
          )}
          {preflight?.can_run && preflight.can_read_pdf === false && (
            <p className="err-message">
              PDF documents can’t be read on this computer yet.{" "}
              <Link to="/setup">Finish setup</Link> if any of your files are
              PDFs.
            </p>
          )}
          {project?.has_review_run && (
            <p className="setup-ok">
              Done —{" "}
              <Link to={`/review?project=${project.id}`}>open the results</Link>
              .
            </p>
          )}
        </li>
      </ol>

      <div className="panel">
        <div className="panel-head">School calendar — optional</div>
        <div className="panel-body">
          <p>
            {project?.has_calendar
              ? "This curriculum has a school calendar, so its pacing plan is dated."
              : "Without a school calendar, units are placed in order rather than on dates. Everything else in the audit is the same."}{" "}
            <Link to="/calendars">More about calendars</Link>
          </p>
        </div>
      </div>

      {/* Said outright: the steps above are still done outside the app. An
          upload button that did not exist yet would be worse than a sentence
          that tells you where the folder is. */}
      <p className="home-note">
        Steps one to three are done in your file manager and a terminal for now.
        Adding documents from inside the app — and a progress screen for the
        audit — is the next piece of work.
      </p>
    </div>
  );
}
