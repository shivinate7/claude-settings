// Browser tests for the roadmap page (skill roadmap, page/index.html), as build.py writes it from a fixture repo.
//   NODE_PATH=<dir with playwright> node --test skills/roadmap/tests/page.test.mjs
// The page is built by tests/built_index.py. A stalled read is set on the built page where a case needs one, the
// same way skills/waiting-page/tests/page.test.mjs sets it. No Playwright or no Chromium: skipped on a laptop, a
// fail in CI (testing/skip-locally-fail-in-ci.mjs).
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { needEnv } from "../../../testing/skip-locally-fail-in-ci.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const BUILT = path.join(HERE, "built_index.py");
const ORIGIN = "http://roadmap.test/";
const require = createRequire(import.meta.url);

let browser;
after(async () => { if (browser) await browser.close(); });

// The built page's ROADMAP_BUILD block: the one regex that reads it. withStalled rewrites it.
const BUILD_BLOCK = /window\.ROADMAP_BUILD = (\{.*\});\n<\/script>/;
function withStalled(html, stalled) {
  assert.match(html, BUILD_BLOCK, "the built page has no ROADMAP_BUILD block to set the stalled read on");
  return html.replace(BUILD_BLOCK, (_, j) => {
    const b = JSON.parse(j);
    if (stalled === undefined) delete b.stalled; else b.stalled = stalled;
    return "window.ROADMAP_BUILD = " + JSON.stringify(b).replace(/</g, "\\u003c") + ";\n</script>";
  });
}
// The page built from a fixture: steps by file stem, the live file's text as an object, and the stalled read (optional).
function builtPage({ steps = {}, live, stalled } = {}) {
  const args = [BUILT, "--data", JSON.stringify({ steps, meta: {} })];
  if (live) args.push("--live", JSON.stringify(live));
  const r = spawnSync(process.env.PYTHON || "python3", args, { encoding: "utf8", maxBuffer: 1 << 28 });
  assert.equal(r.status, 0, "the roadmap build failed: " + (r.stderr || r.error));
  return stalled === undefined ? r.stdout : withStalled(r.stdout, stalled);
}
const stepOf = (title, status, order) => ({ title, status, phase: "cleanup", order, note: "n", updatedAt: "2026-10-26T00:00:00Z" });
const NO_ITEMS = { itemsWhy: "" };

async function open(t, html, width = 1280) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  page.setDefaultTimeout(Number(process.env.WP_TIMEOUT) || 5000);
  t.after(() => page.close());
  // The page is served from a stand-in origin; every other request (the fonts) is refused.
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html; charset=utf-8", body: html }) : r.abort()));
  await page.goto(ORIGIN);
  await page.waitForSelector("#now");
  return page;
}
const stall = (page) => page.locator("#stall");
// The stalled band's text on one line. A page with no band fails here by name, before a text read waits out its timeout.
async function stallText(page) {
  assert.equal(await stall(page).count(), 1, "the Plan page draws no stalled band (#stall)");
  return (await stall(page).textContent()).replace(/\s+/g, " ");
}
// The status button of a step's row in the plan list: its label is the status the page says.
const statusLabel = async (page, id) => {
  assert.equal(await page.locator(`#s-${id}`).count(), 1, `step ${id} has no row in the plan list`);
  return page.locator(`#s-${id} .sp`).getAttribute("aria-label");
};

// ---------------------------------------------------------------- the stalled band: items not read (lane doing-needs-live-lane)
test("zero stalled steps with the items not read: the band does not say No stalled step, and shows the items not-read line", async (t) => {
  const steps = { c1: stepOf("Step c1", "todo", 1) };
  const html = builtPage({ steps, stalled: { why: "", steps: [], paused: [], badPause: [], items: null, itemsWhy: "unknown (live file rows carry no lane yet)" } });
  const page = await open(t, html); if (!page) return;
  const text = await stallText(page);
  assert.doesNotMatch(text, /No stalled step/, "the band says No stalled step with its items not read: " + text);
  assert.match(text, /Waiting items/, "the band shows no waiting-items part: " + text);
  assert.match(text, /not read/i, "the waiting-items part does not say not read: " + text);
});

// ---------------------------------------------------------------- the stalled band: a row never reads In progress
// In progress is for a live doing step only. A stalled or paused step reads Stalled or Paused, in its label and its mark.
// Each row's label, and every mark in it, is checked. Index: the same word must be the row's own, not In progress.
async function assertRowReads(page, id, word) {
  assert.match(await statusLabel(page, id), new RegExp(word), `step ${id} does not read ${word} in its status mark`);
  assert.doesNotMatch(await page.locator(`#s-${id}`).textContent(), /In progress/, `the row of step ${id} says In progress`);
  assert.equal(await page.locator(`#s-${id} [aria-label*="In progress"]`).count(), 0, `a mark in the row of step ${id} is labelled In progress`);
}
test("a stalled step's row reads Stalled, never In progress", async (t) => {
  const steps = { c1: stepOf("Step c1", "doing", 1) };
  const page = await open(t, builtPage({ steps, stalled: { why: "", steps: [{ id: "c1", fix: "todo" }], paused: [], badPause: [], items: [], ...NO_ITEMS } })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
});
test("a paused step's row reads Paused, never In progress", async (t) => {
  const steps = { a3: stepOf("Step a3", "doing", 3) };
  const page = await open(t, builtPage({ steps, stalled: { why: "", steps: [], paused: ["a3"], badPause: [], items: [], ...NO_ITEMS } })); if (!page) return;
  await assertRowReads(page, "a3", "Paused");
});

// ---------------------------------------------------------------- the plan list: a live doing step reads In progress
test("a live doing step reads In progress", async (t) => {
  const steps = { a: stepOf("Step a", "doing", 2) };
  // Step a has an open pull request on its branch a, which makes it a live lane.
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a", branch: "a" }], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live })); if (!page) return;
  assert.match(await statusLabel(page, "a"), /In progress/, "step a has a live thread but does not read In progress");
});

// ---------------------------------------------------------------- the plan list: a stalled step is marked at first load, with no live thread
// The build sets the stalled read from the steps and the live file. Step b has no session and no pull request, so no live lane.
test("a stalled step carries the Stalled tag and the Doing now mark at first load, with no live lane", async (t) => {
  const steps = { b: stepOf("Step b", "doing", 3) };
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live })); if (!page) return;
  assert.equal(await page.locator("#s-b .tag.stl").count(), 1, "step b has no live thread, but its row carries no Stalled tag at first load");
  assert.equal(await page.locator('#now li:has(button[data-go="b"]) [role="img"][aria-label="Stalled"]').count(), 1, "step b has no Stalled mark in Doing now at first load");
});

