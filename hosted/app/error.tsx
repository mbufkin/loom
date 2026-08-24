"use client";

/** Catches a signed-in home/hats miss so the digest page is not the UI. */
export default function AppError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="shell">
      <div className="wrap">
        <p className="kicker">Loom</p>
        <h1>This page did not load</h1>
        <p className="lede">Retry, or go home and sign in again.</p>
        <p className="actions">
          <button className="btn btn-brass" type="button" onClick={() => reset()}>
            Retry
          </button>
        </p>
        <p className="note">
          <a href="/">Home</a>
        </p>
      </div>
    </div>
  );
}