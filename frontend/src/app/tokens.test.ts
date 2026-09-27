/**
 * Contrast of the design tokens in globals.css, both themes (ui-design-system skill; spec 05 WCAG 2.2 AA):
 * text on its background ≥ 4.5:1, borders/focus/icons ≥ 3:1. Colours are oklch() without alpha; the
 * conversion is the OKLab → linear sRGB matrix from Björn Ottosson's reference, then WCAG relative luminance.
 *
 * The focus ring is checked as drawn: globals.css draws it at full opacity (`:focus-visible` below), and
 * no source file may draw it through an alpha modifier such as shadcn's `focus-visible:ring-ring/50`, which
 * would halve its contrast. Every token must also be inside the sRGB gamut, so the contrast computed here
 * is the contrast the browser shows (no silent clamping).
 */
import { readFileSync, readdirSync } from "node:fs";
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

/** Linear sRGB, unclamped, so the gamut check can see values outside [0, 1]. */
function linearRgb([L = 0, C = 0, h = 0]: number[]): [number, number, number] {
  const a = C * Math.cos((h * Math.PI) / 180);
  const b = C * Math.sin((h * Math.PI) / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  return [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
}

function luminance(color: number[]): number {
  const [r, g, b] = linearRgb(color);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
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
  ["muted-foreground", "card"],
  ["muted-foreground", "muted"],
  ["accent-foreground", "accent"],
  ["destructive", "background"],
  ["hl-fg", "hl-bg"],
  ["warn-fg", "warn-bg"],
  ["excluded-fg", "excluded-bg"],
  ["default-clause", "background"],
  ["track-workshop", "background"],
];

/** Every surface a control (and so its border and focus ring) can sit on. */
const SURFACES = ["background", "card", "popover", "muted", "warn-bg", "excluded-bg"];

const NON_TEXT: [string, string][] = [
  ...["border", "input", "ring"].flatMap((fg) => SURFACES.map((bg): [string, string] => [fg, bg])),
  ["primary", "background"], // the selected theme option's fill
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

  it.each([...tokens.keys()])("--%s is inside the sRGB gamut", (name) => {
    for (const channel of linearRgb(get(name))) {
      expect(channel).toBeGreaterThanOrEqual(-1e-4);
      expect(channel).toBeLessThanOrEqual(1 + 1e-4);
    }
  });
});

describe("the focus ring is drawn at full opacity", () => {
  it("globals.css draws :focus-visible as a solid 2px --ring outline", () => {
    const rule = /:focus-visible\s*\{([^}]*)\}/.exec(css)?.[1] ?? "";
    expect(rule).toMatch(/outline:\s*2px solid var\(--ring\)/);
    expect(rule).toMatch(/outline-offset:\s*2px/);
  });

  function sources(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
      const p = path.join(dir, e.name);
      if (e.isDirectory()) return sources(p);
      return /\.(tsx?|css)$/.test(e.name) && !e.name.endsWith(".test.ts") ? [p] : [];
    });
  }

  // shadcn's generated components default to `focus-visible:ring-ring/50` and `outline-ring/50`.
  const src = path.join(import.meta.dirname, "..");
  it.each(sources(src).map((f) => path.relative(src, f)))("%s has no translucent ring or outline", (file) => {
    const text = readFileSync(path.join(src, file), "utf8");
    expect(text).not.toMatch(/\b(?:ring|outline)-ring\/\d+/);
  });
});
