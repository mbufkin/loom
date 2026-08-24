/**
 * Live 500 (digest 199477171): Workspace loads Bargain + Packets from R2.
 * If the bucket rejects the key, an uncaught throw becomes “Application error”.
 *
 * This loop talks to R2 with fake credentials on purpose. It must return
 * empty/false, not throw — same symptom class as the signed-in Workspace.
 */
import assert from "node:assert/strict";
import { describe, it } from "node:test";

const KEYS = [
  "R2_ACCOUNT_ID",
  "R2_ACCESS_KEY_ID",
  "R2_SECRET_ACCESS_KEY",
  "R2_BUCKET",
] as const;

describe("store reads survive a rejected R2 key", () => {
  it("listPackets / Bargain / Ceiling do not throw", async () => {
    const prior: Record<string, string | undefined> = {};
    for (const key of KEYS) {
      prior[key] = process.env[key];
    }
    process.env.R2_ACCOUNT_ID = "00000000000000000000000000000000";
    process.env.R2_ACCESS_KEY_ID = "fake-access-key";
    process.env.R2_SECRET_ACCESS_KEY = "fake-secret-key";
    process.env.R2_BUCKET = "loom-packets";

    try {
      const { listPackets, readBargain, storeCeilingBlocksPaste } = await import(
        "./store"
      );
      const [packets, bargain, full] = await Promise.all([
        listPackets("dallasisd.org"),
        readBargain("dallasisd.org", "google-sub"),
        storeCeilingBlocksPaste(),
      ]);
      assert.deepEqual(packets, []);
      assert.equal(bargain, null);
      assert.equal(full, false);
    } finally {
      for (const key of KEYS) {
        if (prior[key] === undefined) delete process.env[key];
        else process.env[key] = prior[key];
      }
    }
  });
});
