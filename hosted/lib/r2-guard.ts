/**
 * R2 must never take down a signed-in page. A rejected key, a TLS
 * handshake failure, or a 403 from Cloudflare all look the same to
 * an Admin: “Application error”. Reads fall back; writes still throw
 * so paste can name the failure.
 */

export async function r2ReadFallback<T>(
  label: string,
  fallback: T,
  read: () => Promise<T>,
): Promise<T> {
  try {
    return await read();
  } catch (error) {
    const name = error instanceof Error ? error.name : "Error";
    const message = error instanceof Error ? error.message : String(error);
    // One line for Vercel logs. Do not dump keys or the full request.
    console.error(`[store] ${label} failed: ${name}: ${message}`);
    return fallback;
  }
}
