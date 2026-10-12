import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  SECRET_HEADER,
  forwardLoom,
  isBlocked,
  upstreamUrl,
  type Access,
  type ProxyDeps,
} from "./loom-proxy";

const ENV = { LOOM_API_URL: "https://pi.example.test/", LOOM_PROXY_SECRET: "s3cret-test" };

type Seen = { url: string; init: RequestInit };

/** A fake Pi that records what it was sent and answers with `reply`. */
function fakePi(reply: () => Response) {
  const seen: Seen[] = [];
  const fetchImpl = (async (url: string | URL | Request, init?: RequestInit) => {
    seen.push({ url: String(url), init: init ?? {} });
    return reply();
  }) as typeof fetch;
  return { seen, fetchImpl };
}

function deps(access: Access, fetchImpl: typeof fetch, env = ENV): ProxyDeps {
  return { access: async () => access, fetchImpl, env, log: () => {} };
}

const ok = () =>
  new Response(JSON.stringify({ bundle: null }), {
    status: 200,
    headers: {
      "content-type": "application/json",
      "access-control-allow-origin": "*",
      server: "LoomReview/1.0",
    },
  });

describe("upstreamUrl", () => {
  it("maps /api/loom/<rest> to /api/<rest> and keeps the query", () => {
    assert.equal(
      upstreamUrl("https://pi.example.test/", ["projects", "x", "file"], "?path=a%2Fb.md"),
      "https://pi.example.test/api/projects/x/file?path=a%2Fb.md",
    );
  });

  it("refuses dot segments and smuggled slashes", () => {
    assert.equal(upstreamUrl("https://p", ["..", "secrets"], ""), null);
    assert.equal(upstreamUrl("https://p", ["projects", "a/../../x"], ""), null);
    assert.equal(upstreamUrl("https://p", [], ""), null);
  });
});

describe("isBlocked", () => {
  it("blocks desktop-only routes", () => {
    assert.ok(isBlocked(["install-deps"]));
    assert.ok(isBlocked(["models", "select"]));
    assert.ok(isBlocked(["models", "key"]));
    assert.ok(!isBlocked(["projects"]));
    assert.ok(!isBlocked(["modelsets"]));
  });
});

describe("forwardLoom", () => {
  it("401 when signed out, without calling the Pi", async () => {
    const pi = fakePi(ok);
    const res = await forwardLoom(
      new Request("https://site/api/loom/version"),
      ["version"],
      deps("signed-out", pi.fetchImpl),
    );
    assert.equal(res.status, 401);
    assert.equal(pi.seen.length, 0);
  });

  it("403 when signed in but not an invited Admin", async () => {
    const pi = fakePi(ok);
    const res = await forwardLoom(
      new Request("https://site/api/loom/projects"),
      ["projects"],
      deps("forbidden", pi.fetchImpl),
    );
    assert.equal(res.status, 403);
    assert.equal(pi.seen.length, 0);
  });

  it("403 on blocked routes even for an Admin", async () => {
    const pi = fakePi(ok);
    const res = await forwardLoom(
      new Request("https://site/api/loom/models/select", { method: "POST", body: "{}" }),
      ["models", "select"],
      deps("ok", pi.fetchImpl),
    );
    assert.equal(res.status, 403);
    assert.equal(pi.seen.length, 0);
  });

  it("503 when the Pi is not configured", async () => {
    const pi = fakePi(ok);
    const res = await forwardLoom(
      new Request("https://site/api/loom/version"),
      ["version"],
      deps("ok", pi.fetchImpl, { LOOM_API_URL: "", LOOM_PROXY_SECRET: "" }),
    );
    assert.equal(res.status, 503);
  });

  it("forwards GET with the secret and strips cookies and CORS", async () => {
    const pi = fakePi(ok);
    const res = await forwardLoom(
      new Request("https://site/api/loom/version", {
        headers: { cookie: "authjs.session-token=abc", accept: "application/json" },
      }),
      ["version"],
      deps("ok", pi.fetchImpl),
    );
    assert.equal(res.status, 200);
    assert.deepEqual(await res.json(), { bundle: null });
    assert.equal(res.headers.get("access-control-allow-origin"), null);
    assert.equal(res.headers.get("server"), null);
    assert.equal(res.headers.get("cache-control"), "no-store");

    const sent = new Headers(pi.seen[0]!.init.headers);
    assert.equal(pi.seen[0]!.url, "https://pi.example.test/api/version");
    assert.equal(sent.get(SECRET_HEADER), "s3cret-test");
    assert.equal(sent.get("cookie"), null);
  });

  it("forwards an upload as a buffered body with its query string", async () => {
    const pi = fakePi(() => new Response('{"ok":true}', { status: 201 }));
    const bytes = new TextEncoder().encode("unit 1 lesson plan");
    const res = await forwardLoom(
      new Request("https://site/api/loom/projects/demo/documents?name=a%20b.txt", {
        method: "POST",
        headers: { "content-type": "application/octet-stream" },
        body: bytes,
      }),
      ["projects", "demo", "documents"],
      deps("ok", pi.fetchImpl),
    );
    assert.equal(res.status, 201);
    const call = pi.seen[0]!;
    assert.equal(call.url, "https://pi.example.test/api/projects/demo/documents?name=a%20b.txt");
    assert.equal(call.init.method, "POST");
    assert.equal((call.init.body as ArrayBuffer).byteLength, bytes.byteLength);
  });

  it("passes the Pi's own errors through", async () => {
    const pi = fakePi(() => new Response('{"error":"There is already a curriculum called x"}', { status: 409 }));
    const res = await forwardLoom(
      new Request("https://site/api/loom/projects", { method: "POST", body: "{}" }),
      ["projects"],
      deps("ok", pi.fetchImpl),
    );
    assert.equal(res.status, 409);
  });

  it("502 when the Pi is unreachable", async () => {
    const fetchImpl = (async () => {
      throw new TypeError("fetch failed");
    }) as typeof fetch;
    const res = await forwardLoom(
      new Request("https://site/api/loom/projects"),
      ["projects"],
      deps("ok", fetchImpl),
    );
    assert.equal(res.status, 502);
  });

  it("405 for methods the API does not use", async () => {
    const pi = fakePi(ok);
    const res = await forwardLoom(
      new Request("https://site/api/loom/projects", { method: "DELETE" }),
      ["projects"],
      deps("ok", pi.fetchImpl),
    );
    assert.equal(res.status, 405);
  });
});
