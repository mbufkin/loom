import { NextResponse } from "next/server";
import { canPasteOrStart } from "@/lib/bargain";
import { requireAdmin } from "@/lib/require-admin";
import { readBargain, writeBargain } from "@/lib/store";

export async function GET() {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "denied" }, { status: 401 });
  const record = await readBargain(admin.districtId, admin.googleSub);
  return NextResponse.json({
    accepted: canPasteOrStart(Boolean(record)),
  });
}

export async function POST() {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "denied" }, { status: 401 });

  const existing = await readBargain(admin.districtId, admin.googleSub);
  if (!existing) {
    await writeBargain(admin.districtId, {
      googleSub: admin.googleSub,
      acceptedAt: new Date().toISOString(),
    });
  }

  return NextResponse.json({ accepted: true });
}
