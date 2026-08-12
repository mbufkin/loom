import { useMemo } from "react";
import { defineChart, dot, link, text } from "@tanstack/charts";
import { treeLayout } from "@tanstack/charts/hierarchy/tree";
import { Chart } from "@tanstack/charts/react";
import { scaleLinear } from "@tanstack/charts/scales/linear";
import { scaleOrdinal } from "@tanstack/charts/scales/ordinal";
import { tooltip } from "@tanstack/charts/tooltip";
import rows from "./treeData.json";

type TreeRow = {
  path: string;
  kind: string;
  label: string;
};

/** Kind → paint. Kept local so legend HTML and chart ordinal scale stay in sync. */
const KIND_DOMAIN = [
  "course",
  "unit",
  "lesson",
  "material",
  "assessment",
  "uses",
] as const;

const KIND_RANGE = [
  "#0f766e",
  "#0f766e",
  "#1d4ed8",
  "#c2410c",
  "#5b21b6",
  "#78716c",
] as const;

function kindOf(node: { data: TreeRow | null }): string {
  return node.data?.kind ?? "uses";
}

function labelOf(node: { data: TreeRow | null; name: string }): string {
  return node.data?.label ?? node.name;
}

export function App() {
  const definition = useMemo(() => {
    // Official Charts tidy-tree transform (docs: networks-and-hierarchies).
    // Shared HAS-PART edges are duplicated under each Class so the tree
    // matches the graph (tidy trees cannot share one child across parents).
    const hierarchy = treeLayout(rows as TreeRow[], {
      path: "path",
      delimiter: "/",
      orientation: "left",
      // denser breadth — many duplicated shared materials
      nodeSize: [18, 240],
    });

    const color = scaleOrdinal<string, string>()
      .domain([...KIND_DOMAIN])
      .range([...KIND_RANGE]);

    return defineChart({
      marks: [
        link(hierarchy.links, {
          x1: "x1",
          y1: "y1",
          x2: "x2",
          y2: "y2",
          key: "id",
          stroke: "#a8a29e",
          strokeOpacity: 0.85,
          strokeWidth: 1.4,
        }),
        // Dot fill is paint-only (string); use color channel + ordinal scale.
        dot(hierarchy.nodes, {
          x: "x",
          y: "y",
          key: "id",
          r: 4,
          color: kindOf,
          stroke: "#fffcf7",
          strokeWidth: 1.25,
        }),
        text(hierarchy.nodes, {
          x: "x",
          y: "y",
          text: labelOf,
          key: "id",
          fill: (node) => color(kindOf(node)) ?? "#78716c",
          fontSize: 10,
          fontWeight: 500,
          // Spine nodes (course→unit) share y; nudge so labels don't stack.
          anchor: (node) => (node.internal ? "end" : "start"),
          dx: (node) => (node.internal ? -7 : 7),
          dy: (node) => (node.depth === 0 ? -12 : node.depth === 1 ? 12 : 0),
        }),
      ],
      x: { scale: scaleLinear, nice: true },
      y: { scale: scaleLinear, nice: true },
      color: { scale: color },
      guides: false,
      margin: { top: 28, right: 340, bottom: 28, left: 180 },
      tooltip,
    });
  }, []);

  return (
    <div className="page">
      <h1>Cattle unit — TanStack Charts tidy tree</h1>
      <p className="sub">
        Two-unit course · cattle + external anatomy · shared materials duplicated
        under each Class · anti-mangle PASS · lab viz (not Loom UI)
      </p>
      <div className="chart-wrap">
        <Chart
          definition={definition}
          height={2200}
          ariaLabel="Cattle CTE graph hierarchy tree"
        />
      </div>
      <div className="legend">
        <span>
          <i className="swatch" style={{ background: "#0f766e" }} /> Course /
          Unit
        </span>
        <span>
          <i className="swatch" style={{ background: "#1d4ed8" }} /> Lesson
        </span>
        <span>
          <i className="swatch" style={{ background: "#c2410c" }} /> Material
          (describes / spanIn)
        </span>
        <span>
          <i className="swatch" style={{ background: "#5b21b6" }} /> Assessment
        </span>
        <span>
          <i className="swatch" style={{ background: "#78716c" }} /> uses
        </span>
      </div>
    </div>
  );
}
