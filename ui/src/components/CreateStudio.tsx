// Create Studio — research-backed doctrine (docs/CREATE-WORKFLOW.md).
// Primary: unit matrix → UbD Stage 1→2→3 → slot create.
// Secondary: systemic patterns (cross-unit role absences).

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../lib/api";
import type {
  CreateMatrixResponse,
  CreateMatrixUnit,
  CreateRoleSummary,
  CreateSlot,
  CreateStageBucket,
  CreateStatus,
  CreateUnitTreeResponse,
  GapDecision,
  GapItem,
} from "../types";

type View = "matrix" | "patterns" | "unit" | "slot";
type Pane = "brief" | "draft";

type NextAction =
  | { id: "author"; hint: string }
  | { id: "brief"; hint: string }
  | { id: "draft"; hint: string }
  | { id: "edit"; hint: string }
  | { id: "pull_remove"; hint: string }
  | { id: "inspect"; hint: string };

function nextAction(slot: CreateSlot | null): NextAction {
  if (!slot) return { id: "inspect", hint: "Open a missing cell to create it." };
  if (slot.status === "FULFILLED") {
    return {
      id: "inspect",
      hint: "Already present — use as reference. Create only runs on missing cells.",
    };
  }
  if (!slot.decision) {
    return {
      id: "author",
      hint: "Author = create here. Pull = fetch later. Remove = drop from scope.",
    };
  }
  if (slot.decision === "pull" || slot.decision === "remove") {
    return {
      id: "pull_remove",
      hint:
        slot.decision === "pull"
          ? "Pull: get the real file outside Loom."
          : "Remove: this slot is out of scope for this pack.",
    };
  }
  if (!slot.has_brief) {
    return {
      id: "brief",
      hint: "Checklist only — not district curriculum yet.",
    };
  }
  if (!slot.has_draft) {
    return {
      id: "draft",
      hint: "DRAFT_UNVERIFIED. Stays under create/ until you promote later.",
    };
  }
  return { id: "edit", hint: "Edit below, then Save." };
}

function roleName(s: CreateSlot): string {
  return s.role_label || s.role.replace(/_/g, " ");
}

function slotKey(s: CreateSlot): string {
  return `${s.unit_id}|${s.role}|${s.locus}|${s.status}`;
}

function slotToGap(projectId: string, slot: CreateSlot): GapItem | null {
  if (!slot.gap_id) return null;
  return {
    gap_id: slot.gap_id,
    project_id: projectId,
    unit_id: slot.unit_id,
    unit_title: slot.unit_title,
    kind: "role",
    label: slot.role,
    locus: slot.locus,
    pattern: "isolated",
    evidence_refs: [],
    reasoning: slot.reasoning,
    decision: slot.decision,
    decision_note: slot.decision_note,
    has_brief: slot.has_brief,
    has_draft: slot.has_draft,
  };
}

function FillBar({
  missing,
  fulfilled,
}: {
  missing: number;
  fulfilled: number;
}) {
  const total = missing + fulfilled;
  const missPct = total ? (missing / total) * 100 : 0;
  const okPct = total ? (fulfilled / total) * 100 : 0;
  return (
    <div
      className="cs-fillbar"
      title={`${missing} missing · ${fulfilled} present`}
      aria-hidden
    >
      <i className="miss" style={{ width: `${missPct}%` }} />
      <i className="ok" style={{ width: `${okPct}%` }} />
    </div>
  );
}

