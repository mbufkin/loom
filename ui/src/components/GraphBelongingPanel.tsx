import { useMemo, useState } from "react";
import type { GraphOverview, GraphUnitDetail, GraphUnitRollup } from "../types";
import {
  GraphViz,
  overviewToVizNodes,
  type GraphEdgeFilter,
  type GraphVizEdge,
  type GraphVizNode,
} from "./GraphViz";

interface Props {
  overview: GraphOverview | null;
  unitDetail?: GraphUnitDetail | null;
  selectedUnitId?: string | null;
  onOpenUnit: (unitId: string) => void;
  loading?: boolean;
}

/**
 * Build the unit DAG from HAS-PART, then guarantee every inventory row
 * (teacher edition / succeed student / lesson / assessment) is a node.
 * Best practice: the list panels and the SVG must show the same set —
 * inventory-only materials were easy to miss when HAS-PART typing drifted.
 */
function unitDetailToViz(detail: GraphUnitDetail): {
  nodes: GraphVizNode[];
  edges: GraphVizEdge[];
} {
  const hp =
    detail.has_part && typeof detail.has_part === "object"
      ? detail.has_part
      : {};
  const byId = new Map<string, GraphVizNode>();
  for (const n of (Array.isArray(hp.nodes) ? hp.nodes : []) as GraphVizNode[]) {
    if (n?.id) byId.set(n.id, { ...n });
  }

  const unitId = `unit:${detail.unit_id}`;
  if (!byId.has(unitId)) {
    byId.set(unitId, {
      id: unitId,
      type: "LessonGrouping",
      name: detail.unit_id,
    });
  }

  for (const m of detail.materials || []) {
    const id =
      m.id ||
      (m.source_file
        ? `material:${m.source_file.replace(/^doc_([a-f0-9]+)_.*/i, "$1")}`
        : "");
    if (!id) continue;
    const prev = byId.get(id);
    byId.set(id, {
      id,
      type: "Material",
      role: m.role || prev?.role,
      name: m.source_file || prev?.name || id,
      source_file: m.source_file || prev?.source_file,
    });
  }

  for (const l of detail.lessons || []) {
    const id = l.id || "";
    if (!id) continue;
    const prev = byId.get(id);
    byId.set(id, {
      id,
      type: "Lesson",
      name: l.name || prev?.name || id,
    });
  }

  for (const a of detail.assessments || []) {
    const id = a.id || "";
    if (!id) continue;
    const prev = byId.get(id);
    byId.set(id, {
      id,
      type: "Assessment",
      name: a.name || prev?.name || id,
      source_file: a.source_file || prev?.source_file,
    });
  }

  const edges = (
    (Array.isArray(hp.edges) ? hp.edges : []) as GraphVizEdge[]
  ).filter((e) => e?.from && e?.to);

  // Ensure materials/lessons/assessments are linked into the unit spine when
  // HAS-PART omitted an edge — otherwise placeBeside still draws them, but
  // the map looks disconnected.
  const edgeKey = new Set(edges.map((e) => `${e.from}|${e.to}|${e.rel || ""}`));
  const addEdge = (from: string, to: string, rel: string) => {
    const k = `${from}|${to}|${rel}`;
    if (edgeKey.has(k) || !byId.has(from) || !byId.has(to)) return;
    edgeKey.add(k);
    edges.push({ from, to, rel });
  };

  for (const n of byId.values()) {
    if (n.type === "Lesson") addEdge(unitId, n.id, "hasPart");
    if (n.type === "Material") addEdge(unitId, n.id, "hasPart");
    if (n.type === "Assessment") {
      // Prefer lesson→assessment; fall back to unit→assessment.
      const lessonEdge = edges.find(
        (e) =>
          e.to === n.id &&
          (e.from.startsWith("lesson:") ||
            (byId.get(e.from)?.type || "").toLowerCase() === "lesson")
      );
      if (!lessonEdge) addEdge(unitId, n.id, "hasPart");
    }
  }

  return { nodes: [...byId.values()], edges };
}

