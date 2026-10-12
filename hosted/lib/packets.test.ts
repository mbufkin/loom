import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  RUN_STALE_AFTER_MS,
  defaultSelectedRun,
  isPacketFilePath,
  isPacketId,
  isRunStalled,
  normalizePacketName,
  orderedPlates,
  packetListStatus,
  packetListStatusLabel,
  parseRunRecord,
  runDisplayStatus,
  runIsoNow,
  sanitizeFilename,
  type PacketRun,
  type RunStatus,
} from "./packets";

describe("normalizePacketName", () => {
  it("requires a non-empty label and collapses space", () => {
    assert.equal(normalizePacketName("  Ag   Mechanics  "), "Ag Mechanics");
    assert.equal(normalizePacketName("   "), null);
    assert.equal(normalizePacketName("x".repeat(81)), null);
  });
});

const D = "dallasisd.org";
const P = "11111111-1111-4111-8111-111111111111";
const NOW = Date.parse("2026-10-12T16:00:00Z");

function run(
  id: string,
  status: RunStatus,
  queuedAt: string,
  extra: Partial<PacketRun> = {},
): PacketRun {
  return {
    schema: 1,
    id,
    districtId: D,
    packetId: P,
    status,
    queuedAt,
    attempt: 0,
    ...extra,
  };
}

describe("packetListStatus", () => {
  it("lets in progress win over plates so a retry does not look done", () => {
    for (const status of ["queued", "running"] as const) {
      assert.equal(
        packetListStatus(
          [
            run("a", "succeeded", "2026-01-01T00:00:00Z"),
            run("b", status, "2026-10-12T15:55:00Z", {
              heartbeatAt: "2026-10-12T15:59:00Z",
            }),
          ],
          NOW,
        ),
        "in_progress",
      );
    }
  });

  it("is stalled when the only running Run has an old heartbeat", () => {
    assert.equal(
      packetListStatus(
        [run("a", "running", "2026-10-12T10:00:00Z", { heartbeatAt: "2026-10-12T15:30:00Z" })],
        NOW,
      ),
      "stalled",
    );
    assert.equal(packetListStatusLabel("stalled"), "Stalled");
  });

  it("is has plates when any Run succeeded and none are in progress", () => {
    assert.equal(
      packetListStatus([
        run("a", "succeeded", "2026-01-01T00:00:00Z"),
        run("b", "failed", "2026-02-01T00:00:00Z"),
      ]),
      "has_plates",
    );
  });

  it("is failed with no plates only when every start died", () => {
    assert.equal(
      packetListStatus([
        run("a", "failed", "2026-01-01T00:00:00Z"),
        run("b", "interrupted", "2026-01-02T00:00:00Z"),
      ]),
      "failed_no_plates",
    );
  });

  it("is no Run yet when the Packet was only pasted", () => {
    assert.equal(packetListStatus([]), "no_run");
    assert.equal(packetListStatusLabel("no_run"), "No Run yet");
  });
});

describe("stalled detection", () => {
  it("uses the 15-minute contract window", () => {
    assert.equal(RUN_STALE_AFTER_MS, 15 * 60 * 1000);
    const fresh = run("a", "running", "2026-10-12T15:00:00Z", {
      heartbeatAt: new Date(NOW - RUN_STALE_AFTER_MS).toISOString(),
    });
    const old = run("b", "running", "2026-10-12T15:00:00Z", {
      heartbeatAt: new Date(NOW - RUN_STALE_AFTER_MS - 1000).toISOString(),
    });
    assert.equal(isRunStalled(fresh, NOW), false);
    assert.equal(isRunStalled(old, NOW), true);
    assert.equal(runDisplayStatus(old, NOW), "stalled");
  });

  it("falls back to claimedAt, and treats no timestamp as stalled", () => {
    assert.equal(
      isRunStalled(run("a", "running", "2026-10-12T15:00:00Z", { claimedAt: "2026-10-12T15:58:00Z" }), NOW),
      false,
    );
    assert.equal(isRunStalled(run("b", "running", "2026-10-12T15:00:00Z"), NOW), true);
  });

  it("never marks a queued or finished Run stalled", () => {
    assert.equal(isRunStalled(run("a", "queued", "2026-01-01T00:00:00Z"), NOW), false);
    assert.equal(runDisplayStatus(run("b", "succeeded", "2026-01-01T00:00:00Z"), NOW), "succeeded");
  });
});

