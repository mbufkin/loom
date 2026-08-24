import Link from "next/link";
import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";

/** Two hats, two doors. The Admin surface does not link here. */
export default async function HatsPage() {
  const session = await auth();
  if (!session?.user?.isAdmin || !session.user.isOperator) {
    redirect("/");
  }

  return (
    <div className="shell">
      <div className="wrap">
        <div className="bar">
          <p className="kicker" style={{ margin: 0 }}>
            Loom
          </p>
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
        <h1>Which door?</h1>
        <p className="lede">
          This account is an Admin of {session.user.districtId} and an
          Operator. Those are separate hats.
        </p>
        <div className="doors">
          <Link className="door" href="/workspace">
            <h2>Workspace</h2>
            <p>This District’s Packets and plates.</p>
          </Link>
          <Link className="door" href="/operator">
            <h2>Operator</h2>
            <p>Every District. Usage, Freeze, grant.</p>
          </Link>
        </div>
      </div>
    </div>
  );
}
