import type { OutputsTree } from "../types";

interface Props {
  outputs: OutputsTree;
  activePath: string | null;
  onSelect: (path: string, type?: string) => void;
}

// Left-rail navigation: course plates, then stage/layer reports, then a Units
// section (the unit rows themselves render in the main column). Mirrors the
// review-surface priority order from docs/OUTPUTS.md.
export function OutputNav({ outputs, activePath, onSelect }: Props) {
  const group = (title: string, files: OutputsTree["plates"]) =>
    files.length > 0 && (
      <div className="nav-group">
        <h3>{title}</h3>
        {files.map((f) => (
          <button
            key={f.path}
            className={`nav-item ${activePath === f.path ? "active" : ""}`}
            onClick={() => onSelect(f.path, f.type)}
          >
            <span>{f.label}</span>
            {f.type === "pdf" && <span className="tag">pdf</span>}
          </button>
        ))}
      </div>
    );

  return (
    <div className="panel">
      <div className="panel-head">Outputs</div>
      <div className="panel-body">
        {group("Course plates", outputs.plates)}
        {group("Stage reports", outputs.layers)}
        {group("PDF", outputs.pdfs)}
        <div className="nav-group">
          <h3>Units</h3>
          <button
            className={`nav-item ${activePath === "__units__" ? "active" : ""}`}
            onClick={() => onSelect("__units__")}
          >
            <span>Unit heatmap</span>
            <span className="tag">{outputs.units.length}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
