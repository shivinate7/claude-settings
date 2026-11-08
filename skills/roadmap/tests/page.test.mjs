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

async function open(t, html, width = 1280, dpr = 1) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage({ viewport: { width, height: 900 }, deviceScaleFactor: dpr });
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
  return page.locator(`${scope} .bar > i.act`).count();
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
const badColour = (page) => page.evaluate(() => {
  const p = document.createElement("span");
  p.style.color = "var(--bad)";
  document.body.appendChild(p);
  const c = getComputedStyle(p).color;
  p.remove();
  return c;
});
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

// One cell per step, in the order done, in progress, stalled, paused, blocked, to do. Three bars: the Now card, the rail's cleanup
// button and the phase head. The fixture is a full phase of 30 steps: 1 done, a2 live (in progress), s3 stalled, p4 paused, 26 to do.
const BARS = [["the Now card's bar", "#now .bar"], ["the rail's cleanup bar", '#rail button[data-phase="cleanup"] .bar'], ["the phase head's bar", "#phases .ph-head .bar"]];
// c1 is named here: make_repo adds its own to-do c1 to any fixture that does not name one.
// n is the phase's step count (30 by default): the to-do steps fill the rest.
const barFixture = (n = 30) => ({
  c1: stepOf("Step c1", "todo", 1), d1: stepOf("Step d1", "done", 1), a2: stepOf("Step a2", "doing", 2), s3: stepOf("Step s3", "doing", 3), p4: stepOf("Step p4", "doing", 4),
  ...Object.fromEntries(Array.from({ length: n - 5 }, (_, i) => ["t" + (i + 5), stepOf("Step t" + (i + 5), "todo", i + 5)])),
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
const barFixtureBlocked = (n = 30) => ({ ...barFixture(n), t5: stepOf("Step t5", "blocked", 5) });
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

// ---------------------------------------------------------------- the low cell (lane nfp-narrow-paused-cell)
// A paused cell paints its lower half in --muted, not a ring: one gradient, at the bottom and not repeated. It is read from the
// computed style. The colour is a probe of the page's own token, so a token change moves the test with it.
const tokenDefined = (page, name) => page.evaluate((n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim() !== "", name);
const tokenColour = (page, name, prop = "color") => page.evaluate(([n, p]) => {
  const e = document.createElement("span");
  e.style[p] = `var(${n})`;
  document.body.appendChild(e);
  const c = getComputedStyle(e)[p];
  e.remove();
  return c;
}, [name, prop]);
const lowCell = (loc) => loc.evaluate((el) => {
  const s = getComputedStyle(el);
  return { size: s.backgroundSize, pos: s.backgroundPosition, repeat: s.backgroundRepeat, image: s.backgroundImage, shadow: s.boxShadow };
});
// The paused part as drawn: the cell, or its run in a narrow bar. A cell at 0 width is not drawn; a run is drawn only in a runs layer
// that has width (see barLayers).
const drawnPaused = async (page, scope) => {
  const all = page.locator(`${scope} i.pzd`);
  const drawn = [];
  for (let i = 0; i < (await all.count()); i++) {
    const shown = await all.nth(i).evaluate((el) => {
      const host = el.closest(".runs");
      return el.getBoundingClientRect().width > 0 && (!host || host.getBoundingClientRect().width > 0);
    });
    if (shown) drawn.push(all.nth(i));
  }
  return drawn;
};
for (const width of [390, 1280]) for (const [name, scope] of BARS) test(`the paused cell in ${name} at ${width} wide paints its lower half in --muted, with no inset ring, in light and dark`, async (t) => {
  const page = await open(t, builtPage({ steps: barFixture(), live: BAR_LIVE, stalled: STALLED_S3_P4 }), width); if (!page) return;
  assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
  for (const scheme of ["light", "dark"]) {
    await page.emulateMedia({ colorScheme: scheme });
    const dark = await page.evaluate(() => matchMedia("(prefers-color-scheme: dark)").matches);
    assert.equal(dark, scheme === "dark", `the page did not take the ${scheme} scheme`);
    const drawn = await drawnPaused(page, scope);
    assert.equal(drawn.length, 1, `${name} at ${width} wide draws ${drawn.length} paused part(s) in ${scheme}, not one (a cell or a run)`);
    assert.ok(await tokenDefined(page, "--muted"), `--muted is not defined on :root in ${scheme}`);
    const muted = await tokenColour(page, "--muted");
    const c = await lowCell(drawn[0]);
    assert.equal(c.size, "100% 50%", `${name} in ${scheme}: the paused cell's background-size is "${c.size}", not "100% 50%"`);
    assert.equal(c.pos, "0% 100%", `${name} in ${scheme}: the paused cell's background-position is "${c.pos}", not the bottom-left "0% 100%" the page emits`);
    assert.equal(c.repeat.split(" ").pop(), "no-repeat", `${name} in ${scheme}: the paused cell repeats its paint, so it fills the top half too ("${c.repeat}")`);
    assert.ok(c.image.includes(muted), `${name} in ${scheme}: the paused cell's background-image is not --muted (${muted}): "${c.image}"`);
    assert.equal(c.shadow, "none", `${name} in ${scheme}: the paused cell still draws a ring: box-shadow "${c.shadow}"`);
  }
});
// The WCAG 2.x contrast of two rgb() colours. A copy of the waiting page test's CONTRAST, which runs in the browser: the guard does
// not count testing/ as a test folder, so the one home cannot be a shared module.
const linear = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
const luminance = (rgb) => { const [r, g, b] = rgb.match(/\d+/g).map(Number); return 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b); };
const contrast = (a, b) => { const x = luminance(a), y = luminance(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
for (const scheme of ["light", "dark"]) test(`control: --muted and --bad, read from the computed :root, each reach 3:1 against --surface in ${scheme}`, async (t) => {
  const page = await open(t, builtPage({ steps: KIND_FIXTURE, stalled: STALLED_C1 })); if (!page) return;
  await page.emulateMedia({ colorScheme: scheme });
  const dark = await page.evaluate(() => matchMedia("(prefers-color-scheme: dark)").matches);
  assert.equal(dark, scheme === "dark", `the page did not take the ${scheme} scheme`);
  assert.ok(await tokenDefined(page, "--surface"), `--surface is not defined on :root in ${scheme}`);
  const surface = await tokenColour(page, "--surface", "backgroundColor");
  assert.match(surface, /^rgb\(/, `--surface does not compute to a colour in ${scheme}: "${surface}"`);
  for (const token of ["--muted", "--bad"]) {
    assert.ok(await tokenDefined(page, token), `${token} is not defined on :root in ${scheme}`);
    const c = await tokenColour(page, token);
    assert.match(c, /^rgb\(/, `${token} does not compute to a colour in ${scheme}: "${c}"`);
    const ratio = contrast(c, surface);
    assert.ok(ratio >= 3, `${token} is ${ratio.toFixed(2)}:1 against --surface in ${scheme}, under 3:1`);
  }
});

// ---------------------------------------------------------------- the narrow rule (lane nfp-narrow-paused-cell)
// A bar draws one cell per step while it is at least steps x 5px - 2px wide. Under that, it draws one run per kind, in the order done,
// in progress, stalled, paused, blocked, to do, with no empty run and no cell. Each drawn part is at least 3px, the floor this test checks.
// A run gets RUN_MIN_PX (4px) once the bar is 6k - 2px or more (k kinds), as the run floor cases below check. The cells stay in the DOM at 0 width.
const RULE_PX = 30 * 5 - 2;
// The bar's layers from the layout: its own width, and its cells and runs with their widths (a cell at 0 width is not drawn).
// A run keeps its 4px minimum past a 0px runs layer, and the layer clips it, so a run counts as drawn only in a drawn layer.
// With px, the bar is set to that width in the same step as the read, so a re-render cannot undo it. A run's vis is its part inside the
// bar and the runs layer, the two boxes that clip it. cellSpan is the span the drawn cells cover, and runsW the runs layer's width.
const barLayers = (loc, px) => loc.evaluate((bar, set) => {
  if (set !== undefined) { bar.style.setProperty("width", set + "px"); bar.style.flex = "0 0 auto"; }
  const box = (e) => e.getBoundingClientRect();
  const w = (e) => box(e).width;
  const b = box(bar);
  const runs = bar.querySelector(":scope > .runs");
  const clip = runs ? box(runs) : b;
  const vis = (e) => { const r = box(e); return Math.max(0, Math.min(r.right, b.right, clip.right) - Math.max(r.left, b.left, clip.left)); };
  const cells = [...bar.querySelectorAll(":scope > i")];
  const drawn = cells.filter((e) => w(e) > 0);
  return {
    barW: w(bar),
    n: getComputedStyle(bar).getPropertyValue("--n").trim(),
    cells: cells.map((e) => ({ cls: e.className, w: w(e) })),
    cellSpan: drawn.length ? Math.max(...drawn.map((e) => box(e).right)) - Math.min(...drawn.map((e) => box(e).left)) : 0,
    runs: runs ? [...runs.querySelectorAll(":scope > i")].map((e) => ({ cls: e.className, w: w(e), vis: vis(e) })) : [],
    runsW: runs ? w(runs) : 0,
    runsDrawn: !!runs && w(runs) > 0,
  };
}, px);
for (const width of [390, 1280]) for (const scheme of ["light", "dark"]) for (const [name, scope] of BARS) test(`${name} at ${width} wide in ${scheme} draws one layer, cells or runs by the narrow rule, and each drawn part is at least 3px`, async (t) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(), live: BAR_LIVE, stalled: STALLED_S3_P4 }), width); if (!page) return;
  await page.emulateMedia({ colorScheme: scheme });
  assert.equal(await page.locator(scope).count(), 1, `${name} at ${width} wide is missing (${scope})`);
  const L = await barLayers(page.locator(scope));
  const cellsDrawn = L.cells.filter((p) => p.w > 0), runsDrawn = L.runsDrawn ? L.runs : [];
  assert.ok(!(cellsDrawn.length && runsDrawn.length), `${name} at ${width} wide draws cells and runs both`);
  assert.ok(cellsDrawn.length + runsDrawn.length > 0, `${name} at ${width} wide draws no cell and no run`);
  const narrow = L.barW < RULE_PX;
  assert.equal(runsDrawn.length > 0, narrow, `${name} at ${width} wide is ${L.barW.toFixed(1)}px, ${narrow ? "under" : "at least"} ${RULE_PX}px, so it should draw ${narrow ? "runs" : "cells"}, not ${narrow ? "cells" : "runs"}`);
  for (const p of [...cellsDrawn, ...runsDrawn]) assert.ok(p.w >= 3, `${name} at ${width} wide draws a ${p.w.toFixed(1)}px part (${p.cls || "to do"}), under 3px`);
  if (narrow) assert.deepEqual(L.runs.map((r) => r.cls), ["done", "act", "stl", "pzd", "blk", ""], `${name} at ${width} wide: its runs are not one each of done, in progress, stalled, paused, blocked, to do, in that order`);
  else assert.equal(cellsDrawn.length, 30, `${name} at ${width} wide draws ${cellsDrawn.length} cells, not one per step (30)`);
});

// ---------------------------------------------------------------- the edge width (lane nfp-npc-edge)
// The cases set a bar 1px under, 0.02px under, at, and 1px over steps x 5px - 2px. Each checks that exactly one layer draws, that the
// layer spans the bar, and that each run shows RUN_MIN_PX or more. The 0.02px case checks the runs layer at a gap just past one 1/64px
// layout unit: a switch that scales the gap by 1000 would give 20px there, short of these bars. The width is set on the bar, so no
// viewport is in the case. Layout units are 1/64px, so a width reads within LAYOUT_TOL.
const LAYOUT_TOL = 0.05, RUN_MIN_PX = 4;
const edgeWidths = (n) => [[5 * n - 3, "1px under the edge"], [5 * n - 2.02, "0.02px under the edge"], [5 * n - 2, "at the edge"], [5 * n - 1, "1px over the edge"]];
for (const n of [30, 13]) for (const [px, what] of edgeWidths(n)) test(`edge width: a ${n}-step bar set to ${px}px (${what}) draws exactly one layer, cells or runs, and that layer spans the bar`, async (t) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(n), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  const problems = [];
  for (const [name, scope] of BARS) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    const L = await barLayers(page.locator(scope), px);
    assert.equal(L.n, String(n), `${name} reads --n ${L.n}, not ${n}: the fixture did not build a ${n}-step bar`);
    assert.equal(L.cells.length, n, `${name} has ${L.cells.length} cells, not ${n}`);
    assert.ok(Math.abs(L.barW - px) < LAYOUT_TOL, `${name} did not take the ${px}px width: it measures ${L.barW}px`);
    const cellsDrawn = L.cells.some((p) => p.w > 0), runsDrawn = L.runsDrawn;
    if (cellsDrawn === runsDrawn) { problems.push(`${name} at ${px}px draws ${cellsDrawn ? "cells and runs both" : "no cell and no run"}`); continue; }
    const layer = cellsDrawn ? L.cellSpan : L.runsW;
    if (Math.abs(layer - L.barW) > LAYOUT_TOL) problems.push(`${name} at ${px}px: the drawn ${cellsDrawn ? "cells" : "runs layer"} spans ${layer.toFixed(2)}px of a ${L.barW.toFixed(2)}px bar`);
    if (runsDrawn) for (const r of L.runs) if (r.vis < RUN_MIN_PX - LAYOUT_TOL) problems.push(`${name} at ${px}px: its ${r.cls || "to-do"} run shows ${r.vis.toFixed(2)}px, under ${RUN_MIN_PX}px`);
  }
  assert.deepEqual(problems, [], `the ${n}-step bars at ${px}px:\n  ${problems.join("\n  ")}`);
});
// Six steps, all five kinds and a to-do, in a 20px bar. Six runs need 34px at a 4px minimum with 2px gaps, so 4px cannot hold at 20px:
// each run present must show at 1px or more here.
const SIX_FIXTURE = () => ({ c1: stepOf("Step c1", "todo", 1), d1: stepOf("Step d1", "done", 1), a2: stepOf("Step a2", "doing", 2), s3: stepOf("Step s3", "doing", 3), p4: stepOf("Step p4", "doing", 4), t5: stepOf("Step t5", "blocked", 5) });
const RUN_VISIBLE_PX = 1;
test("edge width: a 6-step bar with all five kinds, set to 20px, shows every run present", async (t) => {
  const page = await open(t, builtPage({ steps: SIX_FIXTURE(), live: BAR_LIVE, stalled: STALLED_S3_P4 })); if (!page) return;
  const problems = [];
  for (const [name, scope] of BARS) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    const L = await barLayers(page.locator(scope), 20);
    assert.equal(L.n, "6", `${name} reads --n ${L.n}, not 6: the fixture did not build a 6-step bar`);
    assert.deepEqual(L.cells.map((c) => c.cls), ["done", "act", "stl", "pzd", "blk", ""], `${name} does not draw the six kinds in order`);
    assert.ok(Math.abs(L.barW - 20) < LAYOUT_TOL, `${name} did not take the 20px width: it measures ${L.barW}px`);
    assert.ok(L.runsDrawn, `${name} at 20px draws no runs layer`);
    for (const r of L.runs) if (r.vis < RUN_VISIBLE_PX) problems.push(`${name} at 20px: its ${r.cls || "to-do"} run shows ${r.vis.toFixed(2)}px, under ${RUN_VISIBLE_PX}px`);
  }
  assert.deepEqual(problems, [], `the 6-step bars at 20px:\n  ${problems.join("\n  ")}`);
});

