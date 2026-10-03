// @vitest-environment jsdom
import { undo } from "@codemirror/commands";
import { ensureSyntaxTree } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeAll, expect, it, vi } from "vitest";
import { META, polyfillLayout } from "@/test/api-stub";
import { QueryEditor, type QueryEditorProps } from "./query-editor";

beforeAll(polyfillLayout);
afterEach(cleanup);

function tokens(view: EditorView): string[] {
  const result: string[] = [];
  const tree = ensureSyntaxTree(view.state, view.state.doc.length);
  expect(tree).not.toBeNull();
  tree!.iterate({
    enter: (node) => {
      if (node.name !== "Query") result.push(node.name);
    },
  });
  return result;
}

it("switches the live lexer when meta arrives and changes, retaining document, selection and undo", () => {
  const props: QueryEditorProps = {
    value: "＄x OR y＄",
    meta: null,
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    diagnostics: [],
    diagnosticsFor: null,
    describedBy: "summary",
  };
  const rendered = render(<QueryEditor {...props} />);
  const view = EditorView.findFromDOM(rendered.container.querySelector(".cm-editor") as HTMLElement)!;
  expect(tokens(view)).toEqual(["Word"]);
  act(() => {
    view.dispatch({ changes: { from: view.state.doc.length, insert: " " }, selection: { anchor: 3 } });
  });
  const value = view.state.doc.toString();
  rendered.rerender(<QueryEditor {...props} value={value} meta={{ ...META, tokenizer_version: "2" }} />);
  expect(EditorView.findFromDOM(rendered.container.querySelector(".cm-editor") as HTMLElement)).toBe(view);
  expect(tokens(view)).toEqual(["Word", "Or", "Wildcard"]);
  expect(view.state.doc.toString()).toBe("＄x OR y＄ ");
  expect(view.state.selection.main.anchor).toBe(3);
  rendered.rerender(<QueryEditor {...props} value={value} meta={{ ...META, tokenizer_version: "3" }} />);
  expect(tokens(view)).toEqual(["Word"]);
  expect(view.state.selection.main.anchor).toBe(3);
  act(() => {
    expect(undo(view)).toBe(true);
  });
  expect(view.state.doc.toString()).toBe("＄x OR y＄");
});

it("uses the current lexer for a placeholder or unknown meta version", () => {
  const rendered = render(
    <QueryEditor
      value="＄x OR y＄"
      meta={META}
      onChange={vi.fn()}
      onSubmit={vi.fn()}
      diagnostics={[]}
      diagnosticsFor={null}
      describedBy="summary"
    />,
  );
  const view = EditorView.findFromDOM(rendered.container.querySelector(".cm-editor") as HTMLElement)!;
  expect(tokens(view)).toEqual(["Word"]);
});
