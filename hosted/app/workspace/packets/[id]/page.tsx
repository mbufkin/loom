import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { canPasteOrStart } from "@/lib/bargain";
import {
  MAIN_PLATE,
  defaultSelectedRun,
  orderedPlates,
  runDisplayStatus,
  runDisplayStatusLabel,
  sortRunsNewestFirst,
  type PacketRun,
  type RunPlate,
} from "@/lib/packets";
import { r2Configured } from "@/lib/r2";
import { startBlockReason } from "@/lib/runs";
import {
  listAllRuns,
  listDistrictRuns,
  listRuns,
  readBargain,
  readPacket,
} from "@/lib/store";
import { WorkspaceBar } from "../../chrome";
import { StartRunButton } from "./start-run-button";

/** Dallas ISD is the only invited District; Vercel renders in UTC otherwise. */
const DISPLAY_TIME_ZONE = "America/Chicago";

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const ms = Date.parse(iso);
  if (Number.isNaN(ms)) return "—";
  return new Date(ms).toLocaleString("en-US", {
    timeZone: DISPLAY_TIME_ZONE,
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

function fileHref(key: string, download = false): string {
  return `/api/file?p=${encodeURIComponent(key)}${download ? "&download=1" : ""}`;
}

function PlateLinks({ plate }: { plate: RunPlate }) {
  return (
    <>
      <a href={fileHref(plate.key)} target="_blank" rel="noreferrer">
        View
      </a>
      {" · "}
      <a href={fileHref(plate.key, true)}>Download</a>
    </>
  );
}

function PlatesSection({ run, nowMs }: { run: PacketRun; nowMs: number }) {
  const status = runDisplayStatus(run, nowMs);
  const plates = orderedPlates(run.plates ?? []);
  const main = plates.find((plate) => plate.name === MAIN_PLATE);
  const rest = plates.filter((plate) => plate !== main);

  if (run.status !== "succeeded") {
    return (
      <p className="note">
        Run {run.id.slice(0, 8)} is {runDisplayStatusLabel(status).toLowerCase()}.
        {run.status === "failed" || run.status === "interrupted"
          ? " It produced no report."
          : " The report appears here when it succeeds."}
      </p>
    );
  }
  return (
    <>
      {main ? (
        <div className="card plate-main">
          <p className="kicker" style={{ margin: 0 }}>
            Main report
          </p>
          <h3 style={{ margin: "0.25rem 0" }}>{main.name}</h3>
          <p className="note" style={{ marginTop: 0 }}>
            First-pass audit for this Packet · {formatBytes(main.size)}
          </p>
          <p style={{ margin: 0 }}>
            <PlateLinks plate={main} />
          </p>
        </div>
      ) : (
        <p className="note">This Run finished without a FIRST-PASS report.</p>
      )}
      {rest.length > 0 ? (
        <div className="card" style={{ padding: 0, marginTop: "1rem" }}>
          <table className="table">
            <thead>
              <tr>
                <th>Supporting plate</th>
                <th>Size</th>
                <th>Open</th>
              </tr>
            </thead>
            <tbody>
              {rest.map((plate) => (
                <tr key={plate.key}>
                  <td>{plate.name}</td>
                  <td>{formatBytes(plate.size)}</td>
                  <td>
                    <PlateLinks plate={plate} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  );
}

export default async function PacketPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ run?: string }>;
}) {
  const session = await auth();
  if (!session?.user?.isAdmin || !session.user.districtId) {
    redirect("/");
  }

  const { id } = await params;
  const { run: requestedRunId } = await searchParams;
  const districtId = session.user.districtId;
  const packet = await readPacket(districtId, id);
  if (!packet) notFound();

  // Reads are fail-soft: an R2 hiccup shows no Runs instead of a crash.
  // The Start route re-counts fail-closed, so this cannot skip the Cap.
  const [bargain, packetRuns, districtRuns, allRuns] = await Promise.all([
    readBargain(districtId, session.user.googleSub),
    listRuns(districtId, packet.id),
    listDistrictRuns(districtId),
    listAllRuns(),
  ]);
  const nowMs = Date.now();
  const runs = sortRunsNewestFirst(packetRuns);
  const selected =
    runs.find((run) => run.id === requestedRunId) ?? defaultSelectedRun(runs);

  const blockedReason = !r2Configured()
    ? "The Packet store is not configured on the host."
    : !canPasteOrStart(Boolean(bargain))
      ? "Accept the Bargain on the Workspace before you can start a Run."
      : startBlockReason(districtRuns, allRuns, nowMs);

  const pasted = new Date(packet.pastedAt).toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });

  return (
    <div className="shell">
      <div className="wrap wrap-wide">
        <WorkspaceBar
          districtName={districtId}
          showHats={session.user.isOperator}
        />
        <p className="crumb">
          <Link href="/workspace">Workspace</Link>
        </p>
        <h1>{packet.name}</h1>
        <p className="lede">
          Pasted {pasted}. Same files the Operator opens. A Run audits these
          files on the Loom Worker and publishes the report here.
        </p>

        <h2 className="section">Files</h2>
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Size</th>
              </tr>
            </thead>
            <tbody>
              {packet.files.map((file) => (
                <tr key={file.pathname}>
                  <td>
                    <a href={fileHref(file.pathname)}>{file.name}</a>
                  </td>
                  <td>{formatBytes(file.size)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <h2 className="section">Runs</h2>
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Run</th>
                <th>Status</th>
                <th>Queued</th>
                <th>Finished</th>
                <th>Attempt</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {runs.length === 0 ? (
                <tr>
                  <td className="empty" colSpan={6}>
                    No Run yet.
                  </td>
                </tr>
              ) : (
                runs.map((run) => {
                  const isSelected = run.id === selected?.id;
                  return (
                    <tr key={run.id} className={isSelected ? "row-selected" : undefined}>
                      <td>
                        <Link href={`/workspace/packets/${packet.id}?run=${run.id}`}>
                          {run.id.slice(0, 8)}
                        </Link>
                        {isSelected ? " (shown)" : ""}
                      </td>
                      <td>{runDisplayStatusLabel(runDisplayStatus(run, nowMs))}</td>
                      <td>{formatTime(run.queuedAt)}</td>
                      <td>{formatTime(run.finishedAt)}</td>
                      <td>{run.attempt}</td>
                      <td>{run.error ?? "—"}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {selected ? (
          <>
            <h2 className="section">Report</h2>
            <PlatesSection run={selected} nowMs={nowMs} />
          </>
        ) : null}

        <StartRunButton packetId={packet.id} blockedReason={blockedReason} />
      </div>
    </div>
  );
}
