import { auth } from "@/auth";

export type AdminSession = {
  googleSub: string;
  districtId: string;
  email: string | null | undefined;
  isOperator: boolean;
};

/** Workspace writes (Bargain, paste) need an Admin hat and a person key. */
export async function requireAdmin(): Promise<AdminSession | null> {
  const session = await auth();
  const user = session?.user;
  if (!user?.isAdmin || !user.districtId || !user.googleSub) return null;
  return {
    googleSub: user.googleSub,
    districtId: user.districtId,
    email: user.email,
    isOperator: Boolean(user.isOperator),
  };
}

export async function requireSignedIn() {
  const session = await auth();
  return session?.user ?? null;
}
