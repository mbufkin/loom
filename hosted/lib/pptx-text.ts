/**
 * Slide text from a .pptx — same idea as ../../doc_extract.py _extract_pptx.
 *
 * A PowerPoint file is a ZIP. The words live in ppt/slides/slideN.xml
 * inside <a:t> runs. Photos, video, and speaker-deck chrome stay in
 * media/ and never ship. That is why a 234 MB iCEV deck is ~17 KB of text.
 *
 * Best practice: convert in the browser, upload the .txt. Do not send the
 * deck to Vercel — the Function body cap is 4.5 MB.
 */
import { readZipEntries } from "./zip-deflate";

const SLIDE_NAME = /^ppt\/slides\/slide(\d+)\.xml$/;

/** DrawingML text runs: <a:t>, <t>, any namespace, local name "t". */
const TEXT_RUN = /<(?:[\w.-]+:)?t\b[^>]*>([\s\S]*?)<\/(?:[\w.-]+:)?t>/g;

function decodeXmlEntities(value: string): string {
  return value
    .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&apos;/g, "'")
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex: string) =>
      String.fromCodePoint(Number.parseInt(hex, 16)),
    )
    .replace(/&#(\d+);/g, (_, dec: string) =>
      String.fromCodePoint(Number(dec)),
    )
    .replace(/&amp;/g, "&");
}

export function textRunsFromSlideXml(xml: string): string {
  const parts: string[] = [];
  TEXT_RUN.lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = TEXT_RUN.exec(xml))) {
    const run = match[1];
    if (run) parts.push(decodeXmlEntities(run));
  }
  return parts.join("\n");
}

function slideNumber(name: string): number {
  const match = SLIDE_NAME.exec(name);
  return match ? Number(match[1]) : 0;
}

export async function extractPptxText(buffer: ArrayBuffer): Promise<string> {
  const entries = await readZipEntries(buffer);
  const slides = entries
    .filter((entry) => SLIDE_NAME.test(entry.name))
    .sort((a, b) => slideNumber(a.name) - slideNumber(b.name));
  if (slides.length === 0) {
    throw new Error("This PowerPoint has no slides");
  }
  const decoder = new TextDecoder("utf-8");
  return slides
    .map((slide) => textRunsFromSlideXml(decoder.decode(slide.bytes)))
    .join("\n\n");
}

export function isPptxFilename(name: string): boolean {
  return /\.pptm?x$/i.test(name);
}

export function isLegacyPptFilename(name: string): boolean {
  return /\.ppt$/i.test(name) && !/\.pptm?x$/i.test(name);
}

/**
 * Keep the .pptx in the stored name so a Packet can also hold a
 * same-stem handout.txt without colliding.
 */
export function pptxTextFilename(original: string): string {
  const base = original.replace(/\.pptm?x$/i, "").trim() || "slides";
  return `${base}.pptx.txt`;
}
