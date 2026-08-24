import { NextResponse } from "next/server";
import { authorizePacketFilePut } from "@/lib/r2-put-grant";
import { r2PresignPut } from "@/lib/r2";

type Body = {
  pathname?: string;
  contentType?: string;
  size?: number;
};

/**
 * Client-direct put. Packet bytes skip the 4.5 MB Function body.
 * Needs CORS on the loom bucket — without it the browser reports
 * “Failed to fetch”. Prefer /api/r2/put for files under 4 MB.
 */
export async function POST(request: Request) {
  const body = (await request.json()) as Body;
  const grant = await authorizePacketFilePut({
    pathname: body.pathname ?? "",
    contentType: body.contentType,
    size: body.size ?? 0,
  });
  if (!grant.ok) {
    return NextResponse.json({ error: grant.error }, { status: grant.status });
  }

  const url = await r2PresignPut(grant.pathname, grant.contentType, grant.size);
  return NextResponse.json({ url, pathname: grant.pathname });
}
