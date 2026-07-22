import type {
  ArtifactDoc,
  ArtifactUnit,
  Band,
  LessonFeedbackLesson,
  OutputFile,
  UnitRollup,
  UnitRungUnit,
} from "../types";

interface Props {
  unitId: string;
  // The rich per-unit record from the unit rung (may be undefined for projects
  // without a unit rung, or for a unit_id the rung never scored).
  record?: UnitRungUnit;
  // Layer 1 rollup counts (matched/mismatch) from aggregate-stats — complements
  // the rung's role fulfillment view.
  rollup?: UnitRollup;
  // The per-unit output files (Gap report, Calendar map, Audit PDF, stub Report)
  // so we can link out to the deeper artifacts instead of hiding them.
  files: OutputFile[];
  band: Band;
  onOpenFile: (path: string, type: string) => void;
  // Per-lesson quality feedback for THIS unit (from LESSON-QUALITY-FEEDBACK.json);
  // empty when the feedback report has not been generated or the unit has no
  // enumerated lessons yet. Clicking one drills into the LessonDetail view.
  lessons?: LessonFeedbackLesson[];
  onSelectLesson?: (lessonId: string) => void;
  // The artifact rung's per-unit block (from ARTIFACT-RUNG.json): every NON-lesson
  // doc reviewed for this unit. Absent until the artifact rung has run. Clicking a
  // doc drills into the ArtifactDetail per-doc review.
  artifacts?: ArtifactUnit;
  onSelectArtifact?: (docId: string) => void;
}

function lessonBandClass(band: number | null | undefined, max = 3): string {
  if (band == null) return "band-unrated";
  const pct = band / (max || 3);
  if (pct >= 0.67) return "band-strong";
  if (pct >= 0.34) return "band-developing";
  return "band-weak";
}

const BAND_CLASS: Record<Band, string> = {
  Strong: "band-strong",
  Developing: "band-developing",
  Weak: "band-weak",
  Unrated: "band-unrated",
};

// Human labels for the pacing flag enum emitted by unit_rung.py.
const PACING_LABEL: Record<string, string> = {
  OK: "On pace",
  UNDER_COVERED: "Under-covered",
  OVER_COVERED: "Over-covered",
  NO_PLAN: "No pacing plan",
};

function pct(n: number): string {
  return `${Math.round(n * 100)}%`;
}

// Human-readable labels for the universal role enum, so a reviewer reads
// "Exit ticket" rather than the raw `exit_ticket` doc_type. Unknown roles fall back
// to a title-cased version of whatever the classifier emitted.
const ROLE_LABEL: Record<string, string> = {
  exit_ticket: "Exit ticket",
  quiz: "Quiz",
  answer_key: "Answer key",
  rubric: "Rubric",
  worksheet: "Worksheet",
  project_work: "Project",
  presentation: "Slides",
  game_activity: "Activity",
  lab_activity: "Lab",
  flex_day: "Flex day",
  lesson_content: "Lesson content",
  other: "Other",
};

function roleLabel(role: string): string {
  return (
    ROLE_LABEL[role] ??
    role
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ")
  );
}

// One document row in the unit's inventory: a type tag, the title, and a plain
// status (complete, or the specific parts it is missing). Clicking opens the
// per-doc ArtifactDetail review.
//
// NOTE: the model-based ALIGNMENT verdict ("Aligned / Not aligned") is intentionally
// NOT surfaced here. Presence/completeness is deterministic and trustworthy; the
// alignment band is still advisory and under-validated, so showing it would make a
// stronger claim than we can stand behind today. The data still rides along on
// ArtifactDoc.alignment for when we re-enable it — see docs/ARTIFACT-ALIGNMENT-DEFERRED.md.
function DocRow({ doc, onClick }: { doc: ArtifactDoc; onClick: () => void }) {
  const complete = doc.presence.gate_pass;
  const missing = doc.presence.missing_required ?? [];
  const statusCls = complete ? "ok" : "bad";
  const statusText = complete
    ? "Complete"
    : missing.length > 0
    ? `Missing ${missing[0]}${missing.length > 1 ? ` +${missing.length - 1}` : ""}`
    : "Incomplete";
  return (
    <button className={`doc-row ${statusCls}`} onClick={onClick}>
      <span className="doc-type">{roleLabel(doc.role)}</span>
      <span className="doc-main">
        <span className="doc-title">{doc.title}</span>
        <span className="doc-status">
          <span className={`dot ${statusCls}`} />
          {statusText}
        </span>
      </span>
      <span className="doc-arrow">→</span>
    </button>
  );
}

