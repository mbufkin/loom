/**
 * Packet and Bargain records live in the private R2 bucket.
 * File bytes are the Packet; meta.json is the product object (name, dates,
 * Runs). The Fly volume is scratch and is not the archive.
 *
 * Ceiling reservations live under ceiling/reservations/ — they hold a
 * paste’s bytes so two Admins cannot both slip under a 9 GB check and
 * land 10+ GB.
 */
import type { BargainRecord } from "./bargain";
import {
  bargainPath,
  packetMetaPath,
  type Packet,
} from "./packets";
import { r2ReadFallback } from "./r2-guard";
import {
  r2BucketUsage,
  r2Configured,
  r2Delete,
  r2GetJson,
  r2ListKeys,
  r2PutJson,
} from "./r2";
import {
  RESERVATION_MS,
  STORE_CEILING_REASON,
  type CeilingDecision,
  type StoreReservation,
  ceilingAllowsWrite,
  reservationLive,
  reservationPath,
  reservationPrefix,
} from "./store-ceiling";

export async function readBargain(
  districtId: string,
  googleSub: string,
): Promise<BargainRecord | null> {
  if (!r2Configured()) return null;
  return r2ReadFallback("readBargain", null, () =>
    r2GetJson<BargainRecord>(bargainPath(districtId, googleSub)),
  );
}

export async function writeBargain(
  districtId: string,
  record: BargainRecord,
): Promise<void> {
  await r2PutJson(bargainPath(districtId, record.googleSub), record);
}

export async function readPacket(
  districtId: string,
  packetId: string,
): Promise<Packet | null> {
  if (!r2Configured()) return null;
  return r2ReadFallback("readPacket", null, () =>
    r2GetJson<Packet>(packetMetaPath(districtId, packetId)),
  );
}

export async function writePacket(packet: Packet): Promise<void> {
  await r2PutJson(packetMetaPath(packet.districtId, packet.id), packet);
}

export async function listPackets(districtId: string): Promise<Packet[]> {
  if (!r2Configured()) return [];
  return r2ReadFallback("listPackets", [], async () => {
    const keys = await r2ListKeys(`d/${districtId}/packets/`);
    const packets: Packet[] = [];
    for (const key of keys) {
      if (!key.endsWith("/meta.json")) continue;
      const packet = await r2GetJson<Packet>(key);
      if (packet && packet.districtId === districtId) packets.push(packet);
    }
    packets.sort((a, b) => (a.pastedAt < b.pastedAt ? 1 : -1));
    return packets;
  });
}

export function usedPacketNames(packets: readonly Packet[]): string[] {
  const names = new Set<string>();
  for (const packet of packets) names.add(packet.name);
  return [...names].sort((a, b) => a.localeCompare(b));
}

export async function readReservation(
  packetId: string,
): Promise<StoreReservation | null> {
  if (!r2Configured()) return null;
  return r2ReadFallback("readReservation", null, () =>
    r2GetJson<StoreReservation>(reservationPath(packetId)),
  );
}

export async function writeReservation(
  reservation: StoreReservation,
): Promise<void> {
  await r2PutJson(reservationPath(reservation.packetId), reservation);
}

export async function deleteReservation(packetId: string): Promise<void> {
  await r2Delete(reservationPath(packetId));
}

/**
 * Bytes promised by other live reservations. This Packet’s own hold is
 * skipped so a presign does not double-count the files it is about to put.
 */
export async function reservedBytesByOthers(
  exceptPacketId: string,
  nowMs: number,
): Promise<number> {
  if (!r2Configured()) return 0;
  return r2ReadFallback("reservedBytesByOthers", 0, async () => {
    const keys = await r2ListKeys(reservationPrefix());
    let bytes = 0;
    for (const key of keys) {
      const reservation = await r2GetJson<StoreReservation>(key);
      if (!reservation || reservation.packetId === exceptPacketId) continue;
      if (reservationLive(reservation, nowMs)) bytes += reservation.bytes;
    }
    return bytes;
  });
}

/**
 * used (on disk) + other Admins’ holds + this incoming write.
 * Call before a new reservation and again before plate publish.
 */
export async function ceilingForIncoming(
  incomingBytes: number,
  exceptPacketId: string,
): Promise<CeilingDecision> {
  if (!r2Configured()) {
    return { ok: false, reason: STORE_CEILING_REASON };
  }
  return r2ReadFallback(
    "ceilingForIncoming",
    { ok: false, reason: STORE_CEILING_REASON },
    async () => {
      const [{ bytes: used }, reserved] = await Promise.all([
        r2BucketUsage(),
        reservedBytesByOthers(exceptPacketId, Date.now()),
      ]);
      return ceilingAllowsWrite(used + reserved, incomingBytes);
    },
  );
}

export function newReservation(
  packetId: string,
  bytes: number,
  nowMs: number = Date.now(),
): StoreReservation {
  return {
    packetId,
    bytes,
    remainingBytes: bytes,
    expiresAt: new Date(nowMs + RESERVATION_MS).toISOString(),
  };
}

/** True when the bucket plus live holds already sit on the Ceiling. */
export async function storeCeilingBlocksPaste(): Promise<boolean> {
  if (!r2Configured()) return false;
  // Fail open on the Workspace: a dead store is not “full”. Reserve
  // still fail-closes via ceilingForIncoming so we do not write blind.
  return r2ReadFallback("storeCeilingBlocksPaste", false, async () => {
    const [{ bytes: used }, reserved] = await Promise.all([
      r2BucketUsage(),
      reservedBytesByOthers("", Date.now()),
    ]);
    return !ceilingAllowsWrite(used + reserved, 0).ok;
  });
}
