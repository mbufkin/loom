import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { canPasteOrStart } from "./bargain";

describe("canPasteOrStart", () => {
  it("blocks paste and Start until this Admin accepts", () => {
    assert.equal(canPasteOrStart(false), false);
  });

  it("allows paste and Start after this Admin accepts", () => {
    assert.equal(canPasteOrStart(true), true);
  });
});
