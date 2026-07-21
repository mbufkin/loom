import { useState } from "react";
import type { LessonFeedbackLesson } from "../types";

interface Props {
  lesson: LessonFeedbackLesson;
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
export function LessonDetail({ lesson }: Props) {
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
    </div>
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
