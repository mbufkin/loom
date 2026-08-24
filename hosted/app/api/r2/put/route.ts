import { NextResponse } from "next/server";
import { SERVER_PUT_MAX_BYTES } from "@/lib/packets";
import { authorizePacketFilePut } from "@/lib/r2-put-grant";
import { r2PutBytes } from "@/lib/r2";

export const runtime = "nodejs";
export const maxDuration = 30;

/**
 * Same-origin put. The browser never talks to r2.cloudflarestorage.com,
 * so a bucket with no CORS rule cannot paint “Failed to fetch”.
 *
 * Vercel caps the Function body at 4.5 MB — refuse above 4 MB so we
 * do not silently truncate. Larger files still need a presigned PUT
 * after CORS is set on the loom bucket.
 */
export async function POST(request: Request) {
  const pathname = request.headers.get("x-loom-pathname") ?? "";
  const contentType =
    request.headers.get("x-loom-content-type") || "application/octet-stream";
  const declared = Number(request.headers.get("x-loom-size") ?? "0");

  if (declared > SERVER_PUT_MAX_BYTES) {
    return NextResponse.json(
      {
        error:
          "This file is over 4 MB. Loom cannot carry it through the Function. Add CORS on the loom R2 bucket, then retry.",
      },
      { status: 413 },
    );
  }

  const grant = await authorizePacketFilePut({
    pathname,
    contentType,
    size: declared,
  });
  if (!grant.ok) {
    return NextResponse.json({ error: grant.error }, { status: grant.status });
  }

  const bytes = new Uint8Array(await request.arrayBuffer());
  if (bytes.byteLength !== grant.size) {
    return NextResponse.json(
      { error: "File size did not match the reservation" },
      { status: 400 },
    );
  }

  await r2PutBytes(grant.pathname, bytes, grant.contentType);
  return NextResponse.json({ ok: true, pathname: grant.pathname });
}
