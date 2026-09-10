import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, describeError } from "../lib/api";
import { readiness, usePreflight } from "../lib/usePreflight";
import type { SetupCheck } from "../types";

/**
 * Setup: what this computer still needs, and exactly what to type to get it.
 *
 * This replaces a screen that named the missing commands and stopped there.
 * Naming a dependency is not guidance — the person reading it is a curriculum
 * director, not a sysadmin, and "you are missing bash" is a dead end even for
 * someone who could act on it.
 *
 * Three things make this actionable instead:
 *
 *  1. One requirement per row, each with its own state. A missing PDF reader
 *     and a stopped model are different problems with different fixes, and
 *     collapsing them into one sentence hid both.
 *  2. Commands for *this* machine only. The server reports sys.platform and we
 *     show the matching instruction, so nobody has to work out which of three
 *     package managers applies to them.
 *  3. A re-check button. Installing something in a terminal happens outside
 *     this app; without a way to re-ask, the only recovery is a restart.
 */

/** Which platform's instructions to show, and what to call it out loud. */
function platformName(platform: string): string {
  if (platform === "win32") return "Windows";
  if (platform === "darwin") return "macOS";
  return "Linux";
}

/** The fix text for this machine, falling back to the platform-agnostic one. */
function fixFor(check: SetupCheck, platform: string): string {
  return check.fix[platform] ?? check.fix.all ?? "";
}

/**
 * Does this fix text look like something to run in a terminal?
 *
 * Copy-to-clipboard on a sentence of prose is noise, so we only offer it for
 * lines that are actually commands. Anything with a space-separated verb like
 * `brew`/`choco`/`sudo` at the start, or a quoted interpreter path, qualifies.
 */
