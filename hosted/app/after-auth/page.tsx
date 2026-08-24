import { redirect } from "next/navigation";
import { afterAuthPath, auth } from "@/auth";

/** Lands after Google returns. Picks Workspace, Operator, or the two-hat chooser. */
export default async function AfterAuthPage() {
  const session = await auth();
  if (!session?.user) {
    redirect("/");
  }
  redirect(
    afterAuthPath({
      isAdmin: session.user.isAdmin,
      isOperator: session.user.isOperator,
    }),
  );
}
