import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { r2ReadFallback } from "./r2-guard";

describe("r2ReadFallback", () => {
  it("returns the fallback when the store throws", async () => {
    const value = await r2ReadFallback("listPackets", [], async () => {
      throw Object.assign(new Error("ssl/tls alert handshake failure"), {
        name: "Error",
        code: "EPROTO",
      });
    });
    assert.deepEqual(value, []);
  });

  it("returns the successful read", async () => {
    const value = await r2ReadFallback("listPackets", [], async () => ["ok"]);
    assert.deepEqual(value, ["ok"]);
  });
});
