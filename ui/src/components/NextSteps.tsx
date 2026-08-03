// Next Steps — work queue (default) + agent-workflow deck ("How it works").
// Queue is the product; the deck stays interview-safe presentation.
// Build notes stay off the deck subview.

import { useState } from "react";
import { CreateStudio } from "./CreateStudio";

type NodeKind =
  | "source"
  | "agent"
  | "stage"
  | "process"
  | "gate"
  | "diagnoser"
  | "dataset"
  | "ship";

interface FlowNode {
  id: string;
  kind: NodeKind;
  title: string;
  sub?: string;
  detail?: string;
  badge?: string;
}

const LEGEND: { kind: NodeKind; label: string }[] = [
  { kind: "source", label: "External / Data Source" },
  { kind: "dataset", label: "Dataset / Collection" },
  { kind: "agent", label: "ML / Agent Service" },
  { kind: "stage", label: "Frontend / Pipeline Stage" },
  { kind: "process", label: "Backend / Processing" },
  { kind: "gate", label: "QA / Eval Gate" },
  { kind: "diagnoser", label: "Security / Diagnoser" },
  { kind: "ship", label: "Deploy / Register" },
];

function Node({ n }: { n: FlowNode }) {
  return (
    <div className={`ns-node kind-${n.kind}`} data-id={n.id}>
      {n.badge && <span className="ns-badge mono">{n.badge}</span>}
      <span className="ns-node-kind mono">{kindLabel(n.kind)}</span>
      <span className="ns-node-t">{n.title}</span>
      {n.sub && <span className="ns-node-sub mono">{n.sub}</span>}
      {n.detail && <span className="ns-node-d">{n.detail}</span>}
    </div>
  );
}

function kindLabel(k: NodeKind): string {
  switch (k) {
    case "source":
      return "source";
    case "dataset":
      return "dataset";
    case "agent":
      return "agent";
    case "stage":
      return "stage";
    case "process":
      return "process";
    case "gate":
      return "qa gate";
    case "diagnoser":
      return "diagnoser";
    case "ship":
      return "deploy";
  }
}

function Arrow({
  label,
  tone = "mute",
}: {
  label?: string;
  tone?: "pass" | "fail" | "enhance" | "mute";
}) {
  return (
    <div className={`ns-arrow tone-${tone}`} aria-hidden>
      {label && <span className="ns-arrow-lab mono">{label}</span>}
      <span className="ns-arrow-line" />
    </div>
  );
}

