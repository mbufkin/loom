import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import {
  afterAuthPath,
  decideSignIn,
  parseEmailList,
  type SignInDecision,
} from "@/lib/access";

type GoogleProfileish =
  | { email?: string | null; email_verified?: boolean; hd?: string }
  | null
  | undefined;

/**
 * One place that reads the allowlists, so `signIn` and `jwt` can never
 * disagree about who gets in or which hats they wear.
 */
function decideForProfile(profile: GoogleProfileish): SignInDecision {
  return decideSignIn({
    email: profile?.email,
    emailVerified: Boolean(profile?.email_verified),
    hd: profile?.hd,
    operatorEmails: parseEmailList(process.env.OPERATOR_EMAILS),
    adminEmails: parseEmailList(process.env.ADMIN_EMAILS),
  });
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  // Vercel sets the host; local dev still needs AUTH_URL / AUTH_SECRET.
  trustHost: true,
  providers: [
    Google({
      authorization: {
        params: {
          // Hint the Workspace picker. Not access control — `hd` is enforced below.
          hd: "*",
          prompt: "select_account",
        },
      },
    }),
  ],
  pages: {
    signIn: "/",
    error: "/denied",
  },
  callbacks: {
    async signIn({ profile }) {
      const decision = decideForProfile(profile as GoogleProfileish);
      if (decision.ok) return true;
      return `/denied?reason=${decision.reason}`;
    },
    async jwt({ token, profile, account }) {
      // Only on the first sign-in does Google send `profile`. Later requests
      // reuse the JWT. District identity follows current `hd` on that sign-in.
      if (profile && account?.provider === "google") {
        const decision = decideForProfile(profile as GoogleProfileish);
        if (!decision.ok) {
          return token;
        }
        token.googleSub = profile.sub ?? account.providerAccountId;
        token.hd = decision.districtId;
        token.isAdmin = decision.isAdmin;
        token.isOperator = decision.isOperator;
      }
      return token;
    },
    async session({ session, token }) {
      const hd = typeof token.hd === "string" ? token.hd : null;
      session.user.googleSub =
        typeof token.googleSub === "string" ? token.googleSub : "";
      session.user.hd = hd;
      session.user.isAdmin = Boolean(token.isAdmin);
      session.user.isOperator = Boolean(token.isOperator);
      session.user.districtId = hd;
      return session;
    },
    async redirect({ url, baseUrl }) {
      if (url.startsWith("/")) return `${baseUrl}${url}`;
      if (new URL(url).origin === baseUrl) return url;
      return baseUrl;
    },
  },
});

export { afterAuthPath };
