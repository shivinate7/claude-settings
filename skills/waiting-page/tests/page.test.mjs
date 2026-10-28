// Browser tests for the waiting page template (skill waiting-page).
//   NODE_PATH=<dir with playwright> node --test skills/waiting-page/tests/page.test.mjs
// A stub `window.claude.use("db")` stands in for the artifact database and records every write and
// delete. No Playwright or no Chromium: skipped on a laptop, a fail in CI
// (testing/skip-locally-fail-in-ci.mjs).
// Seam: PAGE_UNDER_TEST is the page to load, for a red run against another copy.
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
const DESIGN_SLOT = '<script type="application/json" id="designData">{}</script>';

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
const mk = (id, n, over = {}) => ({ ...DECISION, id, n, title: "Question " + n, ...over });
const LONG = "A long context that runs past three lines on a phone. ".repeat(8);

// Runs in the page before its script. Collections are maps of id to data; listeners fire on change.
function stubDb({ items, rawItems, answers, failDelete, failDeleteIn, failSet, comments, meta, groups, receipts }) {
  const data = { items: { ...Object.fromEntries(items.map((i) => [i.id, i])), ...rawItems }, answers: { ...answers }, meta: meta ? { page: meta } : {}, groups: { ...groups }, receipts: { ...receipts } };
  const subs = {}, docSubs = {};
  window.__log = [];
  const snap = (name) => ({ docs: Object.entries(data[name] || {}).map(([id, v]) => ({ id, data: () => v })) });
  const dsnap = (name, id) => ({ exists: !!(data[name] || {})[id], data: () => (data[name] || {})[id] || null });
  const fire = (name, id) => {
    (subs[name] || []).forEach((cb) => cb(snap(name)));
    (docSubs[name + "/" + id] || []).forEach((cb) => cb(dsnap(name, id)));
  };
  window.__answers = () => data.answers;
  const db = {
    collection: (name) => ({
      onSnapshot: (cb) => { (subs[name] = subs[name] || []).push(cb); setTimeout(() => cb(snap(name)), 0); return () => {}; },
      doc: (id) => ({
        get: async () => dsnap(name, id),
        set: async (body) => { if (failSet) throw { code: "denied" }; window.__log.push(["set", name, id, body]); (data[name] = data[name] || {})[id] = body; setTimeout(() => fire(name, id), 0); },
        delete: async () => { if (failDelete || failDeleteIn === name) throw { code: "denied" }; window.__log.push(["delete", name, id]); delete (data[name] || {})[id]; setTimeout(() => fire(name, id), 0); },
        onSnapshot: (cb) => { (docSubs[name + "/" + id] = docSubs[name + "/" + id] || []).push(cb); setTimeout(() => cb(dsnap(name, id)), 0); return () => {}; },
      }),
    }),
  };
  // comments: null (capability absent) or { can, canThrows, failCodes, goneThreads }.
  // failCodes rejects every send; goneThreads rejects a send into those thread ids with not_found.
  window.__sent = [];
  const cm = comments && {
    canSendToClaude: async () => { if (comments.canHangs) return new Promise(() => {}); if (comments.canThrows) throw { code: "unavailable" }; return comments.can || "available"; },
    anchorFor: async (el) => ({ path: "h1", x: 0, y: 0, tag: el.tagName }),
    sendToClaude: async (target) => {
      window.__sent.push(target);
      if (comments.sendDelay) await new Promise((r) => setTimeout(r, comments.sendDelay));
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

async function open(t, { items = [DECISION, TASK], rawItems = {}, answers = {}, failDelete = false, failDeleteIn = "", failSet = false, comments = { can: "available" }, storage = {}, meta = null, groups = {}, receipts = {}, designData = null, viewport = { width: 1280, height: 900 }, scheme = "light" } = {}) {
  browser = browser || await needEnv(t, "chromium", async () => require("playwright").chromium.launch());
  if (!browser) return null;
  const page = await browser.newPage({ viewport });
  page.setDefaultTimeout(Number(process.env.WP_TIMEOUT) || 5000);
  t.after(() => page.close());
  await page.emulateMedia({ colorScheme: scheme });
  const body = designData ? html.replace(DESIGN_SLOT, `<script type="application/json" id="designData">${JSON.stringify(designData).replace(/</g, "\\u003c")}</script>`) : html;
  // The page is served from a stand-in origin, so the init script and localStorage both apply.
  // Every other request (the fonts) is refused.
  await page.route("**/*", (r) => (r.request().url() === ORIGIN ? r.fulfill({ contentType: "text/html; charset=utf-8", body }) : r.abort()));
  await page.addInitScript(() => { new MutationObserver(() => { const w = document.querySelector(".dfitwrap"); if (w && window.__firstFit === undefined) window.__firstFit = w.getBoundingClientRect().height; }).observe(document, { childList: true, subtree: true }); });
  await page.addInitScript(stubDb, { items, rawItems, answers, failDelete, failDeleteIn, failSet, comments, meta, groups, receipts });
  await page.addInitScript((kv) => { for (const k in kv) localStorage.setItem(k, kv[k]); }, storage);
  await page.goto(ORIGIN);
  await page.waitForFunction("state.items.length > 0"); // the stub database has delivered the items
  await page.waitForSelector(`#item-${items.length ? items[0].id : Object.keys(rawItems)[0]}`);
  return page;
}
const card = (page, it) => page.locator(`#item-${it.id}`);
const answers = (page) => page.evaluate(() => window.__answers());
// A tap on an option's picture opens the viewer (d9 ruling), so a pick taps the option's label text.
const choose = (page, it, key) => page.locator(`label[for="o-${it.id}-${key}"] .lab`).click();
const takePick = (page, it) => card(page, it).getByRole("button", { name: /Take my pick/ }).click();
const addNote = async (page, it, text) => { await card(page, it).getByRole("button", { name: "Add a note" }).click(); await page.fill(`#n-${it.id}`, text); };
const send = (page) => page.click("#send");
const written = (page) => page.waitForFunction(() => window.__log.some((l) => l[0] === "set"));
const geo = (page) => page.evaluate(() => ({
  h: document.documentElement.scrollHeight,
  cards: [...document.querySelectorAll("article.card")].map((c) => { const r = c.getBoundingClientRect(); return [c.id, Math.round(r.top + scrollY), Math.round(r.height)]; }),
}));
const SAVED_A = { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "a", note: "" } };
// An option may carry design: "<slug>", and its mockup shows inside that option's card (designData holds the HTML).
const opt = (key, label, design) => ({ key, label, how: "h", gain: "g", lose: "l", ...(design ? { design } : {}) });
const DESIGNS = { s1: "<p>one</p>", s2: "<p>two</p>" };
const optFrame = (it, key) => `label.opt[for="o-${it.id}-${key}"] iframe`;

// ---------------------------------------------------------------- the final design

test("a rule question starts blank, my pick is starred in its card, and Take my pick fills it in one tap", async (t) => {
  const page = await open(t); if (!page) return;
  assert.equal(await page.locator(`input[name="g-${DECISION.id}"]:checked`).count(), 0, "an option is preselected");
  const star = page.locator(`label[for="o-${DECISION.id}-a"] .pick`);
  assert.match(await star.textContent(), /Red is bold\./);
  assert.equal(await star.locator("svg").count(), 1, "the pick box holds no inline sparkle icon");
  assert.doesNotMatch(await star.textContent(), /[★⭐]/, "the pick box still holds a star character");
  assert.equal(await page.locator(`label[for="o-${DECISION.id}-b"] .pick`).count(), 0, "the star sits on a second option");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open with nothing answered");
  await takePick(page, DECISION);
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), true);
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.deepEqual([a.item, a.n, a.choice, a.note], [DECISION.id, 27, "a", "accepted pick"]);
});

test("the list has three tiers read from holds and by, then Pick stands last", async (t) => {
  const items = [
    mk("calm-dec", 1), { ...TASK, id: "calm-task", n: 2 },
    mk("due-late", 3, { by: "2026-11-30T12:00:00Z" }), mk("due-soon", 4, { by: "2026-11-02T12:00:00Z" }),
    mk("hold-new", 5, { holds: "A lane waits.", added: "2026-10-26T10:00:00Z" }), mk("hold-old", 6, { holds: "A merge waits.", added: "2026-10-25T10:00:00Z" }),
    mk("stands-1", 7, { stands: true }),
  ];
  const page = await open(t, { items }); if (!page) return;
  const order = await page.evaluate(() => [...document.querySelectorAll("section.tier")].map((s) => [s.id, s.querySelector("h2").textContent.replace(/\d+$/, ""), [...s.querySelectorAll("article.card")].map((c) => c.id.slice(5))]));
  assert.deepEqual(order, [
    ["tier-holds", "Blocking", ["hold-old", "hold-new"]],
    ["tier-due", "Upcoming", ["due-soon", "due-late"]],
    ["tier-calm", "Whenever", ["calm-dec", "calm-task"]],
    ["tier-stands", "Pick stands", ["stands-1"]],
  ]);
  const wait = await card(page, items[4]).locator(".stake.holds").textContent();
  assert.match(wait, /A lane waits\./);
});

test("related items share one frame with one sentence, in the most urgent tier of any member", async (t) => {
  const items = [mk("g-calm", 1, { group: "pair" }), mk("g-hold", 2, { group: "pair", holds: "Stuck." }), mk("loner", 3)];
  const page = await open(t, { items, groups: { pair: { title: "Answer these two together", why: "No. 2 lands only if No. 1 is yes." } } }); if (!page) return;
  const frame = page.locator("#tier-holds section.bundle#group-pair");
  assert.equal(await frame.locator("article.card").count(), 2, "both members sit in the one frame");
  assert.equal(await page.locator("#tier-calm #item-g-calm").count(), 0, "a member stayed in its own tier");
  const head = await frame.locator("header").first().textContent();
  assert.match(head, /Answer these two together/);
  assert.match(head, /No\. 2 lands only if No\. 1 is yes\./);
  assert.match(await card(page, items[0]).locator(".top").textContent(), /goes with No\. 2/);
});

test("a stands item sits in the last section, goes with the next Send, and a changed pick wins", async (t) => {
  const s1 = mk("stand-one", 7, { stands: true }), s2 = mk("stand-two", 8, { stands: true });
  const plain = mk("rule-q", 9);
  const page = await open(t, { items: [s1, s2, plain] }); if (!page) return;
  assert.equal(await page.locator("#tier-stands article.card").count(), 2);
  assert.equal(await page.isChecked(`#o-${s1.id}-a`), true, "a stood pick is not shown");
  assert.equal(await page.locator(`input[name="g-${plain.id}"]:checked`).count(), 0, "a rule question is preselected");
  assert.match(await page.locator("#barStatus").textContent(), /2 where my pick stands/);
  await choose(page, s2, "b");
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  const a = await answers(page);
  assert.deepEqual([a[s1.id].choice, a[s1.id].note], ["a", "accepted pick"]);
  assert.deepEqual([a[s2.id].choice, a[s2.id].note], ["b", ""]);
  assert.equal(plain.id in a, false, "an unanswered rule question was sent");
});

test("a stands item outside the last section is never sent for the owner", async (t) => {
  const grouped = mk("grouped-stand", 1, { stands: true, group: "pair" }), mate = mk("mate", 2, { group: "pair" });
  const nopick = mk("no-pick", 3, { stands: true, pick: "zzz" });
  const page = await open(t, { items: [grouped, mate, nopick] }); if (!page) return;
  assert.equal(await page.locator("#tier-stands #item-grouped-stand").count(), 0);
  assert.equal(await page.locator(`input[name="g-${grouped.id}"]:checked`).count(), 0, "a grouped stands item is preselected");
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on picks nobody saw in the last section");
  assert.equal(await page.locator(`input[name="g-${nopick.id}"]:checked`).count(), 0, "a pick that is no option stood");
});

test("one Send writes every ready answer in the old record shape and leaves the rest open", async (t) => {
  const d1 = mk("d-one", 1), d2 = mk("d-two", 2), d3 = mk("d-three", 3), task = { ...TASK };
  const page = await open(t, { items: [d1, d2, d3, task] }); if (!page) return;
  await choose(page, d1, "b");
  await takePick(page, d2);
  await card(page, task).getByRole("button", { name: "Mark done" }).click();
  assert.equal(await page.locator("#send").textContent(), "Send 3 answers");
  await send(page);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 3);
  const a = await answers(page);
  assert.deepEqual(Object.keys(a).sort(), ["d-one", "d-two", TASK.id]);
  assert.deepEqual([a["d-one"].item, a["d-one"].n, a["d-one"].choice, a["d-one"].note], ["d-one", 1, "b", ""]);
  assert.equal(a["d-two"].note, "accepted pick");
  assert.equal(a[TASK.id].done, true);
  assert.ok(!Number.isNaN(Date.parse(a["d-one"].at)), "at is an ISO time");
  assert.equal(await page.evaluate(() => window.__log.filter((l) => l[0] === "set").length), 3);
  assert.equal(await page.evaluate(() => window.__sent.length), 1, "one notice for the batch");
});

