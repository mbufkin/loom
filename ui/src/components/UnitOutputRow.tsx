import type { Band, UnitRollup } from "../types";

interface Props {
  rollup: UnitRollup;
  band: Band;
  onOpen: () => void;
}

const BAND_CLASS: Record<Band, string> = {
  Strong: "band-strong",
  Developing: "band-developing",
  Weak: "band-weak",
  Unrated: "band-unrated",
};

// One banded heatmap row per unit — the Loom analogue of Fairway's TierRow.
// The swatch + band come from the real unit rung when present; the metrics line
// summarizes Layer 1 role fulfillment from aggregate-stats.unit_rollup.
export function UnitOutputRow({ rollup, band, onOpen }: Props) {
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
      <span className={`u-band ${BAND_CLASS[band]}`}>{band}</span>
    </button>
  );
}