// ---------------------------------------------------------------- the where-you-are line and Latest changes: a stalled step is not in progress
// A stalled step's status is active, so the count and the feed read its stall state, not the raw status.
const STALLED_C1 = { why: "", steps: [{ id: "c1", fix: "todo" }], paused: [], badPause: [], items: [], ...NO_ITEMS };
test("the where-you-are line does not count a stalled step as in progress", async (t) => {
  const steps = { c1: stepOf("Step c1", "doing", 1) };
  const page = await open(t, builtPage({ steps, stalled: STALLED_C1 })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
  assert.ok((await page.locator("#now > div:first-child > .sub").count()) > 0, "the Plan page has no where-you-are line (#now > div:first-child > .sub)");
  const sub = (await page.locator("#now > div:first-child > .sub").first().textContent()).replace(/\s+/g, " ");
  assert.doesNotMatch(sub, /in progress/, "the where-you-are line counts the stalled step as in progress: " + sub);
});
test("the Latest changes row of a stalled step reads Stalled, not In progress", async (t) => {
  const steps = { c1: stepOf("Step c1", "doing", 1) };
  const page = await open(t, builtPage({ steps, stalled: STALLED_C1 })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
  const row = page.locator("#side .feed li", { has: page.locator('button[data-go="c1"]') });
  assert.equal(await row.count(), 1, "step c1 has no row in Latest changes");
  const kind = (await row.locator(".kind").textContent()).trim();
  assert.doesNotMatch(kind, /In progress/, "the Latest changes row of stalled step c1 reads In progress");
  assert.match(kind, /Stalled/, `the Latest changes row of stalled step c1 reads "${kind}", not Stalled`);
});
test("a live doing step still counts as in progress in the where-you-are line", async (t) => {
  const steps = { a: stepOf("Step a", "doing", 2) };
  // Step a has an open pull request on its branch a, which makes it a live lane.
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a", branch: "a" }], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live })); if (!page) return;
  assert.ok((await page.locator("#now > div:first-child > .sub").count()) > 0, "the Plan page has no where-you-are line (#now > div:first-child > .sub)");
  const sub = (await page.locator("#now > div:first-child > .sub").first().textContent()).replace(/\s+/g, " ");
  assert.match(sub, /\b1 in progress/, "the where-you-are line does not count the live doing step as in progress: " + sub);
});
test("the Changes log row of a stalled step reads Stalled, not In progress", async (t) => {
  const steps = { c1: stepOf("Step c1", "doing", 1) };
  const page = await open(t, builtPage({ steps, stalled: STALLED_C1 })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
  const row = page.locator("#days .ev", { has: page.locator('button[data-go="c1"]') });
  assert.equal(await row.count(), 1, "step c1 has no row in the Changes log");
  const kind = (await row.locator(".kind").textContent()).trim();
  assert.doesNotMatch(kind, /In progress/, "the Changes log row of stalled step c1 reads In progress");
  assert.match(kind, /Stalled/, `the Changes log row of stalled step c1 reads "${kind}", not Stalled`);
});
test("a live doing step still reads In progress in the Changes log", async (t) => {
  const steps = { a: stepOf("Step a", "doing", 2) };
  // Step a has an open pull request on its branch a, which makes it a live lane.
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a", branch: "a" }], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live })); if (!page) return;
  const row = page.locator("#days .ev", { has: page.locator('button[data-go="a"]') });
  assert.equal(await row.count(), 1, "step a has no row in the Changes log");
  assert.equal((await row.locator(".kind").textContent()).trim(), "In progress", "the Changes log row of the live doing step does not read In progress");
});

// ---------------------------------------------------------------- paused: a paused step is not in progress in any of the three places
// A paused step keeps status active, as a stalled one does. Paused is its own state in the count, the feed and the log.
const PAUSED_A3 = { why: "", steps: [], paused: ["a3"], badPause: [], items: [], ...NO_ITEMS };
test("the where-you-are line does not count a paused step as in progress", async (t) => {
  const steps = { a3: stepOf("Step a3", "doing", 3) };
  const page = await open(t, builtPage({ steps, stalled: PAUSED_A3 })); if (!page) return;
  await assertRowReads(page, "a3", "Paused");
  assert.ok((await page.locator("#now > div:first-child > .sub").count()) > 0, "the Plan page has no where-you-are line (#now > div:first-child > .sub)");
  const sub = (await page.locator("#now > div:first-child > .sub").first().textContent()).replace(/\s+/g, " ");
  assert.doesNotMatch(sub, /in progress/, "the where-you-are line counts the paused step as in progress: " + sub);
});
test("the Latest changes row of a paused step reads Paused, not In progress", async (t) => {
  const steps = { a3: stepOf("Step a3", "doing", 3) };
  const page = await open(t, builtPage({ steps, stalled: PAUSED_A3 })); if (!page) return;
  await assertRowReads(page, "a3", "Paused");
  const row = page.locator("#side .feed li", { has: page.locator('button[data-go="a3"]') });
  assert.equal(await row.count(), 1, "step a3 has no row in Latest changes");
  const kind = (await row.locator(".kind").textContent()).trim();
  assert.doesNotMatch(kind, /In progress/, "the Latest changes row of paused step a3 reads In progress");
  assert.match(kind, /Paused/, `the Latest changes row of paused step a3 reads "${kind}", not Paused`);
});
test("the Changes log row of a paused step reads Paused, not In progress", async (t) => {
  const steps = { a3: stepOf("Step a3", "doing", 3) };
  const page = await open(t, builtPage({ steps, stalled: PAUSED_A3 })); if (!page) return;
  await assertRowReads(page, "a3", "Paused");
  const row = page.locator("#days .ev", { has: page.locator('button[data-go="a3"]') });
  assert.equal(await row.count(), 1, "step a3 has no row in the Changes log");
  const kind = (await row.locator(".kind").textContent()).trim();
  assert.doesNotMatch(kind, /In progress/, "the Changes log row of paused step a3 reads In progress");
  assert.match(kind, /Paused/, `the Changes log row of paused step a3 reads "${kind}", not Paused`);
});
test("a live doing step reads In progress in all three places", async (t) => {
  const steps = { a: stepOf("Step a", "doing", 2) };
  // Step a has an open pull request on its branch a, which makes it a live lane.
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a", branch: "a" }], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live })); if (!page) return;
  assert.ok((await page.locator("#now > div:first-child > .sub").count()) > 0, "the Plan page has no where-you-are line (#now > div:first-child > .sub)");
  const sub = (await page.locator("#now > div:first-child > .sub").first().textContent()).replace(/\s+/g, " ");
  assert.match(sub, /\b1 in progress/, "the where-you-are line does not count the live doing step: " + sub);
  const feed = page.locator("#side .feed li", { has: page.locator('button[data-go="a"]') });
  assert.equal((await feed.locator(".kind").textContent()).trim(), "In progress", "the Latest changes row of the live doing step does not read In progress");
  const log = page.locator("#days .ev", { has: page.locator('button[data-go="a"]') });
  assert.equal((await log.locator(".kind").textContent()).trim(), "In progress", "the Changes log row of the live doing step does not read In progress");
});

// ---------------------------------------------------------------- the phase bars: a stalled or paused step is not an active cell
// Each bar draws one cell per step: done, then active, then blocked. A stalled or paused step keeps status active, so a bar that counts
// the status alone draws it as active. The bars are aria-hidden, so the cells are read by their class. Step a is in progress, not stalled.
const STALLED_C1_PAUSED_A3 = { why: "", steps: [{ id: "c1", fix: "todo" }], paused: ["a3"], badPause: [], items: [], ...NO_ITEMS };
const barSteps = () => ({ c1: stepOf("Step c1", "doing", 1), a: stepOf("Step a", "doing", 2), a3: stepOf("Step a3", "doing", 3) });
async function barActCells(page, scope) {
  assert.equal(await page.locator(`${scope} .bar`).count(), 1, `${scope} has no phase bar (.bar)`);
  return page.locator(`${scope} .bar i.act`).count();
}
// The scope and the control, shared by both bars: c1 Stalled, a3 Paused, a In progress, and the where-you-are bar already draws one active cell.
async function barControls(page) {
  await assertRowReads(page, "c1", "Stalled");
  await assertRowReads(page, "a3", "Paused");
  assert.match(await statusLabel(page, "a"), /In progress/, "step a is not In progress, so the bar has no genuinely active step to count");
  assert.equal(await barActCells(page, "#now"), 1, "the where-you-are bar does not draw the one step in progress as its one active cell");
}
test("the rail's phase bar draws no stalled or paused step as active", async (t) => {
  const page = await open(t, builtPage({ steps: barSteps(), stalled: STALLED_C1_PAUSED_A3 })); if (!page) return;
  await barControls(page);
  const act = await barActCells(page, '#rail button[data-phase="cleanup"]');
  assert.equal(act, 1, `the rail's cleanup bar draws ${act} active cells for one step in progress: a stalled or paused step is drawn as active`);
});
test("the phase head's bar draws no stalled or paused step as active", async (t) => {
  const page = await open(t, builtPage({ steps: barSteps(), stalled: STALLED_C1_PAUSED_A3 })); if (!page) return;
  await barControls(page);
  const act = await barActCells(page, "#phases .ph-head");
  assert.equal(act, 1, `the phase head's bar draws ${act} active cells for one step in progress: a stalled or paused step is drawn as active`);
});

// ---------------------------------------------------------------- stalled and paused read apart (lane nfp-stalled-kind-color)
// The design (the hatch-and-ring option, as the notes record it): a stalled label is --bad, as the blocked label is; each bar cell is
// its own shape. The colour is read from the page's own --bad token, so a token change moves the test with it.
// A CSS value as the browser computes it on an element: a probe span takes the value inside that element, so a token set on the element
// resolves as it does there. The probe is removed before the read returns. Two computed values compare as strings.
const probeOf = (loc, prop, value) => loc.evaluate((el, [p, v]) => {
  const s = document.createElement("span");
  s.style[p] = v;
  el.appendChild(s);
  const out = getComputedStyle(s)[p];
  s.remove();
  return out;
}, [prop, value]);
const computedOf = (loc, prop) => loc.evaluate((el, p) => getComputedStyle(el)[p], prop);
const badColour = (page) => probeOf(page.locator("body"), "color", "var(--bad)");
const colourOf = (loc) => loc.evaluate((el) => getComputedStyle(el).color);
const feedKind = (page, id) => page.locator("#side .feed li", { has: page.locator(`button[data-go="${id}"]`) }).locator(".kind");
const logKind = (page, id) => page.locator("#days .ev", { has: page.locator(`button[data-go="${id}"]`) }).locator(".kind");
const KIND_FIXTURE = { c1: stepOf("Step c1", "doing", 1), b2: stepOf("Step b2", "blocked", 2) };
for (const scheme of ["light", "dark"]) {
  test(`control: the Blocked label computes to the --bad colour in ${scheme}`, async (t) => {
    const page = await open(t, builtPage({ steps: KIND_FIXTURE, stalled: STALLED_C1 })); if (!page) return;
    await page.emulateMedia({ colorScheme: scheme });
    const bad = await badColour(page);
    assert.equal(await feedKind(page, "b2").count(), 1, "step b2 has no row in Latest changes");
    assert.equal(await colourOf(feedKind(page, "b2")), bad, `the Blocked label is not --bad in ${scheme}: the colour probe reads wrong`);
  });
  test(`the Stalled label of a stalled step computes to the --bad colour in ${scheme}`, async (t) => {
    const page = await open(t, builtPage({ steps: KIND_FIXTURE, stalled: STALLED_C1 })); if (!page) return;
    await page.emulateMedia({ colorScheme: scheme });
    const bad = await badColour(page);
    for (const [where, kind] of [["Latest changes", feedKind(page, "c1")], ["Changes log", logKind(page, "c1")]]) {
      assert.equal(await kind.count(), 1, `the ${where} has no row for stalled step c1`);
      assert.equal(await colourOf(kind), bad, `the ${where} label of stalled step c1 is not --bad in ${scheme}`);
    }
  });
}

// ---------------------------------------------------------------- the row tint: a stalled row takes the stalled colour, a paused row none (lane nfp-stalled-row-tint)
// The tint and the edge are on the row's .rw. A stalled row takes --bad-soft and a 3px left edge in --bad. A paused row takes no tint and a
// 3px left edge in --muted. An in-progress row keeps --accent-soft and --accent. A to-do row takes neither. Each expected value is the page's own token, computed on
// the row, in each scheme. The row's status is checked first, so a red names the tint or the edge and not the label.
test("the row tint: a stalled row's background is --bad-soft and its left edge --bad, in light and dark", async (t) => {
  const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "doing", 1) }, stalled: STALLED_C1 })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
  const row = page.locator("#s-c1 .rw");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", "var(--bad-soft)");
    assert.equal(bg, wantBg, `in ${scheme} the stalled row's background is ${bg}, not the --bad-soft tint ${wantBg}`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "inset 3px 0 0 var(--bad)");
    assert.equal(edge, wantEdge, `in ${scheme} the stalled row's left edge is ${edge}, not the 3px --bad edge ${wantEdge}`);
  }
});
test("the row tint: a paused row takes no tint and a 3px left edge in --muted, in light and dark", async (t) => {
  const page = await open(t, builtPage({ steps: { a3: stepOf("Step a3", "doing", 3) }, stalled: PAUSED_A3 })); if (!page) return;
  await assertRowReads(page, "a3", "Paused");
  const row = page.locator("#s-a3 .rw");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", "transparent");
    assert.equal(bg, wantBg, `in ${scheme} the paused row keeps a tint: its background is ${bg}, not none`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "inset 3px 0 0 var(--muted)");
    assert.equal(edge, wantEdge, `in ${scheme} the paused row's left edge is ${edge}, not the 3px --muted edge ${wantEdge}`);
  }
});
test("control: the row tint: an in-progress row keeps the --accent-soft tint and its 3px --accent edge, in light and dark", async (t) => {
  const steps = { a: stepOf("Step a", "doing", 2) };
  // Step a has an open pull request on its branch a, which makes it a live lane.
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a", branch: "a" }], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live })); if (!page) return;
  assert.match(await statusLabel(page, "a"), /In progress/, "step a has a live thread but does not read In progress");
  const row = page.locator("#s-a .rw");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", "var(--accent-soft)");
    assert.equal(bg, wantBg, `in ${scheme} the in-progress row's background is ${bg}, not the --accent-soft tint ${wantBg}`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "inset 3px 0 0 var(--accent)");
    assert.equal(edge, wantEdge, `in ${scheme} the in-progress row's left edge is ${edge}, not the 3px --accent edge ${wantEdge}`);
  }
});

