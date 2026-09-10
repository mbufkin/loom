import { useCallback, useEffect, useMemo, useState } from "react";
import { api, describeError } from "../lib/api";
import type { ModelDiscovery, ModelProvider } from "../types";

/** Does this endpoint run on this machine? Drives the whole privacy story. */
function isLocalEndpoint(url: string | undefined | null): boolean {
  if (!url) return false;
  return /^https?:\/\/(127\.0\.0\.1|localhost|\[::1\])(:|\/|$)/i.test(url);
}

function hostOf(url: string | undefined | null): string {
  if (!url) return "";
  try {
    return new URL(url).host;
  } catch {
    return url;
  }
}

/**
 * What Loom is reading with right now, stated once and stated loudly.
 *
 * The badge is the point. "llama3.2:3b" and "nvidia/llama-3.3-70b" look
 * equally harmless as bare names, but one keeps every document on this
 * machine and the other posts them to a company. Someone glancing at this
 * screen should be able to tell which without reading a URL.
 */
function CurrentModel({
  current,
  source,
}: {
  current?: { url: string; model: string };
  source: string;
}) {
  if (!current?.url || !current.model) {
    return (
      <div className="model-now none">
        <div className="model-now-model">No model chosen yet</div>
        <div className="model-now-note">
          Loom cannot read a curriculum until one is selected below.
        </div>
      </div>
    );
  }
  const local = isLocalEndpoint(current.url);
  return (
    <div className={`model-now ${local ? "local" : "remote"}`}>
      <div className="model-now-label">Reading with</div>
      <div className="model-now-model mono">{current.model}</div>
      <div className="model-now-where">
        {source}
        {source && " · "}
        <span className="mono">{hostOf(current.url)}</span>
      </div>
      <div className="model-now-badge">
        {local
          ? "Stays on this computer"
          : `Your documents are sent to ${hostOf(current.url)}`}
      </div>
    </div>
  );
}

/**
 * Models whose names say they were built for a job that is not reading a
 * curriculum: embedders, rerankers, safety classifiers, reward models,
 * speech, OCR and vision.
 *
 * A hosted catalogue is one flat list of everything the provider sells, and
 * NVIDIA's is over a hundred entries. Offering `nv-embedqa-mistral-7b-v2`
 * beside a chat model as an equal choice is a trap — pick it and the audit
 * fails with an unhelpful API error, long after you have forgotten which
 * button caused it. These stay reachable behind "show everything" rather
 * than being removed, because a heuristic on a name will be wrong sometimes
 * and hiding a working model with no way back is worse than a long list.
 */
const NOT_FOR_READING =
  /(embed|rerank|guard|safety|reward|topic-control|jailbreak|translate|parse|ocr|clip|speech|asr|[-/]tts|[-/]stt|vila|neva|riva|diffusion|image|video)/i;

/** The chosen model first. Hunting alphabetically for your own choice is not a task. */
function activeFirst(models: string[], active: string | undefined): string[] {
  if (!active) return models;
  return [...models].sort(
    (a, b) => Number(b === active) - Number(a === active),
  );
}

/**
 * One selectable model. Shared by the local and hosted lists so that "in
 * use" looks identical wherever the model happens to live — the previous
 * version only marked local models, so choosing a hosted one left no visible
 * trace anywhere in the list.
 */
