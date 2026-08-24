import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  defaultSelectedRun,
  isPacketFilePath,
  isPacketId,
  normalizePacketName,
  packetListStatus,
  packetListStatusLabel,
  sanitizeFilename,
} from "./packets";

describe("normalizePacketName", () => {
  it("requires a non-empty label and collapses space", () => {
    assert.equal(normalizePacketName("  Ag   Mechanics  "), "Ag Mechanics");
    assert.equal(normalizePacketName("   "), null);
    assert.equal(normalizePacketName("x".repeat(81)), null);
  });
});

describe("packetListStatus", () => {
  it("lets in-flight win over plates so a retry does not look done", () => {
    assert.equal(
      packetListStatus([
        { id: "a", status: "succeeded", startedAt: "2026-01-01" },
        { id: "b", status: "in_flight", startedAt: "2026-06-01" },
      ]),
      "in_flight",
    );
  });

  it("is has plates when any Run succeeded and none are in flight", () => {
    assert.equal(
      packetListStatus([
        { id: "a", status: "succeeded", startedAt: "2026-01-01" },
        { id: "b", status: "failed", startedAt: "2026-02-01" },
      ]),
      "has_plates",
    );
  });

  it("is failed with no plates only when every start died", () => {
    assert.equal(
      packetListStatus([
        { id: "a", status: "failed", startedAt: "2026-01-01" },
      ]),
      "failed_no_plates",
    );
  });

  it("is no Run yet when the Packet was only pasted", () => {
    assert.equal(packetListStatus([]), "no_run");
    assert.equal(packetListStatusLabel("no_run"), "No Run yet");
  });
});

describe("defaultSelectedRun", () => {
  it("selects the latest successful Run, not a failed retry", () => {
    const selected = defaultSelectedRun([
      { id: "old", status: "succeeded", startedAt: "2026-01-01T00:00:00Z" },
      { id: "new", status: "failed", startedAt: "2026-06-01T00:00:00Z" },
    ]);
    assert.equal(selected?.id, "old");
  });
});

describe("path guards", () => {
  it("rejects traversal in filenames", () => {
    assert.equal(sanitizeFilename("../secret.pdf"), "secret.pdf");
    assert.equal(sanitizeFilename(".."), null);
    assert.equal(sanitizeFilename("a/b.pdf"), "b.pdf");
  });

  it("keeps file pathnames inside this Packet", () => {
    assert.equal(
      isPacketFilePath(
        "dallasisd.org",
        "11111111-1111-4111-8111-111111111111",
        "d/dallasisd.org/packets/11111111-1111-4111-8111-111111111111/files/a.pdf",
      ),
      true,
    );
    assert.equal(
      isPacketFilePath(
        "dallasisd.org",
        "11111111-1111-4111-8111-111111111111",
        "d/other.org/packets/11111111-1111-4111-8111-111111111111/files/a.pdf",
      ),
      false,
    );
  });

  it("accepts a UUID Packet id", () => {
    assert.equal(isPacketId("11111111-1111-4111-8111-111111111111"), true);
    assert.equal(isPacketId("not-a-uuid"), false);
  });
});
