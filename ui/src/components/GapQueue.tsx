// Live gap work queue for Next Steps (Phase 0–2).
// Best practice: decisions persist server-side; drafts are explicit and labeled
// DRAFT_UNVERIFIED — never silent writes into sources/.

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type { CreateStatus, GapDecision, GapItem } from "../types";

type Filter = "all" | "systemic" | "isolated" | "undecided" | "author";

export function GapQueue({ projectId }: { projectId: string }) {
  const [gaps, setGaps] = useState<GapItem[]>([]);
  const [status, setStatus] = useState<CreateStatus | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [viewer, setViewer] = useState<{ title: string; text: string } | null>(
    null
  );

  const reload = useCallback(async () => {
    setError("");
    try {
      const [g, s] = await Promise.all([
        api.gaps(projectId),
        api.createStatus(),
      ]);
      setGaps(g.gaps);
      setStatus(s);
    } catch (e) {
      setError(String(e));
    }
  }, [projectId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const visible = useMemo(() => {
    return gaps.filter((g) => {
      if (filter === "systemic") return g.pattern === "systemic";
      if (filter === "isolated") return g.pattern === "isolated";
      if (filter === "undecided") return !g.decision;
      if (filter === "author") return g.decision === "author";
      return true;
    });
  }, [gaps, filter]);

  async function setDecision(gap: GapItem, decision: GapDecision) {
    setBusyId(gap.gap_id);
    setError("");
    try {
      await api.setGapDecision(projectId, gap.gap_id, decision);
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function openBrief(gap: GapItem) {
    setBusyId(gap.gap_id);
    setError("");
    try {
      const res = gap.has_brief
        ? await api.getBrief(projectId, gap.gap_id)
        : await api.makeBrief(projectId, gap.gap_id);
      setViewer({ title: `Brief · ${gap.label}`, text: res.text });
      await reload();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyId(null);
    }
  }

  async function runDraft(gap: GapItem) {
    // Cursor Agent.prompt can take a while — keep UI honest about waiting.
    setBusyId(gap.gap_id);
    setError("");
    setViewer({
      title: `Drafting · ${gap.label}`,
      text: "Calling Cursor (Pi API key)… stay on this page.",
    });
    try {
      const res = await api.makeDraft(projectId, gap.gap_id);
      setViewer({
        title: `Draft · ${gap.label} (${res.model})`,
        text: res.text,
      });
      await reload();
    } catch (e) {
      setError(String(e));
      setViewer(null);
    } finally {
      setBusyId(null);
    }
  }

  async function openDraft(gap: GapItem) {
    setBusyId(gap.gap_id);
    try {
      const res = await api.getDraft(projectId, gap.gap_id);
      setViewer({ title: `Draft · ${gap.label}`, text: res.text });
    } catch (e) {
      setError(String(e));
    } finally {
      setBusyId(null);
    }
  }

  const undecided = gaps.filter((g) => !g.decision).length;
  const systemic = gaps.filter((g) => g.pattern === "systemic").length;

  return (
    <div className="gq">
      <header className="gq-head">
        <div>
          <h1 className="gq-title">Gap work queue</h1>
          <p className="gq-sub mono">
            {projectId} · {gaps.length} gaps · {undecided} undecided ·{" "}
            {systemic} systemic
          </p>
        </div>
        <div className="gq-status mono">
          {status ? (
            <>
              Cursor: {status.cursor_key_present ? "key ok" : "no key"} (
              {status.cursor_key_source}) · sdk{" "}
              {status.cursor_sdk ? "ready" : "missing"}
            </>
          ) : (
            "checking Cursor…"
          )}
        </div>
      </header>

      <p className="gq-doctrine">
        We don’t invent what’s missing. Decide Author / Pull / Remove — then
        brief, optional Cursor draft, human accept, re-audit.
      </p>

      <div className="gq-filters" role="group" aria-label="filter gaps">
        {(
          [
            ["all", "All"],
            ["systemic", "Systemic"],
            ["isolated", "Isolated"],
            ["undecided", "Undecided"],
            ["author", "Author"],
          ] as [Filter, string][]
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={filter === id ? "on" : ""}
            aria-pressed={filter === id}
            onClick={() => setFilter(id)}
          >
            {label}
          </button>
        ))}
        <button type="button" className="gq-reload" onClick={() => void reload()}>
          Reload
        </button>
      </div>

      {error && <div className="gq-error">{error}</div>}

      <div className="gq-list">
        {visible.length === 0 ? (
          <div className="gq-empty">
            No gaps for this filter. Run an audit if the queue is empty.
          </div>
        ) : (
          visible.map((g) => (
            <article key={g.gap_id} className="gq-row">
              <div className="gq-row-main">
                <div className="gq-chips">
                  <span className={`gq-chip ${g.pattern}`}>{g.pattern}</span>
                  <span className="gq-chip kind">{g.kind}</span>
                  {g.has_brief && <span className="gq-chip ok">brief</span>}
                  {g.has_draft && <span className="gq-chip ok">draft</span>}
                </div>
                <h3 className="gq-label">
                  {g.label}{" "}
                  <span className="mono muted">@ {g.locus}</span>
                </h3>
                <p className="gq-unit">
                  {g.unit_title}{" "}
                  <span className="mono muted">({g.unit_id})</span>
                </p>
                {g.reasoning && <p className="gq-reason">{g.reasoning}</p>}
              </div>
              <div className="gq-actions">
                <select
                  value={g.decision ?? ""}
                  disabled={busyId === g.gap_id}
                  onChange={(e) => {
                    const v = e.target.value;
                    void setDecision(
                      g,
                      v === "" ? null : (v as Exclude<GapDecision, null>)
                    );
                  }}
                >
                  <option value="">Decide…</option>
                  <option value="author">Author</option>
                  <option value="pull">Pull</option>
                  <option value="remove">Remove</option>
                </select>
                <button
                  type="button"
                  disabled={busyId === g.gap_id}
                  onClick={() => void openBrief(g)}
                >
                  {g.has_brief ? "Open brief" : "Make brief"}
                </button>
                <button
                  type="button"
                  disabled={
                    busyId === g.gap_id ||
                    g.decision !== "author" ||
                    !status?.cursor_key_present ||
                    !status?.cursor_sdk
                  }
                  title={
                    g.decision !== "author"
                      ? "Set decision to Author first"
                      : "Draft via Cursor (Pi key)"
                  }
                  onClick={() => void runDraft(g)}
                >
                  {busyId === g.gap_id ? "Working…" : "Draft (Cursor)"}
                </button>
                {g.has_draft && (
                  <button
                    type="button"
                    disabled={busyId === g.gap_id}
                    onClick={() => void openDraft(g)}
                  >
                    View draft
                  </button>
                )}
              </div>
            </article>
          ))
        )}
      </div>

      {viewer && (
        <div className="gq-viewer panel">
          <div className="panel-head">
            {viewer.title}
            <button type="button" className="gq-close" onClick={() => setViewer(null)}>
              Close
            </button>
          </div>
          <pre className="gq-viewer-body">{viewer.text}</pre>
        </div>
      )}
    </div>
  );
}
