import type { OutputsTree } from "../types";

/** Synthetic paths handled by RunReview (not real files). */
export const VIEW_UNITS = "__units__";
export const VIEW_GRAPH = "__graph__";
export const VIEW_PATHS = "__paths__";

/** One reviewed curriculum document, as the rail needs to show it. */
export interface NavDoc {
  doc_id: string;
  title: string;
  /** False when the document is missing a part its type is expected to have. */
  gate_pass: boolean;
}

interface Props {
  outputs: OutputsTree;
  activePath: string | null;
  onSelect: (path: string, type?: string) => void;
  /** When true, show Curriculum graph as an available View option. */
  hasGraph?: boolean;
  graphLabel?: string;
  /** How many of the eight checks ran — drives the badge. */
  nPathsRan?: number;
  /** Engineering mode: keep unavailable options visible for diagnosis. */
  advanced?: boolean;
  /** The curriculum documents reviewed in each unit, keyed by unit id. Empty
      until the artifact rung has run. */
  docsByUnit?: Record<string, NavDoc[]>;
  /** Opens one document with the parts of it that were reviewed. Takes the
      unit too: a course-level document is filed under every unit it serves,
      and each of those units reviewed it separately. */
  onSelectDoc?: (docId: string, unitId: string) => void;
  activeDoc?: { docId: string; unitId: string | null } | null;
}

