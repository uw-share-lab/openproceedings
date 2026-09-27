import { afterEach, describe, expect, it, vi } from "vitest";
import nextConfig from "../../next.config";
import { contentSecurityPolicy } from "./security-headers";

const directives = (csp: string) =>
  new Map(csp.split("; ").map((d) => [d.split(" ")[0], d.split(" ").slice(1)]));

afterEach(() => vi.unstubAllEnvs());

describe("security headers", () => {
  it("sends the fixed set on every route", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const rules = await nextConfig.headers?.();
    expect(rules).toHaveLength(1);
    const [rule] = rules ?? [];
    expect(rule?.source).toBe("/:path*");
    expect(Object.fromEntries((rule?.headers ?? []).map((h) => [h.key, h.value]))).toEqual({
      "Content-Security-Policy": contentSecurityPolicy({ dev: false, apiBaseUrl: "" }),
      "X-Content-Type-Options": "nosniff",
      "X-Frame-Options": "DENY",
      "Referrer-Policy": "no-referrer",
    });
  });

  it("locks the CSP down to this origin, with no framing, plugins or eval in production", () => {
    const csp = directives(contentSecurityPolicy({ dev: false, apiBaseUrl: "" }));
    expect(csp.get("default-src")).toEqual(["'self'"]);
    expect(csp.get("script-src")).toEqual(["'self'", "'unsafe-inline'"]);
    expect(csp.get("connect-src")).toEqual(["'self'"]);
    expect(csp.get("object-src")).toEqual(["'none'"]);
    expect(csp.get("base-uri")).toEqual(["'self'"]);
    expect(csp.get("form-action")).toEqual(["'self'"]);
    expect(csp.get("frame-ancestors")).toEqual(["'none'"]);
  });

  it("adds eval only for next dev", () => {
    const csp = directives(contentSecurityPolicy({ dev: true, apiBaseUrl: "" }));
    expect(csp.get("script-src")).toContain("'unsafe-eval'");
  });

  it("allows fetches to a separate API origin, and only its origin", () => {
    const csp = directives(
      contentSecurityPolicy({ dev: false, apiBaseUrl: "https://api.example.org/base/" }),
    );
    expect(csp.get("connect-src")).toEqual(["'self'", "https://api.example.org"]);
  });
});
