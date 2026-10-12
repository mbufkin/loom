/**
 * Start a Run — the Cap and the create step.
 *
 * Cap (issues/08-nim-key-cost-cap.md): a Run is hundreds of NIM calls on
 * the Operator's key, so we count *started* Runs (a failed Run still
 * counts; a Worker requeue reuses the same record and does not).
 *
 * Everything that touches R2 comes in through `StartRunDeps`, so the
 * route's rules are unit-tested without a bucket (runs.test.ts).
 */
import { canPasteOrStart } from "./bargain";
import {
  IN_PROGRESS_STATUSES,
  RUN_SCHEMA,
  isPacketId,
  runIsoNow,
  type Packet,
  type PacketRun,
} from "./packets";

export const MAX_RUNS_PER_DISTRICT_PER_UTC_DAY = 2;
/**
 * App-wide, not per District: the locked Cap is "20 started Runs across
 * all Districts per calendar month". Stricter than per-District, and the
 * same number while only one District is invited.
 */
export const MAX_RUNS_PER_UTC_MONTH_ALL_DISTRICTS = 20;
export const MAX_IN_PROGRESS_RUNS_PER_DISTRICT = 1;

export const START_BLOCKED = {
  inProgress:
    "A Run is already queued or running for this District. Wait for it to finish before starting another.",
  daily: `This District already started ${MAX_RUNS_PER_DISTRICT_PER_UTC_DAY} Runs today (UTC). Try again after midnight UTC.`,
  monthly: `Loom is full this month: ${MAX_RUNS_PER_UTC_MONTH_ALL_DISTRICTS} Runs have started across all Districts. Try again next month (UTC).`,
} as const;

function utcDay(iso: string): string | null {
  const ms = Date.parse(iso);
  return Number.isNaN(ms) ? null : new Date(ms).toISOString().slice(0, 10);
}

/**
 * Why a new Start is refused, or null if allowed. Order matters for the
 * message: the in-progress rule is the one an Admin can wait out soonest.
 *
 * @param districtRuns every run.json in this District (all Packets)
 * @param allRuns      every run.json in the bucket (for the monthly Cap)
 */
export function startBlockReason(
  districtRuns: readonly PacketRun[],
  allRuns: readonly PacketRun[],
  nowMs: number,
): string | null {
  const inProgress = districtRuns.filter((run) =>
    IN_PROGRESS_STATUSES.has(run.status),
  ).length;
  if (inProgress >= MAX_IN_PROGRESS_RUNS_PER_DISTRICT) {
    return START_BLOCKED.inProgress;
  }
  const today = new Date(nowMs).toISOString().slice(0, 10);
  const thisMonth = today.slice(0, 7);
  const startedToday = districtRuns.filter(
    (run) => utcDay(run.queuedAt) === today,
  ).length;
  if (startedToday >= MAX_RUNS_PER_DISTRICT_PER_UTC_DAY) {
    return START_BLOCKED.daily;
  }
  const startedThisMonth = allRuns.filter(
    (run) => utcDay(run.queuedAt)?.slice(0, 7) === thisMonth,
  ).length;
  if (startedThisMonth >= MAX_RUNS_PER_UTC_MONTH_ALL_DISTRICTS) {
    return START_BLOCKED.monthly;
  }
  return null;
}

/** The record Vercel creates. After claim the Worker owns the object. */
export function newRunRecord(input: {
  runId: string;
  districtId: string;
  packetId: string;
  startedBy: string;
  nowMs: number;
}): PacketRun {
  return {
    schema: RUN_SCHEMA,
    id: input.runId,
    districtId: input.districtId,
    packetId: input.packetId,
    status: "queued",
    queuedAt: runIsoNow(input.nowMs),
    attempt: 0,
    startedBy: input.startedBy,
  };
}

/** queue/<runId>.json — the pointer the Worker polls. */
export type QueuePointer = {
  runId: string;
  districtId: string;
  packetId: string;
  queuedAt: string;
};

export function queuePointerFor(run: PacketRun): QueuePointer {
  return {
    runId: run.id,
    districtId: run.districtId,
    packetId: run.packetId,
    queuedAt: run.queuedAt,
  };
}

export type StartAdmin = {
  googleSub: string;
  districtId: string;
  email: string | null | undefined;
};

/** Result of a create-only write: "exists" means someone already wrote that key. */
export type CreateResult = "created" | "exists";

