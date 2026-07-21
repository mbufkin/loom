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

// Real per-unit bands from layer_unit/UNIT-RUNG.json (optional overlay).
export interface UnitRungUnit {
  band: "Strong" | "Developing" | "Weak" | "Unrated";
  title: string;
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
