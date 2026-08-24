import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { BARGAIN_SENTENCE, canPasteOrStart } from "@/lib/bargain";
import { packetListStatus, packetListStatusLabel } from "@/lib/packets";
import { STORE_CEILING_REASON } from "@/lib/store-ceiling";
import {
  listPackets,
  readBargain,
  storeCeilingBlocksPaste,
  writeBargain,
} from "@/lib/store";
import { WorkspaceBar } from "./chrome";

export default async function WorkspacePage() {
  const session = await auth();
  if (!session?.user?.isAdmin || !session.user.districtId) {
    redirect("/");
  }

  const districtId = session.user.districtId;
  const [bargain, packets, storeFull] = await Promise.all([
    readBargain(districtId, session.user.googleSub),
    listPackets(districtId),
    storeCeilingBlocksPaste(),
  ]);
  const accepted = canPasteOrStart(Boolean(bargain));

  async function acceptBargain() {
    "use server";
    const again = await auth();
    if (!again?.user?.isAdmin || !again.user.districtId || !again.user.googleSub) {
      redirect("/");
    }
    const existing = await readBargain(again.user.districtId, again.user.googleSub);
    if (!existing) {
      await writeBargain(again.user.districtId, {
        googleSub: again.user.googleSub,
        acceptedAt: new Date().toISOString(),
      });
    }
    redirect("/workspace");
  }

  return (
    <div className="shell">
      <div className="wrap wrap-wide">
        <WorkspaceBar
          districtName={districtId}
          showHats={session.user.isOperator}
        />
        <h1>Workspace</h1>
        <p className="lede">
          Packets for this District. Anyone on {districtId} may open them.
        </p>
        <p className="identity">
          Signed in as <strong>{session.user.email}</strong>
        </p>

        {accepted && storeFull ? (
          <p className="note">{STORE_CEILING_REASON}.</p>
        ) : accepted ? (
          <p className="actions">
            <Link className="btn btn-brass" href="/workspace/paste">
              Paste a Packet
            </Link>
          </p>
        ) : (
          <div className="card bargain">
            <h2>The Bargain</h2>
            <p>{BARGAIN_SENTENCE}</p>
            <p className="note">
              You can look at this Workspace without accepting. Paste and Start
              wait until you do — for yourself, once. This is a product rule,
              not legal advice.
            </p>
            <form action={acceptBargain}>
              <button className="btn btn-brass" type="submit">
                I accept
              </button>
            </form>
          </div>
        )}

        <div className="card" style={{ marginTop: "1.5rem", padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>Packet name</th>
                <th>Pasted</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {packets.length === 0 ? (
                <tr>
                  <td className="empty" colSpan={3}>
                    No Packets yet.
                  </td>
                </tr>
              ) : (
                packets.map((packet) => {
                  const status = packetListStatus(packet.runs);
                  const pasted = new Date(packet.pastedAt).toLocaleDateString(
                    "en-US",
                    { year: "numeric", month: "short", day: "numeric" },
                  );
                  return (
                    <tr key={packet.id}>
                      <td>
                        <Link href={`/workspace/packets/${packet.id}`}>
                          {packet.name}
                        </Link>
                      </td>
                      <td>{pasted}</td>
                      <td>{packetListStatusLabel(status)}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