function shortName(sourceFile?: string): string {
  if (!sourceFile) return "—";
  const base = sourceFile.split("/").pop() || sourceFile;
  return base.length > 48 ? `${base.slice(0, 45)}…` : base;
}

function roleLabel(role?: string): string {
  if (!role) return "other";
  return role.replace(/_/g, " ");
}

function bandForUnit(u: GraphUnitRollup): string {
  if (!u.has_haspart) return "band-unrated";
  if (u.n_lessons > 0 && u.n_soft_queue === 0) return "band-strong";
  if (u.n_materials > 0 && u.n_soft_queue <= Math.max(1, u.n_materials / 2))
    return "band-developing";
  return "band-weak";
}

/**
 * Curriculum belonging space — research-backed layout:
 * 1) Progressive disclosure (curriculum map → unit DAG)
 * 2) Viz-first (layered DAG is primary; lists are secondary)
 * 3) Compact unit picker instead of duplicating a full card table
 */
export function GraphBelongingPanel({
  overview,
  unitDetail,
  selectedUnitId,
  onOpenUnit,
  loading,
}: Props) {
  const [focusId, setFocusId] = useState<string | null>(null);
  const [edgeFilter, setEdgeFilter] = useState<GraphEdgeFilter>("all");

  // Selected chip → expand that unit's docs on the map (materials + lessons +
  // assessments as nodes). No selection → curriculum Course→Units overview.
  const showingUnit = !!(unitDetail && selectedUnitId === unitDetail.unit_id);
  const mode = showingUnit ? "unit" : "overview";

  const viz = useMemo(() => {
    if (showingUnit && unitDetail) {
      return unitDetailToViz(unitDetail);
    }
    if (!overview)
      return { nodes: [] as GraphVizNode[], edges: [] as GraphVizEdge[] };
    return overviewToVizNodes(overview.project_id, overview.units);
  }, [overview, unitDetail, showingUnit]);

  if (loading) {
    return (
      <div className="graph-panel">
        <div className="graph-panel-head">Curriculum graph</div>
        <div className="empty">Loading model graph…</div>
      </div>
    );
  }
  if (!overview) {
    return (
      <div className="graph-panel">
        <div className="graph-panel-head">Curriculum graph</div>
        <div className="empty">
          No graph runs for this curriculum yet. Run <code>--with-graph</code>{" "}
          to produce model A/B trees.
        </div>
      </div>
    );
  }

  const totals = overview.units.reduce(
    (acc, u) => {
      acc.lessons += u.n_lessons;
      acc.materials += u.n_materials;
      acc.assessments += u.n_assessments;
      acc.soft += u.n_soft_queue;
      return acc;
    },
    { lessons: 0, materials: 0, assessments: 0, soft: 0 }
  );

  return (
    <div className="graph-panel graph-panel-organized">
      {/* Breadcrumb + scope */}
      <div className="graph-panel-head">
        <nav className="graph-crumb" aria-label="Graph scope">
          <button
            type="button"
            className={!showingUnit ? "active" : undefined}
            onClick={() => onOpenUnit("")}
          >
            Curriculum map
          </button>
          {showingUnit && (
            <>
              <span className="graph-crumb-sep" aria-hidden>
                /
              </span>
              <span className="graph-crumb-current">{unitDetail!.unit_id}</span>
            </>
          )}
        </nav>
        <span className="graph-panel-meta mono">
          {overview.model || overview.run_id}
          {overview.backend ? ` · ${overview.backend}` : ""} ·{" "}
          {overview.units.filter((u) => u.has_haspart).length}/
          {overview.units.length} units
        </span>
      </div>

      <div className="graph-totals mono">
        {showingUnit ? (
          <>
            <span>{unitDetail!.stats.n_lessons} lessons</span>
            <span>{unitDetail!.stats.n_materials} materials</span>
            <span>{unitDetail!.stats.n_assessments} assessments</span>
            {unitDetail!.stats.n_soft_queue ? (
              <span>{unitDetail!.stats.n_soft_queue} soft-queue</span>
            ) : null}
          </>
        ) : (
          <>
            <span>{totals.lessons} lessons</span>
            <span>{totals.materials} materials</span>
            <span>{totals.assessments} assessments</span>
            <span>{totals.soft} soft-queue</span>
          </>
        )}
      </div>

      {/* Compact unit picker — not a second full table competing with the viz */}
      <div className="graph-unit-chips" role="list" aria-label="Units">
        {overview.units.map((u) => (
          <button
            type="button"
            role="listitem"
            key={u.unit_id}
            className={`graph-unit-chip ${bandForUnit(u)}${
              selectedUnitId === u.unit_id ? " active" : ""
            }`}
            onClick={() => onOpenUnit(u.unit_id)}
            title={`${u.n_lessons}L · ${u.n_materials}m · ${u.n_assessments}a`}
          >
            <span className={`swatch ${bandForUnit(u)}`} />
            {u.unit_id}
          </button>
        ))}
      </div>

      {/* Controls for the layered DAG */}
      <div className="graph-viz-controls">
        <div className="graph-edge-filters" role="group" aria-label="Edge filter">
          {(
            [
              ["all", "All edges"],
              ["hasPart", "Belonging"],
              ["describes", "Describes"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={edgeFilter === id ? "active" : undefined}
              onClick={() => setEdgeFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
        {showingUnit && (
          <button
            type="button"
            className="graph-back"
            onClick={() => onOpenUnit("")}
          >
            ← Curriculum map
          </button>
        )}
      </div>

      {/* Primary: interactive layered graph */}
      <div className="graph-viz-wrap">
        {selectedUnitId && !showingUnit ? (
          <div className="empty">
            Loading map nodes for <code>{selectedUnitId}</code>…
          </div>
        ) : (
          <GraphViz
            mode={mode}
            edgeFilter={edgeFilter}
            nodes={viz.nodes}
            edges={viz.edges}
            focusId={focusId}
            caption={
              showingUnit
                ? `Map nodes: ${viz.nodes.filter((n) => n.type === "Material").length} materials · ${viz.nodes.filter((n) => n.type === "Lesson").length} lessons · ${viz.nodes.filter((n) => n.type === "Assessment").length} assessments — click to highlight`
                : "Click a unit chip or node to expand its teacher docs, lessons, and assessments on the map"
            }
            onNodeClick={(n) => {
              setFocusId(n.id);
              if (n.id.startsWith("unit:")) {
                onOpenUnit(n.id.slice("unit:".length));
              }
            }}
          />
        )}
      </div>

      {/* Secondary: inventory lists (collapsed by default) */}
      {showingUnit && (
        <details className="graph-details">
          <summary>Node inventory</summary>
          <div className="graph-details-grid">
            <div className="graph-section">
              <div className="graph-section-label">Lessons</div>
              <ul>
                {unitDetail!.lessons.map((l) => (
                  <li key={l.id || l.name}>{l.name || l.id}</li>
                ))}
                {!unitDetail!.lessons.length && <li className="muted">None</li>}
              </ul>
            </div>
            <div className="graph-section">
              <div className="graph-section-label">Materials</div>
              <ul>
                {unitDetail!.materials.map((m) => (
                  <li key={m.id || m.source_file}>
                    <span className="graph-role">{roleLabel(m.role)}</span>{" "}
                    {shortName(m.source_file)}
                  </li>
                ))}
              </ul>
            </div>
            <div className="graph-section">
              <div className="graph-section-label">Assessments</div>
              <ul>
                {unitDetail!.assessments.map((a) => (
                  <li key={a.id || a.name}>
                    {a.name || shortName(a.source_file)}
                  </li>
                ))}
                {!unitDetail!.assessments.length && (
                  <li className="muted">None</li>
                )}
              </ul>
            </div>
          </div>
        </details>
      )}
    </div>
  );
}
