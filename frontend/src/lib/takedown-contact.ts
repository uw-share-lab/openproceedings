/**
 * The takedown contact every deployment names (decision-018): where a rights holder asks for an abstract to be
 * removed. The operator sets it per deployment with `NEXT_PUBLIC_TAKEDOWN_CONTACT`, compiled in at build time
 * like `NEXT_PUBLIC_API_BASE_URL`: an email address (`takedown@example.org` or `mailto:…`) or an `https://` /
 * `http://` page. Unset, the footer points at the project's issue tracker instead of naming no one; set but
 * unusable (another scheme, not an address), it falls back the same way and says so on the build's console.
 */

/** The repository's issues page (the project's own contact), used when a deployment names none. */
export const TAKEDOWN_FALLBACK_URL = "https://github.com/uw-share-lab/openproceedings/issues";

export type TakedownContact =
  /** An address the operator set: the link is `mailto:`, its text the address. */
  | { kind: "email"; href: string; label: string }
  /** A page the operator set (a form or a policy): its text is the URL without the scheme. */
  | { kind: "url"; href: string; label: string }
  /** No usable contact was set: the project's issue tracker. */
  | { kind: "fallback"; href: string; label: string };

// One `@`, no spaces or characters that would end or quote an address in a URL, and a dot in the domain.
const EMAIL = /^[^\s@<>()[\]"',;:\\]+@[^\s@<>()[\]"',;:\\]+\.[^\s@<>()[\]"',;:\\]+$/;

function withoutScheme(url: URL): string {
  const path = url.pathname === "/" ? "" : url.pathname;
  return `${url.host}${path}${url.search}`;
}

const FALLBACK: TakedownContact = {
  kind: "fallback",
  href: TAKEDOWN_FALLBACK_URL,
  label: withoutScheme(new URL(TAKEDOWN_FALLBACK_URL)),
};

/** Reads a configured contact; `warn` hears about a value that was set but can't be used. */
export function takedownContact(
  raw: string | undefined,
  warn: (message: string) => void = (message) => console.warn(message),
): TakedownContact {
  const value = raw?.trim() ?? "";
  if (value === "") return FALLBACK;
  const address = value.toLowerCase().startsWith("mailto:") ? value.slice("mailto:".length) : value;
  if (EMAIL.test(address)) return { kind: "email", href: `mailto:${address}`, label: address };
  if (/^https?:\/\//i.test(value)) {
    try {
      const url = new URL(value);
      return { kind: "url", href: url.href, label: withoutScheme(url) };
    } catch {
      // not a URL after all: falls through to the warning
    }
  }
  warn(
    `NEXT_PUBLIC_TAKEDOWN_CONTACT is neither an email address nor an http(s) URL; the footer links to ` +
      `${TAKEDOWN_FALLBACK_URL} instead. Set it to the address or page that receives takedown requests.`,
  );
  return FALLBACK;
}
