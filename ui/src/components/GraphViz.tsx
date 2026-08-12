import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";

export interface GraphVizNode {
  id: string;
  type?: string;
  name?: string;
  role?: string;
  source_file?: string;
}

export interface GraphVizEdge {
  from: string;
  to: string;
  rel?: string;
}

export type GraphEdgeFilter = "all" | "hasPart" | "describes";
export type GraphVizMode = "overview" | "unit";

interface Props {
  nodes: GraphVizNode[];
  edges: GraphVizEdge[];
  mode?: GraphVizMode;
  edgeFilter?: GraphEdgeFilter;
  focusId?: string | null;
  onNodeClick?: (node: GraphVizNode) => void;
  caption?: string;
}

type Col = "material" | "lesson" | "assessment" | "spine";

function colFor(n: GraphVizNode, mode: GraphVizMode): Col | "skip" {
  const t = (n.type || "").toLowerCase();
  const id = n.id || "";
  // Unit drill-down: hide Course (noise); keep unit as spine header.
  if (mode === "unit" && (t === "course" || id.startsWith("course:"))) {
    return "skip";
  }
  if (t === "material" || id.startsWith("material:")) return "material";
  if (t === "lesson" || id.startsWith("lesson:")) return "lesson";
  if (t === "assessment" || id.startsWith("assessment:")) return "assessment";
  // Overview: units sit in the Units column. Unit drill-down: unit/grouping = spine.
  if (t === "unit" || id.startsWith("unit:")) {
    return mode === "overview" ? "lesson" : "spine";
  }
  if (t === "lessongrouping" || t === "course" || id.startsWith("course:")) {
    return "spine";
  }
  return "spine";
}

function lessonSortKey(n: GraphVizNode): number {
  const m = (n.id || n.name || "").match(/l(\d+)/i) || (n.name || "").match(/(\d+)/);
  return m ? parseInt(m[1], 10) : 999;
}

function roleSortKey(role?: string): number {
  const order = [
    "teacher_edition",
    "learn_student",
    "practice_student",
    "succeed_student",
    "other",
  ];
  const i = order.indexOf(role || "other");
  return i < 0 ? order.length : i;
}

function rolePrefix(role?: string): string {
  switch (role) {
    case "teacher_edition":
      return "TE · ";
    case "learn_student":
      return "Learn · ";
    case "practice_student":
      return "Practice · ";
    case "succeed_student":
      return "Succeed · ";
    default:
      return role ? `${role.replace(/_/g, " ")} · ` : "";
  }
}

function shortLabel(n: GraphVizNode): string {
  const raw =
    n.name ||
    n.source_file ||
    n.id.replace(/^[^:]+:/, "").replace(/^.*:/, "");
  const base = raw.split("/").pop() || raw;
  const cleaned = base
    .replace(/^doc_[a-f0-9]+_/i, "")
    .replace(/_/g, " ")
    .replace(/\.(txt|md|pdf)$/i, "");
  const prefix =
    (n.type || "").toLowerCase() === "material" ? rolePrefix(n.role) : "";
  const full = `${prefix}${cleaned}`;
  return full.length > 28 ? `${full.slice(0, 26)}…` : full;
}

interface LaidOut {
  id: string;
  node: GraphVizNode;
  x: number;
  y: number;
  col: Col;
  w: number;
  h: number;
}

const COL_X: Record<Col, number> = {
  material: 24,
  lesson: 300,
  assessment: 576,
  spine: 300,
};

/**
 * Layered belonging DAG (Materials → Lessons → Assessments).
 *
 * Research-backed choices for this space:
 * - Hierarchic/layered layout for part-of DAGs (not force-directed)
 * - Progressive disclosure via overview vs unit mode
 * - Stable sort so lesson order and roles stay scannable
 */