test("control: the row tint: a to-do row beside a stalled one keeps no tint and no stalled edge, in light and dark", async (t) => {
  const steps = { c1: stepOf("Step c1", "doing", 1), t2: stepOf("Step t2", "todo", 2) };
  const page = await open(t, builtPage({ steps, stalled: STALLED_C1 })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
  assert.match(await statusLabel(page, "t2"), /To do/, "step t2 does not read To do");
  const row = page.locator("#s-t2 .rw");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const bg = await computedOf(row, "backgroundColor"), wantBg = await probeOf(row, "backgroundColor", "transparent");
    assert.equal(bg, wantBg, `in ${scheme} the to-do row takes a tint: its background is ${bg}, not none`);
    const edge = await computedOf(row, "boxShadow"), wantEdge = await probeOf(row, "boxShadow", "none");
    assert.equal(edge, wantEdge, `in ${scheme} the to-do row has a left edge ${edge}, not none`);
  }
});
// A paused title keeps the in-progress title's weight: it is read against that title, not against a literal.
test("the row tint: a paused row's title has the in-progress title's font weight", async (t) => {
  const steps = { a: stepOf("Step a", "doing", 2), a3: stepOf("Step a3", "doing", 3) };
  // Step a has an open pull request on its branch a, which makes it a live lane.
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a", branch: "a" }], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live, stalled: PAUSED_A3 })); if (!page) return;
  await assertRowReads(page, "a3", "Paused");
  assert.match(await statusLabel(page, "a"), /In progress/, "step a does not read In progress: there is no in-progress title to compare with");
  const paused = await computedOf(page.locator("#s-a3 .ttl"), "fontWeight"), active = await computedOf(page.locator("#s-a .ttl"), "fontWeight");
  assert.equal(paused, active, `the paused step's title is weight ${paused}, not the in-progress title's ${active}`);
});
// The paused title's match with the in-progress title means something only if that title is bolder than a plain one. With both titles
// plain, the paused match above passes, so this case fails: it is the anchor for that match.
test("the row tint: the in-progress title is bolder than a to-do title", async (t) => {
  const steps = { a: stepOf("Step a", "doing", 2), t9: stepOf("Step t9", "todo", 9) };
  // Step a has an open pull request on its branch a, which makes it a live lane.
  const live = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a", branch: "a" }], branches: [], sessions: [] };
  const page = await open(t, builtPage({ steps, live })); if (!page) return;
  assert.match(await statusLabel(page, "a"), /In progress/, "step a does not read In progress: there is no in-progress title to compare with");
  assert.match(await statusLabel(page, "t9"), /To do/, "step t9 does not read To do: there is no to-do title to compare with");
  const active = await computedOf(page.locator("#s-a .ttl"), "fontWeight"), todo = await computedOf(page.locator("#s-t9 .ttl"), "fontWeight");
  assert.ok(Number(active) > Number(todo), `the in-progress title is weight ${active}, not bolder than the to-do title's ${todo}`);
});
// The Stalled pill sits on its row's --bad-soft tint. Its own fill is --bad-soft too, so it vanishes unless the rule that sets it to --surface applies.
// The pill's fill is read on .tag.stl and the row's on .rw. Each expected value is a probe of the page's own token, taken on the element it is compared with.
test("the Stalled pill on a stalled row has its own fill, --surface, not the row's --bad-soft tint, in light and dark", async (t) => {
  const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "doing", 1) }, stalled: STALLED_C1 })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
  assert.equal(await page.locator("#s-c1 .tag.stl").count(), 1, "step c1 has no Stalled pill in its row: there is no pill fill to read");
  const pill = page.locator("#s-c1 .tag.stl"), row = page.locator("#s-c1 .rw");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const fill = await computedOf(pill, "backgroundColor"), rowFill = await computedOf(row, "backgroundColor");
    assert.notEqual(fill, rowFill, `in ${scheme} the Stalled pill's fill is ${fill}, the same as its stalled row's: the pill does not show on its row`);
    const wantFill = await probeOf(pill, "backgroundColor", "var(--surface)");
    assert.equal(fill, wantFill, `in ${scheme} the Stalled pill's fill is ${fill}, not --surface ${wantFill}`);
  }
});
// Control for the pill fill above: the Stalled label on the same pill is --bad, so the locator and the probe read the pill right.
test("control: the Stalled pill's label on a stalled row computes to --bad, in light and dark", async (t) => {
  const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "doing", 1) }, stalled: STALLED_C1 })); if (!page) return;
  await assertRowReads(page, "c1", "Stalled");
  assert.equal(await page.locator("#s-c1 .tag.stl").count(), 1, "step c1 has no Stalled pill in its row: there is no pill label to read");
  const pill = page.locator("#s-c1 .tag.stl");
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const colour = await computedOf(pill, "color"), wantColour = await probeOf(pill, "color", "var(--bad)");
    assert.equal(colour, wantColour, `in ${scheme} the Stalled pill's label is ${colour}, not --bad ${wantColour}`);
  }
});

