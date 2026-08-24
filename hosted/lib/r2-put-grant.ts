/**
 * One grant for a Packet file put. Presign (browser → R2) and
 * /api/r2/put (browser → Loom → R2) share this so a second paste
 * cannot skip the Ceiling or land in another District’s folder.
 */
import { canPasteOrStart } from "./bargain";
import {
  MAX_FILE_BYTES,
  districtPathSegment,
  isPacketFilePath,
  isPacketId,
} from "./packets";
import { r2Configured } from "./r2";
import { requireAdmin } from "./require-admin";
import { readBargain, readReservation, writeReservation } from "./store";
import { STORE_CEILING_REASON, spendReservation } from "./store-ceiling";

export type PacketPutOk = {
  ok: true;
  pathname: string;
  contentType: string;
  size: number;
  packetId: string;
};

export type PacketPutDenied = { ok: false; error: string };

/**
 * Path + size only — no I/O. The route layer adds Bargain and the
 * reservation so tests can pin the District folder rule without R2.
 */
export function describePacketPut(input: {
  districtId: string;
  pathname: string;
  contentType?: string;
  size: number;
}): PacketPutOk | PacketPutDenied {
  const pathname = input.pathname;
  const contentType = input.contentType || "application/octet-stream";
  const size = input.size;
  const packetId = pathname.split("/")[3];

  if (size <= 0 || size > MAX_FILE_BYTES) {
    return { ok: false, error: "File is too large" };
  }
  if (
    !packetId ||
    !isPacketId(packetId) ||
    !isPacketFilePath(input.districtId, packetId, pathname) ||
    !districtPathSegment(input.districtId)
  ) {
    return { ok: false, error: "Path is not this District’s Packet" };
  }
  return { ok: true, pathname, contentType, size, packetId };
}

export async function authorizePacketFilePut(input: {
  pathname: string;
  contentType?: string;
  size: number;
}): Promise<(PacketPutOk & { ok: true }) | (PacketPutDenied & { status: number })> {
  const admin = await requireAdmin();
  if (!admin) return { ok: false, status: 401, error: "denied" };
  if (!r2Configured()) {
    return { ok: false, status: 503, error: "Packet store is not configured" };
  }

  const bargain = await readBargain(admin.districtId, admin.googleSub);
  if (!canPasteOrStart(Boolean(bargain))) {
    return { ok: false, status: 403, error: "Bargain required" };
  }

  const described = describePacketPut({
    districtId: admin.districtId,
    pathname: input.pathname,
    contentType: input.contentType,
    size: input.size,
  });
  if (!described.ok) return { ok: false, status: 400, error: described.error };

  const reservation = await readReservation(described.packetId);
  if (!reservation) {
    return { ok: false, status: 409, error: STORE_CEILING_REASON };
  }
  const remaining = spendReservation(reservation, described.size, Date.now());
  if (remaining === null) {
    return { ok: false, status: 409, error: STORE_CEILING_REASON };
  }
  await writeReservation({ ...reservation, remainingBytes: remaining });
  return described;
}
