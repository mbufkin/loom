"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  MAX_FILE_BYTES,
  MAX_FILES_PER_PACKET,
  PACKET_NAME_MAX,
  packetFilePath,
  sanitizeFilename,
} from "@/lib/packets";

type Props = {
  districtId: string;
  names: string[];
};

export function PasteForm({ districtId, names }: Props) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = event.currentTarget;
    const files = [
      ...((form.elements.namedItem("files") as HTMLInputElement).files ?? []),
    ];
    if (files.length === 0) {
      setError("Choose at least one document.");
      return;
    }
    if (files.length > MAX_FILES_PER_PACKET) {
      setError(`At most ${MAX_FILES_PER_PACKET} files in one Packet.`);
      return;
    }
    if (files.some((file) => file.size > MAX_FILE_BYTES)) {
      setError("Each file must be 25 MB or smaller.");
      return;
    }

    setBusy(true);
    const packetId = crypto.randomUUID();
    const bytes = files.reduce((sum, file) => sum + file.size, 0);

    try {
      const hold = await fetch("/api/store-ceiling", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ packetId, bytes, files: files.length }),
      });
      const holdJson = (await hold.json()) as { error?: string };
      if (!hold.ok) {
        throw new Error(holdJson.error ?? "Could not reserve store space");
      }

      const uploaded = [];
      for (const file of files) {
        const filename = sanitizeFilename(file.name);
        if (!filename) {
          throw new Error(`Cannot paste “${file.name}”.`);
        }
        const pathname = packetFilePath(districtId, packetId, filename);
        const contentType = file.type || "application/octet-stream";
        const signed = await fetch("/api/r2/presign", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            pathname,
            contentType,
            size: file.size,
          }),
        });
        const grant = (await signed.json()) as {
          url?: string;
          error?: string;
        };
        if (!signed.ok || !grant.url) {
          throw new Error(grant.error ?? "Could not open the Packet store");
        }
        const put = await fetch(grant.url, {
          method: "PUT",
          headers: { "content-type": contentType },
          body: file,
        });
        if (!put.ok) {
          throw new Error("R2 rejected this file");
        }
        uploaded.push({
          name: filename,
          pathname,
          size: file.size,
          contentType,
        });
      }

      const response = await fetch("/api/packets", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ packetId, name, files: uploaded }),
      });
      const json = (await response.json()) as {
        packet?: { id: string };
        error?: string;
      };
      if (!response.ok || !json.packet) {
        throw new Error(json.error ?? "Could not freeze this Packet");
      }
      router.push(`/workspace/packets/${json.packet.id}`);
      router.refresh();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Paste failed");
      setBusy(false);
    }
  }

  return (
    <form className="stack" onSubmit={onSubmit}>
      <label className="field">
        <span>Packet name</span>
        <input
          list="packet-names"
          name="name"
          required
          maxLength={PACKET_NAME_MAX}
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="Ag Mechanics"
          autoComplete="off"
        />
      </label>
      <datalist id="packet-names">
        {names.map((used) => (
          <option key={used} value={used} />
        ))}
      </datalist>
      <p className="note" style={{ marginTop: 0 }}>
        Pick a name this District already used, or type a new one. A second
        paste is always a new Packet — files do not accumulate.
      </p>
      <label className="field">
        <span>Documents</span>
        <input name="files" type="file" required multiple disabled={busy} />
      </label>
      {error ? <p className="form-error">{error}</p> : null}
      <button className="btn btn-brass" type="submit" disabled={busy}>
        {busy ? "Pasting…" : "Paste Packet"}
      </button>
    </form>
  );
}
