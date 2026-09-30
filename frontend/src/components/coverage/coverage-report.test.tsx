// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { Schemas } from "@/api/client";
import { CoverageReport } from "./coverage-report";
import fixture from "./coverage-fixture.json";
import { count, percent, signed } from "./format";

// The API's own answer (backend/tests/contract/coverage_fixture.py; test_frontend_coverage_fixture.py keeps it
// equal to what GET /coverage serves), so these tests read the contract as served.
const COVERAGE = fixture as unknown as Schemas["CoverageResponse"];

function copy(): Schemas["CoverageResponse"] {
  return structuredClone(COVERAGE);
}

afterEach(cleanup);

function table() {
  return within(screen.getByRole("region", { name: "Coverage table" })).getAllByRole("table")[0]!;
}

function row(venue: string, year: number) {
  const rows = within(table()).getAllByRole("row");
  const found = rows.find((r) => {
    const cells = within(r).queryAllByRole("rowheader");
    return cells[0]?.textContent === venue && r.querySelector("td")?.textContent === String(year);
  });
  if (!found) throw new Error(`no row for ${venue} ${year}`);
  return found;
}

describe("the venue × year table", () => {
  it("shows every venue-year's numbers exactly as the API gives them", () => {
    render(<CoverageReport coverage={COVERAGE} />);
    for (const vy of COVERAGE.venue_years) {
      const cells = [...row(vy.venue, vy.year).querySelectorAll("td")].map((td) => td.textContent);
      const flagged = vy.records > 0 && vy.abstract_missing === vy.records;
      expect(cells.slice(0, 6)).toEqual([
        String(vy.year),
        count(vy.records),
        flagged
          ? `⚠ ${count(vy.abstract_missing)}no abstracts: only titles are searchable`
          : count(vy.abstract_missing),
        count(vy.unknown_track),
        count(vy.unknown_status),
        vy.statuses_indexed.join(", "),
      ]);
    }
  });

  it("orders rows by venue, then newest year first, and names its region, caption and headers", () => {
    render(<CoverageReport coverage={COVERAGE} />);
    const region = screen.getByRole("region", { name: "Coverage table" });
    expect(region.getAttribute("tabindex")).toBe("0");
    expect(within(table()).getByText(COVERAGE.snapshot.name).closest("caption")).not.toBeNull();
    const heads = within(table()).getAllByRole("rowheader");
    const years = [...table().querySelectorAll("tbody tr")].map((tr) =>
      Number(tr.querySelector("td")?.textContent),
    );
    const order = heads.map((h, i) => [h.textContent ?? "", years[i]!] as const);
    const expected = COVERAGE.venue_years
      .map((vy) => [vy.venue, vy.year] as const)
      .sort((a, b) => (a[0] === b[0] ? b[1] - a[1] : a[0] < b[0] ? -1 : 1));
    expect(order).toEqual(expected);
    for (const th of within(table()).getAllByRole("columnheader"))
      expect(th.getAttribute("scope")).toBe("col");
  });

  it("flags a venue-year with no abstracts at all, and only that one", () => {
    const data = copy();
    const vy = data.venue_years.find((v) => v.abstract_missing < v.records)!;
    vy.abstract_missing = vy.records;
    render(<CoverageReport coverage={data} />);
    expect(row(vy.venue, vy.year).textContent).toContain("no abstracts: only titles are searchable");
    const others = data.venue_years.filter((v) => v.abstract_missing < v.records);
    expect(others.length).toBeGreaterThan(0);
    for (const v of others) expect(row(v.venue, v.year).textContent).not.toContain("no abstracts");
  });
});