// One cell per step, in the order done, in progress, stalled, paused, blocked, to do. Three bars: the Now card, the rail's cleanup
// button and the phase head. The fixture is a full phase of 30 steps: 1 done, a2 live (in progress), s3 stalled, p4 paused, 26 to do.
const BARS = [["the Now card's bar", "#now .bar"], ["the rail's cleanup bar", '#rail button[data-phase="cleanup"] .bar'], ["the phase head's bar", "#phases .ph-head .bar"]];
// c1 is named here: make_repo adds its own to-do c1 to any fixture that does not name one.
const barFixture = () => ({
  c1: stepOf("Step c1", "todo", 1), d1: stepOf("Step d1", "done", 1), a2: stepOf("Step a2", "doing", 2), s3: stepOf("Step s3", "doing", 3), p4: stepOf("Step p4", "doing", 4),
  ...Object.fromEntries(Array.from({ length: 25 }, (_, i) => ["t" + (i + 5), stepOf("Step t" + (i + 5), "todo", i + 5)])),
});
const BAR_LIVE = { readAt: new Date().toISOString(), threads: [], pulls: [{ number: 7, title: "Step a2", branch: "a2" }], branches: [], sessions: [] };
const STALLED_S3_P4 = { why: "", steps: [{ id: "s3", fix: "todo" }], paused: ["p4"], badPause: [], items: [], ...NO_ITEMS };
const cellKinds = (page, scope) => page.locator(`${scope} > i`).evaluateAll((els) => els.map((e) => e.className));
const BAR_ORDER = ["done", "act", "stl", "pzd", ...Array(26).fill("")];
test("the bars draw a stalled and a paused step as their own cells, in the order done, in progress, stalled, paused, to do", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  for (const [name, scope] of BARS) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await cellKinds(page, scope), BAR_ORDER, `${name} does not draw a stalled or paused step as its own cell, in order`);
  }
});
// A blocked step is drawn after the paused cell, so the order holds on all three bars with a blocked step among the others.
const barFixtureBlocked = () => ({ ...barFixture(), t5: stepOf("Step t5", "blocked", 5) });
test("the bars draw a blocked step after a stalled and a paused one, in the order done, in progress, stalled, paused, blocked, to do", async (t) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  for (const [name, scope] of BARS) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await cellKinds(page, scope), ["done", "act", "stl", "pzd", "blk", ...Array(25).fill("")], `${name} does not draw the blocked step after the paused one, in order`);
  }
});
test("a stalled cell and a paused cell look different from a to-do cell in each bar", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  const look = (loc) => loc.evaluate((el) => { const s = getComputedStyle(el); return [s.backgroundImage, s.backgroundColor, s.boxShadow].join(" | "); });
  for (const [name, scope] of BARS) {
    const todo = page.locator(`${scope} > i:not([class])`);
    const plainCount = await todo.count();
    assert.equal(plainCount, 26, `${name} draws ${plainCount} to-do cells, not 26: a stalled or paused step is drawn as to do`);
    const plain = await look(todo.first());
    assert.equal(await page.locator(`${scope} > i.stl`).count(), 1, `${name} draws no stalled cell (i.stl)`);
    assert.equal(await page.locator(`${scope} > i.pzd`).count(), 1, `${name} draws no paused cell (i.pzd)`);
    assert.notEqual(await look(page.locator(`${scope} > i.stl`)), plain, `${name}: the stalled cell looks like a to-do cell`);
    assert.notEqual(await look(page.locator(`${scope} > i.pzd`)), plain, `${name}: the paused cell looks like a to-do cell`);
  }
});
test("control: a phase with nothing stalled or paused draws no stalled or paused cell in any bar", async (t) => {
  const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "todo", 1), d1: stepOf("Step d1", "done", 1), a2: stepOf("Step a2", "doing", 2) }, live: BAR_LIVE })); if (!page) return;
  for (const [name, scope] of BARS) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await cellKinds(page, scope), ["done", "act", ""], `${name} draws a stalled or paused cell with none stalled or paused`);
  }
});

