import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { MAX_FILE_BYTES, SERVER_PUT_MAX_BYTES, packetFilePath } from "./packets";
import { describePacketPut } from "./r2-put-grant";
import { R2_S3_CHECKSUMS } from "./r2";

const districtId = "dallasisd.org";
const packetId = "11111111-1111-4111-8111-111111111111";

describe("describePacketPut", () => {
  it("accepts a file in this District’s Packet folder", () => {
    const pathname = packetFilePath(districtId, packetId, "agenda.pdf");
    const grant = describePacketPut({
      districtId,
      pathname,
      contentType: "application/pdf",
      size: 1024,
    });
    assert.equal(grant.ok, true);
    if (grant.ok) {
      assert.equal(grant.packetId, packetId);
      assert.equal(grant.contentType, "application/pdf");
    }
  });

  it("refuses another District’s path", () => {
    const grant = describePacketPut({
      districtId,
      pathname: packetFilePath("other.org", packetId, "agenda.pdf"),
      size: 1024,
    });
    assert.deepEqual(grant, {
      ok: false,
      error: "Path is not this District’s Packet",
    });
  });

  it("refuses a file over the Packet cap", () => {
    const grant = describePacketPut({
      districtId,
      pathname: packetFilePath(districtId, packetId, "huge.bin"),
      size: MAX_FILE_BYTES + 1,
    });
    assert.deepEqual(grant, { ok: false, error: "File is too large" });
  });
});

describe("server put stays inside the Vercel body cap", () => {
  it("is 4 MB — under the 4.5 MB Function limit", () => {
    assert.equal(SERVER_PUT_MAX_BYTES, 4 * 1024 * 1024);
    assert.ok(SERVER_PUT_MAX_BYTES < 4.5 * 1024 * 1024);
  });
});

describe("R2 S3 checksums", () => {
  it("are off unless the API requires them (browser PUT / R2)", () => {
    assert.equal(R2_S3_CHECKSUMS.requestChecksumCalculation, "WHEN_REQUIRED");
    assert.equal(R2_S3_CHECKSUMS.responseChecksumValidation, "WHEN_REQUIRED");
  });
});