describe("a venue-year's details", () => {
  it("is a disclosure that shows track × status from the cells, with – for no cell", () => {
    render(<CoverageReport coverage={COVERAGE} />);
    const vy = COVERAGE.venue_years.find((v) => v.tracks.length > 1) ?? COVERAGE.venue_years[0]!;
    const button = screen.getByRole("button", {
      name: `Details: track and status for ${vy.venue} ${vy.year}`,
    });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(button);
    expect(button.getAttribute("aria-expanded")).toBe("true");
    const detail = document.getElementById(button.getAttribute("aria-controls")!)!;
    const byStatus = within(detail).getByRole("table", {
      name: `${vy.venue} ${vy.year}: records by track and status`,
    });
    const header = within(byStatus)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(header).toEqual(["Track", ...vy.statuses_indexed, "Records", "No abstract", "Sources"]);
    const body = within(byStatus).getAllByRole("row").slice(1);
    expect(body.map((r) => within(r).getByRole("rowheader").textContent)).toEqual(
      vy.tracks.map((t) => t.track),
    );
    body.forEach((r, i) => {
      const track = vy.tracks[i]!;
      const shown = [...r.querySelectorAll("td")].map((td) => td.textContent);
      const expected = vy.statuses_indexed.map((status) => {
        const cell = vy.cells.find((c) => c.track === track.track && c.status === status);
        return cell ? count(cell.count) : "–none";
      });
      expect(shown).toEqual([
        ...expected,
        count(track.records),
        count(track.abstract_missing),
        track.sources.join(", "),
      ]);
    });
    fireEvent.click(button);
    expect(document.getElementById(button.getAttribute("aria-controls")!)).toBeNull();
  });

  it("shows each track against its official count: not gated without one", () => {
    render(<CoverageReport coverage={COVERAGE} />);
    const vy = COVERAGE.venue_years[0]!;
    fireEvent.click(
      screen.getByRole("button", { name: `Details: track and status for ${vy.venue} ${vy.year}` }),
    );
    const official = screen.getByRole("table", {
      name: `${vy.venue} ${vy.year}: accepted records against the official count`,
    });
    const rows = within(official).getAllByRole("row").slice(1);
    rows.forEach((r, i) => {
      const track = vy.tracks[i]!;
      const shown = [...r.querySelectorAll("td")].map((td) => td.textContent);
      expect(shown).toEqual([count(track.indexed_accepted), "no official count", "–none", "not gated"]);
    });
  });

  it("shows an official count with its citation, difference and gate verdict", () => {
    const data = copy();
    const vy = data.venue_years[0]!;
    const [first] = vy.tracks;
    Object.assign(first!, {
      official_accepted: 1234,
      official_counts: "orals and posters",
      official_citation: "https://example.org/stats",
      official_accessed: "2026-09-01",
      delta: -13,
      delta_pct: -1.0535,
      gated: true,
      within_gate: false,
    });
    render(<CoverageReport coverage={data} />);
    fireEvent.click(
      screen.getByRole("button", { name: `Details: track and status for ${vy.venue} ${vy.year}` }),
    );
    const official = screen.getByRole("table", {
      name: `${vy.venue} ${vy.year}: accepted records against the official count`,
    });
    const cells = [...within(official).getAllByRole("row")[1]!.querySelectorAll("td")].map(
      (td) => td.textContent,
    );
    expect(cells).toEqual([
      count(first!.indexed_accepted),
      "1,234orals and posters; https://example.org/stats, read 2026-09-01",
      `${signed(-13)} (${percent(-1.0535)})`,
      "✗ outside the gate",
    ]);
    expect(
      within(official).getByRole("link", { name: "https://example.org/stats" }).getAttribute("href"),
    ).toBe("https://example.org/stats");
  });
});