export type StartRunDeps = {
  storeConfigured: () => boolean;
  hasBargain: (districtId: string, googleSub: string) => Promise<boolean>;
  readPacket: (districtId: string, packetId: string) => Promise<Packet | null>;
  readRun: (
    districtId: string,
    packetId: string,
    runId: string,
  ) => Promise<PacketRun | null>;
  /** Must throw on R2 failure — a silent [] would let the Cap be skipped. */
  loadDistrictRuns: (districtId: string) => Promise<PacketRun[]>;
  loadAllRuns: () => Promise<PacketRun[]>;
  createRunRecord: (run: PacketRun) => Promise<CreateResult>;
  createQueuePointer: (pointer: QueuePointer) => Promise<CreateResult>;
  deleteRunRecord: (run: PacketRun) => Promise<void>;
  nowMs: () => number;
};

export type StartRunResult =
  | { status: 201 | 200; body: { run: PacketRun; alreadyStarted: boolean } }
  | { status: 400 | 401 | 403 | 404 | 409 | 429 | 502 | 503; body: { error: string } };

const fail = (
  status: 400 | 401 | 403 | 404 | 409 | 429 | 502 | 503,
  error: string,
): StartRunResult => ({ status, body: { error } });

/**
 * A retry of a Run we already created. If it is still queued, re-create
 * the queue pointer (create-only, so a live pointer is left alone): an
 * earlier request may have written run.json and died before the pointer,
 * and without it no Worker would ever claim the Run.
 */
async function alreadyStarted(
  deps: StartRunDeps,
  run: PacketRun,
): Promise<StartRunResult> {
  if (run.status === "queued") {
    try {
      await deps.createQueuePointer(queuePointerFor(run));
    } catch {
      return fail(502, "The Run exists but could not be queued. Try again.");
    }
  }
  return { status: 200, body: { run, alreadyStarted: true } };
}

/**
 * POST /api/packets/<id>/runs.
 *
 * Idempotency: the browser mints `runId` once per page view and resends
 * the same id on a double-click or retry. A second request finds the
 * existing run.json (or loses the create-only race) and gets 200 with the
 * same Run instead of starting — and billing — a second one.
 */
export async function startRun(
  deps: StartRunDeps,
  admin: StartAdmin | null,
  rawPacketId: string,
  rawRunId: unknown,
): Promise<StartRunResult> {
  if (!admin) return fail(401, "Sign in as an Admin to start a Run.");

  // Lowercase: the Worker lowercases ids from the queue pointer and would
  // look for a different run.json key than an upper-case one we wrote.
  const packetId = rawPacketId.trim().toLowerCase();
  const runId = typeof rawRunId === "string" ? rawRunId.trim().toLowerCase() : "";
  if (!isPacketId(packetId)) return fail(400, "Bad Packet id.");
  if (!isPacketId(runId)) return fail(400, "Bad Run id. Reload the page and try again.");

  if (!deps.storeConfigured()) {
    return fail(503, "The Packet store is not configured on the host.");
  }
  if (!canPasteOrStart(await deps.hasBargain(admin.districtId, admin.googleSub))) {
    return fail(403, "Accept the Bargain on the Workspace before you start a Run.");
  }
  const packet = await deps.readPacket(admin.districtId, packetId);
  if (!packet || packet.districtId !== admin.districtId || packet.id !== packetId) {
    return fail(404, "That Packet is not in your District.");
  }

  const existing = await deps.readRun(admin.districtId, packetId, runId);
  if (existing) return alreadyStarted(deps, existing);

  let districtRuns: PacketRun[];
  let allRuns: PacketRun[];
  try {
    [districtRuns, allRuns] = await Promise.all([
      deps.loadDistrictRuns(admin.districtId),
      deps.loadAllRuns(),
    ]);
  } catch {
    // Fail closed: if we cannot count, we cannot prove the Cap allows it.
    return fail(503, "Could not check the Run limits. Nothing was started; try again in a minute.");
  }
  const blocked = startBlockReason(districtRuns, allRuns, deps.nowMs());
  if (blocked) return fail(429, blocked);

  const run = newRunRecord({
    runId,
    districtId: admin.districtId,
    packetId,
    startedBy: admin.email ?? admin.googleSub,
    nowMs: deps.nowMs(),
  });

  // run.json first: the Worker ignores a queue pointer whose record is
  // missing, but a record without a pointer would never be picked up.
  if ((await deps.createRunRecord(run)) === "exists") {
    const raced = await deps.readRun(admin.districtId, packetId, runId);
    if (raced) return alreadyStarted(deps, raced);
    return fail(409, "That Run id is already taken. Reload the page and try again.");
  }

  try {
    // "exists" is fine: same runId means a retry already queued it.
    await deps.createQueuePointer(queuePointerFor(run));
  } catch {
    // No pointer = no Worker will ever claim it, yet it would hold the
    // District's one in-progress slot forever. Roll back so the Admin can retry.
    try {
      await deps.deleteRunRecord(run);
    } catch {
      // Leave it; the log line from the store layer names the key.
    }
    return fail(502, "Could not queue the Run. Nothing will run; try again.");
  }

  return { status: 201, body: { run, alreadyStarted: false } };
}
