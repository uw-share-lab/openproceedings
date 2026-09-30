import { takedownContact } from "@/lib/takedown-contact";

const LINK = "text-foreground underline underline-offset-4 wrap-anywhere";

/**
 * The footer on every page (decision-018): the deployment's takedown contact. Read at render time, so a test
 * can stub the variable; Next compiles `process.env.NEXT_PUBLIC_*` in at build time, so a deployment sets it
 * before building (copy deck FT-1 to FT-3). `next.config.ts` has already refused an unusable value, so this
 * never renders one.
 */
export function SiteFooter() {
  const contact = takedownContact(process.env.NEXT_PUBLIC_TAKEDOWN_CONTACT);
  const link = (
    <a href={contact.href} className={LINK}>
      {contact.label}
    </a>
  );
  return (
    <footer className="border-t px-4 py-3 text-sm text-muted-foreground">
      <p>
        {contact.kind === "email" && <>To have an abstract removed from this site, email {link}.</>}
        {contact.kind === "url" && <>To have an abstract removed from this site, contact {link}.</>}
        {contact.kind === "fallback" && (
          <>
            To have an abstract removed from this site, open an issue at {link}. Issues there are public, so
            leave out personal details.
          </>
        )}
      </p>
    </footer>
  );
}
