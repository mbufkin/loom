import { useCallback, useEffect, useState } from "react";
import { api, describeError } from "../lib/api";
import type { ModelDiscovery } from "../types";

/**
 * Find a language model on this computer and connect to it.
 *
 * A model is the one requirement Loom cannot install, but it can nearly
 * always *find* one: Ollama, LM Studio, llama.cpp, Jan, vLLM and the rest all
 * expose the same OpenAI-compatible API, so one scan identifies the server
 * and lists what it can run. That turns "edit models.analyst_url in
 * config.yaml" — which is what this used to require — into picking a name
 * from a list.
 *
 * Lives in Settings, which is where a person looks to change how the program
 * is configured. Setup links here rather than repeating the control: two
 * copies of a stateful picker is two things to keep in step, and the last bug
 * on these screens came from exactly that kind of duplication.
 *
 * The manual field stays for the cases a scan cannot cover: a server on a
 * non-standard port, or an endpoint the district hosts centrally.
 */
export function ModelPicker({ onConnected }: { onConnected: () => void }) {
  const [scan, setScan] = useState<ModelDiscovery | null>(null);
  const [scanning, setScanning] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [manualUrl, setManualUrl] = useState("");
  const [manualModel, setManualModel] = useState("");

  const rescan = useCallback(async () => {
    setScanning(true);
    setNote(null);
    try {
      setScan(await api.discoverModels());
    } catch (e) {
      setNote(describeError(e).message);
    } finally {
      setScanning(false);
    }
  }, []);

  // Scan on arrival rather than behind a button. Asking someone to press
  // "scan" before showing them anything is a step with no decision in it.
  useEffect(() => {
    void rescan();
  }, [rescan]);

  const connect = useCallback(
    async (url: string, model: string) => {
      setBusy(`${url}|${model}`);
      setNote(null);
      try {
        const res = await api.selectModel(url, model);
        if (!res.ok) {
          setNote(res.error ?? "Could not save that choice.");
          return;
        }
        setNote(`Connected to ${model}.`);
        await rescan();
        onConnected();
      } catch (e) {
        setNote(describeError(e).message);
      } finally {
        setBusy(null);
      }
    },
    [onConnected, rescan],
  );

  const current = scan?.current;
  const servers = scan?.servers ?? [];
  // True when the configured endpoint is not one of the servers we found —
  // a district-hosted model, or one on a port the scan does not know. Worth
  // stating, because otherwise the list looks like it has forgotten the
  // model the panel above says is in use.
  const currentIsElsewhere =
    !!current?.url && !servers.some((s) => s.chat_url === current.url);

  return (
    <div className="panel">
      <div className="panel-head">Choose a language model</div>
      <div className="panel-body">
        {scanning && <p className="home-note">Looking on this computer…</p>}

        {!scanning && servers.length === 0 && (
          <>
            <p className="err-message">
              No model server is running on this computer.
            </p>
            <p>
              Loom works with Ollama, LM Studio, llama.cpp, Jan and anything
              else that speaks the OpenAI API. Start one, then scan again.
              Ollama is the usual choice — install it, run{" "}
              <code>ollama pull llama3.1:8b</code>, and it stays running in the
              background.
            </p>
          </>
        )}

        {!scanning && currentIsElsewhere && servers.length > 0 && (
          <p className="setup-detail">
            The model in use, <strong>{current?.model}</strong>, is not one of
            these — it is at <span className="mono">{current?.url}</span>.
          </p>
        )}

        {servers.map((s) => (
          <div className="setup-server" key={s.base}>
            <div className="setup-server-head">
              <strong>{s.name}</strong>
              <span className="mono setup-detail">{s.base}</span>
            </div>
            {s.models.length === 0 ? (
              <p className="setup-hint">Running, but no model is loaded yet.</p>
            ) : (
              <ul className="setup-models">
                {s.models.map((m) => {
                  const active =
                    current?.url === s.chat_url && current?.model === m;
                  return (
                    <li key={m}>
                      <span className="mono">{m}</span>
                      {active ? (
                        <span className="setup-tag">In use</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => void connect(s.chat_url, m)}
                          disabled={busy !== null}
                        >
                          {busy === `${s.chat_url}|${m}`
                            ? "Connecting…"
                            : "Use this"}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ))}

        {note && <p className="setup-detail">{note}</p>}

        <div className="setup-actions">
          <button
            type="button"
            className="btn"
            onClick={() => void rescan()}
            disabled={scanning}
          >
            {scanning ? "Scanning…" : "Scan again"}
          </button>
        </div>

        <details className="err-details">
          <summary>Connect to something else</summary>
          <p className="setup-hint">
            For a model on an unusual port, or one your district hosts. The
            address is the full chat endpoint, usually ending in{" "}
            <code>/v1/chat/completions</code>. Anything not on this computer
            means curriculum text leaves the building, so it should be an
            endpoint your district has approved.
          </p>
          <div className="setup-manual">
            <input
              type="text"
              placeholder="http://127.0.0.1:1234/v1/chat/completions"
              value={manualUrl}
              onChange={(e) => setManualUrl(e.target.value)}
            />
            <input
              type="text"
              placeholder="model name"
              value={manualModel}
              onChange={(e) => setManualModel(e.target.value)}
            />
            <button
              type="button"
              className="btn"
              onClick={() => void connect(manualUrl.trim(), manualModel.trim())}
              disabled={
                !manualUrl.trim() || !manualModel.trim() || busy !== null
              }
            >
              Connect
            </button>
          </div>
        </details>
      </div>
    </div>
  );
}
