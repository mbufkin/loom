import React from "react";
import ReactDOM from "react-dom/client";
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { AppShell } from "./AppShell";
import { Calendars } from "./pages/Calendars";
import { CurriculumSetup } from "./pages/CurriculumSetup";
import { Home } from "./pages/Home";
import { RunReview } from "./pages/RunReview";
import { Settings } from "./pages/Settings";
import "./styles.css";

/**
 * Root path: the home screen, unless the URL is an older-style deep link.
 *
 * The desktop launcher builds `?project=…&view=…` onto the origin (see
 * ui/window.py), and that is also the shape of every URL anyone has bookmarked
 * so far. Rather than break `run-ui --view overview`, forward those to the
 * console with the query intact. Only a bare `/` means "show me home".
 */
function RootRoute() {
  const { search } = useLocation();
  const q = new URLSearchParams(search);
  const isLegacyDeepLink =
    q.has("project") || q.has("view") || q.has("e2e") || q.has("doc");
  if (isLegacyDeepLink) {
    return <Navigate to={{ pathname: "/review", search }} replace />;
  }
  return <Home />;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {/* BrowserRouter rather than HashRouter: the production server already
        falls back to index.html for any extensionless path (_safe_static), and
        Vite does the same in development, so real paths work in both modes and
        the URL stays readable. */}
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<RootRoute />} />
          <Route path="/review" element={<RunReview />} />
          <Route path="/calendars" element={<Calendars />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/curricula/new" element={<CurriculumSetup />} />
          <Route path="/curricula/:projectId" element={<CurriculumSetup />} />
          {/* Anything unrecognised goes home rather than showing a blank
              window, which is the only recovery a desktop user would have. */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
);
