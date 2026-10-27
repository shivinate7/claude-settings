// Browser tests for the waiting page template (skill waiting-page).
//   NODE_PATH=<dir with playwright> node --test skills/waiting-page/tests/page.test.mjs
// A stub `window.claude.use("db")` stands in for the artifact database and records every write and
// delete. No Playwright or no Chromium: skipped on a laptop, a fail in CI
// (testing/skip-locally-fail-in-ci.mjs).
// Seam: PAGE_UNDER_TEST is the page to load, for a red proof against another copy.
import { test, after } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { needEnv } from "../../../testing/skip-locally-fail-in-ci.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PAGE = process.env.PAGE_UNDER_TEST || path.join(HERE, "..", "page.html");
const require = createRequire(import.meta.url);
const ORIGIN = "http://waiting.test/";

const DECISION = {
  id: "pick-a-colour", n: 27, kind: "decision", status: "open", added: "2026-10-26T00:00:00Z",
  ref: "c1, a test step", title: "Pick a colour", owner: "test thread", home: "c1", context: "Which colour?",
  options: [
    { key: "a", label: "Red", how: "h", gain: "g", lose: "l" },
    { key: "b", label: "Blue", how: "h", gain: "g", lose: "l" },
  ],
  pick: "a", why: "Red is bold.",
};
const TASK = {
  id: "plug-in-the-mac", n: 28, kind: "task", status: "open", added: "2026-10-26T00:00:00Z",
  ref: "c2, a test task", title: "Plug in the Mac", owner: "test thread", home: "c2", context: "Plug it in.",
  steps: ["Find the cable", "Plug it in"], links: [], minutes: 1,
};

// Runs in the page before its script. Collections are maps of id to data; listeners fire on change.
function stubDb({ items, answers, failDelete, comments }) {
  const data = { items: Object.fromEntries(items.map((i) => [i.id, i])), answers: { ...answers }, meta: {} };
  const subs = { items: [], answers: [] };
  window.__log = [];
  const snap = (name) => ({ docs: Object.entries(data[name]).map(([id, v]) => ({ id, data: () => v })) });
  const fire = (name) => (subs[name] || []).forEach((cb) => cb(snap(name)));
  window.__answers = () => data.answers;
  const db = {
    collection: (name) => ({
      onSnapshot: (cb) => { (subs[name] = subs[name] || []).push(cb); setTimeout(() => cb(snap(name)), 0); return () => {}; },
      doc: (id) => ({
        set: async (body) => { window.__log.push(["set", name, id, body]); data[name][id] = body; setTimeout(() => fire(name), 0); },
        delete: async () => { if (failDelete) throw { code: "denied" }; window.__log.push(["delete", name, id]); delete data[name][id]; setTimeout(() => fire(name), 0); },
        onSnapshot: (cb) => { setTimeout(() => cb({ exists: false, data: () => null }), 0); return () => {}; },
      }),
    }),
  };
  // comments: null (capability absent) or { can, canThrows, failCodes, goneThreads }.
  // failCodes rejects every send; goneThreads rejects a send into those thread ids with not_found.
  window.__sent = [];
  const cm = comments && {
    canSendToClaude: async () => { if (comments.canThrows) throw { code: "unavailable" }; return comments.can || "available"; },
    anchorFor: async (el) => ({ path: "h1", x: 0, y: 0, tag: el.tagName }),
    sendToClaude: async (target) => {
      window.__sent.push(target);
      if (comments.failCode) throw { code: comments.failCode, message: "stub" };
      if (target.threadId && (comments.goneThreads || []).includes(target.threadId)) throw { code: "not_found", message: "stub" };
      return { threadId: target.threadId || "t-new-" + window.__sent.length, commentId: "c" + window.__sent.length };
    },
  };
  window.claude = { use: async (cap) => (cap === "db" ? db : cap === "comments" ? (cm || null) : null) };
}

let browser;
const html = fs.readFileSync(PAGE, "utf8");
after(async () => { if (browser) await browser.close(); });

