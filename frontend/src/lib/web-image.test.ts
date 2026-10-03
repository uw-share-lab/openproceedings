/**
 * The `web` image's build gate (TASK-136 AC9, decision-018; spec 08 §Deploy): `deploy/web-build-gate.sh` refuses
 * a build that doesn't say whether the instance is public, and a public one without a takedown contact;
 * `deploy/web.Dockerfile` takes both as build arguments, runs the gate before installing anything, and hands
 * them to `next build` (whose `next.config.ts` checks them again). `.dockerignore` keeps the data directory,
 * the takedown log and `.env` files out of the build context.
 */
import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const ROOT = path.join(import.meta.dirname, "..", "..", "..");
const GATE = path.join(ROOT, "deploy", "web-build-gate.sh");
const DOCKERFILE = readFileSync(path.join(ROOT, "deploy", "web.Dockerfile"), "utf8");

function gate(env: Record<string, string>) {
  // only these variables: nothing from the test's own environment reaches the gate
  const clean = { PATH: process.env.PATH ?? "", ...env } as unknown as NodeJS.ProcessEnv;
  const run = spawnSync("sh", [GATE], { env: clean, encoding: "utf8" });
  return { status: run.status, err: run.stderr, out: run.stdout };
}

describe("deploy/web-build-gate.sh", () => {
  it("refuses a build that doesn't say what kind of instance it is", () => {
    for (const instance of [undefined, "", "Public", "prod"]) {
      const r = gate(instance === undefined ? {} : { OPENPROCEEDINGS_INSTANCE: instance });
      expect(r.status).toBe(1);
      expect(r.err).toContain("set --build-arg OPENPROCEEDINGS_INSTANCE=public");
    }
  });

  it("refuses a public instance without a takedown contact", () => {
    for (const contact of [undefined, "", "   "]) {
      const env: Record<string, string> = { OPENPROCEEDINGS_INSTANCE: "public" };
      if (contact !== undefined) env.NEXT_PUBLIC_TAKEDOWN_CONTACT = contact;
      const r = gate(env);
      expect(r.status).toBe(1);
      expect(r.err).toContain("OPENPROCEEDINGS_INSTANCE=public needs NEXT_PUBLIC_TAKEDOWN_CONTACT");
    }
  });

  it("passes a public instance with a contact and a private one without", () => {
    expect(
      gate({ OPENPROCEEDINGS_INSTANCE: "public", NEXT_PUBLIC_TAKEDOWN_CONTACT: "takedown@example.org" }),
    ).toMatchObject({ status: 0, out: "web image: a public instance, takedown contact set\n" });
    expect(gate({ OPENPROCEEDINGS_INSTANCE: "private" })).toMatchObject({
      status: 0,
      out: "web image: a private instance\n",
    });
  });
});

describe("deploy/web.Dockerfile", () => {
  const lines = DOCKERFILE.split("\n");
  const at = (text: string) => lines.findIndex((l) => l.startsWith(text));

  it("takes the instance kind (no default) and the contact as build arguments", () => {
    expect(lines).toContain("ARG OPENPROCEEDINGS_INSTANCE");
    expect(lines).toContain('ARG NEXT_PUBLIC_TAKEDOWN_CONTACT=""');
    expect(DOCKERFILE).toMatch(/ENV OPENPROCEEDINGS_INSTANCE=\$\{OPENPROCEEDINGS_INSTANCE\}/);
    expect(DOCKERFILE).toMatch(/NEXT_PUBLIC_TAKEDOWN_CONTACT=\$\{NEXT_PUBLIC_TAKEDOWN_CONTACT\}/);
  });

  it("runs the gate before installing or building anything", () => {
    const gateAt = at("RUN sh deploy/web-build-gate.sh");
    expect(gateAt).toBeGreaterThan(at("ENV OPENPROCEEDINGS_INSTANCE="));
    expect(gateAt).toBeGreaterThan(-1);
    expect(gateAt).toBeLessThan(at("RUN npm ci"));
    expect(at("RUN npm ci")).toBeLessThan(at("RUN npm run build --workspace frontend"));
  });

  it("ignores no source file: nothing tracked lies under a data/ or takedowns/ directory but the root data/", () => {
    const tracked = spawnSync("git", ["ls-files"], { cwd: ROOT, encoding: "utf8" }).stdout.split("\n");
    expect(tracked.length).toBeGreaterThan(100);
    const swallowed = tracked.filter((f) => /(^|\/)(data|takedowns)\//i.test(f) && !f.startsWith("data/"));
    expect(swallowed).toEqual([]);
  });

  it("builds from a context that holds no data, takedown log or .env file", () => {
    const ignore = readFileSync(path.join(ROOT, ".dockerignore"), "utf8").split("\n");
    expect(ignore[ignore.findIndex((l) => !l.startsWith("#"))]).toBe("*"); // an allow-list
    for (const kept of ["**/data", "**/takedowns", "**/.env", "**/.env.*"]) expect(ignore).toContain(kept);
  });
});
