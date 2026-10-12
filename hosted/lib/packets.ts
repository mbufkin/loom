/**
 * Packet rules for the hosted Workspace.
 *
 * A Packet is one frozen paste. Packet name is a grouping label, not a
 * unique id — two “Ag Mechanics” pastes are two Packets. Completeness
 * (name timeline) is Operator-only and does not live here.
 */

/**
 * Run record contract — mirrors hosted_runs.py (the Worker side). Keep the
 * two in sync: the Worker spreads the record on every write, so fields
 * Vercel adds survive, but a renamed field here would silently read empty.
 */
export const RUN_SCHEMA = 1;
export const RUN_STATUSES = [
  "queued",
  "running",
  "succeeded",
  "failed",
  "interrupted",
] as const;
export type RunStatus = (typeof RUN_STATUSES)[number];

/** queued/running block a new Start; the rest are terminal. */
export const IN_PROGRESS_STATUSES: ReadonlySet<RunStatus> = new Set([
  "queued",
  "running",
]);

/** hosted_runs.STALE_AFTER_SECONDS — the Worker heartbeats every 60 s. */
export const RUN_STALE_AFTER_MS = 15 * 60 * 1000;

/** Plate files in display order. FIRST-PASS is the report; the rest support it. */
export const MAIN_PLATE = "FIRST-PASS.md";
export const PLATE_ORDER = [
  MAIN_PLATE,
  "SUMMARY.md",
  "DASHBOARD.md",
  "GLOBAL-AUDIT-REPORT.pdf",
  "USAGE-SUMMARY.json",
] as const;

export type RunPlate = {
  name: string;
  key: string;
  size: number;
  contentType?: string;
};

/**
 * One run.json. Vercel writes the first five-plus fields (queued); after
 * claim the Worker owns the object and fills the optional ones.
 */
export type PacketRun = {
  schema: number;
  id: string;
  districtId: string;
  packetId: string;
  status: RunStatus;
  queuedAt: string;
  attempt: number;
  startedBy?: string;
  claimedAt?: string | null;
  heartbeatAt?: string | null;
  finishedAt?: string | null;
  worker?: string | null;
  error?: string | null;
  plates?: RunPlate[];
};

/** What the Admin sees: a `running` Run with an old heartbeat reads as stalled. */
export type RunDisplayStatus = RunStatus | "stalled";

function parseTime(value: string | null | undefined): number | null {
  if (!value) return null;
  const ms = Date.parse(value);
  return Number.isNaN(ms) ? null : ms;
}

/**
 * Stalled = running, but the Worker has not heartbeated for 15 min.
 * Falls back to claimedAt (the claim also stamps heartbeatAt, so a missing
 * heartbeat means a hand-edited or truncated record — treat it as stalled).
 */
export function isRunStalled(run: PacketRun, nowMs: number): boolean {
  if (run.status !== "running") return false;
  const beat = parseTime(run.heartbeatAt) ?? parseTime(run.claimedAt);
  if (beat === null) return true;
  return nowMs - beat > RUN_STALE_AFTER_MS;
}

export function runDisplayStatus(
  run: PacketRun,
  nowMs: number,
): RunDisplayStatus {
  return isRunStalled(run, nowMs) ? "stalled" : run.status;
}

export function runDisplayStatusLabel(status: RunDisplayStatus): string {
  switch (status) {
    case "queued":
      return "Queued";
    case "running":
      return "Running";
    case "stalled":
      return "Stalled — no Worker heartbeat for 15+ min";
    case "succeeded":
      return "Succeeded";
    case "failed":
      return "Failed";
    case "interrupted":
      return "Interrupted";
  }
}

/** Plates sorted FIRST-PASS first, then the contract order, then anything new by name. */
export function orderedPlates(plates: readonly RunPlate[]): RunPlate[] {
  const rank = (name: string) => {
    const i = (PLATE_ORDER as readonly string[]).indexOf(name);
    return i === -1 ? PLATE_ORDER.length : i;
  };
  return [...plates].sort(
    (a, b) => rank(a.name) - rank(b.name) || a.name.localeCompare(b.name),
  );
}

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
  /**
   * Legacy field: always written as [] and never updated. Run status lives
   * in runs/<runId>/run.json (see listRuns in store.ts). Kept so the
   * meta.json shape the Worker's parse_packet reads does not change.
   */
  runs: unknown[];
};

/**
 * List-row status. In progress wins so a retry does not look “done.”
 * A Packet with no Run yet is not a failure — paste happened; Start has not.
 * Stalled only shows when every in-progress Run is stalled; one healthy
 * Run means the Worker is alive.
 */
export type PacketListStatus =
  | "in_progress"
  | "stalled"
  | "has_plates"
  | "failed_no_plates"
  | "no_run";