// ---------------------------------------------------------------- one layer at every device scale (lane nfp-npc-r3-red)
// The cells draw at steps x 5px - 2px and above, and the runs layer draws below it. Both switch at that one edge: the cells take the bar less
// the runs layer's width (`.bar>i` and `.bar>.runs` in the page CSS), so no width draws both, and the sweep below checks that.
// Chromium lays a box out in 1/64 of the px its scale maps to: under a page zoom z the grid is 1/(64z) CSS px, and a sweep in that step
// reaches every grid unit near the edge. In this browser a device scale does not move the grid, so the device-scale cases stay green
// here. The sweep runs 0.05px either side of steps x 5px - 2px, and reads the layers in the grid's own px (zoomed px under a zoom).
const oneLayerSweep = async (t, n, { dpr = 1, zoom = 1 }) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(n), live: BAR_LIVE, stalled: STALLED_S3_P4 }), 1280, dpr); if (!page) return null;
  if (zoom !== 1) await page.evaluate((z) => { document.documentElement.style.zoom = String(z); }, zoom);
  const step = 1 / (64 * dpr * zoom), half = Math.round(0.05 / step), tol = LAYOUT_TOL * zoom;
  const problems = [];
  for (const [name, scope] of BARS) {
    assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
    for (let i = -half; i <= half; i++) {
      const px = 5 * n - 2 + i * step;
      const L = await barLayers(page.locator(scope), px);
      assert.equal(L.n, String(n), `${name} reads --n ${L.n}, not ${n}: the fixture did not build a ${n}-step bar`);
      assert.ok(Math.abs(L.barW - px * zoom) < tol, `${name} did not take the ${px}px width: it measures ${L.barW}px`);
      const cellsDrawn = L.cells.some((p) => p.w > 0), runsDrawn = L.runsDrawn;
      if (cellsDrawn === runsDrawn) { problems.push(`${name} at ${px.toFixed(4)}px draws ${cellsDrawn ? "cells and runs both" : "no cell and no run"}`); continue; }
      const layer = cellsDrawn ? L.cellSpan : L.runsW;
      if (Math.abs(layer - L.barW) > tol) problems.push(`${name} at ${px.toFixed(4)}px: the drawn ${cellsDrawn ? "cells" : "runs layer"} spans ${layer.toFixed(2)}px of a ${L.barW.toFixed(2)}px bar`);
    }
  }
  return problems;
};
for (const n of [30, 13]) test(`control: at device scale 1, a ${n}-step bar swept 0.05px either side of its edge draws exactly one layer, and it spans the bar`, async (t) => {
  const problems = await oneLayerSweep(t, n, {}); if (problems === null) return;
  assert.deepEqual(problems, [], `the ${n}-step bars at device scale 1:\n  ${problems.join("\n  ")}`);
});
for (const dpr of [2, 1.1]) for (const n of [30, 13]) test(`one layer at device scale ${dpr}: a ${n}-step bar swept 0.05px either side of its edge draws exactly one layer, and it spans the bar`, async (t) => {
  const problems = await oneLayerSweep(t, n, { dpr }); if (problems === null) return;
  assert.deepEqual(problems, [], `the ${n}-step bars at device scale ${dpr}:\n  ${problems.join("\n  ")}`);
});
for (const zoom of [1.1, 2]) for (const n of [30, 13]) test(`one layer at zoom ${zoom}: a ${n}-step bar swept 0.05px either side of its edge, in steps of 1/(64 x ${zoom})px, draws exactly one layer, and it spans the bar`, async (t) => {
  const problems = await oneLayerSweep(t, n, { zoom }); if (problems === null) return;
  assert.deepEqual(problems, [], `the ${n}-step bars at zoom ${zoom}:\n  ${problems.join("\n  ")}`);
});

