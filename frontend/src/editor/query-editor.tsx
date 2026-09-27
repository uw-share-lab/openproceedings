"use client";

/**
 * The query editor: CodeMirror 6 with the highlighting-only Lezer language (spec 05 §Components 1;
 * codemirror-lezer and accessibility skills; design W3 and §Keyboard and screen reader).
 *
 * - Keyboard: Enter (and Mod-Enter) submits, Shift-Enter inserts a newline, Tab leaves the editor (no
 *   `indentWithTab`), Ctrl-Space opens completion, F8 / Shift-F8 move to the next / previous diagnostic,
 *   Mod-Shift-m opens the lint panel.
 * - Squiggles are the server's: the parent passes diagnostics already converted to UTF-16 (diagnostics.ts)
 *   together with the text they were reported for, and they are drawn only while the document is that text.
 * - Accessible name "Query" (ED-1), described by the diagnostics summary.
 */
import { autocompletion } from "@codemirror/autocomplete";
import { defaultKeymap, history, historyKeymap, insertNewline } from "@codemirror/commands";
import { bracketMatching } from "@codemirror/language";
import {
  lintGutter,
  lintKeymap,
  previousDiagnostic,
  setDiagnostics,
  type Diagnostic as EditorDiagnostic,
} from "@codemirror/lint";
import { EditorSelection, EditorState } from "@codemirror/state";
import { EditorView, keymap } from "@codemirror/view";
import { useEffect, useImperativeHandle, useRef, type Ref } from "react";
import { queryCompletions, type Meta } from "./complete";
import { query } from "./lang";

export interface QueryEditorHandle {
  focus(): void;
  /** Select `[from, to)` (UTF-16) and focus the editor. */
  select(from: number, to: number): void;
}

export interface QueryEditorProps {
  readonly value: string;
  readonly onChange: (text: string) => void;
  readonly onSubmit: () => void;
  /** Squiggles for `diagnosticsFor`, in UTF-16 positions; ignored while the document is another text. */
  readonly diagnostics: readonly EditorDiagnostic[];
  readonly diagnosticsFor: string | null;
  /** The id of the diagnostics summary (`aria-describedby`). */
  readonly describedBy: string;
  readonly meta: Meta | null;
  readonly autoFocus?: boolean;
  readonly handle?: Ref<QueryEditorHandle>;
}

/** Squiggles differ by line style and gutter glyph, never by colour alone (design W3). */
const diagnosticTheme = EditorView.theme({
  "&": {
    minHeight: "4rem",
    fontSize: "0.875rem",
    backgroundColor: "var(--background)",
    color: "var(--foreground)",
  },
  "&.cm-focused": { outline: "2px solid var(--ring)", outlineOffset: "2px" },
  ".cm-content": { fontFamily: "var(--font-mono)", padding: "0.375rem 0", caretColor: "var(--foreground)" },
  ".cm-cursor": { borderLeftColor: "var(--foreground)" },
  ".cm-gutters": { backgroundColor: "var(--background)", border: "none", color: "var(--muted-foreground)" },
  ".cm-lintRange-error": {
    backgroundImage: "none",
    textDecoration: "underline wavy var(--diag-error)",
    textDecorationThickness: "1.5px",
    textDecorationSkipInk: "none",
    textUnderlineOffset: "3px",
  },
  ".cm-lintRange-warning": {
    backgroundImage: "none",
    textDecoration: "underline dotted var(--diag-warning)",
    textDecorationThickness: "2px",
    textDecorationSkipInk: "none",
    textUnderlineOffset: "3px",
  },
  ".cm-lintRange-info": {
    backgroundImage: "none",
    textDecoration: "underline dashed var(--diag-info)",
    textDecorationThickness: "1.5px",
    textDecorationSkipInk: "none",
    textUnderlineOffset: "3px",
  },
  ".cm-lint-marker": {
    content: "normal",
    width: "1em",
    height: "1em",
    lineHeight: "1em",
    textAlign: "center",
  },
  ".cm-lint-marker-error::before": { content: '"✖"', color: "var(--diag-error)" },
  ".cm-lint-marker-warning::before": { content: '"⚠"', color: "var(--diag-warning)" },
  ".cm-lint-marker-info::before": { content: '"↻"', color: "var(--diag-info)" },
  ".cm-tooltip": {
    backgroundColor: "var(--popover)",
    color: "var(--popover-foreground)",
    border: "1px solid var(--border)",
  },
  ".cm-diagnostic-error": { borderLeftColor: "var(--diag-error)" },
  ".cm-diagnostic-warning": { borderLeftColor: "var(--diag-warning)" },
  ".cm-diagnostic-info": { borderLeftColor: "var(--diag-info)" },
});

export function QueryEditor(props: QueryEditorProps) {
  const parent = useRef<HTMLDivElement>(null);
  const view = useRef<EditorView | null>(null);
  // The latest callbacks, read by the editor's listeners, which are created once.
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });

  useImperativeHandle(props.handle, () => ({
    focus: () => view.current?.focus(),
    select: (from, to) => {
      const v = view.current;
      if (v === null) return;
      v.dispatch({ selection: EditorSelection.range(from, to), scrollIntoView: true });
      v.focus();
    },
  }));

  useEffect(() => {
    if (parent.current === null) return;
    const submit = () => {
      latest.current.onSubmit();
      return true;
    };
    const v = new EditorView({
      parent: parent.current,
      state: EditorState.create({
        doc: latest.current.value,
        extensions: [
          history(),
          query(),
          bracketMatching(),
          lintGutter(),
          autocompletion({
            override: [queryCompletions(() => latest.current.meta)],
            activateOnTyping: false,
            icons: false,
          }),
          keymap.of([
            { key: "Enter", run: submit, shift: insertNewline },
            { key: "Mod-Enter", run: submit },
            ...lintKeymap,
            { key: "Shift-F8", run: previousDiagnostic },
            ...historyKeymap,
            ...defaultKeymap,
          ]),
          EditorView.lineWrapping,
          EditorView.contentAttributes.of({
            "aria-label": "Query",
            "aria-describedby": latest.current.describedBy,
          }),
          EditorView.updateListener.of((update) => {
            if (update.docChanged) latest.current.onChange(update.state.doc.toString());
          }),
          diagnosticTheme,
        ],
      }),
    });
    view.current = v;
    if (latest.current.autoFocus) v.focus();
    return () => {
      v.destroy();
      view.current = null;
    };
  }, []);

  // A value set from outside (Revert edits, an example, Load with parentheses): one undoable change.
  useEffect(() => {
    const v = view.current;
    if (v === null || v.state.doc.toString() === props.value) return;
    v.dispatch({
      changes: { from: 0, to: v.state.doc.length, insert: props.value },
      selection: EditorSelection.cursor(props.value.length),
    });
  }, [props.value]);

  // The server's squiggles, only on the text they were reported for.
  useEffect(() => {
    const v = view.current;
    if (v === null || props.diagnosticsFor === null || v.state.doc.toString() !== props.diagnosticsFor)
      return;
    v.dispatch(setDiagnostics(v.state, props.diagnostics));
  }, [props.diagnostics, props.diagnosticsFor]);

  return (
    <div
      ref={parent}
      data-testid="query-editor"
      className="w-full min-w-0 rounded-md border border-input bg-background"
    />
  );
}