// The blocked step: a phase bar draws it as blocked. The rail already does; it is the control.
test("the Now card's bar and the phase head's bar draw a blocked step as blocked, not as to do", async (t) => {
  const page = await open(t, builtPage({ steps: { d1: stepOf("Step d1", "done", 1), b2: stepOf("Step b2", "blocked", 2), t3: stepOf("Step t3", "todo", 3) } })); if (!page) return;
  for (const [name, scope] of [BARS[0], BARS[2]]) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.equal(await page.locator(`${scope} > i.blk`).count(), 1, `${name} draws the blocked step as to do: no blocked cell (i.blk)`);
  }
});
test("control: the rail's cleanup bar draws a blocked step as blocked", async (t) => {
  const page = await open(t, builtPage({ steps: { d1: stepOf("Step d1", "done", 1), b2: stepOf("Step b2", "blocked", 2), t3: stepOf("Step t3", "todo", 3) } })); if (!page) return;
  assert.equal(await page.locator(BARS[1][1]).count(), 1, "the rail has no cleanup bar");
  assert.equal(await page.locator(`${BARS[1][1]} > i.blk`).count(), 1, "the rail's cleanup bar does not draw the blocked step as blocked");
});

// The rail's label names the in-progress step too, as its bar draws it: barFixture has a2 in progress (the phase head's label already does).
test("the rail's cleanup button names its in-progress steps in its label, as its bar draws them", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  assert.equal(await barActCells(page, '#rail button[data-phase="cleanup"]'), 1, "the rail's cleanup bar does not draw the in-progress step (i.act)");
  const label = (await page.locator('#rail button[data-phase="cleanup"]').getAttribute("aria-label")) || "";
  assert.match(label, /\b1 in progress\b/, `the rail's cleanup label does not name the in-progress step: "${label}"`);
});
// The words: the rail's label, the bars' labels and the Now card's count line name the stalled and paused steps.
test("the rail's cleanup button names its stalled and paused steps in its label", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  const btn = page.locator('#rail button[data-phase="cleanup"]');
  assert.equal(await btn.count(), 1, "the rail has no cleanup button");
  assert.match((await btn.getAttribute("aria-label")) || "", /1 stalled, 1 paused/, "the rail's cleanup label does not name the stalled and paused steps");
});
// The rail's label names a blocked step in the form of the stalled and paused words, when the rail's bar draws a blocked cell.
test("the rail's cleanup button names its blocked step in its label, as its bar draws it", async (t) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  assert.equal(await page.locator(`${BARS[1][1]} > i.blk`).count(), 1, "the rail's cleanup bar draws no blocked cell (i.blk)");
  const label = (await page.locator('#rail button[data-phase="cleanup"]').getAttribute("aria-label")) || "";
  assert.match(label, /, 1 blocked\b/, `the rail's cleanup label does not name the blocked step: "${label}"`);
});
test("control: the rail's cleanup label names no blocked step when its bar draws none", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  assert.equal(await page.locator(`${BARS[1][1]} > i.blk`).count(), 0, "the rail's cleanup bar draws a blocked cell with no blocked step");
  const label = (await page.locator('#rail button[data-phase="cleanup"]').getAttribute("aria-label")) || "";
  assert.doesNotMatch(label, /blocked/, `the rail's cleanup label names a blocked step that is not there: "${label}"`);
});
test("the Now card's bar and the phase head's bar are role img", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  for (const [name, scope] of [BARS[0], BARS[2]]) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.equal(await page.locator(scope).getAttribute("role"), "img", `${name} has no role img`);
  }
});
test("the Now card's bar and the phase head's bar have a label that names the stalled and paused steps", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  for (const [name, scope] of [BARS[0], BARS[2]]) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    const label = (await page.locator(scope).getAttribute("aria-label")) || "";
    assert.match(label, /1 stalled/, `${name} has no aria-label naming the stalled step: "${label}"`);
    assert.match(label, /1 paused/, `${name} has no aria-label naming the paused step: "${label}"`);
  }
});
test("the Now card's count line names the stalled and paused steps", async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  assert.ok((await page.locator("#now > div:first-child > .sub").count()) > 0, "the Plan page has no where-you-are count line (#now > div:first-child > .sub)");
  const sub = (await page.locator("#now > div:first-child > .sub").first().textContent()).replace(/\s+/g, " ");
  assert.match(sub, /· 1 stalled · 1 paused/, "the count line does not name the stalled and paused steps: " + sub);
});
test("the Now card's count line names the blocked step when the Now bar draws one", async (t) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  assert.equal(await page.locator("#now .bar > i.blk").count(), 1, "the Now card's bar draws no blocked cell (i.blk)");
  assert.ok((await page.locator("#now > div:first-child > .sub").count()) > 0, "the Plan page has no where-you-are count line (#now > div:first-child > .sub)");
  const sub = (await page.locator("#now > div:first-child > .sub").first().textContent()).replace(/\s+/g, " ");
  assert.match(sub, /· 1 blocked/, "the count line does not name the blocked step: " + sub);
});