// ---------------------------------------------------------------- the run floor (lane nfp-npc-r3-red)
// A run is RUN_MIN_PX or more wide where it shows, once the bar is 6k - 2px or more: k runs take 4px each and k - 1 gaps take 2px each.
// The edge cases check the switch, and a 3px floor passes them, so these read the floor itself. Each case reads its bar at its own
// width on its viewport, then sweeps each width from 6k - 2px up to the edge. The fixture is a 30-step bar with six kinds.
const FLOOR_STEPS = 30, FLOOR_KINDS = 6;
for (const [name, scope, width] of [["the rail's cleanup bar at 320 wide", BARS[1][1], 320], ["the rail's cleanup bar at 390 wide", BARS[1][1], 390], ["the phase head's bar at 1280 wide", BARS[2][1], 1280]]) test(`run floor: ${name} shows each run at ${RUN_MIN_PX}px or more, at its own width and at each width from ${6 * FLOOR_KINDS - 2}px up to the edge`, async (t) => {
  const page = await open(t, builtPage({ steps: barFixtureBlocked(FLOOR_STEPS), live: BAR_LIVE, stalled: STALLED_S3_P4 }), width); if (!page) return;
  assert.equal(await page.locator(scope).count(), 1, `${name} is missing (${scope})`);
  const natural = await barLayers(page.locator(scope));
  assert.ok(natural.runsDrawn, `${name} is ${natural.barW.toFixed(1)}px at its own width and draws no runs layer: the case does not reach the run floor`);
  assert.equal(natural.runs.length, FLOOR_KINDS, `${name} draws ${natural.runs.length} runs at its own width, not ${FLOOR_KINDS}`);
  const floorProblems = (L, at) => L.runs.filter((r) => r.vis < RUN_MIN_PX - LAYOUT_TOL).map((r) => `${name} at ${at}: its ${r.cls || "to-do"} run shows ${r.vis.toFixed(2)}px, under ${RUN_MIN_PX}px`);
  const problems = floorProblems(natural, `${natural.barW.toFixed(2)}px, its own width`);
  const low = 6 * FLOOR_KINDS - 2, high = 5 * FLOOR_STEPS - 3;
  let swept = 0;
  for (let px = low; px <= high; px++) {
    const L = await barLayers(page.locator(scope), px);
    if (!L.runsDrawn) continue;
    swept++;
    problems.push(...floorProblems(L, `${px}px`));
  }
  assert.equal(swept, high - low + 1, `the runs layer drew at ${swept} of the ${high - low + 1} widths from ${low}px to ${high}px`);
  assert.deepEqual(problems.slice(0, 6), [], `${name}: ${problems.length} run(s) under ${RUN_MIN_PX}px, the first ${Math.min(6, problems.length)}:\n  ${problems.slice(0, 6).join("\n  ")}`);
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
