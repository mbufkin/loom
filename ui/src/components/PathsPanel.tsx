// Paths A–H — the router's eight review lenses for one workspace.
//
// Reads projects/<id>/{layer0/route-map.json, path_*/findings.json} via
// /api/projects/<id>/paths, so it works for a live tree and for a frozen
// e2e/runs/<id>/ snapshot alike. Two levels:
//   1. Lens grid   — every path, whether it ran, and how much it flagged.
//   2. Lens detail — per-step presence bars + the documents routed here.
//
// A path with zero routed documents is shown, not hidden: `skipped` is a real
// result (the corpus has no syllabi) and reviewers need to see that it was
// considered rather than silently dropped.

import { useMemo, useState } from "react";
import type {
  PathDoc,
  PathInventoryRow,
  PathStep,
  PathStepStatus,
  PathSummary,
  PathsSummary,
} from "../types";

interface Props {
  summary: PathsSummary | null;
  loading?: boolean;
  /** Open the raw findings.json in the file viewer. */
  onOpenFindings?: (path: string) => void;
}

// Status → swatch class. Order matters: bars stack in this sequence so the
// eye reads left-to-right from healthy to actionable. OPTIONAL_ABSENT sits
// with the neutrals (after MISSING) — it is not a failure, just "no optional
// signal," so it must not read as the red Missing band.
const STATUS_ORDER: PathStepStatus[] = [
  "PRESENT",
  "PARTIAL",
  "MISSING",
  "OPTIONAL_ABSENT",
  "NOT_APPLICABLE",
  "STUB",
  "UNKNOWN",
];

const STATUS_LABEL: Record<PathStepStatus, string> = {
  PRESENT: "Present",
  PARTIAL: "Partial",
  MISSING: "Missing",
  OPTIONAL_ABSENT: "Optional",
  NOT_APPLICABLE: "N/A",
  STUB: "Stub",
  UNKNOWN: "Unknown",
};

/** Short, plain-language read of a path's run state for the lens card. */
function statusBlurb(p: PathSummary): string {
  switch (p.status) {
    case "ok":
      return `${p.n_docs} document${p.n_docs === 1 ? "" : "s"} reviewed`;
    case "skipped":
      return "No documents of this type in the corpus";
    case "stub":
      return "Ran before this lens had presence checks";
    case "emitted":
      return `${p.n_docs} per-document file${p.n_docs === 1 ? "" : "s"} written`;
    default:
      return "No findings file — this path has not run here";
  }
}

function StatusBar({ step }: { step: PathStep }) {
  const total = step.total || 1;
  return (
    <div className="pp-bar" role="img" aria-label={`${step.step} presence`}>
      {STATUS_ORDER.map((s) => {
        const n = step.counts[s] ?? 0;
        if (!n) return null;
        return (
          <span
            key={s}
            className={`pp-seg pp-${s.toLowerCase()}`}
            style={{ width: `${(n / total) * 100}%` }}
            title={`${STATUS_LABEL[s]}: ${n} of ${step.total}`}
          />
        );
      })}
    </div>
  );
}

function LensCard({
  path,
  active,
  onClick,
}: {
  path: PathSummary;
  active: boolean;
  onClick: () => void;
}) {
  const dim = path.status === "skipped" || path.status === "absent";
  return (
    <button
      className={`pp-card ${active ? "active" : ""} ${dim ? "dim" : ""}`}
      onClick={onClick}
      title={statusBlurb(path)}
    >
      <div className="pp-card-top">
        <span className="pp-letter mono">{path.letter}</span>
        <span className={`pp-status pp-st-${path.status}`}>{path.status}</span>
      </div>
      <div className="pp-card-label">{path.label}</div>
      <div className="pp-card-nums mono">
        <span title="Documents routed to this lens">{path.routed} routed</span>
        {path.missing_total > 0 && (
          <span className="pp-flag" title="Total MISSING checklist results">
            {path.missing_total} missing
          </span>
        )}
      </div>
    </button>
  );
}

/** Pull a document's step statuses out of its findings inventory row. */
function rowSteps(row: PathInventoryRow, letter: string): [string, string][] {
  return Object.entries(row)
    .filter(
      ([k, v]) =>
        k.startsWith(letter) &&
        /^\d+$/.test(k.slice(1)) &&
        v &&
        typeof v === "object"
    )
    .sort((a, b) => Number(a[0].slice(1)) - Number(b[0].slice(1)))
    .map(([k, v]) => [k, (v as { status?: string }).status || "UNKNOWN"]);
}

/** Documents keep their doc_id in the filename; show the readable part. */
function docTitle(doc: PathDoc): string {
  const raw = doc.source_file || doc.doc_id || "(unknown)";
  return raw
    .replace(/^doc_[a-f0-9]+_/i, "")
    .replace(/\.(txt|pdf|docx?|pptx?)$/i, "")
    .replace(/_/g, " ");
}

