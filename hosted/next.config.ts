import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // This repo has lockfiles at home, loom root, and hosted/. Pin traces here.
  outputFileTracingRoot: path.join(__dirname),
  async rewrites() {
    return {
      // The React app (public/app, built from ../ui) uses real paths such as
      // /app/curricula/x. `fallback` runs only after public files are checked,
      // so /app/assets/*.js is served as-is and every other /app path gets
      // index.html for the client router to resolve.
      fallback: [{ source: "/app/:path*", destination: "/app/index.html" }],
    };
  },
  async headers() {
    return [
      {
        // index.html names the content-hashed bundles; never cache it, or a
        // deploy leaves people on the old app.
        source: "/app/index.html",
        headers: [{ key: "Cache-Control", value: "no-store" }],
      },
    ];
  },
};

export default nextConfig;
