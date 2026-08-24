/**
 * Sign-in gate for Hosted Loom.
 *
 * Google proves account + optional Workspace `hd`. It does not prove “school”
 * or staff. We enforce the product rule here:
 *   - Operator allowlist skips `hd` (Gmail is fine for Operator only).
 *   - Admin requires a present `hd`. Personal Gmail is a hard deny.
 *   - District identity is `hd`, not the email domain.
 *   - Google `sub` is the person key; email is only for the allowlist.
 *
 * Keep this module free of Auth.js / Next so the rule can be unit-tested
 * without spinning up a session.
 */

export type DenyReason = "unverified" | "no-email" | "no-hd";

export type SignInInput = {
  email: string | null | undefined;
  emailVerified: boolean | undefined;
  /** Google Workspace hosted domain. Absent on personal Gmail. */
  hd: string | null | undefined;
  operatorEmails: readonly string[];
};

export type SignInOk = {
  ok: true;
  isAdmin: boolean;
  isOperator: boolean;
  /** District identity — the `hd`. Null for Operator-only (no Admin hat). */
  districtId: string | null;
};

export type SignInDenied = {
  ok: false;
  reason: DenyReason;
};

export type SignInDecision = SignInOk | SignInDenied;

/** Normalize so "Mbufkin@DallasISD.org" matches the locked allowlist. */
export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function parseOperatorEmails(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => normalizeEmail(part))
    .filter(Boolean);
}

export function isOperatorEmail(
  email: string | null | undefined,
  operatorEmails: readonly string[],
): boolean {
  if (!email) return false;
  const needle = normalizeEmail(email);
  return operatorEmails.some((allowed) => normalizeEmail(allowed) === needle);
}

/**
 * Decide whether this Google profile may enter, and which hats they wear.
 *
 * Fail closed: an empty Operator list means nobody is Operator. A missing
 * `hd` is not an Admin, even if the email looks like a school domain.
 */
export function decideSignIn(input: SignInInput): SignInDecision {
  const email = input.email?.trim();
  if (!email) {
    return { ok: false, reason: "no-email" };
  }
  if (!input.emailVerified) {
    return { ok: false, reason: "unverified" };
  }

  const isOperator = isOperatorEmail(email, input.operatorEmails);
  const hd = input.hd?.trim().toLowerCase() || null;
  const isAdmin = Boolean(hd);

  if (!isOperator && !isAdmin) {
    return { ok: false, reason: "no-hd" };
  }

  return {
    ok: true,
    isAdmin,
    isOperator,
    districtId: hd,
  };
}

/** After a successful sign-in, send them through the correct door. */
export function afterAuthPath(hats: {
  isAdmin: boolean;
  isOperator: boolean;
}): "/workspace" | "/operator" | "/hats" {
  if (hats.isAdmin && hats.isOperator) return "/hats";
  if (hats.isOperator) return "/operator";
  return "/workspace";
}
