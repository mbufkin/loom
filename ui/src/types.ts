// Shared shapes between the local API (ui/server.py) and the review UI.

/** How the Curriculum picker should treat this projects/ folder. */
export type ProjectKind = "curriculum" | "lab" | "other";

export interface Project {
  id: string;
  tier: string;
  /** Human label from manifest when present. */
  title?: string;
  kind?: ProjectKind;
  in_status?: boolean;
  /** 0=Golden … 9=unknown — API already sorts by this. */
  sort_tier?: number;
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
  e2e_run?: string | null;
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

// Per-lesson CURRICULUM REVIEW (output/LESSON-CURRICULUM-REVIEW.json), grouped by
// unit_id like the quality feedback above. This is the two-stage, grounded review
// (curriculum_review.py): the model slots each pedagogical role to a type-correct
// element, then judges the through-line + strengths/shortfalls of the MATERIAL, in
// a reviewer's voice. Every claim cites a real element tag (fabrications dropped).
export type ReviewVerdict = "CONNECTS" | "BREAKS" | "CANNOT_ASSESS";

export interface ReviewLink {
  link: string; // e.g. "objective->instruction"
  verdict: ReviewVerdict;
  reason?: string;
  element_ids: string[];
}
export interface ReviewPoint {
  point: string;
  element_ids: string[];
}
export interface ReviewRole {
  tag: string;
  element_id: string;
  excerpt: string;
}
export interface ReviewEvidence {
  element_id: string;
  excerpt: string;
  role?: string | null;
}
export interface CurriculumReviewLesson {
  lesson_id: string;
  title: string;
  unit_id: string;
  source_file?: string | null;
  scorer?: string;
  seconds?: number;
  roles_verified: number;
  roles: Record<string, ReviewRole | null>;
  through_line: ReviewLink[];
  does_well: ReviewPoint[];
  falls_short: ReviewPoint[];
  evidence: Record<string, ReviewEvidence>;
}
export interface CurriculumReview {
  generated?: string;
  project?: string;
  scorer?: string;
  units: Record<string, CurriculumReviewLesson[]>;
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

/** Create-after-audit gap queue (docs/NEXT-STEPS-BUILD-SPEC.md). */
export type GapDecision = "author" | "pull" | "remove" | null;

export interface GapItem {
  gap_id: string;
  project_id: string;
  unit_id: string;
  unit_title: string;
  kind: "role" | "component" | "artifact_required" | string;
  label: string;
  locus: string;
  pattern: "systemic" | "isolated" | string;
  evidence_refs: string[];
  reasoning?: string;
  decision: GapDecision;
  decision_note: string;
  updated_at?: string | null;
  has_brief: boolean;
  has_draft: boolean;
}

export interface GapsResponse {
  project_id: string;
  count: number;
  gaps: GapItem[];
}

export interface CreateStatus {
  cursor_key_source: string;
  cursor_key_present: boolean;
  cursor_sdk: boolean;
  cursor_sdk_error?: string | null;
  default_model: string;
  note?: string;
}

/** L1 — element type row in the create tree (largest missing first). */
export interface CreateRoleSummary {
  role: string;
  label: string;
  missing: number;
  fulfilled: number;
  pattern: "systemic" | "isolated" | string;
  pending_decisions: number;
}

export interface CreateTreeResponse {
  project_id: string;
  roles: CreateRoleSummary[];
}

/** L2 — one finding slot (missing or present), shared by both axes. */
export interface CreateSlot {
  unit_id: string;
  unit_title: string;
  status: "MISSING" | "FULFILLED" | string;
  locus: string;
  role: string;
  role_label?: string;
  stage?: number;
  reasoning: string;
  fulfilled_by: string[];
  gap_id: string | null;
  decision: GapDecision;
  decision_note: string;
  has_brief: boolean;
  has_draft: boolean;
}

export interface CreateRoleTreeResponse {
  project_id: string;
  role: string;
  label: string;
  pattern: string;
  missing: number;
  fulfilled: number;
  slots: CreateSlot[];
}

/** By-unit L1 row. */
export interface CreateUnitSummary {
  unit_id: string;
  title: string;
  missing: number;
  fulfilled: number;
  pending_decisions: number;
  missing_role_labels: string[];
  missing_role_count: number;
}

export interface CreateUnitsResponse {
  project_id: string;
  units: CreateUnitSummary[];
}

export interface CreateStageBucket {
  id: number;
  key: string;
  label: string;
  missing: number;
  fulfilled: number;
  pending_decisions: number;
  slots?: CreateSlot[];
}

export interface CreateUnitTreeResponse {
  project_id: string;
  unit_id: string;
  title: string;
  missing: number;
  fulfilled: number;
  slots: CreateSlot[];
  stages?: CreateStageBucket[];
  stage1_open?: number;
}

/** Primary Create home — unit matrix with UbD stage rollups. */
export interface CreateMatrixUnit {
  unit_id: string;
  title: string;
  missing: number;
  fulfilled: number;
  pending_decisions: number;
  stage1_open: number;
  stages: CreateStageBucket[];
}

export interface CreateMatrixResponse {
  project_id: string;
  doctrine?: string;
  stage_defs: { id: number; key: string; label: string }[];
  units: CreateMatrixUnit[];
}

/** Full-pipeline snapshot under projects/<id>/e2e/runs/<run_id>/ */
export interface E2ERunInfo {
  run_id: string;
  has_dashboard: boolean;
  has_quality: boolean;
  n_output_units: number;
  n_graph_runs: number;
}

export interface E2ERunsResponse {
  project_id: string;
  runs: E2ERunInfo[];
}

/** Nested graph run under e2e/runs/<e2e>/graph/runs/<run_id>/ (or legacy bare graph/runs). */
export interface GraphRunInfo {
  run_id: string;
  model: string;
  backend?: string | null;
  started_at?: string | null;
  updated_at?: string | null;
  n_units: number;
  n_haspart: number;
  active?: boolean;
}

export interface GraphRunsResponse {
  project_id: string;
  active: string | null;
  e2e_run?: string | null;
  runs: GraphRunInfo[];
}

export interface GraphUnitRollup {
  unit_id: string;
  has_haspart: boolean;
  n_lessons: number;
  n_materials: number;
  n_assessments: number;
  n_soft_queue: number;
  skipped_no_evidence?: string[];
}

export interface GraphOverview {
  project_id: string;
  run_id: string;
  model?: string;
  backend?: string | null;
  units: GraphUnitRollup[];
}

export interface GraphUnitDetail {
  project_id: string;
  run_id: string;
  unit_id: string;
  stats: GraphUnitRollup;
  summary?: Record<string, unknown> | null;
  materials: { id?: string; source_file?: string; role?: string }[];
  assessments: { id?: string; name?: string; source_file?: string }[];
  lessons: { id?: string; name?: string }[];
  has_part?: Record<string, unknown>;
  findings?: Record<string, unknown> | null;
}

/* ---- Paths A–H (review lenses) ---------------------------------------- */

/** Presence outcome for one checklist step on one document. */
export type PathStepStatus =
  | "PRESENT"
  | "PARTIAL"
  | "MISSING"
  | "OPTIONAL_ABSENT"
  | "NOT_APPLICABLE"
  | "STUB"
  | "UNKNOWN";

/** One checklist step rolled up across every document routed to the path. */
export interface PathStep {
  step: string;
  label: string;
  total: number;
  counts: Partial<Record<PathStepStatus, number>>;
  missing: number;
}

/** A document the router assigned to this lens, with the reason it chose it. */
export interface PathDoc {
  doc_id?: string;
  doc_type?: string;
  source_file?: string;
  confidence?: number | null;
  reason?: string;
  element_count?: number;
}

/** Per-document findings row: `<STEP>` keys plus identity fields. */
export type PathInventoryRow = Record<
  string,
  string | number | null | { status?: string; note?: string }
>;

export interface PathSummary {
  letter: string;
  label: string;
  workflow_id: string;
  has_findings: boolean;
  /** ok | skipped | stub | absent */
  status: string;
  routed: number;
  n_docs: number;
  findings_path: string;
  steps: PathStep[];
  missing_total: number;
  top_reasons: { reason: string; count: number }[];
  docs: PathDoc[];
  inventory: PathInventoryRow[];
}

export interface PathsSummary {
  project_id: string;
  e2e_run?: string | null;
  generated_at?: string | null;
  total_routed: number;
  unrouted: number;
  step_statuses: PathStepStatus[];
  paths: PathSummary[];
}