// A phase with no steps has a head bar with no words. The bar must not read as an image with an empty name.
test("the phase head's bar of a phase with no steps is not an image with an empty label", async (t) => {
  const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "todo", 1) } })); if (!page) return;
  await page.locator('#rail button[data-phase="organize"]').click();
  const head = page.locator("#phases .ph-head");
  assert.equal(await head.count(), 1, "the Plan page draws no phase head (#phases .ph-head)");
  assert.equal((await head.locator("h2").textContent()).trim(), "Organize", "the phase head does not show Organize after its rail button is pressed");
  assert.equal((await head.locator(".prog .num").textContent()).trim(), "0/0", "the Organize phase head does not read 0/0");
  const bar = head.locator(".prog .bar");
  assert.equal(await bar.count(), 1, "the Organize phase head has no bar (.prog .bar)");
  const role = await bar.getAttribute("role");
  const label = ((await bar.getAttribute("aria-label")) || "").trim();
  assert.ok(role !== "img" || label !== "", `the bar of the phase with no steps is role img with an empty aria-label: "${label}"`);
});
test("control: the phase head's bar of a phase with steps is labelled with its words", async (t) => {
  const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "todo", 1) } })); if (!page) return;
  const bar = page.locator("#phases .ph-head .prog .bar");
  assert.equal(await bar.count(), 1, "the Plan page draws no phase head bar (#phases .ph-head .prog .bar)");
  assert.equal(await bar.getAttribute("aria-label"), "1 to do", "the phase head's bar is not labelled with its words");
});

