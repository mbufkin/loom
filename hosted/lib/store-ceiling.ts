/**
 * Ceiling — stay inside Cloudflare R2’s free Standard tier.
 *
 * R2 bills the moment you leave 10 GB-month, 1 million Class A
 * (writes/lists), or 10 million Class B (reads). Egress is always free.
 * This app never writes past the Ceiling, so the account should not bill.
 *
 * Do not call this the Cap. The Cap is started Runs (NIM). The Ceiling
 * is Packet-store bytes. Admins get a named reason, not a remaining-GB
 * dashboard — same shape as a blocked Start.
 *
 * Headroom: 9 GB of the 10 GB-month include. The leftover gig covers
 * concurrent pastes that reserved but have not landed, plate publishes,
 * and Cloudflare’s GB-month rounding.
 *
 * Class A (writes/lists) are 1 million / month on the free tier. A 9 GB
 * store of 1-byte files would be millions of PutObjects — that bills
 * while storage still looks empty. The object Ceiling stops that.
 * Class B (reads) and egress stay unmetered; they do not bill first.
 */

export const R2_FREE_STORAGE_BYTES = 10_000_000_000;
export const R2_FREE_CLASS_A = 1_000_000;
export const STORE_CEILING_BYTES = 9_000_000_000;
/** Hard stop on object count so tiny files cannot burn the Class A include. */
export const STORE_CEILING_OBJECTS = 8_000;
export const STORE_CEILING_REASON = "the Packet store is full";
export const RESERVATION_MS = 15 * 60 * 1000;

export type StoreReservation = {
  packetId: string;
  /** Bytes this paste promised at reserve time (all files). */
  bytes: number;
  /** Bytes still allowed on later presigns for this Packet. */
  remainingBytes: number;
  expiresAt: string;
};

export type CeilingDecision =
  | { ok: true }
  | { ok: false; reason: typeof STORE_CEILING_REASON };

export function reservationPath(packetId: string): string {
  return `ceiling/reservations/${packetId}.json`;
}

export function reservationPrefix(): string {
  return "ceiling/reservations/";
}

/** A reservation holds space only while it is unexpired. */
export function reservationLive(
  reservation: StoreReservation,
  nowMs: number,
): boolean {
  return (
    Number.isFinite(Date.parse(reservation.expiresAt)) &&
    Date.parse(reservation.expiresAt) > nowMs &&
    reservation.remainingBytes >= 0
  );
}

/**
 * used = bytes already in the bucket.
 * incoming = this write, plus any other live reservations you already added
 * into `used` (or pass them as incoming — do not double-count).
 */
export function ceilingAllowsWrite(
  usedBytes: number,
  incomingBytes: number,
  usedObjects: number = 0,
  incomingObjects: number = 0,
): CeilingDecision {
  if (
    usedBytes >= STORE_CEILING_BYTES ||
    usedBytes + incomingBytes > STORE_CEILING_BYTES ||
    usedObjects + incomingObjects > STORE_CEILING_OBJECTS
  ) {
    return { ok: false, reason: STORE_CEILING_REASON };
  }
  return { ok: true };
}

/**
 * Spend one file against a live reservation. Returns the new remaining
 * count, or null if the reservation is dead or the file does not fit.
 */
export function spendReservation(
  reservation: StoreReservation,
  fileBytes: number,
  nowMs: number,
): number | null {
  if (!reservationLive(reservation, nowMs)) return null;
  if (fileBytes <= 0 || fileBytes > reservation.remainingBytes) return null;
  return reservation.remainingBytes - fileBytes;
}
