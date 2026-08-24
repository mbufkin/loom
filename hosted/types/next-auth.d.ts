import type { DefaultSession } from "next-auth";

/**
 * Session fields the product needs beyond Auth.js defaults (name/email/image).
 * `hd` is not a default User column — we copy it on sign-in.
 */
declare module "next-auth" {
  interface Session {
    user: DefaultSession["user"] & {
      googleSub: string;
      hd: string | null;
      isAdmin: boolean;
      isOperator: boolean;
      districtId: string | null;
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    googleSub: string;
    hd: string | null;
    isAdmin: boolean;
    isOperator: boolean;
  }
}
