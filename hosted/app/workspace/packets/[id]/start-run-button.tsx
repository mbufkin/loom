"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { MAX_RUNS_PER_DISTRICT_PER_UTC_DAY } from "@/lib/runs";

/**
 * Start a Run. The server re-checks every rule; `blockedReason` only
 * decides whether the button is clickable and what the note says.
 *
 * Double-submit guard, two layers: the button disables while a request
 * is in flight, and the runId is minted once per page view so a retry
 * (or a second tab click racing the first) reuses the same id and the
 * server's create-only write turns it into a no-op.
 */
export function StartRunButton({
  packetId,
  blockedReason,
}: {
  packetId: string;
  blockedReason: string | null;
}) {
  const router = useRouter();
  const runId = useRef<string | null>(null);
  const [pending, setPending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    if (pending) return;
    runId.current ??= crypto.randomUUID();
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const res = await fetch(`/api/packets/${packetId}/runs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ runId: runId.current }),
      });
      const body = (await res.json().catch(() => ({}))) as { error?: string };
      if (!res.ok) {
        setError(body.error ?? `Start failed (${res.status}).`);
        return;
      }
      setMessage("Run queued. The Worker picks it up within a minute; a full Run takes hours.");
      router.refresh();
    } catch {
      setError("Network error. Reload to see whether the Run started.");
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="stack" style={{ marginTop: "1.5rem" }}>
      <button
        className="btn btn-brass"
        type="button"
        disabled={Boolean(blockedReason) || pending || Boolean(message)}
        onClick={start}
      >
        {pending ? "Starting…" : "Start a Run"}
      </button>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : null}
      <p className="note">
        {message ??
          blockedReason ??
          `Runs use the Operator’s NVIDIA key on the Loom Worker, not this browser. Limits: ${MAX_RUNS_PER_DISTRICT_PER_UTC_DAY} Runs per District per day (UTC), one at a time.`}
      </p>
    </div>
  );
}
