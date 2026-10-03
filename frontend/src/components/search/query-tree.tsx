"use client";

/**
 * "How we read your query" (spec 05 §Components 2; design W5 and §Keyboard and screen reader; copy TR-1–3):
 * a disclosure holding the canonical query and the identification string, each copyable, and the server's
 * `effective_ast` as a nested list. The tree is the server's, walked, never re-parsed. A default clause (a
 * top-level filter on a field `/parse` lists in `defaults`) is drawn in `--default-clause` with the text
 * label "default", so it is never marked by colour alone.
 */
import { forwardRef, useId, type ReactNode } from "react";
import { CopyButton } from "@/components/copy-button";
import type { ParseResponse } from "@/editor/parse";

type Node = NonNullable<ParseResponse["effective_ast"]>;
type Leaf = Extract<Node, { kind: "phrase" }>["items"][number];
type FilterValue = Extract<Node, { kind: "filter" }>["values"][number];

const leafText = (n: Leaf): string => (n.kind === "term" ? n.token : `${n.stem}${n.op}`);
const scoped = (field: string | null, text: string) => (field === null ? text : `${field}:${text}`);

function filterValue(v: FilterValue): string {
  if (typeof v === "string") return v;
  return v.lo === v.hi ? String(v.lo) : `${v.lo}..${v.hi}`;
}

const Op = ({ children }: { children: ReactNode }) => <strong className="font-bold">{children}</strong>;

function TreeNode({ node, defaults, top }: { node: Node; defaults: readonly string[]; top: boolean }) {
  switch (node.kind) {
    case "term":
    case "wildcard":
      return <li className="font-mono">{scoped(node.field, leafText(node))}</li>;
    case "phrase":
      return <li className="font-mono">{scoped(node.field, `"${node.items.map(leafText).join(" ")}"`)}</li>;
    case "filter": {
      const isDefault = top && defaults.includes(node.field);
      const values = node.values.map(filterValue);
      return (
        <li className={isDefault ? "text-default-clause" : undefined}>
          <span className="font-mono">
            {node.field}:{" "}
            {values.map((v, i) => (
              <span key={i}>
                {i > 0 && (
                  <>
                    {" "}
                    <Op>OR</Op>{" "}
                  </>
                )}
                {v}
              </span>
            ))}
          </span>
          {isDefault && <span className="ml-2 rounded-sm border px-1 text-xs">default</span>}
        </li>
      );
    }
    case "near":
      return (
        <li>
          <Op>NEAR/{node.distance}</Op>
          <ul className="ml-4 border-l pl-3">
            <TreeNode node={node.left} defaults={defaults} top={false} />
            <TreeNode node={node.right} defaults={defaults} top={false} />
          </ul>
        </li>
      );
    case "not":
      return (
        <li>
          <Op>NOT</Op>
          <ul className="ml-4 border-l pl-3">
            <TreeNode node={node.child} defaults={defaults} top={false} />
          </ul>
        </li>
      );
    case "and":
    case "or":
      return (
        <li>
          <Op>{node.kind.toUpperCase()}</Op>
          <ul className="ml-4 border-l pl-3">
            {node.children.map((c, i) => (
              <TreeNode key={i} node={c} defaults={defaults} top={top && node.kind === "and"} />
            ))}
          </ul>
        </li>
      );
  }
}

export interface QueryTreeProps {
  readonly result: Pick<ParseResponse, "effective_ast" | "canonical" | "identification_query" | "defaults">;
  readonly open: boolean;
  readonly onToggle: () => void;
  /** "Draft — not searched" while the tree is the unsearched draft's (ED-14). */
  readonly draft: boolean;
}

export const QueryTree = forwardRef<HTMLButtonElement, QueryTreeProps>(function QueryTree(
  { result, open, onToggle, draft },
  ref,
) {
  const region = useId();
  const { effective_ast: ast, canonical, identification_query: identification, defaults } = result;
  return (
    <section className="space-y-2 text-sm">
      <h2 className="text-sm font-normal">
        <button
          ref={ref}
          type="button"
          aria-expanded={open}
          aria-controls={region}
          onClick={onToggle}
          className="min-h-6 text-left underline-offset-4 hover:underline"
        >
          <span aria-hidden="true">{open ? "▾" : "▸"} </span>
          {draft && <span className="font-semibold">Draft — not searched: </span>}
          How we read your query
          {defaults.length > 0 && (
            <span className="text-muted-foreground"> (defaults: {defaults.join(", ")})</span>
          )}
        </button>
      </h2>
      {open && (
        <div id={region} className="space-y-2 rounded-md border p-3">
          {canonical !== null && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">Canonical query</p>
              <p className="flex flex-wrap items-start gap-2">
                <code className="font-mono break-all">{canonical}</code>
                <CopyButton text={canonical} label="Copy canonical query" />
              </p>
            </div>
          )}
          {identification !== null && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">
                Identification string (what &lsquo;identified&rsquo; counts)
              </p>
              <p className="flex flex-wrap items-start gap-2">
                <code className="font-mono break-all">{identification === "" ? '""' : identification}</code>
                <CopyButton text={identification} label="Copy identification string" />
              </p>
            </div>
          )}
          {ast !== null && (
            <ul aria-label="Query tree" className="space-y-0.5">
              <TreeNode node={ast} defaults={defaults} top />
            </ul>
          )}
        </div>
      )}
    </section>
  );
});