async function open(t, { items = [DECISION, TASK], answers = {}, failDelete = false, comments = { can: "available" }, storage = {} } = {}) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage();
  page.setDefaultTimeout(5000);
  t.after(() => page.close());
  // The page is served from a stand-in origin, so the init script and localStorage both apply.
  // Every other request (the fonts) is refused.
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html", body: html }) : r.abort()));
  await page.addInitScript(stubDb, { items, answers, failDelete, comments });
  await page.addInitScript((kv) => { for (const k in kv) localStorage.setItem(k, kv[k]); }, storage);
  await page.goto(ORIGIN);
  await page.waitForFunction("state.items.length > 0"); // the stub database has delivered the items
  if (Object.keys(answers).length) await page.check("#showDone"); // an answered item hides by default
  await page.waitForSelector(`#n-${DECISION.id}`);
  return page;
}
const card = (page, it) => page.locator("article.card", { has: page.locator(`#n-${it.id}`) });
const answers = (page) => page.evaluate(() => window.__answers());

test("a decision offers None of these, and it needs a note before it saves", async (t) => {
  const page = await open(t); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("None of these").click();
  const save = c.getByRole("button", { name: "Save answer" });
  assert.equal(await save.isDisabled(), true, "Save is open on None of these with no note");
  await page.fill(`#n-${DECISION.id}`, "   ");
  assert.equal(await save.isDisabled(), true, "a blank note counts as a note");
  await page.fill(`#n-${DECISION.id}`, "Green, none of these fit");
  await save.click();
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "none");
  assert.equal(a.note, "Green, none of these fit");
  assert.equal(a.item, DECISION.id);
});

test("the copied answer line reads none of these with the note", async (t) => {
  const page = await open(t, { answers: { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "none", note: "Green" } } });
  if (!page) return;
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await page.click("#copy");
  assert.equal(await page.evaluate(() => window.__copied), "27 none of these (Green)");
});

test("Clear unselects a drafted pick that was never saved", async (t) => {
  const page = await open(t); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("a) Red").click();
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), true);
  await c.getByRole("button", { name: "Clear" }).click();
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false, "the pick is still selected after Clear");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.draft")), "{}");
  assert.deepEqual(await page.evaluate(() => window.__log), [], "Clear on a draft wrote to the database");
});

test("Clear deletes a saved decision answer, so the item reads as unanswered", async (t) => {
  const page = await open(t, { answers: { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "a", note: "" } } });
  if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Clear" }).click();
  await page.waitForFunction((id) => !(id in window.__answers()), DECISION.id);
  assert.deepEqual(await page.evaluate(() => window.__log), [["delete", "answers", DECISION.id]]);
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false);
  assert.equal(await c.getByRole("button", { name: "Save answer" }).count(), 1);
});

test("Clear deletes a task's done mark too", async (t) => {
  const page = await open(t, { answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } } });
  if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Clear" }).click();
  await page.waitForFunction((id) => !(id in window.__answers()), TASK.id);
  assert.equal(await card(page, TASK).getByRole("button", { name: "Mark done" }).count(), 1);
});

const SAVED_A = { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "a", note: "" } };

test("Clear shows as soon as the owner types a note, and clears it", async (t) => {
  const page = await open(t); if (!page) return;
  const c = card(page, DECISION);
  await page.fill(`#n-${DECISION.id}`, "a thought");
  await c.getByRole("button", { name: "Clear" }).click();
  assert.equal(await page.inputValue(`#n-${DECISION.id}`), "");
});

