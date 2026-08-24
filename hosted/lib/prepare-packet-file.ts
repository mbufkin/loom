/**
 * What actually goes in the Packet store.
 *
 * PDFs and small docs upload as-is. A .pptx is read on this computer and
 * replaced with slide text — pictures never leave the tab, so a 234 MB
 * iCEV deck does not have to fit Vercel’s 4.5 MB Function body or the
 * 25 MB Packet file cap.
 */
import {
  MAX_FILE_BYTES,
  SERVER_PUT_MAX_BYTES,
  sanitizeFilename,
} from "./packets";
import {
  extractPptxText,
  isLegacyPptFilename,
  isPptxFilename,
  pptxTextFilename,
} from "./pptx-text";

/** Browser-only. The cattle-breeds iCEV deck is 234 MB; 300 MB covers it. */
export const PPTX_LOCAL_MAX_BYTES = 300 * 1024 * 1024;

export type PreparedPacketFile = {
  file: File;
  convertedFrom?: string;
};

export async function preparePacketFile(
  file: File,
): Promise<PreparedPacketFile> {
  if (isLegacyPptFilename(file.name)) {
    throw new Error(
      `“${file.name}” is an old PowerPoint. Save it as .pptx, then paste.`,
    );
  }
  if (!isPptxFilename(file.name)) {
    if (file.size > MAX_FILE_BYTES) {
      throw new Error("Each file must be 25 MB or smaller.");
    }
    return { file };
  }
  if (file.size > PPTX_LOCAL_MAX_BYTES) {
    throw new Error(
      `“${file.name}” is too large to read in the browser (over 300 MB).`,
    );
  }

  const text = await extractPptxText(await file.arrayBuffer());
  if (!text.trim()) {
    throw new Error(`“${file.name}” has no slide text to paste.`);
  }

  const name = sanitizeFilename(pptxTextFilename(file.name));
  if (!name) {
    throw new Error(`Cannot paste “${file.name}”.`);
  }
  const out = new File([text], name, { type: "text/plain;charset=utf-8" });
  // Converted text must still fit the same-origin PUT (4 MB). iCEV decks
  // measured at 4–29 KB; if one ever exceeds this, CORS + presign is
  // the fallback — do not silently truncate.
  if (out.size > SERVER_PUT_MAX_BYTES) {
    throw new Error(`Slide text from “${file.name}” is over 4 MB.`);
  }
  return { file: out, convertedFrom: file.name };
}
