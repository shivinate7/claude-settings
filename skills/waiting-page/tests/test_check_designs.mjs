// Tests for skills/waiting-page/check_designs.mjs (rule page-item-design, decision page-item-checked-at-write).
//   NODE_PATH=<dir with playwright> node --test skills/waiting-page/tests/test_check_designs.mjs
// The checker loads a page built from page.html with its designData filled, stubs the artifact database
// with one item, and calls the page's own pictureProblem and card measure. Each case reads the checker's
// JSON line first and its exit code second: a missing script exits 1, so an exit code alone would pass a miss.
// No Playwright or no Chromium: skipped on a laptop, a fail in CI (testing/skip-locally-fail-in-ci.mjs).
// Temp files: the run folder of skills/plain-english-map/tests/temp-root.mjs, the one JS home of the sweep,
// whose own test proves the sweep. The designData splice is one line here, as page.test.mjs writes its own,
// because importing page.test.mjs would run its cases.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { needEnv } from "../../../testing/skip-locally-fail-in-ci.mjs";
import { runFolder, removeRunFolder } from "../../plain-english-map/tests/temp-root.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CHECK = path.join(HERE, "..", "check_designs.mjs");
const PAGE = path.join(HERE, "..", "page.html");
const require = createRequire(import.meta.url);
const SLOT = '<script type="application/json" id="designData">{}</script>';

const html = fs.readFileSync(PAGE, "utf8");
assert.equal(html.split(SLOT).length, 2, "page.html holds its designData slot exactly once");
// Read from the page, never copied: the strip case must sit below the page's own floor.
const MIN_PIC = Number(/const MIN_PIC = (\d+);/.exec(html)?.[1]);
assert.ok(MIN_PIC > 0, "page.html names MIN_PIC");

const dir = runFolder();
after(() => removeRunFolder());
const write = (name, text) => {
  const file = path.join(dir, name);
  fs.writeFileSync(file, text);
  return file;
};

// A phone-shaped mockup. Its text holds an apostrophe and comment openers, which must reach the page as text.
const PHONE = '<div id="vol" data-state="full" style="width:390px;height:844px">Don\'t // /* # full</div>';
// A strip: 2400 px wide and 300 high, drawn at 2400, so the card scales it down to a thin band.
const STRIP = '<div id="vol" data-state="full" style="width:2400px;height:300px">x</div>';
// A phone-shaped mockup whose focus is a 300x40 bar at its natural size. The page never shrinks it, so no floor applies.
const SMALL = '<div style="width:390px;height:844px"><div id="bar" style="width:300px;height:40px">x</div></div>';
const MOCKS = { m1: PHONE, m2: STRIP, m3: SMALL };

const pageWith = (designs) => html.replace(SLOT, () =>
  '<script type="application/json" id="designData">' + JSON.stringify(designs).replace(/</g, "\\u003c") + "</script>");

// Option a carries the picture. Option b has none, so the pair check cannot fire before the picture checks.
// `extra` is merged last: a ranked item, or a status.
function item({ focus, state, slug = "m1", drawn } = {}, extra = {}) {
  return {
    id: "fill-of-volume-card", n: 51, kind: "decision", status: "open",
    title: "Which fill should the volume card show?", context: "The card shows the stock level.",
    options: [
      { key: "a", label: "Full card", how: "The card shows the full stock.", gain: "g", lose: "l", design: slug },
      { key: "b", label: "Empty card", how: "The card shows no stock.", gain: "g", lose: "l" },
    ],
    designs: [{ slug, label: "Full card", option: "a", focus, state, drawn }],
    ...extra,
  };
}

function check(pageFile, itemFile) {
  const run = spawnSync(process.execPath, [CHECK, "--page", pageFile, "--item", itemFile],
    { encoding: "utf8", timeout: 120_000 });
  const line = run.stdout.trim().split("\n").pop() ?? "";
  let json = null;
  try { json = JSON.parse(line); } catch { /* no JSON line: answer() names it */ }
  return { code: run.status, json, stderr: run.stderr.trim() };
}

// The checker's answer: its JSON line first, then its exit code. Returns the problem the line names.
function answer(name, pageText, it, code) {
  const got = check(write(name + ".html", pageText), write(name + ".json", JSON.stringify(it)));
  assert.ok(got.json && "problem" in got.json, `no {"problem": ...} JSON line; exit ${got.code}: ${got.stderr.slice(0, 200)}`);
  assert.equal(got.code, code, `exit code (problem: ${JSON.stringify(got.json.problem)})`);
  return got.json.problem;
}