// ---------------------------------------------------------------- a to-do or done step listed stalled or paused (lane nfp-stalled-kind-color)
// The build lists a stalled or paused step by its id. A to-do or done step keeps its own status: it carries no Stalled or Paused tag,
// and each place that names it says that status. Only a doing step with that listing reads Stalled or Paused.
const OWN = { todo: ["to-do", "To do"], done: ["done", "Done"] };
const listing = (kind, ids) => kind === "stalled"
  ? { why: "", steps: ids.map((id) => ({ id, fix: "todo" })), paused: [], badPause: [], items: [], ...NO_ITEMS }
  : { why: "", steps: [], paused: ids, badPause: [], items: [], ...NO_ITEMS };
for (const kind of ["stalled", "paused"]) for (const status of ["todo", "done"]) {
  test(`a ${OWN[status][0]} step listed ${kind} carries no Stalled or Paused tag, and its row label reads ${OWN[status][1]}`, async (t) => {
    const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "todo", 1), x: stepOf("Step x", status, 2) }, stalled: listing(kind, ["x"]) })); if (!page) return;
    assert.equal(await page.locator("#s-x").count(), 1, `step x has no row in the plan list`);
    assert.equal(await page.locator("#s-x .tag.stl").count(), 0, `step x is ${OWN[status][1]} and listed ${kind}, but its row carries a Stalled tag`);
    assert.equal(await page.locator("#s-x .tag.pzd").count(), 0, `step x is ${OWN[status][1]} and listed ${kind}, but its row carries a Paused tag`);
    assert.match(await statusLabel(page, "x"), new RegExp(`status: ${OWN[status][1]}\\.`), `step x is ${OWN[status][1]} and listed ${kind}, but its row label does not read ${OWN[status][1]}`);
  });
}
for (const [kind, word, tag] of [["stalled", "Stalled", "stl"], ["paused", "Paused", "pzd"]]) {
  test(`control: a doing step listed ${kind} keeps its ${word} tag and reads ${word}`, async (t) => {
    const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "todo", 1), x: stepOf("Step x", "doing", 2) }, stalled: listing(kind, ["x"]) })); if (!page) return;
    assert.equal(await page.locator(`#s-x .tag.${tag}`).count(), 1, `step x is doing and listed ${kind}, but its row carries no ${word} tag`);
    assert.match(await statusLabel(page, "x"), new RegExp(`status: ${word}\\.`), `step x is doing and listed ${kind}, but its row label does not read ${word}`);
  });
}

// The band's count and rows take a listed step only when it is doing. A to-do or done step the build lists is in neither the count nor a
// row. Each case lists doing step a beside step x, so the count is 1 when x is left out and 2 when it is not. The row check comes after
// the plan rows are found, so the steps have arrived.
const BAND_WORD = { stalled: "Stalled", paused: "Paused" };
for (const kind of ["stalled", "paused"]) for (const status of ["todo", "done"]) {
  test(`the band counts a ${OWN[status][0]} step listed ${kind} in neither its count nor a row, and still counts the doing step beside it`, async (t) => {
    const steps = { c1: stepOf("Step c1", "todo", 1), a: stepOf("Step a", "doing", 2), x: stepOf("Step x", status, 3) };
    const page = await open(t, builtPage({ steps, stalled: listing(kind, ["a", "x"]) })); if (!page) return;
    for (const id of ["a", "x"]) await statusLabel(page, id);
    assert.equal(await stall(page).locator('button[data-go="a"]').count(), 1, `the band draws no row for doing step a listed ${kind}`);
    const text = await stallText(page);
    assert.match(text, new RegExp(`${BAND_WORD[kind]}: 1(?!\\d)`), `the band counts the ${OWN[status][0]} step x listed ${kind} as well as doing step a: ${text}`);
    assert.equal(await stall(page).locator('button[data-go="x"]').count(), 0, `the band draws a row for the ${OWN[status][0]} step x listed ${kind}`);
  });
}
// Control: a listed id with no step in the plan keeps its count and its row, named Untitled step, as before the band read steps.
for (const kind of ["stalled", "paused"]) {
  test(`control: a ${kind} id with no step in the plan keeps its count and its row, named Untitled step`, async (t) => {
    const page = await open(t, builtPage({ steps: { c1: stepOf("Step c1", "todo", 1), a: stepOf("Step a", "doing", 2) }, stalled: listing(kind, ["a", "zz"]) })); if (!page) return;
    await statusLabel(page, "a");
    const text = await stallText(page);
    assert.match(text, new RegExp(`${BAND_WORD[kind]}: 2(?!\\d)`), `the band does not count the listed id zz with no step as ${BAND_WORD[kind]}: ${text}`);
    assert.equal(await stall(page).locator('button[data-go="zz"]').count(), 1, "the band draws no row for the listed id zz with no step");
    assert.match(await stall(page).locator('button[data-go="zz"]').textContent(), /Untitled step/, "the row of the listed id zz with no step is not named Untitled step");
  });
}

