import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { ArtifactCriterion, ArtifactDoc } from "../types";

interface Props {
  doc: ArtifactDoc;
  // Needed to fetch the artifact's raw source text from the local API.
  projectId: string;
}

const BAND_LABEL: Record<number, string> = {
  0: "Absent",
  1: "Weak",
  2: "Developing",
  3: "Strong",
};

// Presence verdicts and alignment bands both map onto the shared band colour
// vocabulary so an artifact reads consistently with lessons/units.
function verdictClass(verdict?: string | null): string {
  if (verdict === "PRESENT") return "band-strong";
  if (verdict === "PARTIAL") return "band-developing";
  if (verdict === "MISSING") return "band-weak";
  return "band-unrated";
}
function bandClass(band: number | null | undefined): string {
  if (band == null) return "band-unrated";
  if (band >= 3) return "band-strong";
  if (band === 2) return "band-developing";
  return "band-weak";
}

function Dots({ band }: { band: number | null | undefined }) {
  const n = band ?? 0;
  return (
    <span className="dots" aria-label={`band ${n} of 3`}>
      {"●".repeat(n)}
      {"○".repeat(Math.max(0, 3 - n))}
    </span>
  );
}

// Per-doc artifact review: the deterministic presence gate (does the artifact have
// its structural parts?) and, when the advisory alignment audit was run, the
// objective-anchored alignment bands. Pure presentation of one ARTIFACT-RUNG.json
// record — every verdict keeps its cited evidence.
export function ArtifactDetail({ doc, projectId }: Props) {
  const pres = doc.presence;
  const align = doc.alignment;
  return (
    <div className="ldetail">
      <div className="ldetail-meta mono">
        {doc.role} · type {doc.doc_type}
        {doc.is_fallback ? " (generic fallback)" : ""} ·{" "}
        {pres.gate_pass ? "presence gate PASS" : "presence gate FAIL"}
        {pres.coverage != null ? ` · coverage ${Math.round(pres.coverage * 100)}%` : ""}
      </div>

      {!pres.gate_pass && pres.missing_required.length > 0 && (
        <p className="sub">
          Missing required parts:
          <br />
          {pres.missing_required.map((m) => (
            <span className="chip warn" key={m}>
              {m}
            </span>
          ))}
        </p>
      )}

      <h4>Presence — structural completeness (deterministic)</h4>
      <div className="dim-list">
        {pres.criteria.map((c) => (
          <PresenceRow key={c.criterion_id} c={c} />
        ))}
      </div>

      {renderAlignment(align)}

      <SourceText projectId={projectId} path={doc.source_file} />
    </div>
  );
}

// Alignment is deliberately NOT a headline claim yet. The informational states
// (no criteria / cannot-assess / offline) are plain notes; the actual model-produced
// band verdicts are tucked into a collapsed, clearly-marked EXPERIMENTAL disclosure
// so the review does not assert "aligned / not aligned" more confidently than the
// under-validated scorer warrants. See docs/ARTIFACT-ALIGNMENT-DEFERRED.md.
function renderAlignment(align: ArtifactDoc["alignment"]) {
  if (!align || align.applicable === false) {
    return (
      <p className="muted-note">
        No alignment criteria for this type (generic fallback) — logged to the
        feedback nursery for a future dedicated review.
      </p>
    );
  }
  if (align.cannot_assess) {
    return (
      <p className="muted-note">
        Cannot assess alignment — the unit's lesson has no objective or cited TEKS to
        anchor against. Rolled up as a lesson-level gap.
      </p>
    );
  }
  if (align.skipped) {
    return (
      <p className="muted-note">
        Alignment audit not run (offline). Re-run the artifact rung with{" "}
        <code>--with-model</code> to produce advisory alignment bands.
        {align.error ? ` (${align.error})` : ""}
      </p>
    );
  }
  return (
    <details className="experimental-block">
      <summary>
        Alignment audit
        <span className="chip warn">experimental — not yet validated</span>
      </summary>
      <p className="muted-note">
        Advisory only. These bands come from a model scorer we have not yet calibrated
        against a gold set, so treat them as a prompt for review — not a verdict.
      </p>
      <div className="dim-list">
        {align.criteria.map((c) => (
          <BandRow key={c.criterion_id} c={c} />
        ))}
      </div>
    </details>
  );
}

function PresenceRow({ c }: { c: ArtifactCriterion }) {
  const [open, setOpen] = useState(false);
  const hasEvidence = c.evidence && c.evidence.length > 0;
  return (
    <div className={`dim ${verdictClass(c.verdict)}`}>
      <div className="dim-head">
        <span className={`swatch ${verdictClass(c.verdict)}`} />
        <span className="dim-label">{c.label}</span>
        <span className="dim-band mono">{c.verdict ?? "—"}</span>
      </div>
      {c.note && <div className="dim-note">{c.note}</div>}
      {hasEvidence && <Evidence c={c} open={open} setOpen={setOpen} />}
    </div>
  );
}

function BandRow({ c }: { c: ArtifactCriterion }) {
  const [open, setOpen] = useState(false);
  const hasEvidence = c.evidence && c.evidence.length > 0;
  return (
    <div className={`dim ${bandClass(c.band)}`}>
      <div className="dim-head">
        <span className={`swatch ${bandClass(c.band)}`} />
        <span className="dim-label">{c.label}</span>
        <span className="dim-band mono">
          <Dots band={c.band} />{" "}
          {c.band != null ? BAND_LABEL[c.band] ?? c.band : "—"}
        </span>
      </div>
      <div className="dim-note">{c.note || "—"}</div>
      {hasEvidence && <Evidence c={c} open={open} setOpen={setOpen} />}
    </div>
  );
}

function Evidence({
  c,
  open,
  setOpen,
}: {
  c: ArtifactCriterion;
  open: boolean;
  setOpen: (fn: (v: boolean) => boolean) => void;
}) {
  return (
    <div className="dim-ev">
      <button className="ev-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "▾ hide evidence" : "▸ show evidence"}
      </button>
      {open &&
        c.evidence.map((e, i) => (
          <blockquote key={`${e.element_id}-${i}`} className="ev-quote">
            <span className="mono ev-id">{e.element_id}</span>
            {e.excerpt}
          </blockquote>
        ))}
    </div>
  );
}

// The raw artifact document beneath the review (same pattern as the lesson source
// panel). Lazy-loaded from the local API and open by default.
function SourceText({
  projectId,
  path,
}: {
  projectId: string;
  path?: string | null;
}) {
  const [text, setText] = useState<string | null>(null);
  const [err, setErr] = useState<string>("");

  useEffect(() => {
    if (!path) return;
    let alive = true;
    setText(null);
    setErr("");
    api
      .fileText(projectId, path)
      .then((t) => alive && setText(t))
      .catch((e) => alive && setErr(String(e)));
    return () => {
      alive = false;
    };
  }, [projectId, path]);

  if (!path) {
    return (
      <details className="lesson-source" open>
        <summary>Artifact (source text)</summary>
        <p className="muted-note">No source file recorded for this artifact.</p>
      </details>
    );
  }

  return (
    <details className="lesson-source" open>
      <summary>
        Artifact (source text) <span className="mono src-path">{path}</span>
      </summary>
      {err ? (
        <p className="muted-note">Could not load source: {err}</p>
      ) : text == null ? (
        <p className="muted-note">Loading…</p>
      ) : (
        <pre className="source-pre">{text}</pre>
      )}
    </details>
  );
}