function isCommand(line: string): boolean {
  return /^(sudo |brew |choco |scoop |apt |dnf |pip |python|")/.test(line.trim());
}

function CheckRow({
  check,
  platform,
}: {
  check: SetupCheck;
  platform: string;
}) {
  const [copied, setCopied] = useState<string | null>(null);
  const fix = fixFor(check, platform);
  // Multi-line fixes are a mix of commands and explanation; split so each
  // command gets its own copy button and the prose stays prose.
  const lines = fix.split("\n").filter((l) => l.trim().length > 0);

  const copy = async (line: string) => {
    try {
      await navigator.clipboard.writeText(line);
      setCopied(line);
      window.setTimeout(() => setCopied(null), 1600);
    } catch {
      // Clipboard access can be refused; the text is on screen either way.
    }
  };

  return (
    <li className={`setup-check ${check.ok ? "done" : check.severity}`}>
      <div className="setup-check-head">
        <span className="setup-mark" aria-hidden="true">
          {check.ok ? "✓" : check.severity === "optional" ? "○" : "!"}
        </span>
        <div className="setup-check-title">
          <strong>{check.label}</strong>
          <span className="setup-tag">
            {check.ok
              ? "Ready"
              : check.severity === "required"
                ? "Needed to run"
                : check.severity === "pdf"
                  ? "Needed for PDFs"
                  : "Optional"}
          </span>
        </div>
      </div>
      <p className="setup-why">{check.why}</p>
      {check.ok ? (
        <p className="setup-detail mono">{check.detail}</p>
      ) : (
        <div className="setup-fix">
          <p className="setup-detail">{check.detail}</p>
          {/* The model is the one requirement with a real control behind it,
              and that control lives in Settings. Link to it rather than
              rendering a second copy of the picker here: duplicating a
              stateful component across two screens is what let these pages
              disagree with each other last time. */}
          {check.id === "model" && (
            <p className="setup-fix-action">
              <Link className="btn btn-primary" to="/settings">
                Choose a model
              </Link>
            </p>
          )}
          {lines.map((line) =>
            isCommand(line) ? (
              <div className="setup-cmd" key={line}>
                <code>{line}</code>
                <button type="button" onClick={() => void copy(line)}>
                  {copied === line ? "Copied" : "Copy"}
                </button>
              </div>
            ) : (
              <p className="setup-hint" key={line}>
                {line}
              </p>
            ),
          )}
        </div>
      )}
    </li>
  );
}

export function Setup() {
  // Shared with every other screen, so a model connected here is reflected in
  // Settings without either page having to know the other exists.
  const { preflight, error: preflightError, loaded, refresh } = usePreflight();
  const error = preflightError ? describeError(preflightError) : null;
  const [checking, setChecking] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installLog, setInstallLog] = useState<string | null>(null);

  const load = useCallback(async () => {
    setChecking(true);
    try {
      await refresh();
    } finally {
      setChecking(false);
    }
  }, [refresh]);

  /**
   * Install the Python dependencies, then immediately re-check.
   *
   * Re-checking is the point: an install that leaves the screen still showing
   * the old failures reads as if it did nothing, which is worse than not
   * offering the button at all.
   */
  const install = useCallback(async () => {
    setInstalling(true);
    setInstallLog(null);
    try {
      const res = await api.installDeps();
      setInstallLog(res.output || (res.ok ? "Finished." : "Failed."));
      await load();
    } catch (e) {
      setInstallLog(describeError(e).detail);
    } finally {
      setInstalling(false);
    }
  }, [load]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!loaded) {
    return (
      <div className="home">
        <div className="panel">
          <div className="panel-body empty">Checking this computer…</div>
        </div>
      </div>
    );
  }

  const checks = preflight?.checks ?? [];
  const platform = preflight?.platform ?? "linux";
  // The verdict comes from the server's own can_run, via the one shared
  // helper. Deriving it here by filtering `checks` was the bug behind Settings
  // and Setup contradicting each other: an empty `checks` array filtered down
  // to no problems, which read as success even while can_run was false.
  const { ready, pdfOnly } = readiness(preflight);
  const blocking = checks.filter((c) => c.severity === "required" && !c.ok);
  // Anything whose fix is a pip command can be done for the user. The model
  // and the WeasyPrint system libraries cannot, so a button that claimed to
  // install "everything" would be lying about those two.
  const installable = checks.some(
    (c) => !c.ok && (c.id === "packages" || c.id === "pdf"),
  );
  // Fallback for a response with no `checks` (an older server still running
  // from before an upgrade). Naming what it reported beats a blank screen,
  // and the restart hint is the actual fix.
  const staleServer = !!preflight && checks.length === 0;

  return (
    <div className="home">
      <div className="home-head">
        <h2>Setup</h2>
        <p className="home-sub">
          What Loom needs on this {platformName(platform)} computer in order to
          read a curriculum.
        </p>
      </div>

      {error && (
        <div className="panel">
          <div className="panel-head">Can’t reach Loom</div>
          <div className="panel-body">
            <p className="err-message">{error.message}</p>
            <button type="button" onClick={() => void load()}>
              Try again
            </button>
            <details className="err-details">
              <summary>Technical details</summary>
              <pre>{error.detail}</pre>
            </details>
          </div>
        </div>
      )}

      {preflight && (
        <div className="panel">
          <div className="panel-head">Where you stand</div>
          <div className="panel-body">
            {ready ? (
              <p>
                This computer is ready. You can set up a curriculum and run an
                audit.
              </p>
            ) : pdfOnly ? (
              <p>
                Loom can run here, but it cannot open PDF files yet. If your
                curriculum is Word or plain text you can start now; otherwise
                install the PDF reader below first.
              </p>
            ) : (
              <p>
                {blocking.length === 1
                  ? "One thing is missing"
                  : blocking.length > 1
                    ? `${blocking.length} things are missing`
                    : "Something is missing"}{" "}
                before Loom can read a curriculum here.
                {blocking.length > 0 &&
                  " Each one below has the command to fix it."}{" "}
                Reviewing audits that were run elsewhere works regardless.
              </p>
            )}
            {staleServer && (
              <p className="err-message">
                Loom reported{" "}
                {preflight.missing.length > 0
                  ? preflight.missing.join(", ")
                  : "a problem"}
                , but this window is talking to an older copy of Loom that
                cannot describe it in detail. Close and reopen Loom to get the
                full list.
              </p>
            )}
            <div className="setup-actions">
              {/* Offered whenever anything installable is outstanding. Nearly
                  every requirement is now an ordinary Python package with
                  prebuilt wheels, so "go install this" can be a button rather
                  than an instruction to hand to IT. */}
              {installable && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={() => void install()}
                  disabled={installing}
                >
                  {installing ? "Installing…" : "Install what’s missing"}
                </button>
              )}
              <button
                type="button"
                className="btn"
                onClick={() => void load()}
                disabled={checking || installing}
              >
                {checking ? "Checking…" : "Check again"}
              </button>
            </div>
            {installing && (
              <p className="home-note">
                Downloading and installing. This can take a couple of minutes
                the first time.
              </p>
            )}
            {installLog && (
              <details className="err-details">
                <summary>Installation log</summary>
                <pre>{installLog}</pre>
              </details>
            )}
          </div>
        </div>
      )}

      {checks.length > 0 && (
        <div className="panel">
          <div className="panel-head">Requirements</div>
          <div className="panel-body">
            <ul className="setup-checks">
              {checks.map((c) => (
                <CheckRow check={c} key={c.id} platform={platform} />
              ))}
            </ul>
          </div>
        </div>
      )}

      <p className="home-note">
        After installing something in a terminal, come back and choose{" "}
        <strong>Check again</strong>. Nothing here is sent anywhere — these
        checks only look at this computer.
      </p>
    </div>
  );
}
