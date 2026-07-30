// Overview — distilled meeting deck.
// Phase boxes (A–D) are clickable: open an inline detail panel with a clearer
// flow diagram for that stage. Same neo-brutalist tokens as Review.

import { useEffect, useState } from "react";

interface Step {
  t: string;
  d: string;
}

interface FlowNode {
  label: string;
  note?: string;
}

interface Phase {
  n: string;
  name: string;
  tag: string;
  steps: Step[];
  // Detail panel — what opens when the phase box is clicked.
  blurb: string;
  flow: FlowNode[];
  outputs: string[];
}

const PHASES: Phase[] = [
  {
    n: "A",
    name: "Decode",
    tag: "layer 0–1",
    steps: [
      { t: "Decompose", d: "PDF → elements + evidence spans" },
      { t: "Classify", d: "doc type · graceful fallback" },
    ],
    blurb:
      "One document at a time. The local model reads the full file, pulls instructional elements with verbatim citations, then classifies the doc type so later stages know which workflow to run.",
    flow: [
      { label: "Source file", note: "PDF · Word · slides · text" },
      { label: "Decompose", note: "elements + evidence spans" },
      { label: "Classify", note: "lesson · quiz · general · fallback" },
      { label: "Route map", note: "layer0/route-map.json" },
    ],
    outputs: [
      "Cited element ledger per document",
      "Doc type + confidence",
      "Unknown types → Path C + feedback log (never a hard fail)",
    ],
  },
  {
    n: "B",
    name: "Organize",
    tag: "layer 1–2",
    steps: [
      { t: "Match", d: "elements → units · roles · standards" },
      { t: "Completeness", d: "expected vs. present" },
    ],
    blurb:
      "Routed documents are placed into units against the day grid and packet type. The system compares what the calendar expects with what was found — MATCH, MISMATCH, MISSING, ORPHAN — always with a citation.",
    flow: [
      { label: "Routed docs", note: "from Decode" },
      { label: "Place into units", note: "roles · days · standards" },
      { label: "Completeness", note: "expected vs present" },
      { label: "Findings", note: "MATCH · MISSING · ORPHAN …" },
    ],
    outputs: [
      "Per-unit role fulfillment",
      "Systemic vs isolated gaps",
      "Packet-type completeness score (not a grade)",
    ],
  },
  {
    n: "C",
    name: "Review",
    tag: "the rungs",
    steps: [
      { t: "Lesson quality", d: "7 criteria · per-criterion · cited" },
      { t: "Artifact check", d: "presence gate + alignment" },
    ],
    blurb:
      "Two axes on what is already present: lesson quality (criteria with evidence) and artifact presence/alignment. Weak material is called weak honestly — the auditor never invents a fix.",
    flow: [
      { label: "Fulfilled lessons", note: "Path A" },
      { label: "Quality rung", note: "7 criteria · cited" },
      { label: "Artifacts", note: "Path B/C · presence gate" },
      { label: "Bands", note: "Strong · Developing · Weak" },
    ],
    outputs: [
      "Per-lesson dimension notes with excerpts",
      "Artifact gate pass / missing required parts",
      "Unit rung band for the heatmap",
    ],
  },
  {
    n: "D",
    name: "Deliver",
    tag: "dashboard",
    steps: [{ t: "Director view", d: "verdicts · drill-down · this site" }],
    blurb:
      "Everything rolls up into director-ready packets and this local review console. Drill from curriculum → unit → lesson/artifact without leaving the workstation.",
    flow: [
      { label: "Unit rungs", note: "bands + completeness" },
      { label: "First-pass packet", note: "priorities · decide per gap" },
      { label: "This site", note: "heatmap · drill-down" },
      { label: "PDF + Drive", note: "director + teacher views" },
    ],
    outputs: [
      "GLOBAL-AUDIT / FIRST-PASS work packet",
      "Unit heatmap on Review",
      "Teacher packets when configured",
    ],
  },
];