// The edge: a to-do step listed paused (t1) and a done step listed stalled (d1), beside to-do c1 and doing a2. Each place reads
// the step's own status. EDGE_FULL is the same at full size: 30 steps, so each bar draws every cell.
const EDGE_READ = { why: "", steps: [{ id: "d1", fix: "todo" }], paused: ["t1"], badPause: [], items: [], ...NO_ITEMS };
const EDGE = () => ({ c1: stepOf("Step c1", "todo", 1), t1: stepOf("Step t1", "todo", 2), d1: stepOf("Step d1", "done", 3), a2: stepOf("Step a2", "doing", 4) });
const EDGE_FULL = () => ({ ...EDGE(), ...Object.fromEntries(Array.from({ length: 26 }, (_, i) => ["t" + (i + 5), stepOf("Step t" + (i + 5), "todo", i + 5)])) });
test("the row labels of a to-do step listed paused and a done step listed stalled read To do and Done", async (t) => {
  const page = await open(t, builtPage({ steps: EDGE(), stalled: EDGE_READ })); if (!page) return;
  assert.match(await statusLabel(page, "t1"), /status: To do\./, "step t1 is to do and listed paused, but its row label does not read To do");
  assert.match(await statusLabel(page, "d1"), /status: Done\./, "step d1 is done and listed stalled, but its row label does not read Done");
});
test("the where-you-are line counts neither the to-do step listed paused nor the done step listed stalled", async (t) => {
  const page = await open(t, builtPage({ steps: EDGE(), stalled: EDGE_READ })); if (!page) return;
  assert.ok((await page.locator("#now > div:first-child > .sub").count()) > 0, "the Plan page has no where-you-are line (#now > div:first-child > .sub)");
  const sub = (await page.locator("#now > div:first-child > .sub").first().textContent()).replace(/\s+/g, " ");
  assert.match(sub, /\b1 in progress/, "the where-you-are line does not count the doing step a2: " + sub);
  assert.doesNotMatch(sub, /stalled/, "the where-you-are line counts a done step as stalled: " + sub);
  assert.doesNotMatch(sub, /paused/, "the where-you-are line counts a to-do step as paused: " + sub);
});
test("the bars draw a to-do step listed paused and a done step listed stalled as to-do and done cells, at full size", async (t) => {
  const page = await open(t, builtPage({ steps: EDGE_FULL(), stalled: EDGE_READ })); if (!page) return;
  for (const [name, scope] of BARS) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    assert.deepEqual(await cellKinds(page, scope), ["done", "act", ...Array(28).fill("")], `${name} draws a listed to-do or done step as a stalled or paused cell`);
  }
});
// The kinds read in Latest changes and the Changes log, each after its row is found: a missing row is a named failure, not a timeout.
async function kindsOf(page, id) {
  for (const [where, loc] of [["Latest changes", feedKind(page, id)], ["the Changes log", logKind(page, id)]]) assert.equal(await loc.count(), 1, `step ${id} has no row in ${where}`);
  return { feed: (await feedKind(page, id).textContent()).trim(), log: (await logKind(page, id).textContent()).trim() };
}
test("Latest changes and the Changes log read the to-do step listed paused and the done step listed stalled as they read unlisted", async (t) => {
  const page = await open(t, builtPage({ steps: EDGE(), stalled: EDGE_READ })); if (!page) return;
  const plain = await open(t, builtPage({ steps: EDGE() })); if (!plain) return;
  for (const id of ["t1", "d1"]) {
    const got = await kindsOf(page, id), want = await kindsOf(plain, id);
    assert.equal(got.feed, want.feed, `step ${id} reads ${got.feed} in Latest changes, not ${want.feed}, its unlisted kind`);
    assert.equal(got.log, want.log, `step ${id} reads ${got.log} in the Changes log, not ${want.log}, its unlisted kind`);
  }
});

// The Now card's count line: a group ("· 1 stalled") is never split across lines. Lines are read from the word boxes: a line that
// starts with a group word or a separator, or ends on a bare number, has broken a group. Each helper here is a copy of the one in
// skills/waiting-page/tests/page.test.mjs: the two pages' test files keep their own helpers.
const GROUP_WORDS = new Set(["in", "progress", "done", "stalled", "paused", "blocked"]);
const bare = (w) => w.replace(/[.,·]/g, "");
async function countLines(page, sel) {
  return page.evaluate((s) => {
    const root = document.querySelector(s);
    if (!root) return null;
    const words = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const re = /\S+/g;
      for (let m = re.exec(node.data); m; m = re.exec(node.data)) {
        const range = document.createRange();
        range.setStart(node, m.index);
        range.setEnd(node, m.index + m[0].length);
        const r = range.getClientRects()[0];
        if (r) words.push({ w: m[0], y: (r.top + r.bottom) / 2 });
      }
    }
    const lines = [];
    for (const { w, y } of words) {
      const last = lines[lines.length - 1];
      if (last && Math.abs(last.y - y) < 4) last.words.push(w); else lines.push({ y, words: [w] });
    }
    return lines.map((l) => l.words);
  }, sel);
}
for (const width of [390, 1280]) test(`the Now card's count line keeps each group whole at ${width} wide, with blocked, stalled and paused steps`, async (t) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(), live: BAR_LIVE, stalled: STALLED_S3_P4 }), width); if (!page) return;
  const lines = await countLines(page, "#now > div:first-child > .sub");
  assert.ok(lines && lines.length, "the Plan page has no where-you-are count line (#now > div:first-child > .sub)");
  const text = lines.map((l) => l.join(" ")).join(" | ");
  const starts = lines.find((l) => bare(l[0]) === "" || GROUP_WORDS.has(bare(l[0])));
  assert.equal(starts, undefined, `at ${width} wide a line of the count line starts inside a group: ${text}`);
  const ends = lines.find((l) => /^\d+$/.test(bare(l[l.length - 1])));
  assert.equal(ends, undefined, `at ${width} wide a line of the count line ends on a bare number: ${text}`);
});