test("Send shows a stamp with the Chicago time, and Undo takes back exactly what it wrote", async (t) => {
  const d1 = mk("d-one", 1), d2 = mk("d-two", 2);
  const page = await open(t, { items: [d1, d2] }); if (!page) return;
  await takePick(page, d1); await choose(page, d2, "b");
  await send(page);
  await page.locator("#sent .stamp").waitFor();
  assert.match(await page.locator("#sent .stamp").textContent(), /Sent\s*\d\d:\d\d C[DS]T/);
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 0);
  assert.equal(await page.locator("#sent").isHidden(), true);
  assert.equal(await page.isChecked(`#o-d-one-a`), true, "Undo lost the owner's pick");
  assert.equal(await page.isChecked(`#o-d-two-b`), true);
  assert.equal(await page.locator("#send").textContent(), "Send 2 answers");
});

test("Undo puts back the answer a change had replaced", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  await card(page, DECISION).getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "b");
  await send(page);
  await page.waitForFunction((id) => window.__answers()[id].choice === "b", DECISION.id);
  await page.locator("#undoBtn").click();
  await page.waitForFunction((id) => window.__answers()[id].choice === "a", DECISION.id);
});

test("the Undo button goes after 8 seconds", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.locator("#undoBtn").waitFor({ state: "detached", timeout: 9500 });
  assert.ok((await answers(page))[DECISION.id], "the answer went with the button");
});

test("a card becomes a receipt in place, with Change", async (t) => {
  const items = [mk("above", 1), mk("target", 2), mk("below", 3, { context: LONG })];
  const page = await open(t, { items }); if (!page) return;
  const before = await geo(page);
  await choose(page, items[1], "a");
  await send(page);
  await page.waitForFunction(() => !!window.__answers().target);
  const c = card(page, items[1]);
  await c.locator(".receipt").waitFor();
  assert.match(await c.locator(".receipt").textContent(), /You chose A: Red/);
  assert.deepEqual((await geo(page)).cards.map((x) => x[0]), before.cards.map((x) => x[0]), "the order changed");
  await c.getByRole("button", { name: "Change" }).click();
  assert.equal(await page.isChecked("#o-target-a"), true, "Change lost the saved pick");
  assert.equal(await c.locator(".receipt").count(), 0);
});

for (const withDesigns of [false, true]) for (const viewport of [{ width: 1280, height: 900 }, { width: 390, height: 800 }]) {
  test(`nothing moves when an answer is picked or sent, at ${viewport.width} wide${withDesigns ? ", with option designs" : ""}`, async (t) => {
    const items = [
      mk("first", 1, { context: LONG, holds: "A lane waits.", options: [opt("a", "Red", withDesigns ? "s1" : undefined), opt("b", "Blue with a long label that cannot fit on one line of the ready note at 390 wide", withDesigns ? "s2" : undefined)] }), mk("second", 2, { context: LONG, stands: true }),
      { ...TASK, id: "a-task", n: 3 }, mk("third", 4, { context: LONG, by: "2030-01-01T00:00:00Z" }),
      mk("fourth", 5, { context: LONG, options: [...DECISION.options, { key: "c", label: "Green", how: "h", gain: "g", lose: "l" }] }),
    ];
    const page = await open(t, { items, viewport, designData: withDesigns ? DESIGNS : null }); if (!page) return;
    // With option designs, the in-card frames must be the same DOM nodes after each pick, so none reloads.
    let sent = false;
    if (withDesigns) {
      assert.equal(await page.locator("#item-first iframe").count(), 2, "the option designs have no frames in their cards");
      await page.evaluate(() => { window.__of = [...document.querySelectorAll("#item-first iframe")]; });
    }
    const base = await geo(page);
    const same = async (what) => {
      assert.deepEqual(await geo(page), base, "the page moved on " + what);
      if (withDesigns && !sent) assert.equal(await page.evaluate(() => { const now = [...document.querySelectorAll("#item-first iframe")]; return now.length === window.__of.length && now.every((f, n) => f === window.__of[n]); }), true, "an in-card frame was rebuilt on " + what);
    };
    await choose(page, items[0], "b"); await same("a pick");
    await choose(page, items[0], "a"); await same("a second pick");
    await takePick(page, items[3]); await same("Take my pick");
    await choose(page, items[3], "a"); await same("a click on the selected pick");
    await card(page, items[4]).getByRole("button", { name: /Take my pick/ }).click();
    await choose(page, items[4], "c"); await same("a pick after Take my pick");
    await card(page, items[2]).getByRole("button", { name: "Mark done" }).click(); await same("Mark done");
    sent = true;
    await send(page);
    await page.locator("#sent .stamp").waitFor();
    await page.evaluate(() => new Promise((r) => setTimeout(r, 600)));
    await same("Send");
  });
}

test("a saved answer from an earlier page shows as a receipt and nothing is written on load", async (t) => {
  const none = { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "plugged" };
  const page = await open(t, { answers: { ...SAVED_A, [TASK.id]: none } }); if (!page) return;
  assert.match(await card(page, DECISION).locator(".receipt").textContent(), /You chose A: Red/);
  assert.match(await card(page, TASK).locator(".receipt").textContent(), /Marked done/);
  assert.deepEqual(await page.evaluate(() => window.__log), []);
});

test("an answered card without a filing shows Answered, filing pending, never waited", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  const ans = (await c.locator(".ans").textContent()).trim();
  assert.match(ans, /^Answered, filing pending Oct \d+, \d\d:\d\d C[DS]T$/);
  assert.doesNotMatch(await c.locator(".top").textContent(), /waited|Added/i);
  assert.equal(await c.locator(".ans.filed").count(), 0);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /answered, filing pending$/);
});

test("an answered card with receipts shows Answered, filed in the home with the filed time", async (t) => {
  const page = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match((await c.locator(".ans.filed").textContent()).trim(), /^Answered, filed in c1 Oct 25, 22:00 CDT$/);
  assert.equal(await c.locator(".trail").count(), 0);
  assert.doesNotMatch(await c.locator(".top").textContent(), /waited/i);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /answered, filed$/);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("class"), /filed/);
});

test("a read but unfiled answer shows Read by the owner beside Change", async (t) => {
  const page = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match(await c.locator(".receipt .read").textContent(), /^Read by test thread /);
  assert.match((await c.locator(".ans").textContent()).trim(), /^Answered, filing pending /);
});

test("a receipt older than the answer is ignored: a changed answer reads filing pending", async (t) => {
  const later = { [DECISION.id]: { ...SAVED_A[DECISION.id], at: "2026-10-26T04:00:00Z" } };
  const page = await open(t, { answers: later, receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z", filed: "2026-10-26T03:00:00Z" } } }); if (!page) return;
  const c = card(page, DECISION);
  assert.match((await c.locator(".ans").textContent()).trim(), /^Answered, filing pending /);
  assert.equal(await c.locator(".ans.filed").count(), 0);
  assert.equal(await c.locator(".receipt .read").count(), 0);
  assert.doesNotMatch(await page.locator("#c-" + DECISION.id).getAttribute("class"), /filed/);
  assert.match(await page.locator("#c-" + DECISION.id).getAttribute("aria-label"), /filing pending$/);
});

test("times are 24-hour Chicago time with the zone named", async (t) => {
  const page = await open(t, { items: [mk("timed", 1, { by: "2099-10-27T14:45:00Z" })] }); if (!page) return;
  const f = await page.evaluate(() => [fmt("2026-10-26T20:00:00-05:00"), fmt("2026-12-01T06:05:00Z"), fmt("2026-10-27T05:07:00Z", false)]);
  assert.deepEqual(f, ["Oct 26, 20:00 CDT", "Dec 1, 00:05 CST", "00:07 CDT"]);
  const text = await card(page, { id: "timed" }).textContent();
  assert.match(text, /Added Oct 25, 19:00 CDT/);
  assert.match(text, /Answer by Oct 27, 09:45 CDT/);
});

test("long context folds to three lines and opens on More context", async (t) => {
  const page = await open(t, { items: [mk("longone", 1, { context: LONG })] }); if (!page) return;
  const ctx = page.locator("#ctx-longone");
  assert.match(await ctx.getAttribute("class"), /clamp/);
  await page.getByRole("button", { name: "More context" }).click();
  assert.doesNotMatch(await ctx.getAttribute("class"), /clamp/);
});

test("A to C pick on the focused card, and Ctrl+Enter sends", async (t) => {
  const page = await open(t, { items: [DECISION] }); if (!page) return;
  await card(page, DECISION).locator(".title").click();
  await page.keyboard.press("b");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-b`), true);
  await page.keyboard.press("Control+Enter");
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  assert.equal((await answers(page))[DECISION.id].choice, "b");
});

// ---------------------------------------------------------------- repo colour

const BRANDS = ["#b45f06", "#3d5af1", "#0a84ff", "#f47820", "#6f5ca6", "#27553f", "#0b5fff", "#ffffff", "#000000", "#ffff00", "#ff0000", "#00ff00", "#808080", "#4b5a6b", "#e6e6e6", "#1a1a1a", "#ff00ff", "#00ffff", "#7f7f00"];

// The contrast ratio is computed here from the WCAG formula, not by the page's own helper.
const CONTRAST = `
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const L = (h) => { h = h.replace("#", ""); const c = [0, 2, 4].map((i) => lin(parseInt(h.slice(i, i + 2), 16))); return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; };
  const R = (a, b) => { const x = L(a), y = L(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };`;

test("every derived colour reaches 4.5:1 for any brand, light and dark", async (t) => {
  const page = await open(t); if (!page) return;
  const bad = await page.evaluate(`(() => {${CONTRAST}
    const hslHex = (h, s, l) => { s /= 100; l /= 100; const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l); const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1)); return "#" + [f(0), f(8), f(4)].map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join(""); };
    const brands = ${JSON.stringify(BRANDS)};
    for (let h = 0; h < 360; h += 15) for (const [s, l] of [[100, 50], [100, 25], [60, 70], [30, 50], [100, 90], [10, 10], [80, 40]]) brands.push(hslHex(h, s, l));
    const out = [];
    for (const b of brands) {
      const t = derive(b), chk = (what, fg, bg) => { const r = R(fg, bg); if (r < 4.5) out.push(b + " " + what + " " + r.toFixed(2)); };
      chk("header light", t.onL, t.hdrL); chk("header dark", t.onD, t.hdrD);
      chk("ink light", t.inkL, "#ffffff"); chk("ink dark", t.inkD, "#191e26");
      chk("button light", "#ffffff", t.inkL); chk("button dark", "#11151b", t.inkD);
      chk("ink on tint light", t.inkL, t.softL); chk("ink on tint dark", t.inkD, t.softD);
      for (const [k, soft] of [["holds", null], ["due", ["#fbefd9", "#35270f"]], ["good", ["#e0f2e7", "#15301f"]]]) {
        for (const [th, grounds] of [["l", [t.groundL, "#ffffff", t.softL]], ["d", [t.groundD, "#191e26", t.softD]]]) {
          const c = t[k + th]; for (const g of grounds.concat(soft ? [soft[th === "l" ? 0 : 1]] : [])) chk(k + " " + th + " on " + g, c, g);
        }
      }
      chk("blocking line light", t.onHoldsl, t.holdsl); chk("blocking line dark", t.onHoldsd, t.holdsd);
    }
    return out;
  })()`);
  assert.deepEqual(bad, []);
});

for (const scheme of ["light", "dark"]) {
  test(`the colours the page applies from one brand reach 4.5:1, ${scheme}`, async (t) => {
    const page = await open(t, { meta: { identity: { name: "Agent Q", mark: "Q", brand: "#f47820" } }, items: [mk("h", 1, { holds: "x", by: "2030-01-01T00:00:00Z" })], scheme }); if (!page) return;
    await page.waitForFunction(() => document.getElementById("repoName").textContent === "Agent Q");
    const bad = await page.evaluate(`(() => {${CONTRAST}
      const cs = getComputedStyle(document.documentElement), v = (n) => cs.getPropertyValue(n).trim();
      const hdr = getComputedStyle(document.querySelector("header.hdr")), card = getComputedStyle(document.querySelector("article.card")), body = getComputedStyle(document.body);
      const rgb = (c) => "#" + c.match(/\\d+/g).slice(0, 3).map((x) => (+x).toString(16).padStart(2, "0")).join("");
      const out = [], chk = (what, a, b) => { const r = R(a, b); if (r < 4.5) out.push(what + " " + r.toFixed(2)); };
      chk("header text", rgb(hdr.color), rgb(hdr.backgroundColor));
      chk("body text", rgb(body.color), rgb(body.backgroundColor));
      chk("button", v("--on-acc"), v("--acc"));
      chk("link ink on card", v("--acc"), rgb(card.backgroundColor));
      chk("blocking line", v("--on-holds"), v("--holds"));
      return out.concat(v("--hdr") ? [] : ["--hdr empty"]);
    })()`);
    assert.deepEqual(bad, []);
    assert.equal(await page.title(), "Agent Q: waiting on you");
  });
}

test("a page with no brand uses neutral defaults and draws no colour of its own", async (t) => {
  const page = await open(t, { meta: { identity: { name: "No Colour" } } }); if (!page) return;
  await page.waitForFunction(() => document.getElementById("repoName").textContent === "No Colour");
  assert.equal(await page.evaluate(() => document.documentElement.style.getPropertyValue("--r-hdr-l")), "");
  const page2 = await open(t, { meta: { identity: { name: "Bad", brand: "red; background: url(x)" } } });
  await page2.waitForFunction(() => document.getElementById("repoName").textContent === "Bad");
  assert.equal(await page2.evaluate(() => document.documentElement.style.getPropertyValue("--r-hdr-l")), "", "a brand that is no hex was used");
});

// ---------------------------------------------------------------- designs

test("a design shows in a sandboxed frame on its card, and the Designs tab pages through a sheet", async (t) => {
  const it = mk("with-design", 1, { designs: [{ slug: "s1", label: "Option a" }, { slug: "s2", label: "Option b" }] });
  const page = await open(t, { items: [it, mk("other", 2)], designData: { s1: "<p>one</p>", s2: "<p>two</p>" } }); if (!page) return;
  const f = card(page, it).locator("iframe.dframe");
  assert.equal(await f.getAttribute("sandbox"), "allow-scripts");
  assert.match(await f.getAttribute("srcdoc"), /one/);
  await page.evaluate(() => { window.__f = document.querySelector("article.card iframe.dframe"); });
  await choose(page, it, "a");
  assert.equal(await page.evaluate(() => document.querySelector("article.card iframe.dframe") === window.__f), true, "a pick reloaded the live preview");
  assert.match(await page.locator("#tabD").textContent(), /2/);
  await page.click("#tabD");
  await page.locator("#dsheet").waitFor();
  assert.equal(await page.locator("#dTitle").textContent(), "Option a");
  await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Option b");
  await page.click("#dNext"); await page.click("#dNext");
  assert.equal(await page.locator("#dStage iframe").count(), 2, "a frame was built twice");
  await page.click("#dClose");
  assert.equal(await page.locator("#dsheet").isHidden(), true);
});

// An option names its picture with `design` (a slug of the item's `designs`). A look question whose options name a
// design the item lacks shows a plain warning where the picture belongs.
const LOOK_OPTS = ["a", "b", "c"].map((k) => ({ key: k, label: "Layout " + k, how: "h", gain: "g", lose: "l", design: "price-" + k }));
const GITHUB_FOLDER = "Mockups: https://github.com/shivinate7/banchi/tree/main/docs/mockups/price-history";

test("a look question with three options, a GitHub folder link and no designs shows a warning inside each option card", async (t) => {
  const it = mk("price-history-where", 30, { context: GITHUB_FOLDER, look: true, options: LOOK_OPTS.map(({ design, ...o }) => o), pick: "a" });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await card(page, it).locator(".opt .dwarn").count(), 3, "no warning in an option card");
  assert.equal(await card(page, it).locator(".dwarn").count(), 3, "a warning sits outside the option cards");
  assert.match(await card(page, it).locator(".opt .dwarn").first().textContent(), /picture/i);
  assert.equal(await card(page, it).locator("iframe.dframe").count(), 0);
});

const PICS = { "price-a": "<p>a</p>", "price-b": "<p>b</p>", "price-c": "<p>c</p>" };
const picItem = (id, n) => mk(id, n, { options: LOOK_OPTS, pick: "a", designs: LOOK_OPTS.map((o) => ({ slug: o.design, label: o.label })) });

test("each option's picture is inside its own option card; a tap on it opens the viewer and a tap on the card picks", async (t) => {
  const it = picItem("with-pictures", 31);
  const page = await open(t, { items: [it], designData: PICS }); if (!page) return;
  assert.equal(await card(page, it).locator(".dwarn").count(), 0, "a warning shows although every picture is there");
  for (const o of LOOK_OPTS) assert.equal(await card(page, it).locator(`label.opt[for="o-${it.id}-${o.key}"] .opic iframe.dframe`).count(), 1, "no picture in option " + o.key);
  assert.equal(await card(page, it).locator(".dprev").count(), 0, "a picture named by an option also shows at the front");
  const pic = card(page, it).locator(`label.opt[for="o-${it.id}-b"] .opic`);
  assert.ok((await pic.boundingBox()).height >= 40, "the picture is smaller than a thumb");
  await pic.click();
  assert.equal(await page.isChecked(`#o-${it.id}-b`), false, "a tap on the picture picked the option");
  assert.equal(await page.locator("#dsheet").isVisible(), true, "the viewer did not open");
  await page.click("#dClose");
  await card(page, it).locator(`label.opt[for="o-${it.id}-b"] .lab`).click();
  assert.equal(await page.isChecked(`#o-${it.id}-b`), true, "a tap on the card did not pick the option");
  await card(page, it).locator(`label.opt[for="o-${it.id}-c"] .how`).click();
  assert.equal(await page.isChecked(`#o-${it.id}-c`), true, "a tap on the card's text did not pick the option");
  assert.equal(await card(page, it).locator(".opt iframe.dframe").first().evaluate((f) => getComputedStyle(f).pointerEvents), "none", "the frame swallows the click");
});

