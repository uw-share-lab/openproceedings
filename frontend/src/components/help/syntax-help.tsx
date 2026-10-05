import Link from "next/link";
import type { Schemas } from "@/api/client";
import { INITIAL_STATE, searchHref, type Mode } from "@/lib/search-state";
import { count } from "@/components/coverage/format";
import golden from "@/help/syntax-golden.json";
import { InstanceLimits } from "./instance-limits";
import { Ticked } from "./ticked";

/**
 * `/help/syntax` (spec 05 §Pages; design `2026-09-27-coverage-and-syntax-help.md`). Every example, message,
 * token row, limit, vocabulary and default comes from `syntax-golden.json`, which the backend generates from
 * the parser, the token goldens and spec 02 and checks on every test run, so this page can't drift from the
 * parser. The prose between them states rules; it never restates a number or a value list.
 */
export type SyntaxGolden = typeof golden;

const CODE = "font-mono";

/** The anchor of a diagnostic code: the code in lower case, so a Help ▸ link builds from the code alone. */
export function anchorOf(code: string): string {
  return code.toLowerCase();
}

export const SLOW_CLAUSES_ID = "slow-clauses";

function modeOf(mode: string): Mode {
  return mode === "scholar" ? "scholar" : "native";
}

/** `/search?q=…&mode=…`: the example, in its own mode (pre-pass S15). */
export function exampleHref(q: string, mode: string): string {
  return searchHref({ ...INITIAL_STATE, q, mode: modeOf(mode) });
}

function SearchLink({ q, mode }: { q: string; mode: string }) {
  return (
    <Link
      href={exampleHref(q, mode)}
      aria-label={`Search with this example: ${q}`}
      className="text-xs whitespace-nowrap underline underline-offset-4"
    >
      Search with this example ▸
    </Link>
  );
}

function ModeNote({ mode }: { mode: string }) {
  return mode === "scholar" ? (
    <span className="text-xs text-muted-foreground"> (Google Scholar syntax)</span>
  ) : null;
}

