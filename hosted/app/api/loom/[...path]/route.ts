import { auth } from "@/auth";
import { forwardLoom, type Access } from "@/lib/loom-proxy";

// Never cache: every answer depends on the session and on live Pi state.
export const dynamic = "force-dynamic";
// Uploads and report reads are short; long work is async on the Pi.
export const maxDuration = 60;

/** Same bar as the Workspace: an invited Admin with a Workspace `hd`. */
async function loomAccess(): Promise<Access> {
  const session = await auth();
  const user = session?.user;
  if (!user) return "signed-out";
  if (!user.isAdmin || !user.districtId || !user.googleSub) return "forbidden";
  return "ok";
}

type Ctx = { params: Promise<{ path: string[] }> };

async function handle(req: Request, ctx: Ctx): Promise<Response> {
  const { path } = await ctx.params;
  return forwardLoom(req, path ?? [], { access: loomAccess });
}

export const GET = handle;
export const POST = handle;
