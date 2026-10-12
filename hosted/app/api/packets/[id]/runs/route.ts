import { NextResponse } from "next/server";
import { r2Configured } from "@/lib/r2";
import { requireAdmin } from "@/lib/require-admin";
import { startRun, type StartRunDeps } from "@/lib/runs";
import {
  createQueuePointer,
  createRunRecord,
  deleteRunRecord,
  loadAllRuns,
  loadDistrictRuns,
  readBargain,
  readPacket,
  readRun,
} from "@/lib/store";

const deps: StartRunDeps = {
  storeConfigured: r2Configured,
  hasBargain: async (districtId, googleSub) =>
    Boolean(await readBargain(districtId, googleSub)),
  readPacket,
  readRun,
  loadDistrictRuns,
  loadAllRuns,
  createRunRecord,
  createQueuePointer,
  deleteRunRecord,
  nowMs: () => Date.now(),
};

/**
 * Start a Run on this Packet. All rules (auth, Bargain, District, Cap,
 * idempotency) live in lib/runs.ts so they are tested without R2.
 * Body: { runId: <uuid minted once by the page> }.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const admin = await requireAdmin();
  const { id } = await params;
  let runId: unknown;
  try {
    runId = ((await request.json()) as { runId?: unknown }).runId;
  } catch {
    runId = undefined;
  }
  try {
    const result = await startRun(deps, admin, id, runId);
    return NextResponse.json(result.body, { status: result.status });
  } catch (error) {
    const name = error instanceof Error ? error.name : "Error";
    console.error(`[runs] start failed for packet ${id}: ${name}`);
    return NextResponse.json(
      {
        error:
          "The Packet store did not answer. Reload to see whether the Run started, then try again if it did not.",
      },
      { status: 503 },
    );
  }
}