export function packetListStatus(
  runs: readonly PacketRun[],
  nowMs: number = Date.now(),
): PacketListStatus {
  const active = runs.filter((run) => IN_PROGRESS_STATUSES.has(run.status));
  if (active.length > 0) {
    return active.every((run) => isRunStalled(run, nowMs))
      ? "stalled"
      : "in_progress";
  }
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
    case "in_progress":
      return "In progress";
    case "stalled":
      return "Stalled";
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

function latestBy(
  runs: readonly PacketRun[],
  field: "finishedAt" | "queuedAt",
): PacketRun | null {
  let best: PacketRun | null = null;
  let bestMs = -Infinity;
  for (const run of runs) {
    const ms = parseTime(run[field]) ?? -Infinity;
    if (best === null || ms > bestMs) {
      best = run;
      bestMs = ms;
    }
  }
  return best;
}

/**
 * Opening a Packet shows the latest successful Run (by finishedAt), so a
 * failed retry never hides good plates. With no success, show the newest
 * Run by queuedAt so the Admin sees what is happening now.
 */
export function defaultSelectedRun(
  runs: readonly PacketRun[],
): PacketRun | null {
  const ok = runs.filter((run) => run.status === "succeeded");
  return ok.length > 0 ? latestBy(ok, "finishedAt") : latestBy(runs, "queuedAt");
}

/** Newest first by queuedAt — the Runs table order. */
export function sortRunsNewestFirst(runs: readonly PacketRun[]): PacketRun[] {
  return [...runs].sort(
    (a, b) => (parseTime(b.queuedAt) ?? 0) - (parseTime(a.queuedAt) ?? 0),
  );
}

/** Same string hosted_runs.now_iso() writes: seconds precision, trailing Z. */
export function runIsoNow(nowMs: number = Date.now()): string {
  return new Date(nowMs).toISOString().replace(/\.\d{3}Z$/, "Z");
}

export function runDirPath(
  districtId: string,
  packetId: string,
  runId: string,
): string {
  return `d/${districtId}/packets/${packetId}/runs/${runId}/`;
}

export function runRecordPath(
  districtId: string,
  packetId: string,
  runId: string,
): string {
  return `${runDirPath(districtId, packetId, runId)}run.json`;
}

export function runQueuePath(runId: string): string {
  return `queue/${runId}.json`;
}

const RUN_KEY_RE =
  /^d\/([^/]+)\/packets\/([^/]+)\/runs\/([^/]+)\/run\.json$/;

/** Split a run.json key into its ids, or null if the key is some other object. */
export function parseRunRecordKey(
  key: string,
): { districtId: string; packetId: string; runId: string } | null {
  const m = RUN_KEY_RE.exec(key);
  if (!m?.[1] || !m[2] || !m[3]) return null;
  return { districtId: m[1], packetId: m[2], runId: m[3] };
}

/**
 * Validate a run.json against the key it came from. Returns null for
 * anything that does not match the contract — the caller logs and drops
 * it, so one bad record cannot break the page or the Cap count.
 */
export function parseRunRecord(key: string, raw: unknown): PacketRun | null {
  const ids = parseRunRecordKey(key);
  if (!ids || !raw || typeof raw !== "object") return null;
  const r = raw as Record<string, unknown>;
  if (
    r.id !== ids.runId ||
    r.districtId !== ids.districtId ||
    r.packetId !== ids.packetId ||
    typeof r.status !== "string" ||
    !(RUN_STATUSES as readonly string[]).includes(r.status) ||
    typeof r.queuedAt !== "string" ||
    parseTime(r.queuedAt) === null
  ) {
    return null;
  }
  const optString = (v: unknown) => (typeof v === "string" ? v : null);
  const prefix = `${runDirPath(ids.districtId, ids.packetId, ids.runId)}plates/`;
  // Plate keys must stay inside this Run, so a bad record cannot point the
  // download link at another Packet's files.
  const plates: RunPlate[] = Array.isArray(r.plates)
    ? r.plates.flatMap((p): RunPlate[] => {
        if (!p || typeof p !== "object") return [];
        const plate = p as Record<string, unknown>;
        if (
          typeof plate.name !== "string" ||
          typeof plate.key !== "string" ||
          !plate.key.startsWith(prefix) ||
          plate.key.length <= prefix.length
        ) {
          return [];
        }
        return [
          {
            name: plate.name,
            key: plate.key,
            size: typeof plate.size === "number" ? plate.size : 0,
            contentType: optString(plate.contentType) ?? undefined,
          },
        ];
      })
    : [];
  return {
    schema: typeof r.schema === "number" ? r.schema : RUN_SCHEMA,
    id: ids.runId,
    districtId: ids.districtId,
    packetId: ids.packetId,
    status: r.status as RunStatus,
    queuedAt: r.queuedAt,
    attempt: typeof r.attempt === "number" ? r.attempt : 0,
    startedBy: optString(r.startedBy) ?? undefined,
    claimedAt: optString(r.claimedAt),
    heartbeatAt: optString(r.heartbeatAt),
    finishedAt: optString(r.finishedAt),
    worker: optString(r.worker),
    error: optString(r.error),
    plates,
  };
}
