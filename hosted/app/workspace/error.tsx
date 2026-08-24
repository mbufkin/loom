"use client";

/**
 * Last line if a store read still escapes. The Admin sees a retry,
 * not Next’s digest page.
 */
export default function WorkspaceError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="shell">
      <div className="wrap">
        <p className="kicker">Loom</p>
        <h1>Workspace could not load</h1>
        <p className="lede">
          The Packet store did not answer. Your sign-in is fine — retry, or
          open the other door if you wear both hats.
        </p>
        <p className="actions">
          <button className="btn btn-brass" type="button" onClick={() => reset()}>
            Retry
          </button>
        </p>
        <p className="note">
          <a href="/hats">Choose a door</a>
          {" · "}
          <a href="/">Home</a>
        </p>
      </div>
    </div>
  );
}