export function GraphViz({
  nodes,
  edges,
  mode = "unit",
  edgeFilter = "all",
  focusId,
  onNodeClick,
  caption,
}: Props) {
  const [scale, setScale] = useState(1);
  const [tx, setTx] = useState(12);
  const [ty, setTy] = useState(8);
  const [hoverId, setHoverId] = useState<string | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const drag = useRef<{
    ox: number;
    oy: number;
    tx: number;
    ty: number;
  } | null>(null);

  // Reset pan/zoom when switching unit or mode so the new graph is framed.
  useEffect(() => {
    setScale(1);
    setTx(12);
    setTy(8);
    setHoverId(null);
  }, [mode, nodes]);

  const visibleEdges = useMemo(() => {
    return edges.filter((e) => {
      const rel = (e.rel || "hasPart").toLowerCase();
      if (edgeFilter === "all") return true;
      if (edgeFilter === "hasPart") return rel === "haspart";
      if (edgeFilter === "describes") return rel === "describes";
      return true;
    });
  }, [edges, edgeFilter]);

  const laid = useMemo(() => {
    const materials: GraphVizNode[] = [];
    const lessons: GraphVizNode[] = [];
    const assessments: GraphVizNode[] = [];
    const spine: GraphVizNode[] = [];

    for (const n of nodes) {
      if (!n?.id) continue;
      const c = colFor(n, mode);
      if (c === "skip") continue;
      if (c === "material") materials.push(n);
      else if (c === "lesson") lessons.push(n);
      else if (c === "assessment") assessments.push(n);
      else spine.push(n);
    }

    lessons.sort((a, b) => lessonSortKey(a) - lessonSortKey(b));
    materials.sort(
      (a, b) =>
        roleSortKey(a.role) - roleSortKey(b.role) ||
        shortLabel(a).localeCompare(shortLabel(b))
    );
    assessments.sort((a, b) => shortLabel(a).localeCompare(shortLabel(b)));

    // Overview: course spine left-ish, units as a lesson-column list.
    if (mode === "overview") {
      const out: LaidOut[] = [];
      const rowH = 40;
      const nodeW = 220;
      const nodeH = 32;
      spine.forEach((n, i) => {
        out.push({
          id: n.id,
          node: n,
          x: 40,
          y: 36 + i * rowH,
          col: "spine",
          w: nodeW,
          h: nodeH,
        });
      });
      lessons.sort((a, b) => shortLabel(a).localeCompare(shortLabel(b)));
      lessons.forEach((n, i) => {
        out.push({
          id: n.id,
          node: n,
          x: 340,
          y: 36 + i * rowH,
          col: "lesson",
          w: 280,
          h: nodeH,
        });
      });
      return out;
    }

    // Unit mode: spine header (unit) above; three semantic columns below.
    // Materials (teacher edition, succeed student, …) always get left-column
    // nodes — never inventory-only.
    const out: LaidOut[] = [];
    const rowH = 42;
    const nodeW = 230;
    const nodeH = 34;
    const headerH = spine.length ? 52 : 0;

    spine.forEach((n, i) => {
      out.push({
        id: n.id,
        node: n,
        x: 300,
        y: 28 + i * 40,
        col: "spine",
        w: 220,
        h: 32,
      });
    });

    const top = 28 + headerH + 8;
    // Align materials/assessments near first linked lesson when possible.
    const lessonY = new Map<string, number>();
    lessons.forEach((n, i) => {
      const y = top + i * rowH;
      lessonY.set(n.id, y);
      out.push({
        id: n.id,
        node: n,
        x: COL_X.lesson,
        y,
        col: "lesson",
        w: nodeW,
        h: nodeH,
      });
    });

    const placeBeside = (list: GraphVizNode[], col: Col, fallbackStart: number) => {
      const usedY = new Set<number>();
      list.forEach((n, i) => {
        // Prefer Y of first connected lesson via visible edges.
        let y = top + (fallbackStart + i) * rowH;
        for (const e of visibleEdges) {
          const other =
            e.from === n.id ? e.to : e.to === n.id ? e.from : null;
          if (other && lessonY.has(other)) {
            y = lessonY.get(other)!;
            break;
          }
        }
        while (usedY.has(y)) y += rowH;
        usedY.add(y);
        out.push({
          id: n.id,
          node: n,
          x: COL_X[col],
          y,
          col,
          w: nodeW,
          h: nodeH,
        });
      });
    };

    placeBeside(materials, "material", 0);
    placeBeside(assessments, "assessment", 0);
    return out;
  }, [nodes, mode, visibleEdges]);

  const byId = useMemo(() => {
    const m = new Map<string, LaidOut>();
    for (const L of laid) m.set(L.id, L);
    return m;
  }, [laid]);

  const height = useMemo(() => {
    if (!laid.length) return 200;
    return Math.max(220, Math.max(...laid.map((L) => L.y + L.h)) + 56);
  }, [laid]);

  const onWheel = useCallback((e: ReactWheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.08 : 0.92;
    setScale((s) => Math.min(2.5, Math.max(0.45, s * factor)));
  }, []);

  const onPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLDivElement>) => {
      if ((e.target as Element).closest("[data-node]")) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      drag.current = { ox: e.clientX, oy: e.clientY, tx, ty };
    },
    [tx, ty]
  );

  const onPointerMove = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    if (!drag.current) return;
    const d = drag.current;
    setTx(d.tx + (e.clientX - d.ox));
    setTy(d.ty + (e.clientY - d.oy));
  }, []);

  const onPointerUp = useCallback((e: ReactPointerEvent<HTMLDivElement>) => {
    drag.current = null;
    try {
      e.currentTarget.releasePointerCapture(e.pointerId);
    } catch {
      /* already released */
    }
  }, []);

  // Non-passive wheel so preventDefault actually stops page scroll over canvas.
  useEffect(() => {
    const el = canvasRef.current;
    if (!el) return;
    const handler = (ev: WheelEvent) => {
      ev.preventDefault();
      const factor = ev.deltaY < 0 ? 1.08 : 0.92;
      setScale((s) => Math.min(2.5, Math.max(0.45, s * factor)));
    };
    el.addEventListener("wheel", handler, { passive: false });
    return () => el.removeEventListener("wheel", handler);
  }, []);

  const hover = hoverId ? byId.get(hoverId) : null;

  if (!nodes.length) {
    return (
      <div className="graph-viz empty">No nodes to draw for this graph.</div>
    );
  }

  const counts = useMemo(() => {
    let material = 0;
    let lesson = 0;
    let assessment = 0;
    for (const L of laid) {
      if (L.col === "material") material += 1;
      else if (L.col === "lesson") lesson += 1;
      else if (L.col === "assessment") assessment += 1;
    }
    return { material, lesson, assessment };
  }, [laid]);

  const colLabels =
    mode === "overview"
      ? (
          <>
            <text x={40} y={18} className="graph-viz-col">
              Course
            </text>
            <text x={340} y={18} className="graph-viz-col">
              Units
            </text>
          </>
        )
      : (
          <>
            <text x={COL_X.material} y={18} className="graph-viz-col">
              Materials ({counts.material})
            </text>
            <text x={COL_X.lesson} y={18} className="graph-viz-col">
              Lessons ({counts.lesson})
            </text>
            <text x={COL_X.assessment} y={18} className="graph-viz-col">
              Assessments ({counts.assessment})
            </text>
          </>
        );

  return (
    <div className="graph-viz">
      <div className="graph-viz-toolbar mono">
        <span className="graph-viz-legend">
          <span className="lg haspart" /> hasPart
          <span className="lg describes" /> describes
        </span>
        <span className="graph-viz-actions">
          <button type="button" onClick={() => setScale((s) => Math.min(2.5, s * 1.15))}>
            +
          </button>
          <button type="button" onClick={() => setScale((s) => Math.max(0.45, s / 1.15))}>
            −
          </button>
          <button
            type="button"
            onClick={() => {
              setScale(1);
              setTx(12);
              setTy(8);
            }}
          >
            Reset
          </button>
        </span>
      </div>
      <div
        ref={canvasRef}
        className="graph-viz-canvas"
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
      >
        <svg
          width="100%"
          height={Math.min(520, Math.max(280, height))}
          viewBox={`0 0 820 ${height}`}
          role="img"
          aria-label="Curriculum belonging graph"
        >
          <g transform={`translate(${tx},${ty}) scale(${scale})`}>
            {colLabels}

            {visibleEdges.map((e, i) => {
              const a = byId.get(e.from);
              const b = byId.get(e.to);
              if (!a || !b) return null;
              // Draw left→right when possible for readable flow.
              const left = a.x <= b.x ? a : b;
              const right = a.x <= b.x ? b : a;
              const x1 = left.x + left.w;
              const y1 = left.y + left.h / 2;
              const x2 = right.x;
              const y2 = right.y + right.h / 2;
              const mx = (x1 + x2) / 2;
              const active =
                hoverId === e.from ||
                hoverId === e.to ||
                focusId === e.from ||
                focusId === e.to;
              const rel = (e.rel || "hasPart").toLowerCase();
              return (
                <path
                  key={`${e.from}-${e.to}-${e.rel || ""}-${i}`}
                  d={`M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`}
                  className={`graph-viz-edge${active ? " active" : ""}${
                    rel === "describes" ? " describes" : ""
                  }`}
                  fill="none"
                />
              );
            })}

            {laid.map((L) => {
              const active = focusId === L.id || hoverId === L.id;
              return (
                <g
                  key={L.id}
                  data-node={L.id}
                  className={`graph-viz-node col-${L.col}${active ? " active" : ""}`}
                  transform={`translate(${L.x},${L.y})`}
                  onMouseEnter={() => setHoverId(L.id)}
                  onMouseLeave={() => setHoverId(null)}
                  onClick={(ev) => {
                    ev.stopPropagation();
                    onNodeClick?.(L.node);
                  }}
                  style={{ cursor: "pointer" }}
                >
                  <title>
                    {L.node.type || "node"}: {L.node.name || L.id}
                    {L.node.role ? ` (${L.node.role})` : ""}
                  </title>
                  <rect width={L.w} height={L.h} rx={4} ry={4} />
                  <text x={10} y={22}>
                    {shortLabel(L.node)}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      <div className="graph-viz-caption mono">
        {hover ? (
          <>
            <strong>{hover.node.type || "node"}</strong> ·{" "}
            {hover.node.name || hover.id}
            {hover.node.role ? ` · ${hover.node.role}` : ""}
          </>
        ) : (
          caption || "Drag to pan · scroll to zoom · click a node"
        )}
      </div>
    </div>
  );
}

/** Course → units overview (compact; drill into a unit for HAS-PART). */
export function overviewToVizNodes(
  projectId: string,
  units: {
    unit_id: string;
    n_lessons: number;
    n_materials: number;
    n_assessments: number;
  }[]
): { nodes: GraphVizNode[]; edges: GraphVizEdge[] } {
  const courseId = `course:${projectId}`;
  const nodes: GraphVizNode[] = [
    { id: courseId, type: "Course", name: projectId },
  ];
  const edges: GraphVizEdge[] = [];
  const sorted = [...units].sort((a, b) => a.unit_id.localeCompare(b.unit_id));
  for (const u of sorted) {
    const id = `unit:${u.unit_id}`;
    nodes.push({
      id,
      type: "Unit",
      name: `${u.unit_id} · ${u.n_lessons}L ${u.n_materials}m ${u.n_assessments}a`,
    });
    edges.push({ from: courseId, to: id, rel: "hasPart" });
  }
  return { nodes, edges };
}
