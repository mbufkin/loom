import path from "node:path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // This repo has lockfiles at home, loom root, and hosted/. Pin traces here.
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
