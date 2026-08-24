import NextAuth from "next-auth";
import Google from "next-auth/providers/google";
import {
  afterAuthPath,
  decideSignIn,
  parseOperatorEmails,
} from "@/lib/access";

function operatorEmails(): string[] {
  return parseOperatorEmails(process.env.OPERATOR_EMAILS);
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
      const decision = decideSignIn({
        email: profile?.email,
        emailVerified: Boolean(
          (profile as { email_verified?: boolean } | undefined)?.email_verified,
        ),
        hd: (profile as { hd?: string } | undefined)?.hd,
        operatorEmails: operatorEmails(),
      });
      if (decision.ok) return true;
      return `/denied?reason=${decision.reason}`;
    },
    async jwt({ token, profile, account }) {
      // Only on the first sign-in does Google send `profile`. Later requests
      // reuse the JWT. District identity follows current `hd` on that sign-in.
      if (profile && account?.provider === "google") {
        const decision = decideSignIn({
          email: profile.email,
          emailVerified: Boolean(
            (profile as { email_verified?: boolean }).email_verified,
          ),
          hd: (profile as { hd?: string }).hd,
          operatorEmails: operatorEmails(),
        });
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