const WIDE = [["a", "Layout A"], ["b", "Layout B"]];
const viewerItem = () => mk("viewer-q", 50, {
  pick: "a", options: WIDE.map(([k, l]) => ({ key: k, label: l, how: "h", gain: "g", lose: "l", design: "v-" + k })),
  designs: [{ slug: "v-a", label: "A phone", width: "Phone" }, { slug: "v-a2", option: "a", label: "A wide", width: "Wide" },
    { slug: "v-b", label: "B phone", width: "Phone" }, { slug: "v-b2", option: "b", label: "B wide", width: "Wide" }],
});
const VIEWER_DATA = { "v-a": "<p>a</p>", "v-a2": "<p>a2</p>", "v-b": "<p>b</p>", "v-b2": "<p>b2</p>" };

test("the viewer counts options times widths, steps with Prev and Next, wraps at the ends, and offers full size", async (t) => {
  const it = viewerItem();
  const page = await open(t, { items: [it], designData: VIEWER_DATA }); if (!page) return;
  await page.evaluate(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; });
  await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
  assert.equal(await page.locator("#dTitle").textContent(), "Layout A (Phone)");
  assert.equal(await page.locator("#dPos").textContent(), "1 of 4");
  await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Layout A (Wide)");
  await page.click("#dNext"); await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Layout B (Wide)");
  assert.equal(await page.locator("#dPos").textContent(), "4 of 4");
  await page.click("#dNext");
  assert.equal(await page.locator("#dPos").textContent(), "1 of 4", "Next does not wrap");
  await page.click("#dPrev");
  assert.equal(await page.locator("#dPos").textContent(), "4 of 4", "Prev does not wrap");
  await page.click("#dFull");
  assert.equal(await page.evaluate(() => window.__opened.length), 1, "Open full size opened nothing");
  await page.click("#dClose");
  assert.equal(await page.locator("#dsheet").isHidden(), true);
});

for (const width of [390, 1440]) {
  test(`a design's focus fills the card box whole, never cut, at ${width} wide`, async (t) => {
    const mock = '<body style="margin:0"><div style="height:700px"></div><div id="panel" style="width:300px;height:200px;background:#a62"></div><div style="height:500px"></div></body>';
    const it = mk("focus-q", 51, { pick: "a", options: [{ key: "a", label: "A", how: "h", gain: "g", lose: "l", design: "f-a" }], designs: [{ slug: "f-a", label: "A", focus: "#panel" }] });
    const page = await open(t, { items: [it], designData: { "f-a": mock }, viewport: { width, height: 900 } }); if (!page) return;
    const wrap = card(page, it).locator(".opic .dfitwrap");
    await page.waitForFunction((id) => { const w = document.querySelector(`#item-${id} .opic .dfitwrap`); return w && w.getBoundingClientRect().height > 0 && w.getBoundingClientRect().height < 400 && getComputedStyle(w.querySelector("iframe")).transform !== "none" && w.querySelector("iframe").style.transform.includes("translate"); }, it.id);
    const m = await wrap.evaluate((w) => {
      const f = w.querySelector("iframe"), r = w.getBoundingClientRect(), fr = f.getBoundingClientRect();
      const sc = fr.width / 390;
      return { wrapTop: r.top, wrapH: r.height, wrapW: r.width, panelTop: fr.top + 700 * sc, panelH: 200 * sc, panelW: 300 * sc };
    });
    assert.ok(Math.abs(m.panelTop - m.wrapTop) < 4, `the focused element starts ${m.panelTop - m.wrapTop}px from the top of the box`);
    assert.ok(m.panelH <= m.wrapH + 1, "the focused element is cut at the bottom");
    assert.ok(m.panelW <= m.wrapW + 1, "the focused element is cut at the side");
    assert.ok(m.wrapH < 260, `the box shows more than the focused element (${m.wrapH}px)`);
  });
}