describe("the header", () => {
  it("names the index, snapshot, build time, windows and sources from the snapshot facts", () => {
    render(<CoverageReport coverage={COVERAGE} />);
    const text = document.body.textContent ?? "";
    const s = COVERAGE.snapshot;
    expect(text).toContain(`Index ${COVERAGE.index_version}`);
    expect(text).toContain(
      `tokenizer ${COVERAGE.tokenizer_version} · query version ${COVERAGE.query_version}`,
    );
    expect(text).toContain(s.snapshot_hash);
    expect(text).toContain(`Built ${s.built_at.slice(0, 10)} ${s.built_at.slice(11, 16)} UTC`);
    // the fixture is RIS-only: its window is when the Scholar searches were run, never a crawl
    expect(s.crawl_dates_kind["*"]).toBe("scholar_query_dates");
    // a window within one day is written once, with "on"
    expect(s.crawl_dates["*"]!.from.slice(0, 10)).toBe(s.crawl_dates["*"]!.to.slice(0, 10));
    expect(text).toContain(`Google Scholar searches run on ${s.crawl_dates["*"]!.from.slice(0, 10)}`);
    expect(text).toContain(`ris: Google Scholar searches run on ${s.crawl_dates.ris!.from.slice(0, 10)}`);
    expect(text).not.toMatch(/Crawled/);
    expect(text).toContain(`Sources: ${s.sources.join(", ")}`);
    expect(text).toContain("its counts are not PRISMA identification numbers");
    const t = COVERAGE.totals;
    expect(text).toContain(
      `${count(t.records)} records · ${count(t.abstract_missing)} without an abstract · ` +
        `${count(t.unknown_track)} of unknown track · ${count(t.unknown_status)} of unknown status`,
    );
  });

  it("counts abstracts removed at a rights holder's request only when there are any (TASK-136, CV-6)", () => {
    expect(COVERAGE.totals.abstract_withheld).toBe(0);
    render(<CoverageReport coverage={COVERAGE} />);
    expect(document.body.textContent).not.toMatch(/rights holder|removed on request/);
    cleanup();
    const c = copy();
    const vy = c.venue_years.find((v) => v.records > v.abstract_missing + 2)!;
    const track = vy.tracks[0]!;
    c.totals.abstract_withheld = 2;
    vy.abstract_withheld = 2;
    track.abstract_withheld = 2;
    render(<CoverageReport coverage={c} />);
    expect(document.body.textContent).toContain(
      "of unknown status · 2 with the abstract removed at a rights holder's request",
    );
    const noAbstract = [...row(vy.venue, vy.year).querySelectorAll("td")][2]!;
    expect(noAbstract.textContent).toContain(`${count(vy.abstract_missing)}and 2 removed on request`);
    // a venue-year whose every record lacks a shown abstract, removed ones included, is flagged (CV-5)
    cleanup();
    const all = copy();
    const flagged = all.venue_years.find((v) => v.records > v.abstract_missing)!;
    flagged.abstract_withheld = flagged.records - flagged.abstract_missing;
    render(<CoverageReport coverage={all} />);
    expect([...row(flagged.venue, flagged.year).querySelectorAll("td")][2]!.textContent).toContain(
      "no abstracts: only titles are searchable",
    );
  });

  it("says Crawled for a crawl and drops the citability note for a citable snapshot", () => {
    const data = copy();
    data.snapshot.crawl_dates_kind = { "*": "crawl", ris: "crawl" };
    data.snapshot.identification_citable = true;
    render(<CoverageReport coverage={data} />);
    const text = document.body.textContent ?? "";
    expect(text).toContain("Crawled ");
    expect(text).not.toContain("PRISMA identification numbers");
  });

  it("writes a window over several days from its start to its end", () => {
    const data = copy();
    const window = { from: "2026-09-20T08:14:03Z", to: "2026-09-26T23:59:00Z" };
    data.snapshot.crawl_dates = { "*": window, ris: window };
    data.snapshot.crawl_dates_kind = { "*": "crawl", ris: "crawl" };
    render(<CoverageReport coverage={data} />);
    expect(screen.getByText(/^Built /).textContent).toContain(" · Crawled 2026-09-20 to 2026-09-26");
    expect(document.body.textContent).toContain("ris: Crawled 2026-09-20 to 2026-09-26");
  });
});

describe("no hard-coded numbers (TASK-045 AC1)", () => {
  it("every number on the page, details open, is one of the API's", () => {
    render(<CoverageReport coverage={COVERAGE} />);
    for (const b of screen.getAllByRole("button", { name: /^Details/ })) fireEvent.click(b);
    const served = JSON.stringify(COVERAGE);
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const numbers: string[] = [];
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      numbers.push(...(node.textContent?.match(/\d[\d,]*/g) ?? []));
    }
    expect(numbers.length).toBeGreaterThan(100);
    for (const n of new Set(numbers)) expect(served, n).toContain(n.replaceAll(",", ""));
  });
});
