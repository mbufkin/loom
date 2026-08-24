/**
 * Minimal ZIP reader for Office files (pptx is a ZIP of XML).
 *
 * Why this exists: Vercel will not accept a 50–234 MB Function body, so
 * paste cannot send a raw iCEV deck to the server to convert. The
 * browser already has the bytes. We only need slide XML, which is
 * stored with DEFLATE (method 8) or STORE (method 0).
 *
 * Not a general unzipper: no ZIP64, no encryption, no disk spans.
 * Those do not show up in curriculum .pptx files.
 */

const SIG_EOCD = 0x06054b50;
const SIG_CENTRAL = 0x02014b50;
const METHOD_STORE = 0;
const METHOD_DEFLATE = 8;

function u16(view: DataView, offset: number): number {
  return view.getUint16(offset, true);
}

function u32(view: DataView, offset: number): number {
  return view.getUint32(offset, true);
}

function decoder(flag: number): TextDecoder {
  // Bit 11 = UTF-8 names. Office uses ASCII paths; UTF-8 is the safe default.
  return new TextDecoder(flag & 0x0800 ? "utf-8" : "utf-8");
}

/** Find the End of Central Directory by scanning backward from EOF. */
function eocdOffset(view: DataView): number {
  const end = view.byteLength;
  const min = Math.max(0, end - 22 - 0xffff);
  for (let i = end - 22; i >= min; i--) {
    if (u32(view, i) === SIG_EOCD) return i;
  }
  throw new Error("Not a ZIP file (missing end-of-central-directory)");
}

async function inflateRaw(bytes: Uint8Array): Promise<Uint8Array> {
  // DecompressionStream is in browsers and Node 20+. Office uses raw DEFLATE
  // (no zlib header) — that is "deflate-raw".
  const stream = new Blob([bytes.slice()]).stream().pipeThrough(
    new DecompressionStream("deflate-raw"),
  );
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

export type ZipEntry = {
  name: string;
  bytes: Uint8Array;
};

/**
 * Read every file entry. Directories are skipped.
 * Best practice: always size from the central directory, not the local
 * header — bit 3 (data descriptor) leaves local sizes at zero.
 */
export async function readZipEntries(buffer: ArrayBuffer): Promise<ZipEntry[]> {
  const view = new DataView(buffer);
  const eocd = eocdOffset(view);
  const count = u16(view, eocd + 10);
  const cdSize = u32(view, eocd + 12);
  const cdOffset = u32(view, eocd + 16);
  if (cdOffset === 0xffffffff || cdSize === 0xffffffff) {
    throw new Error("ZIP64 is not supported");
  }

  const entries: ZipEntry[] = [];
  let cursor = cdOffset;
  const cdEnd = cdOffset + cdSize;
  const names = decoder(0);

  for (let i = 0; i < count && cursor + 46 <= cdEnd; i++) {
    if (u32(view, cursor) !== SIG_CENTRAL) {
      throw new Error("Corrupt ZIP (central directory)");
    }
    const flag = u16(view, cursor + 8);
    const method = u16(view, cursor + 10);
    const compressed = u32(view, cursor + 20);
    const uncompressed = u32(view, cursor + 24);
    const nameLen = u16(view, cursor + 28);
    const extraLen = u16(view, cursor + 30);
    const commentLen = u16(view, cursor + 32);
    const localOffset = u32(view, cursor + 42);
    const nameBytes = new Uint8Array(buffer, cursor + 46, nameLen);
    const name = names.decode(nameBytes);
    cursor += 46 + nameLen + extraLen + commentLen;

    if (name.endsWith("/")) continue;
    if (flag & 0x0001) {
      throw new Error(`Encrypted ZIP entry: ${name}`);
    }
    if (compressed === 0xffffffff || uncompressed === 0xffffffff) {
      throw new Error("ZIP64 is not supported");
    }

    // Local header is 30 bytes + name + extra, then the payload.
    const localNameLen = u16(view, localOffset + 26);
    const localExtraLen = u16(view, localOffset + 28);
    const dataOffset = localOffset + 30 + localNameLen + localExtraLen;
    const payload = new Uint8Array(buffer, dataOffset, compressed);

    let bytes: Uint8Array;
    if (method === METHOD_STORE) {
      bytes = payload.slice();
    } else if (method === METHOD_DEFLATE) {
      bytes = await inflateRaw(payload);
    } else {
      throw new Error(`Unsupported ZIP method ${method} in ${name}`);
    }
    entries.push({ name, bytes });
  }
  return entries;
}
