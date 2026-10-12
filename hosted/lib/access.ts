/**
 * Sign-in gate for Hosted Loom.
 *
 * Google proves account + optional Workspace `hd`. It does not prove “school”
 * or staff. We enforce the product rule here:
 *   - Operator allowlist skips `hd` (Gmail is fine for Operator only).
 *   - Admin requires a present `hd` AND an invite (`ADMIN_EMAILS`).
 *     `hd` alone would let any student or vendor on that domain paste
 *     district documents, so the invite is the real gate; `hd` still names
 *     the District. Personal Gmail is a hard deny.
 *   - District identity is `hd`, not the email domain.
 *   - Google `sub` is the person key; email is only for the allowlist.
 *
 * Keep this module free of Auth.js / Next so the rule can be unit-tested
 * without spinning up a session.
 */

export type DenyReason = "unverified" | "no-email" | "no-hd" | "not-invited";

export type SignInInput = {
  email: string | null | undefined;
  emailVerified: boolean | undefined;
  /** Google Workspace hosted domain. Absent on personal Gmail. */
  hd: string | null | undefined;
  operatorEmails: readonly string[];
  /** Invited Admin emails. Empty = nobody wears the Admin hat. */
  adminEmails: readonly string[];
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

/** Parse a comma-separated env allowlist. Missing/blank = empty (fail closed). */
export function parseEmailList(raw: string | undefined): string[] {
  if (!raw) return [];
  return raw
    .split(",")
    .map((part) => normalizeEmail(part))
    .filter(Boolean);
}

/** Kept for existing callers; same parsing as every other allowlist. */
export const parseOperatorEmails = parseEmailList;

export function isListedEmail(
  email: string | null | undefined,
  allowlist: readonly string[],
): boolean {
  if (!email) return false;
  const needle = normalizeEmail(email);
  return allowlist.some((allowed) => normalizeEmail(allowed) === needle);
}

export const isOperatorEmail = isListedEmail;

/**
 * Decide whether this Google profile may enter, and which hats they wear.
 *
 * Fail closed: an empty Operator list means nobody is Operator, and an empty
 * Admin list means nobody is Admin. A missing `hd` is not an Admin, even if
 * the email is invited — the District identity has to come from Google.
 */
export function decideSignIn(input: SignInInput): SignInDecision {
  const email = input.email?.trim();
  if (!email) {
    return { ok: false, reason: "no-email" };
  }
  if (!input.emailVerified) {
    return { ok: false, reason: "unverified" };
  }

  const isOperator = isListedEmail(email, input.operatorEmails);
  const hd = input.hd?.trim().toLowerCase() || null;
  const isInvited = isListedEmail(email, input.adminEmails);
  const isAdmin = Boolean(hd) && isInvited;

  if (!isOperator && !isAdmin) {
    // Check `hd` first so personal Gmail keeps its clearer reason.
    return { ok: false, reason: hd ? "not-invited" : "no-hd" };
  }

  return {
    ok: true,
    isAdmin,
    isOperator,
    // An Operator without the Admin hat has no District, even with `hd`.
    districtId: isAdmin ? hd : null,
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
