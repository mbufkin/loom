import { NextResponse } from "next/server";
import { canPasteOrStart } from "@/lib/bargain";
import {
  MAX_FILE_BYTES,
  districtPathSegment,
  isPacketFilePath,
  isPacketId,
} from "@/lib/packets";
import { r2Configured, r2PresignPut } from "@/lib/r2";
import { requireAdmin } from "@/lib/require-admin";
import { readBargain, readReservation, writeReservation } from "@/lib/store";
import { STORE_CEILING_REASON, spendReservation } from "@/lib/store-ceiling";

type Body = {
  pathname?: string;
  contentType?: string;
  size?: number;
};

/**
 * Client-direct put. Packet bytes skip the 4.5 MB Function body.
 * The signed URL is scoped to this District + Packet after Bargain.
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

  const body = (await request.json()) as Body;
  const pathname = body.pathname ?? "";
  const contentType = body.contentType || "application/octet-stream";
  const size = body.size ?? 0;
  const packetId = pathname.split("/")[3];

  if (size <= 0 || size > MAX_FILE_BYTES) {
    return NextResponse.json({ error: "File is too large" }, { status: 400 });
  }
  if (
    !packetId ||
    !isPacketId(packetId) ||
    !isPacketFilePath(admin.districtId, packetId, pathname) ||
    !districtPathSegment(admin.districtId)
  ) {
    return NextResponse.json(
      { error: "Path is not this District’s Packet" },
      { status: 400 },
    );
  }

  const reservation = await readReservation(packetId);
  if (!reservation) {
    return NextResponse.json({ error: STORE_CEILING_REASON }, { status: 409 });
  }
  const remaining = spendReservation(reservation, size, Date.now());
  if (remaining === null) {
    return NextResponse.json({ error: STORE_CEILING_REASON }, { status: 409 });
  }
  await writeReservation({ ...reservation, remainingBytes: remaining });

  const url = await r2PresignPut(pathname, contentType, size);
  return NextResponse.json({ url, pathname });
}