export function CreateStudio({ projectId }: { projectId: string }) {
  const [view, setView] = useState<View>("matrix");
  const [matrix, setMatrix] = useState<CreateMatrixResponse | null>(null);
  const [patterns, setPatterns] = useState<CreateRoleSummary[]>([]);
  const [unitDetail, setUnitDetail] = useState<CreateUnitTreeResponse | null>(
    null
  );
  const [slot, setSlot] = useState<CreateSlot | null>(null);
  const [status, setStatus] = useState<CreateStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [flash, setFlash] = useState("");
  const [context, setContext] = useState("");
  const [pane, setPane] = useState<Pane>("draft");
  const [editor, setEditor] = useState("");
  const [editorDirty, setEditorDirty] = useState(false);
  const [overrideStageGate, setOverrideStageGate] = useState(false);

  const loadMatrix = useCallback(async () => {
    setError("");
    try {
      const [m, st] = await Promise.all([
        api.createMatrix(projectId),
        api.createStatus(),
      ]);
      setMatrix(m);
      setStatus(st);
    } catch (e) {
      setError(String(e));
    }
  }, [projectId]);

  useEffect(() => {
    void loadMatrix();
  }, [loadMatrix]);

  const action = nextAction(slot);

  const stage1Open = unitDetail?.stage1_open ?? 0;
  const softGate =
    !!slot &&
    slot.status === "MISSING" &&
    (slot.stage ?? 3) >= 3 &&
    stage1Open > 0 &&
    !overrideStageGate;

  useEffect(() => {
    if (!slot?.gap_id || slot.status === "FULFILLED") {
      setEditor("");
      setEditorDirty(false);
      return;
    }
    setPane(
      action.id === "edit" || action.id === "draft" || slot.has_draft
        ? "draft"
        : "brief"
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slot?.gap_id, slot?.status]);

  useEffect(() => {
    if (!slot?.gap_id || slot.status === "FULFILLED") {
      setEditor("");
      setEditorDirty(false);
      return;
    }
    setEditorDirty(false);
    let cancelled = false;
    (async () => {
      try {
        if (pane === "brief" && slot.has_brief) {
          const res = await api.getBrief(projectId, slot.gap_id!);
          if (!cancelled) setEditor(res.text);
        } else if (pane === "draft" && slot.has_draft) {
          const res = await api.getDraft(projectId, slot.gap_id!);
          if (!cancelled) setEditor(res.text);
        } else if (!cancelled) setEditor("");
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    slot?.gap_id,
    slot?.status,
    slot?.has_brief,
    slot?.has_draft,
    pane,
    projectId,
  ]);

  async function openPatterns() {
    setBusy(true);
    setError("");
    try {
      const t = await api.createTree(projectId);
      setPatterns(t.roles);
      setView("patterns");
      setSlot(null);
      setFlash("");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function openUnit(unitId: string) {
    setBusy(true);
    setError("");
    setFlash("");
    setOverrideStageGate(false);
    try {
      const data = await api.createUnitTree(projectId, unitId);
      setUnitDetail(data);
      setView("unit");
      setSlot(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  function openSlot(s: CreateSlot) {
    setSlot(s);
    setView("slot");
    setFlash("");
    setError("");
    setContext("");
    setOverrideStageGate(false);
  }

  function goMatrix() {
    setView("matrix");
    setUnitDetail(null);
    setSlot(null);
    setFlash("");
    void loadMatrix();
  }

  function goUnit() {
    if (!unitDetail) return goMatrix();
    setView("unit");
    setSlot(null);
    setFlash("");
    void openUnit(unitDetail.unit_id);
  }

  async function refreshAfterChange() {
    if (!slot || !unitDetail) return;
    const data = await api.createUnitTree(projectId, unitDetail.unit_id);
    setUnitDetail(data);
    const updated = data.slots.find(
      (s) =>
        s.unit_id === slot.unit_id &&
        s.role === slot.role &&
        s.locus === slot.locus
    );
    if (updated) {
      // Preserve stage from stages buckets if present on slot objects.
      const withStage =
        data.stages
          ?.flatMap((st) => st.slots || [])
          .find(
            (s) =>
              s.unit_id === updated.unit_id &&
              s.role === updated.role &&
              s.locus === updated.locus
          ) || updated;
      setSlot(withStage);
    }
    void loadMatrix();
  }

  async function decide(decision: GapDecision) {
    if (!slot?.gap_id) return;
    setBusy(true);
    setError("");
    try {
      await api.setGapDecision(projectId, slot.gap_id, decision);
      setFlash(
        decision === "author"
          ? "Marked Author — next: Make brief"
          : decision
            ? `Marked ${decision}`
            : "Cleared"
      );
      await refreshAfterChange();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function makeBrief() {
    if (!slot?.gap_id) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.makeBrief(projectId, slot.gap_id);
      setPane("brief");
      setEditor(res.text);
      setEditorDirty(false);
      setFlash("Brief ready — next: Draft with Cursor");
      await refreshAfterChange();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runDraft() {
    if (!slot?.gap_id) return;
    if (softGate) {
      setFlash(
        `Stage 1 still has ${stage1Open} open hole(s). Finish or triage Stage 1 first — or override below.`
      );
      return;
    }
    setBusy(true);
    setError("");
    setFlash("Cursor is drafting…");
    setPane("draft");
    setEditor("…");
    try {
      if (!slot.has_brief) await api.makeBrief(projectId, slot.gap_id);
      const res = await api.makeDraft(projectId, slot.gap_id, context);
      setEditor(res.text);
      setEditorDirty(false);
      setFlash("Draft ready — edit below, then Save");
      await refreshAfterChange();
    } catch (e) {
      setError(String(e));
      setFlash("");
    } finally {
      setBusy(false);
    }
  }

  async function saveEditor() {
    if (!slot?.gap_id) return;
    setBusy(true);
    setError("");
    try {
      if (pane === "brief")
        await api.saveBrief(projectId, slot.gap_id, editor);
      else await api.saveDraft(projectId, slot.gap_id, editor);
      setEditorDirty(false);
      setFlash("Saved.");
      await refreshAfterChange();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const presentInUnit = useMemo(
    () => (unitDetail?.slots ?? []).filter((s) => s.status === "FULFILLED"),
    [unitDetail]
  );

  const gap = slot ? slotToGap(projectId, slot) : null;
  const step =
    !slot || slot.status === "FULFILLED"
      ? 0
      : !slot.decision
        ? 1
        : slot.decision !== "author"
          ? 1
          : !slot.has_brief
            ? 2
            : !slot.has_draft
              ? 3
              : 4;

  const stages: CreateStageBucket[] = unitDetail?.stages ?? [];

  return (
    <div className="cs">
      <div className="cs-strip panel">
        <div className="panel-body cs-strip-body">
          <strong>Create</strong>
          <div className="cs-axis" role="group" aria-label="create views">
            <button
              type="button"
              className={view === "matrix" || view === "unit" || view === "slot" ? "on" : ""}
              onClick={goMatrix}
            >
              Units
            </button>
            <button
              type="button"
              className={view === "patterns" ? "on" : ""}
              onClick={() => void openPatterns()}
            >
              Systemic patterns
            </button>
          </div>
          <nav className="cs-crumb mono" aria-label="breadcrumb">
            <button type="button" className="cs-crumb-link" onClick={goMatrix}>
              Units
            </button>
            {(view === "unit" || view === "slot") && unitDetail && (
              <>
                <span aria-hidden>/</span>
                <button
                  type="button"
                  className="cs-crumb-link"
                  onClick={goUnit}
                >
                  {unitDetail.title}
                </button>
              </>
            )}
            {view === "slot" && slot && (
              <>
                <span aria-hidden>/</span>
                <span>
                  Stage {slot.stage ?? "?"} · {roleName(slot)}
                </span>
              </>
            )}
            {view === "patterns" && (
              <>
                <span aria-hidden>/</span>
                <span>Systemic patterns</span>
              </>
            )}
          </nav>
          <span
            className={`cs-pill ${status?.cursor_key_present ? "ok" : "bad"}`}
          >
            {status?.cursor_key_present ? "Cursor ready" : "No Cursor key"}
          </span>
        </div>
      </div>

      {error && (
        <div className="panel">
          <div className="panel-body cs-error">{error}</div>
        </div>
      )}

      {/* ── Primary: unit matrix ──────────────────────────────────── */}
      {view === "matrix" && (
        <div className="panel">
          <div className="panel-head">
            1 · Which unit are you repairing?
            <button
              type="button"
              className="cs-head-btn"
              onClick={() => void loadMatrix()}
              disabled={busy}
            >
              Reload
            </button>
          </div>
          <div className="panel-body">
            <p className="cs-lead-line">
              Largest holes first. Open a unit to see Stage 1 → 2 → 3 (goals →
              evidence → learning) with present and missing together.{" "}
              <span className="mono muted">docs/CREATE-WORKFLOW.md</span>
            </p>
            <div className="cs-matrix-head mono">
              <span>Unit</span>
              <span>Coverage</span>
              <span>S1</span>
              <span>S2</span>
              <span>S3</span>
              <span>Open</span>
            </div>
            {!matrix?.units.length ? (
              <div className="cs-empty">
                No findings yet — run an audit first.
              </div>
            ) : (
              matrix.units.map((u: CreateMatrixUnit) => {
                const s1 = u.stages.find((s) => s.id === 1);
                const s2 = u.stages.find((s) => s.id === 2);
                const s3 = u.stages.find((s) => s.id === 3);
                return (
                  <button
                    key={u.unit_id}
                    type="button"
                    className="cs-matrix-row"
                    onClick={() => void openUnit(u.unit_id)}
                  >
                    <span className="cs-role-name">
                      <strong>{u.title}</strong>
                      <span className="mono muted">
                        {u.missing} missing · {u.fulfilled} present
                      </span>
                    </span>
                    <FillBar missing={u.missing} fulfilled={u.fulfilled} />
                    <span className="cs-stage-cell">
                      <b className="miss">{s1?.missing ?? 0}</b>
                      <span className="ok">/{s1?.fulfilled ?? 0}</span>
                    </span>
                    <span className="cs-stage-cell">
                      <b className="miss">{s2?.missing ?? 0}</b>
                      <span className="ok">/{s2?.fulfilled ?? 0}</span>
                    </span>
                    <span className="cs-stage-cell">
                      <b className="miss">{s3?.missing ?? 0}</b>
                      <span className="ok">/{s3?.fulfilled ?? 0}</span>
                    </span>
                    <span className="mono muted">{u.pending_decisions}</span>
                  </button>
                );
              })
            )}
            <p className="cs-list-hint mono">
              S1/S2/S3 = missing/present per UbD stage · Open = undecided
              decisions
            </p>
          </div>
        </div>
      )}

      {/* ── Secondary: systemic patterns ──────────────────────────── */}
      {view === "patterns" && (
        <div className="panel">
          <div className="panel-head">
            <button type="button" className="back-link" onClick={goMatrix}>
              ← units
            </button>
            Systemic patterns
          </div>
          <div className="panel-body">
            <p className="cs-lead-line">
              Cross-unit absences (Jacobs large-group lens). Use to prioritize —
              then repair inside a unit on the Units view.
            </p>
            <div className="cs-role-head mono cs-role-head-bar">
              <span>Element</span>
              <span>Coverage</span>
              <span>Missing</span>
              <span>Present</span>
              <span>Open</span>
            </div>
            {patterns.map((r) => (
              <div key={r.role} className="cs-role-row cs-role-row-bar cs-pattern-row">
                <span className="cs-role-name">
                  {r.label}
                  <span className={`cs-chip ${r.pattern}`}>{r.pattern}</span>
                </span>
                <FillBar missing={r.missing} fulfilled={r.fulfilled} />
                <span className="cs-num miss">{r.missing}</span>
                <span className="cs-num ok">{r.fulfilled}</span>
                <span className="mono muted">{r.pending_decisions}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Unit: UbD stages ──────────────────────────────────────── */}
      {view === "unit" && unitDetail && (
        <div className="panel">
          <div className="panel-head">
            <button type="button" className="back-link" onClick={goMatrix}>
              ← units
            </button>
            2 · {unitDetail.title}
            <button
              type="button"
              className="cs-head-btn"
              onClick={() => void openUnit(unitDetail.unit_id)}
              disabled={busy}
            >
              Reload
            </button>
          </div>
          <div className="panel-body">
            <div className="cs-l2-summary">
              <span className="cs-pill bad">{unitDetail.missing} missing</span>
              <span className="cs-pill ok">{unitDetail.fulfilled} present</span>
              {stage1Open > 0 && (
                <span className="cs-pill bad">
                  Stage 1 open: {stage1Open}
                </span>
              )}
              <FillBar
                missing={unitDetail.missing}
                fulfilled={unitDetail.fulfilled}
              />
            </div>
            <p className="cs-list-hint mono">
              Fill Stage 1 (goals/plan) before Stage 3 (learning) when you can.
            </p>
            {stages.map((st) => (
              <section key={st.id} className="cs-stage-block">
                <header className="cs-stage-head">
                  <h3>{st.label}</h3>
                  <span className="mono muted">
                    {st.missing} missing · {st.fulfilled} present
                  </span>
                </header>
                <div className="cs-slot-list">
                  {(st.slots || []).length === 0 ? (
                    <div className="cs-empty">No slots in this stage.</div>
                  ) : (
                    (st.slots || []).map((s) => (
                      <button
                        key={slotKey(s)}
                        type="button"
                        className={`cs-slot-row ${s.status.toLowerCase()}`}
                        onClick={() => openSlot(s)}
                      >
                        <span
                          className={`cs-status ${s.status.toLowerCase()}`}
                        >
                          {s.status === "MISSING" ? "Missing" : "Present"}
                        </span>
                        <span className="cs-slot-main">
                          <strong>{roleName(s)}</strong>
                          <span className="mono muted"> · {s.locus}</span>
                        </span>
                        <span className="cs-slot-meta mono">
                          {s.status === "MISSING"
                            ? s.has_draft
                              ? "has draft"
                              : s.has_brief
                                ? "has brief"
                                : s.decision || "needs decision"
                            : s.fulfilled_by[0]
                              ? `via ${s.fulfilled_by[0]}`
                              : "fulfilled"}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              </section>
            ))}
          </div>
        </div>
      )}

      {/* ── Slot create ───────────────────────────────────────────── */}
      {view === "slot" && slot && unitDetail && (
        <div className="cs-slot-work">
          <div className="panel">
            <div className="panel-head">
              <button type="button" className="back-link" onClick={goUnit}>
                ← {unitDetail.title}
              </button>
              3 · This cell
            </div>
            <div className="panel-body">
              <div className="cs-area-banner">
                <div>
                  <div className="mono cs-area-kicker">
                    Area you’re filling · Stage {slot.stage ?? "?"}
                  </div>
                  <h2 className="cs-sel-title">
                    {roleName(slot)}{" "}
                    <span className="mono muted">
                      · {slot.unit_title} · {slot.locus}
                    </span>
                  </h2>
                </div>
                <FillBar
                  missing={unitDetail.missing}
                  fulfilled={unitDetail.fulfilled}
                />
              </div>

              {presentInUnit.length > 0 && (
                <div className="cs-have">
                  <div className="cs-have-title mono">
                    Already in this unit (reference)
                  </div>
                  <ul className="cs-have-list">
                    {presentInUnit.map((s) => (
                      <li key={slotKey(s)}>
                        <button
                          type="button"
                          className="cs-have-item"
                          onClick={() => openSlot(s)}
                        >
                          <strong>{roleName(s)}</strong>
                          <span className="mono muted"> · {s.locus}</span>
                          {s.fulfilled_by[0] && (
                            <span className="mono cs-have-cite">
                              {" "}
                              ← {s.fulfilled_by[0]}
                            </span>
                          )}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {softGate && (
                <div className="cs-gate panel">
                  <div className="panel-body">
                    <strong>Stage order reminder.</strong> Stage 1 still has{" "}
                    {stage1Open} open hole(s). Pros usually settle goals/plan
                    before drafting Stage 3 learning materials.
                    <div className="cs-decide" style={{ marginTop: 8 }}>
                      <button type="button" onClick={goUnit}>
                        Back to Stage 1
                      </button>
                      <button
                        type="button"
                        onClick={() => setOverrideStageGate(true)}
                      >
                        Override — draft anyway
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {slot.status === "MISSING" && (
                <div className="cs-progress mono" aria-label="progress">
                  <span className={step >= 1 ? "on" : ""}>Decide</span>
                  <span aria-hidden>→</span>
                  <span className={step >= 2 ? "on" : ""}>Brief</span>
                  <span aria-hidden>→</span>
                  <span className={step >= 3 ? "on" : ""}>Draft</span>
                  <span aria-hidden>→</span>
                  <span className={step >= 4 ? "on" : ""}>Edit</span>
                </div>
              )}

              <div className="cs-chips">
                <span className={`cs-status ${slot.status.toLowerCase()}`}>
                  {slot.status === "MISSING" ? "Missing" : "Present"}
                </span>
                {slot.has_brief && <span className="cs-chip ok">brief</span>}
                {slot.has_draft && <span className="cs-chip ok">draft</span>}
              </div>
              {slot.reasoning && <p className="cs-reason">{slot.reasoning}</p>}
              {slot.status === "FULFILLED" && slot.fulfilled_by.length > 0 && (
                <p className="cs-cite mono">
                  Fulfilled by: {slot.fulfilled_by.join(", ")}
                </p>
              )}

              <div className={`cs-next ${busy ? "busy" : ""}`}>
                <p className="cs-next-hint">{action.hint}</p>
                {flash && <p className="cs-flash mono">{flash}</p>}

                {action.id === "author" && (
                  <div className="cs-decide">
                    <button
                      type="button"
                      className="primary cs-big"
                      disabled={busy}
                      onClick={() => void decide("author")}
                    >
                      Author — I’ll create this
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void decide("pull")}
                    >
                      Pull later
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void decide("remove")}
                    >
                      Remove
                    </button>
                  </div>
                )}

                {action.id === "brief" && (
                  <button
                    type="button"
                    className="primary cs-big"
                    disabled={busy}
                    onClick={() => void makeBrief()}
                  >
                    {busy ? "Working…" : "Make brief"}
                  </button>
                )}

                {action.id === "draft" && (
                  <div className="cs-draft-box">
                    <label className="cs-field">
                      <span className="mono">Optional hint for Cursor</span>
                      <textarea
                        rows={2}
                        value={context}
                        onChange={(e) => setContext(e.target.value)}
                        placeholder="Constraints / neighboring excerpts…"
                      />
                    </label>
                    <button
                      type="button"
                      className="primary cs-big"
                      disabled={
                        busy ||
                        softGate ||
                        !status?.cursor_key_present ||
                        !status?.cursor_sdk
                      }
                      onClick={() => void runDraft()}
                    >
                      {busy ? "Drafting…" : "Draft with Cursor"}
                    </button>
                  </div>
                )}

                {action.id === "edit" && (
                  <button
                    type="button"
                    className="primary cs-big"
                    disabled={busy || !editorDirty}
                    onClick={() => void saveEditor()}
                  >
                    {editorDirty ? "Save draft" : "Edit the draft below first"}
                  </button>
                )}

                {(action.id === "pull_remove" ||
                  (action.id === "inspect" &&
                    slot.status === "FULFILLED")) && (
                  <button
                    type="button"
                    className="primary cs-big"
                    onClick={goUnit}
                  >
                    ← Back to unit stages
                  </button>
                )}
              </div>

              {slot.status === "MISSING" && slot.decision === "author" && (
                <div className="cs-skip mono">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void decide(null)}
                  >
                    Undo decision
                  </button>
                </div>
              )}
            </div>
          </div>

          {slot.status === "MISSING" &&
            gap &&
            (slot.has_brief || slot.has_draft || editor) && (
              <div className="panel">
                <div className="panel-head cs-editor-head">
                  <div className="cs-pane-tabs" role="tablist">
                    <button
                      type="button"
                      className={pane === "brief" ? "on" : ""}
                      onClick={() => setPane("brief")}
                    >
                      Brief
                    </button>
                    <button
                      type="button"
                      className={pane === "draft" ? "on" : ""}
                      onClick={() => setPane("draft")}
                    >
                      Draft
                    </button>
                  </div>
                  <div className="cs-editor-actions">
                    {editorDirty && (
                      <span className="mono cs-dirty">unsaved</span>
                    )}
                    <button
                      type="button"
                      className="primary"
                      disabled={
                        busy ||
                        !editorDirty ||
                        (pane === "brief" && !slot.has_brief) ||
                        (pane === "draft" && !slot.has_draft)
                      }
                      onClick={() => void saveEditor()}
                    >
                      Save
                    </button>
                  </div>
                </div>
                <div className="panel-body cs-editor-wrap">
                  <textarea
                    className="cs-editor mono"
                    value={editor}
                    spellCheck={false}
                    onChange={(e) => {
                      setEditor(e.target.value);
                      setEditorDirty(true);
                    }}
                  />
                </div>
              </div>
            )}
        </div>
      )}
    </div>
  );
}
