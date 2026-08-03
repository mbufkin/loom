import { useEffect, useState } from "react";
import { api, type PacketTypeRegistry } from "../lib/api";
import type { PacketType } from "../types";

interface Props {
  projectId: string;
  // The packet type currently declared for this project (from the unit rung).
  packet?: PacketType;
  // Called after a successful change so the parent can reload the project and
  // pick up the freshly-regenerated bands + completeness.
  onChanged: () => void;
}

// The "starting point" control the director asked for: DECLARE what kind of packet
// this curriculum is. Declared beats clever — we never infer it. Changing it writes
// the manifest and regenerates the (deterministic) unit rung, so the heatmap's
// completeness chips update immediately without a full re-run.
export function PacketTypeBar({ projectId, packet, onChanged }: Props) {
  const [registry, setRegistry] = useState<PacketTypeRegistry | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .packetTypes()
      .then(setRegistry)
      .catch(() => setRegistry(null));
  }, []);

  // Fall back to the registry default until the unit rung reports a declared id.
  const current = packet?.id ?? registry?.default ?? "";
  const types = registry?.types ?? [];

  async function choose(id: string) {
    if (id === current || busy) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.setPacketType(projectId, id);
      if (!res.regenerated) setError("Saved, but unit rung did not regenerate.");
      onChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }

  const active = types.find((t) => t.id === current);

  return (
    <div className="packet-bar">
      <span className="packet-lead">Curriculum packet type</span>
      <div className="packet-seg" role="group" aria-label="declare packet type">
        {types.map((t) => (
          <button
            key={t.id}
            type="button"
            aria-pressed={t.id === current}
            disabled={busy}
            title={t.description}
            onClick={() => choose(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <span className="packet-hint">
        {error ? (
          <span className="packet-err">{error}</span>
        ) : active ? (
          <>
            Declared &middot; sets the completeness checklist (
            <b>
              {active.label} &rarr; {active.expected_components.length} expected
            </b>
            ). {busy ? "Recomputing…" : "Never guessed."}
          </>
        ) : (
          "Declared by you — sets the completeness checklist. Never guessed."
        )}
      </span>
    </div>
  );
}
