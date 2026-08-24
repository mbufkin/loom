import assert from "node:assert/strict";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { describe, it } from "node:test";
import { preparePacketFile, PPTX_LOCAL_MAX_BYTES } from "./prepare-packet-file";
import { MAX_FILE_BYTES, SERVER_PUT_MAX_BYTES } from "./packets";
import {
  extractPptxText,
  isLegacyPptFilename,
  pptxTextFilename,
  textRunsFromSlideXml,
} from "./pptx-text";
import { readZipEntries } from "./zip-deflate";

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.byteLength, 0);
  const out = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    out.set(part, offset);
    offset += part.byteLength;
  }
  return out;
}

function u16(value: number): Uint8Array {
  const buf = new Uint8Array(2);
  new DataView(buf.buffer).setUint16(0, value, true);
  return buf;
}

function u32(value: number): Uint8Array {
  const buf = new Uint8Array(4);
  new DataView(buf.buffer).setUint32(0, value, true);
  return buf;
}

async function deflateRaw(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([bytes.slice()])
    .stream()
    .pipeThrough(new CompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** Build a DEFLATE ZIP so the test walks the same path a real .pptx does. */
async function zipDeflate(
  files: Record<string, string>,
): Promise<ArrayBuffer> {
  const locals: Uint8Array[] = [];
  const centrals: Uint8Array[] = [];
  let offset = 0;
  const enc = new TextEncoder();

  for (const [name, text] of Object.entries(files)) {
    const raw = enc.encode(text);
    const compressed = await deflateRaw(raw);
    const nameBytes = enc.encode(name);
    const local = concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(8),
      u16(0),
      u16(0),
      u32(0),
      u32(compressed.byteLength),
      u32(raw.byteLength),
      u16(nameBytes.byteLength),
      u16(0),
      nameBytes,
      compressed,
    ]);
    locals.push(local);
    centrals.push(
      concat([
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(8),
        u16(0),
        u16(0),
        u32(0),
        u32(compressed.byteLength),
        u32(raw.byteLength),
        u16(nameBytes.byteLength),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(offset),
        nameBytes,
      ]),
    );
    offset += local.byteLength;
  }

  const central = concat(centrals);
  const eocd = concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(Object.keys(files).length),
    u16(Object.keys(files).length),
    u32(central.byteLength),
    u32(offset),
    u16(0),
  ]);
  const packed = concat([...locals, central, eocd]);
  return packed.slice().buffer;
}

function slideXml(text: string): string {
  const safe = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return (
    '<?xml version="1.0"?>' +
    '<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" ' +
    'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">' +
    `<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r><a:t>${safe}</a:t></a:r></a:p>` +
    "</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
  );
}

describe("textRunsFromSlideXml", () => {
  it("joins a:t runs and decodes entities", () => {
    const xml =
      '<p><a:t>Breeds of &amp; Livestock</a:t><a:t>Cattle</a:t></p>';
    assert.equal(textRunsFromSlideXml(xml), "Breeds of & Livestock\nCattle");
  });
});

describe("readZipEntries + extractPptxText", () => {
  it("reads slides in numeric order, not string order", async () => {
    // String sort would put slide10 before slide2 — that is a real Office trap.
    const buffer = await zipDeflate({
      "ppt/slides/slide10.xml": slideXml("TEN"),
      "ppt/slides/slide2.xml": slideXml("TWO"),
      "ppt/slides/slide1.xml": slideXml("ONE"),
      "ppt/slides/_rels/slide1.xml.rels": "<Relationships/>",
    });
    const names = (await readZipEntries(buffer)).map((e) => e.name);
    assert.ok(names.includes("ppt/slides/slide10.xml"));
    const text = await extractPptxText(buffer);
    assert.equal(text, "ONE\n\nTWO\n\nTEN");
  });

  it("refuses a ZIP that is not a presentation", async () => {
    const buffer = await zipDeflate({ "readme.txt": "no slides" });
    await assert.rejects(() => extractPptxText(buffer), /no slides/);
  });
});

describe("pptx naming", () => {
  it("keeps .pptx in the stored name so a handout.txt can coexist", () => {
    assert.equal(
      pptxTextFilename("PowerPoint-DownloadableVersion.pptx"),
      "PowerPoint-DownloadableVersion.pptx.txt",
    );
    assert.equal(isLegacyPptFilename("deck.ppt"), true);
    assert.equal(isLegacyPptFilename("deck.pptx"), false);
  });
});

describe("preparePacketFile", () => {
  it("turns a .pptx into a text file under the 4 MB same-origin cap", async () => {
    const buffer = await zipDeflate({
      "ppt/slides/slide1.xml": slideXml("Lab safety"),
    });
    const pptx = new File([buffer], "Lab Safety.pptx", {
      type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    });
    const prepared = await preparePacketFile(pptx);
    assert.equal(prepared.convertedFrom, "Lab Safety.pptx");
    assert.equal(prepared.file.name, "Lab Safety.pptx.txt");
    assert.equal(prepared.file.type, "text/plain;charset=utf-8");
    assert.ok(prepared.file.size < SERVER_PUT_MAX_BYTES);
    assert.equal(await prepared.file.text(), "Lab safety");
  });

  it("leaves a PDF alone and still enforces the 25 MB Packet cap", async () => {
    const pdf = new File([new Uint8Array(16)], "handout.pdf", {
      type: "application/pdf",
    });
    const prepared = await preparePacketFile(pdf);
    assert.equal(prepared.file, pdf);
    assert.equal(prepared.convertedFrom, undefined);

    const huge = new File([new Uint8Array(MAX_FILE_BYTES + 1)], "scan.pdf");
    await assert.rejects(() => preparePacketFile(huge), /25 MB/);
  });

  it("refuses legacy .ppt", async () => {
    const ppt = new File([new Uint8Array(32)], "old.ppt");
    await assert.rejects(() => preparePacketFile(ppt), /old PowerPoint/);
  });
});

describe("iCEV reference (local pull only)", () => {
  it("cattle-breeds deck text is under 4 MB when the pull exists", async () => {
    const path =
      "/Users/michaelbufkin/firstmate/data/curriculum-sources/icev-pull/" +
      "advanced-animal-science/lessons/023-breeds-of-livestock-cattle/" +
      "PowerPoint-DownloadableVersion.pptx";
    if (!existsSync(path)) {
      return;
    }
    const buffer = await readFile(path);
    const text = await extractPptxText(buffer.buffer.slice(
      buffer.byteOffset,
      buffer.byteOffset + buffer.byteLength,
    ));
    const bytes = new TextEncoder().encode(text).byteLength;
    assert.ok(bytes < SERVER_PUT_MAX_BYTES, `text was ${bytes} bytes`);
    assert.ok(bytes > 1000, "expected real slide copy, not an empty extract");
    assert.ok(PPTX_LOCAL_MAX_BYTES > buffer.byteLength);
  });
});
