import type { Band, UnitCompleteness, UnitRollup } from "../types";

interface Props {
  rollup: UnitRollup;
  band: Band;
  // Descriptive completeness profile for Chip 1 (present vs. expected for the
  // declared packet type). `null`/undefined => unknown (rendered as an em dash).
  completeness?: UnitCompleteness | null;
  onOpen: () => void;
}

const BAND_CLASS: Record<Band, string> = {
  Strong: "band-strong",
  Developing: "band-developing",
  Weak: "band-weak",
  Unrated: "band-unrated",
};

// The two chips deliberately answer two DIFFERENT questions and never blur:
//   Chip 1 (packet + completeness) — "what kind of packet is this and how whole
//     is it FOR THAT KIND?"  Descriptive, neutral, never red.
//   Chip 2 (quality) — "how good is the material that IS here?"  This is the
//     graded band and the only thing that carries the row's quality color.
function PacketChip({ c }: { c?: UnitCompleteness | null }) {
  // Unknown completeness (no ledger evidence yet) -> honest em dash, not 0/N.
  if (!c) {
    return (
      <span className="chip-pkt" title="No decomposed evidence yet — completeness unknown">
        <span className="pkt-type">—</span>
        <span className="pkt-comp">
          <span className="comp-num">—</span>
        </span>
      </span>
    );
  }
  const tip =
    `${c.label} expects ${c.expected} component(s); this unit has ${c.present}. ` +
    `Descriptive — it does not lower the quality grade.` +
    (c.missing.length ? ` Missing: ${c.missing.join(", ")}.` : "");
  return (
    <span className="chip-pkt" title={tip}>
      <span className="pkt-type">{c.short}</span>
      <span className="pkt-comp">
        <span className="segs">
          {c.components.map((comp) => (
            <i
              key={comp.label}
              className={comp.present ? "on" : "off"}
              title={`${comp.label}: ${comp.present ? "present" : "not found"}`}
            />
          ))}
        </span>
        <span className="comp-num">
          {c.present}/{c.expected}
        </span>
      </span>
    </span>
  );
}

// One banded heatmap row per unit — the Loom analogue of Fairway's TierRow.
export function UnitOutputRow({ rollup, band, completeness, onOpen }: Props) {
  const total = rollup.fulfilled + rollup.missing;
  const pct = total > 0 ? Math.round((rollup.fulfilled / total) * 100) : null;
  return (
    <button className="unit-row" onClick={onOpen} title="Open unit report">
      <span className={`swatch ${BAND_CLASS[band]}`} />
      <span>
        <span className="u-title">{rollup.title}</span>
        <br />
        <span className="u-metrics">
          {rollup.match} matched · {rollup.fulfilled} fulfilled ·{" "}
          {rollup.missing} missing
          {pct !== null ? ` · ${pct}% roles present` : ""}
        </span>
      </span>
      {/* Two fixed grid columns so the packet tags line up in one straight
          vertical line and the quality bands in another — the whitespace after
          the title is the only thing that varies (a scannable table). */}
      <PacketChip c={completeness} />
      <span
        className={`chip-qual ${BAND_CLASS[band]}`}
        title="Quality of the material that IS here. Systemic curriculum-wide gaps and pacing do not push this down."
      >
        <span className={`dot ${BAND_CLASS[band]}`} />
        {band}
      </span>
    </button>
  );
}
