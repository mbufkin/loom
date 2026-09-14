import { NavLink, Outlet } from "react-router-dom";
import { useFreshBundle } from "./lib/useFreshBundle";

/**
 * Global navigation, persistent across every screen.
 *
 * Until now the app was a single page — the review console — with three
 * internal tabs and no way to reach anything else. Setting a curriculum up,
 * supplying a school calendar and choosing a model all happened outside the
 * app: in a terminal, or by hand-editing YAML. This bar is the one place those
 * destinations live, so nothing new has to invent its own way of being found.
 *
 * Two tiers on purpose. This bar is *global* (which part of the app am I in?);
 * the review console keeps its own bar below for *page context* (which
 * curriculum, which audit). Collapsing them into one row would mean the
 * curriculum picker followed you onto screens where it means nothing.
 */
export function AppShell() {
  // A native window has no address bar, so an upgrade that happened while it
  // was open is otherwise invisible. See lib/useFreshBundle.
  const { stale, reload } = useFreshBundle();

  return (
    <div className="app">
      {/* Above the nav bar, not inside a page: it is true of the whole window
          rather than of whatever screen happens to be open, and it must not
          scroll away. Not a modal either — nothing here is urgent, and a
          window mid-audit should not be interrupted to be told about it. */}
      {stale && (
        <div className="stale-banner" role="status">
          <span>
            Loom has been updated. Reload to use the new version — this won’t
            affect any audit that is running.
          </span>
          <button type="button" onClick={reload}>
            Reload
          </button>
        </div>
      )}
      <header className="shellbar">
        <NavLink to="/" className="shell-brand">
          Loom
        </NavLink>
        {/* aria-current is what NavLink sets, and it is also what the
            stylesheet keys the active state off — so the visual state and the
            state announced to a screen reader cannot drift apart. */}
        <nav className="shellnav" aria-label="Main">
          <NavLink to="/" end>
            Curricula
          </NavLink>
          <NavLink to="/calendars">Calendars</NavLink>
          <NavLink to="/setup">Setup</NavLink>
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="spacer" />
      </header>
      <Outlet />
    </div>
  );
}
