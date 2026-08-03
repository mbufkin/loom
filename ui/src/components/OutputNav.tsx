import type { OutputsTree } from "../types";

interface Props {
  outputs: OutputsTree;
  activePath: string | null;
  onSelect: (path: string, type?: string) => void;
}

// Left-rail navigation. Each section is a collapsible <details> so the rail
// stays readable as the number of plates grows: the primary "Course plates" and
// "Units" sections stay open by default, while the denser stage/PDF sections
// start collapsed. Native <details> keeps this accessible and state-free.
export function OutputNav({ outputs, activePath, onSelect }: Props) {
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

  return (
    <div className="panel">
      <div className="panel-head">Outputs</div>
      <div className="panel-body nav">
        <details className="nav-group" open>
          <summary>
            <span>Units</span>
            <span className="tag">{outputs.units.length}</span>
          </summary>
          <button
            className={`nav-item ${activePath === "__units__" ? "active" : ""}`}
            onClick={() => onSelect("__units__")}
          >
            <span>Unit heatmap</span>
            <span className="tag">heatmap</span>
          </button>
        </details>
        {section("Course plates", outputs.plates, true)}
        {section("Stage reports", outputs.layers, hasActivePlateInLayers)}
        {section("PDF", outputs.pdfs, false)}
      </div>
    </div>
  );
}
