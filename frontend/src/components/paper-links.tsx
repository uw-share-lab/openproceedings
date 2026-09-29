/** A paper's outbound links, each only when the record has it (design W5 result item, P1 "Links"). */

interface Urls {
  readonly forum: string | null;
  readonly pdf: string | null;
  readonly proceedings: string | null;
  readonly doi: string | null;
}

/** A DOI as a link: a bare `10.…` DOI resolves through doi.org; a URL is used as it is. */
export function doiHref(doi: string): string {
  return /^https?:\/\//i.test(doi) ? doi : `https://doi.org/${doi}`;
}

export function paperLinks(urls: Urls): { label: string; href: string }[] {
  return [
    ...(urls.forum === null ? [] : [{ label: "OpenReview", href: urls.forum }]),
    ...(urls.pdf === null ? [] : [{ label: "PDF", href: urls.pdf }]),
    ...(urls.proceedings === null ? [] : [{ label: "Proceedings", href: urls.proceedings }]),
    ...(urls.doi === null ? [] : [{ label: "DOI", href: doiHref(urls.doi) }]),
  ];
}

export function PaperLinks({ urls, label }: { urls: Urls; label: string }) {
  const links = paperLinks(urls);
  if (links.length === 0) return null;
  return (
    <ul aria-label={label} className="flex flex-wrap gap-x-3 text-sm">
      {links.map((l) => (
        <li key={l.label}>
          <a
            href={l.href}
            rel="noopener noreferrer"
            className="inline-flex min-h-6 items-center underline underline-offset-4"
          >
            {l.label}
          </a>
        </li>
      ))}
    </ul>
  );
}
