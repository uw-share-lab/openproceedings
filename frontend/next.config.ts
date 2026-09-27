import path from "node:path";
import type { NextConfig } from "next";

// Spec 05 / nextjs-conventions: the app ships as a standalone Node server in the `web` container (spec 08),
// never bound to a hosting platform. Dependencies are hoisted to the npm workspace root (../node_modules),
// so tracing starts there and the server lands at .next/standalone/frontend/server.js.
const workspaceRoot = path.join(import.meta.dirname, "..");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: workspaceRoot,
  turbopack: { root: workspaceRoot },
  poweredByHeader: false,
};

export default nextConfig;
