import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { RunProgress } from "../components/RunProgress";
import { api, describeError } from "../lib/api";
import { usePreflight } from "../lib/usePreflight";
import type {
  DocumentList,
  Project,
  ProposedUnits,
  RunStatus,
  StorageInfo,
} from "../types";

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
 *
 * Every step is now done here rather than in a file manager and a terminal.
 * The folder paths are still shown, because the folder is real and someone who
 * prefers Explorer should not be locked out of it — but nobody has to go there.
 */

/** Turn what someone typed into a folder name the server will accept.
 *
 * Done here as well as on the server, for different reasons: the server
 * validates because the value becomes a directory name and a subprocess
 * argument, and this one *shows* the result while typing, so "Ms. O'Brien —
 * Ag 2026" visibly becomes `ms-obrien-ag-2026` instead of being typed, sent,
 * and rejected.
 */
function slugify(raw: string): string {
  return raw
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "") // strip accents: "Peña" -> "pena"
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Join a path with the separator the reported root already uses.
 *
 * The root comes from the server, so it is native: a backslashed Windows path
 * or a slashed POSIX one. Hardcoding "\\" rendered `/Users/me/Loom/projects\my-
 * district` on macOS and Linux — a path no file manager would accept, shown to
 * someone being told where their documents live.
 */
function joinPath(root: string, ...parts: string[]): string {
  const sep = root.includes("\\") ? "\\" : "/";
  return [root, ...parts].join(sep);
}

/** "1 document", "6 documents" — as one string, not three JSX children.
 *
 * Written out because `{n} document{n === 1 ? "" : "s"}` renders "document"
 * and "s" as separate text nodes, and the accessibility tree joins those with
 * a space: the row a sighted user reads as "6 documents" is announced as
 * "6 document s".
 */
function plural(n: number, word: string, suffix = "s"): string {
  return `${n} ${word}${n === 1 ? "" : suffix}`;
}

function humanBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${Math.round(n / 1024)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

/** What happened to one file while it was being added. */
interface UploadState {
  name: string;
  status: "uploading" | "done" | "error";
  error?: string;
}

export function CurriculumSetup() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const isNew = !projectId;

  const [project, setProject] = useState<Project | null>(null);
  const [storage, setStorage] = useState<StorageInfo | null>(null);
  const [docs, setDocs] = useState<DocumentList | null>(null);
  const [units, setUnits] = useState<ProposedUnits | null>(null);
  const [error, setError] = useState<{ message: string; detail: string } | null>(
    null,
  );
  const [loaded, setLoaded] = useState(false);
  // Shared with Setup and Settings — see lib/usePreflight.
  const { preflight, refresh: refreshPreflight } = usePreflight();

  // Step 1 — naming a new curriculum.
  const [typedName, setTypedName] = useState("");
  const [creating, setCreating] = useState(false);
  const slug = slugify(typedName);

  // Step 2 — adding documents.
  const [uploads, setUploads] = useState<UploadState[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);

  // Steps 3 and 4 — organise, then audit. Both are tracked runs, polled the
  // same way; kept apart so an audit's progress cannot be shown for an
  // organise, which has no pipeline stages.
  const [organiseRun, setOrganiseRun] = useState<RunStatus | null>(null);
  const [auditRun, setAuditRun] = useState<RunStatus | null>(null);
  const pollRef = useRef<number | null>(null);
  const [expandedUnit, setExpandedUnit] = useState<string | null>(null);

  const stopPoll = useCallback(() => {
    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);
  // A run outlives this screen on the server, but the interval must not: a
  // timer still firing after unmount sets state on a dead component.
  useEffect(() => stopPoll, [stopPoll]);

  const loadProjectState = useCallback(
    async (id: string) => {
      const [ps, d, u] = await Promise.all([
        api.projects(),
        api.documents(id).catch(() => null),
        api.units(id).catch(() => null),
      ]);
      setProject(ps.find((p) => p.id === id) ?? null);
      setDocs(d);
      setUnits(u);
    },
    [],
  );

  const load = useCallback(async () => {
    try {
      const st = await api.storage().catch(() => null);
      setStorage(st);
      await refreshPreflight();
      if (projectId) await loadProjectState(projectId);
      setError(null);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setLoaded(true);
    }
  }, [projectId, refreshPreflight, loadProjectState]);

  useEffect(() => {
    void load();
  }, [load]);

  // --- Step 1: create -------------------------------------------------------

  const create = useCallback(async () => {
    if (!slug || creating) return;
    setCreating(true);
    setError(null);
    try {
      const made = await api.createProject(slug, typedName.trim());
      // Move to the curriculum's own URL so the rest of the checklist is about
      // a real folder, and so a reload lands back in the same place.
      navigate(`/curricula/${made.id}`);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setCreating(false);
    }
  }, [slug, typedName, creating, navigate]);

  // --- Step 2: documents ----------------------------------------------------

  const addFiles = useCallback(
    async (files: FileList | null) => {
      if (!projectId || !files || files.length === 0) return;
      const list = Array.from(files);
      setUploads(list.map((f) => ({ name: f.name, status: "uploading" })));
      setError(null);

      // Sequential, not Promise.all. Twenty parallel uploads of a scanned
      // teacher edition would compete for the same disk and give no useful
      // ordering to the progress list; one at a time also means a rejected
      // file names itself while the rest still go in.
      for (const file of list) {
        try {
          const res = await api.addDocument(projectId, file);
          setUploads((prev) =>
            prev.map((u) =>
              u.name === file.name
                ? {
                    ...u,
                    status: "done",
                    // Surfaced because the stored name is what appears in the
                    // list below, and silently differing from what was dropped
                    // is confusing.
                    error: res.renamed
                      ? `added as ${res.name} — a file of that name was already here`
                      : undefined,
                  }
                : u,
            ),
          );
        } catch (e) {
          const { message } = describeError(e);
          setUploads((prev) =>
            prev.map((u) =>
              u.name === file.name ? { ...u, status: "error", error: message } : u,
            ),
          );
        }
      }
      await loadProjectState(projectId);
    },
    [projectId, loadProjectState],
  );

  const removeDoc = useCallback(
    async (name: string) => {
      if (!projectId) return;
      try {
        await api.removeDocument(projectId, name);
        await loadProjectState(projectId);
      } catch (e) {
        setError(describeError(e));
      }
    },
    [projectId, loadProjectState],
  );

  // --- Steps 3 and 4: organise, then audit ----------------------------------

  const organise = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    try {
      stopPoll();
      const runId = await api.organise(projectId);
      setOrganiseRun({ runId, status: "running", exitCode: null, log: "" });
      pollRef.current = window.setInterval(async () => {
        try {
          const s = await api.runStatus(runId);
          setOrganiseRun(s);
          if (s.status !== "running") {
            stopPoll();
            // Reload regardless of exit code: a failed organise may still have
            // written a manifest, and if it did, the units panel has to show
            // what it actually says rather than the last good state.
            await loadProjectState(projectId);
          }
        } catch {
          stopPoll();
        }
      }, 1500);
    } catch (e) {
      setError(describeError(e));
    }
  }, [projectId, stopPoll, loadProjectState]);

  const runAudit = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    try {
      stopPoll();
      const runId = await api.startRun(projectId, []);
      setAuditRun({ runId, status: "running", exitCode: null, log: "" });
      pollRef.current = window.setInterval(async () => {
        try {
          const s = await api.runStatus(runId);
          setAuditRun(s);
          if (s.status !== "running") {
            stopPoll();
            await loadProjectState(projectId);
          }
        } catch {
          stopPoll();
        }
      }, 2000);
    } catch (e) {
      setError(describeError(e));
    }
  }, [projectId, stopPoll, loadProjectState]);

  // --- Render ---------------------------------------------------------------

  const folder = storage
    ? joinPath(storage.projects_root, projectId ?? "<curriculum-name>")
    : null;
  const sourcesFolder = folder ? joinPath(folder, "sources") : null;
  const organising = organiseRun?.status === "running";
  const auditing = auditRun?.status === "running";
  const busy = organising || auditing;
  const docCount = docs?.count ?? 0;
  const hasManifest = docs?.has_manifest ?? project?.has_manifest ?? false;
  const unreadable = (docs?.documents ?? []).filter((d) => !d.readable);

  if (!loaded) {
    return (
      <div className="home">
        <div className="panel">
          <div className="panel-body empty">Loading…</div>
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

      {error && (
        <div className="panel">
          <div className="panel-head">That didn’t work</div>
          <div className="panel-body">
            <p className="err-message">{error.message}</p>
            <details className="err-details">
              <summary>Technical details</summary>
              <pre>{error.detail}</pre>
            </details>
          </div>
        </div>
      )}

      {!isNew && !project && !hasManifest && docCount === 0 && (
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
        {/* ---- 1. the folder ---- */}
        <li className={isNew ? "" : "done"}>
          <div className="setup-step-head">Name it</div>
          {isNew ? (
            <>
              <p>
                Each curriculum is one folder. Give it a name — a district, a
                course, a year.
              </p>
              <div className="setup-name">
                <input
                  type="text"
                  value={typedName}
                  autoFocus
                  placeholder="My District 2026"
                  onChange={(e) => setTypedName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void create();
                  }}
                />
                <button
                  type="button"
                  className="btn-primary"
                  disabled={!slug || creating}
                  onClick={() => void create()}
                >
                  {creating ? "Creating…" : "Create"}
                </button>
              </div>
              {/* Shown while typing so the folder name is never a surprise. */}
              {slug && storage && (
                <p className="mono setup-path">
                  {joinPath(storage.projects_root, slug)}
                </p>
              )}
            </>
          ) : (
            <>
              <p>This curriculum’s folder is on this computer.</p>
              {folder && <p className="mono setup-path">{folder}</p>}
            </>
          )}
        </li>

        {/* ---- 2. the documents ---- */}
        <li className={docCount > 0 ? "done" : ""}>
          <div className="setup-step-head">Add the documents</div>
          <p>
            Pacing guides, lesson plans, assessments, teacher editions. PDF,
            Word, PowerPoint, Excel, HTML and plain text all work.
          </p>

          {isNew ? (
            <p className="setup-hint">Name the curriculum first.</p>
          ) : (
            <>
              {/* Drag-and-drop with buttons behind it, not instead of it: the
                  embedded browser in the desktop window does not always deliver
                  file drops, and a folder of documents is easier to pick whole
                  than to drag. */}
              <div
                className={`setup-drop${dragging ? " dragging" : ""}`}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragging(true);
                }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  void addFiles(e.dataTransfer.files);
                }}
              >
                <p>Drag documents here</p>
                <div className="setup-drop-actions">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => fileInput.current?.click()}
                  >
                    Choose files
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => folderInput.current?.click()}
                  >
                    Choose a folder
                  </button>
                </div>
                <input
                  ref={fileInput}
                  type="file"
                  multiple
                  hidden
                  onChange={(e) => {
                    void addFiles(e.target.files);
                    // Cleared so picking the same file twice fires onChange
                    // again — otherwise a re-pick after a removal does nothing.
                    e.target.value = "";
                  }}
                />
                <input
                  ref={folderInput}
                  type="file"
                  multiple
                  hidden
                  // Not in the React types, but supported by the embedded
                  // browser and by Chrome, Edge and Safari: lets someone hand
                  // over a whole curriculum folder in one go.
                  {...({ webkitdirectory: "" } as Record<string, string>)}
                  onChange={(e) => {
                    void addFiles(e.target.files);
                    e.target.value = "";
                  }}
                />
              </div>

              {uploads.length > 0 && (
                <ul className="setup-uploads">
                  {uploads.map((u) => (
                    <li key={u.name} className={u.status}>
                      <span className="up-name">{u.name}</span>
                      <span className="up-state">
                        {u.status === "uploading" && "adding…"}
                        {u.status === "done" && (u.error ? u.error : "added")}
                        {u.status === "error" && u.error}
                      </span>
                    </li>
                  ))}
                </ul>
              )}

              {docCount > 0 && (
                <>
                  <p className="setup-ok">
                    {plural(docCount, "document")} in this curriculum.
                  </p>
                  <ul className="setup-docs">
                    {(docs?.documents ?? []).map((d) => (
                      <li key={d.name} className={d.readable ? "" : "unreadable"}>
                        <span className="doc-name">{d.name}</span>
                        <span className="doc-size">{humanBytes(d.bytes)}</span>
                        <button
                          type="button"
                          className="doc-remove"
                          title="Remove this document"
                          disabled={busy}
                          onClick={() => void removeDoc(d.name)}
                        >
                          Remove
                        </button>
                      </li>
                    ))}
                  </ul>
                  {/* Said plainly rather than hidden: a file Loom cannot open
                      would otherwise sit in the folder looking audited. */}
                  {unreadable.length > 0 && (
                    <p className="err-message">
                      {plural(unreadable.length, "file")} can’t be read and will
                      be skipped: {unreadable.map((d) => d.name).join(", ")}
                    </p>
                  )}
                </>
              )}
              {sourcesFolder && (
                <p className="setup-hint">
                  They are copied into{" "}
                  <span className="mono">{sourcesFolder}</span>, so you can also
                  add them there directly.
                </p>
              )}
            </>
          )}
        </li>

        {/* ---- 3. organise ---- */}
        <li className={hasManifest ? "done" : ""}>
          <div className="setup-step-head">Let Loom organise them</div>
          <p>
            Loom reads every document and groups them into units, working out
            what each one is. This has to happen before a full audit can start.
          </p>

          {!isNew && docCount > 0 && (
            <div className="setup-actions">
              <button
                type="button"
                className={hasManifest ? "btn" : "btn-primary"}
                disabled={busy || !preflight?.can_run}
                onClick={() => void organise()}
              >
                {organising
                  ? "Organising…"
                  : hasManifest
                    ? "Organise again"
                    : "Organise documents"}
              </button>
            </div>
          )}
          {!isNew && docCount > 0 && !preflight?.can_run && (
            <p className="err-message">
              Organising needs a working model connection.{" "}
              <Link to="/setup">Finish setup</Link> first.
            </p>
          )}

          {organiseRun && (
            <div className="setup-runlog">
              {/* An organise run has no pipeline stages, so its log is the
                  progress. It is short and it names each document as it is
                  read, which is exactly what someone waiting wants to see. */}
              <div className="runlog">{organiseRun.log || "starting…"}</div>
              {organiseRun.status === "error" && (
                <p className="err-message">
                  Organising stopped before it finished. The log above says
                  where.
                </p>
              )}
            </div>
          )}

          {docs?.organise_stale && !organising && (
            <p className="err-message">
              Documents changed since these units were worked out. Organise
              again so the audit covers everything.
            </p>
          )}

          {units?.has_manifest && units.valid === false && (
            <p className="err-message">
              The units couldn’t be read back: {units.error} Organising again
              usually fixes it.
            </p>
          )}

          {units?.units && units.units.length > 0 && (
            <div className="setup-units">
              <p className="setup-ok">
                {plural(units.units.length, "unit")} — check these look right
                before starting an audit.
              </p>
              <ul>
                {units.units.map((u) => (
                  <li key={u.unit_id}>
                    <button
                      type="button"
                      className="unit-toggle"
                      onClick={() =>
                        setExpandedUnit(
                          expandedUnit === u.unit_id ? null : u.unit_id,
                        )
                      }
                    >
                      <span className="u-title">{u.title}</span>
                      <span className="u-metrics">
                        {plural(u.document_count, "document")}
                        {u.days > 0 ? ` · ${plural(u.days, "day")}` : ""}
                      </span>
                    </button>
                    {expandedUnit === u.unit_id && (
                      <ul className="unit-docs">
                        {u.documents.map((d) => (
                          <li key={d}>{d}</li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </li>

        {/* ---- 4. audit ---- */}
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

          {!isNew && preflight?.can_run && (
            <div className="setup-actions">
              <button
                type="button"
                className="btn-primary"
                disabled={busy || !hasManifest}
                onClick={() => void runAudit()}
              >
                {auditing ? "Auditing…" : "Start the audit"}
              </button>
              {!hasManifest && (
                <span className="setup-hint">Organise the documents first.</span>
              )}
            </div>
          )}

          {auditRun && (
            <div className="setup-runlog">
              <RunProgress
                progress={auditRun.progress}
                status={auditRun.status}
              />
              <details className="err-details">
                <summary>Run log</summary>
                <div className="runlog">{auditRun.log || "starting…"}</div>
              </details>
            </div>
          )}

          {project?.has_review_run && !auditing && (
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
    </div>
  );
}
