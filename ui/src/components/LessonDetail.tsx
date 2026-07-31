import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type {
  CurriculumReviewLesson,
  LessonFeedbackLesson,
  ReviewVerdict,
} from "../types";

interface Props {
  lesson: LessonFeedbackLesson;
  // The grounded two-stage curriculum review for this lesson, if generated.
  review?: CurriculumReviewLesson;
  // Needed to fetch the lesson's raw source text from the local API.
  projectId: string;
}

const BAND_LABEL: Record<number, string> = {
  0: "Absent",
  1: "Weak",
  2: "Developing",
  3: "Strong",
};

// Map a 0-3 band onto the same band colour vocabulary the heatmap uses, so a
// lesson's dimension chips read consistently with unit bands.
function bandClass(band: number | null): string {
  if (band == null) return "band-unrated";
  if (band >= 3) return "band-strong";
  if (band === 2) return "band-developing";
  if (band === 1) return "band-weak";
  return "band-weak";
}

function Dots({ band }: { band: number | null }) {
  const n = band ?? 0;
  return (
    <span className="dots" aria-label={`band ${n} of 3`}>
      {"●".repeat(n)}
      {"○".repeat(Math.max(0, 3 - n))}
    </span>
  );
}

// Lesson drill-down: the per-dimension instructional-coach diagnosis for one
// lesson, rendered from LESSON-QUALITY-FEEDBACK.json. Pure presentation — it
// shows exactly what the feedback scorer said, including any cited evidence.
export function LessonDetail({ lesson, review, projectId }: Props) {
  return (
    <div className="ldetail">
      <div className="ldetail-meta mono">
        mean band {lesson.mean_band ?? "—"}/{lesson.max_band ?? 3} ·{" "}
        {lesson.element_count} elements · {lesson.dimensions.length} dimensions
      </div>
      <div className="dim-list">
        {lesson.dimensions.map((d) => (
          <DimensionRow key={d.criterion_id} d={d} />
        ))}
      </div>
      <CurriculumReviewPanel review={review} />
      <SourceText projectId={projectId} path={lesson.source_file} />
    </div>
  );
}

// The grounded curriculum review: a reviewer's read of how the material holds
// together (through-line) plus what it does well / where it falls short. Every
// claim is tied to a real element tag; the evidence map lets us show the actual
// quote behind each cite. Advisory — this describes the material, it never gates.
const VERDICT_CLASS: Record<ReviewVerdict, string> = {
  CONNECTS: "band-strong",
  BREAKS: "band-weak",
  CANNOT_ASSESS: "band-unrated",
};
const VERDICT_LABEL: Record<ReviewVerdict, string> = {
  CONNECTS: "connects",
  BREAKS: "breaks",
  CANNOT_ASSESS: "can't assess",
};
// Turn "objective->instruction" into a readable "objective → instruction".
function linkLabel(link: string): string {
  return link.replace(/->/g, " → ").replace(/_/g, " ");
}

