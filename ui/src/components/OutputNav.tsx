import type { OutputsTree } from "../types";

/** Synthetic paths handled by RunReview (not real files). */
export const VIEW_UNITS = "__units__";
export const VIEW_GRAPH = "__graph__";
export const VIEW_PATHS = "__paths__";

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

        {section("How it was checked", outputs.layers, hasActivePlateInLayers)}
        {section("PDF", outputs.pdfs, false)}

        {/* Per-unit file lists stay available but collapsed by default. */}
        {outputs.units.length > 0 && (
          <details className="nav-group" open={false}>
            <summary>
              <span>Unit files</span>
              <span className="tag">{outputs.units.length}</span>
            </summary>
            {outputs.units.map((u) => (
              <details key={u.unit_id} className="nav-group nav-unit">
                <summary>
                  <span>{u.title || u.unit_id}</span>
                  <span className="tag">
                    {(u.files?.length ?? 0) + (u.teacher_files?.length ?? 0)}
                  </span>
                </summary>
                {(u.files ?? []).map((f) => (
                  <button
                    key={f.path}
                    className={`nav-item ${activePath === f.path ? "active" : ""}`}
                    onClick={() => onSelect(f.path, f.type)}
                  >
                    <span>{f.label}</span>
                  </button>
                ))}
                {(u.teacher_files ?? []).map((f) => (
                  <button
                    key={f.path}
                    className={`nav-item ${activePath === f.path ? "active" : ""}`}
                    onClick={() => onSelect(f.path, f.type)}
                  >
                    <span>{f.label}</span>
                    <span className="tag">teacher</span>
                  </button>
                ))}
              </details>
            ))}
          </details>
        )}
      </div>
    </div>
  );
}