test("SKILL.md and the designer agent carry the mockup convention", async () => {
  const skill = fs.readFileSync(path.join(HERE, "..", "SKILL.md"), "utf8");
  const designer = fs.readFileSync(path.join(HERE, "..", "..", "..", "agents", "designer.md"), "utf8");
  for (const [name, text] of [["SKILL.md", skill], ["designer.md", designer]]) {
    assert.match(text, /"Sample" banner/, name + " has no Sample banner line");
    assert.match(text, /"Today: <part>"/, name + " has no Today label");
    assert.match(text, /"New: <part>"/, name + " has no New label");
  }
  assert.match(skill, /`focus`/);
  assert.match(skill, /tap on (an option's|the) picture opens the viewer/i);
});

test("a design that names no option shows at the front of the item, before the options", async (t) => {
  const it = mk("loose-design", 34, { designs: [{ slug: "s1", label: "Overview" }] });
  const page = await open(t, { items: [it], designData: { s1: "<p>one</p>" } }); if (!page) return;
  const first = await card(page, it).evaluate((c) => { const f = c.querySelector(".dprev"), o = c.querySelector(".opts"); return !!f && !!o && !!(f.compareDocumentPosition(o) & Node.DOCUMENT_POSITION_FOLLOWING); });
  assert.equal(first, true);
});

test("an item with some designs but not every option's design warns in the option cards that lack one", async (t) => {
  const it = mk("half-pictures", 32, { look: true, options: LOOK_OPTS, pick: "a", designs: [{ slug: "price-a", label: "Layout a" }] });
  const page = await open(t, { items: [it], designData: { "price-a": "<p>a</p>" } }); if (!page) return;
  assert.equal(await card(page, it).locator(".opt .dwarn").count(), 2);
  assert.equal(await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .dwarn`).count(), 0);
});

for (const width of [390, 1440]) {
  test(`a tall mockup is never cropped, at ${width} wide`, async (t) => {
    const it = picItem("tall", 35);
    const tall = '<body style="margin:0"><div style="height:1200px;background:#2a6">tall</div></body>';
    const page = await open(t, { items: [it], designData: { ...PICS, "price-a": tall }, viewport: { width, height: 900 } }); if (!page) return;
    const wrap = card(page, it).locator(`label.opt[for="o-${it.id}-a"] .dfitwrap`);
    await page.waitForFunction((sel) => document.querySelector(sel).getBoundingClientRect().height > 300, `#item-${it.id} label.opt .dfitwrap`);
    const m = await wrap.evaluate((w) => { const f = w.querySelector("iframe").getBoundingClientRect(), r = w.getBoundingClientRect(); return { wrapW: r.width, wrapH: r.height, frameW: f.width, frameH: f.height }; });
    const scale = m.frameW / 390;
    assert.ok(Math.abs(m.frameH - 1200 * scale) < 3, `the frame is ${m.frameH} high, the mockup ${1200 * scale}`);
    assert.ok(m.wrapH >= m.frameH - 1, "the wrapper cuts the bottom of the mockup");
    assert.ok(m.frameW <= m.wrapW + 1, "the mockup is wider than the card");
  });

  test(`a long option key stays on one line and never overlaps the title, at ${width} wide`, async (t) => {
    const it = mk("long-key", 36, { options: [
      { key: "feed-near", label: "Show the price history near the feed in a sheet", how: "h", gain: "g", lose: "l" },
      { key: "feed-far-away-key", label: "Far", how: "h", gain: "g", lose: "l" }], pick: "feed-near" });
    const page = await open(t, { items: [it], viewport: { width, height: 900 } }); if (!page) return;
    for (const o of it.options) {
      const m = await card(page, it).locator(`label.opt[for="o-${it.id}-${o.key}"]`).evaluate((l) => {
        const k = l.querySelector(".key"), b = l.querySelector(".lab");
        return { ws: getComputedStyle(k).whiteSpace, k: k.getBoundingClientRect().toJSON(), b: b.getBoundingClientRect().toJSON() };
      });
      assert.equal(m.ws, "nowrap", "the chip wraps");
      assert.ok(m.k.right <= m.b.left + 1 || m.k.bottom <= m.b.top + 1, `the chip overlaps the title for ${o.key}`);
    }
  });
}

test("an item that is not a look question never warns about pictures, with or without a named design", async (t) => {
  const plain = mk("not-a-look", 37, { options: LOOK_OPTS.map(({ design, ...o }) => o), pick: "a" });
  const named = mk("names-a-design", 38, { options: LOOK_OPTS, pick: "a" });
  const page = await open(t, { items: [plain, named] }); if (!page) return;
  assert.equal(await page.locator(".dwarn").count(), 0);
});

test("a long link in the context never widens the page on a phone", async (t) => {
  const it = mk("price-history-link", 33, { context: GITHUB_FOLDER, options: LOOK_OPTS, pick: "a" });
  const page = await open(t, { items: [it], viewport: { width: 390, height: 900 } }); if (!page) return;
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true, "the page scrolls sideways");
});

test("a page with no designs has no Designs tab", async (t) => {
  const page = await open(t); if (!page) return;
  assert.equal(await page.locator("#tabD").isHidden(), true);
});

test("a decision option with a design shows it in a sandboxed frame inside its own card", async (t) => {
  const it = mk("opt-design", 1, { options: [opt("a", "Red", "s1"), opt("b", "Blue")] });
  const page = await open(t, { items: [it], designData: DESIGNS }); if (!page) return;
  const f = page.locator(optFrame(it, "a"));
  assert.equal(await f.count(), 1, "no frame inside option a's card");
  assert.equal(await f.getAttribute("sandbox"), "allow-scripts");
  assert.ok((await f.getAttribute("srcdoc")).startsWith("<p>one</p>"), "the srcdoc is not the design");
  assert.equal(await page.locator(optFrame(it, "b")).count(), 0, "option b has no design, so it has no frame");
});

test("an option whose design is missing from the page says so in its frame", async (t) => {
  const it = mk("gone-design", 1, { options: [opt("a", "Red", "nope"), opt("b", "Blue")] });
  const page = await open(t, { items: [it], designData: DESIGNS }); if (!page) return;
  assert.equal(await page.locator(optFrame(it, "a")).count(), 1, "no frame inside option a's card");
  await page.frameLocator(optFrame(it, "a")).getByText("This design is missing from the page.").waitFor();
});

test("an option design counts on the Designs tab, and the sheet pages through the option designs", async (t) => {
  const it = mk("opt-only", 1, { options: [opt("a", "Red", "s1"), opt("b", "Blue", "s2")] });
  const page = await open(t, { items: [it], designData: DESIGNS }); if (!page) return;
  assert.equal(await page.locator("#tabD").isVisible(), true, "the Designs tab is hidden");
  assert.equal(await page.locator("#dCount").textContent(), "2", "the count leaves out option designs");
  await page.click("#tabD");
  await page.locator("#dsheet").waitFor();
  const shown = () => page.locator("#dStage .dfitwrap:not(.off) iframe").getAttribute("srcdoc");
  assert.ok((await shown()).startsWith("<p>one</p>"));
  await page.click("#dNext");
  assert.ok((await shown()).startsWith("<p>two</p>"), "Next did not page to the second option design");
  await page.click("#dClose");
  assert.equal(await page.locator("#dsheet").isHidden(), true);
});

test("option rows line up across sibling cards when only one option has a design, at desktop width", async (t) => {
  const it = mk("rows", 1, { options: [
    { ...opt("a", "Red", "s1"), how: "A short way to put it." },
    { ...opt("b", "Blue"), how: "A longer way to put it, which runs onto a second line at desktop width. ".repeat(2) },
  ] });
  const page = await open(t, { items: [it], designData: DESIGNS, viewport: { width: 1280, height: 900 } }); if (!page) return;
  assert.equal(await page.locator(optFrame(it, "a")).count(), 1, "no frame inside option a's card");
  // The pick box is pinned to the bottom of its row, so the pick row is compared by bottom edge.
  const rows = await page.evaluate((id) => ["a", "b"].map((k) => {
    const l = document.querySelector(`label.opt[for="o-${id}-${k}"]`);
    const top = (sel) => Math.round(l.querySelector(sel).getBoundingClientRect().top);
    return { how: top(".how"), gain: top(".tr"), pick: Math.round(l.querySelector(".pick, .nopick").getBoundingClientRect().bottom) };
  }), it.id);
  for (const row of ["how", "gain", "pick"]) assert.ok(Math.abs(rows[0][row] - rows[1][row]) <= 1, `the ${row} rows are not level: ${rows[0][row]} and ${rows[1][row]}`);
});

for (const scheme of ["light", "dark"]) {
  test(`an option design fits a phone with no sideways scroll, ${scheme} scheme`, async (t) => {
    const it = mk("phone-design", 1, { options: [opt("a", "Red", "s1"), opt("b", "Blue")] });
    const page = await open(t, { items: [it], designData: DESIGNS, viewport: { width: 375, height: 800 }, scheme }); if (!page) return;
    const f = page.locator(optFrame(it, "a"));
    assert.equal(await f.count(), 1, "no frame inside option a's card");
    await f.scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, "the page scrolls sideways");
    const box = await f.boundingBox();
    assert.ok(box.x + box.width <= 375, "the option design runs past the phone width");
  });
}

// ---------------------------------------------------------------- answers, notes and withdrawing

test("a decision offers None of these, and it needs a note before it sends", async (t) => {
  const page = await open(t); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "None of these" }).click();
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on None of these with no note");
  await page.fill(`#n-${DECISION.id}`, "   ");
  assert.equal(await page.locator("#send").isDisabled(), true, "a blank note counts as a note");
  await page.fill(`#n-${DECISION.id}`, "Green, none of these fit");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "none");
  assert.equal(a.note, "Green, none of these fit");
  assert.equal(a.item, DECISION.id);
});

test("when the store refuses a write, the answer line can be copied", async (t) => {
  const page = await open(t, { failSet: true }); if (!page) return;
  await card(page, DECISION).getByRole("button", { name: "None of these" }).click();
  await page.fill(`#n-${DECISION.id}`, "Green");
  await send(page);
  await page.locator("#barStatus", { hasText: "Not saved (denied)" }).waitFor();
  await page.evaluate(() => { Object.defineProperty(navigator, "clipboard", { value: { writeText: async (s) => { window.__copied = s; } } }); });
  await page.click("#copy");
  assert.equal(await page.evaluate(() => window.__copied), "27 none of these (Green)");
});

const clearCount = (page) => page.getByRole("button", { name: "Clear" }).count();

test("no Clear button renders, on a fresh card, a drafted pick, a note, a task or a changed answer", async (t) => {
  const page = await open(t, { answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } } }); if (!page) return;
  assert.equal(await clearCount(page), 0);
  await choose(page, DECISION, "a"); await addNote(page, DECISION, "a thought");
  assert.equal(await clearCount(page), 0);
  await card(page, TASK).getByRole("button", { name: "Change" }).click();
  assert.equal(await clearCount(page), 0);
  assert.equal(await page.locator(".clearbtn").count(), 0);
});

test("a second click on the selected option unselects it, with no write", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), true);
  await choose(page, DECISION, "a");
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false, "the pick is still selected after a second click");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.draft")), "{}");
  assert.equal(await page.locator("#send").isDisabled(), true);
  assert.deepEqual(await page.evaluate(() => window.__log), []);
});

test("a second click unselects a stood pick, and it stays unselected", async (t) => {
  const it = mk("stand-solo", 7, { stands: true });
  const page = await open(t, { items: [it] }); if (!page) return;
  assert.equal(await page.isChecked(`#o-${it.id}-a`), true, "the pick does not stand");
  await choose(page, it, "a");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a stood pick cannot be unselected");
  assert.equal(await page.locator("#send").isDisabled(), true, "an unselected stood pick still goes with Send");
  await takePick(page, it);
  assert.equal(await page.isChecked(`#o-${it.id}-a`), true);
  await choose(page, it, "a");
  assert.equal(await page.isChecked(`#o-${it.id}-a`), false, "a pick taken with Take my pick cannot be unselected");
});

test("emptying a note drops it", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, DECISION, "a thought");
  await page.fill(`#n-${DECISION.id}`, "");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.draft")), "{}");
  assert.equal(await page.locator("#send").isDisabled(), true);
});

test("a changed answer left empty makes Send withdraw it", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer", "withdraw is offered with the draft in place");
  await choose(page, DECISION, "a");
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer");
  assert.equal(await page.locator("#send").isDisabled(), false);
  await send(page);
  await page.waitForFunction((id) => !(id in window.__answers()), DECISION.id);
  assert.deepEqual(await page.evaluate(() => window.__log), [["delete", "answers", DECISION.id]]);
  assert.equal(await page.isChecked(`#o-${DECISION.id}-a`), false);
  assert.equal(await c.locator(".receipt").count(), 0);
});

test("a task's done mark is withdrawn the same way", async (t) => {
  const page = await open(t, { answers: { [TASK.id]: { item: TASK.id, n: 28, at: "2026-10-26T01:00:00Z", done: true, note: "" } } });
  if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Change" }).click();
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  assert.equal(await page.locator("#send").textContent(), "Withdraw answer");
  await send(page);
  await page.waitForFunction((id) => !(id in window.__answers()), TASK.id);
  assert.equal(await card(page, TASK).getByRole("button", { name: "Mark done" }).count(), 1);
});

test("a withdraw the store refuses keeps the answer and says so", async (t) => {
  const page = await open(t, { answers: SAVED_A, failDelete: true }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await send(page);
  await c.getByText("Not withdrawn (denied)", { exact: false }).waitFor();
  assert.ok((await answers(page))[DECISION.id], "the saved answer is gone");
});

test("a note with no option picked is an answer: choice none plus the note", async (t) => {
  const page = await open(t); if (!page) return;
  await addNote(page, DECISION, "Green please");
  assert.equal(await page.locator("#send").isDisabled(), false, "Send is shut on a note alone");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  const a = (await answers(page))[DECISION.id];
  assert.equal(a.choice, "none");
  assert.equal(a.note, "Green please");
});

test("a saved none note does not ride along when the owner picks an option", async (t) => {
  const page = await open(t, { answers: { [DECISION.id]: { item: DECISION.id, n: 27, at: "2026-10-26T01:00:00Z", choice: "none", note: "Green" } } });
  if (!page) return;
  const c = card(page, DECISION);
  assert.match(await c.locator(".receipt").textContent(), /Green/);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "b");
  await send(page);
  await page.waitForFunction((id) => window.__answers()[id].choice === "b", DECISION.id);
  assert.equal((await answers(page))[DECISION.id].note, "");
});

// ---------------------------------------------------------------- the notice to Claude

const sent = (page) => page.evaluate(() => window.__sent);
const told = (page, text) => page.locator("#sentStatus", { hasText: text }).waitFor();

test("a send gives one notice that names the item and the choice", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  await addNote(page, DECISION, "bold");
  await send(page);
  await told(page, "Claude was told");
  const s = await sent(page);
  assert.equal(s.length, 1);
  assert.match(s[0].text, /27 a \(bold\)/);
  assert.match(s[0].text, /test thread/);
  assert.ok(s[0].anchor, "the first notice starts an anchored thread");
  assert.ok((await answers(page))[DECISION.id], "the answer did not land");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.thread")), "t-new-1");
});

test("a task send names the item as done", async (t) => {
  const page = await open(t); if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  assert.match((await sent(page))[0].text, /28 done/);
});

test("a second send replies into the stored thread", async (t) => {
  const page = await open(t, { storage: { "waiting.thread": "t-old" } }); if (!page) return;
  await card(page, TASK).getByRole("button", { name: "Mark done" }).click();
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  const s = await sent(page);
  assert.equal(s[0].threadId, "t-old");
  assert.equal(s[0].anchor, undefined);
});

test("Take my pick on two cards and one Send gives exactly one notice for the batch", async (t) => {
  const two = { ...DECISION, id: "pick-a-shape", n: 29, title: "Pick a shape" };
  const page = await open(t, { items: [DECISION, two, TASK] }); if (!page) return;
  await takePick(page, DECISION); await takePick(page, two);
  await send(page);
  await page.waitForFunction(() => window.__sent.length >= 1);
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 2);
  await page.evaluate(() => new Promise((r) => setTimeout(r, 300))); // a second send would land in this window
  const s = await sent(page);
  assert.equal(s.length, 1, "one notice per batch");
  assert.match(s[0].text, /27 a/);
  assert.match(s[0].text, /29 a/);
});

