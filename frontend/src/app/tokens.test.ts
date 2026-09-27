/**
 * Contrast of the design tokens in globals.css, both themes (ui-design-system skill; spec 05 WCAG 2.2 AA):
 * text on its background ≥ 4.5:1, borders/icons ≥ 3:1. Colours are oklch() without alpha; the conversion
 * is the OKLab → linear sRGB matrix from Björn Ottosson's reference, then WCAG relative luminance.
 */
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.join(import.meta.dirname, "globals.css"), "utf8");

function block(selector: string): Map<string, number[]> {
  const start = css.indexOf(`\n${selector} {`);
  if (start < 0) throw new Error(`no ${selector} block in globals.css`);
  const body = css.slice(start, css.indexOf("}", start));
  const tokens = new Map<string, number[]>();
  for (const m of body.matchAll(/--([a-z0-9-]+):\s*oklch\(([^)]*)\);/g)) {
    const name = m[1];
    const args = m[2];
    if (name === undefined || args === undefined) continue;
    if (args.includes("/")) throw new Error(`--${name}: alpha is not supported by this check`);
    tokens.set(name, args.trim().split(/\s+/).map(Number));
  }
  return tokens;
}

function luminance([L = 0, C = 0, h = 0]: number[]): number {
  const a = C * Math.cos((h * Math.PI) / 180);
  const b = C * Math.sin((h * Math.PI) / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const clamp = (x: number) => Math.min(1, Math.max(0, x));
  const r = clamp(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s);
  const g = clamp(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s);
  const bl = clamp(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s);
  return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
}

function contrast(x: number[], y: number[]): number {
  const [hi, lo] = [luminance(x), luminance(y)].sort((p, q) => q - p) as [number, number];
  return (hi + 0.05) / (lo + 0.05);
}

const TEXT: [string, string][] = [
  ["foreground", "background"],
  ["card-foreground", "card"],
  ["popover-foreground", "popover"],
  ["primary-foreground", "primary"],
  ["secondary-foreground", "secondary"],
  ["muted-foreground", "background"],
  ["muted-foreground", "muted"],
  ["accent-foreground", "accent"],
  ["destructive", "background"],
  ["hl-fg", "hl-bg"],
  ["warn-fg", "warn-bg"],
  ["excluded-fg", "excluded-bg"],
  ["default-clause", "background"],
  ["track-workshop", "background"],
];

const NON_TEXT: [string, string][] = [
  ["border", "background"],
  ["input", "background"],
  ["ring", "background"],
  ["warn-border", "warn-bg"],
  ["excluded-border", "excluded-bg"],
];

describe.each([":root", ".dark"])("tokens in %s", (selector) => {
  const tokens = block(selector);
  const get = (name: string): number[] => {
    const v = tokens.get(name);
    if (v === undefined) throw new Error(`--${name} missing from ${selector}`);
    return v;
  };

  it.each(TEXT)("text --%s on --%s is at least 4.5:1", (fg, bg) => {
    expect(contrast(get(fg), get(bg))).toBeGreaterThanOrEqual(4.5);
  });

  it.each(NON_TEXT)("--%s on --%s is at least 3:1", (fg, bg) => {
    expect(contrast(get(fg), get(bg))).toBeGreaterThanOrEqual(3);
  });
});
