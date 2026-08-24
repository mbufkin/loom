import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { auth } from "@/auth";
import { canPasteOrStart } from "@/lib/bargain";
import { packetListStatus, packetListStatusLabel } from "@/lib/packets";
import { readBargain, readPacket } from "@/lib/store";
import { WorkspaceBar } from "../../chrome";

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export default async function PacketPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const session = await auth();
  if (!session?.user?.isAdmin || !session.user.districtId) {
    redirect("/");
  }

  const { id } = await params;
  const districtId = session.user.districtId;
  const packet = await readPacket(districtId, id);
  if (!packet) notFound();

  const bargain = await readBargain(districtId, session.user.googleSub);
  const mayStart = canPasteOrStart(Boolean(bargain));
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
          Pasted {pasted}. Same files the Operator opens. Start is not live
          until the Worker is on Fly — a click now would count against the Cap
          and never finish.
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
                    <a href={`/api/file?p=${encodeURIComponent(file.pathname)}`}>
                      {file.name}
                    </a>
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
              </tr>
            </thead>
            <tbody>
              {packet.runs.length === 0 ? (
                <tr>
                  <td className="empty" colSpan={2}>
                    No Run yet. {packetListStatusLabel(packetListStatus([]))}.
                  </td>
                </tr>
              ) : (
                packet.runs.map((run) => (
                  <tr key={run.id}>
                    <td>{run.id}</td>
                    <td>{run.status}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        <div className="stack" style={{ marginTop: "1.5rem" }}>
          <button className="btn btn-brass" type="button" disabled>
            Start a Run
          </button>
          <p className="note">
            {mayStart
              ? "The Fly Worker is not wired yet. Files stay. Start will use the Operator NIM key on Fly, not in this browser."
              : "Accept the Bargain on the Workspace before you can start a Run."}
          </p>
        </div>
      </div>
    </div>
  );
}
