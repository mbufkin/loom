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
// Descriptive completeness profile (Chip 1) — present vs. expected components for
// the DECLARED packet type. Never a grade. `null` on the unit means "unknown" (no
// ledger evidence yet), which the UI renders as an em dash rather than 0/N.
export interface UnitCompletenessComponent {
  label: string;
  present: boolean;
  matched: string | null;
  any_of: string[];
}
export interface UnitCompleteness {
  packet_type: string;
  label: string;
  short: string;
  present: number;
  expected: number;
  components: UnitCompletenessComponent[];
  missing: string[];
}

export interface UnitRungUnit {
  title: string;
  band: "Strong" | "Developing" | "Weak" | "Unrated";
  completeness?: UnitCompleteness | null;
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
export interface PacketType {
  id: string;
  label: string;
  short: string;
  description: string;
  expected_components: string[];
}
export interface UnitRung {
  summary?: { unit_count: number; band_counts: Record<string, number> };
  packet_type?: PacketType;
  units?: Record<string, UnitRungUnit>;
}

export type Band = "Strong" | "Developing" | "Weak" | "Unrated";

// Per-lesson quality feedback (output/LESSON-QUALITY-FEEDBACK.json), grouped by
// unit_id so the heatmap unit panel can list and drill into its own lessons.
export interface LessonDimension {
  criterion_id: string;
  label: string;
  band: number | null;
  note: string;
  evidence: { element_id: string; excerpt: string }[];
}
export interface LessonFeedbackLesson {
  lesson_id: string;
  title: string;
  unit_id: string;
  // Project-relative path to the lesson's raw source text (e.g.
  // "sources/doc_…txt"), so the UI can show the actual lesson beneath the review.
  source_file?: string | null;
  mean_band: number | null;
  max_band: number | null;
  element_count: number;
  dimensions: LessonDimension[];
}
export interface LessonFeedback {
  generated?: string;
  project?: string;
  scorer?: string;
  units: Record<string, LessonFeedbackLesson[]>;
}

// Artifact rung (layer_artifact/ARTIFACT-RUNG.json) — the Paths B/C non-lesson
// review, grouped by unit_id so the unit panel can list its own documents and drill
// into a per-doc review (presence gate + advisory alignment, both evidence-cited).
export interface ArtifactCriterion {
  criterion_id: string;
  label: string;
  scoring: string;
  verdict?: string | null;
  band?: number | null;
  evidence: { element_id: string; excerpt: string }[];
  note: string;
}
export interface ArtifactDoc {
  doc_id: string;
  unit_id: string;
  title: string;
  source_file?: string | null;
  role: string;
  doc_type: string;
  is_fallback?: boolean;
  nursery?: boolean;
  presence: {
    gate_pass: boolean;
    coverage: number | null;
    missing_required: string[];
    criteria: ArtifactCriterion[];
  };
  alignment?: {
    applicable: boolean;
    cannot_assess: boolean;
    skipped: boolean;
    mean_band: number | null;
    max_band: number | null;
    anchor_kind: string | null;
    error: string | null;
    criteria: ArtifactCriterion[];
  } | null;
}
export interface ArtifactUnit {
  artifact_count: number;
  gate_pass_count: number;
  gate_pass_rate: number;
  roles: Record<string, number>;
  deterministic_gaps: {
    doc_id: string;
    role: string;
    title: string;
    missing_required: string[];
  }[];
  has_artifact_gap: boolean;
  cannot_assess_alignment: number;
  documents: ArtifactDoc[];
}
export interface ArtifactRung {
  project_id?: string;
  with_model?: boolean;
  summary?: {
    artifact_count: number;
    gate_pass_count: number;
    unit_count: number;
    roles: Record<string, number>;
    nursery_count: number;
  };
  units: Record<string, ArtifactUnit>;
}

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
