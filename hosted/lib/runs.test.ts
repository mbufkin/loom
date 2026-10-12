/**
 * Start a Run: the Cap and the route's validation, with the R2 store
 * replaced by an in-memory fake. Nothing here talks to a bucket.
 */
import assert from "node:assert/strict";
import { beforeEach, describe, it } from "node:test";
import type { Packet, PacketRun, RunStatus } from "./packets";
import {
  MAX_RUNS_PER_DISTRICT_PER_UTC_DAY,
  MAX_RUNS_PER_UTC_MONTH_ALL_DISTRICTS,
  START_BLOCKED,
  newRunRecord,
  startBlockReason,
  startRun,
  type QueuePointer,
  type StartAdmin,
  type StartRunDeps,
} from "./runs";

const D = "dallasisd.org";
const P = "11111111-1111-4111-8111-111111111111";
const RUN_ID = "33333333-3333-4333-8333-333333333333";
const NOW = Date.parse("2026-10-12T16:00:00Z");
const ADMIN: StartAdmin = { googleSub: "sub-1", districtId: D, email: "admin@dallasisd.org" };

let seq = 0;
function rec(status: RunStatus, queuedAt: string, districtId = D): PacketRun {
  seq += 1;
  return {
    schema: 1,
    id: `r${seq}`,
    districtId,
    packetId: P,
    status,
    queuedAt,
    attempt: 0,
  };
}

describe("startBlockReason (the Cap)", () => {
  it("allows a first Run", () => {
    assert.equal(startBlockReason([], [], NOW), null);
  });

  it("allows only one queued or running Run per District", () => {
    for (const status of ["queued", "running"] as const) {
      const runs = [rec(status, "2026-10-11T10:00:00Z")];
      assert.equal(startBlockReason(runs, runs, NOW), START_BLOCKED.inProgress);
    }
  });

  it("caps started Runs per District per UTC day, failed ones included", () => {
    assert.equal(MAX_RUNS_PER_DISTRICT_PER_UTC_DAY, 2);
    const runs = [
      rec("failed", "2026-10-12T00:00:01Z"),
      rec("succeeded", "2026-10-12T09:00:00Z"),
    ];
    assert.equal(startBlockReason(runs, runs, NOW), START_BLOCKED.daily);
  });

  it("resets the daily count at midnight UTC", () => {
    const runs = [
      rec("failed", "2026-10-11T23:59:59Z"),
      rec("succeeded", "2026-10-12T09:00:00Z"),
    ];
    assert.equal(startBlockReason(runs, runs, NOW), null);
  });

  it("caps the calendar month across all Districts", () => {
    assert.equal(MAX_RUNS_PER_UTC_MONTH_ALL_DISTRICTS, 20);
    const others = Array.from({ length: 20 }, (_, i) =>
      rec("succeeded", `2026-10-0${(i % 9) + 1}T10:00:00Z`, "other.org"),
    );
    assert.equal(startBlockReason([], others, NOW), START_BLOCKED.monthly);
    // Last month's Runs do not count.
    const lastMonth = others.map((r) => ({ ...r, queuedAt: "2026-09-15T10:00:00Z" }));
    assert.equal(startBlockReason([], lastMonth, NOW), null);
  });
});

describe("newRunRecord", () => {
  it("matches the contract Vercel must create", () => {
    const run = newRunRecord({ runId: RUN_ID, districtId: D, packetId: P, startedBy: "a@b.org", nowMs: NOW });
    assert.deepEqual(run, {
      schema: 1,
      id: RUN_ID,
      districtId: D,
      packetId: P,
      status: "queued",
      queuedAt: "2026-10-12T16:00:00Z",
      attempt: 0,
      startedBy: "a@b.org",
    });
  });
});

/** In-memory store: keys are "run:<id>" and "queue:<id>". */
function fakeDeps(overrides: Partial<StartRunDeps> = {}) {
  const runs = new Map<string, PacketRun>();
  const queue = new Map<string, QueuePointer>();
  const packet: Packet = { id: P, name: "Ag", pastedAt: "2026-10-01T00:00:00Z", districtId: D, files: [], runs: [] };
  const deps: StartRunDeps = {
    storeConfigured: () => true,
    hasBargain: async () => true,
    readPacket: async (d, p) => (d === D && p === P ? packet : null),
    readRun: async (_d, _p, id) => runs.get(id) ?? null,
    loadDistrictRuns: async (d) => [...runs.values()].filter((r) => r.districtId === d),
    loadAllRuns: async () => [...runs.values()],
    createRunRecord: async (run) => {
      if (runs.has(run.id)) return "exists";
      runs.set(run.id, run);
      return "created";
    },
    createQueuePointer: async (ptr) => {
      if (queue.has(ptr.runId)) return "exists";
      queue.set(ptr.runId, ptr);
      return "created";
    },
    deleteRunRecord: async (run) => {
      runs.delete(run.id);
    },
    nowMs: () => NOW,
    ...overrides,
  };
  return { deps, runs, queue };
}