function LensDetail({
  path,
  onOpenFindings,
}: {
  path: PathSummary;
  onOpenFindings?: (p: string) => void;
}) {
  const [showDocs, setShowDocs] = useState(false);

  // Join the route-map rows (which carry filenames) to the findings inventory
  // (which carries per-step status) so one table can show both.
  const invByDoc = useMemo(() => {
    const m = new Map<string, PathInventoryRow>();
    for (const row of path.inventory) {
      const id = row.doc_id;
      if (typeof id === "string") m.set(id, row);
    }
    return m;
  }, [path.inventory]);

  if (path.status === "skipped" || path.status === "absent") {
    return (
      <div className="pp-detail">
        <div className="empty">
          <strong>
            {path.letter} · {path.label}
          </strong>{" "}
          — {statusBlurb(path)}. The router considered this lens and found
          nothing to send it, which is a valid outcome, not a failure.
        </div>
      </div>
    );
  }

  return (
    <div className="pp-detail">
      <div className="pp-detail-head">
        <div>
          <span className="pp-letter mono lg">{path.letter}</span>
          <span className="pp-detail-title">{path.label}</span>
        </div>
        <div className="pp-detail-actions">
          {path.top_reasons.length > 0 && (
            <span className="pp-reasons mono" title="How the router chose this lens">
              {path.top_reasons.map((r) => `${r.reason} ×${r.count}`).join(" · ")}
            </span>
          )}
          {onOpenFindings && (
            <button
              className="pp-link"
              onClick={() => onOpenFindings(path.findings_path)}
            >
              raw findings.json ↗
            </button>
          )}
        </div>
      </div>

      {path.steps.length > 0 ? (
        <>
          <div className="pp-legend mono">
            {STATUS_ORDER.filter((s) => s !== "UNKNOWN").map((s) => (
              <span key={s}>
                <i className={`pp-swatch pp-${s.toLowerCase()}`} />
                {STATUS_LABEL[s]}
              </span>
            ))}
          </div>
          <table className="pp-steps">
            <thead>
              <tr>
                <th className="mono">Step</th>
                <th>Checks for</th>
                <th>Across {path.n_docs} docs</th>
                <th className="pp-num">Missing</th>
              </tr>
            </thead>
            <tbody>
              {path.steps.map((s) => (
                <tr key={s.step} className={s.missing > 0 ? "has-missing" : ""}>
                  <td className="mono pp-step-id">{s.step}</td>
                  <td className="pp-step-label">{s.label || "—"}</td>
                  <td>
                    <StatusBar step={s} />
                  </td>
                  <td className="pp-num mono">
                    {s.missing > 0 ? s.missing : "·"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <div className="empty">
          This lens emits per-document files rather than a checklist table. Open
          the raw findings for the document list.
        </div>
      )}

      {path.docs.length > 0 && (
        <details
          className="pp-docs"
          open={showDocs}
          onToggle={(e) => setShowDocs((e.target as HTMLDetailsElement).open)}
        >
          <summary>
            Documents routed here <span className="tag">{path.docs.length}</span>
          </summary>
          <table className="pp-doctable">
            <thead>
              <tr>
                <th>Document</th>
                <th className="mono">Type</th>
                <th>Steps</th>
              </tr>
            </thead>
            <tbody>
              {path.docs.map((d) => {
                const row = d.doc_id ? invByDoc.get(d.doc_id) : undefined;
                return (
                  <tr key={d.doc_id || d.source_file}>
                    <td className="pp-doc-name" title={d.source_file || ""}>
                      {docTitle(d)}
                    </td>
                    <td className="mono pp-doc-type">{d.doc_type || "—"}</td>
                    <td className="pp-doc-steps">
                      {row ? (
                        rowSteps(row, path.letter).map(([step, status]) => (
                          <span
                            key={step}
                            className={`pp-pip pp-${status.toLowerCase()}`}
                            title={`${step}: ${status}`}
                          >
                            {step.slice(1)}
                          </span>
                        ))
                      ) : (
                        <span className="muted mono">no inventory row</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

export function PathsPanel({ summary, loading, onOpenFindings }: Props) {
  const [selected, setSelected] = useState<string | null>(null);

  // Default to the lens with the most flagged gaps — that is where a reviewer
  // should start, and it avoids opening on an empty path.
  const active = useMemo(() => {
    if (!summary) return null;
    const byLetter = summary.paths.find((p) => p.letter === selected);
    if (byLetter) return byLetter;
    const ran = summary.paths.filter((p) => p.status === "ok");
    if (!ran.length) return summary.paths.find((p) => p.has_findings) ?? null;
    return ran.reduce((a, b) => (b.missing_total > a.missing_total ? b : a));
  }, [summary, selected]);

  if (loading) return <div className="empty">Loading paths…</div>;
  if (!summary) {
    return (
      <div className="empty">
        No route map for this workspace. Paths appear once Layer 0 has routed the
        corpus.
      </div>
    );
  }

  const ran = summary.paths.filter((p) => p.status === "ok").length;
  const flagged = summary.paths.reduce((n, p) => n + p.missing_total, 0);

  return (
    <div className="pp">
      <div className="pp-summary mono">
        <span>
          <strong>{summary.total_routed}</strong> documents routed
        </span>
        <span>
          <strong>{ran}</strong> of 8 lenses ran
        </span>
        <span className={flagged > 0 ? "pp-flag" : ""}>
          <strong>{flagged}</strong> missing elements flagged
        </span>
        {summary.unrouted > 0 && (
          <span className="pp-flag">
            <strong>{summary.unrouted}</strong> unrouted
          </span>
        )}
      </div>

      <div className="pp-grid">
        {summary.paths.map((p) => (
          <LensCard
            key={p.letter}
            path={p}
            active={active?.letter === p.letter}
            onClick={() => setSelected(p.letter)}
          />
        ))}
      </div>

      {active && <LensDetail path={active} onOpenFindings={onOpenFindings} />}
    </div>
  );
}