function CurriculumReviewPanel({ review }: { review?: CurriculumReviewLesson }) {
  if (!review) {
    return (
      <section className="creview">
        <div className="creview-head">
          <h4>Curriculum review</h4>
          <span className="creview-tag">advisory · grounded</span>
        </div>
        <p className="muted-note">
          No curriculum review generated for this lesson yet. Run{" "}
          <code>curriculum_review.py</code> (or a full audit) to populate it.
        </p>
      </section>
    );
  }

  // Cite chips carry the actual quote as a tooltip via the evidence map.
  const Cites = ({ ids }: { ids: string[] }) =>
    ids.length === 0 ? null : (
      <span className="creview-cites">
        {ids.map((id) => (
          <span
            key={id}
            className="cite-chip mono"
            title={review.evidence[id]?.excerpt ?? id}
          >
            {id}
          </span>
        ))}
      </span>
    );

  return (
    <section className="creview">
      <div className="creview-head">
        <h4>Curriculum review</h4>
        <span className="creview-tag">
          advisory · grounded · {review.roles_verified}/4 roles anchored
        </span>
      </div>

      <div className="creview-sub">How the material holds together</div>
      <div className="creview-throughline">
        {review.through_line.map((l) => {
          const v = (l.verdict in VERDICT_CLASS
            ? l.verdict
            : "CANNOT_ASSESS") as ReviewVerdict;
          return (
            <div key={l.link} className={`tl-row ${VERDICT_CLASS[v]}`}>
              <span className="tl-link">{linkLabel(l.link)}</span>
              <span className={`tl-verdict ${VERDICT_CLASS[v]}`}>
                {VERDICT_LABEL[v]}
              </span>
              <span className="tl-reason">
                {l.reason || "—"} <Cites ids={l.element_ids} />
              </span>
            </div>
          );
        })}
      </div>

      <div className="creview-cols">
        <div className="creview-col">
          <div className="creview-sub good">What it does well</div>
          {review.does_well.length === 0 ? (
            <p className="muted-note">—</p>
          ) : (
            <ul className="creview-list">
              {review.does_well.map((p, i) => (
                <li key={i}>
                  {p.point} <Cites ids={p.element_ids} />
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="creview-col">
          <div className="creview-sub bad">Where it falls short</div>
          {review.falls_short.length === 0 ? (
            <p className="muted-note">—</p>
          ) : (
            <ul className="creview-list">
              {review.falls_short.map((p, i) => (
                <li key={i}>
                  {p.point} <Cites ids={p.element_ids} />
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <details className="creview-anchors">
        <summary>Anchored evidence ({review.roles_verified}/4 roles)</summary>
        <div className="anchor-list">
          {(["objective", "instruction", "practice", "assessment"] as const).map(
            (role) => {
              const r = review.roles[role];
              return (
                <div key={role} className="anchor-row">
                  <span className="anchor-role">{role}</span>
                  {r ? (
                    <blockquote className="ev-quote">
                      <span className="mono ev-id">{r.tag}</span>
                      {r.excerpt}
                    </blockquote>
                  ) : (
                    <span className="muted-note">not found in this lesson</span>
                  )}
                </div>
              );
            }
          )}
        </div>
      </details>
    </section>
  );
}

// The actual lesson document beneath the review, so a reviewer can read what the
// bands are describing without leaving the panel. Lazy-loaded from the local API
// and open by default (this is the thing the reviewer asked to see).
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
        <summary>Lesson plan (source text)</summary>
        <p className="muted-note">No source file recorded for this lesson.</p>
      </details>
    );
  }

  return (
    <details className="lesson-source" open>
      <summary>
        Lesson plan (source text) <span className="mono src-path">{path}</span>
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

function DimensionRow({
  d,
}: {
  d: LessonFeedbackLesson["dimensions"][number];
}) {
  const [open, setOpen] = useState(false);
  const hasEvidence = d.evidence && d.evidence.length > 0;
  return (
    <div className={`dim ${bandClass(d.band)}`}>
      <div className="dim-head">
        <span className={`swatch ${bandClass(d.band)}`} />
        <span className="dim-label">{d.label}</span>
        <span className="dim-band mono">
          <Dots band={d.band} /> {d.band != null ? BAND_LABEL[d.band] ?? d.band : "—"}
        </span>
      </div>
      <div className="dim-note">{d.note || "—"}</div>
      {hasEvidence && (
        <div className="dim-ev">
          <button className="ev-toggle" onClick={() => setOpen((v) => !v)}>
            {open ? "▾ hide evidence" : "▸ show evidence"}
          </button>
          {open &&
            d.evidence.map((e, i) => (
              <blockquote key={`${e.element_id}-${i}`} className="ev-quote">
                <span className="mono ev-id">{e.element_id}</span>
                {e.excerpt}
              </blockquote>
            ))}
        </div>
      )}
    </div>
  );
}
