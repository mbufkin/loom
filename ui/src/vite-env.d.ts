/// <reference types="vite/client" />

// The types Vite injects into the app it builds: `import.meta.env` (DEV, PROD,
// BASE_URL…), asset imports, and the hot-reload handle.
//
// A Vite project normally scaffolds this file on day one. This one never had
// it, because nothing had reached for `import.meta` until useFreshBundle
// needed to know whether it was running under the dev server — where the
// stale-bundle check must stay quiet, since Vite reloads the page itself.
// Without the reference, `import.meta.env` is a type error even though it is
// perfectly valid at runtime.