function Examples({ items }: { items: SyntaxGolden["sections"][keyof SyntaxGolden["sections"]] }) {
  return (
    <ul className="space-y-2">
      {items.map((e) => (
        <li key={`${e.mode}:${e.q}`} className="space-y-0.5">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <code className={CODE}>{e.q}</code>
            <ModeNote mode={e.mode} />
            <SearchLink q={e.q} mode={e.mode} />
          </div>
          <div className="text-xs text-muted-foreground">
            read as <code className={CODE}>{e.canonical}</code>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Values({ values }: { values: readonly string[] }) {
  return (
    <>
      {values.map((v, i) => (
        <span key={v}>
          {i > 0 ? ", " : ""}
          <code className={CODE}>{v}</code>
        </span>
      ))}
    </>
  );
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} aria-labelledby={`${id}-heading`} className="scroll-mt-4 space-y-3">
      <h2 id={`${id}-heading`} className="text-base font-semibold">
        {title}
      </h2>
      {children}
    </section>
  );
}

const CONTENTS = [
  ["matching", "Matching"],
  ["phrases", "Phrases"],
  ["operators", "AND, OR, NOT"],
  ["wildcards", "Wildcards"],
  ["near", "NEAR"],
  ["fields", "Fields"],
  ["filters", "Filters"],
  ["defaults", "Default filters"],
  ["scholar", "Google Scholar syntax"],
  ["limits", "Limits"],
  ["messages", "Messages (A–Z)"],
] as const;

type Message = SyntaxGolden["messages"][number];

function MessageEntry({ m }: { m: Message }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
      <dt className="text-muted-foreground">Example</dt>
      <dd className="flex flex-wrap items-baseline gap-x-3">
        {m.example !== null ? (
          <code className={`${CODE} break-all`}>{m.example}</code>
        ) : (
          <span>{m.display}</span>
        )}
        <ModeNote mode={m.mode} />
      </dd>
      <dt className="text-muted-foreground">Message</dt>
      <dd>
        <Ticked text={m.message} />
        {m.note !== null ? <span className="block text-xs text-muted-foreground">{m.note}</span> : null}
      </dd>
      {m.fix !== null ? (
        <>
          <dt className="text-muted-foreground">Fix</dt>
          <dd className="flex flex-wrap items-baseline gap-x-3">
            <code className={CODE}>{m.fix}</code>
            <SearchLink q={m.fix} mode={m.mode} />
          </dd>
        </>
      ) : null}
    </dl>
  );
}

function Messages({ data }: { data: SyntaxGolden }) {
  const groups = new Map<string, Message[]>();
  for (const m of data.messages) groups.set(m.code, [...(groups.get(m.code) ?? []), m]);
  const c = data.constants;
  return (
    <div className="space-y-5">
      {[...groups].map(([code, entries]) => (
        <section
          key={code}
          id={anchorOf(code)}
          aria-labelledby={`${anchorOf(code)}-heading`}
          className="scroll-mt-4 space-y-2"
        >
          <h3 id={`${anchorOf(code)}-heading`} className="text-sm font-semibold">
            <code className={CODE}>{code}</code>{" "}
            <span className="font-normal text-muted-foreground">({entries[0]!.kind})</span>
          </h3>
          {entries.map((m, i) => (
            <MessageEntry key={i} m={m} />
          ))}
        </section>
      ))}
      <section
        id={SLOW_CLAUSES_ID}
        aria-labelledby={`${SLOW_CLAUSES_ID}-heading`}
        className="scroll-mt-4 space-y-2"
      >
        <h3 id={`${SLOW_CLAUSES_ID}-heading`} className="text-sm font-semibold">
          Slow clauses:{" "}
          {data.slow_clauses.map((code, i) => (
            <span key={code} id={anchorOf(code)} className="scroll-mt-4">
              {i > 0 ? ", " : ""}
              <code className={CODE}>{code}</code>
            </span>
          ))}
        </h3>
        <p className="text-sm">
          A phrase with a wildcard in it, and a NEAR, need a position check: the index finds the documents
          that hold the words, then each one is checked for where they occur. An instance runs a limited
          number of these checks per query, and reads a limited number of documents for them (this
          instance&apos;s limits are under{" "}
          <a href="#limits" className="underline underline-offset-4">
            Limits
          </a>
          ). A query over either limit is refused whole, never cut short. To narrow a clause, use a longer
          wildcard stem (at least {count(c.min_wildcard_stem)} letters or digits), rarer words, or a smaller
          NEAR distance.
        </p>
      </section>
    </div>
  );
}

/** The whole reference. `data` is the generated golden; tests pass a changed copy to show nothing is hard-coded. */
export function SyntaxHelp({
  data = golden,
  api,
}: {
  data?: SyntaxGolden;
  api?: Parameters<typeof InstanceLimits>[0]["api"];
}) {
  const c = data.constants;
  const [trackDefault, statusDefault] = data.defaults;
  const defaults: Schemas["Limits"] = {
    max_query_length: c.max_query_length,
    max_query_depth: c.max_query_depth,
    max_verified_clauses: c.max_verified_clauses,
    max_verification_candidates: c.max_verification_candidates,
  };
  return (
    <div className="space-y-8 text-sm">
      <nav aria-label="On this page">
        <h2 className="font-semibold">On this page</h2>
        <ul className="flex flex-wrap gap-x-3 gap-y-1">
          {CONTENTS.map(([id, title]) => (
            <li key={id}>
              <a href={`#${id}`} className="underline underline-offset-4">
                {title}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <Section id="matching" title="Matching: exact words only">
        <p>
          A word matches only that exact word after case, accents and punctuation are normalised: no stemming,
          no synonyms, no stopwords. Other endings count only through a wildcard you write (see{" "}
          <a href="#wildcards" className="underline underline-offset-4">
            Wildcards
          </a>
          ).
        </p>
        <div
          role="region"
          aria-label="Query word matching table"
          tabIndex={0}
          className="overflow-x-auto contain-layout"
        >
          <table className="text-sm">
            <caption className="text-left font-medium">What a query word finds</caption>
            <thead>
              <tr>
                <th scope="col" className="pr-4 text-left">
                  You type
                </th>
                <th scope="col" className="pr-4 text-left">
                  Matches
                </th>
                <th scope="col" className="text-left">
                  Does not match
                </th>
              </tr>
            </thead>
            <tbody>
              {data.consequences.map((row) => (
                <tr key={row.query}>
                  <th scope="row" className="pr-4 text-left font-normal">
                    <code className={CODE}>{row.query}</code>
                  </th>
                  <td className="pr-4">
                    <Ticked text={row.matches} />
                  </td>
                  <td>
                    <Ticked text={row.not} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div
          role="region"
          aria-label="Indexed word examples table"
          tabIndex={0}
          className="overflow-x-auto contain-layout"
        >
          <table className="text-sm">
            <caption className="text-left font-medium">How text is split into indexed words</caption>
            <thead>
              <tr>
                <th scope="col" className="pr-4 text-left">
                  Text
                </th>
                <th scope="col" className="text-left">
                  Indexed as
                </th>
              </tr>
            </thead>
            <tbody>
              {data.tokens.map((row) => (
                <tr key={row.input}>
                  <th scope="row" className="pr-4 text-left font-normal">
                    <code className={CODE}>{row.input}</code>
                  </th>
                  <td>
                    <Values values={row.tokens} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Chinese, Japanese and Korean text is not split into words: a run of it is one word (see{" "}
          <a href={`#${anchorOf("WARN_CJK_RUN")}`} className="underline underline-offset-4">
            <code className={CODE}>WARN_CJK_RUN</code>
          </a>
          ).
        </p>
        <Examples items={data.sections.matching} />
      </Section>

      <Section id="phrases" title="Phrases">
        <p>
          Double quotes keep words in order and next to each other, within one field: a phrase never spans the
          title and the abstract. Any word of a phrase may end in a wildcard.
        </p>
        <Examples items={data.sections.phrases} />
      </Section>

      <Section id="operators" title="AND, OR, NOT">
        <p>
          Operators are uppercase: <code className={CODE}>AND</code>, <code className={CODE}>OR</code>,{" "}
          <code className={CODE}>NOT</code>. Words side by side are ANDed, and{" "}
          <code className={CODE}>-word</code> (a hyphen straight before the word) is NOT. NOT binds tightest,
          then AND, then OR; a query that mixes AND and OR without parentheses is read that way and warned
          about. A lowercase <code className={CODE}>and</code>, <code className={CODE}>or</code> or{" "}
          <code className={CODE}>not</code> is searched as a word. A query must search for something: it
          can&apos;t be negations alone.
        </p>
        <Examples items={data.sections.operators} />
      </Section>

      <Section id="wildcards" title="Wildcards">
        <p>
          <code className={CODE}>*</code> at the end of a word matches any ending;{" "}
          <code className={CODE}>$</code> matches the word or the word plus one more character (a plural). The
          stem before either needs at least {count(c.min_wildcard_stem)} letters or digits, and may match at
          most {count(c.max_expansions)} different words in the index; every word it matched is listed with
          the results. A wildcard is allowed in a phrase, and a stem that splits into several words becomes a
          phrase whose last word carries it.
        </p>
        <Examples items={data.sections.wildcards} />
      </Section>

      <Section id="near" title="NEAR">
        <p>
          <code className={CODE}>a NEAR/n b</code> matches when <code className={CODE}>a</code> and{" "}
          <code className={CODE}>b</code> occur in the same field, in either order, with at most{" "}
          <code className={CODE}>n</code> words between them. <code className={CODE}>n</code> is a whole
          number up to {count(c.max_near)}.
        </p>
        <Examples items={data.sections.near} />
      </Section>

      <Section id="fields" title="Fields">
        <p>
          Without a field, a word is searched in both text fields (<Values values={data.text_fields} />
          ), and nothing else is ever searched. A field prefix searches one of them; on a group it applies to
          every term inside.
        </p>
        <Examples items={data.sections.fields} />
      </Section>

      <Section id="filters" title="Filters">
        <p>Filters are part of the query, so the query you save holds them. Their values are exact:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>
            <code className={CODE}>venue:</code> <Values values={data.values.venue} /> (in any case)
          </li>
          <li>
            <code className={CODE}>year:</code> a four-digit year, or an inclusive range{" "}
            <code className={CODE}>from..to</code>, between {c.min_year} and {c.max_year}
          </li>
          <li>
            <code className={CODE}>track:</code> <Values values={data.values.track} />
          </li>
          <li>
            <code className={CODE}>status:</code> <Values values={data.values.status} />
          </li>
        </ul>
        <p>Values take no wildcards or quotes; join several with OR inside parentheses.</p>
        <Examples items={data.sections.filters} />
      </Section>

      <Section id="defaults" title="Default filters">
        <p>
          A query with no top-level <code className={CODE}>{trackDefault!.field}:</code> clause gets{" "}
          <code className={CODE}>{trackDefault!.canonical}</code>, and one with no top-level{" "}
          <code className={CODE}>{statusDefault!.field}:</code> clause gets{" "}
          <code className={CODE}>{statusDefault!.canonical}</code>. They are written out in the canonical
          query, so a saved query shows them, and the records they exclude are counted with the results. A
          clause of your own replaces the default; one nested inside an OR doesn&apos;t (see{" "}
          <a href={`#${anchorOf("WARN_NESTED_FILTER")}`} className="underline underline-offset-4">
            <code className={CODE}>WARN_NESTED_FILTER</code>
          </a>
          ).
        </p>
        <Examples items={data.sections.defaults} />
      </Section>

      <Section id="scholar" title="Google Scholar syntax">
        <p>
          Choose Google Scholar syntax to run a Google Scholar or Publish or Perish string as it is.{" "}
          <code className={CODE}>|</code> is OR, <code className={CODE}>source:</code> is translated to{" "}
          <code className={CODE}>venue:</code>, <code className={CODE}>$</code> is read as the Web of Science
          zero-or-one wildcard, and unquoted words side by side in an OR item are read as one phrase. Every
          translation is shown with the results. Google Scholar stems words and searches full text; here words
          match exactly, in titles and abstracts only.
        </p>
        <p>
          So a Google Scholar string usually finds fewer papers here until its terms carry a wildcard. The
          notice that lists the terms matched exactly offers <strong>Add $</strong>: it writes{" "}
          <code className={CODE}>$</code> after every listed term that can take one, or after the terms you
          tick under Choose terms, in the editor. A phrase gets it on its last word. Terms that already have a
          wildcard, terms with fewer than {count(c.min_wildcard_stem)} letters or digits, terms that end in a
          symbol or have another <code className={CODE}>$</code> beside them, a lowercase{" "}
          <code className={CODE}>and</code>, <code className={CODE}>or</code> or{" "}
          <code className={CODE}>not</code>, and filter values are left as typed; when no term can take one,
          or the query would be over the length limit with them added, the notice says so and offers nothing.
          Nothing is searched until you press Search, and the editor&apos;s undo takes the change back.{" "}
          <code className={CODE}>$</code> adds at most one character (<code className={CODE}>benchmark$</code>{" "}
          matches <code className={CODE}>benchmark</code> and <code className={CODE}>benchmarks</code>, not{" "}
          <code className={CODE}>benchmarking</code>), which is fewer forms than Google Scholar counts; type{" "}
          <code className={CODE}>*</code> for any ending. After a search, the expansions show every word each
          wildcard matched.
        </p>
        <Examples items={data.sections.scholar} />
      </Section>

      <Section id="limits" title="Limits">
        <ul className="list-disc space-y-1 pl-5 tabular-nums">
          <li>A wildcard stem keeps at least {count(c.min_wildcard_stem)} letters or digits.</li>
          <li>A wildcard matches at most {count(c.max_expansions)} words.</li>
          <li>A NEAR distance is at most {count(c.max_near)} words.</li>
        </ul>
        <InstanceLimits defaults={defaults} {...(api ? { api } : {})} />
      </Section>

      <Section id="messages" title="Messages (A–Z)">
        <p>
          Every error, warning and translation a query can produce, with an example that produces it, the
          message you see, and a fixed version where there is one. Errors stop a query from running; warnings
          and translations say how it was read.
        </p>
        <Messages data={data} />
      </Section>
    </div>
  );
}
