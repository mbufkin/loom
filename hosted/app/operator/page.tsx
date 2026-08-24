import { redirect } from "next/navigation";
import { auth, signOut } from "@/auth";

/**
 * Operator route. Admins never see this door or a Completeness mark.
 * Slice 1: the door exists; Districts / Freeze / +1 come with later slices.
 */
export default async function OperatorPage() {
  const session = await auth();
  if (!session?.user?.isOperator) {
    redirect("/");
  }

  return (
    <div className="shell">
      <div className="wrap">
        <div className="bar">
          <p className="kicker" style={{ margin: 0 }}>
            Operator
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
        <h1>Districts</h1>
        <p className="lede">
          Usage and plates across every District. Emails stay off this list.
        </p>
        <div className="card" style={{ padding: 0 }}>
          <table className="table">
            <thead>
              <tr>
                <th>District</th>
                <th>Last activity</th>
                <th>In flight</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="empty" colSpan={3}>
                  No Districts have started a Run yet.
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
