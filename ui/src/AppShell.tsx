import { NavLink, Outlet } from "react-router-dom";

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
  return (
    <div className="app">
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
          <NavLink to="/settings">Settings</NavLink>
        </nav>
        <div className="spacer" />
      </header>
      <Outlet />
    </div>
  );
}
