// Shared shapes between the local API (ui/server.py) and the review UI.

export interface Project {
  id: string;
  tier: string;
  has_output: boolean;
  has_stats: boolean;
  has_unit_rung: boolean;
}

export interface OutputFile {
  label: string;
  path: string;
  type?: string;
}

export interface UnitOutputs {
  unit_id: string;
  title: string;
  files: OutputFile[];
  teacher_files: OutputFile[];
}

export interface OutputsTree {
  plates: OutputFile[];
  layers: OutputFile[];
  pdfs: OutputFile[];
  units: UnitOutputs[];
}

// Subset of output/aggregate-stats.json the UI actually reads.
export interface UnitRollup {
  unit_id: string;
  title: string;
  match: number;
  mismatch: number;
  fulfilled: number;
  missing: number;
  duplicate: number;
}

export interface Stats {
  documents_judged?: number;
  elements_judged?: number;
  review_queue_pending_pairs?: number;
  finding_status_counts?: Record<string, number>;
  status_counts?: Record<string, number>;
  systemic_missing?: { role: string; unit_count: number }[];
  unit_rollup?: UnitRollup[];
}

// Real per-unit record from layer_unit/UNIT-RUNG.json. Every field beyond
// title/band is optional so the UI degrades gracefully for Unrated units (which
// carry no lesson/pacing detail) and for older runs written before a field
// existed. The band swatch overlay only needs {title, band}; the drill-down
// panel renders the rest when present.
export interface UnitRungUnit {
  title: string;
  band: "Strong" | "Developing" | "Weak" | "Unrated";
  lessons?: {
    count: number;
    gate_pass: number;
    gate_pass_rate: number;
    // Keyed by scorer id (s1_completeness, s3_curriculum_own, …) so we render
    // whatever scorers the locked lesson rung emitted without hardcoding names.
    mean_coverage?: Record<string, number>;
  };
  roles?: {
    fulfilled: number;
    missing: number;
    systemic_absent?: string[];
    isolated_gaps?: { role: string; day_id: string }[];
    isolated_gap_total?: number;
  };
  pacing?: {
    planned_days: number;
    evidence_days: number;
    ratio: number | null;
    flag: string;
  };
  internal?: {
    docs_judged: number;
    docs_incomplete: number;
    top_missing_components?: string[];
  };
  cites?: Record<string, string>;
}
export interface UnitRung {
  summary?: { unit_count: number; band_counts: Record<string, number> };
  units?: Record<string, UnitRungUnit>;
}

export type Band = "Strong" | "Developing" | "Weak" | "Unrated";

export interface RunStatus {
  runId: string;
  status: "running" | "done" | "error";
  exitCode: number | null;
  log: string;
}

export interface ConfigSummary {
  models?: Record<string, string | null>;
  keys?: string[];
  error?: string;
}
