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

async function open(t, html) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
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
