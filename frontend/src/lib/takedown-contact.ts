/**
 * The takedown contact a deployment names (decision-018): where a rights holder asks for an abstract to be
 * removed. The operator sets it with `NEXT_PUBLIC_TAKEDOWN_CONTACT`, compiled in at build time like
 * `NEXT_PUBLIC_API_BASE_URL`: an email address (`takedown@example.org` or `mailto:…`) or an `https://` /
 * `http://` page. Unset, the footer points at the project's issue tracker instead of naming no one. Set but
 * unusable, it is refused: `next.config.ts` calls `checkTakedownContactEnv`, which throws, so the build fails.
 */

/** The repository's issues page (the project's own contact), used when a deployment names none. */
export const TAKEDOWN_FALLBACK_URL = "https://github.com/uw-share-lab/openproceedings/issues";

export type TakedownContact =
  /** An address the operator set: the link is `mailto:`, its text the address. */
  | { kind: "email"; href: string; label: string }
  /** A page the operator set (a form or a policy): its text is the host and path, without scheme, query or hash. */
  | { kind: "url"; href: string; label: string }
  /** No contact was set: the project's issue tracker, whose issues are public. */
  | { kind: "fallback"; href: string; label: string };

/** A set `NEXT_PUBLIC_TAKEDOWN_CONTACT` that is neither a plain email address nor a plain http(s) URL. */
export class TakedownContactError extends Error {
  override name = "TakedownContactError";
}

// ASCII only, no `%`, `?`, `#`, `&`, `/` or `=`: nothing that could add mailto headers (`?cc=`), encode a
// newline (`%0A`), or hide characters (U+202E, U+200B). A domain of dot-separated labels ending in a TLD.
const EMAIL = /^[A-Za-z0-9._+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$/;
// A URL is written as printable ASCII: no spaces, controls, bidi or zero-width characters.
const PRINTABLE_ASCII = /^[\x21-\x7E]+$/;

function hostAndPath(url: URL): string {
  const path = url.pathname === "/" ? "" : url.pathname;
  return `${url.host}${path}`;
}

const FALLBACK: TakedownContact = {
  kind: "fallback",
  href: TAKEDOWN_FALLBACK_URL,
  label: hostAndPath(new URL(TAKEDOWN_FALLBACK_URL)),
};

function refuse(why: string): never {
  throw new TakedownContactError(
    `NEXT_PUBLIC_TAKEDOWN_CONTACT ${why}. Set it to a plain email address (takedown@example.org) or an ` +
      `http(s) page, or leave it unset to link to ${TAKEDOWN_FALLBACK_URL}.`,
  );
}

/** Reads a configured contact: the fallback when unset, else the address or page; throws when unusable. */
export function takedownContact(raw: string | undefined): TakedownContact {
  const value = raw?.trim() ?? "";
  if (value === "") return FALLBACK;
  if (/^mailto:/i.test(value)) {
    const address = value.slice("mailto:".length);
    if (!EMAIL.test(address)) refuse("has a mailto: address that is not a plain email address");
    return { kind: "email", href: `mailto:${address}`, label: address };
  }
  if (EMAIL.test(value)) return { kind: "email", href: `mailto:${value}`, label: value };
  if (!/^https?:\/\//i.test(value)) refuse("is neither an email address nor an http(s) URL");
  if (!PRINTABLE_ASCII.test(value)) refuse("contains spaces, control, invisible or non-ASCII characters");
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    refuse("is not a valid URL");
  }
  if (url.username !== "" || url.password !== "") refuse("is a URL with a username or password");
  return { kind: "url", href: url.href, label: hostAndPath(url) };
}

/**
 * The build's check (`next.config.ts`): throws on a set but unusable value; in production, warns once when the
 * variable is unset, because a publicly reachable instance must set it (spec 08 §Deploy).
 */
export function checkTakedownContactEnv(
  raw: string | undefined,
  production: boolean,
  warn: (message: string) => void = (message) => console.warn(message),
): void {
  if (takedownContact(raw).kind === "fallback" && production) {
    warn(
      "WARNING: NEXT_PUBLIC_TAKEDOWN_CONTACT is unset, so the footer links to the project's public issue " +
        "tracker. Publicly reachable instances must set NEXT_PUBLIC_TAKEDOWN_CONTACT (decision-018, spec 08 §Deploy).",
    );
  }
}