test("no_session sends nothing and the answer still lands", async (t) => {
  const page = await open(t, { comments: { can: "no_session" } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.equal((await sent(page)).length, 0);
  assert.ok((await answers(page))[DECISION.id]);
});

test("a send that rejects leaves the answer and says no session was told", async (t) => {
  const page = await open(t, { comments: { can: "available", failCode: "claude_unavailable" } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.equal((await sent(page)).length, 1, "no retry loop");
  assert.ok((await answers(page))[DECISION.id]);
});

test("a canSendToClaude that rejects counts as unavailable", async (t) => {
  const page = await open(t, { comments: { canThrows: true } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.ok((await answers(page))[DECISION.id]);
});

test("a page without the comments capability still sends", async (t) => {
  const page = await open(t, { comments: null }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "No session was told");
  assert.ok((await answers(page))[DECISION.id]);
});

test("a not_found on the stored thread starts a new anchored thread", async (t) => {
  const page = await open(t, { comments: { can: "available", goneThreads: ["t-old"] }, storage: { "waiting.thread": "t-old" } });
  if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "Claude was told");
  const s = await sent(page);
  assert.equal(s.length, 2);
  assert.equal(s[0].threadId, "t-old");
  assert.ok(s[1].anchor && s[1].anchor.tag === "H1", "the new thread anchors at the h1");
  assert.equal(await page.evaluate(() => localStorage.getItem("waiting.thread")), "t-new-2");
});

test("a long note with control characters is cut to 4 KiB, keeps Owners, and is plain", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  await addNote(page, DECISION, "x\u0001y\u0007z" + "é".repeat(6000));
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  const text = (await sent(page))[0].text;
  assert.ok(Buffer.byteLength(text, "utf8") <= 4096, "over 4 KiB");
  assert.match(text, /Owners: test thread/);
  assert.doesNotMatch(text, /[\u0000-\u0008\u000b-\u001f\u007f]/);
  assert.match(text, /x y z/);
});

test("canSendToClaude is asked before the answer write", async (t) => {
  const page = await open(t); if (!page) return;
  await choose(page, DECISION, "a");
  await page.evaluate(() => {
    window.__order = [];
    const real = state.comments.canSendToClaude;
    state.comments.canSendToClaude = async () => { window.__order.push("can"); return real(); };
    const col = state.db.collection;
    state.db.collection = (n) => { const x = col(n); const d = x.doc; x.doc = (id) => { const y = d(id); const set = y.set; y.set = async (b) => { window.__order.push("set"); return set(b); }; return y; }; return x; };
  });
  await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  assert.deepEqual(await page.evaluate(() => window.__order), ["can", "set"]);
});

test("a batch of many items with long owners is cut to 4 KiB and keeps Owners", async (t) => {
  const many = Array.from({ length: 70 }, (_, i) => ({ ...DECISION, id: i ? "pick-" + i : DECISION.id, n: 100 + i, owner: ("owner" + i + " ").padEnd(120, "o") }));
  const page = await open(t, { items: many }); if (!page) return;
  await page.evaluate(() => document.querySelectorAll("button.takepick").forEach((b) => b.click()));
  await send(page);
  await page.waitForFunction(() => window.__sent.length >= 1);
  const text = (await sent(page))[0].text;
  assert.ok(Buffer.byteLength(text, "utf8") <= 4096, "over 4 KiB");
  assert.match(text, /Owners: owner0 /);
  assert.ok(text.endsWith("…"), "the cut did not run");
});

test("an owner name is capped at 80 characters", async (t) => {
  const long = { ...DECISION, owner: "q".repeat(300) };
  const page = await open(t, { items: [long] }); if (!page) return;
  await takePick(page, long); await send(page);
  await page.waitForFunction(() => window.__sent.length === 1);
  const text = (await sent(page))[0].text;
  assert.ok(text.includes("q".repeat(80)) && !text.includes("q".repeat(81)));
});

test("pressing Send again while a batch is in flight does nothing", async (t) => {
  const page = await open(t, { comments: { can: "available", sendDelay: 600 } }); if (!page) return;
  await takePick(page, DECISION);
  await send(page);
  await page.evaluate(() => { for (let i = 0; i < 3; i++) document.getElementById("send").click(); });
  await page.evaluate(() => new Promise((r) => setTimeout(r, 1500)));
  assert.equal((await sent(page)).length, 1, "a second notice went out");
  assert.equal((await page.evaluate(() => window.__log)).filter((l) => l[0] === "set").length, 1, "the batch saved twice");
});

test("a canSendToClaude that never answers does not hold the send", async (t) => {
  const page = await open(t, { comments: { canHangs: true } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#sentStatus", { hasText: "No session was told" }).waitFor({ timeout: 8000 });
  assert.ok((await answers(page))[DECISION.id]);
  assert.equal((await sent(page)).length, 0);
});

test("Undo tells Claude the answers are withdrawn", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "Claude was told");
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => window.__sent.length === 2);
  assert.match((await sent(page))[1].text, /Undone on the waiting page\. Owners: test thread\. Items: 27 are open again\./);
});

// ---------------------------------------------------------------- fix round 1

const jump = (page, ms) => page.evaluate((m) => { const real = Date.now; Date.now = () => real() + m; }, ms);

test("the Undo window follows the clock, not the timer ticks", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor();
  await jump(page, 9000); // a throttled tab: the clock moved, the timer did not
  await page.locator("#undoBtn").waitFor({ state: "detached", timeout: 2500 });
  assert.ok((await answers(page))[DECISION.id], "the answer went");
});

test("Undo deletes before the canSend wait", async (t) => {
  const page = await open(t, { comments: { canHangs: true } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor({ timeout: 8000 });
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => Object.keys(window.__answers()).length === 0, null, { timeout: 1500 }); // not held behind the 3 s wait
});

test("Undo refuses a delete once 8 seconds from the send have passed", async (t) => {
  const page = await open(t); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.evaluate(() => { const real = Date.now, b = document.getElementById("undoBtn"); Date.now = () => real() + 9000; b.click(); });
  await page.evaluate(() => new Promise((r) => setTimeout(r, 400)));
  assert.equal((await page.evaluate(() => window.__log)).filter((l) => l[0] === "delete").length, 0, "a delete ran after the window");
  assert.ok((await answers(page))[DECISION.id]);
});

test("Undo deletes the receipt of each item it reopens", async (t) => {
  const page = await open(t, { receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } } }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").click();
  await page.waitForFunction((id) => window.__log.some((l) => l[0] === "delete" && l[1] === "receipts" && l[2] === id), DECISION.id);
});

test("the faint text reaches 4.5:1 on chips and the ground, for any brand", async (t) => {
  const faint = [...html.matchAll(/--faint: (#[0-9a-f]{6})/gi)].map((m) => m[1]);
  assert.equal(faint.length, 3);
  const page = await open(t); if (!page) return;
  const bad = await page.evaluate(`(() => {${CONTRAST}
    const f = ${JSON.stringify(faint)}, out = [];
    const hslHex = (h, s, l) => { s /= 100; l /= 100; const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l); const g = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1)); return "#" + [g(0), g(8), g(4)].map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join(""); };
    const brands = ${JSON.stringify(BRANDS)};
    for (let h = 0; h < 360; h += 15) for (const [s, l] of [[100, 50], [100, 25], [60, 70], [100, 90], [80, 40]]) brands.push(hslHex(h, s, l));
    const chk = (w, a, b) => { const r = R(a, b); if (r < 4.5) out.push(w + " " + r.toFixed(2)); };
    chk("light chip", f[0], "#eef1f4"); chk("dark chip", f[1], "#222a35");
    for (const b of brands) { const t = derive(b); chk(b + " light ground", f[0], t.groundL); chk(b + " dark ground", f[1], t.groundD); chk(b + " light card", f[0], "#ffffff"); chk(b + " dark card", f[1], "#191e26"); }
    return out;
  })()`);
  assert.deepEqual(bad, []);
});

test("a sent chip carries a mark, a ring while filing is pending and a check once filed, so it differs from ready by more than colour", async (t) => {
  const mark = (page) => page.evaluate((id) => getComputedStyle(document.getElementById("c-" + id), "::before").content, DECISION.id);
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  assert.match(await mark(page), /○/);
  await page.close();
  const page2 = await open(t, { answers: SAVED_A, receipts: { [DECISION.id]: { filed: "2026-10-26T03:00:00Z" } } }); if (!page2) return;
  assert.match(await mark(page2), /✓/);
});

test("an invalid added or by date shows no NaN and no Invalid", async (t) => {
  const page = await open(t, { items: [mk("badtime", 1, { added: "garbage", by: "nope" })] }); if (!page) return;
  const text = await page.locator("body").innerText();
  assert.doesNotMatch(text, /NaN|Invalid|undefined/);
  assert.equal(await page.locator("#tier-calm #item-badtime").count(), 1, "an invalid deadline made it Upcoming");
});

test("the template declares utf-8", () => {
  assert.match(html.slice(0, 200), /<meta charset="utf-8">/i);
});

// ---------------------------------------------------------------- fix round 2

test("a failed receipt delete does not stop Undo, the page state or the notice", async (t) => {
  const page = await open(t, { receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } }, failDeleteIn: "receipts" }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await told(page, "Claude was told");
  await page.locator("#undoBtn").click();
  await page.waitForFunction(() => window.__sent.length === 2);
  assert.equal(await page.evaluate((id) => id in state.answers, DECISION.id), false, "the page still shows the item as sent");
  assert.equal(await card(page, DECISION).locator(".receipt").count(), 0);
});

test("a partial Undo names every item that stayed sent", async (t) => {
  const items = [mk("d-one", 1), mk("d-two", 2), mk("d-three", 3)];
  const page = await open(t, { items }); if (!page) return;
  for (const it of items) await takePick(page, it);
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await page.evaluate(() => {
    const col = state.db.collection;
    state.db.collection = (n) => { const x = col(n); const d = x.doc; x.doc = (id) => { const y = d(id); const del = y.delete; y.delete = async () => { await del(); const real = Date.now; Date.now = () => real() + 9000; }; return y; }; return x; };
    document.getElementById("undoBtn").click();
  });
  await page.locator("#barStatus", { hasText: "Too late to undo No. 1 and No. 2" }).waitFor();
});

// ---------------------------------------------------------------- option names, counts and the list

const WORDY = [["value", "Value for the card, shown near the feed in a sheet"], ["watch", "Watch"], ["nothing", "Nothing"]]
  .map(([key, label]) => ({ key, label, how: "h", gain: "g", lose: "l" }));

test("an option chip shows its letter by position, never a raw key longer than one character", async (t) => {
  const it = mk("long-keys", 40, { options: WORDY, pick: "watch", why: "Watch fits." });
  const page = await open(t, { items: [it] }); if (!page) return;
  const chips = await card(page, it).locator(".opt .key").allTextContents();
  assert.deepEqual(chips, ["A", "B", "C"]);
});

test("a pick is named by the option's title, shortened with an ellipsis, never by its raw key", async (t) => {
  const it = mk("pick-names", 41, { options: WORDY, pick: "value", why: "Value fits." });
  const page = await open(t, { items: [it] }); if (!page) return;
  const take = card(page, it).getByRole("button", { name: /Take my pick/ });
  const name = await take.textContent();
  assert.doesNotMatch(name, /VALUE|value\)/, "the button shows the raw key: " + name);
  assert.match(name, /^Take my pick \(Value for the card.*…\)$/, name);
  await take.click();
  const ready = await card(page, it).locator(".ready").textContent();
  assert.match(ready, /^Ready to send: Value for the card.*…, my pick\.$/, ready);
  await choose(page, it, "watch");
  assert.equal(await card(page, it).locator(".ready").textContent(), "Ready to send: Watch, your choice.");
});

test("the count digit matches the rest of its line", async (t) => {
  const page = await open(t); if (!page) return;
  const m = await page.evaluate(() => { const b = document.querySelector(".ov-prog .big b"), l = document.querySelector(".ov-prog .big"); return { b: getComputedStyle(b).fontSize, l: getComputedStyle(l).fontSize, v: getComputedStyle(b).fontVariantNumeric }; });
  assert.equal(m.b, m.l, "the digit is a different size from its line");
  assert.doesNotMatch(m.v, /slashed-zero/);
});

for (const width of [1440, 390]) {
  test(`each list entry carries its item's title, at ${width} wide`, async (t) => {
    const items = [mk("first-q", 1, { title: "Where does the price history show" }), { ...TASK, id: "second-q", n: 2, title: "Plug in the Mac" }];
    const page = await open(t, { items, viewport: { width, height: 900 } }); if (!page) return;
    for (const it of items) {
      const chip = page.locator(`#c-${it.id}`);
      assert.equal(await chip.getAttribute("title"), it.title);
      assert.ok((await chip.getAttribute("aria-label")).includes(it.title));
    }
    const shown = await page.locator("#c-first-q .nt").evaluate((e) => getComputedStyle(e).display !== "none" && e.getBoundingClientRect().width > 0).catch(() => false);
    assert.equal(shown, width > 960, width > 960 ? "no visible short title in the list" : "the short title crowds a narrow list");
  });
}

// ---------------------------------------------------------------- withdraw, undo and notes on a stood pick

test("a withdraw opens the 8-second Undo panel, and Undo puts the answer back", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await send(page);
  await page.locator("#sent .stamp").waitFor();
  assert.match(await page.locator("#sent").textContent(), /withdrawn/i);
  assert.equal(await page.locator("#undoBtn").count(), 1, "no Undo after a withdraw");
  await page.click("#undoBtn");
  await page.waitForFunction((id) => !!window.__answers()[id], DECISION.id);
  assert.deepEqual((await answers(page))[DECISION.id], SAVED_A[DECISION.id]);
  assert.equal(await page.evaluate(() => window.__sent.length), 0, "a withdraw or its undo told a session");
});

test("a withdraw leaves an answer that changed since the page read it", async (t) => {
  const page = await open(t, { answers: SAVED_A }); if (!page) return;
  const c = card(page, DECISION);
  await c.getByRole("button", { name: "Change" }).click();
  await choose(page, DECISION, "a");
  await page.evaluate((id) => { window.__answers()[id] = { item: id, n: 27, at: "2026-10-26T05:00:00Z", choice: "b", note: "" }; }, DECISION.id);
  await send(page);
  await c.getByText("changed", { exact: false }).waitFor();
  assert.equal((await answers(page))[DECISION.id].choice, "b", "the newer answer was deleted");
  assert.deepEqual((await page.evaluate(() => window.__log)).filter((l) => l[0] === "delete"), []);
});

test("a note typed on an item whose pick stands sends the stood pick plus the note", async (t) => {
  const it = mk("stand-note", 7, { stands: true });
  const page = await open(t, { items: [it] }); if (!page) return;
  await addNote(page, it, "with a thought");
  await send(page);
  await page.waitForFunction((id) => !!window.__answers()[id], it.id);
  const a = (await answers(page))[it.id];
  assert.equal(a.choice, "a");
  assert.equal(a.note, "with a thought");
});

// ---------------------------------------------------------------- rank inside a tier

const order = (page) => page.evaluate(() => [...document.querySelectorAll("section.tier")].map((sec) => [sec.id, [...sec.querySelectorAll("article.card")].map((c) => c.id.slice(5))]));
const at = (day) => `2026-10-${String(day).padStart(2, "0")}T00:00:00Z`;

test("inside a tier, rank overrides age, and an item with no rank sorts after the ranked ones by age", async (t) => {
  const items = [
    mk("old-rank2", 1, { added: at(1), rank: 2 }), mk("new-rank1", 2, { added: at(5), rank: 1 }),
    mk("old-none", 3, { added: at(2) }), mk("new-none", 4, { added: at(6) }),
  ];
  const page = await open(t, { items }); if (!page) return;
  assert.deepEqual((await order(page)).find((x) => x[0] === "tier-calm")[1], ["new-rank1", "old-rank2", "old-none", "new-none"]);
});

test("a group stays together at its best member's rank", async (t) => {
  const items = [
    mk("solo-0", 1, { added: at(3), rank: 0 }), mk("grp-a", 2, { added: at(1), rank: 5, group: "g" }),
    mk("grp-b", 3, { added: at(2), rank: 1, group: "g" }), mk("solo-3", 4, { added: at(1), rank: 3 }),
  ];
  const page = await open(t, { items }); if (!page) return;
  const calm = (await order(page)).find((x) => x[0] === "tier-calm")[1];
  assert.equal(calm[0], "solo-0");
  assert.deepEqual(calm.slice(1, 3).sort(), ["grp-a", "grp-b"], "the group is split: " + calm);
  assert.equal(calm[3], "solo-3");
});

test("rank never moves an item across tiers", async (t) => {
  const items = [mk("calm-rank0", 1, { rank: 0 }), mk("hold-rank9", 2, { holds: "A lane waits.", rank: 9 }), mk("stand-rank0", 3, { stands: true, rank: 0 })];
  const page = await open(t, { items }); if (!page) return;
  const tiers = await order(page);
  assert.deepEqual(tiers.map((x) => x[0]), ["tier-holds", "tier-calm", "tier-stands"]);
  assert.deepEqual(tiers.map((x) => x[1]), [["hold-rank9"], ["calm-rank0"], ["stand-rank0"]]);
});

test("SKILL.md names the page's one writer and the rank field", async () => {
  const skill = fs.readFileSync(path.join(HERE, "..", "SKILL.md"), "utf8");
  assert.match(skill, /`writer`/);
  assert.match(skill, /`rank`/);
  assert.match(skill, /re-rank/i);
  const rule = fs.readFileSync(path.join(HERE, "..", "..", "..", "docs", "decisions", "questions-go-to-owner.md"), "utf8");
  assert.match(rule, /one writer/i);
  assert.match(rule, /`rank`/);
});

// Decision questions-go-to-owner, "Answer on the page, not in a comment thread":
// a rebuilt page drops its threads, so a session rewrites the item instead.
test("SKILL.md answers a comment by rewriting the item, never in a comment thread", async () => {
  const skill = fs.readFileSync(path.join(HERE, "..", "SKILL.md"), "utf8");
  assert.doesNotMatch(skill, /action `reply`/);
  assert.doesNotMatch(skill, /reply in the comment thread/i);
  assert.match(skill, /never reply in a comment thread/i);
  assert.match(skill, /rewrite that item/i);
});

// ---------------------------------------------------------------- round 2 looks

const PANEL = '<body style="margin:0"><div style="height:700px"></div><div id="panel" style="width:300px;height:45px;background:#a62"></div><div style="height:500px"></div></body>';
const FULLW = '<body style="margin:0;background:#2a6"><div style="width:390px;height:300px;background:#26a">x</div></body>';

for (const width of [390, 1440]) {
  test(`the View control sits under the picture and never covers it, at ${width} wide`, async (t) => {
    const it = mk("pill-q", 52, { pick: "a", options: [{ key: "a", label: "A", how: "h", gain: "g", lose: "l", design: "p-a" }], designs: [{ slug: "p-a", label: "A", focus: "#panel" }] });
    const page = await open(t, { items: [it], designData: { "p-a": PANEL }, viewport: { width, height: 900 } }); if (!page) return;
    await page.waitForFunction((id) => document.querySelector(`#item-${id} .dfitwrap`).getBoundingClientRect().height > 0, it.id);
    const m = await card(page, it).locator(".opic").evaluate((o) => { const w = o.querySelector(".dfitwrap").getBoundingClientRect(), v = o.querySelector(".view").getBoundingClientRect(); return { wrapBottom: w.bottom, wrapTop: w.top, viewTop: v.top, viewH: v.height }; });
    assert.ok(m.viewTop >= m.wrapBottom - 1, "the View control covers the picture");
    assert.ok(m.viewH >= 40, "the View control is under 40px high: " + m.viewH);
  });

  test(`the viewer head is one row, and the mockup is whole and centered, at ${width} wide`, async (t) => {
    const it = viewerItem();
    const page = await open(t, { items: [it], designData: { ...VIEWER_DATA, "v-a": FULLW }, viewport: { width, height: 900 } }); if (!page) return;
    // Stand-in for CI's wider fallback font: the one-row head is then wider than a phone.
    await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
    await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
    await page.waitForFunction(() => { const f = document.querySelector("#dStage .dframe:not(.off)"); return f && f.getBoundingClientRect().height > 60; });
    const m = await page.evaluate(() => { const f = document.querySelector("#dStage iframe").getBoundingClientRect(), h = document.querySelector(".dsh-head").getBoundingClientRect(); return { left: f.left, right: f.right, headH: h.height, close: document.querySelector("#dClose").getBoundingClientRect().right, sheetW: document.querySelector("#dsheet").scrollWidth, vw: innerWidth }; });
    assert.ok(m.headH < 70, "the viewer head is " + m.headH + "px high");
    assert.ok(m.close <= m.vw + 0.5, "Close is cut off: its right edge is " + m.close);
    assert.ok(m.sheetW <= m.vw, "the viewer scrolls sideways: " + m.sheetW + " in " + m.vw);
    assert.ok(m.right <= m.vw + 0.5 && m.left >= -0.5, "the mockup is cut: " + m.left + " to " + m.right);
    if (width > 900) assert.ok(Math.abs((m.left + m.right) / 2 - m.vw / 2) < 3, "the mockup is not centered");
    for (const id of ["dPrev", "dNext", "dFull", "dClose"]) assert.ok((await page.locator("#" + id).boundingBox()).height >= 40, id + " is under 40px");
  });
}

const WIDE_DESIGN = '<body style="margin:0;display:flex;width:1200px"><div style="width:400px;height:200px;background:#a62">1</div><div style="width:400px;height:200px;background:#26a">2</div><div id="last" style="width:400px;height:200px;background:#2a6">3</div></body>';
for (const width of [390, 1440]) {
  test(`a design drawn 1200 wide is whole in the viewer, at ${width} wide`, async (t) => {
    const it = mk("wide-q", 55, { pick: "a", options: [{ key: "a", label: "Wide", how: "h", gain: "g", lose: "l", design: "w-a" }], designs: [{ slug: "w-a", label: "Wide", drawn: 1200 }] });
    const page = await open(t, { items: [it], designData: { "w-a": WIDE_DESIGN }, viewport: { width, height: 900 } }); if (!page) return;
    await card(page, it).locator(".opic").click();
    await page.waitForFunction(() => { const f = document.querySelector("#dStage .dfitwrap:not(.off) iframe"); return f && FIT["w-a|"]; });
    const m = await page.evaluate(() => {
      const f = document.querySelector("#dStage .dfitwrap:not(.off) iframe"), r = f.getBoundingClientRect();
      return { right: r.right, left: r.left, vw: innerWidth, w: f.style.width };
    });
    const tile = await page.frameLocator("#dStage .dfitwrap:not(.off) iframe").locator("#last").boundingBox();
    const f = await page.locator("#dStage .dfitwrap:not(.off)").boundingBox();
    const sc = (await page.locator("#dStage .dfitwrap:not(.off) iframe").evaluate((e) => new DOMMatrix(getComputedStyle(e).transform).a));
    assert.equal(m.w, "1200px", "the frame is not drawn at the design's width");
    assert.ok(Math.abs(tile.x + tile.width - (f.x + f.width)) <= 2 && tile.x + tile.width <= m.vw + 0.5, `the right-most tile is cut: ends at ${tile.x + tile.width}, viewer ends at ${f.x + f.width}`);
    assert.ok(sc < 1, "the design is not scaled down");
  });
}

test("a viewer whose head cuts the title names the design in a one-line caption above it", async (t) => {
  const it = viewerItem();
  const page = await open(t, { items: [it], designData: { ...VIEWER_DATA, "v-a": FULLW }, viewport: { width: 390, height: 900 } }); if (!page) return;
  // Stand-in for CI's wider fallback font, so the head cuts "Layout A (Phone)" at 390.
  await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
  await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
  const cap = page.locator("#dCap");
  assert.equal(await cap.isVisible(), true, "no caption in the viewer");
  assert.equal(await cap.textContent(), await page.evaluate(() => dList[dAt].label));
  const m = await page.evaluate(() => { const c = document.querySelector("#dCap").getBoundingClientRect(), f = document.querySelector("#dStage .dfitwrap:not(.off)").getBoundingClientRect(); return { capBottom: c.bottom, frameTop: f.top, capH: c.height, vw: innerWidth, right: f.right }; });
  assert.ok(m.capBottom <= m.frameTop + 0.5, "the caption sits over the mockup");
  assert.ok(m.capH < 30, "the caption is more than one line: " + m.capH);
  assert.ok(m.right <= m.vw + 0.5, "the mockup is cut");
  await page.setViewportSize({ width: 1440, height: 900 });
  // The resize observer hides the caption a frame after the resize.
  await page.waitForFunction(() => { const c = document.querySelector("#dCap"); return getComputedStyle(c).display === "none"; }, null, { timeout: 2000 }).catch(() => {});
  assert.equal(await cap.isVisible(), false, "the caption shows on a wide screen, where the title fits");
});

// The caption names the design whenever the head cuts the title, and only then (design review round 2).
const TALL_DESIGN = `<body style="margin:0">${Array.from({ length: 25 }, (_, i) => `<div style="height:80px;background:hsl(${i * 14},60%,55%)">${i + 1}</div>`).join("")}</body>`;
const capItem = (labels) => mk("cap-q", 56, { pick: "a", options: labels.map((l, i) => ({ key: "abc"[i], label: l, how: "h", gain: "g", lose: "l", design: "c-" + "abc"[i] })),
  designs: labels.map((l, i) => ({ slug: "c-" + "abc"[i], label: l, width: "Phone" })) });
const capState = (page) => page.evaluate(() => { const c = document.querySelector("#dCap"), t = document.querySelector("#dTitle"), r = c.getBoundingClientRect();
  return { shown: getComputedStyle(c).display !== "none" && r.height > 0, h: r.height, text: c.textContent, cut: c.scrollWidth > c.clientWidth, label: dList[dAt].label, titleCut: t.scrollWidth > t.clientWidth }; });
async function openCap(t, labels, width, design) {
  const it = capItem(labels);
  const page = await open(t, { items: [it], designData: { "c-a": design, "c-b": "<p>b</p>" }, viewport: { width, height: 900 } }); if (!page) return null;
  // Stand-in for CI's wider fallback font.
  await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
  await card(page, it).locator(`label.opt[for="o-${it.id}-a"] .opic`).click();
  await page.waitForFunction(() => FIT["c-a|"] && document.querySelector("#dStage .dfitwrap:not(.off)").getBoundingClientRect().height > 60);
  return page;
}

test("a tall design with a long label is named in a caption with height, at 390 wide", async (t) => {
  const page = await openCap(t, ["Tall A layout with bands", "B"], 390, TALL_DESIGN); if (!page) return;
  const c = await capState(page);
  assert.ok(c.titleCut, "the stand-in label fits the head; the test needs a longer one");
  assert.ok(c.shown && c.h >= 14, "the caption is " + c.h + "px high, so nothing names the design");
  assert.equal(c.text, c.label); assert.ok(!c.cut, "the caption cuts the label");
});

test("at 768 wide a title the head cuts shows in the caption, and Prev to a short title hides it", async (t) => {
  const page = await openCap(t, ["Layout A in a sheet under the feed card", "B"], 768, "<p>a</p>"); if (!page) return;
  let c = await capState(page);
  assert.ok(c.titleCut, "the stand-in label fits the head; the test needs a longer one");
  assert.ok(c.shown, "the head cuts the title and no caption names the design");
  assert.equal(c.text, c.label); assert.ok(!c.cut, "the caption cuts the label");
  await page.click("#dPrev");
  c = await capState(page);
  assert.ok(!c.titleCut, "the short title is cut");
  assert.ok(!c.shown, "the caption repeats a title that fits");
});

test("a title that fits the head gets no caption, at 390 wide", async (t) => {
  const page = await openCap(t, ["A", "B"], 390, "<p>a</p>"); if (!page) return;
  const c = await capState(page);
  assert.ok(!c.titleCut, "the short title is cut");
  assert.ok(!c.shown, "the caption repeats a title that fits");
});

test("a picture's height is reserved from its declared size before it loads", async (t) => {
  const it = mk("reserve-q", 53, { pick: "a", options: [{ key: "a", label: "A", how: "h", gain: "g", lose: "l", design: "r-a" }], designs: [{ slug: "r-a", label: "A", focus: "#panel", size: { w: 600, h: 400 } }] });
  const mockup = '<body style="margin:0;width:700px"><div style="height:700px"></div><div id="panel" style="width:600px;height:400px;background:#a62"></div></body>';
  const page = await open(t, { items: [it], designData: { "r-a": mockup }, viewport: { width: 1440, height: 900 } }); if (!page) return;
  await page.waitForFunction((id) => document.querySelector(`#item-${id} iframe`).style.transform.includes("translate"), it.id);
  const first = await page.evaluate(() => window.__firstFit);
  const last = await page.evaluate((id) => document.querySelector(`#item-${id} .dfitwrap`).getBoundingClientRect().height, it.id);
  assert.ok(first && Math.abs(first - last) <= 3, `first paint ${first}, loaded ${last}`);
});

test("two designs of one slug with different focus keep their own size, and the viewer opens on the tapped option", async (t) => {
  const two = '<body style="margin:0"><div id="p1" style="width:300px;height:200px;background:#a62"></div><div id="p2" style="width:300px;height:100px;background:#26a"></div></body>';
  const it = mk("shared-q", 54, { pick: "a", options: [{ key: "a", label: "Layout A", how: "h", gain: "g", lose: "l" }, { key: "b", label: "Layout B", how: "h", gain: "g", lose: "l" }],
    designs: [{ slug: "shared", option: "a", label: "A", focus: "#p1" }, { slug: "shared", option: "b", label: "B", focus: "#p2" }] });
  const page = await open(t, { items: [it], designData: { shared: two }, viewport: { width: 1440, height: 900 } }); if (!page) return;
  await page.waitForFunction((id) => [...document.querySelectorAll(`#item-${id} .dfitwrap`)].every((w) => w.querySelector("iframe").style.transform.includes("translate")), it.id);
  const hs = await card(page, it).locator(".dfitwrap").evaluateAll((ws) => ws.map((w) => w.getBoundingClientRect().height));
  assert.ok(hs[0] > hs[1] * 1.6, "the second picture took the first one's size: " + hs);
  await card(page, it).locator(`label.opt[for="o-${it.id}-b"] .opic`).click();
  assert.match(await page.locator("#dTitle").textContent(), /^Layout B/);
});

// ---------------------------------------------------------------- each option's picture shows its own difference
const ALERT = (page, it) => card(page, it).locator("p.broken[role=alert]");
const lateRow = (state) => `<body style="margin:0"><div id="late-row">${state}</div><div id="other">x</div></body>`;
const looks = (id, n, designs, over = {}) => mk(id, n, { look: true, pick: "a", options: WIDE.map(([k, l]) => ({ key: k, label: l, how: "h", gain: "g", lose: "l", design: "o-" + k })), designs, ...over });

test("a look question whose options A and B name one design shows an alert and Send is refused", async (t) => {
  const it = mk("same-pic", 60, { look: true, pick: "a",
    options: [{ key: "a", label: "Claim filed and Lost", how: "h", gain: "g", lose: "l", design: "late" }, { key: "b", label: "Six stamps", how: "h", gain: "g", lose: "l", design: "late" }],
    designs: [{ slug: "late", label: "Late" }] });
  const page = await open(t, { items: [it], designData: { late: lateRow("alert") } }); if (!page) return;
  assert.equal(await ALERT(page, it).count(), 1, "no alert on two options with one picture");
  assert.match(await ALERT(page, it).textContent(), /A and B.*share one picture.*neither shows its own difference.*fix item 60/s);
  await page.evaluate(() => { setDraft(byId("same-pic"), { choice: "a", auto: true }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open on an item whose options share a picture");
});

test("two options whose designs have different slugs but the same bytes are refused too", async (t) => {
  const it = looks("same-bytes", 61, [{ slug: "o-a", label: "A" }, { slug: "o-b", label: "B" }]);
  const page = await open(t, { items: [it], designData: { "o-a": lateRow("same"), "o-b": lateRow("same") } }); if (!page) return;
  assert.match(await ALERT(page, it).textContent(), /A and B.*share one picture/s);
});

test("a focus that matches nothing in its mockup, or is no selector, is refused and names the option", async (t) => {
  for (const [id, n, focus] of [["focus-miss", 62, "#no-such"], ["focus-bad", 63, "##("]]) {
    const it = looks(id, n, [{ slug: "o-a", label: "A" }, { slug: "o-b", label: "B", focus }]);
    const page = await open(t, { items: [it], designData: { "o-a": lateRow("one"), "o-b": lateRow("two") } }); if (!page) return;
    assert.equal(await ALERT(page, it).count(), 1, id + " shows no alert");
    assert.match(await ALERT(page, it).textContent(), /option B.*shows nothing the focus names.*fix item/s);
    assert.doesNotMatch(await ALERT(page, it).textContent(), /option A/);
  }
});

test("distinct pictures with a focus that matches show no alert; extra widths and one slug with two focuses stay free", async (t) => {
  const it = looks("own-pics", 64, [{ slug: "o-a", label: "A", focus: "#late-row" }, { slug: "o-b", label: "B", focus: "#late-row" }, { slug: "o-a", option: "a", label: "A wide", width: "Wide" }]);
  const page = await open(t, { items: [it], designData: { "o-a": lateRow("one"), "o-b": lateRow("two") } }); if (!page) return;
  assert.equal(await ALERT(page, it).count(), 0, "an alert on distinct pictures");
  await page.evaluate(() => { setDraft(byId("own-pics"), { choice: "a", auto: true }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), false);
});

// ---------------------------------------------------------------- the database key is the item's key

const { id: _noId, ...DECISION_NO_ID } = DECISION;
const warn = (page, key) => card(page, { id: key }).locator(".status.broken");

test("an item stored with no id field is answered under its database key", async (t) => {
  const page = await open(t, { items: [], rawItems: { k29: { ...DECISION_NO_ID, n: 29 } } }); if (!page) return;
  await choose(page, { id: "k29" }, "b");
  await send(page);
  await written(page);
  const log = await page.evaluate(() => window.__log.filter((l) => l[0] === "set"));
  assert.equal(log.length, 1);
  assert.equal(log[0][2], "k29", "the answer key");
  assert.equal(log[0][3].item, "k29");
  assert.equal(log[0][3].choice, "b");
  assert.match(await warn(page, "k29").textContent(), /no id field.*fix item 29/s);
});

test("an item whose id field differs from its key warns and is answered under the key", async (t) => {
  const page = await open(t, { items: [], rawItems: { k30: { ...DECISION, id: "other-id", n: 30 } } }); if (!page) return;
  assert.match(await warn(page, "k30").textContent(), /id field that differs.*fix item 30/s);
  await choose(page, { id: "k30" }, "a");
  await send(page);
  await written(page);
  const log = await page.evaluate(() => window.__log.filter((l) => l[0] === "set"));
  assert.deepEqual([log.length, log[0][2], log[0][3].item], [1, "k30", "k30"]);
});

test("a decision with a duplicate option key, no options, or a none key warns and Send skips it", async (t) => {
  const opt = (key) => ({ key, label: "L" + key, how: "h", gain: "g", lose: "l" });
  const rawItems = {
    "dup-keys": { ...DECISION, id: "dup-keys", n: 31, options: [opt("a"), opt("a")], pick: "a" },
    "no-opts": { ...DECISION, id: "no-opts", n: 32, options: [], pick: "a" },
    "none-key": { ...DECISION, id: "none-key", n: 33, options: [opt("none"), opt("b")], pick: "b" },
    "good": { ...DECISION, id: "good", n: 34 },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  for (const k of ["dup-keys", "no-opts", "none-key"]) {
    assert.equal(await warn(page, k).count(), 1, k + " shows no warning");
    assert.match(await warn(page, k).textContent(), /cannot be answered.*fix item/s);
  }
  assert.equal(await warn(page, "good").count(), 0, "a sound item warns");
  // A staged draft on a broken item must still not go out; Send carries only the sound one.
  await page.evaluate(() => { for (const k of ["dup-keys", "none-key"]) setDraft(byId(k), { choice: "a", auto: true }); render(); });
  await takePick(page, { id: "good" });
  assert.equal(await page.locator("#send").textContent(), "Send 1 answer");
  await send(page);
  await written(page);
  const log = await page.evaluate(() => window.__log.filter((l) => l[0] === "set").map((l) => l[2]));
  assert.deepEqual(log, ["good"]);
});

test("a bad number or kind warns and Send skips it", async (t) => {
  const rawItems = {
    "bad-n": { ...DECISION, id: "bad-n", n: "7" },
    "bad-kind": { ...TASK, id: "bad-kind", n: 8, kind: "chore" },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.match(await warn(page, "bad-n").textContent(), /no number/);
  assert.match(await warn(page, "bad-kind").textContent(), /neither a decision nor a task/);
  await page.evaluate(() => { setDraft(byId("bad-kind"), { done: true }); setDraft(byId("bad-n"), { choice: "a" }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true);
});

test("a blocked card says it cannot be sent, disables its controls, and Copy answers skips it", async (t) => {
  const opt = (key) => ({ key, label: "L" + key, how: "h", gain: "g", lose: "l" });
  const rawItems = {
    "dup-keys": { ...DECISION, id: "dup-keys", n: 41, options: [opt("a"), opt("a")], pick: "a" },
    "odd-opts": { ...DECISION, id: "odd-opts", n: 42, options: "a, b" },
    "good": { ...DECISION, id: "good", n: 43 },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.match(await warn(page, "odd-opts").textContent(), /not a list/);
  await page.evaluate(() => { setDraft(byId("dup-keys"), { choice: "a", auto: true }); render(); });
  const c = card(page, { id: "dup-keys" });
  assert.equal(await c.locator(".ready").textContent(), "This item cannot be sent.");
  assert.equal(await c.locator(".takepick").isDisabled(), true);
  assert.equal(await c.locator(".nonebtn").isDisabled(), true);
  assert.equal(await c.locator(".opts input").first().isDisabled(), true);
  await takePick(page, { id: "good" });
  assert.equal(await page.evaluate(() => answerLine()), "43 a");
});

test("an item with no id field and a duplicate option key is blocked from Send and Copy, and names the key", async (t) => {
  const opt = (key) => ({ key, label: "L" + key, how: "h", gain: "g", lose: "l" });
  const rawItems = {
    "k50": { ...DECISION_NO_ID, n: 50, options: [opt("x"), opt("x")], pick: "x" },
    "good": { ...DECISION, id: "good", n: 51 },
  };
  const page = await open(t, { items: [], rawItems }); if (!page) return;
  assert.match(await warn(page, "k50").textContent(), /share the key x/);
  await page.evaluate(() => { setDraft(byId("k50"), { choice: "x" }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is open for a blocked item");
  assert.equal(await page.evaluate(() => answerLine()), "");
});

for (const width of [390, 1440]) {
  test(`the viewer is fitted the moment it opens, not after a later resize callback, at ${width} wide`, async (t) => {
    const it = viewerItem();
    const page = await open(t, { items: [it], designData: { ...VIEWER_DATA, "v-a": FULLW }, viewport: { width, height: 900 } }); if (!page) return;
    // Stand-in for CI's wider fallback font: the one-row head is then wider than a phone.
    await page.addStyleTag({ content: ".dsh-head { letter-spacing: 1.2px }" });
    const m = await page.evaluate((id) => {
      document.querySelector(`#item-${id} label.opt .opic`).click();
      const f = document.querySelector("#dStage iframe").getBoundingClientRect();
      return { left: f.left, right: f.right, close: document.querySelector("#dClose").getBoundingClientRect().right, sheetW: document.querySelector("#dsheet").scrollWidth, vw: innerWidth };
    }, it.id);
    assert.ok(m.close <= m.vw + 0.5, "Close is cut off on open: its right edge is " + m.close);
    assert.ok(m.sheetW <= m.vw, "the viewer scrolls sideways on open: " + m.sheetW + " in " + m.vw);
    assert.ok(m.right <= m.vw + 0.5 && m.left >= -0.5, `cut on open: ${m.left} to ${m.right}`);
    if (width > 900) assert.ok(Math.abs((m.left + m.right) / 2 - m.vw / 2) < 3, "not centered on open");
  });
}

// ---------------------------------------------------------------- c100 review defects

// Each helper wraps db.doc().delete so the test controls what a delete does inside Undo.
const hookDelete = (fn) => (page) => page.evaluate(`(() => {
  const col = state.db.collection;
  state.db.collection = (n) => { const x = col(n); const d = x.doc; x.doc = (id) => { const y = d(id); const del = y.delete; y.delete = (${fn})(n, del); return y; }; return x; };
  document.getElementById("undoBtn").click();
})()`);

test("a partial Undo lists late items with commas and one final and", async (t) => {
  const items = [mk("d-one", 1), mk("d-two", 2), mk("d-three", 3), mk("d-four", 4)];
  const page = await open(t, { items }); if (!page) return;
  for (const it of items) await takePick(page, it);
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await hookDelete(`(n, del) => async () => { await del(); const real = Date.now; Date.now = () => real() + 9000; }`)(page);
  await page.locator("#barStatus", { hasText: "Too late to undo" }).waitFor();
  const text = await page.locator("#barStatus").innerText();
  assert.match(text, /Too late to undo No\. 1, No\. 2,? and No\. 3\./, text);
});

test("a failed Undo names every item it could not undo", async (t) => {
  const items = [mk("d-one", 1), mk("d-two", 2), mk("d-three", 3)];
  const page = await open(t, { items }); if (!page) return;
  for (const it of items) await takePick(page, it);
  await send(page);
  await page.locator("#undoBtn").waitFor();
  await hookDelete(`(n, del) => async () => { if (n === "answers") throw { code: "denied" }; return del(); }`)(page);
  await page.locator("#barStatus", { hasText: "Undo failed" }).waitFor();
  const text = await page.locator("#barStatus").innerText();
  for (const n of [1, 2, 3]) assert.match(text, new RegExp("No\\. " + n + "\\b"), "the bar does not name No. " + n + ": " + text);
});

test("a failed receipt delete leaves no old receipt in the page state", async (t) => {
  const page = await open(t, { receipts: { [DECISION.id]: { read: "2026-10-26T02:00:00Z" } }, failDeleteIn: "receipts" }); if (!page) return;
  await takePick(page, DECISION); await send(page);
  await page.locator("#undoBtn").click();
  await page.waitForFunction((id) => !(id in state.answers), DECISION.id);
  assert.equal(await page.evaluate((id) => id in state.receipts, DECISION.id), false, "the old receipt is still in the page state");
});

// ---------------------------------------------------------------- c122: what differs, open this state, short titles

const diffItem = (over = {}) => mk("diff-q", 70, { pick: "a", options: [
  { key: "a", label: "Alpha", how: "same how", gain: "gain A", lose: "same lose", differs: ["gain"] },
  { key: "b", label: "Beta", how: "same how", gain: "gain B", lose: "same lose" },
], ...over });
const SETS = "Sets this option apart: ";

test("a named field gets a bar class, a not-equal sign and screen-reader words; an option with no differs shows none", async (t) => {
  const it = diffItem();
  const page = await open(t, { items: [it] }); if (!page) return;
  const a = card(page, it).locator('label.opt[for="o-diff-q-a"]'), b = card(page, it).locator('label.opt[for="o-diff-q-b"]');
  const g = a.locator(".gain");
  assert.equal(await g.evaluate((e) => e.classList.contains("dif")), true, "gain is not marked");
  assert.equal(await g.locator(".ne").textContent(), "≠");
  assert.equal(await g.locator(".ne").getAttribute("aria-hidden"), "true");
  assert.equal(await g.locator(".sr").textContent(), SETS);
  assert.equal(await a.locator(".how.dif, .lose.dif").count(), 0, "an unnamed field is marked");
  assert.equal(await b.locator(".dif, .ne").count(), 0, "an option with no differs is marked");
  assert.equal(await card(page, it).locator(".difkey").count(), 1, "the legend is not shown once");
  assert.match(await card(page, it).locator(".difkey").innerText(), /≠\s*marks what sets an option apart\./);
});

test("the page drops a named text field whose text equals every other option's, and ignores an unknown name", async (t) => {
  const it = diffItem({ options: [
    { key: "a", label: "Alpha", how: "same how", gain: "gain A", lose: "same lose", differs: ["how", "gain", "colour"] },
    { key: "b", label: "Beta", how: "same how", gain: "gain B", lose: "same lose" },
    { key: "c", label: "Gamma", how: "same how", gain: "gain C", lose: "same lose" },
  ] });
  const page = await open(t, { items: [it] }); if (!page) return;
  const a = card(page, it).locator('label.opt[for="o-diff-q-a"]');
  assert.equal(await a.locator(".how.dif").count(), 0, "how equals the others and is still marked");
  assert.equal(await a.locator(".gain.dif").count(), 1);
  assert.equal(await a.locator(".dif").count(), 1, "an unknown name marked something");
});

test("an item whose differs all drop, or that has none, shows no legend", async (t) => {
  const it = diffItem({ options: [
    { key: "a", label: "Alpha", how: "h", gain: "g", lose: "l", differs: ["how"] }, { key: "b", label: "Beta", how: "h", gain: "g", lose: "l" }] });
  const page = await open(t, { items: [it, DECISION] }); if (!page) return;
  assert.equal(await page.locator(".difkey, .ne").count(), 0);
});

test("a named picture marks the frame and the View bar and says so in its label; picture on an option with no picture is ignored", async (t) => {
  const it = looks("diff-pic", 71, [{ slug: "o-a", label: "A" }, { slug: "o-b", label: "B" }]);
  it.options[0].differs = ["picture"]; it.options[1].differs = ["picture"]; delete it.options[1].design;
  const page = await open(t, { items: [it], designData: { "o-a": lateRow("one"), "o-b": lateRow("two") } }); if (!page) return;
  const pa = card(page, it).locator('label.opt[for="o-diff-pic-a"] .opic');
  assert.equal(await pa.evaluate((e) => e.classList.contains("dif")), true);
  assert.equal(await pa.locator(".view .ne").textContent(), "≠");
  assert.match(await pa.getAttribute("aria-label"), /^View Layout A full screen\. Its picture sets this option apart$/);
  assert.equal(await card(page, it).locator('label.opt[for="o-diff-pic-b"] .dif').count(), 0, "a picture mark on an option with no picture");
});

const STATE_MOCK = '<!doctype html><body style="margin:0"><div data-state="default">d</div><div data-state="late-package" id="late-row">late</div></body>';
const stateItem = (id, n, states, over = {}) => looks(id, n, [
  { slug: "s-a", label: "A", ...(states[0] ? { state: states[0] } : {}) }, { slug: "s-b", label: "B", ...(states[1] ? { state: states[1] } : {}) }], over);
const STATE_DATA = { "s-a": STATE_MOCK, "s-b": STATE_MOCK.replace(">late<", ">late two<") };
const stateOpts = (it) => it.options.forEach((o, i) => { o.design = i ? "s-b" : "s-a"; });

test("a design with a state opens its mockup at that state, in the card frame and in the viewer", async (t) => {
  const it = stateItem("st-frame", 72, ["late-package", "late-package"]); stateOpts(it);
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  const fr = await (await page.locator(optFrame(it, "a")).elementHandle()).contentFrame();
  await fr.waitForLoadState();
  assert.equal(await fr.evaluate(() => location.hash), "#s=late-package");
  const src = await page.locator(optFrame(it, "a")).getAttribute("srcdoc");
  assert.ok(src.search(/<!doctype/i) < src.search(/location\.hash/), "the state script sits before the doctype and puts the frame in quirks mode");
});

test("the viewer names the state in its title and offers Open this state, which opens the blob at #s=<state>", async (t) => {
  const it = stateItem("st-view", 73, ["late-package", null]); stateOpts(it);
  const page = await open(t, { items: [it], designData: STATE_DATA }); if (!page) return;
  await page.evaluate(() => { window.__opened = []; window.open = (u) => { window.__opened.push(String(u)); return null; }; });
  await card(page, it).locator('label.opt[for="o-st-view-a"] .opic').click();
  assert.equal(await page.locator("#dTitle").textContent(), "Layout A (Phone), late package");
  assert.equal(await page.locator("#dCap").textContent(), "Layout A (Phone), late package");
  assert.equal(await page.locator("#dFull .lg").textContent(), "Open this state");
  assert.equal(await page.locator("#dFull").getAttribute("aria-label"), "Open the late package state of the full mockup in a new tab");
  await page.click("#dFull");
  const u = await page.evaluate(() => window.__opened);
  assert.equal(u.length, 1); assert.match(u[0], /^blob:.*#s=late-package$/);
  await page.click("#dNext");
  assert.equal(await page.locator("#dTitle").textContent(), "Layout B (Phone)", "no state: no suffix");
  assert.equal(await page.locator("#dFull .lg").textContent(), "Open full size");
  assert.equal(await page.locator("#dFull").getAttribute("aria-label"), "Open full size");
});

test("a state the mockup does not draw blocks the item and names the option; a drawn state, or two states of one slug and focus, do not", async (t) => {
  const bad = stateItem("st-bad", 74, [null, "no-such-state"]); stateOpts(bad);
  let page = await open(t, { items: [bad], designData: STATE_DATA }); if (!page) return;
  assert.equal(await ALERT(page, bad).count(), 1, "no alert");
  assert.match(await ALERT(page, bad).textContent(), /option B names a state its mockup does not draw\. Ask the session to fix item 74\./);
  await page.evaluate(() => { setDraft(byId("st-bad"), { choice: "a", auto: true }); render(); });
  assert.equal(await page.locator("#send").isDisabled(), true, "Send is not refused");
  const ok = stateItem("st-ok", 75, ["late-package", "default"]);
  ok.designs = ok.designs.map((d, i) => ({ ...d, slug: "s-a", option: "ab"[i] })); ok.options.forEach((o) => { o.design = "s-a"; });
  page = await open(t, { items: [ok], designData: STATE_DATA }); if (!page) return;
  assert.equal(await ALERT(page, ok).count(), 0, "two states of one slug are refused as one picture");
  const same = stateItem("st-same", 76, ["late-package", "late-package"]);
  same.designs = same.designs.map((d, i) => ({ ...d, slug: "s-a", option: "ab"[i] })); same.options.forEach((o) => { o.design = "s-a"; });
  page = await open(t, { items: [same], designData: STATE_DATA }); if (!page) return;
  assert.match(await ALERT(page, same).textContent(), /A and B.*share one picture/s);
});

const shortChip = (page, it) => page.locator(`#c-${it.id}`);
test("the wide rail chip shows the short title; no or an over-long short falls back to the title; the title stays in full on the chip", async (t) => {
  const items = [mk("sh-a", 80, { title: "A very long question title for the rail", short: "Rail name" }), mk("sh-b", 81, { title: "Second long question title here" }), mk("sh-c", 82, { title: "Third long question title here", short: "x".repeat(25) })];
  const page = await open(t, { items }); if (!page) return;
  assert.equal(await shortChip(page, items[0]).locator(".nt").textContent(), "Rail name");
  assert.equal(await shortChip(page, items[1]).locator(".nt").textContent(), "Second long question title here");
  assert.equal(await shortChip(page, items[2]).locator(".nt").textContent(), "Third long question title here");
  assert.equal(await shortChip(page, items[0]).getAttribute("title"), "A very long question title for the rail");
  assert.match(await shortChip(page, items[0]).getAttribute("aria-label"), /^No\. 80, A very long question title for the rail, /);
});