// Gated on Chromium: a laptop without it skips, CI fails.
const chromium = async () => { const b = await require("playwright").chromium.launch(); await b.close(); return true; };

test("item-51 shape: a focus the mockup does not draw is a miss, naming option A and the focus", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  const problem = answer("focus", pageWith(MOCKS), item({ focus: "#fill" }), 1);
  assert.equal(typeof problem, "string");
  assert.match(problem, /option A/);
  assert.match(problem, /focus/);
});

test("a state the mockup does not draw is a miss, naming option A and the state", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  const problem = answer("state", pageWith(MOCKS), item({ focus: "#vol", state: "empty" }), 1);
  assert.equal(typeof problem, "string");
  assert.match(problem, /option A/);
  assert.match(problem, /state/);
});

test("a good item, focus #vol and state full on a phone-shaped mockup, passes with problem null", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  assert.equal(answer("good", pageWith(MOCKS), item({ focus: "#vol", state: "full" }), 0), null);
});

test("a missing mockup slug is not flagged here: the page warns in the frame", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  assert.equal(answer("missing", pageWith(MOCKS), item({ focus: "#vol", state: "full", slug: "m9" }), 0), null);
});

test("a strip mockup, 2400 wide and 300 high drawn at 2400, is a miss below MIN_PIC, naming option A and the height", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  const problem = answer("strip", pageWith(MOCKS), item({ focus: "#vol", state: "full", slug: "m2", drawn: 2400 }), 1);
  assert.equal(typeof problem, "string");
  assert.match(problem, /option A/);
  const heights = (problem.match(/\d+(\.\d+)?/g) ?? []).map(Number);
  assert.ok(heights.some((h) => h < MIN_PIC), `the problem names no height below MIN_PIC (${MIN_PIC}): ${problem}`);
});

// Exit 3 is unknown: the checker could not read its input. Neither case needs Chromium.
test("a missing --page is unknown, exit 3", () => {
  const got = check(path.join(dir, "no-such-page.html"), write("unknown-page.json", JSON.stringify(item({ focus: "#vol" }))));
  assert.equal(got.code, 3, `exit code, stderr: ${got.stderr.slice(0, 200)}`);
});

test("a missing --item is unknown, exit 3", () => {
  const got = check(write("unknown-item.html", pageWith(MOCKS)), path.join(dir, "no-such-item.json"));
  assert.equal(got.code, 3, `exit code, stderr: ${got.stderr.slice(0, 200)}`);
});

// Round 2 cases. The selector finds option cards only, so a ranked card (div.opt.ranked with label.head) is unmeasured.
test("a ranked item whose option picture is a strip is a miss, exit 1, not unknown", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  const problem = answer("ranked-strip", pageWith(MOCKS),
    item({ focus: "#vol", state: "full", slug: "m2", drawn: 2400 }, { ranked: true }), 1);
  assert.equal(typeof problem, "string");
  assert.match(problem, /option A/);
  const heights = (problem.match(/\d+(\.\d+)?/g) ?? []).map(Number);
  assert.ok(heights.some((h) => h < MIN_PIC), `the problem names no height below MIN_PIC (${MIN_PIC}): ${problem}`);
});

// The floor applies only to a picture the page shrank (scale below 1) that still draws under MIN_PIC high.
test("a 300x40 focus drawn at natural size is not a miss: no floor without a shrink", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  assert.equal(answer("natural", pageWith(MOCKS), item({ focus: "#bar", slug: "m3" }), 0), null);
});

// An option with a design, on an item the page does not draw (a closed item has no card), has no picture box to measure.
test("an option with a design and no picture box on the page is unknown, exit 3, not a pass", async (t) => {
  if ((await needEnv(t, "chromium", chromium)) === null) return;
  const got = check(write("closed.html", pageWith(MOCKS)),
    write("closed.json", JSON.stringify(item({ focus: "#vol", state: "full" }, { status: "closed" }))));
  assert.equal(got.code, 3, `exit code (stdout: ${JSON.stringify(got.json)}, stderr: ${got.stderr.slice(0, 200)})`);
});