const LESSON_TILES = ["Objective", "Hook", "Guided", "Practice", "Assess"];
const UNIT_TILES = ["Unit 1", "Unit 2", "Unit 3"];

interface Stage {
  label: string;
  note: string;
  state: "done" | "here" | "future";
}

const ARC: Stage[] = [
  { label: "Concept", note: "audit curriculum, locally", state: "done" },
  {
    label: "Working engine",
    note: "runs end-to-end on real curricula · evidence-cited · fully local",
    state: "here",
  },
  {
    label: "Design-partner v1.0",
    note: "a district installs & runs it themselves",
    state: "future",
  },
  {
    label: "Product",
    note: "any district · supported · at scale",
    state: "future",
  },
];

function PhaseDetail({
  phase,
  onClose,
}: {
  phase: Phase;
  onClose: () => void;
}) {
  return (
    <div className="ov-detail" role="region" aria-label={`${phase.name} detail`}>
      <div className="ov-detail-head">
        <button type="button" className="ov-detail-close" onClick={onClose}>
          Close
        </button>
        <span className="ov-phase-n mono">{phase.n}</span>
        <span className="ov-detail-title">{phase.name}</span>
        <span className="ov-phase-tag mono">{phase.tag}</span>
      </div>
      <div className="ov-detail-body">
        <p className="ov-detail-blurb">{phase.blurb}</p>

        <div className="ov-detail-cap mono">What happens in this phase</div>
        <div className="ov-detail-flow">
          {phase.flow.map((node, i) => (
            <div className="ov-detail-flow-item" key={node.label}>
              <div className="ov-detail-node">
                <span className="ov-detail-node-t">{node.label}</span>
                {node.note && (
                  <span className="ov-detail-node-d mono">{node.note}</span>
                )}
              </div>
              {i < phase.flow.length - 1 && (
                <span className="ov-detail-arrow" aria-hidden />
              )}
            </div>
          ))}
        </div>

        <div className="ov-detail-cap mono">What you get</div>
        <ul className="ov-detail-outs">
          {phase.outputs.map((o) => (
            <li key={o}>{o}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function Overview() {
  const [openPhase, setOpenPhase] = useState<string | null>(null);
  const active = PHASES.find((p) => p.n === openPhase) ?? null;

  // Escape closes the detail panel — same muscle memory as dismissing a modal.
  useEffect(() => {
    if (!openPhase) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenPhase(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [openPhase]);

  return (
    <div className="ov ov-compact">
      <header className="ov-hero">
        <div>
          <div className="ov-kicker">On-device curriculum intelligence · K-12</div>
          <h1 className="ov-title">
            What&apos;s in the curriculum — and is it any good?
          </h1>
          <p className="ov-lead">
            Point it at a district&apos;s curriculum. It tells you{" "}
            <b>what&apos;s there, what&apos;s missing, and how good it is</b> —
            every judgment quoted from the source, nothing leaving the building.
            Works on any pack via a <b>declared packet type</b> — no per-district
            engineering.
          </p>
        </div>
        <div className="ov-pills">
          <span className="ov-pill">
            <i className="dot nv" /> NVIDIA Nemotron · local
          </span>
          <span className="ov-pill">
            <i className="dot ln" /> Lenovo workstation
          </span>
          <span className="ov-pill">
            <i className="dot ink" /> 0 bytes to the cloud
          </span>
        </div>
      </header>

      <section className="ov-sec">
        <h2 className="ov-h">How it works — four phases, layered</h2>
        <p className="ov-hint mono">Click a phase for the diagram</p>
        <div className="ov-spine">
          {PHASES.map((p) => {
            const selected = openPhase === p.n;
            return (
              <button
                type="button"
                className={`ov-phase ov-phase-btn${selected ? " is-open" : ""}`}
                key={p.n}
                aria-expanded={selected}
                aria-controls="ov-phase-detail"
                onClick={() => setOpenPhase(selected ? null : p.n)}
              >
                <div className="ov-phase-head">
                  <span className="ov-phase-n">{p.n}</span>
                  <span className="ov-phase-name">{p.name}</span>
                  <span className="ov-phase-tag mono">{p.tag}</span>
                </div>
                <div className="ov-phase-steps">
                  {p.steps.map((s) => (
                    <div className="ov-step" key={s.t}>
                      <span className="ov-step-body">
                        <b className="ov-step-t">{s.t}</b>
                        <span className="ov-step-d mono">{s.d}</span>
                      </span>
                    </div>
                  ))}
                </div>
                <span className="ov-phase-cta mono">
                  {selected ? "Hide diagram" : "Open diagram"}
                </span>
              </button>
            );
          })}
        </div>

        {active && (
          <div id="ov-phase-detail">
            <PhaseDetail
              phase={active}
              onClose={() => setOpenPhase(null)}
            />
          </div>
        )}

        <div className="ov-fall">
          <div className="ov-fall-cap mono">
            The waterfall · every level aggregates the evidence beneath it
          </div>
          <div className="ov-tier ov-tier-l">
            <span className="ov-tier-lab">Lessons</span>
            <div className="ov-tier-row">
              {LESSON_TILES.map((t) => (
                <span className="ov-tile" key={t}>
                  {t}
                </span>
              ))}
            </div>
          </div>
          <div className="ov-fall-arrow" aria-hidden />
          <div className="ov-tier ov-tier-u">
            <span className="ov-tier-lab">Units</span>
            <div className="ov-tier-row">
              {UNIT_TILES.map((t) => (
                <span className="ov-tile ov-tile-u" key={t}>
                  {t}
                  <i className="ov-axes">
                    <em className="qa" />
                    <em className="co" />
                  </i>
                </span>
              ))}
            </div>
            <span className="ov-tier-note mono">
              two axes · quality × completeness
            </span>
          </div>
          <div className="ov-fall-arrow" aria-hidden />
          <div className="ov-tier ov-tier-c">
            <span className="ov-tier-lab">Curriculum</span>
            <div className="ov-tier-row">
              <span className="ov-tile ov-tile-c">Portfolio verdict</span>
            </div>
          </div>
        </div>

        <div className="ov-local">
          <span className="ov-lock mono">local</span>
          <b>All of it runs on the workstation.</b>
          <span className="mono ov-localnote">
            5 curricula audited · local Nemotron · 0 bytes to the cloud
          </span>
        </div>
      </section>

      <section className="ov-sec">
        <h2 className="ov-h">Why it can only work this way</h2>
        <div className="ov-pillars ov-pillars-2">
          <div className="ov-pillar">
            <div className="ov-ph">
              <i className="tick" /> Private by design
            </div>
            <p>
              Curriculum and student data <b>never leave the building</b>. Cloud
              LLMs are a non-starter for districts — local inference is the only
              path they can adopt.
            </p>
          </div>
          <div className="ov-pillar">
            <div className="ov-ph">
              <i className="tick" /> Evidence, not opinions
            </div>
            <p>
              Every verdict <b>quotes the source text</b>. Two separate axes: is
              it complete for its packet type, and is what&apos;s there any good.
              No hallucinated grades.
            </p>
          </div>
        </div>
      </section>

      <section className="ov-sec">
        <h2 className="ov-h">From working engine to product</h2>
        <div className="ov-arc">
          {ARC.map((s, i) => (
            <div className={`ov-arc-node is-${s.state}`} key={s.label}>
              {s.state === "here" && (
                <span className="ov-arc-here">you are here</span>
              )}
              <div className="ov-arc-dot">
                {s.state === "done" ? "ok" : i + 1}
              </div>
              <span className="ov-arc-label">{s.label}</span>
              <span className="ov-arc-note">{s.note}</span>
            </div>
          ))}
        </div>
        <p className="ov-next-line mono">
          Next · design-partner v1.0 — package, first-run bootstrap, calibrate
          scores. Mechanical productizing, not more invention.
        </p>
      </section>

      <div className="ov-foot mono">Local curriculum audit · on-device</div>
    </div>
  );
}
