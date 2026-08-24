/**
 * Bargain gate — product rule, not legal text.
 *
 * Each Admin accepts once, for themselves, before they may paste or start
 * a Run. Seeing the Workspace does not require accept. The founder does
 * not bind later Admins. Withdrawal is forward-only (we do not delete
 * an accept record to “take back” already-pasted Packets).
 */

export type BargainRecord = {
  acceptedAt: string;
  /** Person key. Email is only for the Operator allowlist. */
  googleSub: string;
};

export function canPasteOrStart(accepted: boolean): boolean {
  return accepted;
}

/** The sentence Admins accept. Keep this aligned with CONTEXT.md. */
export const BARGAIN_SENTENCE =
  "A free Run means the Operator may open this District’s Packets, plates, and usage. We do not use Packets to improve Loom. Other Admins on your hosted domain share this Workspace, including students.";
