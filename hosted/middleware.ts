import { NextResponse } from "next/server";
import { auth } from "@/auth";

/**
 * Doors, not features. Admins never reach /operator. Operator-only
 * (allowlist, no hd) never reaches /workspace.
 */
export default auth((req) => {
  const user = req.auth?.user;
  const path = req.nextUrl.pathname;

  // The full Loom app (React build in public/app). Same bar as the Workspace.
  // Its API calls go to /api/loom, which checks the session itself.
  if (path === "/app" || path.startsWith("/app/")) {
    if (!user?.isAdmin) {
      const dest = user?.isOperator ? "/operator" : "/";
      return NextResponse.redirect(new URL(dest, req.nextUrl.origin));
    }
  }

  if (path.startsWith("/workspace")) {
    if (!user?.isAdmin) {
      const dest = user?.isOperator ? "/operator" : "/";
      return NextResponse.redirect(new URL(dest, req.nextUrl.origin));
    }
  }

  if (path.startsWith("/operator")) {
    if (!user?.isOperator) {
      const dest = user?.isAdmin ? "/workspace" : "/";
      return NextResponse.redirect(new URL(dest, req.nextUrl.origin));
    }
  }

  if (path.startsWith("/hats")) {
    if (!user?.isAdmin || !user.isOperator) {
      const dest = user?.isOperator
        ? "/operator"
        : user?.isAdmin
          ? "/workspace"
          : "/";
      return NextResponse.redirect(new URL(dest, req.nextUrl.origin));
    }
  }
});

export const config = {
  matcher: ["/workspace/:path*", "/operator/:path*", "/hats", "/app", "/app/:path*"],
};
