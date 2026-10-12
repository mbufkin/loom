// Desktop vs hosted, decided at build time.
//
// The same React app ships two ways: inside the desktop window, talking to
// ui/server.py on the same origin at /api; and on the hosted site, behind a
// Google sign-in, where the Next app forwards /api/loom/* to the Pi. Build-time
// env (not a runtime check) so the desktop bundle has no hosted code paths to
// misfire, and the hosted bundle cannot be talked into showing the key UI.
//
//   desktop:  vite build                                   -> /api, settings shown
//   hosted:   VITE_API_BASE=/api/loom VITE_HOSTED=1 vite build --base=/app/

/** Prefix for every API path. "/api" keeps the desktop app unchanged. */
export const API_ROOT: string = (import.meta.env.VITE_API_BASE || "/api").replace(/\/+$/, "");

/** True in the hosted build: hide model choice, API keys, and installers. */
export const IS_HOSTED: boolean = import.meta.env.VITE_HOSTED === "1";

/** react-router basename matching Vite's --base ("/" -> "", "/app/" -> "/app"). */
export const ROUTER_BASENAME: string = import.meta.env.BASE_URL.replace(/\/+$/, "");
