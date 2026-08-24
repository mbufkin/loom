import Link from "next/link";
import { redirect } from "next/navigation";
import { auth } from "@/auth";
import { canPasteOrStart } from "@/lib/bargain";
import { listPackets, readBargain, usedPacketNames } from "@/lib/store";
import { WorkspaceBar } from "../chrome";
import { PasteForm } from "./paste-form";

export default async function PastePage() {
  const session = await auth();
  if (!session?.user?.isAdmin || !session.user.districtId) {
    redirect("/");
  }

  const districtId = session.user.districtId;
  const bargain = await readBargain(districtId, session.user.googleSub);
  if (!canPasteOrStart(Boolean(bargain))) {
    redirect("/workspace");
  }

  const names = usedPacketNames(await listPackets(districtId));

  return (
    <div className="shell">
      <div className="wrap">
        <WorkspaceBar
          districtName={districtId}
          showHats={session.user.isOperator}
        />
        <p className="crumb">
          <Link href="/workspace">Workspace</Link>
        </p>
        <h1>Paste a Packet</h1>
        <p className="lede">
          One frozen set of documents. Start a Run from the Packet after
          these files land. PowerPoint decks become slide text here —
          the pictures never enter the store. New pastes stop if they
          would leave the Packet store’s free tier.
        </p>
        <div className="card">
          <PasteForm districtId={districtId} names={names} />
        </div>
      </div>
    </div>
  );
}