function ModelRow({
  name,
  active,
  busy,
  disabled,
  onUse,
}: {
  name: string;
  active: boolean;
  busy: boolean;
  disabled: boolean;
  onUse: () => void;
}) {
  return (
    <li className={active ? "in-use" : undefined}>
      <span className="mono">{name}</span>
      {active ? (
        <span className="setup-tag in-use-tag">In use</span>
      ) : (
        <button type="button" onClick={onUse} disabled={disabled}>
          {busy ? "Connecting…" : "Use this"}
        </button>
      )}
    </li>
  );
}

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
  current,
  onChanged,
}: {
  provider: ModelProvider;
  /** The endpoint and model config.yaml currently points at, if any. */
  current?: { url: string; model: string };
  onChanged: () => void | Promise<void>;
}) {
  const [keyInput, setKeyInput] = useState("");
  const [present, setPresent] = useState(provider.present);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [models, setModels] = useState<string[] | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  const [showAll, setShowAll] = useState(false);

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
        // Refresh the parent so the card at the top and the "In use" marker
        // update together — the choice is not confirmed until both agree.
        if (res.ok) await onChanged();
      } catch (e) {
        setNote(describeError(e).message);
      } finally {
        setConnecting(null);
      }
    },
    [onChanged, provider.chat_url],
  );

  // If this service is the one in use, fetch its models unprompted. Making
  // someone press "show available models" to see which of them is currently
  // selected would hide the answer behind the question.
  const isActiveProvider = current?.url === provider.chat_url;
  useEffect(() => {
    if (isActiveProvider && present && models === null && !busy) {
      void loadModels();
    }
  }, [isActiveProvider, present, models, busy, loadModels]);

  const activeModel = isActiveProvider ? current?.model : undefined;

  // Narrow the catalogue down to something a person can actually read: the
  // chosen model first, chat-capable models only unless asked otherwise, and
  // a text filter once the list is long enough to need one.
  const { shown, hiddenCount } = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const matches = (models ?? []).filter(
      (m) => !q || m.toLowerCase().includes(q),
    );
    // Counted after the text filter, not before, so the number always
    // describes what "show everything" would actually add to this screen.
    const hidden = matches.filter(
      (m) => NOT_FOR_READING.test(m) && m !== activeModel,
    ).length;
    const usable = showAll
      ? matches
      : matches.filter((m) => !NOT_FOR_READING.test(m) || m === activeModel);
    return { shown: activeFirst(usable, activeModel), hiddenCount: hidden };
  }, [models, filter, showAll, activeModel]);

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
        <>
          <div className="model-filter">
            <input
              type="search"
              spellCheck={false}
              placeholder={`Filter ${models.length} models`}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            />
            <span className="setup-detail">
              {shown.length} shown
              {hiddenCount > 0 && !showAll && ` · ${hiddenCount} hidden`}
            </span>
          </div>

          {shown.length === 0 ? (
            <p className="setup-hint">Nothing matches “{filter}”.</p>
          ) : (
            <ul className="setup-models">
              {shown.map((m) => (
                <ModelRow
                  key={m}
                  name={m}
                  active={m === activeModel}
                  busy={connecting === m}
                  disabled={connecting !== null}
                  onUse={() => void connect(m)}
                />
              ))}
            </ul>
          )}

          {hiddenCount > 0 && (
            <p className="setup-hint">
              <button
                type="button"
                className="link-button"
                onClick={() => setShowAll(!showAll)}
              >
                {showAll
                  ? "Show only models that can read documents"
                  : `Show everything, including ${hiddenCount} models built for other jobs`}
              </button>
              {!showAll &&
                " — embedding, safety, translation and image models are hidden because an audit cannot use them."}
            </p>
          )}
        </>
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

  // Name the place the current model actually runs, by matching its endpoint
  // against what we know. Without this the answer to "what am I using?" is a
  // URL, and a URL is not an answer most people can act on.
  const currentSource =
    servers.find((s) => s.chat_url === current?.url)?.name ??
    providers.find((p) => p.chat_url === current?.url)?.label ??
    (current?.url ? "Custom endpoint" : "");

  return (
    <div className="panel">
      <div className="panel-head">Language model</div>
      <div className="panel-body">
        {/* One prominent statement of what is in use, above the choices.
            Previously this was spread over three places — a separate panel,
            a line of small print, and an "In use" tag buried in a list — so
            after picking a hosted model the only feedback was a sentence at
            the bottom. The badge carries the part that actually matters:
            whether curriculum text stays on this machine. */}
        <CurrentModel current={current} source={currentSource} />

        <h4 className="model-group">On this computer</h4>

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
                {activeFirst(
                  s.models,
                  current?.url === s.chat_url ? current?.model : undefined,
                ).map((m) => (
                  <ModelRow
                    key={m}
                    name={m}
                    active={current?.url === s.chat_url && current?.model === m}
                    busy={busy === `${s.chat_url}|${m}`}
                    disabled={busy !== null}
                    onUse={() => void connect(s.chat_url, m)}
                  />
                ))}
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
            option that keeps curriculum text in the building. Opens by
            itself when a hosted model is the one in use, so the section is
            never hiding the thing that is currently active. */}
        {providers.length > 0 && (
          <details
            className="err-details"
            open={providers.some((p) => p.chat_url === current?.url)}
          >
            <summary>Somewhere else (needs an API key)</summary>
            <p className="setup-hint">
              These run outside your building. Loom sends them your curriculum
              text to read, so this is a decision for whoever owns data policy
              at your district — not just a faster model.
            </p>
            {providers.map((p) => (
              <HostedProvider
                key={p.id}
                provider={p}
                current={current}
                onChanged={async () => {
                  await rescan();
                  onConnected();
                }}
              />
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
