/**
 * Response headers for every route (next.config.ts `headers()`; nextjs-conventions §Security headers).
 *
 * The CSP is static, with `'unsafe-inline'` for scripts and styles. Next's App Router streams its RSC
 * payload in inline `<script>` tags and next-themes sets the theme with an inline script before paint; a
 * nonce would need a proxy (middleware) on every request and would force every page to render
 * dynamically. The trade-off: an injected inline script would run. The defence against that is that the
 * app never builds HTML from strings (`react/no-danger` is an error in eslint; highlights are text nodes
 * cut at API spans). Everything else is locked down: no plugins, no framing, no foreign base or form target,
 * and scripts, fonts, images and fetches only from this origin (plus the API origin when it is separate).
 */
export interface SecurityHeaderOptions {
  /** `next dev` needs `'unsafe-eval'` (React's dev tooling rebuilds call stacks with eval). */
  readonly dev: boolean;
  /** `NEXT_PUBLIC_API_BASE_URL`; "" means the API is same-origin under `/api/v1`. */
  readonly apiBaseUrl: string;
}

export function contentSecurityPolicy({ dev, apiBaseUrl }: SecurityHeaderOptions): string {
  const apiOrigin = apiBaseUrl === "" ? null : new URL(apiBaseUrl).origin;
  const directives: [string, ...string[]][] = [
    ["default-src", "'self'"],
    ["script-src", "'self'", "'unsafe-inline'", ...(dev ? ["'unsafe-eval'"] : [])],
    ["style-src", "'self'", "'unsafe-inline'"],
    ["img-src", "'self'", "data:"],
    ["font-src", "'self'"],
    ["connect-src", "'self'", ...(apiOrigin === null ? [] : [apiOrigin])],
    ["object-src", "'none'"],
    ["base-uri", "'self'"],
    ["form-action", "'self'"],
    ["frame-ancestors", "'none'"],
  ];
  return directives.map((d) => d.join(" ")).join("; ");
}

export function securityHeaders(options: SecurityHeaderOptions): { key: string; value: string }[] {
  return [
    { key: "Content-Security-Policy", value: contentSecurityPolicy(options) },
    { key: "X-Content-Type-Options", value: "nosniff" },
    // frame-ancestors covers current browsers; X-Frame-Options covers the rest.
    { key: "X-Frame-Options", value: "DENY" },
    // Search URLs carry the query text in `q`, so no page sends its URL to another site.
    { key: "Referrer-Policy", value: "no-referrer" },
    // No page uses a device; a script injected despite the CSP gets none of them either.
    { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
    // HTTPS only, for two years, once a browser has seen the site over HTTPS (TASK-067: no downgrade to
    // plain HTTP on a later visit). Browsers ignore it over plain HTTP, so a local production build still
    // works; left out of `next dev`. No includeSubDomains: the hosting domain isn't decided (TASK-064).
    ...(options.dev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=63072000" }]),
  ];
}
