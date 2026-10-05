import type { Page } from "@playwright/test";

/**
 * The fixture API's instances (backend/tests/e2e/fixture_server.py): the default on the API port, `tight` on
 * the next port (2 concept groups and 5 terms counted, the rate limit on with a comparison cooldown long
 * enough to see, a 2,048-byte comparison file cap) and `plain` on the one after (comparisons off). The web build calls the API
 * port; `useInstance` sends a page's API calls to another instance instead, so a state that only another
 * configuration gives is the server's own answer, never one written in the browser.
 */
export const API_PORT = Number(process.env.OP_E2E_API_PORT ?? "8000");
const OFFSET = { tight: 1, plain: 2 } as const;

export function apiUrl(instance: "default" | keyof typeof OFFSET = "default"): string {
  return `http://127.0.0.1:${API_PORT + (instance === "default" ? 0 : OFFSET[instance])}`;
}

export async function useInstance(page: Page, instance: keyof typeof OFFSET): Promise<void> {
  const from = apiUrl();
  const to = apiUrl(instance);
  await page.route(`${from}/**`, (route) => route.continue({ url: route.request().url().replace(from, to) }));
}
