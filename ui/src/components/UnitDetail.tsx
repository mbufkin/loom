import type { Band, OutputFile, UnitRollup, UnitRungUnit } from "../types";

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
}: Props) {
  const title = record?.title ?? rollup?.title ?? unitId;

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
        <UnitFileLinks files={files} onOpenFile={onOpenFile} />
      </div>
    );
  }

  const lessons = record.lessons;
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
        {lessons && (
          <>
            <Stat n={String(lessons.count)} label="Lessons" />
            <Stat
              n={`${lessons.gate_pass}/${lessons.count}`}
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

      {lessons?.mean_coverage &&
        Object.keys(lessons.mean_coverage).length > 0 && (
          <section>
            <h4>Lesson coverage (mean across {lessons.count} lessons)</h4>
            {Object.entries(lessons.mean_coverage).map(([scorer, val]) => (
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
