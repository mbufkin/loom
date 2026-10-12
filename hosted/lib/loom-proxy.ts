/**
 * Forwarder from the signed-in site to the Loom app server on the Pi.
 *
 *   browser ──/api/loom/<rest>──▶ Vercel (session check) ──/api/<rest>──▶ Pi
 *                                         + X-Loom-Proxy-Secret
 *
 * The Pi server trusts whoever holds the shared secret, so this hop is the
 * real access control: no invited-Admin session, no request. The secret and
 * the Pi's address live only in Vercel env (LOOM_PROXY_SECRET, LOOM_API_URL)
 * and never reach the browser.
 *
 * Kept free of Next/Auth.js imports (session lookup and fetch are injected)
 * so the whole decision can be unit-tested without a server.
 *
 * Keep BLOCKED_FIRST_SEGMENTS in step with ui/hosted_guard.py on the Pi, which
 * refuses the same routes. Two layers on purpose.
 */

export const SECRET_HEADER = "X-Loom-Proxy-Secret";

/** Desktop-only routes: model choice, API keys, installing packages. */
export const BLOCKED_FIRST_SEGMENTS: ReadonlySet<string> = new Set([
  "install-deps",
  "models",
]);

/**
 * Vercel refuses request bodies over ~4.5 MB before our code runs; this is
 * the same ceiling stated in our own words for anything that slips past.
 */
export const MAX_BODY_BYTES = 4_400_000;

/** Long work (organise, audits) is async on the Pi; requests should be short. */
export const UPSTREAM_TIMEOUT_MS = 50_000;

export type Access = "ok" | "signed-out" | "forbidden";

export type ProxyDeps = {
  /** Session check. "forbidden" = signed in but not an invited Admin. */
  access: () => Promise<Access>;
  fetchImpl?: typeof fetch;
  env?: { LOOM_API_URL?: string; LOOM_PROXY_SECRET?: string };
  log?: (msg: string) => void;
};

/** Request headers worth passing on. Cookies and auth headers never leave Vercel. */
const FORWARD_REQUEST_HEADERS = ["content-type", "accept"];

/** Response headers worth passing back. CORS and server banners are dropped. */
const FORWARD_RESPONSE_HEADERS = [
  "content-type",
  "content-length",
  "content-disposition",
  "last-modified",
  "etag",
];

function json(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store" },
  });
}

/** True when the first path segment names a desktop-only route. */
export function isBlocked(segments: readonly string[]): boolean {
  const first = segments.find((s) => s !== "");
  return first !== undefined && BLOCKED_FIRST_SEGMENTS.has(first);
}

/**
 * Build the upstream URL, or null for a path we refuse to forward.
 *
 * Next hands us *decoded* segments, so "..%2F" arrives as "../". Rejecting dot
 * segments and re-encoding each one keeps the request inside /api/ on the Pi.
 */
export function upstreamUrl(
  base: string,
  segments: readonly string[],
  search: string,
): string | null {
  if (segments.length === 0) return null;
  if (segments.some((s) => s === "" || s === "." || s === ".." || s.includes("/"))) {
    return null;
  }
  const root = base.replace(/\/+$/, "");
  const path = segments.map(encodeURIComponent).join("/");
  return `${root}/api/${path}${search}`;
}

/** Forward one request. Every failure is a JSON {error} the React app can show. */
export async function forwardLoom(
  req: Request,
  segments: readonly string[],
  deps: ProxyDeps,
): Promise<Response> {
  const log = deps.log ?? ((m: string) => console.error(m));
  const env = deps.env ?? process.env;

  // Session first: a stranger learns nothing about routes or configuration.
  const access = await deps.access();
  if (access === "signed-out") return json({ error: "Sign in to use Loom." }, 401);
  if (access === "forbidden") {
    return json({ error: "This account has not been invited to Loom." }, 403);
  }

  if (req.method !== "GET" && req.method !== "POST") {
    return json({ error: "method not allowed" }, 405);
  }
  if (isBlocked(segments)) {
    return json({ error: "Not available in the hosted app." }, 403);
  }

  const base = env.LOOM_API_URL?.trim();
  const secret = env.LOOM_PROXY_SECRET?.trim();
  if (!base || !secret) {
    log("[loom-proxy] LOOM_API_URL or LOOM_PROXY_SECRET is not set");
    return json({ error: "The Loom service is not configured yet." }, 503);
  }

  const target = upstreamUrl(base, segments, new URL(req.url).search);
  if (!target) return json({ error: "not found" }, 404);

  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = req.headers.get(name);
    if (value) headers.set(name, value);
  }
  headers.set(SECRET_HEADER, secret);

  // Buffered, not streamed: ui/server.py is a stdlib server that reads
  // Content-Length and does not understand chunked bodies, and Vercel caps
  // bodies at ~4.5 MB anyway, so buffering costs nothing real.
  let body: ArrayBuffer | undefined;
  if (req.method === "POST") {
    body = await req.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) {
      return json(
        { error: "That file is too large for the hosted app (about 4 MB per file)." },
        413,
      );
    }
  }

  let upstream: Response;
  try {
    upstream = await (deps.fetchImpl ?? fetch)(target, {
      method: req.method,
      headers,
      body,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (e) {
    // Log the path, never the secret or the body.
    log(`[loom-proxy] upstream failed for /${segments.join("/")}: ${String(e)}`);
    return json({ error: "The Loom service is not reachable right now." }, 502);
  }

  const out = new Headers({ "cache-control": "no-store" });
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) out.set(name, value);
  }
  // Streamed back, so a large report download is not held in memory here.
  return new Response(upstream.body, { status: upstream.status, headers: out });
}
