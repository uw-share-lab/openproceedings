import path from "node:path";
import type { NextConfig } from "next";
import { securityHeaders } from "./src/lib/security-headers";
import { checkTakedownContactEnv } from "./src/lib/takedown-contact";

// Spec 05 / nextjs-conventions: the app ships as a standalone Node server in the `web` container (spec 08),
// never bound to a hosting platform. Dependencies are hoisted to the npm workspace root (../node_modules),
// so tracing starts there and the server lands at .next/standalone/frontend/server.js.
// decision-018: a set but unusable takedown contact fails the build here; unset warns once in production.
checkTakedownContactEnv(process.env.NEXT_PUBLIC_TAKEDOWN_CONTACT, process.env.NODE_ENV === "production");

const workspaceRoot = path.join(import.meta.dirname, "..");

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: workspaceRoot,
  turbopack: { root: workspaceRoot },
  poweredByHeader: false,
  // CSP and friends on every route; the policy and its trade-offs are in src/lib/security-headers.ts.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders({
          dev: process.env.NODE_ENV === "development",
          apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "",
        }),
      },
    ];
  },
};

export default nextConfig;
