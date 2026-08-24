/**
 * Cloudflare R2 is the Packet archive (S3 API). Fly and Vercel both speak
 * this. The bucket is private — browsers never get a public URL.
 *
 * Required env (never commit values):
 *   R2_ACCOUNT_ID
 *   R2_ACCESS_KEY_ID
 *   R2_SECRET_ACCESS_KEY
 *   R2_BUCKET          (default: loom-packets)
 */
import {
  DeleteObjectCommand,
  GetObjectCommand,
  ListObjectsV2Command,
  PutObjectCommand,
  S3Client,
} from "@aws-sdk/client-s3";
import { getSignedUrl } from "@aws-sdk/s3-request-presigner";

/** Thrown on writes when Vercel/Fly has Auth but no R2_* vars. */
export const PACKET_STORE_UNCONFIGURED = "Packet store is not configured";

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`${name} is not set`);
  return value;
}

export function r2Bucket(): string {
  return process.env.R2_BUCKET?.trim() || "loom-packets";
}

export function r2Configured(): boolean {
  return Boolean(
    process.env.R2_ACCOUNT_ID &&
      process.env.R2_ACCESS_KEY_ID &&
      process.env.R2_SECRET_ACCESS_KEY,
  );
}

/**
 * Writes must fail with a product sentence, not `R2_ACCOUNT_ID is not set`.
 * That raw throw became the signed-in Workspace error boundary.
 */
export function assertR2Configured(): void {
  if (!r2Configured()) {
    throw new Error(PACKET_STORE_UNCONFIGURED);
  }
}

/**
 * AWS SDK v3 signs CRC32 checksum query params by default. A browser
 * PUT then either fails CORS (extra headers) or 403s on signature.
 * R2 does not need those checksums for a private Packet put.
 */
export const R2_S3_CHECKSUMS = {
  requestChecksumCalculation: "WHEN_REQUIRED" as const,
  responseChecksumValidation: "WHEN_REQUIRED" as const,
};

export function r2Client(): S3Client {
  // Guard before required() so Accept Bargain names the missing host,
  // not an env var the Admin should never see.
  assertR2Configured();
  const accountId = required("R2_ACCOUNT_ID");
  return new S3Client({
    region: "auto",
    endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId: required("R2_ACCESS_KEY_ID"),
      secretAccessKey: required("R2_SECRET_ACCESS_KEY"),
    },
    ...R2_S3_CHECKSUMS,
  });
}

export async function r2PutJson(key: string, value: unknown): Promise<void> {
  await r2Client().send(
    new PutObjectCommand({
      Bucket: r2Bucket(),
      Key: key,
      Body: JSON.stringify(value),
      ContentType: "application/json",
    }),
  );
}

/** Packet file bytes from a same-origin Function — no browser CORS. */
export async function r2PutBytes(
  key: string,
  body: Uint8Array,
  contentType: string,
): Promise<void> {
  await r2Client().send(
    new PutObjectCommand({
      Bucket: r2Bucket(),
      Key: key,
      Body: body,
      ContentType: contentType,
      ContentLength: body.byteLength,
    }),
  );
}

export async function r2GetJson<T>(key: string): Promise<T | null> {
  try {
    const out = await r2Client().send(
      new GetObjectCommand({ Bucket: r2Bucket(), Key: key }),
    );
    const text = await out.Body?.transformToString();
    if (!text) return null;
    try {
      return JSON.parse(text) as T;
    } catch {
      return null;
    }
  } catch (error) {
    const name = (error as { name?: string }).name;
    const status = (error as { $metadata?: { httpStatusCode?: number } })
      .$metadata?.httpStatusCode;
    if (
      name === "NoSuchKey" ||
      name === "NotFound" ||
      status === 404
    ) {
      return null;
    }
    throw error;
  }
}

export async function r2GetObject(key: string) {
  return r2Client().send(
    new GetObjectCommand({ Bucket: r2Bucket(), Key: key }),
  );
}

export type R2Listed = { key: string; size: number };

export async function r2ListObjects(prefix: string): Promise<R2Listed[]> {
  const objects: R2Listed[] = [];
  let token: string | undefined;
  do {
    const page = await r2Client().send(
      new ListObjectsV2Command({
        Bucket: r2Bucket(),
        Prefix: prefix,
        ContinuationToken: token,
      }),
    );
    for (const obj of page.Contents ?? []) {
      if (obj.Key) objects.push({ key: obj.Key, size: obj.Size ?? 0 });
    }
    token = page.IsTruncated ? page.NextContinuationToken : undefined;
  } while (token);
  return objects;
}

export async function r2ListKeys(prefix: string): Promise<string[]> {
  const objects = await r2ListObjects(prefix);
  return objects.map((obj) => obj.key);
}

/** Every object in the bucket, including reservations and plates. */
export async function r2BucketUsage(): Promise<{ bytes: number; objects: number }> {
  const objects = await r2ListObjects("");
  let bytes = 0;
  for (const obj of objects) bytes += obj.size;
  return { bytes, objects: objects.length };
}

export async function r2Delete(key: string): Promise<void> {
  await r2Client().send(
    new DeleteObjectCommand({ Bucket: r2Bucket(), Key: key }),
  );
}

/**
 * Short-lived PUT so the browser can paste bytes without a Function body.
 * ContentLength is on the signed request so a client cannot PUT more than
 * it declared (that would sneak past the Ceiling).
 */
export async function r2PresignPut(
  key: string,
  contentType: string,
  contentLength: number,
): Promise<string> {
  return getSignedUrl(
    r2Client(),
    new PutObjectCommand({
      Bucket: r2Bucket(),
      Key: key,
      ContentType: contentType,
      ContentLength: contentLength,
    }),
    { expiresIn: 60 * 5 },
  );
}