test("a Clear the store refuses keeps the pick and says so", async (t) => {
  const page = await open(t, { answers: SAVED_A, failDelete: true }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("b) Blue").click();
  await c.getByRole("button", { name: "Clear" }).click();
  await c.getByText("Not cleared (denied)", { exact: false }).waitFor();
  const draft = JSON.parse(await page.evaluate(() => localStorage.getItem("waiting.draft")));
  assert.equal(draft[DECISION.id] && draft[DECISION.id].choice, "b", "the draft went although the answer stayed");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-b`), true);
  assert.ok((await answers(page))[DECISION.id], "the saved answer is gone");
});

test("a saved none note does not ride along when the owner picks an option", async (t) => {
  const page = await open(t, { answers: { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "none", note: "Green" } } });
  if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("b) Blue").click();
  await c.getByRole("button", { name: "Update answer" }).click();
  await page.waitForFunction((id) => window.__answers()[id].choice === "b", DECISION.id);
  assert.equal((await answers(page))[DECISION.id].note, "");
});

const sent = (page) => page.evaluate(() => window.__sent);
const settle = (page) => page.waitForFunction(() => !document.body.textContent.includes("Saving…"));

test("a save sends one notice that names the item and the choice", async (t) => {
  const page = await open(t); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("a) Red").click();
  await page.fill(`#n-${DECISION.id}`, "bold");
  await c.getByRole("button", { name: "Save answer" }).click();
  await page.locator("#barStatus", { hasText: "Claude was told" }).waitFor();
  const s = await sent(page);
  assert.equal(s.length, 1);
  assert.match(s[0].text, /27 a \(bold\)/);
  assert.match(s[0].text, /test thread/);
  assert.ok(s[0].anchor, "the first notice starts an anchored thread");
  assert.ok((await answers(page))[DECISION.id], "the answer did not land");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.thread")), "t-new-1");
});

test("a task save names the item as done", async (t) => {
  const page = await open(t); if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  await page.waitForFunction(() => window.__sent.length === 1);
  assert.match((await sent(page))[0].text, /28 done/);
});

test("a second save replies into the stored thread", async (t) => {
  const page = await open(t, { storage: { "waiting.thread": "t-old" } }); if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  await page.waitForFunction(() => window.__sent.length === 1);
  const s = await sent(page);
  assert.equal(s[0].threadId, "t-old");
  assert.equal(s[0].anchor, undefined);
});

test("Accept every pick sends exactly one notice for the batch", async (t) => {
  const two = { ...DECISION, id: "pick-a-shape", n: 29, title: "Pick a shape" };
  const page = await open(t, { items: [DECISION, two, TASK] }); if (!page) return;
  await page.click("#useAll");
  await page.click("#useAll");
  await page.waitForFunction(() => window.__sent.length >= 1);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  const s = await sent(page);
  assert.equal(s.length, 1, "one notice per batch");
  assert.match(s[0].text, /27 a/);
  assert.match(s[0].text, /29 a/);
});

test("no_session sends nothing and the save still lands", async (t) => {
  const page = await open(t, { comments: { can: "no_session" } }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("a) Red").click();
  await c.getByRole("button", { name: "Save answer" }).click();
  await page.locator("#barStatus", { hasText: "No session was told" }).waitFor();
  assert.equal((await sent(page)).length, 0);
  assert.ok((await answers(page))[DECISION.id]);
});

test("a send that rejects leaves the save and says no session was told", async (t) => {
  const page = await open(t, { comments: { can: "available", failCode: "claude_unavailable" } }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("a) Red").click();
  await c.getByRole("button", { name: "Save answer" }).click();
  await page.locator("#barStatus", { hasText: "No session was told" }).waitFor();
  assert.equal((await sent(page)).length, 1, "no retry loop");
  assert.ok((await answers(page))[DECISION.id]);
});

test("a canSendToClaude that rejects counts as unavailable", async (t) => {
  const page = await open(t, { comments: { canThrows: true } }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("a) Red").click();
  await c.getByRole("button", { name: "Save answer" }).click();
  await page.locator("#barStatus", { hasText: "No session was told" }).waitFor();
  assert.ok((await answers(page))[DECISION.id]);
});

test("a page without the comments capability still saves", async (t) => {
  const page = await open(t, { comments: null }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("a) Red").click();
  await c.getByRole("button", { name: "Save answer" }).click();
  await page.locator("#barStatus", { hasText: "No session was told" }).waitFor();
  assert.ok((await answers(page))[DECISION.id]);
});

test("a not_found on the stored thread starts a new anchored thread", async (t) => {
  const page = await open(t, { comments: { can: "available", goneThreads: ["t-old"] }, storage: { "waiting.thread": "t-old" } });
  if (!page) return;
  const c = card(page, DECISION);
  await c.getByText("a) Red").click();
  await c.getByRole("button", { name: "Save answer" }).click();
  await page.locator("#barStatus", { hasText: "Claude was told" }).waitFor();
  const s = await sent(page);
  assert.equal(s.length, 2);
  assert.equal(s[0].threadId, "t-old");
  assert.ok(s[1].anchor && s[1].anchor.tag === "H1", "the new thread anchors at the h1");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.thread")), "t-new-2");
});
