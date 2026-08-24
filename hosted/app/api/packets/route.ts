import { NextResponse } from "next/server";
import { canPasteOrStart } from "@/lib/bargain";
import {
  MAX_FILES_PER_PACKET,
  isPacketFilePath,
  isPacketId,
  normalizePacketName,
  sanitizeFilename,
  type Packet,
  type PacketFile,
} from "@/lib/packets";
import { requireAdmin } from "@/lib/require-admin";
import {
  deleteReservation,
  listPackets,
  readBargain,
  writePacket,
} from "@/lib/store";

export async function GET() {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "denied" }, { status: 401 });
  const packets = await listPackets(admin.districtId);
  return NextResponse.json({ packets });
}

type PasteBody = {
  packetId?: string;
  name?: string;
  files?: PacketFile[];
};

export async function POST(request: Request) {
  const admin = await requireAdmin();
  if (!admin) return NextResponse.json({ error: "denied" }, { status: 401 });

  const bargain = await readBargain(admin.districtId, admin.googleSub);
  if (!canPasteOrStart(Boolean(bargain))) {
    return NextResponse.json({ error: "Bargain required" }, { status: 403 });
  }

  const body = (await request.json()) as PasteBody;
  const packetId = body.packetId ?? "";
  const name = normalizePacketName(body.name ?? "");
  const files = body.files ?? [];

  if (!isPacketId(packetId)) {
    return NextResponse.json({ error: "Bad Packet id" }, { status: 400 });
  }
  if (!name) {
    return NextResponse.json({ error: "Packet name is required" }, { status: 400 });
  }
  if (files.length === 0 || files.length > MAX_FILES_PER_PACKET) {
    return NextResponse.json({ error: "Choose 1–30 files" }, { status: 400 });
  }

  const cleaned: PacketFile[] = [];
  for (const file of files) {
    const filename = sanitizeFilename(file.name);
    if (
      !filename ||
      !isPacketFilePath(admin.districtId, packetId, file.pathname)
    ) {
      return NextResponse.json({ error: "Bad file path" }, { status: 400 });
    }
    cleaned.push({
      name: filename,
      pathname: file.pathname,
      size: file.size,
      contentType: file.contentType || "application/octet-stream",
    });
  }

  const packet: Packet = {
    id: packetId,
    name,
    pastedAt: new Date().toISOString(),
    districtId: admin.districtId,
    files: cleaned,
    runs: [],
  };

  await writePacket(packet);
  try {
    await deleteReservation(packetId);
  } catch {
    // Reservation expires on its own; do not fail a frozen Packet.
  }
  return NextResponse.json({ packet });
}
