import { signOut } from "@/auth";

export function WorkspaceBar({
  districtName,
  showHats,
}: {
  districtName: string;
  showHats?: boolean;
}) {
  return (
    <div className="bar">
      <p className="kicker" style={{ margin: 0 }}>
        {districtName}
      </p>
      <div className="bar-actions">
        {/* Plain <a>, not <Link>: /app is a separate React app, not a Next page. */}
        <a className="linkish" href="/app/">
          Open Loom app
        </a>
        {showHats ? (
          <a className="linkish" href="/hats">
            Other door
          </a>
        ) : null}
        <form
          action={async () => {
            "use server";
            await signOut({ redirectTo: "/" });
          }}
        >
          <button className="linkish" type="submit">
            Sign out
          </button>
        </form>
      </div>
    </div>
  );
}