// A single "big number" stat tile, mirroring the review-slip stat styling.
function Stat({ n, label }: { n: string; label: string }) {
  return (
    <div className="stat">
      <div className="n">{n}</div>
      <div className="l">{label}</div>
    </div>
  );
}

// The unit drill-down. Renders the deterministic unit-rung verdict (band,
// lesson gate stats, role gaps, pacing, internal completeness) that we already
// compute but previously never surfaced — plus links to the deeper per-unit
// reports. This is a pure presentation of layer_unit/UNIT-RUNG.json; it invents
// nothing.
export function UnitDetail({
  unitId,
  record,
  rollup,
  files,
  band,
  onOpenFile,
  lessons = [],
  onSelectLesson,
  artifacts,
  onSelectArtifact,
}: Props) {
  const title = record?.title ?? rollup?.title ?? unitId;

  const artifactDocs = artifacts?.documents ?? [];
  const gapCount = artifactDocs.filter((d) => !d.presence.gate_pass).length;
  const documentsSection =
    artifactDocs.length > 0 ? (
      <section>
        <div className="section-head">
          <h4>Documents</h4>
          <span className="count-tag">{artifactDocs.length}</span>
          {gapCount > 0 && (
            <span className="chip warn">
              {gapCount} incomplete
            </span>
          )}
        </div>
        <div className="doc-list">
          {artifactDocs.map((d) => (
            <DocRow
              key={d.doc_id}
              doc={d}
              onClick={() => onSelectArtifact?.(d.doc_id)}
            />
          ))}
        </div>
      </section>
    ) : null;

  const lessonsSection =
    lessons.length > 0 ? (
      <section>
        <h4>Lessons ({lessons.length}) — click for the full quality breakdown</h4>
        <div className="lesson-list">
          {lessons.map((l) => (
            <button
              key={l.lesson_id}
              className={`lesson-row ${lessonBandClass(l.mean_band, l.max_band ?? 3)}`}
              onClick={() => onSelectLesson?.(l.lesson_id)}
            >
              <span className={`swatch ${lessonBandClass(l.mean_band, l.max_band ?? 3)}`} />
              <span className="lesson-title">{l.title}</span>
              <span className="lesson-meta mono">
                mean {l.mean_band ?? "—"}/{l.max_band ?? 3}
              </span>
              <span className="lesson-arrow">→</span>
            </button>
          ))}
        </div>
      </section>
    ) : null;

  // No rung record: be honest about why, and still offer the raw artifacts.
  if (!record) {
    return (
      <div className="udetail">
        <div className={`band-head ${BAND_CLASS[band]}`}>
          <span className={`swatch ${BAND_CLASS[band]}`} />
          <span className="u-title">{title}</span>
          <span className={`u-band ${BAND_CLASS[band]}`}>{band}</span>
        </div>
        <p className="muted-note">
          No unit-rung record for <code>{unitId}</code>. This project may predate
          the unit rung, or need a re-run. The band above is derived from Layer 1
          role fulfillment.
        </p>
        {lessonsSection}
        {documentsSection}
        <section>
          <h4>Deeper reports</h4>
          <UnitFileLinks files={files} onOpenFile={onOpenFile} />
        </section>
      </div>
    );
  }

  const rungLessons = record.lessons;
  const roles = record.roles;
  const pacing = record.pacing;
  const internal = record.internal;
  const rolesTotal = roles ? roles.fulfilled + roles.missing : 0;

  return (
    <div className="udetail">
      <div className={`band-head ${BAND_CLASS[band]}`}>
        <span className={`swatch ${BAND_CLASS[band]}`} />
        <span className="u-title">{title}</span>
        <span className={`u-band ${BAND_CLASS[band]}`}>{record.band}</span>
      </div>

      <div className="stat-grid">
        {rungLessons && (
          <>
            <Stat n={String(rungLessons.count)} label="Lessons" />
            <Stat
              n={`${rungLessons.gate_pass}/${rungLessons.count}`}
              label="Gate pass"
            />
          </>
        )}
        {roles && (
          <Stat
            n={rolesTotal > 0 ? pct(roles.fulfilled / rolesTotal) : "—"}
            label="Roles present"
          />
        )}
        {pacing && (
          <Stat
            n={`${pacing.evidence_days}/${pacing.planned_days}`}
            label="Days covered"
          />
        )}
      </div>

      {rungLessons?.mean_coverage &&
        Object.keys(rungLessons.mean_coverage).length > 0 && (
          <section>
            <h4>Lesson coverage (mean across {rungLessons.count} lessons)</h4>
            {Object.entries(rungLessons.mean_coverage).map(([scorer, val]) => (
              <div className="cov" key={scorer}>
                <span className="cov-label mono">{scorer}</span>
                <span className="cov-track">
                  <span
                    className="cov-fill"
                    style={{ width: pct(val) }}
                  />
                </span>
                <span className="cov-val mono">{pct(val)}</span>
              </div>
            ))}
          </section>
        )}

      {roles && (
        <section>
          <h4>
            Role gaps — {roles.fulfilled} fulfilled · {roles.missing} missing
          </h4>
          {roles.systemic_absent && roles.systemic_absent.length > 0 && (
            <p className="sub">
              Systemically absent (a pattern, not a per-lesson flag):
              <br />
              {roles.systemic_absent.map((r) => (
                <span className="chip warn" key={r}>
                  {r}
                </span>
              ))}
            </p>
          )}
          {roles.isolated_gaps && roles.isolated_gaps.length > 0 && (
            <p className="sub">
              Isolated gaps ({roles.isolated_gap_total ?? roles.isolated_gaps.length}):
              <br />
              {roles.isolated_gaps.map((g, i) => (
                <span className="chip" key={`${g.role}-${g.day_id}-${i}`}>
                  {g.role} <span className="mono">@{g.day_id}</span>
                </span>
              ))}
            </p>
          )}
          {(!roles.systemic_absent || roles.systemic_absent.length === 0) &&
            (!roles.isolated_gaps || roles.isolated_gaps.length === 0) && (
              <p className="sub muted-note">No role gaps recorded.</p>
            )}
        </section>
      )}

      {internal && (
        <section>
          <h4>
            Lesson-internal completeness — {internal.docs_incomplete}/
            {internal.docs_judged} lessons incomplete
          </h4>
          {internal.top_missing_components &&
          internal.top_missing_components.length > 0 ? (
            <p className="sub">
              Most-missing components:
              <br />
              {internal.top_missing_components.map((c) => (
                <span className="chip warn" key={c}>
                  {c}
                </span>
              ))}
            </p>
          ) : (
            <p className="sub muted-note">No missing components recorded.</p>
          )}
        </section>
      )}

      {pacing && (
        <section>
          <h4>Pacing</h4>
          <p className="sub">
            <span
              className={`chip ${pacing.flag === "OK" ? "ok" : "warn"}`}
            >
              {PACING_LABEL[pacing.flag] ?? pacing.flag}
            </span>
            {pacing.evidence_days} evidence day
            {pacing.evidence_days === 1 ? "" : "s"} vs {pacing.planned_days}{" "}
            planned
            {pacing.ratio != null ? ` (ratio ${pacing.ratio})` : ""}
          </p>
        </section>
      )}

      {lessonsSection}
      {documentsSection}

      <section>
        <h4>Deeper reports</h4>
        <UnitFileLinks files={files} onOpenFile={onOpenFile} />
      </section>
    </div>
  );
}

// Link list to the per-unit artifacts. Hides the thin stub "Report" when richer
// files exist, but keeps everything else one click away.
function UnitFileLinks({
  files,
  onOpenFile,
}: {
  files: OutputFile[];
  onOpenFile: (path: string, type: string) => void;
}) {
  if (files.length === 0) {
    return <p className="muted-note">No per-unit report files on disk yet.</p>;
  }
  return (
    <div className="quick-links">
      {files.map((f) => (
        <a
          key={f.path}
          href="#"
          onClick={(e) => {
            e.preventDefault();
            onOpenFile(f.path, f.type ?? "md");
          }}
        >
          {f.label} {f.type === "pdf" ? "↗" : ""}
        </a>
      ))}
    </div>
  );
}
