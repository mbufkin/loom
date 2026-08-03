import type { GraphOverview, GraphUnitDetail, GraphUnitRollup } from "../types";

interface Props {
  overview: GraphOverview | null;
  /** When a unit is open, show that unit's belonging detail for the selected model. */
  unitDetail?: GraphUnitDetail | null;
  selectedUnitId?: string | null;
  onOpenUnit: (unitId: string) => void;
  loading?: boolean;
}

function shortName(sourceFile?: string): string {
  if (!sourceFile) return "—";
  const base = sourceFile.split("/").pop() || sourceFile;
  return base.length > 64 ? `${base.slice(0, 61)}…` : base;
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
 * Tasteful belonging panel under the quality heatmap.
 * Driven entirely by the selected model graph run (curriculum + model).
 */
export function GraphBelongingPanel({
  overview,
  unitDetail,
  selectedUnitId,
  onOpenUnit,
  loading,
}: Props) {
  if (loading) {
    return (
      <div className="graph-panel">
        <div className="graph-panel-head">Graph belonging</div>
        <div className="empty">Loading model graph…</div>
      </div>
    );
  }
  if (!overview) {
    return (
      <div className="graph-panel">
        <div className="graph-panel-head">Graph belonging</div>
        <div className="empty">
          No graph runs for this curriculum yet. Run{" "}
          <code>--with-graph</code> to produce model A/B trees.
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
    <div className="graph-panel">
      <div className="graph-panel-head">
        <span>Graph belonging</span>
        <span className="graph-panel-meta mono">
          {overview.model || overview.run_id}
          {overview.backend ? ` · ${overview.backend}` : ""} ·{" "}
          {overview.units.filter((u) => u.has_haspart).length}/
          {overview.units.length} units
        </span>
      </div>

      <div className="graph-totals mono">
        <span>{totals.lessons} lessons</span>
        <span>{totals.materials} materials</span>
        <span>{totals.assessments} assessments</span>
        <span>{totals.soft} soft-queue</span>
      </div>

      {unitDetail && selectedUnitId === unitDetail.unit_id ? (
        <div className="graph-unit-detail">
          <div className="graph-unit-detail-head">
            Unit structure · {unitDetail.unit_id}
          </div>
          <div className="graph-unit-stats mono">
            {unitDetail.stats.n_lessons} lessons ·{" "}
            {unitDetail.stats.n_materials} materials ·{" "}
            {unitDetail.stats.n_assessments} assessments
            {unitDetail.stats.n_soft_queue
              ? ` · ${unitDetail.stats.n_soft_queue} soft-queue`
              : ""}
          </div>
          {unitDetail.lessons.length > 0 && (
            <div className="graph-section">
              <div className="graph-section-label">Lessons</div>
              <ul>
                {unitDetail.lessons.map((l) => (
                  <li key={l.id || l.name}>{l.name || l.id}</li>
                ))}
              </ul>
            </div>
          )}
          <div className="graph-section">
            <div className="graph-section-label">Materials</div>
            <ul>
              {unitDetail.materials.map((m) => (
                <li key={m.id || m.source_file}>
                  <span className="graph-role">{roleLabel(m.role)}</span>{" "}
                  {shortName(m.source_file)}
                </li>
              ))}
            </ul>
          </div>
          {unitDetail.assessments.length > 0 && (
            <div className="graph-section">
              <div className="graph-section-label">Assessments</div>
              <ul>
                {unitDetail.assessments.map((a) => (
                  <li key={a.id || a.name}>{a.name || shortName(a.source_file)}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : (
        <>
          <div className="heat-colhead graph-heat-head">
            <span />
            <span>Unit</span>
            <span className="hc-pkt">Lessons</span>
            <span className="hc-qual">Materials / assess</span>
          </div>
          {overview.units.map((u) => (
            <button
              type="button"
              key={u.unit_id}
              className="unit-row graph-unit-row"
              onClick={() => onOpenUnit(u.unit_id)}
              title="Open unit · show this model's belonging"
            >
              <span className={`swatch ${bandForUnit(u)}`} />
              <span>
                <span className="u-title">{u.unit_id}</span>
                <br />
                <span className="u-metrics">
                  {u.n_lessons} lessons · {u.n_materials} materials ·{" "}
                  {u.n_assessments} assessments
                  {u.n_soft_queue ? ` · ${u.n_soft_queue} soft-queue` : ""}
                </span>
              </span>
              <span className="mono graph-cell">{u.n_lessons}</span>
              <span className={`chip-qual ${bandForUnit(u)}`}>
                {u.n_materials}m / {u.n_assessments}a
              </span>
            </button>
          ))}
        </>
      )}
    </div>
  );
}