function NextStepsDeck() {
  return (
    <div className="ov ns">
      <header className="ov-hero">
        <div>
          <h1 className="ov-title">Loom · Missing-Element Agent Flow</h1>
        </div>
      </header>

      {/* ── 01 Production Agent Pipeline ─────────────────────────────── */}
      <section className="ov-sec">
        <h2 className="ov-h">01 · Production Agent Pipeline</h2>

        <div className="ns-pipeline">
          <Node
            n={{
              id: "src",
              kind: "source",
              title: "Curriculum Pack",
              sub: "Raw Upload",
              detail: "PDF · Word · slides · text",
            }}
          />
          <Arrow label="Sources" />

          <div className="ns-route">
            <div className="ns-skip">
              <span className="ns-skip-lab mono">Complete — no create needed</span>
              <Node
                n={{
                  id: "ok",
                  kind: "process",
                  title: "Quality OK · Report",
                  detail: "Original pack preserved → Director packet",
                }}
              />
            </div>
            <Node
              n={{
                id: "route",
                kind: "agent",
                title: "Audit · Routing Agent",
                sub: "Local multimodal LLM",
                detail: "Decompose · classify · find gaps",
                badge: "today",
              }}
            />
          </div>

          <Arrow label="Gaps found" tone="enhance" />

          <Node
            n={{
              id: "triage",
              kind: "stage",
              title: "Gap Triage",
              sub: "Per-slot decision",
              detail: "Author · Pull · Remove",
            }}
          />
          <Arrow label="Brief" />

          <div className="ns-loop">
            <span className="ns-loop-lab mono">K loops</span>
            <Node
              n={{
                id: "create",
                kind: "process",
                title: "Create Agent",
                sub: "Human-supervised draft",
                detail: "Fill the missing element",
                badge: "next",
              }}
            />
          </div>
          <Arrow label="Candidate" />

          <div className="ns-gate">
            <Node
              n={{
                id: "qa",
                kind: "gate",
                title: "QA Gate · Re-audit",
                sub: "Multi-dimension eval",
                detail: "Presence · Alignment · Citations",
              }}
            />
            <span className="ns-fail mono">FAIL · Feedback + retry ↺</span>
          </div>
          <Arrow label="PASS" tone="pass" />

          <Node
            n={{
              id: "pubqa",
              kind: "diagnoser",
              title: "Publish-Ready QA",
              sub: "Policy + quality checks",
              detail: "Auditor boundary · Swiss cheese",
            }}
          />
          <Arrow label="" tone="pass" />

          <Node
            n={{
              id: "out",
              kind: "stage",
              title: "Delivered Packet",
              sub: "Director + teacher views",
              detail: "Gap closed · evidence logged",
            }}
          />
        </div>

        <div className="ns-trace mono">
          All agents log to flat JSON — every step traceable · citations never
          leave the box
        </div>
      </section>

      {/* ── 02 Continuous Learning ───────────────────────────────────── */}
      <section className="ov-sec">
        <h2 className="ov-h">02 · Continuous Learning &amp; Feedback Loops</h2>

        <div className="ns-learn">
          <div className="ns-learn-col">
            <Node
              n={{
                id: "golden",
                kind: "dataset",
                title: "Golden Dataset",
                detail: "Hand-checked findings · cited ground truth",
              }}
            />
            <span className="ns-v mono">↓</span>
            <Node
              n={{
                id: "offline",
                kind: "process",
                title: "Offline Tuning",
                detail: "Agent output vs. golden · guardrail metrics",
              }}
            />
            <span className="ns-skip-lab mono">Ship</span>
          </div>

          <div className="ns-learn-col">
            <Node
              n={{
                id: "feedback",
                kind: "dataset",
                title: "Feedback Sources",
                detail:
                  "Production drift · Dogfooding · Director review · District metrics",
              }}
            />
            <span className="ns-skip-lab mono">Sample →</span>
          </div>

          <Node
            n={{
              id: "diag",
              kind: "diagnoser",
              title: "Diagnoser Agent",
              detail: "Locate issue · Route fix",
            }}
          />
          <Arrow label="Trigger" tone="enhance" />

          <div className="ns-subsystem">
            <span className="ns-subsystem-lab mono">Auto-Tuning Pipeline</span>
            <Node
              n={{
                id: "reflect",
                kind: "agent",
                title: "Reflect",
                detail: "Denoise + find systemics",
              }}
            />
            <Arrow label="" />
            <Node
              n={{
                id: "synth",
                kind: "agent",
                title: "Synthesize",
                detail: "Write new agent config",
              }}
            />
          </div>
          <Arrow label="" />

          <div className="ns-gate">
            <Node
              n={{
                id: "bench",
                kind: "gate",
                title: "Benchmark vs. Golden",
                detail: "Pass · Register new agent",
              }}
            />
            <span className="ns-fail mono">Fail · re-tune pipeline ↺</span>
          </div>
          <Arrow label="PASS" tone="pass" />

          <Node
            n={{
              id: "deploy",
              kind: "ship",
              title: "New agent version",
              detail: "Registered + deployed → Create Agent",
            }}
          />
        </div>
      </section>

      <div className="ns-legend">
        {LEGEND.map((l) => (
          <span className="ns-legend-item" key={l.kind}>
            <i className={`ns-swatch kind-${l.kind}`} />
            <span className="mono">{l.label}</span>
          </span>
        ))}
      </div>

    </div>
  );
}

export function NextSteps({ projectId }: { projectId: string }) {
  const [mode, setMode] = useState<"studio" | "deck">("studio");
  return (
    <div className={mode === "studio" ? "cs-shell" : "ns-shell"}>
      <div className="ns-mode" role="group" aria-label="next steps mode">
        <button
          type="button"
          aria-pressed={mode === "studio"}
          className={mode === "studio" ? "on" : ""}
          onClick={() => setMode("studio")}
        >
          Create studio
        </button>
        <button
          type="button"
          aria-pressed={mode === "deck"}
          className={mode === "deck" ? "on" : ""}
          onClick={() => setMode("deck")}
        >
          How it works
        </button>
      </div>
      {mode === "studio" ? (
        <CreateStudio projectId={projectId} />
      ) : (
        <NextStepsDeck />
      )}
    </div>
  );
}
