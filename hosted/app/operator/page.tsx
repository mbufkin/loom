import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";
import { IN_PROGRESS_STATUSES, type PacketRun } from "@/lib/packets";
import { listAllRuns } from "@/lib/store";

type DistrictRow = {
  districtId: string;
  lastActivityMs: number;
  inProgress: number;
};

/** Latest timestamp any party wrote on the Run (queue, claim, beat, finish). */
function runActivityMs(run: PacketRun): number {
  return Math.max(
    ...[run.queuedAt, run.claimedAt, run.heartbeatAt, run.finishedAt].map(
      (iso) => (iso ? Date.parse(iso) || 0 : 0),
    ),
  );
}

function districtRows(runs: readonly PacketRun[]): DistrictRow[] {
  const rows = new Map<string, DistrictRow>();
  for (const run of runs) {
    const row = rows.get(run.districtId) ?? {
      districtId: run.districtId,
      lastActivityMs: 0,
      inProgress: 0,
    };
    row.lastActivityMs = Math.max(row.lastActivityMs, runActivityMs(run));
    if (IN_PROGRESS_STATUSES.has(run.status)) row.inProgress += 1;
    rows.set(run.districtId, row);
  }
  return [...rows.values()].sort((a, b) => b.lastActivityMs - a.lastActivityMs);
}

/**
 * Operator route. Admins never see this door or a Completeness mark.
 * Districts are derived from run.json records; Freeze / +1 come later.
 */
export default async function OperatorPage() {
  const session = await auth();
  if (!session?.user?.isOperator) {
    redirect("/");
  }
  const districts = districtRows(await listAllRuns());

  return (
    <div className="shell">
      <div className="wrap">
        <div className="bar">
          <p className="kicker" style={{ margin: 0 }}>
            Operator
          </p>
          <form
            action={async () => {
              "use server";
              await signOut({ redirectTo: "/" });
            }}
          >
            <button className="linkish" type="submit">
              Sign out
            </button>
          </form>
        </div>
        <h1>Districts</h1>
        <p className="lede">
          Run activity across every District, from run records in the
          Packet store. Emails stay off this list.
        </p>
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>District</th>
                <th>Last activity</th>
                <th>Queued or running</th>
              </tr>
            </thead>
            <tbody>
              {districts.length === 0 ? (
                <tr>
                  <td className="empty" colSpan={3}>
                    No Runs recorded yet.
                  </td>
                </tr>
              ) : (
                districts.map((row) => (
                  <tr key={row.districtId}>
                    <td>{row.districtId}</td>
                    <td>
                      {new Date(row.lastActivityMs).toLocaleString("en-US", {
                        timeZone: "UTC",
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                        timeZoneName: "short",
                      })}
                    </td>
                    <td>{row.inProgress}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
