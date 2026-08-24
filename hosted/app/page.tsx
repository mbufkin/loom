import { redirect } from "next/navigation";
import { afterAuthPath, auth, signIn } from "@/auth";

function googleConfigured(): boolean {
  return Boolean(
    process.env.AUTH_SECRET &&
      process.env.AUTH_GOOGLE_ID &&
      process.env.AUTH_GOOGLE_SECRET,
  );
}

export default async function SignInPage() {
  const session = await auth();
  if (session?.user) {
    redirect(
      afterAuthPath({
        isAdmin: session.user.isAdmin,
        isOperator: session.user.isOperator,
      }),
    );
  }

  const ready = googleConfigured();

  return (
    <div className="shell">
      <div className="wrap">
        <p className="kicker">Loom</p>
        <h1>
          Curriculum, as it
          <br />
          actually stands.
        </h1>
        <p className="lede">
          Sign in with a school Google account. Personal Gmail cannot open a
          District Workspace.
        </p>
        <div className="card">
          <form
            action={async () => {
              "use server";
              await signIn("google", { redirectTo: "/after-auth" });
            }}
          >
            <button className="btn btn-brass" type="submit" disabled={!ready}>
              Continue with Google
            </button>
          </form>
          <p className="note">
            {ready
              ? "Workspace membership follows the hosted domain on this sign-in. Students and vendors on that domain are Admins too."
              : "Google sign-in is not configured yet. Copy hosted/.env.example to hosted/.env.local and add AUTH_SECRET, AUTH_GOOGLE_ID, and AUTH_GOOGLE_SECRET."}
          </p>
        </div>
      </div>
    </div>
  );
}
