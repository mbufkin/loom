/**
 * Packet rules for the hosted Workspace.
 *
 * A Packet is one frozen paste. Packet name is a grouping label, not a
 * unique id — two “Ag Mechanics” pastes are two Packets. Completeness
 * (name timeline) is Operator-only and does not live here.
 */

export type RunStatus = "in_flight" | "succeeded" | "failed" | "interrupted";

export type PacketRun = {
  id: string;
  status: RunStatus;
  startedAt: string;
};

export type PacketFile = {
  name: string;
  pathname: string;
  size: number;
  contentType: string;
};

export type Packet = {
  id: string;
  name: string;
  pastedAt: string;
  districtId: string;
  files: PacketFile[];
  runs: PacketRun[];
};

/**
 * List-row status. In-flight wins so a retry does not look “done.”
 * A Packet with no Run yet is not a failure — paste happened; Start has not.
 */
export type PacketListStatus =
  | "in_flight"
  | "has_plates"
  | "failed_no_plates"
  | "no_run";

export function packetListStatus(runs: readonly PacketRun[]): PacketListStatus {
  if (runs.some((run) => run.status === "in_flight")) return "in_flight";
  if (runs.some((run) => run.status === "succeeded")) return "has_plates";
  if (
    runs.some(
      (run) => run.status === "failed" || run.status === "interrupted",
    )
  ) {
    return "failed_no_plates";
  }
  return "no_run";
}

export function packetListStatusLabel(status: PacketListStatus): string {
  switch (status) {
    case "in_flight":
      return "In flight";
    case "has_plates":
      return "Has plates";
    case "failed_no_plates":
      return "Failed — no plates";
    case "no_run":
      return "No Run yet";
  }
}

const NAME_MAX = 80;

/** Required grouping label. Pick-or-create from names this District used. */
export function normalizePacketName(raw: string): string | null {
  const name = raw.trim().replace(/\s+/g, " ");
  if (!name || name.length > NAME_MAX) return null;
  return name;
}

export const PACKET_NAME_MAX = NAME_MAX;
export const MAX_FILES_PER_PACKET = 30;
export const MAX_FILE_BYTES = 25 * 1024 * 1024;
/**
 * Vercel Functions cap the inbound body at 4.5 MB. Stay under that so
 * paste can PUT through /api/r2/put (same origin) instead of the
 * browser talking to R2. R2 CORS is a bucket setting this token cannot
 * write — that path is what painted “Failed to fetch”.
 */
export const SERVER_PUT_MAX_BYTES = 4 * 1024 * 1024;

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function isPacketId(value: string): boolean {
  return UUID_RE.test(value);
}

/** Keep Blob pathnames inside this District’s folder. No `..`, no slashes. */
export function sanitizeFilename(raw: string): string | null {
  const base = raw.replace(/\\/g, "/").split("/").pop() ?? "";
  const name = base.trim();
  if (!name || name === "." || name === ".." || name.length > 200) return null;
  if (/[\u0000-\u001f]/.test(name)) return null;
  return name;
}

export function districtPathSegment(hd: string): string | null {
  const id = hd.trim().toLowerCase();
  if (!/^[a-z0-9][a-z0-9.-]+[a-z0-9]$/.test(id) && !/^[a-z0-9]+$/.test(id)) {
    return null;
  }
  return id;
}

export function bargainPath(districtId: string, googleSub: string): string {
  return `d/${districtId}/bargain/${encodeURIComponent(googleSub)}.json`;
}

export function packetMetaPath(districtId: string, packetId: string): string {
  return `d/${districtId}/packets/${packetId}/meta.json`;
}

export function packetFilePath(
  districtId: string,
  packetId: string,
  filename: string,
): string {
  return `d/${districtId}/packets/${packetId}/files/${filename}`;
}

export function isPacketFilePath(
  districtId: string,
  packetId: string,
  pathname: string,
): boolean {
  const prefix = `d/${districtId}/packets/${packetId}/files/`;
  return pathname.startsWith(prefix) && pathname.length > prefix.length;
}

/** Latest successful Run is selected when opening a Packet. */
export function defaultSelectedRun(
  runs: readonly PacketRun[],
): PacketRun | null {
  const ok = runs.filter((run) => run.status === "succeeded");
  if (ok.length === 0) return null;
  return ok.reduce((latest, run) =>
    run.startedAt > latest.startedAt ? run : latest,
  );
}
