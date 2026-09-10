import { useCallback, useEffect, useState } from "react";
import { api, describeError } from "../lib/api";
import type { ModelDiscovery, ModelProvider } from "../types";

/**
 * A hosted model service: key entry, then its model list.
 *
 * Two things are load-bearing here.
 *
 * The key is write-only from the browser's point of view. It is posted once
 * to the local server, which puts it in the OS credential store, and is
 * never sent back — the UI only ever learns whether one is present. A key
 * echoed into the page is a key in the DOM, in devtools, and in any
 * screenshot someone takes of this screen.
 *
 * And the privacy consequence is stated plainly rather than buried. Loom's
 * whole premise for districts is that curriculum text stays on the machine;
 * choosing a hosted model is the one action that breaks that, so it should
 * be a deliberate decision, not a convenient default someone clicks past.
 */
function HostedProvider({
  provider,
  onConnected,
}: {
  provider: ModelProvider;
  onConnected: () => void;
}) {
  const [keyInput, setKeyInput] = useState("");
  const [present, setPresent] = useState(provider.present);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [models, setModels] = useState<string[] | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);

  const noStore = provider.backend === null;

  const loadModels = useCallback(async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await api.remoteModels(provider.id);
      if (!res.ok) {
        setNote(res.error ?? "Could not list models.");
        setModels(null);
        return;
      }
      setModels(res.models ?? []);
    } catch (e) {
      setNote(describeError(e).message);
    } finally {
      setBusy(false);
    }
  }, [provider.id]);

  const save = useCallback(async () => {
    setBusy(true);
    setNote(null);
    try {
      const res = await api.saveKey(provider.chat_url, keyInput.trim());
      setPresent(res.present);
      setNote(res.message ?? res.error ?? null);
      // Clear the field as soon as it is stored: there is no reason for the
      // secret to stay in a form value once the credential store has it.
      if (res.ok) {
        setKeyInput("");
        await loadModels();
      }
    } catch (e) {
      setNote(describeError(e).message);
    } finally {
      setBusy(false);
    }
  }, [keyInput, loadModels, provider.chat_url]);

  const clear = useCallback(async () => {
    setBusy(true);
    try {
      const res = await api.saveKey(provider.chat_url, null);
      setPresent(res.present);
      setModels(null);
      setNote(res.message ?? null);
    } catch (e) {
      setNote(describeError(e).message);
    } finally {
      setBusy(false);
    }
  }, [provider.chat_url]);

  const connect = useCallback(
    async (model: string) => {
      setConnecting(model);
      try {
        const res = await api.selectModel(provider.chat_url, model);
        setNote(res.ok ? `Connected to ${model}.` : (res.error ?? "Failed."));
        if (res.ok) onConnected();
      } catch (e) {
        setNote(describeError(e).message);
      } finally {
        setConnecting(null);
      }
    },
    [onConnected, provider.chat_url],
  );

  const looksWrong =
    keyInput.trim().length > 0 && !keyInput.trim().startsWith(provider.key_prefix);

  return (
    <div className="setup-server">
      <div className="setup-server-head">
        <strong>{provider.label}</strong>
        <span className="setup-tag">{present ? "Key saved" : "No key"}</span>
      </div>

      <p className="setup-hint">
        This model runs on {provider.host}, not on this computer.{" "}
        <strong>
          Your curriculum documents would be sent there to be read.
        </strong>{" "}
        Only use it if your district permits curriculum material to leave the
        building.
      </p>

      {noStore ? (
        <p className="err-message">
          This computer has no credential store, so a key cannot be saved
          safely here. Set the <code>LOOM_API_KEY</code> environment variable
          instead.
        </p>
      ) : (
        <>
          <div className="setup-manual">
            <input
              type="password"
              autoComplete="off"
              spellCheck={false}
              placeholder={present ? "Replace the saved key" : "Paste your API key"}
              value={keyInput}
              onChange={(e) => setKeyInput(e.target.value)}
            />
            <button
              type="button"
              className="btn"
              onClick={() => void save()}
              disabled={!keyInput.trim() || busy}
            >
              {busy ? "Saving…" : "Save key"}
            </button>
            {present && (
              <button type="button" className="btn" onClick={() => void clear()} disabled={busy}>
                Remove key
              </button>
            )}
          </div>
          <p className="setup-hint">
            {provider.key_help} It is kept in{" "}
            {provider.backend ?? "the system credential store"}, not in a file,
            and is never shown again.
          </p>
          {looksWrong && (
            <p className="err-message">
              That does not look like a {provider.label} key — they start with{" "}
              <code>{provider.key_prefix}</code>.
            </p>
          )}
        </>
      )}

      {present && models === null && !busy && (
        <div className="setup-actions">
          <button type="button" className="btn" onClick={() => void loadModels()}>
            Show available models
          </button>
        </div>
      )}

      {models !== null && models.length > 0 && (
        <ul className="setup-models">
          {models.map((m) => (
            <li key={m}>
              <span className="mono">{m}</span>
              <button
                type="button"
                onClick={() => void connect(m)}
                disabled={connecting !== null}
              >
                {connecting === m ? "Connecting…" : "Use this"}
              </button>
            </li>
          ))}
        </ul>
      )}
      {models !== null && models.length === 0 && (
        <p className="setup-hint">The service returned no models.</p>
      )}

      {note && <p className="setup-detail">{note}</p>}
    </div>
  );
}

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
  const [providers, setProviders] = useState<ModelProvider[]>([]);

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

  // Hosted services are a static catalogue plus a key-present flag, so this
  // is cheap and does not need to wait on the loopback scan.
  useEffect(() => {
    api
      .providers()
      .then((r) => setProviders(r.providers))
      .catch(() => setProviders([]));
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

        {/* Collapsed by default, and below the local servers, because the
            ordering is the recommendation: a model on this machine is the
            option that keeps curriculum text in the building. */}
        {providers.length > 0 && (
          <details className="err-details">
            <summary>Use a hosted service (needs an API key)</summary>
            <p className="setup-hint">
              These run outside your building. Loom sends them your curriculum
              text to read, so this is a decision for whoever owns data policy
              at your district — not just a faster model.
            </p>
            {providers.map((p) => (
              <HostedProvider key={p.id} provider={p} onConnected={onConnected} />
            ))}
          </details>
        )}

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
