import { NextResponse } from "next/server";
import { r2GetObject } from "@/lib/r2";
import { requireSignedIn } from "@/lib/require-admin";

/**
 * Private R2 — browsers cannot fetch the bucket. Admins of that
 * District and Operators may read the same Packet files.
 */
export async function GET(request: Request) {
  const user = await requireSignedIn();
  if (!user) return NextResponse.json({ error: "denied" }, { status: 401 });

  const pathname = new URL(request.url).searchParams.get("p") ?? "";
  const match = /^d\/([^/]+)\/packets\//.exec(pathname);
  if (!match?.[1]) {
    return NextResponse.json({ error: "Bad path" }, { status: 400 });
  }
  const districtId = match[1];

  const allowed =
    user.isOperator || (user.isAdmin && user.districtId === districtId);
  if (!allowed) {
    return NextResponse.json({ error: "denied" }, { status: 403 });
  }

  try {
    const obj = await r2GetObject(pathname);
    if (!obj.Body) {
      return NextResponse.json({ error: "missing" }, { status: 404 });
    }
    const filename = pathname.split("/").pop() ?? "file";
    return new NextResponse(obj.Body.transformToWebStream(), {
      headers: {
        "content-type": obj.ContentType || "application/octet-stream",
        "content-disposition": `inline; filename="${filename.replace(/"/g, "")}"`,
      },
    });
  } catch (error) {
    const name = (error as { name?: string }).name;
    if (name === "NoSuchKey" || name === "NotFound") {
      return NextResponse.json({ error: "missing" }, { status: 404 });
    }
    throw error;
  }
}
