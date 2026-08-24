import Link from "next/link";

const REASONS: Record<string, string> = {
  "no-hd":
    "That Google account has no Workspace hosted domain. Personal Gmail cannot be an Admin.",
  unverified: "Google has not verified that email yet.",
  "no-email": "Google did not return an email on that sign-in.",
  AccessDenied:
    "That Google account has no Workspace hosted domain. Personal Gmail cannot be an Admin.",
};

export default async function DeniedPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string; error?: string }>;
}) {
  const params = await searchParams;
  const key = params.reason ?? params.error ?? "";
  const copy =
    REASONS[key] ??
    "This account cannot sign in. Use a school Google account (Workspace hosted domain).";

  return (
    <div className="shell">
      <div className="wrap">
        <p className="kicker">Loom</p>
        <h1>Not a school account.</h1>
        <p className="reason">{copy}</p>
        <Link className="btn btn-ghost" href="/">
          Try another account
        </Link>
      </div>
    </div>
  );
}