describe("defaultSelectedRun", () => {
  it("selects the latest successful Run by finishedAt, not a failed retry", () => {
    const selected = defaultSelectedRun([
      run("old-ok", "succeeded", "2026-01-01T00:00:00Z", { finishedAt: "2026-01-01T04:00:00Z" }),
      // Queued earlier but finished later: finishedAt decides.
      run("new-ok", "succeeded", "2025-12-31T00:00:00Z", { finishedAt: "2026-01-02T04:00:00Z" }),
      run("retry", "failed", "2026-06-01T00:00:00Z", { finishedAt: "2026-06-01T01:00:00Z" }),
    ]);
    assert.equal(selected?.id, "new-ok");
  });

  it("falls back to the newest Run by queuedAt when none succeeded", () => {
    const selected = defaultSelectedRun([
      run("a", "failed", "2026-01-01T00:00:00Z"),
      run("b", "queued", "2026-02-01T00:00:00Z"),
    ]);
    assert.equal(selected?.id, "b");
    assert.equal(defaultSelectedRun([]), null);
  });
});

describe("parseRunRecord", () => {
  const R = "22222222-2222-4222-8222-222222222222";
  const key = `d/${D}/packets/${P}/runs/${R}/run.json`;
  const plateKey = `d/${D}/packets/${P}/runs/${R}/plates/FIRST-PASS.md`;

  it("accepts a Worker-finished record and keeps in-Run plates only", () => {
    const parsed = parseRunRecord(key, {
      schema: 1,
      id: R,
      districtId: D,
      packetId: P,
      status: "succeeded",
      queuedAt: "2026-10-12T10:00:00Z",
      attempt: 1,
      finishedAt: "2026-10-12T14:00:00Z",
      plates: [
        { name: "FIRST-PASS.md", key: plateKey, size: 10 },
        { name: "evil.md", key: `d/${D}/packets/other/files/x.pdf`, size: 1 },
      ],
    });
    assert.equal(parsed?.status, "succeeded");
    assert.deepEqual(parsed?.plates?.map((p) => p.name), ["FIRST-PASS.md"]);
  });

  it("drops records that disagree with their key or the status set", () => {
    const base = { id: R, districtId: D, packetId: P, status: "queued", queuedAt: "2026-10-12T10:00:00Z" };
    assert.ok(parseRunRecord(key, base));
    assert.equal(parseRunRecord(key, { ...base, status: "in_flight" }), null);
    assert.equal(parseRunRecord(key, { ...base, districtId: "other.org" }), null);
    assert.equal(parseRunRecord(key, { ...base, queuedAt: "soon" }), null);
    assert.equal(parseRunRecord(`d/${D}/packets/${P}/meta.json`, base), null);
    assert.equal(parseRunRecord(key, null), null);
  });

  it("orders plates with FIRST-PASS first", () => {
    const names = orderedPlates([
      { name: "USAGE-SUMMARY.json", key: "k1", size: 1 },
      { name: "FIRST-PASS.md", key: "k2", size: 1 },
      { name: "SUMMARY.md", key: "k3", size: 1 },
    ]).map((p) => p.name);
    assert.deepEqual(names, ["FIRST-PASS.md", "SUMMARY.md", "USAGE-SUMMARY.json"]);
  });

  it("formats times like hosted_runs.now_iso", () => {
    assert.equal(runIsoNow(Date.parse("2026-10-12T16:08:09.123Z")), "2026-10-12T16:08:09Z");
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
