import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  R2_FREE_CLASS_A,
  R2_FREE_STORAGE_BYTES,
  STORE_CEILING_BYTES,
  STORE_CEILING_OBJECTS,
  STORE_CEILING_REASON,
  ceilingAllowsWrite,
  reservationLive,
  reservationPath,
  spendReservation,
  type StoreReservation,
} from "./store-ceiling";

function reservation(
  remainingBytes: number,
  expiresAt: string,
): StoreReservation {
  return {
    packetId: "11111111-1111-4111-8111-111111111111",
    bytes: remainingBytes,
    remainingBytes,
    expiresAt,
  };
}

describe("ceilingAllowsWrite", () => {
  it("lets a paste through when used + incoming stays at or under 9 GB", () => {
    assert.equal(ceilingAllowsWrite(0, 750_000_000).ok, true);
    assert.equal(ceilingAllowsWrite(STORE_CEILING_BYTES - 1, 1).ok, true);
  });

  it("blocks when the bucket is already at the Ceiling", () => {
    const decision = ceilingAllowsWrite(STORE_CEILING_BYTES, 0);
    assert.deepEqual(decision, { ok: false, reason: STORE_CEILING_REASON });
  });

  it("blocks a paste that would cross 9 GB (never the billable 10 GB)", () => {
    const decision = ceilingAllowsWrite(STORE_CEILING_BYTES - 100, 101);
    assert.deepEqual(decision, { ok: false, reason: STORE_CEILING_REASON });
  });

  it("keeps the byte Ceiling inside R2’s 10 GB-month include", () => {
    assert.equal(STORE_CEILING_BYTES < R2_FREE_STORAGE_BYTES, true);
  });

  it("blocks when object count would leave the Class A include reachable", () => {
    assert.equal(STORE_CEILING_OBJECTS < R2_FREE_CLASS_A, true);
    const decision = ceilingAllowsWrite(0, 1, STORE_CEILING_OBJECTS, 1);
    assert.deepEqual(decision, { ok: false, reason: STORE_CEILING_REASON });
  });

  it("lets a small paste through when objects are still under the Ceiling", () => {
    assert.equal(ceilingAllowsWrite(0, 1_024, STORE_CEILING_OBJECTS - 3, 2).ok, true);
  });
});

describe("reservations", () => {
  it("paths stay out of District folders", () => {
    assert.equal(
      reservationPath("11111111-1111-4111-8111-111111111111"),
      "ceiling/reservations/11111111-1111-4111-8111-111111111111.json",
    );
  });

  it("ignores an expired reservation so a failed paste frees the slot", () => {
    const dead = reservation(1_000, "2020-01-01T00:00:00.000Z");
    assert.equal(reservationLive(dead, Date.parse("2026-08-23T00:00:00Z")), false);
    assert.equal(spendReservation(dead, 100, Date.parse("2026-08-23T00:00:00Z")), null);
  });

  it("will not spend more than the reserved bytes (stops a 1 KB reserve + 25 MB put)", () => {
    const live = reservation(1_024, "2026-12-01T00:00:00.000Z");
    const now = Date.parse("2026-08-23T00:00:00Z");
    assert.equal(spendReservation(live, 25 * 1024 * 1024, now), null);
    assert.equal(spendReservation(live, 512, now), 512);
  });
});
