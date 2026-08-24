import { NextResponse } from "next/server";
import { canPasteOrStart } from "@/lib/bargain";
import {
  MAX_FILE_BYTES,
  MAX_FILES_PER_PACKET,
  isPacketId,
} from "@/lib/packets";
import { r2Configured } from "@/lib/r2";
import { requireAdmin } from "@/lib/require-admin";
import {
  ceilingForIncoming,
  newReservation,
  readBargain,
  writeReservation,
} from "@/lib/store";
import { STORE_CEILING_REASON } from "@/lib/store-ceiling";

type ReserveBody = {
  packetId?: string;
  bytes?: number;
};

/**
 * Hold space for one paste before any file PUT. Two Admins cannot both
 * pass a 9 GB check and then land enough bytes to bill R2.
 */
export async function POST(request: Request) {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "denied" }, { status: 401 });
  if (!r2Configured()) {
    return NextResponse.json(
      { error: "Packet store is not configured" },
      { status: 503 },
    );
  }

  const bargain = await readBargain(admin.districtId, admin.googleSub);
  if (!canPasteOrStart(Boolean(bargain))) {
    return NextResponse.json({ error: "Bargain required" }, { status: 403 });
  }

  const body = (await request.json()) as ReserveBody;
  const packetId = body.packetId ?? "";
  const bytes = body.bytes ?? 0;
  const maxPaste = MAX_FILES_PER_PACKET * MAX_FILE_BYTES;

  if (!isPacketId(packetId)) {
    return NextResponse.json({ error: "Bad Packet id" }, { status: 400 });
  }
  if (bytes <= 0 || bytes > maxPaste) {
    return NextResponse.json({ error: "Choose 1–30 files, 25 MB each" }, { status: 400 });
  }

  const decision = await ceilingForIncoming(bytes, packetId);
  if (!decision.ok) {
    return NextResponse.json({ error: STORE_CEILING_REASON }, { status: 409 });
  }

  await writeReservation(newReservation(packetId, bytes));
  return NextResponse.json({ ok: true });
}