// Left-rail navigation. Reports (incl. Global audit) come first; a dedicated
// View group sits *below* those so reviewers open the graph / unit quality
// from Review — not from Next Steps.
export function OutputNav({
  outputs,
  activePath,
  onSelect,
  hasGraph = false,
  graphLabel = "Curriculum graph",
  nPathsRan = 0,
  advanced = false,
  docsByUnit = {},
  onSelectDoc,
  activeDoc = null,
}: Props) {
  const items = (files: OutputsTree["plates"]) =>
    files.map((f) => (
      <button
        key={f.path}
        className={`nav-item ${activePath === f.path ? "active" : ""}`}
        onClick={() => onSelect(f.path, f.type)}
      >
        <span>{f.label}</span>
        {f.type === "pdf" && <span className="tag">pdf</span>}
      </button>
    ));

  const section = (
    title: string,
    files: OutputsTree["plates"],
    open: boolean
  ) =>
    files.length > 0 && (
      <details className="nav-group" open={open}>
        <summary>
          <span>{title}</span>
          <span className="tag">{files.length}</span>
        </summary>
        {items(files)}
      </details>
    );

  const hasActivePlateInLayers = outputs.layers.some(
    (f) => f.path === activePath
  );
  const nTeachers = outputs.units.filter(
    (u) => (u.teacher_files?.length ?? 0) > 0
  ).length;

  return (
    <div className="panel">
      <div className="panel-head">Results</div>
      <div className="panel-body nav">
        {/* Reports first so Global audit is above View options. */}
        {section("Reports", outputs.plates, true)}

        <details className="nav-group" open>
          <summary>
            <span>View</span>
            <span className="tag">
              {3 + (hasGraph ? 1 : 0) + (nTeachers > 0 ? 1 : 0)}
            </span>
          </summary>
          <button
            className={`nav-item ${activePath === VIEW_UNITS ? "active" : ""}`}
            onClick={() => onSelect(VIEW_UNITS)}
            title="How complete and how strong each unit is"
          >
            <span>Unit quality</span>
            <span className="tag">units</span>
          </button>
          <button
            className={`nav-item ${activePath === VIEW_PATHS ? "active" : ""}`}
            onClick={() => onSelect(VIEW_PATHS)}
            title="The eight checks Loom runs, and what each one found"
          >
            <span>What we checked for</span>
            <span className="tag">
              {nPathsRan > 0 ? `${nPathsRan}/8` : "checks"}
            </span>
          </button>
          {/* Only offered when there is a graph to open. A permanently greyed
              row badged "none" reads as something broken rather than as a
              feature this audit simply did not produce. */}
          {(hasGraph || advanced) && (
            <button
              className={`nav-item ${activePath === VIEW_GRAPH ? "active" : ""}`}
              onClick={() => onSelect(VIEW_GRAPH)}
              disabled={!hasGraph}
              title={
                hasGraph
                  ? "How materials, lessons and assessments connect"
                  : "Not available for this audit"
              }
            >
              <span>{graphLabel}</span>
              <span className="tag">{hasGraph ? "graph" : "none"}</span>
            </button>
          )}
          {nTeachers > 0 && (
            <button
              className={`nav-item ${activePath === VIEW_UNITS ? "active" : ""}`}
              onClick={() => onSelect(VIEW_UNITS)}
              title="Open Unit quality, then a unit, for its teacher packet"
            >
              <span>Teacher packets</span>
              <span className="tag">{nTeachers}u</span>
            </button>
          )}
        </details>

        {/* The Layer 0/1/2 and rung reports are the audit's working papers:
            the same findings one stage earlier, before they were written up
            for a reader. Someone reviewing a curriculum wants what was found,
            not the machinery that found it, so these sit behind ?advanced=1
            rather than in the default rail -- still there to diagnose a run
            with, just not competing with the reports for attention. */}
        {advanced &&
          section("How it was checked", outputs.layers, hasActivePlateInLayers)}
        {section("PDF", outputs.pdfs, false)}

        {/* Per unit: the curriculum documents first, then the files Loom
            wrote about them. Documents lead because they are what a reviewer
            came to look at -- opening one shows the document beside the parts
            of it that were reviewed, which is the whole point of the audit.
            The generated packets are the write-up of that and sit under a
            sub-group, present but not first in the eye's path. */}
        {outputs.units.length > 0 && (
          <details className="nav-group" open={false}>
            <summary>
              <span>Unit documents</span>
              <span className="tag">{outputs.units.length}</span>
            </summary>
            {outputs.units.map((u) => {
              const docs = docsByUnit[u.unit_id] ?? [];
              const generated = [
                ...(u.files ?? []),
                ...(u.teacher_files ?? []),
              ];
              return (
                <details key={u.unit_id} className="nav-group nav-unit">
                  <summary>
                    <span>{u.title || u.unit_id}</span>
                    {/* Counts the documents when there are any, because that is
                        what the group now leads with. Falls back to the file
                        count so a unit audited before the artifact rung ran
                        still reports something truthful. */}
                    <span className="tag">
                      {docs.length || generated.length}
                    </span>
                  </summary>
                  {docs.map((d) => {
                    const on =
                      activeDoc?.docId === d.doc_id &&
                      activeDoc?.unitId === u.unit_id;
                    return (
                      <button
                        key={d.doc_id}
                        className={`nav-item ${on ? "active" : ""}`}
                        onClick={() => onSelectDoc?.(d.doc_id, u.unit_id)}
                        title="The document, and the parts of it that were reviewed"
                      >
                        <span>{d.title || d.doc_id}</span>
                        {/* Only the gaps are badged. Tagging every document
                            "complete" would put a label on all of them and
                            leave the reviewer no better off than no labels. */}
                        {!d.gate_pass && <span className="tag warn">gaps</span>}
                      </button>
                    );
                  })}
                  {generated.length > 0 && (
                    <details className="nav-group nav-generated">
                      <summary>
                        <span>Generated files</span>
                        <span className="tag">{generated.length}</span>
                      </summary>
                      {generated.map((f) => (
                        <button
                          key={f.path}
                          className={`nav-item ${activePath === f.path ? "active" : ""}`}
                          onClick={() => onSelect(f.path, f.type)}
                        >
                          <span>{f.label}</span>
                          {f.type === "pdf" && (
                            <span className="tag">pdf</span>
                          )}
                        </button>
                      ))}
                    </details>
                  )}
                  {!docs.length && !generated.length && (
                    <p className="nav-empty">Nothing recorded for this unit.</p>
                  )}
                </details>
              );
            })}
          </details>
        )}
      </div>
    </div>
  );
}