describe("startRun (POST /api/packets/<id>/runs)", () => {
  beforeEach(() => {
    seq = 0;
  });

  it("creates run.json then the queue pointer", async () => {
    const order: string[] = [];
    const { deps, runs, queue } = fakeDeps();
    const create = deps.createRunRecord;
    const pointer = deps.createQueuePointer;
    deps.createRunRecord = async (r) => (order.push("run"), create(r));
    deps.createQueuePointer = async (q) => (order.push("queue"), pointer(q));

    const out = await startRun(deps, ADMIN, P, RUN_ID);
    assert.equal(out.status, 201);
    assert.deepEqual(order, ["run", "queue"]);
    assert.equal(runs.get(RUN_ID)?.status, "queued");
    assert.equal(runs.get(RUN_ID)?.startedBy, "admin@dallasisd.org");
    assert.deepEqual(queue.get(RUN_ID), {
      runId: RUN_ID,
      districtId: D,
      packetId: P,
      queuedAt: "2026-10-12T16:00:00Z",
    });
  });

  it("rejects a signed-out caller, bad ids, no Bargain, and foreign Packets", async () => {
    const { deps, runs } = fakeDeps();
    assert.equal((await startRun(deps, null, P, RUN_ID)).status, 401);
    assert.equal((await startRun(deps, ADMIN, "not-a-uuid", RUN_ID)).status, 400);
    assert.equal((await startRun(deps, ADMIN, P, undefined)).status, 400);
    assert.equal((await startRun(deps, ADMIN, P, "../../x")).status, 400);
    assert.equal(
      (await startRun(deps, { ...ADMIN, districtId: "other.org" }, P, RUN_ID)).status,
      404,
    );
    assert.equal(
      (await startRun({ ...deps, hasBargain: async () => false }, ADMIN, P, RUN_ID)).status,
      403,
    );
    assert.equal(
      (await startRun({ ...deps, storeConfigured: () => false }, ADMIN, P, RUN_ID)).status,
      503,
    );
    assert.equal(runs.size, 0, "no rejected request may write a Run");
  });

  it("lowercases ids so the Worker finds the same keys", async () => {
    const { deps, runs } = fakeDeps();
    const out = await startRun(deps, ADMIN, P.toUpperCase(), RUN_ID.toUpperCase());
    assert.equal(out.status, 201);
    assert.ok(runs.has(RUN_ID));
  });

  it("treats a double-submit with the same runId as the same Run", async () => {
    const { deps, runs, queue } = fakeDeps();
    assert.equal((await startRun(deps, ADMIN, P, RUN_ID)).status, 201);
    const again = await startRun(deps, ADMIN, P, RUN_ID);
    assert.equal(again.status, 200);
    assert.ok("run" in again.body && again.body.alreadyStarted);
    assert.equal(runs.size, 1);
    assert.equal(queue.size, 1);
  });

  it("re-queues a retry whose first request died before the pointer", async () => {
    const { deps, runs, queue } = fakeDeps();
    runs.set(RUN_ID, newRunRecord({ runId: RUN_ID, districtId: D, packetId: P, startedBy: "x", nowMs: NOW }));
    const out = await startRun(deps, ADMIN, P, RUN_ID);
    assert.equal(out.status, 200);
    assert.ok(queue.has(RUN_ID));
  });

  it("returns the raced Run when the create-only write loses", async () => {
    const { deps, runs } = fakeDeps();
    const winner = newRunRecord({ runId: RUN_ID, districtId: D, packetId: P, startedBy: "x", nowMs: NOW });
    let firstRead = true;
    deps.readRun = async () => {
      if (firstRead) {
        firstRead = false;
        return null;
      }
      return winner;
    };
    deps.createRunRecord = async () => "exists";
    const out = await startRun(deps, ADMIN, P, RUN_ID);
    assert.equal(out.status, 200);
    assert.equal(runs.size, 0);
  });

  it("blocks with the Cap message and writes nothing", async () => {
    const { deps, runs } = fakeDeps();
    runs.set("busy", { ...rec("running", "2026-10-12T15:00:00Z"), id: "busy" });
    const out = await startRun(deps, ADMIN, P, RUN_ID);
    assert.equal(out.status, 429);
    assert.deepEqual(out.body, { error: START_BLOCKED.inProgress });
    assert.equal(runs.size, 1);
  });

  it("fails closed when the Run count cannot be read", async () => {
    const { deps, runs } = fakeDeps({
      loadAllRuns: async () => {
        throw new Error("R2 down");
      },
    });
    assert.equal((await startRun(deps, ADMIN, P, RUN_ID)).status, 503);
    assert.equal(runs.size, 0);
  });

  it("rolls back run.json when the queue pointer cannot be written", async () => {
    const { deps, runs } = fakeDeps({
      createQueuePointer: async () => {
        throw new Error("R2 down");
      },
    });
    const out = await startRun(deps, ADMIN, P, RUN_ID);
    assert.equal(out.status, 502);
    assert.equal(runs.size, 0, "an unqueued Run would hold the District's slot forever");
  });
});
