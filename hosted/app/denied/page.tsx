import Link from "next/link";

type DeniedCopy = { heading: string; reason: string };

/**
 * One heading per deny reason (lib/access.ts DenyReason). `AccessDenied`
 * is Auth.js's generic code — our signIn callback redirects with a
 * specific reason, so seeing it means some other refusal, not "no hd".
 */
const REASONS: Record<string, DeniedCopy> = {
  "no-hd": {
    heading: "Not a school account.",
    reason:
      "That Google account has no Workspace hosted domain. Personal Gmail cannot be an Admin.",
  },
  unverified: {
    heading: "Email not verified.",
    reason: "Google has not verified that email yet.",
  },
  "no-email": {
    heading: "No email on that sign-in.",
    reason: "Google did not return an email on that sign-in.",
  },
  "not-invited": {
    heading: "Not invited yet.",
    reason: "Loom is invite-only right now. Ask the Operator to invite this email.",
  },
  AccessDenied: {
    heading: "Sign-in refused.",
    reason:
      "Loom is invite-only. Use a school Google account the Operator has invited.",
  },
};

const FALLBACK: DeniedCopy = {
  heading: "Can’t sign in.",
  reason:
    "This account cannot sign in. Loom is invite-only and needs a school Google account (Workspace hosted domain).",
};

export default async function DeniedPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string; error?: string }>;
}) {
  const params = await searchParams;
  const key = params.reason ?? params.error ?? "";
  const copy = REASONS[key] ?? FALLBACK;

  return (
    <div className="shell">
      <div className="wrap">
        <p className="kicker">Loom</p>
        <h1>{copy.heading}</h1>
        <p className="reason">{copy.reason}</p>
        <Link className="btn btn-ghost" href="/">
          Try another account
        </Link>
      </div>
    </div>
  );
}
